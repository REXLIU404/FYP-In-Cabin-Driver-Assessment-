# Task 8 跟进实现报告 —— New Session 失败后的 Retry、500 类别断言、15 s 期限下界、投递计数显示

## 1. 任务编号与名称

- **TASK-8-FOLLOWUP**：Task 8 评审标出的 4 个阻塞 Minor（H1–H4）
- 工作树 `/Users/liu/Desktop/FYP2-Live-System`，分支 `fyp2/live-system`，基线 HEAD `e37a312`（开工前已核实分支与 HEAD，工作树干净）
- 基线（开工前在同一 HEAD 复现）：pytest 598 passed / vitest 515 passed（19 个文件）/ tsc 0 / eslint 0
- 范围外、零改动：后端、计划文件、模型文件、`docs/fyp2/review/`、`client.ts`、`useLiveSession.ts`、`useCameraPreview.ts`

## 2. 实现状态

**DONE_WITH_CONCERNS。** 四道门禁达标：pytest 598 passed / vitest 533 passed / `tsc` 0 / `eslint` 0。concerns 见第 7 节，最需要知情的三条：

1. H4 需要让循环**多携带一个字段** `LiveFault.manualRetries`（brief 没有逐字写出，但不加它无法区分自动与手动投递，见 4.4）。
2. H2 我**没有改文案**：现行 `model_runtime` 的标题与说明已是中性说法，只补了类别断言（见 4.2）。
3. React 绑定层（`FaultPanel` 的接线、Retry 按钮）仍没有 node 单测，按 brief 转入 Task 10；本跟进没有做浏览器冒烟。

| 项 | 状态 | 守护 |
|---|---|---|
| H1 New Session 建会话失败后 Retry 必须新建会话 | 完成 | `liveLoop.test.ts` 4 个新用例；变异 Y1a–f 全部变红 |
| H2 500 的类别字面量断言 | 完成（只补断言，文案未改） | `retryPolicy.test.ts` 加固既有用例；变异 Y2 变红 |
| H3 15 s 期限下界断言 | 完成 | `client.test.ts` 加固既有用例；变异 Y3 变红 |
| H4 投递计数显示：纯函数 + 接线 | 完成 | `retryPolicy.test.ts` 9 个新用例 + `liveLoop.test.ts` 5 个新用例；变异 Y4、H4a–j 全部变红 |

## 3. 创建 / 修改的文件

**新建（1）**：`docs/fyp2/implementation/task-08-followup.md`（本报告）

**修改（6）**

| 文件 | 说明 |
|---|---|
| `ai/src/liveLoop.ts` | H1：`stopInSetup` 接收 `restart`，`newSessionOnRetry = restart \|\| not_found`；`retry()` 的 setup 分支改为 `start(fault.newSessionOnRetry)`。H4：`LiveFault.manualRetries`、`PendingRequest.manualDeliveries`，`deliver()` 在手动投递时累加 |
| `ai/src/liveLoop.test.ts` | +9 个用例（H1 四个、H4 五个）；既有用例未改 |
| `frontend/src/api/retryPolicy.ts` | 新增纯函数 `deliveryCounts`、`deliveriesText` |
| `frontend/src/api/retryPolicy.test.ts` | H2：500 用例由 `toMatchObject` 改为 `toEqual`，含 `category: "model_runtime"`；H4：+9 个用例 |
| `frontend/src/api/client.test.ts` | H3：既有 15 s 用例加下界与「已 settle」断言（不增加用例数） |
| `frontend/src/App.tsx` | H4 接线：`Deliveries: {deliveriesText(fault)}`，删掉内联的 `Math.min` / `Math.max` 计算 |

没有任何既有测试被删除或弱化。

## 4. 实现摘要

### 4.1 H1：New Session 失败后 Retry 必须新建会话

复现（探针在改动前已让新用例变红）：sess-1 运行中，用户点 New Session（`start(true)`），`api.create` 抛错，进入 setup 停止态，但 `newSessionOnRetry` 为 `false`；随后 `retry()` 调 `start(false)`，此时 `activeSid` 仍是 sess-1，走 reconcile 分支，继续往 sess-1 写数据。

修法有两处，缺一不可：

1. `start()` 把自己的 `restart` 标志传给 `stopInSetup`，`newSessionOnRetry = restart || failure.category === "not_found"`。**任何**发生在 New Session 里的 setup 失败（`api.models` 的 503，也包括 `api.create`）都会记住这个意图。
2. `retry()` 的 setup / 新会话分支由 `start(false)` 改为 `start(fault.newSessionOnRetry)`。404 的既有行为不变（它同时把 `activeSid` 清空，`start(true)` 与 `start(false)` 等价）。

`activeSid` 在 New Session 失败时**保留**（只有 404 才清）：旧会话在服务端仍然有效，面板上显示的也还是它。失败之后用户若点的是 Start Monitoring 而不是 Retry，仍然恢复旧会话（有测试钉住，见下）。

测试（`liveLoop.test.ts`，四个）：

| 用例 | 断言 |
|---|---|
| `api.create` 失败后 Retry | 停止态 `phase:"setup"`、`newSessionOnRetry:true`、`sessionId` 仍是 `sess-1`；Retry 后 `create` 共 3 次、`api.session`（reconcile）**0 次**、`sessionId` 为 `sess-2`、故障清除、运行中、Retry 之后的 `infer` 的 sid 恰为 `["sess-2"]` |
| 失败发生在更早的模型检查（503） | 同上：`create` 在 Retry 后才第 2 次，不走 reconcile |
| 对照：普通 Start 恢复失败（502） | `newSessionOnRetry:false`；Retry 重新 reconcile（`api.session` 共 2 次）、`create` 仍是 1 次、sid 为 `sess-1`。守住「不是一律新建」 |
| 对照：New Session 失败后点普通 Start | 恢复旧会话（reconcile 1 次，`create` 不再增加，sid `sess-1`）。守住「`activeSid` 保留」这个取舍 |

### 4.2 H2：500 的类别字面量断言

`retryPolicy.test.ts` 的 500 用例原先对结果只用 `toMatchObject({status, retryable, counted})`。现在对 `http(500, …)` 用 `toEqual({category: "model_runtime", status: 500, retryable: true, counted: true})`，期望全是字面量。

**文案：没有改。** 我检查了 `FAULT_TEXT.model_runtime`：标题是 “The server failed while processing the frame”，说明是 “A model or storage error on the server (HTTP 500). …”，两处都没有把 500 说成「模型」专属。唯一显示 `model_runtime` 字样的地方是面板的 `Category: <code>model_runtime</code> (HTTP 500)` 一行，它是诊断用的原始类别码（类别字段按 brief 保持不变）。所以存储类 500 会在这一行显示 `model_runtime`，但上方的句子是中性的。若控制者认为这一行仍会误导，改法是只动 `App.tsx` 那一行的显示，不动类别。

### 4.3 H3：15 s 期限下界

`client.test.ts` 的「client's own 15 s deadline」用例：在 `advanceTimersByTimeAsync(14_999)` 之后断言 promise **仍未 settle**（用 `pending.then(…, …)` 设置 `settled` 标志），再推进 1 ms 后断言已 `settled`。原先的用例只在 15 000 ms 之后断言 `TimeoutError`，把期限改成 10 s（X17）时同样会得到 `TimeoutError`，所以存活。

### 4.4 H4：投递计数显示

**为什么需要新字段。** `retryCount` 是该请求全部失败投递的总数（自动 + 手动）。非可重试错误（如 400）在第 1 次自动投递后就停止，所以自动投递数可能是 1、2 或 3；`retryCount` 本身无法拆分。例：400 停止（retryCount 1），手动重试又失败（retryCount 2）——旧算法 `manual = max(0, 2 − 3) = 0`，显示 `Deliveries: 2 of 3`，看起来像自动重试过一次；真相是 1 次自动 + 1 次手动。再例：超时、400（retryCount 2），手动失败（3）：旧算法显示 `3 of 3`，真相是 2 次自动 + 1 次手动。

**做法。**

- `liveLoop.ts`：`PendingRequest.manualDeliveries`，`deliver(g, manual)` 在 `manual` 时加一；每个投递故障带 `manualRetries: request.manualDeliveries`；setup 故障为 0。`retry()` 的 reconcile 失败分支沿用 `...fault`，**不**增加手动数（那一次没有发生投递）。
- `retryPolicy.ts`：
  - `deliveryCounts(fault) → {automatic: retryCount − manualRetries, manual: manualRetries}`
  - `deliveriesText(fault)`，如 `"1 of 3 + 1 manual"`；手动数为 0 时没有后缀。分母仍是 `MAX_ATTEMPTS_PER_REQUEST`。
- `App.tsx`：`<span>Deliveries: {deliveriesText(fault)}</span>`。对三次自动投递耗尽的常见情形，显示与此前相同（`Deliveries: 3 of 3`、`3 of 3 + 1 manual`）。

**测试。**

`retryPolicy.test.ts`（node 环境，纯函数，期望全为字面量）：8 行参数表 + 1 个「400 后手动失败不能显示成 `2 of 3`」。覆盖可重试停止（3/0、4/1、6/3）与不可重试停止（1/0、2/0、2/1、3/1、3/2），每行同时断言 `deliveryCounts` 与 `deliveriesText`。

`liveLoop.test.ts`（5 个）：自动停止（3、0）；自动重试等待期间（1、0，未停止）；三次自动后两次手动失败（4/1、5/2）；400 后两次手动失败（1/0 → 2/1 → 3/2）；手动重试的 reconcile 失败不增加手动数，下一次真的投递并失败才是第一次手动（2/1）。

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

实测：`598 passed, 1 warning`；`Test Files 19 passed (19) / Tests 533 passed (533)`；`tsc exit=0`；`eslint exit=0`。另跑 `./node_modules/.bin/prettier --check`（本项触及的 6 个文件），全部符合。开工前同一 HEAD 的基线为 598 / 515 / 0 / 0。

**红灯先行**：先写测试、后写实现。实现前对 `ai/src/liveLoop.test.ts` 与 `frontend/src/api/retryPolicy.test.ts` 运行 `vitest run --no-cache`，结果 16 个失败（H1 两个：`newSessionOnRetry` 实得 `false`；H4 liveLoop 五个：缺 `manualRetries`；H4 retryPolicy 九个：`deliveryCounts is not a function`）。对照用例「普通 Start 恢复失败」在实现前就绿，符合预期（它守的是「不要改过头」）。「New Session 失败后点普通 Start」是实现后追加的，我随后用 `git show HEAD:ai/src/liveLoop.ts` 的旧实现在隔离副本里单独跑过：`1 passed | 52 skipped`，即它在旧代码上同样为绿（旧代码本来就保留 `activeSid`），它的作用是钉住这个取舍，红灯证据是变异 Y1e。H2、H3 是对既有用例的加固，红灯证据是第 5.2 节的「旧测试放过变异」。

### 5.2 变异验证（隔离副本）

```
D=$(mktemp -d …) && git -C /Users/liu/Desktop/FYP2-Live-System archive HEAD | tar -x -C "$D" \
  && ln -s /Users/liu/Desktop/FYP2-Live-System/.venv "$D/.venv" \
  && ln -s /Users/liu/Desktop/FYP2-Live-System/node_modules "$D/node_modules"
```
再把本项 6 个已修改文件覆盖进副本（`cmp` 逐一确认一致），副本里先跑全量：`533 passed (533)`。每个变异：只改副本里一处，整套 `vitest run --no-cache`，然后**从真实树复制回被改文件**并确认逐字节一致；全程没有在真实工作树里做变异，也没有启动 vite dev server（`node_modules/.vite` 的修改时间仍是开工前的 13:13）。

**brief 指定的 Y1–Y4**

| # | 变异 | 观察到的结果 |
|---|---|---|
| Y1a | 不记住 restart 标志（`newSessionOnRetry = not_found`） | 2 红：H1「create 失败」「模型检查失败」 |
| Y1b | `retry()` 的 setup 分支恒 `start(false)` | 同样 2 红 |
| Y1c | Y1a + Y1b（撤销 H1 的全部修复） | 同样 2 红 |
| Y2 | X19：500 归为 `transport` | 1 红：`retryPolicy.test`「a 500 is retryable whatever its body says…」 |
| Y3 | X17：`REQUEST_TIMEOUT_MS` 15000 → 10000 | 1 红：`client.test`「the client's own 15 s deadline…」 |
| Y4 | 纯函数改回旧算法（`automatic = min(retryCount, 3)`、`manual = max(0, retryCount − 3)`） | 4 红：参数表中 `2/1`、`3/1`、`3/2` 三行 + 「NOT '2 of 3'」 |

**旧测试确实放过了 X17 与 X19**（在副本里用 `git show HEAD:…` 的旧测试文件 + 变异）：旧 `client.test.ts` + X17 → `Tests 16 passed (16)`（存活）；旧 `retryPolicy.test.ts` + X19 → `Tests 27 passed (27)`（存活）。随后已恢复并 `cmp` 确认一致。

**补充变异（新增代码路径，全部变红，无存活）**

| # | 变异 | 结果 |
|---|---|---|
| Y1d | `retry()` 的 setup 分支恒 `start(true)`（过度新建） | 1 红：对照「普通 Start 恢复失败」 |
| Y1e | New Session 失败时清空 `activeSid` | 1 红：「失败后点普通 Start 仍恢复旧会话」 |
| Y1f | 每个 setup 故障都 `newSessionOnRetry = true` | 1 红：同上对照用例 |
| Y3b | 期限改为 20 s | 1 红：同一个 15 s 用例（上界） |
| H4a | `deliver()` 不累加手动数 | 3 红 |
| H4b | 累加条件取反（`!manual`） | 5 红 |
| H4c | 故障里写死 `manualRetries: 0` | 3 红 |
| H4d | 在 `retry()` 入口（reconcile 之前）累加 | 3 红 |
| H4e | reconcile 失败分支把 `manualRetries` 加一 | 1 红：「a reconcile that fails before the manual delivery…」 |
| H4f | 文本无 `+ n manual` 后缀 | 5 红 |
| H4g | 后缀条件 `manual > 0` 改 `> 1` | 3 红 |
| H4h | `automatic` 不扣除手动数 | 5 红 |
| H4i | 分母显示为预算 + 1 | 8 红 |
| H4j | `manual` 取负 | 8 红 |

共 **20 个变异**（Y1a–f、Y2、Y3、Y3b、Y4、H4a–j），全部变红；另有 2 个「旧测试 + 变异」存活的对照。

## 6. PASS / FAIL / SKIP 计数

| 门禁 | 基线（`e37a312`） | 本项之后 | 变化原因 |
|---|---|---|---|
| pytest（真实树） | 598 passed | **598 passed / 0 failed / 0 skipped** | 后端零改动 |
| vitest | 515 passed（19 个文件） | **533 passed**（19 个文件） | +18 = `liveLoop.test.ts` +9（H1 四个、H4 五个）+ `retryPolicy.test.ts` +9（H4 参数表 8 个、「NOT '2 of 3'」1 个）。H2、H3 是改既有用例，计数不变；`client.test.ts` 仍 16 个 |
| `tsc --noEmit` | 0 错 | 0 错 | — |
| `eslint .` | 0 问题 | 0 问题 | — |

## 7. 遗留问题

1. **`LiveFault` 多了一个必填字段 `manualRetries`**（brief 没有逐字列出）。它在 `ai/src/liveLoop.ts` 的允许范围内，也是 H4 的必要条件（4.4）。只有 `App.tsx` 与 `retryPolicy.ts` 消费它；`tsc` 0 错说明没有其他构造 `LiveFault` 的地方漏填。
2. **React 绑定层仍无 node 单测**：`FaultPanel` 对 `deliveriesText` 的接线、Retry 按钮对 `start(true)` 的触发路径只由 `tsc` / `eslint` 守护。纯函数与循环的行为各有变异验证的单测，缺的只是「组件确实调用了它们」这一环。按 brief 转入 Task 10；本跟进**没有**做浏览器冒烟。
3. **H2 文案**：见 4.2。`Category: model_runtime (HTTP 500)` 一行对存储类 500 仍显示 `model_runtime`，句子本身是中性的。
4. **setup 阶段的面板文案没有改**：`Retry repeats the setup: the model check, then the session.` 在「New Session 失败」后依然成立，但没有明说「会新建会话」。要在这种情形下写「Retry repeats the setup and creates a NEW session」需要在 `App.tsx` 增加一个分支，超出本跟进 App.tsx 的授权范围（只限 H4 接线与 H2 文案），留给控制者或 Task 10 决定。
5. **取舍**：New Session 失败时旧会话保持为活动会话（4.1），用测试钉住。若将来希望「New Session 失败即放弃旧会话」，要同时改 Y1e 对应的用例。
6. **未处理（brief 已记录在案）**：手动重试序号超过 1000（需约 997 次手动重试）；U1–U3（Retry 接线、摄像头断开与主动停止的区分、`captureMissReason` 接线）。

## 8. 证据路径

- 本报告：`/Users/liu/Desktop/FYP2-Live-System/docs/fyp2/implementation/task-08-followup.md`
- 实现：`ai/src/liveLoop.ts`、`frontend/src/api/retryPolicy.ts`、`frontend/src/App.tsx`
- 测试：`ai/src/liveLoop.test.ts`、`frontend/src/api/retryPolicy.test.ts`、`frontend/src/api/client.test.ts`
- 变异执行器与输出（会话临时目录，不入库）：`/private/tmp/claude-501/-Users-liu-Desktop-FYP-In-Cabin-Driver-Assessment--1--claude-worktrees-exciting-keller-fdf913/a1949e26-b3d7-4f7f-bd9f-059bf8cb6f0e/scratchpad/task8fu/`
  - `mut.py`：一次一个变异，改副本、跑全量 vitest、从真实树复原并核对
  - `mut_out1.txt`：20 个变异的完整输出
  - `mutdir.txt`：隔离副本路径
- 上一项报告：`docs/fyp2/implementation/task-08.md`

## 9. 下一项依赖

- **Task 9（Live-only 范围落地）**：不依赖本项的改动；遥测来源仍只在 `useLiveSession.ts` 的 `telemetryAt` 一处注入。
- **Task 10（端到端）**：建议补三条浏览器级用例，补上本跟进留下的 React 绑定缺口：(a) 运行中点 New Session、让 `POST /api/sessions` 失败，面板出现后点 Retry，断言新会话 id 出现且旧会话没有新窗口；(b) 400 停止后手动重试再失败，面板文本为 `Deliveries: 1 of 3 + 1 manual`；(c) 三次自动投递耗尽后面板为 `Deliveries: 3 of 3`。面板选择器沿用 Task 8 报告第 9 节（`role="alert"`、`aria-label="Monitoring stopped"`）。
- **阶段 5（裁定 A）**：与本项无交互。
