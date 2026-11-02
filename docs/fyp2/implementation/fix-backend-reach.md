# FIX-BACKEND-REACH 实现报告 —— 「后端没启动」不再被误报为「模型或存储错误」；真实重启后端的端到端测试

## 1. 任务编号与名称

- **FIX-BACKEND-REACH**：后端响应标识 `X-DRA-Backend`；无标识的错误应答归为 `transport`（「The backend cannot be reached」）；停止面板按阶段给标题、只在服务器真给了 `detail` 时才写 "Server message"；两条新的端到端测试（开发代理形态的后端不可达、真实终止并重启 uvicorn）。
- 工作树 `/Users/liu/Desktop/FYP2-Live-System`，分支 `fyp2/live-system`，基线 HEAD `e354af7`（开工前核实：分支与 HEAD 吻合）。
- 基线门禁（brief）：pytest 952 / vitest 870 / tsc 0 / eslint 0。
- 用户现象：只运行了 `npm run dev`（5173），8000 上没有后端；点 Start Monitoring 后停止面板写「The server failed while processing the frame / Category: model_runtime (HTTP 500) / Failed during setup / Server message: API request failed (500)」。
- 根因链（brief 已查明，本项未改变其结论）：Vite 的 `/api` 代理连不上后端时**自己**回 `HTTP 500`、`Content-Type: text/plain`、空正文 → `client.ts` 变成 `ApiError("API request failed (500)", 500)` → `classifyHttp` 把任何 500 归为 `model_runtime`。

## 2. 实现状态

**DONE。** 四项门禁加 build 全部 0 失败、0 skipped；brief 的六条变异（R-M1 至 R-M6）全部在隔离副本里变红在预期的测试上，另外为每一条新增测试补做了变异（共 23 项，其中 R-M1b、R-M2、R-M3a、R-M4、R-M5b 同时在 vitest 或 pytest 与 e2e 上各跑一遍，见 6.3）。

| brief 条目 | 状态 | 守护 |
|---|---|---|
| A 后端：所有响应带 `X-DRA-Backend: 1`（含异常处理器） | 完成 | `test_backend_marker.py` 11 条；R-M1 等 5 次变异变红 |
| B 前端：无标识的非 2xx → `transport`；有标识的分类一行不变；CORS `expose_headers` | 完成 | `client.test.ts` +16、`retryPolicy.test.ts` +17；R-M2、R-M3a/b 变红 |
| C 停止面板：setup 标题、Server message 的显示条件 | 完成 | `runtimeNotices.test.ts` +7、`retryPolicy.test.ts`；R-M4、R-M5a/b/c 变红 |
| D1 开发代理形态：后端不可达，恢复后 Retry | 完成 | `test_e2_a_dev_proxy_answer_without_the_backend_is_reported_as_backend_unreachable` |
| D2 真实重启后端：同库同端口，Retry 续同一会话 | 完成 | `test_e2_a_real_backend_restart_on_the_same_database_and_port_is_resumed_by_retry`；R-M6a/b 变红 |
| `live_e2e.md` 对应行与「仍需人工」 | 完成 | — |

需要先知道的四点：

1. **用户 8000 端口上现在跑着的后端是旧代码，不发这个标识。** 新前端连旧后端时，旧后端的**每一个错误应答**（404、409、422、503、500）都会被读成「后端无法连接」，因为它们都没有标识；成功应答（2xx）不受影响。要看到正确的分类，必须重启那个后端（或它是 `--reload` 且从本工作树启动）。见第 7 节第 1 条。
2. **没有改 `ai/src/liveLoop.ts`**（不在 brief 允许的文件里）。`LiveFault` 只带一个 `message` 字符串，无法区分「服务器的话」和「客户端的兜底文字」，所以 "Server message" 的判定用「有 HTTP 状态 + 不是客户端兜底句型」两条（4.3）。更干净的做法是给 `LiveFault` 加一个字段，需要控制者决定（第 7 节第 2 条）。
3. **「不出现 model / storage 字样」我落成了具体短语**（`Server message|model or storage|model_runtime|storage|processing the frame`），没有禁裸词 `model`：setup 阶段的 Retry 说明本来就写「Retry repeats the setup: the model check, then the session.」，那是准确的，也被既有测试钉住。
4. **产品代码的改动只有标识本身与分类/文案**。融合、FSM、EMA、R10、模型文件、`docs/fyp2/review/`、计划文件、开发库均未碰；没有对 8000 端口做任何操作（测探针用的 Vite 代理目标是一个随机的、已关闭的端口）。

## 3. 创建 / 修改的文件

| 文件 | 改动 |
|---|---|
| `backend/app/routers/faults.py` | 新增常量 `BACKEND_HEADER = "X-DRA-Backend"`、`BACKEND_HEADER_VALUE = "1"`；`on_unhandled_exception` 返回的纯文本 500 显式带这个头 |
| `backend/app/main.py` | 新增纯 ASGI 中间件 `BackendMarkerMiddleware`（最外层的用户中间件，在 CORS 之后添加）；`CORSMiddleware` 增加 `expose_headers=[faults.BACKEND_HEADER]` |
| `frontend/src/api/client.ts` | 非 2xx 且无标识 → 抛 `NotFromBackendError`（`ApiError` 的子类）；导出 `isNoDetailMessage`（客户端兜底句型的判定） |
| `frontend/src/api/retryPolicy.ts` | `classifyFailure` 先判 `NotFromBackendError` → `transport`；`FAULT_TEXT` 增加可选 `titleInSetup`（仅 `model_runtime`）；新增 `faultTitle`、`faultDetail` |
| `frontend/src/components/RuntimeNotices.tsx` | 标题改用 `faultTitle`；消息行改用 `faultDetail`（"Server message" 或 "Details" 或不显示） |
| `backend/tests/test_backend_marker.py`（新） | 11 条，不用浏览器 |
| `backend/tests/test_live_backend_reach.py`（新） | 4 条 e2e（带 `e2e` 标记与 `requires_models`） |
| `backend/tests/e2e_support.py` | `start_server(workdir, *, port=None, log_name="uvicorn.log")`；`ApiTap` 在 `route.fetch` 失败（服务器不在）时向页面回「连接被拒」并记 `unreachable` |
| `frontend/src/api/client.test.ts` | +16 条 |
| `frontend/src/api/retryPolicy.test.ts` | +17 条 |
| `frontend/src/components/runtimeNotices.test.ts` | +7 条 |
| `prototype-tests/live_e2e.md` | 第 8 行改为已自动化，新增 8b 行与两条后端行，「仍需人工」第 3 条改写，运行说明与耗时补上新文件 |
| `docs/fyp2/implementation/fix-backend-reach.md` | 本报告 |

没有改动：`vite.config.ts`、`ai/`、`ml/`、`docs/fyp2/review/`、计划文件、任何数据库。**既有测试一行未改**（870 条 vitest、952 条 pytest 的断言原样通过）。

## 4. 实现摘要

### 4.1 后端：每个响应带标识（A）

- **中间件**是纯 ASGI 类，不是 `BaseHTTPMiddleware`（后者会缓冲/改写流式响应，且对静态文件不必要）。它包住 `send`，在 `http.response.start` 上 `MutableHeaders(scope=message)["X-DRA-Backend"] = "1"`。
- **顺序**：在 CORS 之后添加，所以是最外层的用户中间件：CORS 自己应答的预检也被标上；挂在 `/` 的静态 `dist/` 页面、`StaticFiles` 的 404 也被标上。R-M1d（把中间件放到 CORS 里面）使预检测试变红，证明顺序被测试钉住。
- **异常处理器**：Starlette 的 `ServerErrorMiddleware` 在所有用户中间件**之外**，它发出的响应（`on_unhandled_exception` 的纯文本 500）不经过上面的中间件，所以在处理器里显式加头。常量放在 `routers/faults.py`（brief 允许的文件），`main.py` 从那里取，避免循环导入。
- **CORS `expose_headers`**：同源（Vite 代理、或 uvicorn 同时提供页面与 API）不需要；跨源（设了 `VITE_API_BASE_URL`）时页面只能读 CORS 白名单里的响应头，不暴露的话前端在每个应答上都读不到标识，会把后端自己的所有错误当成代理的（与本次事故相反方向的同类错误）。`test_a_cors_preflight_is_marked_and_the_header_is_exposed_to_pages` 钉住 `Access-Control-Expose-Headers: X-DRA-Backend`。

### 4.2 前端：没有标识的错误应答不是后端说的（B）

- `request()` 在 `!response.ok` 时先看 `response.headers.has("X-DRA-Backend")`：没有就抛 `NotFromBackendError(status)`，**不读正文**。消息写明情形：`the API proxy or a gateway answered HTTP 500 and the backend did not; is the backend running?`（比 brief 的例句多了 "or a gateway"，因为无标识的应答不一定来自 Vite 代理）。
- `classifyFailure` 先判 `NotFromBackendError`，返回 `{category: "transport", retryable: true, counted: true}`，**不带 status**，计数规则与 D02 的 transport 相同。D02 的 `classifyHttp` 一行未改，只是它现在只处理带标识的应答（注释已更新）。
- **为什么用子类而不是给 `ApiError` 加参数**：既有测试和 `liveLoop.test.ts` 大量使用 `new ApiError(detail, status)` 表示「后端的应答」；子类让这些构造点的语义保持原样，一个都不用改。在生产代码里 `ApiError` 只在 `client.ts` 构造。
- 不带标识的 2xx 照常成功（只有非 2xx 受此规则约束）。

### 4.3 停止面板（C）

- **标题**：`faultTitle(fault)`：setup 阶段且该类别有 `titleInSetup` 时用它。只有 `model_runtime` 有：「The server failed while starting the session」（与已有的 `adviceInSetup` 「…while starting the session」一致）。delivery 阶段仍是「…while processing the frame」。`storage` 的标题「could not store the result」在 setup 阶段也不贴切，但现在只有**带标识**的 502/504 等才会走到它，而后端自己从不发这些，所以没有动（第 7 节第 4 条）。
- **消息行**：`faultDetail(fault)`：
  - 没有 HTTP 状态（拒绝连接、超时、或无标识的代理应答）：服务器没说过话，标 **"Details"**，内容是浏览器/客户端自己的文字（例如 `Failed to fetch`，或上面那句代理说明）；
  - 有 HTTP 状态但文字是客户端兜底句型 `API request failed (NNN)`（正文没有 `detail`）：**不显示这一行**，类别行已经写了状态；
  - 其余（有状态且是服务器给的 `detail`）：**"Server message"**。
- 兜底句型由 `client.ts` 导出的 `isNoDetailMessage` 判定，放在构造该句子的同一个文件里，并有测试钉住（正则锚定首尾，`API request failed (500) while saving` 不算）。

### 4.4 测试（D）

**后端 `test_backend_marker.py`（11 条）**：200（含 201、`/api/models`）、404（三种：不存在的会话、不存在的路由、对不存在的会话 infer）、409、两种 422（schema 校验、无效帧）、503 `models_unavailable`（含 `/api/models`）、500 `model_runtime`（JSON）、500 未处理异常（纯文本，`windows._infer` 返回非法对象触发 `ResponseValidationError`）、任意路由上的未处理异常（临时插入一个会抛异常的路由）、CORS 预检与 `expose_headers`、静态页面与静态 404（在 tmp 目录上挂一个与 `main.py` 同样的 `StaticFiles`）、头只出现一次。期望值（头名 `x-dra-backend`、值 `"1"`）都是测试里的字面量。

**vitest（+40）**：
- `client.test.ts` +16：经真实 `fetch` 桩 + `classifyFailure`：无标识的 500（`text/plain`、空正文）、无标识的 404/500/502/503/504、正文像后端 JSON 但无标识 → 全是 `transport`；有标识的 JSON 500、有标识的纯文本 500 → `model_runtime`（后者的消息就是兜底句型）；有标识的 404/409/422/503 → 各自的 D02 类别；2xx 有无标识都成功；`isNoDetailMessage` 的边界；子类仍是 `ApiError`。
- `retryPolicy.test.ts` +17：无标识的 404/500/502/503/504 → `transport`；同一个 500 带标识（普通 `ApiError`）仍是 `model_runtime`；无标识的 503 可重试、有标识的 503 仍停；`faultTitle` 的 setup/delivery/无 setup 标题的类别；`faultDetail` 的四种情形。
- `runtimeNotices.test.ts` +7：静态渲染：用户的原始面板（setup + `model_runtime` + 兜底文字）→ 「starting the session」标题且无 Server message；无标识应答 → 「The backend cannot be reached」+ `Details:` 行、无 model/storage/Server message 字样、类别行无 `(HTTP 5xx)`；delivery 阶段保留「processing the frame」；服务器给的 `detail` 显示为 Server message；浏览器端失败显示为 Details；无 detail 的 HTTP 错误不显示消息行；等待重试的状态行用同一标题规则。

**端到端 `test_live_backend_reach.py`（4 条）**：
1. `test_the_deployed_backend_marks_its_page_and_every_kind_of_answer`：真 uvicorn 提供的 `dist/` 页面、200、404、422 都带标识（经 httpx）。
2. `test_e2_a_dev_proxy_answer_...`（**开发代理形态**）：在 Playwright 里给 `/api/models` 注册一个 route，返回 `500 / Content-Type: text/plain / Vary: Origin / 空正文 / 无 X-DRA-Backend`（形状来自 4.5 的实测）；先用页面里的 `fetch` 验证页面看到的正是 `{status: 500, type: "text/plain", marker: null, body: ""}`。点 Start Monitoring：面板写「Monitoring stopped: The backend cannot be reached」、`Category: transport`、`Failed during setup, before any request was sent`、`Details: the API proxy or a gateway answered HTTP 500 and the backend did not; is the backend running?`；不含 `Server message|model or storage|model_runtime|storage|processing the frame`，类别行无 `(HTTP 500)`；没有会话、没有 infer、库里会话集合不变。放行路由后点 Retry：恰好新建一个会话，窗口 1、2、3 到达，面板消失，`Monitoring active`，`fault_events` 为 0。
3. `test_the_backends_own_500_is_still_a_server_error_...`（反方向）：route 返回**带标识**的 JSON 500 → 面板仍写「The server failed while starting the session」、`Category: model_runtime (HTTP 500)`、`Server message: Vision model failed during inference`，不写「cannot be reached」。
4. `test_e2_a_real_backend_restart_...`（**真实重启**）：用 `start_server` 起一个**自己的** uvicorn（自己的 tmp 目录、库、端口，不用共享的 `e2e_server`）。收到 4 个窗口后 `server.stop()`（SIGTERM，进程确实退出）。循环对同一个冻结请求投递 3 次（`X-Attempt-Index` 1、2、3，字节相同，结果 `unreachable`），面板写「The backend cannot be reached」、`Request id`、`Deliveries: 3 of 3`、「Retry re-sends this same request to the same session.」、无 model/storage 字样；此时库里是连续的 1..N，没有冻结请求。然后在**同一个 workdir 与端口**上再起 uvicorn：会话仍在、`total_windows == N`。点 Retry：没有新会话（`POST /api/sessions` 仍 1 次，库里会话集合仍是 `{sid}`）；冻结请求第 4 次投递 `X-Attempt-Index: 4`，字节相同，201，`window_id == N+1`；该 `request_id` 在库里恰 1 行；`window_id` 为 1..M 连续、`request_id` 无重复；重启前的 N 行逐字段不变；循环恢复（之后至少 3 个窗口，各自第 1 次投递）；面板消失；`fault_events` 为 0。

`e2e_support.py` 的改动不改变既有测试的行为：`start_server(workdir)` 的默认调用与以前相同（空闲端口、新的 `e2e.db`、`uvicorn.log`）；`ApiTap` 新增的分支只在 `route.fetch` 抛异常时运行，既有测试的服务器始终在。

### 4.5 开发代理形态的实测

为了不凭记忆写「与 vite 完全相同」，我用一个临时 Vite（配置文件在 scratchpad，`proxy` 目标是一个随机的、已关闭的端口；**没有碰 8000**）实测了代理的应答，随后已停止该进程：

```
$ curl -si http://127.0.0.1:62055/api/models | od -c      # 原始字节（节选）
HTTP/1.1 500 Internal Server Error
Vary: Origin
Content-Type: text/plain
Date: ...
Connection: keep-alive
Keep-Alive: timeout=5
Transfer-Encoding: chunked
(空正文)
$ curl -s -o /dev/null -w "%{http_code} %{content_type} %{size_download}\n" ...
500 text/plain 0
```

与 brief 的描述一致；e2e 的 route 就按这个形状（500、`text/plain`、`Vary: Origin`、空正文、无标识）。

## 5. 执行的测试（精确命令）

```
cd /Users/liu/Desktop/FYP2-Live-System
export PYTHONDONTWRITEBYTECODE=1
(cd backend && TMPDIR=$(mktemp -d) PYTHONPATH=. ../.venv/bin/python -m pytest tests -q -p no:cacheprovider)
./node_modules/.bin/vitest run --no-cache
./node_modules/.bin/tsc --noEmit
./node_modules/.bin/eslint .
npm run build
```

新测试单独运行：

```
(cd backend && TMPDIR=$(mktemp -d) PYTHONPATH=. ../.venv/bin/python -m pytest tests/test_backend_marker.py tests/test_live_backend_reach.py -q -p no:cacheprovider)
./node_modules/.bin/vitest run --no-cache frontend/src/api/client.test.ts frontend/src/api/retryPolicy.test.ts frontend/src/components/runtimeNotices.test.ts
```

变异：隔离副本 `D=$(mktemp -d)`，`git archive HEAD | tar -x -C "$D"`，再把工作树里本项的 12 个已修改 / 新增文件拷入（`cmp` 逐个确认相同），`.venv`、`node_modules` 以符号链接接入真实工作树的，三个模型文件以只读符号链接接入 `$D/ml/outputs/`。每次变异：对一个源文件做**恰好一次**的精确字符串替换（匹配次数不是 1 则中止）→ 在副本里跑指定测试（后端：`cd $D/backend && PYTHONPATH=. ../.venv/bin/python -m pytest <文件> -q -p no:cacheprovider`；前端：`cd $D && ./node_modules/.bin/vitest run --no-cache <目录>`；e2e 会先在副本里 `npm run build`）→ 还原为真实工作树里的文件内容并断言相同。全部变异之后，副本里 373 个源文件的 sha1 清单与变异前的清单逐行相同。**没有在真实工作树里做任何变异。**

## 6. PASS / FAIL / SKIP 计数

### 6.1 门禁（最终代码）

| 门禁 | 结果 | 与基线的差 |
|---|---|---|
| pytest（完整，含 e2e） | **967 passed**，0 failed，0 skipped，1 warning（`starlette.testclient` 的 httpx 弃用提示，既有），149.35 s | 952 → 967：**+15** = `test_backend_marker.py` 11 + `test_live_backend_reach.py` 4。既有测试一条未增未减 |
| vitest | **910 passed**（29 个文件） | 870 → 910：**+40** = `client.test.ts` 16 + `retryPolicy.test.ts` 17 + `runtimeNotices.test.ts` 7 |
| tsc --noEmit | 0 错误 | — |
| eslint . | 0 错误 | — |
| npm run build | 成功（只有既有的 chunk 超过 500 kB 提示） | — |

pytest 日志里没有「MODEL-DEPENDENT TEST(S) NOT RUN」横幅，没有 skip。完整 pytest 从 134 s（2b 报告）到 149 s：多出的约 15 s 来自新的 4 条 e2e（单独运行约 21 s）。

### 6.2 新增测试（全部 PASS）

后端 11 + e2e 4 + vitest 40 = 55 条，逐条见 4.4。

### 6.3 变异（均在隔离副本；每一项都有明确变红的测试）

brief 的六条：

| # | 变异 | 观察到的结果 |
|---|---|---|
| R-M1 | `routers/faults.py`：未处理异常的纯文本 500 不带标识 | `test_backend_marker.py` 红 2 条：`test_500_unhandled_exception_plain_text_is_marked`、`test_an_unhandled_exception_on_any_route_is_marked_too`（其余 9 条绿：中间件覆盖了它们） |
| R-M2 | `client.ts`：删掉无标识就抛 `NotFromBackendError` 的判断（回到「任何 500 都是 model_runtime」） | vitest 红 7 条（`client.test.ts`：开发代理的 500、无标识的 404/500/502/503/504、正文像后端 JSON 的无标识 500）；e2e `test_e2_a_dev_proxy_...` 红，面板正是用户那张：「Monitoring stopped: The server failed while starting the session … A model or storage error on the server (HTTP 500)」 |
| R-M3a | `retryPolicy.ts`：`classifyHttp` 把带标识的 500 归为 `transport`（反方向） | vitest 红 8 条（`liveLoop.test.ts` 4、`client.test.ts` 2、`retryPolicy.test.ts` 2，含既有的「a 500 is retryable whatever its body says」）；e2e `test_the_backends_own_500_...` 红 |
| R-M3b | `client.ts`：标识判断取反（带标识的被当成无标识） | vitest 红 13 条（`client.test.ts`：无标识的 7 + 有标识的 6） |
| R-M4 | `retryPolicy.ts`：删掉 `titleInSetup`（setup 标题仍写 processing the frame） | vitest 红 4 条（`retryPolicy.test.ts` 2、`runtimeNotices.test.ts` 2）；e2e `test_the_backends_own_500_...` 红（`…processing the frame`） |
| R-M5a | `faultDetail`：去掉兜底句型判断（兜底文字被标成 Server message） | vitest 红 3 条 |
| R-M5b | `faultDetail`：无状态的文字也标 "Server message" | vitest 红 3 条；e2e 红 2 条（开发代理、真实重启：面板出现了 Server message） |
| R-M5c | `RuntimeNotices.tsx`：恢复旧代码 `<p>Server message: {fault.message}</p>` | vitest 红 4 条 |
| R-M6a | `ai/src/liveLoop.ts`：`retry()` 一律走 `start(true)`（重启后点 Retry 新建会话） | e2e `test_e2_a_real_backend_restart_...` 红：`Retry created a new session instead of resuming this one` |
| R-M6b | `ai/src/liveLoop.ts`：Retry 前把 `pending.deliveries` 清零（计数从 1 重来） | e2e 同一条红：`assert ['1', '2', '3', '1'] == ['1', '2', '3', '4']` |

为其余新增测试补做的变异：

| # | 变异 | 结果 |
|---|---|---|
| R-M1b | 去掉整个中间件 | `test_backend_marker.py` 红 9 条（只剩两条纯文本 500，因为处理器自己带头）；e2e `test_the_deployed_backend_...` 红 |
| R-M1c | 去掉 `expose_headers` | 红 1 条（CORS 那条） |
| R-M1d | 中间件放到 CORS 里面（`user_middleware.reverse()`） | 红 1 条（预检未标识） |
| R-M1e | 头被加两次（`append` ×2） | 红 9 条（含 `test_the_marker_is_added_once_not_per_layer`） |
| R-M7 | 标识检查前移到 `!response.ok` 之外（无标识的 2xx 也算错误） | vitest 红 8 条（含「a 2xx answer is a success whether or not it carries the marker」和 7 条既有的） |
| R-M8 | `isNoDetailMessage` 的正则去掉锚定 | 红 1 条 |
| R-M9 | `NotFromBackendError` 不再继承 `ApiError` | 红 1 条 |
| R-M10 | `classifyFailure` 删掉 `NotFromBackendError` 分支 | 红 14 条（`client.test.ts` 与 `retryPolicy.test.ts`） |
| R-M11 | 改 `NotFromBackendError` 的消息文字 | 红 2 条 |
| R-M12 | `faultTitle` 对无 setup 标题的类别返回 "Setup failed" | 红 2 条 |
| R-M13 | `faultDetail` 删掉空消息判断 | 红 1 条 |
| R-M14 | `faultTitle` 不看阶段（总是用 `titleInSetup`） | 红 3 条 |
| R-M15 | `RuntimeNotices.tsx` 永不渲染消息行 | 红 4 条 |

一次工具问题（已更正，不影响结论）：R-M7、R-M8、R-M9 的第一次运行因 zsh 不分词，把多个目录当成一个参数，实际没有跑 vitest（输出 `exit 0` 但没有测试行）；我发现后用字面参数重跑，上表是重跑的结果。R-M6a 的第一次写法（`if (true)`）让 `npm run build` 失败（e2e 以 ERROR 而不是 FAILED 结束），不算变红；改成类型正确的写法后重跑，上表是重跑的结果。

## 7. 遗留问题

1. **旧后端不发标识。** 开发机 8000 端口上正在运行的后端是这次改动之前启动的，不发 `X-DRA-Backend`。新前端连它：成功应答照常，但它的**所有错误应答**（包括它自己的 409/422/503/500）都会被读成「The backend cannot be reached」（可重试，最多 3 次投递）。重启后端即可。这是本设计的固有代价（标识是后端与前端的新约定），不是 bug，但用户一定会在重启前碰到。
2. **`LiveFault` 没有「消息来自服务器」的字段**（`ai/src/liveLoop.ts` 不在允许修改的文件里）。当前用「有 HTTP 状态 + 不是 `API request failed (NNN)` 句型」判定。后果：如果某个服务器的 `detail` 恰好逐字等于该句型，它会被隐藏（无害）。若要彻底，改法是在 `LiveFault` 加 `messageFromServer: boolean`，由 `client.ts` 的 `ApiError` 带出，需要控制者批准改 `ai/src/liveLoop.ts`。
3. **`docs/fyp2/implementation/task-08.md` 第 179 行与 `prototype-tests/README.md`（第 47 行、第 8 步）仍是旧说法**：前者记录的是当时「vite 代理在后端不可达时回 500，所以是 500」的观察（历史报告，不改）；后者仍把「真实重启后端」列为人工项。brief 只允许改 `live_e2e.md`，所以 README 没动，之后需要同步。
4. **`storage` 的标题在 setup 阶段仍写「could not store the result」。** 该类别现在只对**带标识**的 5xx（非 500、非 503）出现，后端自己从不发，所以实际不可达；没有为它加 `titleInSetup`。
5. **开发代理形态是用 route 重现的，不是真的 Vite 加真的停掉的后端**（brief 如此规定）。形状来自一次实测（4.5），但「Vite dev + 8000 上没有后端」这个具体组合没有自动化。若要自动化，可以让测试用临时配置起一个 Vite，代理目标指向已关闭的端口；这需要处理 Vite 的依赖预构建与 `fs.allow`，我没有做，因为超出 brief。`live_e2e.md` 的「仍需人工」第 3 条如实写了这一点。
6. **真实重启用的是 SIGTERM（优雅退出），不是 SIGKILL。** 进行中的请求会被答完，所以「冻结的请求」恰好是终止之后才发的那一个；SIGKILL 在请求已提交、应答丢失时的路径（Retry 的 reconcile 之后重投递得到回放）由既有的 `test_retry_contract.py` / `liveLoop.test.ts` 覆盖，不在这条 e2e 里。
7. **`ApiTap` 的行为有一处扩展**：`route.fetch` 抛异常时，以前异常会冒出处理器，现在向页面回「连接被拒」并记 `unreachable`。只在服务器不在时发生，既有测试不会触及；但如果某个既有测试因为别的原因让 `route.fetch` 失败，失败的样子会从处理器异常变成页面看到的传输故障。
8. **跨源部署下，未处理异常的 500 没有 CORS 头**（`ServerErrorMiddleware` 在 CORS 之外），页面读不到它，会表现为 `fetch` 拒绝，即 `transport`。这是 Starlette 的既有行为，与本项无关，只是顺带记下。
9. 工作树里未跟踪的 `backend/driver_risk.db-shm` 与 `-wal` 属于用户在 8000 上运行的后端，本项没有碰、也没有暂存。

## 8. 证据路径

- 门禁原始输出（本会话 scratchpad，未入库）：`/private/tmp/claude-501/-Users-liu-Desktop-FYP-In-Cabin-Driver-Assessment--1--claude-worktrees-exciting-keller-fdf913/43d73f6d-ed36-4f8a-b584-13c974ccd767/scratchpad/gates/{pytest,vitest,tsc,eslint,build}.log`。
- 变异隔离副本：`/var/folders/0k/dtzqmkm53vqgg530vd7h3fmr0000gn/T/tmp.ZDyc5v1IrU`；变异运行器 `…/scratchpad/mut.py`；变异前后的源文件清单 `…/scratchpad/manifest0.txt` 与 `manifest1.txt`（逐行相同）。
- 代理形态实测：4.5 的输出；临时 Vite 配置 `…/scratchpad/vite-probe.config.mjs`、日志 `vite-probe.log`。
- 代码：`backend/app/main.py`（`BackendMarkerMiddleware`、`expose_headers`）、`backend/app/routers/faults.py`（常量与处理器）、`frontend/src/api/client.ts`、`frontend/src/api/retryPolicy.ts`、`frontend/src/components/RuntimeNotices.tsx`。
- 测试：`backend/tests/test_backend_marker.py`、`backend/tests/test_live_backend_reach.py`、`backend/tests/e2e_support.py`、`frontend/src/api/client.test.ts`、`frontend/src/api/retryPolicy.test.ts`、`frontend/src/components/runtimeNotices.test.ts`；人工/自动对照表 `prototype-tests/live_e2e.md`。
- 既有归档 `docs/evidence/2026-10-20/live-e2e/` 没有重新生成（本项不是 G-W4-A 的归档）。

## 9. 下一项依赖

- 本项不阻塞任何后续项；没有新增依赖，也没有改变数据契约、数据库结构或模型文件。
- 需要用户做的一件事：**重启 8000 上的后端**（第 7 节第 1 条），之后在「只开 `npm run dev`、没有后端」时应看到「The backend cannot be reached」，启动后端后点 Retry 恢复。
- 建议控制者决定的两件事：是否批准给 `LiveFault` 加 `messageFromServer`（第 7 节第 2 条），以及是否把 `prototype-tests/README.md` 的第 8 步与第 47 行同步到 `live_e2e.md`（第 7 节第 3 条）。
