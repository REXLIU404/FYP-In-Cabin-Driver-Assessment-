# Task 10A Stage 5：Release Decision（在役视觉模型）

- **状态：待用户决定（U-5）。** 在用户签字之前，在役模型保持 **stable MobileNetV3-Large**（代码默认值 `active_vision = "stable"`，计划 §8 Step 3：不自动启用 ResNet18）。
- 准备人：Claude（集成会话），2026-10-30。决定人：用户。
- 候选范围：stable MobileNetV3-Large（`stable_mobilenet_v3_large`）、ResNet18 候选（`resnet18_search004_seed42`，validation 选出的首选候选）。HPO MobileNetV3（`mobilenet_v3_large_search006_seed42`）只作对照：它的 clean test 结果不如 stable（下表）。遥测模型不在本次决定范围，固定为 stable XGBoost（`9802cb06…`）。

## 1. 选项与建议

| | A. 保持 stable MobileNetV3-Large（**建议**） | B. 改用 ResNet18 候选 |
|---|---|---|
| 优点 | 正常驾驶（c0）召回 0.921，ResNet18 为 0.833；正常驾驶帧被判为分心的比例 9.0%，ResNet18 为 20.2%；推理更快（服务端视觉中位数约 9.6 ms，ResNet18 约 26.6 ms），模型更小（16 MiB 对 43 MiB）；报告第 2–6 章、Table 23、正面摄像头诊断都以它为准，不必改写 | 整体指标更好：Macro-F1 0.889（stable 0.875）、Accuracy 0.902（0.899）、log loss 0.451（0.574，概率更可信，而 P_distraction 直接进入 RiskScore）；c9 召回 0.492（stable 0.273） |
| 代价 | 放弃 ResNet18 在整体 F1、log loss、c9 上的优势 | c0 召回下降约 9 个百分点，正常驾驶更容易被判为分心；端到端 p95 由 31 ms 升至约 44 ms（仍远低于 1 s）；报告需要改：6.2.3 结论段、Table 23 改为 ResNet18 的实测值、第 2/4 章关于在役模型的描述 |
| 两者都没有证明的 | 正面摄像头上的准确率（只量过 stable 的 domain shift）；目标硬件性能；融合后的风险准确率（没有同步的多模态真值） | 同左 |

**建议 A 的理由**：
1. 系统只使用 P(c0)（`P_distraction = 1 − P(safe_driving)`），所以最贴近风险输出的是「安全 / 分心」二分类：按 0.5 阈值，stable 把 9.0% 的正常驾驶帧判为分心，ResNet18 是 20.2%，多一倍以上；二分类准确率也是 stable 更高（0.965 对 0.959）。正常驾驶被误判为分心会直接抬高 RiskScore、产生误报。（这是离线诊断，不是实时风险的度量。）
2. 整体提升幅度小（Macro-F1 +0.015，Accuracy +0.003，测试集只有 4 名驾驶员）；E1 扰动稳定性互有胜负（例如强亮度降低时 ResNet18 翻转率 10.45%，stable 3.80%；强运动模糊时 ResNet18 48.32%，stable 56.99%）。
3. Stage 2 的系统级对比只能说明两者在 9% 的帧上判断不同、在 200 个窗口中有 5 个 RiskLevel 不同，没有风险真值，不能说明哪一个让风险输出更好。
4. 目标 3（real-time-ready、高效模型）与第 2 章选择 MobileNetV3 的理由一致；ResNet18 的视觉推理约慢 3 倍。

选择 B 也是有依据的选择（概率质量和 c9 更好）。如果选 B，§5 给出报告需要同步修改的地方。

## 2. 证据（每个路径都可打开）

| 证据 | stable MN | ResNet18 | 出处 |
|---|---|---|---|
| Validation 选择 | 历史基线 | validation 首选候选 | 报告 6.2.3；`ml/outputs/candidates/index.json`（role `VALIDATION_PREFERRED`） |
| Clean test（3,657 张，4 名留出驾驶员）Accuracy / Macro-F1 / log loss | 0.8988 / 0.8746 / 0.574 | 0.9016 / 0.8892 / 0.451 | 报告 Table 16；ML 轨道主仓库 `/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/ml/outputs/runs/p4b_20261022/evaluation_metrics.json` |
| c0 召回 / c9 召回 | 0.921 / 0.273 | 0.833 / 0.492 | 报告 Table 17；同上文件的 `confusion` |
| 二分类诊断（P_distraction 阈值 0.5；离线诊断，非实时风险）：准确率 / 正常驾驶帧被判为分心的比例 | 0.965 / **9.0%** | 0.959 / **20.2%** | 同上文件 `models.*.clean.distraction_diagnostic`（`interpretation: ADDITIONAL_OFFLINE_DIAGNOSTIC_NOT_LIVE_RISK`） |
| E1 扰动稳定性 | 互有胜负，无统一最优 | 同左 | 报告 Table 18 |
| 纯模型推理（ORT CPU，session.run p95） | HPO MN 7.25 ms（同架构参考） | 25.42 ms | 报告 Table 20 |
| Stage 1 provider 一致性（stable200，|Δp| ≤ 1e-4，argmax 一致 1.0） | PASS | PASS | `docs/evidence/2026-10-26/task10a-stage1/`；`docs/fyp2/task10a/stage1_audit_table.md`（Codex VERIFIED_PASS） |
| Stage 2 系统对比（stable200，三个模型同日运行，描述性） | 参照 | 与 stable 的 argmax 一致率 0.91；RiskLevel 不同 5/200 窗口；AlertSeverity 不同 12/200 | `docs/evidence/2026-10-29/comparison-official-bf76ddf/comparison_results.json`；`stage2_audit_table.md`（VERIFIED_PASS） |
| Stage 3 端到端（同日交替 3 轮，原始时序可复算） | capture→render p95 31 / 31 / 31 ms；服务端视觉中位数约 9.6 ms | 45 / 44 / 43 ms；约 26.6 ms | `docs/evidence/2026-10-30/stage3-raw/`（README 与六份 `perf01.json` + `perf01_timings.json`） |
| Stage 3 日志完整性（注入故障） | D1/D2 210/210 | 210/210 | `docs/evidence/2026-10-29/perf-stage3/{stable,rn}/perf02.json` |
| Stage 5 回滚演练 | 回滚后 hash `b3a42e8d…`、正常 forward | 在役时 hash `5e226722…`、正常 forward | `docs/evidence/2026-10-30/stage5-rollback-drill/`（11/11 PASS，exit 0） |
| 正面摄像头 | domain shift 已测出（约 5,170 帧几乎全判 c8/c9） | 未测 | `docs/evidence/2026-10-22/vision-runtime-path/README.md` |

## 3. 决定（由用户填写）

- 在役视觉模型：☐ A `stable_mobilenet_v3_large`　☐ B `resnet18_search004_seed42`
- 理由（可直接采用 §1，或写自己的）：
- 日期：
- 用户签字：____________________

## 4. 版本化配置与回滚

- 唯一开关：环境变量 `DRA_ACTIVE_VISION`。不设或设为 `stable` → stable MobileNetV3-Large；设为 `resnet18_search004_seed42` → ResNet18 候选（从 `ml/outputs/candidates/p5_resnet18_search004_seed42_20261023/` 读取，按 runtime manifest 校验 sha256 与类别）。稳定产物 `ml/outputs/vision/mobilenetv3_large_vision.onnx` 从不被覆盖。
- 启动（在仓库根目录）：
  - stable：`.venv/bin/python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000`
  - ResNet18：`DRA_ACTIVE_VISION=resnet18_search004_seed42 .venv/bin/python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000`
- 核对：`curl -s http://127.0.0.1:8000/api/models`，看 `vision.model_id` 与 `vision.sha256`（stable `b3a42e8d…`，ResNet18 `5e226722…`）；仪表盘运行信息行显示「Vision model: …」。
- 回滚：停掉服务，去掉 `DRA_ACTIVE_VISION` 后重新启动，再按上一条核对。这一流程已演练（§2 最后一行）。
- 若选 B：代码默认值不改（仍为 stable），在役状态由启动环境决定，回滚只需去掉环境变量；演示前用 `/api/models` 核对。
- 已知限制：`backend/.env` 也能设置 `DRA_ACTIVE_VISION`（Stage 2 的 R-3）；当前仓库没有 `backend/.env`。

## 5. 报告需要同步的地方（DOCX 由用户修改）

- **6.2.3 最后两句**（现为「The final system vision model remains undecided pending system-level evidence and the user's decision. The prototype retains the stable MobileNetV3 and XGBoost; xgboost_02 is not an approved replacement.」）：
  - 选 A：「After the system-level comparison, runtime measurement and a rollback drill, the stable MobileNetV3-Large was kept as the active vision model, mainly for its higher normal-driving recall (0.921 vs 0.833) and lower inference cost; ResNet18 search_004/seed42 remains an admitted candidate that can be switched in by configuration. xgboost_02 is not an approved replacement.」
  - 选 B：「After the system-level comparison, runtime measurement and a rollback drill, ResNet18 search_004/seed42 was made the active vision model for its higher Macro-F1 and lower log loss, accepting lower normal-driving recall (0.833 vs 0.921) and a higher but still sub-second latency; the stable MobileNetV3-Large remains the rollback model. xgboost_02 is not an approved replacement.」
- **Table 23**：选 A 可保留 10-22 的 stable 数字，或换成 10-30 的同日数字（stable p95 31 ms）；选 B 必须换成 10-30 的 ResNet18 数字（p95 43–45 ms），并注明「one development machine, Chromium fake camera」。
- 选 B 时还要改：第 4 章架构图与模型描述、第 7 章结论中关于在役模型的句子。
