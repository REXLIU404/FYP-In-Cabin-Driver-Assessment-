# Task 10 第 2a 部分验收报告（中文）：Live 端到端框架、ST-LIVE-E2E-01、停止面板真实点击、rVFC 实测

## 1. 任务概要

- **编号与名称**：Task 10 第 2a 部分。Task 10 第 2 部分拆成两半：2a 是端到端测试，2b 是单分支系统测试加 W4 证据归档。
- **实现了什么**：新文件 `backend/tests/test_live_e2e.py`，共 12 条测试，全部用真实浏览器、真实模型、真实后端跑完整链路。
  - **E1：ST-LIVE-E2E-01**，是 G-W4-A 的主测试，共 8 条。开始监测，收集至少 10 个窗口，然后检查：
    - **五方逐 ID 全行对账**：每个窗口在五处的全部 21 个字段逐字段相等，provenance 逐键比较，浮点数要求完全相等。五处是：
      1. 浏览器收到的 `/infer` 响应；
      2. 数据库行（payload 加类型列）；
      3. `GET /windows`；
      4. 导出 JSON；
      5. 导出 CSV。CSV 的比较规则写在测试的 docstring 里，没有跳过任何字段。
    - **IT-UI-01 oracle**：`GET /risk/latest` 等于最后一个窗口。Live Monitor 显示的数字从 DOM 读取，与 `/risk/latest` 按界面的显示格式核对。格式化用的是独立实现的四舍五入（ROUND_HALF_UP），不调用产品代码。
    - **契约**：
      - `LIVE_MODEL_RUNTIME`，`camera_frame` / `prepared_replay`；
      - vision 10 类，telemetry 3 类；
      - D01 不变式；
      - 冻结模型的哈希。
    - **R10 在线上的表现**：
      - 帧身份 `(epoch, index)`；
      - `telemetry_seq` 每 2 s 加 1，同一个 seq 的采集时间逐字节相同，相邻 seq 恰好相差 2000 ms；
      - provenance 中的规范采集时间是首次登记的那个；
      - 两个分支都同时出现 `new` 和 `repeat`；
      - REPEAT 沿用登记时的概率。
    - **flag**：在界面上标记一个窗口，五处都能看到；再取消标记，五处都恢复原样。
    - **五个视图**：都能打开，显示的数据与后端记录一致，控制台没有错误。
  - **E2：停止面板的真实点击**，共 3 条，由 Task 8 转入：
    - 连续 3 次传输失败后点 Retry：仍是同一个会话，这次投递带 `X-Attempt-Index: 4`，服务端只落库一次，循环恢复运行；
    - New Session 失败后点 Retry，会建立新会话；
    - 摄像头意外断开与主动 Stop Camera：两处文字都不同，循环都继续运行（R5）。
  - **E3：rVFC 实测**，1 条，是 R10-B 留下的。只记录，不设门槛。
- **为什么必要**：
  - 这是 G-W4-A 的主证据。
  - 计划 DoD 第 10 行要求逐 ID 全行对账，这里第一次在真实浏览器里证明它成立。
  - R8 中「Task 8 转入 Task 10」的三条断言，也是第一次用真实点击验证。

## 2. 实现证据

- **Commit**：
  - `47484d3`：2a 主体；
  - `afcdd0b`：控制者修正，见第 3 节。
- **文件**：
  - 新增 `backend/tests/test_live_e2e.py`、`backend/tests/e2e_support.py`、`backend/tests/e2e_server_main.py`；
  - 修改 `backend/tests/conftest.py`：加 `e2e` 标记，以及 `e2e_dist`、`e2e_server` 两个 fixture；
  - 控制者修正还改了 `test_model_gate.py`。
- **产品代码一行没改**。拦截请求、注入故障、合成 `ended` 事件、统计 rVFC 回调，全部在测试工具里完成：Playwright 的 route，加上注入页面的 init script。读取计时缓冲只用了 Task 10 第 1 部分已有的只读访问器 `window.__draLiveTimings`，没有新增钩子。
- **运行环境**（与计划 Step 2 一致）：
  - 只起一个 uvicorn，同时提供 `/api` 和 `dist/`，同源访问，不起 vite dev server；
  - 每次测试会话先跑一次 `npm run build`；
  - 数据库和 fault sink 都放在 tmp 目录。启动脚本会拒绝连接开发库；
  - 浏览器是 Chromium 148，带假摄像头。
- **证据目录**：`docs/evidence/2026-10-19/task-10-part2a/`，内容包括：
  - 实现者的门禁日志和 e2e 日志；
  - 变异记录 `mutations.txt`；
  - 三次 rVFC 实测的原始 JSON；
  - 控制者修正的验证记录 `controller-fixes.txt`。
- **关键决定**：
  - **E1 用 5 fps 的假摄像头**（`--use-fake-device-for-media-stream=fps=5`）。默认假摄像头是 20 fps，而循环约 10 Hz，永远比摄像头慢，所以视觉 REPEAT 一次也不会出现。实测 3 次共 181 个窗口，全是 `new`。brief 要求 `new` 和 `repeat` 都要出现，只能放慢摄像头。E2 和 E3 用默认摄像头。
  - **三个模型哈希**：brief 写的是「provenance 中三个模型」，这一句写错了。运行时只加载 ONNX 和 XGBoost，provenance 里也只有这两个哈希；`.pt` 检查点不加载。测试的做法是：
    - 每个窗口的两个 provenance 哈希与冻结值逐一比较；
    - `GET /api/models` 也比较；
    - `.pt` 按磁盘上的 SHA256 比较。

    这满足计划 DoD 的原文「三个模型 SHA256 与 Task 1 基线逐一相等」。控制者认可这个做法，以 DoD 原文为准。

## 3. 测试结果

| 门禁 | 结果（控制者在修正提交的内容上亲自复跑，`scripts/run_gates.py`，`DRA_REQUIRE_MODELS=1`） |
|---|---|
| build | 通过 |
| pytest | **934 passed / 0 failed / 0 skipped**（922 → 934，新增 12 条全部是 e2e；没有改动任何既有断言） |
| vitest | 870 passed，29 个文件（未改前端） |
| tsc / eslint | 0 / 0 |
| 模型 SHA256 | b3a42e8d / 196ca7b1 / 9802cb06，三个都未变 |

**耗时**：
- e2e 模块单独运行约 34 s（12 passed）；
- 全量 pytest 从约 22 s 增加到约 61 s。

**变异检验**：brief 要求的 E2E-M1 到 M8，实现者和评审都在隔离副本里跑过，每项都有明确变红的测试。评审在 M1、M3、M4、M7 上选了与实现者不同的变体：

| # | 变异 | 变红的测试 |
|---|---|---|
| M1 | 导出 JSON 漏掉 provenance 的一个身份字段（实现者删 `vision_frame_id`，评审删 `telemetry_seq`） | test_04、test_07 |
| M2 | `/risk/latest` 返回倒数第二个窗口 | test_04、test_05、test_07 |
| M3 | 「最新」面板的 RiskScore 加 0.1（评审只改 UI 层，格式化函数不动） | 只有 test_05，说明 IT-UI-01 oracle 单独就能抓到 |
| M4 | Retry 新建会话 | E2 传输故障测试：「Retry created a new session instead of resuming this one」 |
| M5 | Retry 的投递序号从 1 重新开始 | 同上：`X-Attempt-Index` 断言为 '1' ≠ '4' |
| M6 | 设备断开与主动停止显示相同文字 | E2 摄像头测试 |
| M7 | 遥测采集时间改回发送时刻 | 全部 12 条：服务端回 409 `observation_conflict`，监测停止 |
| M8 | flag 不写进导出（评审把 JSON 和 CSV 分开测） | test_07 |

评审另外加了 4 项变异，也全部变红：
- M3b：只改仪表盘中心数字；
- M6b：只把提示文字改成相同；
- M8b：只改 CSV；
- X5：New Session 失败后 Retry 不建新会话。

**无模型副本**：12 条显式跳过，并打印 MODEL-DEPENDENT 提示；`DRA_REQUIRE_MODELS=1` 时变成 12 个错误。

**控制者修正**（`afcdd0b`）：评审的 7 条 Minor 中，3 条由控制者修了。每条都在修正前的隔离副本里复现了失败，记录在 `controller-fixes.txt`：

| # | 问题 | 修正前 | 修正后 |
|---|---|---|---|
| F1 | test_07 标记窗口后不恢复，这组测试依赖定义顺序 | 按 07、06、05、04 的顺序运行：2 条失败 | test_07 结尾通过界面取消标记，并重新核对五方。倒序运行 7 条全部通过 |
| F2 | e2e 的 uvicorn 子进程继承开发者 shell 里的 `DRA_*` 变量 | `DRA_MODEL_ROOT=/nonexistent` 时 test_01 失败 | 过滤掉所有 `DRA_*`，同样条件下通过 |
| F3 | 跳过条件只检查 ONNX 文件，缺 `.pt` 时报 `FileNotFoundError` | 缺 `.pt` 时 test_02 报错 | 三个文件都检查：12 条显式跳过，`DRA_REQUIRE_MODELS=1` 时判失败。`test_model_gate` 也要求 e2e 文件带这个标记 |

更正评审的一个例子：评审说 `DRA_FRESHNESS_TOLERANCE_S=1` 会让测试失败，实测并不会。原因是有效期阈值取自前端建会话时传入的会话配置，不读服务端的默认值。F2 改用 `DRA_MODEL_ROOT` 证明，结论不变。

**E3 实测**（Chromium 148，假摄像头，3 次，只记录）：

| 项 | 结果 |
|---|---|
| 采集用的 `<video>` 挂在 DOM 上时的回调 | 约 20 Hz，121 次回调全部在挂载的 video 上 |
| `captureTime` | 100% 存在，所以请求里的 `captured_at_source` 全是 `capture_time` |
| 每次回调耗时 | 中位 2.0–3.4 ms：drawImage 0.5–0.9 ms，toDataURL 1.5–2.4 ms |
| 循环计时缓冲 | 从截帧到发送的中位约 0 ms；网络加服务端中位约 28 ms；渲染中位约 4 ms |
| 视觉观测 | 默认摄像头下 60 个窗口全是 `new` |

与 R10-B 报告不同的地方：R10-B 用的是合成画布流，没有 `captureTime`，所以当时是 `callback`。两边一致的地方：挂载后回调能触发。R10-B 报告的「不挂载时 0 次回调」，这次没有复测。

**存在但未执行的测试**：无。

## 4. 问题与风险

- **失败测试**：无。**非预期回归**：无。**产品缺陷**：本项没有发现。
- **转入 2b 的一项**：E1 只在 5 fps 下做了五方对账。默认摄像头下全是 `new`，这种情形只有 E3 在线上记录过，没有对账。2b 要在默认摄像头上补做一次五方对账。
- **已知的脆弱点，接受并记录**：
  - **两个墙钟容差**：遥测平均间隔要在 [1.8, 2.3] s 之内（实测 2.03 s），每个窗口的年龄要小于 3 s。机器负载很高时，这两条可能先于真实缺陷失败。实现者加评审一共跑了 14 次以上，包括 12 个繁忙进程同时运行的情况，都通过了。没有放宽，因为放宽会削弱「每 2 s 一个 seq」和「无过期证据」这两条断言。
  - **依赖 CSS 类名**：读取 DOM 靠 `.session-strip`、`.risk-gauge` 等类名。产品代码不能改，所以没有 `data-testid`。改界面时要同步更新 `e2e_support.py`。
  - **e2e 的运行依赖**：需要 npm 和 Playwright Chromium，缺少时是硬失败，不是跳过。缺模型时是显式跳过。
- **值得在报告和答辩里说明的两个现象**（都符合设计，没有加断言）：
  - **手动 Retry 的窗口为 UNAVAILABLE**：自动重试经过 2 s 和 4 s 两次退避，之后再手动 Retry 时，这个窗口落库为 UNAVAILABLE，两个分支都过期（年龄约 6.26 s）。原因是冻结 payload 带的是原始采集时间，按裁定 A 过期就当缺失。这正是裁定 A 要的行为：迟到的证据不能当新的用。
  - **CAUTION 与 Low 并存**：RiskLevel 已经是 Low，AlertSeverity 仍可能是 CAUTION。这是 FSM 的 10 s 恢复规则。
- **测的是假摄像头，不是真实摄像头**：真实摄像头上 `captureTime` 是否存在、帧率多少、截帧开销多大，都还没测。假摄像头的画面是简单图案，JPEG 约 10 KB，真实人脸画面会更贵。这些留给 PERF-01。
- **外观问题**：`47484d3` 的提交信息里多了一行 Sonnet 署名，与以前的提交情况相同；最后一行仍是规定的 Opus 行。

## 5. 验收结论

**PASS**

理由：
- E1、E2、E3 全部落实。
- 8 项 brief 变异和 4 项附加变异，在隔离副本里全部变红。
- 评审的 7 条 Minor 中，3 条由控制者修正，并用修正前的副本复现了失败；1 条转入 2b；其余 3 条接受并记录。
- 控制者亲自复跑五道门禁，全部通过，0 跳过。

**G-W4-A 的主测试 ST-LIVE-E2E-01 已经通过。** W4 证据要等 2b 一起归档。

## 6. 下一任务就绪度

- **可以开始 Task 10 第 2b 部分**：
  - 单分支系统测试 ST-BRANCH-T-SMOKE、T-CONTINUITY、V、ZERO，按计划 Step 2A 做，告警序列按 R10 规则断言：算术时间戳下，第 2 个连续 High 样本告警；
  - ST-BRANCH-V 拦截掉遥测时，必须同时去掉 `telemetry_seq`，否则会触发 422；
  - P_t 的 fixture 绑定 XGBoost 的哈希 `9802cb06`；
  - 在默认摄像头上补做一次五方对账（由 2a 转入）；
  - 用 `run_gates.py`，在 `DRA_REQUIRE_MODELS=1` 下归档 G-W4-A 证据到 `docs/evidence/<日期>/live-e2e/`。
- **之后**：W5 的会话生命周期、冷启动（包括把 `.venv` 符号链接换成本地环境）、导出完善，以及 Task 10A。
