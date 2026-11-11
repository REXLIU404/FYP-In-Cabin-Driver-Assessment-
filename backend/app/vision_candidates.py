"""Task 10A: load a P5 vision candidate from its package, driven by the package's runtime manifest.

The stable MobileNetV3 path in ``providers/trained.py`` is not touched by this module. A candidate is
named by a model id in ``<candidates_root>/index.json``; its package directory holds
``runtime_manifest.json`` (manifest v1, checked by the shared validator in ``runtime_manifest.py``),
``model.onnx`` and ``class_metadata.json``. Every check that fails raises ``ModelUnavailable`` with
the plain reason - there is no fallback to another model, ever: a refused candidate is reported
as unavailable (HTTP 503 ``models_unavailable``), never replaced in silence.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .runtime_manifest import SUPPORTED_PREPROCESS, validate_package

CLASSES = [f"c{i}" for i in range(10)]
SAFE_ALIAS = "safe_driving"  # the runtime name of c0; P_distraction = 1 - P(c0)
MEAN = [0.485, 0.456, 0.406]
STD = [0.229, 0.224, 0.225]


def _unavailable(message: str):
    from .providers.trained import ModelUnavailable  # imported late: trained.py imports this module lazily

    return ModelUnavailable(message)


@dataclass
class CandidateVision:
    model_id: str            # e.g. "resnet18_search004_seed42"
    run_id: str              # the package directory name, e.g. "p5_resnet18_search004_seed42_20261023"
    package_dir: Path        # resolved package directory
    session: object = field(repr=False)  # onnxruntime.InferenceSession
    input_name: str = ""
    labels: list[str] = field(default_factory=list)  # runtime names, c0..c9; labels[0] == "safe_driving"
    info: dict = field(default_factory=dict)         # the provider's info["vision"] for this model


def _read_json(path: Path, what: str, model_id: str) -> dict:
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        raise _unavailable(f"vision candidate '{model_id}': {what} is missing ({path})") from None
    except ValueError as exc:
        raise _unavailable(f"vision candidate '{model_id}': {what} is not valid JSON ({exc})") from None


def _package_dir(model_id: str, candidates_root: Path) -> Path:
    index_path = Path(candidates_root) / "index.json"
    if not index_path.exists():
        raise _unavailable(f"vision candidate '{model_id}' is not in {index_path} (no index.json)")
    index = _read_json(index_path, "index.json", model_id)
    entry = index.get(model_id)
    if not isinstance(entry, dict):
        raise _unavailable(f"vision candidate '{model_id}' is not in {index_path}")
    package = entry.get("package")
    if not isinstance(package, str) or not package or Path(package).name != package or package in (".", ".."):
        raise _unavailable(f"vision candidate '{model_id}': index package {package!r} must be a directory name "
                           f"inside {candidates_root}")
    return Path(candidates_root) / package


def _labels(metadata: dict, manifest: dict, model_id: str) -> list[str]:
    if metadata.get("classes") != manifest["classes"] or metadata.get("safe_class") != manifest["safe_class"]:
        raise _unavailable(f"vision candidate '{model_id}': class_metadata.json classes/safe_class do not "
                           "match runtime_manifest.json")
    training = metadata.get("training_labels") or {}
    aliases = metadata.get("runtime_aliases") or {}
    if set(training) != set(CLASSES) or not all(isinstance(training[c], str) and training[c] for c in CLASSES):
        raise _unavailable(f"vision candidate '{model_id}': class_metadata.json needs a training label for "
                           "each of c0..c9")
    labels = [aliases.get(c, training[c]) for c in CLASSES]
    if labels[0] != SAFE_ALIAS:
        raise _unavailable(f"vision candidate '{model_id}': c0 must carry the runtime alias '{SAFE_ALIAS}', "
                           f"got {labels[0]!r}")
    return labels


def load_candidate(model_id: str, candidates_root: Path, *, threads: int = 1) -> CandidateVision:
    """Validate the package of ``model_id`` and open its ONNX model, or raise ``ModelUnavailable``."""
    import numpy as np
    import onnxruntime as ort

    package_dir = _package_dir(model_id, candidates_root)
    manifest = _read_json(package_dir / "runtime_manifest.json", "runtime_manifest.json", model_id)
    errors = validate_package(manifest, package_dir)  # schema, class_to_idx, run_id, containment, sha256
    if errors:
        raise _unavailable(f"vision candidate '{model_id}': " + "; ".join(errors))
    # What the shared validator does not pin down, the runtime contract does.
    if manifest["classes"] != CLASSES or manifest["safe_class"] != "c0":
        raise _unavailable(f"vision candidate '{model_id}': classes must be c0..c9 in order with safe_class c0, "
                           f"got {manifest['classes']} / {manifest['safe_class']!r}")
    if manifest["preprocess"] != SUPPORTED_PREPROCESS:
        raise _unavailable(f"vision candidate '{model_id}': preprocess {manifest['preprocess']!r} is not "
                           f"the provider's {SUPPORTED_PREPROCESS!r}")
    labels = _labels(_read_json(package_dir / "class_metadata.json", "class_metadata.json", model_id),
                     manifest, model_id)

    opts = ort.SessionOptions()
    opts.intra_op_num_threads = threads
    opts.inter_op_num_threads = 1
    model_path = (package_dir / manifest["model"]["path"]).resolve()
    try:
        session = ort.InferenceSession(str(model_path), opts, providers=["CPUExecutionProvider"])
    except Exception as exc:  # onnxruntime raises its own exception types for a bad graph
        raise _unavailable(f"vision candidate '{model_id}': the ONNX model does not load ({exc})") from None
    inp = session.get_inputs()[0]
    if inp.type != "tensor(float)" or list(inp.shape[1:]) != [3, 224, 224]:
        raise _unavailable(f"vision candidate '{model_id}': expected a float32 NCHW 224x224 input, "
                           f"got {inp.type} {inp.shape}")
    try:
        output = session.run(None, {inp.name: np.zeros((1, 3, 224, 224), np.float32)})[0]
    except Exception as exc:
        raise _unavailable(f"vision candidate '{model_id}': warm-up forward failed ({exc})") from None
    if output.shape != (1, 10) or not np.isfinite(output).all():
        raise _unavailable(f"vision candidate '{model_id}': warm-up returned {output.shape}, "
                           "expected (1, 10) finite logits")
    run_id = manifest["run_id"]
    info = {"architecture": manifest["architecture"], "model_id": model_id, "run_id": run_id,
            "source": f"candidate:{run_id}", "sha256": manifest["model"]["sha256"],
            "runtime": "onnxruntime_cpu", "classes": labels, "input": "RGB NCHW float32 224x224",
            "mean": list(MEAN), "std": list(STD)}
    return CandidateVision(model_id=model_id, run_id=run_id, package_dir=package_dir.resolve(), session=session,
                           input_name=inp.name, labels=labels, info=info)
