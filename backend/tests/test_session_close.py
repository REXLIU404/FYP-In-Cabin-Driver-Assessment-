"""Session lifecycle: an ended session refuses new windows but stays readable.

The close operation is additive to the existing lifecycle (create -> assess -> close).
Nothing here touches fusion, EMA, the alert FSM or the R10 admission rules: a closed
session is refused before any of them runs.
"""
import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app import cache, models
from app.main import app

CLOSED_DETAIL = "Session is closed"
LIVE = "LIVE_MODEL_RUNTIME"
PREPARED = "PREPARED_SESSION_RUNTIME"


@pytest.fixture
def close_api(api_factory):
    client = TestClient(app)
    try:
        yield client, api_factory
    finally:
        client.close()
        cache._latest.clear()


def create(client, sid, mode=PREPARED):
    response = client.post("/api/sessions", json={"session_id": sid, "operation_mode": mode})
    assert response.status_code == 201, response.text
    return response.json()


def seed_state(factory, sid, *, next_window_id, state):
    with factory() as db:
        session = db.get(models.SessionMeta, sid)
        session.next_window_id = next_window_id
        session.runtime_state = state
        db.commit()


def snapshot(factory, sid):
    with factory() as db:
        session = db.get(models.SessionMeta, sid)
        records = (db.query(models.InferenceRecord).filter_by(session_id=sid)
                   .order_by(models.InferenceRecord.window_id).all())
        return {
            "status": session.status,
            "next_window_id": session.next_window_id,
            "runtime_state": json.loads(json.dumps(session.runtime_state)),
            "records": [(record.window_id, record.request_id) for record in records],
        }


def faults(factory, sid):
    with factory() as db:
        return [dict(row) for row in db.execute(
            text("SELECT request_id, attempt_index, origin, error_category, http_status, "
                 "retryable, recovery_status FROM fault_events "
                 "WHERE session_id = :sid ORDER BY id"), {"sid": sid}).mappings()]


def window():
    return {"P_distraction": 0.2, "P_telemetry_anomaly": 0.3}


def test_close_marks_a_session_closed_and_is_idempotent(close_api):
    client, factory = close_api
    created = create(client, "close-idempotent")
    assert created["status"] == "ACTIVE"

    first = client.post("/api/sessions/close-idempotent/close")
    assert first.status_code == 200, first.text
    assert first.json()["status"] == "CLOSED"
    assert first.json()["total_windows"] == 0
    assert client.get("/api/sessions/close-idempotent").json()["status"] == "CLOSED"
    assert client.get("/api/sessions").json()[0]["status"] == "CLOSED"

    second = client.post("/api/sessions/close-idempotent/close")
    assert second.status_code == 200, second.text
    assert second.json() == first.json()
    assert faults(factory, "close-idempotent") == []


def test_close_an_unknown_session_is_404(close_api):
    client, _ = close_api
    response = client.post("/api/sessions/never-created/close")
    assert response.status_code == 404


def test_infer_on_a_closed_session_is_409_and_writes_one_non_retryable_fault(close_api):
    client, factory = close_api
    create(client, "closed-infer", LIVE)
    seed_state(factory, "closed-infer", next_window_id=3,
               state={"obs_t_seq": 7, "obs_t_hash": "keep"})
    before = snapshot(factory, "closed-infer")
    assert client.post("/api/sessions/closed-infer/close").status_code == 200

    response = client.post("/api/sessions/closed-infer/infer", json={"request_id": "closed-1"})

    assert response.status_code == 409, response.text
    assert response.json()["detail"] == CLOSED_DETAIL
    assert snapshot(factory, "closed-infer") == {**before, "status": "CLOSED"}
    rows = faults(factory, "closed-infer")
    assert len(rows) == 1, rows
    assert rows[0] == {
        "request_id": "closed-1", "attempt_index": 1, "origin": "session",
        "error_category": "session_closed", "http_status": 409, "retryable": 0,
        "recovery_status": "open",
    }
    assert client.get("/api/sessions/closed-infer/windows").json() == []


def test_windows_on_a_closed_session_is_409_and_writes_one_fault(close_api):
    client, factory = close_api
    create(client, "closed-windows", PREPARED)
    seed_state(factory, "closed-windows", next_window_id=2,
               state={"captured_at": "2026-01-01T00:00:00+00:00"})
    before = snapshot(factory, "closed-windows")
    assert client.post("/api/sessions/closed-windows/close").status_code == 200

    response = client.post("/api/sessions/closed-windows/windows", json=window())

    assert response.status_code == 409, response.text
    assert response.json()["detail"] == CLOSED_DETAIL
    assert snapshot(factory, "closed-windows") == {**before, "status": "CLOSED"}
    rows = faults(factory, "closed-windows")
    assert len(rows) == 1, rows
    assert (rows[0]["request_id"], rows[0]["attempt_index"], rows[0]["origin"],
            rows[0]["error_category"], rows[0]["http_status"], rows[0]["retryable"]) == (
        None, None, "session", "session_closed", 409, 0)


def test_a_closed_session_remains_readable_and_deletable(close_api):
    client, _ = close_api
    create(client, "closed-readable", PREPARED)
    saved = client.post("/api/sessions/closed-readable/windows", json=window())
    assert saved.status_code == 201, saved.text

    closed = client.post("/api/sessions/closed-readable/close")
    assert closed.status_code == 200, closed.text
    assert closed.json()["total_windows"] == 1

    windows = client.get("/api/sessions/closed-readable/windows")
    assert windows.status_code == 200
    assert [record["window_id"] for record in windows.json()] == [1]
    latest = client.get("/api/sessions/closed-readable/risk/latest")
    assert latest.status_code == 200 and latest.json()["window_id"] == 1
    exported = client.get("/api/sessions/closed-readable/export?format=json")
    assert exported.status_code == 200
    assert [record["window_id"] for record in exported.json()["records"]] == [1]
    csv_export = client.get("/api/sessions/closed-readable/export?format=csv")
    assert csv_export.status_code == 200 and "RiskScore" in csv_export.text
    status = client.get("/api/sessions/closed-readable/system-status")
    assert status.status_code == 200
    assert status.json()["exists"] is True and status.json()["total_windows"] == 1

    assert client.delete("/api/sessions/closed-readable").status_code == 204
    assert client.get("/api/sessions/closed-readable").status_code == 404
