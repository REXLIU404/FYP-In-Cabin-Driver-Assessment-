# stable200 验证证据 — 2026-10-26

Task 1.4 / DS-1：`scripts/verify_stable200.py` 的一次真实运行。三个模型全部 **PASS**（exit 0），
证据目录同时保存了两类历史证据与本次新鲜 forward，三者性质不同，见下文区分。

## 三种证据的区分

### (a) ML 侧已存预测的诊断 — 历史
- 位置：`ml/outputs/candidates/<pkg>/validation/saved_prediction_diagnostic.json`（候选包内，git 忽略，未改动）
- 性质：P3 训练流程在 PyTorch（MPS/batch64）上保存的 validation 预测；`provider_load_forward=NOT_RUN`、
  `official_behavior_check=NOT_RUN`，其自身声明「diagnostic only」。
- 冻结成员哈希（与本 run 复核一致）：filename 成员 `601dc3ed6b99e9030f6eb5287e711baf529ea6c0c5b2facab0acd9c3f9373be9`，
  source_id 成员 `2697d288e384f340cb51f002ce39fca024827c6969de9dc9f2db9682246c5d75`。
- 该诊断的历史结论是 10 类唯一众数均等于标签，但**不是**本次 provider 结果。

### (b) P4A parity — 历史
- 位置：`/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/ml/outputs/runs/p4a_20261021/`
  （ML 工作区，只读；sha256 与批准版容差文件 §2 一致）
- 性质：2026-10-21 的 P4A 运行，同一张量上 PyTorch 与 ORT 的历史对比（211 个批次位置、100 个不同来源），
  `result.validation_predictions` 里的 ORT logits 是本次的**参照**。
- 历史最大概率误差：MN-STABLE 4.846e-6、RN-HPO42 2.302e-6、MN-HPO42 6.365e-6（本次未重跑 parity）。

### (c) 本次 provider 的新鲜 forward — 新
- 位置：本目录 `official_stable200_behavior.json` + 每模型一个 JSON + `worker_*` 过程文件
- 性质：2026-10-26 由 `TrainedProvider`（真实加载路径，含 DRA_ACTIVE_VISION 切换）对每张图
  「原始 JPEG 字节 base64（不重编码）→ preprocess → vision.run → 一次 float32 softmax」的 fresh forward；
  每个模型一个独立子进程（cwd=backend、PYTHONPATH=backend）。
- 输入：stable200 全部 200 图（每类 20）+ P4A100 的 100 个来源；preprocess 拒绝 0 张。

## 判定标准（批准版）

- 出处：`docs/fyp2/task10a/tolerance_predeclaration.md`（APPROVED，磁盘 sha256
  `61e3057980d0fd5ac7d697b2a198c1fa7e4c657a3d83b0c1094e37e6616e0666`，与
  `docs/fyp2/task10a/approval_record.json` 记录一致）；FUD-01 批准。
- 每个参照集合：`max_abs_prob_delta ≤ 1e-4` **且** `argmax_agreement == 1.0`（两条件同时满足）。
- 类别规则独立判定：每类 20 图的 argmax 众数集合必须恰为 `[i]`，并列众数失败。
- 稳定模型没有自己的 stable200 已存预测，其 200 图数值比较为 `null`，原因 `NO_STABLE200_REFERENCE`；
  其 100 来源数值检查照常执行，类别规则照常在 200 图上执行。

## 本次结果（全部 PASS，exit 0）

| 模型 | parity100（100 来源） | stable200 CSV（200 图） | 类别规则（200 图） | ONNX sha256 |
|---|---|---|---|---|
| `stable_mobilenet_v3_large` | max_abs=1.778e-7, argmax 100/100 ✓ | null（NO_STABLE200_REFERENCE） | all_unique ✓ | b3a42e8d…e90bcf ✓ |
| `resnet18_search004_seed42` | max_abs=1.540e-7, argmax 100/100 ✓ | max_abs=1.479e-6, argmax 200/200 ✓ | all_unique ✓ | 5e226722…71d8cf3 ✓ |
| `mobilenet_v3_large_search006_seed42` | max_abs=1.688e-7, argmax 100/100 ✓ | max_abs=6.869e-6, argmax 200/200 ✓ | all_unique ✓ | 9ee60abb…9a384828 ✓ |

- 参照文件 sha256：全部与批准版容差文件 §2 一致（parity 三份 + 两份 CSV）。
- 成员哈希：filename 与 source_id 两条规则均复算一致；两个候选包标注成员互相一致。
- preprocess 拒绝：0 张；概率向量 sanity 问题：0 个；worker exit code：0/0/0。
- 环境：python 3.13.3、numpy 2.4.6、onnxruntime 1.26.0、Pillow 12.2.0、xgboost（见各 JSON）。
- 运行命令：`.venv/bin/python scripts/verify_stable200.py --out docs/evidence/2026-10-26/stable200`。

## 目录内容

- `official_stable200_behavior.json`：合并结果（命令、exit code、成员哈希、批准版容差出处与哈希、
  三模型分区 `stable200_behavior` / `parity100_reference_comparison` / `stable200_pytorch_comparison`、
  环境版本、最差样本详情如有）。
- `<model_id>.json`：每模型分区与 worker 记录。
- `worker_spec_*.json` / `worker_out_*.json`：子进程输入清单与原始 forward 结果。

门禁证据（pytest/vitest/tsc/eslint/build）见 `../ds-stable200-gate/`。
