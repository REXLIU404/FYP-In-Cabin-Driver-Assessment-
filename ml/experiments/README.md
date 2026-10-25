# Reproducible project assessment experiments

These tools evaluate the existing trained artifacts and provide optional edge-oriented CNN comparisons.
**Alternate-model work is paused at the user's request. Do not run the linear probe or architecture comparison until that scope is resumed.**
They do not connect the frontend/backend to those models. The implementation plan
is [PROJECT_ASSESSMENT_AND_TEST_PLAN.zh.md](../../docs/PROJECT_ASSESSMENT_AND_TEST_PLAN.zh.md).

Use the existing repository `.venv` from the repository root. Required packages
are torch, torchvision, onnx, onnxruntime, pandas, numpy, scikit-learn, Pillow, and
xgboost (already present in the audited environment). The subsequent live integration has its own runtime requirements in
`backend/requirements-inference.txt`; these experiment tools are not part of serving.

## Commands

All output paths must be new: scripts refuse to overwrite existing evidence.

```bash
# Trained MobileNet full test, stratified PyTorch/ONNX parity, batch-one timing.
.venv/bin/python ml/experiments/vision_benchmark.py --output /tmp/vision-report.json

# Timing only. Run WITHOUT competing CPU-heavy processes for interpretable latency.
.venv/bin/python ml/experiments/vision_benchmark.py --mode benchmark --output /tmp/cpu-report.json

# Trained XGBoost full test, best_iteration vs all trees, one-row timing.
.venv/bin/python ml/experiments/telemetry_benchmark.py --output /tmp/telemetry-report.json

# Same training/validation/test split for two frozen ImageNet backbone probes.
OPENBLAS_NUM_THREADS=2 OMP_NUM_THREADS=2 VECLIB_MAXIMUM_THREADS=2 \
  .venv/bin/python ml/experiments/linear_probe.py --output /tmp/probes.json

# Fixed validation subset, original vs dim/blurred images. No frontal claim.
.venv/bin/python ml/experiments/robustness_probe.py --output /tmp/robustness.json
```

`--data-root` defaults to the sibling data repository documented in `ml/README.md`.
The CSV must have the existing `image_path`, `class_id`, `driver_id`, and `split`
columns; its absolute image paths must resolve. Vision defaults match the actual
notebook: PIL RGB, bilinear `Resize((224,224))`, tensor conversion, ImageNet mean
and standard deviation, canonical `c0..c9` output order.

## What comparisons mean

- Existing MobileNetV3-Large `.pt`/`.onnx`: actual driver fine-tuned checkpoint.
- Timing candidates: Large, Small, B0, each under PyTorch CPU and ONNXRuntime CPU.
  Small/B0 heads are random in the architecture timing test. They test cost only;
  no accuracy is reported from those random models.
- Linear probes: official ImageNet MobileNetV3-Large V2 and EfficientNet-B0 V1
  backbones frozen; train-only StandardScaler + multiclass logistic regression.
  Select `C` from `[0.01,0.1,1.0]` by validation macro-F1, then measure the test set.
  Same downstream protocol, but different upstream ImageNet pretraining recipes;
  this is not a controlled experiment isolating architecture alone.
- Full CNN fine-tuning and real frontal-camera/target-edge evaluation remain
  separate follow-up experiments. Do not rank a frozen probe against a fully
  fine-tuned model as proof that one architecture is intrinsically better.

`linear_probe.py` requires the official weight files. Use `--mobilenet-weights`
and `--efficientnet-weights` to specify their local paths. SHA256 prefixes are
checked against the official filenames. Before the user paused alternate-model work, the existing MobileNet cache
was read and B0 was downloaded from:

https://download.pytorch.org/models/efficientnet_b0_rwightman-7f5810bc.pth

Git-ignored `cache/` contains the B0 download, exported feature backbones, feature
matrices, and trained linear head arrays. The feature cache fingerprints weights,
metadata and preprocessing; if image bytes are changed in place without updating
metadata, delete the relevant feature `.npz` cache before repeating the experiment.
Heads contain mean/scale, coefficient/intercept, and class-order arrays; they are
not pickle files and are not automatically loaded by the application.

## Reading the evidence

- Accuracy and macro-F1 measure held-out source-image performance, not accident
  risk, frontal-camera reliability, or field validation.
- `P_distraction >= 0.5` is evaluated separately from the ten-class argmax.
- Forward timing excludes decode/preprocessing/capture/network/queue/fusion/UI.
  `1000 / mean_ms` is model-only throughput, not measured camera FPS.
- Backend audit tests use temporary databases. The initial `xfail` and unmasked
  failure logs are historical evidence. Those markers have since been removed;
  the live integration suite now requires ordinary passing assertions.
- No original notebook, trained checkpoint, metrics, application database, or
  user changes to `AGENTS.md` were edited by this assessment.

The B0 probe was interrupted, not completed or integrated. Current implementation
status is [IMPLEMENTATION_PROGRESS.zh.md](../../docs/IMPLEMENTATION_PROGRESS.zh.md).
