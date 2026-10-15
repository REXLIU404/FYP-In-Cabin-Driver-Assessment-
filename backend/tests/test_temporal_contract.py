"""Task 5 - the temporal layer: what the EMA and the Alert FSM do over time, and in
particular across a window that carries no assessment.

Everything here runs on an INJECTED clock (``now=``, or a patched
``inference.datetime`` for the HTTP tests); nothing sleeps. The 2000 ms sustain,
the 10000 ms recovery and the 3 s freshness tolerance are written as literals on
purpose - none of them is imported from the implementation, so a changed constant
cannot drag its own expectation along with it.

UT-TIME-01  FSM boundaries                       UT-TIME-04  unavailable is not credited
UT-TIME-02  freshness / gap / UTC offsets        UT-TIME-05  identical captured_at   (known limitation, R10)
UT-TIME-03  EMA seed convention                  UT-TIME-06  expired-only stream never alerts (ruling A)
UT-EMA-PARITY-01  Python half; the TypeScript half is ai/src/emaParity.test.ts
IT-LIVE-AGE  evidence age through POST /infer: the 3 s boundary, a 30-day-old frame, and an
             expired-only stream on the Live path (needs no model weights; the provider is stubbed)

Ruling A (D13): evidence older than ``freshness_tolerance_s`` is EXPIRED and scores as missing;
``{modality}_expired`` / ``{modality}_age_s`` in the provenance keep the reason. The runtime no
longer produces ``stale``. The tests of the evidence-age rule itself are in
``test_evidence_expiry.py``; this file keeps the temporal tests that the rule changed.
"""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from app import fusion, inference
from app.inference import freshness, run_inference
from app.schemas import RuntimeConfig, WindowInput

# Sibling test module: loads ai/reference/risk_logic.py once.
from test_fusion_vectors import reference

REPO_ROOT = Path(__file__).resolve().parents[2]
EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
T0 = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)  # in the past on any real clock

HIGH, MEDIUM, LOW = 1.0, 0.45, 0.0  # P_distraction == P_telemetry_anomaly -> score 100 / 45 / 0


def at(ms):
    return T0 + timedelta(milliseconds=ms)


def epoch_ms(ms):
    """Integer arithmetic on purpose: the expected state value, built independently."""
    return int((T0 - EPOCH).total_seconds()) * 1000 + ms


class Stream:
    """Feeds ``run_inference`` the way the router does: one persistent state dict."""

    def __init__(self, **config):
        self.state = {}
        self.config = RuntimeConfig(**{"ema_alpha": 1, **config})
        self.window_id = 0

    def tick(self, ms, p=LOW, *, vision="fresh", telemetry="fresh", pt=None, provenance=None):
        self.window_id += 1
        window = WindowInput(P_distraction=p, P_telemetry_anomaly=p if pt is None else pt,
                             vision_status=vision, telemetry_status=telemetry)
        return run_inference("s", self.window_id, window, state=self.state, config=self.config,
                             provenance=provenance, now=at(ms))

    def blackout(self, ms):
        """A window with no usable evidence at all."""
        return self.tick(ms, LOW, vision="missing", telemetry="missing")

    def severities(self, steps):
        return [self.tick(ms, p).AlertSeverity for ms, p in steps]


# --------------------------------------------------------------------- UT-TIME-01
def test_ut_time_01_high_sustain_boundaries():
    s = Stream()
    assert s.severities([(0, HIGH), (1900, HIGH), (2000, HIGH), (2100, HIGH)]) == [
        "CAUTION", "CAUTION", "HIGH_ALERT", "HIGH_ALERT"]


def test_ut_time_01_low_recovery_boundaries():
    s = Stream()
    s.severities([(0, HIGH), (1900, HIGH), (2000, HIGH), (2100, HIGH)])
    assert s.tick(2100, LOW).AlertSeverity == "HIGH_ALERT"  # the Low streak starts at 2100
    for ms in range(3100, 12000, 1000):  # keep the stream continuous: no gap above 3 s
        assert s.tick(ms, LOW).AlertSeverity == "HIGH_ALERT"
    assert s.tick(12000, LOW).AlertSeverity == "HIGH_ALERT"  # 9.9 s of Low
    assert s.tick(12100, LOW).AlertSeverity == "NORMAL"      # 10.0 s of Low


def test_ut_time_01_interrupted_high_streak_restarts():
    s = Stream()
    assert s.tick(0, HIGH).AlertSeverity == "CAUTION"
    assert s.tick(1000, MEDIUM).AlertSeverity == "CAUTION"
    assert s.state["high_since"] is None  # streak cleared
    assert s.tick(1500, HIGH).AlertSeverity == "CAUTION"
    assert s.tick(3400, HIGH).AlertSeverity == "CAUTION"      # 1.9 s since 1500
    assert s.tick(3500, HIGH).AlertSeverity == "HIGH_ALERT"   # 2.0 s since 1500


def test_ut_time_01_whole_millisecond_boundaries_are_exact():
    """The exact 1999 / 2000 ms edge holds wherever the stream starts."""
    for offset in range(0, 4000, 37):
        s = Stream()
        base = 123_456 + offset
        s.tick(base, HIGH)
        assert s.tick(base + 1999, HIGH).AlertSeverity == "CAUTION"
        assert s.tick(base + 2000, HIGH).AlertSeverity == "HIGH_ALERT"


# --------------------------------------------------------------------- UT-TIME-02
@pytest.mark.parametrize("age_ms,expected,expired", [
    (2999, "fresh", False), (3000, "fresh", False), (3001, "missing", True)])
def test_ut_time_02_freshness_boundary(age_ms, expected, expired):
    """Ruling A: past the tolerance a branch is MISSING (and expired), never stale."""
    stamp = (at(0) - timedelta(milliseconds=age_ms)).isoformat()
    verdict = freshness("fresh", stamp, at(0), 3)
    assert (verdict.status, verdict.expired) == (expected, expired)


def test_ut_time_02_freshness_through_run_inference_and_health():
    """Both branches carry the same stamp, so at 3001 ms BOTH expire: nothing is left to
    fuse and the window is UNAVAILABLE (it used to be DEGRADED on two 0.45-weight branches)."""
    for age_ms, status, health, available in [(2999, "fresh", "FULL", True), (3000, "fresh", "FULL", True),
                                              (3001, "missing", "UNAVAILABLE", False)]:
        stamp = (at(0) - timedelta(milliseconds=age_ms)).isoformat()
        record = Stream().tick(0, MEDIUM, provenance={"captured_at": stamp, "telemetry_timestamp": stamp})
        assert record.modality_freshness.vision == status
        assert record.modality_freshness.telemetry == status
        assert record.SystemHealth == health
        assert record.assessment_available is available
        assert record.provenance["vision_expired"] is record.provenance["telemetry_expired"] is (not available)


def test_ut_time_02_a_missing_branch_is_never_promoted_by_a_recent_timestamp():
    verdict = freshness("missing", at(0).isoformat(), at(0), 3)
    # Nothing was received, so there is no age to report and nothing expired.
    assert (verdict.status, verdict.expired, verdict.age_s) == ("missing", False, None)


def test_ut_time_02_the_tolerance_comes_from_the_config():
    stamp = (at(0) - timedelta(milliseconds=5000)).isoformat()
    assert freshness("fresh", stamp, at(0), 5).status == "fresh"
    assert freshness("fresh", stamp, at(0), 4.999).status == "missing"
    assert freshness("fresh", stamp, at(0), 4.999).expired is True


def test_ut_time_02_a_gap_over_3_s_resets_the_streak_and_the_ema():
    # Exactly 3000 ms is NOT a gap (strict >): the streak and the chain continue.
    kept = Stream(ema_alpha=0.35)
    kept.tick(0, 0.2)
    assert kept.tick(3000, 1.0).P_distraction == 0.48
    # 3001 ms is: the High streak restarts and the EMA re-seeds.
    cut = Stream(ema_alpha=0.35)
    cut.tick(0, 0.2)
    again = cut.tick(3001, 1.0)
    assert again.P_distraction == 1.0
    assert again.AlertSeverity == "CAUTION"  # not 3.001 s of credited High

    sustained = Stream()
    sustained.tick(0, HIGH)
    assert sustained.tick(3000, HIGH).AlertSeverity == "HIGH_ALERT"
    broken = Stream()
    broken.tick(0, HIGH)
    assert broken.tick(3001, HIGH).AlertSeverity == "CAUTION"


def test_ut_time_02_a_gap_clears_a_latched_alert():
    s = Stream()
    s.severities([(0, HIGH), (1000, HIGH), (2000, HIGH)])
    assert s.state["last_severity"] == "HIGH_ALERT"
    assert s.tick(10_000, LOW).AlertSeverity == "NORMAL"  # no stale latch after the gap


STAMPS_OF_T0 = [  # five spellings of the same instant
    "2025-01-01T12:00:00+00:00", "2025-01-01T12:00:00Z", "2025-01-01T13:00:00+01:00",
    "2025-01-01T07:00:00-05:00", "2025-01-01T17:30:00+05:30",
]


@pytest.mark.parametrize("now_ms,expected,age_s", [(2999, "fresh", 2.999), (3000, "fresh", 3.0),
                                                   (3001, "missing", 3.001)])
def test_ut_time_02_utc_offsets_are_equivalent(now_ms, expected, age_s):
    assert {freshness("fresh", stamp, at(now_ms), 3).status for stamp in STAMPS_OF_T0} == {expected}
    # ...and the reported age is the same instant-to-instant difference in every spelling.
    assert {freshness("fresh", stamp, at(now_ms), 3).age_s for stamp in STAMPS_OF_T0} == {age_s}


def test_ut_time_02_window_timestamps_normalise_to_the_same_utc_instant():
    stored = {WindowInput(P_distraction=0.1, P_telemetry_anomaly=0.1, timestamp=stamp).timestamp
              for stamp in STAMPS_OF_T0}
    assert len(stored) == 1


# --------------------------------------------------------------------- UT-TIME-03
def test_ut_time_03_ema_seeds_on_the_first_sample():
    s = Stream(ema_alpha=0.35)
    first = s.tick(0, 0.2)
    second = s.tick(1000, 1.0)
    assert first.P_distraction == 0.2     # the seed is the sample itself
    assert second.P_distraction == 0.48   # seeding at 0 would give 0.3955
    assert second.P_distraction != pytest.approx(0.3955)
    assert s.tick(2000, 0.0).P_distraction == 0.312


def test_ut_time_03_the_seed_keeps_provider_precision_and_only_a_smoothed_value_is_rounded():
    s = Stream(ema_alpha=0.35)
    assert s.tick(0, 0.123456789).P_distraction == 0.123456789
    assert s.tick(1000, 0.123456789).P_distraction == 0.123  # smoothed -> 3 dp


# --------------------------------------------------------------------- UT-TIME-04
def test_ut_time_04_an_unavailable_interval_is_not_credited_to_the_sustain():
    s = Stream()
    assert s.tick(0, HIGH).AlertSeverity == "CAUTION"
    dead = s.blackout(1000)
    assert dead.AlertSeverity is None
    assert dead.assessment_available is False
    # 2000 ms of wall clock since the first High, but the middle second was dead.
    assert s.tick(2000, HIGH).AlertSeverity == "CAUTION"
    assert s.tick(3900, HIGH).AlertSeverity == "CAUTION"      # 1.9 s since the resume
    assert s.tick(4000, HIGH).AlertSeverity == "HIGH_ALERT"   # 2.0 s since the resume


def test_ut_time_04_the_timers_are_suspended_then_re_anchored_to_the_resume_window():
    s = Stream()
    s.tick(0, HIGH)
    s.blackout(1000)
    assert s.state["unavailable_since"] == epoch_ms(1000)
    assert s.state["high_since"] is None and s.state["low_since"] is None
    for ms in (2000, 3000, 4000, 5000):
        s.blackout(ms)
        assert s.state["unavailable_since"] == epoch_ms(1000)  # marks the START of the interruption
    s.tick(6000, HIGH)
    assert "unavailable_since" not in s.state
    assert s.state["high_since"] == epoch_ms(6000)


def test_ut_time_04_the_dead_interval_does_not_count_toward_the_recovery_either():
    s = Stream()
    s.severities([(0, HIGH), (1000, HIGH), (2000, HIGH)])
    assert s.tick(3000, LOW).AlertSeverity == "HIGH_ALERT"    # recovery timer starts
    for ms in (4000, 5000, 6000, 7000, 8000, 9000, 10_000, 11_000):
        assert s.blackout(ms).AlertSeverity is None
    assert s.tick(12_000, LOW).AlertSeverity == "HIGH_ALERT"  # 9 s after Low@3000, but a fresh streak
    for ms in range(13_000, 21_900, 1000):                    # continuous, so no gap reset
        assert s.tick(ms, LOW).AlertSeverity == "HIGH_ALERT"
    assert s.tick(21_900, LOW).AlertSeverity == "HIGH_ALERT"  # 9.9 s after the resume
    assert s.tick(22_000, LOW).AlertSeverity == "NORMAL"      # 10.0 s after the resume


def test_a_blackout_never_clears_or_escalates_an_active_alert():
    s = Stream()
    s.severities([(0, HIGH), (1000, HIGH), (2000, HIGH)])
    for ms in range(3000, 63_000, 1000):  # a full minute with nothing to assess
        record = s.blackout(ms)
        assert record.AlertSeverity is None
        assert s.state["last_severity"] == "HIGH_ALERT"
    assert s.tick(63_000, LOW).AlertSeverity == "HIGH_ALERT"  # the latch survived, recovery restarts now


def test_a_blackout_on_a_quiet_machine_stays_quiet():
    s = Stream()
    assert s.blackout(0).AlertSeverity is None
    assert "last_severity" not in s.state  # nothing was latched, nothing is invented
    assert s.tick(1000, LOW).AlertSeverity == "NORMAL"


def test_the_emitted_none_is_never_written_back_into_the_fsm_memory():
    s = Stream()
    s.tick(0, MEDIUM)
    for ms in (1000, 2000):
        s.blackout(ms)
        assert s.state["last_severity"] == "CAUTION"
        assert s.state.get("severity") is None  # the legacy key is never written at all
    s.tick(3000, HIGH)
    assert s.state["last_severity"] == "CAUTION"


def test_a_state_row_written_by_the_old_worker_is_still_read_and_migrated():
    s = Stream()
    s.state = {"severity": "HIGH_ALERT", "high_since": epoch_ms(0), "last_processed_ms": epoch_ms(1000)}
    assert s.tick(2000, LOW).AlertSeverity == "HIGH_ALERT"  # the latch was read from the legacy key
    assert s.state["last_severity"] == "HIGH_ALERT"
    assert "severity" not in s.state


# ----------------------------------------------- the confirmed zero-weight FSM leak
def test_zero_weight_unavailable_window_reports_unavailable_health_and_keeps_the_latch():
    """w_v=1.0 / w_t=0.0 with vision missing and telemetry fresh: nothing carries
    weight, so score and level are None. The health used to be computed with the
    DEFAULT 0.5/0.5 weights and came back DEGRADED, the FSM fell into its Low branch
    and an active HIGH_ALERT silently dropped to NORMAL after 10 s."""
    s = Stream(weight_vision=1.0, weight_telemetry=0.0)
    assert s.severities([(0, HIGH), (1000, HIGH), (2000, HIGH)]) == ["CAUTION", "CAUTION", "HIGH_ALERT"]
    for ms in range(3000, 15_000, 1000):  # 12 s, longer than the recovery window
        record = s.tick(ms, HIGH, vision="missing", telemetry="fresh")
        assert record.RiskScore is None and record.RiskLevel is None
        assert record.SystemHealth == "UNAVAILABLE"
        assert record.assessment_available is False
        assert record.DominantEvidence is None
        assert record.AlertSeverity is None
        assert s.state["last_severity"] == "HIGH_ALERT"
    assert s.tick(15_000, LOW).AlertSeverity == "HIGH_ALERT"  # NORMAL before the fix


def test_zero_weight_on_the_only_fresh_branch_is_unavailable_in_every_field():
    s = Stream(weight_vision=0.0, weight_telemetry=1.0)
    record = s.tick(0, HIGH, vision="fresh", telemetry="missing")
    assert (record.assessment_available, record.RiskScore, record.RiskLevel,
            record.DominantEvidence, record.AlertSeverity, record.SystemHealth) == (
        False, None, None, None, None, "UNAVAILABLE")


def test_a_zero_weight_branch_that_is_not_the_missing_one_stays_available_f_z3():
    s = Stream(weight_vision=1.0, weight_telemetry=0.0)
    record = s.tick(0, MEDIUM, vision="fresh", telemetry="missing")
    assert record.assessment_available is True
    assert record.SystemHealth == "DEGRADED"
    assert record.DominantEvidence == "Partial evidence"
    assert record.AlertSeverity == "CAUTION"


def test_the_unavailable_explanation_names_its_cause():
    both = Stream().blackout(0).explanation
    assert both.startswith("No risk assessment is available because both the vision and telemetry inputs are missing")
    zero_weight = Stream(weight_vision=1.0, weight_telemetry=0.0).tick(
        0, HIGH, vision="missing", telemetry="fresh").explanation
    assert "the vision input is missing and the telemetry branch has zero fusion weight" in zero_weight
    other_way = Stream(weight_vision=0.0, weight_telemetry=1.0).tick(
        0, HIGH, vision="fresh", telemetry="missing").explanation
    assert "the vision branch has zero fusion weight and the telemetry input is missing" in other_way
    for text in (both, zero_weight, other_way):
        assert "low-risk" not in text.lower()


# ----------------------------------------- state hygiene: gap reset and persistence
def test_the_gap_reset_wipes_every_temporal_key():
    s = Stream()
    s.severities([(0, HIGH), (1000, HIGH), (2000, HIGH)])
    s.blackout(3000)
    s.state["severity"] = "HIGH_ALERT"  # a row persisted by the pre-Task-5 worker
    # 10 s of silence, then another blackout. A blackout writes neither severity key,
    # so if either is still present the gap reset missed it.
    s.blackout(13_000)
    assert "last_severity" not in s.state
    assert "severity" not in s.state
    assert s.state["unavailable_since"] == epoch_ms(13_000)  # re-marked, not the stale 3000
    assert s.state["previous_vision"] is None
    assert s.state["high_since"] is None and s.state["low_since"] is None


def test_the_temporal_key_list_covers_every_key_the_fsm_ever_writes():
    s = Stream()
    seen = set()
    for step in range(3):
        for ms, p, vision, telemetry in [(0, HIGH, "fresh", "fresh"), (1000, MEDIUM, "fresh", "fresh"),
                                         (2000, LOW, "fresh", "fresh"), (3000, LOW, "missing", "missing")]:
            s.tick(step * 4000 + ms, p, vision=vision, telemetry=telemetry)
            seen |= set(s.state)
    assert seen <= set(inference.TEMPORAL_STATE_KEYS)


def test_watermark_keys_are_disjoint_from_temporal_keys():
    """The out-of-order guard's watermarks must survive a gap, so they may never be
    among the keys a gap clears. The expected value is written out here, not taken
    from the implementation."""
    assert inference.EVIDENCE_WATERMARK_KEYS == ("captured_at", "telemetry_timestamp")
    assert set(inference.EVIDENCE_WATERMARK_KEYS) & set(inference.TEMPORAL_STATE_KEYS) == set()


def test_runtime_state_survives_a_json_round_trip_like_the_persisted_column():
    s = Stream()
    s.severities([(0, HIGH), (1000, HIGH), (2000, HIGH)])
    s.blackout(3000)
    restored = json.loads(json.dumps(s.state))
    assert restored == s.state
    s.state = restored  # what a restarted worker reads back
    assert s.tick(4000, LOW).AlertSeverity == "HIGH_ALERT"  # the latch and the resume marker both survived
    for ms in range(5000, 14_000, 1000):
        assert s.tick(ms, LOW).AlertSeverity == "HIGH_ALERT"
    assert s.tick(13_900, LOW).AlertSeverity == "HIGH_ALERT"  # 9.9 s after the resume at 4000
    assert s.tick(14_000, LOW).AlertSeverity == "NORMAL"      # 10.0 s: a real recovery, not a gap reset


# --------------------------------------------- the record and the write path
def test_a_producer_that_contradicts_its_own_availability_fails_loudly(monkeypatch):
    """run_inference passes assessment_available itself. Were it left to the schema,
    the before-validator would derive the flag from the score and quietly rewrite a
    contradictory record into a clean 'unavailable' one."""
    s = Stream()
    s.tick(0, HIGH)
    snapshot = json.loads(json.dumps(s.state))
    # The denominator says available; a (buggy) producer reports no score.
    monkeypatch.setattr(fusion, "compute_risk_score", lambda *a, **k: None)
    with pytest.raises(ValidationError):
        s.tick(1000, HIGH)
    assert s.state == snapshot  # a rejected window leaves the temporal memory untouched


@pytest.mark.parametrize("patch,value", [
    ("map_system_health", "UNAVAILABLE"),  # available by the denominator, UNAVAILABLE by the health
    ("map_risk_level", None),              # score present, level missing
    ("determine_dominant_evidence", None), # score present, dominant missing
])
def test_every_availability_contradiction_is_rejected(monkeypatch, patch, value):
    monkeypatch.setattr(fusion, patch, lambda *a, **k: value)
    with pytest.raises(ValidationError):
        Stream().tick(0, HIGH)


def test_an_unavailable_denominator_with_a_score_is_rejected(monkeypatch):
    monkeypatch.setattr(fusion, "compute_risk_score", lambda *a, **k: 50.0)
    with pytest.raises(ValidationError):
        Stream().blackout(0)


def test_the_http_write_path_rejects_the_contradiction_and_persists_nothing(api, api_factory, monkeypatch):
    from app import models
    client, sid = api
    monkeypatch.setattr(fusion, "compute_risk_score", lambda *a, **k: None)
    with pytest.raises(ValidationError):
        client.post(f"/api/sessions/{sid}/windows", json={"P_distraction": 1, "P_telemetry_anomaly": 1})
    monkeypatch.undo()
    assert client.get(f"/api/sessions/{sid}/windows").json() == []
    with api_factory() as db:
        assert (db.get(models.SessionMeta, sid).runtime_state or {}) == {}


def test_an_available_record_never_carries_a_null_severity():
    s = Stream()
    for ms, p in [(0, HIGH), (1000, MEDIUM), (2000, LOW)]:
        record = s.tick(ms, p)
        assert record.assessment_available is True
        assert None not in (record.RiskScore, record.RiskLevel, record.DominantEvidence, record.AlertSeverity)


# ------------------------------------------------- HTTP: end to end through SQLite
@pytest.fixture
def fake_clock(monkeypatch):
    """Patches the clock ``run_inference`` reads; ``clock.set(ms)`` moves it."""
    class Clock(datetime):
        current = at(0)

        @classmethod
        def now(cls, tz=None):
            return cls.current

        @classmethod
        def set(cls, ms):
            cls.current = at(ms)

    monkeypatch.setattr(inference, "datetime", Clock)
    return Clock


def post_window(client, sid, p=HIGH, *, blackout=False):
    body = {"P_distraction": p, "P_telemetry_anomaly": p}
    if blackout:
        body.update(vision_status="missing", telemetry_status="missing")
    response = client.post(f"/api/sessions/{sid}/windows", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def test_ut_time_04_end_to_end_through_the_persisted_runtime_state(api, api_factory, fake_clock):
    from app import models
    client, sid = api
    results = []
    for ms, blackout in [(0, False), (1000, True), (2000, False), (3000, False), (4000, False)]:
        fake_clock.set(ms)
        results.append(post_window(client, sid, blackout=blackout))
    assert [r["AlertSeverity"] for r in results] == ["CAUTION", None, "CAUTION", "CAUTION", "HIGH_ALERT"]
    assert [r["assessment_available"] for r in results] == [True, False, True, True, True]
    assert results[1]["SystemHealth"] == "UNAVAILABLE"
    stored = client.get(f"/api/sessions/{sid}/windows").json()
    assert [r["AlertSeverity"] for r in stored] == [r["AlertSeverity"] for r in results]
    with api_factory() as db:
        state = db.get(models.SessionMeta, sid).runtime_state
    assert state["last_severity"] == "HIGH_ALERT"
    assert "unavailable_since" not in state


def test_a_latched_alert_survives_a_blackout_through_the_persisted_state(api, api_factory, fake_clock):
    from app import models
    client, sid = api
    for ms in (0, 1000, 2000):
        fake_clock.set(ms)
        last = post_window(client, sid)
    assert last["AlertSeverity"] == "HIGH_ALERT"
    fake_clock.set(3000)
    assert post_window(client, sid, blackout=True)["AlertSeverity"] is None
    with api_factory() as db:
        state = db.get(models.SessionMeta, sid).runtime_state
    assert state["last_severity"] == "HIGH_ALERT" and state["unavailable_since"] == epoch_ms(3000)
    fake_clock.set(4000)
    assert post_window(client, sid, p=HIGH)["AlertSeverity"] == "HIGH_ALERT"


# --------------------------------------------------------- UT-TIME-05 (limitation)
class _StubProvider:
    """Stands in for the trained provider: a fresh, High vision window that echoes
    the request's captured_at into the provenance, exactly as trained.py does."""

    def infer(self, data):
        window = WindowInput(P_distraction=1.0, P_telemetry_anomaly=0.0,
                             vision_status="fresh", telemetry_status="missing")
        provenance = {"provider": "StubProvider", "request_id": data.request_id,
                      "vision_source": "camera_frame", "telemetry_source": "missing",
                      "captured_at": data.captured_at, "telemetry_timestamp": data.telemetry_timestamp}
        return window, provenance


def test_ut_time_05_identical_captured_at_is_accepted_and_accumulates_alert_time_known_limitation(
        api, fake_clock, monkeypatch):
    """KNOWN LIMITATION, asserted as the CURRENT behaviour - not a desired one.

    The out-of-order guard in routers/windows.py is a strict ``<``, so a window whose
    captured_at EQUALS the previous one is accepted. Three requests that carry the very
    same frame timestamp therefore all pass, and the repeated old evidence accumulates
    sustained-High time all the way to HIGH_ALERT.

    Ruling A (expired evidence scores as missing) is implemented and does NOT close this:
    every frame here is only 0 - 2 s old, so none of them expires. Closing it needs an
    observation identity / evidence clock (R10), which is not decided yet: this limitation
    belongs to R10, not to ruling A."""
    from app.providers import trained
    monkeypatch.setattr(trained, "get_provider", lambda: _StubProvider())
    client, _ = api
    live = client.post("/api/sessions", json={"session_id": "live-ut05", "operation_mode": "LIVE_MODEL_RUNTIME",
                                              "config": {"ema_alpha": 1}})
    assert live.status_code == 201, live.text
    captured_at = at(0).isoformat()
    results = []
    for index, ms in enumerate((0, 1000, 2000)):
        fake_clock.set(ms)
        response = client.post("/api/sessions/live-ut05/infer",
                               json={"request_id": f"frame{index}", "captured_at": captured_at})
        assert response.status_code == 201, response.text  # 409 would mean the guard caught it
        results.append(response.json())
    assert [r["AlertSeverity"] for r in results] == ["CAUTION", "CAUTION", "HIGH_ALERT"]
    assert {r["provenance"]["captured_at"] for r in results} == {captured_at}
    # Control: the guard does exist - an OLDER stamp is refused.
    fake_clock.set(3000)
    older = client.post("/api/sessions/live-ut05/infer",
                        json={"request_id": "older", "captured_at": (at(0) - timedelta(milliseconds=1)).isoformat()})
    assert older.status_code == 409


def test_out_of_order_guard_survives_a_gap(api, api_factory, fake_clock, monkeypatch):
    """Through POST /infer: a pause longer than the freshness tolerance clears the
    temporal memory, but must NOT clear the evidence watermark. If it did, the next
    OLDER frame would be accepted (201) instead of refused (409).

    The long pause is simulated by moving the persisted ``last_processed_ms`` 60 s
    into the past; nothing sleeps. All frame stamps are in the past, so
    ``normalize_timestamp`` accepts them.

    The server clock is the fake clock, set to each frame's own capture time. Under ruling
    A a frame that is 1.7 years old at the REAL processing time is expired, scores as
    missing and starts no High streak - and this test needs a running streak to prove the
    gap cleared it. So the evidence has to be genuinely fresh (age 0) when it is processed."""
    from app import models
    from app.providers import trained
    monkeypatch.setattr(trained, "get_provider", lambda: _StubProvider())
    client, _ = api
    sid = "live-f2"
    created = client.post("/api/sessions", json={"session_id": sid, "operation_mode": "LIVE_MODEL_RUNTIME"})
    assert created.status_code == 201, created.text

    def infer(request_id, stamp):
        return client.post(f"/api/sessions/{sid}/infer",
                           json={"request_id": request_id, "captured_at": stamp.isoformat()})

    def persisted_state():
        with api_factory() as db:
            return dict(db.get(models.SessionMeta, sid).runtime_state or {})

    def record_count():
        with api_factory() as db:
            return db.query(models.InferenceRecord).filter_by(session_id=sid).count()

    # 1. The first frame sets the watermark.
    first_stamp = at(10_000)
    fake_clock.set(10_000)  # processed the instant it was captured: fresh
    response = infer("f2-frame1", first_stamp)
    assert response.status_code == 201, response.text
    state = persisted_state()
    assert state.get("captured_at") == first_stamp.isoformat()
    high_since_before_gap = state["high_since"]
    assert high_since_before_gap is not None

    # 2. A long pause: the last processed window was a minute ago.
    with api_factory() as db:
        sess = db.get(models.SessionMeta, sid)
        paused = dict(sess.runtime_state)
        paused["last_processed_ms"] -= 60_000
        sess.runtime_state = paused
        db.commit()
    assert persisted_state()["last_processed_ms"] == paused["last_processed_ms"]

    # 3. A newer frame is accepted, and run_inference sees the gap.
    # Only 1 s after the first frame - inside the 3 s tolerance - so the gap can come
    # from nothing but the simulated pause in step 2.
    second_stamp = at(11_000)
    fake_clock.set(11_000)
    response = infer("f2-frame2", second_stamp)
    assert response.status_code == 201, response.text
    state = persisted_state()
    # Control: the gap really did clear the temporal memory (the High streak was
    # re-anchored to this window). Without this the test could pass vacuously.
    assert state["high_since"] > high_since_before_gap

    # 4. ...and the watermark is still there, holding the newest accepted stamp.
    assert state.get("captured_at") == second_stamp.isoformat()
    accepted = record_count()
    assert accepted == 2

    # 5. An older frame is refused and leaves nothing behind.
    response = infer("f2-frame3", at(10_500))  # older than the watermark (11 s)
    assert response.status_code == 409, response.text
    assert record_count() == accepted
    assert persisted_state()["captured_at"] == second_stamp.isoformat()


def test_out_of_order_guard_survives_a_gap_for_telemetry(api, api_factory, fake_clock, monkeypatch):
    """Codex R13: the telemetry half of ``test_out_of_order_guard_survives_a_gap``, step for
    step. That test only exercises the ``captured_at`` watermark; ``telemetry_timestamp`` was
    guarded by the static disjointness test alone. Here only the TELEMETRY watermark is in
    play: the requests carry no image and no ``captured_at``, so that key never enters the
    persisted state (asserted below), and a 409 or a lost watermark can only be the telemetry
    one.

    Uses ``_RequestDrivenStubProvider`` and ``TELEMETRY_FEATURES`` (both defined further down,
    in the IT-LIVE-AGE section). The stub reports telemetry 'fresh' and High, vision
    'missing'. The pipeline re-derives freshness from the stamps (R08), and under ruling A
    a reading that is old at processing time is expired and scores as missing - which would
    leave nothing to fuse and no High streak for this test to watch the gap clear. (Before
    ruling A the 2025 stamps came out 'stale' and still scored High, which is what let this
    test run on the real clock.) So the server clock is the fake clock, set to each
    reading's own capture time: the evidence is fresh when it is processed. The long pause
    is simulated by moving the persisted ``last_processed_ms`` 60 s into the past; nothing
    sleeps. All stamps are in the past, so ``normalize_timestamp`` accepts them."""
    from app import models
    from app.providers import trained
    monkeypatch.setattr(trained, "get_provider", lambda: _RequestDrivenStubProvider())
    client, _ = api
    sid = "live-r13"
    created = client.post("/api/sessions", json={"session_id": sid, "operation_mode": "LIVE_MODEL_RUNTIME"})
    assert created.status_code == 201, created.text

    def infer(request_id, stamp):
        return client.post(f"/api/sessions/{sid}/infer",
                           json={"request_id": request_id, "telemetry_features": TELEMETRY_FEATURES,
                                 "telemetry_timestamp": stamp.isoformat(), "telemetry_source": "prepared_replay"})

    def persisted_state():
        with api_factory() as db:
            return dict(db.get(models.SessionMeta, sid).runtime_state or {})

    def record_count():
        with api_factory() as db:
            return db.query(models.InferenceRecord).filter_by(session_id=sid).count()

    # 1. The first reading sets the telemetry watermark - and only that one.
    first_stamp = at(10_000)
    fake_clock.set(10_000)  # processed the instant it was captured: fresh
    response = infer("r13-frame1", first_stamp)
    assert response.status_code == 201, response.text
    state = persisted_state()
    assert state.get("telemetry_timestamp") == first_stamp.isoformat()
    assert "captured_at" not in state  # no image was sent: the vision watermark is not involved
    high_since_before_gap = state["high_since"]
    assert high_since_before_gap is not None

    # 2. A long pause: the last processed window was a minute ago.
    with api_factory() as db:
        sess = db.get(models.SessionMeta, sid)
        paused = dict(sess.runtime_state)
        paused["last_processed_ms"] -= 60_000
        sess.runtime_state = paused
        db.commit()
    assert persisted_state()["last_processed_ms"] == paused["last_processed_ms"]

    # 3. A newer reading is accepted, and run_inference sees the gap.
    # Only 1 s after the first frame - inside the 3 s tolerance - so the gap can come
    # from nothing but the simulated pause in step 2.
    second_stamp = at(11_000)
    fake_clock.set(11_000)
    response = infer("r13-frame2", second_stamp)
    assert response.status_code == 201, response.text
    state = persisted_state()
    # Control: the gap really did clear the temporal memory (the High streak was
    # re-anchored to this window). Without this the test could pass vacuously.
    assert state["high_since"] > high_since_before_gap

    # 4. ...and the telemetry watermark is still there, holding the newest accepted stamp.
    assert state.get("telemetry_timestamp") == second_stamp.isoformat()
    accepted = record_count()
    assert accepted == 2

    # 5. A reading older than that is refused and leaves nothing behind.
    response = infer("r13-frame3", at(10_500))  # older than the watermark (11 s)
    assert response.status_code == 409, response.text
    assert record_count() == accepted
    assert persisted_state()["telemetry_timestamp"] == second_stamp.isoformat()


# --------------------------------------------------------- UT-TIME-06 (ruling A)
# Was the D13 behaviour snapshot "a stale-only stream still reaches HIGH_ALERT". Ruling A made
# that behaviour a defect and fixed it: this is now the REQUIREMENT, asserted as such.
@pytest.mark.parametrize("age,age_s", [(timedelta(seconds=60), 60.0), (timedelta(hours=1), 3600.0),
                                       (timedelta(days=30), 2592000.0)],
                         ids=["1-minute", "1-hour", "30-days"])
def test_ut_time_06_an_expired_only_stream_never_reaches_high_alert(age, age_s):
    """Every window carries only expired evidence, and the evidence would score High if it
    counted. The system must not alert on it: both branches expire, so each window has no
    assessment (UNAVAILABLE, AlertSeverity null) and the alert timers are SUSPENDED - no
    High streak starts, and nothing is latched. The stream runs for 9 s, well past the 2 s
    sustain, so a leak would show as CAUTION / HIGH_ALERT."""
    s = Stream()
    old = (at(0) - age).isoformat()
    records = []
    for ms in range(0, 10_000, 1000):
        # a retried / delayed delivery: the capture stamp is fixed, the server clock moves on
        records.append(s.tick(ms, HIGH, provenance={"captured_at": old, "telemetry_timestamp": old}))
    for ms, record in zip(range(0, 10_000, 1000), records):
        assert record.modality_freshness.vision == "missing"
        assert record.modality_freshness.telemetry == "missing"
        assert record.assessment_available is False
        assert (record.RiskScore, record.RiskLevel, record.DominantEvidence, record.AlertSeverity) == (
            None, None, None, None)
        assert record.SystemHealth == "UNAVAILABLE"
        # The reason is kept: these are EXPIRED, not "no input".
        assert record.provenance["vision_expired"] is True and record.provenance["telemetry_expired"] is True
        assert record.provenance["vision_age_s"] == record.provenance["telemetry_age_s"] == age_s + ms / 1000
    assert [r.AlertSeverity for r in records] == [None] * 10
    # Timers suspended, nothing latched: the FSM never left its initial state.
    assert s.state["high_since"] is None and s.state["low_since"] is None
    assert s.state["unavailable_since"] == epoch_ms(0)
    assert "last_severity" not in s.state


def test_ut_time_06_fresh_evidence_next_to_an_expired_branch_still_alerts():
    """The control for the test above: expiry removes the OLD branch, not the alerting. Vision
    is a day old and expired; telemetry is current and High, so the stream is DEGRADED but
    assessed, and sustained High still latches HIGH_ALERT after 2 s."""
    s = Stream()
    old = (at(0) - timedelta(days=1)).isoformat()
    severities = []
    for ms in (0, 1000, 1999, 2000, 3000):
        record = s.tick(ms, HIGH, provenance={"captured_at": old, "telemetry_timestamp": at(ms).isoformat()})
        assert record.modality_freshness.vision == "missing" and record.modality_freshness.telemetry == "fresh"
        assert record.SystemHealth == "DEGRADED" and record.RiskLevel == "High"
        severities.append(record.AlertSeverity)
    assert severities == ["CAUTION", "CAUTION", "CAUTION", "HIGH_ALERT", "HIGH_ALERT"]


# --------------------------------------------------------------- IT-LIVE-AGE
# Freshness is not the provider's call. run_inference re-derives it from the evidence
# timestamps, so a Live request whose captured_at / telemetry_timestamp is older than the
# tolerance at processing time is EXPIRED - the branch scores as missing and the provenance
# says why (ruling A) - even though the provider reported the branch as present. These tests
# prove it end to end through POST /infer, on a stubbed provider, so they need no model
# weights. (They used to assert the 'stale' / 0.45 tier; the runtime no longer produces it.)
TELEMETRY_FEATURES = {"speed_kmph": 52, "accel_x": 0.7, "accel_y": 0.2, "brake_pressure": 20,
                      "steering_angle": 7.5, "throttle": 40, "lane_deviation": 0.21,
                      "headway_distance": 18}


class _RequestDrivenStubProvider:
    """Stands in for the trained provider with its status logic: a branch is 'fresh' (and
    scores High) exactly when the request carried that branch's input, 'missing' otherwise.
    Unlike _StubProvider it can report telemetry as fresh. It never reports a branch as
    expired: the pipeline must work that out from the timestamps, which is what IT-LIVE-AGE checks."""

    def infer(self, data):
        has_image = data.image_base64 is not None
        has_telemetry = data.telemetry_features is not None
        window = WindowInput(P_distraction=1.0 if has_image else 0.0,
                             P_telemetry_anomaly=1.0 if has_telemetry else 0.0,
                             vision_status="fresh" if has_image else "missing",
                             telemetry_status="fresh" if has_telemetry else "missing",
                             telemetry_features=data.telemetry_features)
        provenance = {"provider": "RequestDrivenStubProvider", "request_id": data.request_id,
                      "vision_source": "camera_frame" if has_image else "missing",
                      "telemetry_source": data.telemetry_source,
                      "captured_at": data.captured_at, "telemetry_timestamp": data.telemetry_timestamp}
        return window, provenance


def _live_age_session(client, monkeypatch, sid):
    from app.providers import trained
    monkeypatch.setattr(trained, "get_provider", lambda: _RequestDrivenStubProvider())
    created = client.post("/api/sessions", json={"session_id": sid, "operation_mode": "LIVE_MODEL_RUNTIME"})
    assert created.status_code == 201, created.text
    return sid


def _live_age_request(request_id, vision_stamp, telemetry_stamp):
    return {"request_id": request_id, "image_base64": "stub-frame", "captured_at": vision_stamp.isoformat(),
            "telemetry_features": TELEMETRY_FEATURES, "telemetry_timestamp": telemetry_stamp.isoformat(),
            "telemetry_source": "prepared_replay"}


@pytest.mark.parametrize("branch", ["vision", "telemetry"])
@pytest.mark.parametrize("age_ms,expected,expired,age_s,health", [
    (2999, "fresh", False, 2.999, "FULL"), (3000, "fresh", False, 3.0, "FULL"),
    (3001, "missing", True, 3.001, "DEGRADED")])
def test_it_live_age_freshness_boundary_is_rederived_from_the_evidence_timestamp_through_infer(
        api, fake_clock, monkeypatch, branch, age_ms, expected, expired, age_s, health):
    """The 3 s tolerance is strict (> 3): 2.999 s and 3.000 s are fresh, 3.001 s is EXPIRED -
    scored as missing, with ``{branch}_expired`` and the measured age in the provenance. The
    provider says 'fresh' every time; only the timestamp can expire a branch. The other branch
    is a fresh control (age 0), so a flipped status is attributable to its own timestamp, and
    DEGRADED can only come from the aged branch."""
    client, _ = api
    sid = _live_age_session(client, monkeypatch, f"live-age-{branch}-{age_ms}")
    fake_clock.set(0)  # the server processes the request at at(0)
    aged, current = at(0) - timedelta(milliseconds=age_ms), at(0)
    stamps = {"vision": current, "telemetry": current, branch: aged}
    response = client.post(f"/api/sessions/{sid}/infer",
                           json=_live_age_request("boundary", stamps["vision"], stamps["telemetry"]))
    assert response.status_code == 201, response.text
    record = response.json()
    control = "telemetry" if branch == "vision" else "vision"
    assert record["modality_freshness"][branch] == expected
    assert record["modality_freshness"][control] == "fresh"
    assert record["SystemHealth"] == health
    assert record["assessment_available"] is True
    provenance = record["provenance"]
    assert provenance[f"{branch}_expired"] is expired
    assert provenance[f"{branch}_age_s"] == age_s
    assert provenance[f"{control}_expired"] is False and provenance[f"{control}_age_s"] == 0.0
    assert provenance["captured_at" if branch == "vision" else "telemetry_timestamp"] == aged.isoformat()


@pytest.mark.parametrize("branch", ["vision", "telemetry"])
def test_it_live_age_a_30_day_old_frame_is_expired_and_scored_as_missing_but_the_window_is_still_assessed(
        api, fake_clock, monkeypatch, branch):
    """One branch is 30 days old, the other is current. The old branch is EXPIRED: it is
    'missing' for scoring (no fusion weight), so the window is DEGRADED and its score is
    the current branch's alone - and the provenance keeps the reason and the age
    (30 * 86400 = 2592000 s)."""
    client, _ = api
    sid = _live_age_session(client, monkeypatch, f"live-age-30d-{branch}")
    fake_clock.set(0)
    old, current = at(0) - timedelta(days=30), at(0)
    stamps = {"vision": current, "telemetry": current, branch: old}
    response = client.post(f"/api/sessions/{sid}/infer",
                           json=_live_age_request("thirty-days", stamps["vision"], stamps["telemetry"]))
    assert response.status_code == 201, response.text
    record = response.json()
    control = "telemetry" if branch == "vision" else "vision"
    assert record["modality_freshness"][branch] == "missing"
    assert record["modality_freshness"][control] == "fresh"
    assert record["provenance"][f"{branch}_expired"] is True
    assert record["provenance"][f"{branch}_age_s"] == 2592000.0
    assert record["provenance"][f"{control}_expired"] is False
    assert record["SystemHealth"] == "DEGRADED"
    assert record["assessment_available"] is True
    assert record["RiskScore"] == 100.0 and record["RiskLevel"] == "High"
    stored = client.get(f"/api/sessions/{sid}/windows").json()
    assert [r["modality_freshness"] for r in stored] == [record["modality_freshness"]]
    assert [r["provenance"] for r in stored] == [record["provenance"]]


def test_it_live_age_an_expired_only_stream_never_reaches_high_alert_through_infer(
        api, api_factory, fake_clock, monkeypatch):
    """Ruling A on the LIVE path, driven through POST /infer - the requirement that replaced the
    D13 behaviour snapshot. Every frame, and every telemetry reading, is 30 days old at
    processing time, and each stamp is newer than the last (so the out-of-order guard accepts
    them) and different from it (so this is not the identical-timestamp case of UT-TIME-05).
    Both branches expire, so every window is UNAVAILABLE with a null AlertSeverity and the alert
    timers are suspended: the server clock advancing 1000 ms per request cannot sustain High,
    however long the stream runs."""
    from app import models
    client, _ = api
    sid = _live_age_session(client, monkeypatch, "live-age-d13")
    records = []
    for index, ms in enumerate((0, 1000, 2000, 3000, 4000)):
        fake_clock.set(ms)
        stamp = at(ms) - timedelta(days=30)
        response = client.post(f"/api/sessions/{sid}/infer", json=_live_age_request(f"old{index}", stamp, stamp))
        assert response.status_code == 201, response.text  # 409 would mean the guard caught it
        records.append(response.json())
    assert len({r["provenance"]["captured_at"] for r in records}) == 5
    for record in records:
        assert record["modality_freshness"] == {"vision": "missing", "telemetry": "missing"}
        assert record["provenance"]["vision_expired"] is True and record["provenance"]["telemetry_expired"] is True
        assert record["provenance"]["vision_age_s"] == record["provenance"]["telemetry_age_s"] == 2592000.0
        assert record["SystemHealth"] == "UNAVAILABLE"
        assert record["assessment_available"] is False
        assert (record["RiskScore"], record["RiskLevel"], record["DominantEvidence"], record["AlertSeverity"]) == (
            None, None, None, None)
    with api_factory() as db:
        state = db.get(models.SessionMeta, sid).runtime_state
    # Suspended, not running: no High streak was ever started, and nothing is latched.
    assert state["high_since"] is None and state["low_since"] is None
    assert state["unavailable_since"] == epoch_ms(0)
    assert "last_severity" not in state


# ------------------------------------------------------- UT-EMA-PARITY-01 (Python)
PARITY_CASES = json.loads((REPO_ROOT / "ai/fixtures/ema_parity_vectors.json").read_text(encoding="utf-8"))
PARITY_IDS = [case["id"] for case in PARITY_CASES]


# A case marked "legacy" exercises the historical stale (0.45) tier. The pure functions still
# implement it, so the reference-specification test below keeps running them; the runtime no
# longer produces it, so run_inference is not asked to reproduce them (see the test after).
RUNTIME_CASES = [case for case in PARITY_CASES if "legacy" not in case]
RUNTIME_IDS = [case["id"] for case in RUNTIME_CASES]
LEGACY_CASES = [case for case in PARITY_CASES if "legacy" in case]


def test_ut_ema_parity_01_covers_the_three_required_situations():
    assert {"first-window-keeps-provider-precision", "first-fresh-after-stale-reseeds",
            "consecutive-fresh-run"} <= set(PARITY_IDS)
    assert len(set(PARITY_IDS)) == len(PARITY_IDS)


def test_ut_ema_parity_01_exactly_the_cases_that_use_the_stale_tier_are_marked_legacy():
    uses_stale = {case["id"] for case in PARITY_CASES
                  if any("stale" in (w["vision_status"], w["telemetry_status"]) for w in case["windows"])}
    assert uses_stale == {"first-fresh-after-stale-reseeds"}
    assert {case["id"] for case in LEGACY_CASES} == uses_stale
    assert all(case["legacy"] for case in LEGACY_CASES)  # a reason, not an empty marker
    assert len(RUNTIME_CASES) == 10


@pytest.mark.parametrize("case", LEGACY_CASES, ids=[case["id"] for case in LEGACY_CASES])
def test_ut_ema_parity_01_the_runtime_never_produces_the_legacy_stale_tier(case):
    """Fed a legacy case's own windows, run_inference treats a branch declared ``stale`` as
    EXPIRED (scored as missing, reason kept) and never emits ``stale`` - which is why the
    case's 0.45-based expectations cannot be asserted against the runtime."""
    s = Stream(**case["config"])
    for index, window in enumerate(case["windows"]):
        record = s.tick(index * 1000, window["P_distraction"], vision=window["vision_status"],
                        telemetry=window["telemetry_status"], pt=window["P_telemetry_anomaly"])
        assert {record.modality_freshness.vision, record.modality_freshness.telemetry} <= {"fresh", "missing"}
        for branch, declared in (("vision", window["vision_status"]), ("telemetry", window["telemetry_status"])):
            if declared == "stale":
                assert getattr(record.modality_freshness, branch) == "missing"
                assert record.provenance[f"{branch}_expired"] is True
                assert record.provenance[f"{branch}_age_s"] is None  # declared, with no timestamp to measure


@pytest.mark.parametrize("source", ["old-capture-time", "declared-stale"])
def test_ema_reseeds_on_the_first_fresh_window_after_an_expired_one(source):
    """Expired vision is missing vision for the EMA too: it must leave no ``previous_vision``
    behind, so the next fresh frame is a new seed (0.6 as it is) and not smoothed against the
    frame from before the expiry (which would give 0.34 = 0.35 * 0.6 + 0.65 * 0.2). The
    middle window stays assessable through telemetry, so only the vision chain is in question."""
    s = Stream(ema_alpha=0.35, weight_vision=0.6, weight_telemetry=0.4)
    old = (at(0) - timedelta(minutes=5)).isoformat()
    first = s.tick(0, 0.2, pt=0.1)
    assert first.P_distraction == 0.2 and first.RiskScore == 16.0
    assert s.state["previous_vision"] == 0.2  # the chain is running
    if source == "old-capture-time":
        middle = s.tick(1000, 0.9, pt=0.1, provenance={"captured_at": old})
    else:
        middle = s.tick(1000, 0.9, pt=0.1, vision="stale")
    # Expired vision contributes nothing: P_distraction is the missing-branch 0.0 and the
    # score is telemetry alone. The chain is dropped, not carried over the expired window.
    assert (middle.modality_freshness.vision, middle.provenance["vision_expired"]) == ("missing", True)
    assert middle.P_distraction == 0.0 and middle.RiskScore == 10.0 and middle.SystemHealth == "DEGRADED"
    assert s.state["previous_vision"] is None
    third = s.tick(2000, 0.6, pt=0.1)
    assert third.P_distraction == 0.6 and third.RiskScore == 40.0 and third.SystemHealth == "FULL"
    assert s.tick(3000, 0.6, pt=0.1).P_distraction == 0.6  # and now the chain smooths again


@pytest.mark.parametrize("case", RUNTIME_CASES, ids=RUNTIME_IDS)
def test_ut_ema_parity_01_run_inference_matches_the_shared_oracle(case):
    s = Stream(**case["config"])
    for index, (window, want) in enumerate(zip(case["windows"], case["expect"])):
        record = s.tick(index * 1000, window["P_distraction"], vision=window["vision_status"],
                        telemetry=window["telemetry_status"], pt=window["P_telemetry_anomaly"])
        assert {"P_distraction": record.P_distraction, "P_telemetry_anomaly": record.P_telemetry_anomaly,
                "assessment_available": record.assessment_available, "RiskScore": record.RiskScore,
                "SystemHealth": record.SystemHealth} == want, (case["id"], index + 1)


@pytest.mark.parametrize("case", PARITY_CASES, ids=PARITY_IDS)
def test_ut_ema_parity_01_the_reference_specification_agrees(case):
    """ai/reference/risk_logic.py is loaded by test_fusion_vectors.py through importlib and
    imported from there as ``reference``; this keeps its ema() honest. The caller
    convention is the one its docstring states: re-seed (previous=None) after anything
    that was not a fresh, assessed window."""
    cfg = case["config"]
    previous = None
    for index, (window, want) in enumerate(zip(case["windows"], case["expect"])):
        vision, telemetry = window["vision_status"], window["telemetry_status"]
        sample = window["P_distraction"] if vision != "missing" else 0.0
        pd = reference.ema(sample, previous, cfg["ema_alpha"]) if vision == "fresh" else sample
        score = reference.compute_risk_score(pd, window["P_telemetry_anomaly"], cfg["weight_vision"],
                                             cfg["weight_telemetry"], vision, telemetry)
        assert (pd, score) == (want["P_distraction"], want["RiskScore"]), (case["id"], index + 1)
        previous = pd if vision == "fresh" and score is not None else None
