"""One authoritative temporal fusion path for replay and trained evidence."""
from datetime import datetime, timezone

from . import fusion
from .config import settings
from .schemas import ModalityFreshness, RiskUpdate, RuntimeConfig, WindowInput

# Alert FSM timing, wall clock. Named constants, but the tests deliberately
# hard-code 2000 / 10000 and never import these: a changed constant must not drag
# its own expectation along with it.
ALERT_SUSTAIN_MS = 2000   # High must persist this long before HIGH_ALERT
ALERT_RECOVER_MS = 10000  # Low must persist this long before a latched alert clears

# The temporal-memory keys: the ones a gap longer than the freshness tolerance
# CLEARS. ``runtime_state`` is a persisted JSON column, so a temporal key that is
# missing from this tuple survives the gap AND a worker restart: the symptom is a
# session resuming hours later with a stale HIGH_ALERT latch and no failing test.
# Every new key that carries *temporal memory* (streaks, latches, the EMA chain)
# must be listed here.
# ``severity`` is the pre-Task-5 name of ``last_severity``; it is only still listed
# (and read as a fallback) so rows persisted by an older worker are wiped too.
TEMPORAL_STATE_KEYS = (
    "previous_vision",
    "severity",
    "last_severity",
    "high_since",
    "low_since",
    "unavailable_since",
    "last_processed_ms",
)

# The out-of-order guard's watermarks, written into the same persisted
# ``runtime_state`` by ``routers/windows.py``. They are deliberately NOT in
# ``TEMPORAL_STATE_KEYS`` and must never be added to it: they have to survive a gap
# and a worker restart. A gap that wiped them would let evidence older than the
# newest one already accepted be taken again after any pause - the guard would
# silently stop guarding. ``test_out_of_order_guard_survives_a_gap`` (captured_at) and
# ``test_out_of_order_guard_survives_a_gap_for_telemetry`` pin this, one per key.
EVIDENCE_WATERMARK_KEYS = ("captured_at", "telemetry_timestamp")


def default_config():
    return RuntimeConfig(**{name: getattr(settings, name) for name in RuntimeConfig.model_fields})


def freshness(status, timestamp, now, tolerance):
    if status == "missing":
        return status
    if timestamp and (now - datetime.fromisoformat(timestamp.replace("Z", "+00:00"))).total_seconds() > tolerance:
        return "stale"
    return status


def _step_alert_fsm(state: dict, level: str | None, now_ms: float) -> str | None:
    """Advance the wall-clock AlertSeverity FSM by one window; returns the severity
    to EMIT, which is ``None`` exactly when the window carries no assessment.

    Two things are kept strictly apart:

    * the emitted value (``None`` for an unavailable window) lives only on the
      returned record;
    * the FSM's memory is ``state["last_severity"]``, which is NEVER ``None``. If an
      emitted ``None`` were written back, the next window would read it, lose the
      ``== "HIGH_ALERT"`` latch, and a single evidence interruption would silently
      downgrade an active alert with no error anywhere.

    An unavailable window SUSPENDS the timers rather than freezing them: the High
    and Low streaks are dropped and ``unavailable_since`` marks the interruption.
    The first available window afterwards re-anchors both timers to itself, so the
    dead interval is credited neither towards the 2 s sustain nor the 10 s
    recovery. The held severity itself is kept. The existing gap rule cannot do
    this job: ``last_processed_ms`` advances on every window, unavailable ones
    included, so a minute of no-evidence windows looks "continuously processed"."""
    if level is None:
        if state.get("unavailable_since") is None:
            state["unavailable_since"] = now_ms
        state["high_since"] = state["low_since"] = None
        return None

    severity = state.get("last_severity") or state.get("severity") or "NORMAL"
    high_since, low_since = state.get("high_since"), state.get("low_since")
    if state.pop("unavailable_since", None) is not None:
        high_since = low_since = None  # resume: the dead interval earns no credit
    if level == "High":
        high_since = now_ms if high_since is None else high_since
        sustained = now_ms - high_since >= ALERT_SUSTAIN_MS
        severity = "HIGH_ALERT" if sustained or severity == "HIGH_ALERT" else "CAUTION"
        low_since = None
    elif level == "Medium":
        severity, high_since, low_since = "CAUTION", None, None
    else:
        low_since = now_ms if low_since is None else low_since
        if now_ms - low_since >= ALERT_RECOVER_MS:
            severity = "NORMAL"
        high_since = None
    state.update(last_severity=severity, high_since=high_since, low_since=low_since)
    state.pop("severity", None)
    return severity


def run_inference(session_id: str, window_id: int, w: WindowInput, *, state=None,
                  config=None, provenance=None, operation_mode="PREPARED_SESSION_RUNTIME", now=None) -> RiskUpdate:
    state = state if state is not None else {}
    config = config or default_config()
    now = now or datetime.now(timezone.utc)
    now_ms = now.timestamp() * 1000
    provenance = dict(provenance or {"provider": "MockAIProvider", "vision_source": "prepared_replay", "telemetry_source": "prepared_replay"})
    vstatus = freshness(w.vision_status, provenance.get("captured_at") or w.timestamp, now, config.freshness_tolerance_s)
    tstatus = freshness(w.telemetry_status, provenance.get("telemetry_timestamp") or w.timestamp, now, config.freshness_tolerance_s)
    # All temporal bookkeeping happens on a scratch copy and is committed only after
    # the record validated, so a producer bug that raises leaves the memory intact.
    scratch = dict(state)
    # A gap breaks a sustained streak and prevents EMA from carrying old evidence.
    if now_ms - scratch.get("last_processed_ms", now_ms) > config.freshness_tolerance_s * 1000:
        for key in TEMPORAL_STATE_KEYS:
            scratch.pop(key, None)
    # EMA: seed-on-first-sample. The seed (and any stale / re-seeded sample) keeps
    # full provider precision; only a smoothed value is rounded, half up to 3 dp.
    pd = w.P_distraction if vstatus != "missing" else 0.0
    if vstatus == "fresh" and scratch.get("previous_vision") is not None:
        pd = fusion.round_half_up(config.ema_alpha * pd + (1 - config.ema_alpha) * scratch["previous_vision"], 3)
    pt = w.P_telemetry_anomaly if tstatus != "missing" else 0.0
    # One denominator, derived from the CONFIGURED weights, decides availability.
    # Score, level, health and dominant evidence all follow from it; passing the
    # weights to map_system_health matters: with defaults it called a zero-weight
    # window DEGRADED while the score was already None, and that contradiction let
    # the FSM treat "no assessment" as a Low window.
    weight_v, weight_t = config.weight_vision, config.weight_telemetry
    _, _, denominator = fusion.effective_weights(weight_v, weight_t, vstatus, tstatus)
    available = denominator > fusion.FUSION_EPSILON
    score = fusion.compute_risk_score(pd, pt, weight_v, weight_t, vstatus, tstatus)
    level = fusion.map_risk_level(score, config.threshold_low, config.threshold_high)
    health = fusion.map_system_health(vstatus, tstatus, weight_v, weight_t)
    dominant = fusion.determine_dominant_evidence(pd, pt, score, health, low=config.threshold_low)
    # The FSM is keyed on "is there a level", never on the health string.
    severity = _step_alert_fsm(scratch, level, now_ms)
    # The EMA chain survives only across consecutive AVAILABLE windows with fresh
    # vision: a fresh-vision window that carried no assessment (w_v=0, w_t=1 and
    # telemetry missing) must not seed the next one.
    scratch.update(previous_vision=pd if vstatus == "fresh" and level is not None else None,
                   last_processed_ms=now_ms)
    provenance["fusion_config"] = config.model_dump()
    provenance.setdefault("P_distraction_raw", w.P_distraction)
    provenance.setdefault("P_telemetry_raw", w.P_telemetry_anomaly)
    record = RiskUpdate(
        session_id=session_id, window_id=window_id, timestamp=now.isoformat(),
        P_distraction=pd, P_telemetry_anomaly=pt,
        # Passed explicitly: if the schema had to derive it, its legacy-rewrite
        # validator would silently launder any producer bug into an "unavailable".
        assessment_available=available,
        RiskScore=score, RiskLevel=level, DominantEvidence=dominant, AlertSeverity=severity,
        SystemHealth=health, operation_mode=operation_mode,
        modality_freshness=ModalityFreshness(vision=vstatus, telemetry=tstatus),
        latency_ms=w.latency_ms, visual_top_classes=w.visual_top_classes,
        telemetry_behavior_classes=w.telemetry_behavior_classes,
        telemetry_feature_contributions=w.telemetry_feature_contributions,
        telemetry_features=w.telemetry_features,
        explanation=fusion.build_explanation(dominant, level, vstatus, tstatus, weight_v, weight_t),
        provenance=provenance,
    )
    state.clear()
    state.update(scratch)
    return record
