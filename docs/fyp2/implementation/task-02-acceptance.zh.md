# Task 2 验收报告（中文）

## 1. 任务概要

- **编号与名称**：Task 2 —— `ai/src` 契约核心：可空 RiskScore 与分母驱动的 health
- **实现了什么**：新增 `ai/src/availability.ts`（有效分母、可用性判定、三态显示状态、不变式断言）与 21 行跨语言数值夹具 `ai/fixtures/fusion_vectors.json`；把 `RiskScore` / `RiskLevel` / `DominantEvidence` / `AlertSeverity` 改为可空并新增必填 `assessment_available`；`SystemHealth` 改由**有效融合分母**判定而非数 `missing` 标志。
- **为什么必要**：审计的两个 P0。B01：两路证据都缺失时系统返回 `0 / Low / NORMAL`，即**把「无评估」伪装成「低风险」**，API 与导出都带着这个捏造值。B02：权重 `(1,0)` 且 vision 缺失时有效分母为 0，系统却报 `DEGRADED` + score 0。
- **行为变化**：无评估的窗口现在返回 `assessment_available:false` 且四个字段为 `null`，`SystemHealth:UNAVAILABLE`。消费方再也拿不到一个可被误读为「安全」的数字。

## 2. 实现证据

- **Commit**：`b6cbf01`（仅 `ai/`，无 `frontend/`、`backend/`、`ai/reference/`、`ml/` 改动，评审已核实）
- **文件**：新增 `ai/src/availability.ts`、`availability.test.ts`、`fusionVectors.test.ts`、`ai/fixtures/fusion_vectors.json`；修改 `ai/src/types.ts`、`riskLogic.ts`、`evidence.ts`、`riskLogic.test.ts`
- **关键决定**：
  - 用声明的 `FUSION_EPSILON = 1e-9` 判零，不用 `=== 0` —— `RuntimeConfig` 允许权重和偏离 `1e-6`，字面零判定会被绕过。
  - **先 round 到 1 位小数再映射等级**（夹具 F-T5 专门钉死这点）。
  - 可用性守卫必须排在所有关系运算之前 —— JS 里 `null < 30` 为 `true`，顺序错了就会把无证据窗口报成「Low observed risk」。
  - `mapSystemHealth` 的两个权重参数给 `0.5/0.5` 默认值，保证三处既有两参调用继续编译。

## 3. 测试结果

| 命令 | 结果 |
|---|---|
| `npx vitest run --no-cache`（评审独立重跑） | **219 passed / 1 failed**（共 220） |
| 其中 `ai/src` 单独 | **211 passed / 0 failed / 0 skipped** |
| `npx tsc --noEmit` | exit 2，**35 条错误，全部在 `frontend/`**，`ai/` 下 0 条 |
| `npx eslint ai` | exit 0 |

**验证核心需求的用例**：`fusionVectors.test.ts` 逐行断言 21 行夹具（期望值只从 JSON 读，不从实现 import）；`availability.test.ts` 的 UT-AVAIL-01 覆盖 9 种 freshness × 3 组权重共 27 种组合的三元恒等式。

**评审做了 3 次变异检验**（独立于实现者）：删掉 `evidence.ts:34` 的 null 守卫 → 17 个失败，失败断言正是 `expected 'Low observed risk' to be null`（即该陷阱）；把 `<= FUSION_EPSILON` 换成 `=== 0` → 2 个失败；删掉 `round1` → 12 个失败含 F-T5。每次 revert 后回到 211/211。这证明测试能抓真缺陷。

**存在但未执行**：无。**无法复核的一项**：实现者声称的「红相」（先写失败测试）只有一个 commit，评审无法重新观察到红状态；变异检验是其替代证据。

## 4. 问题与风险

- **失败测试（1 个，预期之内）**：`frontend/src/data/preparedSessionInput.test.ts:31`。prepared 窗口 17 两路都缺失，`RiskLevel` 集合合法地多出 `null`，原断言写死 3 元集。该文件在 `frontend/`，Task 2 按范围不得修改，**Task 6 Step 6 负责**。
- **预期的临时兼容性错误（Task 6 必须解决）**：**35 条 `tsc` 错误，全部在 `frontend/`**，完整清单已写入 `task-02.md` 第 7.2 节，这是 Task 6 的工作清单。基线为 0 条。其中 8 条来自 `computeRiskContributions` 零分母改返 `null`，集中在 `ExplanationView`。
- **非预期回归**：无。`ai/` 下 0 条 tsc 错误，无 `any`/`!`/`@ts-ignore` 抑制。
- **对后续任务的风险**：
  1. **测试基线已变**：Task 3/4/5 必须断言「219 passed / 1 failed」这个精确值，不能只看「是否全绿」，否则第二个 frontend 失败会藏在已知失败后面。
  2. **夹具缺 epsilon 边界行** —— 用 `== 0` 的 Python 实现能通过全部 21 行。Task 3 的 pytest 必须自行硬编码 `1e-10` / `1e-9` / `1.1e-9`。
  3. **`alertFsm.ts:59-61` 运行时隐患**：null level 会落进 "Low" 分支并启动恢复计时器，目前只有 `App.tsx:62` 的 tsc 错误挡着。**Task 5 落地前不要构建或运行该前端**。
  4. **NaN 绕过（Minor，先于本任务存在）**：`NaN <= eps` 为 false，NaN 会被判为 available，产出 score=NaN / level=High，序列化后 `RiskScore:null` 但 `assessment_available:true`，不变式破裂。已指派 Task 4 在 schema 边界处理。

## 5. 验收结论

**CONDITIONAL PASS** —— 核心任务通过，下游问题已明确记录。

理由：7 个 Step 全部满足，独立评审重跑了全部门禁并做了 3 次变异检验，无 Critical、无 Important。唯一的测试失败与 35 条 tsc 错误**都是契约变更的预期后果，且都在 Task 6 的职责范围内，已逐条记录**。判定为 CONDITIONAL PASS 而非 PASS，是因为仓库在 Task 2 到 Task 6 之间处于「1 红」状态，这个事实必须显式承担，不能当作已完成。

## 6. 下一任务就绪度

- **可以开始 Task 3**（Python 两份移植同步）。
- **已满足的依赖**：canonical 契约与签名已冻结；21 行夹具 JSON 就位，Task 3 读**同一个文件**作为跨语言 oracle。
- **须传递给 Task 3**：pytest 必须自带 epsilon 边界用例；`determine_dominant_evidence` 的新权重参数改用关键字传参；门禁断言「219/1」而非「green」。
