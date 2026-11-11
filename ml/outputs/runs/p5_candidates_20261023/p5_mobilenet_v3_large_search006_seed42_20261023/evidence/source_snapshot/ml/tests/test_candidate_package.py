"""Candidate delivery boundaries: reject unusable or unsafe evidence packages."""
import hashlib
import importlib
import importlib.util
import io
import json
from pathlib import Path
import sqlite3
import subprocess

import numpy as np
import onnx
from onnx import TensorProto, helper
import pytest


def api():
    return importlib.import_module("ml.experiments.package_candidates")


@pytest.fixture
def contract(tmp_path):
    for name in ("runtime_manifest.py", "runtime_manifest.schema.json"):
        (tmp_path / name).write_bytes(subprocess.check_output(
            ["git", "show", f"2745348:backend/app/{name}"]))
    spec = importlib.util.spec_from_file_location("candidate_contract_test", tmp_path / "runtime_manifest.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def graph(path, *, softmax=False, dynamic=True):
    batch = "N" if dynamic else 1
    x = helper.make_tensor_value_info("input", TensorProto.FLOAT, [batch, 3, 224, 224])
    y = helper.make_tensor_value_info("logits", TensorProto.FLOAT, [batch, 10])
    # Static checker only: a tiny valid graph, never executed.
    nodes = [helper.make_node("GlobalAveragePool", ["input"], ["pool"]),
             helper.make_node("Flatten", ["pool"], ["flat"]),
             helper.make_node("MatMul", ["flat", "weight"], ["raw" if softmax else "logits"])]
    if softmax:
        nodes.append(helper.make_node("Softmax", ["raw"], ["logits"], axis=1))
    weight = helper.make_tensor("weight", TensorProto.FLOAT, [3, 10], [0.0] * 30)
    onnx.save(helper.make_model(helper.make_graph(nodes, "fixture", [x], [y], [weight]),
                               opset_imports=[helper.make_opsetid("", 17)]), path)


def package(tmp_path):
    root = tmp_path / "candidate"
    root.mkdir()
    graph(root / "model.onnx")
    manifest = {"manifest_version": 1, "kind": "vision_classifier", "run_id": "candidate",
                "architecture": "resnet18", "model": {"path": "model.onnx", "format": "onnx",
                "sha256": hashlib.sha256((root / "model.onnx").read_bytes()).hexdigest()},
                "input": {"shape": [1, 3, 224, 224], "dtype": "float32", "layout": "NCHW", "color": "RGB"},
                "preprocess": "rgb_resize_224_bilinear_no_crop_div255_imagenet",
                "output": {"kind": "logits", "shape": [1, 10]}, "classes": [f"c{i}" for i in range(10)],
                "class_to_idx": {f"c{i}": i for i in range(10)}, "safe_class": "c0",
                "contract_smoke_set": {"split": "val", "selection": "filename per class first20", "n": 200,
                "sample_ids_sha256": "6" * 64, "rule": "per_class_mode_equals_label"}}
    (root / "runtime_manifest.json").write_text(json.dumps(manifest))
    # These files are actual required delivery evidence, not optional attachments.
    names = ["evaluation_metrics.json", "model_card.md", "class_metadata.json", "predictions_test_clean.csv",
             "validation/predictions_validation.csv", "validation/validation_metrics.json", "validation/class_report.json",
             "validation/stable200_annotations.csv", "validation/stable200_saved_predictions.csv",
             "validation/saved_prediction_diagnostic.json", "validation/p4a100_parity.json", "validation/p4a100_annotations.json",
             "evidence/source_config.json", "evidence/selection_log.json", "evidence/source_export_benchmark_manifest.json",
             "evidence/p4b_completion.json", "evidence/provenance.json", "evidence/source_hashes.json"]
    for name in names:
        target = root / name
        target.parent.mkdir(exist_ok=True)
        target.write_text("{}")
    seal(root)
    return root


def seal(root):
    files = {p.relative_to(root).as_posix(): {"sha256": hashlib.sha256(p.read_bytes()).hexdigest(), "bytes": p.stat().st_size}
             for p in root.rglob("*") if p.is_file() and p.name != "artifact_manifest.json"}
    (root / "artifact_manifest.json").write_text(json.dumps({"files": files}))


def test_valid_self_contained_delivery_passes(tmp_path, contract):
    result = api().validate_candidate(package(tmp_path), contract)
    assert result["status"] == "PASS"
    assert result["provider_load_forward"] == "NOT_RUN"


@pytest.mark.parametrize("missing", ["validation/predictions_validation.csv", "evidence/selection_log.json", "predictions_test_clean.csv"])
def test_missing_delivery_evidence_is_rejected(tmp_path, contract, missing):
    root = package(tmp_path)
    (root / missing).unlink()
    seal(root)
    with pytest.raises(ValueError, match="required"):
        api().validate_candidate(root, contract)


@pytest.mark.parametrize("change", ["metric", "class", "run", "escape", "hash"])
def test_loading_contract_errors_reject_package(tmp_path, contract, change):
    root = package(tmp_path)
    f = root / "runtime_manifest.json"
    m = json.loads(f.read_text())
    if change == "metric": m["provenance"] = {"nested": [{"macro_f1": 0.9}]}
    if change == "class": m["class_to_idx"]["c0"] = 1
    if change == "run": m["run_id"] = "other"
    if change == "escape": m["model"]["path"] = "../outside.onnx"
    if change == "hash": m["model"]["sha256"] = "0" * 64
    f.write_text(json.dumps(m)); seal(root)
    with pytest.raises(ValueError): api().validate_candidate(root, contract)


@pytest.mark.parametrize("unsafe", ["symlink", "checkpoint.joblib", "checkpoint.pt", "comparator.pkl", "random_forest/model.json", "logistic_regression/model.json"])
def test_forbidden_delivery_files_rejected(tmp_path, contract, unsafe):
    root = package(tmp_path)
    if unsafe == "symlink": (root / "alias.json").symlink_to(root / "evaluation_metrics.json")
    else:
        p = root / unsafe; p.parent.mkdir(exist_ok=True); p.write_bytes(b"not loaded")
    seal(root)
    with pytest.raises(ValueError): api().validate_candidate(root, contract)


def test_evidence_tamper_and_inventory_escape_rejected(tmp_path, contract):
    root = package(tmp_path)
    (root / "evaluation_metrics.json").write_text('{"changed":true}')
    with pytest.raises(ValueError, match="hash|integrity"): api().validate_candidate(root, contract)
    seal(root)
    p = root / "artifact_manifest.json"; m = json.loads(p.read_text())
    m["files"]["../secret"] = {"sha256": "0" * 64, "bytes": 0}; p.write_text(json.dumps(m))
    with pytest.raises(ValueError, match="path|inventory"): api().validate_candidate(root, contract)


@pytest.mark.parametrize("kind", ["softmax", "fixed_batch"])
def test_graph_contract_requires_dynamic_raw_logits(tmp_path, kind):
    p = tmp_path / "model.onnx"; graph(p, softmax=kind == "softmax", dynamic=kind != "fixed_batch")
    with pytest.raises(ValueError): api().check_onnx_graph(p)


def cache_fixture(tmp_path, tamper=False):
    db = tmp_path / "cache.sqlite3"; conn = sqlite3.connect(db)
    conn.execute("create table meta (key text,value text)")
    conn.execute("insert into meta values ('manifest',?)", (json.dumps({"schema": 2, "identities": {"RN-HPO42": "a" * 64}}),))
    conn.execute("create table predictions (identity text,source_id text,condition text,input_sha text,label integer,status text,payload blob,payload_sha text,detail text)")
    out = io.BytesIO(); np.save(out, np.array([1., 2., 0., 0., 0., 0., 0., 0., 0., 0.], dtype=np.float32), allow_pickle=False)
    payload = out.getvalue()
    metadata = {"identity": "RN-HPO42", "checkpoint_sha256": "a" * 64, "source_id": "vision-v1:c0/a.jpg",
                "condition": "clean", "input_sha256": "b" * 64, "label": 0}
    digest = hashlib.sha256(json.dumps(metadata, sort_keys=True, separators=(",", ":")).encode() + payload).hexdigest()
    conn.execute("insert into predictions values (?,?,?,?,?,?,?,?,?)", ("RN-HPO42", "vision-v1:c0/a.jpg", "clean", "b" * 64, 0, "COMPLETED", payload, "0" * 64 if tamper else digest, None))
    conn.commit(); conn.close()
    return db


def test_cache_extract_is_readonly_preserves_logits_and_checks_counts(tmp_path):
    db = cache_fixture(tmp_path); before = db.read_bytes()
    rows = api().read_cached_predictions(db, "RN-HPO42", "a" * 64, "clean", 1)
    assert rows[0]["logit_c0"] == 1.0
    assert rows[0]["predicted_label_index"] == 1
    assert len(rows) == 1 and db.read_bytes() == before
    with pytest.raises(ValueError, match="count"): api().read_cached_predictions(db, "RN-HPO42", "a" * 64, "clean", 2)


def test_cache_tamper_rejected_before_delivery(tmp_path):
    with pytest.raises(ValueError, match="SHA|tamper"):
        api().read_cached_predictions(cache_fixture(tmp_path, True), "RN-HPO42", "a" * 64, "clean", 1)


def test_smoke_membership_uses_filename_order_and_labels_saved_diagnostic():
    rows = [{"filename": f"{name}.jpg", "class_id": f"c{i}", "class_name": "normal_driving" if i == 0 else "action",
             "driver_id": "driver", "split": split} for i in range(10) for name, split in [("b", "val"), ("a", "val"), ("0", "test")]]
    predictions = [{"source_id": f"vision-v1:c{i}/a.jpg", "true_label_index": str(i), "predicted_label_index": str(i)} for i in range(10)]
    annotations, saved, diagnostic = api().stable_smoke(rows, predictions, per_class=1)
    assert [r["filename"] for r in annotations] == ["a.jpg"] * 10
    assert len(saved) == 10
    assert diagnostic["scope"] == "SAVED_VALIDATION_PREDICTION_DIAGNOSTIC"
    assert diagnostic["provider_load_forward"] == "NOT_RUN"
    assert diagnostic["official_behavior_check"] == "NOT_RUN"


def test_archive_is_repeatable_and_contains_package_root(tmp_path):
    root = package(tmp_path)
    a, b = tmp_path / "a.zip", tmp_path / "b.zip"
    api().deterministic_zip(root, a); api().deterministic_zip(root, b)
    assert a.read_bytes() == b.read_bytes()
