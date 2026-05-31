"""End-to-end CRUD + fusion smoke test using FastAPI TestClient (no live server)."""
import os
import tempfile

os.environ["DRA_DATABASE_URL"] = "sqlite:///" + os.path.join(
    tempfile.gettempdir(), "dra_test.db"
)

from fastapi.testclient import TestClient  # noqa: E402

from app.db import Base, engine  # noqa: E402
from app.main import app  # noqa: E402

# Ensure a clean schema for the test DB (lifespan only runs under the client
# context manager; create explicitly so each test run starts from tables).
Base.metadata.drop_all(bind=engine)
Base.metadata.create_all(bind=engine)

client = TestClient(app)


def _window(pd, pt, v="fresh", t="fresh"):
    return {
        "P_distraction": pd,
        "P_telemetry_anomaly": pt,
        "vision_status": v,
        "telemetry_status": t,
        "telemetry_features": {
            "speed_kmph": 52.0,
            "accel_x": 0.7,
            "accel_y": 0.2,
            "brake_pressure": 20.0,
            "steering_angle": 7.5,
            "throttle": 40.0,
            "lane_deviation": 0.21,
            "headway_distance": 18.0,
        },
        "telemetry_behavior_classes": [
            {"label": "Safe", "probability": 0.72},
            {"label": "Aggressive", "probability": 0.18},
            {"label": "Distracted", "probability": 0.10},
        ],
        "latency_ms": 42,
    }


def test_full_crud_and_fusion():
    # Create
    r = client.post("/api/sessions", json={"session_id": "T001"})
    assert r.status_code == 201, r.text

    # Create window -> fusion. 0.5/0.5, both fresh: (0.5*0.8+0.5*0.2)*100 = 50.0
    r = client.post("/api/sessions/T001/windows", json=_window(0.8, 0.2))
    assert r.status_code == 201, r.text
    ru = r.json()
    assert ru["RiskScore"] == 50.0
    assert ru["RiskLevel"] == "Medium"
    assert ru["DominantEvidence"] == "Vision-dominant"
    assert ru["SystemHealth"] == "FULL"
    assert ru["window_id"] == 1

    # Read (list + latest)
    assert len(client.get("/api/sessions/T001/windows").json()) == 1
    assert client.get("/api/sessions/T001/risk/latest").json()["RiskScore"] == 50.0

    # Degraded: telemetry missing -> score = vision only = 80, DEGRADED, Partial
    ru2 = client.post(
        "/api/sessions/T001/windows", json=_window(0.8, 0.9, t="missing")
    ).json()
    assert ru2["RiskScore"] == 80.0
    assert ru2["SystemHealth"] == "DEGRADED"
    assert ru2["DominantEvidence"] == "Partial evidence"

    # Update (flag)
    flagged = client.patch("/api/sessions/T001/windows/1/flag?flagged=true").json()
    assert flagged["flagged"] is True

    # Export
    assert client.get("/api/sessions/T001/export?format=json").status_code == 200
    csv_resp = client.get("/api/sessions/T001/export?format=csv")
    assert "RiskScore" in csv_resp.text

    # Delete
    assert client.delete("/api/sessions/T001").status_code == 204
    assert client.get("/api/sessions/T001").status_code == 404
