# Task 10A 交接：候选视觉模型包的 runtime manifest（给 ML 轨道）

- **交接时间**：W5（冲刺计划 v3：W5 周一把 Task 10A 的 manifest schema 交给 Track B）。
- **依据**：主计划 `docs/plans/2026-10-12-fyp2-live-system-completion.md` 中 Task 10A「已拍板的决定」。
- **状态**：这一步**只交 schema**。provider 改造与离线评估器属于 W6 的拓展项，要等 G-W5 通过后才开始。

## 你要交付什么

每个候选模型放在一个**自成一体的包目录**里：`ml/outputs/runs/<run_id>/`。目录内容：

| 文件 | 说明 |
|---|---|
| `runtime_manifest.json` | **加载契约**。格式见下文，用 `scripts/validate_runtime_manifest.py` 校验 |
| `<model>.onnx` | 模型文件，路径写在 manifest 的 `model.path` 里，相对包目录 |
| `evaluation_metrics.json` | **评估证据**，如 macro-F1、每类召回、ECE、Brier，以及带样本 ID 的 test 预测。和 manifest 分开存放：加载器**不读**它，manifest 里**不得**出现任何指标 |

校验命令：

```bash
python3 scripts/validate_runtime_manifest.py ml/outputs/runs/<run_id>/runtime_manifest.json --package-dir ml/outputs/runs/<run_id>
```

输出 `valid` 并以 0 退出，才算交付合格。

## manifest 字段

结构由 `backend/app/runtime_manifest.schema.json`（JSON Schema 2020-12）规定，跨字段的规则由 `backend/app/runtime_manifest.py` 检查。完整示例见 `docs/fyp2/handoff/examples/stable-mobilenetv3.runtime_manifest.json`，它描述的就是当前冻结的稳定模型。

| 字段 | 要求 | 为什么 |
|---|---|---|
| `manifest_version` | `1` | — |
| `kind` | `"vision_classifier"` | 只有视觉模型是替换候选。遥测固定用 XGBoost，RF 和 LR 只做 benchmark |
| `run_id` | 与包目录名一致，只能含 `[A-Za-z0-9_.-]` | — |
| `architecture` | 例如 `mobilenet_v3_large`、`resnet18` | 只用于记录。加载器不再写死架构名 |
| `model.path` | 相对包目录的路径，不能含 `..`，不能是绝对路径。解析符号链接之后，也必须仍在包目录内 | 候选包不能逃出自己的目录 |
| `model.format` | `"onnx"` | 运行时只用 ONNX Runtime |
| `model.sha256` | 64 位小写十六进制，必须与文件逐字节相符 | 能发现文件被意外损坏。要发现文件被替换，还需与经批准的发布清单比对，那是 10A 后续的工作 |
| `input` | `shape [1,3,224,224]`、`float32`、`NCHW`、`RGB` | 运行时只支持这一种输入 |
| `preprocess` | **只接受** `"rgb_resize_224_bilinear_no_crop_div255_imagenet"` | 运行时只实现了这一套预处理：RGB → 直接缩放到 224×224（PIL 双线性，**不裁剪**）→ 除以 255 → ImageNet 均值方差。ResNet 常见的 `Resize(256)` 加 `CenterCrop(224)` 是**另一种**预处理，会被拒绝。想让候选进入影子评估，验证变换必须与运行时一致 |
| `output` | `kind` 必须是 `"logits"`，`shape` 为 `[1, 类别数]` | 运行时会对输出做 softmax。如果导出的是概率，会被 softmax 两次，概率被压平，而形状检查发现不了 |
| `classes` | 按**模型输出的下标顺序**排列的类别码，例如 `c0…c9`，不能重复 | — |
| `class_to_idx` | 必须恰好等于每个类别在 `classes` 里的下标 | 训练时的类别顺序一旦不同，加载照样成功，`P_distraction = 1 − P(c0)` 却会悄悄算错。这是最危险的一类错误 |
| `safe_class` | 必须是 `classes` 中的一个（State Farm 是 `c0`） | 用来算 `P_distraction = 1 − P(safe)` |
| `contract_smoke_set` | 用于行为检查的冒烟集，见下一节 | 元数据校验不等于行为校验 |
| `provenance` | 可选，自由填写，例如来源 checkpoint、训练提交号 | — |

除上表以外的顶层键一律拒绝，尤其是任何评估指标。

## 契约冒烟集（`contract_smoke_set`）

- `split` 只能是 `train` 或 `val`，**绝不能是 `test`**，因为 test set 不得用于选型或调试。
- `selection`：用一句话写清楚样本怎么选，例如「每类按文件名排序取前 20 张」。
- `n`：样本数。
- `sample_ids_sha256`：把样本文件名排序后用 `\n` 连接，再取 sha256。数据本身不进仓库，只记录这个哈希。
- `rule`：固定为 `"per_class_mode_equals_label"`，即每个类别预测结果的众数必须等于该类别。这条检查在 10A 的离线评估器里执行，不在本次 schema 交接的范围内。

稳定模型示例里的冒烟集是：val split，每类按文件名排序取前 20 张，共 200 张，`sample_ids_sha256 = 601dc3ed…73be9`。候选模型应当用**同一份**冒烟集，这样稳定模型和候选模型在同一组输入上比较。

## 已知的待决事项（10A 开工时决定，现在不决定）

1. **稳定模型的符号链接与「不能逃出包目录」规则的冲突**：本工作树里三个稳定模型文件都是指向主仓库的符号链接，用 `--package-dir ml/outputs/vision` 校验会被判为「outside the package」。这是规则**正确地**生效了。指向真实目录时校验通过，哈希也相符。10A 开工时要定下用哪种方式：
   - 稳定模型改为真实文件的包目录；
   - 或者为经批准的发布清单设一个允许的根目录。
2. runtime manifest 最终放在哪里（`ml/` 归 ML 轨道，`backend/` 归系统轨道）、遥测是否也改走 manifest，见主计划 Task 10A「开工时须确定」。
