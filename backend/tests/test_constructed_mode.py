"""Task 1 (constructed scenario) - the new operation mode is a citizen of the Live/R10 path.

``CONSTRUCTED_SCENARIO_RUNTIME`` is a *Live-like* mode: a session created under it runs the R10
observation pipeline (identity, canonical acquisition time, NEW-only EMA, wall clock AND source
span) exactly like ``LIVE_MODEL_RUNTIME``, and stores its records under its own mode name. The
PREPARED runtime keeps its wall-clock FSM and its 409 on ``/infer`` untouched.

One Live-like judgment rules the backend (``schemas.is_live_like``): the inference loop, the
window persist path and the status endpoint all call it, so a mode can never drift between
"runs the R10 FSM" and "is reported like a live session".

The provider is stubbed the way ``test_r10_observations.py`` stubs it (``ProbStub``): ONLY its
model probabilities, so the request, the real router and the real SQLite transaction are all
exercised. No test needs model weights.
"""
from app import inference

from test_r10_observations import ProbStub, body, img, tel
from test_temporal_contract import fake_clock  # noqa: F401  (fake_clock is used as a fixture)

CONSTRUCTED = "CONSTRUCTED_SCENARIO_RUNTIME"


def test_is_live_like():
    from app.schemas import is_live_like

    assert is_live_like("LIVE_MODEL_RUNTIME") is True
    assert is_live_like(CONSTRUCTED) is True
    assert is_live_like("PREPARED_SESSION_RUNTIME") is False
    assert is_live_like("NO_SUCH_MODE") is False


def test_the_live_mode_constant_is_re_exported_from_inference():
    """Existing call sites import ``inference.LIVE_MODE``; the schemas constant must be the
    same string (inference.py re-imports and re-exports it, the plan's interface)."""
    from app.schemas import LIVE_MODE

    assert inference.LIVE_MODE == LIVE_MODE == "LIVE_MODEL_RUNTIME"


def test_a_constructed_session_is_created_and_echoed(api):
    client, _ = api
    created = client.post("/api/sessions", json={"session_id": "cons-echo",
                                                 "operation_mode": CONSTRUCTED})
    assert created.status_code == 201, created.text
    assert created.json()["operation_mode"] == CONSTRUCTED
    fetched = client.get("/api/sessions/cons-echo")
    assert fetched.status_code == 200 and fetched.json()["operation_mode"] == CONSTRUCTED


def test_infer_on_a_constructed_session_stores_records_under_that_mode(api, fake_clock, monkeypatch):
    client, _ = api
    from app.providers import trained

    stub = ProbStub()
    monkeypatch.setattr(trained, "get_provider", lambda: stub)
    created = client.post("/api/sessions", json={"session_id": "cons-infer",
                                                 "operation_mode": CONSTRUCTED,
                                                 "config": {"ema_alpha": 1}})
    assert created.status_code == 201, created.text
    fake_clock.set(0)
    response = client.post("/api/sessions/cons-infer/infer",
                           json=body("w1", image=img(0.9), captured=0, features=tel(0.9), stamp=0))
    assert response.status_code == 201, response.text
    record = response.json()
    assert record["operation_mode"] == CONSTRUCTED
    windows = client.get("/api/sessions/cons-infer/windows").json()
    assert windows and all(w["operation_mode"] == CONSTRUCTED for w in windows)


def test_a_replay_session_still_gets_the_unchanged_409(api, fake_clock):
    client, sid = api  # the fixture's session is PREPARED_SESSION_RUNTIME
    fake_clock.set(0)
    response = client.post(f"/api/sessions/{sid}/infer",
                           json=body("w1", image=img(0.9), captured=0, features=tel(0.9), stamp=0))
    assert response.status_code == 409
    assert response.json()["detail"] == "Create a live model session first"


def test_status_reports_models_for_a_constructed_session(api):
    client, _ = api
    for sid in ("cons-status", "live-status"):
        mode = CONSTRUCTED if sid.startswith("cons") else "LIVE_MODEL_RUNTIME"
        assert client.post("/api/sessions", json={"session_id": sid,
                                                  "operation_mode": mode}).status_code == 201
    constructed = client.get("/api/sessions/cons-status/system-status").json()
    live = client.get("/api/sessions/live-status/system-status").json()
    assert constructed["models_loaded"] == live["models_loaded"]
    assert constructed["ai_provider"] == live["ai_provider"]
