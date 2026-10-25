# Task 7 第二轮跟进实现报告 —— 持锁后重放预检查、全局处理器保护、分类失败保留已知类别（G1–G3）

## 1. 任务编号与名称

- **TASK-7-FOLLOWUP2**：持锁后第二次重放预检查补测（G1）、全局处理器 `classify_exception` 调用路径补测（G2）、`str()` 失败时保留已知类别（G3）
- 工作树 `/Users/liu/Desktop/FYP2-Live-System`，分支 `fyp2/live-system`，基线 HEAD `c4926b3`（开工前已核实分支与 HEAD；工作树干净）
- 对应 brief：`.superpowers/sdd/2026-10-12-fyp2-live-system-completion/task-7-followup2-brief.md`；前序报告 `docs/fyp2/implementation/task-07.md`、`task-07-followup.md`
- 范围外、零改动：`backend/app/routers/windows.py`、`backend/app/routers/faults.py`、前端、`ai/src`、`conftest.py`、`docs/fyp2/review/`、模型文件、任何真实数据库

## 2. 实现状态

**DONE_WITH_CONCERNS。** 三件事全部完成，四道门禁 0 失败；brief 的 W1–W5 全部在隔离副本里变红。concerns 见第 7 节，需要知情的三条：

- **W3（R11）只在 `[classifier-bug]` 这一个参数上变红，在 `[unprintable-error]` 上存活。** 这是 G3 的直接后果：`str()` 失败现在在 `_cause_text` 内部被吸收，`_classify` 对「`__str__` 抛错」的异常不再抛出，于是「全局处理器用 `classify_exception`」与「用 `_classify`」对这类输入行为等价。我用实测证明了这一点（5.3），并为 G2 补了一个「分类本身失败」的参数让 W3 变红。
- **brief 之外新增了 2 个路由层回退测试。** G3 把保护前移后，第一轮的 F3 测试不再触达 `classify_exception` 的外层「整体回退」，去掉外层回退的变异（W7）在改写后的 F3 测试下存活。为不丢这份覆盖，补了 2 个测试（见 4.3）。
- **G1 测试多了一条 `held_lock` 断言（brief 之外）**，因为 `db.rollback()` 被去掉的变异（W12）在 brief 要求的断言下存活。

| 项 | 状态 |
|---|---|
| G1 持锁后第二次 `_existing_request` 命中的分支：返回已存记录、不恢复 fault、不触发融合 / 提交 | 完成（1 个新测试） |
| G2 全局处理器 `on_unhandled_exception` 经 `classify_exception` 记录：恰好一行 fault、响应仍 500、原始异常向上传播 | 完成（1 个测试 × 2 参数） |
| G3 `str()` 失败只丢原因文本，保留 `FaultHTTPException` 自带的 category / origin / status / retryable；占位 `Unprintable <TypeName>`；仅类型无法分类才回退 `unknown` | 完成（实现 + 2 个已有测试的断言更新 + 2 个新的回退测试） |

## 3. 创建 / 修改的文件

| 文件 | 说明 |
|---|---|
| `backend/app/faults.py`（改） | `_cause_text` 内加 `try/except Exception`，失败时 `logger.exception` 并返回 `Unprintable <TypeName>`；`classify_exception` 文档字符串改写为「两层」说明。**函数体与外层 `try/except` 不变** |
| `backend/tests/test_fault_events.py`（改） | 新增 5 个测试用例（4 个测试函数，其中 1 个参数化 ×2）+ 2 个辅助函数；更新 2 个已有测试函数的断言（其中 1 个重命名）；新增 `NativeRuntimeError` 测试异常类。无已有测试被删除 |
| `docs/fyp2/implementation/task-07-followup2.md`（新） | 本报告 |

没有改 `routers/faults.py` 与 `routers/windows.py`：G2 的目标调用 `faults.classify_exception(exc)` 已经存在；G1 不需要为测试改实现。

## 4. 实现摘要

### 4.1 G1：持锁后的第二次重放预检查

`_persist_window` 拿到写锁（`UPDATE … next_window_id`）之后会再查一次重放，命中则 `db.rollback(); return existing`。

**辅助 `blind_to_the_twin_on_the_first_check_only(monkeypatch)`**（`blind_to_the_twin` 的变体）：只让第 1 次 `_existing_request` 调用看不见孪生，第 2 次正常。它**仍然调用真实函数**再决定返回什么，并记录日志 `(真实答案是否命中, 返回答案是否命中)`——这样盲掉的第 1 次也能证明「孪生当时确实在库里」，测试不会因为孪生根本不存在而空过。

**测试 `test_a_twin_found_by_the_check_under_the_writer_lock_is_a_replay_and_recovers_nothing`**：

1. winner 成功提交；之后再制造一行 open fault（winner 提交**之后**，所以不会被 winner 恢复）。
2. 开启「只盲第一次」，重发 winner 的请求（`X-Attempt-Index: 2`）。
3. 断言：
   - 201，响应体与 winner 完全相同，`window_id` 相同；
   - 调用日志恰为 `[(True, False), (True, True)]`：**两次检查都能看见孪生，只有第一次被盲掉，且没有第三次**（第三次是 F4 里 `IntegrityError` 之后的回读）；
   - `inference.run_inference` 一次都没被调用（`fused == []`）：在融合和提交之前就应答了；
   - 请求会话在 `_persist_window` 返回时不在事务中（`held_lock == [False]`）：写锁已归还；
   - `inference_records` 里该 `request_id` 恰好一行；
   - `faults_of(live) == [opened]`：该 fault 行逐字段不变，仍是 `open`；`open_fault_events` 仍为 1；
   - 对照：随后提交一条真正的新记录，同一行变为 `recovered`、计数归 0——证明这个场景下若有人调了 `mark_recovered`，测试看得见。

`fused == []` 的存在理由：把整个第二次检查删掉（W6）时，请求会走 `IntegrityError` 路径，调用日志与最终响应都和正常路径相同；只有融合是否被调用能把两者区分开。

### 4.2 G2：全局处理器的分类保护

**构造方法（brief 要求写明）。** `infer_frame` 的 `try/except` 只包住路由函数体。FastAPI 在调用路由函数**之前**先解析依赖，所以让依赖 `get_db` 的覆盖函数在第一次被调用时抛错，异常就从路由函数外面离开应用：路由函数从未进入，其 `except` 块不会运行，只有 `on_unhandled_exception` 能记录它。辅助 `break_get_db_once(error)` 包装 `app.dependency_overrides[get_db]`：待抛错误队列非空时先抛，之后（包括全局处理器自己为写 fault 再次解析 `get_db` 时）才委托给真实的临时库。它返回待抛队列，测试可再次追加以第二次触发。

没有选「响应校验失败」做触发，因为那依赖 pydantic 内部行为；依赖抛错只依赖 FastAPI「先解依赖、后进路由」这一约定，且 `pending == []` 断言证明依赖确实是抛出者。

**测试 `test_the_global_handler_records_an_error_that_never_reached_the_route`**，参数 `how`：

| 参数 | 触发 | 期望的 fault 行 |
|---|---|---|
| `unprintable-error` | `NativeRuntimeError`（`__str__` 抛 `RuntimeError`），真实分类器 | `unknown` / `unknown` / 500 / 不可重试，detail `Unexpected error; cause: Unprintable NativeRuntimeError` |
| `classifier-bug` | 普通 `ValueError`，`faults._classify` 被替换为抛 `RuntimeError`（分类自身出错） | `unknown` / `unknown` / 500 / 不可重试，detail `Unclassifiable ValueError` |

每个参数都做两次请求：
- 严格客户端（`raise_server_exceptions=True`）：`pytest.raises(type(original))`，且 `caught.value is original`（原始异常，不是分类器的错误）；此时库里**恰好 1 行**；
- 普通客户端：500 + 纯文本 `Internal Server Error`；此时库里**恰好 2 行**（`attempt_index` 为 `[1, 2]`），sink 恰好 2 行，`inference_records` 为 0。

两个请求靠 `X-Attempt-Index`（1 与 2）区分；路由未进入，所以 `fault_context` 未设置，`request_id` 为 NULL，这是此路径的本质，我没有把它断言成契约。

**为什么需要两个参数（W3 的等价性）。** 见 5.3 与第 7 节第 1 条：只用 `unprintable-error` 时，G3 之后 W3 是等价变异。

### 4.3 G3：`str()` 失败时保留已知类别

**实现**（`faults.py`）：

- `_cause_text` 是分类里**唯一**执行别人代码（别人的 `__str__`、`orig` 属性）的一步。现在它自己带 `try/except Exception`：失败时 `logger.exception(...)` 并返回 `Unprintable <TypeName>`。
- `FaultHTTPException` 的 category / origin / status 来自属性，`retryable` 来自 `RETRYABLE[category]`，都不依赖 `str()`，所以现在照常保留。
- `classify_exception` 的外层 `try/except` 原样保留，只剩「类型本身无法分类」这一种情形才回退 `unknown` / 不可重试 / 原响应状态。

**更新的已有测试（逐条）：**

| 测试 | 改动 | 原因 |
|---|---|---|
| `test_a_classifier_failure_never_replaces_the_original_exception`（名字不变） | 断言 `"Unprintable" in row["detail"]` → `row["detail"] == "Unexpected error; cause: Unprintable Unprintable"`。其余断言（原始异常 `is`、`unknown`/`unknown`/500/False/`open`、sink 恰好 1 行、无记录）**不变** | 普通异常本来就是 `unknown`，类别不受影响；变的是 detail：不再是 `Unclassifiable Unprintable`，而是占位文本。原断言只是子串，W4/W5 下仍可能为真，收紧为全等才能钉住占位格式 |
| `test_a_classifier_failure_keeps_the_original_http_response` → 重命名为 `test_an_unprintable_cause_keeps_the_known_category_and_the_original_http_response` | ① 参数化增加 `expected` 列；② `model-runtime-500` 的期望从 `("unknown","unknown",500,False)` 改为 `("model_runtime","vision_model",500,True)` + detail `Vision model failed during inference; cause: Unprintable NativeRuntimeError`；③ `session-conflict-409` 的期望从 `("unknown","unknown",409,False)` 改为 `("mode_conflict","session",409,False)` + detail `Create a live model session first; cause: Unprintable NativeRuntimeError`；④ 新增 `recovery_status == "open"`；⑤ 导致不可打印的原因由 `Unprintable` 换成其子类 `NativeRuntimeError`。**HTTP 响应断言（状态码与 JSON 体）不变** | ②③ 是 brief 要求的方向（brief 只点名了 `model-runtime-500`；`session-conflict-409` 用的是同一个共享期望，同样钉着旧行为，必须一并改）。⑤ 让类型名与占位词 `Unprintable` 区分开，W5（占位丢掉类型名）才能被 detail 全等断言抓住。重命名是因为旧名「分类器失败」已不真实：分类器不再失败 |

**新增的回退测试（brief 之外，必要）：** G3 之后，原 F3 的三个测试都不再经过 `classify_exception` 的外层回退（W7 在改写后的 F3 测试下存活，实测见 5.3）。要保住这层保护，补了：

- `test_an_http_error_the_classifier_does_not_know_is_unknown_with_the_status_the_client_got`：`_run_models` 抛 `FaultHTTPException(409, …, error_category="not-a-category")`（`RETRYABLE` 查不到，分类失败）。响应仍是 409 JSON；fault 为 `unknown`/`unknown`/**409**/False，detail `Unclassifiable FaultHTTPException`（状态是客户端实际拿到的 409，不是写死的 500）。
- `test_a_classifier_bug_never_replaces_the_original_exception`：`faults._classify` 抛错 + provider 抛 `ValueError`。严格客户端拿到的是 `ValueError`（`is original`），不是分类器的 `RuntimeError`；fault 为 `unknown`/`unknown`/500/False，detail `Unclassifiable ValueError`，sink 恰好 1 行。

## 5. 执行的测试（精确命令）

### 5.1 四道门禁（真实工作树，最终代码）

```
cd /Users/liu/Desktop/FYP2-Live-System
export PYTHONDONTWRITEBYTECODE=1
(cd backend && TMPDIR=$(mktemp -d) PYTHONPATH=. ../.venv/bin/python -m pytest tests -q -p no:cacheprovider)
./node_modules/.bin/vitest run --no-cache
./node_modules/.bin/tsc --noEmit
./node_modules/.bin/eslint .
```

实测：`584 passed, 1 warning in 6.27s`；`Test Files 16 passed (16) / Tests 427 passed (427)`；`tsc exit=0`；`eslint exit=0`。开工前在同一 HEAD 复现基线：`579 passed, 1 warning in 7.76s`。只跑本文件：`… pytest tests/test_fault_events.py -q -p no:cacheprovider` → `59 passed`（原 54）。跑完后 `backend/logs/` 仍不存在；`git status` 只有 `faults.py` 与 `test_fault_events.py` 两个已修改文件。

### 5.2 隔离副本的建法

```
D=$(mktemp -d) && git -C /Users/liu/Desktop/FYP2-Live-System archive HEAD | tar -x -C "$D" && ln -s /Users/liu/Desktop/FYP2-Live-System/.venv "$D/.venv"
```

`HEAD` 不含本项尚未提交的改动，所以随后把 `faults.py` 与 `test_fault_events.py` 覆盖进副本（`diff -rq backend "$D/backend"` 无差异）。副本：`/var/folders/0k/dtzqmkm53vqgg530vd7h3fmr0000gn/T/tmp.HPmavXPzTT`；没有 `.git`、没有模型文件，副本全量基线 `577 passed, 7 skipped`（7 个是已有的 `requires_models` 用例；577 = 584 − 7）。每次变异：只改副本里的一处、跑**整个** `tests/`、从真实树还原、`filecmp` 确认逐字节一致（每次输出 `restored identical to real tree: True`）。真实工作树没有被变异。

### 5.3 变异验证（全部在隔离副本里，每次跑整个 `tests/`）

**brief 指定的 W1–W5**

| # | 变异 | 观察到的结果 |
|---|---|---|
| W1 | R15：第二次检查的分支改成 `raise RuntimeError('R15')` | **1 失败**：G1 测试。证据：`assert 500 == 201`（`AssertionError: Internal Server Error`） |
| W2 | R13：`return existing` 之前调 `faults.mark_recovered(db, sid, request_id)` | **1 失败**：G1 测试。证据：`faults_of(live) != [opened]`，那行 fault 变成 `recovery_status: 'recovered'`、`recovered_by_request_id: 'twin-4'` |
| W3 | R11：`on_unhandled_exception` 里 `classify_exception(exc)` → `faults._classify(exc)` | **1 失败**：`test_the_global_handler_records_an_error_that_never_reached_the_route[classifier-bug]`，库里 0 行（`[] == [(… 'Unclassifiable ValueError' …)]`）。**`[unprintable-error]` 参数存活**：单独运行 `-k "never_reached_the_route and unprintable"` 在 W3 下 `1 passed` |
| W4 | 恢复第一轮的整体回退：去掉 `_cause_text` 的保护，任何 `str()` 失败都落到外层 `unknown` | **4 失败**：`…never_replaces_the_original_exception`、`…keeps_the_known_category…[model-runtime-500]`、`…[session-conflict-409]`、`…never_reached_the_route[unprintable-error]`。例：`'unknown' != 'model_runtime'` |
| W5 | 占位文本丢掉类型名（`return "Unprintable"`） | **4 失败**，与 W4 同一组。例：`'… cause: Unprintable' != '… cause: Unprintable NativeRuntimeError'` |

**补充变异（brief 表之外，用于核对每条新断言都有守护者）**

| # | 变异 | 观察到的结果 |
|---|---|---|
| W6 | 整个第二次检查（4 行）删掉，让 `IntegrityError` 路径接手 | **4 失败**：G1 测试，外加 3 个已有的并发孪生测试（它们的「盲两次」窗口以第二次检查存在为前提；删掉后 `IntegrityError` 的回读落进盲区，请求回 500，测试在 `response.json()` 处抛 `JSONDecodeError`）。G1 测试的证据：`fused == []` 处 `[1] == []`，即最终响应与正常路径相同，只有融合是否被调用能区分 |
| W7 | `classify_exception` 去掉外层 `try/except`（`return _classify(exc)`） | **3 失败**，恰为新增的回退测试 ×2 + G2 `[classifier-bug]`；改写后的 F3 测试**全部存活**——这就是需要新增回退测试的实证 |
| W8 | 回退的 `http_status` 写死 500 | **1 失败**：`…does_not_know_is_unknown_with_the_status_the_client_got`（`500 != 409`） |
| W9 | 回退 `retryable=True` | **3 失败**（同 W7 的三个） |
| W9b | 回退 `origin=storage` | **3 失败**（同上） |
| W9c | 回退 `error_category=storage` | **3 失败**（同上） |
| W10 | 回退 detail 丢掉类型名 | **3 失败**（同上） |
| W11 | 路由里 `classify_exception(exc)` → `faults._classify(exc)` | **2 失败**：`…does_not_know…`、`…classifier_bug_never_replaces…`（证据：`ValueError: provider broke` 被 `RuntimeError: a bug in the classifier` 顶替） |
| W12 | 第二次检查的分支去掉 `db.rollback()` | brief 要求的断言下**存活**（`1 passed`）；加了 `held_lock` 断言后 **1 失败**（`[True] == [False]`） |
| W13 | 全局处理器永不记录（`if False:`） | **3 失败**：G2 两个参数 + 已有的 `test_a_stray_exception_outside_the_route_is_recorded_once`——证明 G2 的触发确实走到了全局处理器 |
| W16 | 第二次检查吞掉 409（`except FaultHTTPException: existing = None`），让 `IntegrityError` 路径之后再应答 | **存活**（`577 passed`）。见第 7 节第 4 条 |

## 6. PASS / FAIL / SKIP 计数

| 门禁 | 基线（`c4926b3`） | 本项之后 | 变化原因 |
|---|---|---|---|
| pytest（真实树，模型经符号链接可用） | 579 passed | **584 passed / 0 failed / 0 skipped** | **+5**，全部来自 `test_fault_events.py`：G1 +1；G2 +2（`unprintable-error`、`classifier-bug` 两个参数）；G3 回退测试 +2（`…does_not_know_is_unknown…`、`…classifier_bug_never_replaces…`）。2 个已有测试函数被更新断言（其中 1 个重命名），**用例数不变**；没有任何测试被删除 |
| pytest（隔离副本，无模型） | 572 passed / 7 skipped | 577 passed / 0 failed / **7 skipped** | 同上 +5；7 个 skip 仍是已有的 `requires_models` 用例 |
| `test_fault_events.py` 单文件 | 54 passed | **59 passed** | +5 |
| vitest | 427 passed | **427 passed**（16 个文件） | 本项不碰前端 |
| `tsc --noEmit` | 0 错 | 0 错 | — |
| `eslint .` | 0 问题 | 0 问题 | — |

## 7. 遗留问题

1. **W3 对 `__str__` 抛错的异常是等价变异（G3 的直接后果）。** brief 的 W3 写的是「必须变红 G2」。G3 把 `str()` 的保护放进 `_cause_text`（brief 要求「只保护取原因文本这一步」）之后，`_classify` 对 `__str__` 抛错的异常不再抛出；而能到达全局处理器的只有非 `HTTPException`（`HTTPException` 会被 Starlette 的 `ExceptionMiddleware` 当响应处理），其 `_classify` 里唯一依赖 `str()` 的就是原因文本。所以对 `unprintable-error`，`classify_exception` 与 `_classify` 行为一致，W3 不可能被它杀死（5.3 已实测）。我保留了 `unprintable-error` 参数（它钉住 G3 后整条处理器路径的结果：一行、500、原始异常、占位 detail，W4/W5/W13 都会让它变红），并增加 `classifier-bug` 参数（用注入的分类器故障）去守住 W3。若评审要求 W3 必须被 `__str__` 抛错的异常本身杀死，那需要把 `_classify` 改成对 `str()` 失败仍抛出、再由外层二次重试，与 brief 对 G3 的描述（「只保护取原因文本这一步」）冲突，我没有那样做。
2. **回退的 detail 与占位的信息量。** 占位 `Unprintable <TypeName>` 只带类型名，不带原因的消息文本（能抛错的正是 `str()`）；完整回溯在 `app.faults` 日志里（`logger.exception`）。`FaultHTTPException` 本身的 `detail`（`str(exc.detail)`）仍未被单独保护——它是路由自己写的字符串，不是外来代码的输出。
3. **G2 的触发依赖 FastAPI「先解依赖、后进路由函数」的约定**，并假设 `get_db` 在 `infer_frame` 里是依赖。这是 FastAPI 的稳定行为；若将来 `infer_frame` 不再依赖 `get_db`，`pending == []` 断言会第一个变红，而不是静默空过。此路径上 `request_id` 为 NULL（路由未进入、`fault_context` 未设置）。
4. **持锁后的第二次检查在「输入不同」（409）情形下没有直接测试。** W16 存活：吞掉第二次检查里的 409 后，请求会多做一遍融合，再由 `IntegrityError` 路径回读并给出同样的 409 与同样的一行 fault，可观察结果等价，只是浪费了推理工作。这超出本项 brief（brief 只要求重放命中的分支），故未补。
5. **旧报告 `task-07-followup.md` 第 7 节第 1 条**（「该处理器那条路径没有专门的测试」）现已过时；按「历史报告不改」处理，以本报告为准。

## 8. 证据路径

- 本报告：`/Users/liu/Desktop/FYP2-Live-System/docs/fyp2/implementation/task-07-followup2.md`
- 实现：`/Users/liu/Desktop/FYP2-Live-System/backend/app/faults.py`（`_cause_text`、`classify_exception` 文档字符串）
- 测试：`/Users/liu/Desktop/FYP2-Live-System/backend/tests/test_fault_events.py`（F3 一节的 `NativeRuntimeError` 与两个已更新的测试；文件末尾「Task 7 follow-up 2 (TASK-7-FOLLOWUP2): G1-G3」一节）
- 变异执行器与副本路径（会话临时目录，不入库）：`/private/tmp/claude-501/-Users-liu-Desktop-FYP-In-Cabin-Driver-Assessment--1--claude-worktrees-exciting-keller-fdf913/a1949e26-b3d7-4f7f-bd9f-059bf8cb6f0e/scratchpad/followup2_mut.py`（`python followup2_mut.py W3 -k "…"` 之类；`MUTATIONS` 字典即上表全部变异的原文）与同目录 `followup2_mutdir.txt`；副本本身在 `/var/folders/0k/dtzqmkm53vqgg530vd7h3fmr0000gn/T/tmp.HPmavXPzTT`

## 9. 下一项依赖

- **Task 8（有界重试）**：服务端对分类的约定现在是三档——已知异常按其自带的 category / origin / status / retryable 记录（原因文本不可打印时 detail 里是 `Unprintable <TypeName>`）；纯 `str()` 失败的普通异常是 `unknown` / 不可重试 / 500；只有无法分类的异常才是 `unknown` / 不可重试 / 原响应状态，detail 为 `Unclassifiable <TypeName>`。客户端若镜像 `classifyFailure`，一个打印不出来的原生库异常经 `ModelRuntimeError` 包装成的 500 `model_runtime` 现在记为**可重试**（此前错记为不可重试的 `unknown`），与 D02 一致。
- 无其他依赖本项的后续 Task；本项不改变任何对外契约（响应体、字段、状态码），只改变 fault 行里 `str()` 失败那一类的 category / retryable / detail。
