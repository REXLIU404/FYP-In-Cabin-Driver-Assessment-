# 阶段 1 · 第 3 项（P1-3）技术报告：`telemetry_timestamp` 的对称 HTTP gap 测试（Codex R13）

- 分支 `fyp2/live-system`，工作树 `/Users/liu/Desktop/FYP2-Live-System`，开工 HEAD `9945c76`（与简报要求一致，工作树干净）。
- 日期 2026-10-13。角色：实现者。未派发子 agent。

## 1. 任务编号与名称

P1-3-TGAP：为 `telemetry_timestamp` 水位线补一条经 HTTP（`POST /api/sessions/{sid}/infer`）的 gap 行为测试，与既有 `test_out_of_order_guard_survives_a_gap`（只覆盖 `captured_at`）逐步对称（Codex R13，F2 遗留 minor 4）。顺带更正 `test_ut_ema_parity_01_the_reference_specification_agrees` 的过期 docstring（R08 评审遗留，控制者并入本项）。

## 2. 实现状态

| 简报条目 | 状态 |
|---|---|
| 新增 `test_out_of_order_guard_survives_a_gap_for_telemetry`，五步与 `captured_at` 版一一对应 | 完成 |
| 复用 `_RequestDrivenStubProvider`（P1-2 新增），不改 `_StubProvider` | 完成 |
| 请求不带图像，只让 telemetry 水位线起作用 | 完成，并加断言证明（第 4.2 节） |
| 第 3 步的控制断言（`high_since` 变大，证明 gap 重置真的发生） | 完成 |
| 验收 M1：`TEMPORAL_STATE_KEYS` 加入 `"telemetry_timestamp"` → 新测试在第 4 步变红 | 完成，第 4 步变红（第 5.3 节） |
| 验收 M2：路由水位线循环只守护 `captured_at` → 新测试变红，而 `captured_at` 版仍为绿 | 完成，新测试变红、`captured_at` 版保持绿（第 5.3 节） |
| 追加：更正约第 777 行的过期 docstring，只改 docstring | 完成，断言一字未改 |
| 四项门禁 0 失败；pytest 比上一项多 1 条 | 完成：518 → 519（第 6 节） |

## 3. 创建 / 修改的文件

提交内包含 2 个文件：

| 文件 | 性质 |
|---|---|
| `backend/tests/test_temporal_contract.py` | 修改：+77 / −3。新增 1 个测试函数（约 73 行含 docstring），改 1 处 docstring（−3 / +4） |
| `docs/fyp2/implementation/phase1-03-tgap.md` | 新建：本报告 |

未触碰：`backend/app/`（没有改任何实现，变异只在隔离副本里做）、`docs/fyp2/review/`、`ml/outputs/`、主仓库、计划文档（登记工作留给控制者）。

## 4. 实现摘要

### 4.1 事实依据（我自己核对过源码）

- `backend/app/routers/windows.py:53-58`：`_save_window` 对 `inference.EVIDENCE_WATERMARK_KEYS` 里每个 key，若 provenance 里的时间戳早于 `runtime_state` 里已存的水位线则 409，否则把它写入 `state[key]`。
- `backend/app/inference.py:113-115` 与 `:160-161`：`run_inference` 检测到 gap（`now_ms - last_processed_ms > 3000`）时对 scratch 副本 `pop` 掉 `TEMPORAL_STATE_KEYS`，最后 `state.clear(); state.update(scratch)`。所以如果水位线 key 被误列入 `TEMPORAL_STATE_KEYS`，它会在 gap 之后从持久化状态里消失。
- `backend/app/schemas.py:108-131`（`LiveInput`）：只带遥测时，必须同时有 `telemetry_features`、`telemetry_timestamp` 和非 `missing` 的 `telemetry_source`；`image_base64` 与 `captured_at` 均可为 `None`。`normalize_timestamp` 拒绝比真实时钟超前 5 s 以上的时间戳，所以测试时间戳取 2025 年。
- `_RequestDrivenStubProvider.infer`（`test_temporal_contract.py`）：带 `telemetry_features` 则 telemetry 为 fresh 且概率 1.0，不带图像则 vision 为 missing，并把请求的 `telemetry_timestamp` 回显进 provenance；`captured_at` 回显的是 `None`。

### 4.2 新测试

`test_out_of_order_guard_survives_a_gap_for_telemetry(api, api_factory, monkeypatch)`，放在 `captured_at` 版正后方，便于成对阅读。会话 `live-r13`，`LIVE_MODEL_RUNTIME`。每个请求只含 `request_id`、`telemetry_features`（复用文件里已有的 `TELEMETRY_FEATURES`，8 个特征、有限数值、无多余键）、`telemetry_timestamp`、`telemetry_source: "prepared_replay"`，不含 `image_base64` 和 `captured_at`。

五步与 `captured_at` 版逐步对应，时间戳也相同（`at(10_000)` / `at(20_000)` / `at(15_000)`）：

1. 第一帧返回 201；持久化的 `runtime_state["telemetry_timestamp"]` 等于第一帧时间戳；记下 `high_since`，且非 `None`。
2. 把持久化的 `last_processed_ms` 往回拨 60 000 ms，不 sleep，并断言写入生效。
3. 更新的一帧返回 201；**控制断言** `state["high_since"] > high_since_before_gap`：gap 重置真的发生，测试不会空过。
4. 持久化的 `telemetry_timestamp` 仍在且等于第二帧时间戳；记录数 `== 2`。
5. 时间戳介于两者之间的一帧返回 **409**；记录数不变；水位线仍等于第二帧时间戳。

与 `captured_at` 版相比，我只多加了一条断言：第 1 步里 `"captured_at" not in state`。理由：简报要求「只让 telemetry watermark 起作用」。这条断言把这个前提变成可检验的事实，否则读者只能相信「没发图像所以没有 captured_at 水位线」。第 5 步只断言状态码 409，与 `captured_at` 版一致，没有额外断言响应文本。

期望值全部是测试里的字面量或本地构造的时间戳，没有 import 任何实现常量来构造期望。没有使用 `fake_clock`：与 `captured_at` 版保持一致，用真实时钟 + 回拨持久化状态的方式。`high_since` 是两次请求各自的真实 `now_ms`，第二次必然更大。

### 4.3 docstring 更正

`test_ut_ema_parity_01_the_reference_specification_agrees` 的 docstring 原写「ai/reference/risk_logic.py has no importer」。现改为陈述事实：该文件由 `test_fusion_vectors.py` 经 importlib 加载，本文件再以 `reference` 之名从前者 import。后半句（调用约定）原样保留。只改 docstring，没有改任何断言（`git diff` 里该函数只有 docstring 行变化）。

## 5. 执行的测试（精确命令）

### 5.1 新测试单独运行（真实工作树）

```
cd /Users/liu/Desktop/FYP2-Live-System
export PYTHONDONTWRITEBYTECODE=1
cd backend && TMPDIR=$(mktemp -d) PYTHONPATH=. ../.venv/bin/python -m pytest tests/test_temporal_contract.py -q -p no:cacheprovider -k "survives_a_gap" -v
```

结果：`2 passed, 78 deselected`（`captured_at` 版与 telemetry 版各一条）。

### 5.2 四项门禁（精确命令，真实工作树）

```
cd /Users/liu/Desktop/FYP2-Live-System
export PYTHONDONTWRITEBYTECODE=1
(cd backend && TMPDIR=$(mktemp -d) PYTHONPATH=. ../.venv/bin/python -m pytest tests -q -p no:cacheprovider)
./node_modules/.bin/vitest run --no-cache
./node_modules/.bin/tsc --noEmit
./node_modules/.bin/eslint .
```

另一条只为确认计数差：

```
(cd backend && TMPDIR=$(mktemp -d) PYTHONPATH=. ../.venv/bin/python -m pytest tests -q -p no:cacheprovider --deselect tests/test_temporal_contract.py::test_out_of_order_guard_survives_a_gap_for_telemetry)
```

结果：`518 passed, 1 deselected`。

### 5.3 变异验证（隔离副本）

做法：`D=$(mktemp -d) && git archive HEAD | tar -x -C "$D"`，把 `.venv` 符号链接进去，再把工作树里（尚未提交的）新测试文件拷进副本。每次变异都由脚本断言「目标文本恰好出现一次」才替换；跑完立刻从备份还原，并与 `git show HEAD:<path>` 做 `diff` 确认还原后与 HEAD 逐字相同（测试文件则与真实工作树里的那份逐字相同）。真实工作树没有做任何变异。副本里没有模型文件，依赖模型的测试会 skip，但本项的两条 gap 测试用 stub provider，不受影响；干净副本里这两条均为绿（`2 passed`）。

| 编号 | 变异（隔离副本） | 观察 |
|---|---|---|
| **M1** | `backend/app/inference.py`：在 `TEMPORAL_STATE_KEYS` 末尾加 `"telemetry_timestamp"` | 新测试**红**，失败行为第 4 步断言：`assert None == '2025-01-01T12:00:20+00:00'`（`test_temporal_contract.py:657`）。第 3 步 201 与控制断言都已通过，所以 gap 重置发生了，是随后的 `state.update(scratch)` 把水位线丢了。`captured_at` 版保持绿；静态的 `test_watermark_keys_are_disjoint_from_temporal_keys` 也同时变红（预期：它守的是同一条规则）。还原后 `inference.py` 与 HEAD 相同。 |
| **M2** | `backend/app/routers/windows.py:53`：`for key in inference.EVIDENCE_WATERMARK_KEYS:` 改为 `for key in inference.EVIDENCE_WATERMARK_KEYS[:1]:`（只守护 `captured_at`） | 新测试**红**，失败行为第 1 步断言：`assert None == '2025-01-01T12:00:10+00:00'`（`:633`，telemetry 水位线从未被写入）。**`test_out_of_order_guard_survives_a_gap`（`captured_at` 版）在同一次运行里为绿**：该次输出为 `1 failed, 1 passed`，失败的是 `..._for_telemetry`。这证明新测试是 telemetry 水位线的**唯一**行为防线，`captured_at` 版发现不了这个回归。还原后 `windows.py` 与 HEAD 相同。 |

M2 的失败落在第 1 步，所以第 5 步的 409 在 M2 下没有被走到。为了确认第 5 步和第 3 步的控制断言各自也有牙齿，我另做了两项（简报没要求，是我追加的，下表同样都已还原）：

| 编号 | 变异（隔离副本） | 观察 |
|---|---|---|
| **M3**（追加） | `routers/windows.py:55`：比较条件加 `key == "captured_at" and`，即 telemetry 水位线照常写入，但不再用它拒绝乱序 | 新测试**红**，失败行为第 5 步：`assert response.status_code == 409`（`:663`），实际返回 201（响应体显示 `window_id: 3`、`telemetry_timestamp: 2025-01-01T12:00:15+00:00` 已被接受）。`captured_at` 版保持绿（`1 failed, 1 passed`）。 |
| **M4**（追加，变异的是测试本身） | 只在新测试里把 `paused["last_processed_ms"] -= 60_000` 改成 `-= 0`（脚本断言文件里恰有两处，只改第二处） | 新测试**红**，失败行为第 3 步控制断言：`assert 1791905556340.828 > 1791905556340.828`（`:654`）。证明去掉回拨后 gap 不会发生、测试不会悄悄空过。还原后测试文件与真实工作树版本逐字相同。 |

## 6. PASS / FAIL / SKIP 计数

| 门禁 | 结果 |
|---|---|
| pytest（`backend`，全量） | **519 passed**，0 failed，0 skipped，1 个 warning（`StarletteDeprecationWarning`，既有，与本项无关） |
| vitest | 15 个文件，**397 passed**，0 failed |
| `tsc --noEmit` | 退出码 0，无输出 |
| `eslint .` | 退出码 0，无输出 |

数字变化的解释：

- **pytest 518 → 519（+1）是本项造成的**，且已用 `--deselect` 验证：去掉新测试后是 `518 passed`，加上就是 519。+1 即 `test_out_of_order_guard_survives_a_gap_for_telemetry`；docstring 更正不增减用例。
- 阶段 1 开工基线（`e326449`）是 506；本项开工时（`9945c76`）已是 518。这 +12 来自此前的 P1-1 / P1-2 提交（`f289d66` 至 `9945c76`，其中 `backend/tests/test_temporal_contract.py` 在 `e326449..HEAD` 间 +131 / −9），不是本项。我只对本项的 +1 做了独立验证。
- **vitest 394 → 397**：本项没有改任何 TypeScript 文件（`git diff --stat` 只有 `test_temporal_contract.py`）。+3 来自 P1-1：`e326449..HEAD` 间 `ai/src/emaParity.test.ts` +10 行（`9632812`）。
- 真实工作树里模型文件可用，所以没有 skip；隔离副本里没有模型，约 7 个依赖模型的测试会 skip，这只在变异副本里发生，不影响上表。

## 7. 遗留问题

1. 第 5 步与 `captured_at` 版一样只断言 409 状态码，没有断言响应文本是 `Out-of-order evidence timestamp`。在这个场景里 409 的另外两个来源（`request_id` 复用、会话模式不符）都不可能触发，我没有为此扩大断言；若评审想要更强的区分，可以加一条 `detail` 断言。
2. 新测试引用的 `_RequestDrivenStubProvider` 与 `TELEMETRY_FEATURES` 定义在文件更靠后的 IT-LIVE-AGE 一节（运行时解析，没有问题），我在 docstring 里写明了位置。如果评审更想让测试紧贴它的辅助定义，可以把这条测试挪到 IT-LIVE-AGE 一节之后；我选择与 `captured_at` 版相邻，便于成对阅读。
3. 没有测同时带图像与遥测时两条水位线的交互：那不是 R13 的范围（R13 只要求 telemetry 一侧的对称覆盖）。
4. 计划文档里对应条目的登记（标记 P1-3 完成）没有在本项做，留给控制者，与 P1-1 / P1-2 的 bookkeeping 方式一致。

## 8. 证据路径

- 新测试：`backend/tests/test_temporal_contract.py`，`test_out_of_order_guard_survives_a_gap_for_telemetry`（约第 595 行起）；更正后的 docstring 在 `test_ut_ema_parity_01_the_reference_specification_agrees`。
- 被守护的实现：`backend/app/inference.py`（`TEMPORAL_STATE_KEYS`、`EVIDENCE_WATERMARK_KEYS`、gap 重置）与 `backend/app/routers/windows.py:53-58`（水位线循环）。
- 对称的既有测试：同文件 `test_out_of_order_guard_survives_a_gap`（第 528 行起）。
- 变异副本：`/var/folders/0k/dtzqmkm53vqgg530vd7h3fmr0000gn/T/tmp.NdTWx7YAPM`（保留未删；内容已全部还原为 HEAD + 本项测试文件）。
- 来源评审：`docs/fyp2/review/` 中的 Codex R13（只读，未触碰）。

## 9. 下一项依赖

- 本项不引入新的 helper 或 fixture，下一项无需依赖本项的产物。
- 如果后续有人把新的水位线 key 加进 `EVIDENCE_WATERMARK_KEYS`，应照这条测试再补一条对称的 HTTP gap 测试；`test_watermark_keys_are_disjoint_from_temporal_keys` 仍只是静态守护。
