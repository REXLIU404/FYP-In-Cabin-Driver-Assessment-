"""One authoritative temporal fusion path for replay and trained evidence."""
from datetime import datetime, timezone

from . import fusion
from .config import settings
from .schemas import ModalityFreshness, RiskUpdate, RuntimeConfig, WindowInput


def default_config():
    return RuntimeConfig(**{name: getattr(settings, name) for name in RuntimeConfig.model_fields})


def freshness(status, timestamp, now, tolerance):
    if status == "missing":
        return status
    if timestamp and (now - datetime.fromisoformat(timestamp.replace("Z", "+00:00"))).total_seconds() > tolerance:
        return "stale"
    return status


def run_inference(session_id: str, window_id: int, w: WindowInput, *, state=None,
                  config=None, provenance=None, operation_mode="PREPARED_SESSION_RUNTIME", now=None) -> RiskUpdate:
    state = state if state is not None else {}
    config = config or default_config()
    now = now or datetime.now(timezone.utc)
    now_ms = now.timestamp() * 1000
    provenance = dict(provenance or {"provider": "MockAIProvider", "vision_source": "prepared_replay", "telemetry_source": "prepared_replay"})
    vstatus = freshness(w.vision_status, provenance.get("captured_at") or w.timestamp, now, config.freshness_tolerance_s)
    tstatus = freshness(w.telemetry_status, provenance.get("telemetry_timestamp") or w.timestamp, now, config.freshness_tolerance_s)
    # A gap breaks a sustained streak and prevents EMA from carrying old evidence.
    if now_ms - state.get("last_processed_ms", now_ms) > config.freshness_tolerance_s * 1000:
        for key in ("previous_vision", "severity", "high_since", "low_since", "last_processed_ms"):
            state.pop(key, None)
    pd = w.P_distraction if vstatus != "missing" else 0.0
    if vstatus == "fresh" and state.get("previous_vision") is not None:
        pd = round(config.ema_alpha * pd + (1 - config.ema_alpha) * state["previous_vision"], 3)
    pt = w.P_telemetry_anomaly if tstatus != "missing" else 0.0
    score = fusion.compute_risk_score(pd, pt, config.weight_vision, config.weight_telemetry, vstatus, tstatus)
    level = fusion.map_risk_level(score, config.threshold_low, config.threshold_high)
    health = fusion.map_system_health(vstatus, tstatus)
    dominant = fusion.determine_dominant_evidence(pd, pt, score, health, low=config.threshold_low)
    severity = state.get("severity", "NORMAL")
    if health == "UNAVAILABLE":
        severity, high_since, low_since = "NORMAL", None, None
    elif level == "High":
        high_since = state.get("high_since")
        high_since = now_ms if high_since is None else high_since
        severity = "HIGH_ALERT" if now_ms - high_since >= 2000 or severity == "HIGH_ALERT" else "CAUTION"
        low_since = None
    elif level == "Medium":
        severity, high_since, low_since = "CAUTION", None, None
    else:
        low_since = state.get("low_since")
        low_since = now_ms if low_since is None else low_since
        severity = "NORMAL" if now_ms - low_since >= 10000 else severity
        high_since = None
    state.update(previous_vision=pd if vstatus == "fresh" else None, severity=severity,
                 high_since=high_since, low_since=low_since, last_processed_ms=now_ms)
    provenance["fusion_config"] = config.model_dump()
    provenance.setdefault("P_distraction_raw", w.P_distraction)
    provenance.setdefault("P_telemetry_raw", w.P_telemetry_anomaly)
    return RiskUpdate(
        session_id=session_id, window_id=window_id, timestamp=now.isoformat(),
        P_distraction=pd, P_telemetry_anomaly=pt, RiskScore=score, RiskLevel=level,
        DominantEvidence=dominant, AlertSeverity=severity, SystemHealth=health,
        operation_mode=operation_mode,
        modality_freshness=ModalityFreshness(vision=vstatus, telemetry=tstatus),
        latency_ms=w.latency_ms, visual_top_classes=w.visual_top_classes,
        telemetry_behavior_classes=w.telemetry_behavior_classes,
        telemetry_feature_contributions=w.telemetry_feature_contributions,
        telemetry_features=w.telemetry_features,
        explanation=fusion.build_explanation(dominant, level), provenance=provenance,
    )
