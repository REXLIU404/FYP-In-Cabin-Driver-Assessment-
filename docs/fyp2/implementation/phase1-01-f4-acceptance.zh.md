# 阶段 1 · P1-1 F4 验收报告（中文）

## 1. 任务概要

- **编号与名称**：P1-1 F4 —— 把 ROUND_HALF_UP 写回计划与 SDD 全局约束
- **实现了什么**：在计划 Global Constraints 中新增舍入规则（ROUND_HALF_UP；score 1 位、EMA 3 位；Python `round_half_up`、TS `roundHalfUp`；禁止在 score / 概率 / EMA 上用内置 `round()`、`toFixed`、`Math.round(v*100)`；这是有意的数值改变），把门禁命令改为 `./node_modules/.bin/*`；从计划逐字重新生成 SDD 的 `global-constraints.md`；给过期的 Task 5 brief 顶部加取代说明。**修复轮**另外为 TS 的 EMA 舍入补了两条夹具用例与一条存在性测试。
- **为什么必要**：ROUND_HALF_UP 是 Task 5 期间口头下达的裁定，从未写回计划。由计划生成的 Task 7–10 brief 将不携带舍入模式，后续实现可能把 `round()` / `toFixed` 重新引入，造成跨语言分歧回归。SDD 的约束文件还是 R1 的旧副本，里面甚至保留着已被 R4 推翻的「Live 到不了 stale」。
- **行为变化**：应用行为**无变化**。约束文档现在与代码一致；TS 侧 EMA 舍入从「无测试守护」变为「有测试守护」。

## 2. 实现证据

- **Commits**：`f289d66`（文档，主实现）、`9632812`（修复轮 1：测试与夹具）
- **文件**：`docs/plans/2026-10-12-fyp2-live-system-completion.md`、`docs/fyp2/implementation/phase1-01-f4.md`、`ai/fixtures/ema_parity_vectors.json`、`ai/src/emaParity.test.ts`。另有两个被 git 忽略的 SDD 文件（`global-constraints.md`、`task-5-brief.md`）已更新但不入库。
- **关键决定**：
  - 「前端显示一律用 `roundHalfUp`」的范围限定为 **score、概率、EMA 值**。FPS、延迟、原始遥测读数不是跨语言契约值，不受此约束（控制者裁定）。
  - SDD `global-constraints.md` 与计划该节**逐字节一致**（cmp identical）。评审做了负对照：在副本中改一个词，比对立即报差异。

## 3. 测试结果

| 门禁 | 结果 |
|---|---|
| pytest | **510 passed / 0 failed**（基线 506，+4） |
| vitest | **397 passed / 0 failed**（基线 394，+3） |
| tsc | 0 errors |
| eslint | 0 |

**数字变化的来源**：夹具新增 2 个 EMA 平局用例。Python 端每个用例对应 2 个参数化测试，所以 +4；TS 端是 2 个 `describe.each` 用例加 1 条存在性测试，所以 +3。文档部分不改代码，主实现提交后四项门禁与基线完全相同。

**核心验证 —— 评审发现了一条没有任何测试守护的规则**：把 TS 的 `round3` 改为 `Number(value.toFixed(3))`，修复前 394 条测试**全部仍然通过**。原因是原有的平局用例 0.0625 在二进制中可以精确表示，`toFixed` 碰到它也会正确进位。在 alpha = 0.35 的 1001×1001 网格上，有 **18,049** 个点会出现分歧，例如 0.0385：half-up 得 0.039，`toFixed` 得 0.038。

**修复后的变异检验**（复审在隔离副本中独立复现）：

| 变异 | 修复前 | 修复后 |
|---|---|---|
| TS `round3` → `toFixed(3)` | 394 全绿 | **2 失败** |
| TS `round3` → `Math.round(v*1000)/1000` | 394 全绿 | **1 失败** |
| TS `round3` → `parseFloat(toFixed(3))` | — | **2 失败** |
| 删除夹具里的两个新用例 | — | **1 失败**（存在性守卫） |
| Python `inference.py:120` → 内置 `round` | — | **3 失败** |
| Python `ai/reference` → 内置 `round` | — | **3 失败** |

期望值由复审用只依赖 `decimal.Decimal` 的脚本独立推导，结果与夹具中的字面量一致。

**存在但未执行的测试**：无。

## 4. 问题与风险

- **失败测试**：无。
- **非预期回归**：无。生产代码未改动；三个模型 SHA256 未变。
- **范围扩大（已记录裁定）**：评审原话称这条 Important「是旧问题，不在 F4 只改文档的范围内，建议单独开一项」。控制者的 workflow 脚本只按严重度判断，因此自动派发了修复。控制者裁定接受这次修复：规则正是 F4 写进计划的，补测试只涉及夹具与测试、不碰生产代码，并且经过定向复审。脚本已改为让评审标注「是否属于本项」，范围外的发现今后交给控制者裁定，不再自动修复。
- **残余的变异缺口（Minor，记录在案）**：复审发现 `Math.round((v + Number.EPSILON) * 1000) / 1000` 和指数字符串技巧这两种写法仍能通过全部测试。这两种写法属于刻意规避，不是常见的回退路径。
- **遗留 Minor，已安排到后续项**：
  - **并入 P1-2（R08）**：计划各 task 正文中仍有旧的 `npx` 门禁命令（Task 2、6、10），其中 Task 10 的 brief 会把它带出去；计划第 59 行称 `ai/reference/risk_logic.py`「零 importer，漂移不会让测试失败」，这已不成立（评审实测改动它会让 25 个 pytest 失败）；「三种语言」的措辞应改为「两种语言、三份实现」；R4 记录中 F4 的状态需要更新。
  - **新增 P1-6**：TS 中仍有两处违反新规则：`ai/src/riskLogic.ts:201` 的 `asPercent` 使用 `Math.round(v*100)`（即 F5），`frontend/src/data/preparedSessionInput.ts:58` 的 `round3` 使用 `toFixed(3)`（评审新发现，作用在回放概率上）。另外 `emaParity.test.ts:25` 的文件头注释仍写「两个平局用例」，实际已有四个。

## 5. 验收结论

**PASS**

理由：F4 的规格全部满足（spec ✅ / quality ✅），文档与代码现在一致。评审额外发现了一条「写进了计划却没有测试守护」的规则，已在一轮修复内补上测试，并经变异检验确认有效。剩余的 Minor 都已分配到具体的后续项，没有遗漏。

## 6. 下一任务就绪度

- **可以开始 P1-2（R08 更正）**。
- **已满足的依赖**：舍入规则已写进计划与 SDD 约束文件，之后生成的 brief 都会带上它；门禁命令已统一。
- **需先处理的事项**：无。R08 的 brief 会追加上述计划文字的修正。
