"""R10-A (API level) - observation identity, canonical acquisition time, and the transaction.

Every test here goes through ``POST /api/sessions/{id}/infer`` on a tmp SQLite database, with a clock
the test owns (``fake_clock``, the patched clock ``run_inference`` reads). The provider is stubbed -
but ONLY its model probabilities: the stub reads the probability out of the request's own image bytes
and telemetry values, so the image, the acquisition times and the identity metadata all travel through
the real router, the real classification under the write lock, the real FSM and the real SQLite
transaction. (The pre-R10 stub reported vision 'fresh' without any image, which is exactly the kind
of stand-in that can hide a defect, and is not used here.) No test needs model weights.

Every expectation is a hand-computed literal. Scenarios use H = 0.9 (score 90.0, High) and L = 0.1
(score 10.0, Low); a window with one effective branch scores that branch alone. The sessions use
``ema_alpha = 1`` (the identity) unless a test is about the EMA.

Groups (section 6 of the R10 proposal):
  2  request versus observation    3  telemetry identity       4  vision identity
  5  Codex's counter-examples      10 time (the API half)      11 transaction and restart
  A2 request-hash compatibility    A6 provenance               A7 the fault category
"""
import base64
import csv
import io
import json
import threading
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app import cache, faults, fusion, models
from app.main import app
from app.routers import windows
from app.schemas import LiveInput, WindowInput

from test_retry_contract import fault_count, snapshot
from test_temporal_contract import at, fake_clock  # noqa: F401  (fake_clock is used as a fixture)

H, L = 0.9, 0.1
OUT_OF_ORDER = "Out-of-order evidence timestamp"
CONFLICT = "Observation identity already registered with different content or acquisition time"


# ------------------------------------------------------------------------------ the stub and helpers
def img(p, tag="a"):
    """An 'image': the bytes spell the probability the stub will report, and a tag that makes the
    bytes of two frames differ (or not)."""
    return base64.b64encode(f"{p}|{tag}".encode()).decode()


def tel(p, tag=0):
    """Eight telemetry values; ``throttle`` carries the probability (p * 100), ``speed_kmph`` the tag."""
    return {"speed_kmph": 50 + tag, "accel_x": 0.7, "accel_y": 0.2, "brake_pressure": 20,
            "steering_angle": 7.5, "throttle": p * 100, "lane_deviation": 0.21, "headway_distance": 18}


def _spelled_probability(encoded):
    """The probability an ``img(p, tag)`` spells; 0.5 for any other bytes (the fixed legacy bodies)."""
    try:
        return float(base64.b64decode(encoded).decode().split("|")[0])
    except ValueError:
        return 0.5


class ProbStub:
    """Stands in for the trained provider's MODEL. A branch is 'fresh' exactly when the request carried
    its input; its probability is read from that input (see ``img`` / ``tel``) plus ``bias``. Like
    trained.py it echoes ``captured_at`` / ``telemetry_timestamp`` into the provenance. ``barrier``
    makes concurrent requests meet inside the model stage; ``fail`` makes the model raise."""

    def __init__(self):
        self.bias, self.barrier, self.fail, self.calls = 0.0, None, None, 0

    def infer(self, data):
        self.calls += 1
        if self.barrier is not None:
            self.barrier.wait()
        if self.fail is not None:
            raise self.fail
        has_image, has_telemetry = data.image_base64 is not None, data.telemetry_features is not None
        pd = _spelled_probability(data.image_base64) + self.bias if has_image else 0.0
        pt = data.telemetry_features.throttle / 100 + self.bias if has_telemetry else 0.0
        window = WindowInput(
            P_distraction=pd, P_telemetry_anomaly=pt,
            vision_status="fresh" if has_image else "missing",
            telemetry_status="fresh" if has_telemetry else "missing",
            visual_top_classes=[{"label": "safe_driving", "probability": round(1 - pd, 4)},
                                {"label": "distracted_1", "probability": round(pd, 4)}] if has_image else [],
            telemetry_behavior_classes=[{"label": "Safe", "probability": round(1 - pt, 4)},
                                        {"label": "Aggressive", "probability": round(pt, 4)},
                                        {"label": "Distracted", "probability": 0.0}] if has_telemetry else [],
            telemetry_features=data.telemetry_features)
        provenance = {"provider": "ProbStub", "request_id": data.request_id,
                      "vision_source": "camera_frame" if has_image else "missing",
                      "telemetry_source": data.telemetry_source,
                      "captured_at": data.captured_at, "telemetry_timestamp": data.telemetry_timestamp,
                      "P_distraction_raw": pd, "P_telemetry_raw": pt}
        return window, provenance


def body(rid, *, image=None, captured=0, frame=None, source=None, features=None, stamp=0, seq=None):
    """A /infer body. Times are milliseconds on the test clock; a branch is present iff its input is."""
    out = {"request_id": rid}
    if image is not None:
        out.update(image_base64=image, captured_at=at(captured).isoformat())
        if frame is not None:
            out["vision_frame"] = {"epoch": frame[0], "index": frame[1]}
        if source is not None:
            out["captured_at_source"] = source
    if features is not None:
        out.update(telemetry_features=features, telemetry_timestamp=at(stamp).isoformat(),
                   telemetry_source="prepared_replay")
        if seq is not None:
            out["telemetry_seq"] = seq
    return out


class Driver:
    """One live session, one stub, the test clock. ``send`` moves the clock to ``ms`` and posts."""

    def __init__(self, client, clock, monkeypatch, sid, **config):
        from app.providers import trained
        self.client, self.clock, self.sid, self.stub = client, clock, sid, ProbStub()
        monkeypatch.setattr(trained, "get_provider", lambda: self.stub)
        created = client.post("/api/sessions", json={"session_id": sid, "operation_mode": "LIVE_MODEL_RUNTIME",
                                                     "config": {"ema_alpha": 1, **config}})
        assert created.status_code == 201, created.text

    def send(self, ms, rid, attempt=1, **kwargs):
        self.clock.set(ms)
        return self.client.post(f"/api/sessions/{self.sid}/infer", json=body(rid, **kwargs),
                                headers={"X-Attempt-Index": str(attempt)})

    def ok(self, ms, rid, **kwargs):
        response = self.send(ms, rid, **kwargs)
        assert response.status_code == 201, response.text
        return response.json()


@pytest.fixture
def drive(api, fake_clock, monkeypatch):
    client, _ = api
    counter = iter(range(10_000))

    def make(sid=None, **config):
        return Driver(client, fake_clock, monkeypatch, sid or f"live-{next(counter)}", **config)
    make.client = client
    return make


def state_of(api_factory, sid):
    with api_factory() as db:
        return dict(db.get(models.SessionMeta, sid).runtime_state or {})


def window_count(api_factory, sid):
    with api_factory() as db:
        return db.query(models.InferenceRecord).filter_by(session_id=sid).count()


def last_fault(api_factory, sid):
    with api_factory() as db:
        row = db.execute(text("SELECT error_category, origin, http_status, retryable, detail FROM fault_events "
                              "WHERE session_id = :sid ORDER BY id DESC LIMIT 1"), {"sid": sid}).first()
    return tuple(row) if row else None


# ===================================================================== 1. the original contract (API)
@pytest.mark.parametrize("branch", ["vision", "telemetry"])
@pytest.mark.parametrize("age_ms,status,expired,age_s", [
    (3000, "fresh", False, 3.0),
    (3000.4, "missing", True, 3.0),   # 3.0004 s: the exact age is over 3 s, the shown age rounds to 3.0
    (3001, "missing", True, 3.001),
])
def test_g1_api_the_age_boundary_is_exact_through_the_whole_pipeline(drive, branch, age_ms, status, expired, age_s):
    d = drive()
    kwargs = ({"image": img(H), "captured": -age_ms} if branch == "vision"
              else {"features": tel(H), "stamp": -age_ms})
    record = d.ok(0, "boundary", **kwargs)
    assert record["modality_freshness"][branch] == status
    assert record["provenance"][f"{branch}_expired"] is expired
    assert record["provenance"][f"{branch}_age_s"] == age_s


@pytest.mark.parametrize("tolerance", [2, 3, 5])
def test_g1_api_the_tolerance_is_the_sessions(drive, tolerance):
    d = drive(freshness_tolerance_s=tolerance)
    inside = d.ok(0, "inside", image=img(H, "in"), captured=-tolerance * 1000)
    assert inside["modality_freshness"]["vision"] == "fresh"
    outside = d.ok(100, "outside", image=img(H, "out"), captured=100 - tolerance * 1000 - 0.4)
    assert outside["modality_freshness"]["vision"] == "missing"
    assert outside["provenance"]["vision_expired"] is True


def test_g1_api_nothing_the_runtime_writes_or_reads_is_stale_and_unavailable_means_null(drive):
    d = drive()
    records = [d.ok(0, "a", image=img(L, "2"), captured=-9000),      # expired vision, telemetry absent
               d.ok(1000, "b"),                                      # nothing at all
               d.ok(2000, "c", image=img(H, "1"), features=tel(H, 1))]
    for record in records:
        assert set(record["modality_freshness"].values()) <= {"fresh", "missing"}
    for record in records[:2]:
        assert record["assessment_available"] is False
        assert (record["RiskScore"], record["RiskLevel"], record["DominantEvidence"], record["AlertSeverity"]) == (
            None, None, None, None)
        assert record["SystemHealth"] == "UNAVAILABLE"
    stored = d.client.get(f"/api/sessions/{d.sid}/windows").json()
    exported = d.client.get(f"/api/sessions/{d.sid}/export").json()["records"]
    for seen in (*stored, *exported):
        assert "stale" not in seen["modality_freshness"].values()


# ===================================================================== 2. request versus observation
def test_g2_the_same_request_id_is_replayed_and_leaves_one_window(drive, api_factory):
    d = drive()
    first = d.ok(0, "lost-response", features=tel(H), seq=0)
    committed = snapshot(api_factory, d.sid)
    replay = d.ok(5000, "lost-response", attempt=2, features=tel(H), seq=0)
    assert replay == first and replay["window_id"] == 1
    assert snapshot(api_factory, d.sid) == committed
    assert window_count(api_factory, d.sid) == 1


def test_g2_a_new_request_id_with_the_same_observation_writes_a_window_but_does_not_advance_the_fsm(
        drive, api_factory):
    d = drive()
    first = d.ok(0, "r1", features=tel(H), seq=0)
    assert (first["AlertSeverity"], first["provenance"]["telemetry_obs"]) == ("CAUTION", "new")
    before = state_of(api_factory, d.sid)
    again = d.ok(2000, "r2", features=tel(H), seq=0)  # the same sample, 2 s later: a REPEAT
    assert again["window_id"] == 2 and window_count(api_factory, d.sid) == 2
    assert again["provenance"]["telemetry_obs"] == "repeat"
    assert again["AlertSeverity"] == "CAUTION"  # wall 2000 ms, source span 0: no escalation
    after = state_of(api_factory, d.sid)
    for key in ("high_srv_us", "high_src_us", "high_end_us", "high_contrib", "obs_t_seq", "obs_t_ts", "obs_t_hash"):
        assert after[key] == before[key], key


def test_g2_a_409_changes_neither_the_registry_nor_the_fsm_nor_the_window_count(drive, api_factory):
    d = drive()
    d.ok(0, "r1", features=tel(H, 1), seq=4)
    d.ok(500, "r2", features=tel(H, 1), seq=4)
    committed = snapshot(api_factory, d.sid)
    faults_before = fault_count(api_factory, d.sid)
    # same seq, other features / other time -> conflict; lower seq -> out of order
    for rid, kwargs, category in [
            ("c1", {"features": tel(H, 2), "seq": 4, "stamp": 0}, "observation_conflict"),
            ("c2", {"features": tel(H, 1), "seq": 4, "stamp": 100}, "observation_conflict"),
            ("c3", {"features": tel(H, 3), "seq": 3, "stamp": 600}, "out_of_order_evidence")]:
        response = d.send(600, rid, **kwargs)
        assert response.status_code == 409, response.text
        assert last_fault(api_factory, d.sid)[0] == category
        assert snapshot(api_factory, d.sid) == committed
    assert fault_count(api_factory, d.sid) == faults_before + 3
    assert window_count(api_factory, d.sid) == 2


# ---- A2: the request hash survives the upgrade -------------------------------------------------
# Computed with the code of 348b91c (BEFORE this change): sha256(json.dumps(model_dump(), sort_keys=True))
# of these three fixed bodies. The R10 fields did not exist then.
LEGACY_BODIES = [
    ({"request_id": "r10-compat-1", "image_base64": "RlJBTUUtMDAx", "captured_at": "2025-01-01T12:00:00+00:00",
      "telemetry_features": {"speed_kmph": 52, "accel_x": 0.7, "accel_y": 0.2, "brake_pressure": 20,
                             "steering_angle": 7.5, "throttle": 40, "lane_deviation": 0.21, "headway_distance": 18},
      "telemetry_timestamp": "2025-01-01T12:00:00+00:00", "telemetry_source": "prepared_replay"},
     "3cc1d774c41c29bfce6bc54d4bad7c8f0f6ed6852a61f1b70ca2805140719467"),
    ({"request_id": "r10-compat-2", "captured_at": "2025-01-01T12:00:00+00:00", "image_base64": "RlJBTUUtMDAy"},
     "a9b6eec14da8c9b9b119e2f28e7065205ff2e414f69e93540713f88be97da7e4"),
    ({"request_id": "r10-compat-3"},
     "7bcaf705d4721757555c54b6390a638a4c4e21910816b1808e1f947a4df3d725"),
]


@pytest.mark.parametrize("legacy_body,legacy_hash", LEGACY_BODIES, ids=["both", "vision-only", "empty"])
def test_g2_a_body_sent_before_the_upgrade_keeps_its_request_hash(legacy_body, legacy_hash):
    assert windows.request_digest(LiveInput(**legacy_body)) == legacy_hash


@pytest.mark.parametrize("legacy_body,legacy_hash", LEGACY_BODIES, ids=["both", "vision-only", "empty"])
def test_g2_a_retry_that_crosses_the_upgrade_is_an_idempotent_replay_not_a_409(
        drive, api_factory, fake_clock, legacy_body, legacy_hash):
    """The record is stored under the hash the OLD code computed (the literal is written into the row,
    as the old worker would have left it); the upgraded code must recognise the very same HTTP body
    as the same request and answer from the stored record. (The bodies carry the fixed stamp 12:00:00,
    which is time 0 on the test clock.)"""
    d = drive()
    fake_clock.set(0)
    first = d.client.post(f"/api/sessions/{d.sid}/infer", json=legacy_body)
    assert first.status_code == 201, first.text
    with api_factory() as db:
        record = db.query(models.InferenceRecord).filter_by(session_id=d.sid, request_id=legacy_body["request_id"]).one()
        record.request_hash = legacy_hash
        db.commit()
    committed = snapshot(api_factory, d.sid)
    retry = d.client.post(f"/api/sessions/{d.sid}/infer", json=legacy_body, headers={"X-Attempt-Index": "2"})
    assert retry.status_code == 201, retry.text
    assert retry.json() == first.json()
    assert snapshot(api_factory, d.sid) == committed
    assert window_count(api_factory, d.sid) == 1


def test_g2_a_body_that_uses_the_new_fields_hashes_differently_and_the_fields_are_part_of_the_identity(
        drive, api_factory):
    d = drive()
    with_seq = body("same-id", features=tel(H), seq=3)
    legacy_like = {k: v for k, v in with_seq.items() if k != "telemetry_seq"}
    assert windows.request_digest(LiveInput(**with_seq)) != windows.request_digest(LiveInput(**legacy_like))
    assert d.send(0, "same-id", features=tel(H), seq=3).status_code == 201
    other_seq = d.send(0, "same-id", attempt=2, features=tel(H), seq=4)
    assert other_seq.status_code == 409 and other_seq.json()["detail"] == "request_id already used for different input"
    assert last_fault(api_factory, d.sid)[0] == "idempotency_conflict"


# ===================================================================== 3. telemetry identity
def test_g3_a_telemetry_sample_every_two_seconds_escalates_at_two_seconds(drive):
    d = drive()
    first = d.ok(0, "s0", features=tel(H, 0), seq=0, stamp=0)
    second = d.ok(2000, "s1", features=tel(H, 1), seq=1, stamp=2000)
    assert [first["AlertSeverity"], second["AlertSeverity"]] == ["CAUTION", "HIGH_ALERT"]
    assert second["provenance"]["telemetry_obs"] == "new" and second["provenance"]["telemetry_seq"] == 1
    assert second["provenance"]["identity_source"] == "explicit"


def test_g3_a_telemetry_frozen_on_one_seq_never_alerts_and_then_expires(drive):
    """S2: the same sample re-sent every 500 ms. Fresh for 3.0 s, so the wall clock passes 2 s while the
    source span stays 0: CAUTION throughout; at 3.5 s the sample is over the tolerance -> unavailable."""
    d = drive()
    records = [d.ok(ms, f"f{ms}", features=tel(H), seq=0, stamp=0) for ms in range(0, 3501, 500)]
    assert [r["AlertSeverity"] for r in records] == ["CAUTION"] * 7 + [None]
    assert [r["provenance"]["telemetry_obs"] for r in records] == ["new"] + ["repeat"] * 7
    assert records[-1]["assessment_available"] is False
    assert records[-1]["provenance"]["telemetry_expired"] is True and records[-1]["provenance"]["telemetry_age_s"] == 3.5
    # the REPEAT keeps showing the canonical (first) stamp and age is measured from it
    assert {r["provenance"]["telemetry_timestamp"] for r in records} == {at(0).isoformat()}


@pytest.mark.parametrize("change,label", [
    ({"features": tel(H, 9)}, "other features"),
    ({"stamp": 100}, "other acquisition time"),
])
def test_g3_the_same_seq_with_other_content_or_time_is_a_409_observation_conflict(drive, api_factory, change, label):
    d = drive()
    d.ok(0, "s0", features=tel(H, 1), seq=7, stamp=0)
    committed = snapshot(api_factory, d.sid)
    kwargs = {"features": tel(H, 1), "stamp": 0, **change}
    response = d.send(500, "s0b", seq=7, **kwargs)
    assert response.status_code == 409 and response.json()["detail"] == CONFLICT, label
    assert last_fault(api_factory, d.sid) == ("observation_conflict", "session", 409, 0, CONFLICT)
    assert snapshot(api_factory, d.sid) == committed


def test_g3_a_seq_that_goes_backwards_is_a_409_out_of_order(drive, api_factory):
    d = drive()
    d.ok(0, "s0", features=tel(H, 1), seq=3, stamp=0)
    committed = snapshot(api_factory, d.sid)
    response = d.send(500, "s1", features=tel(H, 2), seq=2, stamp=500)
    assert response.status_code == 409 and response.json()["detail"] == OUT_OF_ORDER
    assert last_fault(api_factory, d.sid) == ("out_of_order_evidence", "session", 409, 0, OUT_OF_ORDER)
    assert snapshot(api_factory, d.sid) == committed


def test_g3_seq_25_with_the_content_of_seq_0_is_new_not_a_repeat(drive):
    """S11: the 25-row replay wraps. The identity is the seq, not the row content, so seq 25 carrying
    seq 0's values is a NEW observation (24 -> 25), and it advances the source span."""
    d = drive()
    d.ok(0, "s0", features=tel(H, 0), seq=0, stamp=0)
    d.ok(48_000, "s24", features=tel(H, 24), seq=24, stamp=48_000)
    wrapped = d.ok(50_000, "s25", features=tel(H, 0), seq=25, stamp=50_000)
    assert wrapped["provenance"]["telemetry_obs"] == "new" and wrapped["provenance"]["telemetry_seq"] == 25
    assert wrapped["AlertSeverity"] == "HIGH_ALERT"  # seq 24 opened the segment at 48000; 2000 ms later


def test_g3_sessions_are_isolated_from_each_other(drive):
    a, b = drive("iso-a"), drive("iso-b")
    a.ok(0, "a0", features=tel(H, 1), seq=5, stamp=0)
    first_in_b = b.ok(100, "b0", features=tel(H, 1), seq=0, stamp=100)  # seq 0 after A's seq 5: fine
    assert first_in_b["provenance"]["telemetry_obs"] == "new"
    same_as_a = b.ok(200, "b1", features=tel(H, 1), seq=5, stamp=200)  # seq 5 here is NEW in B
    assert same_as_a["provenance"]["telemetry_obs"] == "new"


def test_g3_without_a_seq_the_weaker_fallback_applies(drive):
    d = drive()
    first = d.ok(0, "n0", features=tel(H, 1), stamp=0)
    same = d.ok(500, "n1", features=tel(H, 1), stamp=0)            # same time, same features -> REPEAT
    other = d.ok(600, "n2", features=tel(H, 2), stamp=0)           # same time, other features -> NEW
    later = d.ok(700, "n3", features=tel(H, 2), stamp=700)         # later time, even the same features -> NEW
    kinds = [r["provenance"]["telemetry_obs"] for r in (first, same, other, later)]
    assert kinds == ["new", "repeat", "new", "new"]
    assert {r["provenance"]["identity_source"] for r in (first, same, other, later)} == {"fallback"}
    assert first["provenance"]["telemetry_seq"] is None
    older = d.send(800, "n4", features=tel(H, 3), stamp=300)       # an earlier time -> 409
    assert older.status_code == 409 and older.json()["detail"] == OUT_OF_ORDER


def test_g3_a_sample_without_a_seq_in_between_does_not_clear_the_explicit_seq_high_water_mark(drive, api_factory):
    """A3 / Codex C9: explicit identity is monotonic for the whole session, however it is mixed with the
    fallback. seq 10 is accepted; a sample that carries no seq (the fallback, NEW by its later time) is
    accepted in between; seq 3 must STILL be refused as out of order. The fallback registers its own time
    and hash only - it must not write 'no seq' over the mark. (Before the fix it did, and seq 3 came
    back 201 NEW.) Nothing of the refused request may reach the registry, the window count or the FSM."""
    d = drive()
    d.ok(0, "s10", features=tel(H, 1), seq=10, stamp=0)
    between = d.ok(100, "no-seq", features=tel(H, 2), stamp=100)
    assert between["provenance"]["telemetry_obs"] == "new"
    assert between["provenance"]["telemetry_identity_source"] == "fallback"
    committed = snapshot(api_factory, d.sid)
    response = d.send(200, "s3", features=tel(H, 3), seq=3, stamp=200)
    assert response.status_code == 409 and response.json()["detail"] == OUT_OF_ORDER
    assert last_fault(api_factory, d.sid) == ("out_of_order_evidence", "session", 409, 0, OUT_OF_ORDER)
    assert snapshot(api_factory, d.sid) == committed   # registry, watermarks, FSM memory, counter, records
    assert window_count(api_factory, d.sid) == 2
    assert state_of(api_factory, d.sid)["obs_t_seq"] == 10   # the mark survived the seq-less sample
    # Forward is still open: the mark guards the past, it does not freeze the session.
    forward = d.ok(300, "s11", features=tel(H, 4), seq=11, stamp=300)
    assert (forward["provenance"]["telemetry_obs"], forward["provenance"]["telemetry_seq"]) == ("new", 11)


def test_g3_after_mixing_identities_the_last_explicit_seq_resent_unchanged_is_refused(drive, api_factory):
    """Documented limitation (R10-A follow-up review): explicit and fallback identities share one
    content registry, so after a seq-less sample the registered content no longer belongs to seq 10.
    Resending seq 10 unchanged is therefore REFUSED (409 observation_conflict) rather than taken as a
    REPEAT. This is the conservative answer - the stored probabilities would be the wrong sample's -
    and a client that always sends explicit identity (R10-B) never mixes. Pinned so a change is a
    decision, not an accident."""
    d = drive()
    d.ok(0, "s10", features=tel(H, 1), seq=10, stamp=0)
    d.ok(100, "no-seq", features=tel(H, 2), stamp=100)
    committed = snapshot(api_factory, d.sid)
    response = d.send(200, "s10-again", features=tel(H, 1), seq=10, stamp=0)
    assert response.status_code == 409 and response.json()["detail"] == CONFLICT
    assert snapshot(api_factory, d.sid) == committed
    assert window_count(api_factory, d.sid) == 2


# ===================================================================== 4. vision identity
def test_g4_a_frame_re_sent_under_new_request_ids_is_a_repeat_and_never_alerts(drive):
    """S4: the same frame (0, 0) every 500 ms: REPEAT, canonical time kept, CAUTION until the frame
    is 3.0 s old; at 3.5 s it expires."""
    d = drive()
    records = [d.ok(ms, f"v{ms}", image=img(H), captured=0, frame=(0, 0)) for ms in range(0, 3501, 500)]
    assert [r["AlertSeverity"] for r in records] == ["CAUTION"] * 7 + [None]
    assert [r["provenance"]["vision_obs"] for r in records] == ["new"] + ["repeat"] * 7
    assert records[0]["provenance"]["vision_frame_id"] == "0:0"
    assert records[-1]["provenance"]["vision_expired"] is True


def test_g4_new_metadata_with_the_same_image_bytes_is_still_new_and_carries_the_audit_flag(drive):
    """C3: the hash only audits. Five different frames (0, 0) ... (0, 4) with IDENTICAL bytes, 500 ms
    apart in source time: each is NEW (the audit flag from the second on), and they escalate at 2000 ms."""
    d = drive()
    records = [d.ok(ms, f"v{ms}", image=img(H, "same"), captured=ms, frame=(0, ms // 500)) for ms in range(0, 2001, 500)]
    assert [r["provenance"]["vision_obs"] for r in records] == ["new"] * 5
    assert [r["provenance"]["vision_hash_repeat_audit"] for r in records] == [False, True, True, True, True]
    assert [r["AlertSeverity"] for r in records] == ["CAUTION"] * 4 + ["HIGH_ALERT"]
    assert records[-1]["provenance"]["vision_frame_id"] == "0:4"


def test_g4_a_new_epoch_with_the_same_first_image_is_new(drive):
    d = drive()
    d.ok(0, "e0", image=img(H, "x"), captured=0, frame=(0, 41))
    restarted = d.ok(500, "e1", image=img(H, "x"), captured=500, frame=(1, 0))
    assert restarted["provenance"]["vision_obs"] == "new"
    assert restarted["provenance"]["vision_hash_repeat_audit"] is True
    assert restarted["provenance"]["vision_frame_id"] == "1:0"


@pytest.mark.parametrize("change,label", [({"image": img(H, "other")}, "other bytes"), ({"captured": 50}, "other time")])
def test_g4_the_same_frame_id_with_other_bytes_or_time_is_a_409_observation_conflict(drive, api_factory, change, label):
    d = drive()
    d.ok(0, "v0", image=img(H, "x"), captured=0, frame=(0, 3))
    committed = snapshot(api_factory, d.sid)
    kwargs = {"image": img(H, "x"), "captured": 0, **change}
    response = d.send(100, "v1", frame=(0, 3), **kwargs)
    assert response.status_code == 409 and response.json()["detail"] == CONFLICT, label
    assert last_fault(api_factory, d.sid)[0] == "observation_conflict"
    assert snapshot(api_factory, d.sid) == committed


def test_g4_an_older_epoch_or_frame_is_a_409_out_of_order(drive, api_factory):
    d = drive()
    d.ok(0, "v0", image=img(H, "a"), captured=0, frame=(1, 5))
    committed = snapshot(api_factory, d.sid)
    for rid, frame in (("old-epoch", (0, 99)), ("old-frame", (1, 4))):
        response = d.send(100, rid, image=img(H, rid), captured=100, frame=frame)
        assert response.status_code == 409 and response.json()["detail"] == OUT_OF_ORDER
        assert last_fault(api_factory, d.sid)[0] == "out_of_order_evidence"
        assert snapshot(api_factory, d.sid) == committed


def test_g4_without_frame_metadata_the_image_hash_is_the_fallback_identity(drive):
    d = drive()
    first = d.ok(0, "v0", image=img(H, "x"), captured=0)
    again = d.ok(100, "v1", image=img(H, "x"), captured=100)       # same bytes, re-stamped by the client
    other = d.ok(200, "v2", image=img(H, "y"), captured=200)       # other bytes -> NEW
    assert [r["provenance"]["vision_obs"] for r in (first, again, other)] == ["new", "repeat", "new"]
    assert {r["provenance"]["identity_source"] for r in (first, again, other)} == {"fallback"}
    assert again["provenance"]["captured_at"] == at(0).isoformat()  # the REGISTERED time, not the new stamp
    assert again["provenance"]["vision_frame_id"] is None
    # a NEW fallback frame is still subject to the captured_at watermark; a repeat is not judged by its stamp
    older = d.send(300, "v3", image=img(H, "z"), captured=50)
    assert older.status_code == 409 and older.json()["detail"] == OUT_OF_ORDER
    repeat_with_old_stamp = d.ok(400, "v4", image=img(H, "y"), captured=10)
    assert repeat_with_old_stamp["provenance"]["vision_obs"] == "repeat"


def test_g4_a_frame_without_metadata_in_between_does_not_clear_the_explicit_frame_high_water_mark(drive, api_factory):
    """A3 / Codex C9, the vision half. Frame (1, 5) is accepted; a frame with no vision_frame (the
    fallback, NEW because its bytes differ) is accepted in between; an older epoch (0, 99) - and an
    older index of the same epoch (1, 4) - must STILL be refused as out of order. The fallback registers
    its own time and hash only, never 'no frame' over the mark. (Before the fix (0, 99) came back 201
    NEW.) The refused requests change nothing: registry, window count, FSM memory."""
    d = drive()
    d.ok(0, "v15", image=img(H, "a"), captured=0, frame=(1, 5))
    between = d.ok(100, "bare", image=img(H, "b"), captured=100)
    assert between["provenance"]["vision_obs"] == "new"
    assert between["provenance"]["vision_identity_source"] == "fallback"
    committed = snapshot(api_factory, d.sid)
    for rid, frame in (("old-epoch", (0, 99)), ("old-index", (1, 4))):
        response = d.send(200, rid, image=img(H, rid), captured=200, frame=frame)
        assert response.status_code == 409 and response.json()["detail"] == OUT_OF_ORDER, rid
        assert last_fault(api_factory, d.sid) == ("out_of_order_evidence", "session", 409, 0, OUT_OF_ORDER)
        assert snapshot(api_factory, d.sid) == committed, rid
    assert window_count(api_factory, d.sid) == 2
    held = state_of(api_factory, d.sid)
    assert (held["obs_v_epoch"], held["obs_v_index"]) == (1, 5)   # the mark survived the bare frame
    # Forward is still open.
    forward = d.ok(300, "v16", image=img(H, "c"), captured=300, frame=(1, 6))
    assert (forward["provenance"]["vision_obs"], forward["provenance"]["vision_frame_id"]) == ("new", "1:6")


def test_g4_a_repeat_uses_the_stored_probabilities_not_the_models_new_answer(drive):
    """The stub is made to answer differently the second time; the REPEAT window must show the
    probabilities and the per-class breakdown stored when the observation was first accepted."""
    d = drive()
    first = d.ok(0, "v0", image=img(0.5, "x"), captured=0, frame=(0, 0), features=tel(0.4, 1), stamp=0, seq=0)
    d.stub.bias = 0.2
    again = d.ok(500, "v1", image=img(0.5, "x"), captured=0, frame=(0, 0), features=tel(0.4, 1), stamp=0, seq=0)
    assert (again["P_distraction"], again["P_telemetry_anomaly"]) == (first["P_distraction"], first["P_telemetry_anomaly"]) == (0.5, 0.4)
    assert again["provenance"]["P_distraction_raw"] == 0.5 and again["provenance"]["P_telemetry_raw"] == 0.4
    assert again["visual_top_classes"] == first["visual_top_classes"]
    assert again["telemetry_behavior_classes"] == first["telemetry_behavior_classes"]
    assert d.stub.calls == 2  # the model did run again - and its answer was not used


# ===================================================================== 5. Codex's counter-examples
def test_c1_a_first_window_whose_two_branches_are_2500_ms_apart_cannot_alert_on_resends_alone(drive):
    """Vision captured 2500 ms before it was processed, telemetry captured at processing time, both
    High; afterwards ONLY repeats arrive (every 100 ms). The span starts at 0 at the NEWEST of the two
    acquisition times, so no amount of re-sending can build 2000 ms of it - the pre-fill that made
    the old rule alert at 2.00 s is gone. Vision expires at 0.6 s, telemetry at 3.1 s."""
    d = drive()
    records = [d.ok(ms, f"c1-{ms}", image=img(H, "c1"), captured=-2500, frame=(0, 0),
                    features=tel(H, 1), stamp=0, seq=0) for ms in range(0, 3201, 100)]
    assert [r["AlertSeverity"] for r in records] == ["CAUTION"] * 31 + [None, None]  # 0 ... 3000, then 3100, 3200
    by_ms = {ms: r for ms, r in zip(range(0, 3201, 100), records)}
    assert by_ms[500]["SystemHealth"] == "FULL" and by_ms[600]["SystemHealth"] == "DEGRADED"
    assert by_ms[2000]["AlertSeverity"] == "CAUTION"  # the moment the old rule alerted
    assert by_ms[3100]["provenance"]["telemetry_expired"] is True


def test_c2_a_low_stream_cannot_recover_by_borrowing_an_old_frames_time(drive, api_factory):
    """A latched alert. The first window carries vision captured 2500 ms earlier and telemetry at 0,
    both Low; then telemetry sends NEW samples at 2 / 4 / 6 / 8 s and is only re-sent after that. The
    newest NEW Low sample is at 8000, so the source span is 8000 ms, not the 10500 ms the old frame
    would have given: at 10 s of wall clock the alert is still HIGH_ALERT."""
    d = drive()
    with api_factory() as db:
        sess = db.get(models.SessionMeta, d.sid)
        sess.runtime_state = {"last_severity": "HIGH_ALERT"}
        db.commit()
    out = {}
    for ms in range(0, 11_001, 1000):
        seq = min(ms // 2000, 4)
        extra = {"image": img(L, "c2"), "captured": -2500, "frame": (0, 0)} if ms == 0 else {}
        out[ms] = d.ok(ms, f"c2-{ms}", features=tel(L, seq), stamp=2000 * seq, seq=seq, **extra)
    assert out[0]["provenance"]["vision_obs"] == "new"
    assert [out[ms]["provenance"]["telemetry_obs"] for ms in range(0, 11_001, 1000)] == [
        "new", "repeat", "new", "repeat", "new", "repeat", "new", "repeat", "new", "repeat", "repeat", "repeat"]
    assert {r["AlertSeverity"] for r in out.values()} == {"HIGH_ALERT"}
    assert state_of(api_factory, d.sid)["low_end_us"] - state_of(api_factory, d.sid)["low_src_us"] == 8_000_000


def test_c4_re_stamping_a_repeated_frame_does_not_keep_it_fresh(drive, api_factory):
    """The client sends the SAME bytes every 100 ms and stamps each request with the time it was
    built. Without frame metadata the bytes are the identity: every request after the first is a
    REPEAT and ages from the stamp the frame was first registered with, so it expires 3 s after
    the first request, however often it is re-stamped - and it never alerts on the way."""
    d = drive()
    records = [d.ok(ms, f"c4-{ms}", image=img(H, "c4"), captured=ms) for ms in range(0, 3501, 100)]
    assert {r["provenance"]["captured_at"] for r in records} == {at(0).isoformat()}
    assert [r["provenance"]["vision_obs"] for r in records] == ["new"] + ["repeat"] * 35
    by_ms = dict(zip(range(0, 3501, 100), records))
    assert by_ms[3000]["modality_freshness"]["vision"] == "fresh" and by_ms[3000]["provenance"]["vision_age_s"] == 3.0
    assert by_ms[3100]["modality_freshness"]["vision"] == "missing"
    assert by_ms[3100]["provenance"]["vision_expired"] is True and by_ms[3100]["provenance"]["vision_age_s"] == 3.1
    assert by_ms[3100]["AlertSeverity"] is None
    assert [r["AlertSeverity"] for r in records[:31]] == ["CAUTION"] * 31
    assert state_of(api_factory, d.sid)["captured_at"] == at(0).isoformat()  # a repeat never moves the watermark


# ===================================================================== 10. time (the API half)
def test_g10_a_timestamp_up_to_5_s_ahead_is_accepted_and_clips_the_age_to_zero_beyond_that_it_is_a_422(
        api, monkeypatch):
    """The 5 s tolerance of the existing schema check, on the real clock (the schema reads it). 4 s
    ahead is accepted, age 0.0; 6 s ahead is refused. R10 does not synchronise clocks."""
    from app.providers import trained
    client, _ = api
    stub = ProbStub()
    monkeypatch.setattr(trained, "get_provider", lambda: stub)
    assert client.post("/api/sessions", json={"session_id": "future", "operation_mode": "LIVE_MODEL_RUNTIME"}).status_code == 201
    now = datetime.now(timezone.utc)
    ok = client.post("/api/sessions/future/infer", json={"request_id": "ahead-4", "image_base64": img(H),
                                                         "captured_at": (now + timedelta(seconds=4)).isoformat()})
    assert ok.status_code == 201, ok.text
    assert ok.json()["provenance"]["vision_age_s"] == 0.0 and ok.json()["modality_freshness"]["vision"] == "fresh"
    refused = client.post("/api/sessions/future/infer", json={"request_id": "ahead-6", "image_base64": img(H, "b"),
                                                              "captured_at": (now + timedelta(seconds=6)).isoformat()})
    assert refused.status_code == 422
    assert "timestamp is in the future" in "; ".join(item["msg"] for item in refused.json()["detail"])


def test_g10_a_late_first_delivery_is_expired_and_a_later_repeat_of_it_stays_expired(drive, api_factory):
    """A frame captured at 0 first reaches the server at 3.5 s (a slow network): registered, but
    expired. The same frame under a new request id at 3.6 s is a REPEAT and ages from the original
    capture time (3.6 s), not from its own arrival. Re-sending the FIRST request is a replay of the
    stored record (age 3.5, not re-judged)."""
    d = drive()
    first = d.ok(3500, "late", image=img(H), captured=0, frame=(0, 0))
    assert first["provenance"]["vision_expired"] is True and first["provenance"]["vision_age_s"] == 3.5
    second = d.ok(3600, "late-again", image=img(H), captured=0, frame=(0, 0))
    assert second["provenance"]["vision_obs"] == "repeat"
    assert second["provenance"]["vision_age_s"] == 3.6 and second["provenance"]["vision_expired"] is True
    retry = d.ok(9000, "late", attempt=3, image=img(H), captured=0, frame=(0, 0))
    assert retry == first


def test_g10_a_client_clock_that_steps_back_is_expired_with_a_seq_and_a_409_without_one(drive, api_factory):
    d = drive()
    d.ok(10_000, "t5", features=tel(H, 5), seq=5, stamp=10_000)
    stepped = d.ok(10_500, "t6", features=tel(H, 6), seq=6, stamp=2000)   # claims 8.5 s ago: NEW, expired
    assert stepped["provenance"]["telemetry_obs"] == "new"
    assert stepped["provenance"]["telemetry_expired"] is True and stepped["provenance"]["telemetry_age_s"] == 8.5
    assert stepped["assessment_available"] is False
    assert state_of(api_factory, d.sid)["telemetry_timestamp"] == at(10_000).isoformat()  # the watermark does not drop
    back = d.send(10_600, "n1", features=tel(H, 7), stamp=2500)           # no seq: the old guard applies
    assert back.status_code == 409 and back.json()["detail"] == OUT_OF_ORDER


# ===================================================================== A6. provenance
def test_a6_provenance_names_the_verdict_the_identity_and_the_source_of_the_stamp(drive):
    d = drive()
    record = d.ok(0, "p0", image=img(H), captured=0, frame=(2, 7), source="capture_time",
                  features=tel(H), stamp=0)  # vision explicit, telemetry by the fallback
    p = record["provenance"]
    assert (p["vision_obs"], p["telemetry_obs"]) == ("new", "new")
    assert (p["vision_frame_id"], p["telemetry_seq"]) == ("2:7", None)
    assert (p["vision_identity_source"], p["telemetry_identity_source"]) == ("explicit", "fallback")
    assert p["identity_source"] == "fallback"  # one fallback branch makes the request 'fallback'
    assert p["vision_hash_repeat_audit"] is False and p["captured_at_source"] == "capture_time"
    both = d.ok(500, "p1", image=img(H, "b"), captured=500, frame=(2, 8), features=tel(H, 1), stamp=500, seq=1)
    assert both["provenance"]["identity_source"] == "explicit" and both["provenance"]["telemetry_seq"] == 1
    nothing = d.ok(600, "p2")
    assert (nothing["provenance"]["vision_obs"], nothing["provenance"]["telemetry_obs"],
            nothing["provenance"]["identity_source"]) == (None, None, None)


def test_a6_the_new_provenance_survives_the_stored_record_and_both_exports(drive):
    d = drive()
    d.ok(0, "x0", image=img(H), captured=0, frame=(0, 1), features=tel(H), stamp=0, seq=3, source="callback")
    stored = d.client.get(f"/api/sessions/{d.sid}/windows").json()[0]["provenance"]
    exported = d.client.get(f"/api/sessions/{d.sid}/export").json()["records"][0]["provenance"]
    for provenance in (stored, exported):
        assert (provenance["vision_obs"], provenance["telemetry_seq"], provenance["vision_frame_id"],
                provenance["captured_at_source"]) == ("new", 3, "0:1", "callback")
    row = next(csv.DictReader(io.StringIO(d.client.get(f"/api/sessions/{d.sid}/export?format=csv").text)))
    in_csv = json.loads(row["provenance"])
    assert (in_csv["vision_obs"], in_csv["telemetry_seq"], in_csv["vision_frame_id"], in_csv["captured_at_source"]) == (
        "new", 3, "0:1", "callback")
    assert row["telemetry_source"] == "prepared_replay"  # the existing column is not shadowed by a new key


# ===================================================================== A7. the fault category
def test_a7_the_observation_conflict_is_its_own_category_and_not_retryable():
    exc = faults.FaultHTTPException(409, CONFLICT, error_category=faults.CATEGORY_OBSERVATION_CONFLICT,
                                    origin=faults.ORIGIN_SESSION)
    info = faults.classify_exception(exc)
    assert (info.error_category, info.origin, info.http_status, info.retryable) == (
        "observation_conflict", "session", 409, False)
    assert "observation_conflict" in faults.ERROR_CATEGORIES
    # A bare 409 from older code is still a mode conflict: nothing was reclassified.
    from fastapi import HTTPException
    assert faults.classify_exception(HTTPException(409, "x")).error_category == "mode_conflict"


# ===================================================================== 11. transaction and restart
def _race(d, bodies):
    """Post the bodies at the same moment, each from its own client and thread; the stub's barrier makes
    them all meet inside the model stage, i.e. after the duplicate pre-check and before the writer lock."""
    d.stub.barrier = threading.Barrier(len(bodies), timeout=20)
    d.clock.set(0)
    results = []

    def worker(payload):
        client = TestClient(app)
        try:
            results.append(client.post(f"/api/sessions/{d.sid}/infer", json=payload))
        finally:
            client.close()
    threads = [threading.Thread(target=worker, args=(payload,)) for payload in bodies]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(30)
    assert len(results) == len(bodies)
    return results


def test_g11_two_concurrent_identical_requests_commit_exactly_once(drive, api_factory):
    d = drive()
    one, two = _race(d, [body("twin", features=tel(H), seq=0, stamp=0)] * 2)
    assert (one.status_code, two.status_code) == (201, 201)
    assert one.json() == two.json()
    assert window_count(api_factory, d.sid) == 1
    assert state_of(api_factory, d.sid)["obs_t_seq"] == 0


def test_g11_two_new_requests_for_the_same_seq_count_the_observation_once(drive, api_factory):
    d = drive()
    results = _race(d, [body("race-a", features=tel(H), seq=0, stamp=0),
                        body("race-b", features=tel(H), seq=0, stamp=0)])
    assert sorted(r.status_code for r in results) == [201, 201]
    assert sorted(r.json()["provenance"]["telemetry_obs"] for r in results) == ["new", "repeat"]  # not two 'new'
    assert window_count(api_factory, d.sid) == 2
    state = state_of(api_factory, d.sid)
    assert state["high_srv_us"] == state["high_src_us"] == state["high_end_us"]  # one NEW opened the segment


def test_g11_a_model_failure_consumes_nothing(drive, api_factory):
    from app.providers.trained import ModelRuntimeError
    d = drive()
    d.ok(0, "ok0", features=tel(H, 1), seq=0)
    committed = snapshot(api_factory, d.sid)
    d.stub.fail = ModelRuntimeError("telemetry model failed", origin=faults.ORIGIN_TELEMETRY_MODEL)
    assert d.send(500, "boom", features=tel(H, 2), seq=1, stamp=500).status_code == 500
    assert snapshot(api_factory, d.sid) == committed
    d.stub.fail = None
    retry = d.ok(600, "boom", attempt=2, features=tel(H, 2), seq=1, stamp=500)
    assert retry["provenance"]["telemetry_obs"] == "new" and retry["window_id"] == 2


def test_g11_a_validation_failure_consumes_nothing(drive, api_factory):
    from app.providers.trained import InvalidFrame
    d = drive()
    d.ok(0, "ok0", image=img(H, "a"), captured=0, frame=(0, 0))
    committed = snapshot(api_factory, d.sid)
    d.stub.fail = InvalidFrame("Invalid or damaged image")
    assert d.send(500, "bad", image=img(H, "b"), captured=500, frame=(0, 1)).status_code == 422
    d.stub.fail = None
    assert d.send(500, "bad-schema", image=img(H, "b"), captured=500, frame=(-1, 0)).status_code == 422
    assert snapshot(api_factory, d.sid) == committed
    again = d.ok(600, "good", image=img(H, "b"), captured=600, frame=(0, 1))  # frame (0, 1) was not consumed
    assert again["provenance"]["vision_obs"] == "new"


def test_g11_a_storage_failure_consumes_nothing(drive, api_factory, monkeypatch):
    from sqlalchemy.exc import OperationalError
    from sqlalchemy.orm import Session
    d = drive()
    d.ok(0, "ok0", features=tel(H, 1), seq=0)
    committed = snapshot(api_factory, d.sid)
    real_commit, calls = Session.commit, []

    def failing_commit(self):
        calls.append(1)
        if len(calls) == 1:
            raise OperationalError("COMMIT", {}, Exception("disk I/O error"))
        return real_commit(self)
    d.clock.set(500)
    lenient = TestClient(app, raise_server_exceptions=False)
    with monkeypatch.context() as patched:
        patched.setattr(Session, "commit", failing_commit)
        failed = lenient.post(f"/api/sessions/{d.sid}/infer", json=body("disk", features=tel(H, 2), seq=1, stamp=500))
    lenient.close()
    assert failed.status_code == 500
    assert last_fault(api_factory, d.sid)[:3] == ("storage", "storage", 500)
    assert snapshot(api_factory, d.sid) == committed
    retry = d.ok(600, "disk", attempt=2, features=tel(H, 2), seq=1, stamp=500)
    assert retry["provenance"]["telemetry_obs"] == "new" and retry["window_id"] == 2


def test_g11_a_failure_after_the_classification_still_consumes_nothing(drive, api_factory, monkeypatch):
    """The nastiest one: classification has already registered seq 1 in the working copy of the state when
    the record fails its own validation. The rollback must take the registration with it, so the next
    request for seq 1 is NEW and the observation counts once."""
    d = drive()
    d.ok(0, "ok0", features=tel(H, 1), seq=0)
    committed = snapshot(api_factory, d.sid)
    d.clock.set(500)
    with monkeypatch.context() as patched:
        patched.setattr(fusion, "compute_risk_score", lambda *a, **k: None)  # a producer bug: no score, yet 'available'
        lenient = TestClient(app, raise_server_exceptions=False)
        response = lenient.post(f"/api/sessions/{d.sid}/infer", json=body("late-fail", features=tel(H, 2), seq=1, stamp=500))
        lenient.close()
    assert response.status_code == 500
    assert snapshot(api_factory, d.sid) == committed
    retry = d.ok(600, "late-fail", attempt=2, features=tel(H, 2), seq=1, stamp=500)
    assert retry["provenance"]["telemetry_obs"] == "new" and retry["window_id"] == 2


def test_g11_the_registry_and_the_fsm_memory_survive_a_restart(drive, api_factory):
    """The worker keeps nothing but the output cache: drop it and the identities are still
    enforced from the persisted runtime_state."""
    d = drive()
    d.ok(0, "r0", image=img(H, "a"), captured=0, frame=(0, 3), features=tel(H, 1), stamp=0, seq=4)
    cache._latest.clear()
    fresh_client = TestClient(app)
    d.client = fresh_client
    repeat = d.ok(500, "r1", image=img(H, "a"), captured=0, frame=(0, 3), features=tel(H, 1), stamp=0, seq=4)
    assert (repeat["provenance"]["vision_obs"], repeat["provenance"]["telemetry_obs"]) == ("repeat", "repeat")
    assert d.send(600, "r2", features=tel(H, 2), seq=3, stamp=600).status_code == 409
    assert d.send(600, "r3", image=img(H, "b"), captured=600, frame=(0, 2)).status_code == 409
    fresh_client.close()


def test_g11_the_registry_crosses_a_gap(drive, api_factory):
    """A pause longer than the tolerance clears the temporal memory but not what was accepted:
    seq 4 is still the high-water mark after it."""
    d = drive()
    d.ok(0, "g0", features=tel(H, 1), seq=4, stamp=0)
    with api_factory() as db:
        sess = db.get(models.SessionMeta, d.sid)
        paused = dict(sess.runtime_state)
        paused["last_processed_ms"] -= 60_000
        sess.runtime_state = paused
        db.commit()
    resumed = d.ok(1000, "g1", features=tel(H, 5), seq=5, stamp=1000)
    assert resumed["provenance"]["telemetry_obs"] == "new"
    state = state_of(api_factory, d.sid)
    assert state["high_srv_us"] == 1_735_732_801_000_000  # re-anchored by the gap (1000 ms after T0)
    assert d.send(1100, "g2", features=tel(H, 1), seq=4, stamp=0).status_code == 409


def test_g11_a_row_persisted_by_the_pre_r10_worker_is_read_safely(drive, api_factory):
    """A pre-R10 row carries a Low streak that began 11 s ago. Inheriting it would recover the latch at
    once; a LIVE window must re-anchor instead and keep HIGH_ALERT. The seed is chosen so the two
    answers differ (the premise below runs the pre-R10 FSM on the same row)."""
    from app import inference
    d = drive()
    seed = {"previous_vision": 0.9, "last_severity": "HIGH_ALERT", "high_since": None,
            "low_since": 1_735_732_789_000.0, "last_processed_ms": 1_735_732_799_500.0,
            "captured_at": at(-500).isoformat(), "telemetry_timestamp": at(-500).isoformat()}
    # Premise: on this row the pre-R10 FSM recovers immediately - so HIGH_ALERT below is a real verdict.
    assert inference._step_alert_fsm(dict(seed), "Low", 1_735_732_800_000.0) == "NORMAL"
    with api_factory() as db:
        sess = db.get(models.SessionMeta, d.sid)
        sess.runtime_state = seed
        db.commit()
    # No registry, no seq: the fallback applies and the OLD watermark is honoured (-600 < -500).
    older = d.send(0, "old-row-0", features=tel(L, 2), stamp=-600)
    assert older.status_code == 409 and older.json()["detail"] == OUT_OF_ORDER
    record = d.ok(0, "old-row", features=tel(L, 1), stamp=0)
    assert record["AlertSeverity"] == "HIGH_ALERT"  # the latch was read from the old row
    state = state_of(api_factory, d.sid)
    assert "low_since" not in state and state["low_srv_us"] == 1_735_732_800_000_000
