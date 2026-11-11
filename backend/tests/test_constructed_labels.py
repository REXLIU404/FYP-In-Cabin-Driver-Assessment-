"""Task 2 (constructed scenario) - server-authoritative source labels, the ``replay`` block and
``replay_clock``.

In CONSTRUCTED_SCENARIO_RUNTIME the server writes the source labels itself, whatever the client
claims: ``provenance.vision_source == "dataset_replay"`` and ``provenance.telemetry_source ==
"dataset_replay"`` (a branch the request did not carry stays ``"missing"``). Live sessions keep
``camera_frame`` / the client's own ``telemetry_source`` - ``trained.py`` is not touched.

The optional ``replay`` block rides in the request, is kept VERBATIM in ``provenance.replay``,
and never influences a score: it is a ground-truth label for the demo, not an input to fusion.
It is accepted only in a constructed scenario session (422 ``input_validation`` elsewhere);
``captured_at_source: "replay_clock"`` is accepted only there too. An absent ``replay`` block
leaves the request hash unchanged, and the schema keeps refusing ``telemetry_source:
"dataset_replay"`` - the client is never believed about the dataset.

The provider for most tests is the REAL ``TrainedProvider`` with fake weights (the
``test_fault_events`` path): its provenance is overwritten by the mode logic, which is the
point. The hash / score tests use ``ProbStub`` so the probabilities are spelled by the request
bytes and no timing noise enters the comparison.
"""
import csv
import io
import json
from types import SimpleNamespace

import pytest
from pydantic import ValidationError
from fastapi.testclient import TestClient

from app.routers import windows
from app.schemas import LiveInput

from test_fault_events import FakeBooster, FakeVision, build_provider, image_data, make_payload
from test_r10_observations import LEGACY_BODIES, ProbStub, body, img, tel
from test_temporal_contract import fake_clock  # noqa: F401  (fake_clock is used as a fixture)

CONSTRUCTED = "CONSTRUCTED_SCENARIO_RUNTIME"
BLOCK = {"scenario_id": "viva_v1", "segment_index": 3, "frame_file": "0000_img_1.jpg",
         "vision_label": "safe_driving", "telemetry_label": "Safe", "telemetry_row": 42}


@pytest.fixture
def replay_session(api_factory, tmp_path, monkeypatch):
    """A constructed-scenario session on a tmp database with the REAL provider class and fake
    weights, the way ``test_fault_events.live`` builds it."""
    from app import cache
    from app.main import app
    from app.providers import trained

    vision, booster = FakeVision(), FakeBooster()
    monkeypatch.setattr(trained, "_provider", build_provider(vision, booster))
    client = TestClient(app, raise_server_exceptions=False)
    env = SimpleNamespace(client=client, sid=f"cons-{tmp_path.name}", vision=vision,
                          booster=booster, factory=api_factory)
    created = client.post("/api/sessions", json={"session_id": env.sid,
                                                 "operation_mode": CONSTRUCTED})
    assert created.status_code == 201, created.text
    try:
        yield env
    finally:
        client.close()
        cache._latest.clear()


# ------------------------------------------------------------------ the server-authoritative labels
def test_the_server_writes_dataset_replay_whatever_the_client_claims(replay_session):
    """The client declares ``telemetry_source: "prepared_replay"`` (and the provider echoes
    ``camera_frame`` for the image): the mode overwrites both with ``dataset_replay``."""
    env = replay_session
    response = env.client.post(f"/api/sessions/{env.sid}/infer", json=make_payload("labelled-1"))
    assert response.status_code == 201, response.text
    provenance = response.json()["provenance"]
    assert provenance["vision_source"] == "dataset_replay"
    assert provenance["telemetry_source"] == "dataset_replay"


def test_an_absent_branch_is_labelled_missing(replay_session):
    env = replay_session
    response = env.client.post(f"/api/sessions/{env.sid}/infer",
                               json=make_payload("missing-1", image=False, telemetry=False))
    assert response.status_code == 201, response.text
    provenance = response.json()["provenance"]
    assert provenance["vision_source"] == "missing"
    assert provenance["telemetry_source"] == "missing"


def test_live_sessions_still_say_camera_frame_and_prepared_replay(replay_session):
    env = replay_session
    created = env.client.post("/api/sessions", json={"session_id": f"{env.sid}-live",
                                                     "operation_mode": "LIVE_MODEL_RUNTIME"})
    assert created.status_code == 201, created.text
    response = env.client.post(f"/api/sessions/{env.sid}-live/infer", json=make_payload("live-1"))
    assert response.status_code == 201, response.text
    provenance = response.json()["provenance"]
    assert provenance["vision_source"] == "camera_frame"
    assert provenance["telemetry_source"] == "prepared_replay"


# ------------------------------------------------------------------ the replay block
def test_the_replay_block_is_kept_in_provenance(replay_session):
    env = replay_session
    body = {**make_payload("block-1"), "replay": BLOCK}
    response = env.client.post(f"/api/sessions/{env.sid}/infer", json=body)
    assert response.status_code == 201, response.text
    assert response.json()["provenance"]["replay"] == BLOCK


def test_truth_labels_never_change_the_scores(api, fake_clock, monkeypatch):
    """Two constructed sessions, IDENTICAL inputs, different ground-truth labels: the records
    differ in nothing but the replay block, the ids and the server timestamp. A label that
    leaked into fusion (or the hash of anything but the request) would break the equality."""
    from app.providers import trained

    client, _ = api
    stub = ProbStub()
    monkeypatch.setattr(trained, "get_provider", lambda: stub)
    base = body("same", image=img(0.9), captured=0, features=tel(0.1), stamp=0)
    labels = ({"scenario_id": "s", "segment_index": 0, "vision_label": "safe_driving",
               "telemetry_label": "Safe"},
              {"scenario_id": "s", "segment_index": 0, "vision_label": "distracted_9",
               "telemetry_label": "Distracted"})
    records = []
    for n, replay in enumerate(labels):
        sid = f"cons-truth-{n}"
        created = client.post("/api/sessions", json={"session_id": sid,
                                                     "operation_mode": CONSTRUCTED,
                                                     "config": {"ema_alpha": 1}})
        assert created.status_code == 201, created.text
        fake_clock.set(0)
        response = client.post(f"/api/sessions/{sid}/infer", json={**base, "replay": replay})
        assert response.status_code == 201, response.text
        records.append(response.json())
    a, b = records
    for record in (a, b):
        record.pop("session_id")
        record.pop("timestamp")
        record.pop("latency_ms")  # measured per request; a timing, not a score
        record["provenance"].pop("replay")
    assert a == b


@pytest.mark.parametrize("kind", ["replay_block", "replay_clock"])
def test_replay_data_on_a_live_session_is_422_input_validation(api, kind):
    client, _ = api
    created = client.post("/api/sessions", json={"session_id": "live-422",
                                                 "operation_mode": "LIVE_MODEL_RUNTIME"})
    assert created.status_code == 201, created.text
    payload = body("r", image=img(0.9), captured=0, features=tel(0.9), stamp=0)
    if kind == "replay_block":
        payload["replay"] = {"scenario_id": "s", "segment_index": 0}
    else:
        payload["captured_at_source"] = "replay_clock"
    response = client.post("/api/sessions/live-422/infer", json=payload)
    assert response.status_code == 422, response.text
    faults = client.get("/api/faults", params={"session_id": "live-422"}).json()
    assert any(f["error_category"] == "input_validation" for f in faults), faults


def test_an_absent_replay_block_keeps_the_request_hash():
    """``canonical_body`` must not grow a ``replay`` key when the block is absent, or every
    pre-upgrade request hash would change (LEGACY_BODIES pins the three fixed hashes)."""
    legacy_body, legacy_hash = LEGACY_BODIES[0]
    parsed = LiveInput(**legacy_body)
    assert "replay" not in parsed.canonical_body()
    assert windows.request_digest(parsed) == legacy_hash


def test_the_same_request_id_with_another_replay_block_is_409(replay_session):
    env = replay_session
    first = {**make_payload("dup"), "replay": {**BLOCK, "segment_index": 0}}
    second = {**make_payload("dup"), "replay": {**BLOCK, "segment_index": 1}}
    ok = env.client.post(f"/api/sessions/{env.sid}/infer", json=first)
    assert ok.status_code == 201, ok.text
    conflict = env.client.post(f"/api/sessions/{env.sid}/infer", json=second)
    assert conflict.status_code == 409
    assert conflict.json()["detail"] == "request_id already used for different input"


def test_the_request_schema_does_not_accept_dataset_replay():
    with pytest.raises(ValidationError):
        LiveInput(request_id="r", image_base64=image_data(), captured_at="2025-01-01T12:00:00+00:00",
                  telemetry_features={"speed_kmph": 52, "accel_x": 0.7, "accel_y": 0.2, "brake_pressure": 20,
                                      "steering_angle": 7.5, "throttle": 40, "lane_deviation": 0.21,
                                      "headway_distance": 18},
                  telemetry_timestamp="2025-01-01T12:00:00+00:00", telemetry_source="dataset_replay")


def test_both_exports_show_dataset_replay(replay_session):
    env = replay_session
    body = {**make_payload("exp-1"), "replay": BLOCK}
    response = env.client.post(f"/api/sessions/{env.sid}/infer", json=body)
    assert response.status_code == 201, response.text
    exported = env.client.get(f"/api/sessions/{env.sid}/export").json()["records"]
    assert exported[0]["provenance"]["vision_source"] == "dataset_replay"
    assert exported[0]["provenance"]["telemetry_source"] == "dataset_replay"
    assert exported[0]["provenance"]["replay"] == BLOCK
    csv_text = env.client.get(f"/api/sessions/{env.sid}/export", params={"format": "csv"}).text
    rows = list(csv.DictReader(io.StringIO(csv_text)))
    assert rows and rows[0]["vision_source"] == "dataset_replay"
    assert rows[0]["telemetry_source"] == "dataset_replay"
    cell = json.loads(rows[0]["provenance"])  # the whole provenance, JSON-encoded in one cell
    assert cell["replay"] == BLOCK
