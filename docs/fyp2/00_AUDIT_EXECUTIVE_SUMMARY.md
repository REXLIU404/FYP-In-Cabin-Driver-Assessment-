# FYP2 Repository Audit — Executive Summary

> 审计日期：2026-10-10（Asia/Kuala_Lumpur）；实跑检查时间见各 evidence 日志（主要为 2026-10-09）。审计对象是用户确认的桌面主仓库 `/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1`，branch `dev_cc`，HEAD `17c4b41bcfe517c8311b7f6fc2a327f616a916fe` **加未提交内容**。本文所有应用源码相对路径都相对此根目录，不相对当前旧工作树。输出工作树 HEAD `ae550415237fc1f67bf0de50c643a6d8bd6aca60`。命令 ID、环境、时间、退出码、指纹见 [07 证据索引](07_EVIDENCE_MANIFEST.md) 与 [source inventory](evidence/source_inventory.json)。

证据层次：`CURRENT_VERIFIED`=本次源码/产物检查或明确限定范围的实跑；`FYP1_REPORTED`=未在本次对应范围复现的继承指标；`PLANNED`=建议，未执行。旧实验日志标明 historical，不算本次运行。实现状态与测试执行状态分别记录；`MISSING_TEST` 是测试缺口标记，不是实现状态。未发现只适用于已扫描范围。

## 结论与置信度

**当前是已接入真实 baseline 的本机研究原型，W3 的核心 backend 链路已有实跑证据；尚不能签署 W7 feature-complete。** 对代码路径和本次测试结果置信度高，对完整浏览器演示为部分验证，对真实道路/正面摄像头泛化没有足够证据。不能从日期推断当前 academic week。

- `CURRENT_VERIFIED / TEST_PASSED`：后端 28 tests、前端/共享逻辑 32 tests、lint、替代 config loader 下的 production build 均通过。标准 build 曾因沙箱不允许写主仓库 `node_modules/.vite-temp` 而 BLOCKED，不能记成应用编译缺陷或隐去失败。证据：`PYTEST/VITEST/LINT/BUILD/BUILD-RUNNER`。
- `CURRENT_VERIFIED / TEST_PASSED`：真实 ONNX + XGBoost → `/infer` → backend EMA/fusion/FSM → SQLite/latest/flag/JSON/CSV；现有 live 集成测试输入是确定性纯色 JPEG 和手写 telemetry，证明模型执行及持久化，不证明驾驶行为识别正确。`backend/tests/test_live_inference.py:17–81`；`PYTEST`。
- `PARTIALLY_VERIFIED`：React Live 模式消费服务器结果，默认 `LIVE_MODEL_RUNTIME`；摄像头配 **prepared raw telemetry**，并非两路真实车载传感器。`ai/src/riskLogic.ts:13–24`、`frontend/src/hooks/useLiveSession.ts:137–179`。本次没有新浏览器/摄像头演示；2026-10-05 浏览器与 10-09 HTTP 记录为历史辅助证据。
- `CURRENT_VERIFIED`：原始视觉 split 的司机集合无交集（18/4/4 drivers，15899/2868/3657 frames）；本次视觉仅 20 张 smoke，不重申 full-test accuracy 已重跑。XGBoost 全 4500 synthetic test records 本次复现 accuracy `0.9993333333`、macro-F1 `0.9993331847`。`ML-VISION-SMOKE/ML-TELEMETRY`、`evidence/data_artifact_audit.json`。
- 三个要求中的 comparator（ResNet18、telemetry RF、telemetry LR）及五模型 HPO 没有完成证据。存在的图像 frozen-backbone logistic probe 不能替代 telemetry LR；Small/B0 latency 不能替代 ResNet18。`ml/experiments/vision_benchmark.py:22–35`、`ml/experiments/linear_probe.py:103`。

## Top 10 blockers / gaps

| ID | 优先级 | 发现与精确证据 | 实现/验证状态 | 下一步与验收 |
|---|---|---|---|---|
| B01 | P0 | 双 missing 返回 `0/Low/NORMAL + UNAVAILABLE`；API/export 与无证据语义矛盾。`fusion.py:37–38`、`inference.py:38–65` | `TEST_FAILED` 对 E3-03；DIAGNOSTICS。Live 主面板已隐藏 score，不能说整个 UI 无提示 | 统一 unavailable 数据契约，含 export/trends/inspector；UT-FUS-03 + ST-FAIL-01 |
| B02 | P0 | `(w_v,w_t)=(1,0)`、V missing/T fresh 时有效分母为 0，但 health=DEGRADED、score=0。`schemas.py:90–105`、`fusion.py:34–58` | `TEST_FAILED`；UT-FUS-ZERO-WEIGHT diagnostic | 按有效证据可用性处理，而非只数 missing flags |
| B03 | P0 | 错误码处理有实现，但缺 DB 不可用、模型运行异常、网络恢复的 UI+DB+error-log 验证；错误请求无持久 fault 表。`windows.py:101–106`、`models.py:20–66` | `PARTIALLY_VERIFIED`；`MISSING_TEST` | 注入故障并恢复，证明无伪预测、无重复/丢失且错误可追踪 |
| B04 | P0 | 完整 browser→API→DB 演示仅历史记录，本次无可重复 E2E suite；W2 replay UI 也不经过 API。`App.tsx:50–79` | `PARTIALLY_VERIFIED` | 同一 frame/request ID 从 UI 到 export 的 ST-REPLAY-01 |
| B05 | P0 | clone 不含未提交 runtime 与 git-ignored 模型；notebooks/metrics 与当前本机状态不能构成 release。`source_inventory.json`、`ml/.gitignore` | `BLOCKED` 对 clean-checkout demo gate | 后续交付版本清单、受控模型分发、锁定依赖；本次不 commit/push |
| B06 | P1 | 五模型对照与 bounded tuning 不齐；baseline selection 为 vision val accuracy、XGB val logloss early stop。notebook cells 13/7 | `PLANNED_ONLY`（完整五模型要求） | 先批准固定预算/validation macro-F1 选择规则，再实施；禁止本次启动 |
| B07 | P1 | E1 只有 validation 上 dim/gaussian-blur pilot，缺 test 6×3、D1–D3 generators、第二视觉/三遥测模型结果。`robustness_probe.py:22–46` | `PARTIALLY_VERIFIED` pilot；required pack `PLANNED_ONLY` | 固定样本/参数/label QC，与 DMD 分开 |
| B08 | P1 | E2/E5 缺 source-ID scenario pairs、五权重结果、独立场景 oracle；无真实同步 severity 标签证据 | `PLANNED_ONLY`；扫描清单/规范 | 只评 operational consistency/complementarity；不得声称真实风险识别提升 |
| B09 | P1 | 未测 capture→render p95≤1s 或有分母的 log completeness≥99%；server latency 在 commit 前结束。`windows.py:62–73` | `NOT_FOUND`（所需指标产物） | PERF-01/02，分开处理时延、警报持续门槛和模型前向时延 |
| B10 | P1 | UAT 实际参与者/任务结果和官方 rubric 原文件未发现；原文档 E1–E5 命名冲突 | `NOT_FOUND` UAT/官方 rubric；legacy plan present | 执行真实 UAT，确认 rubric 与 revised criteria；不要伪造人数 |

以上优先级是本次审计建议，不代表修复已获执行授权或完成。P0 先于模型优化；P1 的五模型 HPO 是开发必需项，不降为 optional。

## E1–E5 方法学判定

| 项 | 判定 | 正确解释与禁止结论 |
|---|---|---|
| E1 | `SOUND_WITH_RESTRICTIONS`；现有 pilot 要 `NEEDS_REDRAFT` 才能满足规范 | paired held-out corruption、train-only statistics；D2 label-conditioned，可能使原标签失效；grayscale 不是真 IR |
| E2 | `SOUND_WITH_RESTRICTIONS` | 手算 formula/边界/五权重与证据解释合理；constructed pair 不提供真实风险分类 accuracy |
| E3 | formula cases `SOUND`；无条件 ΔRisk 门槛 `NEEDS_REDRAFT` | `.1/.9` full `.5`，V missing 后 `.9`，Δ=.4 是正确重归一化；记录原目标未达，不能报 formula failure |
| E4 | `SOUND_WITH_RESTRICTIONS`；recovery-tail 旧测试 `NEEDS_REDRAFT` | fake clock、EMA variance 与 lag 同报；当前没有 N=3 failure policy；不能用绿色单测证明完整故障恢复 |
| E5 | `SOUND_WITH_RESTRICTIONS`；仅靠更小 score drift 证明 safety 的推论 `INVALID` | 简单平均天然缩小波动，也可能稀释高风险分支，须报告反例及标签限制 |

## 下一步 72 小时（建议，未执行）

1. **0–24h：**冻结当前 source/model/split manifest，完成 B01/B02 契约决策，补独立 formula/zero-denominator/freshness tests；先使正常及不可用路径一致。
2. **24–48h：**补真实 baseline 的 browser/API/DB/export 可重复 demo 和故障恢复，定义 error logs 分母；建立 clean-start package，处理 P0。
3. **48–72h：**锁定五模型 HPO 预算和 split；准备 E1 generators 与 E2/E5 provenance/oracle 小样例、PERF/UAT 脚本。先验收脚本，不把 72 小时写成五模型实验全部完成。

详细依赖与每周 gates 见 [06](06_WEEK7_CRITICAL_PATH_AND_ACTION_PLAN.md)。九份要求文档为本目录 `00`–`08`；机器清单为 [audit_manifest.json](audit_manifest.json)，日志见 [evidence](evidence/)。本次审计交付完成不等于上述开发缺口已修复。
