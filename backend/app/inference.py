"""Inference Orchestrator.

Single place that turns a window payload into a fully-fused ``RiskUpdate``:
MockAIProvider (Core AI stand-in) -> late fusion -> risk interpretation ->
explanation. Persistence and window-id allocation stay in the router; this
module is pure (no DB), so it can be reused by the windows endpoint, a future
fixed-interval fusion loop, or tests.
"""
from datetime import datetime, timezone

from . import fusion
from .config import settings
from .providers.mock_ai import mock_ai
from .schemas import ModalityFreshness, RiskUpdate, WindowInput


def run_inference(session_id: str, window_id: int, w: WindowInput) -> RiskUpdate:
    """Run the Core AI stand-in + late fusion for one window. Pure: no DB I/O."""
    out = mock_ai.infer(w)

    score = fusion.compute_risk_score(
        out["P_distraction"],
        out["P_telemetry_anomaly"],
        settings.weight_vision,
        settings.weight_telemetry,
        out["vision_status"],
        out["telemetry_status"],
    )
    level = fusion.map_risk_level(score)
    health = fusion.map_system_health(out["vision_status"], out["telemetry_status"])
    dominant = fusion.determine_dominant_evidence(
        out["P_distraction"], out["P_telemetry_anomaly"], score, health
    )
    alert = fusion.map_alert_severity(level)
    ts = w.timestamp or datetime.now(timezone.utc).isoformat()

    return RiskUpdate(
        session_id=session_id,
        window_id=window_id,
        timestamp=ts,
        P_distraction=out["P_distraction"],
        P_telemetry_anomaly=out["P_telemetry_anomaly"],
        RiskScore=score,
        RiskLevel=level,
        DominantEvidence=dominant,
        AlertSeverity=alert,
        SystemHealth=health,
        modality_freshness=ModalityFreshness(
            vision=out["vision_status"], telemetry=out["telemetry_status"]
        ),
        latency_ms=out["latency_ms"],
        visual_top_classes=out["visual_top_classes"],
        telemetry_behavior_classes=out["telemetry_behavior_classes"],
        telemetry_feature_contributions=out["telemetry_feature_contributions"],
        telemetry_features=out["telemetry_features"],
        explanation=fusion.build_explanation(dominant, level),
    )
