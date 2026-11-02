# Task 10 第 2a 部分 实现报告 —— Live 端到端框架、ST-LIVE-E2E-01、逐 ID 全行对账、停止面板真实点击、rVFC 实测

## 1. 任务编号与名称

- **TASK-10-PART2A**：计划 Task 10 Step 2，以及 DoD 第 10 行（含 R4 追加的逐 ID 全行对账）；R8 修订记录里「Task 8 转入 Task 10」的三条真实点击断言；R9 / R10 在线上的表现；冲刺计划 v3 G-W4-A 的 `ST-LIVE-E2E-01`（IT-UI-01 oracle）；R10-B 遗留的 rVFC 实测。
- 工作树 `/Users/liu/Desktop/FYP2-Live-System`，分支 `fyp2/live-system`，基线 HEAD `e010a6a`（开工前核实：分支与 HEAD 吻合，`git status --porcelain` 为空）。
- 基线门禁：pytest 922 / vitest 870 / tsc 0 / eslint 0（与 brief 一致）。
- **不属于本部分**：单分支系统测试 `ST-BRANCH-*`、W4 证据归档（2b）。本部分没有做，也没有产出任何性能结论（E3 只记录）。
- **产品代码零改动**：`git diff --numstat` 的已跟踪文件只有 `backend/tests/conftest.py`（+39 / −1）。请求拦截、合成 `ended`、路由故障、rVFC 探针全部在测试工具里。唯一读到的产品钩子是 Task 10 第 1 部分已有的只读访问器 `window.__draLiveTimings`（E3 里读，没有新增任何钩子）。
- 没有派发子 agent；没有执行任何被禁的 git 操作；没有碰主仓库、模型文件、`docs/fyp2/review/`、计划文件、开发库。

## 2. 实现状态

**DONE_WITH_CONCERNS。** 四项门禁全绿：pytest **934 passed / 0 failed / 0 skipped**，vitest 870 passed，`tsc` 0，`eslint` 0。E1 / E2 / E3 全部落地，8 条指定变异各有明确变红的测试。**没有发现产品缺陷**（没有因此停下）。concerns 见第 7 节，最需要知情的三条：

1. **「provenance 里三个模型的 SHA256」无法按字面成立。** 运行时只加载两个文件（ONNX 视觉模型、XGBoost 遥测模型），provenance 里只有 `vision_model_sha256` 与 `telemetry_model_sha256` 两个。第三个（视觉 `.pt` 检查点）不被加载、没有 provenance 条目。我的处理：两个 provenance 值与 `GET /api/models` 的值逐窗口对冻结基线字面量；`.pt` 用磁盘文件的 SHA256 对基线。
2. **E1 用的是 5 fps 假摄像头，不是默认的 20 fps。** 默认假摄像头（20 fps）下 10 Hz 的请求循环追不上相机，三次实测 181 个窗口里 `vision_obs` 全是 `new`，从不出现 `repeat`；而 brief 要求「`vision_obs` 有 `new` 也有 `repeat`」。`--use-fake-device-for-media-stream=fps=5` 让循环快于相机，实测约一半窗口是 `repeat`。E2、E3 用默认相机。
3. **e2e 让全量 pytest 从约 22 s 变成约 54–61 s。** 它们是门禁的一部分（brief 要求），且依赖 node / npm、Playwright 的 Chromium、模型文件。缺模型会按既有机制显式跳过；缺浏览器是**失败**而不是跳过（我认为静默跳过正是「什么都没证明的绿」）。

| 交付 | 状态 | 守护 |
|---|---|---|
| E1 ST-LIVE-E2E-01 | 完成（`TestStLiveE2E01`，8 个测试，一次监测运行） | M1、M2、M3、M7、M8 变红 |
| E2 停止面板真实点击 | 完成（3 个测试） | M4、M5、M6 变红 |
| E3 rVFC 实测 | 完成（1 个测试，只记录；3 次运行的原始 JSON 入证据） | 不设门槛，无变异 |

## 3. 创建 / 修改的文件

提交含 4 个测试侧文件、本报告、1 个证据目录；**无应用代码**。

| 文件 | 变化 |
|---|---|
| `backend/tests/test_live_e2e.py`（新，约 700 行） | `e2e` 标记；`TestStLiveE2E01`（8 个）、E2（3 个）、E3（1 个）；`LiveRun`、`Parties`、`parties_diffs` |
| `backend/tests/e2e_support.py`（新，约 610 行） | 单 uvicorn 的启动 / 停止、`npm run build`、`ApiTap`（Playwright 路由：记录、abort、hold）、`Chrome`、五处存放位置的读取与逐字段比对、CSV 规则、界面显示格式的独立实现（`half_up`、`fixed`、`percent`）、`PROBE_JS`（init script） |
| `backend/tests/e2e_server_main.py`（新，35 行） | e2e 的 uvicorn 启动器：把故障 sink 指到测试目录；`DRA_DATABASE_URL` 不是测试一次性库就拒绝启动 |
| `backend/tests/conftest.py` | +39 / −1：`pytest_configure` 注册 `e2e` 标记；会话级 `e2e_dist`（`npm run build`）与 `e2e_server`（单 uvicorn）；文件头注释「Four jobs」改「Five jobs」并补第 5 条。助手模块一律在 fixture 内延迟导入，不选 e2e 的运行不会构建也不会起进程 |
| `docs/evidence/2026-10-19/task-10-part2a/`（新） | `e2e-pytest.log`、`rvfc-measurement-run{1,2,3}.json`、`mutations.txt`、`gate-{pytest,vitest,tsc,eslint}.txt`（第 8 节） |
| `docs/fyp2/implementation/task-10-part2a.md` | 本报告 |

## 4. 实现摘要

### 4.1 运行环境（计划 Step 2 的既定做法）

- **一个 uvicorn 进程**同时挂 `/api` 与构建好的 `dist/`（`app/main.py` 在 `dist/` 存在时挂 StaticFiles），同源访问，**不启动 vite dev server**。进程由 `e2e_server_main.py` 启动，工作目录是一次性目录（`Settings` 的 `env_file=".env"` 相对工作目录，开发者的 `backend/.env` 因此无法改库），`DRA_DATABASE_URL` 指向 `tmp_path_factory` 下的 SQLite，故障 sink 重定向到同一目录，端口取空闲端口。**不碰开发库**；启动器在 `DRA_DATABASE_URL` 与测试给定的一次性库不一致时直接退出。
- **每个 pytest 会话先跑 `npm run build`**（`dist/` 被 git 忽略、可能过期）。构建失败、`npm` 不在 PATH、`dist/index.html` 不存在都是硬错误。
- Playwright 1.60（`.venv`）+ 已装的 Chromium **148.0.7778.96**（R10-B 报告里是 Browser 窗格的 Chrome 152，不是同一个浏览器）。启动参数沿用 `--use-fake-device-for-media-stream`、`--use-fake-ui-for-media-stream`，上下文授予 `permissions=["camera"]`；E1 的相机参数见 4.2。每个测试一个 Chromium，上下文各自独立（localStorage 不串）。
- 没有模型文件：`pytestmark` 里的 `requires_models`（与 `test_live_inference.py` 同一句 reason）让 12 个测试按既有机制显式跳过并出现横幅；`DRA_REQUIRE_MODELS=1` 时判为失败。我在没有模型的隔离副本里验证过两种情况（第 6 节）。`test_model_gate.py::test_every_model_skipif_uses_the_reason_the_gate_recognises` 会扫描本文件的标记，保持通过。

### 4.2 记录与控制全部在测试侧

- **`ApiTap`**（Playwright `page.route("**/api/**")`）：`/infer` 与 `POST /api/sessions` 走 `route.fetch()`，请求体（逐字节）、`X-Attempt-Index`、响应体都被记录，浏览器照常拿到真实应答；其余请求原样放行。三个开关：`abort_infer = N`（接下来 N 个 infer 请求在网络层失败，不到达服务端）、`hold_infer`（infer 请求不应答，服务端也看不到）、`abort_session_posts = {n}`（第 n 个 `POST /api/sessions` 失败）。
- **让服务端静止（E1 的关键技巧）**：收集够窗口后设 `hold_infer`。循环一次只发一个请求，所以下一个被 hold 住的请求出现，就意味着上一个已经应答并被浏览器接收；服务端库里恰好是浏览器收到的那些窗口，界面「最新」面板显示的就是它们里最新的一个。然后读界面、点 **Pause**（浏览器自己取消被 hold 的请求），之后所有断言都面对一个静止的服务端。这样既没有「Pause 中途取消一个服务端已提交的请求」造成的库内多一行，也没有读界面与读 `/risk/latest` 之间新窗口插队的竞态。`Chrome.close()` 会 `abort` 残留的被 hold 路由再 `unroute_all`，避免 Playwright 在拆除时打印 `CancelledError`。
- **`PROBE_JS`**（`add_init_script`，页面脚本之前注入）：包装 `HTMLVideoElement.prototype.requestVideoFrameCallback`（记录每次注册、每个回调的时刻、耗时、`presentedFrames`、`captureTime` 是否存在、回调时刻减 `captureTime`）、`CanvasRenderingContext2D.drawImage` 与 `HTMLCanvasElement.toDataURL`（耗时），以及 `navigator.mediaDevices.getUserMedia`（留下每个 stream，E2 用它给采集轨道派发合成的 `ended` 事件；`MediaStreamTrack.stop()` 不会触发 `ended`）。
- `wait_until`：用 `page.wait_for_timeout` 轮询（路由处理函数只在 Playwright 调用内运行，所以不用 `time.sleep`）；应用出现停止面板而测试没预期时**立即失败并带面板文字**，不等超时。

### 4.3 E1：`TestStLiveE2E01`（一次监测运行，8 个测试，按定义顺序共享）

收集条件：≥ 10 个窗口且遥测序号覆盖 0..3（约 6 s，实测 60–62 个窗口，约 10 Hz）。运行中出错（停止面板、超时）不抛异常，写入 `run.error`，由第 1 个测试报告，这样变异 M7 得到的是一条带原因的 FAILED 而不是 fixture 错误。

| 测试 | 断言 |
|---|---|
| `test_01` | 每个请求都是一个不同的已存窗口：`window_id` 为 1..N 连续；`request_id` 唯一且等于 provenance 里的 `request_id`；所有投递的 `X-Attempt-Index` 都是 `1`；除那个被 hold 的请求外全部 201；只创建了一个会话；库里恰好 N 行（没有被取消却已提交的窗口）；该会话 0 条 `fault_events` |
| `test_02` 契约 | 每个窗口：键集恰为 21 个契约字段（字面量清单）；`operation_mode = LIVE_MODEL_RUNTIME`；`provenance.vision_source = camera_frame`、`telemetry_source = prepared_replay`、`provider = MobileNetV3ONNX+XGBoost`；视觉 10 类（首项 `safe_driving`）、遥测 3 类（`Safe / Aggressive / Distracted`）、两组概率和为 1；D01 不变式（`assessment_available == (RiskScore is not None) == (SystemHealth != "UNAVAILABLE")`，四个风险字段同有同无）；两个 provenance SHA256 等于冻结基线字面量；窗口全部 `fresh / FULL`。另：三个模型文件的磁盘 SHA256 与 `GET /api/models` 的两个 SHA256 都对基线字面量 |
| `test_03` R10 在线上 | 见 4.4 |
| `test_04` 五方对账 | 见 4.5 |
| `test_05` IT-UI-01 | 见 4.6 |
| `test_06` 五个视图 | Signal Inspector：窗口列表按钮数 == N、首项 `Window N`；选窗口 3 后 RiskScore / RiskLevel / Evidence Type / P_distraction / Telemetry non-safe / 两个 freshness / Latency / Flag 与记录一致；10 个视觉类别的标签与两位小数概率逐行一致。Risk Trends：图表渲染、表格 N 行（新到旧）、每行的 RiskScore（一位小数）/ RiskLevel / Alert / Evidence Type / Flag 与记录一致。Explanation：RiskScore、两个 P（两位小数）、RiskLevel 与记录一致。Configuration：点 **Export JSON / Export CSV**，下载的字节等于服务端导出的字节。回到 Live Monitor。全程无控制台错误、无页面异常 |
| `test_07` flag | 在 Inspector 里选窗口 3 点 **Flag**：界面出现 `Unflag`；`("PATCH", "/api/sessions/{sid}/windows/3/flag?flagged=true")` 在请求记录里；之后五处对**所有窗口**逐字段重新对账（期望 = /infer 的体，仅窗口 3 的 `flagged` 变为 `True`）；JSON 导出与 CSV 导出里窗口 3 是 `true`、且只有它；`/risk/latest`（窗口 N）`flagged` 仍为 `False`；Risk Trends 里恰好窗口 3 显示 `flagged` |
| `test_08` | 全程没有控制台错误、页面异常；`fault_events` 对该会话为 0 |

### 4.4 R10 在线上（`test_03`）

- **帧身份**：浏览器支持 `requestVideoFrameCallback` 时，产品必须注册过回调（`probe.regs` 非空，否则判产品没注册）。若回调触发（本环境触发）：每个带图像的请求都有 `vision_frame {epoch, index}`（epoch 在整次运行内唯一、index 不减）、`captured_at_source ∈ {capture_time, callback}`；同一 `(epoch, index)` 的请求图像字节与 `captured_at` 逐字节相同（重发的是缓存元组）。若回调不触发则断言回退路径（无 `vision_frame`、`client_clock`）。本环境实测走显式路径。
- **遥测**：第一个请求 `telemetry_seq == 0`；序号不减、不跳号；同一 seq 的 `telemetry_timestamp` 在所有请求里**逐字节相同**；相邻 seq 的时间恰好差 2000 ms；相邻 seq 首次出现的墙钟间隔均值在 [1.8, 2.3] s（实测 2.03 s：偏移 0 / 2.02 / 4.06 / 6.09 s）。
- **服务端的判定**：第 i 个窗口的 `telemetry_obs` 是 `new` 当且仅当 seq 与前一个请求不同；`vision_obs` 是 `new` 当且仅当帧身份与前一个请求不同；两个分支都**同时出现** `new` 与 `repeat`（实测视觉 31–32 new / 29–30 repeat，遥测 4 new / 57 repeat）。provenance 含全部 8 个身份字段与 4 个过期字段；`telemetry_seq` / `vision_frame_id`（`"epoch:index"`）/ 三个 `*_identity_source` 与请求吻合；provenance 里的 `telemetry_timestamp` 与 `captured_at` 等于**规范（首次见到）采集时间**；`vision_expired / telemetry_expired` 为 `False`、两个 `*_age_s` ∈ [0, 3)。
- **repeat 就是它所重复的观察**：`vision_obs = repeat` 的窗口，`P_distraction` 与 `visual_top_classes` 等于前一个窗口；`telemetry_obs = repeat` 的窗口，`P_telemetry_anomaly` 与 `telemetry_behavior_classes` 等于前一个窗口。

### 4.5 逐 ID 全行对账（`test_04`）与 CSV 规则

对每个 `window_id`，五处对 `RiskUpdate` 的 **21 个契约字段**逐字段相等，`provenance` 逐键比较，浮点精确相等（`deep_diff` 报告每一处差异及路径，`True` 不等于 `1`）：

1. `/infer` 的响应体（`ApiTap` 在浏览器里拦截记录）；
2. 数据库行：`payload`（JSON）与全部类型列（`window_id`、`timestamp`、`p_distraction`、`p_telemetry_anomaly`、`risk_score`、`risk_level`、`dominant_evidence`、`alert_severity`、`system_health`、`assessment_available`、`latency_ms`、`flagged`、`request_id`）逐一对照；
3. `GET /windows`（`after=0&limit=1000`）；
4. JSON 导出（顶层恰为 `{"session_id", "records"}`）；
5. CSV 导出。

**CSV 规则（写在 `csv_row_diffs` 与 `test_04` 的文档字符串里）**：每个契约字段都有 CSV 列，所以 21 个字段**全部**比较，没有跳过的列。标量按导出器自己的显式编码：`None` ↔ 空单元格，`bool` ↔ `true` / `false`，整数 ↔ 整数文本，浮点 ↔ `repr`（`float(cell) == value` 精确相等）；六个结构化字段（`provenance`、`modality_freshness`、`visual_top_classes`、`telemetry_behavior_classes`、`telemetry_feature_contributions`、`telemetry_features`）按单元格里的 JSON 文档比较；导出器从 provenance 里提出来的 7 列（`request_id`、`vision_source`、`telemetry_source`、两个模型 SHA256、`P_distraction_raw`、`P_telemetry_raw`）与 provenance 里的值比较；`payload_unreadable*` 两列在可读行上必须为空。另外：各处窗口集合相同（1..N）、`GET /api/sessions/{id}` 的 `total_windows == N`、`GET /risk/latest` 的整条记录等于最后一个窗口。

### 4.6 IT-UI-01 oracle（`test_05`）

服务端静止那一刻，从 DOM 读 Live Monitor 的「最新」面板（`read_latest_panel` 一次 `page.evaluate`，同一个 JS 任务里读完，不会被 React 提交打断）：会话条（Session / Window / Stored records）、顶部「Current Monitoring Status」横幅文字与徽章、仪表盘的 `aria-label` 与中心数字、`RiskLevel / Evidence / Alert` 徽章、两张模态卡（百分比、新鲜度、两位小数概率）。期望值由 `GET /risk/latest` 经**测试里独立实现的显示规则**写出：RiskScore 一位小数、概率两位小数、百分比 = `round(round(p,2)×100)`，按十进制数字的 **half-up** 舍入（不是银行家舍入，也不是二进制 `toFixed`）。

### 4.7 E2：停止面板真实点击

- **传输故障后 Retry**：`abort_infer = 3`，Start Monitoring。第一个逻辑请求的三次投递（间隔 2 s、4 s）全部在网络层失败，界面出现停止面板：`Monitoring stopped: The backend cannot be reached`、`Category: transport`、`Request id: <第一个请求的 id>`、`Deliveries: 3 of 3`、`Retry re-sends this same request to the same session.`；三次的 `X-Attempt-Index` 为 1、2、3，请求体逐字节相同，库里 0 行。恢复路由，点 **Retry**：第 4 次投递的 `X-Attempt-Index` 是 **4**，体与第一次逐字节相同，201、`window_id == 1`；**没有新建会话**（`POST /api/sessions` 只有 1 次，新增会话集合恰为 `{sid}`）；该 `request_id` 在库里恰好 **1** 行；循环继续（窗口 1、2、3、4…，同一会话，之后的投递 `attempt == "1"`、`request_id` 各不相同）；停止面板消失、`Monitoring active`。
- **New Session 失败后 Retry 新建会话**：先跑到 3 个窗口；让第 2 次 `POST /api/sessions` 失败，点 **New Session**：停止面板写 `Failed during setup, before any request was sent` 与 `Retry repeats the setup: the model check, then a NEW session.`；点 **Retry**：第 3 次 `POST /api/sessions` 成功，新会话 id 与旧的不同，新增会话集合恰为 `{旧, 新}`，新会话窗口编号从 1 重来（1、2、3），界面会话条显示新 id；旧会话在失败之后没有再增加窗口。
- **摄像头意外断开与主动 Stop Camera**：跑到 5 个带图窗口；对采集轨道派发合成 `ended`：状态行 `Camera: error · disconnected at …`，提示 `(the camera was disconnected)`；循环继续（又收到 5 个窗口，请求体无 `image_base64`、无 `vision_frame`，遥测仍在，应答 `modality_freshness = {vision: missing, telemetry: fresh}`、`vision_source = missing`）。再点 **Start Camera**（新 epoch，大于旧 epoch，图像恢复）后点 **Stop Camera**：状态行 `Camera: idle · stopped by you at …`，提示 `(the camera was stopped)`，循环继续（又 5 个无图窗口）。两种情况的状态行（去掉时刻）与提示都不同，且都没有出现停止面板（R5）。

### 4.8 E3：rVFC 实测（只记录，不设门槛）

默认假摄像头（20 fps），60 个窗口后读探针与请求记录；结果写入 `rvfc-measurement.json`（`DRA_E2E_MEASUREMENTS_DIR` 指定目录时落盘，否则写在 `tmp_path`），并打印一行 `E3-MEASUREMENT {...}`。**只断言结构**：运行健康（≥ 60 个窗口）；浏览器支持时产品确实注册过回调；回调触发则每个请求有 `vision_frame`，否则全部走 `client_clock` 回退。实测结果见第 6 节末尾的表与第 7 节的对比。

## 5. 执行的测试（精确命令）

门禁（brief 与 `phase2-context.md` 的精确命令，在最终代码上运行并保存了原始输出）：

```
cd /Users/liu/Desktop/FYP2-Live-System
export PYTHONDONTWRITEBYTECODE=1
(cd backend && TMPDIR=$(mktemp -d) PYTHONPATH=. ../.venv/bin/python -m pytest tests -q -p no:cacheprovider)
./node_modules/.bin/vitest run --no-cache
./node_modules/.bin/tsc --noEmit
./node_modules/.bin/eslint .
```

e2e 单独运行与证据采集：

```
cd backend
TMPDIR=$(mktemp -d) PYTHONPATH=. ../.venv/bin/python -m pytest tests/test_live_e2e.py -v -s --durations=0 -p no:cacheprovider
DRA_E2E_MEASUREMENTS_DIR=../docs/evidence/2026-10-19/task-10-part2a  (……  -k e3 重复两次)
pytest tests -m e2e --collect-only -q        # 选择 / 排除： -m e2e  /  -m "not e2e"
```

变异（隔离副本，见 6.3）：

```
D=$(mktemp -d) && git archive HEAD | tar -x -C "$D" && ln -s <worktree>/.venv "$D/.venv" && ln -s <worktree>/node_modules "$D/node_modules"
# 三个模型文件以只读符号链接接入 $D/ml/outputs/{vision,telemetry}/；把本项四个测试侧文件拷入 $D/backend/tests/
# 每个变异：改一处 → 在 $D/backend 里跑 pytest tests/test_live_e2e.py -q -p no:cacheprovider -rf → 用 git show HEAD:<path> 还原 → 逐字节比对还原结果
```

没有模型文件的环境（另一个隔离副本，不链接模型、不链接 node_modules）：

```
pytest tests/test_live_e2e.py tests/test_model_gate.py -q -p no:cacheprovider
DRA_REQUIRE_MODELS=1 pytest tests/test_live_e2e.py -q -p no:cacheprovider
```

## 6. PASS / FAIL / SKIP 计数

### 6.1 门禁

| 门禁 | 基线 | 之后 | 变化的解释 |
|---|---|---|---|
| pytest | 922 passed | **934 passed / 0 failed / 0 skipped**（60.81 s；另一次 53.71 s） | +12，全部是新增：`TestStLiveE2E01` 8 + E2 3 + E3 1。没有替换、删除或改动任何既有测试。耗时从 W3 门禁的约 22 s（pytest 自报 21.95 s）变成约 54–61 s |
| vitest | 870 passed（29 个文件） | 870 passed（29 个文件） | 无变化：没有改任何 TS |
| tsc | 0 | 0 | — |
| eslint | 0 | 0 | — |

`git status --short` 在四项门禁之后只有本项文件；`dist/` 与 `tsconfig.tsbuildinfo` 被 e2e 的构建重新生成，二者都被 git 忽略。

**e2e 耗时**：单独运行 12 passed 在 34.2 / 34.4 / 33.9 / 34.7 s（连续 4 次）、37.7 / 38.2 s（含 `-v -s`）；在 12 个满负荷 Python 进程（8 核机器）的压力下一次 44.2 s，仍全部通过（另有一次我以为加了压力、实际上 macOS 没有 `timeout` 命令，压力进程根本没起，那次 34.5 s 只算一次普通运行，不算压力测试）。耗时构成（`--durations=0`）：`TestStLiveE2E01` 的 fixture 约 13–16 s（含会话级 `npm run build` 约 4–5 s、uvicorn 启动、Chromium 启动、模型加载、约 6 s 收集）；E2 传输故障测试约 7.1 s（含 2 s + 4 s 退避）；E3 约 6.6 s；E2 另外两个各约 2.3–2.5 s；`test_06` 约 2.3 s；`test_07` 约 0.7 s；其余各 < 0.2 s。

### 6.2 e2e 的 12 个测试（全部 PASS）

`TestStLiveE2E01::test_01` … `test_08`（8）、`test_e2_transport_faults_stop_the_loop_and_retry_resumes_the_same_session`、`test_e2_a_failed_new_session_makes_retry_create_a_new_session`、`test_e2_an_unexpected_camera_loss_and_stop_camera_read_differently_and_neither_stops_the_loop`、`test_e3_rvfc_behaviour_on_the_fake_camera_is_recorded`。

没有模型文件的隔离副本：`test_live_e2e.py` + `test_model_gate.py` 得到 **8 passed, 12 skipped**，12 个 e2e 全部列入 `12 MODEL-DEPENDENT TEST(S) NOT RUN` 横幅，没有构建 `dist/`、没有起进程；`DRA_REQUIRE_MODELS=1` 时 **12 errors in 0.07 s**（每个跳过变成失败）。

### 6.3 变异（8 条，全部变红；在隔离副本里对**字节级等同于提交内容**的测试文件重跑过）

隔离副本：`git archive HEAD`（`e010a6a`）、`.venv` 与 `node_modules` 符号链接、三个模型只读符号链接、四个测试侧文件拷入。每个变异跑整个 `test_live_e2e.py`（含 `npm run build`，前端变异因此被构建），然后用 `git show HEAD:<path>` 还原并**逐字节比对**（6 个被改的文件全部 identical）。基线（M0，副本里未变异）：12 passed。真实工作树从未被变异。原始输出与每个变异的补丁在 `mutations.txt`。表里引用的具体数字（窗口号、分数、差异条数）随运行而变，取自最后一轮运行。

| # | 变异（文件） | 变红的测试 | 观察到的断言 |
|---|---|---|---|
| E2E-M1 | JSON 导出漏掉 `provenance.vision_frame_id`（`routers/export.py`） | `test_04`、`test_07` | `61 differences, first ["window 1 export JSON: provenance.vision_frame_id: left has '1792407342206:9', absent on the right", …]` |
| E2E-M2 | `/risk/latest` 返回倒数第二个窗口（`routers/risk.py` 加 `.offset(1)`） | `test_04`、`test_05`、`test_07` | `assert (59 == 60)`（最新窗口号 ≠ 最后一个窗口） |
| E2E-M3 | 界面 RiskScore 多加 0.1（`utils/format.ts` 的 `formatRiskScore`） | `test_05`、`test_06` | `the Live Monitor does not show GET /risk/latest: ["bannerText: 'RiskScore: 10.5 / 100 | …' != 'RiskScore: 10.4 / 100 | …'", "gaugeLabel: 'RiskScore: 10.5 / 100' != 'RiskScore: 10.4 / 100'"]`；Inspector：`assert '13.8 / 100' == '13.7 / 100'` |
| E2E-M4 | Retry 改成 `start(true)`（`ai/src/liveLoop.ts`） | e2 传输故障 | `Retry created a new session instead of resuming this one`（`assert 2 == 1`，`POST /api/sessions` 2 次）。第一版的等待只会超时 60 s（95 s 才红），我把等待改成看到第二个会话就立刻失败，现在约 35 s 内带明确文字变红 |
| E2E-M5 | Retry 的序号从 1 重新开始（`liveLoop.ts`：`pending.deliveries = 0`） | e2 传输故障 | `a manual retry continues the delivery count (1, 2, 3 automatic; 4 manual)`，`assert '1' == '4'` |
| E2E-M6 | 摄像头 `ended` 与主动停止显示相同文字（`utils/runtimeNotices.ts`：状态行与提示两处） | e2 摄像头 | `Camera: error · stopped by you at …` 不匹配 `Camera: error · disconnected at .+` |
| E2E-M7 | 遥测采集时间改回发送时刻（`data/preparedSessionInput.ts`：`acquiredAtMs: nowMs`） | **12 个全部**；明确的是 `test_01` | `while waiting for 10 windows…: the app stopped monitoring: Monitoring stopped: The same observation identity was sent again with different content … Category: observation_conflict (HTTP 409) … Deliveries: 1 of 3`。同一 seq 带了不同时间，服务端第二个请求就判 409，循环停止 |
| E2E-M8 | flag 不写进导出（`routers/export.py`：JSON 与 CSV 两处写死 `flagged: False`） | `test_07` | `2 differences: ['window 3 export JSON: flagged: True != False', "window 3: csv flagged: cell 'false' for value True"]` |

M7 跑 77 s：除 `test_01` 立即报告外，E2 的几个等待要到超时才红。M2 / M3 的第一行断言各只给出一个差异，但 `test_04` / `test_05` / `test_06` / `test_07` 的其余断言都会独立变红，没有哪个变异靠一个脆弱的偶然断言才被发现。

### 6.4 E3 实测数据（3 次运行；Chromium 148.0.7778.96，默认假摄像头；原始 JSON 在证据目录）

| 项 | run 1 | run 2 | run 3 |
|---|---|---|---|
| `requestVideoFrameCallback` 支持 / 产品注册次数 | 是 / 122 | 是 / 165 | 是 / 182 |
| 回调次数（采集 `<video>` 挂在 DOM 上） | 121（全部挂在文档里） | 164（同） | 181（同） |
| 回调跨度 / 速率 | 6.0 s / 20.0 Hz | 8.16 s / 19.98 Hz | 9.05 s / 19.89 Hz |
| `captureTime` 存在 / 缺失 | 121 / 0 | 164 / 0 | 181 / 0 |
| 请求里 `captured_at_source` | `capture_time` × 60 | `capture_time` × 60 | `capture_time` × 61 |
| 响应里 `vision_obs` | `new` × 60 | `new` × 60 | `new` × 61 |
| 回调时刻 − `captureTime`（ms，中位 / p95 / 最大） | 4.9 / 6.4 / 28.9 | 10.5 / 11.4 / 15.9 | 14.9 / 21.2 / 28.0 |
| **每次回调里截帧**（含 `drawImage` + `toDataURL`，ms，中位 / p95 / 最大） | 2.0 / 3.2 / 5.2 | 2.2 / 3.2 / 4.9 | 3.4 / 5.2 / 18.4 |
| `drawImage`（ms，中位 / p95 / 最大） | 0.5 / 1.2 / 1.6 | 0.6 / 1.1 / 2.4 | 0.9 / 1.5 / 6.9 |
| `toDataURL`（ms，中位 / p95 / 最大） | 1.5 / 2.1 / 2.9 | 1.6 / 2.1 / 3.3 | 2.4 / 3.6 / 9.9 |
| `image_base64` 长度（字符，中位 / 最大） | 12745 / 15103 | 13023 / 15591 | 12871 / 15599 |
| 请求到达 tap 时画面的年龄（ms，中位 / p95 / 最大） | 31.9 / 53.2 / 62.0 | 42.6 / 60.4 / 63.1 | 37.2 / 62.2 / 64.9 |
| 循环自带缓冲 `capture → send`（ms，中位 / 最大） | 0 / 1 | 0 / 1 | 0 / 1 |
| 循环缓冲 `network`（含服务端，ms，中位 / p95 / 最大） | 28 / 39 / 53 | 27 / 42 / 118 | 48 / 76 / 282 |
| 循环缓冲 `render`（ms，中位 / p95 / 最大） | 4 / 7 / 17 | 5 / 7 / 20 | 8 / 12 / 31 |

run 3 的各项耗时偏高，是机器当时更忙的结果（采集在同一台机器上与浏览器、uvicorn、模型并行）；这些数字都是「记录」，不是门槛，也不是 PERF-01 的结论。

## 7. 遗留问题

1. **provenance 只有两个模型 SHA256**（见第 2 节第 1 条）。如果控制者希望 provenance 也记录 `.pt` 的哈希，那是后端改动，不在本部分。
2. **E1 的相机是 5 fps，不是默认 20 fps。** 原因与数据见第 2 节第 2 条。副作用：E1 看到的是「循环快于相机」这一种工况；「相机快于循环」（默认假摄像头，所有窗口 `vision_obs = new`）由 E3 的三次运行记录，E1 不覆盖。若控制者更想让 E1 用默认相机，视觉 `repeat` 的断言就只能改成「若出现则……」，那会让 R10 的视觉 repeat 在线上无人验证，我没有这么做。
3. **E3 与 R10-B 报告的对照（brief 要求如实写出）。**
   - R10-B：Chromium 152（Browser 窗格），`canvas.captureStream(30)` 合成流；挂载 45 次回调 / 1.5 s，`captured_at_source: callback`（合成流**没有** `captureTime`）。
   - 本次：Chromium 148（Playwright），Chromium 假摄像头设备；挂载的采集 `<video>` 回调约 20 Hz（= 假设备的 20 fps），**`captureTime` 每次都存在**，所以 `captured_at_source` 是 `capture_time` 而不是 `callback`。这是**与 R10-B 不一致的一点**：`capture_time` 路径在 R10-B 里只有单测覆盖，这次第一次在真实浏览器里跑通。
   - **一致的一点**：挂在 DOM 上的采集 `<video>` 确实触发回调（181 / 181 个回调都在文档里）。
   - **未验证**：R10-B 的「分离的 `<video>` 1.5 s 内 0 次回调」这一条我没有重做（brief 只要求记录挂载情形），所以本部分对它既没有证实也没有推翻。
   - **未覆盖**：真实摄像头。Chromium 假设备不是物理相机：`captureTime` 是否由真实摄像头提供、真实相机的帧率与 `presentedFrames` 的行为，仍是未知数；PERF-01 若要引用，须注明「假设备」。
   - 截帧成本：每次回调里 `drawImage + toDataURL` 的总耗时中位 2–3.4 ms，约占 20 Hz 回调间隔 50 ms 的 4–7 %；画面是简单合成图案，JPEG 只有约 10 KB（base64 约 13 K 字符），真实人脸画面的编码耗时与体积会更大。
4. **耗时与依赖。** 全量 pytest 多约 32–38 s；需要 node / npm / Playwright Chromium / 模型文件。缺模型是显式跳过（`DRA_REQUIRE_MODELS=1` 时失败）；缺 npm / 浏览器是失败。没有为 CI 之外的环境做任何降级。
5. **断言里有两处时间容差。** 遥测相邻序号的墙钟间隔 [1.8, 2.3] s（实测 2.03 s，裕量约 ±10 %）与窗口全部 `fresh`（`age < 3 s`；设计上最坏约 2 s + 请求延迟）。修好测试自身的一处等待（见 M4 行）之后，完整 e2e 在真实工作树上单独运行 9 次（含满负荷 1 次）、随全量 pytest 运行 2 次，无一次失败；但在极慢的机器上这两条断言可能先于功能变红。我没有放宽它们：放宽会削弱「每 2 s 加 1」与「证据没有过期」这两条断言。
6. **界面读取依赖 CSS 类名。** `LATEST_PANEL_JS` 与 `test_06` 的读取用了 `.session-strip`、`section.alert-banner`、`.risk-gauge`、`.modality-card`、`.risk-badges`、`.window-list`、`.stat-list`、`.bar-row`、`.summary-metric-grid`、`table tbody tr`；界面重构改这些类名时要同步改 `e2e_support.py`。选 DOM 类名而不是加 `data-testid` 是因为 brief 禁止改产品代码。
7. **观察（没有设断言，也不是缺陷）**：
   - E2 传输故障测试里，Retry 重发的第一个窗口被服务端存为 **UNAVAILABLE**：两个分支都过期（`vision_age_s` 6.26、`telemetry_age_s` 6.254，`modality_freshness` 两个都是 `missing`，`assessment_available = false`）。这是 `liveLoop.ts` 头部注释写明的 T5 后果（裁定 A），不是新问题；我只是在系统层面第一次看到它。
   - 紧接着的下一个窗口 `telemetry_seq` 是 4（三次失败期间游标走到第 3 步，成功投递后 `resume` 取 `startSeq + step + 1`），符合 R10 的「每次恢复开新段」设计。
   - `AlertSeverity` 在 `RiskLevel = Low` 时仍可为 `CAUTION`（窗口里有过 Medium，恢复到 `NORMAL` 需要 Low 持续 ≥ 10 s），是 FSM 的设计行为。
8. **工作树里被写入的位置。** e2e 构建会重写工作树的 `dist/` 与 `tsconfig.tsbuildinfo`（均被 git 忽略）；`vite build` 经隔离副本里指向工作树 `node_modules` 的符号链接，可能写 `node_modules/.vite-temp`（工作树本地目录，`phase2-context.md` 第 17 行明确允许这种链接）。全程没有链接到主仓库的 `node_modules`；跑完后我检查过主仓库的 `.venv` 在过去 2 小时内没有任何文件被修改。
9. **没有发现产品缺陷。** 没有出现「先写红测试再停下」的情形。

## 8. 证据路径

- 测试：`backend/tests/test_live_e2e.py`、`backend/tests/e2e_support.py`、`backend/tests/e2e_server_main.py`、`backend/tests/conftest.py`
- `docs/evidence/2026-10-19/task-10-part2a/e2e-pytest.log` —— `test_live_e2e.py -v -s --durations=0`，12 passed in 38.15 s，含 `E3-MEASUREMENT` 行
- `docs/evidence/2026-10-19/task-10-part2a/rvfc-measurement-run{1,2,3}.json` —— E3 三次运行的原始测量
- `docs/evidence/2026-10-19/task-10-part2a/mutations.txt` —— 8 条变异 + 基线：补丁、变红的测试、第一条断言原文
- `docs/evidence/2026-10-19/task-10-part2a/gate-pytest.txt`（934 passed, 1 warning in 60.81s）、`gate-vitest.txt`（29 files / 870 tests）、`gate-tsc.txt`（EXIT 0）、`gate-eslint.txt`（EXIT 0）
- 冻结基线字面量的来源：`docs/evidence/2026-10-19/w3-gate/freeze_manifest.txt`
- R10-B rVFC 报告（对照）：`docs/fyp2/implementation/r10b-frontend.md` 第 4 节「隐藏挂载采集 `<video>`」与第 6 节

## 9. 下一项依赖

- **2b（`ST-BRANCH-*` 与 W4 证据归档）**：可以直接复用 `e2e_support.py`（`Chrome` / `ApiTap` / `Parties` 式的读取、`e2e_server` / `e2e_dist` fixture、`SLOW_FAKE_CAMERA_ARGS`）。单分支系统测试需要「只有摄像头」或「只有遥测」的会话，可以在 `ApiTap` 里改写请求体（去掉 `image_base64` 或遥测字段）而不碰产品代码——E2 的摄像头测试已经证明 `image_base64 = null` 的请求在线上被正确处理。G-W4-A 归档可以引用本目录的证据与 `ST-LIVE-E2E-01` 的 8 个测试。
- **PERF-01**：E3 的回调速率、截帧耗时、`capture → send / network / render` 分布可作为输入，但都是 Chromium 148 假设备上的数据；真实摄像头的 `captureTime` 与帧率需要另一次实测。
- **控制者待定**：第 7 节第 1 条（是否要在 provenance 里记录第三个模型哈希）与第 2 条（E1 的相机速度）。
- 阶段 5（裁定 A）仍未实施，本项没有碰；`liveLoop.ts` 头部关于 T5 的注释与第 7 节第 7 条的观察是一致的，裁定 A 落地时 E2 传输故障测试的观察部分不需要改动。
