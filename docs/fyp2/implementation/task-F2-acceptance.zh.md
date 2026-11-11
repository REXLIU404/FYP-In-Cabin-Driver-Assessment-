# Task F2 验收报告（中文）

## 1. 任务概要

- **编号与名称**：Task F2 —— 声明 evidence watermark 豁免，堵住乱序守卫的静默失效（跨任务复审发现 F2，Task 7 的硬前置条件）
- **实现了什么**：新增单一来源常量 `inference.EVIDENCE_WATERMARK_KEYS = ("captured_at", "telemetry_timestamp")`，`routers/windows.py` 改为引用它；改正 `TEMPORAL_STATE_KEYS` 上方的注释和计划第 524 行的指引；新增两条测试把这条保证钉住。
- **为什么必要**：乱序守卫的两个 watermark 与时序记忆写在**同一个**持久化 `runtime_state` 里。旧注释称 `TEMPORAL_STATE_KEYS` 是「EVERY key」，计划也要求「新加的每个 state 键都要进这个元组」。照做的人会把 watermark 加进去，一次 gap 就把刚写入的 watermark 清掉，之后**更旧**的帧会拿到 201 而不是 409。复审在 scratch 副本里做过这个变异：504/504 仍然全绿，没有任何测试守住它。
- **行为变化**：**无运行时行为变化**。常量替换字面量元组，语义逐字相同。变化在于这条保证现在有文档、有测试守护。

## 2. 实现证据

- **Commit**：`ef2417d`（5 个文件，+180 / −4）
- **主要文件**：`backend/app/inference.py`（常量与注释）、`backend/app/routers/windows.py`（1 行）、`backend/tests/test_temporal_contract.py`（+2 测试）、`docs/plans/2026-10-12-fyp2-live-system-completion.md`（第 524 行）、`docs/fyp2/implementation/task-F2.md`（技术报告）
- **关键决定**：
  - HTTP 层测试复用同文件已有的 `_StubProvider`，monkeypatch `trained.get_provider`，**不依赖模型权重**。
  - 用「直接把 DB 里的 `last_processed_ms` 减 60 秒」模拟长暂停，不 sleep、不用 fake clock。
  - 实现者在步骤 3 额外加了**控制断言**：`high_since` 变大，证明 gap 重置真的发生，避免测试空转通过。评审认可。

## 3. 测试结果

| 命令 | 结果 |
|---|---|
| `pytest backend/tests -q` | **506 passed / 0 failed**（504 + 新增 2） |
| `./node_modules/.bin/vitest run --no-cache` | 394 / 0（未触碰前端） |
| `./node_modules/.bin/tsc --noEmit` | exit 0 |

**新增用例**：

1. `test_watermark_keys_are_disjoint_from_temporal_keys`：期望值字面量写死在测试里，断言两个常量交集为空。
2. `test_out_of_order_guard_survives_a_gap`：经 `POST /api/sessions/{sid}/infer`，序列 `T0+10s → 201`、模拟 60 秒暂停、`T0+20s → 201`（gap 触发）、断言 watermark 等于第二次的 stamp、`T0+15s → 409` 且没有新增 `InferenceRecord`。

**变异验证**（评审独立复现，不是采信实现者的转述）：

| 变异 | 结果 |
|---|---|
| 把两个 watermark 键加进 `TEMPORAL_STATE_KEYS` | 两条测试都变红；HTTP 测试失败在**步骤 4**（`captured_at` 被 gap 清掉） |
| 删掉 `windows.py` 里 `if stamp: state[key] = stamp` | HTTP 测试变红，失败在**步骤 1** |
| 评审追加：把 `<` 反成 `>` | HTTP 测试在步骤 3 意外得到 409，变红 |

**存在但未执行的测试**：无。

## 4. 问题与风险

- **失败测试**：无。
- **非预期回归**：无。`run_inference` 的 gap 逻辑、严格 `<` 判断（`UT-TIME-05` 的已知限制）、`frontend/`、`ai/`、`ml/` 均未改动。
- **过程失误（已纠正）**：实现者第一次做变异时，在改动尚未暂存的情况下执行了 `git checkout --`，把本任务对 `inference.py` 的真实改动一并还原。随后重做同样的编辑，之后改为「先暂存再变异」。评审逐文件核对了 HEAD，确认重做完整。
- **时钟依赖**：控制断言依赖真实时钟下 `high_since` 严格增大。评审实测两值间隔约 5 ms、时钟分辨率 1 µs，余量约 5000 倍，循环 60 次 0 失败。只有系统时钟回跳超过 5 ms 才可能偶发失败，判定可忽略。
- **遗留 Minor（延后）**：
  1. `test_temporal_contract.py:4-8` 的模块 docstring 称全部用注入时钟，新测试用的是真实时钟，表述已不准确。
  2. 第 5 步只断言状态码 409，没有钉住 `detail="Out-of-order evidence timestamp"`。
  3. `docs/fyp2/implementation/task-05.md:149` 的历史移交文字仍是旧指引。计划已修正，Task 7 的 brief 由计划生成、不读 task-05.md，disjoint 测试也会拦住误加，所以保留历史文档原貌。
  4. HTTP 测试只覆盖 `captured_at`；`telemetry_timestamp` 只由静态的 disjoint 测试守护。

## 5. 验收结论

**PASS**

理由：要求的四项全部完成，三项门禁全绿，三个变异都让测试按预期变红，且评审独立复现。没有运行时行为变化，遗留的四个 Minor 都不影响正确性。

## 6. 下一任务就绪度

- F2 这一项 Task 7 前置条件**已满足**。
- **F4**（`ROUND_HALF_UP` 写回计划与 `global-constraints.md`）按你的指示**暂不做**，等 Codex 审阅结果。
- **Task 7 暂不开工**，同样等 Codex 审阅结果。
