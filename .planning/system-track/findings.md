# 发现与决策

## 需求

- 用户要求（2026-10-13）：理解 Codex 审阅结果；判断是否更新计划；为系统开发轨道建 roadmap；整理文档；说明 Codex 现在并行做什么；把本会话的上下文交给「Tasks1-6+7」会话继续开发。
- 长期偏好：中文回答；Codex 反馈原文展示；一次一个问题；Codex 在主仓库内用分支下拉切换，不为它新建文件夹。

## Codex 独立审阅（`docs/fyp2/review/CODEX_INDEPENDENT_AUDIT_REVIEW_2026-10-13.md`）要点

> 原件在主仓库 `docs/fyp2/09_INDEPENDENT_AUDIT_REVIEW.md`（未跟踪，在 Codex 的工作区里）。系统轨道保存了一份逐字副本，两者 SHA-256 前缀均为 `0731ebfbe8c49ef0`。

**审阅没有按提示词逐项回答 D-A…D-F**，改为做了一份方法学 + QA 审查（32 行 reviewer matrix、E1–E5 方法学结论、Top 10 缺口、补测清单）。因此 D-A 的 7 条 Ruling 没有逐条「接受 / 推翻」；其中能间接读出的：
- ROUND_HALF_UP：R30 称「half-up 数值有意改变」，要求写回计划（即 F4），未推翻。
- 迁移改写历史行：R31 要求「披露不可逆改写，真实迁移另需备份与授权」，未推翻。
- 不引入 jsdom：R17 要求 E2E 做逐 ID 验证，未要求 DOM 测试。

**已确认修好（不再列为缺陷）**：R04（双 missing 不再伪造 0 / Low）、R05（零有效权重）、R11（30 / 60、2 s / 10 s 边界）、R12（unavailable 期间 FSM 挂起）、R13（F2 watermark）。

**判我们错的（INCORRECT）**：
- **R08**：「Live 不会出现 stale」是错的。已核实：`backend/app/inference.py:107` 用 `provenance.captured_at` 重判 freshness；`backend/tests/test_live_inference.py:114-118` 自己就断言旧 `captured_at` 经 `/infer` 得到 `stale` / `DEGRADED`。正常浏览器操作下前端打 `new Date()`，age 接近 0，但网络或处理延迟超过 3 秒、客户端时钟偏差、或任何直接调用 API 的客户端都能触发。**D13 因此在 Live 上可达**。
- **R14**：`DominantEvidence` 不接收权重。pd=.8、pt=.6、w=.3/.7 时 score 66，贡献 24 对 42，却标「Vision-dominant」。若对外解释为「驱动了融合输出」，就与加权贡献相反。
- **R26**（数据侧，归 ML 轨道）：外部 EDA 脚本在 split 之前对全量 30k 计算 median，文档却写 train-only。原始 8 特征无 NaN，所以**没有证据说当前 .9993 被污染**，但未来 D3 有泄漏风险。

**无法认证（UNRESOLVED）**：
- R02：最新 506 / 394 未被独立重跑（Codex 只独立跑了 tsc = 0）。要求发布 version / env / argv / exit / skips 的原始日志。
- R03：约 40 次变异检验没有逐次的不可变运行产物。
- R27：测试集已被多次接触，不能称「pristine」；未发现直接用 test 选参的代码。

**Top 10 缺口中属于系统轨道的**：#1 Live stale 与 expiry 政策（P0）、#2 typed fault + bounded frozen retry + 持久 outcome ledger（P0，即 Task 7 / 8）、#3 当前版本的 browser → API → DB → export E2E（P0，即 Task 10）、#4 目标摄像头带标注验证（P0 / P1）、#5 版本绑定的 release 证据（P1）、#8 E2 / E5 pair manifest 与 DominantEvidence 语义（P1）、#9 E4 lag / 性能 / logging（P1）、#10 UAT 与 F1 / F4 同步（P1）。
**属于 ML 轨道的**：#6 五模型 + 全部 bounded HPO、#7 E1 生成与 train-only 统计 provenance。

## 是否更新计划：是（计划 R4）

理由：R08 推翻了计划里的一条事实陈述（第 44 行、R1 #8、风险表）；R16 / R17 / R02 / R31 给 Task 7 / 8 / 10 加了具体的必测场景；R09 / R10 / R14 是新的待决政策项；F4 与 F1 的「等 Codex」前提已解除。Tasks 1–6 本身**不需要重做**。

## 归属建议：E2–E5 由系统轨道负责

- Codex 的 `fyp2/ml-training` 停在 `efb3ea6`，那是 Tasks 1–6 **之前**的代码：没有 nullable 契约、没有 ROUND_HALF_UP、没有 FSM 挂起。在那里跑融合评估，结果对应的是旧系统。
- 与 Task 10A 的决定一致：融合 / EMA / FSM 的评估复用系统代码，不在 ML 轨道另写一份。
- ML 轨道保留：五模型比较、bounded HPO、E1（vision 6×3、telemetry D0–D3）、R26 imputer provenance、R27 test 曝光披露、候选模型包。

## 文档整理（盘点结果，待用户确认后执行删除 / 归档）

`dev_cc` 相对分叉点只**新增**了 `docs/fyp2/09_BROWSER_VERIFICATION_2026-10-12.md`、`10_SYSTEM_PARAMETERS_EXPLAINED.zh.md` 与浏览器证据，和下列文件**没有重叠**，所以在 `fyp2/live-system` 上删除或移动不会造成合并冲突。

| 类别 | 文件 | 建议 |
|---|---|---|
| 现行 | `README.md`、`CLAUDE.md`、`PROJECT_MEMORY.md`、`backend/README.md`、`docs/plans/…completion.md`、`docs/fyp2/implementation/*`、`docs/fyp2/release/RELEASE_MANIFEST.md`、`docs/fyp2/review/*`、`docs/LIVE_RUNTIME_GUIDE.zh.md`、`docs/explanation-implementation-guide.zh.md` | 保留（`LIVE_RUNTIME_GUIDE` 内容停在 10-09，Task 9 / 10 时更新） |
| 审计包（冻结证据） | `docs/fyp2/00`–`08`、`audit_manifest.json`、`docs/fyp2/evidence/*`、`docs/fyp2/{task_plan,findings,progress}.md`（首轮审计员的工作笔记） | 保留原位：Codex 审阅按路径与哈希引用它们，移动会断链 |
| 报告证据 | `docs/evidence/`（按日期的 Chapter 5 证据） | 保留 |
| 零引用、已被取代 | `Changelog.md`（05-21，19 行）、`backend/COMPLETION_PLAN.md`（06-03，被计划取代） | **已删除**（2026-10-13，用户批准） |
| 零引用、历史快照 | `docs/prototype-summary.md`、`docs/system-explanation-script.zh.md`、`docs/figma-wireframe-fit-analysis.md` | **已删除**（2026-10-13，用户批准） |
| 被审计包引用的历史快照 | `docs/DEVELOPMENT_SCHEDULE.md`、`docs/IMPLEMENTATION_PROGRESS.zh.md`、`docs/CLAUDE_HANDOFF_PROMPT.zh.md`、`docs/FYP2_CLAUDE_DEVELOPMENT_HANDBOOK.zh.md`、`docs/PROJECT_ASSESSMENT_AND_TEST_PLAN.zh.md` | **不删**（审计证据引用）；在 `docs/README.md` 索引中标为「已被取代的历史快照」 |
| 已修正的数据 | `ai/prototype-data/.../missing_cases.csv` | 不是文档，属 F1，阶段 1 修 |

## A–G 模型防范清单审查（未复核）

三个视角的原始结果在 workflow journal（run `wf_fbb31b26-162`）。合并复核步骤因会话额度失败，所以**未复核、未写入计划**。等写 Codex 的「候选模型包要求」时再用。各视角提出的、需用户裁定的开放问题已记在该 journal 里，例如：基线 ONNX 是否走「只有清单」的 legacy 处理；冒烟集取自 val 还是 train；模型哈希变化时会话如何处理。

## 资源

- 计划：`docs/plans/2026-10-12-fyp2-live-system-completion.md`
- SDD ledger：`.superpowers/sdd/2026-10-12-fyp2-live-system-completion/progress.md`
- Codex 审阅副本：`docs/fyp2/review/CODEX_INDEPENDENT_AUDIT_REVIEW_2026-10-13.md`
- Codex 提示词：`docs/fyp2/review/CODEX_REVIEW_PROMPT.md`、`CODEX_ML_TRACK_PROMPT.md`
