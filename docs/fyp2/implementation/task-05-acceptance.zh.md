# Task 5 验收报告（中文）

## 1. 任务概要

- **编号与名称**：Task 5 —— 时序路径：unavailable 期间的 FSM 与 EMA
- **实现了什么**：定义「无评估窗口」在时序层的行为。FSM 计时器**挂起而非冻结**；EMA 在 stale/missing 后重新 seed；三份实现统一 `ROUND_HALF_UP`；修复零权重下 FSM 走错分支的真实 bug。
- **为什么必要**：前四个 task 让数据契约可空了，但时序层仍按旧假设运行。评审此前确认了一个真实缺陷：权重 `1.0/0.0`、vision missing、telemetry fresh 时 score/level 为 `None` 而 health 仍是 `DEGRADED`，控制流落进 **Low 分支**，`low_since` 开始计时，**已激活的 HIGH_ALERT 会在 10 秒后被悄悄降回 NORMAL**。
- **行为变化**：证据中断期间不再累积告警时长；中断结束后计时器从当前时刻重新锚定；跨语言分数现在精确一致。

## 2. 实现证据

- **Commit**：`9befa55`（13 个文件，范围干净 —— 无 `frontend/src/`、无 `schemas.py`、无 `ml/outputs/`）
- **文件**：修改 `backend/app/inference.py`、`fusion.py`、`ai/reference/risk_logic.py`、`ai/src/{alertFsm,riskLogic}.ts`、`ai/fixtures/fusion_vectors.json`；新增 `backend/tests/test_temporal_contract.py`（592 行）、`ai/src/emaParity.test.ts`、`ai/fixtures/ema_parity_vectors.json`
- **关键决定**：
  - **发射值与 FSM 内部记忆分成两个 key**。往 `state['severity']` 写 `None` 会让 `:48` 的 `severity == "HIGH_ALERT"` 锁存静默失效，且任何地方都不报错。内部用 `last_severity`，永不为空。
  - **FSM 挂起条件绑定在 `level is None`**，不是字符串 `health == "UNAVAILABLE"` —— 这正是上面那个 bug 的根因。
  - `unavailable_since` 作为独立挂起标记。不能复用 gap 分支：`last_processed_ms` 对**每个**窗口（含 unavailable）都更新，所以一段 60 秒的无证据窗口在 gap 逻辑看来是「持续处理中」。
  - 新写入的 7 个 state key 全部进 `TEMPORAL_STATE_KEYS`，并有一条测试断言「写入集合 ⊆ 重置元组」（方向正确）。

## 3. 测试结果

| 门禁 | 实现者报告 | 评审独立实测 |
|---|---|---|
| pytest | 504/0 | **504 passed / 0 failed**（基线 367） |
| vitest | 276p/1f | **276 passed / 1 failed**（基线 219/1） |
| tsc | 34 | **34，`ai/` 下 0 条**（基线 35） |
| `test_restart.py` + `test_audit_regressions.py` | 绿，未改期望值 | **13 passed；两个文件根本不在 diff 里** |

**ROUND_HALF_UP 的停止条件未触发** —— 钉死的 `.312` 与 EMA 期望值都原样保留。新 Python 与新 TS 在 1,002,001 格全网格上**零差异**。

**测试不从实现 import 阈值常量**，2000/10000 是字面量（审计 EX-TS-19/21 关闭）。EMA 奇偶校验的 oracle 是独立 JSON，两套测试共读。

**评审做了 6 次变异检验**：

| 变异 | 结果 |
|---|---|
| 往内部 severity 写 `None` | 8 失败 |
| FSM 改回绑 `health == "UNAVAILABLE"` 字符串 | 8 失败 |
| 从 `TEMPORAL_STATE_KEYS` 删 `last_severity` | 3 失败 |
| 挂起改成冻结 | 5 失败 |
| 删掉 resume re-anchor | **仍 504 全绿** ← 见下方 Minor |

## 4. 问题与风险

- **失败测试**：无（唯一那条 vitest 失败是 Task 6 的既有项）。
- **预期的临时兼容性错误**：tsc **34 条，全在 `frontend/`**。注意**少的那一条不是被修好的** —— 见下方 Important 1。
- **Important 1 —— `App.tsx:66` 的潜在契约违规现已「解禁」**：`updateAlertState` 现在接受 `null`，所以 `:62` 不再是类型错误；而 `:66` 仍然把非空 `fsm.severity` 盖到记录上。后果是一条 `RiskLevel: null` 但 `AlertSeverity: "CAUTION"` 的回放记录，破坏四字段同空契约，**而剩下 34 条 tsc 错误没有一条指向它**。这是 Task 6 的债，不是 Task 5 的缺陷。
- **Important 2 —— 回放演示数据变了（评审独立复现）**：25 个窗口里 **11 个**数值不同，RiskLevel 变动 2 个：
  - **W16 `35.6 Medium` → `62.5 High`**
  - **W18 `47.3 Medium` → `70 High`**（DominantEvidence 由 Telemetry-dominant 变 Combined）
  - W19 DominantEvidence 由 Combined 变 Vision-dominant；W7/W9 为舍入；W20–25 为重新 seed 的位移

  评审判定这是「Python 语义优先」裁定的**正确后果，不是回归**。但量级大且用户可见：**任何引用回放 RiskScore / RiskLevel / DominantEvidence 的报告图表、表格、截图现在都已过期，必须重新生成。**
- **裁定口径更正（必须如实记录）**：`ROUND_HALF_UP` 的影响面**远大于我下裁定时假设的 4%**。评审在 1,001×1,001 网格上独立复现：相对旧 Python 变化 **17.0%**（170,228 格），相对旧 TS **13.0%**（130,174 格），**556 格的 RiskLevel 发生改变**。原因是旧实现按二进制浮点噪声随机进位。裁定维持（两种语言现在精确一致是契约要求），但量级必须说清。
- **审计痕迹缺口**：`ROUND_HALF_UP` 裁定**不在 brief 里**，brief 原文反而说「不要整理 EMA 舍入」。它是我在 Task 3 评审后于派发时下达的 ruling，未同步回写计划，导致评审无法从三份输入验证授权。今后覆盖 brief 的 ruling 必须先写回计划再重生成 brief。
- **遗留 Minor（3 项）**：
  1. `inference.py:14-20` 自称列出「每一个 key」但不完整 —— `windows.py:58` 的 watermark 键故意豁免（正确），但豁免无处声明，且给 Task 7 的指引「任何新 key 都要加进去」对 watermark 类键是错的。
  2. `inference.py:71-72` 的 resume re-anchor 完全冗余且**无测试防守**（删掉仍 504 全绿）；`unavailable_since` 只写不读。
  3. `ai/reference/risk_logic.py` 的 `ema()` 改了代码而 brief 只要求加注释（已声明；该文件是测试 oracle）。
- **brief 前提更正**：`UT-TIME-04` 的前提「旧代码会误升级」**是错的**。旧代码在 `health==UNAVAILABLE` 时强置 `NORMAL`，真实旧缺陷是**立刻丢掉锁存**，比预测的更糟。该测试保留为「挂起 vs 冻结」的守卫。

## 5. 验收结论

**CONDITIONAL PASS**

理由：全部 Step 满足，0 Critical。评审逐条核实了五项最难的保证（内部 severity 不为空、gap-reset key 完整、挂起而非冻结、FSM 绑 `level is None`、停止条件未触发），并做了 6 次变异检验，其中 4 次正确变红。两个 Important 都是**下游债而非本任务缺陷**，已精确移交 Task 6。判 CONDITIONAL 而非 PASS，是因为回放演示数据的用户可见变化 + 报告图表过期这件事必须被显式承担，不能当作无事发生。

## 6. 下一任务就绪度

- **可以开始 Task 6**（前端展示层）—— 这是本批最后一个。
- **已满足的依赖**：时序语义确定；跨语言分数精确一致；`roundHalfUp` 已从 `ai/src` 导出可供 UI 复用。
- **Task 6 必须承担的五项**：
  1. `App.tsx:66` → `AlertSeverity: record.RiskLevel === null ? null : fsm.severity`（**tsc 不会提醒**）
  2. `preparedSessionInput.test.ts:31`（唯一那条 vitest 失败）
  3. 刷新所有引用回放数值的报告图表（W7/9/16/18–25；W16 与 W18 现在是 **High**）
  4. UI 显示舍入一律用 `roundHalfUp`，不要用 `toFixed`
  5. 在 Task 7 新增 state key 之前，声明 `captured_at`/`telemetry_timestamp` 的豁免
