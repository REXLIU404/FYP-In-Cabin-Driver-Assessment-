"""E2 / E5-light runner (scripts/fusion_eval.py): the parts that decide what is measured.

The full runs are evidence (docs/evidence/<date>/e2-*, e5-*), not tests. These tests cover:

- the pre-declared protocol is what the runner reads;
- the pairs are drawn exactly by the protocol's rule;
- the oracle is independent of the product code and still agrees with it;
- the variants change one branch only;
- the timeline follows ai/src/scenarioTimeline.ts;
- the summary statistics count what they say they count.
"""
import importlib.util
import json
import random
import sys
from datetime import datetime, timezone
from fractions import Fraction
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "scripts"


def load(name):
    spec = importlib.util.spec_from_file_location(f"_{name}", SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


fe = load("fusion_eval")
PROTOCOL = json.loads((REPO / "docs" / "fyp2" / "e2e5" / "protocol.json").read_text(encoding="utf-8"))
POLICY = PROTOCOL["operational_reference_policy"]


# ------------------------------------------------------------------- protocol + gate
def test_the_protocol_is_predeclared_descriptive_and_matches_report_table_9():
    assert PROTOCOL["status"] == "PREDECLARED"
    assert PROTOCOL["decision_rule"] == "DESCRIPTIVE_ONLY"
    assert [(w["w_v"], w["w_t"]) for w in PROTOCOL["e2"]["weights"]] == [
        (0.5, 0.5), (0.6, 0.4), (0.4, 0.6), (0.7, 0.3), (0.3, 0.7)]
    assert PROTOCOL["e2"]["weights"][PROTOCOL["e2"]["baseline_weight_index"]]["w_v"] == 0.5
    assert all(abs(w["w_v"] + w["w_t"] - 1) < 1e-12 for w in PROTOCOL["e2"]["weights"])
    assert len(PROTOCOL["e2"]["strata"]) == 6 and PROTOCOL["e2"]["pairs_per_stratum"] == 10
    assert [v["id"] for v in PROTOCOL["e5_light"]["variants"]] == [
        "FUSED", "VISION_HELD_SAFE", "TELEMETRY_HELD_SAFE"]


@pytest.mark.parametrize("vision,telemetry,expected", [
    ("c0", "Safe", ("REF_LOW", ["Low"])),
    ("c0", "Aggressive", ("REF_ELEVATED", ["Medium", "High"])),
    ("c0", "Distracted", ("REF_ELEVATED", ["Medium", "High"])),
    ("c4", "Safe", ("REF_ELEVATED", ["Medium", "High"])),
    ("c9", "Aggressive", ("REF_HIGH", ["High"])),
    ("c1", "Distracted", ("REF_HIGH", ["High"])),
])
def test_the_reference_reads_source_labels_only(vision, telemetry, expected):
    assert fe.reference(vision, telemetry, POLICY) == expected


START = datetime(2026, 11, 2, 12, 0, tzinfo=timezone.utc)


def test_the_gate_passes_a_committed_unmodified_protocol_older_than_the_run():
    assert fe.gate_verdict(dirty=False, commit="abc", commit_time="2026-11-02T17:03:53+08:00",
                           blob_matches=True, run_start=START) == []


@pytest.mark.parametrize("kwargs,needle", [
    ({"commit": None, "commit_time": None}, "not committed"),
    ({"dirty": True}, "uncommitted changes"),
    ({"blob_matches": False}, "differs from its committed blob"),
    ({"commit_time": "2026-11-02T12:00:00+00:00"}, "not before the run start"),
])
def test_the_gate_blocks_a_protocol_that_was_not_declared_first(kwargs, needle):
    args = {"dirty": False, "commit": "abc", "commit_time": "2026-11-02T08:00:00+00:00",
            "blob_matches": True, "run_start": START} | kwargs
    assert any(needle in p for p in fe.gate_verdict(**args))


# ------------------------------------------------------------------------- E2 pairs
def _pools():
    vision = [{"filename": f"img_{c}_{i:03d}.jpg", "class_id": c, "driver_id": f"p{i % 4}",
               "split": "test", "image_path": f"/x/{c}/{i}.jpg"}
              for c in [f"c{n}" for n in range(10)] for i in range(40)]
    vision += [{"filename": f"train_{i}.jpg", "class_id": "c0", "driver_id": "p9", "split": "train",
                "image_path": f"/t/{i}.jpg"} for i in range(200)]
    telemetry = [{"behavior_label": label, **{f: str(i) for f in fe.TELEMETRY_FEATURES}}
                 for i in range(150) for label in ("Safe", "Aggressive", "Distracted")]
    random.Random(7).shuffle(vision)
    return vision, telemetry


def test_e2_pairs_follow_the_declared_rule_with_no_reuse_and_test_split_only():
    vision, telemetry = _pools()
    pairs = fe.e2_pairs(vision, telemetry, PROTOCOL["e2"], POLICY)
    assert len(pairs) == 60
    assert len({p["vision"]["filename"] for p in pairs}) == 60
    assert len({p["telemetry"]["row"] for p in pairs}) == 60
    assert not any(p["vision"]["filename"].startswith("train_") for p in pairs)
    for p in pairs:
        stratum = next(s for s in PROTOCOL["e2"]["strata"] if s["id"] == p["stratum"])
        assert p["vision"]["class_id"] in PROTOCOL["e2"]["vision_pools"][stratum["vision"]]
        assert p["telemetry"]["label"] == stratum["telemetry"]
        assert (p["reference"], p["reference_levels"]) == fe.reference(
            p["vision"]["class_id"], p["telemetry"]["label"], POLICY)
    # The declared draw, replayed by hand: one Random(seed), sorted pools, draw order
    # safe, distracted, Safe, Aggressive, Distracted; handed out S1..S6.
    rng = random.Random(PROTOCOL["e2"]["seed"])
    test = [r for r in vision if r["split"] == "test"]
    safe = rng.sample(sorted((r for r in test if r["class_id"] == "c0"), key=lambda r: r["filename"]), 30)
    rng.sample(sorted((r for r in test if r["class_id"] != "c0"), key=lambda r: r["filename"]), 30)
    safe_rows = rng.sample([n for n, r in enumerate(telemetry) if r["behavior_label"] == "Safe"], 20)
    assert [p["vision"]["filename"] for p in pairs[:30]] == [r["filename"] for r in safe]
    assert [p["telemetry"]["row"] for p in pairs[:10]] == safe_rows[:10]
    assert [p["telemetry"]["row"] for p in pairs[30:40]] == safe_rows[10:]
    assert fe.e2_pairs(vision, telemetry, PROTOCOL["e2"], POLICY) == pairs


def test_e2_sessions_are_one_fresh_window_per_pair_and_weight():
    vision, telemetry = _pools()
    pairs = fe.e2_pairs(vision, telemetry, PROTOCOL["e2"], POLICY)
    sessions = fe.e2_sessions(pairs, PROTOCOL)
    assert len(sessions) == 300 and len({s["session_id"] for s in sessions}) == 300
    assert all(len(s["steps"]) == 1 and s["mode"] == "LIVE_MODEL_RUNTIME" for s in sessions)
    step = sessions[7]["steps"][0]
    assert step["captured_at"] == step["telemetry_timestamp"] == step["server_time"]
    assert sessions[7]["config"]["weight_vision"] == PROTOCOL["e2"]["weights"][2]["w_v"]
    times = [s["steps"][0]["server_time"] for s in sessions]
    assert times == sorted(times) and len(set(times)) == 300


# ----------------------------------------------------------------------------- oracle
@pytest.mark.parametrize("pd,pt,wv,wt,expected", [
    (0.1, 0.1, 0.5, 0.5, Fraction(10)),
    (0.9, 0.1, 0.5, 0.5, Fraction(50)),
    (0.8, 0.6, 0.3, 0.7, Fraction(66)),
    (1.2, -0.1, 0.5, 0.5, Fraction(50)),
])
def test_the_exact_oracle_is_hand_arithmetic(pd, pt, wv, wt, expected):
    assert fe.exact_score(pd, pt, wv, wt) == expected


def test_the_independent_oracle_agrees_with_the_product_fusion_on_a_grid():
    from app import fusion

    rng = random.Random(3)
    ties = 0
    for _ in range(2000):
        pd, pt = round(rng.random(), 3), round(rng.random(), 3)
        wv = rng.choice((0.3, 0.4, 0.5, 0.6, 0.7))
        product = fusion.compute_risk_score(pd, pt, wv, round(1 - wv, 1))
        exact = fe.exact_score(pd, pt, wv, round(1 - wv, 1))
        assert abs(product - float(exact)) <= 0.05 + 1e-9
        if fe.is_decimal_tie(exact):
            # The product rounds the double's repr: on an exact tie it may sit one tenth low.
            ties += 1
            assert product in (fe.round_half_up_1dp(exact), fe.round_half_up_1dp(exact) - 0.1) or \
                abs(product - (fe.round_half_up_1dp(exact) - 0.1)) < 1e-9
        else:
            assert product == fe.round_half_up_1dp(exact)
        assert fe.level_of(product, 30, 60) == fusion.map_risk_level(product, 30, 60)
        assert fe.dominant_of(pd, pt, product, 30) == fusion.determine_dominant_evidence(
            pd, pt, product, "FULL", low=30)
    assert ties > 0  # the grid does reach the tie case it allows for


def test_decimal_ties():
    assert fe.is_decimal_tie(Fraction(1253, 20))  # 62.65
    assert not fe.is_decimal_tie(Fraction(626, 10)) and not fe.is_decimal_tie(Fraction(6266, 100))


def test_r14_disagreement_is_the_documented_counter_example():
    # pd .8, pt .6, w .3/.7: raw strength says vision, weighted contribution says telemetry.
    assert fe.r14_disagrees("Vision-dominant", 0.8, 0.6, 0.3, 0.7)
    assert not fe.r14_disagrees("Vision-dominant", 0.8, 0.6, 0.5, 0.5)
    assert fe.r14_disagrees("Telemetry-dominant", 0.6, 0.8, 0.7, 0.3)
    assert not fe.r14_disagrees("Combined evidence", 0.6, 0.65, 0.3, 0.7)


# ---------------------------------------------------------------------- E2 summary
def _row_window(pd, pt, score, level, dominant):
    return {"P_distraction": pd, "P_telemetry_anomaly": pt, "RiskScore": score, "RiskLevel": level,
            "DominantEvidence": dominant, "P_distraction_raw": pd, "P_telemetry_raw": pt,
            "SystemHealth": "FULL", "AlertSeverity": "NORMAL", "vision_freshness": "fresh",
            "telemetry_freshness": "fresh", "vision_obs": "new", "telemetry_obs": "new"}


def test_e2_rows_and_summary_count_agreement_changes_attenuation_and_model_errors():
    proto = json.loads(json.dumps(PROTOCOL))
    proto["e2"]["strata"] = PROTOCOL["e2"]["strata"][3:4]  # S4: vision distracted, telemetry Safe
    proto["e2"]["pairs_per_stratum"] = 2
    pairs = [
        {"pair_id": "S4-01", "stratum": "S4", "vision": {"filename": "a.jpg", "class_id": "c1", "driver_id": "p1"},
         "telemetry": {"row": 1, "label": "Safe"}, "reference": "REF_ELEVATED", "reference_levels": ["Medium", "High"]},
        {"pair_id": "S4-02", "stratum": "S4", "vision": {"filename": "b.jpg", "class_id": "c2", "driver_id": "p1"},
         "telemetry": {"row": 2, "label": "Safe"}, "reference": "REF_ELEVATED", "reference_levels": ["Medium", "High"]},
    ]
    # Pair 1: a strong vision signal, attenuated to Medium at 0.5/0.5 and lifted at 0.7/0.3.
    # Pair 2: the vision model misses the distraction (pd 0.3): Low everywhere.
    windows = {
        ("S4-01", 0): _row_window(0.9, 0.1, 50.0, "Medium", "Vision-dominant"),
        ("S4-01", 3): _row_window(0.9, 0.1, 66.0, "High", "Vision-dominant"),
        ("S4-02", 0): _row_window(0.3, 0.1, 20.0, "Low", "Low observed risk"),
        ("S4-02", 3): _row_window(0.3, 0.1, 24.0, "Low", "Low observed risk"),
    }
    sessions = [{"meta": {"pair_id": p, "weight_index": j}, "windows": [w]} for (p, j), w in windows.items()]
    rows = fe.e2_rows(pairs, sessions, proto)
    by = {(r["pair_id"], r["weight_index"]): r for r in rows}
    assert by[("S4-01", 0)]["agrees"] and not by[("S4-02", 0)]["agrees"]
    assert by[("S4-01", 0)]["attenuation_case"] and not by[("S4-01", 3)]["attenuation_case"]
    assert by[("S4-02", 0)]["vision_model_disagrees"] and not by[("S4-01", 0)]["vision_model_disagrees"]
    assert all(r["formula_error"] == 0 and r["level_oracle_match"] for r in rows)

    proto["e2"]["weights"] = [PROTOCOL["e2"]["weights"][0], {"w_v": 0.6, "w_t": 0.4, "name": "unused"},
                              {"w_v": 0.4, "w_t": 0.6, "name": "unused2"}, PROTOCOL["e2"]["weights"][3]]
    summary = fe.e2_summary(rows, proto)
    change = summary["level_change_vs_baseline"]["Strong vision-priority"]
    assert (change["changed"], change["up"], change["down"]) == (1, 1, 0)
    assert change["pairs_changed"] == ["S4-01"]
    assert summary["by_weight"]["Balanced baseline"]["agrees"] == 1
    assert summary["by_weight"]["Balanced baseline"]["agrees_model_consistent_pairs"] == 1
    assert summary["model_consistent_pairs"] == 1
    assert summary["branch_model_disagreement"]["S4"] == {"vision": 1, "telemetry": 0}
    assert [e["pair_id"] for e in summary["attenuation_examples_baseline"]] == ["S4-01"]
    assert summary["checks"]["probabilities_identical_across_weights"]


# ------------------------------------------------------------------------- E5 plan
def test_e5_variants_change_exactly_one_branch():
    base = json.loads((REPO / "demo" / "scenarios" / "viva_compact.json").read_text(encoding="utf-8"))
    variants = fe.e5_variant_scenarios(base, PROTOCOL["e5_light"]["variants"])
    assert variants["FUSED"] == base
    held_v, held_t = variants["VISION_HELD_SAFE"], variants["TELEMETRY_HELD_SAFE"]
    assert len({base["scenario_id"], held_v["scenario_id"], held_t["scenario_id"]}) == 3
    for b, v, t in zip(base["segments"], held_v["segments"], held_t["segments"]):
        assert v["vision_class"] == "c0" and v["telemetry_label"] == b["telemetry_label"]
        assert t["telemetry_label"] == "Safe" and t["vision_class"] == b["vision_class"]
        for other in (v, t):
            assert {k: other[k] for k in ("title", "duration_s", "driver_id")} == \
                   {k: b[k] for k in ("title", "duration_s", "driver_id")}
    assert held_v["seed"] == held_t["seed"] == base["seed"]


def _manifest():
    segments = [{"index": 0, "title": "A", "start_ms": 0, "duration_ms": 4000, "vision_class": "c0",
                 "telemetry_label": "Safe"},
                {"index": 1, "title": "B", "start_ms": 4000, "duration_ms": 4000, "vision_class": "c4",
                 "telemetry_label": "Aggressive"}]
    frames = [{"n": n, "file": f"{n:04d}.jpg", "class_id": "c0" if n < 20 else "c4",
               "vision_label": "x", "segment_index": 0 if n < 20 else 1, "sha256": f"h{n}"} for n in range(40)]
    telemetry = [{"n": k, "row": 100 + k, "label": "Safe" if k < 2 else "Aggressive",
                  "segment_index": 0 if k < 2 else 1, "features": {"speed_kmph": float(k)}} for k in range(4)]
    return {"scenario_id": "toy", "frame_period_ms": 200, "telemetry_period_ms": 2000,
            "duration_ms": 8000, "segments": segments, "frames": frames, "telemetry": telemetry}


def test_e5_steps_follow_the_scenario_timeline():
    steps = fe.e5_steps(_manifest(), Path("/f"), 100, POLICY, "FUSED")
    assert len(steps) == 80
    assert [s["meta"]["frame_n"] for s in steps[:5]] == [0, 0, 1, 1, 2]
    assert [s["telemetry_seq"] for s in (steps[0], steps[19], steps[20], steps[39], steps[40], steps[79])] \
        == [0, 0, 1, 1, 2, 3]
    s = steps[45]  # pos 4500 ms: frame 22, row 2, segment 1
    assert (s["vision_frame"], s["meta"]["row_k"], s["meta"]["segment_index"]) == ({"epoch": 1, "index": 22}, 2, 1)
    assert s["captured_at"] == fe.iso_at(22 * 200) and s["telemetry_timestamp"] == fe.iso_at(4000)
    assert s["server_time"] == fe.iso_at(4500)
    assert s["meta"]["reference"] == "REF_HIGH" and steps[0]["meta"]["reference"] == "REF_LOW"
    assert s["replay"] == {"scenario_id": "toy", "segment_index": 1, "frame_file": "0022.jpg",
                           "vision_label": "x", "telemetry_row": 102, "telemetry_label": "Aggressive"}
    assert all(s["captured_at"] <= s["server_time"] and s["telemetry_timestamp"] <= s["server_time"]
               for s in steps)


def test_unchanged_segments_must_have_identical_inputs():
    base = _manifest()
    held = json.loads(json.dumps(base))
    held["segments"][1]["vision_class"] = "c0"
    for f in held["frames"][20:]:
        f["sha256"] = "other"
    report = fe.unchanged_segment_identity({"FUSED": base, "VISION_HELD_SAFE": held})
    assert report["VISION_HELD_SAFE"] == [
        {"segment_index": 0, "labels_unchanged": True, "vision_identical": True, "telemetry_identical": True},
        {"segment_index": 1, "labels_unchanged": False, "vision_identical": False, "telemetry_identical": True},
    ]


def test_e5_summary_lag_alert_and_branch_contribution():
    manifest = _manifest()
    steps = fe.e5_steps(manifest, Path("/f"), 100, POLICY, "FUSED")

    def windows(score_of):
        out = []
        for s in steps:
            score = score_of(s["meta"]["pos_ms"])
            level = fe.level_of(score, 30, 60)
            out.append({"meta": s["meta"], "RiskScore": score, "RiskLevel": level,
                        "DominantEvidence": "Combined evidence",
                        "AlertSeverity": "HIGH_ALERT" if score >= 60 else "NORMAL",
                        "P_distraction": 0.5, "P_telemetry_anomaly": 0.5})
        return out

    fused = windows(lambda pos: 10.0 if pos < 4000 else min(70.0, 10.0 + (pos - 4000) / 50))
    by_variant = {"FUSED": fused, "VISION_HELD_SAFE": windows(lambda pos: 10.0),
                  "TELEMETRY_HELD_SAFE": windows(lambda pos: 10.0)}
    summary = fe.e5_summary(by_variant, {v: manifest for v in by_variant})
    seg = summary["segments"][1]["variants"]["FUSED"]
    assert seg["reference"] == "REF_HIGH"
    assert seg["lag_ms_to_reference"] == 2500  # first score >= 60 at pos 6500
    assert seg["first_high_alert_ms"] == 2500 and seg["alert_max"] == "HIGH_ALERT"
    assert summary["segments"][0]["variants"]["FUSED"]["agrees"] == 40
    assert summary["segments"][1]["contribution_from_vision"]["max"] == 60.0
    assert summary["segments"][0]["contribution_from_telemetry"]["max"] == 0.0
