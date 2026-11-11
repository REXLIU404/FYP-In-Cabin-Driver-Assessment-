# 阶段 1 · P1-3 TGAP 验收报告（中文）

## 1. 任务概要

- **编号与名称**：P1-3 TGAP —— `telemetry_timestamp` 的对称 HTTP gap 测试（Codex R13）
- **实现了什么**：新增测试 `test_out_of_order_guard_survives_a_gap_for_telemetry`，与已有的 `captured_at` 版逐步对称，共五步：
  1. 只带遥测的请求被接受，telemetry 水位线写入；
  2. 把持久化的 `last_processed_ms` 拨回 60 秒，模拟长时间暂停；
  3. 下一个请求触发 gap，时序状态被清空，并用控制断言确认 `high_since` 被重新锚定；
  4. 水位线**没有**被清掉；
  5. 时间戳更旧的遥测请求被拒，返回 409。
- **为什么必要**：F2 修复之后，只有 `captured_at` 有经 HTTP 的 gap 测试。`telemetry_timestamp` 只受一条静态断言保护，即两组键不相交。只要有人把 telemetry 漏在 `windows.py` 的水位线循环之外，没有任何测试会变红。
- **行为变化**：应用行为**无变化**。只新增一个测试，并修正第 777 行附近一条过期的 docstring（P1-2 遗留）。

## 2. 实现证据

- **Commit**：`d83782d`（本项）、`e9216b7`（控制者记账，见下）
- **文件**：`backend/tests/test_temporal_contract.py`（+77 / −3）、`docs/fyp2/implementation/phase1-03-tgap.md`
- **关键决定**：
  - 复用 P1-2 的 `_RequestDrivenStubProvider`，原 `_StubProvider` 一字未改。
  - 请求不带图像、不带 `captured_at`，第 1 步额外断言 `captured_at` 不在持久化状态中。所以出现 409 或水位线丢失时，只可能是 telemetry 那一条。
  - 控制者记账（`e9216b7`）：
    - 新测试的 docstring 原来说 telemetry 是 'fresh'，评审的探针显示持久化窗口其实是 'stale'。改为如实描述：2025 年的时间戳被管线重判为 stale（R08），单独一路 stale 仍得 High（D13）。
    - `inference.py:37` 的注释改为同时点名两条 gap 测试。只改注释，不改代码。

## 3. 测试结果

| 门禁 | 结果 |
|---|---|
| pytest | **519 passed / 0 failed / 0 skipped**（518 + 1 条新增） |
| vitest | 397 / 0（未改 TS） |
| tsc / eslint | 0 / 0 |

以上是控制者在 `e9216b7` 修正 docstring 后亲自重跑的结果。评审另在 `9945c76` 和 `d83782d` 的隔离副本中核对过：两者恰好相差 +1，就是新测试。

**变异检验**（评审在隔离副本中独立复现）：

| 变异 | 新测试 | `captured_at` 版 |
|---|---|---|
| M1：把 `telemetry_timestamp` 加进 `TEMPORAL_STATE_KEYS` | 第 4 步红 | 绿 |
| **M2：`windows.py` 只守护 `EVIDENCE_WATERMARK_KEYS[:1]`** | **第 1 步红** | **绿** |
| M3（追加）：telemetry 水位线照写，但不再拒绝乱序 | 第 5 步红 | 绿 |
| M4（追加）：测试里不拨回时钟（`-= 0`） | 控制断言红 | 绿 |

M2 是关键：接入真实模型跑全量 519 条，**只有新测试变红**。这说明它是 telemetry 水位线唯一的行为防线，而本项之前这道防线并不存在。

**存在但未执行的测试**：无。

## 4. 问题与风险

- **失败测试**：无。**非预期回归**：无。三个模型 SHA256 未变。
- **与 D13 的耦合（已记入路线图）**：两条 gap 测试的第 1 步都依赖 D13 的现状，即「只有 stale 证据的窗口仍能得到 High」。如果阶段 5 落地证据年龄策略（例如裁定 A：过期按 missing 计分），这两条测试会在第 1 步**响亮失败**，不会悄悄通过。届时要把时间戳改到 fake clock 上，让证据真正 fresh。docstring 已写明这一点。
- **未采纳的可选加强**：第 5 步只断言状态码 409，没有断言 detail 文本。不加的理由有三：与 `captured_at` 版保持对称；本场景不存在其他 409 来源；M3 已经证明这一步能抓到问题。
- **评审无法核实的点**：控制断言「`high_since` 严格变大」依赖真实墙钟单调前进，与 `captured_at` 版相同。时钟回拨的情形没有测试覆盖。
- **评审报告的 commit trailer 疑问**：实现者按分支惯例写的是 `Claude Opus 5.5`，与本会话归属规则一致，无需更改。

## 5. 验收结论

**PASS**

理由：brief 要求全部满足；评审独立复现了必做的 M1、M2 与追加的 M3、M4，全部被杀死。唯一的阻塞性 Minor 只涉及 docstring 措辞，控制者已修正，并重跑四项门禁，结果全绿。

## 6. 下一任务就绪度

- **可以开始 P1-4 IT-EPS**：经 API 测试 near-epsilon 权重（1e-10 / 1e-9 / 1.1e-9，双向），杀死 `inference.py:129` 的 `>` → `>=` 变异。
- **需先处理的事项**：无。另有一项计划修改要先单独提交：另一会话转来的单分支系统测试（Task 8/9/10），只改计划，不实施。
