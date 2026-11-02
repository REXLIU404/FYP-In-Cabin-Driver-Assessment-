# 阶段 1 · P1-6 TS 取整验收报告（中文）

## 1. 任务概要

- **编号与名称**：P1-6，TS 取整违规（F4 评审新增，排在 F1 之前）。
- **实现了什么**：
  - `ai/src/riskLogic.ts` 的 `asPercent` 生成解释文本里的百分比，例如 "P_distraction (57%)"。原来是 `Math.round(v*100)`，现改为：先在小数上 half-up 到 2 位，再放大。
  - `frontend/src/utils/format.ts` 的 `formatPercent` 改为与 `asPercent` 同一种舍入，这样界面显示与解释文本不会出现两种舍入结果。
  - `frontend/src/data/preparedSessionInput.ts` 的 `round3` 原来用 `toFixed(3)`，现改为 `roundHalfUp(…, 3)`。
- **为什么必要**：F4 已把 ROUND_HALF_UP 定为全局规则，但这几处仍用 JS 默认的舍入。默认舍入有两个问题：二进制误差可能越过平局点，`toFixed` 本身也不是 half-up。结果是同一个概率在 Python 端、TS 端、界面与解释文本里，可能显示成不同的数字。
- **行为变化**：
  - **出货回放的数值零变化**（停止条件未触发，见下）。
  - 解释文本只在概率恰好落在平局上时变化，例如 28.5% 原显示为 28%，现显示为 29%。

## 2. 实现证据

- **Commit**：`b53f007`（本项）、`1849505`（控制者记账，见下）。
- **文件**：
  - 代码：`ai/src/riskLogic.ts`、`frontend/src/utils/format.ts`、`frontend/src/data/preparedSessionInput.ts`
  - 测试：`riskLogic.test.ts`、`format.test.ts`、`preparedSessionInput.test.ts`
  - 报告：`docs/fyp2/implementation/phase1-06-tsround.md`
- **关键决定**：导出 `buildPreparedWindows(csv)`，这就是 brief 要求的「回放公开解析路径」。新测试用它喂入一份 4 位小数的 CSV，`p_safe` 取 0.0635、0.3135、0.9385、0.4895，期望值另用 Python `Decimal` 独立核算。
- **控制者记账**：实现者报告的第 7.3 节称 `trendSeries.ts` 的 `* 100` 不产生文本，这是错的，已更正。实际上它会经趋势图 tooltip 渲染成文本。

## 3. 测试结果

| 门禁 | 结果 |
|---|---|
| pytest | 525 / 0（未改 Python） |
| vitest | **405 passed / 0 failed**（397 + 8 条新增；没有修改或删除任何既有测试） |
| tsc / eslint | 0 / 0 |

**停止条件核对**：分别从改动前和改动后的副本导出全部 25 个回放窗口，以及 25 条 `buildRiskUpdate` 记录（含解释文本）。两份 JSON 的 **SHA-256 完全相同**。`preparedSessionInput.test.ts` 原有的 8 个用例一字未改。

原因很简单：出货 CSV 的 `p_safe` 只有 2 位小数。按 2、3、4 位小数穷举，`toFixed(3)` 与 half-up 的分歧数分别为 0、0、286 个。所以这次修正不改变任何出货数值，只是防止将来出现 4 位小数的平局数据时算错。

**变异检验**（评审在隔离副本中独立复现）：

| 变异 | 结果 |
|---|---|
| `asPercent` 改回 `Math.round(v*100)` | 5 红 |
| `asPercent` 去掉「先在小数上舍入」这一步 | 5 红 |
| `formatPercent` 改用自写的 `Math.round` | 2 红 |
| `round3` 改回 `toFixed(3)` | 1 红 |
| `round3` 改成 `Math.round(v*1000)/1000` | 1 红（靠新增的 0.4895 这一行抓到） |
| 四个解释文本调用点逐一改回 | 每个 2 红 |

**存在但未执行的测试**：无。

## 4. 问题与风险

- **失败测试**：无。**非预期回归**：无。
- **遗留（已列入路线图阶段 3，在 Task 9 修）**：趋势图 tooltip 先把概率乘 100，再保留 1 位小数，同样会让二进制误差越过平局。评审实测，概率 0.2855 显示为 "28.5%"，按十进制 half-up 应为 28.6%。只有小数位 ≥ 4 且恰好落在平局上的概率才会触发，也就是 Live 模式的模型原始精度值；出货回放不受影响。
- **无法测试的一处（不加测试）**：视觉分支的 `inferDistraction` 调用点即使单独改回旧写法，也没有测试会变红。原因是视觉 safe 概率表的值都是 2 位小数，`1 − x` 在 3 位上永远不会出现平局。按当前数据，这条回退不可能发生。
- **已存记录**：本项之前保存的解释文本保留旧字符串，不做迁移。
- **规则范围外的舍入**：以下几处 `toFixed` / `Math.round` 不在「score、概率、EMA」范围内，本项未改：证据差阈值、原始传感量、FPS 与延迟显示。

## 5. 验收结论

**PASS**

理由：brief 要求全部满足；停止条件经逐字节核对未触发；全部变异都被杀；唯一需要处理的 Minor 只是报告措辞，已更正。

## 6. 下一任务就绪度

- **可以开始 P1-5 F1**：修正 `missing_cases.csv` 的 9 行期望值，并加一个测试读取它逐行比对。本项已确认回放数值稳定，F1 可以放心把它们钉进 CSV。
- **需先处理的事项**：无。
