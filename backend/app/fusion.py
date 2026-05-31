"""Decision-level late fusion and risk interpretation.

Python port of the framework-agnostic risk-logic layer (ai/src/riskLogic.ts +
ai/src/evidence.ts). The formulas and thresholds are identical so the backend
produces the same risk_update as the TypeScript prototype.
"""
from .config import settings

EVIDENCE_GAP = 0.15


def freshness_weight(status: str) -> float:
    if status == "missing":
        return 0.0
    if status == "stale":
        return 0.45
    return 1.0  # fresh


def _clamp(v: float) -> float:
    return max(0.0, min(1.0, v))


def compute_risk_score(
    p_distraction: float,
    p_telemetry_anomaly: float,
    weight_vision: float,
    weight_telemetry: float,
    vision_status: str = "fresh",
    telemetry_status: str = "fresh",
) -> float:
    """Eq. 2 (freshness-aware). Reduces to the baseline weighted sum when both
    modalities are fresh and weights sum to 1. Returns a 0-100 score."""
    eff_v = weight_vision * freshness_weight(vision_status)
    eff_t = weight_telemetry * freshness_weight(telemetry_status)
    total = eff_v + eff_t
    if total == 0:
        return 0.0  # guard: no usable modality
    score = (eff_v * _clamp(p_distraction) + eff_t * _clamp(p_telemetry_anomaly)) / total
    return round(score * 100, 1)


def map_risk_level(score: float, low: float | None = None, high: float | None = None) -> str:
    low = settings.threshold_low if low is None else low
    high = settings.threshold_high if high is None else high
    if score < low:
        return "Low"
    if score < high:
        return "Medium"
    return "High"


def map_system_health(vision_status: str, telemetry_status: str) -> str:
    if vision_status == "missing" and telemetry_status == "missing":
        return "UNAVAILABLE"
    if vision_status != "fresh" or telemetry_status != "fresh":
        return "DEGRADED"
    return "FULL"


def determine_dominant_evidence(
    p_distraction: float,
    p_telemetry_anomaly: float,
    risk_score: float,
    system_health: str,
    low: float | None = None,
    gap: float = EVIDENCE_GAP,
) -> str:
    low = settings.threshold_low if low is None else low
    if system_health != "FULL":
        return "Partial evidence"
    if risk_score < low:
        return "Low observed risk"
    if abs(p_distraction - p_telemetry_anomaly) < gap:
        return "Combined evidence"
    return "Vision-dominant" if p_distraction > p_telemetry_anomaly else "Telemetry-dominant"


def map_alert_severity(level: str) -> str:
    """Per-window instantaneous severity. The wall-clock AlertSeverity FSM
    (hysteresis) is applied by the orchestration layer, not here."""
    return {"Low": "NORMAL", "Medium": "CAUTION", "High": "HIGH_ALERT"}[level]


def build_explanation(dominant: str, level: str) -> str:
    lvl = level.lower()
    if dominant == "Vision-dominant":
        return f"Vision evidence is driving the {lvl} risk output."
    if dominant == "Telemetry-dominant":
        return f"Telemetry non-safe behaviour is driving the {lvl} risk output."
    if dominant == "Combined evidence":
        return f"Vision and telemetry evidence both contribute to the {lvl} risk output."
    if dominant == "Partial evidence":
        return "Output is based on partial evidence; one modality is stale or missing."
    return "The current window is below the low-risk threshold."
