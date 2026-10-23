# Five-model Comparison and Hyperparameter Tuning Audit

> 审计日期：2026-10-10（Asia/Kuala_Lumpur）；实跑检查时间见各 evidence 日志（主要为 2026-10-09）。审计对象是用户确认的桌面主仓库 `/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1`，branch `dev_cc`，HEAD `17c4b41bcfe517c8311b7f6fc2a327f616a916fe` **加未提交内容**。本文所有应用源码相对路径都相对此根目录，不相对当前旧工作树。输出工作树 HEAD `ae550415237fc1f67bf0de50c643a6d8bd6aca60`。命令 ID、环境、时间、退出码、指纹见 [07 证据索引](07_EVIDENCE_MANIFEST.md) 与 [source inventory](evidence/source_inventory.json)。

证据层次：`CURRENT_VERIFIED`=本次源码/产物检查或明确限定范围的实跑；`FYP1_REPORTED`=未在本次对应范围复现的继承指标；`PLANNED`=建议，未执行。旧实验日志标明 historical，不算本次运行。实现状态与测试执行状态分别记录；`MISSING_TEST` 是测试缺口标记，不是实现状态。未发现只适用于已扫描范围。

## Model-by-model truth

| Model | Training/preprocessing/seed/selection evidence | Checkpoint, validation and held-out metrics | Tuning and deployment state |
|---|---|---|---|
| MobileNetV3-Large | `ml/vision/train_vision.ipynb` cells 1/3/9/11/13: torch+NumPy seed42, ImageNet V2, 224² RGB normalization, rotation8°, ColorJitter .2, no horizontal flip, AdamW LR8e-4/wd1e-4, cosine, 5 epochs/batch64. Select **val accuracy**, not macro-F1 | `.pt/.onnx` present. `metrics.json` history, val/test class reports. Full test .8988 accuracy/.8746 macro-F1 remains `FYP1_REPORTED` with historical 09-28 reproduction; current run 20-image smoke only | Baseline `PARTIALLY_VERIFIED`; local live inference `TEST_PASSED`. Required multi-trial HPO `PLANNED_ONLY`; env overrides are not a search |
| ResNet18 | Training script, pretrained recipe, search, seed and serialization not found in primary source scan | checkpoint/val/test/timing `NOT_FOUND` | v2 requirement `PLANNED_ONLY`; Small/B0 cost comparisons are different architectures |
| XGBoost | telemetry notebook cells 3/5/7: 8 ordered raw features, seed42, max400 trees/depth6/LR.1/subsample.9/colsample.9/lambda1, early stop30 on validation mlogloss; best_iteration90 | JSON present, val/test metrics and class report. **This audit:** 4500 test rows, accuracy .9993333333, macro-F1 .9993331847 (`ML-TELEMETRY`) | baseline evaluation/inference `TEST_PASSED`; five-model HPO requirement not fulfilled by early stopping |
| Random Forest (telemetry) | no training pipeline/search/scaler/seed evidence | checkpoint/metrics/timing `NOT_FOUND` | `PLANNED_ONLY` |
| Logistic Regression (telemetry) | no telemetry pipeline. `ml/experiments/linear_probe.py:103` fits an **image backbone head**, not 8-feature telemetry LR | telemetry LR artifact/metrics `NOT_FOUND` | `PLANNED_ONLY`; train-only scaling/imputation must be implemented later |

All five must receive bounded tuning; a fixed baseline is not tuned because a validation split exists. No new training, HPO, model downloads or conversions were executed in this audit.

## Data provenance and leakage checks

`CURRENT_VERIFIED` metadata checks in [data_artifact_audit.json](evidence/data_artifact_audit.json), reproduced by the metadata script in [audit_commands.md](evidence/audit_commands.md):

| Branch | Location and verified observations | Remaining uncertainty |
|---|---|---|
| Vision | external sibling root `/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment-`; `eda_outputs/processed/vision/vision_metadata_with_split.csv`; 15899 train/2868 val/3657 test; drivers18/4/4; all pairwise driver intersections=0; duplicate image paths=0; missing paths=0 | No pixel-hash or near-duplicate frame audit; only 4 test drivers, frame-level count is not independent-person sample size. Training notebook trusts split CSV rather than enforcing driver assertions itself |
| Telemetry | `eda_outputs/processed/telemetry/telemetry_{train,val,test}.csv`: 21000/4500/4500; 3 balanced classes; no missing values, exact complete-row duplicates or intersplit complete-row overlap | No immutable source_record_id; exact-row checks cannot establish independent underlying sources/generator conditions; split-generator seed and imputation fit provenance not reconstructed |
| Feature exclusions | CSV/schema/model list contains exactly eight intended features; phone_usage/reaction_time excluded. Sibling `EDA_Data_Cleaning_Final_Report.md:30–35` states rationale | Exclusion does not remove near-separability of rule-generated labels; original dataset generation and license not independently verified |
| Immutable split | current CSV and checkpoint hashes recorded | Hashing today is a snapshot, not proof that historical training used immutable hashes or that repeated test inspection never influenced decisions |

Vision CSV SHA256 `b4f8e90dec769bb419eaa490aea869668bed6484089cebe4d545c7667baa8ea4`; telemetry test SHA256 `3bc3d47680a87359e1470fd8ffaf5ff330dc4419b37cc645e5736d51a91c96de`. Train/val hashes in evidence JSON. Freeze these before comparator work; track source IDs plus split assignment and content fingerprints.

Vision preprocessing is verified by service-vs-torchvision test (`test_live_inference.py:195–219`). No left/right-invalid horizontal flip appears in current training augmentation. Rotation/crop still requires semantic QC. Stored full-test class report identifies c9 recall≈.2733/F1≈.3972 and c8 F1≈.7979; these are inherited class metrics, not reproduced in the 20-image audit smoke. Do not tune against these particular held-out images; use validation errors for development.

## Current measurements and interpretation

- `ML-VISION-SMOKE`: random seed42 sample of 20 held-out records, accuracy .9, macro-F1 .6575758 with the script's fixed 10-class denominator. Some classes are absent. Actual PyTorch/ONNX parity covers **16 samples / 8 classes**, despite requested budget20, max probability difference `1.7285347e-6`, zero argmax disagreement. It verifies reload/preprocessing/parity only for those inputs, not full-test performance or c9 robustness.
- `ML-TELEMETRY`: all4500 records; best-iteration prediction reproduced baseline. Using all saved trees changes probabilities by max `.0792410` although accuracy remains the same. Live provider correctly uses `[0,91)` (`trained.py:56–58,115`).
- Telemetry forward-only timing: p50 `.033875ms`, p95 `.042004ms`, CPU, 2 model threads, 20 warmups/100 iterations; excludes feature extraction and DMatrix. Hardware recorded as macOS26.6.2 arm64; precise CPU/memory query was sandbox-blocked. Therefore this is a limited host diagnostic, not a defensible target-device benchmark or E2E target pass.
- Historical vision benchmark has CPU p50/p95 and model sizes, but is not a current device claim. Do not compare random-weight Small/B0 timing to fine-tuned accuracy. Retain accuracy+macro-F1+class precision/recall+confusion; ROC/PR only for explicitly defined valid one-vs-rest targets. Binary distraction is distinct from 10-class argmax.
- No mandatory probability-calibration run found. Record probability comparability/interpretation limitation; do not make calibration a new Week7 gate. RiskScore is an operational indicator, not calibrated accident probability.

## Bounded HPO proposal — PLANNED, requires subsequent implementation authorization

| Model | Finite proposal | Maximum initial budget | Selection and artifact |
|---|---|---|---|
| MobileNetV3-Large | LR {1e-4,3e-4,8e-4} × wd {1e-4,1e-3}; fix current valid augmentation/resolution/batch | 6 seed42 trials × max8 epochs, patience2; chosen config additionally seeds43,44, same cap: ≤8 runs/model | validation macro-F1 primary, predefined class-recall and measured latency reporting; retain existing baseline untouched |
| ResNet18 | same LR×wd and augmentation; declare own architecture/head/pretraining recipe | same 6+2 capped runs, no test access | common split, early stop on val macro-F1; disclose differing upstream pretraining and compute |
| XGBoost | depth {3,6} × LR {.03,.1} × subsample {.8,1}; fix colsample.9/lambda1 | 8 trials, max400 trees, early stop30 on validation; 2 confirmation seeds for selected config | use val macro-F1 for across-trial ranking; log internal early-stop criterion separately |
| RF | trees {200,400} × depth {None,12,24}, min_leaf fixed2 | 6 trials +2 selected-config seeds; n_jobs2 | train-only median preprocessing shared with other telemetry models |
| LR | C {.01,.1,1,10,100,1000}, fixed lbfgs, max_iter1000 | 6 trials +2 reproducibility checks if stochasticity exists; do not present deterministic duplicates as independent evidence | median + StandardScaler fit on train only in pipeline; val-only selection |

Budget is a proposed ceiling, not a claim of feasibility on unspecified target hardware. Stop on agreed wall-time cap and document incomplete trials; do not expand silently. Compare untouched baselines too. Freeze selection before one final held-out evaluation; past baseline test exposure must be disclosed, so avoid calling it a pristine never-seen test. Consider a newly sealed external holdout if feasible, not necessary for this audit.

Each future run must emit `run_id/config.json`, split/model/content hashes, seed, commit+dirty snapshot, preprocessing/class/feature/unit contract, `trials.csv`, validation metrics and class reports, selection record, chosen checkpoint, final test predictions with IDs, confusion/ROC-PR if valid, and timing raw samples (warmup vs measured, batch, threads, provider, device). None of these proposed paths implies current file existence.

## External DMD feasibility / supervisor gate

DMD access/license, actual local clips, interval/frame labels and a faithful mapping manifest were **NOT_FOUND in the audited primary repository**. No download or entitlement claim was made. This is `BLOCKED` for quantitative external validation, not a blocker to finishing this audit.

Before use: obtain documented access/license; inspect RGB viewpoint and action intervals; predeclare compatible mapping/coverage; extract at a fixed rate with frame timestamps and clip/person grouping; detect adjacent-frame duplication; keep external test separate from target-domain tuning. A frame classifier can consume extracted frames; video architecture is not inherently required. If only a compatible binary/subset mapping exists, report that restricted task. No invented 10-class cross-dataset accuracy, no grayscale-as-IR claim, no synthetic substitute called external validation.

## Stored validation metrics (artifact inspection only)

These are `FYP1_REPORTED` / inspected stored values, not freshly rerun validation.

| Model | Validation accuracy | Validation macro-F1 | Source |
|---|---:|---:|---|
| vision baseline | 0.897489540 | 0.890650772 | `ml/outputs/vision/metrics.json` / metrics.val |
| telemetry baseline | 0.998444444 | 0.998444443 | `ml/outputs/telemetry/metrics.json` / metrics.val |
