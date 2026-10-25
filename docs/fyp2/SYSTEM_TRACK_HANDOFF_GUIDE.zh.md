# 系统轨道交接指南：让其他 agent 评估完成度；撰写报告的 System Development 与 Evaluation 部分

> 适用分支：`fyp2/live-system`。本指南列出的提交号、数字和路径，都是生成本文时已经提交的证据。
> 原则只有一条：**报告和评估里的每个数字，都必须能在下文列出的某个文件里找到出处。**

## 0. 一页地图：先读这些

| 用途 | 文件 |
|---|---|
| **总索引**：每一项的验收报告、技术报告、提交号、测试数变化，以及每周 gate | `docs/fyp2/implementation/README.md` |
| 主计划与完成定义（DoD，Task 1–10 / 10A） | `docs/plans/2026-10-12-fyp2-live-system-completion.md`：Global Constraints；「Definition of Done」一节；R1–R9 修订记录 |
| W5 / W6 系统测试执行计划 | `docs/plans/2026-10-22-w5-w6-system-tests.md`（S1–S10） |
| 每周 gate 的定义 | 冲刺计划 v3：`/Users/liu/Desktop/01_FYP2_Parallel_Sprint_Plan_W2_W7_v3.zh.md`，§5 和 §6。**不在仓库里** |
| 评估设计（E1–E5）与 2026-10-22 增补节 | `docs/fyp2/03_EVALUATION_COVERAGE_MATRIX.md`（以末尾的增补节为准） |
| 报告各章对应的审计意见（10-10 版，部分状态已过时，以本指南第 2 节为准） | `docs/fyp2/05_RUBRIC_TRACEABILITY_AND_REPORT_MAP.md` |
| 待导师决定的事项 | `docs/fyp2/08_OPEN_DECISIONS_FOR_SUPERVISOR.md`（D06 构造场景、D07 延迟口径等） |
| 每项的中文验收报告（固定 6 节） | `docs/fyp2/implementation/*-acceptance.zh.md` |
| 每项的技术报告（实现者写，9 节：命令、变异、行号） | `docs/fyp2/implementation/<项>.md` |
| Task 10A 交接给 ML 轨道的模型包契约 | `docs/fyp2/handoff/task-10a-runtime-manifest.md` |

**每周 gate 的原始证据**（每个目录都有 `SUMMARY.md`、5 道门禁的完整日志、`freeze_manifest.txt`，以及把 gate 检查项逐条对应到测试的 `README.md`）：

| Gate | 目录 | 结果 |
|---|---|---|
| G-W2-A（补档） | `docs/evidence/2026-10-16/w2-gate/` | 全绿 |
| G-W3-A | `docs/evidence/2026-10-19/w3-gate/` | 全绿 |
| G-W4-A（Live 端到端 + 单分支系统测试） | `docs/evidence/2026-10-20/live-e2e/` | 全绿 |
| G-W5-A（会话生命周期、冷启动） | `docs/evidence/2026-10-22/w5-gate/`，冷启动在 `docs/evidence/2026-10-22/coldstart/` | 全绿 |
| G-W6-A（长会话、PERF；不含 E2–E5 runner） | `docs/evidence/2026-10-22/perf/`，回归在 `docs/evidence/2026-10-22/coldstart-final/` | 全绿（全新克隆上 pytest 1028 / 0 skipped） |
| 界面审查与暂缓 Minor 修复（2026-10-23） | `docs/evidence/2026-10-23/ui-minors-gate/`，截图在 `docs/evidence/2026-10-23/ui-review/` | 全绿（pytest 1046 / 0 skipped，vitest 954）；独立评审的 31 条交给 DeepSeek 验证与修复 |
| 视觉 domain shift 的证据 | `docs/evidence/2026-10-22/vision-runtime-path/` | 管线正确，问题在摄像头视角 |

**不在仓库里的两样东西**：
- SDD 账本 `.superpowers/sdd/2026-10-12-fyp2-live-system-completion/progress.md`，被 git 忽略，记录了每一次派发和每条裁定；
- Codex 对 R10 的评审，在 `/private/tmp/r10-independent-review-yixmo02m/`。

需要的话，可以把这两样单独交给评估者。

---

## 1. 让其他 agent 评估完成度

### 1.1 推荐流程：三层核对

1. **固定一个提交**：让评估者只读这个提交，或者在临时目录里克隆这个提交。不要让它在你的工作树里改东西。
2. **声明层**：逐份读验收报告，核对报告里写到的提交、测试文件、测试名、证据路径、数字，是否都真实存在并且一致。
3. **复现层**：一条命令在全新克隆上复现全部门禁：

   ```bash
   scripts/coldstart_check.sh <commit>
   ```

   它会克隆、按锁文件装依赖、`npm ci`、链接模型、跑 build / pytest（含全部浏览器测试）/ vitest / tsc / eslint，最后从干净副本启动服务。可选项：
   - `-m long`：15 分钟长会话；
   - `scripts/perf01.py`、`scripts/perf02.py`：性能和日志完整性。
4. **质量层**：抽查 2–3 项变异。验收报告第 3 节写明了每项变异的具体改法，在隔离副本里改一处，确认对应的测试会变红。
5. **输出**：一张完成度矩阵，每一行是一项，状态从 VERIFIED / PARTIAL / NOT_DONE / CANNOT_VERIFY 中选一个，并附证据路径。核对的依据有三份：主计划的 DoD、冲刺计划各周的 gate、覆盖矩阵。

### 1.2 可以直接粘贴给评估 agent 的 prompt（Codex 或另一个 Claude 均可）

```text
You are an independent auditor of the FYP2 system track. Work READ-ONLY.

Repository: /Users/liu/Desktop/FYP2-Live-System, branch fyp2/live-system, commit <COMMIT>.
Do all checks in a fresh clone: `git clone /Users/liu/Desktop/FYP2-Live-System /tmp/audit && git -C /tmp/audit checkout <COMMIT>`.
Never touch port 8000, backend/driver_risk.db*, the main repository, or push anything.

Inputs, in this order:
1. docs/fyp2/SYSTEM_TRACK_HANDOFF_GUIDE.zh.md (this guide): sections 0 and 1.3.
2. docs/fyp2/implementation/README.md: the index of every item, its acceptance report and commits.
3. The specs:
   - docs/plans/2026-10-12-fyp2-live-system-completion.md ("Definition of Done", Global Constraints);
   - docs/plans/2026-10-22-w5-w6-system-tests.md;
   - docs/fyp2/03_EVALUATION_COVERAGE_MATRIX.md (including the 2026-10-22 addendum);
   - the sprint plan /Users/liu/Desktop/01_FYP2_Parallel_Sprint_Plan_W2_W7_v3.zh.md, sections 5 and 6 (gates).

Procedure:
A. Claims. For every acceptance report (docs/fyp2/implementation/*-acceptance.zh.md), check that each commit,
   file, test name, evidence path and number it states exists and matches (git show, grep, read the logs in
   docs/evidence/**). List every mismatch.
B. Reproduction. Run `scripts/coldstart_check.sh <COMMIT>` from the clone, with COLDSTART_OUT pointing to a temp
   dir, and the three model files supplied via COLDSTART_MODEL_ROOT. Report every step, its result and the
   pytest / vitest counts.
C. Test quality. For three items of your choice, apply one mutation listed in the item's acceptance report
   (section 3) in an isolated copy and confirm the named test fails. Restore afterwards.
D. Gates. For each sprint-plan gate G-W2-A ... G-W6-A, map every check to evidence. Mark each:
   VERIFIED / PARTIAL / NOT_DONE / CANNOT_VERIFY.

Output: one completion matrix (item or gate check x status x evidence path x note), then a list of
discrepancies by severity. Items listed in the guide's section 1.3 as "known not done" are NOT
omissions: record them as NOT_DONE with that reason. Do not edit any file.
```

### 1.3 已知未完成：让评估者知道这些不是遗漏

| 项 | 状态 | 原因 |
|---|---|---|
| E2 / E5 runner（权重与构造配对、反事实） | NOT_DONE | D06 已于 2026-10-23 由用户决定（见 `08_OPEN_DECISIONS_FOR_SUPERVISOR.md` 末尾的决定记录），runner 尚未实现 |
| E3 / E4 的完整 runner | PARTIAL | E3 已有 3×3 新鲜度网格测试；E4 已有 PERF-01 / PERF-02 / ST-LONG-01 / R10 FSM 测试；单独的 runner 与报告表格未做 |
| E1（模型鲁棒性）与概率可靠性诊断 | ML 轨道 | Codex 负责 |
| Task 10A 的 provider 改造与离线评估器 | NOT_DONE（W6 拓展项） | schema 已交接；待候选模型包，以及「符号链接 containment」的决定 |
| R14：DominantEvidence 是否考虑权重 | 等你决定 | 涉及三份实现与夹具 |
| UAT | NOT_DONE | 需要真实参与者，由你主导 |
| Constructed scenario 回放模式 | 进行中 | 在 `fyp2/constructed-scenario` 分支开发，合并前有独立的门禁；**它的运行结果不作为报告结果** |
| 真实摄像头 / 目标硬件上的性能 | NOT_DONE | 只测了一台开发机加假摄像头 |

---

## 2. 撰写报告：System Development（第 5 章）与 Evaluation（第 6 章）

### 2.1 章节与证据的对应（更新 `05_RUBRIC_TRACEABILITY_AND_REPORT_MAP.md`）

**第 5 章 System Development**

| 小节 | 写什么 | 证据 |
|---|---|---|
| 5.1 环境与可复现 | 锁定版本的依赖；一条命令从全新克隆到全绿门禁并启动服务；模型产物用哈希冻结 | `README.md`「Clean start」；`backend/requirements.lock.txt`；`docs/evidence/2026-10-22/coldstart/`；各 gate 的 `freeze_manifest.txt` |
| 5.4 推理、融合与时间逻辑 | 后期融合；不可用时可空的契约（D01：无证据时为 `null` / UNAVAILABLE，不是 0）；过期证据按缺失计分（裁定 A）；R10 观测身份与双条件告警 FSM；NEW-only EMA | Task 2–6 验收、`p0-d13-ruling-a-acceptance.zh.md`、`r10a-backend-acceptance.zh.md`、`r10b-frontend-acceptance.zh.md`；代码在 `backend/app/fusion.py`、`inference.py` |
| 5.5 API、前端与故障处理 | 故障记录表；有界重试（3 次投递、冻结 payload、手动 Retry）；Live-only 范围；「后端不可达」与服务端错误的区分；解释卡片的 TreeSHAP 贡献 | `task-07`、`task-08`、`task-09`、`fix-backend-reach`、`telemetry-contributions` 的验收报告 |
| 5.6 会话、持久化与导出 | 会话生命周期；选中窗口跟随最新；全量导出（超过页面保留的 500 个窗口） | `w5-system-tests-acceptance.zh.md`（ST-SESSION-01、S1）、`task-10-part2a-acceptance.zh.md` |
| 5.x 模型集成与版本 | 候选模型包的 manifest 契约（预处理、类别顺序、logits、哈希、路径不能逃出包），为模型替换做准备 | `docs/fyp2/handoff/task-10a-runtime-manifest.md` |

**第 6 章 Evaluation**

| 小节 | 写什么 | 证据 |
|---|---|---|
| 6.1 设置 | 机器（Apple M2，8 核，24 GB）、Chromium 148、Python 3.13.3；冻结模型哈希 b3a42e8d / 196ca7b1 / 9802cb06；门禁脚本；假摄像头 | `perf01.json` 中的 `machine`；`freeze_manifest.txt`；`scripts/run_gates.py` |
| 6.5 E3（缺失与过期） | 3×3 新鲜度网格：expired 的分数与 missing 完全相同，原因写在 provenance；两路都没有证据时为 UNAVAILABLE；零权重的单分支 | `w5-system-tests-acceptance.zh.md`（S10）；P0-D13 的 IT-EXPIRY 测试；`task-10-part2b-acceptance.zh.md`（ST-BRANCH-*） |
| 6.6 E4（运行时鲁棒性） | 延迟（capture → render p95）；日志完整性（两个分母，注入故障）；长会话；告警 FSM 的 2 s / 10 s 双条件；故障恢复 | `w6-system-tests-acceptance.zh.md`；`perf01.json`；`perf02.json`；`long-session.json`；R10-A 验收 |
| 6.8 软件测试 | 测试分层（单元 / 集成 / 系统 / 浏览器端到端）；每周 gate 的测试数；**变异测试**作为「测试会抓到错误」的证据；系统测试清单 | 第 2.2 节的数字表；各验收报告第 3 节 |
| 发现：视觉 domain shift | 同一条实时管线在 State Farm test 集上准确率 0.898、c0 召回 0.921；正面摄像头约 5,170 帧几乎全判为 c8 / c9。结论是视角问题，不是程序缺陷 | `docs/evidence/2026-10-22/vision-runtime-path/README.md` |
| 6.4 / 6.7 E2 / E5 | 按 D06 决定写：人工配对的样本称为「constructed evaluation scenarios」，预先声明 operational reference policy，报告互补性与衰减；限制（没有同时采集的多模态数据、配对是构造的）写进报告。runner 未完成前，写成「已设计、未执行」 | 覆盖矩阵；`08_OPEN_DECISIONS_FOR_SUPERVISOR.md` 末尾的 D06 决定记录 |
| 6.9 UAT | 未完成，不编造人数 | — |

### 2.2 关键数字（引用时注明出处文件）

| 数字 | 值 | 出处 |
|---|---|---|
| G-W5-A 门禁 | pytest 1021 passed / 0 skipped；vitest 922；tsc 0；eslint 0；build 通过 | `docs/evidence/2026-10-22/w5-gate/SUMMARY.md` |
| 最终代码的全量门禁（全新克隆） | pytest 1028 passed / 0 skipped；vitest 922；启动服务检查通过 | `docs/evidence/2026-10-22/coldstart-final/SUMMARY.md` |
| 界面审查与 Minor 修复后的全量门禁 | pytest 1046 passed / 0 skipped；vitest 954；tsc 0；eslint 0；build 通过 | `docs/evidence/2026-10-23/ui-minors-gate/SUMMARY.md` |
| 冷启动（全新克隆） | 依赖安装 82 s，门禁 268 s；pytest 987 / 0 skipped；服务健康检查 200 | `docs/evidence/2026-10-22/coldstart/SUMMARY.md` |
| capture → render 延迟 | p50 28 ms，**p95 39 ms**，最大 280 ms（600 窗口，9.8 Hz） | `docs/evidence/2026-10-22/perf/perf01.json` |
| 服务端分段（中位数） | 总计 16.7 ms；视觉 8.6 ms；预处理 2.6 ms；遥测 1.1 ms；提交 0.9 ms | 同上 |
| 新鲜度敏感性 | 阈值 2 s 时 0.89% 的遥测窗口过期（560 个中有 5 个）；3 s 和 5 s 时为 0%。遥测年龄 0–2 s 是回放分段造成的，不是传感器年龄 | 同上 |
| 日志完整性 | D1 211/211、D2 211/211（100%），注入了丢包、后端重启和 422 | `docs/evidence/2026-10-22/perf/perf02.json` |
| 长会话 | 15 分钟，8,867 个窗口（9.85 Hz），全部完整存储和导出；JS 堆（CDP 读数）在 16.4–29.1 MB 之间波动、没有上升趋势；DOM 节点数没有增长 | `docs/evidence/2026-10-22/perf/long-session/long-session.json` |
| 视觉管线的一致性 | test 集 3,657 张：直接 ONNX、Runtime Provider、HTTP 三条路径的预测逐张相同；准确率 0.8988；c0 召回 0.921 | `docs/evidence/2026-10-22/vision-runtime-path/README.md` |
| 正面摄像头的塌缩 | 约 5,170 帧中 `safe_driving` 只出现 5 次；P_distraction 中位数 1.000 | 同上 |

### 2.3 措辞规则（viva-safe）

**更新**：项目自带 `report-writer` agent 里的几条规则已经过时，以下面这些为准。

1. **告警 FSM**：Live 模式的告警 FSM **在后端实现**（`inference.py`），采用 R10 双条件：服务端时间与新观测的来源跨度都达到 2 s 才升级、都达到 10 s 才恢复。旧的 legacy replay 才在 TypeScript 编排层。
2. **模型状态**：模型**已经训练并接入 Live**（MobileNetV3 ONNX 和 XGBoost）。不要再写「designed for FYP2」。但正面摄像头上的视觉准确率**没有**建立，只能写 domain shift 限制。
3. **数据规模与范围**：所有性能数字是「一台开发机、Chromium 假摄像头、冻结模型」下的结果，不代表车载或目标硬件。
4. **新鲜度阈值**：`freshness_tolerance_s = 3 s` 是可配置的**设计阈值**，不是经过验证的安全阈值。
5. **特征贡献**：TreeSHAP 贡献是**局部归因**，作用于 Safe 类打分（取负号，正号推向不安全），单位为 log-odds；**不代表因果**，也不是数据集层面的特征重要性。
6. **构造场景**：Constructed scenario 是演示手段，**不是**实时监测，也**不是**风险准确率的证据。报告里引用的结果只用 Live 的。
7. **风险等级**：RiskScore 是 0–100；RiskLevel 是推导出的运行等级，不是有监督的事故严重度；融合权重是透明、可调的设计参数。
8. **测试数字**：只引用证据目录里的日志，不要从记忆或旧文档里取数。

### 2.4 可以直接粘贴给写报告 agent 的 prompt

```text
You are writing two chapters of an FYP report: "System Development" (Chapter 5) and "Evaluation"
(Chapter 6) for the In-Cabin Multi-Modal Driver Risk Assessment system. Work in /Users/liu/Desktop/FYP2-Live-System
(branch fyp2/live-system, commit <COMMIT>). Do not change any code.

Read first, in this order:
1. docs/fyp2/SYSTEM_TRACK_HANDOFF_GUIDE.zh.md, section 2 (chapter -> evidence map, numbers table,
   wording rules). These wording rules OVERRIDE older rules elsewhere, including .claude/agents/report-writer.md.
2. docs/fyp2/implementation/README.md (index) and the acceptance reports it lists.
3. docs/fyp2/03_EVALUATION_COVERAGE_MATRIX.md (with its 2026-10-22 addendum) and
   docs/fyp2/08_OPEN_DECISIONS_FOR_SUPERVISOR.md.

Rules:
- Every number must come from a file under docs/evidence/** or an acceptance report. Cite the file next
  to the number, in a comment or footnote.
- Use only Live results. The Constructed-scenario replay is a demo aid, never a result.
- Write planned or undone items (E2/E5 runners, UAT, Task 10A provider, target hardware, real camera)
  as planned, with the reason. Never as done.
- State the frontal-camera domain shift as a measured limitation, with its evidence.
- RiskScore is 0-100; RiskLevel is a derived operational level; the fusion weights are transparent
  design parameters; TreeSHAP contributions are local and not causal; the 3 s freshness tolerance is
  a design threshold, not a validated safety threshold.

Output: a draft of Chapter 5 (5.1-5.6) and Chapter 6 (6.1, 6.4-6.9), with figure and table
placeholders, plus a list of every claim and the file that supports it.
```

---

## 3. 注意事项

- 证据目录里的日志、提交号、数字是**不可变的记录**，不要改。需要更新时，跑一次新的门禁，生成一个新的日期目录。
- 回放分支合并之后，在总索引里给它加一行。它的验收和门禁单独记录，但**不进入报告的结果部分**。
- 引用延迟数字时，统计口径按覆盖矩阵增补节：capture → render 的 **p95**。模型前向耗时和 Server-Timing 各段要分开写。
