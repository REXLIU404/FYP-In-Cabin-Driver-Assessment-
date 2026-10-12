# Task 1–6 实施总结与验收汇总

> 分支 `fyp2/live-system`，工作树 `/Users/liu/Desktop/FYP2-Live-System`，起点 `dev_cc@845b43a`，终点 `1edb923`。
> 2026-10-12。本文件**不**宣告系统完成 —— Task 7–10 仍未开始。

## 状态词汇

本文严格区分五种状态，不混用：

| 状态 | 含义 |
|---|---|
| **IMPLEMENTED** | 代码已写入并提交 |
| **TESTED** | 存在自动化测试且本轮实测通过 |
| **VERIFIED** | 经独立评审 agent 复核，且至少一次变异检验证明测试能抓住该缺陷 |
| **BLOCKED** | 无法安全继续 |
| **NOT COMPLETED** | 不在本批范围或未做 |

「实现完成」不等于「测试通过」，「测试通过」不等于「已验证」。

---

## 1. 总体实施概要

本批修复了审计列出的两个 P0 数据契约缺陷，并把修复贯通到全部五个实现层。

**B01**：两路证据都缺失时，系统原本返回 `RiskScore 0 / RiskLevel Low / AlertSeverity NORMAL`，即**把「没有评估」伪装成「低风险」**，这个捏造值会进入 API、数据库与导出。

**B02**：权重 `(1.0, 0.0)` 且 vision 缺失时，有效融合分母为 0，系统却报 `DEGRADED` 与 score 0。

修复后的契约：

```
assessment_available === (RiskScore !== null) === (SystemHealth !== "UNAVAILABLE")
不可用时：RiskScore、RiskLevel、DominantEvidence、AlertSeverity 四者同时为 null
可用时：  四者同时非 null
SystemHealth：有效分母 <= 1e-9 → UNAVAILABLE；否则任一分支非 fresh → DEGRADED；否则 FULL
```

该契约现在在五个位置**一致成立**，经跨任务复审确认：`ai/src/`（TypeScript，权威）、`backend/app/fusion.py`、`ai/reference/risk_logic.py`、`backend/app/inference.py` + `schemas.py`（生产者与校验器）、`frontend/src/`。

另外修复了一个审计未列出、由评审在实施中**发现并确认**的真实 bug：权重 `1.0/0.0` 且 vision 缺失时，score 与 level 为 `null` 但 health 仍是 `DEGRADED`，控制流落进 Alert FSM 的 **Low 分支**，导致**已激活的 HIGH_ALERT 在 10 秒后被悄悄降回 NORMAL**。

## 2. 任务状态表

| Task | 名称 | 验收 | IMPLEMENTED | TESTED | VERIFIED | 修复轮 |
|---|---|---|:-:|:-:|:-:|:-:|
| 1 | 冻结基线、清理 AGENTS.md 引用、lint 范围 | **PASS** | ✅ | ✅ | ✅ | 0 |
| 2 | `ai/src` 可空契约与分母驱动 health | **CONDITIONAL PASS** | ✅ | ✅ | ✅ | 0 |
| 3 | Python 两份移植同步与跨语言 oracle | **CONDITIONAL PASS** | ✅ | ✅ | ✅ | 0 |
| 4 | 后端 schema、持久化、迁移与导出 | **PASS** | ✅ | ✅ | ✅ | 0 |
| 5 | 时序路径：FSM 挂起、EMA 对齐、舍入统一 | **CONDITIONAL PASS** | ✅ | ✅ | ✅ | 0 |
| 6 | 前端渲染 canonical 记录 | **CONDITIONAL PASS** | ✅ | ✅ | ⚠️ 仅纯函数层 | 1 |

**各 CONDITIONAL PASS 的条件**：

- **Task 2**：交付时仓库处于「1 个测试红 + 35 条 tsc 错误」状态，均为契约变更的预期后果，归 Task 6 处理。**已在 Task 6 清零。**
- **Task 3**：遗留一条 pytest 失败归 Task 4 的 schema；评审用反事实实验证明它只源于 schema。**已在 Task 4 消除。**
- **Task 5**：回放演示数据发生用户可见的变化，引用这些数值的报告图表已过期。**仍未处理**，见第 6 节 F1。
- **Task 6**：前端只被证明到纯函数层，**不是 UI 层**。没有 DOM 测试，Live 模式未对真实后端运行。**仍未处理**，属 Task 10 范围。

## 3. Git 提交

全部为本地提交，**均未 push**，`dev_cc` 未被修改或合并。

| Commit | 说明 | 规模 |
|---|---|---|
| `6553a46` | Task 1：冻结基线、删除 AGENTS.md、修正 lint 范围 | 10 文件，+1921 / −4 |
| `b6cbf01` | Task 2：可空契约与分母驱动的可用性 | 9 文件，+1515 / −42 |
| `6faed56` | Task 3：两份 Python 移植同步 | 4 文件，+631 / −36 |
| `64d67b9` | Task 4：契约贯通 schema、持久化与导出 | 12 文件，+987 / −18 |
| `9befa55` | Task 5：FSM 挂起、EMA 对齐、舍入统一 | 13 文件，+1845 / −68 |
| `8236244` | Task 6：渲染 canonical 记录 | 37 文件，+2513 / −293 |
| `1edb923` | Task 6 修复轮 1：为两处可用性守卫补测试 | 2 文件，+121 |

**合计 77 个文件，+9520 / −448。**

`64d67b9` 由控制者代为提交：实现 agent 完成全部工作与报告后被 API 速率限制终止，未能提交。commit message 中已注明。

## 4. 变更文件清单

| 区域 | 新增 | 修改 | 删除 |
|---|:-:|:-:|:-:|
| `ai/src/` | 4 | 6 | — |
| `ai/fixtures/` | 2 | — | — |
| `ai/reference/` | — | 1 | — |
| `backend/app/` | — | 9 | — |
| `backend/tests/` | 4 | 2 | — |
| `backend/requirements*` | 1 | 2 | — |
| `frontend/src/` | 15 | 19 | — |
| `docs/` | 8 | — | — |
| `scripts/` | 1 | — | — |
| 根目录 | — | 2（`CLAUDE.md`、`eslint.config.js`） | 1（`AGENTS.md`） |

**未触碰**：`ml/`（三个模型 checkpoint）、`ai/prototype-data/`（回放源数据）、主仓库 `dev_cc` 工作目录。

## 5. 完整测试结果

### 5.1 最终回归（`1edb923`，本轮实测）

| # | 命令 | 结果 |
|---|---|---|
| 1 | `cd backend && PYTHONPATH=. ../.venv/bin/python -m pytest tests -q -p no:cacheprovider` | **504 passed / 0 failed / 0 skipped** |
| 2 | `./node_modules/.bin/vitest run --no-cache` | **394 passed / 0 failed**（15 文件） |
| 3 | `pytest tests/test_fusion_vectors.py`（跨语言融合契约，Python 侧） | 366 passed |
| 4 | `pytest tests/test_temporal_contract.py`（时序 / EMA 契约） | 65 passed |
| 5 | `pytest test_api.py test_migration.py test_restart.py test_unavailable_contract.py`（API、SQLite、导出） | 48 passed |
| 6 | `./node_modules/.bin/tsc --noEmit` | **exit 0，0 errors** |
| 7 | `./node_modules/.bin/vite build` | ✓ built |
| 8 | `./node_modules/.bin/eslint .` | **exit 0** |
| 9 | 三个模型 SHA256 | **与 Task 1 基线逐字节一致** |

pytest 必须先 `export TMPDIR=$(mktemp -d)`：`backend/tests/test_api.py` 在收集阶段会销毁一个固定路径的临时数据库。本机 `npx` 被 `rtk` 包装器改写，故直接调用 `./node_modules/.bin/*`。

### 5.2 门禁数字演进

每一次跳变都在对应任务报告中逐项说明，跨任务复审确认**无未解释的跳变**。

| 时点 | pytest | vitest | tsc |
|---|---|---|---|
| 基线 `845b43a` | 28 / 0 | 32 / 0 | 0 |
| Task 1 后 | 28 / 0 | 32 / 0 | 0 |
| Task 2 后 | 28 / 0 | 219 / **1** | **35** |
| Task 3 后 | 321 / **1** | 219 / 1 | 35 |
| Task 4 后 | 367 / 0 | 219 / 1 | 35 |
| Task 5 后 | 504 / 0 | 276 / 1 | 34 |
| Task 6 后 | 504 / 0 | 390 / 0 | 0 |
| Task 6 修复后 | **504 / 0** | **394 / 0** | **0** |

Task 5 的 tsc 从 35 降到 34 **不是修好了一个错误**：`updateAlertState` 改为接受 `null`，使 `App.tsx:62` 不再报错，同时**解禁**了 `App.tsx:66` 的一个潜在契约违规。Task 6 已修复该处。

### 5.3 独立验证的强度

每个 task 都由一个独立评审 agent 复核：复跑全部门禁、逐 Step 核对规格，并做变异检验 —— 故意破坏实现，确认测试会变红，再还原。本批共计约 **40 次变异检验**。

最有说服力的几次：

- **Task 2**：删掉 `evidence.ts` 的 null 守卫 → 17 条测试失败，失败断言正是 `expected 'Low observed risk' to be null`，证明 JavaScript 中 `null < 30 === true` 这个陷阱被真正守住。
- **Task 4**：评审**自建了一个 7 行的遗留数据库**（含 NULL payload、畸形 JSON、JSON 数组、`{"proof":"keep this"}`），对它跑**两遍**迁移。第二遍零变化，四种特殊 payload 全部**字节级不变**。
- **Task 5**：评审确认两个钉死的期望值文件**根本不在 diff 里** —— `ROUND_HALF_UP` 的停止条件未被绕过。
- **Task 6**：五个静默失败点由评审**从当前源码重新推导**，而不是采信实现者的转述。

**变异检验并非证明了每一道防线。** 跨任务复审中有 **3 个变异在完整套件下存活**：`inference.py:119` 的 `>` 改为 `>=`、改为 `> 0`，以及把 watermark 键加进 `TEMPORAL_STATE_KEYS`。见第 6 节 F2、F3。

## 6. 未解决问题

来自跨任务一致性复审。该复审只看任务之间的接缝，是单任务评审抓不到的那一类问题。

### Important

**F1 —— 期望回放矩阵已过期。**
`ai/prototype-data/prepared_sessions/session_001/missing_cases.csv` 被 `preparedSessionInput.ts:87` 称为「逐窗口期望风险/证据矩阵」，其 9 行中有 3 行错误：

| 窗口 | 矩阵写的 | 实际值 |
|---|---|---|
| W16 | Medium | **High**（62.5） |
| W17 | Low / Partial evidence | **null / null** |
| W19 | Combined evidence | **Vision-dominant** |

**W17 那一行仍在编码本分支要消除的捏造读数。** 任何展示这份矩阵的人都会与仪表盘矛盾。Task 5 曾移交「刷新所有引用回放的表格」，Task 6 将其声明为超出范围，之后无任务承接。

**F2 —— watermark 豁免未声明（潜伏，会直接坑到 Task 7）。**
`inference.py:14-28` 自称 `TEMPORAL_STATE_KEYS` 包含「EVERY key」，计划与 `task-05.md` 都指示 Task 7「把每个新 state key 加进去」。但 `windows.py:51-58,73` 把 `captured_at` / `telemetry_timestamp` 这两个 watermark 存在同一个 `runtime_state` 里，它们**必须**跨越 gap 保留。

评审在 scratch 副本中把这两个键加进元组：**504/504 仍然全绿**。而此时「暂停超过 3 秒后再送一个比上一帧更旧的帧」会得到 201，真实代码给的是 409。**乱序守卫会被静默杀死，且没有任何测试报警。**

### Minor

- **F3**：`inference.py:119` 的可用性判定（`>`）未被测试钉住；改为 `>=` 或 `> 0` 后后端套件仍全绿。后果是 `1e-10`~`1e-9` 的权重使 `/windows` 返回 500 而非 unavailable 记录 —— 属于**大声**失败，不是静默的。
- **F4**：**`ROUND_HALF_UP` 从未写回计划与 `global-constraints.md`。** 这是控制者的流程失误：该裁定在派发时口头下达，未同步回计划。`task-5-brief.md:42` 甚至仍写着「不要动 EMA 舍入」。由计划生成的 Task 7–10 brief **将不携带舍入模式**。
- **F5**：`riskLogic.ts:201` 用 `Math.round(v*100)`，而 `format.ts:31` 先做 half-up。对 0.285 / 0.565 / 0.145，记录中的 explanation 会写 28% / 56% / 14%，UI 显示 29% / 57% / 15%。当前回放数据未命中这些值。
- **F6**：在中间提交 `9befa55` 跑过回放的开发者浏览器，其 localStorage 中可能留有 `assessment_available:false` 却 `AlertSeverity:"CAUTION"` 的矛盾记录。仅影响跑过该提交的浏览器。

### 各任务延后的 Minor

完整清单在 SDD ledger 的 `Task N: minor (deferred)` 行。值得单独列出的：

- `freeze_manifest.py`：坏的 `FYP_DATA_ROOT` 会静默回退到 sibling 仓库；找不到数据时仍 exit 0。
- `requirements.lock.txt` 是共享 `.venv` 的 143 条全量 pin，真实依赖闭包只有 39 个。若要声称 clean-install 验证，需先改为闭包锁。
- `export.py` 的 JSON 分支缺 CSV 分支已有的 `or {}` 守卫：NULL payload 会在 200 已发出后的流中段抛错。只有手写数据才会触发。
- NaN 绕过：`NaN <= eps` 为 false，NaN 会被判为可用。**该项从未被处理**，只是在当前入口不可达（API 边界的 `Field(ge=0, le=1)` 会拒绝 NaN）。

## 7. 已知限制

以下是**系统性限制**，不是待修的缺陷，必须在报告与答辩中如实陈述。

1. **D13：过期证据可无限累积告警时长。** 对任何提供了时间戳的分支，freshness 判定永远只返回 `stale`、不会变成 `missing`，所以任意旧的证据都会持续以 0.45 权重参与融合并累积 sustained-High，最终触发 `HIGH_ALERT`。`UT-TIME-06` 记录了这个**当前行为**，测试名含 `known_limitation`。**该路径在 Live 主运行时不可达**（`trained.py` 只输出 fresh 或 missing），但可经保留的回放路径或直接 POST `/windows` 触发。**系统尚未实现最大证据年龄。**
2. **Live 主运行时永远到不了 `stale`。** 前端对两路证据都打 `new Date()` 时间戳，且 `trained.py` 只输出 fresh/missing。因此「因过期而 DEGRADED」这条分支在主运行时是死路。
3. **前端未经 UI 层验证。** 没有 DOM 测试；Recharts 的空值渲染是假设；CSS 是 grep 验证；Live 模式未对真实后端运行。
4. **相等时间戳可累积告警时长。** `windows.py:55` 用严格 `<` 做乱序判定，所以重复的同一时刻证据可以通过。`UT-TIME-05` 记录了这个行为。
5. **`ROUND_HALF_UP` 的影响面大于最初估计。** 最初按 4% 估计（旧 Python 与旧 TS 之间的分歧率）。实测相对旧 Python 改变了 **17.0%** 的分数，相对旧 TS 改变了 **13.0%**，**556 个网格点的 RiskLevel 发生改变**。两种语言现在精确一致，这是契约要求；但分数口径变了。

## 8. 兼容性考虑

- **历史数据可读。** 改契约之前落盘的记录（SQLite payload 与浏览器 localStorage）没有 `assessment_available` 键。两层都会在**读取时**归一化：SQLite 侧由 schema 的 `before` validator 加幂等迁移双保险，localStorage 侧由 `normalizeRiskUpdate` 处理。历史上存成 `0 / Low / NORMAL / UNAVAILABLE` 的捏造行会被归一化为全 null。
- **迁移是幂等且不丢数据的**，已对自建遗留数据库跑两遍验证。**但它会改写历史数据**：历史 `UNAVAILABLE` 行中的四个捏造值会被置为 null，这是不可逆的。**本批没有迁移任何真实数据库** —— 仓库中本来就不存在开发数据库。对任何真实数据库执行迁移前，需要先验证备份并取得明确批准。
- **回放演示数值变了。** 25 个窗口中 11 个数值不同，其中 **W16 与 W18 由 Medium 变为 High**。这是「以 Python 语义为准」裁定的正确后果，不是回归；但**任何引用回放分数、等级或证据类型的报告图表、表格、截图都已过期**。
- **两份 CSV 导出是两个不同的制品。** Live 会话走后端 `/export`，回放走前端 `utils/export.ts`，没有任何记录会被两者同时导出，所以可追溯性没有被破坏。它们只在 6 个契约单元格上编码一致；**表头、列集合与列顺序都不同**（前端行 `2,,,,UNAVAILABLE,false`，后端行 28 列）。
- **主仓库 `dev_cc` 仍跟踪 `AGENTS.md`。** 本分支已 `git rm`；主仓库工作区中该文件被删除但未提交。两边需要由你自行对齐。

## 9. Task 7–10 就绪度

**可以开始，但有两项硬前置条件必须先处理。**

| 前置项 | 原因 | 不处理的后果 |
|---|---|---|
| **F2** 声明 watermark 豁免 | Task 7 会新增 state key，现有指引让它把每个 key 都加进 `TEMPORAL_STATE_KEYS` | 乱序守卫被静默杀死，504 个测试照样全绿 |
| **F4** 把 `ROUND_HALF_UP` 写回计划与 `global-constraints.md`，并重新生成 brief | Task 7–10 的 brief 由计划生成 | 后续任务可能重新引入 `round()` / `toFixed`，跨语言分歧回归 |

**已满足的依赖**：

- 数据契约在五层一致（跨任务复审确认）。
- 跨语言 oracle 就位：TS 与 Python 读同一份夹具文件，任一侧漂移即变红。
- 时序语义确定，FSM 挂起与 EMA 重新 seed 均被测试与变异检验覆盖。
- CSV/JSON 的 unavailable 表示已固定。
- 门禁全绿：504 / 394 / 0。

**各任务的准备情况**：

- **Task 7（fault_events）**：可开始。注意 `db.py` 中 Task 4 已划定区块，Task 7 只能在 `additions` 循环**之前**插入独立的 `CREATE TABLE` 块。
- **Task 8（有界重试）**：依赖 Task 7 的错误分类。
- **Task 9（Live-only 范围）**：依赖 Task 6 与 Task 8。
- **Task 10（端到端）**：承担本批所有 UI 层未验证项 —— DOM 渲染、Recharts 空值、CSS 外观、Live 对真实后端。

## 10. 剩余的 Week 7 阻塞项

对照审计 `docs/fyp2/06_WEEK7_CRITICAL_PATH_AND_ACTION_PLAN.md` 的签收清单：

| 签收项 | 状态 |
|---|---|
| 以记录的方式干净启动，记录源码、模型、依赖哈希 | **部分完成**。manifest 与模型哈希已有；锁文件不是依赖闭包 |
| 真实模型推理，类别概率与 raw / post-EMA 可追溯，同一请求到达 UI 与导出 | **NOT COMPLETED**。属 Task 10 |
| 启动、暂停、恢复、重启、会话切换按明确策略保留或重置状态 | **NOT COMPLETED**。属 Task 8、9 |
| 五个视图读正确的已存数据；无评估不是一个安全的数值结果 | **IMPLEMENTED + TESTED**（纯函数层）。**UI 层未验证** |
| 单路/双路缺失、过期、非法输入、模型故障、网络超时、DB 故障都暴露诚实状态并可恢复 | **NOT COMPLETED**。属 Task 7、8 |
| 回归包全绿，被拒绝/错误事件有日志，请求计数可对账 | **部分完成**。回归全绿；错误事件日志属 Task 7 |
| 采集→渲染延迟与日志完整性度量 | **NOT COMPLETED**。本阶段范围外 |

**P0 阻塞项现状**：B01、B02 **已解决并验证**；B03（故障恢复）、B04（可重复端到端）**未开始**；B05（可复现交付）**部分解决**。

---

## 不应对外陈述的说法

跨任务复审明确列出了证据**不支持**的说法。撰写报告或答辩时请避免：

- 前端与后端 CSV「字节一致」或「一致」—— 只有 6 个契约单元格编码一致。
- `ROUND_HALF_UP`「与旧的 `toFixed` 结果相同」—— 它改变了 13%–17% 的分数和 556 个等级。
- 回放期望表或报告图表「是最新的」—— 见 F1。
- 时序 state key 清单「是完整的」—— 见 F2。
- 生产者的 epsilon 边界「已被端到端测试」—— 见 F3。
- NaN 缺口「已由 Task 4 关闭」—— 它从未被处理，只是当前不可达。
- 过期证据（D13）「已被处理」—— 没有。
- 组件渲染「有测试覆盖」—— 只有抽出的纯函数有。
- 变异检验「证明了每一道防线」—— 有 3 个变异存活。
- 系统「已完成」—— Task 7–10 未开始。
