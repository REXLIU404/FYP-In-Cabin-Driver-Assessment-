# Task 7 实现报告 —— fault_events：可观测且能活过会话删除

## 1. 任务编号与名称

- **Task 7**（`TASK-7-FAULTS`）：`fault_events` —— 每一次失败的 `/infer` 尝试都有持久记录，且记录不随会话删除而消失（含控制者 R6 裁定 C1–C11 与审阅 R16 补测）
- 工作树 `/Users/liu/Desktop/FYP2-Live-System`，分支 `fyp2/live-system`，基线 HEAD `1865766`（开工前已核实分支与 HEAD）
- 范围外、零改动：前端、`ai/src`、融合逻辑、`inference.py`、模型文件、`docs/fyp2/review/`、计划文件

## 2. 实现状态

**DONE_WITH_CONCERNS。** 四道门禁全部达标：pytest 568 passed / 0 failed / 0 skipped、vitest 427 passed、`tsc` 0 错、`eslint` 0 问题。concerns 见第 7 节，其中最需要知情的是：

- 同一 `(session_id, request_id, attempt_index)` 在库里只有一行（唯一索引的设计目的）。**如果客户端不随重试递增 `X-Attempt-Index`，第 2、3 次失败会被折叠成一行**（文件 sink 仍逐次留痕）。这要求 Task 8 的 `retry()` 真的发这个头。
- 500 的两种成因响应体不同：`model_runtime` 是 JSON `{"detail": …}`，`storage` 仍是原样的 `Internal Server Error` 纯文本（C8 要求不改动）。两者都可重试，所以 Task 8 不必区分，但不要依赖响应体区分它们。

| 项 | 状态 |
|---|---|
| `fault_events` 表：无 FK、可空带索引的 `session_id`、显式 `CREATE TABLE IF NOT EXISTS`、唯一索引 `uq_fault_session_request_attempt` | 完成 |
| `record_fault`：独立 session，绑 `db.get_bind()`，在 `rollback()` 之后调用，永不抛出，文件 sink 兜底 | 完成 |
| `mark_recovered` / `open_fault_count` / `GET /api/faults` / `SystemStatusOut.open_fault_events` | 完成 |
| `trained.py`：运行期错误与模型不可用拆开（C4、C5） | 完成 |
| `RequestValidationError` 与漏网 `Exception` 的全局处理器（C8） | 完成 |
| `_save_window` 的并发重复（`IntegrityError`）不再冒成 500 | 完成 |
| ST-FAIL-01/02/03/04、ST-RECOVER-01、IT-FAULT-ORT、IT-FAULT-SINGLE-BRANCH、IT-FAULT-INTEGRITY、IT-OUTCOME-01、迁移测试、接口测试 | 全部完成，均不依赖模型文件 |
| 每条新增测试的变异验证 | 完成（第 5 节：M1–M9 + 39 个补充变异，0 个无法解释的存活） |

## 3. 创建 / 修改的文件

**新建（4）**

| 文件 | 说明 |
|---|---|
| `backend/app/faults.py` | 全部常量（`ORIGIN_*`、`CATEGORY_*`、`RETRYABLE`）；`ensure_schema`（表的**唯一**描述）；`FaultHTTPException`、`classify_exception`；`FaultSink` / `get_fault_sink`；`record_fault`、`mark_recovered`、`open_fault_count`、`list_fault_events`；请求解析小函数 |
| `backend/app/routers/faults.py` | `GET /api/faults`；`RequestValidationError` 与 `Exception` 两个全局处理器及 `install_exception_handlers` |
| `backend/tests/test_fault_events.py` | 29 个测试函数，参数化后 43 个用例 |
| `docs/fyp2/implementation/task-07.md` | 本报告 |

**修改（8）**

| 文件 | 说明 |
|---|---|
| `backend/app/routers/windows.py` | `_save_window` 拆成 `_persist_window`（不回滚）+ `_save_window`（回滚，供 replay）；`infer_frame` 路由内记录；`_run_models` 把三类模型错误映射到 422/503/500；`IntegrityError` 读回既有记录；成功路径 `mark_recovered`；`X-Attempt-Index` 头；各 404/409 改用 `FaultHTTPException`（响应不变） |
| `backend/app/providers/trained.py` | 新增 `ModelRuntimeError`；`vision.run` / `telemetry.predict` 的异常、非有限输出、形状不对一律走它；`ModelUnavailable` 只留给文件缺失 / 依赖缺失或加载失败 / 元数据校验失败 |
| `backend/app/db.py` | `initialize_database()` 末尾调 `ensure_schema` |
| `backend/app/main.py` | 注册 `faults` 路由与异常处理器 |
| `backend/app/schemas.py` | 新增 `FaultEventOut`；`SystemStatusOut.open_fault_events` 由占位的 `= 0` 改为必填 |
| `backend/app/routers/status.py` | `open_fault_events=open_fault_count(...)` |
| `backend/tests/conftest.py` | `api_factory` 调 `ensure_schema` 并 override `get_fault_sink` 到 `tmp_path`；新增 autouse 夹具把默认 sink 路径重定向到 `tmp_path`（C9、C10） |
| `.gitignore` | `backend/logs/`（C10） |

**没有改动的已有测试**：C4 把「非有限输出 → 503」改成 500，但已有测试里没有任何一条断言过这个行为（已 grep 核实），`test_missing_artifacts_are_503` 与 `test_missing_inference_dependency_is_503` 原样保持绿。**未改 `models.py`**：C9 要求表只有一个来源，若在 `Base` 上声明 ORM 模型，`create_all` 会用另一份 DDL 建同名表。`test_the_fault_table_has_one_description_and_no_foreign_key` 断言 `"fault_events" not in Base.metadata.tables`。

## 4. 实现摘要

### 4.1 数据流（一次 `/infer` 的失败路径）

```
POST /infer ──► FastAPI 校验 ──失败──► on_request_validation_error ──► record_fault ──► 原样返回 422
                   │ 通过
                   ▼
            infer_frame（路由内）
              try: _infer(...)  # 404/409/422/503/500 都在这里抛出
              except Exception:
                  db.rollback()                 ◄── 必须先于下一行（M3）
                  record_fault(...)             ◄── 独立 session，绑 db.get_bind()；永不抛出
                  request.state.fault_recorded = True
                  raise                         ◄── 原异常，原样
                   │ 路由之外才冒出的异常（例如响应校验）
                   ▼
            on_unhandled_exception ──(未记录过才)──► record_fault ──► 原样的 500 纯文本
```

- `record_fault` 每次先写库，再**无条件**向文件 sink 追加一行 JSON（含 `db_written` 标志）。库不可写时，这一行就是该次尝试唯一的持久 outcome。
- 成功路径：`commit` 成功之后、`cache.set_latest` 之前调 `mark_recovered`。幂等重放与 `IntegrityError` 读回的 twin 都在它之前就返回了，所以不触发恢复。

### 4.2 C1–C11 逐条如何落地

| 裁定 | 落地 |
|---|---|
| **C1** 503 不可重试 | `RETRYABLE["models_unavailable"] = False`。ST-FAIL-02 的 503 子用例断言 `retryable is False`；变异 E32（改成 True）使 3 条测试变红 |
| **C2** 拼写 | 全部为 `models_unavailable`（常量 `CATEGORY_MODELS_UNAVAILABLE`），测试里是字面量 |
| **C3** `attempt_index` | 列名与唯一索引 `uq_fault_session_request_attempt ON fault_events(session_id, request_id, attempt_index)`；路由参数 `Header(1, ge=1, alias="X-Attempt-Index")`，缺省 1；非整数或 < 1 → FastAPI 422 → 全局处理器按 `input_validation` 记录，此时 `attempt_index` 存 **NULL**（值不可解析，没有可存的整数；SQLite 唯一索引视 NULL 互不相等，所以每个这类尝试各占一行）。**不进 `request_hash`**：摘要仍只由 `payload.model_dump()` 计算，`test_attempt_index_is_told_by_the_client…` 与 IT-OUTCOME-01 的「attempt 2 重放」守护，M9 使其变红 |
| **C4** 运行期错误与不可用分开 | `ModelRuntimeError(message, origin)`；`vision.run`、`telemetry.predict`（含 `DMatrix` 构造）的任何异常，以及 logits 非有限 / 形状 ≠ `(10,)`、概率非有限 / 形状 ≠ `(3,)`，一律 → `FaultHTTPException(500, …, model_runtime)`，`retryable = True`。`ModelUnavailable` → 503 只剩三种：文件缺失、依赖缺失或加载失败、元数据校验失败（`get_provider()` 里原样保留） |
| **C5** 单分支失败 = 整个请求失败 | 异常自然向上传播，不存在降级路径；`origin` 取 `vision_model` / `telemetry_model`。两个方向各一条测试，均断言无 `InferenceRecord`、`/windows` 为空、`/risk/latest` 404，并在清除故障后用同一 payload 成功 |
| **C6** `origin` 取值 | 常量定义在 `faults.py`：`request_validation`、`session`、`vision_model`、`telemetry_model`、`model_load`、`storage`、`unknown`。映射：schema/坏图/头非法 → `request_validation`；404、模式不符、hash 冲突、乱序 → `session`；503 → `model_load`；commit 失败 → `storage`；生产者自相矛盾 → `unknown` |
| **C7** 恢复语义 | 只写 `open` / `recovered`；`exhausted` 在 `CHECK` 约束里保留，永不写入。`mark_recovered(db, session_id, request_id)` 把**该会话**所有 `open` 行改为 `recovered` 并填 `recovered_by_request_id`、`recovered_at`。服务端不含任何 3 次上界：ST-RECOVER-01 的第 4 次提交带 `X-Attempt-Index: 4`，另一条测试记录了 `99` |
| **C8** 在哪里记录 | 路由内 `try/except`（此时 `request_id` 可得）；全局只有两个处理器：`RequestValidationError`（`request_id` 取自 `exc.body`，取不到为 null；detail 只含字段路径与消息，**丢弃 pydantic 的 `input`**，否则会把 2.8 MB 的 base64 帧写进库）与漏网 `Exception`（靠 `request.state.fault_recorded` 避免重复）。两个处理器都返回与 FastAPI/Starlette 默认**完全相同**的响应，仅 `POST /api/sessions/{id}/infer` 生效。生产者自相矛盾（`RiskUpdate` 的 `after` validator 抛 `ValidationError`）：记为 `unknown`/`unknown`、500、`retryable = False`，HTTP 仍是原样的裸 500，异常原样抛出 |
| **C9** 表结构只有一个来源 | `faults.ensure_schema(conn)` 同时含 `CREATE TABLE IF NOT EXISTS`、`CREATE INDEX IF NOT EXISTS`、`CREATE UNIQUE INDEX IF NOT EXISTS`；`initialize_database()` 与 `conftest.api_factory` 都调它；`Base` 上**没有** `fault_events` |
| **C10** 文件 sink | `backend/logs/fault_events.log`（`DEFAULT_SINK_PATH`），`.gitignore` 加 `backend/logs/`，`get_fault_sink` 是可 override 的依赖；conftest 另有一个 **autouse** 夹具把 `DEFAULT_SINK_PATH` 重定向到每个测试的 `tmp_path`——`test_audit_regressions.py` 的模块级 `api` 夹具只 override `get_db`，没有这一层，已有测试里的失败请求会写进真实的 `backend/logs/`。运行全部门禁后 `backend/logs/` 不存在（已核实） |
| **C11** 增量迁移 | `test_initialize_database_adds_the_fault_table_without_touching_anything_else`：用 `test_migration.make_legacy_engine` 造**两份**真正的旧 schema 库（无 `fault_events`，含 3 行已有记录）；对照库把 `db.ensure_fault_schema` 换成空函数后迁移，实验库用真实函数迁移，然后断言除 `fault_events`（及其 `sqlite_sequence` 簿记）外所有表、索引、行逐值相等；再插一行 fault、重跑迁移，断言行还在、DDL 不变（幂等）。没有对任何开发库运行 |

### 4.3 为了让变异有意义而做的结构调整

`_save_window` 原来在自己的 `except` 里 `rollback()`，所以任何走到路由 `except` 的存储失败都已经回滚过——把「记录」挪到「回滚」之前（M3）在行为上无差别，没有测试能抓到。我把它拆成 `_persist_window`（失败时**不**回滚，事务边界归调用方）与 `_save_window`（replay 用，保持原行为）。这样 `infer_frame` 里 `rollback → record_fault` 成为唯一的、可被变异的顺序点。replay 的 `/windows` 行为没有改变。

### 4.4 超出 brief 字面的取舍（均需知情）

- **新增类别 `out_of_order_evidence`。** 乱序时间戳的 409 与 hash 冲突的 409 必须可区分（D02 失败表里两者的 UI 文案不同），所以不能都叫 `idempotency_conflict`。
- **sink 无条件镜像每一次 fault，不是仅在库失败时兜底。** 计划 ST-FAIL-03 子用例 1 要求在库**可写**时 sink 里也有一行 `storage` + request_id，故按此实现，并加 `db_written` 标志。后果：IT-OUTCOME-01 里「sink 行算 outcome」只在库里没有任何 outcome 时成立。
- **`INSERT … ON CONFLICT DO NOTHING`，不是 `INSERT OR IGNORE`。** 只跳过唯一约束冲突（同一次尝试的重复投递）；`NOT NULL` / `CHECK` 违反仍然抛错并落到 sink，不会被静默吞掉。
- **`open_fault_count` 容忍「没有这张表」返回 0。** `test_audit_regressions.py` 的 `api` 夹具与 `test_api.py` 只跑 `create_all`，而按 C9 只有两个调用方可以建表，不能改这些夹具；不容忍的话它们对 `/system-status` 的断言会 500。其他读写路径不容忍。
- **`SystemStatusOut.open_fault_events` 去掉了默认值。** 它早已作为占位（`= 0`）存在，Task 4 的测试断言过 0；现在是必填，漏接线会立刻变成 500。
- **`GET /api/faults`** 的 `session_id` 可选（缺省返回全部），另有 `limit`（1–1000，默认 500）。

## 5. 执行的测试（精确命令）

### 5.1 四道门禁（真实工作树，在最终代码上）

```
cd /Users/liu/Desktop/FYP2-Live-System
export PYTHONDONTWRITEBYTECODE=1
(cd backend && TMPDIR=$(mktemp -d) PYTHONPATH=. ../.venv/bin/python -m pytest tests -q -p no:cacheprovider)
./node_modules/.bin/vitest run --no-cache
./node_modules/.bin/tsc --noEmit
./node_modules/.bin/eslint .
```

实测：`568 passed, 1 warning in 7.18s`；`Test Files 16 passed (16) / Tests 427 passed (427)`；`tsc exit=0`；`eslint exit=0`。开工前在同一 HEAD 复现基线：`525 passed in 5.87s`。

只跑新测试：`(cd backend && TMPDIR=$(mktemp -d) PYTHONPATH=. ../.venv/bin/python -m pytest tests/test_fault_events.py -q -p no:cacheprovider)` → `43 passed`。

### 5.2 手工核对（不入库）

在 `.claude` scratchpad 下用一次性 SQLite 文件、`DRA_DATABASE_URL` 指向它、sink 路径改到同目录，走完整 lifespan 的 `TestClient`：`initialize_database()` 建出 `fault_events`；带 `X-Attempt-Index: 2` 的坏帧与带未知字段的请求各得 422，`GET /api/faults?session_id=e2e` 返回两行（`attempt_index` 分别为 2、1），`open_fault_events == 2`，sink 两行 `db_written: true`。**没有对开发库启动 uvicorn。**

### 5.3 IT-OUTCOME-01：脚本、分母与 eligible 的定义

**eligible 的定义**：到达应用的每一个 `POST /api/sessions/{id}/infer` HTTP 请求，**包括 schema 校验失败的请求**（它们到不了路由函数，只能由全局处理器观察）。分母来自测试脚本自己的请求清单（16 项）与它拿到的状态码，不来自数据库；分子来自每次尝试前后 `inference_records` / `fault_events` / sink 的差值。

| # | 尝试 | 状态 | 持久 outcome |
|---|---|---|---|
| 1 | 成功 `ok-1` | 201 | 新 `InferenceRecord` |
| 2 | `ok-1` 幂等重放（`X-Attempt-Index: 2`） | 201 | 既有记录 |
| 3 | schema 422（未知字段） | 422 | fault 行 |
| 4 | schema 422（无 `request_id`） | 422 | fault 行（`request_id` 为 null） |
| 5 | 坏图 422 | 422 | fault 行 |
| 6 | 会话不存在 | 404 | fault 行（`session_id = no-such-session`） |
| 7 | 会话模式不符 | 409 | fault 行（`mode_conflict`） |
| 8 | hash 冲突 | 409 | fault 行（`idempotency_conflict`） |
| 9 | 乱序时间戳 | 409 | fault 行（`out_of_order_evidence`） |
| 10 | 视觉运行期错误 | 500 | fault 行（`model_runtime` / `vision_model`） |
| 11 | 模型不可用 | 503 | fault 行（`models_unavailable` / `model_load`） |
| 12 | 存储失败且库完全不可写 | 500 | **sink 行**（`db_written: false`） |
| 13 | 成功 `ok-2` | 201 | 新 `InferenceRecord` |
| 14 | 仅遥测成功 `ok-3` | 201 | 新 `InferenceRecord` |
| 15 | `X-Attempt-Index: 0` | 422 | fault 行（`attempt_index` 为 NULL） |
| 16 | 遥测运行期错误 | 500 | fault 行（`model_runtime` / `telemetry_model`） |

- **(b) 全部 outcome 的记录率** = 有恰好 1 个持久 outcome 的尝试数 / eligible 尝试数 = **16 / 16 = 100%**（用 `Fraction` 断言等于 1；每一步还单独断言 outcome 个数恰好为 1，且与上表的预期种类一致）。
- **(a) 成功预测的持久化率** = 返回 201 的**不同** `request_id`（`ok-1`、`ok-2`、`ok-3`；重放与 `ok-1` 同 id）中有 `InferenceRecord` 的比例 = **3 / 3 = 100%**。
- 账目：3 条记录、11 行 fault、12 行 sink（11 行镜像 + 1 行库不可写）；`ok-2` 之后 `open_fault_events` 为 2（#15、#16），另两个会话各 1。
- 对每个 fault 步骤，还断言了刚写入那一行的 `(error_category, origin, http_status, retryable, session_id, attempt_index, request_id)`。

### 5.4 变异验证（全部在隔离副本里做）

**副本的建法**：`D=$(mktemp -d) && git archive HEAD | tar -x -C "$D" && ln -s /Users/liu/Desktop/FYP2-Live-System/.venv "$D/.venv"`。因为 `HEAD`（1865766）不含尚未提交的实现，随后把本项的 11 个文件覆盖进副本，再在副本的 `backend/` 里改一行、跑 `pytest tests/test_fault_events.py`、从真实树复原、`diff` 确认与真实树逐字节一致。真实工作树没有被改动，每次变异后「restored identical to real tree」均为 True。副本里没有模型文件：全量 `pytest tests` 为 `561 passed, 7 skipped`（7 个是依赖真实模型的旧测试），新增的 43 个全绿且不依赖权重。

**brief 指定的 M1–M9**

| # | 变异 | 观察到的结果 |
|---|---|---|
| M1 | `fault_events.session_id` 加 `REFERENCES sessions(id) ON DELETE CASCADE` | 5 失败，含 **ST-FAIL-01**（`test_st_fail_01_faults_outlive_the_session`）、IT-OUTCOME-01、接口测试、`…_no_foreign_key` |
| M2 | `record_fault` 改用模块级 `SessionLocal`（并给全局库建了表，使误写能成功） | 35 失败；`test_faults_are_written_to_the_request_database_not_the_module_level_one` 专门断言请求库 1 行、全局库 0 行 |
| M3 | 记录挪到 `rollback()` 之前 | 4 失败：ST-FAIL-03 子用例 1、`…_a_broken_sink…`、IT-OUTCOME-01、`…_contradictory_producer…`。**观察到的现象**：失败事务仍握着 SQLite 写锁，第二连接的 INSERT 等满 `busy_timeout=15000`（15 s）后报 `database is locked`，被 `record_fault` 吞掉，库里没有 fault 行，断言失败；全文件耗时 131.4 s（每个被阻塞的写 15 s，共约 9 次）。正常实现下整文件 2 s |
| M4 | 运行期异常改回 503（a：路由映射；b：provider 对视觉异常抛 `ModelUnavailable`；c：对非有限 logits 抛 `ModelUnavailable`） | a 13 失败、b 6 失败、c 3 失败；**ST-FAIL-04**、**IT-FAULT-ORT**（逐参数）均变红 |
| M5 | 删除 `uq_fault_session_request_attempt` | 3 失败；ST-FAIL-02 失败在 `assert len(faults_of(live)) == 1`（`2 == 1`），即「重复请求不产生第二行」本身 |
| M6 | 成功路径不调 `mark_recovered` | 2 失败：**ST-RECOVER-01**、IT-OUTCOME-01 |
| M7 | sink / 库失败时改写原始异常 | **7a**（`record_fault` 的库写失败分支 `raise`）：2 失败，含 **ST-FAIL-03 子用例 2**。**7b**（仅 `FaultSink.write` 改成抛错）：**存活**——`record_fault` 外层另有一道 `try/except` 兜底，是纵深防御，单层变异等价。**7b′**（`FaultSink.write` 抛错且去掉外层兜底）：1 失败（`…_a_broken_sink_never_masks_the_original_error`） |
| M8 | 不记录 schema 422 | 11 失败，含 **IT-OUTCOME-01**（第 3、4、15 步无 outcome） |
| M9 | `X-Attempt-Index` 进入 `request_hash` | 5 失败：**ST-RECOVER-01**、**IT-OUTCOME-01**（第 2 步重放变 409）、幂等重放、attempt 头测试、（连带）stray 测试（变异改了 `_infer` 签名） |

**补充变异（每条新增测试至少被一个变异杀死）**

| 变异 | 失败的测试 |
|---|---|
| E1 去掉 `ge=1` | `…invalid_attempt_header[0]`、`[-3]`、IT-OUTCOME-01 |
| E2 `model_runtime` 标不可重试 | ST-FAIL-04、ST-RECOVER-01、全部 IT-FAULT-ORT / SINGLE-BRANCH、IT-OUTCOME-01（12） |
| E3 去掉 `IntegrityError` 读回 | IT-FAULT-INTEGRITY 两条 |
| E4 `mark_recovered` 不限会话 | `…recovery_is_scoped_to_the_session`、IT-OUTCOME-01 |
| E5 幂等重放也调 `mark_recovered` | `…idempotent_replay_is_not_a_recovery` |
| E6 / E9 去掉 `fault_recorded` 守卫 / 不注册 `Exception` 处理器 | `…contradictory_producer…`、IT-OUTCOME-01 / `…stray_exception…` |
| E7 / E38 `request_id` 不取 `exc.body` / 为不可用 body 编造一个 | 7 条 / 5 条 schema-422 与 IT-OUTCOME-01 |
| E8 detail 回显 `input` | `…schema_422_is_recorded_with_the_request_id_and_without_echoing_the_input` |
| E10 / E11 `initialize_database` 不建表 / `ensure_schema` 先 `DROP TABLE` | 迁移测试 |
| E12 `api_factory` 不调 `ensure_schema` | 40 条（含 `…api_factory_builds…`） |
| E13 / E37 去掉 autouse 重定向 / sink 不建目录 | `…tests_cannot_reach_the_real_log_directory` |
| E14 replay 的 `_save_window` 也记录 | `…replay_windows_route_records_no_faults` |
| E15 / E16 / E42 类别或 origin 标错 | IT-OUTCOME-01（逐步断言类别与 origin） |
| E17 / E18 sink 不写 / `db_written` 恒真 | 6 条 / 2 条 |
| E19 / E19b 恢复后仍计数 / 状态接口不接线 | ST-RECOVER-01 等 / 6 条 |
| E20 / E21 / E35 排序 / `LIMIT` / `session_id` 过滤失效 | `…get_faults_returns_the_contract_fields_oldest_first` |
| E22 默认 attempt 为 2 | ST-FAIL-02、attempt 头测试、IT-OUTCOME-01 |
| E24 视觉错误记到遥测分支 | ORT、SINGLE-BRANCH、ST-RECOVER-01、IT-OUTCOME-01 |
| E25a–d 去掉视觉 / 遥测的形状 / 有限性检查 | 对应的 `vision-shape`、`telemetry-shape`、`vision-nan/inf`、`telemetry-nan` 各自变红 |
| E27 `parse_attempt_header` 接受 0 | `…invalid_attempt_header[0]`、IT-OUTCOME-01 |
| E28 / E29 `recovered_at` 不填 / `recovered_by_request_id` 填错 | ST-RECOVER-01 |
| E32 / E40 / E41 503 标可重试 / `unknown` 标可重试 / 存储错误不归 `storage` | 3 条 / 1 条 / 1 条 |
| E33 去掉 `recovery_status` 的 `CHECK` | `…no_foreign_key`（该测试插入 `'bogus'` 期望 `IntegrityError`，并确认 `'exhausted'` 合法） |

**两处无法用变异覆盖，如实说明**：① `ORDER BY occurred_at, id` 里的 `id` 次序键——SQLite 对表扫描按 rowid 升序，去掉它后并列行的次序仍相同，该变异是等价的；测试只守护 `occurred_at` 键。② M7b 单层变异等价，见上。

## 6. PASS / FAIL / SKIP 计数

| 门禁 | 基线（1865766） | 本项之后 | 变化原因 |
|---|---|---|---|
| pytest（真实树，模型经符号链接可用） | 525 passed | **568 passed / 0 failed / 0 skipped** | +43 = `test_fault_events.py` 的 43 个用例（29 个函数，参数化：IT-FAULT-ORT 7、SINGLE-BRANCH 2、非法头 5、无可用 request_id 4）。没有任何已有测试被修改、删除或替换 |
| pytest（隔离副本，无模型） | — | 561 passed / 0 failed / **7 skipped** | 7 个 skip 都是已有的 `requires_models` 用例（`test_live_inference.py` 4 个、`test_unavailable_contract.py` 3 个），预期内；新增的 43 个不依赖权重 |
| vitest | 427 passed | **427 passed**（16 个文件） | 本项不碰前端 |
| `tsc --noEmit` | 0 错 | 0 错 | — |
| `eslint .` | 0 问题 | 0 问题 | — |

## 7. 遗留问题

### 7.1 计划行号的漂移（对照基线 `1865766` 核实）

| 计划写的 | 当前实际 |
|---|---|
| `db.py:44` `inspect(conn).get_columns(table)` | `db.py:48` |
| `db.py:52-53` 幂等唯一索引写法 | `db.py:56-57` |
| `windows.py:42-108`（`infer_frame`） | `_save_window` 在 `:33-79`，`infer_frame` 在 `:87-109` |
| `windows.py:72` `runtime_state` 写入 | `:73` |
| `windows.py:62` 计时早于 commit | `:63` |
| `windows.py:95` `request_hash` | `:96` |
| `windows.py:51-58` 乱序守卫 | 守卫本体 `:53-56`（循环 `:51-58`） |
| `test_migration.py:8` 只 import `app.db` | 顶部现在只有 `json`/`pytest`/`sqlalchemy`，`from app import db` 在各测试函数内（`:64` 起） |
| `schemas.py:122-131`（`LiveInput` 校验） | `:117-131`（`consistent_inputs` 在 `:123`） |
| 「`SystemStatusOut` 新增 `open_fault_events`」 | 字段早已作为占位存在（`schemas.py:247`，`= 0`；`test_unavailable_contract.py:393` 断言它为 0） |
| `inference.py:13-18` 的 freshness 描述 | `freshness()` 现在在 `inference.py:45-50`（与本 Task 无关，D13 段落引用） |
| 「新 conftest 要复用同一个 pragma 钩子」 | `api_factory` 已有 `foreign_keys` 与 `busy_timeout`，但没有 `journal_mode=WAL`（生产的 `db.py:25` 有）。回滚日志模式下写者互斥更严，对 M3 更敏感，不影响结论 |
| 未漂移（已核实） | `models.py:34` / `:45` / `:50`、`db.py:21-27` / `:24` / `:26`、`main.py:14`、`schemas.py:97`、`trained.py:122-123` |

### 7.2 未实现 / 有意不做

- 计划「新建文件」表里还列了 `GET /api/sessions/{id}/faults` 与 `POST /api/faults`（客户端上报，不以会话存在为前提）。brief 的需求与测试清单没有它们，C7 又说「3 次上界属于客户端，如何上报由 Task 8 决定」，所以**没做**。Task 8 若需要客户端侧上报 `transport_timeout` / `exhausted`，要在那里补，或回到这里加。
- 可选的 `requires_models` 真实模型用例没写：真实树里所有旧的 `requires_models` 测试在门禁中都是 PASS（模型经符号链接可用），没有新增的必要。

### 7.3 已知限制与风险

1. **`attempt_index` 由客户端诚实告知。** 服务端不强制它递增。不发该头的客户端（含当前前端）所有失败都记为 `attempt_index = 1`，同一 `request_id` 下会折叠成一行；文件 sink 仍逐次留痕。→ Task 8 必须发送 `X-Attempt-Index`。
2. **非法头的 fault 行 `attempt_index` 为 NULL**，且不受唯一索引去重。
3. **sink 无轮转**：`backend/logs/fault_events.log` 只追加。本地单用户原型可以接受。
4. **`storage` 与 `model_runtime` 的 500 响应体不同**（纯文本 vs JSON）。D02 里两者都可重试，客户端不需要区分，但 Task 8 的 `classifyFailure` 不应靠响应体判断类别。
5. **并发重复（`IntegrityError`）在当前单库部署里几乎不可达**：写锁由 `UPDATE sessions …` 先拿到，之后的重复检查已在锁内。防线是为了将来换部署形态；测试靠让前两次检查「看不见」twin、由真实唯一索引在 `commit` 时触发来模拟，而不是伪造 `IntegrityError`。
6. **`ModelRuntimeError` 的 HTTP detail 是固定通用句**（不含 onnxruntime 内部信息）；内部异常类型与消息只写进 fault 行的 `detail`（≤ 1000 字符）和 sink。
7. M7b 的存活变异与 `id` 次序键的不可测性见 5.4。

## 8. 证据路径

- 本报告：`/Users/liu/Desktop/FYP2-Live-System/docs/fyp2/implementation/task-07.md`
- 实现：`backend/app/faults.py`、`backend/app/routers/faults.py`、`backend/app/routers/windows.py`、`backend/app/providers/trained.py`、`backend/app/db.py`、`backend/app/main.py`、`backend/app/schemas.py`、`backend/app/routers/status.py`、`.gitignore`
- 测试：`backend/tests/test_fault_events.py`、`backend/tests/conftest.py`
- 变异脚本与结果输出（会话临时目录，不入库）：`/private/tmp/claude-501/-Users-liu-Desktop-FYP-In-Cabin-Driver-Assessment--1--claude-worktrees-exciting-keller-fdf913/a1949e26-b3d7-4f7f-bd9f-059bf8cb6f0e/scratchpad/`（`mutlib.py` 为一次一条变异的执行器，`m1.py`–`m7.py` 为各批变异；隔离副本路径记在同目录 `mutdir.txt`）
- 手工核对用的一次性库与 sink：同目录 `e2e/`

## 9. 下一项依赖

- **Task 8（有界重试）依赖本项提供的**：`X-Attempt-Index` 请求头（从 1 开始，1 = 首发；缺省 1；非法 → 422，不可重试）；500 `model_runtime` / `storage` 可重试、503 `models_unavailable` 不可重试、409 的两种成因（hash 冲突 vs 乱序）在 fault 行里是不同类别；`GET /api/faults?session_id=…` 与 `SystemStatusOut.open_fault_events` 可作为「停止态」面板与对账的数据源；恢复语义（新提交一条记录即恢复，重放不算）。
- **Task 8 需要自己决定的**：`exhausted` 与客户端侧 `transport_timeout` 如何上报（计划里的 `POST /api/faults` 尚未实现）；`retry()` 是否从 1 重新计数。
- **Task 10（端到端）可直接复用**：IT-OUTCOME-01 的 16 步脚本与两个分母的算法作为 logging ≥ 99% 的证据；`backend/logs/` 在 Live 端到端运行时会真的被写入，归档证据时注意该目录已被 git 忽略。
