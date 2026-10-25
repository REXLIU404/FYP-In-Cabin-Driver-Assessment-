"""Task 7 - fault_events: every failed ``/infer`` attempt is observable, and the record
outlives the session it failed in.

None of these tests needs the trained model files. ``live`` installs a REAL
``TrainedProvider`` instance whose onnxruntime session and XGBoost booster are
hand-written fakes, so the real ``trained.py`` error handling, the real routes and
the real SQLite are exercised; only the weights are missing.

Every expected value is a literal: no constant is imported from the implementation
to build an expectation.
"""
import base64
import io
import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from fractions import Fraction
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from fastapi.exceptions import ResponseValidationError
from fastapi.testclient import TestClient
from PIL import Image
from pydantic import ValidationError
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from test_migration import make_legacy_engine

FAULT_FIELDS = {"id", "session_id", "request_id", "attempt_index", "origin", "error_category",
                "http_status", "retryable", "detail", "recovery_status",
                "recovered_by_request_id", "occurred_at", "recovered_at"}

TELEMETRY = {"speed_kmph": 52, "accel_x": .7, "accel_y": .2, "brake_pressure": 20,
             "steering_angle": 7.5, "throttle": 40, "lane_deviation": .21, "headway_distance": 18}


# --- fakes ---------------------------------------------------------------------------
class FakeVision:
    """Stands in for ``onnxruntime.InferenceSession``: ``run(None, feeds) -> [logits]``."""

    def __init__(self):
        self.calls = 0
        self.fail = None
        self.output = np.array([[3.0] + [0.0] * 9], dtype=np.float32)

    def run(self, names, feeds):
        self.calls += 1
        if self.fail is not None:
            raise self.fail
        return [self.output]


class FakeBooster:
    """Stands in for ``xgboost.Booster``: ``predict(matrix, iteration_range=..., pred_contribs=...)``.
    ``fail`` is raised by every call, ``contribs_fail`` only by the ``pred_contribs=True`` one (the
    TreeSHAP call: (1, 3 classes, 8 features + bias)); ``output`` / ``contribs_output`` are what each returns."""

    def __init__(self):
        self.calls = 0
        self.fail = None
        self.contribs_fail = None
        self.output = np.array([[0.6, 0.3, 0.1]], dtype=np.float32)
        self.contribs_output = np.zeros((1, 3, 9), dtype=np.float32)

    def predict(self, matrix, iteration_range=None, pred_contribs=False):
        self.calls += 1
        if self.fail is not None:
            raise self.fail
        if pred_contribs:
            if self.contribs_fail is not None:
                raise self.contribs_fail
            return self.contribs_output
        return self.output


FAKE_XGB = SimpleNamespace(DMatrix=lambda data, feature_names=None: SimpleNamespace(data=data))


def build_provider(vision, booster):
    from app.providers.trained import TrainedProvider
    from app.schemas import TelemetryFeatures
    provider = object.__new__(TrainedProvider)  # skip __init__: it loads the weights
    provider.xgb = FAKE_XGB
    provider.labels = ["safe_driving"] + [f"distracted_{i}" for i in range(1, 10)]
    provider.features = list(TelemetryFeatures.model_fields)
    provider.input_name = "input"
    provider.vision = vision
    provider.telemetry = booster
    provider.iteration_end = 7
    provider.info = {"provider": provider.name, "vision": {"sha256": "a" * 64}, "telemetry": {"sha256": "b" * 64}}
    return provider


def image_data(color=(80, 130, 180)):
    buffer = io.BytesIO()
    Image.new("RGB", (64, 48), color).save(buffer, format="JPEG")
    return base64.b64encode(buffer.getvalue()).decode()


def make_payload(request_id, *, image=True, telemetry=True, at=None):
    stamp = (at or datetime.now(timezone.utc)).isoformat()
    body = {"request_id": request_id}
    if image:
        body.update(image_base64=image_data(), captured_at=stamp)
    if telemetry:
        body.update(telemetry_features=dict(TELEMETRY), telemetry_timestamp=stamp,
                    telemetry_source="prepared_replay")
    return body


# --- fixture and helpers --------------------------------------------------------------
@pytest.fixture
def live(api_factory, tmp_path, monkeypatch):
    """A live session on a tmp database, a fake-weights provider, the sink in tmp_path.
    ``client`` returns responses; ``strict`` re-raises what the app raised."""
    from app import cache
    from app.main import app
    from app.providers import trained

    vision, booster = FakeVision(), FakeBooster()
    monkeypatch.setattr(trained, "_provider", build_provider(vision, booster))
    client, strict = TestClient(app, raise_server_exceptions=False), TestClient(app)
    env = SimpleNamespace(client=client, strict=strict, sid=f"live-{tmp_path.name}", vision=vision,
                          booster=booster, factory=api_factory, sink_path=tmp_path / "fault_events.log")
    created = client.post("/api/sessions", json={"session_id": env.sid, "operation_mode": "LIVE_MODEL_RUNTIME"})
    assert created.status_code == 201, created.text
    try:
        yield env
    finally:
        client.close()
        strict.close()
        cache._latest.clear()


def infer(env, body, *, attempt=None, sid=None, client=None):
    headers = {} if attempt is None else {"X-Attempt-Index": str(attempt)}
    return (client or env.client).post(f"/api/sessions/{sid or env.sid}/infer", json=body, headers=headers)


def rows(env, sql, **params):
    with env.factory() as db:
        return [dict(r) for r in db.execute(text(sql), params).mappings().all()]


def scalar(env, sql, **params):
    with env.factory() as db:
        return db.execute(text(sql), params).scalar()


def faults_of(env, sid=None):
    response = env.client.get("/api/faults", params={"session_id": sid or env.sid})
    assert response.status_code == 200, response.text
    return response.json()


def record_count(env, sid=None):
    return scalar(env, "SELECT COUNT(*) FROM inference_records WHERE session_id = :s", s=sid or env.sid)


def total_windows(env):
    return env.client.get(f"/api/sessions/{env.sid}").json()["total_windows"]


def open_faults(env, sid=None):
    return env.client.get(f"/api/sessions/{sid or env.sid}/system-status").json()["open_fault_events"]


def sink_lines(env):
    if not env.sink_path.exists():
        return []
    return [json.loads(line) for line in env.sink_path.read_text().splitlines()]


def bad_frame(request_id):
    return {**make_payload(request_id), "image_base64": "not-base64"}


def commit_fails_once_with(message):
    """A ``Session.commit`` replacement: the first call (the request's own commit) raises."""
    real = Session.commit
    calls = []

    def commit(self):
        calls.append(1)
        if len(calls) == 1:
            raise OperationalError("COMMIT", {}, Exception(message))
        return real(self)
    return commit, calls


# --- ST-FAIL-02 -------------------------------------------------------------------------
def test_st_fail_02_bad_frame_is_one_open_non_retryable_fault(live):
    body = bad_frame("bad-frame-1")
    response = infer(live, body)
    assert response.status_code == 422
    assert total_windows(live) == 0
    assert live.client.get(f"/api/sessions/{live.sid}/risk/latest").status_code == 404

    [row] = faults_of(live)
    assert row["session_id"] == live.sid
    assert row["request_id"] == "bad-frame-1"
    assert row["attempt_index"] == 1
    assert row["error_category"] == "input_validation"
    assert row["origin"] == "request_validation"
    assert row["http_status"] == 422
    assert row["retryable"] is False
    assert row["recovery_status"] == "open"
    assert row["recovered_by_request_id"] is None and row["recovered_at"] is None

    # The same attempt delivered again is the same fault, not a second one.
    assert infer(live, body).status_code == 422
    assert len(faults_of(live)) == 1
    assert record_count(live) == 0


def test_st_fail_02_missing_models_are_503_and_not_retryable(live, monkeypatch, tmp_path):
    from app.providers import trained
    empty = tmp_path / "no-model-files"
    empty.mkdir()
    monkeypatch.setattr(trained, "_provider", None)
    monkeypatch.setattr(trained.settings, "model_root", empty)

    assert infer(live, make_payload("no-models-1")).status_code == 503
    [row] = faults_of(live)
    assert row["request_id"] == "no-models-1"
    assert row["error_category"] == "models_unavailable"
    assert row["origin"] == "model_load"
    assert row["http_status"] == 503
    assert row["retryable"] is False
    assert total_windows(live) == 0


# --- ST-FAIL-04 --------------------------------------------------------------------------
def test_st_fail_04_missing_models_and_a_runtime_error_are_told_apart(live, monkeypatch, tmp_path):
    from app.providers import trained
    live.vision.fail = RuntimeError("onnxruntime: Non-zero status code returned while running Conv node")
    runtime = infer(live, make_payload("runtime-1"))
    assert runtime.status_code == 500
    assert runtime.json() == {"detail": "Vision model failed during inference"}

    empty = tmp_path / "no-model-files"
    empty.mkdir()
    monkeypatch.setattr(trained, "_provider", None)
    monkeypatch.setattr(trained.settings, "model_root", empty)
    unavailable = infer(live, make_payload("unavailable-1"))
    assert unavailable.status_code == 503

    by_request = {r["request_id"]: r for r in faults_of(live)}
    assert set(by_request) == {"runtime-1", "unavailable-1"}  # one row each, no more
    assert len(faults_of(live)) == 2
    assert (by_request["runtime-1"]["error_category"], by_request["runtime-1"]["http_status"],
            by_request["runtime-1"]["retryable"]) == ("model_runtime", 500, True)
    assert (by_request["unavailable-1"]["error_category"], by_request["unavailable-1"]["http_status"],
            by_request["unavailable-1"]["retryable"]) == ("models_unavailable", 503, False)
    assert "RuntimeError: onnxruntime: Non-zero status code" in by_request["runtime-1"]["detail"]
    assert record_count(live) == 0


# --- ST-FAIL-03 --------------------------------------------------------------------------
def test_st_fail_03_commit_failure_is_a_storage_fault_and_the_original_error_surfaces(live, monkeypatch):
    commit, calls = commit_fails_once_with("disk I/O error")
    with monkeypatch.context() as patched:
        patched.setattr(Session, "commit", commit)
        # What the application raised, untouched: the storage error, not the fault logger's.
        with pytest.raises(OperationalError) as caught:
            infer(live, make_payload("storage-1"), client=live.strict)
        assert caught.value.orig.args == ("disk I/O error",)

        # What a client sees when the server swallows it: the unchanged bare 500.
        calls.clear()
        response = infer(live, make_payload("storage-2"))
        assert response.status_code == 500
        assert response.text == "Internal Server Error"

    assert total_windows(live) == 0
    assert record_count(live) == 0
    stored = {r["request_id"]: r for r in faults_of(live)}
    assert set(stored) == {"storage-1", "storage-2"}
    for row in stored.values():
        assert (row["error_category"], row["origin"], row["http_status"], row["retryable"]) == (
            "storage", "storage", 500, True)
        assert "disk I/O error" in row["detail"]
    # The independent file sink holds the event too.
    assert {(line["request_id"], line["error_category"], line["db_written"]) for line in sink_lines(live)} == {
        ("storage-1", "storage", True), ("storage-2", "storage", True)}


def test_st_fail_03_fault_logger_failure_never_masks_the_original_error(live, monkeypatch):
    calls = []

    def commit(self):
        calls.append(1)
        if len(calls) == 1:
            raise OperationalError("COMMIT", {}, Exception("disk I/O error"))
        raise RuntimeError("fault logger commit failed")  # the fault session's own commit

    with monkeypatch.context() as patched:
        patched.setattr(Session, "commit", commit)
        with pytest.raises(OperationalError) as caught:
            infer(live, make_payload("storage-3"), client=live.strict)
        assert caught.value.orig.args == ("disk I/O error",)  # not RuntimeError, not wrapped

        calls.clear()
        response = infer(live, make_payload("storage-4"))
        assert (response.status_code, response.text) == (500, "Internal Server Error")

    # The database could not be written at all: the sink line is the persistent outcome.
    assert faults_of(live) == []
    assert {(line["request_id"], line["db_written"]) for line in sink_lines(live)} == {
        ("storage-3", False), ("storage-4", False)}


def test_st_fail_03_a_broken_sink_never_masks_the_original_error(live, monkeypatch, tmp_path):
    from app.faults import FaultSink, get_fault_sink
    from app.main import app
    blocker = tmp_path / "a-file-not-a-directory"
    blocker.write_text("x")
    app.dependency_overrides[get_fault_sink] = lambda: FaultSink(blocker / "fault_events.log")  # mkdir fails
    commit, _ = commit_fails_once_with("disk I/O error")
    with monkeypatch.context() as patched:
        patched.setattr(Session, "commit", commit)
        with pytest.raises(OperationalError) as caught:
            infer(live, make_payload("storage-5"), client=live.strict)
        assert caught.value.orig.args == ("disk I/O error",)
    assert [r["request_id"] for r in faults_of(live)] == ["storage-5"]  # the database row survived


# --- ST-FAIL-01 --------------------------------------------------------------------------
def test_st_fail_01_faults_outlive_the_session(live):
    assert infer(live, make_payload("alive-1")).status_code == 201
    assert infer(live, bad_frame("gone-1")).status_code == 422
    assert infer(live, bad_frame("gone-2")).status_code == 422
    before = faults_of(live)
    assert [r["request_id"] for r in before] == ["gone-1", "gone-2"]
    assert record_count(live) == 1

    assert live.client.delete(f"/api/sessions/{live.sid}").status_code == 204
    assert live.client.get(f"/api/sessions/{live.sid}").status_code == 404

    assert faults_of(live) == before  # same rows, same occurred_at
    assert record_count(live) == 0  # the cascade did remove the session's records
    status = live.client.get(f"/api/sessions/{live.sid}/system-status").json()
    assert (status["exists"], status["open_fault_events"]) == (False, 2)


# --- ST-RECOVER-01 -----------------------------------------------------------------------
def test_st_recover_01_failures_are_recovered_by_a_new_committed_record(live):
    first = make_payload("rec-1")
    assert infer(live, first).status_code == 201
    second = make_payload("rec-2")
    live.vision.fail = RuntimeError("transient onnxruntime failure")
    for attempt in (1, 2, 3):
        assert infer(live, second, attempt=attempt).status_code == 500

    failed = faults_of(live)
    assert [r["attempt_index"] for r in failed] == [1, 2, 3]
    assert {r["request_id"] for r in failed} == {"rec-2"}
    assert {(r["error_category"], r["origin"], r["http_status"], r["retryable"], r["recovery_status"])
            for r in failed} == {("model_runtime", "vision_model", 500, True, "open")}
    assert open_faults(live) == 3
    assert record_count(live) == 1  # failures wrote no record

    live.vision.fail = None
    # The 4th delivery reuses the request id and payload, as Task 8's retry() will. The
    # server keeps no attempt budget: attempt 4 is accepted like any other.
    fourth = infer(live, second, attempt=4)
    assert fourth.status_code == 201, fourth.text

    recovered = faults_of(live)
    assert [r["attempt_index"] for r in recovered] == [1, 2, 3]
    assert {r["recovery_status"] for r in recovered} == {"recovered"}
    assert {r["recovered_by_request_id"] for r in recovered} == {"rec-2"}
    assert all(r["recovered_at"] for r in recovered)
    assert [r["occurred_at"] for r in recovered] == [r["occurred_at"] for r in failed]
    assert open_faults(live) == 0
    assert record_count(live) == 2  # not 3 failures + 2: exactly the two successes

    # A replay of that success is still a replay: same body, nothing new stored.
    replay = infer(live, second, attempt=5)
    assert (replay.status_code, replay.json()) == (201, fourth.json())
    assert record_count(live) == 2


def test_an_idempotent_replay_is_not_a_recovery(live):
    done = make_payload("replay-done")
    assert infer(live, done).status_code == 201
    live.vision.fail = RuntimeError("transient")
    assert infer(live, make_payload("replay-broken")).status_code == 500
    live.vision.fail = None

    assert infer(live, done, attempt=2).status_code == 201  # a replay of an old success
    [row] = faults_of(live)
    assert (row["recovery_status"], row["recovered_by_request_id"]) == ("open", None)
    assert open_faults(live) == 1
    assert record_count(live) == 1


def test_recovery_is_scoped_to_the_session(live):
    other = f"other-{live.sid}"
    assert live.client.post("/api/sessions", json={"session_id": other,
                                                   "operation_mode": "LIVE_MODEL_RUNTIME"}).status_code == 201
    assert infer(live, bad_frame("scoped-bad")).status_code == 422
    assert infer(live, make_payload("scoped-good"), sid=other).status_code == 201
    assert open_faults(live) == 1  # another session's success recovers nothing here
    assert open_faults(live, sid=other) == 0


# --- IT-FAULT-ORT: native runtime errors, no weights needed -------------------------------
NAN_LOGITS = np.array([[np.nan] + [0.0] * 9], dtype=np.float32)
INF_LOGITS = np.array([[np.inf] + [0.0] * 9], dtype=np.float32)
SHORT_LOGITS = np.zeros((1, 7), dtype=np.float32)
NAN_PROBS = np.array([[np.nan, 0.5, 0.5]], dtype=np.float32)
SHORT_PROBS = np.array([[0.5, 0.5]], dtype=np.float32)
NAN_CONTRIBS = np.full((1, 3, 9), np.nan, dtype=np.float32)
INF_CONTRIBS = np.full((1, 3, 9), np.inf, dtype=np.float32)
SHORT_CONTRIBS = np.zeros((1, 3, 8), dtype=np.float32)  # the bias column is missing


@pytest.mark.parametrize("break_it, origin, detail", [
    (lambda e: setattr(e.vision, "fail", RuntimeError("onnxruntime: kernel crashed")),
     "vision_model", "Vision model failed during inference"),
    (lambda e: setattr(e.booster, "fail", ValueError("xgboost: feature_names mismatch")),
     "telemetry_model", "Telemetry model failed during inference"),
    (lambda e: setattr(e.vision, "output", NAN_LOGITS),
     "vision_model", "Vision model produced non-finite or wrongly shaped output"),
    (lambda e: setattr(e.vision, "output", INF_LOGITS),
     "vision_model", "Vision model produced non-finite or wrongly shaped output"),
    (lambda e: setattr(e.vision, "output", SHORT_LOGITS),
     "vision_model", "Vision model produced non-finite or wrongly shaped output"),
    (lambda e: setattr(e.booster, "output", NAN_PROBS),
     "telemetry_model", "Telemetry model produced non-finite or wrongly shaped output"),
    (lambda e: setattr(e.booster, "output", SHORT_PROBS),
     "telemetry_model", "Telemetry model produced non-finite or wrongly shaped output"),
    # TELEMETRY-CONTRIBUTIONS: the TreeSHAP call fails like the probability call does - the same
    # category and origin, the whole request, no record.
    (lambda e: setattr(e.booster, "contribs_fail", ValueError("xgboost: pred_contribs failed")),
     "telemetry_model", "Telemetry model failed during inference"),
    (lambda e: setattr(e.booster, "contribs_output", NAN_CONTRIBS),
     "telemetry_model", "Telemetry model produced non-finite or wrongly shaped feature contributions"),
    (lambda e: setattr(e.booster, "contribs_output", INF_CONTRIBS),
     "telemetry_model", "Telemetry model produced non-finite or wrongly shaped feature contributions"),
    (lambda e: setattr(e.booster, "contribs_output", SHORT_CONTRIBS),
     "telemetry_model", "Telemetry model produced non-finite or wrongly shaped feature contributions"),
], ids=["ort-raises", "xgboost-raises", "vision-nan", "vision-inf", "vision-shape", "telemetry-nan",
        "telemetry-shape", "contribs-raises", "contribs-nan", "contribs-inf", "contribs-shape"])
def test_it_fault_ort_runtime_failure_is_500_model_runtime(live, break_it, origin, detail):
    break_it(live)
    response = infer(live, make_payload("ort-1"))
    assert (response.status_code, response.json()) == (500, {"detail": detail})
    [row] = faults_of(live)
    assert (row["request_id"], row["error_category"], row["origin"], row["http_status"], row["retryable"]) == (
        "ort-1", "model_runtime", origin, 500, True)
    assert total_windows(live) == 0
    assert record_count(live) == 0


# --- IT-FAULT-SINGLE-BRANCH --------------------------------------------------------------
@pytest.mark.parametrize("failing, origin", [("vision", "vision_model"), ("telemetry", "telemetry_model")])
def test_it_fault_single_branch_failure_fails_the_whole_request(live, failing, origin):
    (live.vision if failing == "vision" else live.booster).fail = RuntimeError("branch down")
    body = make_payload("branch-1")  # both branches present, exactly one raises
    assert infer(live, body).status_code == 500

    [row] = faults_of(live)
    assert (row["error_category"], row["origin"], row["retryable"]) == ("model_runtime", origin, True)
    assert record_count(live) == 0 and total_windows(live) == 0
    assert live.client.get(f"/api/sessions/{live.sid}/risk/latest").status_code == 404
    assert live.client.get(f"/api/sessions/{live.sid}/windows").json() == []  # no degraded window

    # The identical payload is fine once the branch works: the 500 was the branch's doing.
    (live.vision if failing == "vision" else live.booster).fail = None
    ok = infer(live, body, attempt=2)
    assert ok.status_code == 201
    assert ok.json()["modality_freshness"] == {"vision": "fresh", "telemetry": "fresh"}


# --- IT-FAULT-INTEGRITY ------------------------------------------------------------------
def blind_to_the_twin(monkeypatch):
    """The duplicate-request pre-checks miss the twin (the race window); the real unique
    index on (session_id, request_id) then fires at commit. Returns the call log."""
    from app.routers import windows
    real, calls = windows._existing_request, []

    def existing(db, sid, request_id, digest):
        calls.append(1)
        return None if len(calls) <= 2 else real(db, sid, request_id, digest)
    monkeypatch.setattr(windows, "_existing_request", existing)
    return calls


def test_it_fault_integrity_a_concurrent_twin_with_the_same_input_returns_the_stored_record(live, monkeypatch):
    body = make_payload("twin-1")
    winner = infer(live, body)
    assert winner.status_code == 201
    calls = blind_to_the_twin(monkeypatch)

    loser = infer(live, body)
    assert (loser.status_code, loser.json()) == (201, winner.json())
    assert len(calls) == 3  # two blind checks, then the re-read after the IntegrityError
    assert record_count(live) == 1
    assert faults_of(live) == []


def test_it_fault_integrity_a_concurrent_twin_with_different_input_is_409(live, monkeypatch):
    body = make_payload("twin-2")
    assert infer(live, body).status_code == 201
    calls = blind_to_the_twin(monkeypatch)

    loser = infer(live, {**body, "image_base64": image_data((255, 0, 0))})
    assert (loser.status_code, loser.json()) == (409, {"detail": "request_id already used for different input"})
    assert len(calls) == 3
    assert record_count(live) == 1
    [row] = faults_of(live)
    assert (row["error_category"], row["origin"], row["http_status"], row["retryable"]) == (
        "idempotency_conflict", "session", 409, False)


# --- IT-OUTCOME-01 -----------------------------------------------------------------------
def test_it_outcome_01_every_attempt_has_exactly_one_persistent_outcome(live, monkeypatch, tmp_path):
    """Eligible attempt = every POST /api/sessions/{id}/infer that reaches the application,
    schema-invalid ones included. The denominators come from the script below (its own list
    of requests and the statuses it got back), never from what the database says it stored."""
    from app.providers import trained
    replay_sid = f"replay-mode-{live.sid}"
    assert live.client.post("/api/sessions", json={"session_id": replay_sid}).status_code == 201
    empty_models = tmp_path / "no-model-files"
    empty_models.mkdir()
    ok1 = make_payload("ok-1")

    def storage_down(body):
        with monkeypatch.context() as m:  # no commit works at all: the database is unwritable
            def commit(self):
                raise OperationalError("COMMIT", {}, Exception("database is unwritable"))
            m.setattr(Session, "commit", commit)
            return infer(live, body)

    def models_gone(body):
        with monkeypatch.context() as m:
            m.setattr(trained, "_provider", None)
            m.setattr(trained.settings, "model_root", empty_models)
            return infer(live, body)

    def runtime_failure(branch, body):
        target = live.vision if branch == "vision" else live.booster
        target.fail = RuntimeError("runtime failure")
        try:
            return infer(live, body)
        finally:
            target.fail = None

    long_ago = datetime(2000, 1, 1, tzinfo=timezone.utc)
    header_zero = {"X-Attempt-Index": "0"}
    sid = live.sid
    # (label, request id, send, expected status, expected kind, expected fault row)
    # Kinds: new_record | replay | fault | sink. A fault row is
    # (error_category, origin, http_status, retryable, session_id, attempt_index).
    script = [
        ("success", "ok-1", lambda: infer(live, ok1), 201, "new_record", None),
        ("idempotent replay, attempt 2", "ok-1", lambda: infer(live, ok1, attempt=2), 201, "replay", None),
        ("schema 422 (unknown field)", "schema-1",
         lambda: infer(live, {"request_id": "schema-1", "unexpected": True}), 422, "fault",
         ("input_validation", "request_validation", 422, False, sid, 1)),
        ("schema 422 (no request_id)", None, lambda: infer(live, {}), 422, "fault",
         ("input_validation", "request_validation", 422, False, sid, 1)),
        ("bad frame 422", "bad-image-1", lambda: infer(live, bad_frame("bad-image-1")), 422, "fault",
         ("input_validation", "request_validation", 422, False, sid, 1)),
        ("session not found 404", "ghost-1",
         lambda: infer(live, make_payload("ghost-1"), sid="no-such-session"), 404, "fault",
         ("not_found", "session", 404, False, "no-such-session", 1)),
        ("wrong session mode 409", "mode-1",
         lambda: infer(live, make_payload("mode-1"), sid=replay_sid), 409, "fault",
         ("mode_conflict", "session", 409, False, replay_sid, 1)),
        ("hash conflict 409", "ok-1",
         lambda: infer(live, {**ok1, "image_base64": image_data((255, 0, 0))}), 409, "fault",
         ("idempotency_conflict", "session", 409, False, sid, 1)),
        ("out-of-order timestamp 409", "old-1",
         lambda: infer(live, make_payload("old-1", at=long_ago)), 409, "fault",
         ("out_of_order_evidence", "session", 409, False, sid, 1)),
        ("model runtime 500", "runtime-1",
         lambda: runtime_failure("vision", make_payload("runtime-1")), 500, "fault",
         ("model_runtime", "vision_model", 500, True, sid, 1)),
        ("models unavailable 503", "models-1", lambda: models_gone(make_payload("models-1")), 503, "fault",
         ("models_unavailable", "model_load", 503, False, sid, 1)),
        ("storage failure, database unwritable", "storage-1",
         lambda: storage_down(make_payload("storage-1")), 500, "sink", None),
        ("success after the failures", "ok-2", lambda: infer(live, make_payload("ok-2")), 201, "new_record", None),
        ("telemetry-only success", "ok-3",
         lambda: infer(live, make_payload("ok-3", image=False)), 201, "new_record", None),
        ("invalid attempt header 422", "header-1",
         lambda: live.client.post(f"/api/sessions/{sid}/infer", json=make_payload("header-1"),
                                  headers=header_zero), 422, "fault",
         ("input_validation", "request_validation", 422, False, sid, None)),
        ("telemetry runtime 500", "runtime-2",
         lambda: runtime_failure("telemetry", make_payload("runtime-2")), 500, "fault",
         ("model_runtime", "telemetry_model", 500, True, sid, 1)),
    ]

    def totals():
        return (scalar(live, "SELECT COUNT(*) FROM inference_records"),
                scalar(live, "SELECT COUNT(*) FROM fault_events"), len(sink_lines(live)))

    results = []  # (request id, status, persistent outcomes found for this attempt)
    for label, request_id, send, expected_status, expected_kind, expected_fault in script:
        records_before, faults_before, sink_before = totals()
        response = send()
        records_after, faults_after, sink_after = totals()
        new_records = records_after - records_before
        new_faults = faults_after - faults_before
        new_sink = sink_after - sink_before
        # A replay answers 201 from a record that already exists and writes nothing.
        replayed = (response.status_code == 201 and new_records == 0 and new_faults == 0
                    and scalar(live, "SELECT COUNT(*) FROM inference_records WHERE request_id = :r",
                               r=request_id) == 1)
        # The sink line is THE outcome only when the database holds nothing for the attempt.
        sink_only = new_records == 0 and new_faults == 0 and not replayed and new_sink == 1
        outcomes = new_records + new_faults + int(replayed) + int(sink_only)
        kind = ("new_record" if new_records else "fault" if new_faults else "replay" if replayed
                else "sink" if sink_only else "none")
        assert response.status_code == expected_status, label
        assert kind == expected_kind, label
        assert outcomes == 1, label
        if expected_fault is not None:
            [row] = rows(live, "SELECT * FROM fault_events ORDER BY id DESC LIMIT 1")
            assert (row["error_category"], row["origin"], row["http_status"], bool(row["retryable"]),
                    row["session_id"], row["attempt_index"]) == expected_fault, label
            assert row["request_id"] == request_id, label
        results.append((request_id, response.status_code, outcomes))

    # (b) outcome-recording rate: attempts with a persistent outcome / every eligible attempt.
    eligible = len(results)
    assert eligible == 16
    assert Fraction(sum(1 for _, _, outcomes in results if outcomes == 1), eligible) == 1
    # (a) successful-prediction persistence: distinct request ids that got a 201 and own a record.
    succeeded = {request_id for request_id, status, _ in results if status == 201}
    assert succeeded == {"ok-1", "ok-2", "ok-3"}
    persisted = {r["request_id"] for r in rows(live, "SELECT request_id FROM inference_records")}
    assert Fraction(len(succeeded & persisted), len(succeeded)) == 1

    # The books balance: 3 records, 11 fault rows, 12 sink lines (the 11 plus the unwritable-database one).
    assert scalar(live, "SELECT COUNT(*) FROM inference_records") == 3
    assert scalar(live, "SELECT COUNT(*) FROM fault_events") == 11
    assert len(sink_lines(live)) == 12
    assert [line["db_written"] for line in sink_lines(live)].count(False) == 1
    # ok-2 recovered the seven faults this session had before it; the two after it, and the
    # faults of the two other sessions, are still open.
    assert open_faults(live) == 2
    assert open_faults(live, sid="no-such-session") == 1
    assert open_faults(live, sid=replay_sid) == 1


# --- interface -----------------------------------------------------------------------------
def test_get_faults_returns_the_contract_fields_oldest_first(live):
    insert = ("INSERT INTO fault_events (session_id, request_id, attempt_index, origin, error_category, "
              "http_status, retryable, detail, recovery_status, occurred_at) VALUES "
              "(:s, :r, 1, 'storage', 'storage', 500, 1, 'd', 'open', :t)")
    with live.factory() as db:
        for session_id, request_id, stamp in [(live.sid, "late", "2026-10-14T10:00:05.000000+00:00"),
                                              (live.sid, "early-a", "2026-10-14T10:00:01.000000+00:00"),
                                              ("elsewhere", "other-session", "2026-10-14T10:00:03.000000+00:00"),
                                              (live.sid, "early-b", "2026-10-14T10:00:01.000000+00:00")]:
            db.execute(text(insert), {"s": session_id, "r": request_id, "t": stamp})
        db.commit()

    mine = faults_of(live)
    assert [r["request_id"] for r in mine] == ["early-a", "early-b", "late"]  # occurred_at, then id
    assert [r["id"] for r in mine] == [2, 4, 1]
    assert set(mine[0]) == FAULT_FIELDS
    assert mine[0]["retryable"] is True and mine[0]["attempt_index"] == 1
    everything = live.client.get("/api/faults").json()
    assert [r["request_id"] for r in everything] == ["early-a", "early-b", "other-session", "late"]
    assert [r["request_id"] for r in live.client.get("/api/faults", params={"limit": 2}).json()] == ["early-a", "early-b"]
    assert live.client.get("/api/faults", params={"limit": 0}).status_code == 422
    assert live.client.get("/api/faults", params={"session_id": "nobody"}).json() == []


def test_system_status_counts_open_fault_events(live):
    assert open_faults(live) == 0
    assert infer(live, bad_frame("count-1")).status_code == 422
    assert infer(live, bad_frame("count-2")).status_code == 422
    status = live.client.get(f"/api/sessions/{live.sid}/system-status").json()
    assert status["open_fault_events"] == 2


def test_attempt_index_is_told_by_the_client_and_is_not_part_of_the_request_hash(live):
    live.vision.fail = RuntimeError("down")
    body = make_payload("attempt-1")
    infer(live, body)                # no header: attempt 1
    infer(live, body, attempt=2)
    infer(live, body, attempt=99)    # no retry budget on the server (only the 1000 sanity bound, tested below)
    assert [r["attempt_index"] for r in faults_of(live)] == [1, 2, 99]

    live.vision.fail = None
    stored = infer(live, body, attempt=3)
    assert stored.status_code == 201
    # The same request re-sent with another attempt index is a replay, never a 409.
    again = infer(live, body, attempt=7)
    assert (again.status_code, again.json()) == (201, stored.json())
    assert record_count(live) == 1


@pytest.mark.parametrize("value", ["abc", "0", "-3", "1.5", " "])
def test_an_invalid_attempt_header_is_a_recorded_422(live, value):
    response = live.client.post(f"/api/sessions/{live.sid}/infer", json=make_payload("header-x"),
                                headers={"X-Attempt-Index": value})
    assert response.status_code == 422
    [row] = faults_of(live)
    assert (row["request_id"], row["attempt_index"], row["error_category"], row["origin"],
            row["http_status"], row["retryable"]) == ("header-x", None, "input_validation", "request_validation", 422, False)
    assert record_count(live) == 0


def test_a_schema_422_is_recorded_with_the_request_id_and_without_echoing_the_input(live):
    huge = {**make_payload("huge-1"), "image_base64": "A" * 2_800_001}
    response = infer(live, huge)
    assert response.status_code == 422
    [row] = faults_of(live)
    assert (row["request_id"], row["error_category"], row["origin"]) == ("huge-1", "input_validation", "request_validation")
    assert "image_base64" in row["detail"]
    assert "AAAAAAAAAA" not in row["detail"] and len(row["detail"]) <= 500
    assert "AAAAAAAAAA" not in live.sink_path.read_text()


@pytest.mark.parametrize("raw", [b"{not json", b"[1, 2]", b'{"request_id": 7}', b'{"image_base64": "x"}'],
                         ids=["malformed", "not-an-object", "id-not-a-string", "no-id"])
def test_a_schema_422_without_a_usable_request_id_has_a_null_one(live, raw):
    response = live.client.post(f"/api/sessions/{live.sid}/infer", content=raw,
                                headers={"content-type": "application/json"})
    assert response.status_code == 422
    [row] = faults_of(live)
    assert (row["request_id"], row["error_category"], row["session_id"]) == (None, "input_validation", live.sid)


def test_the_replay_windows_route_records_no_faults(api):
    client, sid = api
    assert client.post(f"/api/sessions/{sid}/windows", json={"P_distraction": 1.1, "P_telemetry_anomaly": 0}).status_code == 422
    assert client.post("/api/sessions/no-such-session/windows", json={"P_distraction": .1, "P_telemetry_anomaly": 0}).status_code == 404
    assert client.get("/api/faults").json() == []


def test_a_contradictory_producer_is_one_unknown_fault_and_still_a_500(live, monkeypatch):
    from app import inference
    from app.schemas import ModalityFreshness, RiskUpdate

    def contradictory(session_id, window_id, w, **kwargs):
        return RiskUpdate(session_id=session_id, window_id=window_id, timestamp="2026-10-14T00:00:00+00:00",
                          assessment_available=True, P_distraction=0, P_telemetry_anomaly=0,
                          RiskScore=None, RiskLevel=None, DominantEvidence=None, AlertSeverity=None,
                          SystemHealth="FULL", modality_freshness=ModalityFreshness(vision="fresh", telemetry="fresh"),
                          latency_ms=0)
    monkeypatch.setattr(inference, "run_inference", contradictory)

    with pytest.raises(ValidationError):
        infer(live, make_payload("contradiction-1"), client=live.strict)
    response = infer(live, make_payload("contradiction-2"))
    assert (response.status_code, response.text) == (500, "Internal Server Error")

    rows_ = faults_of(live)
    assert [r["request_id"] for r in rows_] == ["contradiction-1", "contradiction-2"]
    for row in rows_:
        assert (row["error_category"], row["origin"], row["http_status"], row["retryable"]) == ("unknown", "unknown", 500, False)
        assert "an available assessment must carry" in row["detail"]
    assert len(sink_lines(live)) == 2  # one write per attempt: the global handler did not add a second
    assert record_count(live) == 0


def test_a_stray_exception_outside_the_route_is_recorded_once(live, monkeypatch):
    from app.routers import windows
    monkeypatch.setattr(windows, "_infer", lambda db, session_id, payload: {"not": "a RiskUpdate"})

    with pytest.raises(ResponseValidationError):
        infer(live, make_payload("stray-1"), client=live.strict)
    response = infer(live, make_payload("stray-2"))
    assert (response.status_code, response.text) == (500, "Internal Server Error")

    assert [(r["request_id"], r["error_category"], r["origin"]) for r in faults_of(live)] == [
        ("stray-1", "unknown", "unknown"), ("stray-2", "unknown", "unknown")]
    assert len(sink_lines(live)) == 2


# --- where the data goes -------------------------------------------------------------------
def test_faults_are_written_to_the_request_database_not_the_module_level_one(live):
    from app import db as app_db
    from app import faults
    assert "driver_risk.db" not in str(app_db.engine.url)
    with app_db.engine.begin() as conn:  # give the global database the table so a stray write would SUCCEED
        faults.ensure_schema(conn)
        conn.execute(text("DELETE FROM fault_events"))
    assert infer(live, bad_frame("where-1")).status_code == 422
    assert scalar(live, "SELECT COUNT(*) FROM fault_events WHERE request_id = 'where-1'") == 1
    with app_db.engine.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM fault_events")).scalar() == 0


def test_tests_cannot_reach_the_real_log_directory(live):
    from app import faults
    from app.main import app
    real = Path(faults.__file__).resolve().parents[1] / "logs" / "fault_events.log"
    before = real.stat() if real.exists() else None
    app.dependency_overrides.pop(faults.get_fault_sink)  # a module that overrides only get_db
    assert infer(live, bad_frame("sink-1")).status_code == 422

    assert faults.get_fault_sink().path == faults.DEFAULT_SINK_PATH != real
    assert [json.loads(l)["request_id"] for l in faults.DEFAULT_SINK_PATH.read_text().splitlines()] == ["sink-1"]
    assert (real.stat() if real.exists() else None) == before


# --- schema and migration -------------------------------------------------------------------
def test_the_fault_table_has_one_description_and_no_foreign_key(tmp_path):
    from app import faults
    from app.db import Base
    engine = create_engine(f"sqlite:///{tmp_path / 'schema.db'}")
    Base.metadata.create_all(engine)
    assert "fault_events" not in Base.metadata.tables  # create_all cannot build a second, different one
    assert not inspect(engine).has_table("fault_events")

    for _ in range(2):  # idempotent
        with engine.begin() as conn:
            faults.ensure_schema(conn)
    with engine.connect() as conn:
        assert conn.execute(text("PRAGMA foreign_key_list(fault_events)")).all() == []
        indexes = {i["name"]: i for i in inspect(conn).get_indexes("fault_events")}
        assert indexes["uq_fault_session_request_attempt"]["unique"] == 1
        assert indexes["uq_fault_session_request_attempt"]["column_names"] == ["session_id", "request_id", "attempt_index"]
        assert indexes["ix_fault_events_session_id"]["column_names"] == ["session_id"]
        columns = {c["name"]: c for c in inspect(conn).get_columns("fault_events")}
        assert set(columns) == FAULT_FIELDS
        assert columns["session_id"]["nullable"] is True  # a session that never existed has a fault too
    insert = ("INSERT INTO fault_events (origin, error_category, retryable, recovery_status, occurred_at) "
              "VALUES ('storage', 'storage', 1, :status, '2026-10-14T00:00:00+00:00')")
    with engine.begin() as conn:
        conn.execute(text(insert), {"status": "exhausted"})  # reserved for Task 8, but legal
    with pytest.raises(IntegrityError), engine.begin() as conn:
        conn.execute(text(insert), {"status": "bogus"})
    engine.dispose()


def test_api_factory_builds_the_fault_table_through_ensure_schema(api_factory):
    with api_factory() as db:
        assert db.execute(text("SELECT COUNT(*) FROM fault_events")).scalar() == 0


def legacy_snapshot(engine):
    """Every non-fault object and row of a database, as comparable plain data."""
    with engine.connect() as conn:
        objects = conn.execute(text("SELECT type, name, tbl_name, sql FROM sqlite_master "
                                    "WHERE tbl_name != 'fault_events' AND name != 'sqlite_sequence' "
                                    "ORDER BY type, name")).all()
        tables = {t: conn.execute(text(f"SELECT * FROM {t} ORDER BY 1")).all()
                  for t in ("sessions", "inference_records")}
    return [tuple(o) for o in objects], {t: [tuple(r) for r in rs] for t, rs in tables.items()}


def test_initialize_database_adds_the_fault_table_without_touching_anything_else(tmp_path, monkeypatch):
    from app import db
    (tmp_path / "with").mkdir()
    (tmp_path / "without").mkdir()
    migrated = make_legacy_engine(tmp_path / "with")      # an OLD schema: no fault_events, existing sessions and records
    control = make_legacy_engine(tmp_path / "without")    # the same database, migrated with the fault step switched off
    with migrated.connect() as conn:
        assert not inspect(conn).has_table("fault_events")
        assert conn.execute(text("SELECT COUNT(*) FROM inference_records")).scalar() == 3

    with monkeypatch.context() as patched:
        patched.setattr(db, "engine", control)
        patched.setattr(db, "ensure_fault_schema", lambda conn: None)
        db.initialize_database()

    monkeypatch.setattr(db, "engine", migrated)
    db.initialize_database()
    with migrated.connect() as conn:
        assert inspect(conn).has_table("fault_events")
        assert "uq_fault_session_request_attempt" in {i["name"] for i in inspect(conn).get_indexes("fault_events")}
        fault_sql = conn.execute(text("SELECT sql FROM sqlite_master WHERE tbl_name = 'fault_events' ORDER BY name")).all()
    assert legacy_snapshot(migrated) == legacy_snapshot(control)  # the fault step changed no table, index or row

    # Idempotent, and rows written in between survive another run.
    with migrated.begin() as conn:
        conn.execute(text("INSERT INTO fault_events (session_id, request_id, attempt_index, origin, error_category, "
                          "retryable, detail, occurred_at) VALUES ('legacy', 'kept', 1, 'storage', 'storage', 1, '', "
                          "'2026-10-14T00:00:00+00:00')"))
    after_first = legacy_snapshot(migrated)
    db.initialize_database()
    with migrated.connect() as conn:
        assert conn.execute(text("SELECT request_id FROM fault_events")).scalars().all() == ["kept"]
        assert conn.execute(text("SELECT sql FROM sqlite_master WHERE tbl_name = 'fault_events' ORDER BY name")).all() == fault_sql
    assert legacy_snapshot(migrated) == after_first
    migrated.dispose()
    control.dispose()


# =============================================================================================
# Task 7 follow-up (TASK-7-FOLLOWUP): F1-F5
# =============================================================================================

# --- F1: X-Attempt-Index has an upper bound ------------------------------------------------
@pytest.mark.parametrize("payload", ["valid", "bad-frame"])
@pytest.mark.parametrize("value", ["1001", "100000000000000000000"], ids=["1001", "10-to-the-20"])
def test_an_attempt_header_above_1000_is_a_recorded_422_with_a_null_attempt_index(live, value, payload):
    """1001 is the first rejected value; 10**20 is one an INTEGER column cannot hold (the
    INSERT would overflow and the attempt would be left without its fault row). The bad-frame
    variant makes the route fail by itself, so a missing bound shows up as a row carrying the
    huge index (or no row at all) instead of as a 201."""
    body = make_payload("too-many-1") if payload == "valid" else bad_frame("too-many-1")
    response = live.client.post(f"/api/sessions/{live.sid}/infer", json=body,
                                headers={"X-Attempt-Index": value})
    assert response.status_code == 422

    [row] = faults_of(live)  # exactly one
    assert (row["request_id"], row["attempt_index"], row["error_category"], row["origin"],
            row["http_status"], row["retryable"], row["recovery_status"]) == (
        "too-many-1", None, "input_validation", "request_validation", 422, False, "open")
    assert "X-Attempt-Index" in row["detail"]  # the header was what got rejected
    assert record_count(live) == 0 and total_windows(live) == 0
    [line] = sink_lines(live)
    assert (line["request_id"], line["attempt_index"], line["db_written"]) == ("too-many-1", None, True)


def test_attempt_index_1000_is_the_last_accepted_value(live):
    body = make_payload("limit-1")
    live.vision.fail = RuntimeError("down")
    assert infer(live, body, attempt=1000).status_code == 500  # the normal failure path
    [row] = faults_of(live)
    assert (row["request_id"], row["attempt_index"], row["error_category"], row["origin"],
            row["http_status"], row["retryable"]) == ("limit-1", 1000, "model_runtime", "vision_model", 500, True)

    # A schema 422 is recorded by the global handler, which parses the header on its own: it must
    # agree with the route that 1000 is a real attempt index, not an unparseable one.
    assert infer(live, {"request_id": "limit-schema", "unexpected": True}, attempt=1000).status_code == 422
    schema_row = {r["request_id"]: r for r in faults_of(live)}["limit-schema"]
    assert (schema_row["attempt_index"], schema_row["error_category"]) == (1000, "input_validation")

    live.vision.fail = None
    assert infer(live, body, attempt=1000).status_code == 201  # and the normal success path
    assert record_count(live) == 1
    assert open_faults(live) == 0


# --- F2: the production default sink location -----------------------------------------------
def git_check_ignore(repo, relative_path):
    """Exit status of `git check-ignore` for a path, using only the repo's own .gitignore:
    no global or system config and no user-level excludes file can ignore it for us."""
    env = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}
    result = subprocess.run(["git", "-c", f"core.excludesFile={os.devnull}", "check-ignore", "-v", relative_path],
                            cwd=repo, env=env, capture_output=True, text=True)
    assert result.returncode in (0, 1), result.stderr  # 128 = git itself failed
    return result.returncode, result.stdout


def test_the_production_default_sink_path_is_backend_logs_and_git_ignored(tmp_path, monkeypatch):
    """The autouse fixture redirects DEFAULT_SINK_PATH for every test, so nothing else ever
    sees the real default. This test looks at it, and never writes to it."""
    from app import faults
    # Only the autouse redirect is active in this test (no `live`/`api_factory`, whose patches
    # undo() would drop as well). Dropping it exposes the value the module really defines.
    monkeypatch.undo()
    default = faults.DEFAULT_SINK_PATH
    backend_dir = Path(__file__).resolve().parents[1]  # this file is backend/tests/test_fault_events.py
    repo_root = backend_dir.parent

    assert default == backend_dir / "logs" / "fault_events.log"
    assert default.parts[-3:] == ("backend", "logs", "fault_events.log")

    # A throw-away repo holding only the project's .gitignore: works in a `git archive` copy too.
    repo = tmp_path / "ignore-check"
    repo.mkdir()
    shutil.copy(repo_root / ".gitignore", repo / ".gitignore")
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True, capture_output=True)
    status, matched = git_check_ignore(repo, default.relative_to(repo_root).as_posix())
    assert status == 0, "the default fault log is not git-ignored"
    assert "backend/logs/" in matched
    # Control: the check can say no. A sibling of backend/logs/ is not ignored.
    assert git_check_ignore(repo, "backend/fault_events.log")[0] == 1


# --- F3: a failing classifier never replaces the original error ------------------------------
class Unprintable(Exception):
    """An error whose own __str__ raises, as a buggy native-library exception might."""

    def __str__(self):
        raise RuntimeError("the original error cannot be printed")


class NativeRuntimeError(Unprintable):
    """The same, under a name that differs from the word in the placeholder
    (``Unprintable <TypeName>``), so an assertion on the detail can tell the type name from it."""


def test_a_classifier_failure_never_replaces_the_original_exception(live, monkeypatch):
    from app.providers import trained
    original = Unprintable("provider failed")

    def provider_raises(payload):
        raise original
    monkeypatch.setattr(trained._provider, "infer", provider_raises)

    with pytest.raises(Unprintable) as caught:  # strict client: the app's exception reaches the test
        infer(live, make_payload("hostile-1"), client=live.strict)
    assert caught.value is original  # not the RuntimeError raised by its __str__

    [row] = faults_of(live)
    assert (row["request_id"], row["error_category"], row["origin"], row["http_status"],
            row["retryable"], row["recovery_status"]) == ("hostile-1", "unknown", "unknown", 500, False, "open")
    # A plain exception IS "unknown" (nothing in it says more); what the unprintable cause
    # costs is only the text, which becomes the placeholder (it names the type).
    assert row["detail"] == "Unexpected error; cause: Unprintable Unprintable"
    assert len(sink_lines(live)) == 1  # the route's write only: the global handler added none
    assert record_count(live) == 0


@pytest.mark.parametrize("arrange, status, body, expected", [
    ("runtime", 500, {"detail": "Vision model failed during inference"},
     ("model_runtime", "vision_model", 500, True,
      "Vision model failed during inference; cause: Unprintable NativeRuntimeError")),
    ("conflict", 409, {"detail": "Create a live model session first"},
     ("mode_conflict", "session", 409, False,
      "Create a live model session first; cause: Unprintable NativeRuntimeError")),
], ids=["model-runtime-500", "session-conflict-409"])
def test_an_unprintable_cause_keeps_the_known_category_and_the_original_http_response(
        live, monkeypatch, arrange, status, body, expected):
    """The error BEHIND an HTTP error is unprintable. The client must still get that HTTP error,
    and the fault row must keep what the HTTP error itself says (category, origin, status,
    retryable); only the cause text becomes the placeholder."""
    from app.faults import FaultHTTPException
    from app.routers import windows
    if arrange == "runtime":
        live.vision.fail = NativeRuntimeError("vision failed")  # trained.py wraps it: HTTP 500 caused by it
    else:
        def run_models(payload):
            raise FaultHTTPException(409, "Create a live model session first", error_category="mode_conflict",
                                     origin="session") from NativeRuntimeError("cause")
        monkeypatch.setattr(windows, "_run_models", run_models)

    response = infer(live, make_payload("hostile-2"))
    assert (response.status_code, response.json()) == (status, body)  # the original response, unchanged
    [row] = faults_of(live)
    assert (row["request_id"], row["error_category"], row["origin"], row["http_status"], row["retryable"],
            row["detail"]) == ("hostile-2",) + expected  # the known class, not "unknown"
    assert row["recovery_status"] == "open"
    assert record_count(live) == 0


# --- F4: a concurrent twin is a replay, so it recovers nothing --------------------------------
def test_it_fault_integrity_the_concurrent_twin_path_does_not_recover_open_faults(live, monkeypatch):
    body = make_payload("twin-3")
    winner = infer(live, body)
    assert winner.status_code == 201
    assert infer(live, bad_frame("twin-open-fault")).status_code == 422  # opened AFTER the winner's commit
    [opened] = faults_of(live)
    assert opened["recovery_status"] == "open"
    assert open_faults(live) == 1

    with monkeypatch.context() as patched:  # NOT monkeypatch.undo(): `live` has patches of its own
        calls = blind_to_the_twin(patched)
        loser = infer(live, body, attempt=2)
    assert (loser.status_code, loser.json()) == (201, winner.json())  # answered from the twin's record
    assert len(calls) == 3  # it did go through the IntegrityError re-read
    assert record_count(live) == 1

    assert faults_of(live) == [opened]  # byte-for-byte the same row: still open, nothing recovered it
    assert open_faults(live) == 1

    # Control: a genuinely new record does recover that very fault, so the setup could show it.
    assert infer(live, make_payload("twin-3-next")).status_code == 201
    assert open_faults(live) == 0
    assert [r["recovery_status"] for r in faults_of(live)] == ["recovered"]


# --- F5: record_fault uses a session and a transaction of its own -----------------------------
class UnusableRequestSession:
    """The request's session, broken: it can still say which database it is bound to
    (``get_bind``) but any other use - execute, commit, rollback, ... - raises."""

    def __init__(self, bind):
        self._bind = bind

    def get_bind(self):
        return self._bind

    def execute(self, *args, **kwargs):
        raise RuntimeError("the request session must not be used to write a fault")

    def commit(self):
        raise RuntimeError("the request session must not be used to commit a fault")

    def __getattr__(self, name):
        raise RuntimeError(f"the request session was touched: {name}")


def test_record_fault_writes_through_a_session_and_transaction_of_its_own(live):
    from app.faults import FaultSink, record_fault
    with live.factory() as probe:
        bind = probe.get_bind()

    record_fault(UnusableRequestSession(bind), session_id=live.sid, request_id="own-session-1", attempt_index=4,
                 origin="storage", error_category="storage", http_status=500, retryable=True,
                 detail="the request session is broken", sink=FaultSink(live.sink_path))

    # Read back through a brand-new session on the same database.
    [row] = rows(live, "SELECT * FROM fault_events")
    assert (row["session_id"], row["request_id"], row["attempt_index"], row["origin"], row["error_category"],
            row["http_status"], bool(row["retryable"]), row["detail"], row["recovery_status"]) == (
        live.sid, "own-session-1", 4, "storage", "storage", 500, True, "the request session is broken", "open")
    [line] = sink_lines(live)
    assert (line["request_id"], line["db_written"]) == ("own-session-1", True)


# =============================================================================================
# Task 7 follow-up 2 (TASK-7-FOLLOWUP2): G1-G3
# =============================================================================================

# --- G1: the replay check made under the writer lock ------------------------------------------
def blind_to_the_twin_on_the_first_check_only(monkeypatch):
    """Only the FIRST duplicate pre-check (``_infer``, before the models run) misses the twin: it
    commits after that check. The SECOND check (``_persist_window``, after the writer lock is taken)
    sees it. Returns the call log, one ``(real answer was a hit, returned answer was a hit)`` per call;
    asking the real function even on the blinded call proves the twin WAS there to be seen."""
    from app.routers import windows
    real, log = windows._existing_request, []

    def existing(db, sid, request_id, digest):
        found = real(db, sid, request_id, digest)
        returned = found if log else None  # blind on the first call only
        log.append((found is not None, returned is not None))
        return returned
    monkeypatch.setattr(windows, "_existing_request", existing)
    return log


def test_a_twin_found_by_the_check_under_the_writer_lock_is_a_replay_and_recovers_nothing(live, monkeypatch):
    from app import inference
    from app.routers import windows
    body = make_payload("twin-4")
    winner = infer(live, body)
    assert winner.status_code == 201
    assert infer(live, bad_frame("twin-4-open-fault")).status_code == 422  # opened AFTER the winner's commit
    [opened] = faults_of(live)
    assert opened["recovery_status"] == "open"
    assert open_faults(live) == 1

    fused, real_run_inference = [], inference.run_inference
    held_lock, real_persist = [], windows._persist_window

    def counting_run_inference(*args, **kwargs):
        fused.append(1)
        return real_run_inference(*args, **kwargs)

    def persist_and_look(db, *args, **kwargs):
        result = real_persist(db, *args, **kwargs)
        held_lock.append(db.in_transaction())  # the allocating UPDATE took SQLite's only write lock
        return result
    with monkeypatch.context() as patched:  # NOT monkeypatch.undo(): `live` has patches of its own
        log = blind_to_the_twin_on_the_first_check_only(patched)
        patched.setattr(inference, "run_inference", counting_run_inference)
        patched.setattr(windows, "_persist_window", persist_and_look)
        loser = infer(live, body, attempt=2)

    assert loser.status_code == 201, loser.text
    assert loser.json() == winner.json()  # the stored record, not a new one
    assert loser.json()["window_id"] == winner.json()["window_id"]
    # The second check ran, and it is the one that answered: both checks could see the twin, only
    # the first was blinded, and there was no third look (the IntegrityError re-read of the F4 test).
    assert log == [(True, False), (True, True)]
    assert fused == []  # answered before any fusion work, so before any commit could collide
    assert held_lock == [False]  # and the replay gave the write lock back before it answered
    assert record_count(live) == 1
    assert scalar(live, "SELECT COUNT(*) FROM inference_records WHERE request_id = 'twin-4'") == 1

    assert faults_of(live) == [opened]  # field for field the same row: still open, nothing recovered it
    assert open_faults(live) == 1

    # Control: a genuinely new record does recover that very fault, so the setup could show it.
    assert infer(live, make_payload("twin-4-next")).status_code == 201
    assert open_faults(live) == 0
    assert [r["recovery_status"] for r in faults_of(live)] == ["recovered"]


# --- G2: the global handler's classification is protected too --------------------------------------
def break_get_db_once(error):
    """Make the NEXT resolution of the ``get_db`` dependency raise ``error``. FastAPI resolves
    dependencies before it calls the route function, so ``infer_frame`` (and its try/except) is never
    entered: the error leaves the application from outside the route and only the global handler can
    record it. The handler resolves ``get_db`` once more to write the fault; that call gets the
    working database. Returns the list of errors still pending (append to arm it again)."""
    from app.db import get_db
    from app.main import app
    working = app.dependency_overrides[get_db]
    pending = [error]

    def get_db_that_fails_once():
        if pending:
            raise pending.pop()
        yield from working()
    app.dependency_overrides[get_db] = get_db_that_fails_once
    return pending


@pytest.mark.parametrize("how", ["unprintable-error", "classifier-bug"])
def test_the_global_handler_records_an_error_that_never_reached_the_route(live, monkeypatch, how):
    """Two ways classification can go wrong inside ``on_unhandled_exception``:

    * ``unprintable-error``: the error's own ``__str__`` raises. Since G3 the classifier absorbs this
      by itself (placeholder text, nothing else lost), so the whole handler path must still end in one
      row, a 500 and the original exception;
    * ``classifier-bug``: classification fails for a reason of its own (injected). Only the guarded
      ``classify_exception`` survives that; the bare ``_classify`` would leave the attempt unrecorded."""
    from app import faults
    if how == "unprintable-error":
        def make_error(n):
            return NativeRuntimeError(f"native failure {n}")
        expected = ("unknown", "unknown", 500, False, "Unexpected error; cause: Unprintable NativeRuntimeError")
    else:
        def broken(exc):
            raise RuntimeError("a bug in the classifier")
        monkeypatch.setattr(faults, "_classify", broken)

        def make_error(n):
            return ValueError(f"native failure {n}")
        expected = ("unknown", "unknown", 500, False, "Unclassifiable ValueError")

    def recorded(attempt):
        return [(r["session_id"], r["error_category"], r["origin"], r["http_status"], r["retryable"],
                 r["detail"], r["recovery_status"])
                for r in faults_of(live) if r["attempt_index"] == attempt]
    want = [(live.sid,) + expected + ("open",)]

    original = make_error(1)
    pending = break_get_db_once(original)
    with pytest.raises(type(original)) as caught:  # strict client: what the application raised
        infer(live, make_payload("global-1"), attempt=1, client=live.strict)
    assert caught.value is original  # propagated unchanged
    assert pending == []  # the dependency really was what raised
    assert recorded(1) == want and len(faults_of(live)) == 1  # exactly one row

    pending.append(make_error(2))
    response = infer(live, make_payload("global-2"), attempt=2)  # what a client sees
    assert (response.status_code, response.text) == (500, "Internal Server Error")
    assert recorded(2) == want and len(faults_of(live)) == 2  # one more row, not two
    assert [r["attempt_index"] for r in faults_of(live)] == [1, 2]
    assert len(sink_lines(live)) == 2  # one write per attempt
    assert record_count(live) == 0


# --- G3: only an exception that cannot be classified at all becomes "unknown" -----------------------
def test_an_http_error_the_classifier_does_not_know_is_unknown_with_the_status_the_client_got(live, monkeypatch):
    """The category is not one the classifier has a retry rule for: classification fails. The attempt is
    still recorded, as the status the client received (409), not as a fixed 500."""
    from app.faults import FaultHTTPException
    from app.routers import windows

    def run_models(payload):
        raise FaultHTTPException(409, "Create a live model session first", error_category="not-a-category",
                                 origin="session")
    monkeypatch.setattr(windows, "_run_models", run_models)

    response = infer(live, make_payload("unclassifiable-1"))
    assert (response.status_code, response.json()) == (409, {"detail": "Create a live model session first"})
    [row] = faults_of(live)
    assert (row["request_id"], row["error_category"], row["origin"], row["http_status"], row["retryable"],
            row["detail"], row["recovery_status"]) == (
        "unclassifiable-1", "unknown", "unknown", 409, False, "Unclassifiable FaultHTTPException", "open")
    assert record_count(live) == 0


def test_a_classifier_bug_never_replaces_the_original_exception(live, monkeypatch):
    from app import faults
    from app.providers import trained
    original = ValueError("provider broke")

    def provider_raises(payload):
        raise original
    monkeypatch.setattr(trained._provider, "infer", provider_raises)

    def broken(exc):
        raise RuntimeError("a bug in the classifier")
    monkeypatch.setattr(faults, "_classify", broken)

    with pytest.raises(ValueError) as caught:  # strict client: not the classifier's RuntimeError
        infer(live, make_payload("unclassifiable-2"), client=live.strict)
    assert caught.value is original

    [row] = faults_of(live)
    assert (row["request_id"], row["error_category"], row["origin"], row["http_status"], row["retryable"],
            row["detail"], row["recovery_status"]) == (
        "unclassifiable-2", "unknown", "unknown", 500, False, "Unclassifiable ValueError", "open")
    assert len(sink_lines(live)) == 1
    assert record_count(live) == 0
