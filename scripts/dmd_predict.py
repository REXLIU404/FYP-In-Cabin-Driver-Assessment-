"""Classify one image with the stable and/or the adapted vision model.

Reuses the exact preprocessing and softmax of `dmd_infer_test.py`, so what this prints
is what the offline evaluation measures.

    PYTHONPATH=backend:scripts .venv/bin/python scripts/dmd_predict.py <image> [--model both|stable|adapted]
"""
from __future__ import annotations

import argparse
from pathlib import Path

import onnxruntime as ort

from dmd_infer_test import preprocess, softmax

LABELS = ["safe_driving", "texting_right", "talking_phone_right", "texting_left",
          "talking_phone_left", "operating_radio", "drinking", "reaching_behind",
          "hair_makeup", "talking_to_passenger"]
MODELS = {
    "stable": Path("ml/outputs/vision/mobilenetv3_large_vision.onnx"),
    "adapted": Path("ml/outputs/candidates/dmd_adapted_mobilenet_v3_20261029/model.onnx"),
}
THRESHOLD = 0.7038  # the val-selected working point


def predict(model_path: Path, tensor) -> dict:
    session = ort.InferenceSession(str(model_path), providers=["CPUExecutionProvider"])
    logits = session.run(None, {"input": tensor})[0][0].tolist()
    probs = softmax(logits)
    top = sorted(zip(LABELS, probs), key=lambda item: -item[1])
    return {"top": top[:3], "distraction": 1.0 - probs[0],
            "alert": (1.0 - probs[0]) >= THRESHOLD}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("image", type=Path)
    parser.add_argument("--model", default="both", choices=["both", "stable", "adapted"])
    args = parser.parse_args()

    tensor = preprocess(args.image)
    names = ["stable", "adapted"] if args.model == "both" else [args.model]
    for name in names:
        result = predict(MODELS[name], tensor)
        print(f"{name:<9} P_distraction={result['distraction']:.4f}  "
              f"alert={result['alert']}")
        for label, prob in result["top"]:
            print(f"    {label:<22} {prob:.4f}")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
