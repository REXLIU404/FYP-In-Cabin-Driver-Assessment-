# B. 运行时兼容性与 provider 一致性（2026-11-02）

**问题**：`dmd_adapted_mobilenet_v3_20261029` 能否按现有 runtime manifest 被后端 provider 加载？
provider 的数值路径与直接跑 ONNX 是否一致？

**性质**：兼容性检查，不评价模型准确率，不切换在役模型。

## 命令

```bash
.venv/bin/python scripts/dmd_candidate_runtime_check.py \
  --out docs/evidence/2026-11-02/dmd-candidate/b-runtime-compat
```

协议门禁：`docs/fyp2/dmd-candidate/protocol.json` 的提交 `a198a15`，早于运行。
候选包只读；`evaluation_metrics.json` 仍为 `{}`，未修改。

## 1. runtime manifest 校验

`scripts/validate_runtime_manifest.py` 的完整输出见 `manifest_validation.json`：

```
valid
exit code 0
```

校验内容包括 manifest schema、`classes`/`class_to_idx`/`safe_class`、`run_id`、
模型文件 containment 与 `model.onnx` 的 sha256。

## 2. Provider 身份（`DRA_ACTIVE_VISION=dmd_adapted_mobilenet_v3_20261029`）

来源：`provider_identity.json`（子进程里真实 `TrainedProvider` 的 `info`）。

| 字段 | 值 |
|---|---|
| provider name | `VisionCandidateONNX+XGBoost` |
| vision.model_id | `dmd_adapted_mobilenet_v3_20261029` |
| vision.source | `candidate:dmd_adapted_mobilenet_v3_20261029` |
| vision.sha256 | `01f1d6a3a57936590d29f1a86856fd6e67c8c9fd382f48bd601f9c66ed2b4d55` |
| architecture | `mobilenet_v3_large` |
| runtime | `onnxruntime_cpu`，输入 `RGB NCHW float32 224x224` |
| classes | `safe_driving, texting_right, …, talking_to_passenger`（c0 = safe_driving） |
| telemetry sha256 | `9802cb06…`（stable XGBoost，未变） |

身份检查：`identity_ok = true`。如果 `DRA_ACTIVE_VISION` 未生效，worker 会报错而不是回退到 stable。

## 3. Provider 预处理 + provider ONNX session vs 独立 ONNX（200 张 State Farm 图）

样本规则（协议预先声明）：从 p4b 冻结测试清单按类排序，每类取前 20 个文件名，共 200 张；
`source_ids_sha256 = 082a8108591bb0c5a21f7ccfe360b191e7d53705e4a17e4b4b70f3931de1752d`。

方法：provider 的 `preprocess` 张量同时送入
(1) provider 持有的 ONNX session 与 (2) 另一个独立加载的 ONNX session；
两侧都做一次相同的 float32 softmax，再转 float64 比较。这不是完整的
`TrainedProvider.infer` 调用：本检查不经过 fusion/EMA/HTTP，也不比较
`visual_top_classes` / `P_distraction_raw` 的整条响应路径；完整 `/infer` 路径由其他测试覆盖。

**判定规则（不事后放宽）**：`max_abs_prob_delta <= 1e-4` 且 `argmax_agreement == 1.0`，
即 `docs/fyp2/task10a/tolerance_predeclaration.md` 的 FUD-01（2026-10-26 批准）。

| 检查 | 结果 |
|---|---|
| 样本数 | 200 |
| 最大概率绝对差 | **1.192e-06** |
| argmax 一致率 | **1.0** |
| 不一致样本 | 0 |
| **通过** | **true** |

最大差样本：`vision-v1:c1/img_11187.jpg`，两侧 top-1 均为 c1（margin 0.4832），
逐类差见 `provider_parity.json` 的 `worst`。

额外信息（不属于判定规则）：provider 预处理张量与 `scripts/dmd_infer_test.py` 独立预处理的
最大张量差为 **0.0**（200/200）；用独立预处理再跑 ONNX 与 provider 概率的最大差同为 **1.192e-06**，
argmax 一致率 1.0。

## 能证明 / 不能证明

**能证明**

- 该候选包按现有 manifest 校验通过，并能由 `DRA_ACTIVE_VISION` 经真实 provider 加载。
- 在 200 张 State Farm 原图上，provider 预处理 + provider 的 ONNX session 前向与独立 ONNX
  前向在 1e-4 / argmax 1.0 内一致。

**不能证明**

- 不证明模型正确率、DMD/正面摄像头的表现，也不证明浏览器重编码后的相机路径。
- 200 张图不是全部输入分布；数值一致性不是精度证据。
- 不证明目标硬件性能（见 D 项）。

## 文件

| 文件 | 内容 |
|---|---|
| `results.json` | 合并结果、身份、样本、判定、状态 |
| `manifest_validation.json` | 校验器完整 stdout / exit code |
| `provider_identity.json` | provider 在子进程里报告的身份 |
| `provider_parity.json` | 200 张图的判定、最差样本、独立预处理对照 |
| `worker_out.json` | worker 的逐图原始概率与 argmax |
| `tests-RED.log` / `tests-GREEN.log` / `tests-candidates-GREEN.log` | 先失败、后通过；含真实 provider 的标记测试 |
