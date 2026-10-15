# Task 10 第 1 部分 实现报告 —— 类型检查门禁、模型跳过显式化、导出守卫、freeze_manifest 严格化、分段计时、门禁原始日志（不含端到端）

## 1. 任务编号与名称

- **TASK-10-PART1**：计划 Task 10 的 Step 1、Step 3、Step 4，及「R4 追加（审阅 R02、R17、R31）」中不依赖 R10 的部分。brief 的 P1–P6：P1 类型检查门禁、P2 模型跳过显式化、P3 导出守卫（R31）、P4 `freeze_manifest.py` 不得静默回退、P5 分段计时、P6 门禁原始日志（R02）。
- 工作树 `/Users/liu/Desktop/FYP2-Live-System`，分支 `fyp2/live-system`，基线 HEAD `a0859bd`（开工前核实：分支与 HEAD 吻合，`git status --porcelain` 为空）。
- 基线门禁（开工前在同一 HEAD 复现）：pytest 704 passed / vitest 709 passed（24 个文件）/ tsc 0 / eslint 0，与 brief 一致。
- 本部分**没有**新建 `test_live_e2e.py`，没有启动 Playwright，没有启动 vite dev server，没有断言任何「≤ 1 s」，也没有产出任何性能结论。
- 零改动：融合 / FSM / EMA / freshness 逻辑、R10 相关的游标与观测身份、模型文件（门禁后用 `freeze_manifest.py` 复核，三个 SHA256 全部 MATCH，`Models unchanged vs frozen baseline: YES`）、`docs/fyp2/review/`、计划文件、主仓库。

## 2. 实现状态

**DONE_WITH_CONCERNS。** 四道门禁达标：pytest 774 passed / 0 failed / 0 skipped，vitest 750 passed，`tsc` 0 错，`eslint` 0 问题。P1–P6 全部落地。concerns 见第 7 节，最需要知情的五条：

1. **`liveLoop.ts` 不能 import `./liveTiming`**：既有的范围守卫 `frontend/src/data/preparedRawTelemetry.test.ts`（Task 9）把 `liveLoop.ts` 的 import 集合钉死为 `["./types"]`。我第一版直接 import 了缓冲实现，这个守卫变红。我没有改别人的守卫，改为**依赖注入**：接口（`WindowTiming`、`TimingInput`、`TimingRecorder`）声明在 `liveLoop.ts` 里，`LiveLoopDeps.timings` 是可选依赖，`useLiveSession` 注入 `createTimingBuffer()`。代价：不注入就不记录（默认关）。
2. **服务端的 `Server-Timing` 没有进前端缓冲**：前端缓冲的 `server` 字段目前恒为 `null`，TypeScript 的 `parseServerTiming` 目前只有单测在用。原因：`api/client.ts` 的 `infer` 只返回 body、丢弃响应头，而 `client.ts` 不在本项允许修改的范围内。第 2 部分的 Playwright 可以直接从网络响应读头。
3. **React 绑定层没有单测**：`markRendered` 的 effect 与 `window.__draLiveTimings` 访问器在 `useLiveSession.ts` 里，仓库没有 DOM 测试环境（计划已决定不引入 jsdom）。纯逻辑部分（缓冲、分段计算、循环里的记录）都有 node 环境单测；effect 本身要到第 2 部分的真实浏览器里验证。
4. **`run_gates.py` 的 `build` 门禁没有真跑**：`npm run build` 会调 vite，vite 加载配置时写 `node_modules/.vite-temp`，而 `node_modules` 是指向主仓库的符号链接。其余四项（pytest、vitest、tsc、eslint）通过 `run_gates.py` 真实跑通，全绿；`build` 只有 `--dry-run` 验证了 argv / cwd / 日志格式。
5. **一次变异事故**：我的变异 E9b（「dry-run 也执行门禁」）第一次被我指向了整个 `test_run_gates.py`，内含的「内置门禁列表」测试就真的在隔离副本里执行了五项真实门禁（含 `npm run build`，以及递归的 pytest）。进程被 600 s 超时终止，无残留进程。已知的副作用：主仓库 `node_modules/.vite-temp`（空目录）的 mtime 变成了当天 04:20，我无法判断它此前是否存在；目录内无文件，`.vite/deps`、`.vite/vitest` 的 mtime 未变。详见第 7 节。

| 项 | 状态 | 守护 |
|---|---|---|
| P1 类型检查门禁 | 完成 | `repoGuards.test.ts` 6 个；Q1、Q1b、E1a、E1b、E2 变红 |
| P2 模型跳过显式化 | 完成 | `test_model_gate.py` 8 个；Q2、E3、E4、E4b 变红 |
| P3 导出守卫 | 完成 | `test_export_guard.py` 6 个；Q3、Q4、Q4b、E5、E5b、E5c 变红 |
| P4 freeze_manifest 严格化 | 完成 | `test_freeze_manifest.py` 8 个；Q5、E6、E6b 变红 |
| P5 分段计时（后端 + 前端） | 完成 | `test_server_timing.py` 13 个 + `liveTiming.test.ts` 27 个 + `liveLoopTiming.test.ts` 8 个；Q6、Q7、E7 系列、E8 系列变红 |
| P6 门禁原始日志 | 完成（`build` 仅 dry-run） | `test_run_gates.py` 35 个；Q8、E9 系列变红 |

## 3. 创建 / 修改的文件

提交内含 19 个文件：7 个已跟踪文件修改（行数为 `git diff --numstat` 的新增 / 删除），11 个新文件，加本报告。

**实现**

| 文件 | 变化 |
|---|---|
| `package.json` | +2/−1：新增 `"typecheck": "tsc --noEmit"`，`"test"` 改为 `"npm run typecheck && vitest run"`（P1） |
| `backend/tests/conftest.py` | +78/−1：`pytest_runtest_makereport`（hookwrapper）与 `pytest_terminal_summary`；`DRA_REQUIRE_MODELS=1` 开关（P2） |
| `backend/app/routers/export.py` | +64/−12：`_decode_payload`、`_unreadable_record`；改按列 + 原始文本查询；CSV 追加两列（P3） |
| `scripts/freeze_manifest.py` | +29/−5：`DataRootError`；显式 `FYP_DATA_ROOT` 错误时退出码 2、stdout 为空（P4） |
| `backend/app/timing.py`（新，115 行） | `format_server_timing`、`SegmentTimer`、`ContextVar` 式的 `activate` / `measure` / `record_provider_timings`（P5 后端） |
| `backend/app/routers/windows.py` | +19/−7：`infer_frame` 注入 `Response`，成功时写 `Server-Timing`；`_persist_window` 里给 `fusion`、`commit` 计时；`_infer` 里取 provider 的分段（P5 后端） |
| `ai/src/liveTiming.ts`（新，186 行） | `segmentsOf`、`parseServerTiming`、`createTimingBuffer`（500 条环形缓冲）（P5 前端） |
| `ai/src/liveLoop.ts` | +94/−0：`WindowTiming` / `TimingInput` / `TimingRecorder` 接口、可选依赖 `timings`、`LiveLoop.getTimings()` / `markRendered()`；`PendingRequest.capturedAtMs`；成功投递后 `timings?.push(...)`。**游标、重试、分类、取消逻辑 0 行改动** |
| `frontend/src/hooks/useLiveSession.ts` | +26/−0：注入 `createTimingBuffer()`；`useEffect` 里 `markRendered`；`window.__draLiveTimings` 只读访问器 |
| `scripts/run_gates.py`（新，358 行） | 门禁运行器（P6） |

**测试**

| 文件 | 变化 |
|---|---|
| `ai/src/repoGuards.test.ts`（新，77 行） | 6 个（P1） |
| `backend/tests/test_model_gate.py`（新，149 行） | 8 个（P2） |
| `backend/tests/test_export_guard.py`（新，188 行） | 6 个（P3） |
| `backend/tests/test_freeze_manifest.py`（新，106 行） | 8 个（P4） |
| `backend/tests/test_server_timing.py`（新，170 行） | 13 个（P5 后端） |
| `ai/src/liveTiming.test.ts`（新，224 行） | 27 个（P5 前端纯逻辑） |
| `ai/src/liveLoopTiming.test.ts`（新，284 行） | 8 个（P5 循环接线，虚拟时钟） |
| `backend/tests/test_run_gates.py`（新，352 行） | 35 个（P6） |

**文档**：`docs/fyp2/implementation/task-10-part1.md`（本报告）。

未触碰：`ml/outputs/`、`docs/fyp2/review/`、计划文件、主仓库、任何数据库（所有测试用 tmp 库）、既有的任何测试文件。没有把真实运行产生的门禁日志写进仓库（`git status` 中 `docs/evidence` 条目数为 0）。

## 4. 实现摘要

### P1　类型检查门禁（计划 Step 1）

- `package.json`：`"typecheck": "tsc --noEmit"`；`"test": "npm run typecheck && vitest run"`。验证过链路：`npm run typecheck` 退出 0；`npm test -- --no-cache` 退出 0（tsc 后 vitest 27 个文件、750 个测试）；在隔离副本里故意植入类型错误后 `npm test -- --no-cache` 退出 2、vitest **未启动**、输出含 `TS2322`（E2）。
- vitest 的 include glob 保持只收 `*.test.ts`，没有引入 jsdom 或任何 npm 依赖。
- 新测试 `ai/src/repoGuards.test.ts`：(a) `typecheck` 脚本逐字等于 `tsc --noEmit`；(b) `test` 脚本第一步是 `npm run typecheck` 且之后有 `vitest run`；(c) 钉住 `vitest.config.ts` 的 include glob 两项；(d) 全仓库不存在 `*.test.tsx`；(e) 所有 `*.test.ts` 都在 `ai/src` 或 `frontend/src` 下（否则同样会被 glob 静默跳过）。(d)(e) 用 Vite 的 `import.meta.glob`（字面量模式，排除 `node_modules`、`.venv`、`dist`、`.git`、`.claude`、`.superpowers`），因为仓库没有 `@types/node`，不能用 `node:fs`。
- 另有一个自检用例：glob 本身能找到已知文件（Vite 的 glob 不返回调用它的文件自身，所以用相邻文件做哨兵）。

### P2　模型跳过显式化（计划 Step 3）

- `backend/tests/conftest.py`：
  - `pytest_runtest_makereport`（hookwrapper）识别「`skipif` 的 reason 等于 `local trained artifacts not installed`」的 setup 阶段跳过，记入名单；
  - `pytest_terminal_summary` 打印红色加粗的横幅：`N MODEL-DEPENDENT TEST(S) NOT RUN (models missing)`、缺失的模型文件、逐个 `SKIPPED  <nodeid>`；`-q` 下也会显示；
  - 环境变量 `DRA_REQUIRE_MODELS=1` 时，上述每个跳过在 makereport 里被改写为失败（pytest 把 setup 阶段的失败标成 `ERROR`），会话退出码 1。只有字面值 `1` 生效（`0`、空、`true`、`yes` 都不算）。
- 识别方式是 reason 文本，所以加了一个守卫测试：静态扫描 `backend/tests/test_*.py` 里所有提到 `MODEL_ROOT` / `ml/outputs` 的 `pytest.mark.skipif`，reason 必须逐字等于该文本（E4b：把 `test_unavailable_contract.py` 的 reason 改掉，守卫测试变红）。
- **在隔离副本里按 brief 的两种情况验证**（副本由 `git ls-files -co` 导出，无 `.git`、无 `node_modules`、无模型文件）：
  - 默认：`767 passed, 7 skipped`，退出码 0，汇总里是 `7 MODEL-DEPENDENT TEST(S) NOT RUN`，逐个列出 7 个 nodeid（`test_live_inference.py` 4 个，`test_unavailable_contract.py` 3 个，含 2 个参数化）；
  - `DRA_REQUIRE_MODELS=1`：`767 passed, 7 errors`，退出码 1。
- 真实工作树里模型齐全，汇总里没有横幅，0 skipped；在真实工作树里设 `DRA_REQUIRE_MODELS=1` 实跑：`774 passed`，退出 0，只打印一行 `DRA_REQUIRE_MODELS=1: no model-dependent test was skipped.`。
- 测试 `test_model_gate.py` 起一个**独立的 pytest 会话**（带着 `conftest.py` 的拷贝和一个 reason 相同、条件恒真的合成测试），所以不论本检出有没有模型，结果都一样。

### P3　导出守卫（R31）

- 原因：`routers/export.py` 的 JSON 分支是 `{**rec.payload, "flagged": ...}`，CSV 分支是 `rec.payload or {}`。payload 为 SQL NULL、不是合法 JSON（`JSON` 列类型在 ORM 加载时就抛异常）、或是合法 JSON 但不是对象时，都在**生成器内部、响应已经开始之后**才抛，客户端拿到的是截断的文件。
- 做法：查询改为 `db.query(window_id, flagged, type_coerce(payload, String))`，payload 以**原始文本**取回，由 `_decode_payload` 自己解码并返回 `(对象, None)` 或 `(None, 原因)`。原因共四类：`payload is NULL`；`payload is not valid JSON: <解码器消息>`；`payload is a JSON array|string|number|boolean|null, not an object`；以及字节不是 UTF-8。
- 坏行导出为最小记录：`session_id`、`window_id`、`flagged`、`RiskScore` / `RiskLevel` / `DominantEvidence` / `AlertSeverity` 四个**都是 null**、`payload_unreadable: true`、`payload_unreadable_reason`。四个风险字段**不**取自同一行旁边的类型化列（`risk_score` 等），因为那些列不保证描述这个 blob。不丢行，不伪造。
- CSV 的表头在末尾**追加**两列 `payload_unreadable`、`payload_unreadable_reason`（只追加、不插入，沿袭 Task 4 的做法；既有的 `ORIGINAL_COLUMNS` 前缀测试仍通过）。可读行这两格为空，坏行为 `true` 和原因。
- **好行字节不变**：JSON 里的可读行与改动前**逐字节相同**；CSV 的可读行等于改动前的行再加两个空格子（`,,`）。测试里的两个「黄金」字符串是我在隔离的 HEAD 副本（旧代码）上对同一 payload 实际导出得到的，不是从新代码推出来的。
- 测试在 tmp 库里直接写入 7 种坏行（SQL NULL、`{not json`、`[1, 2]`、`"just a string"`、`null`、`42`、非 UTF-8 的 BLOB `\xff\xfe`）和 3 个好行（其中一个是内容为合法 JSON 对象的 BLOB），各导出 JSON 与 CSV：断言 200、整份可解析、10 行不缺、顺序、每个坏行的标记 / 原因 / flagged / 四个 null、好行逐字节；另有一个「只有坏行的会话」和一个「夹具确实能击败 ORM」的自检。SQLite 是动态类型：列的亲和性是 NUMERIC，所以 `"42"` 实际存成 INTEGER，BLOB 存成 BLOB，两者到达导出器时分别是 `int` 和 `bytes`，这正是 `_decode_payload` 里 `str(raw)` 与 `bytes.decode` 两个分支（我用 `typeof(payload)` 核实过）。
- 同一套测试在**旧 `export.py`**（HEAD 副本）上跑：5 个红（`JSONDecodeError`、`TypeError: 'NoneType' object is not a mapping`、表头缺列），1 个绿（夹具自检）。

### P4　`freeze_manifest.py` 不得静默回退（R4 追加）

- 设置了 `FYP_DATA_ROOT`（**空串也算设置**）时，它是唯一候选；其下没有 `eda_outputs/processed` 就抛 `DataRootError`，`main()` 在做任何事之前捕获，向 stderr 打印 `error: FYP_DATA_ROOT=... does not contain eda_outputs/processed ... No other location was tried.`，**stdout 为空**（所以 `> manifest.md` 不会留下一份误导性的清单），退出码 **2**。
- 未设置时，候选顺序（仓库根 → 兄弟仓库）与 `NOT FOUND` 行为不变。
- 测试用子进程跑脚本的**拷贝**：拷贝所在的假仓库根下放一个**有效**的 `eda_outputs/processed`（静默回退就会成功），HOME 指向空目录（兄弟仓库默认值不存在），PATH 指向空目录（git / node / npm 立即「找不到」）。有效 / 无效（目录不存在、空目录、有 `eda_outputs` 无 `processed`、是个文件）/ 空串 / 未设置 / 未设置且找不到，共 8 个。
- 同一套测试在旧脚本上跑：5 个红（所有「错误路径」），3 个绿（所有「行为不变」）。

### P5　分段计时（R4 追加；为第 2 部分的 PERF-01 做准备）

**后端：`Server-Timing`**

- `POST /infer` 成功时响应带 `Server-Timing: preprocess;dur=…, vision;dur=…, telemetry;dur=…, fusion;dur=…, commit;dur=…, total;dur=…`（固定顺序，两位小数）。各段含义：
  - `preprocess` / `vision` / `telemetry`：直接取 provider 写进 provenance 的 `timing_ms`（`preprocess_ms` / `vision_ms` / `telemetry_ms`）；没有输入的分支没有运行，输出 `dur=0.00;desc="skipped"`，**不省略**；
  - `fusion`：`inference.run_inference` 的耗时（freshness、EMA、融合、等级、告警 FSM）；
  - `commit`：**只**包住 `db.commit()`，在它**返回之后**才取值；
  - `total`：整个路由处理函数（会话查询、幂等检查、模型、持久化、commit、缓存）。不含请求解析 / 校验（在处理函数之前）和响应序列化（在处理函数之后）。
- 幂等重发（直接用已存记录回答）没有做任何工作，只带 `total`。失败响应与 replay 的 `/windows` 路由不带该头。
- **`latency_ms` 的语义没有改**：起点是 `_infer` 进入处，终点是 `run_inference` 返回之后、构造 `InferenceRecord`、`db.add`、`db.commit()` 之前。所以它**不含 commit，也不含缓存写入**；它被写进随后提交的 payload，因而不可能包含 commit。`Server-Timing: total` 恒 ≥ `latency_ms`（差一个取整），差值就是持久化成本。这一点同时写在 `backend/app/timing.py` 的模块文档和 `windows.py` 的注释里。
- 实现方式：计时器通过 `ContextVar`（`timing.activate`）在 `/infer` 期间「环境式」生效，`_persist_window` / `_infer` 的签名**没有改**。原因：既有测试用固定的三参数 lambda 去 monkeypatch `windows._infer`（`test_fault_events.py`），改签名会破坏它。replay 路由没有激活的计时器，`measure` 是空操作。
- 测试用既有的 `live` 夹具（真实 `TrainedProvider.infer` + 手写的假 onnx / xgboost），因此头里的分段名是对着**真实 provider 的 `timing_ms` 键**验证的，且不需要模型文件。可观测的 commit 断言：把真实 `Session.commit` 延迟到 150 ms，provider 真实耗时 80 ms；断言 `commit ≥ 150`、`fusion < 80`、`total ≥ 230`、`80 ≤ latency_ms < 150`。

**前端：每窗口三段**

- `ai/src/liveTiming.ts`（纯模块）：`segmentsOf`（`captureToSendMs` / `networkMs` / `renderMs`，负差值夹到 0）、`parseServerTiming`（支持带引号的 `desc` 内含逗号分号、重复名求和、无数值 `dur` 的忽略）、`createTimingBuffer(capacity = 500)`（环形，满后覆盖最旧，同窗口重复投递替换而不新增，按 `(sessionId, windowId)` 区分，条目冻结，`snapshot()` 返回新数组）。
- `ai/src/liveLoop.ts`：`tick` 里记 `capturedAtMs`（取帧**之前**），`deliver` 成功后 `timings?.push({... sentAtMs, receivedAtMs ...})`，返回 `getTimings()` 与 `markRendered(windowId)`。
  - `captureToSendMs`：取帧开始 → **成功的那次投递**发出。重试过的窗口包含退避时间（那一帧确实已经这么旧），`attemptIndex` 标明是第几次投递；
  - `networkMs`：发出 → 响应收到并解析完；
  - `renderMs`：响应收到 → 该窗口提交到界面。`useLiveSession` 在 `useEffect` 里对最新窗口调 `markRendered`，所以是 **React 提交之后**、**不含首次绘制**。
- 访问器：`window.__draLiveTimings`（`Object.defineProperty` 的 getter，每次读取是新数组，卸载时删除），供第 2 部分用 `page.evaluate` 读取。
- 时间戳全部来自注入的 `now()`（浏览器里是 `Date.now()`），1 ms 精度、非单调；时钟回拨造成的负值夹到 0。

### P6　门禁原始日志（R02）

- `scripts/run_gates.py`（只用标准库）依次运行：`01 build`（`npm run build`）、`02 pytest`（`../.venv/bin/python -m pytest tests -q -p no:cacheprovider`，cwd `backend`，`PYTHONPATH=.`，每次一个新的 `TMPDIR`）、`03 vitest`（`./node_modules/.bin/vitest run --no-cache`）、`04 tsc`、`05 eslint`，全部与计划 Step 4 一字不差，所有子进程带 `PYTHONDONTWRITEBYTECODE=1`。
- 每项写 `NN-<name>.log`：`GATE` / `STATUS` / `EXIT CODE` / 起止时间 / 耗时 / `ARGV`（JSON）/ `CWD` / 关键环境变量（`PYTHONDONTWRITEBYTECODE`、`PYTHONPATH`、`TMPDIR`、`DRA_REQUIRE_MODELS`、`DRA_DATABASE_URL`、`FYP_DATA_ROOT`、`NODE_ENV`、`CI`、`VIRTUAL_ENV`，未设置也写 `(unset)`）/ 工具版本（python、`.venv` python、pytest、node、npm、vitest、tsc、eslint；缺失则写 `unavailable (...)`，不空缺）/ pytest 门禁的 `PYTEST SKIPPED`（取**最后一条**汇总行里的 skipped 数，没有汇总行写 `unknown` 而不是 0）/ **完整**的 stdout 与 stderr（测试里用 300 000 + 200 000 字符验证没有截断）。
- `SUMMARY.md`：结论（`**GREEN**` / `**RED**: N of M gate(s) FAILED: **name**`）、UTC 时间、HEAD / 分支 / 工作树脏度、命令行、每项一行的表（失败行 `**FAIL**` / `**TIMEOUT**` 加粗）、有 skip 时的提示。终端是 TTY 时失败行用 ANSI 红色。
- 退出码：全过（或 `--dry-run`）0；任一项失败或超时 1（**一项失败不会让后面的项停止**）；用法错误 2。
- 选项：`--out`（默认 `docs/evidence/<UTC 日期>/gates`）、`--only a,b`（可重复；编号保持其在全列表中的位置，`--only vitest` 写 `03-vitest.log`）、`--dry-run`（只写日志头，什么都不执行）、`--timeout`（默认 1800 s，超时用 `killpg` 杀掉整个进程组，保留已有输出，状态 `TIMEOUT`）、`--gates-file`（JSON 列表替换内置五项；测试与自定义门禁集使用）。无法启动的命令记为 `FAIL` / 127。
- **没有**把真实运行的日志提交进仓库；本次真实运行的输出在会话草稿目录（第 8 节）。

## 5. 执行的测试（精确命令）

**四项门禁**（真实工作树，`export PYTHONDONTWRITEBYTECODE=1`）：

```
cd /Users/liu/Desktop/FYP2-Live-System
(cd backend && TMPDIR=$(mktemp -d) PYTHONPATH=. ../.venv/bin/python -m pytest tests -q -p no:cacheprovider)
./node_modules/.bin/vitest run --no-cache
./node_modules/.bin/tsc --noEmit
./node_modules/.bin/eslint .
```

另外：`npm run typecheck`、`npm test -- --no-cache`；`python3 scripts/run_gates.py --only pytest,vitest,tsc,eslint --out <草稿目录>`（退出 0，`GREEN: all 4 gate(s) passed`，pytest 门禁 `PYTEST SKIPPED: 0`）；`.venv/bin/python scripts/run_gates.py --dry-run --out <草稿目录>`；`.venv/bin/python scripts/freeze_manifest.py`（退出 0，三个模型 `MATCH`）；`./node_modules/.bin/prettier --check` 于本项涉及的 TS 文件与 `package.json`（通过；`ai/src/evidence.ts`、`ai/src/riskLogic.test.ts` 的格式警告是既有的、不是我改的）。

**P2 在隔离副本里的验证**（副本无模型、无 `.git`、无 `node_modules`）：

```
cd <副本>/backend
TMPDIR=$(mktemp -d) PYTHONPATH=. ../.venv/bin/python -m pytest tests -q -p no:cacheprovider
DRA_REQUIRE_MODELS=1 TMPDIR=$(mktemp -d) PYTHONPATH=. ../.venv/bin/python -m pytest tests -q -p no:cacheprovider
```

**变异**：全部在隔离副本（`git ls-files -co` 导出，另 `git init` 出一个只属于副本的仓库用来核对 `git status`）里做；还原**不用任何 git 还原命令**，而是从真实工作树把那一个文件拷回去，然后在副本里 `git status` 核对（还原后的源文件与基线一致）。期望值都是测试里的字面量。

brief 要求的 Q1–Q8：

| # | 变异 | 观察到 |
|---|---|---|
| Q1 | `"test"` 改回 `"vitest run"`（不先 typecheck） | `repoGuards.test.ts`：1 failed / 5 passed。Q1b：`typecheck` 脚本改成 `echo skipped`，同样 1 failed |
| Q2 | `DRA_REQUIRE_MODELS=1` 时仍然跳过（`_require_models()` 恒 False） | `test_model_gate.py`：2 failed / 6 passed（`test_require_models_turns_each_model_skip_into_a_failure`、`test_with_the_models_present_...`） |
| Q3 | JSON 分支对 NULL payload 直接 `{**payload, ...}` | `test_export_guard.py`：2 failed / 4 passed（JSON 的两个） |
| Q4 | 坏行 `continue` 丢弃（JSON）；Q4b 同样（CSV） | 各 2 failed / 4 passed（行数 / 标记断言） |
| Q5 | 无效 `FYP_DATA_ROOT` 时回退到其他候选 | `test_freeze_manifest.py`：5 failed / 3 passed |
| Q6 | `commit` 段在 `db.commit()` **之前**结束 | `test_server_timing.py`：1 failed / 12 passed（`commit ≥ 150` 不成立）。加强测试后又重跑一次，仍是该测试红 |
| Q7 | 环形缓冲没有上限（`size = size + 1`） | vitest 两个文件：5 failed / 30 passed（缓冲的 4 个单测 + 循环里「500 条」那个） |
| Q8 | 某一项失败时仍以 0 退出 | `test_run_gates.py`：6 failed / 29 passed（进程内 5 个 + 子进程 CLI 1 个）。用最终版测试重跑一次，结果相同 |

我自己设计的补充变异（E 系列，全部最终变红）：

| # | 变异 | 观察到 |
|---|---|---|
| E1a / E1b | 在 `frontend/src/hooks/` 里放一个 `stray.test.tsx`；在 `scripts/` 里放一个 `stray.test.ts` | `repoGuards.test.ts` 各有 1 个红 |
| E2 | 在 `ai/src/liveTiming.ts` 末尾植入类型错误后 `npm test -- --no-cache` | 退出 2，vitest 未启动，含 `TS2322` |
| E3 | `pytest_terminal_summary` 直接 `return` | `test_model_gate.py` 7 failed / 1 passed |
| E4 / E4b | model-skip 识别恒为 False；把 `test_unavailable_contract.py` 的 reason 改掉 | 6 failed / 2 passed；守卫测试 1 failed |
| E5 / E5b / E5c | 坏行的 `RiskScore` 伪造成 0；好行 JSON 换了分隔符；CSV 表头不追加两列 | 各 2 failed / 4 passed |
| E6 / E6b | 空串 `FYP_DATA_ROOT` 当作未设置；错误路径退出 0 | 1 failed；5 failed |
| E7 | `_infer` 读错 provider 的键（`timings`） | `test_server_timing.py` 4 failed |
| E7b | 去掉 skipped 标记 | 4 failed |
| E7c | `latency_ms` 赋值整块删除 | **起初存活（13 passed）**，见下 |
| E7c-1 / E7c-2 | 重跑：删除；以及挪到 commit 之后 | 加强测试后各 1 failed |
| E8a–E8g | 取帧时刻取在取帧之后；`networkMs` 从取帧算起；重试窗口的 `attemptIndex` 恒为 1；`markRendered` 可覆盖；`renderMs` 从发出算起；`parseServerTiming` 不认引号；不同会话的窗口混在一起 | 其中 E8f 起初存活（见下），其余各 1–5 个红 |
| E9a–E9h | 日志漏掉 stderr；dry-run 也执行；`--only` 重新编号；skip 取第一条汇总行；失败即停后面的；超时当通过；日志丢工具版本；失败项的退出码记成 0 | 各有 1–4 个红 |
| E10a / E10b / E10c | 导出：非 UTF-8 的 BLOB 解码错误漏出；BLOB 一律判不可读；INTEGER 值不转字符串 | 各 2 failed / 4 passed |

**两次起初存活的变异**（都暴露了测试的弱点，已修测试并重跑变红）：

- **E7c**：删掉 `latency_ms` 的赋值，测试仍全绿——因为我只断言「`latency_ms < 120`」，而 `0` 满足。现在 provider 真实耗时 80 ms，断言 `80 ≤ latency_ms < 150`，这同时守住「含模型时间」与「不含 commit」。
- **E8f**：让 `parseServerTiming` 不认引号，测试仍绿——因为我的带引号 `desc` 样例里逗号出现在 `dur` **之后**，不认引号也能拆对。现在样例是 `a;desc="x, y; dur=99";dur=1, b;desc="q";dur=2`（引号里藏着一个假的 `dur=99`），不认引号会读出 `{y: 99}`。

**测试环境依赖的两处修正**：第一次在隔离副本里跑 `test_run_gates.py` 时有 2 个失败——我的测试假设了「在 git 检出里」（汇总里的 `Repository:` 行）和「有 `node_modules`」（真实工具版本）。标准隔离副本（`git archive | tar -x`）两者都没有，评审者会看到无谓的红。已改成：git 状态用临时仓库单测（`clean` / `dirty` / `unknown`），工具版本按「该检出里有这个工具才断言真实版本，没有就必须是 `unavailable (...)`」，并新增一个专测「缺失的工具被如实报告」的用例。

## 6. PASS / FAIL / SKIP 计数

| 环境 | pytest | vitest | tsc | eslint |
|---|---|---|---|---|
| 基线（HEAD `a0859bd`，开工前复现） | 704 passed / 0 failed / 0 skipped | 709 passed（24 个文件） | 0 | 0 |
| **最终，真实工作树** | **774 passed / 0 failed / 0 skipped** | **750 passed / 0 failed**（27 个文件） | **0** | **0** |
| 最终，隔离副本（无模型、无 `.git`、无 `node_modules`），默认 | 767 passed / 0 failed / **7 skipped**，退出 0，横幅列出 7 个 | — | — | — |
| 同上，`DRA_REQUIRE_MODELS=1` | 767 passed / **7 errors**，退出 1 | — | — | — |

**测试数的变化逐项解释**

- pytest **+70**（704 → 774）：`test_export_guard.py` 6、`test_freeze_manifest.py` 8、`test_model_gate.py` 8、`test_server_timing.py` 13、`test_run_gates.py` 35。没有任何既有测试被删除、修改或弱化。
- vitest **+41**（709 → 750）：`repoGuards.test.ts` 6、`liveTiming.test.ts` 27、`liveLoopTiming.test.ts` 8。既有的 `liveLoop.test.ts`（58 个）与 Task 9 的范围守卫 `preparedRawTelemetry.test.ts`（38 个）原样通过。
- 24 → 27 个测试文件：恰好是三个新文件。
- 模型存在时 0 skipped；模型缺失时 7 skipped 是既有行为（现在被显式打印），不是新增的。
- pytest 墙钟时间从约 8.6 s 涨到约 15–19 s：新增的子进程式测试（`test_model_gate.py` 约 3.5 s，`test_run_gates.py` 约 3.4 s）。

## 7. 遗留问题

**计划与代码的漂移**（先对照当前代码核实的结果）

| 计划写的 | 当前代码 |
|---|---|
| `windows.py:62` 的计时早于 commit | `latency_ms` 赋值在 `windows.py:73`，`db.commit()` 在 `:85`（HEAD 版）。语义与计划描述一致 |
| `main.py:66-68` 在 `dist/` 存在时挂 StaticFiles | 现在是 `main.py:71-73` |
| `config.py:30` 只允许 `:5173` | 一致 |
| 干净检出上「五个」最重的 live 测试 SKIP | 实际 **7 个**：`test_live_inference.py` 4 个，另有计划没提到的第二个 `requires_models`（`test_unavailable_contract.py:26`）3 个（含 2 个参数化） |
| `useLiveSession.ts:145` 是 2 s 回放节奏 | 游标已在 Task 9 搬到 `preparedTelemetryAt`，hook 里是 `telemetryAt: preparedTelemetryAt` |
| `ConfigurationView.tsx:35-38` | 一致 |
| vitest include 只有 `*.test.ts` | 一致，且现在有两个根：`ai/src/**` 与 `frontend/src/**`（`repoGuards.test.ts` 钉住） |

**需要控制者知情或裁定的事项**

1. **`liveLoop.ts` 的 import 守卫冲突**（第 2 节第 1 条）。如果控制者更希望「默认开启记录」，需要同时放宽 `preparedRawTelemetry.test.ts:232` 的 `["./types"]` 精确相等；我没有动它。
2. **`WindowTiming.server` 恒为 null / TS `parseServerTiming` 暂无生产调用方**（第 2 节第 2 条）。要接通，需要让 `api.infer` 把 `Server-Timing` 头带出来（`api/client.ts` 不在本项范围），或者由 Playwright 直接读响应头。**另外**：开发模式下前端（`:5173`）跨源访问后端（`:8000`）时，`fetch` 读不到 `Server-Timing`，需要 CORS 的 `expose_headers=["Server-Timing"]`（`main.py`，不在本项范围）。第 2 部分按计划是单 uvicorn + 静态 `dist/` 同源，不受影响，Playwright 读响应头也不受 CORS 限制。
3. **React 绑定层未单测**（第 2 节第 3 条）。第 2 部分的验收应包括：`window.__draLiveTimings` 非空、每个窗口的 `renderMs` 在下一个窗口到达前已被填上、卸载后访问器消失。
4. **测量口径的限制**：`Date.now()` 精度 1 ms 且非单调（负差夹到 0，会把时钟回拨「藏」成 0）；`captureToSendMs` 的起点是 tick 开始，包含 JPEG 编码，但不包含摄像头内部的取帧延迟；`renderMs` 终点是 React 提交后的 effect，不含首次绘制；`Server-Timing: total` 不含请求解析与响应序列化。这些都应在第 2 部分的 PERF-01 结论里如实写明，不能把这几段相加就当作端到端延迟。
5. **导出守卫的边界**：只覆盖 brief 列出的三类（NULL、非法 JSON、非对象）。一个**是 JSON 对象但子字段类型不对**的 payload 仍可能在 CSV 路径中途出错——我核实过一个具体例子：`{"provenance": "request_id is mentioned here"}`，CSV 路径在 `provenance.get(...)` 处抛 `AttributeError: 'str' object has no attribute 'get'`（如果该字符串里不含任何列名，则恰好不出错，因为 `k in provenance` 是子串判断）。我没有修，因为它超出 brief；可以用同样的「标记为不可读」做法补上，请控制者裁定是否纳入。
6. **CSV 模式变化**：所有 CSV 导出多了末尾两列（`payload_unreadable`、`payload_unreadable_reason`），可读行为空。只追加、不插入，不影响按位置读取旧列的消费者；但表头长度从 28 变成 30。JSON 的可读行没有任何变化。
7. **`DRA_REQUIRE_MODELS` 的适用范围**：只作用于「带 `requires_models` reason 的测试」。如果某次运行把这些测试 deselect 掉了，开关不会因此失败（它不是「模型必须存在」的会话级检查）。这是有意的：保证的是「没有任何测试被静默跳过」。
8. **`FYP_DATA_ROOT` 空串**被我定为「已设置但无效」→ 退出 2，而不是当作未设置。brief 没有明说；这样做是为了让 `export FYP_DATA_ROOT=$UNSET_VAR` 这类笔误不会静默回退。
9. **`run_gates.py` 的 `build` 项没有真跑**（第 2 节第 4 条）。要真跑，请在拥有自己 `node_modules` 副本的隔离副本里运行，不要用指向主仓库的符号链接。
10. **变异事故的副作用**（第 2 节第 5 条）：主仓库 `node_modules/.vite-temp` 是空目录，mtime 04:20；我没有去清理它（主仓库禁止触碰）。同时给两个会 dry-run「真实门禁列表」的测试加了 `--timeout 5` 作为保险：万一将来 dry-run 退化成真的执行，pytest 门禁递归重跑自己的链条会在 5 s 后被杀，而不是无限递归。
11. **文档未更新**：`CLAUDE.md`、`README.md` 等仍写着旧的 `npm test` 说明，也没提 `typecheck`、`run_gates.py`、`DRA_REQUIRE_MODELS`。这不在本项范围，建议第 2 部分收尾时一并更新。
12. **既有格式警告**：`prettier --check` 对 `ai/src/evidence.ts`、`ai/src/riskLogic.test.ts` 报警，是既有的，与本项无关。

## 8. 证据路径

仓库内：

- 本报告 `/Users/liu/Desktop/FYP2-Live-System/docs/fyp2/implementation/task-10-part1.md`
- 新测试文件：`/Users/liu/Desktop/FYP2-Live-System/ai/src/{repoGuards,liveTiming,liveLoopTiming}.test.ts`、`/Users/liu/Desktop/FYP2-Live-System/backend/tests/test_{model_gate,export_guard,freeze_manifest,server_timing,run_gates}.py`

会话草稿目录（不入库，会话结束后可能被清理）`/private/tmp/claude-501/-Users-liu-Desktop-FYP-In-Cabin-Driver-Assessment--1--claude-worktrees-exciting-keller-fdf913/43d73f6d-ed36-4f8a-b584-13c974ccd767/scratchpad/`：

- `gates-real-run/`：本次通过 `run_gates.py` 真实跑 pytest / vitest / tsc / eslint 的 `02-…05-…log` 与 `SUMMARY.md`（GREEN）
- `mut.py`、`q12.py`、`q345.py`、`q678.py`、`q8final.py`、`extras1.py`…`extras7.py`：全部变异脚本（每个脚本里能看到被替换的原文与新文）
- `golden.py`：在旧代码上捕获好行 JSON / CSV 黄金输出的脚本；`probe_prov.py`：第 7 节第 5 条的复现
- `mkcopy.sh`：隔离副本的导出脚本

隔离副本（`$TMPDIR` 下）：变异副本 `…/tmp.gf9FJSzD5V`；P2 最终验证副本 `…/tmp.JPYnulu9ix`；旧代码（HEAD）副本的路径记在 `scratchpad/old_head_copy.txt`。

## 9. 下一项依赖

第 2 部分（Playwright 端到端、单分支系统测试、逐 ID 全行对账、React 绑定层真实点击）可以直接使用：

- **`window.__draLiveTimings`**：每窗口 `captureToSendMs` / `networkMs` / `renderMs` / `attemptIndex`（最多最近 500 个，按会话区分）。
- **`Server-Timing` 响应头**：Playwright 的 `response.headers["server-timing"]` 逐窗口取六段，用响应 body 的 `window_id` 与前端缓冲按 `(session, window_id)` 对上。PERF-01 的口径必须同时写明：`latency_ms` 终点在 commit 之前；`total` 不含请求解析与响应序列化；`renderMs` 不含首次绘制；前端时间是 `Date.now()`。
- **`scripts/run_gates.py --out docs/evidence/<日期>/gates`**：归档用。真跑 `build` 请在拥有自己 `node_modules` 副本的隔离副本里；归档前先决定要不要在发布前门禁里设置 `DRA_REQUIRE_MODELS=1`（设置后模型缺失会让 pytest 退出 1）。
- **`freeze_manifest.py`**：现在在 `FYP_DATA_ROOT` 错误时退出 2、stdout 为空，归档脚本应检查退出码。
- **R10**：本项没有碰游标与观测身份；告警序列的预期仍取决于 R10，仍由第 2 部分按届时生效的规则断言。
- 若要让前端缓冲带上服务端分段（`server` 字段），需要先决定是否放开 `api/client.ts` 与 `main.py` 的 `expose_headers`（第 7 节第 2 条）。
