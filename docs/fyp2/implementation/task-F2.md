## Task F2

声明 evidence watermark 豁免，堵住乱序守卫的静默失效（跨任务复审发现 F2，Task 7 的硬前置条件）。

### 状态

**DONE**。三项门禁全绿，两个变异测试都按预期把新测试变红。

### 问题（一句话）

`routers/windows.py` 把乱序守卫的两个 watermark（`captured_at`、`telemetry_timestamp`）写进与时序记忆**同一个**持久化 `runtime_state`；`inference.py` 的注释却声称 `TEMPORAL_STATE_KEYS` 是「EVERY key」，计划第 524 行也要求「新加的每个 state 键都必须进 pop 元组」。照做的人会把 watermark 加进去，一次 gap 就把刚写入的 watermark 弹掉，之后更旧的帧得到 201 而不是 409。复审在 scratch 副本做过该变异：504/504 仍全绿。

### 改动的文件

| 文件 | 改动 |
|---|---|
| `backend/app/inference.py` | 新增 `EVIDENCE_WATERMARK_KEYS = ("captured_at", "telemetry_timestamp")`（紧跟 `TEMPORAL_STATE_KEYS`）；改写 `TEMPORAL_STATE_KEYS` 上方注释，去掉「EVERY key」，明确它是「一次 gap 会清空的时序记忆键」，并说明 watermark 故意不在其中、不得加入 |
| `backend/app/routers/windows.py` | `_save_window` 的字面量元组改为 `inference.EVIDENCE_WATERMARK_KEYS`（`inference` 本就已 import）。语义不变 |
| `docs/plans/2026-10-12-fyp2-live-system-completion.md` | 第 524 行：新增的「时序记忆」键必须进 `TEMPORAL_STATE_KEYS`；`EVIDENCE_WATERMARK_KEYS` 中的键绝不能加入 |
| `backend/tests/test_temporal_contract.py` | 新增两个测试（见下） |
| `docs/fyp2/implementation/task-F2.md` | 本报告 |

没有触碰 `run_inference` 的 gap 逻辑、严格 `<` 判断（`UT-TIME-05` 的已知限制保持不变）、`frontend/`、`ai/`、`ml/`。

### 新增测试

1. `test_watermark_keys_are_disjoint_from_temporal_keys`：期望值 `("captured_at", "telemetry_timestamp")` 字面量写死在测试里，断言两个常量交集为空。
2. `test_out_of_order_guard_survives_a_gap`：HTTP 层，经 `POST /api/sessions/{sid}/infer`。
   - 复用同文件已有的 `_StubProvider`（UT-TIME-05 所用）并 `monkeypatch.setattr(trained, "get_provider", ...)`，不依赖模型权重；用 `conftest.py` 的 tmp-DB `api` / `api_factory`。
   - 时间戳取 `T0 + 10s / 20s / 15s`（T0 = 2025-01-01，均在过去），每个请求不同 `request_id`，没有 sleep、没有 fake clock。
   - 序列：
     1. 请求 1（`T0+10s`）→ 201，持久化的 `captured_at` 等于该 stamp，记下 `high_since`。
     2. 在 DB 里把 `runtime_state["last_processed_ms"]` 减 60000，模拟长暂停。
     3. 请求 2（`T0+20s`）→ 201；**控制断言**：`high_since` 变大，证明 gap 重置真的发生（没有它，测试可能空转通过）。
     4. 断言持久化的 `runtime_state["captured_at"]` 等于请求 2 的 stamp。
     5. 请求 3（`T0+15s`，比请求 2 旧）→ 409；`InferenceRecord` 数量不变（2），watermark 不变。
   - 比计划序列多出的只有步骤 3 的控制断言，以及每步对持久化 state 的读取。

### 变异验证（真实输出）

每次变异前先 `git add` 本任务文件，所以 `git checkout -- <file>` 还原到的是暂存版本（而不是 HEAD，否则会把本任务的真实改动一并丢掉；第一次变异后我就是这样误还原了一次 `inference.py`，已立刻重做同样的编辑并核对 diff，之后的流程改为先暂存）。每次还原后 `git diff | wc -l` 为 0。

**变异 1：把两个 watermark 键加进 `TEMPORAL_STATE_KEYS`**

```
tests/test_temporal_contract.py::test_watermark_keys_are_disjoint_from_temporal_keys  FAILED
>       assert set(inference.EVIDENCE_WATERMARK_KEYS) & set(inference.TEMPORAL_STATE_KEYS) == set()
E       AssertionError: assert {'captured_at...ry_timestamp'} == set()

tests/test_temporal_contract.py::test_out_of_order_guard_survives_a_gap  FAILED
>       assert state.get("captured_at") == second_stamp.isoformat()
E       AssertionError: assert None == '2025-01-01T12:00:20+00:00'
2 failed, 65 deselected
```

`test_out_of_order_guard_survives_a_gap` 失败在**步骤 4**：步骤 1（watermark 已写入）、步骤 3（201 与 gap 控制断言）都通过，之后持久化 state 里已没有 `captured_at`。这正是静默失效的那个位置。

**变异 2：删掉 `windows.py` 里 `if stamp: state[key] = stamp` 的写入**

```
tests/test_temporal_contract.py::test_out_of_order_guard_survives_a_gap  FAILED
>       assert state.get("captured_at") == first_stamp.isoformat()
E       AssertionError: assert None == '2025-01-01T12:00:10+00:00'
1 failed, 1 passed, 65 deselected
```

失败在**步骤 1**：第一个请求之后持久化 state 就没有 watermark（`test_watermark_keys_are_disjoint_from_temporal_keys` 不受影响，仍通过，符合预期，它只守常量不相交）。

两次还原后 `git status` 只剩本任务的暂存文件，`git diff`（工作区对暂存区）为空。

### 门禁（还原所有变异之后，最终代码上的真实输出）

```
$ cd backend && PYTHONPATH=. ../.venv/bin/python -m pytest tests -q     # TMPDIR=$(mktemp -d)
506 passed, 1 warning in 5.82s

$ ./node_modules/.bin/vitest run --no-cache
 Test Files  15 passed (15)
      Tests  394 passed (394)

$ ./node_modules/.bin/tsc --noEmit
tsc exit=0
```

pytest：504 → **506**（新增 2），0 failed。vitest：**394 / 0**。tsc：**0**。

### 说明与遗留

- 唯一的 warning 是既有的 Starlette `httpx` 弃用提示，与本任务无关。
- 步骤 3 的控制断言依赖真实时钟下 `high_since` 单调增大（浮点毫秒、两次请求间隔远大于 1 µs），不依赖 sleep。
- F4（ROUND_HALF_UP 写回计划）按指示未做，等 Codex 审阅。
