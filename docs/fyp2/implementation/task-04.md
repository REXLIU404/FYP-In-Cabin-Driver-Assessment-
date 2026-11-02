# Task 4 实现报告 —— 后端 schema、迁移与导出

## 1. Task ID and name

- **Task 4**：后端 schema、迁移与导出 —— 把 Task 2/3 已提交的「可空 + 分母驱动」契约沿 `schemas.py` -> `models.py` -> `db.py` 迁移 -> 路由 -> `export.py` 一路传下去
- 工作树 `/Users/liu/Desktop/FYP2-Live-System`，分支 `fyp2/live-system`，基线 HEAD `6faed56`
- 范围外、零改动：`backend/app/inference.py`（Task 5）、`backend/app/cache.py`（brief 明确「无结构改动」）、`frontend/`、`ai/src/`、`ml/outputs/`、故障事件（Task 7）。

## 2. Implementation status

**DONE_WITH_CONCERNS。** 契约已贯通 schema、持久化、迁移、状态、导出；基线那条失败测试 `test_live_inference.py::test_missing_expired_and_out_of_order_inputs` 现已通过。concerns 全部来自 `inference.py` 仍归 Task 5（第 7 节第 1–3 条），其中第 2 条是一个我在范围内无法修、但会在 Task 5 咬人的潜在缺陷。

| Step | 内容 | 状态 |
|---|---|---|
| 1 | `conftest.py` + tmp_path 作用域 `api` fixture | 完成 |
| 2 | 写失败测试 | 完成 |
| 3 | 确认红 | 完成（25 failed / 21 passed，见第 5 节） |
| 4 | 改 schema（两道防线） | 完成 |
| 5 | 改模型与迁移 | 完成 |
| 6 | 改导出、状态、cache 收紧 | 完成 |
| 7 | 全套 + 类型检查 + 反事实验证 | 完成 |

**关于「322」这个门槛**：控制者给的 322 passed 是**既有测试集**的数字（321 + 修好的那 1 条）。我新增了 45 条测试，所以全量是 **367 passed / 0 failed**。我用排除全部新增测试的方式单独复现了 322（第 5 节命令 6），两个数字都是实测，没有漂移。

## 3. Files created or modified

| 文件 | 动作 | 说明 |
|---|---|---|
| `backend/app/schemas.py` | 修改 | `RiskUpdate`：`assessment_available: bool` 放在 `timestamp` 之后、`P_distraction` 之前；四字段改 `Optional`（**无默认值**，见第 4 节陷阱）；新增 `model_validator(before)` + `model_validator(after)`。`SystemStatusOut` 增 `latest_assessment_available` / `latest_risk_score` / `open_fault_events: int = 0` |
| `backend/app/models.py` | 修改 | 仅加 `assessment_available = Column(Boolean, nullable=False, default=True, server_default="1")`；四个风险列本来就可空，未动 |
| `backend/app/db.py` | 修改 | `additions` 字典加新列；新增 `_backfill_assessment_available()`（带守卫的 payload 回填 + 列修正）。**没有**碰 `additions` 之外的结构，Task 7 的 `CREATE TABLE` 可无冲突地加在循环前 |
| `backend/app/routers/windows.py` | 修改 | 写入 `assessment_available` 列；`delete_window` 的 `cache.clear` 收紧为「只在被删的就是缓存那条时才清」 |
| `backend/app/routers/risk.py` | 修改 | 删无用的 `cache` import；注释 404 与 200+`assessment_available=false` 的语义区别 |
| `backend/app/routers/status.py` | 修改 | 新增三个字段；`latest.payload or {}` / `provenance or {}` 守卫 |
| `backend/app/routers/export.py` | 修改 | `_COLUMNS` **追加** `assessment_available, P_distraction_raw, P_telemetry_raw`；新增 `_csv_cell`；`payload or {}` 守卫 |
| `backend/tests/conftest.py` | 新建 | 强制 `DRA_DATABASE_URL`；`api_factory` + `api` fixture |
| `backend/tests/test_unavailable_contract.py` | 新建 | 32 项 |
| `backend/tests/test_migration.py` | 修改 | legacy fixture 扩为 3 行；新增 4 个测试函数（共 13 项用例） |
| `backend/tests/test_live_inference.py` | 修改 | `:98-100` 的单一 `SystemHealth` 断言换成完整契约断言 |
| `docs/fyp2/implementation/task-04.md` | 新建 | 本报告 |

## 4. Implementation summary

**Pydantic 陷阱（已避开，且有回归测试）。** 四字段写成 `RiskLevel: Optional[RiskLevel]`（**无** `= None`）：必填但可为 null。类体里一旦出现 `RiskLevel = ...` 赋值，类作用域的名字 `RiskLevel`（即模块级 `Literal` 别名）就被改绑，之后 pydantic 对每个值都只接受 `None`。类 docstring 里写明了这一点；`test_available_record_derives_flag_and_keeps_enum_values` 守着它。反事实：加上 `= None` 后 25 条失败。

**两道防线（schemas.py）**

1. `model_validator(mode="before")`：当且仅当 `assessment_available` 键不存在、且 `RiskScore` 与 `SystemHealth` 键都在时，`available = RiskScore is not None and SystemHealth != "UNAVAILABLE"`；若 `not available`，把四字段改写为 `None`、`SystemHealth` 改写为 `"UNAVAILABLE"`。这同时盖住三类输入：
   - 历史行里捏造的 `0 / "Low" / "NORMAL"` + `UNAVAILABLE`；
   - 控制者点名的「零权重」类：`RuntimeConfig` 允许 `(1.0, 0.0)`，此时 `inference.py` 算出 `RiskScore=None`，却仍用默认权重把健康标成 `DEGRADED`、严重度标成 `NORMAL`；
   - `inference.py` 现在对两路 missing 产出的 `AlertSeverity="NORMAL"`。
   键存在时**不做任何改写**，由第 2 道防线严格裁决 —— 所以 Task 5 日后若显式传 `assessment_available` 却自相矛盾，会立刻 `ValidationError`，不会被悄悄修好。
2. `model_validator(mode="after")`：`assessment_available=True` 要求四字段全非 null 且 `SystemHealth != "UNAVAILABLE"`；`False` 要求四字段全 null 且 `SystemHealth == "UNAVAILABLE"`。

**为什么 before 防线是承重的。** `inference.py` 构造 `RiskUpdate` 时**不传** `assessment_available`，全靠 before 防线推导。反事实 M1（禁用推导）使 33 条测试失败，几乎包含全部既有的 `/windows` 用例。这不是缺陷，但意味着 Task 5 之前这个 validator 不能动。

**迁移（db.py）**

- 新列 `assessment_available BOOLEAN NOT NULL DEFAULT 1`（`ALTER TABLE ADD COLUMN` 对常量默认值合法）。
- payload 回填分两步，**顺序强制**：①先处理 `UNAVAILABLE` 行 —— `json_set` 把四个值置 `json('null')`、`assessment_available` 置 `json('false')`，并把列也置 NULL / 0；②再把其余「有 `RiskScore`」的行置 `json('true')`。②若先跑，会把捏造的 `RiskScore=0.0` 判为「有分数」而错标 available（反事实 M7 抓到）。
- **守卫**：每个 payload 谓词都包在 `CASE WHEN payload IS NOT NULL AND json_valid(payload) THEN ... ELSE 0 END` 里。比 brief 里的裸 `AND` 链更严：SQLite 不保证 `AND` 从左到右求值，而 `json_extract` / `json_type` 遇到畸形文本会**抛错**而不是返回 NULL。此外要求 `json_type(payload) = 'object'`，挡住 `'null'`、数组、数字。
- 用 `json('true')` / `json('false')`，不用整数。导出直接 dump 存储的 blob，整数会让迁移行导出 `"assessment_available": 1`、新行导出 `true`。
- 幂等（`_NO_FLAG_YET` 谓词）；二次运行结果逐字节相同（测试断言）。

**导出（export.py）**

- `_COLUMNS` 末尾追加 `assessment_available, P_distraction_raw, P_telemetry_raw`；前 25 列顺序有测试钉死。raw 两列此前只在 `provenance` JSON 里，没有 CSV 列；它们由既有的「provenance 同名键覆盖」机制自动填充，**`assessment_available` 不进 provenance**（测试断言）。
- `_csv_cell`：`None -> ""`，`bool -> "true"/"false"`，其余原样。显式实现，不依赖 `DictWriter` 的隐式行为。防注入守卫在它**之前**执行，且只处理 `str`，空串与 `None` 都不受影响。
- JSON 分支不变（原样 dump payload），靠迁移保证历史行也是 `null` / `false`。

**状态 / cache**：`latest_assessment_available` 读新列，所以 `None`（尚无记录）与 `False`（有记录但无评估）可区分；`delete_window` 对齐 `flag_window` 的写法。

**conftest.py**

- 模块顶部**强制**（非 `setdefault`）`DRA_DATABASE_URL` 指向 `tempfile.mkdtemp()` 下的一次性目录，`atexit` 清理。这样即使某个测试模块在 `test_api.py` 之前 import `app.config`，也只会落到一次性库，不会在 cwd 生成 `./driver_risk.db`，也不会被开发者的 `.env` 劫持。`test_api.py` 自己的赋值照旧生效。
- `api_factory`：tmp_path 内的 engine（与生产同款 `foreign_keys` / `busy_timeout` pragma）、`get_db` override、不进 lifespan。`api`：yield `(client, sid)`，契约与既有 fixture 相同；teardown 清 `cache._latest`（模块全局）并还原 `dependency_overrides`。
- 既有 `test_audit_regressions.py` 的同名 fixture 未动（模块级定义优先于 conftest），见第 7 节。

**测试覆盖（brief 点名项）**：`UT-FUS-03`（回放路径 + 真模型路径 + 读回一致）、`UT-FUS-ZERO-WEIGHT`（回放 `(1.0,0.0)` / `(0.0,1.0)` 两个方向 + 真模型两个方向 + 对照组 `F-Z3` / `0.5/0.5 stale -> 65.2 DEGRADED` / `0.1/0.9 -> 90.0 DEGRADED`）、`EX-NULL-01`（JSON `is None` / `is False`；CSV 空串、`"false"`、前 25 列顺序）、`ST-STATUS-01`。另有：schema 11 个显式矛盾用例、历史行读取（`/windows`、`/risk/latest`、`PATCH flag`）、`NULL` payload 的 status、cache 收紧。

## 5. Tests executed (exact commands)

所有 pytest 命令均先 `export TMPDIR=$(mktemp -d)`，在 `/Users/liu/Desktop/FYP2-Live-System/backend` 下以 `PYTHONPATH=. ../.venv/bin/python -m pytest ... -p no:cacheprovider` 运行。

1. **基线**（改动前）：`pytest tests -q` -> `1 failed, 321 passed`（失败项即 `test_missing_expired_and_out_of_order_inputs`）。
2. **红**（只加测试、未改实现）：`pytest tests/test_unavailable_contract.py tests/test_migration.py -q` -> `25 failed, 21 passed`。
3. **绿**：`pytest tests -q` -> `367 passed, 1 warning in 4.45s`，0 skip（真模型用例确实跑了）。
4. **既有集合复现 322**：
   `pytest tests -q --ignore=tests/test_unavailable_contract.py --deselect tests/test_migration.py::test_migration_adds_flag_column_and_backfills_columns_and_payload --deselect tests/test_migration.py::test_migration_is_idempotent_and_preserves_new_rows --deselect tests/test_migration.py::test_migration_never_erases_a_row_whose_payload_is_unusable --deselect tests/test_migration.py::test_migrated_legacy_rows_export_as_json_booleans_and_nulls`
   -> `322 passed, 13 deselected`。
5. `cd /Users/liu/Desktop/FYP2-Live-System && npx vitest run --no-cache` -> `1 failed | 219 passed (220)`，失败为 `frontend/src/data/preparedSessionInput.test.ts`（Task 6 所有）。
6. `npx tsc --noEmit` -> 35 条 `error TS`，其中 `frontend/` 之外 0 条。
7. **反事实（在 scratchpad 里的副本上做，未碰工作树）**：逐项破坏实现，确认测试会红。

| 破坏 | 结果 |
|---|---|
| M1 禁用 before 推导 | 33 failed（含几乎全部 `/windows` 既有用例） |
| M2 去掉 after 校验 | 11 failed（全部为「显式矛盾必须被拒」） |
| M3 去掉 payload 守卫（裸 `json_set`） | 7 failed（4 条「不抹行」+ 3 条回填） |
| M4 `json('true')` 换成整数 `1` | 2 failed（`is True` 与导出布尔） |
| M5 去掉 `_csv_cell` | 1 failed（CSV 空串/小写布尔） |
| M6 `RiskLevel: Optional[RiskLevel] = None` | 25 failed |
| M7 回填两步颠倒 | 2 failed |

## 6. PASS / FAIL / SKIP counts

| 套件 | 改动前 | 改动后 |
|---|---|---|
| pytest 全量 | 321 passed / 1 failed / 0 skipped | **367 passed / 0 failed / 0 skipped** |
| pytest 既有集合（排除 45 条新增） | 321 / 1 | **322 passed / 0 failed** |
| vitest | 219 passed / 1 failed | 219 passed / 1 failed（**未漂移**） |
| tsc | 35 errors（全在 `frontend/`） | 35 errors（全在 `frontend/`，**未漂移**） |

新增 45 条 = `test_unavailable_contract.py` 32 + `test_migration.py` 13。

## 7. Remaining issues

1. **`inference.py` 不传 `assessment_available`（Task 5）。** 目前完全靠 before 防线推导。Task 5 应改为显式传入；传了之后 after 防线会严格校验。届时 before 防线对 `inference.py` 就不再承重，但仍需保留给历史行。
2. **潜在缺陷（Task 5 必须修）：零权重的「不可用」窗口会误入 FSM 的 Low 分支。** `inference.py` 用 `health == "UNAVAILABLE"` 判断是否挂起 FSM，而 `health` 是默认 `0.5/0.5` 权重算的。对 `(1.0, 0.0)` + vision missing + telemetry fresh：`score=None`、`level=None`、`health="DEGRADED"`，于是落入 `else`（Low）分支，会启动 `low_since` 计时，**10 秒后可能把 `HIGH_ALERT` 降回 `NORMAL`**，尽管这段时间没有任何可评估的证据。我的 schema 只能在**响应与落库值**上把 `AlertSeverity` 改成 `None`、健康改成 `UNAVAILABLE`，改不了 `runtime_state` 里的 FSM 状态。Task 5 的挂起条件应该是 `level is None`（或 `not available`），不是 `health == "UNAVAILABLE"`。
3. **`build_explanation(dominant, level)` 仍只传两个参数**，所以零权重窗口的 `explanation` 是泛化原因文案，而不是点名「telemetry 权重为零」。属 Task 5。
4. **我加了一条比 brief 更严的规则**：`assessment_available=True` 时，除 `RiskScore` 外 `RiskLevel` / `DominantEvidence` / `AlertSeverity` 也必须非 null（brief 只明确要求「False 时四字段同为 null」）。理由是部分为 null 的「可用」记录会让消费方在 available 分支里崩。若后续 task 确实需要「可用但无严重度」，放宽一行即可，报错信息会直接指向这里。
5. **后端 CSV 的 `flagged` 从 `True/False` 变成 `true/false`**（跨栈约定「布尔一律小写」）。仓库内没有测试或消费方依赖大写形式；Task 6 的前端 `utils/export.ts` 需要与此一致。
6. **重复 fixture**：`test_audit_regressions.py` 里仍有同契约的 `api`，`test_live_inference.py` 仍 `from test_audit_regressions import api`。我按 brief 的「新测试只用 conftest」没动它们。建议后续单独清理，消除那条靠 `sys.path` 才成立的跨模块 import。
7. **迁移依赖 SQLite JSON 函数**（`json_valid` / `json_type` / `json_set` / `json()`，3.38+ 内置；本机 3.49.1）。若部署环境的 SQLite 缺 JSON1，`initialize_database()` 会在启动时抛错。此前迁移不需要这些函数。未加能力探测，因为不在 brief 内，且 `requirements.lock.txt` 指向 Python 3.13。
8. **`latest_assessment_available` 读新列而非 payload。** 经过 `initialize_database()` 的库永远正确；绕过 lifespan、手工塞入的未迁移历史行会读到列默认值 `True`。仅测试夹具能触发。
9. **已知 Minor（未碰相邻代码，未修）**：`NaN <= epsilon` 为假，NaN 概率可能被当作「可用」。API 边界的 `Field(ge=0, le=1)` 已拒绝 NaN，且我没有改动 `fusion.py`。
10. **JSON 导出的历史行完整性取决于迁移已跑。** 导出原样 dump payload，不经 `RiskUpdate`，所以未迁移的历史行导出里没有 `assessment_available`。正常路径下 lifespan 总会先迁移；我没有在导出里加归一化，是因为中途抛错会让 200 之后的流被截断（brief 点名的风险），宁可让读路径（`windows` / `risk`）承担归一化。

## 8. Evidence paths

- 实现：`/Users/liu/Desktop/FYP2-Live-System/backend/app/schemas.py`、`models.py`、`db.py`、`routers/{windows,risk,status,export}.py`
- 测试：`/Users/liu/Desktop/FYP2-Live-System/backend/tests/conftest.py`、`test_unavailable_contract.py`、`test_migration.py`、`test_live_inference.py`
- 契约来源：`/Users/liu/Desktop/FYP2-Live-System/backend/app/fusion.py`、`ai/src/types.ts`、`ai/fixtures/fusion_vectors.json`
- 反事实工作副本（非交付物）：`/private/tmp/claude-501/-Users-liu-Desktop-FYP-In-Cabin-Driver-Assessment--1--claude-worktrees-audit-files-dev-plan-ed0c73/be4350f1-4e5a-4bf1-9aeb-63516764da7e/scratchpad/mut/`
- 未创建任何真实开发数据库；所有迁移与读写都在 `tmp_path` 或一次性 `TMPDIR` 内。

## 9. Next task dependencies

- **Task 5（`inference.py`）**：①显式传 `assessment_available`；②用 `fusion.map_system_health(v, t, w_v, w_t)` 带权重算健康；③FSM 挂起条件改成 `level is None`（第 7 节第 2 条）；④`AlertSeverity` 在不可用时直接给 `None`；⑤把权重传给 `build_explanation` 以得到点名的原因文案。完成后可在 `test_unavailable_contract.py` 里把「零权重」用例的 `AlertSeverity`/健康断言从「被 schema 归一化」收紧为「由 producer 直接产出」。
- **Task 6（前端）**：CSV 表示必须与本任务一致 —— 四字段空单元格、`assessment_available` 为 `false`、`SystemHealth` 为 `UNAVAILABLE`、布尔小写；`flagged` 同样小写。后端 CSV 新增的 `assessment_available` / `P_distraction_raw` / `P_telemetry_raw` 三列在末尾。
- **Task 7（故障事件）**：`SystemStatusOut.open_fault_events` 已占位为 `0`，由 Task 7 填充；`db.py` 的 `CREATE TABLE` 块请加在 `additions` 循环之前，不要改我的 `additions` 字典与 `_backfill_assessment_available`。
