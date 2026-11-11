# `ml/` — FYP2 Model Training (baselines)

Jupyter notebooks that train the two evidence branches of the In-Cabin Multi-Modal Driver Risk
Assessment system and report **baseline** metrics. These are the FYP2 models referenced (as
*designed*) by the FYP1 prototype — this folder is where they actually get trained.

> **Status:** baselines only. Pipeline + honest metrics, not tuned/deployment models.

## Contents

| File | Branch | Model | Output |
|------|--------|-------|--------|
| [`telemetry/train_telemetry.ipynb`](telemetry/train_telemetry.ipynb) | Telemetry | XGBoost multiclass (Safe / Aggressive / Distracted), 8 features | `outputs/telemetry/` |
| [`vision/train_vision.ipynb`](vision/train_vision.ipynb) | Vision | MobileNetV3 (ImageNet-pretrained, fine-tuned), 10 classes | `outputs/vision/` |

Each notebook is **self-contained**: it resolves the dataset path itself and imports no project
`.py` module, so it runs as-is in Jupyter Lab.

> **Model weights are not version-controlled.** The trained binaries
> (`outputs/vision/*.pt`, `outputs/vision/*.onnx`, `outputs/telemetry/xgb_telemetry.json`) are
> git-ignored to keep the repo light; re-running a notebook regenerates them. Only the result
> artifacts — metrics, figures, classification reports, and the executed notebooks — are tracked.

## Data dependency (not copied into this repo)

The EDA-prepared, pre-split data lives in the **sibling** repo
`~/Desktop/FYP-In-Cabin-Driver-Assessment-` (note: no trailing `1`):

- Telemetry: `eda_outputs/processed/telemetry/telemetry_{train,val,test}.csv` (+ `telemetry_feature_order.csv`)
- Vision: `eda_outputs/processed/vision/vision_metadata_with_split.csv` + `state-farm-distracted-driver-detection/imgs/train/`

The notebooks read straight from there (the ~1.5 GB image set is **not** duplicated). Override the
location with the `FYP_DATA_ROOT` environment variable if the sibling repo moves.

## How to run

```bash
# from the repo root
.venv/bin/jupyter lab        # then open a notebook and pick the "FYP ML (.venv)" kernel
```

Or non-interactively (re-runs and embeds outputs in place):

```bash
FYP_DATA_ROOT="$HOME/Desktop/FYP-In-Cabin-Driver-Assessment-" \
  .venv/bin/jupyter nbconvert --to notebook --execute --inplace \
  --ExecutePreprocessor.kernel_name=fyp-ml ml/telemetry/train_telemetry.ipynb
```

Vision hyperparameters are env-overridable: `VISION_EPOCHS`, `VISION_BATCH`, `VISION_ARCH`
(`large`|`small`), `VISION_LR`, `VISION_WORKERS`.

> **`VISION_WORKERS` defaults to 0** inside the notebook on purpose: on macOS + Python 3.13 a
> Jupyter kernel can't reliably use `DataLoader(num_workers>0)` (spawn can't pickle the in-notebook
> Dataset; fork-after-threads can crash the kernel). Set it higher only when running as a plain
> script.

## Dependencies

Installed into the repo-root `.venv` (in addition to the backend's): `pandas`, `scikit-learn`,
`xgboost` (needs `libomp` via Homebrew), `torch`, `torchvision`, `onnx`, `onnxruntime`,
`jupyterlab`, `nbformat`, `nbconvert`, `ipykernel`. Kernel registered as `fyp-ml`.

## Baseline results

### Telemetry (XGBoost, 8 features, test split = 4500)
- **accuracy 0.9993 · macro-F1 0.9993 · macro-AUC 1.000** (best_iteration ≈ 90, < 1 s to train)
- Top features by gain: `accel_x`, `brake_pressure`, `lane_deviation`, `throttle`.

> ⚠️ **Honest caveat.** `Driver_Behavior.csv` is a **synthetic / rule-generated** dataset whose
> classes are near-separable; near-perfect metrics demonstrate the *pipeline*, not field accuracy.
> Disclose this in the report/viva.

### Vision (MobileNetV3-Large, 10 classes, driver-grouped split, test = 3657)
- **test accuracy 0.8988 · macro-F1 0.8746 · weighted-F1 0.8856** (best_val_acc 0.8975; 5 epochs,
  MPS, ~19 min). Full breakdown: [`outputs/vision/metrics.json`](outputs/vision/metrics.json),
  [`outputs/vision/classification_report_test.txt`](outputs/vision/classification_report_test.txt).
- Reported on a **driver-grouped** split (no subject leakage) — the honest generalisation estimate,
  intentionally lower than the leaky ~0.99 a random split would show.
- **macro-F1 < accuracy** because one class is hard: `c9 talking_to_passenger` (F1 ≈ 0.40,
  recall ≈ 0.27) is visually close to `c0 normal_driving` and gets confused — a genuine,
  report-worthy limitation that the driver-grouped split exposes. `c8 hair_makeup` is the next
  weakest (F1 ≈ 0.80).
- Augmentation **excludes horizontal flips** (left/right hand actions are distinct labels).
- ONNX export (`mobilenetv3_large_vision.onnx`, opset 17, dynamic batch axis, verified with
  onnxruntime) aligns with the final demo plan (MobileNetV3 ONNX + live camera + prepared telemetry).

> *(Numbers above are from the first full run; the canonical re-run reproduces them within MPS
> run-to-run variance.)*

## Scope notes

- `P_telemetry_anomaly = 1 − P(Safe)` and `P_distraction = 1 − P(c0)` are the probabilities the
  late-fusion layer consumes; the classifiers here are full multiclass models and those
  probabilities are derived downstream. Decision-level late fusion only — these branches stay
  independent.
- Models are **baselines**, not vehicle-grade / deployment artifacts.
