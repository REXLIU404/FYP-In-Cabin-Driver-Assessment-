# Task 10A 容差预声明 — CX-0

日期：2026-10-26（Asia/Kuala_Lumpur）。状态：**DRAFT / FOR_USER_DECISION**。用户尚未批准；`effective=false`，本文件不授权任何比较或 runner。本次仅查阅已有文件和冻结源码，没有新模型 forward、训练、HPO、导出或 benchmark。

## 1. 两项必须写准的事实

1. **stable200 已存 CSV 是 PyTorch 参照；P4A validation_predictions 是 ORT 参照。** P3 `ml/vision/train_hpo.py:123-124,160-169` 在 MPS/batch64 上获取 PyTorch logits/probabilities，P5 `package_candidates.py:350-357` 只筛选、复制 CSV。相反，P4A 冻结源码 `source_snapshot/ml/experiments/p4_preflight.py:116-117,129-134,434-437` 把 `actual=runtime(batch)` 存入 `single_predictions`，再写入 `result.validation_predictions`。三份 parity 文件的 `source_sha256=ffdfa6637bace58c9818ade3b9a84e812a59d2f681543927b10403061301dece` 与该冻结源码匹配。不能把这些缓存 logits 统称为 PyTorch 输出。
2. 分析 U-1 的“最大 4.85e-6”只适用于 MN-STABLE；三个模型的 P4A 最大值是 MN-HPO42 的 **6.364584130613693e-6**。下表是今日读取历史文件所得，不是今日重跑 parity。

## 2. 每模型的参照及验证范围

所有文件路径前缀：ML=`/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1`；P4A=`/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/ml/outputs/runs/p4a_20261021`；P5=`/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/ml/outputs/runs/p5_candidates_20261023`。后续 runner 必须核对参照文件 hash、source_id 和类别顺序，不能只按行号配对。

| 模型 | provider fresh forward 的输入 | 数值比较参照 | 独立的 stable200 规则 |
|---|---|---|---|
| `stable_mobilenet_v3_large`，env=`stable` | P4A100 的100个不同来源原始JPEG；每来源batch1 | `parity_MN-STABLE.json:result.validation_predictions` 的10个历史ORT logits；float64稳定softmax一次得到参照概率 | 另跑全部200图，按10类评估 `per_class_mode_equals_label` |
| `resnet18_search004_seed42` | stable200全部200图；另对P4A100全部100来源batch1 | 200图对本包 `validation/stable200_saved_predictions.csv` 中的10个 `probability_c*`（PyTorch）；100图对 `parity_RN-HPO42.json` 的历史ORT logits | 在200图的provider argmax上评估同一规则 |
| `mobilenet_v3_large_search006_seed42` | 同上 | 自己的200图PyTorch CSV；另对 `parity_MN-HPO42.json` 的100来源历史ORT logits | 同上 |

稳定模型没有自己的 stable200 saved predictions，不得借用候选的200图预测。稳定模型的数值比较 `n_compared=100`；它的类别规则 `n_behavior=200`，不应填成200图都存在数值参照。稳定200的数值差字段可写 `null`，原因 `NO_STABLE200_REFERENCE`，但100来源数值检查必须执行。

P4A 的211是历史批次位置总数（100次单图 + 32/32/32/4 + 2 + 9），不同来源仍只有100；本方案新增provider比较是每来源一次，不冒充重现历史211位置。

稳定模型没有候选式 runtime manifest；对稳定模型采用两候选 manifest 已声明的共同200成员/规则作对照诊断，不伪称它原本有一份 manifest。

模型 ONNX SHA256：

- `stable_mobilenet_v3_large`：`b3a42e8dd4553355b1fd7d9e7fe3d28e318decb894e76eb029489b7ff2e90bcf`
- `resnet18_search004_seed42`：`5e226722e0712824c78aa0976afa6fa5b8dc6100b147a7f523a09048171d8cf3`
- `mobilenet_v3_large_search006_seed42`：`9ee60abb78007773cc625af80c313049c1970f63c1f041bed9f5b2539a384828`

参照文件 SHA256：

- `/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/ml/outputs/runs/p4a_20261021/parity_MN-STABLE.json`：`bcecf7d0afcafa48213c0a4f9b85eb6f56ea05e5f463e24881cdf914888af0f8`
- `/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/ml/outputs/runs/p4a_20261021/parity_RN-HPO42.json`：`3885dbf8b87120382f0663f1aaad84d715f2c59cbb49f63006740e002c8c8cf9`
- `/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/ml/outputs/runs/p4a_20261021/parity_MN-HPO42.json`：`a8544656b264a5e0698418999c05bf2fe8e869af1b03e24041d2bbf6548fd73b`
- RN `validation/stable200_saved_predictions.csv`：`c7d233c813a01d54ff286a836e5c6cab069558b52a9ee547953052fc92a0787d`。
- MN候选同名 CSV：`47fd6f678247c81f6b0384a6453c7467c5b3dd39208647a9847f33807dba74b6`。
- 两包各自 `validation/p4a100_parity.json` 与相应根目录 `parity_*-HPO42.json` 字节 hash 一致，可在复制后使用，但须记录实际路径/hash。

## 3. 比较量与建议容差

对每个参照集合**分别**报告：

- `max_abs_prob_delta = max_{sample,c0..c9} abs(p_provider - p_reference)`，单位为0–1概率；不能用平均值代替最大值。
- `argmax_agreement = 一致的样本数 / 该参照集合样本数`，比较provider与相同模型参照的argmax；这不是对真实标签的accuracy。
- 缓存logits先做一次数值稳定softmax；CSV已是概率，直接读取，不二次softmax。provider遵循当前float32 logits→softmax一次的真实路径；差值计算可转float64。
- 按source_id配对，断言10类有限、[0,1]、概率和合理、c0..c9索引一致；UI `safe_driving`对应c0，不能误按概率排名配列。
- 单样本并列argmax沿用最低索引的一致规则并记录margin；不得用近似相同或“差不多”豁免argmax分歧。

**FUD-01 / FOR_USER_DECISION**：建议三个模型、各自所有有参照的集合均采用 **`max_abs_prob_delta <= 1e-4` 且 `argmax_agreement == 1.0`**。两个条件同时满足才通过数值检查；容差仅在用户批准后生效。runner docstring和输出须记录批准版本、值及依据。不要把历史P4A的logit `atol + rtol*abs(expected)` 误当成本方案概率绝对容差。

| 模型 | 历史P4A最大logit绝对误差 | 历史P4A最大概率绝对误差 | 历史argmax | 1e-4 / 历史概率最大误差（约） |
|---|---:|---:|---|---:|
| MN-STABLE | 5.340576171875e-5 | 4.846009571957133e-6 | 211位置全部一致 | 20.6 |
| RN-HPO42 | 1.9073486328125e-5 | 2.302238954254854e-6 | 211位置全部一致 | 43.4 |
| MN-HPO42 | 4.100799560546875e-5 | 6.364584130613693e-6 | 211位置全部一致 | 15.7 |

理由：1e-4高于三个已测同张量PyTorch CPU–ORT概率误差，统一标准避免只为稳定模型施加较窄1e-5标准。它为float32运算次序、softmax精度、CSV文本舍入，以及CPU/ORT与历史PyTorch MPS batch64差异留出工程余量。**这些倍率是依据已存误差计算的，不是provider/JPEG路径的实测上界或模型敏感度证明。** P4A没有测过P3 MPS/batch64→当前provider这整个差异链，因此不能保证1e-4一定覆盖它。

## 4. provider preprocess 与 ML 验证变换

已读 Live `/Users/liu/Desktop/FYP2-Live-System/backend/app/providers/trained.py:94-114`；源码SHA `a240d77aaa2bfff1bf726dd4ae814e4c1078e2ab60023124214736877a136e2f`。

| 步骤 | provider | ML 验证/P4A | 判断 |
|---|---|---|---|
| 图像解码 | base64严格解码原字节→Pillow `Image.open(BytesIO)`→RGB | P3 `Image.open(path).convert('RGB')`；P4A同Pillow RGB | 相同JPEG字节经base64不会有损；文件/BytesIO入口本身不应改变像素。不能说provider必然使用不同JPEG解码器 |
| 缩放 | Pillow直接 `resize((224,224), BILINEAR)` | P3在PIL图像上 `transforms.Resize((224,224))`，默认bilinear；P4A直接Pillow bilinear | 都是强制224×224、无crop，不是短边256/CenterCrop；没有发现实质resize策略冲突 |
| 归一化 | HWC float32 /255→ImageNet mean/std→transpose NCHW | P3 ToTensor→CHW /255→Normalize；P4A先transpose再/255与同mean/std | 数学等价；布局、NumPy/PyTorch实现和浮点运算次序可有末位差异 |
| 增强 | 无 | validation=False，无RandomRotation/ColorJitter；只有training=True启用这些增强 | 验证时不能启用训练增强 |
| dtype/device | contiguous float32 NCHW，ORT CPU，真实softmax为float32 | P3验证PyTorch MPS/batch64；P4A CPU同张量，参照概率用float64 softmax | P3→provider包含额外backend/batch差异，P4A未给它数值上界 |
| 输入约束 | ≤2MB；PNG/JPEG；边长16..4096 | 离线loader没有相同API限制 | 可能产生输入拒绝而非小数值偏差；runner需如实记录，不能跳样本 |

今日Live环境的Pillow12.2.0、NumPy2.4.6、torch2.12.0、torchvision0.27.0、ORT1.26.0与P4A历史environment_snapshot对应包版本相同（只核对版本；不构成整套二进制相等证明）。

**可能带来大差异的偏离**：浏览器canvas再编码JPEG、质量/色彩管理变化、先镜像/旋转、EXIF自动转置、RGB/BGR颠倒、使用tensor插值而非PIL插值、改用等比缩放+裁剪、先ToTensor再resize、错误mean/std或类别顺序。这些都不是本次允许的验证输入路径，不能用1e-4“覆盖”。后续runner必须base64原始JPEG字节，禁止重编码；若未来要测browser路径，须单独批准，不可把这份容差直接套上去。

所以本容差覆盖的是**同原图、同语义预处理下预计的小数值差异，并有大于已测同张量误差的余量**；并无证据证明它覆盖任意JPEG/缩放变化。任一模型超限或argmax不一致时，输出 `pass:false`、最差样本source_id/各列差值、top1-top2 margin、图像hash及环境；追查输入/变换/设备差异，保留原阈值，不跑新benchmark、不重训、不重导出、不悄悄放宽。

## 5. 三模型共同评估 manifest 的类别规则

在stable200 fresh provider结果上，对每个真实类c_i的20张图统计10类argmax次数，取所有并列众数集合 `winners`；仅 `winners == [i]` 为该类通过，10类全部通过才为 `all_unique_modes_equal_label=true`。并列众数也失败，不能偷偷改成“正确类在众数里即可”。

这项检查独立于数值一致性；数值一致不自动等于类别规则通过。即使稳定模型规则失败也照实记录。候选包当前历史 `SAVED_VALIDATION_PREDICTION_DIAGNOSTIC` 均报告10类唯一众数符合标签，**不是本次provider结果**。

未来输出应分开保存：`stable200_behavior`（200）；`parity100_reference_comparison`（100）；仅候选另有 `stable200_pytorch_comparison`（200）。三个模型都要保存执行命令、exit code、model/hash、preprocess标识、reference/hash、批准后的容差、source_id/hash、概率、argmax和类别计数。缺任一必需参照/图像时写 `BLOCKED` 及精确路径。

本次：`provider_load_forward=NOT_RUN`，`official_stable200_behavior=NOT_RUN`，没有填入任何新数值比较结果。

## 6. 待用户决定

- **FUD-01 — FOR_USER_DECISION**：批准或调整三模型统一1e-4/1.0的阈值与失败处理；批准前不运行任何比较。
- FUD-02–FUD-05在Stage-2协议草案中逐项列明；Stage-1审计和Stage-5选择仍各自有用户关卡。
- **FUD-06 — FOR_USER_DECISION**：确认分析U-2对Stage-3规格的perf01/perf02更正。本次不修改规格原件。

事实来源的当日命令、exit code与关键输出见同目录 `preflight_report.md` 的附录；P4A数值全为历史证据，未重跑。
