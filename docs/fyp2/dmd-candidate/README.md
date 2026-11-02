# DMD 候选模型在役资格证据：协议

本目录只回答一个问题：**`dmd_adapted_mobilenet_v3_20261029` 是否具备作为系统在役视觉模型的证据基础**。
本协议、脚本和证据都**不切换在役模型**；最终由用户决定。

- 机器可读的事先声明：[protocol.json](protocol.json)
- 声明日期：2026-11-02。`protocol.json` 必须先单独提交，提交时间早于任何结果。
- 决策规则：`DESCRIPTIVE_ONLY`。不预设“胜者”，不在测试集上挑阈值或融合权重。

## 比较对象

| | stable | DMD 候选 |
|---|---|---|
| model id | `stable_mobilenet_v3_large` | `dmd_adapted_mobilenet_v3_20261029` |
| ONNX | `ml/outputs/vision/mobilenetv3_large_vision.onnx` | `ml/outputs/candidates/dmd_adapted_mobilenet_v3_20261029/model.onnx` |
| sha256 | `b3a42e8d…` | `01f1d6a3…` |
| 选择方式 | 不设 `DRA_ACTIVE_VISION` | `DRA_ACTIVE_VISION=dmd_adapted_mobilenet_v3_20261029` |

同一数据集内，两个模型读**同一批原始图片**、走**同一段推理代码**、用**同一套指标代码**。
State Farm 用后端 provider 路径；DMD 测试集用 `scripts/dmd_infer_test.py`。

## A. 源域与适配域评估

- **State Farm 冻结测试集**：3657 帧、4 名测试司机（`p012/p026/p035/p050`）。
  输入清单直接读 p4b 运行保存的
  `/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/ml/outputs/runs/p4b_20261022/shared_inputs/vision_sources.json`
  （sha256 `098001f1…`），不重新划分。
  指标：accuracy、macro-F1、10 类逐类 P/R/F1、log loss、混淆矩阵；二分类诊断（safe c0 对其余九类，
  阈值 0.5）的 `c0_false_positive_proxy`、`distraction_recall`、二分类准确率。
  稳定模型的重算结果与 p4b 存档做交叉核对。
- **DMD body 测试集**：`sampling_manifest.csv` 中 `split == test` 的 1354 帧、两名留出受试者
  （`gC_13` / `gE_29`）。两个模型都从 ONNX logits 做一次 softmax。
  指标：上述多分类指标 + 二分类指标（0.5 与历史 0.7038 两列）。
  重算结果分别与 2026-10-29 的 `zero_shot_unexposed.json` / `comparison_test.json` 交叉核对。

## B. 运行时兼容性

1. `scripts/validate_runtime_manifest.py` 校验候选包的 `runtime_manifest.json`（含模型文件 sha256）。
2. 用 `DRA_ACTIVE_VISION=dmd_adapted_mobilenet_v3_20261029` 经后端 `TrainedProvider` 加载，记录
   provider 报告的 model id、sha256、类别名。
3. Provider 一致性：State Farm 冻结测试清单中每类按文件名排序取前 20 张（共 200 张）。
   同一个 provider 预处理张量分别送入 provider 的 ONNX session 和另一个独立加载的 ONNX session，
   概率差 `<= 1e-4` 且 argmax 一致率 `== 1.0` 才通过（沿用
   `docs/fyp2/task10a/tolerance_predeclaration.md` 的 FUD-01，已批准）。结果出来后不放宽容差。

候选包里的 `evaluation_metrics.json` 目前是 `{}`，**不原地修改**；需要补充的内容只写进证据目录并说明原因。

## C. 阈值语义（必须一并写明）

系统融合直接使用 `P_distraction = 1 − P(safe_driving)`，不使用任何视觉阈值。2026-10-29 在验证受试者
`gB_10` 上选出的 `0.7037721940337633` **不在运行时路径上**。因此：

- 运行时等价的二分类诊断是 **0.5 那一列**；DMD 候选在 DMD 测试集上 FPR = **0.2074**；
- 0.7038 那一列（FPR = **0.0891**）只是历史描述，不能当作部署误报率。

## D. 性能

`scripts/perf01.py`，stable 与 DMD 候选各 3 轮，交替进行；每轮 600 个测量窗口（预热 20 个）。
报告 capture→render 的 p50/p95、Server-Timing total 与 vision 的 p50/p95。每轮保留
`perf01.json` + `perf01_timings.json`，原始计时按 2026-10-30 stage3-raw 的方式校验和复算。
范围：一台开发机（Apple M2）、Chromium 假摄像头、冻结模型；不是目标硬件或真实摄像头。

## E. 系统级对比（可选）

A–D 完成后才考虑。若要做，必须**另写并先提交**一份新协议（不能改已提交的
`docs/fyp2/e2e5/protocol.json`），并给 `scripts/fusion_eval.py` 增加“由协议指定视觉模型”的入口与测试。
2026-11-02 的 stable E2/E5 证据保留原样，不重跑覆盖。

## F. 实时摄像头检查（用户本人操作）

只准备脚本与清单，执行者不代跑。用户按清单分别启动 stable / DMD 后端，完成
正常坐姿 60 秒、拿手机 60 秒、喝水 60 秒；脚本保存原始逐帧结果并计算：

- 正常坐姿：`safe_driving` 为 top-1 的比例；
- 拿手机 / 喝水：top-1 类别分布、`P_distraction` 均值/中位数、`P_distraction >= 0.5` 的比例。

操作见 `docs/fyp2/dmd-candidate/camera_check_checklist.md`，脚本为 `scripts/camera_ab_check.py`。

## 禁止与措辞

- 不修改 `DRA_ACTIVE_VISION` 默认值、`release_decision.md`、报告 docx。
- 不把权重、DMD 帧、State Farm 图片或 constructed scenario bundle 提交进 git。
- 不 push、不合并到其他分支、不占用 8000 端口、不写 `backend/driver_risk.db*`。
- 结论只用“描述性 / 本数据集上 / 构造场景”这类措辞；不声称真实世界准确率或安全收益。

## 产物

所有证据在 `docs/evidence/2026-11-02/dmd-candidate/`；事实汇总在
`docs/fyp2/dmd-candidate/decision_facts.md`（只列事实和数字，不做选择）。
