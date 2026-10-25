"""One authoritative temporal fusion path for replay and trained evidence."""
from datetime import datetime, timedelta, timezone
from typing import NamedTuple, Optional, Union

from . import fusion
from .config import settings
from .schemas import ModalityFreshness, RiskUpdate, RuntimeConfig, WindowInput

# Alert FSM timing, wall clock. Named constants, but the tests deliberately
# hard-code 2000 / 10000 and never import these: a changed constant must not drag
# its own expectation along with it.
ALERT_SUSTAIN_MS = 2000   # High must persist this long before HIGH_ALERT
ALERT_RECOVER_MS = 10000  # Low must persist this long before a latched alert clears

# R10 (LIVE_MODEL_RUNTIME only): each of the High and the Low segment keeps four more values -
# ``srv`` the server time of the segment's first supported window, ``src`` / ``end`` the first
# and the newest ACQUISITION time of the NEW supporting observations, and ``contrib`` the
# modality that supplied ``end`` - in integer microseconds, so no comparison is ever made on a
# rounded or float-accumulated number.
SEGMENT_FIELDS = ("srv_us", "src_us", "end_us", "contrib")
SEGMENT_STATE_KEYS = tuple(f"{segment}_{field}" for segment in ("high", "low") for field in SEGMENT_FIELDS)

# The temporal-memory keys: the ones a gap longer than the freshness tolerance
# CLEARS. ``runtime_state`` is a persisted JSON column, so a temporal key that is
# missing from this tuple survives the gap AND a worker restart: the symptom is a
# session resuming hours later with a stale HIGH_ALERT latch and no failing test.
# Every new key that carries *temporal memory* (streaks, latches, the EMA chain, the R10
# segment anchors above) must be listed here.
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
) + SEGMENT_STATE_KEYS

# The out-of-order guard's watermarks, written into the same persisted
# ``runtime_state`` by ``routers/windows.py``. They are deliberately NOT in
# ``TEMPORAL_STATE_KEYS`` and must never be added to it: they have to survive a gap
# and a worker restart, or evidence older than the newest one already accepted
# would be taken again after any pause. ``test_out_of_order_guard_survives_a_gap``
# (captured_at) and ``..._survives_a_gap_for_telemetry`` pin this, one per key.
EVIDENCE_WATERMARK_KEYS = ("captured_at", "telemetry_timestamp")

# R10: the observation registry - what the session has already ACCEPTED, per modality. Like the
# watermarks above it is evidence bookkeeping, not temporal memory: it has to survive a gap and a
# worker restart, or an observation seen before a pause would be taken as new after it. It must
# never be added to ``TEMPORAL_STATE_KEYS``. Flat keys on purpose (``dict(state)`` is a shallow
# copy, so nothing nested may be edited in place); a list value is only ever replaced.
#   telemetry: seq = the highest EXPLICIT seq accepted (only moves forward; a seq-less fallback
#              sample never clears it), canonical acquisition time, sha256 of the feature values,
#              the raw model probability, the per-class probabilities, the per-feature
#              contributions (TreeSHAP local attribution on the Safe-class score, sign flipped so
#              that a positive value pushes toward unsafe; log-odds; not causal, not a
#              dataset-level feature importance), and the method / baseline that explain them
#              (``obs_t_contrib_meta``: None when the provider gave no contributions)
#   vision:    frame epoch / index = the highest EXPLICIT identity accepted (same rule), canonical
#              acquisition time, sha256 of the image bytes, the raw probability, the EMA-smoothed
#              probability the observation was FUSED with, the per-class probabilities
#   The content fields are shared by explicit and fallback observations: after a fallback sample,
#   resending the last explicit identity unchanged is refused (409), not taken as a REPEAT.
OBSERVATION_REGISTRY_KEYS = (
    "obs_t_seq", "obs_t_ts", "obs_t_hash", "obs_t_raw", "obs_t_classes", "obs_t_contribs",
    "obs_t_contrib_meta", "obs_v_epoch", "obs_v_index", "obs_v_ts", "obs_v_hash", "obs_v_raw", "obs_v_p", "obs_v_classes",
)

LIVE_MODE = "LIVE_MODEL_RUNTIME"
_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
_ONE_US = timedelta(microseconds=1)


class Observation(NamedTuple):
    """The verdict ``routers/windows.py`` reached on one modality of one live request.

    ``kind`` is ``"new"`` for an observation the session had not accepted before and
    ``"repeat"`` for one it had. ``acquired_at`` is the CANONICAL acquisition time: the one
    registered when the identity was first accepted. A repeat never refreshes it, whatever
    time the request that repeats it carries. ``identity`` says how the verdict was reached:
    ``"explicit"`` (a telemetry seq / a vision (epoch, index)) or ``"fallback"`` (timestamp +
    feature hash / image hash, a weaker guarantee). ``ref`` is the telemetry seq, or the
    ``"epoch:index"`` frame id, and None for a fallback. ``hash_repeat_audit`` is True when a NEW
    explicit vision frame has the same image bytes as the previous accepted frame: an audit flag
    only, it never changes the verdict."""

    kind: str
    acquired_at: str
    identity: str = "explicit"
    ref: Optional[Union[int, str]] = None
    hash_repeat_audit: bool = False


class Observations(NamedTuple):
    """Both branches of one live request; None = the request carried no such input."""

    vision: Optional[Observation] = None
    telemetry: Optional[Observation] = None


def default_config():
    return RuntimeConfig(**{name: getattr(settings, name) for name in RuntimeConfig.model_fields})


class Freshness(NamedTuple):
    """The verdict on one evidence branch.

    ``status`` is ``"fresh"`` or ``"missing"`` and nothing else: ruling A (D13) retired
    the runtime ``stale`` tier, so evidence that is too old is scored exactly like
    evidence that never arrived. What used to be the difference between the two now
    lives in ``expired`` and ``age_s``, which ``run_inference`` records in the
    provenance so that "unusable because it expired" and "no input was received" stay
    distinguishable.

    ``expired`` is True only when the branch DID carry evidence and that evidence was
    rejected for its age (or was declared ``stale`` by the sender); a branch that sent
    nothing is ``expired = False``. ``age_s`` is ``max(0, processing time - capture
    time)`` rounded half up to 3 dp, and None when the branch has no input or no
    capture time to measure."""

    status: str
    expired: bool
    age_s: float | None


def freshness(status, timestamp, now, tolerance) -> Freshness:
    """Judge one branch. ``status`` is what the sender declared (fresh / stale /
    missing); ``timestamp`` is the evidence's capture time, ``now`` the processing time
    and ``tolerance`` the session's ``freshness_tolerance_s`` - a design threshold, not
    a validated safety threshold.

    The comparison is strict: an age of exactly ``tolerance`` is still fresh. It is made
    on the exact age, not on the rounded ``age_s`` that is reported, so an age of 3.0004 s
    is expired yet reports ``age_s = 3.0`` (the difference is below a millisecond). A
    sender that declares ``stale`` is treated as expired whatever its timestamp says: the
    pipeline no longer has a stale tier to put it in."""
    if status == "missing":
        return Freshness("missing", False, None)
    age_s, too_old = None, False
    if timestamp:
        seconds = (now - datetime.fromisoformat(timestamp.replace("Z", "+00:00"))).total_seconds()
        age_s = fusion.round_half_up(max(0.0, seconds), 3)
        too_old = seconds > tolerance
    if status == "stale" or too_old:
        return Freshness("missing", True, age_s)
    return Freshness(status, False, age_s)


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


def _parse_utc(stamp: str) -> datetime:
    return datetime.fromisoformat(stamp.replace("Z", "+00:00"))


def _to_us(moment: datetime) -> int:
    """Integer microseconds since the epoch: exact, so a boundary such as 2000.000 ms is never
    decided by float rounding."""
    return (moment - _EPOCH) // _ONE_US


class _Signal(NamedTuple):
    """What one modality contributes to the LIVE alert FSM in one window.

    ``effective``: it was observed, is neither missing nor expired, and has fusion weight.
    ``kind`` / ``acquired_us``: its observation verdict and canonical acquisition time.
    ``score``: its single-branch score, ``round_half_up(100 * P, 1)`` of the probability that
    actually entered the fusion (the NEW-only EMA value for vision, the stored one for a repeat)."""

    effective: bool
    kind: Optional[str]
    acquired_us: Optional[int]
    score: Optional[float]


def _supports(signal: _Signal, level: str, config: RuntimeConfig) -> bool:
    """Is this modality's own score on the ``level`` side of the SESSION's thresholds?
    High: ``score >= threshold_high``. Low: ``score < threshold_low`` (the same cut-offs
    ``map_risk_level`` applies to the fused score). Never the defaults 30 / 60."""
    if not signal.effective or signal.score is None:
        return False
    if level == "High":
        return signal.score >= config.threshold_high
    return signal.score < config.threshold_low


def _clear_segments(state: dict, segments=("high", "low")) -> None:
    for segment in segments:
        for field in SEGMENT_FIELDS:
            state[f"{segment}_{field}"] = None


def _advance_segment(state: dict, segment: str, level: str, threshold_ms: int, now_us: int,
                     signals: dict, config: RuntimeConfig) -> bool:
    """Advance one High (or Low) segment by one window; True when it is DONE.

    Four values per segment (see ``SEGMENT_FIELDS``). In order:

    1. A NEW observation of an effective modality that supports ``level`` is a *supporter*.
    2. The first window with a supporter opens the segment: ``srv`` = server time now, and
       ``src`` = ``end`` = the NEWEST acquisition time among this window's supporters - the
       source span starts at 0, whatever older evidence rides along in the same request.
       ``contrib`` = the modality that supplied it.
    3. Later, a supporter whose acquisition time is later than ``end`` moves ``end`` (and
       ``contrib``) there. Only NEW observations ever do: a REPEAT is not a supporter.
    4. Done = the server clock has run ``threshold`` since ``srv`` AND the source span
       ``end - src`` has reached ``threshold`` AND the completion guard holds: ``contrib`` - the
       modality that last advanced ``end`` - is still effective in THIS window and its score
       (NEW or REPEAT) is still on the supporting side. This window may be a REPEAT; a repeat
       can finish the wall-clock condition, never create the source progress.
    """
    key = {field: f"{segment}_{field}" for field in SEGMENT_FIELDS}
    srv, src, end, contrib = (state.get(key[field]) for field in SEGMENT_FIELDS)
    if None in (srv, src, end):  # nothing open, or a half-written row: start from scratch
        srv = src = end = contrib = None
    supporters = [(name, signal.acquired_us) for name, signal in signals.items()
                  if signal.kind == "new" and _supports(signal, level, config)]
    if supporters:
        newest_name, newest = max(supporters, key=lambda item: item[1])
        if srv is None:
            srv, src, end, contrib = now_us, newest, newest, newest_name
        elif newest > end:
            end, contrib = newest, newest_name
    state.update({key["srv_us"]: srv, key["src_us"]: src, key["end_us"]: end, key["contrib"]: contrib})
    if srv is None:
        return False
    threshold_us = threshold_ms * 1000
    guard = contrib in signals and _supports(signals[contrib], level, config)
    return now_us - srv >= threshold_us and end - src >= threshold_us and guard


def _step_alert_fsm_live(state: dict, level: Optional[str], now_ms: float, now_us: int,
                         signals: dict, config: RuntimeConfig) -> Optional[str]:
    """The LIVE_MODEL_RUNTIME alert FSM (R10): what ``_step_alert_fsm`` does, except that a
    High (Low) segment ends in HIGH_ALERT (NORMAL) only when BOTH the server clock and the
    SOURCE time of new supporting evidence have covered the threshold - see ``_advance_segment``.
    The 2000 / 10000 ms thresholds are unchanged. Everything else is the Task 5 contract:

    * an unavailable window emits None, suspends both segments, marks ``unavailable_since`` and
      leaves the latched severity alone; the first available window afterwards re-anchors;
    * a Medium window is CAUTION at once and clears both segments;
    * a gap longer than the freshness tolerance cleared the segment keys before this ran.
    The pre-R10 ``high_since`` / ``low_since`` of a row persisted by an older worker are dropped."""
    state.pop("high_since", None)
    state.pop("low_since", None)
    if level is None:
        if state.get("unavailable_since") is None:
            state["unavailable_since"] = now_ms
        _clear_segments(state)
        return None

    severity = state.get("last_severity") or state.get("severity") or "NORMAL"
    if state.pop("unavailable_since", None) is not None:
        _clear_segments(state)  # resume: the dead interval earns no credit
    if level == "Medium":
        severity = "CAUTION"
        _clear_segments(state)
    elif level == "High":
        _clear_segments(state, ("low",))
        done = _advance_segment(state, "high", "High", ALERT_SUSTAIN_MS, now_us, signals, config)
        severity = "HIGH_ALERT" if done or severity == "HIGH_ALERT" else "CAUTION"
    else:
        _clear_segments(state, ("high",))
        if _advance_segment(state, "low", "Low", ALERT_RECOVER_MS, now_us, signals, config):
            severity = "NORMAL"
    state.update(last_severity=severity)
    state.pop("severity", None)
    return severity


def _stored_classes(state: dict, key: str) -> list:
    return list(state.get(key) or [])


def run_inference(session_id: str, window_id: int, w: WindowInput, *, state=None,
                  config=None, provenance=None, operation_mode="PREPARED_SESSION_RUNTIME", now=None,
                  observations: Optional[Observations] = None) -> RiskUpdate:
    """Fuse one window. ``operation_mode`` picks the alert FSM: ``LIVE_MODEL_RUNTIME`` runs the
    R10 one (observation identity, canonical acquisition time, NEW-only EMA, wall clock AND
    source span) and then REQUIRES ``observations``, the per-branch verdict that
    ``routers/windows.py`` reached under the write lock; any other mode keeps the wall-clock FSM
    unchanged, window for window, and ignores ``observations``."""
    state = state if state is not None else {}
    config = config or default_config()
    now = now or datetime.now(timezone.utc)
    now_ms = now.timestamp() * 1000
    provenance = dict(provenance or {"provider": "MockAIProvider", "vision_source": "prepared_replay", "telemetry_source": "prepared_replay"})
    live = operation_mode == LIVE_MODE
    if live and observations is None:
        raise ValueError("LIVE_MODEL_RUNTIME needs the observation verdicts of the request")
    v_obs = observations.vision if live else None
    t_obs = observations.telemetry if live else None
    # All temporal bookkeeping happens on a scratch copy and is committed only after
    # the record validated, so a producer bug that raises leaves the memory intact.
    scratch = dict(state)
    if live:
        # A REPEAT is the observation it repeats: the probabilities (and the per-class
        # breakdowns) stored when it was first accepted, not this request's re-inference.
        if v_obs is not None and v_obs.kind == "repeat":
            w = w.model_copy(update={"P_distraction": scratch.get("obs_v_raw", w.P_distraction),
                                     "visual_top_classes": _stored_classes(scratch, "obs_v_classes")})
            provenance["P_distraction_raw"] = w.P_distraction
        if t_obs is not None and t_obs.kind == "repeat":
            # The contributions too. A session registered before they existed has no entry (None, not
            # a list): the repeat then keeps the model's own, identical answer for the same bytes.
            stored = scratch.get("obs_t_contribs")
            w = w.model_copy(update={"P_telemetry_anomaly": scratch.get("obs_t_raw", w.P_telemetry_anomaly),
                                     "telemetry_behavior_classes": _stored_classes(scratch, "obs_t_classes"),
                                     "telemetry_feature_contributions":
                                         w.telemetry_feature_contributions if stored is None else list(stored)})
            provenance["P_telemetry_raw"] = w.P_telemetry_anomaly
            # The method and baseline that explain the registered contributions travel with them, so
            # contributions + baseline still sum to the registered margin. Absent (a session registered
            # before they were kept): the model's own answer for the same bytes stays, as above.
            if stored is not None and "obs_t_contrib_meta" in scratch:
                meta = scratch["obs_t_contrib_meta"]
                provenance.pop("telemetry_contribution_method", None)
                provenance.pop("telemetry_contribution_baseline", None)
                if meta is not None:
                    provenance.update(telemetry_contribution_method=meta["method"],
                                      telemetry_contribution_baseline=meta["baseline"])
        # Age is measured from the CANONICAL acquisition time. A branch the request did not
        # carry has no observation and is missing, whatever the provider declared.
        vision = freshness(w.vision_status if v_obs is not None else "missing",
                           v_obs.acquired_at if v_obs is not None else None, now, config.freshness_tolerance_s)
        telemetry = freshness(w.telemetry_status if t_obs is not None else "missing",
                              t_obs.acquired_at if t_obs is not None else None, now, config.freshness_tolerance_s)
    else:
        vision = freshness(w.vision_status, provenance.get("captured_at") or w.timestamp, now, config.freshness_tolerance_s)
        telemetry = freshness(w.telemetry_status, provenance.get("telemetry_timestamp") or w.timestamp, now, config.freshness_tolerance_s)
    # Only "fresh" and "missing" come out of here. An expired branch is a missing one as
    # far as the score, the health, the EMA chain and the FSM are concerned.
    vstatus, tstatus = vision.status, telemetry.status
    # A gap breaks a sustained streak and prevents EMA from carrying old evidence.
    if now_ms - scratch.get("last_processed_ms", now_ms) > config.freshness_tolerance_s * 1000:
        for key in TEMPORAL_STATE_KEYS:
            scratch.pop(key, None)
    # EMA: seed-on-first-sample. The seed (and any re-seeded sample) keeps full
    # provider precision; only a smoothed value is rounded, half up to 3 dp. Expired
    # vision is missing vision: it contributes 0.0 here and, below, leaves no
    # ``previous_vision`` behind, so the next fresh frame re-seeds the chain.
    pd = w.P_distraction if vstatus != "missing" else 0.0
    if live and v_obs is not None and v_obs.kind == "repeat" and vstatus == "fresh":
        # R10: only a NEW observation moves the chain. A repeat shows the smoothed value it was
        # first fused with and neither reads nor extends the chain.
        stored = scratch.get("obs_v_p")
        pd = stored if stored is not None else pd
    elif vstatus == "fresh" and scratch.get("previous_vision") is not None:
        pd = fusion.round_half_up(config.ema_alpha * pd + (1 - config.ema_alpha) * scratch["previous_vision"], 3)
    pt = w.P_telemetry_anomaly if tstatus != "missing" else 0.0
    # One denominator, derived from the CONFIGURED weights, decides availability.
    # Score, level, health and dominant evidence all follow from it; passing the
    # weights to map_system_health matters: with defaults it called a zero-weight
    # window DEGRADED while the score was already None, and that contradiction let
    # the FSM treat "no assessment" as a Low window.
    weight_v, weight_t = config.weight_vision, config.weight_telemetry
    effective_v, effective_t, denominator = fusion.effective_weights(weight_v, weight_t, vstatus, tstatus)
    available = denominator > fusion.FUSION_EPSILON
    score = fusion.compute_risk_score(pd, pt, weight_v, weight_t, vstatus, tstatus)
    level = fusion.map_risk_level(score, config.threshold_low, config.threshold_high)
    health = fusion.map_system_health(vstatus, tstatus, weight_v, weight_t)
    dominant = fusion.determine_dominant_evidence(pd, pt, score, health, low=config.threshold_low)
    # The FSM is keyed on "is there a level", never on the health string.
    if live:
        def signal(obs, status, probability, effective_weight):
            if obs is None:
                return _Signal(False, None, None, None)
            return _Signal(status == "fresh" and effective_weight > fusion.FUSION_EPSILON, obs.kind,
                           _to_us(_parse_utc(obs.acquired_at)),
                           fusion.round_half_up(100 * max(0.0, min(1.0, probability)), 1))
        signals = {"vision": signal(v_obs, vstatus, pd, effective_v),
                   "telemetry": signal(t_obs, tstatus, pt, effective_t)}
        severity = _step_alert_fsm_live(scratch, level, now_ms, _to_us(now), signals, config)
    else:
        severity = _step_alert_fsm(scratch, level, now_ms)
    # The EMA chain survives only across consecutive AVAILABLE windows with fresh
    # vision: a fresh-vision window that carried no assessment (w_v=0, w_t=1 and
    # telemetry missing) must not seed the next one.
    if not live:
        chain = pd if vstatus == "fresh" and level is not None else None
    elif vstatus != "fresh" or level is None:
        chain = None  # missing, expired or unavailable: the chain is broken
    elif v_obs.kind == "new":
        chain = pd
    else:
        chain = scratch.get("previous_vision")  # a repeat leaves the chain as it is - never re-links a broken one
    scratch.update(previous_vision=chain, last_processed_ms=now_ms)
    if live:
        # Register what this window ACCEPTED, so a later repeat can reproduce it.
        if v_obs is not None and v_obs.kind == "new":
            scratch.update(obs_v_raw=w.P_distraction, obs_v_p=pd if vstatus == "fresh" else None,
                           obs_v_classes=[c.model_dump() for c in w.visual_top_classes])
        if t_obs is not None and t_obs.kind == "new":
            scratch.update(obs_t_raw=w.P_telemetry_anomaly,
                           obs_t_classes=[c.model_dump() for c in w.telemetry_behavior_classes],
                           obs_t_contribs=[c.model_dump() for c in w.telemetry_feature_contributions],
                           obs_t_contrib_meta=None if "telemetry_contribution_method" not in provenance else {
                               "method": provenance["telemetry_contribution_method"],
                               "baseline": provenance.get("telemetry_contribution_baseline")})
        explicit = [o.identity == "explicit" for o in (v_obs, t_obs) if o is not None]
        provenance.update(
            vision_obs=v_obs.kind if v_obs is not None else None,
            telemetry_obs=t_obs.kind if t_obs is not None else None,
            vision_frame_id=v_obs.ref if v_obs is not None and v_obs.identity == "explicit" else None,
            telemetry_seq=t_obs.ref if t_obs is not None and t_obs.identity == "explicit" else None,
            vision_identity_source=v_obs.identity if v_obs is not None else None,
            telemetry_identity_source=t_obs.identity if t_obs is not None else None,
            # One word for the whole request: "explicit" only when EVERY observed branch was
            # identified explicitly; a single fallback makes the request "fallback".
            identity_source=None if not explicit else ("explicit" if all(explicit) else "fallback"),
            vision_hash_repeat_audit=bool(v_obs is not None and v_obs.hash_repeat_audit))
        # The age above was measured from these, so they are what the record must show.
        if v_obs is not None:
            provenance["captured_at"] = v_obs.acquired_at
        if t_obs is not None:
            provenance["telemetry_timestamp"] = t_obs.acquired_at
    provenance["fusion_config"] = config.model_dump()
    # Always written, for both branches, so a record can say WHY a branch carried no
    # weight: ``expired`` with an age, or simply never received (``expired`` false).
    # Assigned, not ``setdefault``: these four are this function's verdict, never the
    # provider's.
    provenance.update(vision_expired=vision.expired, vision_age_s=vision.age_s,
                      telemetry_expired=telemetry.expired, telemetry_age_s=telemetry.age_s)
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
