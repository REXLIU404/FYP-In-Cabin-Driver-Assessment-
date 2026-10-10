"""Reload the existing XGBoost booster and reproduce full-test metrics."""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.metrics import accuracy_score, f1_score

from vision_benchmark import ROOT, sha256, timings


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--data-root", type=Path, default=Path.home() / "Desktop/FYP-In-Cabin-Driver-Assessment-")
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    if args.output.exists():
        p.error("Choose a new output path")
    model_path = ROOT / "ml/outputs/telemetry/xgb_telemetry.json"
    metadata = json.loads((model_path.parent / "metrics.json").read_text())
    data_path = args.data_root / "eda_outputs/processed/telemetry/telemetry_test.csv"
    df = pd.read_csv(data_path)
    labels = metadata["classes"]
    assert labels == ["Safe", "Aggressive", "Distracted"]
    y = df.behavior_label.map({c: i for i, c in enumerate(labels)}).to_numpy(int)
    frame = df[metadata["features"]].astype(float)
    model = xgb.Booster()
    model.load_model(model_path)
    model.set_param({"nthread": 2})
    assert model.feature_names == list(frame.columns)
    best = int(model.attr("best_iteration"))
    assert best == metadata["best_iteration"]
    data = xgb.DMatrix(frame)
    probs = model.predict(data, iteration_range=(0, best + 1))
    all_trees = model.predict(data)
    assert probs.shape == (len(df), 3)
    assert np.allclose(probs.sum(1), 1, atol=1e-5)
    single = xgb.DMatrix(frame.iloc[:1])
    report = {"runtime": "xgboost_cpu", "version": xgb.__version__, "threads": 2,
              "model_sha256": sha256(model_path), "data_sha256": sha256(data_path),
              "samples": len(df), "classes": labels, "features": list(frame.columns),
              "best_iteration": best, "iteration_range": [0, best + 1],
              "accuracy": float(accuracy_score(y, probs.argmax(1))),
              "macro_f1": float(f1_score(y, probs.argmax(1), average="macro")),
              "all_trees_accuracy": float(accuracy_score(y, all_trees.argmax(1))),
              "all_trees_max_probability_difference": float(np.abs(probs - all_trees).max()),
              "single_row_forward_only": timings(lambda: model.predict(single, iteration_range=(0, best + 1)), 20, 100),
              "scope": "Synthetic rule-generated dataset; not field accuracy. Timing excludes feature extraction and DMatrix construction."}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
