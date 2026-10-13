# Codex ML 轨道：补充说明 R4（2026-10-13，独立审阅之后）

本文件补充 `CODEX_ML_TRACK_PROMPT.md`。原提示词的硬性约束全部继续有效：三个线上模型文件只读；不往 `./.venv` 安装包；只改 `ml/` 与 `docs/fyp2/ml/`；只在 `fyp2/ml-training` 提交，不 push、不 merge；第一个 commit 先修 `ml/.gitignore`。
用中文写报告；代码标识符、路径、指标名保持原文。

## 1. 范围调整：E2–E5 不在 ML 轨道

原提示词第 2 节第 4 条「E1–E5 评估实验」**改为只做 E1**。

原因：`fyp2/ml-training` 停在 `efb3ea6`，上面的融合、EMA 与 Alert FSM 是 Tasks 1–6 **之前**的旧代码：没有 nullable 契约，没有 `ROUND_HALF_UP`，FSM 也不会在 unavailable 时挂起。在这个分支上跑 E2–E5，结果描述的是一个已经不存在的系统。E2–E5 由系统轨道基于最新代码完成。

**不要**在 `ml/` 下另写一份融合、EMA 或 FSM 的实现，也不要 import `backend/` 的融合代码来做评估。

## 2. 现在要做的事（按优先级）

依据：`docs/fyp2/09_INDEPENDENT_AUDIT_REVIEW.md`（你自己的独立审阅）第 4、6、7 节，以及审计 03、04。

1. **补齐三个指定对照模型**：ResNet18（vision），Random Forest 与 Logistic Regression（telemetry）。MobileNetV3-Small、EfficientNet、图像 linear probe 都**不能**替代它们（R24）。
2. **对五个模型做 bounded HPO**：只用 validation 选型；trial 预算按审计 04 执行，不得静默扩大；保留 selection log。最终 test **只在选型冻结后跑一次**。
3. **E1-V（vision 6×3）**：按审阅第 4 节的变换与强度执行，使用固定的 held-out ID manifest 和 seed 42，保存 kernel 方向、遮挡位置与裁切参数，两个模型的输入逐字节相同；遮挡或裁切可能移除动作判据，所以需要独立的可识别性 QC；统计推断按 driver / clip 做 cluster，4 名 test 司机不等于 3657 个独立样本。命名上，Gaussian 不能叫 motion，grayscale 不能叫 IR（R19）。
4. **E1-T（telemetry D0–D3）**：4500 条 source ID × (1 + 9) = 45k 行，三个模型共用同一份生成集与 mask。D0 标为 synthetic=true、perturbed=false。D2 称为 label-conditioned stress（R21）。
5. **R26 train-only 统计**：外部 EDA 脚本 `run_eda_data_cleaning.py` 在 split 之前对全量数据计算 median，与文档里写的 train-only 不一致。**不要修改数据文件夹**。在 `ml/` 自己的流水线里用只在 train 上 fit 的 imputer，并在报告中写明这个 provenance 差异。目前原始 8 个特征没有 NaN，所以**不得**声称现有的 .9993 被污染。
6. **R27 test 曝光披露**：报告中写明 test split 已被多次评估过，不再称其为「从未见过」；同时写明没有发现直接用 test 选参的代码。
7. **DMD**：没有明确的 access / license、动作区间、按人分组和类别映射之前，保持 blocked，不得用其他数据顶替（R29）。

## 3. 候选模型包要求（会进入系统轨道的 Task 10A 影子评估）

系统轨道已决定：视觉 provider 改为读取独立的 `runtime_manifest.json`，并对预处理、类别映射、输入/输出、路径、哈希做严格校验，**不符合的候选会被拒绝加载**。manifest 的最终 schema 由系统轨道在 Task 10A 开工时确定。你现在导出候选时，请确保以下几点成立，并把对应信息写进模型包：

| 项 | 要求 | 原因 |
|---|---|---|
| 预处理 | 与运行时**完全相同**：RGB → 直接缩放到 224×224（PIL bilinear，**不裁剪**）→ `/255` → ImageNet mean `[0.485,0.456,0.406]`、std `[0.229,0.224,0.225]` → NCHW float32。即现有 notebook 的 `eval_tf = Resize((224,224)) + ToTensor + Normalize` | 运行时只实现这一套（`backend/app/providers/trained.py:87-92`）。ResNet18 常见的 `Resize(256)` + `CenterCrop(224)` 会被拒绝加载 |
| 输出 | ONNX 输出必须是**原始 logits**，不得在模型内做 softmax | 运行时自己做 softmax；如果输出已经是概率，形状检查拦不住，结果会被二次 softmax 压平 |
| 类别 | 10 类，索引顺序 c0…c9，c0 = `safe_driving`；把训练时真实使用的 `class_to_idx` 原样写进模型包 | `P_distraction = 1 − P(c0)`。只核对元数据无法发现索引错位，系统轨道会用带标注的冒烟样本做行为检查 |
| 输入 | 输入名 `input`、输出名 `logits`，float32 `[N,3,224,224]`，batch 维动态 | 与现有导出一致 |
| 两份文件分开 | `runtime_manifest.json` 只写加载所需的内容（文件名、SHA-256、输入、预处理、输出语义、`class_to_idx`、标签名、架构、来源 run_id 与 commit）；`evaluation_metrics.json` 单独存放指标 | 用户裁定：评估指标不是加载的前提条件 |
| 位置 | `ml/outputs/runs/<run_id>/` 下自成一个目录；目录内**不得有符号链接**，不得引用目录外的文件 | 路径越界会被拒绝 |
| 证据 | 带样本 ID 的 test 预测（logits 或概率需注明）、validation 指标、selection log | 系统轨道做「稳定 vs 候选」的成对比较需要它们 |
| 安全 | 读取 `.pt` 一律 `torch.load(..., weights_only=True)`；RF / LR 的 `.joblib` / `.pkl` 只用于 benchmark，不进入任何候选包 | pickle 会执行代码；RF / LR 不会被部署 |

**不要**替换线上模型，也不要给候选模型起会覆盖 `ml/outputs/vision/` 或 `ml/outputs/telemetry/` 下现有文件的名字。

## 4. 你的审阅报告

`docs/fyp2/09_INDEPENDENT_AUDIT_REVIEW.md` 目前是主仓库里一个未跟踪的文件。系统轨道已经在 `fyp2/live-system` 上保存了一份逐字副本：`docs/fyp2/review/CODEX_INDEPENDENT_AUDIT_REVIEW_2026-10-13.md`。**请不要在 `fyp2/ml-training` 上提交它**，否则合并时同一份内容会出现在两个位置。

## 5. 汇报

每完成一项，在 `docs/fyp2/ml/` 下写明：做了什么、真实指标、哪些是 smoke 运行、哪些是完整实验、哪些被阻塞及原因。没跑完就写没跑完，不得编造结果。
