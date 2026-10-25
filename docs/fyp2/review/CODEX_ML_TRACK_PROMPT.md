# Codex 任务：FYP2 ML 训练轨道

你负责 ML 训练轨道。系统开发轨道由 Claude 在另一个文件夹里并行进行，两条轨道必须互不干扰。
用中文写报告；代码标识符、路径、指标名保持原文。

## 0. 你在哪里

- 项目文件夹：`/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1`
- 分支：**`fyp2/ml-training`**，2026-10-13 从 `dev_cc` @ `efb3ea6` 新建，目前没有任何额外 commit。

**开工前先确认，任何一条不满足就停下来报告，不要自行修复：**

```bash
git branch --show-current     # 期望 fyp2/ml-training
git log --oneline -1          # 期望 efb3ea6 chore: remove AGENTS.md（或你自己之后的 commit）
git status --short            # 期望为空
```

如果 `git status --short` 不为空，说明有别处的未提交改动被切分支带了过来。**不要提交它们，也不要丢弃它们**，停下来报告。

另一个文件夹 `/Users/liu/Desktop/FYP2-Live-System` 是 Claude 的系统开发工作区。**不要进入、不要读写它。**

## 1. 硬性约束 —— 违反任何一条都会直接破坏另一条轨道

### 1.1 三个线上模型文件：只读

你工作区里 `ml/outputs/` 下的这三个文件是**线上原件**。Claude 的开发文件夹通过**符号链接**实时使用它们。你改了它们，正在开发的系统就会在中途被换掉模型：

| 文件 | SHA256 |
|---|---|
| `ml/outputs/vision/mobilenetv3_large_vision.onnx` | `b3a42e8dd4553355b1fd7d9e7fe3d28e318decb894e76eb029489b7ff2e90bcf` |
| `ml/outputs/vision/mobilenetv3_large_vision.pt` | `196ca7b151d84e0c4a8eac87128da9dd8f22c894984a991ef611536bb523e7c7` |
| `ml/outputs/telemetry/xgb_telemetry.json` | `9802cb06ca98f0c1befaf851fa7668cfec70e005cf8bb3884e49d7d45d7aec07` |

- 可以**读**它们，作为对比基线。
- **绝不能写、覆盖、移动、重新导出它们。**
- 开工前和每次交付前各算一次上表哈希，确认没变。

**特别警告 —— 现有的训练代码默认就会覆盖它们：**

- `ml/telemetry/train_telemetry.ipynb:466`：`clf.get_booster().save_model(str(TEL_OUT / "xgb_telemetry.json"))`
- `ml/vision/train_vision.ipynb:827`（`torch.save`）与 `:850`（`torch.onnx.export`）：写 `ml/outputs/vision/` 下的 `.pt` 与 `.onnx`

**原样重跑这些 notebook 就会直接覆盖线上原件。** 任何训练之前，必须先把输出目录改成 `ml/outputs/runs/<run_id>/`；或者另写新脚本，不要复用这些默认路径。

### 1.2 Python 环境

用工作区里的 `./.venv/bin/python`。2026-10-13 核实，已安装：torch 2.12.0、torchvision 0.27.0、scikit-learn 1.9.0、xgboost 3.2.0、onnxruntime 1.26.0。MPS（Apple GPU）可用。

- **绝不能用 `pip install` 往 `./.venv` 里安装或升级任何包。** 系统轨道共用这个环境，升级一个依赖就可能让对方的测试变红。
- 确实需要新包时，另建 `python -m venv .venv-ml`，只装进那里，并把 `.venv-ml` 加进 `.gitignore`。

### 1.3 数据

```bash
export FYP_DATA_ROOT=/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment-
```

划分好的数据在 `$FYP_DATA_ROOT/eda_outputs/processed/{vision,telemetry}/` 下。2026-10-13 核实，哈希与审计记录一致：

- `vision/vision_metadata_with_split.csv`：`b4f8e90dec769bb419eaa490aea869668bed6484089cebe4d545c7667baa8ea4`
- `telemetry/telemetry_test.csv`：`3bc3d47680a87359e1470fd8ffaf5ff330dc4419b37cc645e5736d51a91c96de`

开工前再核一次；不一致就停下报告。**不得修改数据。** 缓存、特征文件等中间产物写在 `ml/outputs/runs/` 下。

### 1.4 文件范围

- 只改 `ml/` 和 `docs/fyp2/ml/`。
- **不得触碰** `backend/`、`ai/src/`、`ai/reference/`、`frontend/`。这些归系统轨道。两条分支修改的文件互不重叠，将来才能各自干净地合并。

### 1.5 Git

- **第一个 commit 必须先修 `ml/.gitignore`。** 现在它只忽略 `*.pt`、`*.onnx` 和 `outputs/telemetry/xgb_telemetry.json` 这一个具体文件。你新训练出来的 XGBoost `.json`、Random Forest / Logistic Regression 的 `.joblib` / `.pkl` 都**不会**被忽略，会被误提交进仓库。请忽略 `ml/outputs/runs/` 下的模型二进制，同时保留指标、配置、报告这类小文件可以提交。
- 只在 `fyp2/ml-training` 上提交。**未经用户明确授权不得 push 或 merge。**
- 工作结束时把工作区切回 `dev_cc`：`git switch dev_cc`。

## 2. 范围

依据 `docs/fyp2/04_ML_COMPARISON_AND_TUNING_AUDIT.md` 与 `docs/fyp2/03_EVALUATION_COVERAGE_MATRIX.md`：

1. 补齐三个缺失的对照模型：**ResNet18**（vision）、**Random Forest** 和 **Logistic Regression**（telemetry）。现有的图像 linear probe **不能**替代 telemetry LR。
2. 对五个模型做**有界超参搜索**。预算按审计 04 的「Bounded HPO proposal」表执行，不得静默扩大。到达预算或时间上限时，记录未完成的 trial，不要悄悄加量。
3. **用 validation macro-F1 选型**。held-out test 只在选型冻结之后跑一次。
4. E1–E5 评估实验，按审计 03 的设计执行。

每次运行必须产出：

- `run_id/config.json`
- split 与模型的哈希、seed、commit 与 dirty 状态
- `trials.csv`、validation 指标与 class report、选型记录
- 选中的 checkpoint
- 带样本 ID 的 test 预测
- 计时原始样本，区分 warmup 和正式测量

## 3. 模型替换不在本轨道

即使新模型更好，也**不要**替换线上模型。替换是之后单独的集成步骤，由系统轨道执行。

你只需要交付：模型卡、哈希，以及它是否满足现有 provider 契约（见 `backend/app/providers/trained.py`）：

- **vision**：10 类，顺序 c0–c9，c0 = `safe_driving`；ONNX 输入为 float32 NCHW `[N,3,224,224]`，ImageNet 归一化
- **telemetry**：3 类 `Safe / Aggressive / Distracted`；8 个特征，固定顺序 `speed_kmph, accel_x, accel_y, brake_pressure, steering_angle, throttle, lane_deviation, headway_distance`

## 4. 报告

进度与结果写到 `docs/fyp2/ml/` 下。每个阶段结束时汇报：

- 做了什么
- 真实的指标数字
- 哪些是 smoke 运行，哪些是完整实验
- 哪些被阻塞，原因是什么

**不得编造结果。** 没跑完的就写没跑完。
