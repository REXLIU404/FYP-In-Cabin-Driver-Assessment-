# Task 4 验收报告（中文）

## 1. 任务概要

- **编号与名称**：Task 4 —— 后端 schema、持久化、迁移与导出
- **实现了什么**：把 Task 2/3 的可用性契约贯通到后端表面。`RiskUpdate` 新增必填 `assessment_available`，四个风险字段改为可空；新增 `assessment_available` 数据库列与**幂等的历史数据回填**；JSON/CSV 导出统一无评估表示；新建仓库里第一个 `conftest.py`。
- **为什么必要**：融合层改完之后，后端仍把这些字段声明为必填 float，于是一个无评估窗口会让 live `/infer` 直接 500。更关键的是**所有读路径都从存储的 JSON blob 重建对象**（`windows.py:19`、`risk.py:24`、`export.py:36`），加一个无默认值的必填字段会让**每一条历史记录读取时 500**。
- **行为变化**：无评估窗口现在能正常落库、查询与导出；历史记录照常可读；CSV 中无评估单元格是**空**而不是 `0`。

## 2. 实现证据

- **Commit**：`64d67b9`（12 个文件，全部在范围内）
- **文件**：修改 `schemas.py`、`db.py`、`models.py`、`routers/{export,risk,status,windows}.py`、`tests/test_live_inference.py`、`tests/test_migration.py`；新增 `tests/conftest.py`、`tests/test_unavailable_contract.py`（429 行）
- **关键决定**：
  - 四个字段写成 **required-but-nullable（无默认值）**。写 `= None` 会重绑定类作用域里的同名 `Literal` 别名，pydantic 随后要求每个值都是 `None`。评审实测：加上 `= None` 后 32 条契约测试里有 9 条立刻变红 —— 这个陷阱**被测试守住**，不是只靠注释。
  - **两道历史数据防线**：`before` validator 推导缺失的 flag 并把捏造的 `0/Low/NORMAL + UNAVAILABLE` 行归一化为全 `None`；`after` validator 强制三元恒等式。
  - 迁移里每个 payload 判定都包在 `CASE WHEN payload IS NOT NULL AND json_valid(payload)` 之后 —— `json_set()` 作用在 NULL 或畸形 JSON 上返回 NULL，会**整行抹掉**。用 `json('true')`/`json('false')` 而非整数 `1`。
  - `_COLUMNS` 用**追加**而非插入；`assessment_available` 绝不放进 `provenance`（行构造器允许 provenance 同名键覆盖顶层值）。

## 3. 测试结果

| 命令 | 结果 |
|---|---|
| `cd backend && PYTHONPATH=. ../.venv/bin/python -m pytest tests -q` | **367 passed / 0 failed / 0 skipped** |
| 既有测试集单独（deselect 45 条新增） | **322 passed**（与 Task 3 评审的反事实预测一致） |
| `npx vitest run --no-cache` | 219 passed / 1 failed（**未变**） |
| `npx tsc --noEmit` | 35 errors（**未变**） |

**新增 45 条**：`test_unavailable_contract.py` 32 条 + `test_migration.py` 13 条。涵盖 UT-FUS-03、UT-FUS-ZERO-WEIGHT（双向 + 真实模型变体）、EX-NULL-01、ST-STATUS-01。真实模型测试**已运行，未跳过**。

**评审自建遗留数据库做破坏性验证**：7 行（含 NULL payload、畸形 JSON、JSON 数组、`{"proof":"keep this"}`），跑**两遍**迁移 —— 第二遍零变化，四种特殊 payload 全部**字节级不变**，`json_type` 确认写入的是 JSON 布尔。

**5 次变异检验**：删 `json_valid` 守卫 → 2 失败；`json('true')`→`1` → 2 失败；禁用 before-validator → 33 失败；触发 pydantic 陷阱 → 9 失败；`_COLUMNS` 改插入 → 1 失败。

**5 种收集顺序**（单文件、新在旧前、全套反序）全部通过，证明新 `conftest.py` 没有引入顺序耦合。

**是否有测试被削弱以求通过**：**没有**。`test_live_inference.py` 的改动是**加强**断言（新增 201、flag、四个 null、恒等式、freshness）；`test_migration.py` 保留原有 proof 断言并新增行数检查。

## 4. 问题与风险

- **失败测试**：无。
- **预期的临时兼容性错误**：`tsc` 仍 35 条、全在 `frontend/`，**无新增**；vitest 那 1 条失败仍是 Task 6 的。Task 4 不引入新的前端问题。
- **非预期回归**：无。三个模型 SHA256 未变；仓库内无任何 `.db`/`.sqlite`/`-wal`/`-shm`，测试全部用一次性 `TMPDIR`。**原始开发数据库未被迁移或写入**（本来就不存在）。
- **遗留 Minor（2 项）**：
  1. `export.py:~49` 的 JSON 分支仍是 `{**rec.payload, …}`，缺 CSV 分支已有的 `or {}` 守卫。评审写入一行 NULL payload 后 `/export?format=json` 抛 TypeError，且发生在 200 已发出之后的流中段。只有手写行才可能 NULL payload，故 Minor。
  2. 迁移对「非 RiskUpdate 形状但 `system_health=UNAVAILABLE`」的 payload 会注入四个 null 键。不现实，且不丢数据。
- **对 Task 5 的风险（评审确认三项，其中第 2 条是已证实的真实 bug）**：
  1. `inference.py` 未显式传 `assessment_available`，当前靠 schema 的 before-validator 兜底。
  2. **零权重 FSM 泄漏**：权重 `1.0/0.0`、vision missing、telemetry fresh 时 score/level 为 `None` 但 health 为 `DEGRADED`，控制流落进 **Low 分支**，`low_since` 开始计时，已激活的 `HIGH_ALERT` 会在 10 秒后降回 `NORMAL`。**Task 5 必须把 FSM 挂起条件绑定在 `level is None` 上，不能绑在字符串 `health == "UNAVAILABLE"` 上。**
  3. `build_explanation` 只有两参，unavailable 文案拿不到成因（cosmetic）。

## 5. 验收结论

**PASS**

理由：全部 Step 满足，0 Critical、0 Important。评审做了本轮最硬的验证 —— 自建遗留数据库跑两遍迁移证明不丢数据、5 次变异检验、5 种收集顺序、独立重跑全部门禁。两个 Minor 都只在手写异常数据下触发。没有任何测试被削弱。pytest 从 321/1 变为 **367/0**，且既有集合单独为 322，与 Task 3 评审的反事实预测精确吻合。

## 6. 下一任务就绪度

- **可以开始 Task 5**（时序路径：FSM / EMA）。
- **已满足的依赖**：schema 可空、历史数据可读、迁移幂等且不丢数据、CSV/JSON 表示已固定（Task 6 的前端半边必须与之精确匹配）。
- **须传递给 Task 5 的四条**：上述三项 carry-forward，外加 Task 3 裁定的 **ROUND_HALF_UP 统一**（含「若 `test_restart.py:44` 钉死的 `.312` 变红必须停下报告」这一约束）。
