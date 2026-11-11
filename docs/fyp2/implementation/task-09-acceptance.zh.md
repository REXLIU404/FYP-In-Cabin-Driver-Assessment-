# Task 9 验收报告（中文）：Live-only 范围落地（D03），遥测游标除外

## 1. 任务概要

- **编号与名称**：Task 9，Live-only 范围落地。按你在 10-15 的决定，**遥测游标并入 R10**，本 Task 不改游标规则。
- **实现了什么**：
  - **K6 拆分**：新增 `PREPARED_RAW_TELEMETRY`（只含原始遥测），Live 路径只引用它；带预设概率的 `PREPARED_SESSION_WINDOWS` 只留给 replay。源码级范围守卫保证 Live 路径的代码（包括游标函数 `preparedTelemetryAt` 本身）不引用 replay 表。另有内容测试，逐行对照 `telemetry.csv`。
  - **K4 回放降级**：重新打开页面时总是回到 `LIVE_MODEL_RUNTIME`，不会悄悄进入 replay。「Data mode」选项改名为「Prepared replay (legacy, test-only)」，说明文字同步改写。
  - **K2**：游标落在第 14 / 17 行时，照常以 `telemetry_source: "missing"` 发送，不跳过、不停止。用真实回放行验证。
  - **K3**：replay 调用点的 D01 兼容在 Task 5 / 6 已完成。本 Task 核实后补了守护测试与变异证明，没有重复实现。
  - **K5（P1-6 遗留）**：趋势图 tooltip 改为先在小数上 half-up，再放大。平局用例：0.2855 → 28.6%，0.5005 → 50.1%。
  - **K8（Task 8 遗留文案）**：停止面板的说明按停止原因选文案，「自动重发用尽」与「手动重试失败」说法不同。setup 阶段新建会话失败时，写明 Retry 会新建会话。计数注释改为「已发出的投递」。
  - **K9（P0-D13 遗留）**：前端导出新增 `vision_expired`、`vision_age_s`、`telemetry_expired`、`telemetry_age_s` 四列，历史记录没有这些字段时导出为空单元格。replay 的 3 s 阈值保持固定，并在代码注释、页面说明和 README 中写明：replay 固定 3 s，Live 由后端按会话配置判定。
  - **K10（原定 Task 10，提前做）**：用 `react-dom/server` 静态渲染测试停止面板的文案，以及两种摄像头原因码（意外断开 / 主动停止）的显示。Retry 的点击处理抽成纯函数 `retryHandler`，测试证明它只调用 `live.retry()`，不会调用 `start(true)`。
  - **K7 文档**：重写 `prototype-tests/README.md` 为 Live 端到端清单；在 `docs/fyp2/06` 末尾追加范围说明，原文结论不动；`README.md` 与 `frontend/README.md` 加范围说明。
- **为什么必要**：D03 规定系统只保留 Live Monitoring 作为正式运行模式。修复前有两个问题：Live 路径引用了带预设概率的对象；回访用户会被悄悄带回 replay。报告里「Live-only」的说法因此站不住。

## 2. 实现证据

- **Commit**：
  - `da9cdb0`：路线图，写明游标移出本 Task；
  - `c304aa0`：Task 9 主体，26 个文件；
  - `6ec6799`：修复轮；
  - `27e805a`：控制者修正与记账。
- **范围偏离（控制者追认）**：新增 `frontend/src/utils/dataMode.ts`、`RuntimeNotices.tsx`、`runtimeNotices.ts`、`testing/markup.ts`。这些是 K8 / K10 抽出纯函数和组件所必需的，`dataMode.ts` 虽不严格必需，但有测试，一并接受。`retryPolicy.ts` 与 `liveLoop.ts` 只改了 K8 点名要求的部分；经核实，`liveLoop.ts` 只改了注释。后端、`ml/`、`docs/fyp2/review/`、计划文件都未改动。
- **游标**：规则未改，仍是 `floor(elapsed/2000) % 25`，`telemetry_timestamp` 仍是发送时刻。原先写在 hook 里的内联表达式被抽成命名函数 `preparedTelemetryAt`，R10 实施时只需替换这一个函数。

## 3. 测试结果

| 门禁 | 结果（控制者在 `27e805a` 亲自复跑） |
|---|---|
| pytest | 704 passed / 0 failed（未改后端） |
| vitest | **709 passed / 0 failed，24 个文件**（594 → 706 → 709） |
| tsc / eslint | 0 / 0 |
| 模型 SHA256 | 三个都未变 |
| 主仓库 `node_modules/.vite` | 修改时间未变（10-15 13:13），本 Task 没有碰主仓库 |

另外，实现者在一个**完全隔离**的副本里（它自己复制了一份 `node_modules`）跑通了 `tsc -b` 和 `vite build`，并做了浏览器冒烟。确认的几点：
- 「Data mode」显示 legacy / test-only 标签；
- 选了 replay 之后刷新页面，回到 Live；
- 停止面板的 setup 文案，会随是否新建会话而变化。

**变异检验**：实现者在隔离副本中逐个跑了 58 个变异，57 个变红，剩下 1 个是等价变异。另有 2 个变异起初存活，实现者随后加强了测试，最终都被杀死。

**控制者修正（评审的 Minor）**：有两条 `faultAdvice` 测试，期望值是用被测模块里的常量 `FAULT_TEXT` 构造的，等于自己验证自己。改法如下：
- 对 10 个类别，断言说明文字**不随停止原因变化**，且不为空；
- 把表中 `model_runtime` / `timeout` 的自动文案写成字面量钉住。

在隔离副本中验证了两个变异：
- 让某个类别的文案随停止原因变化 → 变红；
- 改写表中的自动文案 → 变红。

**存在但未执行的测试**：无。

## 4. 问题与风险

- **失败测试**：无。**非预期回归**：无。
- **首轮评审的 Important 问题（已修复）**：游标函数从 hook 搬进 `preparedSessionInput.ts` 之后，原有的范围守卫只扫描 hook 和 `liveLoop.ts`，扫不到这个函数。把它改成读取 replay 表，全部测试仍然通过。修复轮改为截取这个函数的源码，断言它只引用 `PREPARED_RAW_TELEMETRY`。同一个变异现在会让 2 个测试变红。
- **转入 R10 的事项**：
  - 游标规则、`telemetry_seq`、算术采集时间；
  - 手动 Retry 的「对账」请求失败时，停止面板仍显示「已自动重发」文案。修它需要在 `LiveFault` 里加一个标志，属于 `liveLoop` 的逻辑改动，而 R10 本来就要改 `liveLoop`。
- **未在真实浏览器中验证**：摄像头 `ended` / `stopped_by_user` 两个事件，以及停止后点 Retry 的真实点击。Browser 窗格屏蔽了摄像头。这两项留给 Task 10 的 Playwright 端到端测试。
- **说明**：生产包里两张表都在，因为同一模块同时构建了两张表，App 也仍然 import replay 窗口。守卫保证的是代码层面的边界（Live 代码不引用带概率的表），不是打包层面的排除。
- **既有问题**：`preparedSessionInput.ts` 的 prettier 格式偏差在本 Task 之前就存在，没有处理。

## 5. 验收结论

**PASS**

理由：
- 计划 Task 9 与 DoD 第 9 行的要求全部满足，游标部分按你的决定并入 R10；
- 评审发现的 Important 问题已在修复轮解决，Minor 由控制者修正，都经过变异验证；
- 门禁由控制者亲自复跑，全部通过。

## 6. 下一任务就绪度

- **R10**：修订政策（双条件规则）在等 Codex 的独立评审，以及你的最终批准。R10 实施时还要接手：Task 9 留下的游标函数、K2 与游标相关的测试，以及「对账失败」的文案标志。
- **Task 10**：其中有一部分与 R10 无关，可以先做：类型检查门禁、显式打印模型缺失导致的 skip、导出遇到 NULL 或畸形数据时的守卫、`freeze_manifest`、门禁原始日志、分段计时。依赖 R10 的部分要等 R10 落地后再做：端到端测试中的告警序列断言，以及单分支连续性测试的预期值。
