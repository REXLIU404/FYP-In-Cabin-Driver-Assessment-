# 独立评审 2745348 修复报告（DS-0 车道）

- 日期：2026-10-26
- 分支：`fyp2/ds-review-fixes`（worktree `/Users/liu/Desktop/FYP2-DeepSeek`），基线 `7e64c4d`（与状态板「当前基线」核对一致）
- 评审范围：`87d8668..2745348`（UI 易用性审查 + 暂缓 Minor），共 31 条（R1–R31）
- 门禁：`DRA_REQUIRE_MODELS=1 .venv/bin/python scripts/run_gates.py --out docs/evidence/2026-10-26/ds-review-fixes`，全绿、0 skipped
- 红线遵守：未改动融合公式、FSM、EMA、R10 观测逻辑；未触碰 8000 端口与任何 `driver_risk.db*`；未改 ML 工作区

## 1. 判定总览

31 条全部独立复现（每条都用一个测试或一段带 `file:line` 的代码路径证明），判定：

- **REAL：31 条**；NOT_REAL：0 条。
- 重复对（同一根因、同一修复）：
  - R9 ≈ R20：`App.tsx` 的 `appendReplay` 每个 tick 调 `setSelectedWindowId`，选择栏永远显示 pinned、用户 pin 被下一个 tick 覆盖。
  - R7 ≈ R10 ≈ R28：`bannerShown`（`App.tsx` 中「live/inspector/trends 且有 latest」）掩盖了「latest 窗口 unavailable 时」的 stale 提示；App 内注释的前提在该分支下不成立。
  - R11 ≈ R27：`ConfigurationView` 的说明「next Start Monitoring creates a session」对 Prepared replay（继续同一 replay 会话）不成立。
  - R12 ≈ R19：`alertHoldNote`（`display.ts`）只描述墙钟 FSM；R19 标 Important，因为 Live 后端走 `_step_alert_fsm_live`（服务器时间 AND 新观测源时间跨度），默认模式下「2 s」错达 2 s。

- 处置：修复 26 项（Important 3 条 + 可修的 Minor 23 项），deferred 5 条（R22、R23、R24、R25、R29，理由见各条）。

## 2. 逐条明细

### R1. [minor] PASS 后 SUMMARY.md 仍指向已删除的 scratch checkout
- 判定：**REAL**。`scripts/coldstart_check.sh` 中 `summary PASS`（写 SUMMARY.md）先于 `rm -rf "$WORK"` 执行；SUMMARY.md 第 54 行打印的 `- Scratch checkout: $REPO` 在默认 PASS 后指向不存在的目录，且 `COLDSTART_KEEP=1` 与默认跑产生的 SUMMARY.md 完全相同。
- 修复：`summary()` 在写摘要前按 `COLDSTART_KEEP` 决定清理动作并标注：默认 PASS 写 `(removed after PASS)`，`COLDSTART_KEEP=1` 写 `(kept: COLDSTART_KEEP=1)`；FAIL 保持原样（scratch 保留供检查，路径仍是有效指针）。
- 测试（红→绿）：新增 `backend/tests/test_coldstart_summary.py`（真实脚本 + step 打桩为成功，摘要与清理代码原样运行）。
  - 红：`FAILED test_a_passing_default_run_records_that_the_scratch_checkout_was_removed` / `FAILED test_a_passing_run_with_coldstart_keep_records_that_it_was_kept`（`2 failed in 0.59s`，SUMMARY.md 无任何标注）。
  - 绿：`2 passed in 0.56s`；`bash -n` 语法检查通过。

### R2. [minor] unavailable 横幅的 'System health' 标签无测试
- 判定：**REAL**。`usability.test.ts` 只渲染有评估的 AlertBanner 变体；`branchStatusRender.test.ts` 只断言裸 UNAVAILABLE pill 出现在某处，不检查它挂在哪个标签下。删除 `AlertBanner.tsx:32` 的 `<span>System health</span>` 后 954 个测试全绿（评审的 mutation 证据）。
- 修复：`usability.test.ts` 补测：对 `AlertBanner({latest: expiryRecords.bothExpired()})` 断言 `pillsAfter(html, "System health") == ["UNAVAILABLE:UNAVAILABLE"]` 且 `pillsAfter(html, "Alert") == []`。
- 测试：守卫测试首跑即绿（现状正确；守卫性质，删除标签时该测试会红）。

### R3. [minor] hold-note 测试从不检查 Alert pill（无滞回的 Alert 计算不被发现）
- 判定：**REAL**。display.test 只断言文字，不断言 pill 由 AlertSeverity 驱动。
- 修复：`usability.test.ts` 补测：hold note 出现时，Alert pill 来自 `AlertSeverity` 字段而非由 `RiskLevel` 现算。
- 测试：守卫测试首跑即绿。

### R4. [minor] 无测试保证 stale/unavailable Live Monitor 面板不显示 hold note
- 判定：**REAL**。`alertHoldNote` 对 stale/unavailable 应返回 null，但没有用例锁定。
- 修复：`display.test.ts` / `usability.test.ts` 补测 stale 与 unavailable 两个面板不渲染 hold note。
- 测试：守卫测试首跑即绿。

### R5. [minor] 'Monitoring paused' 从未被检查
- 判定：**REAL**。`RuntimeNotices` 的措辞无测试锁定，paused 状态读成 stopped 不会红。
- 修复：`runtimeNotices.test.ts` / `usability.test.ts` 补测：CaptureMissNotice 措辞「Vision evidence is missing; monitoring continues with telemetry only.」与 `role="status"`。
- 测试：守卫测试首跑即绿（21 passed）。

### R6. [minor] 相机测试跳过 'denied' 与 'error' 状态
- 判定：**REAL**。`usability.test.ts` 的相机测试只覆盖 requesting/停止路径；权限被拒后 Start Camera 错误地 disabled 没有测试能发现。
- 修复：与 R13 一起修（见下），补 denied/error 的守卫断言。
- 测试：与 R13 同一批红→绿。

### R7 ≈ R10 ≈ R28. [minor×3] latest 窗口 unavailable 时 stale 提示被掩盖
- 判定：**REAL（重复对）**。`App.tsx` 中 `!bannerShown` 的条件基于「live/inspector/trends 且有 latest」；当 latest 存在但无评估（unavailable）时，`getDisplayState` 优先显示 unavailable，stale 提示在 Inspector/Trends 上完全消失——与 App 内注释「banner already shows stale」的前提矛盾。
- 修复：`display.ts` 新增 `runtimeStaleNoticeShown(activeView, latest, stale)` helper：stale 时，若当前视图无 banner（latest 不存在）→ 显示；若有 banner，则仅当 banner 状态不是 stale 时再显示（banner 已在显示 stale 就不重复）。`App.tsx` 用该 helper 替代 `!bannerShown`。
- 测试（红→绿）：`display.test.ts` 新增 4 个用例（latest 有/无 × stale 真/假）。
  - 红：`TypeError: runtimeStaleNoticeShown is not a function`。
  - 绿：`display.test.ts` 48 passed。

### R8. [minor] display.test 钉住 Medium + HIGH_ALERT 的 hold 解释，与两个 FSM 都矛盾
- 判定：**REAL**。Medium + HIGH_ALERT 组合在两个 FSM 下都不可达（HIGH_ALERT 只在 High 持续后出现），用例锁死了一个不可能状态的文案。
- 修复：把 (Medium, HIGH_ALERT) 用例移入「返回 null」组，与 R12/R19 同一批。
- 测试：与 R12 同一批红→绿（display.test 4 failed → 44 passed）。

### R9 ≈ R20. [important×2] Prepared replay 选择栏永远显示 'pinned'，用户 pin 每 tick 被覆盖
- 判定：**REAL（重复对）**。`App.tsx` 的 `appendReplay` 对每条新纪录调 `setSelectedWindowId(record.window_id)`：`describeSelection` 里「null = 跟随最新」的语义被破坏——选择栏永远显示 pinned，Follow latest 按钮与行 pin 在下一个 tick 全部失效。
- 修复：删掉 `App.tsx` 中 `appendReplay` 内的 `setSelectedWindowId(record.window_id)` 一行（null 本来就表示跟随最新）。
- 测试（红→绿）：`runtimeNotices.test.ts` 按 `import appSource from "../App.tsx?raw"` 的既有模式加源码守卫测试「a prepared-replay tick never sets the selected window」。
  - 红：断言 appendReplay 块不含 `setSelectedWindowId` 失败（源码仍含该行）。
  - 绿：`runtimeNotices.test.ts` 81 passed。（附带修复 eslint `no-regex-spaces`：正则中的两个空格写为 ` {2}`。）

### R11 ≈ R27. [minor×2] Configuration 文案「creates a session」对 Prepared replay 不成立
- 判定：**REAL（重复对）**。`ConfigurationView.tsx:55` 的说明只对 LIVE 模式成立；Prepared replay 的 Start Monitoring 继续同一 replay 会话。
- 修复：说明改为按模式措辞：LIVE 模式「Start Monitoring creates a new session with these settings.」，Prepared replay「Start Monitoring resumes the prepared replay session with these settings; New Session restarts it from the top.」。
- 测试（红→绿）：`usability.test.ts` 对两种模式渲染并断言字面量。
  - 红：Prepared 模式断言失败（文案仍说 creates a session）。
  - 绿：`usability.test.ts` 24 passed（同批含 R21）。

### R12 ≈ R19. [minor/important] alertHoldNote 只描述墙钟 FSM；Live R10 FSM 下「2 s」错达 2 s
- 判定：**REAL（重复对；R19 标 important）**。`display.ts` 的 `alertHoldNote` 只引用 `ai/src/alertFsm.ts` 与后端 `_step_alert_fsm`。LIVE_MODEL_RUNTIME 下后端跑 `_step_alert_fsm_live`：segment 只在 NEW 观测上打开，且要求「服务器时间 AND 新观测源时间跨度」都达到阈值；Prepared telemetry 每 2000 ms 才有一次 NEW，其余 tick 是 REPEAT。评审的仿真：High 从 500 ms 持续到 4000 ms（3.5 s）才 HIGH_ALERT，Low 持续 11.5 s 才 NORMAL——而提示文字仍说 2 s / 10 s。
- 修复：措辞对两个 FSM 都成立，例如
  `Escalation pending: HIGH_ALERT follows only if RiskLevel stays High for 2 s (Live: 2 s of server time and of new observations).`，
  `Alert held at X: it returns to NORMAL only after RiskLevel has stayed Low for 10 s (Live: 10 s of server time and of new observations).`
  docstring 同时引用 `_step_alert_fsm_live`；`usability.test.ts` 中的字面量同步。
- 测试（红→绿）：`display.test.ts` 期望改为新字面量（写死）。
  - 红：`display.test.ts` 4 failed（三个字面量断言 + R8 的不可达用例）。
  - 绿：`display.test.ts` 44 passed。

### R13 ≈ 相关 R6. [minor] 相机预览失去取消 pending 权限请求的唯一途径
- 判定：**REAL**。`CameraPreview.tsx` 中 `canStop` 不含 `requesting`：请求权限期间 Start Camera 被 disabled，Stop 不显示，用户无法取消 pending 请求；权限被拒（denied/error）后同样卡住。
- 修复：`canStop = isLive || status === "requesting"`；requesting 时按钮显示 Stop Camera（点击即取消），并补 denied/error 状态的守卫断言。
- 测试（红→绿）：`usability.test.ts` 相机测试改为 requesting → Stop。
  - 红：requesting 用例 1 failed（仍渲染 disabled Start）。
  - 绿：`usability.test.ts` 18 passed。

### R14. [minor] M8 结构测试漏掉「只检查一个文件」的 marker
- 判定：**REAL**。`test_model_gate.py` 的 `test_every_model_skipif_checks_all_three_stable_model_files` 把三个文件名对**整个文件**断言（`assert all(name in source for name in files)`）：只要文件名出现在文件任何位置就通过，即使 skipif 条件本身只检查一个文件；且定位靠 segment 里出现 `MODEL_ROOT`/`ml/outputs` 变量名而非 reason。
- 修复：提取 `_model_skipif_conditions(directory)`（按 reason == REASON 定位，返回 `(file, reason, 条件源码段)`）与 `_names_all_three(condition)`；守卫测试改为**条件级**检查三个文件名与 `onnx').exists()` 反模式；新增合成用例证明「条件只查一个文件、其余两个名字出现在文件别处」会被条件级守卫抓住（旧的文件级断言会放过）。
- 测试（红→绿）：
  - 红：`NameError: name '_model_skipif_conditions' is not defined`（`2 failed, 8 passed`）。
  - 绿：`tests/test_model_gate.py` `10 passed in 4.90s`。

### R15. [minor] M7：标识符正则与 pytest 的 -m 语法不一致
- 判定：**REAL**。`conftest.py:149` 用 `re.findall(r"[A-Za-z_][A-Za-z0-9_]*", markexpr)` 切词；pytest 的 mark 表达式标识符允许 `-` 等字符（`(\w|:|\+|-|\.|\[|\]|\\|/)+`）。`-m "not long-run"` 被切成 `long`、`run` 两个词 → conftest 误以为要求 long → 15 分钟测试真的启动。
- 修复：conftest 按 pytest 的 `IdentsRegex` 切词后再比较 token `"long"`。
- 测试（红→绿）：`test_long_marker.py` 新增 `-m "not long-run"` 用例。
  - 红：`assert '1 passed, 1 deselected' in '.. [100%]\\n2 passed in 0.24s\\n'`（long 测试被启动）。
  - 绿：`tests/test_long_marker.py` `4 passed in 2.50s`。

### R16. [minor] parse_server_timing 自称镜像 TS 实现，但重复名、转义引号、inf/nan/hex 行为不同
- 判定：**REAL**。`scripts/perf01.py` 的 `_split_outside_quotes` 不处理 `\"` 转义；`out[name] = float(...)` 是 last-wins（TS 求和）；`float()` 接受 `inf`/`nan`/`1_0`（TS `Number()` + `isFinite` 会丢弃）；`.strip('"')` 剥掉任意多引号（TS 只剥两侧各一个）；`0x10` 与空串行为也不同。
- 修复：`_split_outside_quotes` 支持反斜杠转义；新增 `_js_number`（空串→0、含下划线→丢弃、hex→整数转 float、非有限→丢弃）与 `_strip_one_quote_per_side`；重复名求和 `out[name] = out.get(name, 0.0) + number`。
- 测试（红→绿）：`test_perf_scripts.py` 参数化表 +8 用例。
  - 红：`8 failed, 6 passed`（新增用例全部红）。
  - 绿：`tests/test_perf_scripts.py` `20 passed in 0.37s`。

### R17. [minor] ST-LONG-01 first_1000 / last_1000 在不足 2000 窗口时静默重叠
- 判定：**REAL**。`test_live_long_session.py:153` 直接 `timed[:EDGE]` / `timed[-EDGE:]`，无守卫无标注；`DRA_LONG_MINUTES` 是环境变量，评审用 2.1 分钟跑出 1241 窗口，两集合重叠 759 个（76%），JSON 里 `n` 仍是 1000，重叠不可见。
- 修复：提取 `edge_sets(timed, edge)`：`len(timed) < 2*edge` 时返回 None，measurement 写 `first_1000 = last_1000 = None` + `edge_note`；否则返回不相交两半。
- 测试（红→绿）：新增 `backend/tests/test_long_session_helpers.py`（独立文件，避开 `long` 标记）。
  - 红：`ImportError: cannot import name 'edge_sets' from 'test_live_long_session'`。
  - 绿：`4 passed in 0.31s`。

### R18. [minor] per-minute 行无上界，边界窗口被两行重复计数
- 判定：**REAL**。`test_live_long_session.py:101` 只有 `capturedAtMs >= minute_start_ms` 下界；采样总是晚于整分钟，晚到期间采集的窗口计入本行又计入下一行。评审实测：minute-1 行含 4 个结束后采集的窗口，minute-2 行含 1 个。
- 修复：提取 `minute_window(timings, minute_start_ms, minute_end_ms)`（双端界 `[start, end)`），接线 `minute_end_ms = next_sample * 1000`。
- 测试：与 R17 同文件：`test_the_minute_window_is_bounded_on_both_ends`、`test_a_late_sample_never_counts_a_window_in_two_rows`；红→绿同上（4 passed）。

### R19 → 见 R12（重复对，一起修复）。

### R20 → 见 R9（重复对，一起修复）。

### R21. [minor] 'Click a row to pin that window in every view' 与事实不符
- 判定：**REAL**。`RiskTrends.tsx` 的提示说「in every view」，但 Live Monitor（与横幅）忽略 pin（null 表示跟随最新）。
- 修复：措辞改为 `Click a row to pin that window in Signal Inspector, Risk Trends and Explanation.`
- 测试（红→绿）：`usability.test.ts` 断言新字面量、断言不含 "in every view"。
  - 红：旧措辞断言失败。
  - 绿：`usability.test.ts` 24 passed（同批含 R11/R27）。

### R22. [minor] High/CAUTION hold note 每次 High/Medium 翻转时上下跳动约 69 px
- 判定：**REAL**。评审在 1280 px 实测：note 高 55 px，模态网格位移 69 px；`alertHoldNote` 对 Medium+CAUTION 返回 null，窗口级翻转时 note 每 tick 出现/消失。
- 处置：**deferred**。修复要么给 note 预留固定高度（改布局、影响其他面板），要么按「持续超过一个窗口才显示」引入新的状态机（改动超过约 20 行且是布局/交互设计取舍）。当前评审场景是短时抖动，不影响数据正确性；建议在下一轮 UI 轮与 R24 一起设计。

### R23. [minor] 各视图状态名与大小写不一致
- 判定：**REAL**。Live Monitor/横幅用 'Risk level'/'Alert'/'System health' + 'CAUTION'，Explanation/Signal Inspector 用 'RiskLevel'/'AlertStatus'/'SystemHealth' + 'Caution'，且 test_05 锁定现状。
- 处置：**deferred**。统一标签集（合约 token vs 平实词）与值大小写是全局命名决策，牵连五个视图与 e2e `test_05` 期望、README/交接文档；属于跨车道一致性问题，不适合在本车道单方面拍板（见「需要用户决定」）。

### R24. [minor] High/CAUTION 不一致只在 Live Monitor 有解释
- 判定：**REAL**。`alertHoldNote` 只在 `LiveMonitor.tsx` 使用；Risk Trends、Inspector、Explanation 对同一矛盾没有任何说明（评审截图：8 行 High + CAUTION 无解释）。
- 处置：**deferred**。把 note 扩散到三个视图并给 Trends 加 tooltip/图例是组件级改动（>20 行），且与 R23 的标签决策、R22 的布局预留相互耦合；评审自己也给出替代选项「窄化 README 声明」。建议与 R22/R23 打包处理。

### R25. [minor] Risk Trends 上选择栏说 'Showing Window N'，页面上却没有该窗口
- 判定：**REAL**。`App.tsx:328` 在 trends 视图也渲染 SelectionBar；趋势图是全会话的，pin 只影响 520 px 滚动盒里的行高亮且不 `scrollIntoView`，旧窗口 pin 后页面上看不到该窗口。
- 处置：**deferred**。修法（滚动到 pin 行 + 措辞改「highlighted in the log」）需要 `scrollIntoView` refs 与视图感知措辞，超过约 20 行；与 R24 的 Trends 交互属同一轮设计。当前数据无错误，仅文案误导。

### R26. [minor] 'Server processing time' tooltip 在 Prepared replay（无后端）下不成立
- 判定：**REAL**。`LiveMonitor.tsx` 延迟行文案对两种模式共用；Prepared replay 的延迟是合成数据，没有服务器/数据库时间。
- 修复：`LiveMonitor` 加 `mode?: "LIVE_MODEL_RUNTIME" | "PREPARED_SESSION_RUNTIME"` prop（默认 LIVE），延迟行按模式渲染「Prepared latency (synthetic)」或「Server processing time」；`App.tsx` 传入 `mode={config.operationMode}`。
- 测试（红→绿）：`usability.test.ts` 断言两种模式的标签字面量。
  - 红：TS 报 `"mode" 不在类型 "Partial<LiveMonitorProps>" 中`（预期内，prop 尚未添加）。
  - 绿：`usability.test.ts` 22 passed。

### R27 → 见 R11（重复对，一起修复）。

### R28 → 见 R7（重复对，一起修复）。

### R29. [minor] 690–870 px 宽度下一行导航裁掉 'Configuration' 且滚动条隐藏
- 判定：**REAL**。评审浏览器探针（800 px）：`{clientWidth: 609, scrollWidth: 684, overflowX: 'auto', scrollbarWidth: 'none', lastBtn: ['Configuration', 725, 862], vw: 800}`；`styles.css:1219` 的 `.nav-list` 在 ≤900 px 变为单行横向滚动且 `scrollbar-width: none`，brand-copy 只在 ≤680 px 隐藏。
- 处置：**deferred**。三种修法（≤900 px 也隐藏 brand-copy / 加边缘渐隐 / 允许换行）都是视觉取舍，静态测试无法验证视觉效果；需要真实浏览器探针验收（见「需要用户决定」）。本次未改 CSS 以控制范围。

### R30. [minor] 新 chip 标签在 HIGH_ALERT 与 unavailable 横幅上不达 WCAG AA 对比度
- 判定：**REAL**。`styles.css` 的 `.badge-field > span:first-child` 用 `var(--muted)`（#64748b），在浅色横幅底（#fef2f2/#f1f5f9）上约 4.35:1，低于 AA 的 4.5:1。
- 修复：`color: #475569`（slate-600，在所有横幅底色上 ≥ 6:1），注释写明原因。
- 测试（红→绿）：`usability.test.ts` 加源码守卫测试（CSS 规则块含 `color: #475569`、不含 `var(--muted)`）。
  - 红（两次）：第一次因 vitest 在 node 环境吞掉一切 `.css` 导入（`?raw`/`?inline` 均返回空串）导致正则匹配 null；改用 `node:fs` 的 `readFileSync`（`@types/node` 非项目依赖，用 `@ts-expect-error` 注释）后红因正确：规则块不含 `#475569`（`1 failed | 24 passed`）。
  - 绿：`usability.test.ts` 25 passed。

### R31. [minor] M4 legacy 回退（「注册前会话保留模型自身答案」）无测试
- 判定：**REAL**。`test_telemetry_contributions.py:210` 的 legacy 测试把 `obs_t_contribs` 与 `obs_t_contrib_meta` **都** pop 掉 → 走的是更老的「无 contributions」分支；M4 新键引入的状态（contribs 有、meta 键无——正是 pre-M4 会话写入用户 dev DB 的状态）完全没有覆盖。评审的 mutation A（`scratch.get` + pop）在全后端套件下全绿。
- 修复（补测试）：新增两个用例：
  1. 只 pop `obs_t_contrib_meta`、保留 `obs_t_contribs`，REPEAT 断言 `telemetry_contribution_method == METHOD`、baseline 存在（stub 保持 bias 不变——真实模型确定，同字节的当前答案就是注册答案）。
  2. 注册的 meta 为 None（ProbStub NEW 后 ContribStub REPEAT）：断言 REPEAT 的 provenance 无 method/baseline（守卫 `provenance.pop` 两行）。
- 验证（红→绿 + mutation）：
  - 首跑：`1 failed, 9 passed`——失败的是我把 stub bias 改为 0.25 后断言 baseline == -4.0 得到 -4.25；这说明 meta 键缺失时 baseline 来自「模型对相同字节的当前答案」（确定性模型下与注册值相同），与 M4 提交信息「keeps the model's own answer」一致。按评审建议的写法（bias 不变）收敛：`10 passed`。
  - mutation A 验证（临时副本改 `inference.py` 为 `scratch.get`，跑完立即恢复）：新测试 `1 failed`——守卫力得到证明；`inference.py` 无残留改动。

## 3. 修复前红 / 修复后绿摘录

| 修复 | 红（修复前） | 绿（修复后） |
|---|---|---|
| R9/R20 | 源码守卫失败：`appendReplay` 块仍含 `setSelectedWindowId` | `runtimeNotices.test.ts` 81 passed |
| R12/R19/R8 | `display.test.ts` 4 failed（新字面量 3 条 + 不可达用例 1 条） | `display.test.ts` 44 passed |
| R7/R10/R28 | `TypeError: runtimeStaleNoticeShown is not a function` | `display.test.ts` 48 passed |
| R13/R6 | requesting 用例失败（仍渲染 disabled Start） | `usability.test.ts` 18 passed |
| R2/R3/R4/R5 | 首跑即绿（守卫测试，锁现状；对应 mutation 会红） | 21 passed |
| R26 | TS 错误：`"mode" 不在类型 "Partial<LiveMonitorProps>" 中` | `usability.test.ts` 22 passed |
| R11/R27 + R21 | Prepared 措辞与 "in every view" 断言失败 | `usability.test.ts` 24 passed |
| R30 | 第一次：`expected null to be truthy`（vitest 吞 CSS 导入）→ 修读取方式后红因正确：规则块无 `#475569` | `usability.test.ts` 25 passed |
| R14 | `NameError: name '_model_skipif_conditions' is not defined`（2 failed, 8 passed） | `test_model_gate.py` 10 passed |
| R15 | `assert '1 passed, 1 deselected' in '2 passed in 0.24s'`（long 真的启动了） | `test_long_marker.py` 4 passed |
| R16 | 新增 8 用例全红（`8 failed, 6 passed`） | `test_perf_scripts.py` 20 passed |
| R17/R18 | `ImportError: cannot import name 'edge_sets'` | `test_long_session_helpers.py` 4 passed |
| R31 | 补测试首跑 `1 failed, 9 passed`（bias 0.25 暴露语义）→ 按评审写法收敛 | `test_telemetry_contributions.py` 10 passed；mutation A 下新测试红（守卫力验证） |
| R1 | 2 failed（SUMMARY.md 无标注） | `test_coldstart_summary.py` 2 passed；`bash -n` 通过 |

## 4. 门禁结果

命令：`DRA_REQUIRE_MODELS=1 .venv/bin/python scripts/run_gates.py --out docs/evidence/2026-10-26/ds-review-fixes`

| # | 门 | 状态 | 退出码 | 耗时 | Skipped |
|---|---|---|---|---|---|
| 01 | build | PASS | 0 | 3.77 s | - |
| 02 | pytest | PASS | 0 | 177.91 s | **0** |
| 03 | vitest | PASS | 0 | 2.76 s | - |
| 04 | tsc | PASS | 0 | 1.77 s | - |
| 05 | eslint | PASS | 0 | 1.53 s | - |

- **pytest：1064 passed, 1 deselected, 0 skipped**（基线 1046；+18 全为本次新增/扩充的测试；deselected 的是 `long` 标记的 ST-LONG-01，符合预期）
- **vitest：968 passed（32 files）**（基线 954；+14）
- 日志与 SUMMARY.md：`docs/evidence/2026-10-26/ds-review-fixes/`

## 5. 提交

本分支（`fyp2/ds-review-fixes`）分提交完成，信息为英文；未 push、未 merge，未改 `fyp2/live-system`：

1. `4972e2f` frontend: fix review-2745348 findings R9/R20, R12/R19/R8, R7/R10/R28, R13/R6, R2-R5, R26, R11/R27, R21, R30
2. `2d85312` backend tests: fix review-2745348 findings R14, R15, R16, R17/R18, R31
3. `0061de2` scripts: fix review-2745348 findings R1 and R16
4. docs 提交：本报告 + 门禁证据（`docs/evidence/2026-10-26/ds-review-fixes/`）

## 6. 需要用户决定

1. **R29（窄屏导航裁切）**：三种修法（≤900 px 隐藏 brand-copy / 边缘渐隐提示 / 允许两行换行）是视觉取舍，且需要真实浏览器探针验收。本车道按红线（浏览器 e2e 之外不做视觉验收）未动 CSS；建议由评审/主车道选定一种后在下一轮实施。
2. **R23（标签与大小写统一）**：统一为「合约 token（RiskLevel/AlertStatus/SystemHealth）」还是「平实词（Risk level/Alert/System health）」是跨五视图 + e2e `test_05` + 文档的全局命名决策，需要用户或评审拍板，本车道不单方面改。
3. **R22/R24/R25（hold note 布局与解释扩散）**：三者互相耦合（预留高度、多视图 note、Trends 滚动/提示），建议作为一次 UI 轮打包设计；本车道分别记为 deferred。
4. **R31 附带发现**：当 `obs_t_contribs` 有、`obs_t_contrib_meta` 键无时，REPEAT 的 baseline 来自「模型对相同字节的当前推断答案」（真实模型确定 → 与注册值一致，UI 正确）。若希望该状态下 provenance 完全不带 method/baseline（与 meta=None 一致），需要改 `inference.py` 的 REPEAT 分支——这属于 R10 观测逻辑的语义选择，未在本次改动，请确认是否需要。
