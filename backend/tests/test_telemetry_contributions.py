"""TELEMETRY-CONTRIBUTIONS: what the Explanation card's "Feature Contribution" row shows in Live mode.

``telemetry_feature_contributions`` of a live record is a TreeSHAP local attribution (XGBoost
``pred_contribs=True``) on the SAFE-class score, sign flipped so that a POSITIVE value pushes toward
UNSAFE, in log-odds. It explains the number that is fused, ``P_telemetry_anomaly = 1 - P(Safe)``. It is
not causal and not a dataset-level feature importance. ``provenance`` says so for every window that
has them: ``telemetry_contribution_method`` and ``telemetry_contribution_baseline`` (= -(the Safe-class
bias)), so that ``sum(contributions) + baseline = -margin_Safe``.

Two halves.

* With the trained model (``requires_models``, the provider called directly): the 23 telemetry rows of
  the prepared replay against the FROZEN literals of ``fixtures/telemetry_pt_by_row.json`` (made by an
  independent script that calls ``pred_contribs`` itself), the additivity against a margin this file
  takes from its OWN booster with ``output_margin=True``, the sign of row 1 as literals, the contract,
  and the no-telemetry window.
* Without it (a stub provider through the real router, the real fusion and the real SQLite): the R10
  rule that a REPEAT is the observation it repeats (its contributions are the registered ones, not a new
  inference's), the registry written by a session that predates the contributions, and the rule for an
  expired and for a telemetry-less window - the same as ``telemetry_behavior_classes`` has.

Every expectation is a literal in this file or in the frozen fixture; no constant is imported from the
implementation to build one.
"""
import hashlib
import json
from pathlib import Path

import pytest

from app import models
from app.schemas import LiveInput, TelemetryFeatureContribution, TelemetryFeatures

from test_r10_observations import ProbStub, drive, img, state_of, tel  # noqa: F401  (drive is a fixture)
from test_temporal_contract import fake_clock  # noqa: F401  (a fixture)

MODEL_ROOT = Path(__file__).resolve().parents[2] / "ml/outputs"
# All three stable files, like every other ``requires_models`` here (test_model_gate.py checks it).
requires_models = pytest.mark.skipif(
    not all((MODEL_ROOT / name).exists() for name in ("vision/mobilenetv3_large_vision.onnx",
                                                      "vision/mobilenetv3_large_vision.pt",
                                                      "telemetry/xgb_telemetry.json")),
    reason="local trained artifacts not installed",
)
FIXTURE = Path(__file__).with_name("fixtures") / "telemetry_pt_by_row.json"
TELEMETRY_XGB_SHA256 = "9802cb06ca98f0c1befaf851fa7668cfec70e005cf8bb3884e49d7d45d7aec07"
FEATURES = ["speed_kmph", "accel_x", "accel_y", "brake_pressure", "steering_angle", "throttle",
            "lane_deviation", "headway_distance"]
METHOD = "xgboost_treeshap_neg_safe_margin"


def telemetry_input(features, request_id):
    return LiveInput(request_id=request_id, telemetry_features=TelemetryFeatures(**features),
                     telemetry_timestamp="2026-01-01T00:00:00Z", telemetry_source="prepared_replay")


def frozen_rows():
    """The fixture, after checking it belongs to THE frozen model; the rows that carry telemetry."""
    fixture = json.loads(FIXTURE.read_text())
    model = hashlib.sha256((MODEL_ROOT / "telemetry/xgb_telemetry.json").read_bytes()).hexdigest()
    assert fixture["telemetry_model_sha256"] == model == TELEMETRY_XGB_SHA256
    rows = [r for r in fixture["rows"] if r["telemetry_features"] is not None]
    assert len(rows) == 23
    return rows


# ====================================================================== the trained model
@requires_models
def test_the_contributions_equal_the_frozen_literals_on_all_23_telemetry_rows():
    from app.providers.trained import get_provider
    provider, problems = get_provider(), []
    for row in frozen_rows():
        window, provenance = provider.infer(telemetry_input(row["telemetry_features"], f"row-{row['row']}"))
        shown = [c.model_dump() for c in window.telemetry_feature_contributions]
        frozen = [{"feature": f, "contribution": v} for f, v in row["feature_contributions"].items()]
        if shown != frozen:  # exact: not a tolerance, the same float32 arithmetic
            problems.append(f"row {row['row']}: contributions {shown!r} != frozen {frozen!r}")
        if provenance["telemetry_contribution_baseline"] != row["contribution_baseline"]:
            problems.append(f"row {row['row']}: baseline {provenance['telemetry_contribution_baseline']!r} "
                            f"!= frozen {row['contribution_baseline']!r}")
    assert not problems, f"{len(problems)} problems, first {problems[:3]}"


@requires_models
def test_contributions_plus_baseline_equal_minus_the_safe_margin_on_every_row():
    """The margin is taken HERE, from this test's own booster with ``output_margin=True`` over the
    frozen model's trees (iterations 0..90; the file holds 121 rounds, so the range matters)."""
    import numpy as np
    import xgboost as xgb
    from app.providers.trained import get_provider

    booster = xgb.Booster()
    booster.load_model(MODEL_ROOT / "telemetry/xgb_telemetry.json")
    booster.set_param({"nthread": 1})
    assert booster.attr("best_iteration") == "90" and booster.num_boosted_rounds() == 121
    provider, problems = get_provider(), []
    for row in frozen_rows():
        features = row["telemetry_features"]
        matrix = xgb.DMatrix(np.array([[features[k] for k in FEATURES]], dtype=np.float32), feature_names=FEATURES)
        margin_safe = float(booster.predict(matrix, iteration_range=(0, 91), output_margin=True)[0][0])
        window, provenance = provider.infer(telemetry_input(features, f"row-{row['row']}"))
        total = sum(c.contribution for c in window.telemetry_feature_contributions) + provenance["telemetry_contribution_baseline"]
        if abs(total + margin_safe) >= 1e-4:  # float32 arithmetic
            problems.append(f"row {row['row']}: contributions + baseline = {total!r}, -margin_Safe = {-margin_safe!r}")
    assert not problems, f"{len(problems)} problems, first {problems[:3]}"


@requires_models
def test_the_sign_positive_pushes_toward_unsafe_row_1_as_literals():
    """Replay row 1 (0-based; window_id 2) has P_telemetry_anomaly 0.6768: the model calls it unsafe. XGBoost's
    own Safe-class attribution is headway_distance -4.764, brake_pressure +2.296, accel_y +0.197 - it pulls
    the Safe score DOWN with headway. The record shows them negated: headway_distance +4.764 (toward unsafe)."""
    from app.providers.trained import get_provider
    row = frozen_rows()[1]
    assert row["row"] == 1 and row["window_id"] == 2
    window, _ = get_provider().infer(telemetry_input(row["telemetry_features"], "row-1"))
    assert window.P_telemetry_anomaly == pytest.approx(0.6768, abs=5e-5)
    shown = {c.feature: c.contribution for c in window.telemetry_feature_contributions}
    assert shown["headway_distance"] == pytest.approx(4.764, abs=5e-4)
    assert shown["brake_pressure"] == pytest.approx(-2.296, abs=5e-4)
    assert shown["accel_y"] == pytest.approx(-0.197, abs=5e-4)
    by_size = sorted(shown, key=lambda name: abs(shown[name]), reverse=True)
    assert by_size[:3] == ["headway_distance", "brake_pressure", "accel_y"]


@requires_models
def test_the_contract_eight_features_in_the_models_order_and_the_two_provenance_keys():
    from app.providers.trained import get_provider
    row = frozen_rows()[0]
    window, provenance = get_provider().infer(telemetry_input(row["telemetry_features"], "contract"))
    contributions = window.telemetry_feature_contributions
    assert len(contributions) == 8
    assert [c.feature for c in contributions] == FEATURES  # the model's fixed order; the view sorts
    assert all(isinstance(c.contribution, float) for c in contributions)
    assert provenance["telemetry_contribution_method"] == METHOD
    assert isinstance(provenance["telemetry_contribution_baseline"], float)
    # The class breakdown it is the sibling of: present together.
    assert len(window.telemetry_behavior_classes) == 3


@requires_models
def test_a_window_without_telemetry_has_no_contributions_just_as_it_has_no_classes():
    from app.providers.trained import get_provider
    window, provenance = get_provider().infer(LiveInput(request_id="no-telemetry"))
    assert window.telemetry_behavior_classes == []
    assert window.telemetry_feature_contributions == []
    assert "telemetry_contribution_method" not in provenance
    assert "telemetry_contribution_baseline" not in provenance


# ====================================================================== the R10 rules (stub provider)
class ContribStub(ProbStub):
    """``ProbStub`` that also answers with per-feature contributions: feature number i gets
    ``throttle / 10 + bias + i`` (the throttle spells the probability, 40 -> 4.0), so the answer
    changes with ``bias`` - which is how a REPEAT that used the new answer would be caught."""

    def infer(self, data):
        window, provenance = super().infer(data)
        if data.telemetry_features is not None:
            base = data.telemetry_features.throttle / 10 + self.bias
            window = window.model_copy(update={"telemetry_feature_contributions": [
                TelemetryFeatureContribution(feature=name, contribution=base + index)
                for index, name in enumerate(FEATURES)]})
            provenance = {**provenance, "telemetry_contribution_method": METHOD,
                          "telemetry_contribution_baseline": -base}
        return window, provenance


def stubbed(drive):
    d = drive()
    d.stub = ContribStub()  # the router reads ``d.stub`` at call time
    return d


def listing(base):
    return [{"feature": name, "contribution": base + index} for index, name in enumerate(FEATURES)]


def test_a_repeat_carries_the_contributions_registered_with_the_observation(drive, api_factory):
    d = stubbed(drive)
    first = d.ok(0, "t0", features=tel(0.4, 1), stamp=0, seq=0)
    assert first["provenance"]["telemetry_obs"] == "new"
    assert first["telemetry_feature_contributions"] == listing(4.0)
    assert state_of(api_factory, d.sid)["obs_t_contribs"] == listing(4.0)
    d.stub.bias = 0.25  # the model answers differently now ...
    again = d.ok(500, "t1", features=tel(0.4, 1), stamp=0, seq=0)
    assert again["provenance"]["telemetry_obs"] == "repeat"
    assert d.stub.calls == 2  # ... it did run again ...
    assert again["telemetry_feature_contributions"] == listing(4.0)  # ... and its answer (4.25 ...) was not used
    # Deferred minor M4: the method and baseline that explain those contributions are the registered
    # ones too (baseline -4.0), not this request's (-4.25) - otherwise contributions + baseline would no
    # longer sum to the registered margin.
    assert again["provenance"]["telemetry_contribution_method"] == METHOD
    assert again["provenance"]["telemetry_contribution_baseline"] == -4.0
    assert state_of(api_factory, d.sid)["obs_t_contrib_meta"] == {"method": METHOD, "baseline": -4.0}
    assert again["telemetry_behavior_classes"] == first["telemetry_behavior_classes"]
    # A NEW sample with the same throttle is judged by the new answer, and registered.
    new = d.ok(1000, "t2", features=tel(0.4, 2), stamp=1000, seq=1)
    assert new["provenance"]["telemetry_obs"] == "new"
    assert new["telemetry_feature_contributions"] == listing(4.25)
    assert state_of(api_factory, d.sid)["obs_t_contribs"] == listing(4.25)
    # And the repeat of THAT one is the new registration, not the first.
    d.stub.bias = 0.5
    third = d.ok(1500, "t3", features=tel(0.4, 2), stamp=1000, seq=1)
    assert third["provenance"]["telemetry_obs"] == "repeat"
    assert third["telemetry_feature_contributions"] == listing(4.25)
    assert third["provenance"]["telemetry_contribution_baseline"] == -4.25


def test_a_repeat_in_a_session_registered_before_the_contributions_existed_keeps_the_models_answer(drive, api_factory):
    """Its registry has ``obs_t_classes`` but no ``obs_t_contribs``. The repeat has the same bytes as the
    observation it repeats, so the model's own answer IS the registered one: not an empty list beside a
    provenance that claims a method."""
    d = stubbed(drive)
    d.ok(0, "t0", features=tel(0.4, 1), stamp=0, seq=0)
    with api_factory() as db:
        sess = db.get(models.SessionMeta, d.sid)
        legacy = dict(sess.runtime_state)
        assert legacy.pop("obs_t_contribs") == listing(4.0)
        assert legacy.pop("obs_t_contrib_meta") == {"method": METHOD, "baseline": -4.0}
        sess.runtime_state = legacy
        db.commit()
    assert "obs_t_contribs" not in state_of(api_factory, d.sid)
    again = d.ok(500, "t1", features=tel(0.4, 1), stamp=0, seq=0)
    assert again["provenance"]["telemetry_obs"] == "repeat"
    assert again["telemetry_feature_contributions"] == listing(4.0)
    assert again["provenance"]["telemetry_contribution_method"] == METHOD


def test_expired_and_telemetry_less_windows_follow_the_rule_the_class_breakdown_has(drive):
    """Today's rule for ``telemetry_behavior_classes`` (inference.run_inference passes the provider's
    value through): a window whose request carried telemetry keeps what the model said about it - an
    EXPIRED one too (ruling A zeroes its score, P_telemetry_anomaly, not its recorded breakdown) - and a
    window whose request carried none has the empty list. The contributions are the same kind of value
    and must do exactly that."""
    d = stubbed(drive)
    expired = d.ok(0, "old", features=tel(0.4, 1), stamp=-4000, seq=0)  # 4 s old, the tolerance is 3 s
    assert expired["modality_freshness"]["telemetry"] == "missing"
    assert expired["provenance"]["telemetry_expired"] is True
    assert expired["P_telemetry_anomaly"] == 0.0  # scored as missing
    assert [c["label"] for c in expired["telemetry_behavior_classes"]] == ["Safe", "Aggressive", "Distracted"]
    assert expired["telemetry_feature_contributions"] == listing(4.0)
    fresh = d.ok(1000, "now", features=tel(0.4, 2), stamp=1000, seq=1)
    assert fresh["modality_freshness"]["telemetry"] == "fresh"
    assert len(fresh["telemetry_behavior_classes"]) == 3
    assert fresh["telemetry_feature_contributions"] == listing(4.0)
    picture_only = d.ok(2000, "pic", image=img(0.5, "x"), captured=2000, frame=(0, 0))
    assert picture_only["modality_freshness"] == {"vision": "fresh", "telemetry": "missing"}
    assert picture_only["telemetry_behavior_classes"] == []
    assert picture_only["telemetry_feature_contributions"] == []
    assert "telemetry_contribution_method" not in picture_only["provenance"]
    # The parity itself, window by window: both lists are empty together and non-empty together.
    for record in (expired, fresh, picture_only):
        assert bool(record["telemetry_behavior_classes"]) == bool(record["telemetry_feature_contributions"])
