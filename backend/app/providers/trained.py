"""Actual existing MobileNet ONNX and XGBoost artifacts. No network downloads."""
import base64
import binascii
import hashlib
import io
import json
import threading
import time
from datetime import datetime, timezone

from ..config import settings
from ..schemas import LiveInput, WindowInput


class ModelUnavailable(RuntimeError):
    pass


class InvalidFrame(ValueError):
    pass


class TrainedProvider:
    name = "MobileNetV3ONNX+XGBoost"

    def __init__(self):
        from PIL import Image  # noqa: F401 - validate decoder dependency at readiness check
        import numpy as np
        import onnxruntime as ort
        import xgboost as xgb

        self.xgb = xgb
        root = settings.model_root
        vision_path = root / "vision/mobilenetv3_large_vision.onnx"
        telemetry_path = root / "telemetry/xgb_telemetry.json"
        vision = json.loads((root / "vision/metrics.json").read_text())
        telemetry = json.loads((root / "telemetry/metrics.json").read_text())
        if vision["classes"] != [f"c{i}" for i in range(10)] or telemetry["classes"] != ["Safe", "Aggressive", "Distracted"]:
            raise ModelUnavailable("Model class order does not match runtime contract")
        self.labels = ["safe_driving", *vision["class_names"][1:]]
        self.features = telemetry["features"]
        from ..schemas import TelemetryFeatures
        if self.features != list(TelemetryFeatures.model_fields):
            raise ModelUnavailable("Model telemetry feature order does not match runtime contract")
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = settings.inference_threads
        opts.inter_op_num_threads = 1
        self.vision = ort.InferenceSession(str(vision_path), opts, providers=["CPUExecutionProvider"])
        inp = self.vision.get_inputs()[0]
        if inp.type != "tensor(float)" or inp.shape[1:] != [3, 224, 224]:
            raise ModelUnavailable("Expected float32 NCHW 224x224 image model")
        self.input_name = inp.name
        self.telemetry = xgb.Booster()
        self.telemetry.load_model(telemetry_path)
        self.telemetry.set_param({"nthread": settings.inference_threads})
        self.iteration_end = int(self.telemetry.attr("best_iteration")) + 1
        if self.telemetry.feature_names != self.features or self.iteration_end != telemetry["best_iteration"] + 1:
            raise ModelUnavailable("Telemetry model metadata mismatch")
        output = self.vision.run(None, {self.input_name: np.zeros((1, 3, 224, 224), np.float32)})[0]
        if output.shape != (1, 10) or not np.isfinite(output).all():
            raise ModelUnavailable("Vision model warmup returned invalid logits")
        self.info = {
            "provider": self.name,
            "vision": {"architecture": "mobilenet_v3_large", "sha256": hashlib.sha256(vision_path.read_bytes()).hexdigest(),
                       "runtime": "onnxruntime_cpu", "classes": self.labels, "input": "RGB NCHW float32 224x224",
                       "mean": [0.485, 0.456, 0.406], "std": [0.229, 0.224, 0.225]},
            "telemetry": {"architecture": "xgboost", "sha256": hashlib.sha256(telemetry_path.read_bytes()).hexdigest(),
                          "classes": telemetry["classes"], "features": self.features, "iteration_range": [0, self.iteration_end]},
            "scope": "Frontal-camera inference is experimental; source dataset metrics do not validate frontal reliability",
        }

    @staticmethod
    def preprocess(encoded):
        import numpy as np
        from PIL import Image, UnidentifiedImageError
        if encoded.startswith("data:"):
            if not encoded.startswith(("data:image/jpeg;base64,", "data:image/png;base64,")):
                raise InvalidFrame("Only JPEG/PNG frames are supported")
            encoded = encoded.split(",", 1)[1]
        try:
            raw = base64.b64decode(encoded, validate=True)
            if len(raw) > 2_000_000:
                raise InvalidFrame("Frame exceeds 2 MB")
            with Image.open(io.BytesIO(raw)) as image:
                if image.format not in ("JPEG", "PNG") or max(image.size) > 4096 or min(image.size) < 16:
                    raise InvalidFrame("Expected JPEG/PNG image between 16 and 4096 pixels per side")
                image = image.convert("RGB").resize((224, 224), Image.Resampling.BILINEAR)
                values = np.asarray(image, dtype=np.float32) / 255.0
        except (binascii.Error, UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
            raise InvalidFrame("Invalid or damaged image") from exc
        values = (values - np.array([0.485, 0.456, 0.406], np.float32)) / np.array([0.229, 0.224, 0.225], np.float32)
        return np.ascontiguousarray(values.transpose(2, 0, 1)[None])

    def infer(self, data: LiveInput):
        import numpy as np
        started = time.perf_counter()
        pd, pt, visual, behaviors = 0.0, 0.0, [], []
        timing = {}
        if data.image_base64 is not None:
            x = self.preprocess(data.image_base64)
            timing["preprocess_ms"] = (time.perf_counter() - started) * 1000
            before = time.perf_counter()
            logits = self.vision.run(None, {self.input_name: x})[0][0]
            if not np.isfinite(logits).all():
                raise ModelUnavailable("Vision model produced non-finite output")
            exp = np.exp(logits - np.max(logits))
            probs = exp / exp.sum()
            pd = float(1 - probs[0])
            visual = [{"label": label, "probability": float(prob)} for label, prob in zip(self.labels, probs)]
            timing["vision_ms"] = (time.perf_counter() - before) * 1000
        if data.telemetry_features is not None:
            before = time.perf_counter()
            values = data.telemetry_features.model_dump()
            matrix = self.xgb.DMatrix(np.array([[values[k] for k in self.features]], dtype=np.float32), feature_names=self.features)
            probs = self.telemetry.predict(matrix, iteration_range=(0, self.iteration_end))[0]
            if probs.shape != (3,) or not np.isfinite(probs).all():
                raise ModelUnavailable("Telemetry model produced invalid output")
            pt = float(1 - probs[0])
            behaviors = [{"label": label, "probability": float(prob)} for label, prob in zip(["Safe", "Aggressive", "Distracted"], probs)]
            timing["telemetry_ms"] = (time.perf_counter() - before) * 1000
        window = WindowInput(P_distraction=pd, P_telemetry_anomaly=pt,
                             vision_status="fresh" if data.image_base64 is not None else "missing",
                             telemetry_status="fresh" if data.telemetry_features is not None else "missing",
                             visual_top_classes=visual, telemetry_behavior_classes=behaviors,
                             telemetry_features=data.telemetry_features,
                             latency_ms=round((time.perf_counter() - started) * 1000))
        provenance = {"provider": self.name, "request_id": data.request_id,
                      "vision_source": "camera_frame" if data.image_base64 is not None else "missing",
                      "telemetry_source": data.telemetry_source,
                      "vision_model_sha256": self.info["vision"]["sha256"],
                      "telemetry_model_sha256": self.info["telemetry"]["sha256"],
                      "captured_at": data.captured_at, "telemetry_timestamp": data.telemetry_timestamp,
                      "processed_at": datetime.now(timezone.utc).isoformat(), "timing_ms": timing,
                      "P_distraction_raw": pd, "P_telemetry_raw": pt}
        return window, provenance


_provider = None
_load_lock = threading.Lock()


def loaded_model_info():
    """Inspect this worker without loading weights or inferring readiness from old records."""
    return _provider.info if _provider is not None else {}


def get_provider():
    global _provider
    with _load_lock:
        if _provider is None:
            try:
                _provider = TrainedProvider()
            except Exception as exc:
                raise ModelUnavailable("Trained models are unavailable; check local model artifacts and inference dependencies") from exc
    return _provider
