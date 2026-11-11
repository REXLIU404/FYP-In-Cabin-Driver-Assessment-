# Task 7 跟进实现报告 —— 评审遗留的 5 个 Minor（F1–F5）

## 1. 任务编号与名称

- **TASK-7-FOLLOWUP**：`X-Attempt-Index` 上界（F1）、sink 默认路径测试（F2）、`classify_exception` 保护（F3）、并发孪生路径「重放不算恢复」补测（F4）、`record_fault` 独立 session 与事务补测（F5）
- 工作树 `/Users/liu/Desktop/FYP2-Live-System`，分支 `fyp2/live-system`，基线 HEAD `6e8039c`（开工前已核实分支与 HEAD；工作树干净）
- 对应 brief：`.superpowers/sdd/2026-10-12-fyp2-live-system-completion/task-7-followup-brief.md`；前序报告 `docs/fyp2/implementation/task-07.md`
- 范围外、零改动：前端、`ai/src`、`backend/app/routers/faults.py`、`conftest.py`、其余全部文件、`docs/fyp2/review/`、模型文件、任何真实数据库

## 2. 实现状态

**DONE_WITH_CONCERNS。** 5 件事全部完成，四道门禁 0 失败；brief 的 V1–V5 全部在隔离副本里变红，且恰好落在对应的新测试上。concerns 见第 7 节，需要知情的两条：

- F3 的保护放在 `faults.classify_exception` **内部**（让它永不抛出），而不是在 `windows.py` 的调用处包 try/except。行为等价，且同时保护了 `routers/faults.py::on_unhandled_exception` 里的另一处调用——那个文件不在本项允许修改的范围内，无法在调用处补。
- 变异 V1e（把 `faults.MAX_ATTEMPT_INDEX` 改成 999，路由的 `le=1000` 不变）**一度存活**，我据此给 F1 的边界测试补了一步（`X-Attempt-Index: 1000` 配合 schema 422），之后被杀死。见 5.3。

| 项 | 状态 |
|---|---|
| F1 `Header(1, ge=1, le=1000)`；`parse_attempt_header` 同界；越界 → 422 + 恰好一行 fault（`attempt_index` 为 NULL） | 完成 |
| F2 断言 monkeypatch 之前的 `DEFAULT_SINK_PATH` 恰为 `backend/logs/fault_events.log` 且被 git 忽略；不写该路径 | 完成 |
| F3 分类失败 → 回退 `unknown` / 状态与原响应一致 / 不可重试；原始异常原样抛出 | 完成 |
| F4 open fault 存在时走并发孪生路径，fault 仍为 `open`，`open_fault_events` 不变 | 完成 |
| F5 请求 session 不可用（`execute`/`commit` 抛错，`get_bind()` 正常）时 fault 仍写进同一库 | 完成 |

## 3. 创建 / 修改的文件

| 文件 | 说明 |
|---|---|
| `backend/app/faults.py`（改） | 新增 `MAX_ATTEMPT_INDEX = 1000`；`parse_attempt_header` 改为 `1 <= value <= MAX_ATTEMPT_INDEX`；`classify_exception` 变为永不抛出的外壳，原函数体改名 `_classify`；新增 `_response_status` |
| `backend/app/routers/windows.py`（改） | `Header(1, ge=1, le=1000, alias="X-Attempt-Index")`；两处注释（说明 `le=1000` 与 `faults.MAX_ATTEMPT_INDEX` 同值、`classify_exception` 永不抛出）；无其他改动 |
| `backend/tests/test_fault_events.py`（改） | 新增 11 个用例（7 个测试函数，其中 2 个参数化）；新增 `os` / `shutil` / `subprocess` 三个 import；已有测试的一行注释由「the server imposes no upper bound」改为「no retry budget on the server (only the 1000 sanity bound, tested below)」——该注释因 F1 变得不实，**没有改动任何已有断言** |
| `docs/fyp2/implementation/task-07-followup.md`（新） | 本报告 |

## 4. 实现摘要

### F1：`X-Attempt-Index` 上界

- 路由 `le=1000`：超界时 FastAPI 在进入路由体之前就回 422，由已有的 `RequestValidationError` 全局处理器记录。
- 处理器是用 `parse_attempt_header(request.headers[...])` 自己解析请求头的，所以 `parse_attempt_header` **必须同界**，否则 1001 会以 `attempt_index = 1001` 入库，而不是 brief 要求的 NULL。为此新增 `faults.MAX_ATTEMPT_INDEX = 1000`。`windows.py` 里保留字面量 `le=1000`（brief 的写法，也便于对照变异 V1），两处数字的一致性由测试钉死（V1b、V1c、V1d、V1e 四条变异分别守护两侧）。
- 超大数字串（例如 5000 位）会被 Python 的整数转换上限抛 `ValueError`，同样落到 `None`，已用直接调用核对。
- 这是 sanity 上界，不是重试预算（预算属于客户端，Task 8）。

### F2：生产默认 sink 路径

`conftest.py` 的 autouse 夹具对每个测试都重定向 `DEFAULT_SINK_PATH`，所以没有测试见过真实默认值。新测试只依赖那一个 autouse 夹具，开头调 `monkeypatch.undo()` 取回模块真正定义的值，然后：

1. 断言它等于 `Path(__file__).resolve().parents[1] / "logs" / "fault_events.log"`（期望值由**测试文件自己的位置**与字面量构造，不 import 实现的常量），并断言 `parts[-3:] == ("backend", "logs", "fault_events.log")`。
2. 在 `tmp_path` 里 `git init` 一个一次性仓库，只拷入项目根的 `.gitignore`，用 `git check-ignore -v` 检查该路径（相对仓库根）被忽略，且命中规则含 `backend/logs/`。用一次性仓库而不是真仓库，是因为隔离副本由 `git archive` 产生、**没有 `.git`**；这样测试在两种环境里都能跑。`git` 以 `GIT_CONFIG_GLOBAL=/dev/null`、`GIT_CONFIG_NOSYSTEM=1`、`-c core.excludesFile=/dev/null` 调用，用户的全局忽略规则不可能让它假通过。
3. 对照组：`backend/fault_events.log`（V2 变异落到的位置）必须**不**被忽略（退出码 1），证明检查本身能说「不」。

测试不调用任何会写 sink 的代码；跑完整套门禁后 `backend/logs/` 仍不存在（已核实）。

### F3：`classify_exception` 永不抛出

- `classify_exception(exc)` 现在是 `try: return _classify(exc) / except Exception: ...` 的外壳。分类失败时返回 `FaultClass(origin="unknown", error_category="unknown", http_status=<原响应状态>, retryable=False, detail="Unclassifiable <异常类型名>")`，并 `logger.exception` 记一笔。
- 「原响应状态」由 `_response_status` 给出：`HTTPException` 取其 `status_code`，其他一律 500（即客户端实际拿到的裸 500）。
- 回退的 `detail` 只含**类型名**，不含 `str(exc)`——能抛错的正是 `str()`。
- 路由 `except` 块里的 `raise` 不变，原始异常原样向上；分类失败不再顶替它。
- 为什么放在 `classify_exception` 里而不是调用处：另一处调用 `routers/faults.py::on_unhandled_exception` 被外层 `try/except` 包着，分类失败时会被吞掉，该次尝试**没有 fault 行**（同样违反 C8）。那个文件不在允许修改范围内；让分类器本身永不抛出，两处调用同时受保护。

三个测试覆盖三种形态：

| 用例 | 构造 | 断言 |
|---|---|---|
| 原始异常原样抛出 | provider 的 `infer` 直接 `raise Unprintable(...)`（`__str__` 抛 `RuntimeError`）；严格客户端 | `pytest.raises(Unprintable)` 且 `caught.value is original`；恰好一行 `unknown`/`unknown`/500/`retryable=False`/`open`；detail 含 `Unprintable`；sink 恰好一行（全局处理器没有补记第二次）；无记录 |
| 模型运行期 500 | `vision.fail = Unprintable(...)`，`trained.py` 包成 `ModelRuntimeError`，路由再包成 500 `FaultHTTPException`，根因不可打印 | 响应仍是原来的 `500 {"detail": "Vision model failed during inference"}`；fault 为 `unknown`/`unknown`/500/False |
| 状态与原响应一致 | `_run_models` 抛 409 `FaultHTTPException … from Unprintable(...)` | 响应仍是 `409 {"detail": ...}`；fault 的 `http_status == 409`（不是写死的 500） |

### F4：并发孪生路径不算恢复

沿用 IT-FAULT-INTEGRITY 的 `blind_to_the_twin`（让前两次重复检查「看不见」孪生记录，由真实唯一索引在 `commit` 时触发 `IntegrityError`）。顺序：`winner` 成功 → 再制造一行 open fault（在 winner 提交**之后**，所以不会被 winner 恢复）→ 开启孪生模拟 → 重发 winner 的请求（`X-Attempt-Index: 2`）。断言：返回 winner 的记录；`_existing_request` 恰被调用 3 次（走了 `IntegrityError` 读回）；`faults_of(live) == [opened]`，即该行**逐字段**与之前相同（仍 `open`，`recovered_by_request_id` / `recovered_at` 仍为 NULL）；`open_fault_events == 1`。末尾加一步对照：再提交一条真正的新记录，同一行 fault 变为 `recovered`、计数归 0——证明这个场景里「如果有人调了 `mark_recovered`，测试看得见」。孪生模拟用 `with monkeypatch.context()` 限定作用域；我最初写成 `monkeypatch.undo()`，那会连带撤销 `live` 夹具对 `trained._provider` 的替身，对照步骤在真实树里会悄悄加载真实模型、在副本里变 503，属于「靠错误的原因通过」。已在跑变异之前发现并改掉。

### F5：`record_fault` 自己的 session 与事务

`UnusableRequestSession` 只有 `get_bind()`（返回真实库的 engine）能用，`execute` / `commit` 抛 `RuntimeError`，任何其他属性（`rollback`、`add`、`close` …）经 `__getattr__` 也抛错。直接调 `record_fault(UnusableRequestSession(bind), …)`，再用 `live.factory()` 的**新 session** 读回：恰好一行，所有字段等于传入值；sink 一行且 `db_written is True`（`stored` 只在整个 try 块——含 `with` 退出——成功后才为真）。

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

实测：`579 passed, 1 warning in 6.62s`；`Test Files 16 passed (16) / Tests 427 passed (427)`；`tsc exit=0`；`eslint exit=0`。开工前在同一 HEAD 复现基线：`568 passed, 1 warning in 7.45s`。只跑本文件：`… pytest tests/test_fault_events.py -q -p no:cacheprovider` → `54 passed`（原 43）。

### 5.2 隔离副本的建法

```
D=$(mktemp -d) && git -C /Users/liu/Desktop/FYP2-Live-System archive HEAD | tar -x -C "$D" && ln -s /Users/liu/Desktop/FYP2-Live-System/.venv "$D/.venv"
```

`HEAD` 不含本项尚未提交的改动，所以随后把 `faults.py`、`windows.py`、`test_fault_events.py` 三个文件覆盖进副本。副本在 `/var/folders/0k/dtzqmkm53vqgg530vd7h3fmr0000gn/T/tmp.YnEzU3jEyc`；没有 `.git`、没有模型文件。副本全量：`572 passed, 7 skipped`（7 个是已有的 `requires_models` 用例，预期内；572 = 561 + 11）。每次变异：改一处、跑**整个** `tests/`、从真实树还原、`filecmp` 确认与真实树逐字节一致（每次输出 `restored identical to real tree: True`）。真实工作树没有被变异。变异执行器与目录路径见第 8 节。

### 5.3 变异验证（全部在隔离副本里，每次跑整个 `tests/`）

**brief 指定的 V1–V5**

| # | 变异 | 观察到的结果 |
|---|---|---|
| V1 | 去掉 `windows.py` 的 `le=1000` | **4 失败**，恰为 F1 的 4 个越界用例。`1001-valid` 得到 `201`（断言 422）；`10-to-the-20-bad-frame` 库里**没有 fault 行**，日志为 `could not store fault event in the database; the sink keeps it`——即 brief 描述的 C8 违例本身 |
| V2 | X41：`DEFAULT_SINK_PATH` 改为 `parents[1] / "fault_events.log"` | **1 失败**：F2 测试，在路径相等断言处（`…/backend/fault_events.log == …/backend/logs/fault_events.log`） |
| V3 | 去掉 F3 的保护（`classify_exception` 直接 `return _classify(exc)`） | **3 失败**，恰为 F3 的 3 个用例。第一个：`RuntimeError: the original error cannot be printed` 顶替了 `Unprintable`（brief 描述的缺陷本身）；另两个：客户端拿到裸 500 纯文本，`response.json()` 抛 `JSONDecodeError`，而不是原来的 JSON 错误响应 |
| V4 | X30：孪生路径 `return twin` 之前调 `mark_recovered` | **1 失败**：F4 测试；该 fault 变成 `recovery_status: 'recovered'`、`recovered_by_request_id: 'twin-3'` |
| V5 | X32：`record_fault` 改走请求的 `db` | **1 失败**：F5 测试；`db.execute` 抛 `RuntimeError`，被 `record_fault` 吞掉，库里 0 行 |

**补充变异（每条断言各被至少一个变异守护）**

| 变异 | 结果 |
|---|---|
| V1b `parse_attempt_header` 去掉上界（路由 `le=1000` 保留） | 4 失败（4 个越界用例：处理器会以 1001 / 10²⁰ 入库而不是 NULL） |
| V1c `le=999` | 1 失败：`test_attempt_index_1000_is_the_last_accepted_value` |
| V1d `le=1001` | 2 失败：`1001-valid`、`1001-bad-frame` |
| V1e `MAX_ATTEMPT_INDEX = 999`（路由保持 `le=1000`） | **第一版测试下存活**（572 passed）：1000 只走了路由内的记录路径，没经过处理器的 `parse_attempt_header`。补了「1000 + schema 422 → `attempt_index == 1000`」一步后：1 失败（边界测试） |
| V2b 删除 `.gitignore` 里的 `backend/logs/` 行 | 1 失败：F2 测试（`status == 0` 处） |
| V2c `"logs"` 改成 `"log"` | 1 失败：F2 测试 |
| V3b 回退的 `http_status` 写死 500 | 1 失败：`session-conflict-409` 用例 |
| V3c 回退 `retryable = True` | 3 失败（F3 全部） |
| V3d 回退 `origin = storage` | 3 失败（F3 全部） |
| V3e 回退 `error_category = storage` | 3 失败（F3 全部） |
| V3f 回退 detail 不含类型名 | 1 失败：`…never_replaces_the_original_exception` |
| V5b 在 fault 提交之后对请求 session 调 `rollback()` | 1 失败：F5 测试（`db_written` 变 False，且任何对请求 session 的触碰都被 `__getattr__` 拦下） |

无法解释的存活变异：0。无等价变异。

## 6. PASS / FAIL / SKIP 计数

| 门禁 | 基线（`6e8039c`） | 本项之后 | 变化原因 |
|---|---|---|---|
| pytest（真实树，模型经符号链接可用） | 568 passed | **579 passed / 0 failed / 0 skipped** | **+11**，全部来自 `test_fault_events.py`：F1 越界用例 4（2 个值 × 2 种载荷）+ 1 个 1000 边界；F2 1；F3 1 + 2（参数化 2 个）；F4 1；F5 1。没有任何已有测试被删除、替换或改断言 |
| pytest（隔离副本，无模型） | 561 passed / 7 skipped | 572 passed / 0 failed / **7 skipped** | 同上 +11；7 个 skip 仍是已有的 `requires_models` 用例 |
| `test_fault_events.py` 单文件 | 43 passed | **54 passed** | +11 |
| vitest | 427 passed | **427 passed**（16 个文件） | 本项不碰前端 |
| `tsc --noEmit` | 0 错 | 0 错 | — |
| `eslint .` | 0 问题 | 0 问题 | — |

## 7. 遗留问题

1. **F3 的保护位置与 brief 字面不同。** brief 写的是在 `windows.py` 调用处包 try/except；我放进了 `classify_exception` 本身。可观察行为（brief 的全部断言）一致，并多保护了 `routers/faults.py::on_unhandled_exception`。该处理器那条路径**没有专门的测试**（不在本项范围，也没有简单办法让一个不可打印的异常越过路由的 `except` 到达它）；我只用直接调用核对过 `classify_exception(Unprintable())` 返回 `unknown/unknown/500/False`。
2. **回退的 detail 丢掉了原因文本。** 分类失败时 detail 只有 `Unclassifiable <类型名>`，比如 SQLAlchemy 的驱动消息就不在行里了。这是有意的（能抛错的正是 `str()`）；完整回溯在 `app.faults` 日志里。
3. **上界数字有两份**：`windows.py` 的字面量 `le=1000` 与 `faults.MAX_ATTEMPT_INDEX`。没有让路由引用常量，是为了与 brief 的变异描述逐字对应。漂移会被 V1b–V1e 对应的测试抓到，但仍是两份数字。
4. **F2 测试的前提。** ① 它调用 `monkeypatch.undo()`，因此只能与 autouse 夹具共存，不能再加 `live` / `api_factory`（已在测试里注释）。② 它需要 `git` 可执行文件；缺失时是**响亮失败**而不是 skip（skip 会让变异验证悄悄通过）。③ 只拷贝了根 `.gitignore`；仓库里 `backend/` 下唯一的嵌套 `.gitignore` 是 pytest 缓存目录自带的 `backend/.pytest_cache/.gitignore`（只管该目录自身；其余嵌套的在 `ml/`、`ml/experiments/`、`.superpowers/sdd/`，`find` 核实），所以结论与真实仓库一致，真实树里 `git check-ignore -v backend/logs/fault_events.log` 命中 `.gitignore:14:backend/logs/`。
5. **`parse_attempt_header` 行为变化**：1001 以上以前返回该整数，现在返回 `None`。只有全局处理器（schema 422 与漏网异常）调用它；路由内的 `attempt_index` 来自已校验的 `Header`，不受影响。
6. **brief「不做」清单**照旧：`GET /api/faults` 分页、`routers/status.py` 越界、不带请求头的重试折叠成一行（Task 8 必须发该头）——本项均未触碰。

## 8. 证据路径

- 本报告：`/Users/liu/Desktop/FYP2-Live-System/docs/fyp2/implementation/task-07-followup.md`
- 实现：`/Users/liu/Desktop/FYP2-Live-System/backend/app/faults.py`、`/Users/liu/Desktop/FYP2-Live-System/backend/app/routers/windows.py`
- 测试：`/Users/liu/Desktop/FYP2-Live-System/backend/tests/test_fault_events.py`（文件末尾「Task 7 follow-up (TASK-7-FOLLOWUP): F1-F5」一节）
- 变异执行器与副本路径（会话临时目录，不入库）：`/private/tmp/claude-501/-Users-liu-Desktop-FYP-In-Cabin-Driver-Assessment--1--claude-worktrees-exciting-keller-fdf913/a1949e26-b3d7-4f7f-bd9f-059bf8cb6f0e/scratchpad/followup_mut.py`（`python followup_mut.py V3` 之类；`MUTATIONS` 字典即上表全部变异的原文）与同目录 `followup_mutdir.txt`；副本本身在 `/var/folders/0k/dtzqmkm53vqgg530vd7h3fmr0000gn/T/tmp.YnEzU3jEyc`

## 9. 下一项依赖

- **Task 8（有界重试）**：`X-Attempt-Index` 现在有明确的合法区间 **1..1000**，超界是不可重试的 422（`input_validation`，`attempt_index` 为 NULL）。Task 8 的重试预算（3 次）远低于上界，无冲突；仍必须发送该请求头（否则失败会被折叠成一行）。
- `classify_exception` 现在永不抛出——Task 8 若在客户端侧镜像分类逻辑（`classifyFailure`），不需要为「分类失败」另设路径，但应知道服务端对分类失败的约定是 `unknown` / 不可重试 / 原状态码。
- 无其他依赖本项的后续 Task；本项不改变任何对外契约（响应体、字段、状态码），只收紧一个输入上界。
