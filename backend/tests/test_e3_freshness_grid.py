"""E3 freshness grid (evaluation matrix, addendum 2026-10-22): every combination of
vision x telemetry in {fresh, missing, expired}, through /infer, after ruling A (D13).

The addendum fixes what the grid must show: an EXPIRED branch scores exactly like a MISSING one
(weight 0, never the legacy 0.45 tier), and only the provenance says which it was
({branch}_expired / {branch}_age_s). Both branches without usable evidence -> UNAVAILABLE with the
four risk fields null; one usable branch -> scored from it alone.

Provider stubbed (vision 0.8, telemetry 0.2: 50.0 = both fused, 80.0 = vision alone, 20.0 =
telemetry alone), fake clock at 0, default weights 0.5 / 0.5 and tolerance 3 s. fresh = 0.5 s old,
expired = 10 s old, missing = not sent. Each combination is its own session, so each record is the
session's FIRST window: the alert FSM starts at NORMAL, Medium is CAUTION at once, High is CAUTION
until it has lasted 2 s (it never has here), Low stays NORMAL. Expectations are literals.
"""
import pytest

from test_evidence_expiry import NO_ASSESSMENT, _ago, _infer, _live_session, _request, _risk_fields
from test_temporal_contract import fake_clock  # noqa: F401

AGE = {"fresh": 0.5, "expired": 10.0, "missing": None}
STATES = ("fresh", "missing", "expired")

# (vision, telemetry) -> (RiskScore, RiskLevel, SystemHealth, DominantEvidence, AlertSeverity) at default
# weights; None = unavailable. (fresh, fresh): FULL, 50 >= 30 and |0.8 - 0.2| = 0.6 >= the 0.15 gap, vision
# higher -> Vision-dominant.
EXPECTED = {
    ("fresh", "fresh"): (50.0, "Medium", "FULL", "Vision-dominant", "CAUTION"),
    ("fresh", "missing"): (80.0, "High", "DEGRADED", "Partial evidence", "CAUTION"),
    ("fresh", "expired"): (80.0, "High", "DEGRADED", "Partial evidence", "CAUTION"),
    ("missing", "fresh"): (20.0, "Low", "DEGRADED", "Partial evidence", "NORMAL"),
    ("expired", "fresh"): (20.0, "Low", "DEGRADED", "Partial evidence", "NORMAL"),
    ("missing", "missing"): None,
    ("missing", "expired"): None,
    ("expired", "missing"): None,
    ("expired", "expired"): None,
}
GRID = [(v, t) for v in STATES for t in STATES]


def _record(client, monkeypatch, vision, telemetry):
    sid = _live_session(client, monkeypatch, f"e3-{vision}-{telemetry}")
    body = _request("r1",
                    vision_at=None if AGE[vision] is None else _ago(AGE[vision]),
                    telemetry_at=None if AGE[telemetry] is None else _ago(AGE[telemetry]))
    return _infer(client, sid, body)


@pytest.mark.parametrize("vision,telemetry", GRID, ids=[f"V-{v}_T-{t}" for v, t in GRID])
def test_e3_each_combination_scores_as_specified_and_keeps_its_reason(api, fake_clock, monkeypatch, vision, telemetry):
    client, _ = api
    fake_clock.set(0)
    record = _record(client, monkeypatch, vision, telemetry)
    expected = EXPECTED[(vision, telemetry)]
    usable = {"vision": vision == "fresh", "telemetry": telemetry == "fresh"}
    assert record["modality_freshness"] == {b: "fresh" if ok else "missing" for b, ok in usable.items()}
    if expected is None:
        assert record["assessment_available"] is False and record["SystemHealth"] == "UNAVAILABLE"
        assert _risk_fields(record) == NO_ASSESSMENT
    else:
        assert (record["RiskScore"], record["RiskLevel"], record["SystemHealth"], record["DominantEvidence"],
                record["AlertSeverity"]) == expected
        assert record["assessment_available"] is True
    provenance = record["provenance"]
    for branch, state in (("vision", vision), ("telemetry", telemetry)):
        assert (provenance[f"{branch}_expired"], provenance[f"{branch}_age_s"]) == (state == "expired", AGE[state]), branch
    assert "stale" not in str(record["modality_freshness"]) and record.get("SystemHealth") != "STALE"


@pytest.mark.parametrize("vision,telemetry", [c for c in GRID if "expired" in c], ids=lambda c: str(c))
def test_e3_an_expired_branch_scores_exactly_like_a_missing_one(api, fake_clock, monkeypatch, vision, telemetry):
    """Replace every 'expired' by 'missing': every assessment field compared below - the four risk
    fields, the alert, SystemHealth, availability, freshness and both probabilities - is equal; only
    the provenance reason differs."""
    client, _ = api
    fake_clock.set(0)
    with_expired = _record(client, monkeypatch, vision, telemetry)
    as_missing = _record(client, monkeypatch, *("missing" if s == "expired" else s for s in (vision, telemetry)))
    for key in ("RiskScore", "RiskLevel", "DominantEvidence", "AlertSeverity", "SystemHealth",
                "assessment_available", "modality_freshness", "P_distraction", "P_telemetry_anomaly"):
        assert with_expired[key] == as_missing[key], key
