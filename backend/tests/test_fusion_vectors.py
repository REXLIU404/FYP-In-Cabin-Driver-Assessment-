"""Cross-language fusion oracle: both Python ports against ``ai/fixtures/fusion_vectors.json``.

The TypeScript suite (``ai/src/fusionVectors.test.ts``) reads the SAME file. Every
expectation below comes from that JSON or from a literal written in this file -
nothing is imported from an implementation to build an expectation - so whichever
implementation drifts goes red on its own side.

Two ports are checked: the backend module (``app.fusion``) and the
language-agnostic reference (``ai/reference/risk_logic.py``). The reference has no
other importer or test, so without this it would drift silently.

Thresholds (30 / 60), the evidence gap (0.15) and the epsilon boundary values are
hard-coded literals from the contract, not imports.
"""
import importlib.util
import json
import sys
from pathlib import Path

import pytest

from app import fusion

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE = REPO_ROOT / "ai" / "fixtures" / "fusion_vectors.json"
REFERENCE = REPO_ROOT / "ai" / "reference" / "risk_logic.py"

THRESHOLD_LOW = 30
THRESHOLD_HIGH = 60
EVIDENCE_GAP = 0.15


def _load_reference():
    # Registered in sys.modules first: @dataclass resolves string annotations
    # (``from __future__ import annotations``) through sys.modules[cls.__module__].
    spec = importlib.util.spec_from_file_location("risk_logic_reference", REFERENCE)
    module = importlib.util.module_from_spec(spec)
    sys.modules["risk_logic_reference"] = module
    spec.loader.exec_module(module)
    return module


reference = _load_reference()
PORTS = {"backend_fusion": fusion, "reference_risk_logic": reference}

VECTORS = json.loads(FIXTURE.read_text(encoding="utf-8"))
VECTOR_IDS = [row["id"] for row in VECTORS]


# ---------------------------------------------------------------- fixture shape
class TestFixtureShape:
    def test_is_an_array_of_25_rows_with_unique_ids(self):
        assert isinstance(VECTORS, list)
        assert len(VECTORS) == 25
        assert len(set(VECTOR_IDS)) == 25

    def test_every_row_carries_the_full_field_set(self):
        for row in VECTORS:
            # ``legacy`` is the one optional key (see the next test); every other key is required.
            assert sorted(key for key in row if key != "legacy") == sorted(
                ["expect", "id", "pd", "pt", "telemetry", "vision", "wt", "wv"])
            assert sorted(row["expect"]) == sorted(["available", "dominant", "health", "level", "score"])

    def test_exactly_the_rows_that_use_the_stale_tier_are_marked_legacy(self):
        """Ruling A (D13): the runtime no longer produces ``stale``. The 0.45 tier survives only
        for historical records, so every row that exercises it says so - and no other row does.
        The marker is a reason string; the rows' expectations are untouched."""
        uses_stale = {row["id"] for row in VECTORS if "stale" in (row["vision"], row["telemetry"])}
        assert uses_stale == {"F-S1", "F-S2", "F-S3", "F-M3", "F-M4"}
        assert {row["id"] for row in VECTORS if "legacy" in row} == uses_stale
        assert all(isinstance(row["legacy"], str) and row["legacy"] for row in VECTORS if "legacy" in row)

    def test_unavailable_rows_null_score_level_dominant_together_and_only_then(self):
        for row in VECTORS:
            e = row["expect"]
            assert e["available"] == (e["score"] is not None)
            assert e["available"] == (e["level"] is not None)
            assert e["available"] == (e["dominant"] is not None)
            assert e["available"] == (e["health"] != "UNAVAILABLE")


# ------------------------------------------------------- vectors, both ports
@pytest.mark.parametrize("port_name", PORTS)
@pytest.mark.parametrize("row", VECTORS, ids=VECTOR_IDS)
class TestFusionVector:
    def test_compute_risk_score(self, port_name, row):
        port = PORTS[port_name]
        score = port.compute_risk_score(row["pd"], row["pt"], row["wv"], row["wt"], row["vision"], row["telemetry"])
        assert score == row["expect"]["score"]

    def test_map_risk_level(self, port_name, row):
        port = PORTS[port_name]
        score = port.compute_risk_score(row["pd"], row["pt"], row["wv"], row["wt"], row["vision"], row["telemetry"])
        assert port.map_risk_level(score, THRESHOLD_LOW, THRESHOLD_HIGH) == row["expect"]["level"]

    def test_map_system_health(self, port_name, row):
        port = PORTS[port_name]
        assert port.map_system_health(row["vision"], row["telemetry"], row["wv"], row["wt"]) == row["expect"]["health"]

    def test_determine_dominant_evidence(self, port_name, row):
        port = PORTS[port_name]
        score = port.compute_risk_score(row["pd"], row["pt"], row["wv"], row["wt"], row["vision"], row["telemetry"])
        health = port.map_system_health(row["vision"], row["telemetry"], row["wv"], row["wt"])
        dominant = port.determine_dominant_evidence(
            row["pd"], row["pt"], score, health, low=THRESHOLD_LOW, gap=EVIDENCE_GAP
        )
        assert dominant == row["expect"]["dominant"]


@pytest.mark.parametrize("row", VECTORS, ids=VECTOR_IDS)
class TestReferenceBuildRiskUpdate:
    def test_agrees_with_the_fixture_end_to_end(self, row):
        record = reference.build_risk_update(
            row["pd"], row["pt"], w_v=row["wv"], w_t=row["wt"], v=row["vision"], t=row["telemetry"]
        )
        e = row["expect"]
        assert record.assessment_available is e["available"]
        assert record.RiskScore == e["score"]
        assert record.RiskLevel == e["level"]
        assert record.DominantEvidence == e["dominant"]
        assert record.SystemHealth == e["health"]


# ------------------------------------------------------------ rounding order
@pytest.mark.parametrize("port_name", PORTS)
def test_rounding_precedes_level_mapping_f_t5(port_name):
    """The exact fused value for F-T5 is 29.951: below 30 before rounding, 30 after.
    The level must be mapped from the ROUNDED score, so it lands in Medium."""
    port = PORTS[port_name]
    row = next(r for r in VECTORS if r["id"] == "F-T5")
    assert (0.5 * 0.29951 + 0.5 * 0.29951) / 1 * 100 < THRESHOLD_LOW  # the row has teeth
    score = port.compute_risk_score(row["pd"], row["pt"], row["wv"], row["wt"], row["vision"], row["telemetry"])
    assert score == 30
    assert port.map_risk_level(score, THRESHOLD_LOW, THRESHOLD_HIGH) == "Medium"


# ------------------------------------------------------------- rounding mode
# F-R1..F-R4 are exact decimal ties. Rounding is HALF UP on the shortest decimal
# representation, in every port: Python's own round() is banker's rounding
# (84.25 -> 84.2) and the TypeScript toFixed rounds the exact binary value
# (29.95 -> 29.9), so before this contract the ports disagreed on about 4% of
# inputs. The raw scores and the old results are hard-coded below so the rows
# have teeth: each one is a value the old Python round() got wrong.
TIE_ROWS = {
    # id: (raw score as the pipeline computes it, what Python round() gave, expected)
    "F-R1": (84.25, 84.2, 84.3),
    "F-R2": (29.95, 29.9, 30),
    "F-R3": (29.95, 29.9, 30),
    "F-R4": (22.25, 22.2, 22.3),
}


@pytest.mark.parametrize("port_name", PORTS)
@pytest.mark.parametrize("row_id", TIE_ROWS)
def test_tie_rows_round_half_up_and_not_bankers(port_name, row_id):
    port = PORTS[port_name]
    row = next(r for r in VECTORS if r["id"] == row_id)
    raw, bankers, expected = TIE_ROWS[row_id]
    unrounded = (row["wv"] * row["pd"] + row["wt"] * row["pt"]) / (row["wv"] + row["wt"]) * 100
    assert unrounded == raw  # the pipeline really produces this exact tie
    assert round(unrounded, 1) == bankers != expected  # the old behaviour was wrong here
    score = port.compute_risk_score(row["pd"], row["pt"], row["wv"], row["wt"], row["vision"], row["telemetry"])
    assert score == expected == row["expect"]["score"]


@pytest.mark.parametrize("port_name", PORTS)
def test_a_tie_can_change_the_level_f_r2(port_name):
    """29.95 is Low under banker's / toFixed (29.9) and Medium under half up (30)."""
    port = PORTS[port_name]
    assert port.compute_risk_score(0.2995, 0.2995, 0.5, 0.5, "fresh", "fresh") == 30
    assert port.map_risk_level(30, THRESHOLD_LOW, THRESHOLD_HIGH) == "Medium"
    assert port.map_risk_level(29.9, THRESHOLD_LOW, THRESHOLD_HIGH) == "Low"


@pytest.mark.parametrize("port_name", PORTS)
@pytest.mark.parametrize("value,places,expected", [
    (84.25, 1, 84.3), (0.125, 2, 0.13), (2.675, 2, 2.68), (1.005, 2, 1.01),
    (0.4125, 3, 0.413), (0.4124999, 3, 0.412), (0.0005, 3, 0.001), (0.0004999, 3, 0.0),
    (1e-7, 3, 0.0), (5e-7, 6, 0.000001), (0.0, 1, 0.0), (100.0, 1, 100.0),
    (27.849999999999998, 1, 27.8),  # 17 digits: an exponent-shift implementation hits 27.85
])
def test_round_half_up_hard_cases(port_name, value, places, expected):
    assert PORTS[port_name].round_half_up(value, places) == expected


# ------------------------------------------------------ epsilon boundary cases
# The shared fixture does NOT cover these: an implementation that tested the
# denominator with `== 0` instead of `<= FUSION_EPSILON` passes all 25 rows.
# Every case uses weights that sum to 1 (inside RuntimeConfig's 1e-6 tolerance);
# the small denominator comes from the missing branch contributing 0. The
# boundary literals are hard-coded on purpose - FUSION_EPSILON is never imported.
EPSILON_CASES = [
    # id, w_v, w_t, vision, telemetry, denominator, available
    ("denominator-1e-10-vision", 1e-10, 1 - 1e-10, "fresh", "missing", 1e-10, False),
    ("denominator-1e-9-vision-exactly-epsilon", 1e-9, 1 - 1e-9, "fresh", "missing", 1e-9, False),
    ("denominator-1.1e-9-vision", 1.1e-9, 1 - 1.1e-9, "fresh", "missing", 1.1e-9, True),
    ("denominator-1e-10-telemetry", 1 - 1e-10, 1e-10, "missing", "fresh", 1e-10, False),
    ("denominator-1e-9-telemetry-exactly-epsilon", 1 - 1e-9, 1e-9, "missing", "fresh", 1e-9, False),
    ("denominator-1.1e-9-telemetry", 1 - 1.1e-9, 1.1e-9, "missing", "fresh", 1.1e-9, True),
    # stale weight 0.45 is part of the denominator: 2.2e-9 * 0.45 ~ 9.9e-10 < 1e-9
    ("stale-below-epsilon", 2.2e-9, 1 - 2.2e-9, "stale", "missing", 9.9e-10, False),
    ("stale-above-epsilon", 2.3e-9, 1 - 2.3e-9, "stale", "missing", 1.035e-9, True),
]


@pytest.mark.parametrize("port_name", PORTS)
@pytest.mark.parametrize(
    "case_id,wv,wt,vision,telemetry,denominator,available",
    EPSILON_CASES,
    ids=[c[0] for c in EPSILON_CASES],
)
class TestEpsilonBoundary:
    def test_weights_are_a_legal_runtime_config(self, port_name, case_id, wv, wt, vision, telemetry, denominator, available):
        assert abs((wv + wt) - 1) <= 1e-6

    def test_effective_denominator_is_the_expected_magnitude(self, port_name, case_id, wv, wt, vision, telemetry, denominator, available):
        port = PORTS[port_name]
        _, _, total = port.effective_weights(wv, wt, vision, telemetry)
        assert total == pytest.approx(denominator, rel=1e-9, abs=0)

    def test_score_is_none_iff_denominator_is_not_above_epsilon(self, port_name, case_id, wv, wt, vision, telemetry, denominator, available):
        port = PORTS[port_name]
        score = port.compute_risk_score(0.1, 0.9, wv, wt, vision, telemetry)
        assert (score is not None) is available

    def test_health_agrees_with_the_score(self, port_name, case_id, wv, wt, vision, telemetry, denominator, available):
        port = PORTS[port_name]
        health = port.map_system_health(vision, telemetry, wv, wt)
        assert (health != "UNAVAILABLE") is available
        if available:
            assert health == "DEGRADED"  # one branch is missing / stale

    def test_level_and_dominant_follow(self, port_name, case_id, wv, wt, vision, telemetry, denominator, available):
        port = PORTS[port_name]
        score = port.compute_risk_score(0.1, 0.9, wv, wt, vision, telemetry)
        health = port.map_system_health(vision, telemetry, wv, wt)
        level = port.map_risk_level(score, THRESHOLD_LOW, THRESHOLD_HIGH)
        dominant = port.determine_dominant_evidence(0.1, 0.9, score, health, low=THRESHOLD_LOW, gap=EVIDENCE_GAP)
        if available:
            assert level is not None
            assert dominant == "Partial evidence"
        else:
            assert level is None
            assert dominant is None


# ------------------------------------------------- None handling (the traps)
@pytest.mark.parametrize("port_name", PORTS)
class TestNoneHandling:
    def test_map_risk_level_none_does_not_raise_and_returns_none(self, port_name):
        # Python raises TypeError on `None < 30`; the None check must come first.
        assert PORTS[port_name].map_risk_level(None, THRESHOLD_LOW, THRESHOLD_HIGH) is None

    def test_dominant_is_none_on_null_score_even_when_health_is_not_full(self, port_name):
        # The old `system_health != "FULL" -> Partial evidence` branch used to
        # shield the None comparison and silently invent "Partial evidence".
        port = PORTS[port_name]
        assert port.determine_dominant_evidence(0.1, 0.9, None, "DEGRADED", low=THRESHOLD_LOW, gap=EVIDENCE_GAP) is None
        assert port.determine_dominant_evidence(0.1, 0.9, None, "FULL", low=THRESHOLD_LOW, gap=EVIDENCE_GAP) is None

    def test_dominant_is_none_on_unavailable_health_even_with_a_score(self, port_name):
        port = PORTS[port_name]
        assert port.determine_dominant_evidence(0.1, 0.9, 50.0, "UNAVAILABLE", low=THRESHOLD_LOW, gap=EVIDENCE_GAP) is None

    def test_weight_defaults_are_half_half(self, port_name):
        # map_system_health gained weight parameters; omitting them keeps 0.5/0.5.
        port = PORTS[port_name]
        assert port.map_system_health("missing", "missing") == "UNAVAILABLE"
        assert port.map_system_health("fresh", "missing") == "DEGRADED"
        assert port.map_system_health("fresh", "fresh") == "FULL"

    def test_unknown_freshness_status_is_treated_as_fresh(self, port_name):
        # Same as the TypeScript freshnessWeight: only missing/stale are special.
        assert PORTS[port_name].effective_weights(0.5, 0.5, "unexpected", "fresh") == (0.5, 0.5, 1.0)


# ---------------------------------------------------------- backend-only pieces
class TestBackendExplanation:
    def test_unavailable_names_no_level_and_never_claims_low_risk(self):
        for row in VECTORS:
            if row["expect"]["available"]:
                continue
            text = fusion.build_explanation(
                None, None, row["vision"], row["telemetry"], row["wv"], row["wt"]
            )
            assert text.startswith("No risk assessment is available")
            lowered = text.lower()
            for forbidden in ("low-risk", "below", "low risk", "medium", "high", "caution", "normal"):
                assert forbidden not in lowered, (row["id"], forbidden, text)

    def test_both_missing_names_both_branches(self):
        text = fusion.build_explanation(None, None, "missing", "missing", 0.5, 0.5)
        assert "both the vision and telemetry inputs are missing" in text

    def test_zero_weight_branch_is_named_f_z1_and_f_z2(self):
        f_z1 = next(r for r in VECTORS if r["id"] == "F-Z1")
        f_z2 = next(r for r in VECTORS if r["id"] == "F-Z2")
        t1 = fusion.build_explanation(None, None, f_z1["vision"], f_z1["telemetry"], f_z1["wv"], f_z1["wt"])
        t2 = fusion.build_explanation(None, None, f_z2["vision"], f_z2["telemetry"], f_z2["wv"], f_z2["wt"])
        assert "the vision input is missing and the telemetry branch has zero fusion weight" in t1
        assert "the vision branch has zero fusion weight and the telemetry input is missing" in t2

    def test_legacy_two_argument_call_still_works_when_unavailable(self):
        # inference.py now passes the statuses and weights; the two-argument form must keep working.
        text = fusion.build_explanation(None, None)
        assert text.startswith("No risk assessment is available")
        assert "low-risk" not in text.lower()

    def test_a_none_level_with_a_dominant_is_still_unavailable_text(self):
        text = fusion.build_explanation("Partial evidence", None)
        assert text.startswith("No risk assessment is available")

    def test_unrecognised_dominant_is_not_reported_as_low_risk(self):
        text = fusion.build_explanation("Something else", "Low")
        assert "low-risk" not in text.lower()
        assert "not recognised" in text

    def test_available_dominants_keep_their_wording(self):
        assert fusion.build_explanation("Vision-dominant", "High") == "Vision evidence is driving the high risk output."
        assert fusion.build_explanation("Telemetry-dominant", "Medium") == "Telemetry non-safe behaviour is driving the medium risk output."
        assert fusion.build_explanation("Combined evidence", "Medium") == "Vision and telemetry evidence both contribute to the medium risk output."
        assert fusion.build_explanation("Partial evidence", "Low") == "Output is based on partial evidence; one modality is stale or missing."
        assert fusion.build_explanation("Low observed risk", "Low") == "The current window is below the low-risk threshold."


class TestMapAlertSeverityIsDeadCode:
    def test_none_guard(self):
        assert fusion.map_alert_severity(None) is None

    def test_mapping_is_unchanged(self):
        assert fusion.map_alert_severity("Low") == "NORMAL"
        assert fusion.map_alert_severity("Medium") == "CAUTION"
        assert fusion.map_alert_severity("High") == "HIGH_ALERT"

    def test_nothing_in_the_backend_calls_it(self):
        """It maps High straight to HIGH_ALERT with no 2 s sustain, contradicting
        the FSM in inference.py. Wiring it up would silently delete the sustain gate."""
        app_dir = REPO_ROOT / "backend" / "app"
        callers = [
            path.name
            for path in app_dir.rglob("*.py")
            if path.name != "fusion.py" and "map_alert_severity" in path.read_text(encoding="utf-8")
        ]
        assert callers == []
