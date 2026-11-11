"""Task 10A handoff (S4): the runtime manifest a candidate vision model package must carry.

The contract the ML track exports against: what the loader may rely on (file, hash, input,
the ONE supported preprocessing, logits out, class order, safe class, the contract smoke set)
and nothing else - evaluation metrics live in a separate file and are rejected here.
No model is loaded: these tests run anywhere.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from app.runtime_manifest import SUPPORTED_PREPROCESS, validate_manifest, validate_package

EXAMPLE = Path(__file__).resolve().parents[2] / "docs/fyp2/handoff/examples/stable-mobilenetv3.runtime_manifest.json"


def example() -> dict:
    return json.loads(EXAMPLE.read_text())


def test_the_stable_example_is_valid_and_describes_the_frozen_model():
    manifest = example()
    assert validate_manifest(manifest) == []
    assert manifest["model"]["sha256"] == "b3a42e8dd4553355b1fd7d9e7fe3d28e318decb894e76eb029489b7ff2e90bcf"
    assert manifest["preprocess"] == SUPPORTED_PREPROCESS == "rgb_resize_224_bilinear_no_crop_div255_imagenet"
    assert manifest["classes"] == [f"c{i}" for i in range(10)] and manifest["safe_class"] == "c0"


def _set(manifest: dict, path: str, value) -> dict:
    out = copy.deepcopy(manifest)
    *parents, last = path.split(".")
    node = out
    for key in parents:
        node = node[key]
    if value is _DELETE:
        del node[last]
    else:
        node[last] = value
    return out


_DELETE = object()

REJECTED = [
    ("preprocess", "resize256_centercrop224_imagenet", "preprocess"),       # ResNet-style crop: a different input
    ("output.kind", "probabilities", "logits"),                              # would be softmaxed twice
    ("model.path", "../stable/model.onnx", "path"),                          # escapes the package
    ("model.path", "/Users/x/model.onnx", "path"),                           # absolute
    ("model.sha256", _DELETE, "sha256"),
    ("model.sha256", "b3a42e8d", "sha256"),                                  # not 64 hex digits
    ("macro_f1", 0.87, "macro_f1"),                                          # metrics are not a loading contract
    ("classes", ["c0", "c1", "c2", "c3", "c4", "c5", "c6", "c7", "c8", "c8"], "classes"),
    ("class_to_idx.c1", 2, "class_to_idx"),                                  # index order differs from classes
    ("safe_class", "c10", "safe_class"),
    ("contract_smoke_set.split", "test", "test"),                            # never the held-out test split
    ("output.shape", [1, 9], "classes"),                                     # 9 outputs for 10 classes
    ("input.shape", [1, 3, 256, 256], "input"),
]


@pytest.mark.parametrize("path,value,word", REJECTED, ids=[f"{p}={v!r}" for p, v, _ in REJECTED])
def test_a_manifest_that_breaks_the_contract_is_rejected_with_a_reason(path, value, word):
    errors = validate_manifest(_set(example(), path, value))
    assert errors, f"{path}={value!r} was accepted"
    assert any(word in error for error in errors), errors


def _package(tmp_path: Path, body: bytes = b"onnx bytes") -> tuple[Path, dict]:
    root = tmp_path / "run_001"
    root.mkdir()
    (root / "model.onnx").write_bytes(body)
    manifest = _set(example(), "model.path", "model.onnx")
    manifest["model"]["sha256"] = hashlib.sha256(body).hexdigest()
    manifest["run_id"] = root.name
    return root, manifest


def test_a_package_whose_file_matches_its_hash_is_valid(tmp_path):
    root, manifest = _package(tmp_path)
    assert validate_package(manifest, root) == []


def test_a_package_whose_file_does_not_match_its_hash_is_rejected(tmp_path):
    root, manifest = _package(tmp_path)
    (root / "model.onnx").write_bytes(b"replaced")
    assert any("sha256 mismatch" in e for e in validate_package(manifest, root))


def test_a_missing_model_file_is_rejected(tmp_path):
    root, manifest = _package(tmp_path)
    (root / "model.onnx").unlink()
    assert any("missing" in e for e in validate_package(manifest, root))


def test_a_symlink_that_leaves_the_package_is_rejected(tmp_path):
    root, manifest = _package(tmp_path)
    outside = tmp_path / "elsewhere.onnx"
    outside.write_bytes(b"onnx bytes")
    (root / "model.onnx").unlink()
    (root / "model.onnx").symlink_to(outside)
    assert any("outside the package" in e for e in validate_package(manifest, root))


# ---- final-review fix: the validator enforces what the handoff document promises -------------------
def _named_package(tmp_path: Path, run_id: str = "run_001") -> tuple[Path, dict]:
    root, manifest = _package(tmp_path)
    manifest["run_id"] = run_id
    return root, manifest


def test_a_model_path_that_is_a_directory_is_an_error_not_a_crash(tmp_path):
    root, manifest = _named_package(tmp_path)
    (root / "weights").mkdir()
    manifest["model"]["path"] = "weights"
    errors = validate_package(manifest, root)
    assert any("not a file" in e for e in errors), errors


@pytest.mark.parametrize("provenance", [{"macro_f1": 0.87}, {"notes": {"val_accuracy": 0.9}}, {"ECE": 0.02}],
                         ids=["macro_f1", "nested accuracy", "ECE"])
def test_evaluation_metrics_are_rejected_inside_provenance_too(provenance):
    manifest = example()
    manifest["provenance"] = provenance
    errors = validate_manifest(manifest)
    assert any("metric" in e for e in errors), errors


def test_the_run_id_must_be_the_package_directory_name(tmp_path):
    root, manifest = _named_package(tmp_path, run_id="some_other_run")
    assert any("run_id" in e for e in validate_package(manifest, root))
    manifest["run_id"] = root.name
    assert validate_package(manifest, root) == []


def test_the_cli_reports_invalid_json_without_a_traceback(tmp_path):
    import subprocess
    import sys

    bad = tmp_path / "runtime_manifest.json"
    bad.write_text("{ not json")
    script = Path(__file__).resolve().parents[2] / "scripts/validate_runtime_manifest.py"
    done = subprocess.run([sys.executable, str(script), str(bad)], capture_output=True, text=True)
    assert done.returncode == 1
    assert "not valid JSON" in done.stdout and "Traceback" not in done.stderr, (done.stdout, done.stderr)
