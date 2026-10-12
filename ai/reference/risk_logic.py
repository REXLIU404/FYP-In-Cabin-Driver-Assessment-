"""
Decision-level late-fusion risk logic — Python reference implementation.

This module is the canonical, language-agnostic specification of the fusion and
risk-scoring engine. The FYP1 dashboard runs the identical algorithm client-side
in TypeScript (ai/src/riskLogic.ts) to render the live demo; this Python module is
the same maths in the AI-inference-layer language, and is fully runnable/testable.

Availability contract (mirrors ai/src/availability.ts): a window is *available*
exactly when the effective fusion denominator
    w_vision * fw(vision_status) + w_telemetry * fw(telemetry_status)
is strictly greater than FUSION_EPSILON. Otherwise there is no evidence to fuse:
RiskScore / RiskLevel / DominantEvidence are None, SystemHealth is "UNAVAILABLE"
and assessment_available is False. The engine never invents a "safe" reading
(0 / Low) for a window it could not assess.

Only the branch probability INPUTS (P_distraction, P_telemetry_anomaly) are mocked
in FYP1 (prepared values standing in for the untrained MobileNetV3 / XGBoost).
The fusion engine below is REAL working code, not a mock.

Cross-language oracle: ai/fixtures/fusion_vectors.json. backend/tests/
test_fusion_vectors.py checks this module AND backend/app/fusion.py against it, so
this specification cannot drift silently from the TypeScript implementation.
"""
from __future__ import annotations
import math
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

# ---- thresholds & weights (transparent prototype parameters) ----
THRESHOLD_LOW = 30.0      # RiskScore < 30  -> Low
THRESHOLD_HIGH = 60.0     # RiskScore >= 60 -> High
EVIDENCE_GAP = 0.15       # |pD - pT| below this -> Combined evidence
EMA_ALPHA = 0.35          # temporal smoothing coefficient

# Tolerance for "the effective denominator is zero". Runtime configs accept
# weights whose sum is off by up to 1e-6, so a literal `== 0` test would let a
# near-zero denominator through and divide by it. Always compare `<=`.
FUSION_EPSILON = 1e-9


def clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def round_half_up(value: float, places: int) -> float:
    """Round half UP on the shortest decimal representation of ``value``.

    Every implementation of this specification (backend/app/fusion.py and
    ai/src/riskLogic.ts) rounds the same way, so a score such as 84.25 is 84.3
    everywhere. The built-in ``round`` is banker's rounding (84.25 -> 84.2) and
    JavaScript's ``toFixed`` rounds the exact binary value, so neither is used."""
    if not math.isfinite(value):
        return value
    return float(Decimal(str(value)).quantize(Decimal(f"1e-{places}"), rounding=ROUND_HALF_UP))


def freshness_weight(status: str) -> float:
    """fresh -> full trust, stale -> down-weighted, missing -> dropped."""
    return {"fresh": 1.0, "stale": 0.45, "missing": 0.0}.get(status, 1.0)


def effective_weights(
    w_vision: float,
    w_telemetry: float,
    vision_status: str,
    telemetry_status: str,
) -> tuple[float, float, float]:
    """The one place the fusion denominator is computed: (eff_v, eff_t, total).
    Score, health and dominant evidence all read this, so they cannot disagree."""
    eff_v = w_vision * freshness_weight(vision_status)
    eff_t = w_telemetry * freshness_weight(telemetry_status)
    return eff_v, eff_t, eff_v + eff_t


def compute_risk_score(
    p_distraction: float,
    p_telemetry_anomaly: float,
    w_vision: float = 0.5,
    w_telemetry: float = 0.5,
    vision_status: str = "fresh",
    telemetry_status: str = "fresh",
) -> float | None:
    """
    Freshness-weighted decision-level late fusion, returned on a 0..100 scale
    rounded half up to 1 decimal place.

        eff_v = w_vision    * fw(vision_status)
        eff_t = w_telemetry * fw(telemetry_status)
        RiskScore = (eff_v * pD + eff_t * pT) / (eff_v + eff_t) * 100

    Returns None - never 0 - when eff_v + eff_t <= FUSION_EPSILON (both branches
    missing, or every branch that has evidence carries zero weight).
    """
    eff_v, eff_t, total = effective_weights(w_vision, w_telemetry, vision_status, telemetry_status)
    if total <= FUSION_EPSILON:
        return None
    score = (eff_v * clamp01(p_distraction) + eff_t * clamp01(p_telemetry_anomaly)) / total * 100
    return round_half_up(score, 1)


def map_risk_level(
    score: float | None, low: float = THRESHOLD_LOW, high: float = THRESHOLD_HIGH
) -> str | None:
    # None check FIRST: Python raises TypeError on `None < 30` (JavaScript silently
    # yields true). An unavailable window has no level.
    if score is None:
        return None
    if score < low:
        return "Low"
    if score < high:
        return "Medium"
    return "High"


def map_system_health(
    vision_status: str,
    telemetry_status: str,
    w_vision: float = 0.5,
    w_telemetry: float = 0.5,
) -> str:
    """denominator <= FUSION_EPSILON -> UNAVAILABLE; else any branch not fresh ->
    DEGRADED; else FULL. FULL/DEGRADED looks only at freshness, never at weights."""
    _, _, total = effective_weights(w_vision, w_telemetry, vision_status, telemetry_status)
    if total <= FUSION_EPSILON:
        return "UNAVAILABLE"
    if vision_status != "fresh" or telemetry_status != "fresh":
        return "DEGRADED"
    return "FULL"


def determine_dominant_evidence(
    p_distraction: float,
    p_telemetry_anomaly: float,
    risk_score: float | None,
    system_health: str,
    low: float = THRESHOLD_LOW,
    gap: float = EVIDENCE_GAP,
) -> str | None:
    """Ordered decision tree. Availability is checked FIRST (None => no evidence)."""
    if risk_score is None or system_health == "UNAVAILABLE":
        return None
    if system_health != "FULL":
        return "Partial evidence"
    if risk_score < low:
        return "Low observed risk"
    if abs(p_distraction - p_telemetry_anomaly) < gap:
        return "Combined evidence"
    return "Vision-dominant" if p_distraction > p_telemetry_anomaly else "Telemetry-dominant"


def ema(current: float, previous: float | None, alpha: float = EMA_ALPHA) -> float:
    """Exponential moving average anti-jitter smoothing of P_distraction.

    Seed convention (seed-on-first-sample): when ``previous`` is None the sample
    is its own previous value, so it is emitted as-is at full provider precision -
    it is NOT rounded and NOT pulled towards 0. (0.2 -> 1.0 therefore smooths to
    0.48; seeding at 0 would give 0.3955.) Only a smoothed value is rounded, half
    up to 3 decimals.

    Re-initialisation convention: the chain is only valid across CONSECUTIVE
    windows whose vision evidence was fresh. A caller must pass ``previous=None``
    - re-seeding, no smoothing - for the first fresh window after any window whose
    vision was stale or missing, after any window with no assessment (the
    effective denominator was zero), and after a gap longer than the freshness
    tolerance. backend/app/inference.py does all of this; ai/src/riskLogic.ts does
    the first two (it has no wall clock, so no gap rule). This function is
    stateless and relies on the caller for it."""
    if previous is None:
        return current
    return round_half_up(alpha * current + (1 - alpha) * previous, 3)


@dataclass
class RiskUpdate:
    P_distraction: float
    P_telemetry_anomaly: float
    assessment_available: bool
    RiskScore: float | None
    RiskLevel: str | None
    DominantEvidence: str | None
    SystemHealth: str


def build_risk_update(pD, pT, w_v=0.5, w_t=0.5, v="fresh", t="fresh") -> RiskUpdate:
    score = compute_risk_score(pD, pT, w_v, w_t, v, t)
    health = map_system_health(v, t, w_vision=w_v, w_telemetry=w_t)
    return RiskUpdate(
        P_distraction=round_half_up(pD, 3),
        P_telemetry_anomaly=round_half_up(pT, 3),
        assessment_available=score is not None,
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

    # ---- Unavailable example: both branches missing -> nothing to fuse ----
    print("\nUnavailable example (vision AND telemetry missing, w 0.5/0.5):")
    ru3 = build_risk_update(0.0, 0.0, w_v=0.5, w_t=0.5, v="missing", t="missing")
    print("  -> assessment_available =", ru3.assessment_available)
    print("  -> RiskScore       =", ru3.RiskScore, "(None, never 0)")
    print("  -> RiskLevel       =", ru3.RiskLevel)
    print("  -> DominantEvidence=", ru3.DominantEvidence)
    print("  -> SystemHealth    =", ru3.SystemHealth)
