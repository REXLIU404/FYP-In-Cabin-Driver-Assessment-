"""
Decision-level late-fusion risk logic — Python reference implementation.

This module is the canonical, language-agnostic specification of the fusion and
risk-scoring engine. The FYP1 dashboard runs the identical algorithm client-side
in TypeScript (ai/src/riskLogic.ts) to render the live demo; this Python module is
the same maths in the AI-inference-layer language, and is fully runnable/testable.

Only the branch probability INPUTS (P_distraction, P_telemetry_anomaly) are mocked
in FYP1 (prepared values standing in for the untrained MobileNetV3 / XGBoost).
The fusion engine below is REAL working code, not a mock.
"""
from __future__ import annotations
from dataclasses import dataclass

# ---- thresholds & weights (transparent prototype parameters) ----
THRESHOLD_LOW = 30.0      # RiskScore < 30  -> Low
THRESHOLD_HIGH = 60.0     # RiskScore >= 60 -> High
EVIDENCE_GAP = 0.15       # |pD - pT| below this -> Combined evidence
EMA_ALPHA = 0.35          # temporal smoothing coefficient


def clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def freshness_weight(status: str) -> float:
    """fresh -> full trust, stale -> down-weighted, missing -> dropped."""
    return {"fresh": 1.0, "stale": 0.45, "missing": 0.0}.get(status, 1.0)


def compute_risk_score(
    p_distraction: float,
    p_telemetry_anomaly: float,
    w_vision: float = 0.5,
    w_telemetry: float = 0.5,
    vision_status: str = "fresh",
    telemetry_status: str = "fresh",
) -> float:
    """
    Freshness-weighted decision-level late fusion, returned on a 0..100 scale.

        eff_v = w_vision    * fw(vision_status)
        eff_t = w_telemetry * fw(telemetry_status)
        RiskScore = (eff_v * pD + eff_t * pT) / (eff_v + eff_t) * 100
    """
    eff_v = w_vision * freshness_weight(vision_status)
    eff_t = w_telemetry * freshness_weight(telemetry_status)
    total = eff_v + eff_t
    if total == 0:
        return 0.0
    score = (eff_v * clamp01(p_distraction) + eff_t * clamp01(p_telemetry_anomaly)) / total * 100
    return round(score, 1)


def map_risk_level(score: float, low: float = THRESHOLD_LOW, high: float = THRESHOLD_HIGH) -> str:
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
    low: float = THRESHOLD_LOW,
    gap: float = EVIDENCE_GAP,
) -> str:
    """Ordered 5-type decision tree."""
    if system_health != "FULL":
        return "Partial evidence"
    if risk_score < low:
        return "Low observed risk"
    if abs(p_distraction - p_telemetry_anomaly) < gap:
        return "Combined evidence"
    return "Vision-dominant" if p_distraction > p_telemetry_anomaly else "Telemetry-dominant"


def ema(current: float, previous: float | None, alpha: float = EMA_ALPHA) -> float:
    """Exponential moving average anti-jitter smoothing."""
    if previous is None:
        return round(current, 3)
    return round(alpha * current + (1 - alpha) * previous, 3)


@dataclass
class RiskUpdate:
    P_distraction: float
    P_telemetry_anomaly: float
    RiskScore: float
    RiskLevel: str
    DominantEvidence: str
    SystemHealth: str


def build_risk_update(pD, pT, w_v=0.5, w_t=0.5, v="fresh", t="fresh") -> RiskUpdate:
    score = compute_risk_score(pD, pT, w_v, w_t, v, t)
    health = map_system_health(v, t)
    return RiskUpdate(
        P_distraction=round(pD, 3),
        P_telemetry_anomaly=round(pT, 3),
        RiskScore=score,
        RiskLevel=map_risk_level(score),
        DominantEvidence=determine_dominant_evidence(pD, pT, score, health),
        SystemHealth=health,
    )


if __name__ == "__main__":
    # ---- Worked example reproducing the dashboard screenshot ----
    # weights moved to 0.4 / 0.6; both modalities fresh
    pD, pT = 0.175, 0.28
    print("Worked example (w_v=0.4, w_t=0.6, both fresh):")
    print("  P_distraction      =", pD)
    print("  P_telemetry_anomaly=", pT)
    ru = build_risk_update(pD, pT, w_v=0.4, w_t=0.6)
    print("  -> RiskScore       =", ru.RiskScore, "/ 100")
    print("  -> RiskLevel       =", ru.RiskLevel)
    print("  -> DominantEvidence=", ru.DominantEvidence)
    print("  -> SystemHealth    =", ru.SystemHealth)

    # ---- Degraded example: telemetry missing ----
    print("\nDegraded example (telemetry missing, w 0.5/0.5):")
    ru2 = build_risk_update(0.62, 0.0, w_v=0.5, w_t=0.5, v="fresh", t="missing")
    print("  -> RiskScore       =", ru2.RiskScore, "/ 100  (vision-only re-normalised)")
    print("  -> SystemHealth    =", ru2.SystemHealth)
    print("  -> DominantEvidence=", ru2.DominantEvidence)
