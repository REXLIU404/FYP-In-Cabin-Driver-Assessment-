# Task 10 第 2b 部分 实现报告 —— 单分支系统测试 ST-BRANCH-*、默认摄像头五方对账、G-W4-A 证据归档

## 1. 任务编号与名称

- **TASK-10-PART2B**（第二次派发，接续第一次中断留下的草稿）：计划 Task 10 Step 2A 的四个单分支系统测试（`ST-BRANCH-T-SMOKE` / `-T-CONTINUITY` / `-V` / `-ZERO`）；由 2a 转入的「默认 20 fps 摄像头下的五方对账」；Step 4 的 G-W4-A 证据归档；计划 Task 10 Files 里的 `prototype-tests/live_e2e.md`；DoD 第 10 行的 R5 追加部分。
- 工作树 `/Users/liu/Desktop/FYP2-Live-System`，分支 `fyp2/live-system`，基线 HEAD `b7d68dd`（开工前核实：分支与 HEAD 吻合；工作树里只有上一次派发留下的未提交草稿，没有别人写过分支）。
- 基线门禁（brief）：pytest 934 / vitest 870 / tsc 0 / eslint 0。
- **产品代码零改动**：已跟踪文件的改动只有三个测试侧文件（`conftest.py`、`e2e_support.py`、`test_live_e2e.py`）；新增文件全部在 `backend/tests/`、`prototype-tests/`、`docs/`。没有碰模型文件、`docs/fyp2/review/`、计划文件、开发库、主仓库。没有派发子 agent；除本任务要求的 `git add` / `git commit` 外没有执行任何被禁的 git 操作。
- 交付两个本地提交：**提交一** = 测试 + 冻结 fixture + 生成脚本 + `live_e2e.md` + 本报告；**提交二** = `docs/evidence/2026-10-20/live-e2e/` + 本报告末尾追加的「附：G-W4-A 归档结果」（归档必须在已提交的代码上运行，所以它的结果无法写进提交一里的报告）。

## 2. 实现状态

**DONE。** 草稿经过通读、逐条对照 brief、运行与变异验证后保留，改动很小（见 4.6）。没有发现产品缺陷，没有因此停下；独立推导的告警序列与控制者给出的表**完全一致**（第 7 节第 1 条）。

| 交付 | 状态 | 守护 |
|---|---|---|
| ST-BRANCH-T-SMOKE（`TestStBranchTSmoke`，3 个测试） | 完成 | B-M1、B-M2、B-M9 变红；X-M1（fixture 哈希被改）变红 |
| ST-BRANCH-T-CONTINUITY（`TestStBranchTContinuity`，5 个测试，约 56 s 的一整轮加回绕） | 完成 | B-M3、B-M3b、B-M4、B-M5、B-M9 变红 |
| ST-BRANCH-V（`TestStBranchV`，5 个测试） | 完成 | B-M6、B-M7 变红 |
| ST-BRANCH-ZERO（`TestStBranchZero`，4 个测试） | 完成 | B-M8 变红 |
| 默认摄像头五方对账（E3 末尾追加） | 完成 | B-M10 变红 |
| 冻结 fixture + 生成脚本 | 完成 | 与模型 `9802cb06…` 绑定；`--check --cross-check-provider` 通过 |
| `prototype-tests/live_e2e.md` | 完成 | — |
| G-W4-A 证据归档 | 见提交二与末尾附录 | — |

需要先知道的三点：

1. **新增测试是 17 条，不是 brief 里说的 18 条**（3 + 5 + 5 + 4）。E3 是改了原有测试（加对账），没有新增。pytest 934 → 951 全部来自这 17 条。
2. **B-M3 的字面写法（不可用窗口输出上一次的 severity）确实让 T-CONTINUITY 变红，但不是经过 AlertSeverity 的断言**：产品的 `RiskUpdate` 校验器（D01）先拒绝这条记录，服务端回 HTTP 500，循环按 R8 在三次重发后停止，T-CONTINUITY 在等待里带着停止面板文字失败。为了让变异碰到告警断言本身，我另做了同类变异 **B-M3b**（不可用窗口把 `None` 写回 `last_severity`，锁存丢失），它只让 `test_04_alert_severity_follows_the_r10_rule` 变红（第 6.3 节）。
3. **e2e 让全量 pytest 从 54–61 s 变成 134 s**（第 6.1 节）。

## 3. 创建 / 修改的文件

| 文件 | 变化 |
|---|---|
| `backend/tests/test_live_single_branch.py`（新，约 830 行） | 四个测试类共 17 条；`Frozen`（冻结表的读取、哈希校验、按特征反查回放行）、`common_problems` / `row_problems` / `assert_clean_run` / `common_and_reconciliation`、`ALERT_BY_SEQ`（字面量）、`vision_only`（V 的请求改写）、`ema_problems`（NEW-only EMA 的期望链） |
| `backend/tests/fixtures/telemetry_pt_by_row.json`（新） | 25 行回放中每行的 `P_telemetry_anomaly` 与三类概率；第 13、16 行为 null；记录模型与回放 CSV 的 SHA-256 |
| `backend/tests/fixtures/make_telemetry_pt_fixture.py`（新） | 单独的生成脚本，只读模型文件与回放 CSV；`--check` 比对已提交文件与重新计算；`--cross-check-provider` 证明与产品 `TrainedProvider` 逐位相等 |
| `backend/tests/e2e_support.py` | 挪入 `LiveRun`、`Parties`、`parties_diffs`、`frame_key`（原样）；新增 `assert_reconciled`、`assert_ui_shows_latest`、`evidence_dir`（`DRA_E2E_EVIDENCE_DIR`）、`half_up_float`；`ApiTap.rewrite_infer` 与 `InferCall.sent_raw / sent_body`（V 的改写）、`ApiTap.answered_with_image`；`Chrome(permissions=…)` 参数；`expected_latest_panel` 增加「无评估」分支 |
| `backend/tests/test_live_e2e.py` | 辅助代码移走并改为 import；E3 末尾追加五方对账与 IT-UI-01；五个视图截图与导出落盘的钩子（`DRA_E2E_EVIDENCE_DIR` 未设置时什么都不写） |
| `backend/tests/conftest.py` | 只加 `pw` fixture（模块级 Playwright，原先在 `test_live_e2e.py` 里）与文件头注释 |
| `prototype-tests/live_e2e.md`（新） | `prototype-tests/README.md` 的 Live 人工验收步骤逐条对应到自动化测试，并写明仍需人工的部分 |
| `docs/evidence/2026-10-20/live-e2e/`（提交二） | 第 8 节 |
| `docs/fyp2/implementation/task-10-part2b.md` | 本报告 |

## 4. 实现摘要

### 4.1 共同机制

- 所有四个测试都在 2a 的框架上跑：一个 uvicorn 同时挂 `/api` 与新构建的 `dist/`，Chromium 假摄像头，`ApiTap` 记录每个 `/infer` 的请求与应答。每个测试类一次监测运行，类内多个测试共享，运行出错写入 `run.error` 由第一个测试报告。
- **让服务端静止再读**（`LiveRun.settle`，2a 的技巧原样复用）：设 `hold_infer`，等到下一个请求被挂住（说明上一个已应答），读界面「最新」面板，再点 Pause。之后所有对账面对静止的服务端。
- **五方对账 + 最新窗口**（`assert_reconciled` / `assert_ui_shows_latest`，四个新测试和 E3 共用）：对**每个**窗口，`/infer` 应答 = 数据库行（payload 与全部类型列）= `GET /windows` = JSON 导出 = CSV 导出，21 个契约字段逐一相等、`provenance` 逐键、浮点精确；窗口集合在各处都是 1..N，`total_windows == N`，导出顶层恰为 `{session_id, records}`；`GET /risk/latest` 整条等于最后一个窗口；界面「最新」面板等于 `/risk/latest`。`expected_latest_panel` 现在也会写出「无评估」窗口应有的面板（横幅文字固定、只有 SystemHealth 徽章、没有仪表盘和三个徽章），ZERO 的最后一个窗口是不可用的，所以这条路径在浏览器里真实验证过。
- **共同断言**（`common_problems`）：`DominantEvidence == ("Partial evidence" if assessment_available else None)`；可用的单分支窗口四个风险字段非空且 `SystemHealth = DEGRADED`；不可用窗口四个风险字段为 null、`SystemHealth = UNAVAILABLE`；D01：`assessment_available == (RiskScore is not None) == (SystemHealth != "UNAVAILABLE")`。范围：T-SMOKE、ZERO 在 Stop Camera 之前的双分支窗口不参与这些断言（只参与对账）；V 的所有窗口都是单分支或不可用。
- **窗口与回放行的对应**（`Frozen.row_of` + `row_problems`）：用记录里的 `telemetry_features`（八个特征的 float 元组）在冻结表里反查行号，不按时间推算，再与 `telemetry_seq % 25` 交叉核对，两者必须相等；第 13、16 行的窗口必须没有特征。
- **无故障**（`assert_clean_run`）：停止面板从未出现（`wait_until` 在等待期间一出现就失败并带面板文字，结尾再数一次）、该会话 `fault_events` 为 0、没有控制台错误和页面异常、所有 `X-Attempt-Index` 都是 `1`（没有重发）、除那一个被挂住的请求外全部 201、只创建一个会话、`window_id` 为 1..N、`request_id` 不重复。

### 4.2 冻结 fixture（brief 第 1 条）

- `telemetry_pt_by_row.json` 由独立脚本 `make_telemetry_pt_fixture.py` 产出：直接读 `xgb_telemetry.json` 与回放 CSV，按 `trained.py` 的方式跑 booster（八个特征按模型自己的顺序转 float32、`iteration_range=(0, best_iteration + 1)`、`P = float(1 - probs[0])`），**不 import 产品 provider**；`--cross-check-provider` 单独导入一次产品 provider，证明 23 个有遥测的行逐位相等。我实际运行了 `--check --cross-check-provider`：`identical on all 23 telemetry rows` 与 `equals a fresh computation (model 9802cb06)`，退出码 0。
- 测试（`Frozen.verify()`）先核对 fixture 记录的模型哈希等于磁盘上 `xgb_telemetry.json` 的 SHA-256，再核对它等于测试里的字面量 `9802cb06ca98…`，再核对回放 CSV 的哈希，最后核对行号 0..24 与 null 行恰为 13、16。不符时的失败信息写明「fixture 与模型不匹配」。X-M1 把 fixture 记录的哈希末位改成 `7`，T-SMOKE 的 `test_02` 与 `test_03` 变红，信息是 `the frozen fixture does not match the model: … 9802cb07, the file on disk is 9802cb06`。
- 测试里期望值全是字面量或来自 fixture；唯一在运行时算出来的是十进制 half-up 舍入，用 2a 的独立实现 `half_up`（`Decimal(repr(x))`），不调用产品代码、模拟器或模型。

### 4.3 ST-BRANCH-T-SMOKE（3 条）

默认 20 fps 假摄像头，开始监测，等到 ≥ 3 个带图像的窗口，点 **Stop Camera**，再等 ≥ 5 个不带图像的窗口且遥测序号覆盖 4 个不同位置（实测落在行 0、1、2、3，即 Low 和 High 两种都有）。

- `test_01`：停止前的窗口是 `{fresh, fresh}` / `FULL`；状态行 `Camera: idle · stopped by you at …`；无故障。
- `test_02`（核心）：对每个不带图像的窗口——`modality_freshness == {vision: missing, telemetry: fresh}`、`SystemHealth = DEGRADED`、`vision_source = missing`、`telemetry_source = prepared_replay`；`P_telemetry_anomaly` 与冻结表该行**完全相等**；三类概率与冻结表相等；`RiskScore == round_half_up(100 × P, 1)`（用记录里未取整的 P）、`RiskLevel` 按取整后的分数与 30 / 60 映射；`P_distraction == 0.0`、视觉类别为空；覆盖到 Low 与 High 两种等级。
- `test_03`：全部窗口的回放行对应；共同断言；五方对账、`/risk/latest`、界面「最新」面板；无故障。

### 4.4 ST-BRANCH-T-CONTINUITY（5 条，约 56 s）

- **视觉从一开始就没有——用「摄像头本身不可用」实现，没有拦截 `/infer`**。Chromium 不带假设备参数、上下文不授予摄像头权限，`getUserMedia` 被拒。`App.start()` 先 `await camera.start()`（它捕获错误，不抛）再启动循环，所以循环照常运行、只发遥测——这是产品自己的降级路径，也是用户拒绝摄像头授权时真实发生的事（R5）。实测：第一次草稿运行时断言 `Camera: error · failed to start at …` 通过，说明浏览器抛的是无设备类错误（状态词 `error`）；产品对 `NotAllowedError` 会显示 `denied`，所以我把正则放宽为 `(error|denied)`——这个测试关心的是「failed to start」。**不需要退到拦截方案**：循环没有停，没有产品行为发现。
- **运行长度**：等到 `telemetry_seq ≥ 27`（第 26 位完整，即一整轮 25 行加回绕后的第 2 圈第 2 行），实测 535 个窗口、约 9.6 Hz、56 s；每个位置约 20 个窗口。
- `test_01`：循环没停；整个运行里没有任何请求带过 `image_base64`、`captured_at`、`vision_frame`、`captured_at_source`；状态行是 `failed to start`；无故障（`X-Attempt-Index` 全为 1、窗口 id 连续、无停止面板）。
- `test_02`（位置与回放行）：把每个窗口放到它的遥测游标位置（有 `telemetry_seq` 的请求用它；第 13、16 行按合同没有 `telemetry_seq`，位置由前一个有 seq 的请求推出，并被「恰好是 `seq % 25` 属于空行的那些位置」这个断言验证）。位置单调、不跳号、每个位置都出现；空行恰好没有特征、没有 seq、没有时间戳、`telemetry_source = missing`；反查行号与 `seq % 25` 一致（含回绕）；**告警序列的前提**：同一 seq 的 `telemetry_timestamp` 逐字节相同，相邻 seq 恰好相差 2000 ms（跨空行 4000 ms）；服务端判定 `telemetry_obs == "new"` 的窗口恰为每个有遥测的位置一次。
- `test_03`：每个有遥测的位置，`{missing, fresh}` / `DEGRADED`、来源、`P_t` 等于冻结表、`RiskScore` / `RiskLevel`；第 13、16 位的窗口两路都 `missing`、`UNAVAILABLE`、四字段 null；下一个位置（14、15、17、18）恢复为 `DEGRADED`。
- `test_04`（告警序列，字面量 `ALERT_BY_SEQ`）：见第 7 节。docstring 写明这是 R10 规则、依赖算术采集时间、来源时间抖动时告警可能延迟一个样本（K2），本测试只在算术时间下成立，前提由 `test_02` 断言。
- `test_05`：共同断言（含 Partial / null）、五方对账、界面最新面板、无故障，覆盖**全部** 535 个窗口。

### 4.5 ST-BRANCH-V（5 条）与 ST-BRANCH-ZERO（4 条）

**V**：5 fps 假摄像头（`SLOW_FAKE_CAMERA_ARGS`）让 10 Hz 的循环追过相机，出现 REPEAT。`ApiTap.rewrite_infer = vision_only`（Playwright 路由）把每个请求体改成：`telemetry_features = null`、`telemetry_timestamp = null`、`telemetry_source = "missing"`，**同时删除 `telemetry_seq`**（否则违反 R10 的 422 规则，前端收到 422 会停止循环）。改写是请求体的纯函数、用固定的分隔符序列化，同一个请求重发得到逐字节相同的结果；`InferCall.raw / body` 仍是浏览器自己的体，`sent_raw / sent_body` 是服务端收到的。运行：等到 6 个 NEW 与 6 个 REPEAT → **Stop Camera** → 等 6 个不带图像的窗口 → **Start Camera** → 再等 6 个 NEW 与 6 个 REPEAT → 静止。

- `test_01`：服务端看到的确实是纯视觉（并且浏览器确实发过遥测，改写不是空操作）；改写字节等于 `vision_only(浏览器的体)`；`vision_only` 对同一输入两次输出逐字节相同，且不修改它的输入；无故障。
- `test_02`：带图像的窗口 `{fresh, missing}` / `DEGRADED`、`camera_frame` / `missing`、`RiskScore == round_half_up(100 × P_distraction, 1)`、`RiskLevel`；`P_telemetry_anomaly == 0.0`，遥测字段为空。
- `test_03`（EMA 链，NEW-only，R10）：见 **4.5.1**。实测 25 个带图窗口里 NEW 13、REPEAT 12，播种帧在第 1 个窗口和第 24 个窗口（Start Camera 之后的第一个 NEW）。
- `test_04`：不带图像的窗口（Stop Camera 期间、Start Camera 之后相机尚无画面的那几个）全部 `assessment_available = false`、`UNAVAILABLE`、四字段 null、两路 `missing`、两个来源 `missing`。
- `test_05`：共同断言、五方对账、界面最新面板、无故障。不断言具体数值（假摄像头每帧画面不同）。

**4.5.1 EMA 重新播种的条件（读 `inference.run_inference` 后写进 `ema_problems` 的 docstring）**：LIVE 模式下

1. NEW 观测在链不存在时是**播种**：`P_distraction == provenance.P_distraction_raw`（全精度）；链存在时 `P_distraction == round_half_up(α × raw + (1 − α) × 链上一个 NEW 的 P_distraction, 3)`，链随后等于这个值；
2. REPEAT 显示它所重复的观测登记时的值（`P_distraction` 与 `P_distraction_raw` 都是），既不读也不推进链，也不会把已断开的链重新接上；
3. 链在以下情形之后断开（下一个 NEW 重新播种）：任一窗口视觉分支不是 fresh（缺失或过期）、或该窗口没有评估（`level is None`）、或两个相邻窗口的处理间隔超过 `freshness_tolerance_s`（此时 `TEMPORAL_STATE_KEYS` 被清空，含 `previous_vision`）。

断言：本次运行里 NEW 与 REPEAT 都出现 ≥ 12 次，至少两次播种（首帧与 Start Camera 之后的首个 NEW），后者的 `P_distraction == raw` 逐位相等，其间有 ≥ 6 个不带图像的窗口，其后的 NEW 不是每个都等于自己的 raw（链确实在平滑）。

**ZERO**：在 Configuration 视图把 Vision Weight 滑块填成 1（Telemetry 自动变 0.00，页面显示 `Vision Weight: 1.00` / `Telemetry Weight: 0.00`），回 Live Monitor，开始监测，≥ 3 个带图像的窗口后 **Stop Camera**，再等 ≥ 5 个不带图像且覆盖 4 个遥测位置的窗口。

- `test_01`：所有窗口的 `provenance.fusion_config` 为 `weight_vision = 1`、`weight_telemetry = 0`。
- `test_02`：停止之后每个窗口 `assessment_available = false`、`UNAVAILABLE`、四个风险字段全是 null、`RiskScore` 不等于 `round_half_up(100 × P_t, 1)`；同时遥测分支本身完好（`telemetry: fresh`、`P_t` 等于冻结表的该行）——所以没有分数是因为零有效权重，而不是遥测坏了；并要求这些窗口里至少一个的 `100 × P_t ≥ 60`，使得泄漏的 `100 × P_t` 一定看得见。
- `test_03`：停止之前带图像的窗口可用，`RiskScore == round_half_up(100 × P_distraction, 1)`。**依据代码**：`map_system_health` 只看新鲜度、「never at the weights」，所以这些窗口是 `FULL`；分数是 `(1.0·P_d + 0.0·P_t) / 1.0`。它们的 `DominantEvidence` 我**没有断言**：决策树比较的是两路原始概率、不看权重，所以对零权重的遥测路可以写出 `Telemetry-dominant`（本次实测为 `Low observed risk`）。这是已知的 R14，不是本部分要改的东西。
- `test_04`：共同断言（范围是停止之后的窗口）、五方对账、界面最新面板（最后一个窗口是不可用的）、无故障。

### 4.6 对草稿的处理

通读草稿的 17 条测试、`e2e_support.py` 与 `test_live_e2e.py` 的 diff、fixture 脚本与 `live_e2e.md`，逐条对照 brief，没有发现需要重写的地方。我做的改动：

1. T-CONTINUITY 的状态行正则 `error` → `(error|denied)`（原因见 4.4）；
2. T-CONTINUITY 类 docstring：写清 seq 2 可以**没有**任何 `CAUTION` 窗口（实测正是如此），补上手算的推导摘要；
3. V `test_01`：增加 `vision_only` 的纯度断言（同输入两次同字节、不改输入）；
4. `live_e2e.md`：状态词、耗时数字改为实测值；
5. 没有改动任何 2a 断言（见下）。

**对 2a 的改动逐条（含义都没有变）**：(a) `LiveRun` / `Parties` / `parties_diffs` / `frame_key` 原样挪到 `e2e_support.py`（diff 核对过，代码逐字相同，`Parties` 多存了两个未使用的字节属性）；(b) `LiveRun.collect` 拆成 `collect` + `settle`，等待与读取的顺序和内容不变；唯一的行为差别是运行中抛出**非** `AssertionError` 的异常（例如 Playwright 超时）时，原来是 fixture 错误，现在写入 `run.error` 由第一个测试报告——只改变失败的呈现方式；(c) `pw` fixture 挪到 `conftest.py`（模块作用域不变）；(d) E1 的 `test_06` 增加截图与导出落盘，E3 增加 rVFC JSON 落盘，都只在 `DRA_E2E_EVIDENCE_DIR` 设置时发生；(e) E3 末尾追加五方对账，原有断言一字未动。2a 的 12 条在三个环境下都通过：工作树（41.97 s）、隔离副本基线 M0（与新文件一起，29 passed）、全量 pytest。

### 4.7 默认摄像头五方对账（brief 第 5 条）

E3（默认 20 fps，所有视觉观测都是 `new`）在测量之后：`LiveRun(chrome)` → `settle()`（Pause 让服务端静止）→ `assert_reconciled`（对它收到的全部窗口五方对账 + `/risk/latest`）→ `assert_ui_shows_latest`。B-M10（CSV 漏掉 `request_id` 列）单独跑 E3 变红：`60 differences, first ["window 1: csv request_id: cell '' for value '315af837-…'", …]`。

### 4.8 G-W4-A 证据归档（提交二）

按 brief 的顺序，在已提交的代码上：`DRA_REQUIRE_MODELS=1 python3 scripts/run_gates.py --out docs/evidence/2026-10-20/live-e2e`；同目录 `freeze_manifest.txt`；一次 E1 运行（`DRA_E2E_EVIDENCE_DIR`）留下的五个视图截图、该会话的 JSON / CSV 导出、E3 的 rVFC 实测 JSON；`mutations.txt`；`README.md`（把 G-W4-A 每一项对应到具体测试与验收报告，每个 ID 都用 `grep` 核实过存在）。结果见末尾「附：G-W4-A 归档结果」。

## 5. 执行的测试（精确命令）

门禁（`phase2-context.md` 的精确命令，真实工作树，提交前）：

```
cd /Users/liu/Desktop/FYP2-Live-System
export PYTHONDONTWRITEBYTECODE=1
(cd backend && TMPDIR=$(mktemp -d) PYTHONPATH=. ../.venv/bin/python -m pytest tests -q -p no:cacheprovider)
./node_modules/.bin/vitest run --no-cache
./node_modules/.bin/tsc --noEmit
./node_modules/.bin/eslint .
```

新测试单独运行（草稿首次运行、核对耗时与打印）：

```
(cd backend && TMPDIR=$(mktemp -d) PYTHONPATH=. ../.venv/bin/python -m pytest tests/test_live_single_branch.py -v -s --durations=0 -p no:cacheprovider)
(cd backend && ... pytest tests/test_live_e2e.py -v -s --durations=0 -p no:cacheprovider)
(cd backend && ... pytest tests -m e2e --collect-only -q)        # 29 / 951 collected, 922 deselected
(cd backend && ... pytest tests -m "not e2e" --collect-only -q)  # 922 / 951 collected
.venv/bin/python -I backend/tests/fixtures/make_telemetry_pt_fixture.py --check --cross-check-provider
```

变异（隔离副本；命令与 `phase2-context.md` 一致，另按 2a 的做法接入模型与 `node_modules`）：

```
D=$(mktemp -d) && git -C /Users/liu/Desktop/FYP2-Live-System archive HEAD | tar -x -C "$D" \
  && ln -s /Users/liu/Desktop/FYP2-Live-System/.venv "$D/.venv" \
  && ln -s /Users/liu/Desktop/FYP2-Live-System/node_modules "$D/node_modules"      # 工作树自己的 node_modules，不是主仓库的
# 三个模型文件以只读符号链接接入 $D/ml/outputs/{vision,telemetry}/；把本项六个测试侧文件从工作树拷入 $D/backend/tests/（fixtures 在 fixtures/ 下）
# 每个变异：在 $D 里对源文件做一次精确字符串替换（匹配次数必须恰为 1）→ 在 $D/backend 里 pytest <文件> -v -rf -p no:cacheprovider → 用 git show HEAD:<path> 还原 → 逐字节比对
```

两个副本并行各跑一条队列（同时最多两个 e2e 会话）；每条变异跑整个新测试文件（17 条），B-M10 跑 `test_live_e2e.py`（并单独 `-k test_e3`）。基线 M0 先在**未变异**的副本里跑两个 e2e 文件。真实工作树从未被变异。

## 6. PASS / FAIL / SKIP 计数

### 6.1 门禁

| 门禁 | 基线 | 之后 | 变化的解释 |
|---|---|---|---|
| pytest | 934 passed | **951 passed / 0 failed / 0 skipped**（133.76 s） | +17，全部是新增：T-SMOKE 3 + T-CONTINUITY 5 + V 5 + ZERO 4。没有替换、删除或改动既有测试的断言；E3 是在原测试末尾追加断言，不改计数。其中 e2e 标记 29 条（12 + 17），非 e2e 922 条（与 2a 之前一致） |
| vitest | 870 passed（29 个文件） | 870 passed（29 个文件） | 无变化：没有改任何 TS/TSX |
| tsc | 0 | 0 | — |
| eslint | 0 | 0 | — |
| build | — | e2e 的会话级 fixture 每次先 `npm run build`，三次全量/多次单独运行都成功；提交二里 `run_gates.py` 的 build 门禁另有独立日志 | — |

门禁之后 `git status --short` 只有本项文件：`dist/`、`tsconfig.tsbuildinfo` 被 git 忽略；`DRA_E2E_EVIDENCE_DIR` 未设置时测试不向仓库写任何东西。主仓库的 `.venv` 与 `ml/outputs/` 在本次会话期间没有任何文件被修改（`find -newermt` 核对过）。

**耗时**：新文件 17 条单独运行 85.61 s（草稿首次运行；类 fixture：T-CONTINUITY 55.6 s、T-SMOKE 15.8 s、ZERO 7.4 s、V 5.0 s）；`test_live_e2e.py` 12 条 41.97 s（2a 时 34–38 s，多出的是 E3 末尾的 settle 与对账）；**全量 pytest 133.76 s，2a 时是 53.7–60.8 s（934 条），W3 门禁（无 e2e）是 23.65 s**。

### 6.2 17 条新测试（全部 PASS）

`TestStBranchTSmoke::test_01…test_03`、`TestStBranchTContinuity::test_01…test_05`、`TestStBranchV::test_01…test_05`、`TestStBranchZero::test_01…test_04`。同一份测试文件另外在隔离副本 M0 里（与 2a 的 12 条一起）29 passed（116.61 s，并行另一个 e2e 会话）；草稿首次运行 17 passed（85.61 s）；全量 pytest 里再通过一次。

### 6.3 变异（12 次：brief 的 10 条 + B-M3b + X-M1；每一次在隔离副本里，全部变红在预期的测试上）

基线 M0（未变异的副本，两个 e2e 文件）：29 passed。每条变异后文件都用 `git show HEAD:<path>` 逐字节比对，**全部 identical**。原始补丁与输出在 `docs/evidence/2026-10-20/live-e2e/mutations.txt`。

| # | 变异 | 变红的测试（新文件共 17 条中的几条） | 观察到的断言 |
|---|---|---|---|
| B-M1 | `fusion.compute_risk_score`：单分支分母用 `w_v + w_t` | **T-SMOKE `test_02`**；另 T-CONT `test_03`、`test_04`，V `test_02`（4 红 13 绿） | `window 21: RiskScore 33.8 != round_half_up(100 x P_t, 1) = 67.7`（即 50·P） |
| B-M2 | `trained.py`：`P_t = 1 - probs[1]` | **T-SMOKE `test_02`**；另 T-CONT `test_03`、`test_04`，ZERO `test_02`（4 红） | `window 5: P_telemetry_anomaly 0.99993… != frozen row 0 0.00022095…` |
| B-M3 | `inference._step_alert_fsm_live`：不可用窗口返回上一次的 severity | **T-CONT 全部 5 条**，另 V、ZERO 全部（14 红，仅 T-SMOKE 的 3 条绿） | `Monitoring stopped: The server failed while processing the frame … Category: model_runtime (HTTP 500)`：产品的 `RiskUpdate` 校验器拒绝带 severity 的不可用记录，循环三次重发后停止；红在停止面板，**没有走到告警断言** |
| B-M3b | 同类：不可用窗口把 `None` 写回 `last_severity`（锁存丢失） | **T-CONT `test_04`**（1 红 16 绿） | `seq 14: expected every window HIGH_ALERT, got ['CAUTION'] (20 windows)`；`seq 17: …` |
| B-M4 | live High 段改成「两个连续 High 窗口即完成」 | **T-CONT `test_04`**（1 红） | `seq 1: expected every window CAUTION, got ['CAUTION', 'HIGH_ALERT'] (20 windows)` |
| B-M5 | 前端游标行号 `seq % 24` | **T-CONT `test_02`、`test_03`**（2 红；先 `npm run build` 了被变异的前端） | `window 476: its features are replay row 0, but telemetry_seq 24 is row 24` |
| B-M6 | EMA 在 REPEAT 上也推进并平滑 | **V `test_03`**（1 红） | `window 2: REPEAT shows P 0.201 / raw 0.20105…, its observation was registered with 0.20105… / 0.20105…` |
| B-M7 | 不可用 / 非 fresh 窗口之后 EMA 链不断开 | **V `test_03`**（1 红） | `window 23: NEW P_distraction 0.206, expected 0.20105… (seed = raw)`（Start Camera 之后的首个 NEW 没有播种） |
| B-M8 | `fusion.effective_weights`：有效权重总和为 0 时退回只看新鲜度（零权重被忽略） | **ZERO `test_02`**（1 红） | `window 4: assessment_available=True SystemHealth=DEGRADED`；`a risk field is set: [0.0, 'Low', 'Partial evidence', 'NORMAL']`；`RiskScore equals round_half_up(100 x P_t, 1)` |
| B-M9 | `determine_dominant_evidence`：先判 Low 再判 Partial | **T-CONT `test_05`**；另 T-SMOKE `test_03`、V `test_05`（3 红） | `window 5: DominantEvidence 'Low observed risk' with assessment_available=True` |
| B-M10 | 导出 CSV 漏掉 `request_id` 身份列 | **E3**（单独跑 `-k test_e3`：1 红，14 s）；整个 `test_live_e2e.py`：E1 `test_04`、`test_07` 与 E3 共 3 红 | `60 differences, first ["window 1: csv request_id: cell '' for value '315af837-…'", …]` |
| X-M1 | fixture 里记录的模型哈希 `9802cb06` → `9802cb07` | **T-SMOKE `test_02`、`test_03`**（2 红） | `the frozen fixture does not match the model: … made for xgb_telemetry.json 9802cb07, the file on disk is 9802cb06` |

所有变异都由「该防守的那一行实现」被破坏引起，没有靠脆弱的偶然断言：B-M1、B-M2 同时被多个测试从不同角度抓到；B-M4、B-M5 的红信息直接指向 seq 与回放行。B-M3 字面版与 B-M3b 的区别见第 2 节第 2 点。

## 7. 遗留问题

1. **告警序列的独立推导，以及与控制者的表是否一致——一致。** 推导在读 brief 的表之前先按代码做的，用了三条互相独立的途径：
   - **手算**（`inference._step_alert_fsm_live` / `_advance_segment`，每个位置一次）：位置 0（行 0，Low）：NEW 只开 Low 段，不到 10 s，`NORMAL`；位置 1（行 1，High 67.7）：第一个窗口开 High 段（`srv` = 服务端时间，`src = end` = 位置 1 的采集时间），来源跨度 0，`CAUTION`，该位置其余窗口都是 REPEAT（REPEAT 不是 supporter，不推进跨度）所以全程 `CAUTION`；位置 2（行 2，High 79.3）：第一个窗口是 NEW，`end` 推进到位置 2 的采集时间，来源跨度恰为 2000 ms（算术时间）；墙钟条件是「距位置 1 的首个窗口 ≥ 2000 ms」，这个首个窗口的服务端时间与位置 1 的首个窗口之差在 2000 ± 一个循环周期之间，所以 `HIGH_ALERT` 出现在位置 2 的首个窗口或同位置稍后的 REPEAT 窗口（完成守卫：`contrib` = 遥测，仍有效且仍在 High 一侧），不会晚于位置 2 结束；位置 3（Low）：`_clear_segments(state, ("high",))`，Low 段新开，锁存不变，`HIGH_ALERT`；位置 4–12 High，锁存保持；位置 13、16（两路都没有输入）：`level is None`，`_step_alert_fsm_live` 清段、记 `unavailable_since`、返回 `None`，`last_severity` 不动；位置 14、15、17–20：恢复后重新锚定，`severity == "HIGH_ALERT"` 保持；位置 21–25 是 Low 段（21、22、23、24 四行 Low 加回绕后位置 25 的行 0），来源跨度到位置 25 为止 8000 ms < 10000 ms，不恢复；位置 26 是 High，直接清掉 Low 段。
   - **用产品的真实 FSM 函数跑合成流**：临时脚本（在会话的临时目录里，不入仓库）以 `app.inference.run_inference` 驱动算术采集时间的遥测流，扫描 96 种循环配置（周期 100 / 110 / 130 / 170 / 250 / 400 ms，相位 0 / 5 / 10 / 37 / 50 / 99 ms，抖动 0 / ±30 / ±60 ms，抖动小于半个周期），每种都跑到位置 27，逐窗口检查：**与控制者的表零差异**（位置 0 全 NORMAL、位置 1 全 CAUTION、位置 2 先若干 CAUTION 后 HIGH_ALERT 且至少一个 HIGH_ALERT、之后全 HIGH_ALERT、位置 13 / 16 全 null）。位置 2 里：62 种配置一个 `CAUTION` 都没有（首个窗口就是 `HIGH_ALERT`），34 种配置先有 `CAUTION`——这印证了测试必须同时允许两种形状。
   - **真实运行**：T-CONTINUITY 的 535 个窗口与表逐位置一致；草稿首次运行里位置 2 的 20 个窗口 **0 个** `CAUTION`、从第一个窗口起就是 `HIGH_ALERT`（属于上面 62 种之一）。
   - 每个位置的分数与等级也核对了：用 fixture 的 P 重算 `round_half_up(100·P, 1)`，25 行与 brief 的表**没有任何差异**。
   所以没有分歧，没有因此停下。
2. **B-M3 的字面写法在本代码上走的是 D01 校验器，不是告警断言**（第 2 节第 2 点）。这本身说明产品有第二道防线；告警断言是否还会单独守住这一条，由 B-M3b 回答。
3. **V 的重新播种只有「不可用窗口」一种在线上被触发**。`ema_problems` 里按 `freshness_tolerance_s` 的间隔断链这一支，本次运行里没有发生（`gap_resets = 0`），没有被端到端验证；它在测试工具里存在，是为了机器偶发停顿 > 3 s 时不产生误报。要在线上单独触发这一条，需要暂停再恢复且恢复时拿到新帧，brief 没要求，我没做。
4. **ZERO 的双分支窗口**：`SystemHealth` 是 `FULL`（`map_system_health` 只看新鲜度，注释写明「never at the weights」），`DominantEvidence` 不看权重（可以写出对零权重路的 `Telemetry-dominant`，本次实测为 `Low observed risk`）。我没有断言 `DominantEvidence`，也没有改产品代码；这是已知的 R14。
5. **IT-UI-01 的 DOM 读取依赖 CSS 类名**（延续 2a 遗留）；`expected_latest_panel` 的「无评估」分支又多依赖横幅的固定文字，界面重构时要同步改 `e2e_support.py`。
6. **`prototype-tests/README.md` 里仍有一句「scripted Live end-to-end … does not exist yet」已过时**；改它不在本 brief 允许的范围内，`live_e2e.md` 末尾已写明。`docs/fyp2/implementation/README.md` 索引里 G-W4-A 一行仍是「待做」，同样没有改。
7. **时间容差**：沿用 2a（遥测相邻序号墙钟间隔 [1.8, 2.3] s、窗口 `age < 3 s`）。新测试自己的时间依赖：T-CONTINUITY 要求每个位置 ≥ 3 个窗口（实测约 20）；V 的 `5 fps` 假摄像头依赖 Chromium 的 `fps=5` 参数。运行并行 2 个 e2e 会话时（变异队列）都稳定通过；在极慢的机器上这些断言可能先于功能变红，我没有放宽。
8. **`.venv` 是指向主仓库 `.venv` 的符号链接**（既有状态，不是本任务引入的）：解释器与依赖从主仓库只读使用；`PYTHONDONTWRITEBYTECODE=1`，会话期间该目录没有文件被修改。

## 8. 证据路径

- 测试：`backend/tests/test_live_single_branch.py`、`backend/tests/e2e_support.py`、`backend/tests/test_live_e2e.py`、`backend/tests/conftest.py`
- 冻结 fixture：`backend/tests/fixtures/telemetry_pt_by_row.json`；生成脚本 `backend/tests/fixtures/make_telemetry_pt_fixture.py`
- 人工验收对应表：`prototype-tests/live_e2e.md`
- 提交二的证据目录 `docs/evidence/2026-10-20/live-e2e/`：`README.md`（G-W4-A 逐项对应）、`SUMMARY.md` 与 `01-build.log … 05-eslint.log`（`run_gates.py`，`DRA_REQUIRE_MODELS=1`）、`freeze_manifest.txt`、`e2e-evidence-run.log`（一次 E1 运行）、`screenshots/01…05-*.png`、`session-export.json` / `session-export.csv`、`rvfc-measurement.json`、`mutations.txt`（上节的补丁与原始输出）
- 门禁与独立推导的原始输出在本会话的临时目录，不入仓库；`mutations.txt` 与 `SUMMARY.md` 是入库的原始证据
- 冻结基线字面量来源：`docs/evidence/2026-10-19/w3-gate/freeze_manifest.txt`

## 9. 下一项依赖

- **W5（会话生命周期、冷启动与导出）**：可以复用 `e2e_support.py` 的 `LiveRun` / `assert_reconciled` / `ApiTap.rewrite_infer`；冷启动与导出的端到端只需要新的驱动步骤，不需要新的对账代码。
- **阶段 5 的 R14**（`DominantEvidence` 语义）若改变 Partial 的判定顺序或文案，`common_problems` 里的期望要按届时生效的规则改（B-M9 就是守这一处）。
- **裁定 A / R10 的后续改动**若改变 `ALERT_SUSTAIN_MS` / `ALERT_RECOVER_MS`、算术采集时间或其他 FSM 规则，`ALERT_BY_SEQ` 要重新推导。
- **控制者待定**：第 7 节第 6 条（`prototype-tests/README.md` 与 `docs/fyp2/implementation/README.md` 索引的过时描述）归谁改；第 7 节第 3 条是否需要一个单独触发「处理间隔 > 容差」重新播种的线上用例。

## 附：G-W4-A 归档结果（提交二追加；归档必须在已提交的代码上运行，所以这一节不可能在提交一里）

门禁提交 `ae1c197`（提交一）。全部在真实工作树、已提交代码上运行，证据目录 `docs/evidence/2026-10-20/live-e2e/`：

- `DRA_REQUIRE_MODELS=1 python3 scripts/run_gates.py --out docs/evidence/2026-10-20/live-e2e`：**GREEN，五道门禁全绿**。build PASS（3.67 s）；pytest **951 passed / 0 skipped**（134.08 s；日志里 `PYTEST SKIPPED: 0` 与 `DRA_REQUIRE_MODELS=1: no model-dependent test was skipped`）；vitest 870 passed（2.49 s）；tsc 0（1.43 s）；eslint 0（1.16 s）。`SUMMARY.md` 里的 "working tree dirty (1 entries)" 是证据目录本身。
- `freeze_manifest.txt`：三个模型文件的 SHA-256 与冻结基线全部 MATCH（onnx `b3a42e8d…`、pt `196ca7b1…`、xgb `9802cb06…`）。
- 一次 E1 运行（`DRA_E2E_EVIDENCE_DIR` 指向证据目录，`pytest tests/test_live_e2e.py -v -s`，**12 passed in 36.77 s**，日志 `e2e-evidence-run.log`）留下：五个视图的截图（`screenshots/01…05`，我看过 `01-live-monitor.png`，是真实渲染）、该会话的导出 `session-export.json` / `session-export.csv`（各 60 个窗口，窗口号相同，`request_id` 不重复，CSV 的 `request_id` 列等于 provenance 里的值，无 flag）、E3 的 `rvfc-measurement.json`（Chromium 148.0.7778.96，60 个请求，全部走 `capture_time` 路径）。
- `mutations.txt`：第 6.3 节 12 次变异的补丁、变红的测试、第一条断言、还原后的逐字节比对。
- `README.md`：把 G-W4-A 的五项检查（五方逐行一致、单分支行为、失败与恢复、无重复写入、模型哈希不变）逐项对应到具体测试与验收报告；其中 `ST-FAIL-01..04`、`ST-RECOVER-01`、`IT-OUTCOME-01`（`test_fault_events.py`）、`IT-RETRY-IDENTITY`（`test_retry_contract.py`）和 2a 的三条 E2 都用 `grep` 核实过确实存在。
- 会话结束前再次核对：主仓库的 `.venv` 与 `ml/outputs/` 在本次会话期间没有任何文件被修改。
