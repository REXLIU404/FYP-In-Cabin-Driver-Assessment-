# FIX-BACKEND-REACH 验收报告（中文）：「后端没启动」不再被误报为「模型或存储错误」；真实重启后端的端到端测试

## 1. 任务概要

- **来源**：用户 10-20 实测时遇到的问题。只启动了 `npm run dev`（vite，5173），没有启动后端（8000）。点 Start Monitoring 后，停止面板显示：
  - 「The server failed while processing the frame」；
  - 「A model or storage error on the server (HTTP 500)」；
  - 「Server message: API request failed (500)」。
- **根因**（控制者用 curl 复现）：
  1. vite 的 `/api` 代理连不上后端时，自己回一个 HTTP 500，`text/plain`，正文为空；
  2. 前端把**任何** 500 都归为 `model_runtime`；
  3. 另外两处文字也不对：setup 阶段根本没有处理任何帧，标题却写 frame；「Server message」那一行显示的是前端自己的兜底文字，不是服务器发来的。
- **实现了什么**：
  - **后端**：自己产生的每个响应都带 `X-DRA-Backend: 1`，包括未处理异常的纯文本 500、CORS 预检和静态页面。为了让跨源部署的页面读得到这个头，把它加进了 `expose_headers`。
  - **前端**：**不带**这个标识的非 2xx 响应，判定为不是本后端发出的，归为 `transport`，显示「The backend cannot be reached」，并说明是代理或网关代答的。带标识的响应，分类规则一行没改，D02 的分类表不变。
  - **停止面板**：setup 阶段有自己的标题。「Server message」只在服务器确实给出 detail 时显示。
  - **端到端测试**（`test_live_backend_reach.py`，4 条）：
    - 开发代理形态：用 route 返回与 vite 实测完全相同的应答（500、`text/plain`、空正文、无标识），断言面板说后端无法连接，恢复后点 Retry 能正常开始；
    - **真实重启后端**：用一个独立的 uvicorn，在会话中途把它停掉，3 次投递后停止；在同一个数据库、同一个端口上重启，然后点 Retry；
    - 本后端自己的 500 仍按服务器错误处理；
    - 部署形态下的页面带标识。
- **为什么必要**：误报会把排查方向引向模型，而真正的原因只是后端没开。另外，「真实重启后端」原来列为人工项，现在已经自动化。

## 2. 实现证据

- **Commit**：
  - `83219da`：本项主体；
  - 本报告所在提交：控制者补的文档。
- **两次派发**：第一次派发的实现者已经完成了实现、测试、23 项变异和报告，但在提交之前撞上了每周额度。草稿备份在 SDD 的 `fix-backend-reach-partial-run1/`。控制者在完全相同的树上复跑门禁，结果全绿，原样提交为 `83219da`。随后以「只做评审」的模式派发独立评审。
- **文件**：
  - 后端：`backend/app/main.py`（`BackendMarkerMiddleware`，纯 ASGI，放在最外层的用户中间件位置；`expose_headers`）、`backend/app/routers/faults.py`（未处理异常的 500 显式加标识）；
  - 前端：`frontend/src/api/client.ts`（`NotFromBackendError`）、`retryPolicy.ts`（setup 阶段的标题、`faultDetail`）、`components/RuntimeNotices.tsx`；
  - 测试：`test_backend_marker.py`（11 条）、`test_live_backend_reach.py`（4 条）、vitest 新增 40 条；
  - `e2e_support.py`：`start_server` 可以指定端口和数据库，向后兼容。
- 融合、FSM、EMA、R10、模型文件、`ai/`、`vite.config.ts` 都没有改动。

## 3. 测试结果

| 门禁 | 结果（控制者与评审各自在 `83219da` 上复跑） |
|---|---|
| build | 通过 |
| pytest | **967 passed / 0 skipped**（952 → 967：标识测试 11 条 + e2e 4 条） |
| vitest | **910 passed**（870 → 910：`client` 16 条 + `retryPolicy` 17 条 + `runtimeNotices` 7 条） |
| tsc / eslint | 0 / 0 |
| 模型哈希 | 三个都未变 |

**变异检验**：评审在隔离副本中复现了 brief 要求的 R-M1 到 R-M6，每一项都在预期的测试上变红。评审还另加了 8 项变异，也全部变红：

| # | 变异 | 结果 |
|---|---|---|
| R-M1 | 未处理异常的 500 不带标识 | 标识测试 2 条变红 |
| R-M2 | 前端忽略标识 | vitest 7 条变红；开发代理 e2e 变红，面板变回用户当时看到的样子 |
| R-M3 | 带标识的真 500 被当成 transport | vitest 8 条变红；e2e 变红 |
| R-M4 | setup 标题仍写 processing the frame | vitest 4 条变红；e2e 变红 |
| R-M5 | 兜底文字被标成 Server message | vitest 3 条变红；e2e 2 条变红 |
| R-M6 | 重启后 Retry 新建会话，或投递序号从 1 重新计 | 真实重启的 e2e 变红 |

**评审的独立探针**：评审在随机端口上起了真 uvicorn，前面放一个真 vite，全程没有碰 8000 端口，核实了两件事：
- 后端在线时，vite 代理会把标识原样透传给页面；
- 后端停掉之后，经代理得到的应答是 500、`text/plain`、空正文、无标识，与 e2e 测试里用 route 复现的形状完全一致。

**用户环境的验证**：控制者在 8000 端口用 `83219da` 的代码重新启动了后端。经 5173 的代理访问，`/api/models` 返回 200，并带有 `x-dra-backend: 1`。

## 4. 问题与风险

评审给出 6 条 Minor，都不阻塞本项。处理结果如下：

- **接受**：面板里仍有「the model check」这几个词。它说的是 Retry 会重做模型检查，内容准确，也被已有测试钉住，并没有把故障归因到模型。
- **接受，记为限制**：`storage` 类别在 setup 阶段的标题仍写「could not store the result」。按现在的规则，只有带标识、并且状态码不是 500 / 503 的 5xx 才会落到这个类别，而现有后端只会发 500 和 503，所以实际走不到这里。
- **需要注意**：前端如果连的是 `83219da` 之前启动的旧后端，旧后端不发标识，它自己的**所有**错误应答都会被显示成「后端无法连接」，连迟到帧的 409 也会。重启后端就能消除。用户 8000 端口上的后端已经是新代码，不受影响。
- **记录**：跨源部署时，未处理异常的 500 没有 CORS 头。这是 Starlette 的既有行为，早于本项；同源部署不受影响。
- **记录**：`e2e_support.py` 里 `except Exception` 捕获的范围太宽，测试框架自身的故障会被伪装成页面上的传输故障。目前没有造成错误结果。
- **记录**：有一条 vitest 用了 liveLoop 实际不会出现的状态（setup 阶段、未停止），测试价值偏低，但不影响正确性。
- **实现者留下的两项**：
  - `prototype-tests/README.md` 仍把「真实重启后端」列为人工项。控制者已改，说明第 8 步已由 `test_live_backend_reach.py` 自动化。
  - `LiveFault` 没有「消息来自服务器」的字段，目前按「有 HTTP 状态，且不是客户端兜底句型」来判断。如果某个服务器 detail 恰好与兜底句型逐字相同，它会被隐藏，这是无害的。要彻底解决需要改 `ai/src/liveLoop.ts`，留作以后的小项。
- **没有自动化的部分**：「真 vite 开发服务器 + 真浏览器 + 停掉的后端」这条完整的界面流程。HTTP 层由评审用真 vite 核实，界面层由 route 复现的 e2e 守护。

## 5. 验收结论

**PASS**

理由：
- A、B、C、D 四项全部落实；
- R-M1 到 R-M6 以及评审另加的 8 项变异全部变红；
- 评审用真 vite 独立核实了代理应答的形状，以及标识的透传；
- 控制者与评审各自复跑门禁，全部通过，0 skipped。

## 6. 下一任务就绪度

- 开发流程的便利性：用户提议，用一条命令同时启动后端和 vite（`npm run dev:all`），等用户确认后做。
- 视觉的数据集回放演示模式（用户 10-22 选择 A：为演示服务）正在设计讨论中，将在独立分支 / 工作副本里进行。
- 之后是 W5：会话生命周期、冷启动、导出完善、Task 10A 的 manifest 交接。
