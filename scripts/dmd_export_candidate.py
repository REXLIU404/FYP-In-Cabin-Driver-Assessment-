"""Export the adapted checkpoint as a runtime candidate package.

The package layout is the one ``backend/app/vision_candidates.py`` already loads:
``model.onnx`` + ``runtime_manifest.json`` (manifest v1) + ``class_metadata.json``.
``provenance`` is a free-form object, but its key names may not look like evaluation
metrics - those belong in ``evaluation_metrics.json``.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

PREPROCESS = "rgb_resize_224_bilinear_no_crop_div255_imagenet"
CLASSES = [f"c{i}" for i in range(10)]


def _sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def build_manifest(*, run_id: str, model_sha256: str, parent_sha256: str,
                   smoke: dict) -> dict:
    return {
        "manifest_version": 1,
        "kind": "vision_classifier",
        "run_id": run_id,
        "architecture": "mobilenet_v3_large",
        "model": {"format": "onnx", "path": "model.onnx", "sha256": model_sha256},
        "input": {"color": "RGB", "dtype": "float32", "layout": "NCHW",
                  "shape": [1, 3, 224, 224]},
        "preprocess": PREPROCESS,
        "output": {"kind": "logits", "shape": [1, 10]},
        "classes": CLASSES,
        "class_to_idx": {name: index for index, name in enumerate(CLASSES)},
        "safe_class": "c0",
        "contract_smoke_set": smoke,
        "provenance": {
            "parent_model_sha256": parent_sha256,
            "source_dataset": "DMD body view (CC BY-NC-ND 4.0)",
            "training_labels": "DMD driver_actions mapped per label_mapping.json",
            "runtime_c0_alias": "safe_driving",
            "seed": 42,
            "graph_batch": "dynamic N",
            "input_name": "input",
            "output_name": "logits",
        },
    }


def export(checkpoint: Path, out_dir: Path, *, parent_sha256: str,
           smoke_n: int = 1, sample_ids_sha256: str = "0" * 64,
           smoke_selection: str = "gB_10 val frames grouped by class",
           model_factory=None) -> dict:
    """Write the package. ``smoke_n`` must be >= 1: the manifest schema rejects 0.

    ``model_factory`` exists so tests can inject a small same-shaped network; production
    always builds the real MobileNetV3. Building the real one a dozen times inside a
    long pytest process crashes torch 2.12 on macOS during ONNX export.
    """
    if smoke_n < 1:
        raise ValueError("smoke_n must be at least 1 (runtime manifest schema)")
    import torch
    from torchvision.models import mobilenet_v3_large

    factory = model_factory or (lambda: mobilenet_v3_large(weights=None, num_classes=10))
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    model = factory()
    model.load_state_dict(torch.load(checkpoint, map_location="cpu"))
    model.eval()

    onnx_path = out_dir / "model.onnx"
    # torch 2.12 defaults to the dynamo exporter, which needs an extra `onnxscript`
    # dependency. The legacy exporter emits the same opset-17 graph and keeps the
    # environment unchanged.
    torch.onnx.export(model, torch.zeros(1, 3, 224, 224), str(onnx_path),
                      input_names=["input"], output_names=["logits"],
                      dynamic_axes={"input": {0: "batch"}, "logits": {0: "batch"}},
                      opset_version=17, dynamo=False)
    manifest = build_manifest(
        run_id=out_dir.name, model_sha256=_sha256(onnx_path),
        parent_sha256=parent_sha256,
        smoke={"split": "val", "selection": smoke_selection, "n": smoke_n,
               "sample_ids_sha256": sample_ids_sha256,
               "rule": "per_class_mode_equals_label"})
    (out_dir / "runtime_manifest.json").write_text(json.dumps(manifest, indent=2))
    (out_dir / "class_metadata.json").write_text(json.dumps({
        "classes": CLASSES,
        "class_to_idx": {name: index for index, name in enumerate(CLASSES)},
        "safe_class": "c0",
        "runtime_aliases": {"c0": "safe_driving"},
        "meaning": "Runtime alias does not rename the DMD training action.",
    }, indent=2))
    (out_dir / "evaluation_metrics.json").write_text(json.dumps({}, indent=2))
    return manifest
