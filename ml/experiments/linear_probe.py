"""Matched, full-split frozen-backbone experiment; NOT full CNN fine-tuning.

Compare ImageNet MobileNetV3-Large and EfficientNet-B0 using the same driver-
grouped splits, RGB 224x224 preprocessing, and validation-selected logistic head.
No test data are used for fitting, scaling, or regularization selection.
"""
import argparse
import hashlib
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from PIL import Image
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from torchvision import models

from vision_benchmark import metrics, preprocessing, session, sha256


def extract(arch, weights_path, meta, cache_dir, threads, batch):
    fingerprint = hashlib.sha256((sha256(weights_path) + meta.to_csv(index=False)
                                  + "rgb-bilinear-224-imagenet-meanstd-v1").encode()).hexdigest()
    feature_path = cache_dir / f"{arch}-{fingerprint[:16]}.npz"
    if feature_path.exists():
        with np.load(feature_path) as data:
            return data["features"], {"cache_hit": True, "cache_fingerprint": fingerprint}
    full = getattr(models, arch)(weights=None)
    full.load_state_dict(torch.load(weights_path, map_location="cpu", weights_only=True), strict=True)
    backbone = torch.nn.Sequential(full.features, full.avgpool, torch.nn.Flatten(1)).eval()
    onnx_path = cache_dir / f"{arch}-imagenet-backbone.onnx"
    torch.onnx.export(backbone, torch.zeros(1, 3, 224, 224), str(onnx_path),
                      input_names=["image"], output_names=["features"],
                      dynamic_axes={"image": {0: "batch"}, "features": {0: "batch"}},
                      opset_version=17, dynamo=False)
    runtime = session(onnx_path, threads)
    tf = preprocessing()
    result = []
    start = time.perf_counter()
    for offset in range(0, len(meta), batch):
        xs = []
        for path in meta.iloc[offset:offset + batch].image_path:
            with Image.open(path) as image:
                xs.append(tf(image.convert("RGB")))
        values = torch.stack(xs).numpy()
        result.append(runtime.run(None, {"image": values})[0])
        if offset % (batch * 50) == 0:
            print(f"{arch} features {offset + len(xs)}/{len(meta)} ({time.perf_counter() - start:.1f}s)", flush=True)
    features = np.concatenate(result)
    np.savez_compressed(feature_path, features=features)
    return features, {"cache_hit": False, "cache_fingerprint": fingerprint,
                      "feature_extraction_seconds": time.perf_counter() - start,
                      "feature_dimensions": features.shape[1]}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--data-root", type=Path, default=Path.home() / "Desktop/FYP-In-Cabin-Driver-Assessment-")
    p.add_argument("--mobilenet-weights", type=Path, default=Path.home() / ".cache/torch/hub/checkpoints/mobilenet_v3_large-5c1a4163.pth")
    p.add_argument("--efficientnet-weights", type=Path, default=Path(__file__).parent / "cache/efficientnet_b0_rwightman-7f5810bc.pth")
    p.add_argument("--cache-dir", type=Path, default=Path(__file__).parent / "cache")
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--threads", type=int, default=2)
    p.add_argument("--batch", type=int, default=32)
    args = p.parse_args()
    if args.output.exists():
        p.error("Choose a new output path")
    if min(args.threads, args.batch) <= 0:
        p.error("threads and batch must be positive")
    torch.set_num_threads(args.threads)
    meta_path = args.data_root / "eda_outputs/processed/vision/vision_metadata_with_split.csv"
    meta = pd.read_csv(meta_path)
    splits = {s: (meta.split == s).to_numpy() for s in ("train", "val", "test")}
    drivers = {s: set(meta.loc[mask, "driver_id"]) for s, mask in splits.items()}
    for a, b in (("train", "val"), ("train", "test"), ("val", "test")):
        if drivers[a] & drivers[b]:
            raise ValueError("Driver leakage")
    labels = meta.class_id.str[1:].astype(int).to_numpy()
    args.cache_dir.mkdir(parents=True, exist_ok=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    report = {"experiment": "frozen_imagenet_backbone_plus_standardized_logistic_head",
              "scope": "Matched linear probes, NOT equal-compute CNN fine-tuning or frontal/edge validation",
              "split_sizes": {s: int(mask.sum()) for s, mask in splits.items()},
              "metadata_sha256": sha256(meta_path), "threads": args.threads, "batch": args.batch,
              "head_selection": "C in [0.01,0.1,1.0], maximum validation macro-F1; standardizer and classifier fit only on train",
              "models": []}
    for arch, weights, prefix in [
        ("mobilenet_v3_large", args.mobilenet_weights, "5c1a4163"),
        ("efficientnet_b0", args.efficientnet_weights, "7f5810bc"),
    ]:
        digest = sha256(weights)
        if not digest.startswith(prefix):
            raise ValueError(f"Unexpected official weight checksum for {weights}")
        x, extraction = extract(arch, weights, meta, args.cache_dir, args.threads, args.batch)
        candidates = []
        best, best_score, best_c = None, -1, None
        for c in (0.01, 0.1, 1.0):
            start = time.perf_counter()
            classifier = make_pipeline(StandardScaler(), LogisticRegression(C=c, max_iter=1000, random_state=42))
            classifier.fit(x[splits["train"]], labels[splits["train"]])
            assert classifier.classes_.tolist() == list(range(10))
            validation = metrics(labels[splits["val"]], classifier.predict_proba(x[splits["val"]]))
            candidate = {"C": c, "val_accuracy": validation["accuracy"], "val_macro_f1": validation["macro_f1"],
                         "fit_seconds": time.perf_counter() - start,
                         "solver_iterations": classifier[-1].n_iter_.tolist()}
            candidates.append(candidate)
            print(arch, json.dumps(candidate), flush=True)
            if validation["macro_f1"] > best_score:
                best, best_score, best_c = classifier, validation["macro_f1"], c
        row = {"architecture": arch, "weights_sha256": digest, **extraction,
               "selected_C": best_c, "validation_candidates": candidates,
               "test": metrics(labels[splits["test"]], best.predict_proba(x[splits["test"]]))}
        # Export the head as arrays instead of an unsafe executable pickle.
        head_path = args.cache_dir / f"{arch}-linear-head.npz"
        np.savez(head_path, mean=best[0].mean_, scale=best[0].scale_,
                 coef=best[-1].coef_, intercept=best[-1].intercept_, classes=best.classes_)
        row["head_sha256"] = sha256(head_path)
        report["models"].append(row)
        args.output.write_text(json.dumps(report, indent=2) + "\n")
        print(f"{arch}: test accuracy={row['test']['accuracy']:.6f}, macro-F1={row['test']['macro_f1']:.6f}", flush=True)
    print(f"Saved {args.output}", flush=True)


if __name__ == "__main__":
    main()
