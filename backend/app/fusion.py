"""Decision-level late fusion and risk interpretation.

Python port of the framework-agnostic risk-logic layer (ai/src/riskLogic.ts +
ai/src/availability.ts + ai/src/evidence.ts). The formulas, thresholds and the
availability contract are identical so the backend produces the same
risk_update as the TypeScript implementation. ``ai/fixtures/fusion_vectors.json``
is the cross-language oracle both ports are tested against.

Availability contract: a window is *available* exactly when the effective
fusion denominator ``w_v * fw(vision) + w_t * fw(telemetry)`` is strictly
greater than ``FUSION_EPSILON``. Otherwise there is no evidence to fuse and the
score, level and dominant evidence are ``None`` and the health is
``UNAVAILABLE`` - the pipeline never invents a "safe" reading (0 / Low).
"""
import math
from decimal import ROUND_HALF_UP, Decimal

from .config import settings

EVIDENCE_GAP = 0.15

# Tolerance for "the effective denominator is zero". RuntimeConfig accepts
# weights whose sum is off by up to 1e-6, so a literal `== 0` test would let a
# near-zero denominator through and divide by it. Always compare `<=`.
FUSION_EPSILON = 1e-9


def freshness_weight(status: str) -> float:
    """fresh 1.0, missing 0.0 - and stale 0.45, which is HISTORICAL ONLY.

    Ruling A (D13): the runtime no longer produces ``stale``. ``inference.freshness()``
    returns only "fresh" or "missing"; evidence older than ``freshness_tolerance_s`` is
    EXPIRED and arrives here as "missing" (weight 0), with the reason kept in the provenance
    (``{modality}_expired`` / ``{modality}_age_s``). The 0.45 tier is retained, unchanged,
    for one purpose: records written before the ruling carry ``stale`` and must keep
    reading and rendering. It is a legacy compatibility weight, not a model input the
    pipeline can reach - and not a validated number."""
    if status == "missing":
        return 0.0
    if status == "stale":
        return 0.45
    return 1.0  # fresh


def _clamp(v: float) -> float:
    return max(0.0, min(1.0, v))


def round_half_up(value: float, places: int) -> float:
    """Round half UP on the shortest decimal representation of ``value``.

    Python's built-in ``round`` is banker's rounding (84.25 -> 84.2) while the
    TypeScript port used ``toFixed`` (84.25 -> 84.3), so the two disagreed on about
    4% of inputs and, because ``RuntimeConfig`` allows float thresholds, could even
    disagree on the RiskLevel (a 30.25 score against a 30.3 threshold). Both ports
    now round the ``repr`` of the double with ROUND_HALF_UP, so what is printed is
    what is rounded (29.95, whose binary value sits just below the tie, is 30.0);
    ``roundHalfUp`` in ``ai/src/riskLogic.ts`` is the identical algorithm. Inputs
    here are never negative; for a negative value this rounds half away from
    zero."""
    if not math.isfinite(value):
        return value
    quantum = Decimal(f"1e-{places}")
    return float(Decimal(str(value)).quantize(quantum, rounding=ROUND_HALF_UP))


def effective_weights(
    w_v: float,
    w_t: float,
    vision_status: str,
    telemetry_status: str,
) -> tuple[float, float, float]:
    """The one place the fusion denominator is computed: ``(eff_v, eff_t, total)``.

    Score, health, dominant evidence and the explanation all read this, so they
    cannot disagree about whether a window is assessable."""
    eff_v = w_v * freshness_weight(vision_status)
    eff_t = w_t * freshness_weight(telemetry_status)
    return eff_v, eff_t, eff_v + eff_t


def compute_risk_score(
    p_distraction: float,
    p_telemetry_anomaly: float,
    weight_vision: float,
    weight_telemetry: float,
    vision_status: str = "fresh",
    telemetry_status: str = "fresh",
) -> float | None:
    """Eq. 2 (freshness-aware). Reduces to the baseline weighted sum when both
    modalities are fresh and weights sum to 1. Returns a 0-100 score rounded half
    up to 1 decimal place (``round_half_up``), or ``None`` - never 0 - when the
    effective denominator is <= FUSION_EPSILON (nothing to fuse; 0 would read as
    "safe")."""
    eff_v, eff_t, total = effective_weights(
        weight_vision, weight_telemetry, vision_status, telemetry_status
    )
    if total <= FUSION_EPSILON:
        return None
    score = (eff_v * _clamp(p_distraction) + eff_t * _clamp(p_telemetry_anomaly)) / total
    return round_half_up(score * 100, 1)


def map_risk_level(score: float | None, low: float | None = None, high: float | None = None) -> str | None:
    """Maps a (rounded) score to a level. The None check comes FIRST: Python
    raises TypeError on ``None < 30`` (the opposite failure mode to JavaScript,
    where it is silently ``true``), and an unavailable window has no level."""
    if score is None:
        return None
    low = settings.threshold_low if low is None else low
    high = settings.threshold_high if high is None else high
    if score < low:
        return "Low"
    if score < high:
        return "Medium"
    return "High"


def map_system_health(
    vision_status: str,
    telemetry_status: str,
    weight_vision: float = 0.5,
    weight_telemetry: float = 0.5,
) -> str:
    """Health is derived from the effective fusion denominator, not from
    counting ``missing`` flags:

        denominator <= FUSION_EPSILON          -> UNAVAILABLE
        else any branch not "fresh"            -> DEGRADED
        else                                   -> FULL

    The FULL / DEGRADED boundary looks only at freshness, never at the weights."""
    _, _, total = effective_weights(weight_vision, weight_telemetry, vision_status, telemetry_status)
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
    low: float | None = None,
    gap: float = EVIDENCE_GAP,
) -> str | None:
    """Ordered decision tree. Availability is checked FIRST: without it the
    `system_health != "FULL"` branch below would shield the score comparison
    and silently label a no-evidence window "Partial evidence". Call with
    keyword arguments for ``low`` / ``gap`` so a positional slip cannot
    misalign them."""
    if risk_score is None or system_health == "UNAVAILABLE":
        return None
    low = settings.threshold_low if low is None else low
    if system_health != "FULL":
        return "Partial evidence"
    if risk_score < low:
        return "Low observed risk"
    if abs(p_distraction - p_telemetry_anomaly) < gap:
        return "Combined evidence"
    return "Vision-dominant" if p_distraction > p_telemetry_anomaly else "Telemetry-dominant"


def map_alert_severity(level: str | None) -> str | None:
    """NOT CALLED ANYWHERE - DO NOT WIRE THIS UP. The AlertSeverity FSM (2 s
    High sustain, 10 s Low recovery, unavailable suspension) lives in
    ``inference.py``. This direct mapping turns High into HIGH_ALERT with no
    sustain, so calling it from the pipeline would silently delete the 2 s
    gate. Kept (this phase removes no functionality) with a None guard so an
    unavailable window yields None instead of a KeyError."""
    if level is None:
        return None
    return {"Low": "NORMAL", "Medium": "CAUTION", "High": "HIGH_ALERT"}[level]


def describe_unavailable_cause(
    vision_status: str | None = None,
    telemetry_status: str | None = None,
    weight_vision: float | None = None,
    weight_telemetry: float | None = None,
) -> str:
    """Names which side(s) left the effective fusion denominator at zero. Only
    meaningful for unavailable windows, where every branch is either missing or
    carries zero fusion weight. When the statuses are not supplied (legacy
    two-argument callers) a generic cause is returned."""
    generic = "no input branch carries usable evidence (each is missing or has zero fusion weight)"
    if vision_status is None or telemetry_status is None:
        return generic
    if vision_status == "missing" and telemetry_status == "missing":
        return "both the vision and telemetry inputs are missing"
    wv = 0.5 if weight_vision is None else weight_vision
    wt = 0.5 if weight_telemetry is None else weight_telemetry

    def branch_reason(name: str, status: str, weight: float) -> str | None:
        if status == "missing":
            return f"the {name} input is missing"
        if weight * freshness_weight(status) <= FUSION_EPSILON:
            return f"the {name} branch has zero fusion weight"
        return None

    reasons = [
        r
        for r in (
            branch_reason("vision", vision_status, wv),
            branch_reason("telemetry", telemetry_status, wt),
        )
        if r is not None
    ]
    return " and ".join(reasons) if reasons else generic


def build_explanation(
    dominant: str | None,
    level: str | None,
    vision_status: str | None = None,
    telemetry_status: str | None = None,
    weight_vision: float | None = None,
    weight_telemetry: float | None = None,
) -> str:
    # Availability first. The unavailable text deliberately names no level and
    # never falls through to the "below the low-risk threshold" claim, which
    # would otherwise be rendered (and exported) for a window with no evidence.
    if dominant is None or level is None:
        cause = describe_unavailable_cause(vision_status, telemetry_status, weight_vision, weight_telemetry)
        return (
            f"No risk assessment is available because {cause}, "
            "so the effective fusion denominator is zero and there is no evidence to fuse."
        )
    lvl = level.lower()
    if dominant == "Vision-dominant":
        return f"Vision evidence is driving the {lvl} risk output."
    if dominant == "Telemetry-dominant":
        return f"Telemetry non-safe behaviour is driving the {lvl} risk output."
    if dominant == "Combined evidence":
        return f"Vision and telemetry evidence both contribute to the {lvl} risk output."
    if dominant == "Partial evidence":
        return "Output is based on partial evidence; one modality is stale or missing."
    if dominant == "Low observed risk":
        return "The current window is below the low-risk threshold."
    # An unrecognised dominant value must not be reported as low risk.
    return "The dominant evidence type is not recognised, so no explanation is available."
