# 系统轨道证据总索引

> **给评估者和写报告的人**：先读 `docs/fyp2/SYSTEM_TRACK_HANDOFF_GUIDE.zh.md`。里面有一页地图、可以直接粘贴的评估 prompt 和写报告 prompt、章节与证据的对应，以及措辞规则。

本文件把系统轨道（分支 `fyp2/live-system`）每一项工作的验收报告、技术报告、提交和门禁证据集中列在一处。

- **验收报告** `*-acceptance.zh.md`：中文，固定 6 节，即任务概要、实现证据、测试结果、问题与风险、验收结论、下一任务就绪度。由控制者在亲自复跑门禁后写成。
- **技术报告**：与验收报告同名、但不带 `-acceptance` 的文件。由实现者撰写，9 节，内容包括精确命令、变异记录、行号漂移等。
- **门禁计数**：「a → b」表示该项前后的测试数。四道门禁是 pytest、vitest、tsc、eslint，从 Task 10 第 1 部分起另加 build。

权威的逐任务规格在 `docs/plans/2026-10-12-fyp2-live-system-completion.md`，修订记录为 R1–R9。阶段状态见 `.planning/system-track/task_plan.md`。

## 1. 逐项完成证据

### 阶段 0：Tasks 1–6 与 F2

| 项 | 验收报告 | 技术报告 | 提交 |
|---|---|---|---|
| Task 1–6 | `task-01-acceptance.zh.md` … `task-06-acceptance.zh.md` | `task-01.md` … `task-06.md`；汇总见 `TASK_1_TO_6_SUMMARY.md`（含 R08 勘误） | `845b43a..564d0b1` |
| F2 | `task-F2-acceptance.zh.md` | `task-F2.md` | `ef2417d` |

### 阶段 1：审阅修复批次

| 项 | 验收报告 | 技术报告 | 提交 |
|---|---|---|---|
| F4：ROUND_HALF_UP | `phase1-01-f4-acceptance.zh.md` | `phase1-01-f4.md` | `f289d66`、`9632812` |
| R08：stale 说法勘误，UT/IT-LIVE-AGE | `phase1-02-r08-acceptance.zh.md` | `phase1-02-r08.md` | `c7391b5` |
| R13：遥测 gap 测试 | `phase1-03-tgap-acceptance.zh.md` | `phase1-03-tgap.md` | `d83782d` |
| R05：IT-EPS | `phase1-04-iteps-acceptance.zh.md` | `phase1-04-iteps.md` | `2c07d79` |
| P1-6：TS 舍入 | `phase1-06-tsround-acceptance.zh.md` | `phase1-06-tsround.md` | `b53f007` |
| F1 / R30：missing_cases 重核 | `phase1-05-f1-acceptance.zh.md` | `phase1-05-f1.md` | `239f7c2` |

### 阶段 2 起：Task 7 以后

| 项 | 验收报告 | 技术报告 | 提交 | pytest / vitest |
|---|---|---|---|---|
| Task 7：`fault_events` | `task-07-acceptance.zh.md` | `task-07.md`、`task-07-followup.md`、`task-07-followup2.md` | `6e8039c`、`c4926b3`、`9b21296` | 525 → 584 / 427 |
| Task 8：有界重试 | `task-08-acceptance.zh.md` | `task-08.md`、`task-08-followup.md` | `e37a312`、`90a2f2f` | 584 → 598 / 427 → 533 |
| P0-D13：裁定 A（过期证据按 missing） | `p0-d13-ruling-a-acceptance.zh.md` | `p0-d13-ruling-a.md` | `5e72340`、`67af63e` | 598 → 704 / 533 → 594 |
| Task 9：Live-only 范围 | `task-09-acceptance.zh.md` | `task-09.md` | `c304aa0`、`6ec6799` | 704 / 594 → 709 |
| Task 10 第 1 部分：门禁基础设施 | `task-10-part1-acceptance.zh.md` | `task-10-part1.md` | `1a321b0`、`89e8df0` | 704 → 775 / 709 → 771 |
| R10-A：后端观测身份与双条件 FSM | `r10a-backend-acceptance.zh.md` | `r10a-backend.md`、`r10a-followup.md` | `44b7c62`、`6c95db4`、`ef341fa`、`cc477d6` | 775 → 907 / 771 |
| R10-B：前端 seq、帧元组、payload | `r10b-frontend-acceptance.zh.md` | `r10b-frontend.md` | `8e9319a`、`daa08ad`、`c359945` | 907 → 922 / 771 → 870 |
| Task 10 第 2a 部分：Live 端到端 | `task-10-part2a-acceptance.zh.md` | `task-10-part2a.md` | `47484d3`、`afcdd0b` | 922 → 934 / 870 |
| Task 10 第 2b 部分：单分支系统测试与 W4 归档 | `task-10-part2b-acceptance.zh.md` | `task-10-part2b.md` | `ae1c197`、`c2191c0`、`87bdc3f`、`eb000bc` | 934 → 952 / 870 |
| FIX-BACKEND-REACH：后端没启动被误报为模型错误；真实重启后端 e2e | `fix-backend-reach-acceptance.zh.md` | `fix-backend-reach.md` | `83219da` | 952 → 967 / 870 → 910 |
| TELEMETRY-CONTRIBUTIONS：Live 遥测特征贡献（TreeSHAP，解释非安全风险） | `telemetry-contributions-acceptance.zh.md` | `telemetry-contributions.md` | `346f3a6` | 967 → 979 / 910 → 918 |
| W5 系统测试（S1–S5、S10）：选中跟随最新、ST-SESSION-01、ST-COLDSTART-01、Task 10A manifest 交接、E3 网格 | `w5-system-tests-acceptance.zh.md` | 执行计划 `docs/plans/2026-10-22-w5-w6-system-tests.md` | `62f13fb`…`6491dd7`，评审后修复 `183d38f`、`258e380`、`0530b1a`、`7110615` | 979 → 1021 / 918 → 922 |
| W6 系统测试（S6–S9）：ST-LONG-01、PERF-01、PERF-02、G-W6-A | `w6-system-tests-acceptance.zh.md` | 同上 | `bb947f0`、`4f38cfc`、`66327ee`，评审后修复 `349ee61`、`e03ed41`、证据重跑 `2897000` | 1021 → 1028 / 922 |
| 界面易用性审查与暂缓 Minor（M1–M4、M6–M11、M13、Server-Timing） | `ui-review-minors-acceptance.zh.md` | 提交信息即技术说明；截图在 `docs/evidence/2026-10-23/ui-review/` | `6886a2e`、`2745348` | 1028 → 1046 / 922 → 954 |

每份验收报告的第 3 节都列出了变异检验：每项变异在隔离副本里运行，并写明变红的测试。

## 2. 每周 gate 证据（原始门禁日志）

周计划与 gate 的定义在冲刺计划 v3，即桌面上的 `01_FYP2_Parallel_Sprint_Plan_W2_W7_v3.zh.md`（§5、§6），不在仓库里。

| Gate | 目录 | 提交 | 结果 |
|---|---|---|---|
| G-W2-A（补档） | `docs/evidence/2026-10-16/w2-gate/` | `cbe573f`，在隔离副本上运行 | 全绿：pytest 584，0 skipped；vitest 427 |
| G-W3-A（提前关闭） | `docs/evidence/2026-10-19/w3-gate/` | `ce45f53` | 全绿：build；pytest 922；vitest 870；tsc 0；eslint 0 |
| G-W4-A（提前关闭） | `docs/evidence/2026-10-20/live-e2e/` | `87bdc3f` | 全绿：build；pytest 952，0 skipped；vitest 870；tsc 0；eslint 0。另有五视图截图、会话导出、rVFC 实测 |
| G-W5-A（硬性，提前关闭） | `docs/evidence/2026-10-22/w5-gate/`，冷启动 `docs/evidence/2026-10-22/coldstart/` | `5040e9d` | 全绿：pytest 1021 / 0 skipped（1 deselected = ST-LONG-01），vitest 922，tsc，eslint，build |
| G-W6-A（提前完成，不含 E2–E5 runner） | `docs/evidence/2026-10-22/perf/`，回归 `docs/evidence/2026-10-22/coldstart-final/` | `2897000` | 全绿：全新克隆上 pytest 1028 / 0 skipped，vitest 922；长会话 8,867 窗口；capture→render p95 39 ms；日志完整性 100%；E2–E5 等 D06 |
| 界面审查与 Minor 修复（不是计划内的 gate） | `docs/evidence/2026-10-23/ui-minors-gate/` | `2745348` | 全绿：pytest 1046 / 0 skipped，vitest 954，tsc，eslint，build |

每个 gate 目录都包含以下文件：

- `SUMMARY.md`；
- 各道门禁的完整日志，含版本、环境、argv、退出码、跳过数；
- `freeze_manifest.txt`，即三个模型文件的哈希；
- `README.md`，把计划里的每项 gate 检查对应到具体测试和验收报告。

单项的附加证据：`docs/evidence/2026-10-19/task-10-part2a/`，包括 e2e 日志、变异记录、rVFC 实测 JSON、控制者修正的验证记录。人工验收清单与自动化测试的对应关系见 `prototype-tests/live_e2e.md`。

更早的 `docs/evidence/2026-09-28/`、`2026-10-05/`、`2026-10-09/` 是 Live 系统开工前的基线运行证据，保留原样。

## 3. 审计与评审

| 内容 | 位置 |
|---|---|
| 原始 FYP2 审计（执行摘要、测试清单、评估矩阵、证据清单等） | `docs/fyp2/00_…` 到 `08_…`，以及 `docs/fyp2/evidence/` |
| Codex 独立审阅（10-13） | `docs/fyp2/review/CODEX_INDEPENDENT_AUDIT_REVIEW_2026-10-13.md` |
| Codex 对 R10 的独立评审（10-16，结论 REVISE，已按 v3 处理） | 不在仓库里：`/private/tmp/r10-independent-review-yixmo02m/R10_INDEPENDENT_REVIEW.zh.md`；SDD 目录 `r10/` 下有副本 |
| ML 轨道进度（Codex 维护） | 主仓库 `docs/fyp2/ml/ML_TRACK_PROGRESS.md` 与 `ml/outputs/runs/` |

## 4. 不在仓库里的过程记录

SDD 工作区 `.superpowers/sdd/2026-10-12-fyp2-live-system-completion/` 被 git 忽略，只在本机。里面有：

- `progress.md`：每一步的派发、评审结论与控制者裁定（`Ruling:`）；
- 每项的 brief；
- R10 提案 v3 与模拟器。

验收报告已经写进了其中影响结论的裁定。
