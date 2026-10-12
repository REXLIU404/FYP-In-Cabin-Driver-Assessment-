"""Task 5 - the temporal layer: what the EMA and the Alert FSM do over time, and in
particular across a window that carries no assessment.

Everything here runs on an INJECTED clock (``now=``, or a patched
``inference.datetime`` for the HTTP tests); nothing sleeps. The 2000 ms sustain,
the 10000 ms recovery and the 3 s freshness tolerance are written as literals on
purpose - none of them is imported from the implementation, so a changed constant
cannot drag its own expectation along with it.

UT-TIME-01  FSM boundaries                       UT-TIME-04  unavailable is not credited
UT-TIME-02  freshness / gap / UTC offsets        UT-TIME-05  identical captured_at   (known limitation)
UT-TIME-03  EMA seed convention                  UT-TIME-06  stale-only stream, D13  (known limitation)
UT-EMA-PARITY-01  Python half; the TypeScript half is ai/src/emaParity.test.ts
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
@pytest.mark.parametrize("age_ms,expected", [(2999, "fresh"), (3000, "fresh"), (3001, "stale")])
def test_ut_time_02_freshness_boundary(age_ms, expected):
    stamp = (at(0) - timedelta(milliseconds=age_ms)).isoformat()
    assert freshness("fresh", stamp, at(0), 3) == expected


def test_ut_time_02_freshness_through_run_inference_and_health():
    for age_ms, status, health in [(2999, "fresh", "FULL"), (3000, "fresh", "FULL"), (3001, "stale", "DEGRADED")]:
        stamp = (at(0) - timedelta(milliseconds=age_ms)).isoformat()
        record = Stream().tick(0, MEDIUM, provenance={"captured_at": stamp, "telemetry_timestamp": stamp})
        assert record.modality_freshness.vision == status
        assert record.modality_freshness.telemetry == status
        assert record.SystemHealth == health


def test_ut_time_02_a_missing_branch_is_never_promoted_by_a_recent_timestamp():
    assert freshness("missing", at(0).isoformat(), at(0), 3) == "missing"


def test_ut_time_02_the_tolerance_comes_from_the_config():
    stamp = (at(0) - timedelta(milliseconds=5000)).isoformat()
    assert freshness("fresh", stamp, at(0), 5) == "fresh"
    assert freshness("fresh", stamp, at(0), 4.999) == "stale"


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


@pytest.mark.parametrize("now_ms,expected", [(2999, "fresh"), (3000, "fresh"), (3001, "stale")])
def test_ut_time_02_utc_offsets_are_equivalent(now_ms, expected):
    assert {freshness("fresh", stamp, at(now_ms), 3) for stamp in STAMPS_OF_T0} == {expected}


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
    sustained-High time all the way to HIGH_ALERT. The complete evidence-age policy
    (decision D13) is out of scope for this phase."""
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


# --------------------------------------------------------- UT-TIME-06 (limitation)
@pytest.mark.parametrize("age", [timedelta(seconds=60), timedelta(hours=1), timedelta(days=30)],
                         ids=["1-minute", "1-hour", "30-days"])
def test_ut_time_06_stale_only_stream_still_reaches_high_alert_known_limitation_d13(age):
    """BEHAVIOUR SNAPSHOT for decision D13 - NOT desired behaviour.

    The system has NO maximum evidence age: ``freshness()`` can only ever return
    'stale' for a branch that has a timestamp, never 'missing', and a stale branch
    keeps its 0.45 fusion weight indefinitely. A stream whose every window carries
    only stale evidence, and whose score stays High, therefore still accumulates
    sustained-High time and escalates to HIGH_ALERT - on a 30-day-old frame as on a
    one-minute-old one. This asserts what the code does today so the limitation is on
    record; do NOT read it as 'stale evidence is handled'.

    It is unreachable from the Live runtime: trained.py only emits fresh / missing
    (see the source guard below), so it needs a replay input or a direct POST /windows."""
    s = Stream()
    old = (at(0) - age).isoformat()
    records = [s.tick(ms, HIGH, provenance={"captured_at": old, "telemetry_timestamp": old})
               for ms in (0, 1000, 2000, 3000)]
    for record in records:
        assert record.modality_freshness.vision == "stale"
        assert record.modality_freshness.telemetry == "stale"
        assert record.SystemHealth == "DEGRADED"
        assert record.DominantEvidence == "Partial evidence"
        assert record.RiskLevel == "High"
    assert [r.AlertSeverity for r in records] == ["CAUTION", "CAUTION", "HIGH_ALERT", "HIGH_ALERT"]


def test_ut_time_06_source_guard_the_trained_provider_never_emits_stale():
    """Why UT-TIME-06 is unreachable from Live. If this fails, the provider started
    reporting 'stale' and D13 is no longer a replay-only limitation: revisit it."""
    source = (REPO_ROOT / "backend/app/providers/trained.py").read_text(encoding="utf-8")
    assert "stale" not in source
    assert 'vision_status="fresh" if data.image_base64 is not None else "missing"' in source
    assert 'telemetry_status="fresh" if data.telemetry_features is not None else "missing"' in source


# ------------------------------------------------------- UT-EMA-PARITY-01 (Python)
PARITY_CASES = json.loads((REPO_ROOT / "ai/fixtures/ema_parity_vectors.json").read_text(encoding="utf-8"))
PARITY_IDS = [case["id"] for case in PARITY_CASES]


def test_ut_ema_parity_01_covers_the_three_required_situations():
    assert {"first-window-keeps-provider-precision", "first-fresh-after-stale-reseeds",
            "consecutive-fresh-run"} <= set(PARITY_IDS)
    assert len(set(PARITY_IDS)) == len(PARITY_IDS)


@pytest.mark.parametrize("case", PARITY_CASES, ids=PARITY_IDS)
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
    """ai/reference/risk_logic.py has no importer; this keeps its ema() honest. The
    caller convention is the one its docstring states: re-seed (previous=None) after
    anything that was not a fresh, assessed window."""
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
