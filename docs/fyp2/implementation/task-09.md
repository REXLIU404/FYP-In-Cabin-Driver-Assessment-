# Task 9 实现报告 —— Live-only 范围落地（含 P1-6 / Task 8 / P0-D13 遗留与 React 绑定层静态渲染断言）

## 1. 任务编号与名称

- **Task 9**（`TASK-9-LIVE-ONLY`）：Live-only 范围落地（计划 D03 / D11）。brief 的 K1–K10：K1 游标不改、K2 保持 R5、K3 replay 调用点的 D01 兼容、K4 回访用户不再被带回 replay、K5 趋势图 tooltip 舍入（P1-6 遗留）、K6 `PREPARED_RAW_TELEMETRY` 拆分、K7 文档、K8 Task 8 遗留文案、K9 P0-D13 遗留（导出列、replay 阈值）、K10 React 绑定层静态渲染断言（原定 Task 10，提前）。
- 工作树 `/Users/liu/Desktop/FYP2-Live-System`，分支 `fyp2/live-system`，基线 HEAD `da9cdb0`（开工前核实：分支与 HEAD 吻合，`git status --porcelain` 为空）。
- 基线门禁（开工前在同一 HEAD 复现）：pytest 704 passed / vitest 594 passed（21 个文件）/ tsc 0 / eslint 0。
- 零改动：后端、融合 / FSM / EMA 逻辑、模型文件、`docs/fyp2/review/`、计划文件、主仓库。**不删除任何东西**：prepared-probability replay 仍在，仍可从页面里选择。

## 2. 实现状态

**DONE_WITH_CONCERNS。** 四道门禁达标：pytest 704 passed / 0 failed / 0 skipped，vitest 706 passed，`tsc` 0 错，`eslint` 0 问题。K1–K10 全部落地。concerns 见第 7 节，最需要知情的四条：

1. **K10 的「点击」只证明到函数层**：Retry 按钮的 `onClick` 绑定的是 `onRetry`、`onRetry` 是 `retryHandler(live)`（调 `live.retry()` 而不是 `start(true)`）、App 把它传给了 `FaultPanel`——这三层各有测试 / 源码守卫；但「在真实浏览器里点这个按钮」没有被自动化断言，留给 Task 10 的 Playwright。摄像头 `ended` 与 `stopped_by_user` 事件同样没有在真实浏览器里触发（浏览器窗格屏蔽摄像头）。
2. **K9 的四个新导出列属于 replay 的前端导出**：Live 模式下导出按钮走的是后端 `GET /api/sessions/{id}/export`（`live.exportSession`），前端 `export.ts` 只服务 legacy replay。后端导出本来就带完整 `provenance`（含四个过期字段），本项没有改后端。
3. **K1 的游标逻辑未改，但被「搬」了位置**：为了让 K2 能用真实数据驱动循环，把 `Math.floor(elapsedMs / 2000) % N` 这一个表达式原样搬进命名函数 `preparedTelemetryAt`（`preparedSessionInput.ts`），hook 只剩 `telemetryAt: preparedTelemetryAt`。推进规则一个字没变；R10 要换规则时只需换这一个函数。
4. 58 个变异里只有 **1 个存活（N4d）**，它是等价变异（行为与原代码相同），见 5.3。

| 项 | 状态 | 守护 |
|---|---|---|
| K1 游标不改 | 完成（规则未变，只搬位置） | N3d（改成每秒一行）→ 5 个测试变红 |
| K2 保持 R5 | 完成：用真实 prepared 行驱动循环 | 新增 4 个测试；N3a–c 变红 |
| K3 replay 调用点的 D01 | **核实：已由 Task 5 / 6 完成**；补上调用点缺口 | 既有 3 + 新增 6；N8a–d 变红 |
| K4 回访用户 | 完成 | 新增 7 + 7 个测试；N4a–c、N4e–h 变红 |
| K5 tooltip 舍入 | 完成 | 新增 7 个测试；N5a–e 变红 |
| K6 拆分 | 完成 | 新增 35 个测试（含静态范围守卫）；N6a–d、N7a–f 变红 |
| K7 文档 | 完成 | 无（文档）；`docs/fyp2/06` 原文 0 行删除 |
| K8 文案 | 完成 | 新增 9（`retryPolicy`）+ 1（`liveLoop`）个测试，另有 7 个 FaultPanel 渲染断言计入 K10 的 26 个；N9a–h 变红 |
| K9 导出列 + replay 阈值 | 导出列完成；阈值选「注释说明」 | 新增 10 个测试；N10a–f 变红 |
| K10 静态渲染 | 完成（点击留给 Task 10，见上） | 新增 26 个测试；N11a–k 变红 |

## 3. 创建 / 修改的文件

提交内含 26 个文件：19 个已跟踪文件修改（行数为 `git diff --numstat`），6 个新文件，加本报告。

**实现**

| 文件 | 变化 |
|---|---|
| `frontend/src/data/preparedSessionInput.ts` | +62/−3：`PreparedRawTelemetryRow`、`buildPreparedRawTelemetry`、`PREPARED_RAW_TELEMETRY`、`preparedTelemetryAt`；`PREPARED_FRESHNESS_TOLERANCE_S` 旁的注释重写（K9） |
| `frontend/src/hooks/useLiveSession.ts` | +4/−6：不再 import `PREPARED_SESSION_WINDOWS`，`telemetryAt: preparedTelemetryAt` |
| `frontend/src/utils/persistence.ts` | +13/−6：`loadConfig` 恒返回 `LIVE_MODEL_RUNTIME`（K4） |
| `frontend/src/utils/dataMode.ts`（新，27 行） | Data mode 选项与说明文字：`DATA_MODE_OPTIONS`、`DATA_MODE_NOTE`（K4） |
| `frontend/src/components/trendSeries.ts` | +13/−2：`toPercentPoint`，先在小数上 half-up 再放大（K5） |
| `frontend/src/api/retryPolicy.ts` | +48/−2：`faultAdvice`、`retryNote`，`FAULT_TEXT` 加可选的 `adviceAfterManualRetry`（K8） |
| `ai/src/liveLoop.ts` | +10/−4：只改 `retryCount` / `manualRetries` 的注释（K8）；无逻辑改动 |
| `frontend/src/utils/export.ts` | +12/−0：四个过期列（K9） |
| `frontend/src/components/RuntimeNotices.tsx`（新，105 行） | 从 `App.tsx` 原样搬出的 `FaultPanel`，加 `CaptureMissNotice`、`CameraStatusLine`（K10 需要可导出的组件） |
| `frontend/src/utils/runtimeNotices.ts`（新，38 行） | `CAPTURE_MISS_TEXT`、`CAMERA_EVENT_TEXT`（从 `App.tsx` 搬出）、`captureMissText`、`retryHandler` |
| `frontend/src/App.tsx` | +19/−113：删除内联的 `FaultPanel` 与两个文字表，改用上面的组件；Data mode 选项与说明改读 `dataMode.ts`；`onRetry={retryHandler(live)}` |

**测试**

| 文件 | 变化 |
|---|---|
| `frontend/src/data/preparedRawTelemetry.test.ts`（新，185 行） | 35 个：原始表 = CSV 逐行（25 行 + 其余）、游标、静态范围守卫 |
| `ai/src/liveLoop.test.ts` | +116/−2：rig 增加 `telemetrySource` 选项；K2 的 4 个用例；K8 的「按发出计数」1 个用例。删除的 2 行只是被替换的 `telemetryAt` 桩，没有测试被删除或弱化 |
| `frontend/src/utils/alertOverlay.test.ts` | +90：K3 的 6 个 |
| `frontend/src/utils/persistence.test.ts` | +75：K4 的 7 个 |
| `frontend/src/utils/dataMode.test.ts`（新，60 行） | K4 的 7 个（标签 5 + App 源码守卫 2） |
| `frontend/src/components/trendChart.test.ts` | +72：K5 的 7 个 |
| `frontend/src/api/retryPolicy.test.ts` | +102：K8 的 9 个 |
| `frontend/src/utils/export.test.ts` | +130：K9 的 10 个 |
| `frontend/src/components/runtimeNotices.test.ts`（新，318 行） | K10 的 26 个 |
| `frontend/src/testing/markup.ts` | +27/−1：`findElements`（走返回的元素树，用来在没有 DOM 的环境里「点击」） |

**文档**

| 文件 | 变化 |
|---|---|
| `prototype-tests/README.md` | 重写：Week 7 验收口径改为 Live 端到端（K7） |
| `docs/fyp2/06_WEEK7_CRITICAL_PATH_AND_ACTION_PLAN.md` | 末尾追加一节（+21/−0，**原文 0 行删除**） |
| `README.md`、`frontend/README.md` | 加范围说明 |
| `docs/fyp2/implementation/task-09.md` | 本报告 |

未触碰：`backend/`、`ml/outputs/`、`docs/fyp2/review/`、计划文件、主仓库、任何数据库（浏览器冒烟只用隔离副本里的一次性 SQLite）。

## 4. 实现摘要

### K1　游标不改

推进规则仍是 `Math.floor(elapsedMs / 2000) % 25`，`startedAt` 仍只在新建会话时设置（`ai/src/liveLoop.ts` 的 create 分支）。所以 pause/resume 或重试之后游标仍会跳跃、`telemetry_timestamp` 仍是发送时刻——这两点按裁定并入 R10，本项没有碰。唯一的改动是位置：表达式由 `useLiveSession` 的内联 lambda 搬进 `preparedTelemetryAt`（数据源由 `PREPARED_SESSION_WINDOWS` 换成 `PREPARED_RAW_TELEMETRY`，K6 要求的「只改 import 与数据来源」）。`preparedRawTelemetry.test.ts` 用字面量钉住规则（0 / 1999 / 2000 / 25 999 / 26 000 / 27 999 / 28 000 / 32 000 / 50 000 ms），变异 N3d（改成每秒一行）使 5 个测试变红。

### K2　保持 R5

行为本来就是对的（Task 8），本项没有改循环；补的是**真实数据**上的证明。`liveLoop.test.ts` 的 rig 新增 `telemetrySource` 选项，4 个新用例把**生产的** `preparedTelemetryAt` 接进循环，2 inferences/s、API 零延迟，所以第 i 个 tick 落在 `i × 500 ms`、读第 `⌊i/4⌋ + 1` 行：

- 摄像头开：一整轮 50 s 恰好 100 次 `infer`，第 52–55 tick（第 14 行）与第 64–67 tick（第 17 行）的载荷是 `telemetry_features: null`、`telemetry_timestamp: null`、`telemetry_source: "missing"`，且**带图像**（`image_base64: frame-N`）；其余 tick 为 `prepared_replay`；结束时 `running: true`、`fault: null`、history 100 条；
- 第 14 行之后的 tick 回到真实遥测（第 13 / 14 / 15 / 16 / 17 / 18 行逐个断言）；
- 摄像头关：同样 100 次，第 14 / 17 行两路都没有输入，`imagelessRequests` 为 100，循环不停；
- 第 51 s 起回到第 1 行（回绕）。

Task 8 的 R5 用例（`the camera never stops the loop (R5)` 5 个）未改，仍绿。变异 N3a（第 14 行改为跳过发送）：5 个红，其中包含 Task 8 原有的「with neither image nor telemetry…」；N3b（仅两路皆无时跳过）2 个红；N3c（该行直接停止循环）5 个红。

### K3　replay 调用点的 D01 兼容——核实结论：Step 4 已在 Task 5 / 6 完成，补上了调用点缺口

核实：`App.tsx` 的 `appendReplay` 调的是 `applyAlertState(record, alertFsmRef.current, Date.now())`（基线 `:148`），不再 spread `AlertSeverity: fsm.severity`；`applyAlertState` 在 `RiskLevel === null` 时输出 `AlertSeverity: null`，FSM 的 `updateAlertState(…, null, …)` 清空两个计时（挂起）。

已有的守护：`alertOverlay.test.ts` 3 个（不可用记录保持 null 且 FSM 记忆保留、四字段为 null、可用记录仍得到 FSM 严重度）；`alertFsm.test.ts` 的「a window with no assessment suspends the FSM」一组（UT-TIME-04 等）。

**缺口**：没有任何东西证明 App 的调用点真的走这条路径，也没有在 prepared 数据上跑过「窗口 17」。补了 6 个测试：
- 按 App 的做法（`buildRiskUpdate` → `applyAlertState`，每窗 2 s）折叠完整 25 窗口的 prepared 会话：窗口 17 的 `RiskLevel` 与 `AlertSeverity` 都为 null；窗口 16 为 High 而窗口 17 之后 `lowSince` 与 `highSince` 都为 null（不再被读成 Low 去推进 10 s 恢复计时），窗口 18 的 High 连击重新锚定在自己的时刻；全部 25 条通过 `assertAvailabilityInvariant`，且只有窗口 17 的严重度为 null；
- 源码守卫（读 `App.tsx`，去注释后）：含 `applyAlertState(`，不含 `updateAlertState`，不含 `AlertSeverity:`。

变异（隔离副本）：N8a（null `RiskLevel` 继承上一个 severity）4 个红（含原有的 2 个）；N8b（App 调用点把 FSM 严重度 spread 回记录）1 个红（源码守卫）；N8c（FSM 的 null 分支失效、落到 Low 分支）4 个红；N8d（调用点不再用 `applyAlertState`）1 个红。

### K4　回访用户不再被悄悄带回 replay

`loadConfig` 不再恢复保存的 `operationMode`：恒为 `LIVE_MODEL_RUNTIME`（注释写明原因），其余已保存的设置（权重、阈值、帧率、新鲜度容差）照常恢复。页面自己的 `useState(() => loadConfig())` 持有本次访问的模式，用户在页面里选 replay 才进入 replay；`saveConfig` 仍会把所选模式写进存储，但下一次加载不读它。

「Data mode」选项与说明改读新的 `dataMode.ts`：选项文字 `Prepared replay demo` → `Prepared replay (legacy, test-only)`；说明文字改成「Legacy / test-only replay, not the Live system: prepared probabilities and local risk logic, with no trained model and no backend. The camera preview does not drive it. It is kept for regression tests and backward compatibility, and the next page load starts on Live again. Evidence older than a fixed 3 s counts as expired here; the freshness setting applies to Live sessions only.」

测试：`persistence.test.ts` 的 `loadConfig`（node 环境、沿用文件里已有的内存 `localStorage` 桩）7 个：无存储 → Live；存了 replay → Live；存了 Live → Live；无法识别的值 → Live；存了 replay 且有其他设置（权重 0.7/0.3、帧率 5、容差 5）→ Live 且其余设置保留；用户在本次访问里选 replay 并 `saveConfig` 之后再 `loadConfig` → Live；没有 `window` → Live。`dataMode.test.ts` 7 个：标签字面量、说明里的 legacy / test-only / not the Live system / starts on Live again、固定 3 s 一句，以及 App 源码守卫（选项来自 `DATA_MODE_OPTIONS.map`、说明来自 `DATA_MODE_NOTE[config.operationMode]`、不再硬编码旧文字）。

**真实浏览器核对**（隔离副本，见 5.4）：在页面里选 replay → `localStorage.app_config.operationMode` 变为 `PREPARED_SESSION_RUNTIME`、说明换成 legacy 文字；重新加载 → 选择器回到 `LIVE_MODEL_RUNTIME`。

### K5　趋势图 tooltip 舍入（P1-6 遗留）

根因：序列点是 `P × 100`，乘法在二进制里做，`0.2855 × 100 = 28.549999999999997`，平局在 `formatFixed` 看到它之前就没了。改为 `toPercentPoint(p) = roundHalfUp(roundHalfUp(p, 3) × 100, 1)`：先在小数上 half-up 到 3 位（0.1 %），再放大，外层 `roundHalfUp` 只负责去掉放大带来的二进制尘埃——与 `asPercent` 同一顺序。`formatTrendTooltip` 不变。

**图表坐标的变化**：brief 允许不变；实际上它变成了「到 0.1 % 的干净值」（`0.07 → 7` 而不是 `7.000000000000001`；对后端已存的 3 位概率，坐标等于 `P × 100` 的精确值）。

测试走整条路径（记录 → 序列点 → tooltip）：0.2855 → `28.6%`，0.1455 → `14.6%`（brief 要求的两个平局），telemetry 序列同样；加了两个其他取整写法会错的平局（`Math.round(P × 1000) / 10` 对 0.5005 得 50.0；`(P × 100).toFixed(1)` 对 0.0015 得 0.1）——它们杀死了最初存活的变异 N5e（`Math.round` 写法）；非平局值（0.2854 / 0.2856）与端点（0 / 0.5 / 1）；3 位概率的坐标无二进制尘埃（0.07 / 0.29 / 0.57 / 0.286）。

### K6　`PREPARED_RAW_TELEMETRY` 拆分

`preparedSessionInput.ts` 新增 `PreparedRawTelemetryRow { timestamp, telemetry_features, telemetry_age_s }`、`buildPreparedRawTelemetry(csv)`、`PREPARED_RAW_TELEMETRY`（与 replay 窗口**同一条解析路径**，所以两者不会对同一行产生分歧）和 `preparedTelemetryAt`。`telemetry_age_s` 在没有遥测的行（14、17）为 `null`（CSV 的 999 是哨兵，不当年龄）。`useLiveSession.ts` 只 import `preparedTelemetryAt`。带 `P_distraction` / `P_telemetry_anomaly` / `visual_top_classes` 的 `PREPARED_SESSION_WINDOWS` 只剩 `App.tsx` 的 replay 在用。

`preparedRawTelemetry.test.ts`（35 个）：
- **内容测试**：用 `?raw` 读 `telemetry.csv`（与 F1 的 `missingCases.test.ts` 同一读法，测试自带解析器，不借用实现），对每一行断言 `timestamp`（`10:00:SS+08:00` → `2026-05-06T02:00:SS.000Z`）、8 个特征（值与**固定顺序**）或 `null`、`telemetry_age_s`（可用行为 CSV 的值，否则 `null`）；另用字面量钉住第 1 行的 8 个值、缺失行恰为 `[14, 17]`、第 16 行的年龄为 4；每行恰好只有三个键（不含任何概率）；与 `PREPARED_SESSION_WINDOWS` 的 `telemetry_features` / `timestamp` 逐项相等；
- **范围守卫**（注释里写明这是守卫而不是行为测试）：`useLiveSession.ts` 与 `ai/src/liveLoop.ts` 的源码（去注释后）不含 `PREPARED_SESSION_WINDOWS` 或 `buildPreparedWindows`；`liveLoop.ts` 的 import 恰为 `["./types"]`；正向检查 hook 含 `telemetryAt: preparedTelemetryAt`（防止守卫因为来源被删而空过）。

**边界**：`PREPARED_RAW_TELEMETRY` 与 `PREPARED_SESSION_WINDOWS` 在同一个模块里，该模块加载时两者都会构建，而 `App.tsx` 为了 legacy replay 仍 import 后者，所以生产 bundle 里两者都有。守住的是**代码层面**的边界：Live 代码不读、也不命名那个概率对象。

### K7　文档

- `prototype-tests/README.md` 按计划 Step 5 重写：被验收的链路、四道自动门禁、手动 Live 端到端清单（后端就绪且 `/api/models` 报模型已加载 → Start Monitoring → 至少 N 个来自 `/sessions/{id}/infer` 的 201 并记录 `request_id` → 五个视图读后端记录 → flag 经 PATCH 持久化 → 导出覆盖整个会话而不是 UI 的 500 条 → pause / retry / restart 符合策略 → 注入的传输故障 3 次后停止并能手动恢复），并声明脚本化版本是 Task 10 的 `backend/tests/test_live_e2e.py`、**目前尚不存在**。每一步的端点、文案都对照过代码（`PATCH …/windows/{id}/flag`、`GET …/export`、`GET /api/faults`、`DRA_DATABASE_URL`、停止面板与延迟重试的文字）；没有声称任何一步已被自动化。
- `docs/fyp2/06` 末尾追加一节（中文）：声明 `ST-REPLAY01`（计划写作 `ST-REPLAY-01`）在本阶段由 Live 端到端取代；原文结论、状态、勾选框一字未动（`git diff --numstat`：+21 / −0）；并明确本节不使任何 W7 签收框变为已勾选。
- `README.md` 与 `frontend/README.md` 加范围说明（Live 是唯一主运行时；replay 保留为 legacy / test-only；Live 只读 raw telemetry；不声称的东西）。

### K8　Task 8 遗留文案

- **投递计数行与说明矛盾**：`FAULT_TEXT` 里 `model_runtime` 与 `timeout` 的说明写「请求已自动重发但持续失败」。停止原因由 `manualRetries` 区分：为 0 表示自动预算用尽（这两个类别可重试，所以此时一定已发 3 次）；大于 0 表示最后一次投递是用户手动发起且失败了。新增纯函数 `faultAdvice(fault)`：手动失败时改用 `adviceAfterManualRetry`（「A model or storage error on the server (HTTP 500). The retry you triggered failed as well.」/「No answer within 10 seconds. The retry you triggered timed out as well. Check the backend, then use Retry.」），不再声称「自动重发」；其余类别不变。
- **setup 阶段的 Retry 说明**：新增纯函数 `retryNote(fault)`：setup 且 `newSessionOnRetry` → 「Retry repeats the setup: the model check, then a NEW session.」；setup 否则 → 原句；delivery 阶段两句不变。`FaultPanel` 改用 `faultAdvice` 与 `retryNote`。
- **`liveLoop.ts` 注释**：`retryCount` 改为「已**发出**的投递（自动 + 手动），发出时就计数，被 Pause 在途取消的那次也算在内，所以不严格等于失败数」；`manualRetries` 同口径。为让这句注释成为受守护的事实，新增 `liveLoop.test.ts` 用例：3 次自动失败 → 手动重试发出第 4 次并 hang → Pause 取消它 → 再 Retry 发出第 5 次且失败 ⇒ `retryCount 5`、`manualRetries 2`、`attemptIndex 5`；变异 N9h（被取消的投递不计数）1 个红。

测试：`retryPolicy.test.ts` 9 个（两个类别在自动 / 手动两种原因下的**逐字**句子；手动句不含 `automatically`；两种原因从不共用一句；其余类别两种原因下相同；`FAULT_TEXT` 的 advice 仍是自动句；`retryNote` 四种组合）；`runtimeNotices.test.ts` 的 FaultPanel 渲染把每一种组合与投递计数行并排断言（`Deliveries: 3 of 3` + 自动句；`Deliveries: 1 of 3 + 1 manual` + 手动句且无 `automatically`；超时的 `3 of 3 + 1 manual`）。

### K9　P0-D13 遗留

- **导出列**：`EVIDENCE_COLUMNS` 在 `telemetry_freshness` 之后追加 `vision_expired`、`vision_age_s`、`telemetry_expired`、`telemetry_age_s`（共 23 列），取自 `record.provenance`；历史记录没有这些字段时 CSV 为空单元格、JSON 为 `null`（不伪造 `false` / `0`），所有记录的 JSON 键集合一致。和 `*_freshness` 两列一样，只在证据解释开启时出现；关闭时导出不变。测试 10 个：表头位置；vision 过期（age 4）与 telemetry 过期（age 7.5，两路年龄故意不同）；从未到达（`false` + 空年龄）；两路都过期；pre-ruling 记录（`provenance` 为 undefined）四个空单元格；provenance 有别的键但没有这四个也为空；JSON 的 `null` 与同构；关闭证据解释时不变；CSV 表头与 JSON 键同序。
- **replay 的过期阈值——选「在常量旁注释清楚」，不让它跟随 `AppConfig`**。理由：(1) prepared 窗口在**模块加载时**一次性构建（`PREPARED_SESSION_WINDOWS` 是模块常量），此刻还没有任何配置；要让它跟随设置，就得把窗口构建延后到有配置之后，改变 replay 的数据结构与它所有的调用方（`App`、`testing/records.ts`、四个测试文件）；(2) replay 是保留的 legacy 路径，这个 task 的原则是「只降级、澄清」；(3) 它会让钉死的 replay 输出随设置漂移（`missing_cases.csv` 的 W16 = 60.0、`preparedSessionInput.test.ts` 的 3 s 严格边界都以 3 s 为前提）。注释现在明确写「The replay is fixed at 3 s; Live is judged by the backend from the session's own configuration」，并同步到页面（replay 说明里的「Evidence older than a fixed 3 s counts as expired here; the freshness setting applies to Live sessions only」，有测试钉住）与 `frontend/README.md` 的对照表。

### K10　React 绑定层静态渲染断言

沿用 `branchStatusRender.test.ts` 的办法：`react-dom/server` 的 `renderToStaticMarkup` + `createElement`，node 环境，无 jsdom、无新依赖。为了能渲染，把 `App.tsx` 里内联的 `FaultPanel` 与两个文字表**原样**搬到 `components/RuntimeNotices.tsx`（并导出），同时新增 `CaptureMissNotice`、`CameraStatusLine`；非组件的导出（文字表、`captureMissText`、`retryHandler`）放在 `utils/runtimeNotices.ts`（`react-refresh/only-export-components` 不允许组件文件导出函数）。`runtimeNotices.test.ts` 26 个：

- **停止面板**：delivery 阶段 `newSessionOnRetry` 为 false → 「Retry re-sends this same request to the same session.」且无 `NEW session`；为 true（404）→ 「Retry will create a NEW session.」且无「re-sends」；setup 阶段两种（K8 的文案）；setup 面板没有 request id 与投递计数行；非停止态是 `role="status"` 的状态行且没有按钮；停止态是 `role="alert"`、`aria-label="Monitoring stopped"`，含类别、HTTP 状态、request id、服务端消息；按钮读 `Retry`，`retrying` 时 `disabled` 且读 `Retrying…`。
- **摄像头两种原因码显示不同的文字**：`stopped_by_user` →「(the camera was stopped)」，`device_disconnected` →「(the camera was disconnected)」，两者渲染不相等；7 个原因码各有自己的文字（集合大小 7）且不会漏出原始代码；未知代码原样显示；R5 的那句「monitoring continues with telemetry only」仍在。状态行 `CameraStatusLine`：`stopped by you at` / `disconnected at` / `failed to start at`，用户停止与设备断开不同；无事件时 `Camera: live · 30.0 FPS`（29.95 half-up；FPS 改用 `formatFixed`，不再用 `toFixed`）。
- **点击**：静态渲染测不到点击，所以拆成三层。(1) `FaultPanel` 无 hook，直接调用它得到返回的元素树，`findElements` 找到唯一的 `button`，调它的 `props.onClick()` → `onRetry` 恰好被调一次；(2) 抽出纯函数 `retryHandler(live)`：调 `live.retry()` 一次，**不**调 `start`（测试里的假 `live` 同时带 `retry` 与 `start` 的 mock）；把它接到按钮上再「点」→ `live.retry()` 被调一次；(3) App 的接线用源码守卫钉住：`<FaultPanel … onRetry={retryHandler(live)} />` 且没有 `onRetry={() =>`；`<CaptureMissNotice reason={live.lastCaptureMiss} />`；`<CameraStatusLine … status={camera.status} actualFps={camera.actualFps} event={camera.event} />`。**真实浏览器里的点击**留给 Task 10（见第 7 节）。

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

实测：`704 passed, 1 warning in 8.76s`（0 skipped）；`Test Files 24 passed (24) / Tests 706 passed (706)`；`tsc exit=0`；`eslint exit=0`。开工前同一 HEAD 的基线：`704 passed`；`21 files / 594 passed`；`0`；`0`。另跑 `./node_modules/.bin/prettier --write` 于本项新建与改动的文件（`README.md`、`frontend/README.md`、`prototype-tests/README.md` 与各 `.ts` / `.tsx`），`preparedSessionInput.ts` **除外**——它在 `da9cdb0` 上就不符合 prettier（只有第 97–117 行那个大数组，P0-D13 报告第 7 节第 8 条已记录），本项新增的代码行符合，未顺手格式化以免产生无关改动。

### 5.2 红灯先行（实现之前先写测试，运行得到的失败数）

| 项 | 实现前的 vitest 结果 |
|---|---|
| K6 内容 / 游标 / 守卫 | `33 failed \| 2 passed (35)`（`preparedTelemetryAt` 等不存在） |
| K4 `loadConfig` | `3 failed \| 17 passed (20)` |
| K5 tooltip | `3 failed \| 12 passed (15)`（0.2855、0.1455、telemetry 各一） |
| K8 文案 | `9 failed \| 36 passed (45)`（`faultAdvice` / `retryNote` 不存在） |
| K9 导出 | `8 failed \| 20 passed (28)` |

**没有红灯先行的**（诚实声明）：K2（测的是 Task 8 已有的行为）、K3（App 的调用点早已正确）、K10（先做了搬出 `FaultPanel` 的重构，再写测试，首次运行即绿）、K8 的「按发出计数」用例（注释本来就对应既有行为）。它们的「会变红」证据是 5.3 的变异。

### 5.3 变异验证（全部在隔离副本里做）

```
D=$(mktemp -d) && git -C /Users/liu/Desktop/FYP2-Live-System archive HEAD | tar -x -C "$D" \
  && ln -s /Users/liu/Desktop/FYP2-Live-System/.venv "$D/.venv" \
  && ln -s /Users/liu/Desktop/FYP2-Live-System/node_modules "$D/node_modules"
```

再把本项 25 个改动 / 新增文件叠加进副本（逐个 `cmp` 确认一致）。`mut9.py` 每次只改副本里一处、跑**整套** `vitest run --no-cache --reporter=json`、记录变红的测试，然后**从真实树复制回被改文件**并 `filecmp` 逐字节确认一致（58 次全部 `restored-identical=True`）。没有在真实工作树里做过任何变异。最终一轮是对**最终**测试重跑全部变异。

共 **58 个变异：57 个变红，1 个存活（N4d，等价变异）**。brief 的 N3–N11 逐项（括号内为变红的测试数，总数 706）：

| brief | 变异（副本里） | 观察到的结果 |
|---|---|---|
| **N3** | N3a `tick` 在遥测为 null 时跳过发送；N3b 仅在两路皆无时跳过；N3c 该行直接停止循环；N3d 游标改成每秒一行 | N3a 5、N3b 2、N3c 5、N3d 5。N3a 包含 Task 8 原有的 R5 用例（「with neither image nor telemetry…」）与 K2 的 4 个新用例 |
| **N4** | N4a `loadConfig` 恢复保存的模式（原代码）；N4b 只恢复 replay；N4c 恒返回 replay；N4e 选项改回「Prepared replay demo」；N4f 说明文字丢掉 legacy / not the Live system；N4g App 硬编码「Demo mode」说明；N4h App 硬编码旧选项 | N4a 3、N4b 3、N4c 7、N4e 1、N4f 1、N4g 2、N4h 2 |
| **N5** | N5a tooltip 改回 `P × 100`；N5b 先放大再取整；N5c 只还原 telemetry 序列；N5d 只还原 vision 序列；N5e 改成 `Math.round(P × 1000) / 10` | N5a 4、N5b 3、N5c 1、N5d 3、N5e 1 |
| **N6** | N6a hook 重新 import `PREPARED_SESSION_WINDOWS`；N6b hook 改读它；N6c `liveLoop.ts` import 它；N6d hook 的 `telemetryAt` 不再来自 raw 源 | N6a 1、N6b 2、N6c 2、N6d 1 |
| **N7** | N7a 少一行；N7b 错一个值（第 8 行 `brake_pressure` 78→79，仅 raw 表）；N7c 第 16 行年龄错（仅 raw 表）；N7d 第 14 行带空特征对象而不是 null；N7e 时间戳不是 ISO；N7f 混进概率字段 | N7a 5、N7b 2、N7c 2、N7d 8、N7e 26、N7f 1 |
| **N8** | N8a null `RiskLevel` 继承上一个 severity（overlay）；N8b App 调用点 spread 回 FSM 严重度；N8c FSM 的 null 分支失效；N8d 调用点不再用 `applyAlertState` | N8a 4、N8b 1、N8c 4、N8d 1 |
| **N9** | N9a 手动失败的停止仍显示「已自动重发」；N9b 边界（`> 1`）；N9c 无手动投递也用手动句；N9d setup + New Session 读起来像普通恢复；N9e 面板不用 `faultAdvice`；N9f 面板写死 Retry 说明；N9g delivery 阶段忽略 `newSessionOnRetry`；N9h 被 Pause 取消的投递不计数 | N9a 4、N9b 4、N9c 4、N9d 2、N9e 2、N9f 3、N9g 2、N9h 1 |
| **N10** | N10a 表头没有四列；N10b 列在但不带值；N10c 历史记录得到伪造的 `false`；N10d 缺失年龄导出为 0；N10e vision 与 telemetry 互换；N10f telemetry 年龄列带了 expired 标志 | N10a 9、N10b 5、N10c 3、N10d 4、N10e 5、N10f 4 |
| **N11** | N11a 设备断开读成「stopped」（提示）；N11b 设备断开读成「stopped by you」（状态行）；N11c 用户停止读成「disconnected」；N11d `retryHandler` 调 `start(true)`（N11d2 什么都不做，N11d3 调两次）；N11e 按钮不绑 `onRetry`；N11f 按钮不 `disabled`；N11g 未知代码被通用语掩盖；N11h FPS 改用 `toFixed`；N11i App 把 Retry 接到 `start(true)`；N11j 给错 `reason`；N11k 不给 `event` | N11a 3、N11b 2、N11c 3、N11d 2、N11d2 2、N11d3 2、N11e 2、N11f 1、N11g 1、N11h 1、N11i 1、N11j 1、N11k 1 |

**最初存活、补测后杀死的 2 个**：N5e（`Math.round(P × 1000) / 10` 在 0.2855 / 0.1455 上碰巧正确 → 补了 0.5005 与 0.0015 两个平局）；N6d（`telemetryAt: () => null` 仍留着 import，只查标识符会空过 → 守卫改为匹配 `telemetryAt: preparedTelemetryAt`）。

**唯一存活：N4d**——`{...merged, ...saved, operationMode, …}`。`merged` 本来就是 `{...DEFAULT_CONFIG, ...saved}`，再 spread 一次 `saved` 得到逐字段相同的对象，是**等价变异**，不是测试缺口。

### 5.4 构建与真实浏览器冒烟（不入库）

- 完全隔离的第三份副本（`git archive` + 叠加 + **复制**了一份 `node_modules`，不是符号链接，所以 vite 不会碰主仓库）：`tsc -b` 通过；`vite build` 输出 `✓ 2238 modules transformed` 与 `✓ built in 1.46s`。
- 同一副本里起 uvicorn（端口 18090，`DRA_DATABASE_URL` 指向一次性 SQLite，**没有链接模型**，所以 `/api/models` 为 503），在 Browser 窗格里：
  1. 页面加载：Data mode 选项为 `Live trained models` / `Prepared replay (legacy, test-only)`，选中 Live，说明为 Live 的那句；
  2. 选 replay → 存储里的模式变为 `PREPARED_SESSION_RUNTIME`，说明换成 legacy 文字；**重新加载 → 选择器回到 `LIVE_MODEL_RUNTIME`**（K4）；
  3. 点 Start Monitoring（摄像头被窗格屏蔽）：状态行 `Camera: error · failed to start at 23:48:30`（`CameraStatusLine`）；停止面板 `Monitoring stopped: The trained models are not available on the server`，`Category: models_unavailable (HTTP 503)`，`Failed during setup, before any request was sent`，**`Retry repeats the setup: the model check, then the session.`**；
  4. 点 New Session：同一类面板，但说明变成 **`Retry repeats the setup: the model check, then a NEW session.`**（K8，截图确认）。
  冒烟结束后停掉 uvicorn（18090 无监听）。主仓库的 `node_modules/.vite` 与 `node_modules/.vite-temp` 的修改时间在冒烟前后都是 `2026-10-15 13:13`，没有被触碰；没有启动 vite dev server。

## 6. PASS / FAIL / SKIP 计数

| 门禁 | 基线（`da9cdb0`） | 本项之后 | 变化原因 |
|---|---|---|---|
| pytest（真实树，模型经符号链接可用） | 704 passed | **704 passed / 0 failed / 0 skipped** | 无变化：后端零改动 |
| vitest | 594 passed（21 个文件） | **706 passed**（24 个文件） | +112，逐文件见下；新增 3 个测试文件，**无既有测试被删除或弱化** |
| `tsc --noEmit` | 0 错 | 0 错 | — |
| `eslint .` | 0 问题 | 0 问题 | — |

vitest 的 +112（每个文件的前后数由 JSON 报告核对，基线副本与最终副本各跑一次）：

| 文件 | 前 → 后 | 新增了什么 |
|---|---|---|
| `frontend/src/data/preparedRawTelemetry.test.ts`（新） | 0 → 35 | 25 行逐行 + 第 1 行字面量 / 缺失行 / 无概率键 / 与 replay 一致（4）+ 游标 2 + 范围守卫 4 |
| `frontend/src/components/runtimeNotices.test.ts`（新） | 0 → 26 | FaultPanel Retry 说明 4、advice 与计数行 3、结构 3、点击 4、摄像头 9、App 接线守卫 3 |
| `frontend/src/utils/export.test.ts` | 18 → 28 | +10（K9） |
| `frontend/src/api/retryPolicy.test.ts` | 36 → 45 | +9（`faultAdvice` 5、`retryNote` 4） |
| `frontend/src/utils/dataMode.test.ts`（新） | 0 → 7 | 标签 / 说明 5 + App 源码守卫 2 |
| `frontend/src/utils/persistence.test.ts` | 13 → 20 | +7（`loadConfig`） |
| `frontend/src/components/trendChart.test.ts` | 9 → 16 | +7（K5：参考平局 2 + 取整写法对照 1 + telemetry 1 + 非平局与端点 1 + 坐标无尘埃 1 + 自检 1） |
| `frontend/src/utils/alertOverlay.test.ts` | 3 → 9 | +6（replay 折叠 4 + 调用点源码守卫 2） |
| `ai/src/liveLoop.test.ts` | 53 → 58 | +5（K2 的 4 + K8 的 1） |

594 + 35 + 26 + 10 + 9 + 7 + 7 + 7 + 6 + 5 = 706。

## 7. 遗留问题

### 7.1 计划行号的漂移（对照基线 `da9cdb0` 逐处核实）

| 计划写的 | 当前实际（`da9cdb0`） |
|---|---|
| `App.tsx:37-39`（replay 相关 import / 常量） | replay 的 import 在 `:12-14`；`CAPTURE_MISS_TEXT` `:38`、`CAMERA_EVENT_TEXT` `:48`、`FaultPanel` `:59`（后三者现已搬出 `App.tsx`） |
| `App.tsx:50-69`（replay 调用点；Step 4 的 `:60-64` / `:66`） | `appendReplay` 在 `:136-153`，`applyAlertState` 在 `:148`；Step 4 描述的 spread 写法已不存在 |
| `App.tsx:191-210`（Data mode 选项） | `:281-300`（`aria-label="Data mode"` 在 `:283`，两个 `<option>` 在 `:294-297`） |
| `App.tsx:240-244`（说明文字） | `:329-333`（「Demo mode: …」在 `:332`） |
| `persistence.ts:90-94`（`loadConfig` 的模式恢复） | `loadConfig` 在 `:103`，模式恢复在 `:109-113` |
| `useLiveSession.ts:3`（import `PREPARED_SESSION_WINDOWS`） | `:11` |
| `useLiveSession.ts:145-149`（遥测游标） | `:54-57`（Task 8 之后该文件由 273 行缩到 173 行） |
| `useLiveSession.ts:108`（`startedAt.current` 只在新建会话时设置） | 现在是 `ai/src/liveLoop.ts:531` 的 `startedAt = deps.now()`（取值处在 `:342`） |
| `ai/src/riskLogic.ts:14`（`DEFAULT_CONFIG.operationMode`） | `:20` |
| Step 4「`PREPARED_SESSION_WINDOWS` 只被读 `.telemetry_features`」 | 现状：`useLiveSession.ts` 是读它的唯一 Live 文件；本项之后改读 `PREPARED_RAW_TELEMETRY` |
| K5 `trendSeries.ts`（brief 无行号） | `P × 100` 在 `:32` / `:36`，`formatFixed(numeric, 1)` 在 `:52` |

### 7.2 已知限制与需要知情的取舍

1. **K10 的真实点击没有被自动化证明。** 已证明：`FaultPanel` 的按钮 `onClick` 绑 `onRetry`、`retryHandler` 调 `live.retry()` 且不调 `start`、App 的接线（源码守卫）、停止面板在真实浏览器里能出现并显示正确文字（5.4）。**未证明**：在真实浏览器里点 Retry 后恢复监控；摄像头 `ended`（意外断开）与 `stopped_by_user` 事件显示——Browser 窗格屏蔽摄像头，冒烟只走到了 `start_failed`。这些留给 Task 10 的 Playwright（假摄像头 + 真点击）。
2. **K9 的四个新导出列只影响 replay 的前端导出**（`App.exportLog` 在 Live 模式下走 `live.exportSession`，下载的是后端 `/export`）。Live 导出的 JSON 本来就带完整 `provenance`（含 `vision_expired` / `vision_age_s` / `telemetry_expired` / `telemetry_age_s`），CSV 里 `provenance` 是 JSON 单元格——没有改后端，也没有给后端 CSV 增加独立的四列。若要在 Live 的 CSV 里也有独立的四列，是后端改动，超出本项范围。
3. **游标仍有 R10 的问题（K1，未改）**：`startedAt` 只在新建会话时设置，pause/resume 与重试之后游标仍会跳跃；`telemetry_timestamp` 仍是发送时刻，所以裁定 A 对 Live 遥测仍不真正生效；同一行遥测在 2 s 内被提交约 20 次（默认 10 fps）。K2 的测试把 tick 编号（`i × 500 ms`）与行号（`⌊i/4⌋ + 1`）的对应写成了字面量，R10 改规则时这些用例（以及 `preparedRawTelemetry.test.ts` 的游标用例）必须随之改写——它们会响亮地变红，不会空过。
4. **`FaultPanel` 的一个边角**：手动 Retry 时 reconcile（GET）本身失败，`retry()` 会保留旧的 `retryCount` / `manualRetries` 而换成 reconcile 的类别；若那个类别恰为 `model_runtime` 或 `timeout` 且 `manualRetries` 为 0，说明会写「请求已自动重发…」，而失败的其实是 reconcile。计数行与说明不矛盾（自动确实发了 3 次），只是措辞略泛；未处理。
5. **tooltip 之外的图表坐标**：`toPercentPoint` 把 vision / telemetry 序列点收敛到 0.1 %。对后端存的 3 位概率没有可见变化；对第一帧未取整的原始概率，坐标最多移动 0.05 个百分点，低于坐标轴可分辨的精度。
6. **`PREPARED_RAW_TELEMETRY` 与 replay 窗口同模块**（见 K6）：生产 bundle 里两者都有，守护的是 Live 代码不读它，不是 bundle 里没有它。
7. **仍使用旧选项名「Prepared replay demo」的文档**（不在本项的 Files 范围，未改）：`docs/LIVE_RUNTIME_GUIDE.zh.md:92`、`docs/FYP2_CLAUDE_DEVELOPMENT_HANDBOOK.zh.md:48`、`docs/IMPLEMENTATION_PROGRESS.zh.md:24`。控制者决定是否同步。
8. **预先存在的 prettier 偏差**：`frontend/src/data/preparedSessionInput.ts` 第 97–117 行的大数组（见 5.1），未处理。
9. **`prototype-tests/README.md` 的手动清单没有被我完整执行**：冒烟只跑了其中与本项相关的步骤（Data mode、setup 停止面板、New Session 的 Retry 说明）；第 3–8 步需要真实模型与摄像头，由 Task 10 的端到端与用户的 Week 7 验收承担。
10. **K3 的调用点守卫是源码守卫**：`App.tsx` 是带 hook 的组件，没法在 node 里运行；纯函数层（`applyAlertState`、`updateAlertState`）与 prepared 数据上的折叠有行为测试，调用点本身只有读源码的守卫。

## 8. 证据路径

- 本报告：`/Users/liu/Desktop/FYP2-Live-System/docs/fyp2/implementation/task-09.md`
- 实现：`frontend/src/data/preparedSessionInput.ts`、`frontend/src/hooks/useLiveSession.ts`、`frontend/src/utils/persistence.ts`、`frontend/src/utils/dataMode.ts`、`frontend/src/components/trendSeries.ts`、`frontend/src/api/retryPolicy.ts`、`frontend/src/utils/export.ts`、`frontend/src/components/RuntimeNotices.tsx`、`frontend/src/utils/runtimeNotices.ts`、`frontend/src/App.tsx`、`ai/src/liveLoop.ts`（仅注释）
- 测试：`frontend/src/data/preparedRawTelemetry.test.ts`、`frontend/src/components/runtimeNotices.test.ts`、`frontend/src/utils/dataMode.test.ts`、`frontend/src/utils/{alertOverlay,persistence,export}.test.ts`、`frontend/src/components/trendChart.test.ts`、`frontend/src/api/retryPolicy.test.ts`、`ai/src/liveLoop.test.ts`、`frontend/src/testing/markup.ts`
- 变异与冒烟产物（会话临时目录，不入库）：`/private/tmp/claude-501/-Users-liu-Desktop-FYP-In-Cabin-Driver-Assessment--1--claude-worktrees-exciting-keller-fdf913/43d73f6d-ed36-4f8a-b584-13c974ccd767/scratchpad/task9/`
  - `mut9.py`：一次一个变异，改隔离副本、跑整套 vitest（JSON 报告）、从真实树复原并 `filecmp`
  - `muts_main.py`、`muts_extra.py`、`muts_wiring.py`、`muts_mode.py`：58 个变异的定义（`muts_main.py` 里的 N11d 因格式化后模式不匹配被跳过，由 `muts_extra.py` 的 N11d 取代）
  - `final_mutations.txt`：对最终测试重跑全部变异的完整输出；`out_*.txt`：分批运行的输出
  - `base_counts.json` / `work_counts2.json`：基线与最终的逐文件 vitest 结果；`mut_<id>.json`：每个变异的 JSON 报告
  - `base_dir.txt` / `work_dir.txt` / `build_dir.txt`：三份隔离副本的路径；`smoke/`：冒烟用的一次性 SQLite 与 `uvicorn.log`
- Task 8 / P0-D13 的相关报告：`docs/fyp2/implementation/task-08.md`、`task-08-followup.md`、`p0-d13-ruling-a.md`

## 9. 下一项依赖

- **Task 10（端到端）**：
  - 可直接复用：停止面板（`role="alert"`、`aria-label="Monitoring stopped"`、`Retry` 按钮、`Category` / `Request id` / `Deliveries: n of 3`、setup 面板的 `Failed during setup…`）；延迟重试状态行（`role="status"`）；`Camera:` 状态行与摄像头原因提示的文字（`the camera was stopped` / `the camera was disconnected`）；手动清单 `prototype-tests/README.md`。
  - 必须在真实浏览器里补的：Retry 按钮真点击后恢复、摄像头 `ended` 与 `stopped_by_user` 的显示（见 7.2 第 1 条）。
  - `ST-BRANCH-T-CONTINUITY` 的预期值（现行游标）：一整轮 50 s；2 inferences/s 为 100 个 tick，默认 10 fps 为约 500 个；第 14 / 17 行共 8（2 fps）个 tick 带 `telemetry_source: "missing"` 且循环不停。**这依赖 R10 是否已改规则**，brief 应按届时生效的规则写。
  - 经 `PREPARED_RAW_TELEMETRY` 反查窗口与回放行的对应关系（`telemetry_features` 与表中某行逐值相等），而不是按时间推算。
- **R10（观察身份 / 遥测采集时间戳 / 游标语义）**：替换点只有 `preparedTelemetryAt` 一个函数与 `liveLoop.ts` 里 `telemetry_timestamp` 的取值；要同步改写的测试：`liveLoop.test.ts` 的 K2 一组（tick 与行号的对应）、`preparedRawTelemetry.test.ts` 的游标两条、变异 N3d 所对应的钉死规则。R10 落地后才应补「遥测过期」的端到端断言（P0-D13 报告第 9 节已提）。
- **阶段 5**：本项没有改任何与 0.45 stale 档或 D13 有关的东西。
- **控制者**：决定是否同步第 7.2 第 7 条所列的三份中文文档里的旧选项名；决定第 7.2 第 2 条（Live 的 CSV 是否要独立的四个过期列，需要后端改动）要不要排进 Task 10 或之后。
