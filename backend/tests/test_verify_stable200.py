"""Pure-logic tests for scripts/verify_stable200.py (Task 1.4 / DS-1).

The script is a Task 10A stage-1 verification runner: it re-computes the frozen stable200
membership hashes, drives fresh provider forwards for the three vision models in one child
process each, and compares them against the approved references from
docs/fyp2/task10a/tolerance_predeclaration.md. Only its PURE parts are tested here, with
synthetic data, so these tests run everywhere (no model artifacts, no images). Tests that
need the real candidate packages or the real JPEGs carry ``@pytest.mark.candidates`` and are
deselected by default (see conftest.py OPT_IN_MARKERS).

The expected hash vectors below were computed with the algorithm frozen in
docs/fyp2/task10a/preflight_report.md: sha256("\n".join(sorted(...)).encode("utf-8")), no
trailing newline; the softmax vectors are float64 math.exp values.
"""
import csv
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"


def load(name):
    spec = importlib.util.spec_from_file_location(f"_{name}", SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


verify = load("verify_stable200")

MEMBER_A_B_C = "f51a71fe85231c5646ea13be59f4db05a3e4b7d0ff4ad0b1e2ff349924e77815"  # "a.jpg\nb.jpg\nc.jpg"
MEMBER_A = "509b0d4641a7c3ba088ffa28559d1f57207ea980447bc1773b1d406d788386ee"  # "a.jpg"
SOURCES_A_X = "e51ab99a9ebc2d51f9434cac26245e24f6bcff98712a04834ede9287478f1b25"  # "a\nx"


# --------------------------------------------------------------------- membership hashes
class TestMembershipHashes:
    def test_joins_sorted_filenames_without_trailing_newline(self):
        rows = [{"filename": "c.jpg"}, {"filename": "a.jpg"}, {"filename": "b.jpg"}]
        assert verify.membership_sha256(rows) == MEMBER_A_B_C

    def test_uses_only_the_filename_column(self):
        rows = [{"filename": "c.jpg", "source_id": "s2"}, {"filename": "a.jpg", "source_id": "s0"},
                {"filename": "b.jpg", "source_id": "s1"}]
        assert verify.membership_sha256(rows) == MEMBER_A_B_C

    def test_source_ids_sha256_sorts_the_source_id_column(self):
        rows = [{"source_id": "x"}, {"source_id": "a"}]
        assert verify.source_ids_sha256(rows) == SOURCES_A_X

    def test_empty_rows_hash_the_empty_string(self):
        assert verify.membership_sha256([]) == hashlib.sha256(b"").hexdigest()


# --------------------------------------------------------------------------- softmax / argmax
class TestSoftmax:
    def test_known_vector(self):
        assert verify.stable_softmax64([1.0, 2.0, 3.0]) == pytest.approx(
            [0.09003057317038046, 0.24472847105479764, 0.6652409557748218])

    def test_tie_all_equal(self):
        assert verify.stable_softmax64([1000.0, 1000.0, 1000.0]) == pytest.approx([1 / 3] * 3)

    def test_two_classes(self):
        assert verify.stable_softmax64([0.0, 0.0]) == pytest.approx([0.5, 0.5])

    def test_shift_invariant_and_sums_to_one(self):
        shifted = verify.stable_softmax64([1001.0, 1000.0, 1000.0])
        unshifted = verify.stable_softmax64([1.0, 0.0, 0.0])
        assert shifted == pytest.approx(unshifted)
        assert sum(shifted) == pytest.approx(1.0)

    def test_extreme_values_do_not_overflow(self):
        probs = verify.stable_softmax64([-1e6, 1e6])
        assert probs == pytest.approx([0.0, 1.0], abs=1e-12)


class TestArgmax:
    def test_picks_lowest_index_on_tie(self):
        assert verify.argmax([0.4, 0.4, 0.2]) == 0
        assert verify.argmax([0.2, 0.4, 0.4]) == 1

    def test_picks_the_clear_maximum(self):
        assert verify.argmax([0.1, 0.7, 0.2]) == 1


class TestTop1Top2Margin:
    def test_clear_winner(self):
        assert verify.top1_top2_margin([0.5, 0.3, 0.2]) == pytest.approx(0.2)

    def test_tie_gives_zero_margin(self):
        assert verify.top1_top2_margin([0.4, 0.4, 0.2]) == pytest.approx(0.0)


# ------------------------------------------------------------------------ source_id pairing
class TestProjectFresh:
    def test_projects_down_to_the_reference_set(self):
        # a worker forwards 200 stable200 + 100 parity images; the parity comparison must
        # pair ONLY the 100 parity ids, never the extra 200 (they are a different set).
        fresh = {"p1": [0.9, 0.1], "s1": [0.8, 0.2], "s2": [0.7, 0.3]}
        projected = verify.project_fresh(fresh, {"p1": [0.9, 0.1]})
        assert projected == {"p1": [0.9, 0.1]}
        assert "s1" not in projected and "s2" not in projected

    def test_reference_ids_without_a_forward_stay_missing(self):
        projected = verify.project_fresh({"a": [1.0, 0.0]}, {"a": [1.0, 0.0], "x": [0.5, 0.5]})
        assert projected == {"a": [1.0, 0.0]}


class TestPairBySourceId:
    def test_matches_by_id_not_row_order(self):
        fresh = {"a": [1.0, 0.0], "b": [0.0, 1.0]}
        reference = {"b": [0.0, 1.0], "a": [1.0, 0.0]}  # different insertion order
        pairs, missing_fresh, missing_reference = verify.pair_by_source_id(fresh, reference)
        assert [(p[0], p[1], p[2]) for p in pairs] == [("a", [1.0, 0.0], [1.0, 0.0]),
                                                      ("b", [0.0, 1.0], [0.0, 1.0])]
        assert missing_fresh == [] and missing_reference == []

    def test_reports_missing_on_both_sides(self):
        pairs, missing_fresh, missing_reference = verify.pair_by_source_id(
            {"a": [1.0, 0.0]}, {"a": [1.0, 0.0], "x": [0.5, 0.5]})
        assert missing_fresh == ["x"] and missing_reference == []
        pairs, missing_fresh, missing_reference = verify.pair_by_source_id(
            {"a": [1.0, 0.0], "y": [0.5, 0.5]}, {"a": [1.0, 0.0]})
        assert missing_fresh == [] and missing_reference == ["y"]


# --------------------------------------------------------------------- comparison verdicts
class TestCompareSet:
    def test_identical_predictions_pass(self):
        fresh = {"a": [0.9, 0.1], "b": [0.1, 0.9]}
        result = verify.compare_set(fresh, dict(fresh))
        assert result["pass_numeric"] is True
        assert result["max_abs_prob_delta"] == 0.0
        assert result["argmax_agreement"] == 1.0
        assert result["worst"] is None
        assert result["missing_fresh"] == [] and result["missing_reference"] == []

    def test_fails_over_tolerance_with_worst_sample_details(self):
        fresh = {"ok": [0.9, 0.1], "bad": [0.80, 0.20]}
        reference = {"ok": [0.9, 0.1], "bad": [0.8002, 0.1998]}
        result = verify.compare_set(fresh, reference)
        assert result["pass_numeric"] is False
        assert result["max_abs_prob_delta"] == pytest.approx(2e-4)
        assert result["argmax_agreement"] == 1.0  # argmax still agrees everywhere
        worst = result["worst"]
        assert worst["source_id"] == "bad"
        assert worst["per_class_deltas"] == pytest.approx([2e-4, 2e-4])
        assert worst["fresh_argmax"] == 0 and worst["reference_argmax"] == 0
        assert worst["top1_top2_margin_fresh"] == pytest.approx(0.6)
        assert worst["top1_top2_margin_reference"] == pytest.approx(0.6004)

    def test_tolerance_boundary_passes(self):
        # 0.0001 parses to the exact float64 the 1e-4 tolerance literal also parses to,
        # so this delta is <= the tolerance and must pass (boundary, not off-by-one-ulp).
        fresh = {"a": [0.0, 1.0]}
        reference = {"a": [0.0001, 0.9999]}
        result = verify.compare_set(fresh, reference)
        assert result["max_abs_prob_delta"] == pytest.approx(1e-4)
        assert result["pass_numeric"] is True

    def test_argmax_mismatch_fails_even_with_tiny_delta(self):
        fresh = {"a": [0.50001, 0.49999], "b": [0.4, 0.6]}
        reference = {"a": [0.49999, 0.50001], "b": [0.4, 0.6]}
        result = verify.compare_set(fresh, reference)
        assert result["pass_numeric"] is False
        assert result["argmax_agreement"] == 0.5
        assert result["argmax_mismatches"] == ["a"]

    def test_missing_reference_blocks_pass(self):
        result = verify.compare_set({"a": [0.9, 0.1]}, {"a": [0.9, 0.1], "x": [0.5, 0.5]})
        assert result["pass_numeric"] is False
        assert result["missing_fresh"] == ["x"]

    def test_nothing_compared_is_not_a_pass(self):
        result = verify.compare_set({}, {"x": [0.5, 0.5]})
        assert result["pass_numeric"] is False
        assert result["n_compared"] == 0


# ----------------------------------------------------------------------------- class rule
class TestValidateProbs:
    def test_clean_vector_has_no_problems(self):
        assert verify.validate_probs([0.1] * 10) == []

    def test_wrong_length_is_reported(self):
        assert any("10 classes" in p for p in verify.validate_probs([0.5, 0.5]))

    def test_out_of_range_and_bad_sum_are_reported(self):
        problems = verify.validate_probs([2.0] + [0.0] * 9)
        assert any("outside [0,1]" in p for p in problems)
        assert any("sum" in p for p in problems)

    def test_non_finite_is_reported(self):
        problems = verify.validate_probs([float("nan")] + [0.0] * 9)
        assert any("non-finite" in p for p in problems)


class TestClassRule:
    def test_mode_winners_lists_every_tied_mode(self):
        assert verify.mode_winners([0, 1, 0, 1]) == [0, 1]
        assert verify.mode_winners([0, 0, 1]) == [0]
        assert verify.mode_winners([]) == []

    def test_all_classes_with_unique_correct_mode_pass(self):
        samples = [{"class_id": f"c{i}", "argmax": i} for i in range(10) for _ in range(20)]
        result = verify.evaluate_class_rule(samples)
        assert result["all_unique_modes_equal_label"] is True
        assert result["per_class"]["c0"]["pass"] is True
        assert result["per_class"]["c9"]["pass"] is True

    def test_tied_mode_fails_that_class_and_the_whole_rule(self):
        # every class is perfect except c0, which ties 10-10: the ONLY failure is the tie.
        samples = [{"class_id": "c0", "argmax": 0}] * 10 + [{"class_id": "c0", "argmax": 1}] * 10
        samples += [{"class_id": f"c{i}", "argmax": i} for i in range(1, 10) for _ in range(20)]
        result = verify.evaluate_class_rule(samples)
        assert result["per_class"]["c0"]["winners"] == [0, 1]
        assert result["per_class"]["c0"]["pass"] is False
        assert result["per_class"]["c1"]["pass"] is True
        assert result["per_class"]["c9"]["pass"] is True
        assert result["all_unique_modes_equal_label"] is False

    def test_class_with_no_samples_fails(self):
        result = verify.evaluate_class_rule([{"class_id": "c0", "argmax": 0}] * 20)
        assert result["per_class"]["c1"]["pass"] is False
        assert result["all_unique_modes_equal_label"] is False


# ---------------------------------------------------------------------------- reference io
class TestReferences:
    def test_parity_reference_softmaxes_cached_logits(self, tmp_path):
        path = tmp_path / "parity.json"
        path.write_text(json.dumps({"result": {"validation_predictions": [
            {"source_id": "vision-v1:c0/a.jpg", "class_id": "c0", "driver_id": "p002",
             "predicted_class": "c0", "logits": [1.0, 2.0, 3.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]},
        ]}}))
        refs, meta = verify.parity_reference(path)
        # softmax of the FULL 10-logit vector (seven zeros contribute to the denominator)
        assert refs["vision-v1:c0/a.jpg"] == pytest.approx(
            [0.07308609080044932, 0.1986685925359692, 0.5400372249760593] + [0.026886870241074588] * 7)
        assert meta["n"] == 1
        assert meta["sha256"] == verify.sha256_file(path)

    def test_csv_reference_reads_probabilities_without_re_softmax(self, tmp_path):
        # probabilities that are deliberately NOT the softmax of the logits: the loader must
        # not touch them (PyTorch CSV probabilities are read directly per the tolerance doc).
        path = tmp_path / "saved.csv"
        cols = ["source_id", "true_label_index", "predicted_label_index"]
        cols += [f"logit_c{i}" for i in range(10)] + [f"probability_c{i}" for i in range(10)]
        row = ["s1", "0", "0"] + ["0.0"] * 10 + ["0.05"] * 10
        path.write_text(",".join(cols) + "\n" + ",".join(row) + "\n")
        refs, meta = verify.csv_reference(path)
        assert refs["s1"] == pytest.approx([0.05] * 10)
        assert meta["n"] == 1
        assert meta["sha256"] == verify.sha256_file(path)

    def test_csv_reference_parses_real_decimal_layout(self, tmp_path):
        path = tmp_path / "saved.csv"
        cols = ["source_id", "true_label_index", "predicted_label_index"]
        cols += [f"logit_c{i}" for i in range(10)] + [f"probability_c{i}" for i in range(10)]
        row = ["s1", "0", "0", "5.296996", "0.9607185"] + ["0.0"] * 8 \
            + ["0.9607185", "0.0005120502"] + ["0.0"] * 8
        path.write_text(",".join(cols) + "\n" + ",".join(row) + "\n")
        refs, _ = verify.csv_reference(path)
        assert refs["s1"][0] == pytest.approx(0.9607185)
        assert refs["s1"][1] == pytest.approx(0.0005120502)

    def test_sha256_file_matches_known_bytes(self, tmp_path):
        path = tmp_path / "data.bin"
        path.write_bytes(b"abc")
        assert verify.sha256_file(path) == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


# --------------------------------------------------------------------- candidates-marked
# These need the real P5 packages (ml/outputs/candidates/ is git-ignored) or the real JPEGs;
# they are deselected unless the run asks with -m candidates (conftest.py OPT_IN_MARKERS).
@pytest.mark.candidates
class TestRealArtifacts:
    REPO = Path(__file__).resolve().parents[2]
    P5 = REPO / "ml/outputs/candidates/p5_resnet18_search004_seed42_20261023"
    MN_P5 = REPO / "ml/outputs/candidates/p5_mobilenet_v3_large_search006_seed42_20261023"

    def test_real_annotations_reproduce_the_frozen_membership_hashes(self):
        rows = verify.parse_annotations(self.P5 / "validation/stable200_annotations.csv")
        assert verify.membership_sha256(rows) == verify.EXPECTED_MEMBERSHIP_SHA256
        assert verify.source_ids_sha256(rows) == verify.EXPECTED_SOURCE_IDS_SHA256
        assert len(rows) == 200
        assert {r["class_id"] for r in rows} == {f"c{i}" for i in range(10)}

    def test_reference_file_sha256s_match_the_approved_tolerance_document(self):
        assert verify.sha256_file(self.P5 / "validation/stable200_saved_predictions.csv") == \
            "c7d233c813a01d54ff286a836e5c6cab069558b52a9ee547953052fc92a0787d"
        assert verify.sha256_file(self.MN_P5 / "validation/stable200_saved_predictions.csv") == \
            "47fd6f678247c81f6b0384a6453c7467c5b3dd39208647a9847f33807dba74b6"

    def test_provider_forward_smoke_on_one_real_image(self):
        # The stable model only: one real JPEG through the exact provider path
        # (base64 of the ORIGINAL bytes -> preprocess -> vision.run -> float32 softmax).
        import base64
        import os

        rows = verify.parse_annotations(self.P5 / "validation/stable200_annotations.csv")
        row = next(r for r in rows
                   if (verify.DEFAULT_DATA_ROOT / r["class_id"] / r["filename"]).is_file())
        os.environ["DRA_ACTIVE_VISION"] = "stable"
        from app.providers.trained import TrainedProvider

        provider = TrainedProvider()
        raw = (verify.DEFAULT_DATA_ROOT / row["class_id"] / row["filename"]).read_bytes()
        sample = verify.forward_sample(provider, raw, row["source_id"])
        assert len(sample["probs"]) == 10
        assert sum(sample["probs"]) == pytest.approx(1.0, abs=1e-5)
        assert sample["sha256"] == verify.sha256_bytes(raw)
        assert sample["argmax"] == verify.argmax(sample["probs"])
        assert base64.b64encode(raw).decode()  # sanity: forward_sample encodes the raw bytes
