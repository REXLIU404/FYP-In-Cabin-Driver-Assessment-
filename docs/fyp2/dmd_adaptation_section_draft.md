# DMD body 视角域适应：外部验证节草稿

> 供第 5 章外部验证节使用。所有数字取自 `docs/evidence/2026-10-29/dmd-adaptation/`，
> 每个表格都标注了来源文件。本文不声称任何安全收益或事故风险降低。

## 5.x.1 协议

| 项 | 取值 |
|---|---|
| 数据集 | DMD (Driver Monitoring Dataset)，body 视角，RGB |
| 许可 | CC BY-NC-ND 4.0；模型权重不随论文发布 |
| 受试者 | 6 人 / 19 个标注 session（`gA_1, gA_5, gB_6, gB_10, gC_13, gE_29`） |
| 采样 | 按 `driver_actions/*` 标注区间，每 30 帧取 1 帧（1 FPS） |
| 同步 | `body_frame_idx = annotation_frame_idx − frame_shift`；`gB_10_s3_0313` 用 20（官方 14，互相关复检 18–20） |
| 类别 | 10 类，映射见 `FYP2-DMD-zero-shot/manifests/label_mapping.json` |
| 划分 | 按受试者：train `gA_1+gA_5+gB_6` / val `gB_10` / test `gC_13+gE_29` |
| 帧数 | 4141（train 2005 / val 782 / test 1354） |
| 基线模型 | `stable_mobilenet_v3_large`（ONNX `b3a42e8d…`） |
| 微调 | 解冻 `features[15:17]` + `classifier`，AdamW（1e-4 / 1e-3），batch 32，≤30 轮，patience 8 |
| BatchNorm | 全部 BN 层全程 `eval()`，每 epoch 断言 |
| 损失 | 不加权 CrossEntropy |
| 阈值 | 仅在 val（`gB_10`）上按 FPR ≤ 0.10 选择；test 不参与任何选择 |

**开发期不接触 test**：checkpoint、预处理、阈值、ONNX 全部冻结后，才第一次对 test 推理。

## 5.x.2 零样本基线（test 集）

来源：`zero_shot_unexposed.json`

| 指标 | 值 |
|---|---|
| accuracy | 0.2777 |
| macro-F1 | 0.3105 |
| FPR @0.5 | 0.8157 |
| recall @0.5 | 0.9531 |
| rocAUC | 0.7390 |
| ECE | 0.3658 |

**解读**：未做域适应时，固定阈值 0.5 把 81.6% 的安全驾驶帧判为分心，因此 recall 虽高但无操作意义。rocAUC 0.739 说明排序信号仍在。

## 5.x.3 微调结果（同集对比）

来源：`comparison_test.json`、`run_config.json`

| 指标 | zero-shot @0.5 | adapted @0.5 | adapted @0.7038 |
|---|---|---|---|
| accuracy | 0.2777 | 0.7171 | 0.7171 |
| macro-F1 | 0.3105 | 0.5065 | 0.5065 |
| FPR | 0.8157 | 0.2074 | **0.0891** |
| recall | 0.9531 | 0.7881 | **0.6344** |
| precision | 0.5579 | 0.8041 | 0.8849 |
| rocAUC | 0.7390 | **0.8570** | 0.8570 |
| prAUC | 0.7117 | 0.8593 | 0.8593 |
| Brier | 0.3500 | 0.1482 | 0.1482 |
| ECE | 0.3658 | **0.0523** | 0.0523 |

rocAUC 与 prAUC 与阈值无关；FPR / recall / precision 随阈值变化。

### 逐类指标（test，10 类全列）

来源：`comparison_test.json` → `adapted_per_class` / `zero_shot_per_class`

| 类 | support | zero P | zero R | zero F1 | adapt P | adapt R | adapt F1 |
|---|---|---|---|---|---|---|---|
| c0 safe_driving | 651 | 0.794 | 0.195 | 0.313 | 0.730 | **0.886** | 0.801 |
| c1 texting_right | 69 | 0.500 | 0.014 | 0.028 | 0.473 | 0.377 | 0.419 |
| c2 talking_phone_right | 144 | 0.907 | 0.271 | 0.417 | 0.727 | **0.944** | 0.822 |
| c3 texting_left | 78 | 0.941 | 0.410 | 0.571 | 0.892 | 0.423 | 0.574 |
| c4 talking_phone_left | 168 | 0.920 | 0.274 | 0.422 | 0.822 | 0.768 | 0.794 |
| c5 operating_radio | 56 | 0.759 | 0.732 | 0.745 | 0.764 | 0.750 | 0.757 |
| c6 drinking | 40 | 0.000 | 0.000 | 0.000 | 0.760 | 0.475 | 0.585 |
| c7 reaching_behind | 23 | 0.273 | 0.261 | 0.267 | 0.242 | 0.348 | 0.286 |
| c8 hair_makeup | 65 | 0.148 | **0.815** | 0.251 | 0.200 | **0.015** | **0.029** |
| c9 talking_to_passenger | 60 | 0.049 | 0.517 | 0.090 | **0.000** | **0.000** | **0.000** |

**必须如实报告的两处退化**：

- **c8 `hair_makeup`**：recall 0.815 → 0.015，F1 0.251 → 0.029。微调后几乎不再被识别。
- **c9 `talking_to_passenger`**：recall 0.517 → 0.000，F1 0.090 → 0.000。完全失效。

这两类在训练集中合计 339 帧（8.2%），远少于 c0 的 1902 帧（45.9%）。macro-F1 的整体提升（0.311 → 0.507）掩盖了这两个类别的退化；报告不应只引用 macro-F1。

### 两个测试受试者的分项

| 受试者 | n | zero acc | adapt acc | zero FPR | adapt FPR | zero recall | adapt recall | zero AUC | adapt AUC |
|---|---|---|---|---|---|---|---|---|---|
| gC_13 | 653 | 0.2420 | 0.7320 | 0.8640 | 0.0765 | 0.9900 | 0.7100 | 0.6994 | **0.9014** |
| gE_29 | 701 | 0.3110 | 0.7033 | 0.5403 | 0.1040 | 0.9082 | 0.5782 | 0.8014 | 0.8303 |

两个受试者的收益不均衡：`gC_13` 的 AUC 提升 0.20，`gE_29` 只提升 0.03，且 `gE_29` 的 FPR（0.1040）略超 0.10 预算。**单个阈值无法同时满足两个受试者的同一预算**。

## 5.x.4 阈值

来源：`selected_threshold.json`

```json
{
  "threshold": 0.7037721940337633,
  "recall": 0.7962184873949579,
  "fpr": 0.09803921568627451,
  "precision": 0.9266503667481663,
  "balanced_accuracy": 0.8490896358543417,
  "feasible": true,
  "max_fpr": 0.1
}
```

在 val（`gB_10`）上选出；`feasible=true` 只说明预算在**验证集**上可达。

迁移到 test 后：FPR 0.0891（仍达标），recall 0.6344（比 val 低 16.2 个百分点）。

**不能声称**：该阈值在部署中会维持 10% 误报；也不能反过来说模型"保守"是设计选择——它是数据量与域差异的结果。

## 5.x.5 训练过程

来源：`training_history.json`

| epoch | train macro-F1 | val macro-F1 |
|---|---|---|
| 1 | 0.589 | **0.584**（best） |
| 2 | 0.731 | 0.581 |
| 4 | 0.804 | 0.334 |
| 9 | 0.895 | 0.255（early stop） |

**最佳 checkpoint 是第 1 轮**，约 63 个梯度步。之后 train 持续上升、val 持续下降，是典型的过拟合，不是收敛。

## 5.x.6 限制

1. **val 与 train 共享 group**：`gB_10`（val）与 `gB_6`（train）同属 group gB，验证指标偏乐观。这是为了让 test（gC / gE）在受试者与 group 两个层面都独立而做的取舍。
2. **两个 UNEXPOSED 受试者被消耗**：`gB_6` 用于训练、`gB_10` 用于验证，二者不再是独立测试；最终测试只剩 `gC_13` 与 `gE_29`。
3. **训练量极小**：2005 帧 / 3 个受试者，最佳模型只训练 1 轮。
4. **c7 训练样本 37 帧**：`reaching_behind` 的 F1（0.286）不足以支持任何应用结论。
5. **c8 / c9 退化**：见 5.x.3，必须与 macro-F1 一同报告。
6. **BatchNorm 统计量未更新**：沿用 State Farm 源域统计量，这是小样本下的保守选择，也意味着模型没有真正适配 DMD 的成像特性。
7. **仅 body 视角**：face 视角的零样本与微调均不在本实验范围。
8. **不推广到车载正面摄像头**：DMD body 视角与实际部署视角不同，本文不做任何跨视角推断。
9. **单次运行**：未做 k-fold 或多种子重复，指标没有置信区间。

## 5.x.7 复现

| 项 | 值 |
|---|---|
| 脚本 | `scripts/dmd_common.py` / `dmd_sampling.py` / `dmd_extract.py` / `dmd_dataset.py` / `dmd_train.py` / `dmd_threshold.py` / `dmd_evaluate.py` / `dmd_export_candidate.py` / `dmd_infer_test.py` |
| 数据 | `/Users/liu/Desktop/fyp2/ml-training/FYP2-DMD-body-v1/`（manifest + frames，git 外） |
| 证据 | `docs/evidence/2026-10-29/dmd-adaptation/` |
| seed | 42 |
| 父模型 | `mobilenetv3_large_vision.pt`（`196ca7b1…`） |
| 适配模型 | `model.onnx`（`01f1d6a3a57936590d29f1a86856fd6e67c8c9fd382f48bd601f9c66ed2b4d55`） |
| 候选 id | `dmd_adapted_mobilenet_v3_20261029` |
| 一致性 | PyTorch vs ONNX：`max_abs_diff 9.5e-07`，`top1_mismatches 0` |

复现命令见 `docs/superpowers/plans/2026-10-29-dmd-domain-adaptation.md` 的 Task 9。
