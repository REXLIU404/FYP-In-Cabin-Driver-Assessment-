# Task 3 验收报告（中文）

## 1. 任务概要

- **编号与名称**：Task 3 —— Python 侧契约同步（两份移植）
- **实现了什么**：把 `backend/app/fusion.py` 与 `ai/reference/risk_logic.py` 两份 Python 移植同步到 Task 2 已冻结的 TypeScript 契约；新增 `backend/tests/test_fusion_vectors.py`，读**与 TS 测试同一个** `ai/fixtures/fusion_vectors.json` 作为跨语言 oracle。
- **为什么必要**：项目有三份融合实现。`fusion.py` 是后端运行时真正用的，`ai/reference/risk_logic.py` 被文档声明为「语言无关规范」却**零 importer、零测试覆盖**——不同步它，报告里的公式叙述就会和实现分叉且无人察觉。
- **行为变化**：后端融合现在与前端契约一致：无评估返回 `None` 而非 `0.0`；`SystemHealth` 由有效分母判定；`determine_dominant_evidence` 对无评估窗口返回 `None` 而不再编造 `"Partial evidence"`；`build_explanation` 不再对无评估窗口输出「低于低风险阈值」这句捏造文案。

## 2. 实现证据

- **Commit**：`6faed56`
- **文件**：修改 `backend/app/fusion.py`、`ai/reference/risk_logic.py`；新增 `backend/tests/test_fusion_vectors.py`（284 行）
- **关键决定**：
  - `determine_dominant_evidence` 的 `None` 返回放在**第一个**分支（`fusion.py:119`）。原先 `if system_health != "FULL": return "Partial evidence"` 恰好挡住了对 `None` 的数值比较，所以这个 bug **不会崩**，只会安静地给无证据窗口编一个非空标签。
  - `build_explanation` 加前置 unavailable 分支，且文案不含任何 level 词。旧的兜底句会写进 Explanation 视图和 CSV 的 `explanation` 列 —— 等于 B01 换成英文句子继续存活。
  - `map_alert_severity` 保留但加 `None` 守卫与「NOT CALLED ANYWHERE - DO NOT WIRE THIS UP」docstring，并加了静态扫描测试守卫它不被接线（它绕过 2 秒 sustain）。
  - pytest **自带 epsilon 边界用例**（夹具没有这类行）：分母 `1e-10`、`1e-9` → unavailable，`1.1e-9` → available，另有 `9.9e-10` 与 `1.035e-9` 两个 stale 情形。

## 3. 测试结果

| 命令 | 结果 |
|---|---|
| `cd backend && PYTHONPATH=. ../.venv/bin/python -m pytest tests -q` | **321 passed / 1 failed** |
| 其中新增 `test_fusion_vectors.py` | **294 passed / 0 failed** |
| `npx vitest run --no-cache` | 219 passed / 1 failed（**与 Task 2 基线一致，无漂移**） |
| `npx tsc --noEmit` | 35 errors，全部在 `frontend/`（**与基线一致**） |

**评审独立做了 7 次变异检验**，每次 revert 后回到 294 passed：

| 变异 | 失败数 |
|---|---|
| `<= FUSION_EPSILON` 换成 `== 0` | 15 |
| `None` 返回移到 `!= "FULL"` 分支之后 | 10 |
| 禁用 `build_explanation` 的 unavailable 分支 | 5 |
| reference 实现丢掉 `map_system_health` 的权重 | 2（F-Z1、F-Z2） |
| 删掉 `compute_risk_score` 的 round | 8（含 F-T5） |
| 把 `map_alert_severity` 接进 `inference.py` | 1 |

**存在但未执行**：无。**无法复核**：实现者声称的红相（190 failed）只有一个 commit，无法重新观察；变异检验是替代证据。

## 4. 问题与风险

- **失败测试（1 个，诊断已被独立证实）**：`test_live_inference.py::test_missing_expired_and_out_of_order_inputs`。融合现在返回 `None`，而未被本任务触碰的 `schemas.py:140-142` 仍把 `RiskScore`/`RiskLevel`/`DominantEvidence` 声明为必填 float → `ValidationError`。
  **评审做了反事实验证**：在 scratch 副本里只把那四个字段改 `Optional` → **322 passed / 0 failed**。证明该失败确实只源于 schema，没有掩盖别的缺陷。**Task 4 负责。**
  **实现者的描述偏窄（已更正）**：触发条件不只是「两路缺失」。权重 `1.0/0.0` 的会话在单路缺失时同样会让 live `/infer` 返回 500，直到 Task 4 落地。
- **预期的临时兼容性错误**：`tsc` 仍是 35 条、全在 `frontend/`，**无新增**。Task 3 不引入新的 TS 问题。
- **非预期回归**：无。范围干净（只有 3 个源文件 + 报告），三个模型 SHA256 未变。
- **重要风险 —— 跨语言舍入漂移（评审推翻了实现者的两项说法）**：
  - Python `round(x, 1)` 是 banker's rounding，TS `toFixed(1)` 半点进位。
  - 分歧率 **4.0%**（1,002,001 网格对中 40,054 个），**不是实现者说的 0.4%**，低报了约 10 倍。
  - 「永不改变 RiskLevel」**为假**：`RuntimeConfig` 允许浮点阈值，`threshold_low=30.3` 时 score 30.25 在 TS 得 `Medium`、Python 得 `Low`（已实测）。
  - 21 行夹具里**没有任何半点行**，所以现有 oracle 检测不到这个分歧。
  - EMA 的 `round(..., 3)` 同样受影响，会波及 Task 5 的 `UT-EMA-PARITY-01`。
  - **已裁定由 Task 5 统一为 ROUND_HALF_UP** 并往夹具加半点行。附加约束：若该改动让 `test_restart.py:44`（钉死 `.312`）或 `test_audit_regressions.py:139` 变红，**Task 5 必须停下报告，不得直接改这两个钉死的期望值**。

## 5. 验收结论

**CONDITIONAL PASS**

理由：全部 Step 满足，评审逐行比对了两份移植、独立重跑全部门禁、并做了 7 次变异检验证明测试有效。无 Critical。唯一 pytest 失败已被反事实实验证明只源于 Task 4 的 schema，且触发面已修正说明。舍入漂移是 Important 级别但**先于本任务存在**、不由 Task 3 引入，已指派 Task 5 并附带防止篡改钉死期望值的约束。

## 6. 下一任务就绪度

- **可以开始 Task 4**（后端 schema / 迁移 / 导出）。
- **已满足的依赖**：两份 Python 移植语义一致；跨语言 oracle 就位（任一侧漂移即红）；epsilon 边界已覆盖。
- **须传递给 Task 4 的三条**：
  1. **pydantic 陷阱**：不要写 `RiskLevel: Optional[RiskLevel] = None` —— 该默认值会重绑定类作用域内的同名 Literal，pydantic 随后会要求每个值都是 None。用无默认值或给 Literal 取别名。
  2. 门禁断言精确基线 **pytest 321/1、vitest 219/1、tsc 35**，不是「green」。
  3. Task 4 改完 schema 后 pytest 应到 **322 passed / 0 failed**（评审已用反事实验证过该数字）。
