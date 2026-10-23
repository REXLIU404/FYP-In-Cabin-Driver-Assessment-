"""Regression tests for the defects found in the 2026-09-28 audit.

Each case uses an isolated temporary database. These are now ordinary passing
assertions; the original failing results are preserved in docs/evidence/.
"""

from concurrent.futures import ThreadPoolExecutor
import threading

import pytest


@pytest.fixture
def api(tmp_path):
    # Delayed imports also allow the original smoke test to configure its own
    # database during collection before app settings are instantiated.
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app import cache
    from app.db import Base, get_db
    from app.main import app

    engine = create_engine(
        f"sqlite:///{tmp_path / 'audit.db'}",
        connect_args={"check_same_thread": False},
    )
    factory = sessionmaker(bind=engine)
    Base.metadata.create_all(engine)

    def isolated_db():
        with factory() as db:
            yield db

    old_overrides = dict(app.dependency_overrides)
    app.dependency_overrides[get_db] = isolated_db
    # Intentionally no lifespan context: it would initialize the global engine.
    client = TestClient(app)
    sid = f"audit-{tmp_path.name}"
    assert client.post("/api/sessions", json={"session_id": sid}).status_code == 201
    try:
        yield client, sid
    finally:
        client.close()
        cache.clear(sid)
        app.dependency_overrides.clear()
        app.dependency_overrides.update(old_overrides)
        engine.dispose()


def window(pd=0.8, pt=0.2, **overrides):
    return {"P_distraction": pd, "P_telemetry_anomaly": pt, **overrides}


def test_primary_probability_bounds_are_enforced(api):
    client, sid = api
    assert client.post(f"/api/sessions/{sid}/windows", json=window(1.1)).status_code == 422


def test_provider_status_matches_replay_behavior(api):
    client, sid = api
    result = client.post(f"/api/sessions/{sid}/windows", json=window()).json()
    status = client.get(f"/api/sessions/{sid}/system-status").json()
    assert result["P_distraction"] == 0.8
    assert result["RiskScore"] == 50.0
    assert status["ai_provider"] == "MockAIProvider"
    assert status["models_loaded"] is False


def test_latest_reflects_flag_update(api):
    client, sid = api
    client.post(f"/api/sessions/{sid}/windows", json=window())
    flagged = client.patch(f"/api/sessions/{sid}/windows/1/flag?flagged=true")
    assert flagged.json()["flagged"] is True
    assert client.get(f"/api/sessions/{sid}/risk/latest").json()["flagged"] is True


def test_latest_falls_back_after_deletion(api):
    client, sid = api
    client.post(f"/api/sessions/{sid}/windows", json=window(0.1))
    client.post(f"/api/sessions/{sid}/windows", json=window(0.9))
    assert client.delete(f"/api/sessions/{sid}/windows/2").status_code == 204
    assert client.get(f"/api/sessions/{sid}/risk/latest").json()["window_id"] == 1


def test_latest_is_empty_after_all_windows_deleted(api):
    client, sid = api
    client.post(f"/api/sessions/{sid}/windows", json=window())
    assert client.delete(f"/api/sessions/{sid}/windows/1").status_code == 204
    assert client.get(f"/api/sessions/{sid}/risk/latest").status_code == 404


def test_concurrent_writers_receive_unique_window_ids(api):
    client, sid = api
    barrier = threading.Barrier(2, timeout=10)

    def post_together():
        barrier.wait()
        return client.post(f"/api/sessions/{sid}/windows", json=window())

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(post_together) for _ in range(2)]
        responses = [future.result(timeout=15) for future in futures]
    assert all(response.status_code == 201 for response in responses)
    assert sorted(response.json()["window_id"] for response in responses) == [1, 2]


def test_invalid_timestamp_is_rejected(api):
    client, sid = api
    response = client.post(
        f"/api/sessions/{sid}/windows", json=window(timestamp="not-a-timestamp")
    )
    assert response.status_code == 422


def test_old_capture_timestamp_cannot_be_full_health(api):
    client, sid = api
    response = client.post(
        f"/api/sessions/{sid}/windows",
        json=window(timestamp="2000-01-01T00:00:00Z"),
    )
    assert response.status_code == 201
    assert response.json()["SystemHealth"] != "FULL"


def test_first_high_window_observes_alert_sustain_period(api):
    client, sid = api
    response = client.post(f"/api/sessions/{sid}/windows", json=window(1.0, 1.0))
    assert response.status_code == 201
    assert response.json()["AlertSeverity"] == "CAUTION"


def test_second_window_uses_vision_ema(api):
    client, sid = api
    client.post(f"/api/sessions/{sid}/windows", json=window(0.2))
    response = client.post(f"/api/sessions/{sid}/windows", json=window(1.0))
    assert response.status_code == 201
    assert response.json()["P_distraction"] == pytest.approx(0.35 * 1.0 + 0.65 * 0.2)


@pytest.mark.parametrize(
    "overrides",
    [
        {"latency_ms": -100},
        {"visual_top_classes": [{"label": "safe_driving", "probability": 2.0}]},
    ],
    ids=["negative-latency", "class-probability-over-one"],
)
def test_invalid_measurements_are_rejected(api, overrides):
    client, sid = api
    response = client.post(f"/api/sessions/{sid}/windows", json=window(**overrides))
    assert response.status_code == 422
