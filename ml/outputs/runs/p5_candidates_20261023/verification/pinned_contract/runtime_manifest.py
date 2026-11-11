"""The runtime manifest of a vision classifier package (Task 10A, handed to the ML track in W5).

Structure is the JSON Schema next to this file (``runtime_manifest.schema.json``); the rules a
schema cannot state are checked here: the class index order, the safe class, the output width,
a model path that stays inside its package, and - for a package on disk - the file's SHA-256.
Every check returns plain-language errors; an empty list means valid. Nothing is loaded or run.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path, PurePosixPath

SCHEMA_PATH = Path(__file__).with_name("runtime_manifest.schema.json")
SUPPORTED_PREPROCESS = "rgb_resize_224_bilinear_no_crop_div255_imagenet"
# Words that mark an evaluation metric. Metrics live in evaluation_metrics.json; the free-form
# ``provenance`` object must not smuggle them in (matched on whole words of each key, any depth).
METRIC_WORDS = frozenset({"f1", "accuracy", "acc", "precision", "recall", "auc", "ece", "brier", "nll", "loss",
                          "metric", "metrics", "score", "mae", "mse", "rmse"})


def _metric_keys(value, path: str = "provenance") -> list[str]:
    found = []
    if isinstance(value, dict):
        for key, inner in value.items():
            where = f"{path}.{key}"
            if METRIC_WORDS & set(re.split(r"[^a-z0-9]+", str(key).lower())):
                found.append(where)
            found += _metric_keys(inner, where)
    elif isinstance(value, list):
        for index, inner in enumerate(value):
            found += _metric_keys(inner, f"{path}[{index}]")
    return found


def _schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text())


def validate_manifest(manifest: dict) -> list[str]:
    """Errors in the manifest itself (no files are read)."""
    from jsonschema import Draft202012Validator

    errors = []
    for error in sorted(Draft202012Validator(_schema()).iter_errors(manifest), key=lambda e: list(e.path)):
        where = ".".join(str(p) for p in error.path) or "(top level)"
        if error.validator == "additionalProperties":
            extra = sorted(set(error.instance) - set(error.schema.get("properties", {})))
            errors.append(f"{where}: keys not allowed in a runtime manifest: {', '.join(extra)}"
                          " (evaluation metrics go in evaluation_metrics.json)")
        else:
            errors.append(f"{where}: {error.message}")
    if errors:
        return errors
    path = manifest["model"]["path"]
    parts = PurePosixPath(path).parts
    if path.startswith("/") or "\\" in path or ".." in parts or not parts:
        errors.append(f"model.path: {path!r} must be a relative path inside the package (no '..', not absolute)")
    classes = manifest["classes"]
    expected = {name: index for index, name in enumerate(classes)}
    if manifest["class_to_idx"] != expected:
        errors.append(f"class_to_idx: must give each class its index in 'classes' ({expected}), got {manifest['class_to_idx']}")
    if manifest["safe_class"] not in classes:
        errors.append(f"safe_class: {manifest['safe_class']!r} is not one of the classes")
    if manifest["output"]["shape"][1] != len(classes):
        errors.append(f"output.shape: {manifest['output']['shape'][1]} outputs for {len(classes)} classes")
    for where in _metric_keys(manifest.get("provenance", {})):
        errors.append(f"{where}: looks like an evaluation metric; metrics go in evaluation_metrics.json, not the manifest")
    return errors


def validate_package(manifest: dict, package_dir: Path) -> list[str]:
    """``validate_manifest`` plus the model file of a package on disk: present, inside the package
    after resolving symbolic links, and matching its SHA-256."""
    errors = validate_manifest(manifest)
    if errors:
        return errors
    root = Path(package_dir).resolve()
    if manifest["run_id"] != root.name:
        errors.append(f"run_id: {manifest['run_id']!r} must be the package directory name {root.name!r}")
    model = Path(package_dir) / manifest["model"]["path"]
    if not model.exists():
        return [f"model.path: {manifest['model']['path']!r} is missing from {package_dir}"]
    real = model.resolve()
    if root != real and root not in real.parents:
        return errors + [f"model.path: {manifest['model']['path']!r} resolves to {real}, outside the package {root}"]
    if not real.is_file():
        return errors + [f"model.path: {manifest['model']['path']!r} is not a file"]
    digest = hashlib.sha256(real.read_bytes()).hexdigest()
    if digest != manifest["model"]["sha256"]:
        errors.append(f"model.sha256 mismatch: the manifest says {manifest['model']['sha256']}, the file is {digest}")
    return errors
