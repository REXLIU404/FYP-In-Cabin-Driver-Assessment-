"""Validation-only photometric stress test; it does NOT simulate frontal view."""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from PIL import Image, ImageEnhance, ImageFilter

from vision_benchmark import ROOT, metrics, preprocessing, session, sha256, softmax


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--data-root", type=Path, default=Path.home() / "Desktop/FYP-In-Cabin-Driver-Assessment-")
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    if args.output.exists():
        p.error("Choose a new output path")
    torch.set_num_threads(2)
    metadata = args.data_root / "eda_outputs/processed/vision/vision_metadata_with_split.csv"
    df = pd.read_csv(metadata)
    df = df.loc[df.split == "val"].groupby("class_id", group_keys=False).sample(n=100, random_state=42).sort_index()
    y = df.class_id.str[1:].astype(int).to_numpy()
    model_path = ROOT / "ml/outputs/vision/mobilenetv3_large_vision.onnx"
    runtime, tf = session(model_path, 2), preprocessing()
    result = {"split": "val", "sampling": "100 images per class, random_state=42",
              "samples": len(df), "model_sha256": sha256(model_path), "metadata_sha256": sha256(metadata),
              "scope": "Controlled brightness/blur corruption; does not validate viewpoint transfer or natural low-light scenes", "conditions": {}}
    for condition in ("original", "brightness_0.35", "gaussian_blur_radius_2"):
        probabilities = []
        for offset in range(0, len(df), 16):
            xs = []
            for path in df.iloc[offset:offset + 16].image_path:
                with Image.open(path) as file:
                    image = file.convert("RGB")
                if condition == "brightness_0.35":
                    image = ImageEnhance.Brightness(image).enhance(0.35)
                elif condition == "gaussian_blur_radius_2":
                    image = image.filter(ImageFilter.GaussianBlur(radius=2))
                xs.append(tf(image))
            logits = runtime.run(None, {runtime.get_inputs()[0].name: torch.stack(xs).numpy()})[0]
            probabilities.append(softmax(logits))
        values = metrics(y, np.concatenate(probabilities))
        result["conditions"][condition] = values
        print(condition, values["accuracy"], values["macro_f1"], flush=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()
