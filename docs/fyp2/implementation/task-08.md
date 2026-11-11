# Task 8 实现报告 —— 有界重试、冻结 payload、可见停止态

## 1. 任务编号与名称

- **Task 8**（`TASK-8-RETRY`）：有界重试、冻结 payload、可见停止态（含 R5「摄像头停止后循环继续」、R7 裁定 T1–T7、IT-RETRY-IDENTITY、IT-RETRY-STALE）
- 工作树 `/Users/liu/Desktop/FYP2-Live-System`，分支 `fyp2/live-system`，基线 HEAD `cbe573f`（开工前已核实分支与 HEAD，工作树干净）
- 范围外、零改动：后端应用代码（只新增后端测试）、融合 / FSM / EMA、模型文件、`docs/fyp2/review/`、计划文件
- 前两次运行留下的两份草稿（`task-8-drafts-run2/`）只作为起点阅读：结构沿用，但全部按 TDD 重新验证（先写失败的测试，再实现），并对每条规则做了变异验证；草稿目录没有提交。

## 2. 实现状态

**DONE_WITH_CONCERNS。** 四道门禁达标：pytest 598 passed / 0 failed / 0 skipped，vitest 515 passed，`tsc` 0 错，`eslint` 0 问题。concerns 见第 7 节，最需要知情的三条：

1. **T5 如实声明**：现行后端下，重试成功落库、且距采集已超过 3 s 的窗口是 **stale / DEGRADED**，并继续累积 sustained-High（D13 现状）。阶段 5 按裁定 A 实施后它们会变成过期、按 missing 计分。IT-RETRY-STALE 钉住的是**现行**行为，届时会变红，是预期的。
2. **React 绑定层没有 node 单测**（无 DOM 环境，已决定不引入 jsdom）。`useLiveSession.ts`、`useCameraPreview.ts` 的 hook 本体与 `App.tsx` 的停止面板由 `tsc` / `eslint` / `vite build` 与一次真实浏览器冒烟验证（第 5.4 节），不是由变异验证的单测守护。摄像头 `ended` 事件与 `stopped_by_user` 在 Browser 窗格里无法触发（摄像头被屏蔽），只走到了 `start_failed`。
3. **我在冒烟时短暂触碰了主仓库的 vite 依赖缓存**（第 7.3 节第 1 条），已止损并披露。

| 项 | 状态 |
|---|---|
| `retryPolicy.ts`：`MAX_ATTEMPTS_PER_REQUEST = 3`、`classifyFailure`、`backoffMs`（2000 / 4000）、`RETRY_POLICY`、`FAULT_TEXT` | 完成 |
| `liveLoop.ts`：纯模块，api / 摄像头 / 遥测 / id / 时钟 / 定时器全部注入；冻结 payload；3 次投递；可见停止态；手动重试 | 完成 |
| `client.ts`：`X-Attempt-Index` 头、独立的 `TimeoutError`、五个只读 / 写入函数补 `signal` | 完成 |
| `useLiveSession.ts`：改为 `useSyncExternalStore` 绑定；`fault` 与 `error` 分离 | 完成 |
| `useCameraPreview.ts`：`captureFrame` 返回原因码；`ended` 事件作为显示用 `event` 暴露 | 完成 |
| `App.tsx`：停止面板 + Retry、延迟重试状态行、无图像提示、摄像头事件、丢帧计数 | 完成 |
| 后端 IT-RETRY-IDENTITY、IT-RETRY-STALE、文本钉死、全空输入 | 完成（只新增测试，无后端应用代码改动） |
| 每条新增测试的变异验证 | 完成（第 5.3 节：共 86 个变异，其中 4 个最初存活，补测后全部杀死，无遗留存活） |

## 3. 创建 / 修改的文件

**新建（7）**

| 文件 | 说明 |
|---|---|
| `ai/src/liveLoop.ts` | 纯采集循环：`createLiveLoop(deps)` 返回 `getState / subscribe / start / pause / retry / loadSession / replaceRecord`。只 import `./types` |
| `ai/src/liveLoop.test.ts` | 44 个测试（虚拟时钟 + mock api；另有 1 个经真实 `api` 客户端、仅替换 `fetch` 的线上形状测试） |
| `frontend/src/api/retryPolicy.ts` | 预算、分类、退避、`RETRY_POLICY`、各类别的面板文案 `FAULT_TEXT` |
| `frontend/src/api/retryPolicy.test.ts` | 27 个测试 |
| `frontend/src/hooks/useCameraPreview.test.ts` | 6 个测试，守护纯函数 `diagnoseCapture` |
| `backend/tests/test_retry_contract.py` | 14 个用例：IT-RETRY-IDENTITY、IT-RETRY-STALE、IT-RETRY-TEXTS、IT-RETRY-EMPTY |
| `docs/fyp2/implementation/task-08.md` | 本报告 |

**修改（5）**

| 文件 | 说明 |
|---|---|
| `frontend/src/api/client.ts` | `infer(sid, payload, signal, attemptIndex)` 带 `X-Attempt-Index`；`request()` 的 15 s 超时抛 `TimeoutError`；`sessions / session / latest / windows / flag` 接受 `signal`；`LivePayload` 改为从 `ai/src/liveLoop` 再导出 |
| `frontend/src/api/client.test.ts` | 既有 `api.infer` 调用补第 4 个参数；新增 11 个用例（头、暂停 vs 超时、七个函数的取消） |
| `frontend/src/hooks/useLiveSession.ts` | 273 行的内联循环换成对 `createLiveLoop` 的薄绑定 |
| `frontend/src/hooks/useCameraPreview.ts` | `diagnoseCapture`、`CaptureResult`、`CameraEvent`；`captureFrame` 返回 `{frame, reason}` |
| `frontend/src/App.tsx` | `FaultPanel`、延迟重试状态行、无图像提示、摄像头事件行、`live.retrying` 禁用开始按钮 |

没有任何已有测试被删除或弱化（`client.test.ts` 里唯一被改动的既有调用只是随签名补了参数 `1`）。没有改动 `styles.css`：面板复用 `runtime-error` / `runtime-warning` / `runtime-details` / `button`。

## 4. 实现摘要

### 4.1 数据流

```
useLiveSession（React 绑定：浏览器的 api / 摄像头 / 预备遥测 / crypto / 真实定时器）
      │ 注入
      ▼
createLiveLoop（ai/src/liveLoop.ts，纯）
  tick:  sampleFrame() → telemetryAt() → 构造一次 PendingRequest{payload 冻结, deliveries:0}
  deliver(attemptIndex = ++deliveries):  api.infer(sid, payload, signal, attemptIndex)
      成功 → 清 fault、入 history、按配置间隔排下一 tick
      失败 → policy.classify(err):
               counted=false（乱序帧 409 / 非本方 abort） → 丢弃这一帧，下一 tick 照常
               retryable 且 deliveries < 3 且非手动      → 退避 2000 / 4000 ms 后原样重发
               否则                                       → fault.stopped = true，running = false，不排任何定时器
  retry():  reconcile 一次（session → latest → windows）→ 再投递一次（序号接着数）
                │
                ▼
        client.ts：POST /api/sessions/{id}/infer，头 X-Attempt-Index: N，body 逐字节相同
```

### 4.2 T1–T7 逐条如何落地

| 裁定 | 落地 | 守护 |
|---|---|---|
| **T1** 类别名与后端对齐 | `FaultCategory` 共 12 类。503 → `models_unavailable`（不可重试、计数）；新增 `conflict_mode`（409，detail 含 `operation mode` 或 `live model session`；不可重试、计数）、`clock_skew`（422，detail 含 `timestamp is in the future`；不可重试、计数、有专属文案）。`classifyFailure` 按**状态码**分类，只在 409 与 422 两处读 detail；500 不看响应体，一律 `model_runtime`（可重试），502 / 504 等其余 5xx 为 `storage`（可重试） | `retryPolicy.test.ts` 27 个；后端 `test_it_retry_texts_…` 把客户端依赖的五段 detail 文本钉死（改措辞会变红） |
| **T2** 乱序帧 409 丢弃、不停止 | detail 含 `out-of-order` 的 409 → `conflict_stale_frame`，`retryable:false, counted:false`。循环对 `counted:false` 的失败：清掉 pending、`droppedFrames++`、不置 fault、按间隔排下一 tick（下一 tick 是**新**请求）。hash 冲突与未识别的 409 仍立即停止 | `liveLoop.test.ts`「a late frame is dropped, not fatal」两个用例；M6 |
| **T3** 尝试序号与手动重试 | 每次投递序号 = `++request.deliveries`：1 / 2 / 3，手动重试接着 4 / 5。`retry()` 沿用同一 `PendingRequest`（同 payload、同 `request_id`），先 reconcile 一次再投递**恰好一次**；失败：保持停止态并更新 `retryCount` / `attemptIndex`，且**不**自动再试（`!manual` 守卫）；成功：fault 清空、`running` 恢复、按配置间隔排下一 tick，下一个逻辑请求序号重新从 1 开始。`exhausted` 不上报 | `liveLoop.test.ts`「manual retry」与「after a stop」共 10 个；经真实 `api` + 替换 `fetch` 的测试断言线上头依次为 `"1","2","3","4"` 且 body 逐字节相同；M7 |
| **T4** 摄像头停止后循环继续（R5） | `captureFrame()` 为 null 时照发（`image_base64`、`captured_at` 为 null），**不计失败、不停止**；图像与遥测都为 null 时照发（`telemetry_source:"missing"`），UNAVAILABLE 窗口入 history，循环继续；`captureFrame` 抛异常按「无帧」处理。原因码经可选依赖 `captureMissReason()` 进入状态（`lastCaptureMiss`、`imagelessRequests`），**只用于显示**，不影响任何决策。`ended` 事件由 `useCameraPreview` 以 `event` 暴露并显示，不通知循环 | `liveLoop.test.ts`「the camera never stops the loop (R5)」5 个；后端：既有 `test_live_inference_with_no_inputs_is_201_unavailable`（真实模型，在门禁里是 PASS 而非 SKIP）与新增的免权重 `test_it_retry_empty_…`；M5 |
| **T5** 重试与新鲜度 | 见 4.4。后端新增 IT-RETRY-STALE，用 `test_temporal_contract.py` 的 fake clock 与 `_RequestDrivenStubProvider`，断言**现行**行为 | `test_it_retry_stale_…`（3 个）、`…late_resends_keep_accumulating…`；S1 / S2 |
| **T6** IT-RETRY-IDENTITY | 「commit 之后 response 丢失」：首次 POST 成功；以同一 UUID、同一字节在 +0 / +6 s / +12 s 再发（序号头 2 / 3 / 4）→ 响应与首次**逐字节相等**（仍是 window 1，freshness 仍 fresh，不按当前时钟重判）、该 `request_id` 恰好 1 行、`runtime_state`（EMA 链、High 连续时长、两个证据水位线）+ `next_window_id` + 全部记录与首次提交后**快照完全相等**、无 fault 行、下一条新请求是 window 2（编号无空洞）。同一 UUID 改 payload（图像 / `captured_at` / 遥测值 / `telemetry_timestamp` 四种）→ 409 且快照不变 | `test_it_retry_identity_…`（8 个用例）；M9a / b / c |
| **T7** 纯模块边界 | `liveLoop.ts` 只 import `./types`（已 grep 核实）；api、captureFrame、遥测来源、id、时钟、定时器、分类器与预算全部以接口注入。`retryPolicy.ts` 在 `frontend/src/api/`。两者的测试都是 node 环境的 `*.test.ts` | 门禁 |

### 4.3 其余规则的落地

- **冻结 payload**：整个 `LivePayload` 在 `tick()` 里构造**一次**（frame、`captured_at`、遥测、`telemetry_timestamp`、`request_id`），存入 `pending`；`deliver()` 只读它。测试断言重试时 `captureFrame` / `telemetryAt` / `newRequestId` 各只被调用 1 次，两次 `infer` 收到的 body 字符串相等。
- **预算与退避**：`MAX_ATTEMPTS_PER_REQUEST = 3`（1 首发 + 2 重试）；退避 2000 / 4000 ms，`backoffMs` 的类型只接受 `1 | 2`（测试里用 `@ts-expect-error` 守住「没有第三次退避」）；第 3 次失败后不排任何定时器（测试断言 `time.pending === 0`）。
- **暂停 ≠ 失败，暂停 ≠ 超时**：每次投递有自己的 `AbortController` 与 10 s 定时器，定时器触发时置 `timedOut`，此时无论 api 以什么拒绝，都归为 `TimeoutError`；暂停 / 新的 `start()` / 卸载递增 `generation`，之后 resolve 的任何东西都被丢弃。`client.ts` 的 15 s 内部超时同样用 `timedOut` 标志抛 `TimeoutError`，调用方 signal 触发的是 `AbortError`。
- **暂停与停止态**：停止态下 `pause()` 保留 fault 与冻结的请求（Retry 之后仍可用）；非停止态下 `pause()` 清掉 fault 与 pending。`start()` / `loadSession()` 清空停止态。
- **setup 失败**：`api.models` 返回 503 时在建会话之前就停（`api.create` 未被调用），进入与投递失败相同的停止态（`phase:"setup"`）；setup 不自动重试，整个 setup 共用 15 s 期限；Retry 重跑 setup。404（会话不存在）→ `newSessionOnRetry: true`，面板写明「Retry 将新建会话」，Retry 调一次 `api.create`。
- **状态分离**：`fault` 只由循环改动，别处无法覆盖或清除；`useLiveSession` 的 `error` 只承载保存会话 / flag / 导出的错误，由下一次同类操作清除，**成功的 tick 不再清它**。
- **`stale`**（结果显示年龄）仍在 hook 里，与 0.45 的模型输入权重无关，未改动。

### 4.4 T5 声明（须如实陈述）

重试逐字节重发**首次采集**的 `captured_at` 与 `telemetry_timestamp`。2 s + 4 s 退避之后，第 3 次投递距采集已 ≥ 6 s；若第 1 次因 10 s 超时失败，第 2 次投递（+12 s）就已超过 3 s 容差。后端用这些时间戳重新判定 freshness（`inference.py`），因此：

- **现行代码**：这类重试成功落库的窗口是 **stale / DEGRADED**，仍有评分，且按 D13 现状继续累积 sustained-High。IT-RETRY-STALE 的实测：+2000 ms 到达 → fresh / FULL；+6000 ms 与 +12000 ms 到达 → `{"vision":"stale","telemetry":"stale"}`、`DEGRADED`、`RiskScore 100.0 / High`，provenance 里的两个时间戳等于首次采集值；三条逻辑请求各延迟 6 s 送达（server 时间 6000 / 8000 / 10000）→ 全部 stale，`AlertSeverity` 为 `CAUTION, HIGH_ALERT, HIGH_ALERT`。
- **阶段 5（裁定 A）实施后**：这些窗口会变成**过期，按 missing 计分**（`{modality}_expired = true`）；因为两路同时过期，窗口会是 `assessment_available = false`、`UNAVAILABLE`、四个风险字段为 null。两条 IT-RETRY-STALE 测试的 docstring 已写明这一点，它们预期在那时变红并被重写。
- 另一半事实：**幂等重放不会被重判为 stale**。如果首次投递其实已经 commit（response 丢失），重放返回的是**存储的记录**，仍是当时算出的 fresh（IT-RETRY-IDENTITY 断言了这一点）。所以 stale 重试窗口只出现在「更早的投递没有提交」的情形。
- 本 Task **没有**修复这一点，也不得据此声称系统已完整处理过期证据。

### 4.5 超出 brief 字面的取舍（均需知情）

- **`captureMissReason`、`lastCaptureMiss`、`imagelessRequests`、`droppedFrames`、`replaceRecord`**：brief 没有逐字列出。前三个是 T4「原因码用于显示和记录」所需的最小载体（让 React 能随状态订阅它们）；`droppedFrames` 让 T2 的丢帧可见；`replaceRecord` 是因为 history 搬进了循环，flag 切换要替换其中一条。
- **500 一律报为 `model_runtime`**：按 brief「按状态码分类，不依赖响应体」，客户端无法区分 `model_runtime` 与 `storage`（两者都可重试，处置相同）。面板文案对这一类写的是「服务端处理帧时失败（HTTP 500）」，没有声称是模型错误。
- **新增两个后端测试组**（brief 只要求 T5、T6）：IT-RETRY-TEXTS 把客户端靠文本分类的 409 / 422 的 detail 钉死——没有它，后端改措辞会让乱序帧重新停掉会话；IT-RETRY-EMPTY 是不依赖权重的全空输入测试（既有那条需要真实模型，在干净检出上会 SKIP）。
- **`FAULT_TEXT` 放在 `retryPolicy.ts`**：用 `Record<FaultCategory, …>`，新增类别而漏写文案会在编译期报错；也让「时钟偏移有专属文案」可以在 node 里测。
- **手动重试成功后的节奏**按本次投递的发送时刻计（`间隔 − (完成 − 发送)`），草稿按「首次 tick 开始」计，会在多次重试后立刻连发；按配置间隔恢复是 T3 的字面要求。

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

实测：`598 passed, 1 warning`；`Test Files 19 passed (19) / Tests 515 passed (515)`；`tsc exit=0`；`eslint exit=0`。开工前在同一 HEAD 复现基线：`584 passed`；`16 files / 427 passed`；`tsc 0`；`eslint 0`。另跑了 `./node_modules/.bin/prettier --check`（本项触及的 10 个源 / 测试文件），全部符合。

只跑新测试：
```
(cd backend && TMPDIR=$(mktemp -d) PYTHONPATH=. ../.venv/bin/python -m pytest tests/test_retry_contract.py -q -p no:cacheprovider)   # 14 passed
./node_modules/.bin/vitest run --no-cache ai/src/liveLoop.test.ts frontend/src/api/retryPolicy.test.ts frontend/src/api/client.test.ts frontend/src/hooks/useCameraPreview.test.ts
```

**红灯先行**：在写任何实现之前，三个前端测试文件已就绪，`vitest run` 为 `Test Files 4 failed | 15 passed`、`Tests 13 failed | 431 passed`（`retryPolicy.ts` / `liveLoop.ts` 不存在，两个测试文件在文件级失败；`diagnoseCapture` 未导出，6 个相机用例失败；`client.test.ts` 的新用例因缺 `X-Attempt-Index`、`TimeoutError`、`signal` 等失败）。后端 14 个用例落在**已存在**的后端行为上，它们第一次运行就是绿的，其「会变红」的证据是第 5.3 节的变异。

### 5.2 隔离副本（无模型）

```
D=$(mktemp -d) && git -C /Users/liu/Desktop/FYP2-Live-System archive HEAD | tar -x -C "$D" \
  && ln -s /Users/liu/Desktop/FYP2-Live-System/.venv "$D/.venv" \
  && ln -s /Users/liu/Desktop/FYP2-Live-System/node_modules "$D/node_modules"
```
再把本项的 11 个未提交文件覆盖进副本（`HEAD` 不含它们）。副本里没有模型文件：`pytest tests` 为 `591 passed, 7 skipped`（7 个是既有 `requires_models` 用例，预期内）；新增的 14 个不依赖权重。每次变异后从真实树复制回被改文件并 `diff` 确认逐字节一致（每条输出均为 `restored identical: True`）。

### 5.3 变异验证（全部在隔离副本里做）

脚本见第 8 节。下表的失败数是在**最终**测试上重跑全部 73 个前端变异得到的（先后两轮之间只有补测导致的个位数差异，全部仍为红；汇总文件 `final_js_summary.txt`）。共 **86 个变异**：前端 73 个（brief 的 M1–M8 共 10 个变体 + 63 个补充），后端 13 个（brief 的 M9 三个变体 + 10 个补充）。

**brief 指定的 M1–M9**

| # | 变异 | 观察到的结果 |
|---|---|---|
| M1 | `MAX_ATTEMPTS_PER_REQUEST` 改为 4 | 11 个测试变红：`retryPolicy.test`「exactly 3」、`liveLoop.test`「delivers a failing request 3 times - not 4」、「counts per logical request」、「leaves the next request its full budget of 3」、手动重试与 after-a-stop 各用例、线上形状测试 |
| M2 | 重试时重新生成 `request_id` | 9 个变红，含「a 10 s timeout is retried with the SAME payload」、手动重试各用例、线上形状测试 |
| M3 | 重试时重新调用 `captureFrame()` | 6 个变红，含「frozen payload」、「evidence timestamps of a retry are those of the first capture」 |
| M4 | pause 的 abort 计入失败 | **4a**（删掉循环里的 `generation` 守卫）：1 个变红，「a pause is not a failure > aborts the in-flight request…」。**4b**（分类器把 `AbortError` 改为 `counted:true`）：1 个变红，`retryPolicy.test`「a pause or unmount abort…NOT counted」 |
| M5 | `captureFrame` 为 null 时计为失败 | 5 个变红：R5 的全部 5 个用例 |
| M6 | 乱序帧 409 计数并停止 | **6a**（`counted:true`）：3 个变红；**6b**（去掉 `out-of-order` 分支，退化为 `conflict_hash`）：同样 3 个变红，含 `liveLoop.test`「a late frame is dropped, not fatal」两个用例 |
| M7 | 手动重试的序号重置为 1 | 5 个变红：「re-sends the SAME payload once…numbers the delivery 4」、「on failure it stays stopped…」、「a manual retry that fails with a retryable error…」、「a pause keeps the stop panel…」、线上形状测试 |
| M8 | 503 归为可重试 | 3 个变红：`retryPolicy.test` 两条、`liveLoop.test`「…stops after exactly 1 delivery as models_unavailable」 |
| M9 | 后端幂等重放时再次推进状态 | **9a**（删除 `_infer` 的提前返回，且重放分支用 `commit` 代替 `rollback`，即重放消耗一个窗口号）：4 个变红；**9b**（重放时改写 `runtime_state` 并 commit）：4 个变红；**9c**（幂等查找恒返回 None）：9 个变红。变红的都是 IT-RETRY-IDENTITY 的快照 / 恰好一行 / 409 用例 |

**补充变异（前端，均被杀死）**：退避表（1000/2000）、时钟偏移嗅探去除、`conflict_mode` 两个关键词各去一个、500 / 502 / 504 不可重试、`TimeoutError` 不可重试 / 报成 transport、未识别错误不计数、400 / 404 可重试、`clock_skew` 文案泛化、未识别 409 当乱序帧、422 恒为 input；循环：`timedOut` 被忽略、尝试期限 11 s、setup 期限 150 s、计数器跨请求、停止条件 `<=`、退避恒取第一档、手动重试跳过 reconcile、成功后不清 fault、404 不触发新会话、models 503 不停止 setup、暂停忘记冻结请求、重试守卫去掉 `retrying`、相机异常外抛、成功 / 丢帧后零间隔、重试重盖遥测时间戳、丢帧 / 无图像请求不计数、`lastCaptureMiss` 不清除、`getState` 返回副本、`replaceRecord` 空操作、暂停不 abort 请求、迟到响应被接受、history 不按 `window_id` 去重、`retryCount` 卡在 1、fault 不带 request id；`client.ts`：不发头 / 头放进 body、内部超时不转 `TimeoutError`、期限 20 s、五个函数各自忽略 signal、调用方 abort 被误报成 Timeout；`diagnoseCapture`：八个分支各去一个。

**最初存活、补测后杀死的 4 个**：E32「`start()` 不清 fault」（原测试只在成功之后断言 fault 为 null；现在在 `start()` 刚调用、setup 尚未完成时断言）；E34「`cancel()` 不清退避定时器」（`generation` 守卫掩盖了它；现在暂停后立刻断言 `pending === 0`）；E35「`loadSession` 不清 `activeSid`」（原用例之前没有活动会话；现在先建会话再加载历史会话）；E41「手动重试失败后仍自动重试」（预算耗尽掩盖了 `!manual` 守卫；新增「先 400 停止，再手动重试遇到 transport 错误」的用例）。

**后端（均被杀死）**：S1（过期证据按 missing 计分——即阶段 5 的改动）→ 3 个 IT-RETRY-STALE 用例变红；S2（容差放宽到 8 s）→ 2 个变红；T1–T4（四段 409 文案改写）与 T5（未来时间戳文案改写）、T6（未来容差放宽到 120 s）→ 各让 IT-RETRY-TEXTS（T1 另含 4 个 409 用例）变红；E1（LiveInput 要求至少一项输入）→ IT-RETRY-EMPTY 变红；H1（序号头上限降为 100）→ 「replay does not depend on the attempt header」变红。

**一处值得说明**：变异 E24（成功后零间隔排下一 tick）在虚拟时钟里会让 `advance` 无限触发零延迟定时器，该次运行耗时 106 s、23 个测试变红——它是红的，只是慢。

### 5.4 真实浏览器冒烟（不入库）

在**隔离副本**里（不是真实工作树），后端指向一次性 SQLite（`DRA_DATABASE_URL=sqlite:///<tmp>/smoke.db`，端口 18000，没有碰任何开发库），vite 指向端口 15173，Browser 窗格打开页面：

1. 点 Start Monitoring：摄像头被窗格屏蔽（status `denied`），**循环照常运行**，约 9.8 FPS、43 个窗口，页面显示「Camera: denied · failed to start at …」与「No camera image is being sent (the camera could not be started). Vision evidence is missing; monitoring continues with telemetry only.」，窗口为 Partial evidence / DEGRADED（这正是 R5）。
2. 停掉后端：页面先显示延迟重试状态行，约 6 s 后出现**停止面板**：「Monitoring stopped: The server failed while processing the frame」，`Category: model_runtime (HTTP 500)`、`Request id: <uuid>`、`Deliveries: 3 of 3`、`Retry re-sends this same request to the same session.`（vite 开发代理在后端不可达时回 500，所以是 500 而不是 fetch 拒绝）。控制台只有预期的 3 个 500。
3. 重启后端（同一库），点 Retry：面板消失，监控恢复，**同一会话**继续；库里 145 行、145 个不同的 `request_id`、`window_id` 从 1 到 145 连续，被冻结的那条请求在 window 66 恰好落库一次。服务端没有 fault 行（后端宕机期间它从未见到这些请求）。
4. `vite build`（在副本里）通过。

## 6. PASS / FAIL / SKIP 计数

| 门禁 | 基线（`cbe573f`） | 本项之后 | 变化原因 |
|---|---|---|---|
| pytest（真实树，模型经符号链接可用） | 584 passed | **598 passed / 0 failed / 0 skipped** | +14 = `test_retry_contract.py`：IT-RETRY-IDENTITY 参数化 3（0 / 6000 / 12000 ms）+ 头无关 1 + 改 payload 参数化 4；IT-RETRY-STALE 参数化 3 + 累积 1；IT-RETRY-TEXTS 1；IT-RETRY-EMPTY 1。既有测试一个未改 |
| pytest（隔离副本，无模型） | — | 591 passed / 0 failed / **7 skipped** | 7 个 skip 都是既有 `requires_models` 用例；新增 14 个不依赖权重 |
| vitest | 427 passed（16 个文件） | **515 passed**（19 个文件） | +88 = `retryPolicy.test.ts` 27 + `liveLoop.test.ts` 44 + `useCameraPreview.test.ts` 6 + `client.test.ts` 新增 11（头 1、暂停 vs 超时 3、七个函数的取消 7）。+3 个文件 |
| `tsc --noEmit` | 0 错 | 0 错 | — |
| `eslint .` | 0 问题 | 0 问题 | — |

## 7. 遗留问题

### 7.1 计划行号的漂移（对照基线 `cbe573f` 逐处核实）

| 计划写的 | 当前实际 |
|---|---|
| `useLiveSession.ts` 的 `:28`、`:136`、`:142`、`:144`、`:153`、`:157`、`:165`、`:178`、`:181`、`:187-194`、`:204-206` | **未漂移**（逐处核实：`runId.current++` `:28`、`let failures` `:136`、10 s controller `:142`、`captureFrame()` `:144`、`randomUUID` `:153`、`new Date()` `:157`、dedupe `:165`、`setError(null)` `:178`、`!current()` `:181`、`[404, 409, 422, 503]` `:189`、退避表达式 `:205`）。该文件现已整体重写 |
| `client.ts:9-45`（`request`） | `request` 在 `:17-45`（`ApiError` 在 `:8-15`） |
| `client.ts:62-104`（api 对象） | `export const api` 在 `:67`，对象到 `:111`（漂移约 +5 / +7） |
| `client.ts:19-23`（controller 与 15 s 定时器） | `:18-22`（漂移 −1） |
| `client.ts:88-101`（`sessions / session / latest / windows / flag`） | `:93-108` |
| `useCameraPreview.ts:66-71`、`:82-104` | `:66`（`ended` 监听）、`:82-`（`captureFrame`）：**未漂移** |
| `App.tsx:97-116`（start / pause / updateConfig） | `pause` `:92`、`start` `:96`、`updateConfig` `:112`：基本吻合 |
| `App.tsx:156-186`（顶栏按钮） | `:156-180`：基本吻合 |
| `App.tsx:278-293` | `live.stale` 提示 `:278-283`、`AlertBanner` `:285-288`；`live.error` 块在 `:273-277`（正是本次替换处） |
| `App.tsx:324`（`onStop={camera.stop}`） | `:324`：**未漂移** |
| `windows.py:28`（hash 冲突 409） | `:30` |
| `windows.py:56`（乱序证据 409） | `:64`（守卫循环 `:61-`；计划写 `:51-58`） |
| `windows.py:95`（`request_hash`） | `:144` |
| `schemas.py:122-131`（`LiveInput` 校验） | `consistent_inputs` 在 `:123-131`，`LiveInput` 在 `:108`；`normalize_timestamp` 的未来时间戳报错在 `:86` |

### 7.2 未实现 / 有意不做

- **`exhausted` 与客户端侧 `transport` / `timeout` 的服务端上报**：按 C7 / T3 本 Task 不上报。后果：后端宕机或请求超时时，服务端没有任何 fault 行（冒烟已见：`fault_events` 为 0），这类失败只在前端停止面板里可见。若 Task 10 要审计它们，需要补计划里列出的 `POST /api/faults`。
- **setup 阶段不做自动重试**：一次失败即进入可见停止态，由 Retry 重跑。D02 的预算只计 `infer` 请求本身。
- **没有为 `X-Attempt-Index > 1000` 设上限**：后端 `le=1000`，超过会 422（被客户端当作 `input`）。要累计 997 次手动重试才会到，未处理。
- **没有引入 jsdom**（已有裁定），所以 React 绑定层没有 DOM 测试；见下一节。

### 7.3 已知限制与风险

1. **主仓库 `node_modules/.vite` 被短暂触碰（流程偏差，已披露）**。冒烟时我在隔离副本里启动 `vite` dev server，而副本的 `node_modules` 是指向主仓库 `node_modules` 的符号链接，vite 的依赖优化缓存默认写在 `node_modules/.vite`，于是它把主仓库的 `node_modules/.vite/deps` 重新优化了一遍（我看到了日志 `Re-optimizing dependencies because vite config has changed`，立即停掉并改用 `cacheDir` 指向副本后重启）。被写的只是可再生的缓存，没有任何源文件、模型或训练产物；Codex 下次运行 vite 时会自动重新优化。此前与此后的所有 vitest 一律带 `--no-cache`。控制者如需，可自行清理该缓存。
2. **React 绑定层不被单测守护**：`useLiveSession` 的接线（refs 同步、`useSyncExternalStore`、`flag` / `export` 的 `error`）、`useCameraPreview` 的 hook 本体（`release` 的原因码赋值、`ended` 监听）、`App.tsx` 的 `FaultPanel` 没有变异验证的单测。证据只有 `tsc` / `eslint` / `vite build` / 一次冒烟（5.4）。`ended` 与 `stopped_by_user` 两条路径在真实浏览器里**未**走到（摄像头被窗格屏蔽）；它们的判定逻辑（纯函数 `diagnoseCapture`）有单测，但「赋值 `lastStop`」的那几行没有。Task 10 的 Playwright 端到端是补它们的合适位置。
3. **500 无法区分 `model_runtime` 与 `storage`**，面板统一说「服务端处理帧时失败」；另外，任何反向代理在后端宕机时返回的 **503** 会被分类为 `models_unavailable`（不可重试），而不是「后端不可达」。当前的 vite 开发代理返回 500，所以冒烟里是可重试路径；换成会回 503 的网关，宕机会变成「立即停止 + 要求修复部署」。按 brief 的状态码分类规则这是预期，但文案对这种部署会有误导。
4. **非本方发起的 `AbortError`**（既不是暂停也不是期限触发）被当作 `counted:false` 的非失败丢弃、下一 tick 继续。在现有接线里不可达（只有暂停与期限会 abort），但如果将来出现，它会让请求静默丢失而不是计入预算。
5. **暂停于重试退避中会放弃该逻辑请求**：它在服务端留下的 `open` fault 行要等该会话之后的下一次成功提交才被标为 `recovered`（Task 7 语义）。
6. **T5 的两条 IT-RETRY-STALE 测试在阶段 5 必然变红**，需要随裁定 A 一起重写（docstring 已写明目标期望）。

## 8. 证据路径

- 本报告：`/Users/liu/Desktop/FYP2-Live-System/docs/fyp2/implementation/task-08.md`
- 实现：`ai/src/liveLoop.ts`、`frontend/src/api/retryPolicy.ts`、`frontend/src/api/client.ts`、`frontend/src/hooks/useLiveSession.ts`、`frontend/src/hooks/useCameraPreview.ts`、`frontend/src/App.tsx`
- 测试：`ai/src/liveLoop.test.ts`、`frontend/src/api/retryPolicy.test.ts`、`frontend/src/api/client.test.ts`、`frontend/src/hooks/useCameraPreview.test.ts`、`backend/tests/test_retry_contract.py`
- 变异执行器与各批变异脚本（会话临时目录，不入库）：`/private/tmp/claude-501/-Users-liu-Desktop-FYP-In-Cabin-Driver-Assessment--1--claude-worktrees-exciting-keller-fdf913/a1949e26-b3d7-4f7f-bd9f-059bf8cb6f0e/scratchpad/task8/`
  - `mut8.py`：一次一个变异，改隔离副本、跑测试、从真实树复原并 `diff`
  - `run_js1.py`（brief M1–M8）、`run_js2.py`（循环与分类器补充变异）、`run_js3.py`（客户端、摄像头与 4 个补测后重跑）、`run_py1.py`（后端）
  - `final_js_summary.txt`：在最终测试上重跑全部 73 个前端变异的汇总（每行一个变异，含失败数）
  - 隔离副本路径：同目录 `mutdir.txt`；冒烟副本路径：`smokedir.txt`（含一次性库 `smoke.db`）
- 草稿（未提交，仅作起点）：`.superpowers/sdd/2026-10-12-fyp2-live-system-completion/task-8-drafts-run2/`

## 9. 下一项依赖

- **Task 9（Live-only 范围落地）依赖本项**：遥测来源在 `useLiveSession.ts` 的 `telemetryAt(elapsedMs)` 一处注入（现为按 2 s 取模的游标）；Task 9 的「游标单调可注入」应改这一处，循环与测试不用动。R5 的用例（`captureFrame` 为 null / 全空输入照发）在游标改动后必须仍绿，它们不依赖游标取值。
- **Task 10（端到端）可直接复用**：停止面板是 `role="alert"`、`aria-label="Monitoring stopped"`，内含 `Retry` 按钮与 `Category` / `Request id` / `Deliveries: n of 3` 文本；延迟重试状态行是 `role="status"`；摄像头事件在 `Camera:` 行；`X-Attempt-Index` 的线上形状测试可作为 E2E 的对照。ST-BRANCH 系列依赖的「图像为 null 照发 → Partial evidence」已在冒烟中见到。
- **阶段 5（裁定 A）**：必须同步改写 `test_it_retry_stale_…` 两条（期望改为 `missing` + `{modality}_expired`，两路同时过期则 UNAVAILABLE）；`liveLoop.ts` 的文件头注释里的 T5 说明也要随之更新。
- **若要审计客户端侧的 transport / timeout 失败**：需要后端的 `POST /api/faults`（Task 7 报告 7.2 已列为未做），本项没有做。
