# 阶段 1 · P1-4 IT-EPS 验收报告（中文）

## 1. 任务概要

- **编号与名称**：P1-4 IT-EPS：经 API 测试 near-epsilon 权重（Codex R05）
- **实现了什么**：在 `backend/tests/test_unavailable_contract.py` 新增 6 个参数化测试，分两组：
  - **刚好在 ε 或以下**：某一路权重取 1e-10 或 1e-9，另一路 missing，经 `/windows` 提交，期望 201 和一条 unavailable 记录；
  - **刚好在 ε 之上**：同样设置，权重取 1.1e-9，期望 201 和一条可用的 DEGRADED 记录。

  每组都测两个镜像方向（vision 取小权重、telemetry 取小权重）。
- **为什么必要**：生产者判定是否可用只靠一行，`inference.py:129` 的 `available = denominator > FUSION_EPSILON`。改动之前，把它改成 `>=` 或 `> 0`，**整个测试集仍然全绿**。一旦这行出错，后果也不是静默的：`assessment_available` 会与 `RiskScore is None` 互相矛盾，schema 的 validator 会让请求变成 500。
- **行为变化**：应用行为**无变化**，只新增测试。

## 2. 实现证据

- **Commit**：`2c07d79`（本项）、`179837e`（控制者记账，见下）。
- **文件**：`backend/tests/test_unavailable_contract.py`、`docs/fyp2/implementation/phase1-04-iteps.md`。
- **关键决定**：
  - 期望值都写成字面量；
  - 测试另外断言 `provenance.fusion_config` 里记录的小权重恰好等于 ε，并从 `/risk/latest` 与 `/windows` 读回结果核对，防止测试空过。
- **控制者记账**：评审发现测试头注释写的区间有误，原文写「(1e-10 .. 1e-9]」。实际上，`> 0` 变异下出问题的区间是 (0, 1e-9]（1e-10 的用例也会变红），`>=` 变异下只有恰好等于 1e-9 时出问题。已改正注释，改后 pytest 525 全绿。

## 3. 测试结果

| 门禁 | 结果 |
|---|---|
| pytest | **525 passed / 0 failed / 0 skipped**（519 + 6）；控制者改注释后重跑，仍为 525 |
| vitest | 397 / 0（未改 TS） |
| tsc / eslint | 0 / 0（评审在 `2c07d79` 上运行） |

**变异检验**：评审在隔离副本里独立复现。「改动前」一栏是旧测试集的对照：

| 变异 | 改动前（旧测试集） | 改动后 |
|---|---|---|
| M1：`>` 改为 `>=` | **全绿**（512 passed / 7 skipped） | 2 红（两个 1e-9 用例） |
| M2：改为 `> 0` | **全绿** | 4 红（1e-10 与 1e-9 用例，两个方向） |
| M5：只在生产者侧改为 `> 1e-8` | **全绿** | 2 红（两个 1.1e-9 用例） |
| M3 / M4：`FUSION_EPSILON` 改为 1e-8 / 1e-10 | — | 各 11 红 |
| M6：`map_system_health` 不传权重 | — | 10 红 |

M1、M2、M5 在改动前都存活，改动后全部被杀。这一行代码从此有了经 API 的防线。

**存在但未执行的测试**：无。

## 4. 问题与风险

- **失败测试**：无。**非预期回归**：无。三个模型的 SHA256 未变。
- **失败的表现形式与 brief 不同**：brief 写的是变异后「返回 500 而不是 201」。实际上 TestClient 默认会把服务端异常直接抛进测试，所以测试看到的是 pydantic `ValidationError`，测试照样变红。评审用 `raise_server_exceptions=False` 另做了验证：同一个请求返回的是 HTTP 500，与 brief 描述的真实服务器行为一致。
- **转入 Task 7**：生产者自相矛盾时，现在只返回一个裸的 "Internal Server Error"，没有分类。Task 7 本来就要加全局异常处理器和 fault 记录，已把它写进 Task 7 的 brief。
- **阶段 5 要复核的点**：1e-9 用例依赖有效分母恰好等于浮点字面量 1e-9，前提是 fresh 的权重为 1.0、另一路为 0.0。阶段 5 按裁定 A 修改 freshness 权重时，需要复核这一点。

## 5. 验收结论

**PASS**

理由：brief 的全部要求都已满足；三个改动前存活的变异，改动后全部被杀；唯一需要处理的 Minor 只是注释措辞，控制者已经修正。

## 6. 下一任务就绪度

- **可以开始 P1-6**：TS 取整违规，即 `asPercent` 和 `preparedSessionInput.ts` 的 `round3`。若回放中任何钉死的值发生变化，立即停下。
- **需先处理的事项**：无。
