"""Trained-model API/SQLite integration. Images are deterministic test fixtures."""
import base64
import io
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from test_audit_regressions import api  # noqa: F401

MODEL_ROOT = Path(__file__).resolve().parents[2] / "ml/outputs"
# All three stable files (test_model_gate.py checks every ``requires_models`` for it).
requires_models = pytest.mark.skipif(
    not all((MODEL_ROOT / name).exists() for name in ("vision/mobilenetv3_large_vision.onnx",
                                                      "vision/mobilenetv3_large_vision.pt",
                                                      "telemetry/xgb_telemetry.json")),
    reason="local trained artifacts not installed",
)


def image_data(color=(80, 130, 180)):
    buffer = io.BytesIO()
    Image.new("RGB", (640, 480), color).save(buffer, format="JPEG")
    return base64.b64encode(buffer.getvalue()).decode()


def live_session(client, name="live", config=None):
    body = {"session_id": name, "operation_mode": "LIVE_MODEL_RUNTIME"}
    if config:
        body["config"] = config
    response = client.post("/api/sessions", json=body)
    assert response.status_code == 201, response.text
    return name


def payload(request_id="frame1"):
    now = datetime.now(timezone.utc).isoformat()
    return {"request_id": request_id, "image_base64": image_data(), "captured_at": now,
            "telemetry_features": {"speed_kmph": 52, "accel_x": .7, "accel_y": .2,
                "brake_pressure": 20, "steering_angle": 7.5, "throttle": 40,
                "lane_deviation": .21, "headway_distance": 18},
            "telemetry_timestamp": now, "telemetry_source": "prepared_replay"}


@requires_models
def test_real_models_persist_latest_flag_export_and_idempotency(api):
    from app.providers.trained import get_provider
    from app.schemas import LiveInput
    client, _ = api
    sid = live_session(client)
    data = payload()
    # Independent provider call using the exact image/features, before any EMA history.
    expected, _ = get_provider().infer(LiveInput(**data))
    response = client.post(f"/api/sessions/{sid}/infer", json=data)
    assert response.status_code == 201, response.text
    result = response.json()
    assert result["P_distraction"] == pytest.approx(expected.P_distraction, abs=1e-6)
    assert result["P_telemetry_anomaly"] == pytest.approx(expected.P_telemetry_anomaly, abs=1e-6)
    assert len(result["visual_top_classes"]) == 10
    assert len(result["telemetry_behavior_classes"]) == 3
    assert result["visual_top_classes"][0]["label"] == "safe_driving"
    assert result["operation_mode"] == "LIVE_MODEL_RUNTIME"
    assert result["provenance"]["provider"] == "MobileNetV3ONNX+XGBoost"
    assert len(result["provenance"]["vision_model_sha256"]) == 64
    assert result["latency_ms"] >= 0
    retry = client.post(f"/api/sessions/{sid}/infer", json=data).json()
    assert retry == result
    assert client.get(f"/api/sessions/{sid}").json()["total_windows"] == 1
    conflict = {**data, "image_base64": image_data((255, 0, 0))}
    assert client.post(f"/api/sessions/{sid}/infer", json=conflict).status_code == 409
    assert client.get(f"/api/sessions/{sid}/risk/latest").json() == result
    client.patch(f"/api/sessions/{sid}/windows/1/flag?flagged=true")
    exported = client.get(f"/api/sessions/{sid}/export").json()["records"][0]
    assert exported["flagged"] is True
    assert exported["provenance"] == result["provenance"]
    assert "image_base64" not in str(exported)
    csv = client.get(f"/api/sessions/{sid}/export?format=csv").text
    assert result["provenance"]["vision_model_sha256"] in csv
    assert "prepared_replay" in csv
    import csv as csv_module
    import json
    exported_csv = next(csv_module.DictReader(io.StringIO(csv)))
    assert json.loads(exported_csv["telemetry_features"]) == data["telemetry_features"]
    assert json.loads(exported_csv["visual_top_classes"]) == result["visual_top_classes"]
    assert client.get(f"/api/sessions/{sid}/system-status").json()["models_loaded"] is True


@requires_models
def test_bad_frame_does_not_create_result_or_fallback(api):
    client, _ = api
    sid = live_session(client)
    data = {**payload(), "image_base64": "not-base64"}
    assert client.post(f"/api/sessions/{sid}/infer", json=data).status_code == 422
    assert client.get(f"/api/sessions/{sid}").json()["total_windows"] == 0
    assert client.get(f"/api/sessions/{sid}/risk/latest").status_code == 404


@requires_models
def test_missing_expired_and_out_of_order_inputs(api):
    client, _ = api
    sid = live_session(client)
    missing = {"request_id": "empty"}
    response = client.post(f"/api/sessions/{sid}/infer", json=missing)
    assert response.status_code == 201, response.text
    result = response.json()
    # Full "no evidence" contract: nothing fused, so nothing invented (no 0 / Low / NORMAL).
    assert result["assessment_available"] is False
    for name in ("RiskScore", "RiskLevel", "DominantEvidence", "AlertSeverity"):
        assert result[name] is None, name
    assert result["SystemHealth"] == "UNAVAILABLE"
    assert result["assessment_available"] == (result["RiskScore"] is not None) == (result["SystemHealth"] != "UNAVAILABLE")
    assert result["modality_freshness"] == {"vision": "missing", "telemetry": "missing"}
    data = payload("current")
    assert client.post(f"/api/sessions/{sid}/infer", json=data).status_code == 201
    # A DIFFERENT frame (red, not the accepted blue one) with an old stamp: out of order. The same
    # image again would be a repeat of the accepted observation, judged by its first stamp.
    old = {**payload("old"), "image_base64": image_data((255, 0, 0)), "captured_at": "2000-01-01T00:00:00+00:00"}
    assert client.post(f"/api/sessions/{sid}/infer", json=old).status_code == 409
    other = live_session(client, "expired")
    stale = {**payload("stale"), "captured_at": "2000-01-01T00:00:00+00:00"}
    result = client.post(f"/api/sessions/{other}/infer", json=stale).json()
    # Ruling A: an old frame is EXPIRED - scored as missing - not a 0.45-weight "stale" one.
    # Telemetry is current, so the window is DEGRADED but still assessed, from telemetry alone.
    assert result["modality_freshness"] == {"vision": "missing", "telemetry": "fresh"}
    assert result["provenance"]["vision_expired"] is True
    assert result["provenance"]["vision_age_s"] > 700_000_000  # 2000-01-01 is over 26 years ago
    assert result["provenance"]["telemetry_expired"] is False
    assert result["SystemHealth"] == "DEGRADED"
    assert result["assessment_available"] is True


def test_wrong_mode_and_invalid_config(api):
    client, sid = api
    assert client.post(f"/api/sessions/{sid}/infer", json=payload()).status_code == 409
    live = live_session(client)
    assert client.post(f"/api/sessions/{live}/windows", json={"P_distraction": 0.8, "P_telemetry_anomaly": 0.2}).status_code == 409
    r = client.post("/api/sessions", json={"config": {"weight_vision": 0.9, "weight_telemetry": 0.9}})
    assert r.status_code == 422


def test_missing_artifacts_are_503(api, monkeypatch, tmp_path):
    from app.providers import trained
    client, _ = api
    monkeypatch.setattr(trained, "_provider", None)
    monkeypatch.setattr(trained.settings, "model_root", tmp_path)
    sid = live_session(client)
    assert client.get("/api/models").status_code == 503
    assert client.post(f"/api/sessions/{sid}/infer", json=payload()).status_code == 503
    assert client.get(f"/api/sessions/{sid}").json()["total_windows"] == 0


@pytest.mark.parametrize("dependency", ["PIL", "numpy", "onnxruntime", "xgboost"])
def test_missing_inference_dependency_is_503(api, monkeypatch, dependency):
    import builtins
    from app.providers import trained
    client, _ = api
    monkeypatch.setattr(trained, "_provider", None)
    original_import = builtins.__import__

    def without_dependency(name, *args, **kwargs):
        if name == dependency:
            raise ImportError(f"Missing test dependency: {dependency}")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", without_dependency)
    assert client.get("/api/models").status_code == 503


@requires_models
def test_historical_live_record_does_not_imply_models_loaded(api, monkeypatch):
    from app.providers import trained
    client, _ = api
    sid = live_session(client)
    assert client.post(f"/api/sessions/{sid}/infer", json=payload()).status_code == 201
    monkeypatch.setattr(trained, "_provider", None)  # state of a newly restarted worker
    status = client.get(f"/api/sessions/{sid}/system-status").json()
    assert status["total_windows"] == 1
    assert status["models_loaded"] is False
    assert status["model_info"] == {}
    assert trained._provider is None  # status inspection must not load models


def test_sequence_never_reuses_deleted_id_and_survives_cache_reset(api):
    from app import cache
    client, sid = api
    route = f"/api/sessions/{sid}/windows"
    data = {"P_distraction": .2, "P_telemetry_anomaly": .2}
    assert client.post(route, json=data).json()["window_id"] == 1
    client.delete(route + "/1")
    cache.clear(sid)
    result = client.post(route, json={**data, "P_distraction": 1}).json()
    assert result["window_id"] == 2
    assert result["P_distraction"] == .48


def test_fsm_sequence_and_gap_reset():
    from app.inference import run_inference
    from app.schemas import RuntimeConfig, WindowInput
    state = {}
    config = RuntimeConfig(ema_alpha=1)
    time = datetime.now(timezone.utc)
    def tick(seconds, p):
        return run_inference("s", int(seconds) + 1, WindowInput(P_distraction=p, P_telemetry_anomaly=p),
                             state=state, config=config, now=time + timedelta(seconds=seconds))
    assert tick(0, 1).AlertSeverity == "CAUTION"
    assert tick(1, 1).AlertSeverity == "CAUTION"
    assert tick(2, 1).AlertSeverity == "HIGH_ALERT"
    for seconds in range(3, 13):
        assert tick(seconds, 0).AlertSeverity == "HIGH_ALERT"
    assert tick(13, 0).AlertSeverity == "NORMAL"
    assert tick(14, 1).AlertSeverity == "CAUTION"
    assert tick(20, 1).AlertSeverity == "CAUTION"  # gap breaks streak


def test_pil_service_preprocess_matches_training_notebook():
    # Training uses PyTorch, serving uses ORT/XGBoost. Keep these native thread
    # runtimes in separate processes (macOS OpenMP can deadlock when mixed).
    import subprocess
    import sys
    code = """
import base64, io, sys
import torch
import numpy as np
from PIL import Image
from torchvision import transforms
from app.providers.trained import TrainedProvider
torch.set_num_threads(1)
encoded = sys.argv[1]
with Image.open(io.BytesIO(base64.b64decode(encoded))) as image:
    expected = transforms.Compose([transforms.Resize((224,224)), transforms.ToTensor(),
        transforms.Normalize([.485,.456,.406],[.229,.224,.225])])(image.convert('RGB'))
np.testing.assert_allclose(TrainedProvider.preprocess(encoded), expected.unsqueeze(0).numpy(), atol=1e-6)
"""
    # Non-uniform pixels exercise resize interpolation as well as normalization.
    pixels = np.random.default_rng(42).integers(0, 256, size=(71, 113, 3), dtype=np.uint8)
    buffer = io.BytesIO()
    Image.fromarray(pixels).save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode()
    subprocess.run([sys.executable, "-c", code, encoded], check=True, timeout=30)
