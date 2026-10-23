# R10-B 前端实现报告 —— 遥测 seq 与算术采集时间游标、视觉帧元组与 epoch、payload 422 约束、observation_conflict 文案、手动对账失败标志

## 1. 任务编号与名称

- **R10B-FRONTEND**：R10-B 前端（brief 的 B1–B7）。接手 Task 9 留下的 `preparedTelemetryAt`，给 Live 请求带上观测身份（遥测 `seq`、视觉 `(epoch, index)`）和规范采集时间，遵守后端 R10-A 的两条 422 约束，识别新的 409 类别，并处理 Task 9 遗留的「对账失败仍显示自动重发」。
- 依据：用户 2026-10-16 批准的 R10 v3（第 5 条 estp5）与 3 个细节；规格见计划 Global Constraints 的 Alert FSM 一条与 R9 修订记录，以及 `r10/R10_ESTP_proposal_v3.md` 第 5 节；brief 为 `r10b-frontend-brief.md`，共同规则为 `phase2-context.md`；后端实际字段名、422 规则与 409 文本来自 `r10a-backend.md` 与 `r10a-backend-acceptance.zh.md`。
- 工作树 `/Users/liu/Desktop/FYP2-Live-System`，分支 `fyp2/live-system`，基线 HEAD `a495457`。开工前核实：分支与 HEAD 吻合，`git status` 干净。
- 基线门禁（开工前复跑）：pytest **907 passed**、vitest **771 passed（28 个文件）**、tsc 0、eslint 0，与 brief 一致。
- 范围：没有改后端应用代码（`backend/app/` 一字未动，只在 `backend/tests/` 新增测试与数据），没有改融合、FSM、EMA，没有碰模型文件（三个文件的 SHA256 开头仍为 `b3a42e8d…`、`196ca7b1…`、`9802cb06…`）、`docs/fyp2/review/`、计划文件、`CLAUDE.md`、`ai/src/types.ts`、`App.tsx`，也没有动主仓库。

## 2. 实现状态

**DONE_WITH_CONCERNS。** B1–B7 全部实现；四项门禁达标；brief 列出的 U1–U11 在隔离副本里逐项变异，每一项都有明确变红的测试；另外跑了 12 项自己追加的变异和 3 项后端 / 夹具侧变异，全部变红；还在真实浏览器里对真实的钩子、循环和后端做了一次冒烟（不是 Task 10 第 2 部分的测试）。需要控制者知情的 concerns 在第 7 节，最要紧的四条：

1. **游标的「暂停」不仅指用户点 Pause**：循环只要不在运行（用户暂停、故障停机、`loadSession`），游标就冻结；任何让循环重新运行的路径（Start、手动 Retry 成功、手动 Retry 遇到被丢弃的乱序帧）都会恢复游标并开启新分段。这是我对「有效监测时间」的解读，brief 没有逐一写明故障停机的情形（第 7.1 条）。
2. **遥测的「采集时间」按 brief 取时间片起点**，因此一个样本到达服务端时的年龄 = 它在时间片内被取走的位置（0–2000 ms）+ 请求延迟。默认容差 3 s 下余量只有 1 s 减去延迟；容差调到 2 s 时，时间片尾部的请求会因此过期（第 7.2 条）。这是 brief 规定的语义，不是实现偏差，但 PERF-01 和 2 / 3 / 5 s 敏感性测试要把它算进去。
3. **采集视频 `<video>` 挂到了 DOM 上（隐藏）**。理由与实测见第 4 节 B2；这是 brief 允许、但要求说明理由的改动。
4. **`captureTime` 换算用 `performance.timeOrigin`**，页面加载之后系统时钟被回拨时，换算出的时间会比服务端时钟超前；超前超过 5 s 会得到 422（不可重试，会话停下）。brief 没要求防护，我没有加（第 7.4 条）。

## 3. 创建 / 修改的文件

提交含 15 个文件：5 个实现 / 接线文件的修改、6 个已跟踪测试文件的修改、2 个新测试文件、1 个新数据文件、本报告。行数为 `git diff --numstat`（新增 / 删除）或 `wc -l`。

**实现**

| 文件 | 变化 |
|---|---|
| `ai/src/liveLoop.ts` | +145/−22：`FaultCategory` 增加 `observation_conflict`；`LiveFrame` 增加 `captured_at_source`、`vision_frame`；`LivePayload` 增加三个可选字段；新类型 `TelemetryReading`、`TelemetrySource`；导出 `buildLivePayload`（省略规则只在这一处）；`LiveLoopDeps.telemetryAt` 换成 `telemetry: TelemetrySource`，循环在 start / cancel / 停机 / 恢复处调用 `reset` / `pause` / `resume`；`LiveFault.fromManualRetry` |
| `frontend/src/data/preparedSessionInput.ts` | +68/−11：删除 `preparedTelemetryAt`，新增 `createPreparedTelemetryCursor` 与 `PREPARED_TELEMETRY_PERIOD_MS`（只改游标相关部分） |
| `frontend/src/hooks/useCameraPreview.ts` | +202/−16：纯逻辑 `nextCameraEpoch`、`createFrameCapture`（元组缓存、三种模式、回退判定）；钩子接线：采集 `<video>` 隐藏挂载、`requestVideoFrameCallback` 注册与取消、每次摄像头启动取新 epoch；`captureFrame` 只取缓存元组 |
| `frontend/src/hooks/useLiveSession.ts` | +5/−3：`telemetry: createPreparedTelemetryCursor()` |
| `frontend/src/api/retryPolicy.ts` | +23/−10：识别 `observation_conflict`（409 + detail）；`FAULT_TEXT.observation_conflict`；`faultAdvice` 读 `fromManualRetry` |

**测试与数据**

| 文件 | 变化 |
|---|---|
| `ai/src/liveLoop.test.ts` | +450/−28：夹具换成真实游标；K2 的 4 条改写并加 1 条；新增 3 组共 16 条（请求携带身份与算术时间、游标随会话与暂停、B5 标志）；故障表加一行 |
| `ai/src/liveLoopTiming.test.ts` | +7/−1：夹具适配新接口 |
| `ai/src/livePayloadContract.test.ts`（新，246 行） | 19 条：构造器与循环产出的形状等于共享夹具；构造器不可能产出被拒绝的形状 |
| `frontend/src/api/retryPolicy.test.ts` | +160/−11：新 409 的分类与文案、两条 422 的分类、标志对 `faultAdvice` 的作用 |
| `frontend/src/components/runtimeNotices.test.ts` | +54/−0：面板上的标志文案与 `observation_conflict` 面板 |
| `frontend/src/data/preparedRawTelemetry.test.ts` | +232/−24：游标测试按新语义改写；范围守卫更新并保持强度 |
| `frontend/src/hooks/useCameraPreview.test.ts` | +426/−2：epoch、元组缓存、回退判定、钩子接线守卫（含守卫自己的变异表） |
| `backend/tests/test_r10b_payload_contract.py`（新，182 行） | 15 条：真实 `/infer` 路由对共享夹具的 201 / 422 |
| `backend/tests/fixtures/live_payload_shapes.json`（新，111 行） | 前后端共用的字面量 JSON：5 个被接受的形状、2 个被拒绝的形状 |
| `docs/fyp2/implementation/r10b-frontend.md` | 本报告 |

## 4. 实现摘要

### B1 遥测游标（`preparedSessionInput.ts` 与 `liveLoop.ts`）

接口（`liveLoop.ts`）：`TelemetrySource { reset, pause, resume, read }`，`read` 返回 `{ features, seq, acquiredAtMs }`。游标是纯逻辑，时钟由调用者传入（`nowMs`），没有任何全局时钟，用 node 环境单测。

- **算术采集时间**：`分段基线时间 + (seq − 分段起始 seq) × 2000`，写成 `baseMs + step × 2000`。同一个 `seq` 在不同请求里拿到的时间逐字节相同（测试：同一时间片内的 4 个 tick 发出同一个 `seq` 和同一个时间戳）。
- **seq 不封顶**：`seq` 原样发送，行号 = `seq % rows.length`。真实 25 行的第二轮第一个 tick 发 `telemetry_seq: 25`、时间 `…:50.000Z`、特征等于第 1 行。
- **暂停冻结，恢复开新分段**：`pause` 把游标冻结在当时的位置（幂等）；`resume` 开新分段：起始 seq = 冻结的 seq + 1，基线时间 = 恢复时刻（幂等，已在运行时不做事）。「冻结的位置」取暂停时刻的算术位置，不是最后一次发出的 seq；两者只在「最后一次读取到暂停之间恰好越过时间片边界」时差 1，都单调、都有效。
- **新会话 seq 从 0**：`reset`。
- **重试不移动游标**：游标只在 `tick` 里读一次（`buildLivePayload` 之前）；重试、手动重试重发冻结的 payload（测试：3 次自动重试加 1 次手动重试之后 `read` 仍只调用过 1 次，四个请求体逐字节相同）。
- **单调保护**：`step = max(step, floor((now − base)/2000))`，时钟回拨不会让 seq 倒退（倒退会被服务端当作乱序帧丢弃）。
- **循环与游标的生命周期**：`cancel()`（Pause、Start、Retry、loadSession 都经过它）调用 `pause`；故障最终停机调用 `pause`；新会话建好后 `reset`，续接已有会话 `resume`；一次投递成功、或一次被丢弃的乱序帧让循环重新运行时调用 `resume`（手动 Retry 成功是从停机回来的唯一路径，漏掉它游标会永远冻结，遥测证据 3 s 后全部过期；见变异 X1）。
- **逻辑事件时间**：代码注释（`liveLoop.ts` 头部与 `TelemetrySource`、`preparedSessionInput.ts` 的游标）都写明：这是 prepared 回放的**逻辑事件时间**，不是真实传感器的采集时间，也不是发送时刻。

### B2 视觉帧元组（`useCameraPreview.ts`）

纯逻辑 `createFrameCapture`（依赖全部注入：`epoch`、`now`、`timeOrigin`、`draw`、是否支持回调），钩子只做接线。

- **显式模式**：每次 `requestVideoFrameCallback` 回调里**立即**截帧（`drawImage` + `toDataURL`），缓存一个完整元组 `{image_base64, captured_at, captured_at_source, vision_frame: {epoch, index: presentedFrames}}`。有 `captureTime` 时 `captured_at = performance.timeOrigin + captureTime`（来源 `capture_time`），没有时取回调时刻（`callback`）；不是有限数、或换算后不是合法日期，按「没有」处理。`take()`（每个 tick 调用）只返回最新缓存元组，**从不截帧**，所以推理比相机快时几个 tick 拿到同一个元组（服务端判 REPEAT），也不可能把旧元数据与另一次 `drawImage` 的字节拼在一起（变异 U5）。
- **epoch**：`nextCameraEpoch(previous, nowMs) = max(floor(nowMs), previous + 1)`，每次摄像头启动取一次，钩子用 `Date.now()` 并记住。页面刷新后计数器归零，但启动时刻的毫秒数仍然更大；计数器从 0 开始则会在刷新后落在服务端已有 epoch 之后（变异 U6，且后端契约测试证明 epoch 回退会得到 409 乱序）。
- **回退**：不支持 `requestVideoFrameCallback`，或注册后 **1000 ms**（含 1000，判定用 `≥`）内一次回调都没来，进入回退模式；之后每个 tick 自己截帧，不发 `vision_frame`，`captured_at_source = client_clock`，时间取页面时钟，服务端用图像哈希作身份。**回退是终态**：同一次摄像头启动里之后到的回调被忽略，包括「过了期限才来的第一个回调」（变异 U11）。等待期（≤1 s）内的 tick 没有帧（`not_ready`，请求不带图像，不是失败），不在这段时间里偷偷用回退帧，免得身份模式来回切换。
- **隐藏挂载采集 `<video>`**（brief 允许但要求说明理由）：我在浏览器里做了一次对照实测（Chromium 152，Browser 窗格里的 Chrome/152.0.7977.130，用 `canvas.captureStream(30)` 合成流，不是真摄像头）：**分离的 `<video>` 注册回调后 1.5 s 内 0 次回调；挂到 `document.body` 的（1×1、`opacity:0`、`pointer-events:none`、`aria-hidden`）45 次，`presentedFrames` 从 2 到 46**。所以挂载是必要的，否则 Chromium 上几乎必然落入回退模式。释放时 `cancelVideoFrameCallback` 并 `remove()`。该实测页与结果在 scratchpad（第 8 节），不入库。
- **取消与重启**：回调里先重新注册下一次回调再处理，处理中抛错也不会断链；摄像头 `release` 时丢弃缓存与回调句柄，新启动用新 epoch、新缓存、新模式。
- **成本**：每个回调都 `drawImage` + `toDataURL`（brief 的规定）。在上述合成流上测 120 次，中位数 2.2 ms、p95 2.6 ms；真实摄像头画面的 JPEG 会更大，30 fps 下需要 PERF-01 实测。

### B3 payload（`buildLivePayload`）

带上 `telemetry_seq`、`telemetry_timestamp`（算术采集时间）、`vision_frame`、`captured_at`、`captured_at_source`。省略规则只在构造器一处：无图像时不发 `vision_frame` 与 `captured_at_source`；遥测为 null 时不发 `telemetry_seq`，`telemetry_source` 为 `"missing"`，`telemetry_timestamp` 为 null；回退帧不发 `vision_frame`。字段是**不存在**，不是 null（线上字节级核对：4 种组合的键集合逐一断言）。Task 8 的冻结 payload 语义不变。

### B4 `retryPolicy.ts`

`classifyConflict` 先匹配 `observation identity`（后端 `OBSERVATION_CONFLICT_DETAIL` 的子串），返回 `observation_conflict`：不可重试、计数、停机。文案（英文，与表内其它条目一致）：标题 *The same observation identity was sent again with different content*；建议说明服务端已持有该帧 / 样本，这是客户端缺陷，不是网络问题，再发一次无法修复，请新建会话并报告。测试断言全文不含 `request id`，也不与 `conflict_hash`、`conflict_stale_frame` 共用句子。「身份回退」的 `Out-of-order evidence timestamp` 仍归 `conflict_stale_frame`（丢帧、不计数），测试同时钉住四种 409 互不混淆。两条新的 422（`vision_frame requires an image`、`telemetry_seq requires telemetry feature values`）按 `input` 分类、不可重试，也有测试。

### B5 手动对账失败标志

`LiveFault.fromManualRetry: boolean`：自动路径的故障为 false；手动投递失败为 true；`retry()` 里**对账请求失败**为 true（这条路径不增加投递次数，`manualRetries` 分辨不出）；setup 阶段的故障为 false。`faultAdvice` 在 `manualRetries > 0 || fromManualRetry` 时选 `adviceAfterManualRetry`。测试覆盖循环层（同一类别 `model_runtime` 在标志翻转前后建议句子不同；标志不会残留到下一次自动停机）、纯函数层和面板渲染层。

### B6 既有测试

- Task 9 的 K2 tick / 行测试（`liveLoop.test.ts`）按新语义改写：仍用**生产游标 + 真实 25 行**，空行 14 / 17 的请求仍发送，但现在断言没有 `telemetry_seq`、`telemetry_timestamp` 为 null；有遥测的 tick 断言 `seq = floor(tick/4)` 与对应的算术时间，并在 6 个手算 tick 上钉字面量。
- `preparedRawTelemetry.test.ts` 里 2 条旧游标测试（按已过时间取行、50 s 回绕）删除，换成 14 条新游标测试（3 行小表上的手算字面量 11 条，真实 25 行 3 条）。
- **范围守卫继续成立且强度不降**：Live 路径（`useLiveSession.ts`、`liveLoop.ts`）不出现 `PREPARED_SESSION_WINDOWS` / `buildPreparedWindows`；钩子正向检查改为 `telemetry: createPreparedTelemetryCursor()`；对游标自身源码的检查把锚点换成 `export const createPreparedTelemetryCursor`，仍检查「提取的是完整语句」「读 `PREPARED_RAW_TELEMETRY`」「不出现回放对象」，并新增 `PREPARED_TELEMETRY_PERIOD_MS = 2000` 的字面量检查；`liveLoop.ts` 仍只从 `./types` 导入。

### B7 跨语言契约

共享夹具 `backend/tests/fixtures/live_payload_shapes.json`（字面量 JSON，时间基准 2025-01-01T12:00:00Z，与后端测试的假时钟 `at(0)` 一致）：

- 被接受：`frame_and_telemetry`、`no_frame`、`no_telemetry`（遥测为 null）、`fallback_mode`、`nothing`（两者都没有）。
- 被拒绝：`no_frame_but_vision_frame`、`no_telemetry_but_telemetry_seq`；每个都是对应被接受形状加上唯一的违规键（两边的测试都断言了这一点）。

后端 `test_r10b_payload_contract.py` 把它们发给真实 `/infer` 路由（真实路由、真实分类、真实 SQLite 事务，只替身模型概率）：5 个被接受形状各自 201，并断言服务端读到的身份（`vision_obs` / `telemetry_obs` / `vision_frame_id` / `telemetry_seq` / `identity_source` / `captured_at_source` 等，手写字面量）；2 个违规形状 422，且没有写窗口、没有登记身份。另外三条契约：冻结 payload 隔 6 s 原样重发是同一窗口的 201 重放；同一帧同一样本的下一个 tick 是 REPEAT；epoch 回退到 1 得到 409 `Out-of-order evidence timestamp`，更大的 epoch 正常继续。前端 `livePayloadContract.test.ts` 读同一个夹具（`?raw`），断言 `buildLivePayload` 与整个循环对手写输入产出的 JSON 逐键相等，并对「3 种帧 × 2 种遥测」的所有组合断言构造器不会产出任何一条 422 违规。**只加测试，没有改后端应用代码。**

### 浏览器冒烟（不是 Task 10 第 2 部分）

真实的钩子、循环和后端（真实模型）：`vite` 开发服务器 + 一个临时后端（临时 SQLite 与临时故障日志，通过 scratchpad 里的启动脚本把 `DRA_DATABASE_URL` 与 `faults.DEFAULT_SINK_PATH` 指向 scratchpad；没有触碰开发库，没有对开发库启动 uvicorn），摄像头用页面里注入的 `canvas.captureStream(30)` 替代 `getUserMedia`（没有硬件），并包住 `fetch` 记录每个 `/infer` 的请求体与状态：

- Start Monitoring：88 个请求（约 9 s）全部 201；`vision_frame {epoch: 1792389725233, index: 2, 5, 8 …}` 递增，`captured_at_source: callback`（合成流没有 `captureTime`）；遥测 `telemetry_seq` 0 → 4，`telemetry_timestamp` 为 `…:05.258`、`…:13.258`，每 2000 ms 精确前进；同一 seq 的第二个请求在服务端是 `telemetry_obs: repeat`。
- Pause 4 s：期间 0 个请求；Start Monitoring 恢复：首个请求 `telemetry_seq` 比冻结位置大 1，时间戳是恢复时刻（`…:28.589`），之后 11、12。
- Stop Camera：23 个无图像请求，键集合恰好是 `captured_at, image_base64, request_id, telemetry_features, telemetry_seq, telemetry_source, telemetry_timestamp`，没有 `vision_frame` / `captured_at_source`，全部 201。Start Camera：新 epoch `1792389765983` > 旧 epoch，`index` 从 2 重新开始，29 个请求全部 201。
- 把 `requestVideoFrameCallback` 置空后重启摄像头（模拟不支持的浏览器）：33 个请求全部 201，`captured_at_source: client_clock`，无 `vision_frame`，`identity_source: fallback`，`vision_obs: new`；恢复方法后再启动摄像头：显式身份回来，epoch `1792389784928` 更大，34 个请求全部 201。
- 全程没有 409 / 422，控制台无错误；数据库 1 个会话、772 个窗口、0 条故障事件。冒烟结束后两个服务进程已停止，仓库状态与冒烟前一致。

## 5. 执行的测试（精确命令）

门禁（与 `phase2-context.md` 逐字一致；开工前与完工前各跑一遍）：

```
cd /Users/liu/Desktop/FYP2-Live-System
export PYTHONDONTWRITEBYTECODE=1
(cd backend && TMPDIR=$(mktemp -d) PYTHONPATH=. ../.venv/bin/python -m pytest tests -q -p no:cacheprovider)
./node_modules/.bin/vitest run --no-cache
./node_modules/.bin/tsc --noEmit
./node_modules/.bin/eslint .
```

新增后端契约测试单跑：`(cd backend && TMPDIR=$(mktemp -d) PYTHONPATH=. ../.venv/bin/python -m pytest tests/test_r10b_payload_contract.py -q -p no:cacheprovider)` → 15 passed。

**变异**全部在隔离副本里做：`git archive HEAD | tar -x` 到临时目录，覆盖上本项的 14 个改动 / 新增文件，`.venv` 与 `node_modules` 符号链接到**本工作树**的（没有链接主仓库）；每项变异改副本里的一个文件，跑副本的**全部** vitest（后端侧变异跑契约测试文件），再从真实工作树拷回并 `filecmp` 逐字节确认还原；真实工作树不做任何变异。运行器是 scratchpad 里的 `r10b/mutate.py`、`r10b/run_mutations.py`（每项变异的精确改动都在里面，逐字），完整输出 `r10b/mutation-run-final.log`。未变异副本 862 passed；全部变异跑完后还原副本 862 passed；副本里全量 pytest 915 passed + 7 skipped（没有模型文件，依赖真实模型的 7 个测试 skip，预期内）。

| # | 变异（文件：改动） | 变红 | 主要的变红测试 |
|---|---|---|---|
| U1a | `liveLoop.ts`：`telemetry_timestamp` 改回 tick 时的 `deps.now()` | 8 | 「同一时间片内的 tick 发同一个 seq 和同一个时间」、K2 整轮与 6 个手算 tick、暂停 / 恢复 / 乱序帧的时间断言、契约夹具 |
| U1b | `preparedSessionInput.ts`：游标报告读取时刻 | 14 | 同上，加游标单测 |
| U2a | 游标：`pause` 不再冻结 | 9 | 游标「暂停冻结」「恢复开新观测」、循环的暂停 / 恢复 |
| U2b | `liveLoop.ts`：`cancel()` 不再暂停游标 | 2 | 「暂停冻结游标并在恢复时开新观测」「每次恢复各有分段」 |
| U3 | 游标：恢复沿用冻结的 seq | 8 | 游标「恢复开新观测」「每次恢复各有分段」「冻结位置」「幂等」、循环三条 |
| U4a | `liveLoop.ts`：发送 `seq % 25` | 1 | 「循环按行回绕但序号不回绕：第二轮第一个 tick 是序号 25」 |
| U4b | 游标：报告 `seq % rows.length` | 13 | 同上，加游标、循环多条 |
| U5 | `useCameraPreview.ts`：每个 tick 重新截帧却沿用缓存的帧 id | 6 | 显式模式的元组测试（tick 间同一元组、不截帧、新回调整体替换） |
| U6a | epoch 用页内计数器（纯函数） | 2 | `nextCameraEpoch`「启动时刻毫秒数」「页面刷新后仍更大」 |
| U6b | epoch 用页内计数器（钩子） | 2 | 钩子接线守卫的 `EPOCH` |
| U7 | `liveLoop.ts`：无图像时仍发 `vision_frame` | 9 | 「无图像」键集合、「neither」严格等价、K2 无摄像头整轮、契约夹具与组合性质 |
| U8 | `liveLoop.ts`：遥测为 null 时仍发 `telemetry_seq` | 10 | 「遥测为 null」键集合、K2 空行、契约夹具与组合性质 |
| U9 | `retryPolicy.ts`：`observation_conflict` 可重试 | 2 | 循环「一次失败就停」表中的新行、分类单测 |
| U10 | `retryPolicy.ts`：`faultAdvice` 忽略标志 | 3 | 循环层、纯函数层、面板渲染层各 1 |
| U11 | `useCameraPreview.ts`：回退之后又切回显式身份 | 2 | 「过期限后的第一个回调太晚」「回退是终态」 |
| X1 | 手动 Retry 成功后不恢复游标 | 1 | 「故障停机后手动 Retry 成功，游标带着新观测回来」 |
| X2 | 故障停机时不暂停游标 | 1 | 同上 |
| X3 | 续接同一会话时 `reset` | 2 | 暂停 / 恢复两条循环测试 |
| X4 | 新会话用 `resume` 而不是 `reset` | 1 | 「新会话 seq 重新从 0 开始」 |
| X5 | 游标不再单调保护 | 1 | 「时钟回拨不会让序号倒退」 |
| X6 | 回退期限判定改为 `>`（1000 ms 仍等待） | 4 | 「恰好 1000 ms 即回退」等 |
| X7 | 忽略 `captureTime` | 2 | 「有 captureTime 时用 timeOrigin + captureTime」 |
| X12 | 无法成为日期的 `captureTime`（NaN、1e20）当作时间用 | 3 | 三个参数化用例 |
| X8 | 回退帧的来源标成 `callback` | 4 | 回退帧三条测试 |
| X9 | 手动投递失败不打标志 | 1 | 「手动投递失败也是手动重试的失败」 |
| X10 | 对账失败不打标志 | 2 | 「对账失败打标志」「标志不残留」 |
| X11 | 不再识别 `observation_conflict` | 3 | 循环故障表、分类单测两条 |
| B1 | 后端（副本）去掉 `vision_frame requires an image` 校验 | 1（pytest） | 契约测试「无图像的帧 id 是 422」 |
| B2 | 后端（副本）去掉 `telemetry_seq requires telemetry` 校验 | 1（pytest） | 同上，另一参数 |
| B3 | 夹具：`no_frame` 形状带上 `vision_frame` | vitest 2 + pytest 2 | 两边的形状等价测试 |

此外钩子接线守卫自带一张变异表（9 项：epoch 改成计数器、epoch 不记住、不挂载、不移除、回调不截帧、回调先截帧后注册、tick 自己截帧、tick 自己打时间、tick 不取缓存），每一项在测试里就地变红。

## 6. PASS / FAIL / SKIP 计数

| 门禁 | 结果 |
|---|---|
| pytest（真实工作树，模型在位） | **922 passed**，0 failed，0 skipped |
| vitest | **862 passed**，29 个文件，0 failed |
| `tsc --noEmit` | exit 0 |
| `eslint .` | exit 0 |
| pytest（隔离副本，无模型文件） | 915 passed，7 skipped（依赖真实模型的测试），0 failed |

数字的变化逐项解释：

- **pytest 907 → 922 = +15**：全部来自新文件 `test_r10b_payload_contract.py`（9 个函数 / 15 个用例：夹具覆盖 1、5 个被接受形状 5、新鲜度 1、`nothing` 1、冻结重发 1、REPEAT 1、epoch 回退 1、422 的 2 个、「违规键唯一」的 2 个）。既有 907 个用例一个都没有删除、改动或 skip；后端应用代码未改。
- **vitest 771 → 862 = +91**，文件 28 → 29：

| 文件 | 变化 | 说明 |
|---|---|---|
| `ai/src/liveLoop.test.ts` | 58 → 76（+18） | K2 描述块 4 → 5（改写 4 条，加 1 条「手算 tick 上的序号与时间」）+1；故障表加 `observation_conflict` 一行 +1；新组「请求携带身份与算术时间」+6；新组「游标随会话与暂停」+5；新组「手动重试失败与自动预算耗尽区分」+5 |
| `ai/src/livePayloadContract.test.ts`（新） | +19 | 夹具 1、构造器 5 + 1、组合性质 6 + 1、循环 5 |
| `frontend/src/api/retryPolicy.test.ts` | 45 → 52（+7） | 新 409 分类 1、其它 409 不混淆 1、两条 422 分类 2、`observation_conflict` 文案 1、标志对 `faultAdvice` 2 |
| `frontend/src/components/runtimeNotices.test.ts` | 26 → 29（+3） | 面板：标志文案 2、`observation_conflict` 面板 1 |
| `frontend/src/data/preparedRawTelemetry.test.ts` | 38 → 51（+13） | 删 2 条旧游标测试；加游标单测 11 + 真实行 3 + 守卫的周期字面量 1 = 15 |
| `frontend/src/hooks/useCameraPreview.test.ts` | 6 → 37（+31） | epoch 3、显式模式 11、回退 7、接线守卫 1 + 变异表 9 |
| `ai/src/liveLoopTiming.test.ts` | 8 → 8 | 只改夹具 |

被改写的既有断言都写明了理由：`telemetryAt` 接口消失，所有以 `telemetryAt` 为对象的断言改为对 `telemetry.read` 的断言；K2 的「按已过时间取行」改为「按序号取行」；其余既有用例的期望没有被放宽。

## 7. 遗留问题

### 7.1 需要控制者知情的 concerns

1. **故障停机也冻结游标。** 我把「暂停」解读为「循环不在运行」：用户 Pause、故障最终停机、`loadSession` 都冻结，Start 续接已有会话、手动 Retry 成功、手动 Retry 遇到被丢弃的乱序帧都 `resume`。备选做法是只在用户暂停时冻结，故障停机期间让游标继续走（服务端同样接受，seq 只会跳得更大）。我选前者是因为它让「游标运行 ⇔ 循环运行」成为一条不变式，也符合「有效监测时间」。若控制者要备选做法，改动是 `onFailure` 里去掉一行 `pause` 和 `deliver` 里去掉一行 `resume`，并改两条测试（X1、X2 钉的就是这两行）。
2. **遥测证据按设计比到达时刻老 0–2000 ms。** 采集时间 = 时间片起点（brief 的公式），一个 tick 在时间片内第 t 毫秒取走样本，到服务端时年龄 ≈ t + 请求延迟。2 fps 下时间片内的 tick 在 0 / 500 / 1000 / 1500 ms，最坏 1.5 s + 延迟；默认容差 3 s 有余量，容差调到 2 s 时尾部请求可能过期（裁定 A 下按缺失计）。这不是缺陷而是语义，但 PERF-01 的延迟分布与 2 / 3 / 5 s 敏感性测试需要把它算进去，报告里也不应把它说成「传感器年龄」。
3. **回调里每帧 `drawImage` + `toDataURL`。** 这是 brief 的规定。合成流上实测 2.2 ms（中位）；真实摄像头、30 fps 的主线程占用要 Task 10 第 2 部分实测。
4. **`captureTime` 换算依赖 `performance.timeOrigin`。** 页面加载后系统时钟被回拨（睡眠唤醒后 NTP 校正等）时，换算出的采集时间会超前于服务端时钟；超前超过 5 s 是 422 `clock_skew`，不可重试，会话停下。我没有加防护（brief 没有要求，且任何阈值都是新的设计参数）。若要防护，最小做法是「换算结果比回调时刻晚超过 1 s 就改用回调时刻并标 `callback`」。真实摄像头是否提供 `captureTime` 也未实测（合成流没有）。
5. **`FaultPanel` 的两处既有措辞与事实不符，本项没有改。** (a) 对账（15 s 期限）超时时，`timeout` 的建议句子仍写「No answer within 10 seconds」；(b) setup 阶段（没有自动重发）的 `model_runtime` / `timeout` 停机仍写「re-sent automatically」。B5 只要求手动 Retry 的对账失败，我只处理了这一条，并把 setup 阶段的 `fromManualRetry` 明确定为 false。
6. **等待期的 tick 没有图像。** 摄像头启动后到第一个回调之前（通常几十毫秒，最长 1 s）的 tick，请求不带图像（原因 `not_ready`，R5：不是失败）。`Start Monitoring` 在摄像头已运行时调用，这一窗口通常已过。
7. **回退模式的保证较弱。** 回退下服务端用图像哈希作身份，没有显式身份的保证（R10 v3 已知限制）；冻结的相机会产生字节相同的 JPEG 才判 REPEAT。
8. **同一会话里跨摄像头启动切换模式。** 本项只锁死「同一次摄像头启动内不得回退后再切回」。冒烟显示显式 → 回退 → 显式（每次启动 epoch 更大）全部 201，与 R10-A 跟进项的结论一致，但这一条没有单独做成自动化测试。
9. **契约夹具位于 `backend/tests/fixtures/`，前端测试用 `?raw` 读取它。** 这是有意的耦合（单一字面量来源），代价是前端测试依赖一个后端目录路径。
10. **后端契约测试从 `test_r10_observations` / `test_temporal_contract` 导入夹具（`drive`、`fake_clock`）和辅助函数**，沿用该目录已有的做法；这两个模块若改名，本文件会一起坏。
11. **`preparedSessionInput.ts` 有 66 行既有的 prettier 偏差**（视觉概率数组的折行，HEAD 上就是），不是本项引入，没有顺手改；本项新增的部分 prettier 干净，其余被改文件均通过 `prettier --check`。
12. **提交 trailer**：最后一行按任务要求是 `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`；系统给出的署名要求是 `Claude Sonnet 5.5`，我把它放在 Opus 行之前，两行并存，与 R10-A 的做法一致。
13. 没有更新 `CLAUDE.md` 和计划文件（brief 不允许改计划文件；`CLAUDE.md` 在 `348b91c` 已记录 R10）。

### 7.2 没有做的事（范围外）

- rVFC 在真实摄像头上的行为、`captureTime` 是否提供、capture → commit → render 延迟分布、API = DB = latest = UI = export 的逐窗口一致：属于 Task 10 第 2 部分。
- 阶段 5（裁定 A）不在本项实施，现行代码仍有 0.45 stale 档，本项没有碰。
- 没有给 UI 增加「当前视觉身份模式」指示。

## 8. 证据路径

提交内：`ai/src/liveLoop.ts`、`ai/src/liveLoop.test.ts`、`ai/src/liveLoopTiming.test.ts`、`ai/src/livePayloadContract.test.ts`、`frontend/src/api/retryPolicy.ts`、`frontend/src/api/retryPolicy.test.ts`、`frontend/src/components/runtimeNotices.test.ts`、`frontend/src/data/preparedSessionInput.ts`、`frontend/src/data/preparedRawTelemetry.test.ts`、`frontend/src/hooks/useCameraPreview.ts`、`frontend/src/hooks/useCameraPreview.test.ts`、`frontend/src/hooks/useLiveSession.ts`、`backend/tests/test_r10b_payload_contract.py`、`backend/tests/fixtures/live_payload_shapes.json`、本报告。

提交外（scratchpad，供评审复现，不入库）：根目录 `/private/tmp/claude-501/-Users-liu-Desktop-FYP-In-Cabin-Driver-Assessment--1--claude-worktrees-exciting-keller-fdf913/43d73f6d-ed36-4f8a-b584-13c974ccd767/scratchpad/`

| 文件 | 内容 |
|---|---|
| `r10b/mutate.py`、`r10b/run_mutations.py` | 隔离副本的变异运行器（每项变异的精确改动，逐字） |
| `r10b/mutation-run-final.log` | 在冻结后的代码上整体跑一遍的输出（含 UNMUTATED / RESTORED） |
| `r10b/mutation-run-1.log` | 首次完整运行（尚在 `createFrameCapture` 最后一次小改之前，结论相同） |
| `r10b/smoke/` | 浏览器冒烟的后端启动脚本（临时库与临时日志）、`backend.log`、`smoke.db`、`vite.log` |
| `rvfc/smoke.html` | rVFC「分离 vs 挂载」对照实测页 |

评审若要独立复现变异：`git archive HEAD | tar -x -C "$D"`，把本项的 14 个改动 / 新增文件覆盖进去，`ln -s <本工作树>/.venv "$D/.venv"`、`ln -s <本工作树>/node_modules "$D/node_modules"`，按第 5 节表格改一处，在 `$D` 里跑 `./node_modules/.bin/vitest run --no-cache`（后端侧变异在 `$D/backend` 里跑 `pytest tests/test_r10b_payload_contract.py -q -p no:cacheprovider`）。

## 9. 下一项依赖

- **Task 10 第 2 部分**（浏览器与导出端到端、单分支系统测试、PERF-01、证据归档）：
  - 在真实摄像头与目标浏览器上确认 rVFC 回调频率、`captureTime` 是否提供、隐藏挂载的 `<video>` 是否在目标浏览器上都触发回调；
  - ST-BRANCH-T-CONTINUITY 可以按算术时间断言：遥测单路、2 s 节拍的 High 在第 2 个连续样本触发，**前提是**跨度恰为 2000 ms；跨度 < 2000 ms 时延到第 3 个样本（已知限制 K2），不得写死「第 2 个样本必定触发」；
  - PERF-01 要把第 7.1 条第 2、3 点（遥测年龄的构成、回调截帧的成本）算进去；
  - 导出里的新 provenance（`vision_frame_id`、`telemetry_seq`、`identity_source`、`captured_at_source`）的往返由后端 R10-A 的 API 测试覆盖，浏览器侧的逐窗口一致仍要在那里验证。
- **控制者待定**：第 7.1 条第 1、4、5 点（故障停机是否冻结游标、`captureTime` 防护、两处既有措辞）。
- **阶段 5（裁定 A）**不依赖本项，也未被本项改动；落地时遥测的「逻辑事件时间 = 时间片起点」会与 3 s 容差共同决定过期窗口，见第 7.1 条第 2 点。

## 修复轮 1

独立评审给出 2 条 Important（均为 blocks_this_item），本轮只修这两条，未改任何实现代码（`ai/src/liveLoop.ts`、`useCameraPreview.ts` 一字未动），只改了两个测试文件。开工前核实：HEAD 为 `8e9319a`，`git status` 干净。

### 修复轮 1.1 发现与处理

| # | 发现 | 根因 | 处理 |
|---|---|---|---|
| 1 | 钩子层的 U5（每个 tick 重新截帧、却沿用缓存的帧 id）让整个套件保持绿色 | `useCameraPreview.test.ts` 里的接线守卫 `TICK_DOES_NOT_DRAW` 只在 `captureFrame` 的函数体里找 `drawImage\|toDataURL\|new Date\|Date\.now`；调用本文件自己的 `drawFrame()` 助手不含这些词，逃过检查。守卫自带的自测变异体「a tick that draws a fresh picture of its own」只是因为同时多写了一句字面的 `canvasRef.current?.toDataURL()` 才变红 | 守卫的禁用词正则加上 `drawFrame` 与 `canvasRef`（tick 不得调用画图助手，也不得碰画布）；自测变异体去掉 `toDataURL` 拐杖；新增 2 个自测变异体，使每个新词都由一个只靠它才会变红的变异体守护 |
| 2 | `ai/src/liveLoop.ts:637` 的 `deps.telemetry.resume(deps.now())`（`onFailure` 不计数分支）没有任何测试覆盖；删掉该行套件仍是 862 绿 | 唯一覆盖「丢帧」的既有测试「a dropped late frame (not a failure) does not restart or freeze the cursor」只走自动路径，那里游标本来就在运行，`resume` 是空操作；而报告第 4 节 B1 写明的「手动 Retry 的投递被当作乱序帧丢弃」这条恢复路径从未被执行过 | 在 `liveLoop.test.ts` 加 1 条循环测试，覆盖「故障停机后手动 Retry，其投递被 409 乱序丢弃」 |

### 修复轮 1.2 改动

文件（2 个，均为测试；`git diff --stat`：`ai/src/liveLoop.test.ts` +44，`frontend/src/hooks/useCameraPreview.test.ts` +34/−2）：

1. `frontend/src/hooks/useCameraPreview.test.ts`
   - 正则：`/drawImage|toDataURL|new Date|Date\.now/` → `/drawFrame|canvasRef|drawImage|toDataURL|new Date|Date\.now/`，并在旁边写明两个新词的理由（`drawFrame` 是本文件把视频画到画布上的助手，`canvasRef` 是 tick 能够碰到画布的唯一途径）。
   - 变异体「a tick that draws a fresh picture of its own」：只保留 `void drawFrame(video, document.createElement("canvas"));`（画在一块不是钩子自己的画布上，没有 `canvasRef`、`drawImage`、`toDataURL`），因此只有 `drawFrame` 一个词能抓住它；`toDataURL` 拐杖已去掉。
   - 新增变异体「a tick that redraws and sends the new bytes under the cached frame id」：逐字就是评审的 U5c（保留 `take()` 一行，其后 `const fresh = frame && canvasRef.current ? drawFrame(video, canvasRef.current) : null; if (frame && fresh) return { frame: { ...frame, image_base64: fresh }, reason: null };`）。
   - 新增变异体「a tick that reads the canvas by some other route」：`canvasRef.current?.toBlob(() => undefined);`，不含 `drawFrame`、`drawImage`、`toDataURL`，只有 `canvasRef` 能抓住它。
   - 已用 `prettier --write` 格式化（HEAD 版本本就 prettier 干净，修改后同样干净）。
2. `ai/src/liveLoop.test.ts`：在 describe「the telemetry cursor follows the session and the pauses (R10-B)」里，紧接「after a fault stopped the loop, a successful manual Retry …」之后新增
   「after a fault stopped the loop, a manual Retry whose delivery is dropped as a late frame also puts the cursor back in motion with a new observation」。场景与评审复现的一致：脚本为 3 次传输错误加 1 次 `409 Out-of-order evidence timestamp`；+6 s 停机（游标冻结在 seq 3）；+16 s 手动 Retry；断言
   - 第 4 个请求（手动投递）与第 1 个请求逐字节相同，并被丢弃：`droppedFrames: 1`、`fault: null`、`running: true`、`retrying: false`；
   - 下一个 tick（+16.5 s，共 5 个请求）是新观测：`telemetry_seq: 4`、`telemetry_timestamp: "2026-01-01T12:00:16.000Z"`（不是冻结位置 seq 3 / `12:00:06.000Z`）；
   - 再过 1500 ms（+18 s）：`telemetry_seq: 5`、`telemetry_timestamp: "2026-01-01T12:00:18.000Z"`，即分段从重试时刻起按 2000 ms 网格前进，而不是晚一个 tick。

   期望值全部是测试里手算的字面量。

### 修复轮 1.3 执行的命令与输出

隔离副本：`D=$(mktemp -d) && git archive HEAD | tar -x -C "$D"`，`node_modules` 与 `.venv` 符号链接到本工作树（不是主仓库）；变异只改副本里的一个文件，每项之后从真实工作树拷回并 `cmp` 确认逐字节还原；真实工作树不做任何变异。

**先复现（修复前的测试，HEAD 版本）**

| 变异（在副本里） | 命令 | 结果 |
|---|---|---|
| U5c：`useCameraPreview.ts` 在 `const frame = framesRef.current?.take() ?? null;` 之后加评审给出的两行 | `./node_modules/.bin/vitest run --no-cache` | `Test Files 29 passed (29)`、`Tests 862 passed (862)`：**保持绿色，复现了评审的发现** |
| E1：`liveLoop.ts` 删去 `onFailure` 不计数分支里的 `deps.telemetry.resume(deps.now());`（配 HEAD 的 `liveLoop.test.ts`） | 同上 | `Test Files 29 passed (29)`、`Tests 864 passed (864)`：**保持绿色，复现了评审的发现**（864 而不是 862，因为副本里此时已是修复后的 `useCameraPreview.test.ts`，多 2 条） |

**再验证（修复后的测试）**

守卫（发现 1）——变异的是真实的钩子源码，命令均为 `./node_modules/.bin/vitest run --no-cache`（全量）：

| 变异 | 结果 |
|---|---|
| U5c（评审原样：保留 `take()` 一行，其后重画并以新字节顶替缓存帧的图像） | `Tests 1 failed \| 863 passed (864)`；红的是 `…the hook's source meets every wiring requirement` |
| U5d：只加 `void drawFrame(video, document.createElement("canvas"));`，别无其它 | `Tests 1 failed \| 863 passed (864)`；红的同上一条 |
| U5b：替换 `take()` 那一行（保留 `framesRef.current?.take()`，其结果的图像被 `drawFrame` 的新字节顶替） | `Tests 6 failed \| 858 passed (864)`；红的包括 `…the hook's source meets every wiring requirement`（这次不再是只靠锚点漂移而红） |
| 还原钩子源码 | `cmp` 逐字节一致；`Test Files 29 passed (29)`、`Tests 864 passed (864)` |

守卫自己的正则（证明新词各有自测变异体守护），命令 `./node_modules/.bin/vitest run --no-cache frontend/src/hooks/useCameraPreview.test.ts`：

| 变异（改副本里的测试文件） | 结果 |
|---|---|
| G1：正则去掉 `drawFrame` | `Tests 1 failed \| 38 passed (39)`；红的是「a tick that draws a fresh picture of …」 |
| G2：正则去掉 `canvasRef` | `Tests 1 failed \| 38 passed (39)`；红的是「a tick that reads the canvas by some …」 |
| G3：正则回到修复前（两个词都没有） | `Tests 3 failed \| 36 passed (39)`；红的是上面两条加「a tick that redraws and sends the new …」 |

（第一次跑 G1–G3 时，我给正则写了两个反斜杠，`Date\\.now` 不再匹配 `Date.now`，使「a tick that stamps its own time …」多红了一条；那是我的转义错误，不是守卫的行为。改正后重跑得到上表，上表是唯一采信的结果。）

循环（发现 2）——命令均为 `./node_modules/.bin/vitest run --no-cache`（全量）：

| 变异（改副本里的 `liveLoop.ts` 第 637 行） | 结果 |
|---|---|
| E1：删去 `deps.telemetry.resume(deps.now());` | `Tests 1 failed \| 864 passed (865)`；红的是新测试，断言失败在 `liveLoop.test.ts:1548`（`calls[4].payload` 应为 `telemetry_seq: 4` @ `…16.000Z`，实际是冻结位置） |
| E1b：改成 `deps.telemetry.resume(request.capturedAtMs);`（用被丢弃请求自己的采集时刻，而不是现在） | `Tests 1 failed \| 864 passed (865)`；红的是新测试 |
| E1c：改成 `if (!manual) deps.telemetry.resume(deps.now());`（手动路径的丢帧不恢复） | `Tests 1 failed \| 864 passed (865)`；红的是新测试 |
| 还原 `liveLoop.ts` | `cmp` 逐字节一致；`Test Files 29 passed (29)`、`Tests 865 passed (865)` |

**四项门禁（真实工作树，与 `phase2-context.md` 逐字一致的命令）**

```
cd /Users/liu/Desktop/FYP2-Live-System
export PYTHONDONTWRITEBYTECODE=1
(cd backend && TMPDIR=$(mktemp -d) PYTHONPATH=. ../.venv/bin/python -m pytest tests -q -p no:cacheprovider)
./node_modules/.bin/vitest run --no-cache
./node_modules/.bin/tsc --noEmit
./node_modules/.bin/eslint .
```

| 门禁 | 结果 |
|---|---|
| pytest | `922 passed, 1 warning in 18.76s`（与修复前相同；后端与夹具未动） |
| vitest | `Test Files 29 passed (29)`、`Tests 865 passed (865)` |
| `tsc --noEmit` | exit 0 |
| `eslint .` | exit 0 |

### 修复轮 1.4 数字的变化

- vitest **862 → 865 = +3**：`useCameraPreview.test.ts` 37 → 39（+2，新增的两个守卫自测变异体）；`liveLoop.test.ts` 76 → 77（+1，新增的手动 Retry 丢帧测试）。没有删除、放宽或改写任何既有断言；「a tick that draws a fresh picture of its own」的变异体改了编辑内容（去掉 `toDataURL` 拐杖），它仍然断言 `TICK_DOES_NOT_DRAW` 被打破。
- pytest 922 不变，tsc / eslint 仍为 0。
- 上面第 5 节里「钩子接线守卫自带一张变异表（9 项）」现为 **11 项**；第 6 节里 vitest 862、`useCameraPreview.test.ts` 37、`liveLoop.test.ts` 76 的数字以本小节为准。

### 修复轮 1.5 遗留

- 守卫仍是对源码的正则检查，不是在 DOM 里运行钩子（本仓库的测试在 node 环境，无法渲染钩子）。新词只堵住了「tick 里调用画图助手 / 碰画布」这一类；一个自己新写、既不叫 `drawFrame` 也不碰 `canvasRef` 的助手仍然逃得过。该风险由 Task 10 第 2 部分的浏览器实测兜底（真实钩子下，同一 `(epoch, index)` 的请求字节应当逐字相同）。
- 第 7 节其余各条（尤其是 7.1 的 1、4、5 点）不受本轮影响，仍待控制者裁定。
