# A. State Farm test + DMD test：stable 与 DMD 候选（2026-11-02）

**问题**：`dmd_adapted_mobilenet_v3_20261029` 在 DMD body 视角微调后，对源域（State Farm）是否明显变差？
在 DMD 留出测试集上，它相对 stable 的差异是什么？

**性质**：描述性对比。没有选模型、没有改阈值/权重、没有改在役模型。

## 命令

```bash
.venv/bin/python scripts/dmd_candidate_eval.py \
  --out docs/evidence/2026-11-02/dmd-candidate/a-source-domain
```

协议门禁：`docs/fyp2/dmd-candidate/protocol.json` 的提交 = `a198a15`（2026-11-02T18:20:19+08:00），
早于本次运行；运行记录在 `results.json` 的 `protocol_gate`。脚本 sha256 也记录在 `results.json`。

## 输入与模型

| 项 | 值 |
|---|---|
| State Farm 输入 | p4b 冻结清单 `.../p4b_20261022/shared_inputs/vision_sources.json`，sha256 `098001f1…` |
| State Farm 规模 | 3657 帧；测试司机 `p012/p026/p035/p050`；各类 support 与 p4b 一致 |
| State Farm 推理 | provider preprocess → provider 的 ONNX session → logits → **float64 softmax**；两个模型各一个子进程。这不是完整的 `TrainedProvider.infer` 调用 |
| DMD 输入 | `sampling_manifest.csv` 的 `split == test`：1354 帧；受试者 `gC_13`/`gE_29` |
| DMD 推理 | `scripts/dmd_infer_test.py`，两个 ONNX 同一段 preprocess/infer/softmax |
| stable | `stable_mobilenet_v3_large`，ONNX sha256 `b3a42e8d…` |
| DMD 候选 | `dmd_adapted_mobilenet_v3_20261029`，ONNX sha256 `01f1d6a3…` |

输入清单与每张图的 sha256 在运行前全部核对，未重新划分、未重新编码。

## 结果（State Farm 冻结测试集）

来源：`results.json` → `state_farm.metrics.*.provider_path`；`summary.csv`；`state_farm/per_class.csv`。

注意：`state_farm/predictions_*.json` 中的 `provider_probs` 是从 provider session 的 logits
再做一次 **float64 softmax** 得到的，与 `float64_probs` 逐元素相同（最大差 0.0）。这个字段名
不表示 provider 的 float32 softmax；`provider_path` 也只是沿用运行结果的键名。

| 指标 | stable | DMD 候选 |
|---|---|---|
| accuracy | **0.8988** | 0.8091 |
| macro-F1 | **0.8746** | 0.7266 |
| log loss | **0.5745** | 0.8030 |
| c0→分心比例（P_distraction ≥ 0.5） | 0.0905（39/431） | **0.0487**（21/431） |
| 分心帧召回（≥ 0.5） | **0.9721** | 0.9510 |
| 二分类准确率（0.5） | **0.9647** | 0.9511 |

逐类（完整 10 类）：

| class | stable P | stable R | stable F1 | DMD P | DMD R | DMD F1 | support |
|---|---|---|---|---|---|---|---|
| c0 | 0.8102 | 0.9211 | 0.8621 | 0.6779 | 0.9768 | 0.8004 | 431 |
| c1 | 0.9813 | 0.9000 | 0.9389 | 0.9310 | 0.6943 | 0.7954 | 350 |
| c2 | 0.9890 | 1.0000 | 0.9945 | 0.7780 | 1.0000 | 0.8752 | 361 |
| c3 | 0.9852 | 0.9803 | 0.9828 | 0.9279 | 0.9803 | 0.9534 | 407 |
| c4 | 0.9483 | 0.9747 | 0.9613 | 0.8697 | 0.9797 | 0.9214 | 395 |
| c5 | 0.9074 | 0.9901 | 0.9470 | 0.9416 | 0.9926 | 0.9664 | 406 |
| c6 | 0.9102 | 0.9894 | 0.9482 | 0.6205 | 0.9921 | 0.7635 | 379 |
| c7 | 0.8503 | 0.9941 | 0.9166 | 0.9091 | 0.9792 | 0.9429 | 337 |
| c8 | 0.7664 | **0.8321** | 0.7979 | 1.0000 | **0.0679** | **0.1271** | 280 |
| c9 | 0.7265 | **0.2733** | 0.3972 | 1.0000 | **0.0643** | **0.1208** | 311 |

**本数据集上的事实**：DMD 微调使 State Farm 十分类 accuracy 下降 8.97 个百分点、macro-F1 下降 14.80 个百分点。
c8（hair_makeup）召回 0.8321 → 0.0679，c9（talking_to_passenger）召回 0.2733 → 0.0643。
同时 c0 误报率从 0.0905 降到 0.0487，分心帧召回从 0.9721 降到 0.9510。

## 结果（DMD body 测试集）

来源：`results.json` → `dmd_test.metrics.*`；`summary.csv`；`dmd_test/per_class.csv`。

| 指标 | stable（零样本） | DMD 候选 |
|---|---|---|
| accuracy | 0.2777 | **0.7171** |
| macro-F1 | 0.3105 | **0.5065** |
| log loss | 3.4896 | **0.9586** |
| c0→分心比例 @0.5 | 0.8157 | **0.2074** |
| 分心帧召回 @0.5 | **0.9531** | 0.7881 |
| rocAUC | 0.7390 | **0.8570** |
| c0 召回 | 0.1951 | **0.8863** |
| c8 召回 | **0.8154** | 0.0154 |
| c9 召回 | **0.5167** | 0.0000 |

DMD 候选在 0.5 阈值下的操作点：FPR **0.2074**、recall **0.7881**；
历史 0.7038 那一列：FPR **0.0891**、recall **0.6344**。**运行时等价的是 0.5 列**：
系统直接融合连续值 `P_distraction = 1 − P(safe_driving)`，0.7038 阈值不在产品路径上
（`protocol.json` → `c_threshold_semantics`）。

c8/c9 的退化在 DMD 测试集上同样存在：c8 召回 0.8154 → 0.0154，c9 0.5167 → 0.0000。
macro-F1 的整体提升（0.3105 → 0.5065）不能掩盖这两类。

## 交叉核对

| 对照 | 结果 |
|---|---|
| State Farm stable vs p4b `MN-STABLE.clean` | accuracy、macro-F1、混淆矩阵一致；p4b 缓存 float32 logits 与本轮 provider session logits 最大差 **2.5e-5**；log loss 差 **5.815e-9**（0.574453149292 vs 0.574453143476） |
| DMD stable vs 2026-10-29 `zero_shot_unexposed.json` | 输入文件/标签逐项一致；概率最大差 **0.0**；accuracy/macro-F1 一致 |
| DMD 候选 vs 2026-10-29 `comparison_test.json` | accuracy/macro-F1 在存档四舍五入范围内一致；逐类差 < 1e-4；0.5 二分类各指标差 ≤ 4.9e-5（存档只保留有限位） |

**status = PASS_WITH_WARNINGS**，唯一 warning 是 p4b 的 log loss 差 5.8e-9，超过协议写下的
严格 1e-9。原因已核实：p4b 缓存的 float32 logits 与本轮 provider 路径的 logits 最多相差
**2.47955322265625e-05（最差样本 `vision-v1:c4/img_67465.jpg`）**；逐样本 argmax 和混淆矩阵
完全一致，softmax 后的 log loss 因此只差 5.8e-9。没有隐藏这个差异，也没有放宽协议。

## 能证明 / 不能证明

**能证明（仅限这些数据集）**

- 在同一份 3657 帧 State Farm 冻结测试清单上，DMD 候选的十分类整体指标低于 stable，
  且 c8/c9 召回大幅下降；c0 误报率同时下降。
- 在同一份 1354 帧 DMD 测试清单上，DMD 候选的十分类 accuracy/macro-F1 更高；二分类中
  FPR、精确率、平衡准确率和 ROC-AUC 更好，但 0.5 阈值下的分心召回率更低（0.9531→0.7881）；
  c8/c9 仍然接近失效。
- 两个模型都通过同一段代码、同一批输入重算，且与历史存档可核对。

**不能证明**

- 不能证明正面摄像头、真实车内光照/遮挡/运动下的准确率；DMD 是 body 视角，State Farm 是侧视。
- 不能证明风险分数或安全收益；这里没有同步的多模态风险真值。
- 不能用 0.7038 列描述运行时误报率；运行时没有这个阈值。
- 不能从 1354 帧、2 名测试受试者推出总体性能或置信区间。
- 不能推断训练充分性或跨受试者泛化：DMD 只用 `gA_1`、`gA_5`、`gB_6` 三名受试者、共 **2005 帧**
  训练；checkpoint 按**唯一验证者 `gB_10`** 的 macro-F1 选出，是 **9 轮中的第 1 轮**，
  `training_history.json` 记录 `converged = false`。只训练一次（seed 42），没有多种子或 k-fold。

## 候选包 `evaluation_metrics.json` 的处理

`ml/outputs/candidates/dmd_adapted_mobilenet_v3_20261029/evaluation_metrics.json` 仍是 `{}`，
**没有原地修改**。本次指标全部写在本证据目录；candidate 包只作為运行时制品被读取。

## 文件

| 文件 | 内容 |
|---|---|
| `results.json` | 身份、门禁、输入统计、全部指标、交叉核对、状态 |
| `summary.csv` | 两数据集的并列摘要 |
| `state_farm/predictions_<model>.json` | 3657 张图的 provider session logits、float64 softmax 概率、argmax；`provider_probs` 与 `float64_probs` 相同 |
| `state_farm/per_class.csv` / `confusion_<model>.csv` / `binary_diagnostics.csv` | 逐类与混淆矩阵、二分类诊断 |
| `dmd_test/predictions_<model>.json` | 1354 帧的 logits、概率、P_distraction |
| `dmd_test/per_class.csv` / `confusion_<model>.csv` / `binary_diagnostics.csv` | 逐类与混淆矩阵、0.5 与 0.7038 两列 |
| `tests-RED.log` / `tests-GREEN.log` | 先写失败测试、后实现通过 |
