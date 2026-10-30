# Task 10A Stage 5：Release Decision（在役视觉模型）

- **状态：已决定（U-5）——A，保留 stable MobileNetV3-Large。** 用户于 2026-10-30 在对话中选择（见 §3）；书面签字待用户补签。在役模型不变：代码默认值 `active_vision = "stable"` 本来就是 stable，不需要改任何配置（计划 §8 Step 3：没有自动启用 ResNet18）。
- 准备人：Claude（集成会话），2026-10-30。决定人：用户。
- 候选范围：stable MobileNetV3-Large（`stable_mobilenet_v3_large`）、ResNet18 候选（`resnet18_search004_seed42`，validation 选出的首选候选）。HPO MobileNetV3（`mobilenet_v3_large_search006_seed42`）只作对照：它的 clean test 结果不如 stable（Accuracy 0.8731、Macro-F1 0.8677，见报告 Table 16）。遥测模型不在本次决定范围，固定为 stable XGBoost（`9802cb06…`）。

## 1. 选项与建议

| | A. 保持 stable MobileNetV3-Large（**建议**） | B. 改用 ResNet18 候选 |
|---|---|---|
| 优点 | 正常驾驶（c0）召回 0.921，ResNet18 为 0.833；正常驾驶帧被判为分心的比例 9.0%，ResNet18 为 20.2%；「安全 / 分心」二分类准确率 0.965（ResNet18 0.959）；推理更快（服务端视觉中位数约 9.6 ms，ResNet18 约 26.6 ms），模型更小（16 MiB 对 43 MiB）；报告与已有证据都以它为准，不必改写 | 十分类整体指标更好：Macro-F1 0.889（stable 0.875）、Accuracy 0.902（0.899）；log loss 0.451（0.574），按这一指标概率估计更好，而 P_distraction 直接进入 RiskScore；分心帧被漏判为安全的比例 1.95%（stable 2.79%）；c9 召回 0.492（stable 0.273） |
| 代价 | 放弃 ResNet18 在十分类 F1、log loss、漏报率、c9 上的优势 | 正常驾驶帧被判为分心的比例约翻倍（20.2% 对 9.0%）；端到端 p95 由 31 ms 升至约 44 ms（仍远低于 1 s）；报告需要改：6.2.3 结论段、Table 23、第 2 章选择模型的理由、第 4 章架构与模型描述、第 7 章结论 |
| 两者都没有证明的 | 正面摄像头上的准确率（只量过 stable 的 domain shift）；目标硬件性能；融合后的风险准确率（没有同步的多模态真值） | 同左 |

**建议 A 的理由**：
1. 系统只使用 P(c0)（`P_distraction = 1 − P(safe_driving)`），所以最贴近风险输出的是「安全 / 分心」二分类。按 0.5 阈值（离线诊断，不是实时风险的度量）：
   - 正常驾驶帧被判为分心：stable 9.0%（39/431），ResNet18 20.2%（87/431）；
   - 分心帧被漏判为安全：stable 2.79%（90/3226），ResNet18 1.95%（63/3226）；
   - 合计错误：stable 129 帧，ResNet18 150 帧；二分类准确率 0.965 对 0.959。

   ResNet18 少漏几个分心帧，但多出一倍的正常驾驶误报。真实驾驶中正常驾驶占大多数（这个测试集里反而只有 431 帧），所以我更看重误报一侧；这是判断，不是测量结论。
2. 两边的差异都来自同一个小测试集（4 名留出驾驶员；c0 只有 431 帧），对 A 依赖的 c0 差异和 B 的整体提升同样适用。十分类整体提升幅度小（Macro-F1 +0.015，Accuracy +0.003）；E1 扰动稳定性互有胜负（例如强亮度降低时 ResNet18 翻转率 10.45%，stable 3.80%；强运动模糊时 ResNet18 48.32%，stable 56.99%）。
3. Stage 2 的系统级对比只能说明两者在 9% 的帧上判断不同、在 200 个窗口中有 5 个 RiskLevel 不同，没有风险真值，不能说明哪一个让风险输出更好。
4. 目标 3（real-time-ready、高效模型）与第 2 章选择 MobileNetV3 的理由一致；ResNet18 的视觉推理约慢 3 倍。

选择 B 也是有依据的选择（log loss、漏报率、十分类 F1 和 c9 更好）。如果选 B，§5 给出报告需要同步修改的地方。

## 2. 证据（每个路径都可打开）

| 证据 | stable MN | ResNet18 | 出处 |
|---|---|---|---|
| Validation 选择 | 历史基线 | validation 首选候选 | 报告 6.2.3；`ml/outputs/candidates/index.json`（role `VALIDATION_PREFERRED`） |
| Clean test（3,657 张，4 名留出驾驶员）Accuracy / Macro-F1 / log loss | 0.8988 / 0.8746 / 0.574 | 0.9016 / 0.8892 / 0.451 | 报告 Table 16；ML 轨道主仓库 `/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/ml/outputs/runs/p4b_20261022/evaluation_metrics.json` |
| c0 召回 / c9 召回 | 0.921 / 0.273 | 0.833 / 0.492 | 报告 Table 17；同上文件的 `confusion` |
| 二分类诊断（P_distraction 阈值 0.5；离线诊断，非实时风险）：准确率 / 正常驾驶帧被判为分心 / 分心帧被漏判为安全 | 0.965 / **9.0%**（39/431）/ 2.79%（90/3226） | 0.959 / **20.2%**（87/431）/ **1.95%**（63/3226） | 同上文件 `models.*.clean.distraction_diagnostic`（`interpretation: ADDITIONAL_OFFLINE_DIAGNOSTIC_NOT_LIVE_RISK`）；漏判数：ResNet18 由候选包 `predictions_test_clean.csv` 逐行计数，stable 由准确率与误报数推出（129 − 39） |
| E1 扰动稳定性 | 互有胜负，无统一最优 | 同左 | 报告 Table 18 |
| 纯模型推理（ORT CPU，session.run p95） | HPO MN 7.25 ms（同架构参考） | 25.42 ms | 报告 Table 20 |
| Stage 1 provider 一致性 | PASS（数值一致性由 parity100 的 100 个样本检查；stable200 按每类众数规则） | PASS（stable200：|Δp| ≤ 1e-4，argmax 一致 1.0） | `docs/evidence/2026-10-26/task10a-stage1/`；`docs/fyp2/task10a/stage1_audit_table.md`（Codex VERIFIED_PASS） |
| Stage 2 系统对比（stable200，三个模型同日运行，描述性） | 参照 | 与 stable 的 argmax 一致率 0.91；RiskLevel 不同 5/200 窗口；AlertSeverity 不同 12/200 | `docs/evidence/2026-10-29/comparison-official-bf76ddf/comparison_results.json`；`stage2_audit_table.md`（VERIFIED_PASS） |
| Stage 3 端到端（同日交替 3 轮；capture→render 可由原始时序复算，服务端分段只有汇总） | capture→render p95 31 / 31 / 31 ms；服务端视觉中位数约 9.6 ms | 45 / 44 / 43 ms；约 26.6 ms | `docs/evidence/2026-10-30/stage3-raw/`（README 与六份 `perf01.json` + `perf01_timings.json`） |
| Stage 3 日志完整性（注入故障） | D1/D2 210/210 | 210/210 | `docs/evidence/2026-10-29/perf-stage3/{stable,rn}/perf02.json` |
| Stage 5 回滚演练 | 回滚后 hash `b3a42e8d…`、正常 forward | 在役时 hash `5e226722…`、正常 forward | `docs/evidence/2026-10-30/stage5-rollback-drill/`（11/11 PASS，exit 0） |
| 正面摄像头 | domain shift 已测出（约 5,170 帧中 `safe_driving` 为最高类只有 5 次） | 未测 | `docs/evidence/2026-10-22/vision-runtime-path/README.md` |

## 3. 决定（由用户填写）

- 在役视觉模型：☑ A `stable_mobilenet_v3_large`　☐ B `resnet18_search004_seed42`
- 理由：采用 §1 的理由（正常驾驶误报约为 ResNet18 的一半、二分类总错误更少、推理更快、与报告一致；接受十分类 F1、log loss 与漏报率略差）。
- 日期：2026-10-30
- 记录方式：用户在 Claude 会话（Tasks1-10A）的问答中选择「A：保留 stable MobileNetV3」，同时选择 Table 23 改用 10-30 同日数字（§5）。
- ResNet18 候选保留为已接入、可一键切换的候选（§4），不删除。
- 用户签字：____________________

## 4. 版本化配置与回滚

- 唯一开关：环境变量 `DRA_ACTIVE_VISION`。不设或设为 `stable` → stable MobileNetV3-Large；设为 `resnet18_search004_seed42` → ResNet18 候选（从 `ml/outputs/candidates/p5_resnet18_search004_seed42_20261023/` 读取，按 runtime manifest 校验 sha256 与类别）。稳定产物 `ml/outputs/vision/mobilenetv3_large_vision.onnx` 从不被覆盖。
- 启动（在仓库根目录）：
  - stable：`.venv/bin/python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000`
  - ResNet18：`DRA_ACTIVE_VISION=resnet18_search004_seed42 .venv/bin/python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000`
- 核对：`curl -s http://127.0.0.1:8000/api/models`，看 `vision.model_id` 与 `vision.sha256`（stable `b3a42e8d…`，ResNet18 `5e226722…`）；仪表盘运行信息行显示「Vision model: …」。
- 回滚：停掉服务，去掉 `DRA_ACTIVE_VISION` 后重新启动，再按上一条核对。这一流程已演练（§2 最后一行）。
- 若选 B：代码默认值不改（仍为 stable），在役状态由启动环境决定，回滚只需去掉环境变量；演示前用 `/api/models` 核对。
- 已知限制：设置会读取**启动时当前目录**下的 `.env`，所以按上面的命令（在仓库根目录启动）时，仓库根目录的 `.env` 也能设置 `DRA_ACTIVE_VISION`（Stage 2 的 R-3）。目前仓库根目录和 `backend/` 下都没有 `.env`。

## 5. 报告需要同步的地方（DOCX 由用户修改）

- **6.2.3 最后两句**（现为「The final system vision model remains undecided pending system-level evidence and the user's decision. The prototype retains the stable MobileNetV3 and XGBoost; xgboost_02 is not an approved replacement.」）：
  - 选 A（**已选**，请用这一段）：「After the system-level comparison, runtime measurement and a rollback drill, the stable MobileNetV3-Large was kept as the active vision model, mainly for its higher normal-driving recall (0.921 vs 0.833) and lower inference cost; ResNet18 search_004/seed42 remains an admitted candidate that can be switched in by configuration. xgboost_02 is not an approved replacement.」
  - 选 B：「After the system-level comparison, runtime measurement and a rollback drill, ResNet18 search_004/seed42 was made the active vision model for its higher Macro-F1 and lower log loss, accepting lower normal-driving recall (0.833 vs 0.921) and a higher but still sub-second latency; the stable MobileNetV3-Large remains the rollback model. xgboost_02 is not an approved replacement.」
- **Table 23（用户已选：换成 10-30 同日数字）**：capture→render 一行改为「三轮各 600 个窗口（预热 20 个之后），中位数 27 / 28 / 28 ms，p95 31 / 31 / 31 ms，最大 127 / 63 / 58 ms，约 9.8 Hz」；Server total 一行改为「中位数 17.7–18.2 ms」；出处 `docs/evidence/2026-10-30/stage3-raw/`（stable-r1..r3）。注明「one development machine (Apple M2), Chromium fake camera, frozen models」。日志完整性与长会话两行沿用各自的证据（10-29 perf02：210/210；10-22 长会话：15 分钟 8,867 个窗口），并保留各自日期。
- 选 B 时还要改：第 2 章选择模型的理由、第 4 章架构图与模型描述、第 7 章结论中关于在役模型的句子（与 §1 的代价一栏一致）。
