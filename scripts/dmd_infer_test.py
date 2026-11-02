"""Run any vision classifier package over one split and dump logits + metrics.

Both the zero-shot baseline and the adapted model are evaluated through THIS function,
so the only difference between the two tables is the ONNX file. ONNX emits LOGITS -
every probability metric must start from the softmax below.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np

MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)


def preprocess(path: Path) -> np.ndarray:
    from PIL import Image

    with Image.open(path) as image:
        image = image.convert("RGB").resize((224, 224), Image.Resampling.BILINEAR)
        values = np.asarray(image, dtype=np.float32) / 255.0
    values = (values - MEAN) / STD
    return np.ascontiguousarray(values.transpose(2, 0, 1)[None])


def infer(model_path: Path, frames_root: Path, files: list[str]) -> list[list[float]]:
    import onnxruntime as ort

    session = ort.InferenceSession(str(model_path), providers=["CPUExecutionProvider"])
    input_name = session.get_inputs()[0].name
    logits: list[list[float]] = []
    for rel in files:
        tensor = preprocess(Path(frames_root) / rel)
        logits.append(session.run(None, {input_name: tensor})[0][0].tolist())
    return logits


def softmax(row: list[float]) -> list[float]:
    """ONNX returns LOGITS; every probability metric must start from this."""
    top = max(row)
    exp = [math.exp(v - top) for v in row]
    total = sum(exp)
    return [v / total for v in exp]


def run(model_path: Path, manifest_csv: Path, frames_root: Path, split: str) -> dict:
    import csv

    from dmd_dataset import CLASS_IDS
    from dmd_evaluate import multiclass_metrics

    rows = [r for r in csv.DictReader(Path(manifest_csv).open()) if r["split"] == split]
    files = [r["file"] for r in rows]
    labels = [CLASS_IDS.index(r["class_id"]) for r in rows]
    matrix = infer(model_path, frames_root, files)
    probs = [softmax(row) for row in matrix]        # ONNX output is LOGITS
    distraction = [1.0 - p[0] for p in probs]       # P_distraction = 1 - P(c0)
    return {"split": split, "n": len(rows), "files": files, "labels": labels,
            "logits": matrix, "probabilities": probs, "distraction": distraction,
            "multiclass": multiclass_metrics(labels, matrix)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("model_path", type=Path)
    parser.add_argument("manifest_csv", type=Path)
    parser.add_argument("frames_root", type=Path)
    parser.add_argument("--split", default="test")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.out.write_text(json.dumps(
        run(args.model_path, args.manifest_csv, args.frames_root, args.split), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
