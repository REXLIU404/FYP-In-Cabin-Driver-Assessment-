"""Reproduce trained-model evaluation and batch-one CPU architecture benchmarks.

Run from the repo root with .venv/bin/python. No downloads and no retraining.
Random-weight candidate timings are explicitly NOT accuracy measurements.
"""
import argparse
import hashlib
import json
import platform
import tempfile
import time
from pathlib import Path

import numpy as np
import onnxruntime as ort
import pandas as pd
import torch
from PIL import Image
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score
from torchvision import models, transforms

ROOT = Path(__file__).resolve().parents[2]
ARCHES = ("mobilenet_v3_large", "mobilenet_v3_small", "efficientnet_b0")
MEAN, STD = [0.485, 0.456, 0.406], [0.229, 0.224, 0.225]


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def build_model(arch, num_classes=10):
    if arch not in ARCHES:
        raise ValueError(f"Unsupported architecture: {arch}")
    model = getattr(models, arch)(weights=None)
    model.classifier[-1] = torch.nn.Linear(model.classifier[-1].in_features, num_classes)
    return model.eval()


def preprocessing():
    # Exactly matches the existing notebook; do not silently use ImageNet center-crop.
    return transforms.Compose([
        transforms.Resize((224, 224)), transforms.ToTensor(), transforms.Normalize(MEAN, STD)
    ])


def load_checkpoint(path):
    checkpoint = torch.load(path, map_location="cpu", weights_only=True)
    if checkpoint["classes"] != [f"c{i}" for i in range(10)]:
        raise ValueError("Expected canonical c0..c9 order with safe class at index zero")
    model = build_model(checkpoint["arch"])
    model.load_state_dict(checkpoint["state_dict"], strict=True)
    return model, checkpoint


def session(path, threads):
    opts = ort.SessionOptions()
    opts.intra_op_num_threads = threads
    opts.inter_op_num_threads = 1
    opts.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
    return ort.InferenceSession(str(path), opts, providers=["CPUExecutionProvider"])


def softmax(logits):
    exp = np.exp(logits - logits.max(axis=1, keepdims=True))
    return exp / exp.sum(axis=1, keepdims=True)


def metrics(y, probs):
    pred = probs.argmax(1)
    binary_target = y != 0
    binary_pred = (1 - probs[:, 0]) >= 0.5
    report = classification_report(y, pred, labels=list(range(10)), output_dict=True, zero_division=0)
    return {
        "samples": len(y), "accuracy": float(accuracy_score(y, pred)),
        "macro_f1": float(f1_score(y, pred, labels=list(range(10)), average="macro", zero_division=0)),
        "per_class": report, "confusion_matrix": confusion_matrix(y, pred, labels=list(range(10))).tolist(),
        "distraction_threshold": 0.5,
        "binary_distraction_recall": float(binary_pred[binary_target].mean()),
        "safe_false_positive_rate": float(binary_pred[~binary_target].mean()),
        "binary_brier_score": float(np.mean(((1 - probs[:, 0]) - binary_target) ** 2)),
    }


def timings(fn, warmup, iterations):
    for _ in range(warmup):
        fn()
    samples = []
    for _ in range(iterations):
        start = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - start) * 1000)
    return {"warmup": warmup, "iterations": iterations, "mean_ms": float(np.mean(samples)),
            "p50_ms": float(np.percentile(samples, 50)), "p95_ms": float(np.percentile(samples, 95)),
            "p99_ms": float(np.percentile(samples, 99)),
            "serial_model_only_fps": float(1000 / np.mean(samples))}


def benchmark(args, report):
    torch.manual_seed(42)
    x = torch.randn(1, 3, 224, 224)
    trained, checkpoint = load_checkpoint(args.checkpoint)
    rows = []
    with torch.inference_mode():
        for arch in ARCHES:
            model = trained if arch == checkpoint["arch"] else build_model(arch)
            row = {"architecture": arch, "runtime": "pytorch_cpu", "batch": 1,
                   "input_shape": list(x.shape), "dtype": "float32",
                   "weight_status": "trained_driver_checkpoint" if model is trained else "random_latency_only",
                   "parameters": sum(p.numel() for p in model.parameters()),
                   "tensor_weights_mib": sum(p.numel() * p.element_size() for p in model.parameters()) / 2**20,
                   **timings(lambda: model(x), args.warmup, args.iterations)}
            rows.append(row)
            print(json.dumps(row), flush=True)
        # Same runtime for every candidate: never compare PyTorch B0 to ORT MobileNet.
        with tempfile.TemporaryDirectory(prefix="vision-benchmark-") as temp:
            for arch in ARCHES:
                path = args.onnx
                if arch != checkpoint["arch"]:
                    path = Path(temp) / f"{arch}.onnx"
                    model = build_model(arch)
                    torch.onnx.export(model, x, str(path), input_names=["input"],
                                      output_names=["logits"], opset_version=17, dynamo=False,
                                      dynamic_axes={"input": {0: "batch"}, "logits": {0: "batch"}})
                sess = session(path, args.threads)
                values = x.numpy()
                row = {"architecture": arch, "runtime": "onnxruntime_cpu", "batch": 1,
                       "weight_status": "trained_driver_checkpoint" if arch == checkpoint["arch"] else "random_latency_only",
                       "file_mib": path.stat().st_size / 2**20,
                       **timings(lambda: sess.run(None, {sess.get_inputs()[0].name: values}), args.warmup, args.iterations)}
                rows.append(row)
                print(json.dumps(row), flush=True)
    report["latency"] = rows
    report["latency_scope"] = "CPU forward-pass only; synthetic preprocessed input; excludes camera/decode/resize/network/queue/fusion/UI; not target-device FPS"


def evaluate(args, report):
    meta_path = args.data_root / "eda_outputs/processed/vision/vision_metadata_with_split.csv"
    meta = pd.read_csv(meta_path)
    groups = {s: set(meta.loc[meta.split == s, "driver_id"]) for s in ("train", "val", "test")}
    overlap = {f"{a}_{b}": sorted(groups[a] & groups[b]) for a, b in (("train", "val"), ("train", "test"), ("val", "test"))}
    if any(overlap.values()):
        raise ValueError(f"Driver leakage: {overlap}")
    report["split_audit"] = {"metadata_sha256": sha256(meta_path), "driver_overlap": overlap,
                             "driver_counts": {s: len(v) for s, v in groups.items()},
                             "rows": meta.split.value_counts().to_dict()}
    df = meta.loc[meta.split == args.split].copy()
    if args.limit:
        df = df.sample(n=min(args.limit, len(df)), random_state=42).sort_index()
    df = df.reset_index(drop=True)
    # Metadata are class-sorted: checking only the first batch would test c0 alone.
    # Spread the parity budget across all represented classes instead.
    parity_positions = set()
    classes = sorted(df.class_id.unique())
    for i, label in enumerate(classes):
        available = df.loc[df.class_id == label]
        count = args.parity_samples // len(classes) + (i < args.parity_samples % len(classes))
        parity_positions.update(available.sample(n=min(count, len(available)), random_state=42).index)
    model, _ = load_checkpoint(args.checkpoint)
    sess = session(args.onnx, args.threads)
    tf = preprocessing()
    batches, labels = [], []
    max_logit_diff, max_prob_diff, mismatches, parity_samples = 0.0, 0.0, 0, 0
    start = time.perf_counter()
    for offset in range(0, len(df), args.batch):
        rows = df.iloc[offset:offset + args.batch]
        tensors = []
        for path in rows.image_path:
            with Image.open(path) as im:
                tensors.append(tf(im.convert("RGB")))
        x = torch.stack(tensors)
        logits = sess.run(None, {sess.get_inputs()[0].name: x.numpy()})[0]
        probs = softmax(logits)
        parity_mask = [i for i in range(len(rows)) if offset + i in parity_positions]
        if parity_mask:
            with torch.inference_mode():
                pt = model(x[parity_mask]).numpy()
            max_logit_diff = max(max_logit_diff, float(np.max(np.abs(pt - logits[parity_mask]))))
            max_prob_diff = max(max_prob_diff, float(np.max(np.abs(softmax(pt) - probs[parity_mask]))))
            mismatches += int(np.sum(pt.argmax(1) != logits[parity_mask].argmax(1)))
            parity_samples += len(parity_mask)
        batches.append(probs)
        labels.extend(int(c[1:]) for c in rows.class_id)
        if offset % (args.batch * 20) == 0:
            print(f"evaluated {offset + len(rows)}/{len(df)}", flush=True)
    report["evaluation"] = {"split": args.split, "runtime": "onnxruntime_cpu",
                            "checkpoint_sha256": sha256(args.checkpoint), "onnx_sha256": sha256(args.onnx),
                            "preprocess": "PIL RGB, bilinear Resize(224,224), ToTensor, ImageNet mean/std",
                            "seconds_including_decode_and_parity": time.perf_counter() - start,
                            **metrics(np.array(labels), np.concatenate(batches))}
    report["onnx_parity"] = {"samples": parity_samples, "max_abs_logit_difference": max_logit_diff,
                             "max_abs_probability_difference": max_prob_diff, "argmax_disagreements": mismatches,
                             "sampling": "seed42 class-stratified",
                             "classes": sorted(df.loc[list(parity_positions), "class_id"].unique().tolist())}
    print(json.dumps({"evaluation": {k: v for k, v in report["evaluation"].items() if k not in ("per_class", "confusion_matrix")}, "onnx_parity": report["onnx_parity"]}), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("benchmark", "evaluate", "all"), default="all")
    parser.add_argument("--data-root", type=Path, default=Path.home() / "Desktop/FYP-In-Cabin-Driver-Assessment-")
    parser.add_argument("--checkpoint", type=Path, default=ROOT / "ml/outputs/vision/mobilenetv3_large_vision.pt")
    parser.add_argument("--onnx", type=Path, default=ROOT / "ml/outputs/vision/mobilenetv3_large_vision.onnx")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--threads", type=int, default=2)
    parser.add_argument("--warmup", type=int, default=20)
    parser.add_argument("--iterations", type=int, default=100)
    parser.add_argument("--batch", type=int, default=16)
    parser.add_argument("--split", choices=("val", "test"), default="test")
    parser.add_argument("--limit", type=int, default=0, help="0 means full split")
    parser.add_argument("--parity-samples", type=int, default=128)
    args = parser.parse_args()
    if min(args.threads, args.iterations, args.batch) <= 0 or min(args.limit, args.warmup, args.parity_samples) < 0:
        parser.error("threads/iterations/batch must be positive; limit/warmup/parity-samples nonnegative")
    if args.output.exists():
        parser.error("Choose a new output path to preserve prior evidence")
    torch.set_num_threads(args.threads)
    report = {"environment": {"platform": platform.platform(), "processor": platform.processor(),
                              "python": platform.python_version(), "torch": torch.__version__,
                              "onnxruntime": ort.__version__, "threads": args.threads,
                              "mps_available": torch.backends.mps.is_available()},
              "command_config": {k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items()}}
    if args.mode in ("all", "benchmark"):
        benchmark(args, report)
    if args.mode in ("all", "evaluate"):
        evaluate(args, report)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(f"Saved {args.output}", flush=True)


if __name__ == "__main__":
    main()
