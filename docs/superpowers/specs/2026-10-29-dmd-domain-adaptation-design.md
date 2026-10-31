# DMD 域适应微调设计（2026-10-29）

## 1. 目标

在已部署的 `stable_mobilenet_v3_large` 上做一次有界的域适应微调，使其在 DMD（Driver
Monitoring Dataset）body 视角上可用，并给出可写进报告的外部评估结果。

**不是**替换 stable，**不是**做 face 视角，**不是**声称车辆级泛化。

## 2. 背景与已有证据

| 事实 | 来源 |
|---|---|
| stable 模型在 DMD 上零样本失效：10 类 acc 8.9%（gA_1 body）/ 14.2%（gA_5 body） | `FYP2-DMD-zero-shot/report.md` |
| face 视角塌缩到 `reaching_behind`（safe 误判 286/313），acc 1.6–2.4% | 同上 |
| body 视角保留排序信号：二分类 rocAUC 0.80–0.85，但固定阈值 0.5 的 FPR 0.90–1.00 | 同上 |
| 本地 DMD 原始数据：6 受试者 / 19 个已标注 session，body 与 face 视频齐全 | `/Users/liu/Desktop/DMD/` |
| 官方 2026 修订版的可用主体名单（1, 5, 6, 7, 9, 10, 13, 14, 23, 28, 29, 33, 36, 37）覆盖本地全部 6 个受试者 | DMD 官方仓库 README |
| 现成 1300 张 body 帧只覆盖 gA_1 / gA_5，不足以做受试者级划分 | `FYP2-DMD-zero-shot/frames/` |
| stable 训练配置：5 epochs / batch 64 / lr 8e-4 / MPS，15899 样本耗时 1098 s | `ml/outputs/vision/metrics.json` |

`04_ML_COMPARISON_AND_TUNING_AUDIT.md:58` 记录 DMD license `BLOCKED`；zero-shot 报告记录
许可为 CC BY-NC-ND 4.0。本设计按"本地研究、不发布权重"执行，见第 7 节。

## 3. 数据

### 3.1 来源与抽帧

原始数据在 `/Users/liu/Desktop/DMD/`，6 个受试者 / 19 个已标注 session：

| root | 受试者 | sessions |
|---|---|---|
| `dmd` | gA_1 | s1, s2, s3 |
| `dmd 2` | gA_5 | s1, s2, s3 |
| `dmd 6` | gB_6 | s1, s2, s3 |
| `dmd 10` | gB_10 | s1, s2, s3（2019-03-12）, s3（2019-03-13） |
| `dmd 13` | gC_13 | s1, s2, s3 |
| `dmd 29` | gE_29 | s1, s2, s3 |

全部 6 个受试者都在官方 2026 修订版的无限制使用名单内。许可仍为 CC BY-NC-ND 4.0。

官方 DEx（Dataset Explorer）依赖 Python 3.8 + VCD 6.0，只在 Ubuntu / Windows 测试过，
macOS 上不可直接用。DEx 抽帧的底层就是 ffmpeg 按标注区间导出，因此本设计自写等价脚本：

1. 解析每个 session 的 `*_rgb_ann_distraction.json`，取 `openlabel.actions` 中
   `type` 以 `driver_actions/` 开头的条目的 `frame_intervals`。这些帧号属于 face 时间轴。
2. 读取该 session 的**同步偏移**：`openlabel.streams.body_camera.stream_properties.sync.frame_shift`。
   `gB_10_s3_2019-03-13T14;22;40+01;00` 的官方值为 14，但 `DMD-data-prep` 的互相关复检
   估到 18–20，已由 `DMD-data-prep/data/inventory/shift_overrides.json` 覆盖为 **20**，
   本设计采用 20。其余 session 用官方 `frame_shift`。
3. 每个区间内从 `frame_start` 起每 30 帧取 1 个 annotation 帧号；
   `body_frame_idx = annotation_frame_idx − effective_shift`，负值丢弃并计数。
4. 从 `*_rgb_body.mp4` 按 **body 帧号**导出 JPEG q90（不是 annotation 帧号）。
5. 输出 `{subject}/{session}/{class_id}/{body_frame_idx:08d}.jpg`，同时写
   `sampling_manifest.csv`（subject, session, annotation_frame_idx, body_frame_idx,
   effective_shift, class_id, action, source_video）；每条跳过记录写入
   `extraction_log.json` 与原因，并记录该 session 的同步复检状态
   （`OK` / `MISMATCH` / `OVERRIDDEN`）。
6. 类别映射沿用 `FYP2-DMD-zero-shot/manifests/label_mapping.json`：`safe_drive→c0`、
   `texting_right→c1`、`phonecall_right→c2`、`texting_left→c3`、`phonecall_left→c4`、
   `radio→c5`、`drinking→c6`、`reach_backseat→c7`、`hair_and_makeup→c8`、
   `talking_to_passenger→c9`；`reach_side`、`unclassified`、`change_gear`、
   `standstill_or_waiting` 不进入训练。

抽帧规则与 zero-shot 既有 1300 帧一致，但覆盖全部 6 个受试者。**不混用**旧帧与新帧，
全部重新抽取，避免新旧口径不一致。

### 3.2 划分

按受试者划分。`c7 reach_backseat` 在**每个**受试者的 s3 都存在（视频帧数：gA_1 473、
gA_5 201、gB_6 330、gB_10 652、gC_13 247、gE_29 339），因此受试者级划分不会出现
训练集缺 c7 的问题。

| 划分 | 受试者 | group | 估计样本（1 FPS） | c7 估计 | 用途 |
|---|---|---|---|---|---|
| train | gA_1 + gA_5 + gB_6 | gA, gB | ~2232 | ~33 | 训练 |
| val | gB_10 | gB | ~851 | ~22 | 早停、选超参 |
| test | gC_13 + gE_29 | **gC, gE** | ~1472 | ~20 | 只评估 |

估计值 = 各受试者 `driver_actions` 区间总帧数 ÷ 30（gA_1 22233、gA_5 21210、gB_6 23515、
gB_10 25535、gC_13 21184、gE_29 22969）。实际数以 `sampling_manifest.csv` 为准，写入
`run_config.json`，不使用估计值作为报告数字。

测试集两个受试者属于 gC 与 gE，**两个 group 在训练和验证中都未出现**，受试者级与 group 级
都独立。

取舍说明：val 的 `gB_10` 与 train 的 `gB_6` 同属 group gB，这会让 val 指标偏乐观（早停可能偏晚）。
这是为了让**测试集在受试者与 group 两个层面都完全独立**而做的取舍；另一个方案是
val = gC_13、test = gE_29 + gB_10，val 更干净但会把 group gB 泄漏进测试集，不可接受。
报告里写明这一取舍。

holdout 消耗：`gA_1` 与 `gA_5` 原属 `EXPOSED`（已用于 zero-shot 评估与接触表复核），只能作
train/val；`gB_6` 与 `gB_10` 原属 `UNEXPOSED`（保留作独立测试），本设计分别用作 train 与
val，因此同时失去独立测试资格。最终测试只用 `gC_13` + `gE_29`，这两个受试者在 zero-shot
阶段和本设计中都未参与训练、验证或任何人工复核。这一消耗写入报告限制。

**不采用** k-fold：三折会让训练与评估组合翻倍，时间成本超出本次目标；改为在报告里注明
样本量限制，并保留一次完整复现所需的最小配置。

### 3.3 预处理与增强

推理预处理与生产一致（`backend/app/providers/trained.py`）：PIL RGB → 双线性 resize
224×224 → /255 → ImageNet mean/std。

训练增强：

- `RandomResizedCrop(224, scale=(0.7, 1.0), ratio=(0.85, 1.18))`
- `ColorJitter(brightness=0.2, contrast=0.2, saturation=0.2, hue=0.05)`
- **不做水平翻转**：左右手是标签语义（`texting_left` vs `texting_right`）。
- **不做随机旋转**：车载相机安装角度固定，旋转不是真实变化。

## 4. 模型与训练

### 4.1 基线

`ml/outputs/vision/mobilenetv3_large_vision.pt`（sha256 `196ca7b1…`），torchvision
`mobilenet_v3_large`，10 类输出，class 顺序 c0..c9。

### 4.2 解冻策略

| 部分 | 状态 | 学习率 |
|---|---|---|
| `features[0:15]`（block 0–14） | 冻结 | — |
| `features[15:17]`（block 15 残差块 + block 16 末端 1×1 conv） | 训练 | 1e-4 |
| `classifier` | 训练 | 1e-3 |

命名说明：torchvision `mobilenet_v3_large().features` 是 17 个 block 的 `Sequential`（索引 0–16），
`features[-2:]` 精确对应 block 15 与 16，即“最后一个倒残差块 + 末端卷积”。代码中用
`features[-2:]` 表达，文档统一写“最后两个 block（15、16）”，不再使用含糊的“两个 stage”。

选择理由：训练集约 2232 帧、来自 3 个受试者，全量微调仍有把 backbone 带跑偏的风险；
线性探测的上限受限于 backbone 在 DMD 上已经塌缩的特征（zero-shot 证据）。解冻最后两个 block
是两者之间的折中。

**BatchNorm 统计量必须全程冻结**。`requires_grad=False` 只挡梯度，不挡 `running_mean` /
`running_var` 更新；训练时 `model.train()` 会让全部 BN 层用当前 batch 覆盖 stable 模型在
15899 张图上沉淀的统计量。每个 epoch 按下列顺序设置（顺序不能反，先 eval 再 train 会把 BN
切回训练模式）：

```python
model.train()
model.features[:-2].eval()
for m in model.modules():
    if isinstance(m, torch.nn.BatchNorm2d):
        m.eval()
```

即：解冻层的卷积核与 `classifier` 适应 DMD 姿态，BN 统计量一律沿用 stable 的值。这条写成
训练脚本的断言：每个 epoch 结束时检查全部 BN 层 `training == False`，不满足就报错退出。

### 4.3 训练配置

| 项 | 值 |
|---|---|
| optimizer | AdamW |
| weight_decay | 0.01 |
| scheduler | CosineAnnealingLR（T_max = epochs） |
| epochs | 30（早停 patience 8） |
| batch_size | 32 |
| 早停指标 | val macro-F1 |
| 保存 | val macro-F1 最高的 checkpoint |
| seed | 42（与 Task 10A 候选一致） |
| device | MPS |

轮数上限固定 30，**不设 60 轮放宽**。2232 帧 / batch 32 约 70 step 每 epoch，30 轮共约
2100 步，对 5.5M 参数的 MobileNetV3 足够收敛。若第 30 轮 val macro-F1 仍在上升，报告标注
"未收敛"，不做延长——val 与 train 共享 group gB，继续训练大概率在拟合 gB 的车厢光照与
相机位置，而不是学到可迁移的分心特征。报告同时给出 val 与 test 的逐轮或末期对照，
用来验证"val 偏高、test 下降"这个假设是否成立。

### 4.4 类别不平衡与阈值

训练集 c0 占 39.8%（26645/66958 帧）、c7 占 1.5%（1004/66958 帧）。

**不做类别加权。** 风险公式是 `P_distraction = 1 − P(c0)`，任何压低 c0 损失权重的做法都会
直接推高 FPR。按 `w_c ∝ (1/freq_c)^0.5` 归一化到均值 1 后，c0 的权重是 0.543；即使
`clamp(min=1.0)` 再归一化也只有 0.846，仍低于所有分心类（c7 为 2.366）。zero-shot 的 FPR
已经是 0.90–1.00，再推高没有报告价值。

改用阈值选择。训练完成后，在 val（gB_10）上扫描 `P_distraction` 阈值，选一个满足
FPR ≤ 0.10 且 recall 最大的阈值，记录为 `selected_threshold`。测试集同时报告两组数字：

1. 固定阈值 0.5（与 zero-shot 协议可直接对比）
2. val 选出的阈值（本模型的实际工作点）

并总是报告阈值无关的 rocAUC。阈值只在 gB_10 上选，gC / gE 不参与任何阈值或超参选择。

**报告方式**：主结果是**不加权**训练。另跑一次加权对照（c0 权重用
`max(weights[0], weights[1:].max())`），只用于说明加权的代价，不进入主表。两条阈值下的
FPR–recall 对照必须同时给出，不允许只报告好看的一栏。

## 5. 评估协议

### 5.1 指标

复用 zero-shot 协议，保证可比：

- 10 类：accuracy、macro-F1、per-class precision/recall/F1、混淆矩阵
- 二分类（`P_distraction = 1 − P(c0)`）：recall、FPR、rocAUC、prAUC、balanced-accuracy、
  Brier、ECE（10 bin）
- 阈值：固定 0.5（与 zero-shot 可比）与 val 选出的 `selected_threshold`（工作点）各报告一组，
  并附阈值无关的 rocAUC；两条阈值的 FPR–recall 对照必须同时给出

### 5.2 对比基线

zero-shot 报告只覆盖 gA_1 / gA_5，**没有**测试集两个受试者（gC_13 / gE_29）的数字。
为形成同集对比，本设计在**冻结之后**做一次统一评估：

**开发期间（训练、选阈值、选超参）只看 train 与 val，不接触 test。** 任何 test 指标在
checkpoint、预处理、阈值和最终 ONNX 全部冻结之前不得产生，避免测试集影响任何选择。

冻结时的顺序固定为：

1. 冻结 `best.pt`、预处理参数、`selected_threshold`；导出最终 ONNX（含真实 `contract_smoke_set`）。
2. 同一命令、同一批 test 帧上分别推理 stable ONNX 与 adapted ONNX，得
   `zero_shot_unexposed.json` 与 `adapted_unexposed.json`；
3. 两张表逐项对比，并分别报告两个测试受试者的分项结果。

`gB_10` 作为验证受试者，其零样本数字单独记录在 `zero_shot_val.json`，只用于说明验证集上的
变化，**不进入**测试对比表。

### 5.3 报告要求

- 每一类都必须列出，不允许只报告 c0 或 c2。
- 若 macro-F1 低于零样本在 body 上的表现，如实报告，不隐瞒。
- 明确写出：结果只对 DMD body 视角成立，不推广到车载正面摄像头。

## 6. 产物

### 6.1 模型包

写入 `ml/outputs/candidates/dmd_adapted_mobilenet_v3_20261029/`：

- `model.onnx`（opset 与现有候选一致，输入名 `input`，输出名 `logits`）
- `runtime_manifest.json`（`manifest_version: 1`，`preprocess:
  rgb_resize_224_bilinear_no_crop_div255_imagenet`，`class_to_idx` c0..c9，
  `provenance.parent_model_sha256` 指向 stable checkpoint）
- `class_metadata.json`（`runtime_aliases: {c0: safe_driving}`）
- `evaluation_metrics.json`（第 5 节的指标）

`runtime_manifest.json` 必须通过 `backend/app/runtime_manifest.py` 的 `validate_package`。
该 schema 顶层 `additionalProperties: false`，且 `contract_smoke_set` 是**必填**字段，
`rule` 只能是常量 `per_class_mode_equals_label`。本包的取值：

| 字段 | 值 |
|---|---|
| `split` | `val` |
| `selection` | `gB_10 val frames grouped by class; each class contributes up to 20 by filename, classes with fewer frames contribute all they have` |
| `n` | `Σ_c min(20, count_c)`，由 gB_10 抽帧结果计算 |
| `sample_ids_sha256` | 上述 sample id 按文件名排序拼接后的 SHA-256，实施时计算 |
| `rule` | `per_class_mode_equals_label` |

`n` 与 `sample_ids_sha256` 是抽帧结果的派生值，不是设计决策；实施时由 `sampling_manifest.csv`
计算并写入，spec 不预设具体数字。

该字段只作为契约记录，运行时**不执行**（`vision_candidates.py` 只校验结构，不跑 smoke
推理）。任一类别的众数预测不等于标签时如实记录，不修改 `rule` 或缩小 `n` 去凑通过。

`provenance` 是自由对象，但键名不能命中 `runtime_manifest.py` 的 `METRIC_WORDS`
（f1 / accuracy / auc / ece / brier / loss / metric 等），指标只能放 `evaluation_metrics.json`。

写入 `ml/outputs/candidates/index.json` 的新条目：

```json
"dmd_adapted_mobilenet_v3_20261029": {
  "package": "dmd_adapted_mobilenet_v3_20261029",
  "role": "EXTERNAL_DOMAIN_ADAPTED",
  "architecture": "mobilenet_v3_large"
}
```

`role` 是新增值。`vision_candidates.py` 只读 `package`，`scripts/compare_vision_models.py`
没有读取 `role`（已 grep 确认），因此新增取值不影响任何加载或比较路径。

### 6.2 证据

`docs/evidence/2026-10-29/dmd-adaptation/`：

- `zero_shot_unexposed.json`、`adapted_unexposed.json`
- `per_class_metrics.json`、`confusion_matrix.png`
- `training_history.json`（loss / val macro-F1 逐 epoch）
- `run_config.json`（seed、超参、checkpoint sha256、数据划分哈希、`selected_threshold`、
  两条阈值下的 FPR/recall、BN 断言自检结果）

### 6.3 报告章节草稿

`docs/fyp2/dmd_adaptation_section_draft.md`，供第 5 章外部验证节使用。

## 7. 风险与限制

| 风险 | 处理 |
|---|---|
| CC BY-NC-ND 4.0 的 ND 条款禁止分发衍生作品 | 权重只留本地 `ml/outputs/`（已 git-ignore）；报告写明"权重不随论文发布" |
| 训练集约 2232 帧，受试者级差异大 | 部分解冻 + 早停 + 数据增强；逐受试者报告指标 |
| c7 训练样本约 33 个 | 不承诺 c7 指标；逐类如实报告 |
| val 只有单一受试者（gB_10），且与 train 的 gB_6 同组 | 早停指标噪声大且偏乐观；严格 30 轮上限；报告里说明 |
| `gB_6` / `gB_10` 原属 UNEXPOSED，用作 train/val 后失去独立测试资格 | 最终测试只用 gC_13 + gE_29；报告写明这一消耗 |
| BN running statistics 被 3 个受试者覆盖 | 每个 epoch 强制全部 BN 层 `eval()`，并在 epoch 末断言 `training == False` |
| 阈值在 val 上选，与零样本固定 0.5 不可直接比 | 两组阈值都报告，并附阈值无关的 rocAUC |
| 自写抽帧脚本与官方 DEx 可能不一致 | 抽帧规则写成显式参数并固定；随机抽 20 帧人工核对帧号与标注区间 |
| 全部重抽后，zero-shot 旧数字不可直接复用 | 在测试集上重跑 stable 基线（第 5.2 节） |

## 8. 不做的事

- 不改 `stable` 的模型文件、默认配置或任何现有证据。
- 不改 `backend/`、`frontend/`、`viva_v1`、`session_001/telemetry.csv`、`viva_compact` 场景。
- 不做 face 视角微调。
- 不做双分支（face + body）融合。
- 不做 k-fold 交叉验证。
- 不做温度校准：阈值选择已经确定工作点，温度缩放不改变 rocAUC，只会增加一个需额外报告的自由度。
  若实施中确实需要，必须在报告里并列校准前后的 recall / FPR / ECE，不得声称"全面提升"。
- 不下载任何新数据。
- 不修改 `FYP2-DMD-zero-shot/` 与 `FYP2-DMD-expanded/`（只读引用）。

## 9. 验收标准

1. 按第 3.1 节的规则对 19 个 session 抽帧，每个 session 的帧号均落在其标注区间内；跳过的
   记录在 `extraction_log.json` 中逐条给出原因，各类别与各受试者的成功数记入 `run_config.json`。
2. `zero_shot_unexposed.json` 与 `adapted_unexposed.json` 使用同一批帧、同一预处理。
3. 相同帧上重新推理，输出字节级可复现（固定 seed 与 deterministic 设置）。
4. candidate 包通过 `backend/app/runtime_manifest.py` 的 `validate_package`。
5. `DRA_ACTIVE_VISION=dmd_adapted_mobilenet_v3_20261029` 启动后 `/api/models` 报告的身份
   与 `runtime_manifest.json` 一致；切回 `stable` 后行为不变。
6. 现有测试全绿：`pytest`、`vitest`、`tsc`、`eslint`、`build`。
7. 训练日志逐 epoch 记录全部 BN 层的 `training` 状态，断言均为 `False`；任一 epoch 不满足
   则训练失败退出，不产出候选包。
8. 报告草稿含逐类指标、混淆矩阵、与零样本的同集对比，以及第 7 节的全部限制。
