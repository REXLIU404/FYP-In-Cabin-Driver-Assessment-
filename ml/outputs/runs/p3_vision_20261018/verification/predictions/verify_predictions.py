"""Read-only S3 audit of saved validation predictions; never loads a model or test data.

Run with ./.venv/bin/python -B <this file>. Outputs stay beside this script.
Each assertion below counts once, including vectorized assertions. No per-cell
or per-sample multiplication is used to inflate the reported check count.
"""
import hashlib
import json
import math
import platform
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import sklearn
from sklearn.metrics import log_loss

OUT = Path(__file__).resolve().parent
RUN = OUT.parents[1]
CLASSES = [f"c{i}" for i in range(10)]
INPUT_NAMES = ["sample_manifest.csv", "predictions_validation.csv",
               "probabilities_validation.npy", "validation_metrics.json",
               "class_report.json", "timing_samples.csv"]
checks = []


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check(name, condition, detail=None):
    record = {"name": name, "passed": bool(condition)}
    if detail is not None:
        record["detail"] = detail
    checks.append(record)
    if not condition:
        print("FAIL", name, json.dumps(detail, ensure_ascii=False))


def close(actual, expected, atol=1e-12, rtol=1e-12):
    return bool(np.isclose(actual, expected, atol=atol, rtol=rtol))


def dump(name, value):
    (OUT / name).write_text(json.dumps(value, indent=2, ensure_ascii=False,
                                      allow_nan=False) + "\n")


def main():
    started = time.monotonic()
    directories = sorted(p.parent for p in (RUN / "search").rglob("sample_manifest.csv"))
    check("attempt_count", len(directories) == 16, len(directories))
    check("model_attempt_counts", {
        model: sum(p.parent.parent.name == model for p in directories)
        for model in ["mobilenet_v3_large", "resnet18"]
    } == {"mobilenet_v3_large": 8, "resnet18": 8})
    inputs = [directory / name for directory in directories for name in INPUT_NAMES]
    check("all_inputs_regular_non_symlink", all(p.is_file() and not p.is_symlink() for p in inputs))
    before = {str(p.relative_to(RUN)): {"sha256": sha256(p), "bytes": p.stat().st_size} for p in inputs}
    reference = None
    summaries = []
    for directory in directories:
        label = str(directory.relative_to(RUN))
        start_checks = len(checks)

        def verify(name, condition, detail=None):
            check(f"{label}:{name}", condition, detail)

        manifest = pd.read_csv(directory / "sample_manifest.csv", keep_default_na=False)
        prediction = pd.read_csv(directory / "predictions_validation.csv", keep_default_na=False)
        probabilities = np.load(directory / "probabilities_validation.npy", allow_pickle=False)
        metrics = json.loads((directory / "validation_metrics.json").read_text())
        report = json.loads((directory / "class_report.json").read_text())
        timing = pd.read_csv(directory / "timing_samples.csv", keep_default_na=False)
        training = manifest.loc[manifest.split == "train"].reset_index(drop=True)
        validation = manifest.loc[manifest.split == "val"].reset_index(drop=True)
        verify("manifest_columns", list(manifest) == ["source_id", "split", "source_row", "class_id", "driver_id"])
        verify("manifest_split_counts", len(training) == 15899 and len(validation) == 2868 and len(manifest) == 18767)
        verify("manifest_unique_source_ids", manifest.source_id.is_unique)
        verify("manifest_original_source_rows_unique", manifest.source_row.is_unique)
        verify("train_validation_source_disjoint", set(training.source_id).isdisjoint(validation.source_id))
        verify("train_validation_driver_disjoint", set(training.driver_id).isdisjoint(validation.driver_id))
        verify("driver_ids_complete", bool((manifest.driver_id.str.len() > 0).all()))
        for split, frame in [("train", training), ("val", validation)]:
            verify(f"{split}_ten_classes", set(frame.class_id) == set(CLASSES))
            # source_row preserves the original full metadata index rather than
            # a reset split-local index; gaps from other splits are expected.
            verify(f"{split}_original_source_rows_valid", np.issubdtype(frame.source_row.dtype, np.integer)
                   and frame.source_row.is_unique and frame.source_row.is_monotonic_increasing
                   and bool((frame.source_row >= 0).all()))
            source_class = frame.source_id.str.extract(r"^vision-v1:(c[0-9])/[^/]+$", expand=False)
            verify(f"{split}_source_id_class_mapping", bool((source_class == frame.class_id).all()))
        if reference is None:
            reference = manifest.copy()
        verify("identical_source_ids_order_split_drivers_all_attempts", manifest.equals(reference))
        expected_columns = ["source_id", "true_label_index", "predicted_label_index"]
        for cls in CLASSES:
            expected_columns += [f"logit_{cls}", f"probability_{cls}"]
        verify("prediction_column_class_order", list(prediction) == expected_columns)
        verify("prediction_count", len(prediction) == 2868)
        verify("prediction_source_ids_unique", prediction.source_id.is_unique)
        verify("prediction_ids_order_equal_validation_manifest", prediction.source_id.tolist() == validation.source_id.tolist())
        y = prediction.true_label_index.to_numpy()
        predicted = prediction.predicted_label_index.to_numpy()
        expected_y = validation.class_id.str.slice(1).astype(int).to_numpy()
        verify("true_label_mapping_c0_through_c9", np.array_equal(y, expected_y))
        verify("true_label_integer_dtype", np.issubdtype(y.dtype, np.integer))
        verify("predicted_label_integer_dtype", np.issubdtype(predicted.dtype, np.integer))
        verify("true_label_range", set(y) == set(range(10)))
        verify("predicted_label_range", bool(((predicted >= 0) & (predicted < 10)).all()))
        logits = prediction[[f"logit_{cls}" for cls in CLASSES]].to_numpy(dtype=np.float64)
        csv_probabilities = prediction[[f"probability_{cls}" for cls in CLASSES]].to_numpy(dtype=np.float32)
        verify("npy_float32", probabilities.dtype == np.float32)
        verify("npy_shape", probabilities.shape == (2868, 10))
        verify("npy_finite", bool(np.isfinite(probabilities).all()))
        verify("logits_finite", bool(np.isfinite(logits).all()))
        verify("csv_probabilities_finite", bool(np.isfinite(csv_probabilities).all()))
        verify("probabilities_range", bool(((probabilities >= 0) & (probabilities <= 1)).all()))
        verify("probabilities_sum_one", bool(np.allclose(probabilities.sum(axis=1), 1, atol=2e-6, rtol=0)))
        verify("csv_npy_float32_roundtrip_equal", np.array_equal(csv_probabilities, probabilities))
        exp_logits = np.exp(logits - logits.max(axis=1, keepdims=True))
        independently_softmaxed = exp_logits / exp_logits.sum(axis=1, keepdims=True)
        max_softmax_difference = float(np.abs(independently_softmaxed - probabilities).max())
        verify("logits_softmax_matches_probabilities", bool(np.allclose(independently_softmaxed, probabilities, atol=3e-7, rtol=2e-6)), max_softmax_difference)
        verify("argmax_matches_saved_prediction", np.array_equal(predicted, probabilities.argmax(axis=1)))
        verify("logit_argmax_matches_saved_prediction", np.array_equal(predicted, logits.argmax(axis=1)))
        confusion = np.zeros((10, 10), dtype=np.int64)
        np.add.at(confusion, (y, predicted), 1)
        support = confusion.sum(axis=1)
        predicted_support = confusion.sum(axis=0)
        tp = confusion.diagonal()
        precision = np.divide(tp, predicted_support, out=np.zeros(10), where=predicted_support != 0)
        recall = np.divide(tp, support, out=np.zeros(10), where=support != 0)
        class_f1 = np.divide(2 * precision * recall, precision + recall, out=np.zeros(10), where=(precision + recall) != 0)
        accuracy = float(tp.sum() / len(y))
        macro_f1 = float(class_f1.mean())
        # Keep the original NPY float32 scorer input. CSV float64 would change
        # epsilon clipping, producing misleading log-loss mismatches.
        scored_log_loss = float(log_loss(y, probabilities, labels=list(range(10))))
        clipped = np.clip(probabilities, np.finfo(np.float32).eps, 1 - np.finfo(np.float32).eps)
        manual_log_loss = float((-np.log(clipped[np.arange(len(y)), y])).mean())
        verify("metric_status", metrics["status"] == "COMPLETED")
        verify("metric_scope", metrics["interpretation"] == "FORMAL_VALIDATION_ONLY" and metrics["formal_comparison_valid"] is True)
        verify("metric_sample_counts", (metrics["samples"], metrics["train_samples"], metrics["validation_samples"]) == (2868, 15899, 2868))
        verify("metric_accuracy_recomputed", close(accuracy, metrics["accuracy"]))
        verify("metric_macro_f1_recomputed", close(macro_f1, metrics["macro_f1"]))
        verify("metric_log_loss_float32_recomputed", close(scored_log_loss, metrics["log_loss"]))
        verify("metric_log_loss_independent_clipped_formula", close(manual_log_loss, metrics["log_loss"], atol=2e-7, rtol=1e-6), manual_log_loss)
        verify("metric_confusion_matrix_recomputed", np.array_equal(confusion, np.asarray(metrics["confusion_matrix"])))
        verify("report_class_keys_order", list(report) == CLASSES + ["accuracy", "macro avg", "weighted avg"])
        for i, cls in enumerate(CLASSES):
            for field, expected in [("precision", precision[i]), ("recall", recall[i]), ("f1-score", class_f1[i]), ("support", support[i])]:
                verify(f"class_report_{cls}_{field}", close(report[cls][field], expected))
        verify("report_accuracy", close(report["accuracy"], accuracy))
        for avg, weights in [("macro avg", np.ones(10) / 10), ("weighted avg", support / support.sum())]:
            for field, values in [("precision", precision), ("recall", recall), ("f1-score", class_f1)]:
                verify(f"report_{avg}_{field}", close(report[avg][field], float(np.dot(values, weights))))
            verify(f"report_{avg}_support", report[avg]["support"] == 2868)
        epochs = metrics["epochs"]
        n_epochs = len(epochs)
        verify("epochs_range", 1 <= n_epochs <= 8 and metrics["epochs_completed"] == n_epochs)
        verify("epoch_numbers_contiguous", [e["epoch"] for e in epochs] == list(range(1, n_epochs + 1)))
        verify("epoch_values_finite", all(math.isfinite(v) for e in epochs for v in e.values()))
        verify("best_epoch_first_maximum_macro_f1", metrics["best_epoch"] == int(np.argmax([e["macro_f1"] for e in epochs])) + 1)
        verify("best_epoch_metric_equal_final_saved", close(epochs[metrics["best_epoch"] - 1]["macro_f1"], macro_f1))
        verify("timing_phases", set(timing.phase) == {"train", "validation", "reload_validation"})
        verify("timing_seconds_finite_positive", bool((np.isfinite(timing.seconds) & (timing.seconds > 0)).all()))
        verify("timing_resources", bool((timing.device == "mps").all() and (timing.threads == 2).all() and (timing.batch == 64).all()))
        verify("timing_epoch_range", set(timing.epoch) == set(range(1, n_epochs + 1)))
        for epoch in range(1, n_epochs + 1):
            for phase, count, steps in [("train", 15899, 249), ("validation", 2868, 45)]:
                t = timing.loc[(timing.epoch == epoch) & (timing.phase == phase)]
                verify(f"epoch_{epoch}_{phase}_full_samples", int(t.samples.sum()) == count)
                verify(f"epoch_{epoch}_{phase}_step_count_order", len(t) == steps and np.array_equal(t.step.to_numpy(), np.arange(1, steps + 1)))
                verify(f"epoch_{epoch}_{phase}_batch_sizes", bool(((t.samples > 0) & (t.samples <= 64)).all()))
        reload_timing = timing.loc[timing.phase == "reload_validation"]
        verify("recorded_reload_shape", len(reload_timing) == 1 and int(reload_timing.samples.iloc[0]) == 16)
        verify("reload_recorded_verified", metrics["reload_verified"] is True and metrics["reload_samples"] == 16 and math.isfinite(metrics["reload_max_abs_logit_difference"]) and metrics["reload_max_abs_logit_difference"] <= 1e-5)
        verify("zero_test_access_recorded", metrics["test_predictions"] == 0 and metrics["test_images_opened"] == 0)
        own_checks = checks[start_checks:]
        summary = {"attempt": label, "checks": len(own_checks), "failures": sum(not c["passed"] for c in own_checks),
                   "accuracy": accuracy, "macro_f1": macro_f1, "log_loss_float32": scored_log_loss,
                   "epochs_completed": n_epochs, "best_epoch": metrics["best_epoch"],
                   "train_driver_ids": sorted(training.driver_id.unique().tolist()),
                   "validation_driver_ids": sorted(validation.driver_id.unique().tolist()),
                   "class_support": support.tolist(), "max_softmax_absolute_difference": max_softmax_difference}
        summaries.append(summary)
        print("ATTEMPT", json.dumps(summary, sort_keys=True))
    for relative, record in before.items():
        check(f"read_only_input_unchanged:{relative}", sha256(RUN / relative) == record["sha256"])
    failures = sum(not c["passed"] for c in checks)
    result = {"status": "VERIFIED_PASS" if failures == 0 else "FAILED", "checks": len(checks),
              "failures": failures, "check_count_definition": "One count per assertion, including vectorized assertions; no multiplication by cells or samples.",
              "attempts_audited": len(summaries), "validation_predictions_audited": 2868 * len(summaries),
              "input_files_hashed_before_after": len(before), "runtime_seconds": time.monotonic() - started,
              "no_fit_or_forward_executed": True, "no_checkpoint_loaded": True,
              "no_test_images_or_test_csv_opened": True,
              "reload_limitation": "Only existing reload records checked; no model inference repeated by this audit.",
              "source_provenance_limitation": "Cross-attempt frozen manifests and driver separation checked; source images and external source CSVs not reopened.",
              "validator_development_note": "Initial validator assumed split-local contiguous source_row and raised 32 false flags. Inspection of load_vision and train_hpo confirmed preserved full-metadata indices; changed validator to check unique, ordered, non-negative original indices. initial_validator.log preserves the initial output. No audited input changed.",
              "float32_log_loss_note": "Scorer consumes original float32 NPY; CSV floats are round-tripped to float32 before equality checks.",
              "software": {"python": platform.python_version(), "numpy": np.__version__, "pandas": pd.__version__, "scikit-learn": sklearn.__version__},
              "command": "./.venv/bin/python -B " + str(Path(__file__).resolve()),
              "trial_summaries": summaries, "check_results": checks}
    dump("config.json", result)
    manifest = {"status": result["status"], "input_files_unchanged": before,
                "verification_artifacts": {name: {"sha256": sha256(OUT / name), "bytes": (OUT / name).stat().st_size}
                                           for name in ["verify_predictions.py", "config.json"]}}
    dump("artifact_manifest.json", manifest)
    print("PREDICTION_AUDIT", result["status"], "checks", len(checks), "failures", failures,
          "attempts", len(summaries), "saved_predictions", result["validation_predictions_audited"])
    return int(failures != 0)


if __name__ == "__main__":
    sys.exit(main())
