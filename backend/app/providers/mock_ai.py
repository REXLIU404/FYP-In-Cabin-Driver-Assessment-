"""MockAIProvider — stand-in for the Core AI Inference Layer.

In production this would call MobileNetV3 (vision) and the XGBoost behaviour
classifier (telemetry). For the FYP1 backend skeleton it echoes the
probabilities supplied with the window (which originate from the prepared
session), so the backend can demonstrate the full fusion + persistence pipeline
without trained models. Swapping in real models is a drop-in replacement of
this class only.
"""
from ..schemas import WindowInput


class MockAIProvider:
    name = "MockAIProvider"

    def infer(self, w: WindowInput) -> dict:
        return {
            "P_distraction": w.P_distraction,
            "P_telemetry_anomaly": w.P_telemetry_anomaly,
            "vision_status": w.vision_status,
            "telemetry_status": w.telemetry_status,
            "visual_top_classes": w.visual_top_classes,
            "telemetry_behavior_classes": w.telemetry_behavior_classes,
            "telemetry_feature_contributions": w.telemetry_feature_contributions,
            "telemetry_features": w.telemetry_features,
            "latency_ms": w.latency_ms,
        }


mock_ai = MockAIProvider()
