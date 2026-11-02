"""DMD candidate evidence, item A: source-domain and adapted-domain evaluation.

These tests pin what the runner measures before it runs on any image:
the pre-declared protocol, the two frozen input lists, the metric definitions and the
cross-checks against the archived 2026-10-29 / p4b numbers.

The runner is ``scripts/dmd_candidate_eval.py`` (loaded lazily so a missing file is a
failure of the tests that need it, not a collection error).
"""
import csv
import hashlib
import importlib.util
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "scripts"
PROTOCOL_PATH = REPO / "docs" / "fyp2" / "dmd-candidate" / "protocol.json"


def load_runner():
    path = SCRIPTS / "dmd_candidate_eval.py"
    assert path.is_file(), f"missing runner {path}"
    spec = importlib.util.spec_from_file_location("_dmd_candidate_eval", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def runner():
    return load_runner()


@pytest.fixture(scope="module")
def protocol():
    return json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))


def _jpg(tmp_path, name="img.jpg", payload=b"\xff\xd8fakejpeg"):
    path = tmp_path / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path


def _source(tmp_path, source_id="vision-v1:c0/img_1.jpg", class_id="c0", split="test", **extra):
    path = _jpg(tmp_path, name=source_id.split(":", 1)[1])
    row = {"source_id": source_id, "class_id": class_id, "split": split,
           "image_path": str(path), "filename": path.name,
           "source_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    row.update(extra)
    return row


# ------------------------------------------------------------------- protocol facts
def test_protocol_is_predeclared_descriptive_and_pins_the_operative_threshold(protocol):
    assert protocol["status"] == "PREDECLARED"
    assert protocol["decision_rule"] == "DESCRIPTIVE_ONLY"
    a = protocol["a_source_domain"]
    assert a["state_farm_test"]["expected_records"] == 3657
    assert a["state_farm_test"]["expected_drivers"] == ["p012", "p026", "p035", "p050"]
    assert a["dmd_body_test"]["expected_records"] == 1354
    assert a["dmd_body_test"]["operative_threshold"] == 0.5
    assert a["dmd_body_test"]["non_operative_threshold"] == 0.7037721940337633
    assert "not used by the runtime" in protocol["c_threshold_semantics"]["fact"]


# --------------------------------------------------------- State Farm frozen list
def test_state_farm_loader_accepts_the_declared_shape(runner, tmp_path):
    rows = [_source(tmp_path, "vision-v1:c0/a.jpg", "c0"),
            _source(tmp_path, "vision-v1:c1/b.jpg", "c1")]
    path = tmp_path / "sources.json"
    path.write_text(json.dumps(rows))
    loaded = runner.load_state_farm_sources(path)
    assert [r["source_id"] for r in loaded] == ["vision-v1:c0/a.jpg", "vision-v1:c1/b.jpg"]


def test_state_farm_loader_refuses_non_test_duplicates_and_missing_files(runner, tmp_path):
    good = _source(tmp_path, "vision-v1:c0/a.jpg", "c0")
    train = _source(tmp_path, "vision-v1:c0/b.jpg", "c0", split="train")
    duplicate = dict(good)
    path = tmp_path / "sources.json"
    path.write_text(json.dumps([good, train, duplicate]))
    with pytest.raises(ValueError, match="split"):
        runner.load_state_farm_sources(path)
    path.write_text(json.dumps([good, duplicate]))
    with pytest.raises(ValueError, match="duplicate"):
        runner.load_state_farm_sources(path)
    missing = dict(good, source_id="vision-v1:c0/missing.jpg", image_path=str(tmp_path / "nope.jpg"))
    path.write_text(json.dumps([missing]))
    with pytest.raises(ValueError, match="missing"):
        runner.load_state_farm_sources(path)


def test_state_farm_validation_pins_the_protocol_counts(runner, tmp_path, protocol):
    expected = dict(protocol["a_source_domain"]["state_farm_test"])
    rows = [_source(tmp_path, "vision-v1:c0/a.jpg", "c0")]
    problems = runner.state_farm_problems(rows, expected)
    assert any("3657" in p for p in problems)
    assert any("driver" in p for p in problems)
    assert any("class" in p for p in problems)


def test_state_farm_image_hashes_are_checked_against_the_frozen_list(runner, tmp_path, protocol):
    rows = [_source(tmp_path, "vision-v1:c0/a.jpg", "c0")]
    assert runner.verify_image_hashes(rows) == []
    rows[0]["source_sha256"] = "0" * 64
    assert runner.verify_image_hashes(rows)[0]["source_id"] == "vision-v1:c0/a.jpg"


# --------------------------------------------------------------- DMD test list
def _write_dmd_csv(tmp_path, rows):
    path = tmp_path / "sampling_manifest.csv"
    fields = ["subject", "session", "split", "action", "class_id", "annotation_frame_idx",
              "body_frame_idx", "effective_shift", "video", "file"]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows([{f: row.get(f, "") for f in fields} for row in rows])
    return path


def test_dmd_loader_keeps_only_the_test_split(runner, tmp_path):
    path = _write_dmd_csv(tmp_path, [
        {"subject": "gC_13", "split": "test", "class_id": "c0", "file": "gC_13/c0/0.jpg"},
        {"subject": "gA_1", "split": "train", "class_id": "c1", "file": "gA_1/c1/0.jpg"},
        {"subject": "gE_29", "split": "test", "class_id": "c2", "file": "gE_29/c2/0.jpg"},
    ])
    rows = runner.load_dmd_test_rows(path)
    assert [r["subject"] for r in rows] == ["gC_13", "gE_29"]


def test_dmd_validation_pins_the_protocol_counts_and_class_ids(runner, tmp_path, protocol):
    expected = dict(protocol["a_source_domain"]["dmd_body_test"])
    rows = [{"subject": "gC_13", "class_id": "c0", "file": "a.jpg"},
            {"subject": "gC_13", "class_id": "cX", "file": "b.jpg"}]
    problems = runner.dmd_problems(rows, expected)
    assert any("1354" in p for p in problems)
    assert any("class" in p for p in problems)


# -------------------------------------------------------------------- metrics
def _probs(classes, n=10):
    out = []
    for label in classes:
        row = [0.0] * n
        row[label] = 0.9
        rest = 0.1 / (n - 1)
        out.append([rest if i != label else 0.9 for i in range(n)])
    return out


def test_binary_diagnostic_counts_the_c0_false_positive_proxy(runner):
    labels = [0, 0, 1, 9]
    probs = _probs([0, 1, 1, 9])
    diag = runner.binary_diagnostic(labels, probs, 0.5)
    assert diag["threshold"] == 0.5
    assert diag["c0_false_positive_proxy"] == 0.5  # one of the two true c0 frames
    assert diag["distraction_recall"] == 1.0
    assert diag["binary_accuracy"] == 0.75
    assert diag["counts"] == {"tp": 2, "fp": 1, "fn": 0, "tn": 1}


def test_multiclass_log_loss_and_per_class_metrics(runner):
    labels = list(range(10))
    probs = _probs(labels)
    summary = runner.summarise(labels, probs, {"0.5": 0.5})
    assert summary["multiclass"]["accuracy"] == 1.0
    assert summary["multiclass"]["macro_f1"] == 1.0
    assert summary["multiclass"]["log_loss"] == pytest.approx(-math.log(0.9), abs=1e-12)
    assert [summary["multiclass"]["per_class"][f"c{i}"]["support"] for i in range(10)] == [1] * 10
    assert summary["multiclass"]["per_class"]["c3"]["recall"] == 1.0
    assert len(summary["multiclass"]["confusion_matrix"]) == 10


def test_summary_keeps_all_declared_threshold_columns(runner):
    labels = [0, 1]
    probs = _probs([0, 1])
    summary = runner.summarise(labels, probs, {"0.5": 0.5, "0.7037721940337633": 0.7037721940337633})
    assert set(summary["binary"]) == {"0.5", "0.7037721940337633"}
    assert summary["binary"]["0.5"]["c0_false_positive_proxy"] == 0.0
    assert summary["binary"]["0.7037721940337633"]["c0_false_positive_proxy"] == 0.0


# ----------------------------------------------------------------- cross-checks
def test_cross_check_reports_only_real_mismatches(runner):
    actual = {"accuracy": 0.8988241728192508, "macro_f1": 0.8746408408872671,
              "log_loss": 0.5744531434764406}
    assert runner.cross_check(actual, actual) == []
    moved = dict(actual, log_loss=0.6)
    mismatch = runner.cross_check(moved, actual)
    assert len(mismatch) == 1 and mismatch[0]["metric"] == "log_loss"


def test_cross_check_reads_the_archived_files_by_their_declared_paths(runner):
    assert runner.ARCHIVE_ZERO_SHOT.is_file()
    assert runner.ARCHIVE_COMPARISON.is_file()
    assert runner.P4B_METRICS.is_file()


def test_zero_shot_archive_metrics_come_from_its_labels_and_probabilities(runner):
    archive = {"labels": [0, 1, 1, 2], "probabilities": _probs([0, 1, 1, 9])}
    metrics = runner.archive_zero_shot_metrics(archive)
    assert metrics["accuracy"] == 0.75
    # sklearn's unlabelled macro average covers the four classes present: c0/c1 are perfect,
    # c2/c9 score zero -> (1 + 1 + 0 + 0) / 4.
    assert metrics["macro_f1"] == pytest.approx(0.5)


# ------------------------------------------------------------------ protocol gate
def test_the_gate_blocks_a_protocol_not_committed_first(runner):
    start = datetime(2026, 11, 2, 12, 0, tzinfo=timezone.utc)
    assert runner.gate_verdict(dirty=False, commit="abc", commit_time="2026-11-02T08:00:00+00:00",
                               blob_matches=True, run_start=start) == []
    assert runner.gate_verdict(dirty=True, commit="abc", commit_time="2026-11-02T08:00:00+00:00",
                               blob_matches=True, run_start=start)
    assert runner.gate_verdict(dirty=False, commit=None, commit_time=None,
                               blob_matches=True, run_start=start)
    assert runner.gate_verdict(dirty=False, commit="abc", commit_time="2026-11-02T13:00:00+00:00",
                               blob_matches=True, run_start=start)
