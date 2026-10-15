"""P0-D13, ruling A - expired evidence scores as missing, and the reason is kept.

Ruling A (D13 / Codex R09; confirmed by the user on 2026-10-13):

1. Evidence older than ``freshness_tolerance_s`` (strict ``>``: exactly 3.000 s is still fresh)
   is EXPIRED and scores as ``missing`` - freshness factor 0.
2. The reason is kept: the provenance records ``{modality}_expired`` and ``{modality}_age_s``
   for BOTH branches of EVERY new record, so "unusable because it expired" and "no input was
   received" can be told apart.
3. If both branches are missing or expired the window is unavailable exactly as before (D01):
   ``assessment_available`` false, the four risk fields null, ``SystemHealth`` UNAVAILABLE.
4. The runtime never produces ``stale`` any more. The 0.45 tier survives only so that records
   written before this ruling can still be read and rendered.
5. The threshold is the session's ``freshness_tolerance_s`` (default 3 s, configurable in
   (0, 30]). It is a DESIGN threshold - derived from the 2 s telemetry period plus the <= 1 s
   end-to-end target - not a validated safety threshold.

IT-EXPIRY-REASON       an expired branch and a missing branch are distinguishable; an expired
                       branch next to a fresh one is DEGRADED and scores from the fresh one alone
IT-EXPIRY-SENSITIVITY  the tolerance is per-session (2 / 3 / 5 s) and the comparison is strict.
                       This proves the CONFIGURATION is wired and ``>`` is strict. It is NOT
                       evidence that 3 s is the right number: the empirical check against the
                       measured capture -> fusion latency (PERF-01) belongs to Task 10.
IT-EXPIRY-NO-STALE     no new record, through /infer or /windows, ever carries ``stale``
(historical)           a stored record that DOES carry ``stale`` is still read and exported

The age rule itself is also covered, at unit level, in ``test_temporal_contract.py`` (UT-TIME-02)
and, end to end with the 3001 ms boundary and a 30-day-old frame, in IT-LIVE-AGE there.

No test needs model weights: the provider is stubbed, the clock is the fake clock of
``test_temporal_contract``, and every expectation is a literal.
"""
import csv
import io
import json
from datetime import timedelta

import pytest

from app import models
from app.inference import freshness, run_inference
from app.schemas import RuntimeConfig, WindowInput

# Sibling test module: the fake clock, the instant helper and the telemetry sample that
# IT-LIVE-AGE already uses. ``fake_clock`` is a fixture; importing it makes it visible here.
from test_temporal_contract import TELEMETRY_FEATURES, at, fake_clock  # noqa: F401


class _ProbabilityStub:
    """Stands in for the trained provider. A branch is 'fresh' exactly when the request carried
    its input, and then it reports a fixed, DIFFERENT probability per branch (vision 0.8,
    telemetry 0.2), so a score identifies which branches were fused: 80.0 = vision alone,
    20.0 = telemetry alone, 50.0 = both. It never reports a branch as expired or stale - that
    is the pipeline's job, from the timestamps."""

    def infer(self, data):
        has_image = data.image_base64 is not None
        has_telemetry = data.telemetry_features is not None
        window = WindowInput(P_distraction=0.8 if has_image else 0.0,
                             P_telemetry_anomaly=0.2 if has_telemetry else 0.0,
                             vision_status="fresh" if has_image else "missing",
                             telemetry_status="fresh" if has_telemetry else "missing",
                             telemetry_features=data.telemetry_features)
        provenance = {"provider": "ProbabilityStub", "request_id": data.request_id,
                      "vision_source": "camera_frame" if has_image else "missing",
                      "telemetry_source": data.telemetry_source,
                      "captured_at": data.captured_at, "telemetry_timestamp": data.telemetry_timestamp}
        return window, provenance


def _live_session(client, monkeypatch, sid, tolerance=None):
    from app.providers import trained
    monkeypatch.setattr(trained, "get_provider", lambda: _ProbabilityStub())
    sid = sid.replace(".", "p")  # a session id may not contain a dot; a test id such as 2.999 does
    body = {"session_id": sid, "operation_mode": "LIVE_MODEL_RUNTIME"}
    if tolerance is not None:
        body["config"] = {"freshness_tolerance_s": tolerance}
    created = client.post("/api/sessions", json=body)
    assert created.status_code == 201, created.text
    return sid


def _request(request_id, *, vision_at=None, telemetry_at=None):
    """A /infer body. A branch is present iff its capture time is given."""
    body = {"request_id": request_id}
    if vision_at is not None:
        body.update(image_base64="stub-frame", captured_at=vision_at.isoformat())
    if telemetry_at is not None:
        body.update(telemetry_features=TELEMETRY_FEATURES, telemetry_timestamp=telemetry_at.isoformat(),
                    telemetry_source="prepared_replay")
    return body


def _infer(client, sid, body):
    response = client.post(f"/api/sessions/{sid}/infer", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def _ago(seconds):
    """The capture instant of evidence that is ``seconds`` old when the fake clock reads 0."""
    return at(0) - timedelta(seconds=seconds)


NO_ASSESSMENT = (None, None, None, None)


def _risk_fields(record):
    return (record["RiskScore"], record["RiskLevel"], record["DominantEvidence"], record["AlertSeverity"])


# ----------------------------------------------------------------- IT-EXPIRY-REASON
def test_it_expiry_reason_an_expired_branch_and_a_missing_branch_are_told_apart(api, fake_clock, monkeypatch):
    """Vision EXPIRED + telemetry never received, versus nothing received at all. The scoring
    outcome is identical - both are UNAVAILABLE, both branches 'missing' - and the provenance
    is the only thing that says which one it was."""
    client, _ = api
    fake_clock.set(0)
    expired = _infer(client, _live_session(client, monkeypatch, "reason-expired"),
                     _request("expired", vision_at=_ago(10)))
    nothing = _infer(client, _live_session(client, monkeypatch, "reason-nothing"), _request("nothing"))

    for record in (expired, nothing):
        assert record["modality_freshness"] == {"vision": "missing", "telemetry": "missing"}
        assert record["assessment_available"] is False
        assert _risk_fields(record) == NO_ASSESSMENT
        assert record["SystemHealth"] == "UNAVAILABLE"
        assert record["AlertSeverity"] is None
    # ...but not for the same reason.
    provenance = expired["provenance"]
    assert (provenance["vision_expired"], provenance["vision_age_s"]) == (True, 10.0)
    assert (provenance["telemetry_expired"], provenance["telemetry_age_s"]) == (False, None)
    provenance = nothing["provenance"]
    assert (provenance["vision_expired"], provenance["vision_age_s"]) == (False, None)
    assert (provenance["telemetry_expired"], provenance["telemetry_age_s"]) == (False, None)


def test_it_expiry_reason_the_mirror_case_and_both_branches_expired(api, fake_clock, monkeypatch):
    client, _ = api
    fake_clock.set(0)
    only_telemetry = _infer(client, _live_session(client, monkeypatch, "reason-telemetry"),
                            _request("t", telemetry_at=_ago(7.5)))
    both = _infer(client, _live_session(client, monkeypatch, "reason-both"),
                  _request("b", vision_at=_ago(4), telemetry_at=_ago(60)))
    p = only_telemetry["provenance"]
    assert (p["vision_expired"], p["vision_age_s"], p["telemetry_expired"], p["telemetry_age_s"]) == (
        False, None, True, 7.5)
    p = both["provenance"]
    assert (p["vision_expired"], p["vision_age_s"], p["telemetry_expired"], p["telemetry_age_s"]) == (
        True, 4.0, True, 60.0)
    for record in (only_telemetry, both):
        assert record["assessment_available"] is False and record["SystemHealth"] == "UNAVAILABLE"
        assert _risk_fields(record) == NO_ASSESSMENT


@pytest.mark.parametrize("expired_branch,fresh_score,fresh_level", [("vision", 20.0, "Low"), ("telemetry", 80.0, "High")])
def test_it_expiry_reason_an_expired_branch_next_to_a_fresh_one_scores_from_the_fresh_one_alone(
        api, fake_clock, monkeypatch, expired_branch, fresh_score, fresh_level):
    """Expired vision (0.8) next to fresh telemetry (0.2) is DEGRADED and scores 20.0 - exactly
    what telemetry alone scores - not the 50.0 of both branches, and not a down-weighted blend
    (the old 0.45 tier gave 37.4). The mirror case scores 80.0."""
    client, _ = api
    fake_clock.set(0)
    stamps = {"vision": at(0), "telemetry": at(0), expired_branch: _ago(30)}
    record = _infer(client, _live_session(client, monkeypatch, f"reason-degraded-{expired_branch}"),
                    _request("mixed", vision_at=stamps["vision"], telemetry_at=stamps["telemetry"]))
    fresh_branch = "telemetry" if expired_branch == "vision" else "vision"
    # The same evidence with the expired branch simply absent: the control the score must equal.
    alone_stamp = {"vision_at": at(0)} if fresh_branch == "vision" else {"telemetry_at": at(0)}
    control = _infer(client, _live_session(client, monkeypatch, f"reason-control-{expired_branch}"),
                     _request("alone", **alone_stamp))

    assert record["modality_freshness"][expired_branch] == "missing"
    assert record["modality_freshness"][fresh_branch] == "fresh"
    assert record["provenance"][f"{expired_branch}_expired"] is True
    assert record["provenance"][f"{expired_branch}_age_s"] == 30.0
    assert record["provenance"][f"{fresh_branch}_expired"] is False
    assert record["SystemHealth"] == "DEGRADED"
    assert record["assessment_available"] is True
    assert record["DominantEvidence"] == "Partial evidence"
    assert record["RiskScore"] == fresh_score and record["RiskLevel"] == fresh_level
    assert record["RiskScore"] == control["RiskScore"]
    # The record's own probability for the expired branch is the missing-branch 0.0; the model
    # output is not lost - the provenance keeps it.
    probability = "P_distraction" if expired_branch == "vision" else "P_telemetry_anomaly"
    raw = "P_distraction_raw" if expired_branch == "vision" else "P_telemetry_raw"
    assert record[probability] == 0.0
    assert record["provenance"][raw] == (0.8 if expired_branch == "vision" else 0.2)


def test_it_expiry_reason_two_fresh_branches_are_the_unexpired_control(api, fake_clock, monkeypatch):
    client, _ = api
    fake_clock.set(0)
    record = _infer(client, _live_session(client, monkeypatch, "reason-control-both"),
                    _request("both", vision_at=at(0), telemetry_at=_ago(2)))
    assert record["modality_freshness"] == {"vision": "fresh", "telemetry": "fresh"}
    assert record["RiskScore"] == 50.0 and record["SystemHealth"] == "FULL"
    p = record["provenance"]
    assert (p["vision_expired"], p["vision_age_s"], p["telemetry_expired"], p["telemetry_age_s"]) == (
        False, 0.0, False, 2.0)


# ------------------------------------------------------------- IT-EXPIRY-SENSITIVITY
# For each tolerance, the ages (in seconds) that are EXPIRED. Every other age in AGES is fresh.
# Written out, not computed: 2.0 / 3.0 / 5.0 are the exact boundaries and are FRESH (strict >).
AGES = [1.9, 2.0, 2.1, 2.9, 3.0, 3.1, 4.9, 5.0, 5.1]
EXPIRED_AT = {
    2: {2.1, 2.9, 3.0, 3.1, 4.9, 5.0, 5.1},  # fresh: 1.9 and the boundary 2.0 itself
    3: {3.1, 4.9, 5.0, 5.1},                 # fresh: up to and including the boundary 3.0
    5: {5.1},                                # fresh: up to and including the boundary 5.0
}


@pytest.mark.parametrize("branch", ["vision", "telemetry"])
@pytest.mark.parametrize("age", AGES)
@pytest.mark.parametrize("tolerance", [2, 3, 5])
def test_it_expiry_sensitivity_the_tolerance_is_per_session_and_the_comparison_is_strict(
        api, fake_clock, monkeypatch, tolerance, age, branch):
    """Session tolerance 2 / 3 / 5 s against evidence aged 1.9 ... 5.1 s: expired iff the age is
    strictly greater than the session's tolerance. One branch carries the age, the other is a
    current control, so a verdict is attributable to the branch under test."""
    expired = age in EXPIRED_AT[tolerance]
    client, _ = api
    sid = _live_session(client, monkeypatch, f"sens-{tolerance}-{age}-{branch}", tolerance=tolerance)
    fake_clock.set(0)
    stamps = {"vision": at(0), "telemetry": at(0), branch: _ago(age)}
    record = _infer(client, sid, _request("sens", vision_at=stamps["vision"], telemetry_at=stamps["telemetry"]))
    control = "telemetry" if branch == "vision" else "vision"

    assert record["provenance"]["fusion_config"]["freshness_tolerance_s"] == tolerance
    assert record["modality_freshness"][branch] == ("missing" if expired else "fresh")
    assert record["provenance"][f"{branch}_expired"] is expired
    assert record["provenance"][f"{branch}_age_s"] == age
    assert record["modality_freshness"][control] == "fresh"
    assert record["provenance"][f"{control}_expired"] is False
    assert record["SystemHealth"] == ("DEGRADED" if expired else "FULL")
    assert record["assessment_available"] is True


def test_it_expiry_sensitivity_the_default_tolerance_is_3_seconds(api, fake_clock, monkeypatch):
    client, _ = api
    sid = _live_session(client, monkeypatch, "sens-default")  # no config: the default applies
    fake_clock.set(0)
    fresh = _infer(client, sid, _request("a", vision_at=_ago(3.0), telemetry_at=at(0)))
    fake_clock.set(1000)
    over = _infer(client, sid, _request("b", vision_at=at(1000) - timedelta(seconds=3.1), telemetry_at=at(1000)))
    assert fresh["provenance"]["fusion_config"]["freshness_tolerance_s"] == 3
    assert fresh["modality_freshness"]["vision"] == "fresh"
    assert over["modality_freshness"]["vision"] == "missing" and over["provenance"]["vision_expired"] is True


@pytest.mark.parametrize("tolerance,status", [(0, 422), (-1, 422), (30.001, 422), (31, 422),
                                              (0.001, 201), (3, 201), (30, 201)])
def test_it_expiry_sensitivity_the_tolerance_is_configurable_within_0_exclusive_to_30(api, tolerance, status):
    """(0, 30]: zero would expire every frame the instant it arrived, and 30 s is the ceiling."""
    client, _ = api
    session_id = "range-" + str(tolerance).replace(".", "p").replace("-", "m")
    response = client.post("/api/sessions", json={"session_id": session_id,
                                                  "config": {"freshness_tolerance_s": tolerance}})
    assert response.status_code == status, response.text


# ----------------------------------------------------------------- IT-EXPIRY-NO-STALE
INFER_AGES = [(0, False), (1, False), (2.999, False), (3.0, False), (3.001, True), (4, True), (60, True),
              (3600, True), (2592000, True)]  # (age in seconds, expired?)


@pytest.mark.parametrize("age,expired", INFER_AGES)
def test_it_expiry_no_stale_infer_never_produces_stale(api, fake_clock, monkeypatch, age, expired):
    """Through POST /infer, then through every read path. Whatever the age, a branch is 'fresh'
    or 'missing' - and when it is 'missing' for age, the provenance says so."""
    client, _ = api
    sid = _live_session(client, monkeypatch, f"nostale-infer-{age}")
    fake_clock.set(0)
    record = _infer(client, sid, _request("a", vision_at=_ago(age), telemetry_at=_ago(age)))
    assert record["modality_freshness"] == {"vision": "missing" if expired else "fresh",
                                            "telemetry": "missing" if expired else "fresh"}
    assert (record["provenance"]["vision_expired"], record["provenance"]["telemetry_expired"]) == (expired, expired)
    stored = client.get(f"/api/sessions/{sid}/windows").json()
    latest = client.get(f"/api/sessions/{sid}/risk/latest").json()
    exported = client.get(f"/api/sessions/{sid}/export").json()["records"]
    for seen in (record, *stored, latest, *exported):
        assert "stale" not in seen["modality_freshness"].values()
        assert set(seen["modality_freshness"].values()) <= {"fresh", "missing"}


# (vision declared, telemetry declared, age of the window's timestamp in s | None,
#  vision, telemetry, vision_expired, telemetry_expired, vision_age_s, telemetry_age_s)
WINDOW_ROWS = [
    ("fresh", "fresh", None, "fresh", "fresh", False, False, None, None),
    ("fresh", "fresh", 0, "fresh", "fresh", False, False, 0.0, 0.0),
    ("fresh", "fresh", 2.999, "fresh", "fresh", False, False, 2.999, 2.999),
    ("fresh", "fresh", 3.0, "fresh", "fresh", False, False, 3.0, 3.0),
    ("fresh", "fresh", 3.001, "missing", "missing", True, True, 3.001, 3.001),
    ("fresh", "fresh", 3600, "missing", "missing", True, True, 3600.0, 3600.0),
    # A branch DECLARED stale by the sender is expired whatever its timestamp says.
    ("stale", "fresh", None, "missing", "fresh", True, False, None, None),
    ("fresh", "stale", None, "fresh", "missing", False, True, None, None),
    ("stale", "stale", None, "missing", "missing", True, True, None, None),
    ("stale", "fresh", 0, "missing", "fresh", True, False, 0.0, 0.0),
    ("stale", "stale", 60, "missing", "missing", True, True, 60.0, 60.0),
    # A branch declared missing was never received: not expired, and it has no age.
    ("missing", "fresh", 3600, "missing", "missing", False, True, None, 3600.0),
    ("fresh", "missing", 3600, "missing", "missing", True, False, 3600.0, None),
    ("missing", "missing", None, "missing", "missing", False, False, None, None),
    ("missing", "stale", None, "missing", "missing", False, True, None, None),
    ("stale", "missing", 3600, "missing", "missing", True, False, 3600.0, None),
]


@pytest.mark.parametrize("row", WINDOW_ROWS, ids=[f"{r[0]}-{r[1]}-{r[2]}" for r in WINDOW_ROWS])
def test_it_expiry_no_stale_windows_never_produces_stale(api, fake_clock, row):
    """Through POST /windows (the prepared / replay path), where the SENDER declares a status.
    'stale' is accepted as input - old clients send it - but never comes out."""
    declared_v, declared_t, age, vision, telemetry, v_expired, t_expired, v_age, t_age = row
    client, sid = api
    fake_clock.set(0)
    body = {"P_distraction": 0.8, "P_telemetry_anomaly": 0.2,
            "vision_status": declared_v, "telemetry_status": declared_t}
    if age is not None:
        body["timestamp"] = _ago(age).isoformat()
    response = client.post(f"/api/sessions/{sid}/windows", json=body)
    assert response.status_code == 201, response.text
    record = response.json()
    assert record["modality_freshness"] == {"vision": vision, "telemetry": telemetry}
    p = record["provenance"]
    assert (p["vision_expired"], p["telemetry_expired"], p["vision_age_s"], p["telemetry_age_s"]) == (
        v_expired, t_expired, v_age, t_age)
    stored = client.get(f"/api/sessions/{sid}/windows").json()
    assert [r["modality_freshness"] for r in stored] == [record["modality_freshness"]]
    assert "stale" not in stored[0]["modality_freshness"].values()


# ------------------------------------------------- the provenance fields themselves
def _run(*, provenance=None, vision="fresh", telemetry="fresh", window_timestamp=None, **config):
    window = WindowInput(P_distraction=0.8, P_telemetry_anomaly=0.2, vision_status=vision,
                         telemetry_status=telemetry, timestamp=window_timestamp)
    return run_inference("s", 1, window, state={}, config=RuntimeConfig(**config), provenance=provenance, now=at(0))


def test_the_four_fields_are_always_written_for_both_branches():
    """Default provenance (the replay path), a provider's provenance, and a window with no
    inputs at all: the keys exist every time, so a reader never has to guess whether a missing
    key means 'false' or 'not recorded'."""
    for record in (_run(), _run(provenance={"provider": "x"}),
                   _run(vision="missing", telemetry="missing")):
        assert {"vision_expired", "vision_age_s", "telemetry_expired", "telemetry_age_s"} <= set(record.provenance)
        assert record.provenance["vision_expired"] is False and record.provenance["telemetry_expired"] is False


def test_the_verdict_overwrites_whatever_the_provider_put_under_those_names():
    """The four fields are run_inference's verdict. A provider that happened to emit the same
    keys must not be able to claim 'not expired' for evidence the pipeline expired."""
    record = _run(provenance={"captured_at": _ago(10).isoformat(), "vision_expired": False, "vision_age_s": 0.0})
    assert (record.provenance["vision_expired"], record.provenance["vision_age_s"]) == (True, 10.0)


def test_age_is_rounded_half_up_to_three_decimals():
    """2.0005 s -> 2.001. Half UP on the decimal digits: banker's rounding (and a naive round()
    of the binary value) would both give 2.0."""
    assert freshness("fresh", _ago(2.0005).isoformat(), at(0), 3).age_s == 2.001
    assert freshness("fresh", _ago(2.0004).isoformat(), at(0), 3).age_s == 2.0
    assert freshness("fresh", _ago(1.2345).isoformat(), at(0), 3).age_s == 1.235


def test_age_is_never_negative_and_a_stamp_from_a_fast_clock_is_not_expired():
    """Clock skew up to 5 s ahead is accepted by the schema; the age is then 0, not -4."""
    verdict = freshness("fresh", (at(0) + timedelta(seconds=4)).isoformat(), at(0), 3)
    assert verdict == ("fresh", False, 0.0)


def test_age_is_null_without_a_timestamp_and_fresh_stays_fresh():
    assert freshness("fresh", None, at(0), 3) == ("fresh", False, None)
    assert freshness("fresh", "", at(0), 3) == ("fresh", False, None)


def test_a_declared_stale_branch_is_expired_with_or_without_a_timestamp():
    assert freshness("stale", None, at(0), 3) == ("missing", True, None)
    assert freshness("stale", at(0).isoformat(), at(0), 3) == ("missing", True, 0.0)
    assert freshness("stale", _ago(5).isoformat(), at(0), 3) == ("missing", True, 5.0)


def test_the_expiry_decision_uses_the_exact_age_not_the_rounded_one():
    """3.0004 s is over the line: expired, although the age it reports rounds to 3.0. (A
    comparison made on the rounded value would call it fresh.)"""
    assert freshness("fresh", _ago(3.0004).isoformat(), at(0), 3) == ("missing", True, 3.0)
    assert freshness("fresh", _ago(3.0).isoformat(), at(0), 3) == ("fresh", False, 3.0)


def test_a_fully_expired_window_keeps_the_raw_model_output_in_the_provenance():
    record = _run(provenance={"captured_at": _ago(60).isoformat(), "telemetry_timestamp": _ago(60).isoformat()})
    assert record.assessment_available is False
    assert (record.P_distraction, record.P_telemetry_anomaly) == (0.0, 0.0)
    assert (record.provenance["P_distraction_raw"], record.provenance["P_telemetry_raw"]) == (0.8, 0.2)


# ----------------------------------------------------------- historical records
HISTORIC_PROVENANCE = {"provider": "MockAIProvider", "vision_source": "prepared_replay",
                       "telemetry_source": "prepared_replay"}


def _historic_payload(session_id):
    """A record exactly as the pre-ruling-A pipeline stored a stale-vision window: the 0.45
    tier (score 65.2, DEGRADED) and a provenance with no expiry fields. Literals only."""
    return {
        "session_id": session_id, "window_id": 1, "timestamp": "2026-10-01T09:00:00+00:00",
        "assessment_available": True, "P_distraction": 0.1, "P_telemetry_anomaly": 0.9,
        "RiskScore": 65.2, "RiskLevel": "High", "DominantEvidence": "Partial evidence",
        "AlertSeverity": "CAUTION", "SystemHealth": "DEGRADED",
        "operation_mode": "PREPARED_SESSION_RUNTIME",
        "modality_freshness": {"vision": "stale", "telemetry": "fresh"},
        "latency_ms": 12, "visual_top_classes": [], "telemetry_behavior_classes": [],
        "telemetry_feature_contributions": [], "telemetry_features": None,
        "explanation": "Output is based on partial evidence; one modality is stale or missing.",
        "flagged": False, "provenance": dict(HISTORIC_PROVENANCE),
    }


def test_a_stored_stale_record_is_still_read_and_exported_without_error(api, api_factory, fake_clock):
    """The 0.45 tier outlives the runtime for exactly this reason: a record written before the
    ruling, with ``stale`` in its modality_freshness and none of the expiry fields, must still
    load through every read path - list, latest, flag, JSON export, CSV export - unchanged and
    without a 500. A new window written next to it carries no ``stale``."""
    client, sid = api
    payload = _historic_payload(sid)
    with api_factory() as db:
        db.add(models.InferenceRecord(
            session_id=sid, window_id=1, timestamp=payload["timestamp"], p_distraction=0.1,
            p_telemetry_anomaly=0.9, risk_score=65.2, risk_level="High", dominant_evidence="Partial evidence",
            alert_severity="CAUTION", system_health="DEGRADED", assessment_available=True, latency_ms=12,
            flagged=False, payload=payload))
        db.get(models.SessionMeta, sid).next_window_id = 1
        db.commit()

    listed = client.get(f"/api/sessions/{sid}/windows")
    assert listed.status_code == 200, listed.text
    assert listed.json() == [payload]  # returned as stored: history is not rewritten
    assert listed.json()[0]["modality_freshness"] == {"vision": "stale", "telemetry": "fresh"}
    assert "vision_expired" not in listed.json()[0]["provenance"]

    latest = client.get(f"/api/sessions/{sid}/risk/latest")
    assert latest.status_code == 200 and latest.json() == payload

    exported = client.get(f"/api/sessions/{sid}/export")
    assert exported.status_code == 200
    assert exported.json()["records"] == [payload]
    as_csv = client.get(f"/api/sessions/{sid}/export?format=csv")
    assert as_csv.status_code == 200
    (csv_row,) = list(csv.DictReader(io.StringIO(as_csv.text)))
    assert json.loads(csv_row["modality_freshness"]) == {"vision": "stale", "telemetry": "fresh"}

    flagged = client.patch(f"/api/sessions/{sid}/windows/1/flag?flagged=true")
    assert flagged.status_code == 200 and flagged.json()["modality_freshness"]["vision"] == "stale"

    # The runtime keeps working next to it, and never writes the tier again.
    fake_clock.set(0)
    new = client.post(f"/api/sessions/{sid}/windows",
                      json={"P_distraction": 0.1, "P_telemetry_anomaly": 0.9, "vision_status": "stale"})
    assert new.status_code == 201, new.text
    assert new.json()["window_id"] == 2
    assert new.json()["modality_freshness"] == {"vision": "missing", "telemetry": "fresh"}
    assert new.json()["RiskScore"] == 90.0  # not the historic 65.2
    both = client.get(f"/api/sessions/{sid}/windows").json()
    assert [r["modality_freshness"]["vision"] for r in both] == ["stale", "missing"]
