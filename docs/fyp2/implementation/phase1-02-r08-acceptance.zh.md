# 阶段 1 · P1-2 R08 验收报告（中文）

## 1. 任务概要

- **编号与名称**：P1-2 R08 更正 ——「Live 到不了 stale」是错的
- **实现了什么**：
  - **文档更正**：在计划第 510 行（Task 5 的 UT-TIME-06 规格）与第 755 行（Task 9 可达性表）删去错误说法，改为正确说法；在 `TASK_1_TO_6_SUMMARY.md` 加勘误节；在 `task-05.md:133` 补一处错误说法。
  - **删除测试**：删除 `test_ut_time_06_source_guard_the_trained_provider_never_emits_stale`。它正是那条错误推理的编码：从「trained.py 源码不含 stale」推出「D13 在 Live 不可达」。
  - **新增测试**：新增 9 个经 `POST /infer` 的 **IT-LIVE-AGE** 用例。
  - **计划文字修正**：把各 task 正文的 `npx` 改为 `./node_modules/.bin/*`；更正 Global Constraints 中「`ai/reference` 零 importer」的说法；「三种语言」改为「两种语言、三份实现」；在 R4 记录中标出 F4 已完成；重新生成 SDD 约束文件。
- **为什么必要**：我在 Task 1–6 期间写下了「Live 永远到不了 stale」，并据此说 D13 不是在役缺陷。Codex R08 判为 INCORRECT，优先级 P0。事实是：后端 `inference.py:107-108` 按 `captured_at` / `telemetry_timestamp` 重新判定新鲜度，网络延迟超过 3 秒、时钟偏差，或任何直接调用 `/infer` 的客户端，都会让 Live 出现 stale。旧的 source guard 测试会持续制造错误的安全感。
- **行为变化**：应用行为**无变化**。变化在两处：文档不再低估 D13；测试从「对源码字符串做静态断言」改为「对完整 pipeline 做可反证的行为断言」。

## 2. 实现证据

- **Commit**：`c7391b5`（本项）；`a078879`（控制者记账：R4 第 1 行标完成，清除 Task 1 与 DoD 表中残留的 `npx`、Task 3 正文中「零 importer」的说法、114-117 行号引用）
- **文件**：`backend/tests/test_temporal_contract.py`、`docs/plans/...completion.md`、`docs/fyp2/implementation/TASK_1_TO_6_SUMMARY.md`、`docs/fyp2/implementation/task-05.md`、`docs/fyp2/implementation/phase1-02-r08.md`
- **关键决定**：
  - 新增 `_RequestDrivenStubProvider`：请求带图像时 vision 为 fresh，带遥测时 telemetry 为 fresh。原 `_StubProvider` 一字未改。下一项（telemetry 对称 gap 测试）直接复用它。
  - **时钟注入**：把 `app.inference` 模块中的 `datetime` 替换为受控子类，`app.schemas` 的真实时钟不动（它负责拒绝超前 5 秒以上的时间戳）。帧时间戳取 2025 年。
  - 每个边界用例使用独立会话，避免乱序 409 与 gap 重置互相干扰。

## 3. 测试结果

| 门禁 | 结果 |
|---|---|
| pytest | **518 passed / 0 failed**（510 − 1 条删除 + 9 条新增） |
| vitest | 397 / 0（未改 TS） |
| tsc / eslint | 0 / 0 |

**9 个 IT-LIVE-AGE 用例**：
- vision、telemetry 各自的 **2999 / 3000 / 3001 ms** 边界，期望依次为 fresh / fresh / stale。
- 30 天旧帧，两路各一例，期望为 stale、DEGRADED、`assessment_available = True`。
- 一个 **D13 行为快照**：连续的 30 天旧帧依次得到 `CAUTION, CAUTION, HIGH_ALERT`。测试名含 `known_limitation`，docstring 写明这不是期望行为。

**变异检验**（评审在隔离副本中独立复现）：

| 变异 | 新测试结果 |
|---|---|
| M-a：`inference.py:107` 不再使用 `captured_at` | 3 红 |
| M-b：`freshness()` 的 `>` 改为 `>=` | 2 红（恰好是两个 3000 ms 用例） |
| M-c：`freshness()` 永不返回 stale | 5 红 |
| M-d：`:108` 不再使用 `telemetry_timestamp` | 3 红 |
| M-swap：两路时间戳互换 | 4 红 |
| **M-maxage：超过 1 天按 missing 处理** | **3 红**（30 天两例 + D13 快照） |

**新旧对照**：在 M-c 下，旧的 source guard 本身**仍为绿**，旧文件中经 `/infer`、不依赖模型的 3 个测试也全部为绿。旧测试里唯一能在 Live 路径抓到 M-c 的一条依赖模型文件，在干净检出上会被 skip。新测试不依赖模型，就能抓到 M-c。

**存在但未执行的测试**：无。

## 4. 问题与风险

- **失败测试**：无。**非预期回归**：无。三个模型 SHA256 未变。
- **我自己 brief 中的前提错误**：brief 写的是「M-c 下旧测试集会全绿」，按字面不成立。实际旧全套在 M-c 下有 8 个失败，它们直接驱动 `freshness()` 或走 `/windows`。成立的是较窄的说法：旧 source guard 本身为绿，旧的、不依赖模型的 `/infer` 测试为绿。实现者和评审都如实指出了这一点。
- **与 D13 裁定的关系**：另一个会话转述，你对 D13 选了裁定 A（过期按 missing 计分，并标记 `expired`），这一点还**待你在本会话确认**。如果确认，阶段 5 实现时，这里的 3001 ms 用例、30 天用例与 D13 快照都要改为期望 `missing`，并断言 `{modality}_expired = true`。**M-maxage 变异会让这 3 个用例变红，正说明它们会在裁定落地时如实报警**。本项建立的时钟注入测试框架，可以直接给阶段 5 使用。
- **遗留**：`backend/tests/test_temporal_contract.py:777` 的 docstring 仍写着「ai/reference/risk_logic.py has no importer」，这句话已过期。已并入下一项（P1-3），因为 P1-3 本就要改这个文件。

## 5. 验收结论

**PASS**

理由：brief 中 A、B、C 三部分全部满足；评审独立复现了必做的 3 个变异与额外的 3 个变异，全部被杀死。这条错误前提现在被一个不依赖模型、可反证的行为测试替代，而那个错误前提曾让我把一个 P0 问题说成非在役缺陷。

## 6. 下一任务就绪度

- **可以开始 P1-3**（telemetry 对称 gap 测试），它直接复用本项的 `_RequestDrivenStubProvider`。
- **需先处理的事项**：无。
