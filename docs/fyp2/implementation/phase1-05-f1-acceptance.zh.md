# 阶段 1 · P1-5 F1 验收报告（中文）

## 1. 任务概要

- **编号与名称**：P1-5 F1：修正过期的回放期望矩阵，并让它不能再悄悄过期（Codex R30）
- **实现了什么**：
  - `ai/prototype-data/prepared_sessions/session_001/missing_cases.csv` 共 9 行，全部按真实回放流水线重新核对。错的正是 W16、W17、W19 这三行，已改正。
  - 新增两列：`expected_risk_score`（保留 1 位小数，不可用时为空单元格）和 `expected_assessment_available`（小写 `true` / `false`）。
  - 新增测试 `frontend/src/data/missingCases.test.ts`，读取这份 CSV，逐行和流水线的真实输出比对。
- **为什么必要**：代码注释把这份 CSV 称为「逐窗口期望矩阵」，但没有任何代码读取它，所以它能悄悄过期。Task 2 把「无评估」改成 null，Task 5 改了 EMA 与舍入，它都没有跟着变。W17 甚至还写着「两路都缺失时为 Low / Partial evidence」，这正是本项目要消除的捏造读数。
- **行为变化**：应用行为**无变化**，只改了数据文件和测试。

## 2. 实现证据

- **Commit**：`239f7c2`（本项）、`2529a14`（控制者补测与记账）。
- **改正的三行**：

| 窗口 | 原来写的 | 现在（真实输出） |
|---|---|---|
| W16 Telemetry stale | Medium | **High / 62.5** |
| W17 Both modalities missing | Low / Partial evidence | **空 / UNAVAILABLE / 空 / false** |
| W19 | Combined evidence | **Vision-dominant / 45.0** |

- 只改了 W19 的 `case` 文字（改为 "Both branches active (vision leads)"），因为原名与该行的真实结果矛盾。
- **控制者补测**：评审发现矩阵的输入列（`vision_available`、`telemetry_available`、`telemetry_age_s`）没有和 `telemetry.csv` 核对，仍可能悄悄过期。例如把 W16 的数据年龄从 4 改成 9，它依然是 stale、依然得 62.5，输出列的测试全部照绿。我补了 9 条用例，逐行比对这三列与 `telemetry.csv`。

## 3. 测试结果

| 门禁 | 结果 |
|---|---|
| pytest | 525 / 0（未改 Python） |
| vitest | **427 passed / 0 failed**：基线 405，加本项新增 13 条（4 条格式 + 9 条逐行输出），再加控制者补的 9 条输入列用例 |
| tsc / eslint | 0 / 0 |

**变异检验**：实现者与评审在隔离副本中共做了 25 个变异，全部被杀。主要包括：
- 把 W16、W17、W19 分别改回旧值；
- 删除首行、中间行、末行；
- 分数写成整数格式；
- 布尔值大小写写错；
- 改动回放的 stale 阈值、高风险阈值、分数舍入位数、遥测概率；
- 让「不可用」返回 0 而不是 null。

控制者补测的两个变异：
- 把矩阵 W16 的数据年龄从 4 改成 0；
- 把 `telemetry.csv` 中 W16 的数据年龄从 4 改成 9。

补测之前这两个变异都存活，补测之后都变红（1 failed / 21 passed）。

**存在但未执行的测试**：无。

## 4. 问题与风险

- **失败测试**：无。**非预期回归**：无。
- **与裁定 A 的关系**：W16 依赖现行的 stale 档。评审粗略模拟了裁定 A，只有 W16 的分数从 62.5 变为 60，等级、health、dominant 都没变。阶段 5 实施时这条测试会如实变红，测试文件的注释已写明届时应改 CSV，不得跳过或放宽断言。
- **矩阵里没有 Combined evidence 行**：真实的 Combined 窗口是 W18，不在矩阵里。brief 要求保留原有行，所以没有加。以后要加行时，必须同时修改测试里写死的窗口集合，这是有意设计的。
- **已知假设**：流水线的 `window_id` 等于行号加 1，与 CSV 中的 `window_id` 对得上，前提是 `telemetry.csv` 的 id 是从 1 到 25 连续的。现有测试也依赖这个假设。

## 5. 验收结论

**PASS**

理由：
- brief 的四项要求全部满足；
- 评审独立导出流水线输出，逐行核对 9 行都正确；
- 评审发现的残余缺口（输入列未核对）已由控制者补齐，并做了变异验证。

## 6. 下一任务就绪度

**阶段 1 全部完成**：F4、R08、P1-3、P1-4、P1-6、F1。门禁：pytest 525、vitest 427、tsc 0、eslint 0；三个模型的 SHA256 未变。

- **可以开始 Task 7**（`fault_events`）。brief 已备好，里面对计划中自相矛盾的 4 处做了裁定。我会先把这些更正写进计划，然后派发 Task 7。
- **需先处理的事项**：无。
