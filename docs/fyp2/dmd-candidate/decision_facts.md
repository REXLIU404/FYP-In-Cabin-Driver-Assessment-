# DMD 候选是否可作为在役模型：事实汇总

日期：2026-11-02。**本文件只列事实和数字，不做选择。** 在役模型仍为 stable MobileNetV3-Large
（`docs/fyp2/task10a/release_decision.md`，用户签字 2026-10-30）。是否切换由用户决定。

- 协议（先于任何结果提交）：`docs/fyp2/dmd-candidate/protocol.json`（commit `a198a15`）
- 阈值语义：`docs/fyp2/dmd-candidate/threshold_note.md`
- 证据根目录：`docs/evidence/2026-11-02/dmd-candidate/`

## 1. 模型身份

| | stable | DMD 候选 |
|---|---|---|
| model id | `stable_mobilenet_v3_large` | `dmd_adapted_mobilenet_v3_20261029` |
| ONNX sha256 | `b3a42e8d…` | `01f1d6a3…` |
| 加载方式 | 不设 `DRA_ACTIVE_VISION` | `DRA_ACTIVE_VISION=dmd_adapted_mobilenet_v3_20261029` |
| manifest 校验 | 无候选式 manifest（stable 路径） | `valid`（`b-runtime-compat/manifest_validation.json`） |
| provider 一致性 | 历史 stable200/parity100 证据 | 200 张：max Δp **1.192e-06**，argmax **1.0**，PASS |

## 2. State Farm 冻结测试集（3657 帧，4 名测试司机）

来源：`a-source-domain/results.json`、`summary.csv`、`state_farm/per_class.csv`。
输入清单直接取 p4b 运行保存的 `vision_sources.json`（sha256 `098001f1…`），未重新划分。

| 指标 | stable | DMD 候选 | 差异（DMD − stable） |
|---|---|---|---|
| accuracy | 0.8988 | 0.8091 | −0.0897 |
| macro-F1 | 0.8746 | 0.7266 | −0.1480 |
| log loss | 0.5745 | 0.8030 | +0.2285 |
| c0 被误判为分心（P_distraction ≥ 0.5） | 0.0905（39/431） | 0.0487（21/431） | −0.0418 |
| 分心帧召回（≥ 0.5） | 0.9721 | 0.9510 | −0.0211 |
| 二分类准确率（0.5） | 0.9647 | 0.9511 | −0.0136 |
| c8 `hair_makeup` 召回 | 0.8321 | 0.0679 | −0.7642 |
| c9 `talking_to_passenger` 召回 | 0.2733 | 0.0643 | −0.2090 |

- stable 重算与 p4b `MN-STABLE.clean`：accuracy、macro-F1、混淆矩阵一致；log loss 差 **5.815e-9**
  （0.574453149292 vs 0.574453143476），超过协议写下的 1e-9，记为 `PASS_WITH_WARNINGS`，未隐藏。
- 在**这个数据集**上，DMD 候选的十分类整体指标低于 stable，c0 误报率也更低；c8/c9 召回大幅下降。
- 逐类退化不只在 c8/c9：**c1 召回 0.9000 → 0.6943**；**c0、c2、c6 的精确率**分别为
  0.8102 → 0.6779、0.9890 → 0.7780、0.9102 → 0.6205。完整 10 类数字见
  `a-source-domain/state_farm/per_class.csv`。

## 3. DMD body 测试集（1354 帧，2 名留出受试者 gC_13 / gE_29）

来源：`a-source-domain/results.json`、`dmd_test/per_class.csv`、`binary_diagnostics.csv`。
两个模型都从 ONNX logits 做一次 softmax；与 2026-10-29 存档交叉核对通过
（stable 零样本概率最大差 0.0；候选与 `comparison_test.json` 在存档舍入范围内一致）。

| 指标 | stable（零样本） | DMD 候选 |
|---|---|---|
| accuracy | 0.2777 | 0.7171 |
| macro-F1 | 0.3105 | 0.5065 |
| log loss | 3.4896 | 0.9586 |
| c0 召回 | 0.1951 | 0.8863 |
| rocAUC | 0.7390 | 0.8570 |
| c8 召回 | 0.8154 | 0.0154 |
| c9 召回 | 0.5167 | 0.0000 |

二分类诊断（DMD 测试集）：

| | 阈值 | recall | FPR | precision |
|---|---|---|---|---|
| stable @0.5 | 0.5 | 0.9531 | 0.8157 | 0.5579 |
| DMD 候选 @0.5（**运行时等价列**） | 0.5 | 0.7881 | **0.2074** | 0.8041 |
| DMD 候选 @历史阈值（**运行时不用**） | 0.7037721940337633 | 0.6344 | 0.0891 | 0.8849 |

- c8/c9 在 DMD 测试集上同样退化：c8 0.8154 → 0.0154，c9 0.5167 → 0.0000。
- macro-F1 的提升（0.3105 → 0.5065）不能覆盖这两类的退化。
- **不能**把 0.0891 描述为部署误报率；运行时直接使用连续 `P_distraction = 1 − P(safe_driving)`，
  没有 0.7038 阈值。运行时等价的是 0.5 列（FPR 0.2074）。

## 4. 性能（perf01，stable 与 DMD 各 3 轮）

来源：`d-perf/`、`d-perf/recompute.json`。每轮 600 个窗口（预热 20 个），stable/DMD 交替。
范围：一台开发机（Apple M2）、Chromium 假摄像头、冻结模型；不是目标硬件或真实摄像头。

| 轮次 | 模型 | capture→render p50 / p95 / max (ms) | Server total p50 / p95 (ms) | Server vision p50 / p95 (ms) | 速率 |
|---|---|---|---|---|---|
| 1 | stable | 27 / 45 / 127 | 16.42 / 23.53 | 8.645 / 12.56 | 9.84 Hz |
| 1 | DMD | 27 / 30 / 186 | 17.26 / 18.84 | 9.23 / 9.99 | 9.83 Hz |
| 2 | stable | 27 / 36 / 136 | 16.57 / 20.37 | 8.88 / 10.87 | 9.82 Hz |
| 2 | DMD | 28 / 36 / 104 | 17.44 / 20.42 | 9.345 / 10.83 | 9.83 Hz |
| 3 | stable | 28 / 35 / 149 | 17.62 / 20.10 | 9.41 / 11.00 | 9.83 Hz |
| 3 | DMD | 28 / 39 / 124 | 17.23 / 21.60 | 9.095 / 11.85 | 9.83 Hz |

- 六轮全部 `short_run = false`、0 console errors、`attempts_other_than_1 = 0`，
  `target_1s`（capture→render p95 ≤ 1000 ms）全部 met。
- 六轮原始计时的 sha256 与复算 p50/p95 全部一致（`d-perf/recompute.log`，6/6）。
- 运行期间机器负载（load average）高于 2026-10-30 stage3 的 2.3–4.1；绝对毫秒数不应与 stage3 直接比较。
- 两模型的 p95 在 30–45 ms 之间交替，Server vision 中位数 stable 8.645–9.41 ms、DMD 9.095–9.345 ms，
  差异在轮间波动范围内；这是描述性结果，不是“哪个更快”的结论。

## 5. c8 / c9 退化（必须与整体指标一起报告）

| 数据集 | c8 stable → DMD | c9 stable → DMD |
|---|---|---|
| State Farm test（recall） | 0.8321 → 0.0679 | 0.2733 → 0.0643 |
| DMD test（recall） | 0.8154 → 0.0154 | 0.5167 → 0.0000 |

微调后模型几乎不再输出 c8/c9 的 top-1；在 State Farm 上 c8/c9 的精确率变为 1.0000 是因为它几乎
不再预测这两类。DMD **训练集**（2005 帧）中 c8+c9 合计 **137 帧（6.8%）**，c0 为 **945 帧（47.1%）**。
一种可能的解释是这两类训练样本少，但这是**推测**，没有做因果验证，不能写成已证实的退化原因。
逐类退化也不限于 c8/c9：State Farm 上 c1 召回 0.9000 → 0.6943，c0/c2/c6 精确率分别
0.8102 → 0.6779、0.9890 → 0.7780、0.9102 → 0.6205；完整表见
`a-source-domain/state_farm/per_class.csv`。

## 6. 系统级 E2 / E5（构造场景，描述性）

来源：`e-system-level/README.md`、`e2-dmd/results.json`、`e5-dmd/results.json`。
DMD 的 E2/E5 均 `PASS`；stable 的 2026-11-02 E2/E5 结果保留原样（未重跑、未覆盖）。

- **E2**（60 对构造输入 × 5 权重，种子与输入相同）：
  - 0.5/0.5 下与参考一致：stable 59/60，DMD 59/60；
  - RiskLevel 分布 L/M/H：stable 10/28/22，DMD 9/26/25；
  - 衰减例：stable 28，DMD 25；
  - 视觉分支与源标签不一致：stable 3 次、DMD 2 次（构造样本，不是准确率）；
  - telemetry 分支不一致两边都是 0；两边都通过全部 runner 检查。
- **E5**（`viva_compact`，FUSED 0.5/0.5）：
  - Baseline（纯 c0）：DMD 的 P_distraction mean 0.0641、RiskScore mean 3.228；
    stable 两项约为 0；
  - Telemetry-only：DMD 的 RiskScore max 60.9（2/40 窗口 High），stable 为 50.0（0/40 High）；
    参考允许 Medium/High，所以两边 `agrees` 都是 40/40；
  - Vision-only：DMD 一致 98/100、lag 200 ms；stable 96/100、lag 400 ms；
  - Both：DMD score mean 99.356、stable 93.076；两边 Alert max 都是 HIGH_ALERT；
  - 两边的场景、段顺序/时长、分支反事实完全相同；Alert max 在每段都没有变化。
- **不能证明**真实多模态风险准确率；E2 的 60 对与 E5 的构造场景都不是风险真值，
  也不能从这些段推断 DMD body 视角或正面摄像头的真实表现。

## 7. 运行时兼容性

- manifest：`valid`。
- `DRA_ACTIVE_VISION` 经真实 provider 加载成功：model id/sha256/classes 与协议一致，
  provider name `VisionCandidateONNX+XGBoost`，c0 别名为 `safe_driving`。
- 200 张 State Farm 原图：provider 路径 vs 独立 ONNX session，max Δp 1.192e-06（≤ 1e-4），
  argmax 一致率 1.0（= 1.0），PASS。独立预处理张量与 provider 预处理张量最大差 0.0。
- 不证明相机路径（浏览器重编码）或目标硬件性能。

## 8. 实时摄像头检查

**未运行**（需要用户本人操作）。材料：`docs/fyp2/dmd-candidate/camera_check_checklist.md`、
`scripts/camera_ab_check.py`、`f-camera-check/README.md`。用户运行后会得到
`stable.json` / `dmd.json` / `comparison.json`。

## 9. 如果切换在役模型，需要一起改的东西

以下只是清单，不代表建议切换。DMD 目前补齐的是候选加载、推断、源域/目标域对比和
perf01 延迟；Task 10A 的多项发布关卡没有在 DMD 上执行。

1. **新的用户决定记录**：`docs/fyp2/task10a/release_decision.md` 与用户签字需要改为
   `dmd_adapted_mobilenet_v3_20261029`，记录新的日期和签字；这不是代理可以代替的决定。
2. **Task 10A 未在 DMD 上执行的关卡**：
   - **Stage 2 系统对比**：2026-10-29 的 `comparison-official-bf76ddf` 是 stable/RN 的
     配对比较，不是 DMD；DMD 没有 stable200 式的 Stage 2 逐窗口系统对比。E2 的 60 对
     构造输入不能替代 Stage 2。
   - **Stage 3 的 perf02 和日志完整性**：DMD 只有 perf01 延迟；没有 perf02 的故障注入、
     后端重启、逐条日志完整性（stable 基线为 D1/D2 211/211）和长会话复测。
   - **Stage 5 回滚演练**：stable 已有 2026-10-30 的 rollback drill；DMD 没有
     “DMD 在役 → 切回 stable → hash 校验 → 正常 forward”的实测记录。
   - **stable200 式验证**：B 项的 200 张图只验证 provider 数值一致性，不等于 DMD 的
     `official_stable200_behavior` 或选型验证；DMD 没有产出这一项。
3. **Table 20 与 Table 23 中只在 stable 上测过的行**：
   - **Table 20**（纯模型推理，ORT CPU `session.run` p95）当前只含 stable/HPO MN/RN 的
     数字，没有 DMD；切换需要加入 DMD 的同口径测量，不能沿用现有 stable/HPO MN 的数字
     （其中 7.25 ms 是 HPO MobileNetV3 同架构参考）。
   - **Table 23** 的 **Fault-injection 211/211**、**Persisted outcomes（210 + 1）**、
     **Long session 8,867 windows** 都是 stable 的 10-22 结果；DMD 未复测。若切换，
     要么补做 DMD 的同口径运行，要么在表中明确标为 stable-only，不能把数字归到 DMD。
   - Table 23 的 capture→render 与 Server total 两行可以用 D 项的 2026-11-02 数字，
     但 Server total/vision 的 p50/p95 只有 `perf01.json` 汇总，没有逐窗口原始数据
     （见 §4 与 `d-perf/README.md`）。
4. **报告正文与模型描述**：第 2 章的模型选型理由、6.2.3 的英文决定段落、第 4 章架构与
   模型描述、第 7 章结论，以及任何引用 stable 延迟/模型大小/准确率的地方都需要改写。
   release decision 里的英文段落目前写的是“stable MobileNetV3-Large was kept...”，
   切换后必须替换，不能保留原句。Table 16/17 的上下文也要说明 DMD 在 State Farm 与
   DMD 上的新数字来自本证据目录；`ml/outputs/runs/p4b_20261022` 是 stable 的历史证据，
   不能改写成 DMD 的数字。
5. **报告里的 E2/E5 引用**：`docs/evidence/2026-11-02` 的 `e2-weight-sensitivity` 和
   `e5-light-counterfactual` 是 **stable** 跑的，保留不动；DMD 的两份已在
   `dmd-candidate/e-system-level/e2-dmd` 与 `e5-dmd`（新协议 `4b8506f` 已提前提交，
   `fusion_eval.py --protocol` 入口已实现）。若切换，报告应改为引用 DMD 这两份，
   并把 stable 版本标为历史对照；**不要**修改 `docs/fyp2/e2e5/protocol.json`，
   也不要覆盖 stable 的旧证据。
6. **让切换长期生效**：当前默认值在 `backend/app/config.py` 的 `active_vision = "stable"`。
   只在一个终端里设 `DRA_ACTIVE_VISION` 只管这一次启动；要长期生效，必须由用户决定并
   修改配置默认值，或在 `scripts/dev.sh` / `scripts/coldstart_check.sh`（及实际部署的
   启动入口）里显式设置环境变量。这个持久化改动需要新的用户决定，不能在候选评估中
   顺带完成。
7. **候选包元数据**：`ml/outputs/candidates/dmd_adapted_mobilenet_v3_20261029/evaluation_metrics.json`
   目前是 `{}`；若成为在役模型，需要一份正式指标文件（本次没有原地修改，指标在证据目录）。
8. **许可与发布**：DMD 数据是 CC BY-NC-ND 4.0；模型权重不得发布到公开仓库。报告与演示中
   需要保留这一限制。

## 10. 仍然未知 / 不能声称

- 正面摄像头、真实车内光照/遮挡/运动下的准确率；DMD 是 body 视角，State Farm 是侧视。
- 风险分数或安全收益：没有同步的多模态风险真值。
- 总体性能与置信区间：DMD test 只有 2 名受试者、1354 帧；单次运行，无 k-fold/多种子。
- 训练与选型的代表性：DMD 只用 **gA_1、gA_5、gB_6** 三名受试者、共 **2005 帧**训练；
  checkpoint 按**单个验证者 gB_10** 的 macro-F1 选出，是 **9 轮中的第 1 轮**，
  `training_history.json` 记录 `converged = false`（没有收敛）。只训练了一次（seed 42），
  没有多个随机种子，也没有 k-fold，因此不能声称训练充分或跨受试者泛化稳定。
- 目标硬件性能与真实摄像头延迟。
- 0.7038 阈值在部署中的误报率（运行时没有这个阈值）。
- c8/c9 的退化是否可接受：这是产品/报告决策，不是本文件的事实判断。
