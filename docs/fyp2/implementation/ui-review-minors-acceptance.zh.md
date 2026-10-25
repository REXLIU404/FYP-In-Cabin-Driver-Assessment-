# 界面易用性审查与暂缓 Minor 修复：验收报告（中文）

## 1. 任务概要

- **来源**：用户 2026-10-23 的要求：
  - 「review the UI, make sure is user friendly」；
  - 「暂缓的 Minor … 你帮我修补这个问题吧」；
  - 「E3 网格补上 AlertSeverity 的对照；Explanation 测试多核对几个字段」。
- **范围**：
  - 五个视图的易用性问题；
  - 最终评审（W5 / W6）记为暂缓的全部 Minor：M1–M4、M6–M11、M13，以及「计时缓冲收不到 Server-Timing」。
  - M5 与 M12 当时已上调为 Important 并修复，不在本轮。
- **方法**：
  - 先在真实仪表盘上截图审查（与端到端测试同一套环境：假摄像头、一次性数据库）；
  - 每一项先写会失败的测试，再实现；
  - 没能先看到红灯的测试，事后在隔离副本里做变异；
  - 最后在提交后的代码上跑全量门禁。
- **web-artifacts-builder 技能**：它的流程是另建一个 shadcn 工程，不适合审查已有应用。只采用了它的设计准则（避免居中堆叠、紫色渐变、千篇一律的圆角等），审查的是真实应用。

## 2. 实现证据

| 提交 | 内容 |
|---|---|
| `6886a2e` | 界面审查、M1、M2、M13 |
| `2745348` | M3、M4、M6–M11、Server-Timing |

截图（修改前 / 修改后）与采集脚本：`docs/evidence/2026-10-23/ui-review/`（README 里逐条对应问题与截图）。

**界面改动**

| 问题 | 改动 |
|---|---|
| 状态标签没有名字 | Live Monitor 标为 Risk level / Evidence / Alert；横幅标为 Alert / System health |
| CSS 把统计列表里的标签拉成整行灰条，颜色也失效 | 标签选择器改为 `span:not(.pill)`；横幅的同类规则只作用于标题与正文 |
| RiskLevel 为 Low 却显示 CAUTION，像是矛盾 | `alertHoldNote`（只是显示文字，不做判断）按 FSM 常量说明：「Alert held at CAUTION … Low for 10 s」或「Escalation pending … High for 2 s」 |
| M1：看不出窗口是固定的还是在跟随最新，也回不去 | 在 Inspector、Trends、Explanation 上方加选择栏，写明当前窗口以及是否固定，并提供 Follow latest。`describeSelection` 不会把已滑出历史的窗口说成「已固定」 |
| 同一个概率显示两次（100% 与 1.00） | 只显示百分数，精确值放到悬停提示（P = 0.50）。五方对账改为读这个提示 |
| 会话 ID 折成三行 | 单行显示，超长时用省略号，完整值放在 title 里（textContent 不变） |
| 摄像头运行时，半透明的禁用按钮叠在画面上 | 只显示当前可用的那个按钮 |
| Configuration 重复了顶栏的开始 / 暂停 / 重启 | 删掉；说明文字改为指向顶栏 |
| 故障停止时徽标写「paused」，过期提示重复三次 | 徽标改为「Monitoring stopped」；横幅已显示时，运行面板不再重复 |
| Risk Trends 的表没有上限（页面约 5,600 px 高） | 表格限高并可滚动，表头固定；加上「N windows, newest first」 |
| 分布图只标出一半类别 | 改为横向条形图，每个类别名占一行 |
| Inspector 的视觉类别按类别编号排列、名字被截断 | 按概率从高到低排序；加宽名字列，悬停显示全名 |
| 手机宽度下侧栏盖住约三分之一屏幕 | 改为细的置顶栏，视图入口排成一行、可横向滚动；网格列改为 `minmax(0, 1fr)`，页面不再横向溢出 |
| 术语与标签 | 「Server processing time」「Showing N of M saved windows」「Research prototype」 |
| M13 | 给 `.feature-contribution-note` 加上样式 |

**暂缓 Minor**

| 项 | 修复 |
|---|---|
| M2 | ST-SESSION-01 核对 Explanation 摘要的全部字段（两个概率、RiskScore、RiskLevel、AlertStatus、SystemHealth）和 Evidence Type。窗口可评估与不可评估两种情况都有期望值；同时核对选择栏 |
| M3 | E3 网格的期望表加上 DominantEvidence 与 AlertSeverity 两列字面量。(fresh, fresh) 原来是同义反复，现在是 Vision-dominant / CAUTION。expired 与 missing 的对照也比较 AlertSeverity；docstring 不再说 byte-for-byte |
| M4 | 遥测 REPEAT 使用登记时的贡献方法与基线（新登记键 `obs_t_contrib_meta`），贡献加基线仍等于登记的 margin。在这个键出现之前登记的会话，沿用模型本次的答案 |
| M6 | `drop_images` 对被改写的请求保留精简后的 `sent_raw`，`sent_body` 仍然代表服务器收到的内容 |
| M7 | conftest 按标记名（整词）判断 `long`；`-m "not longer"` 不会再放出 15 分钟的测试 |
| M8 | 所有 `requires_models` 都检查三个模型文件，由 test_model_gate 钉住。这条检查另外发现 `test_live_inference.py` 和 `test_unavailable_contract.py` 也只查了 ONNX，一并修正 |
| M9 | ST-LONG-01 每 20 s 读取一次页面的计时缓冲并累积（缓冲只有 500 条），每分钟统计和计划要求的「前 1,000 对比后 1,000」都基于全部窗口；去掉了不起作用的 `[-600:]` |
| M10 | perf01 运行不足时标记 `short_run` 并以退出码 1 结束（JSON 照常写出）；perf02 分母为 0 时完成率为 None、判为未达标，不再除零；`parse_server_timing` 支持带引号的值、跳过坏值，并有单元测试 |
| M11 | 冷启动脚本把路径作为参数传入，不再拼进命令字符串；单独检查 Playwright 的 Chromium 能从干净 venv 启动；PASS 后删除约 1 GB 的临时克隆（`COLDSTART_KEEP=1` 保留；FAIL 时总是保留） |
| Server-Timing | `api.infer` 把响应头交给循环（`onServerTiming`），循环写入计时缓冲（`TimingEntry.server` 原来恒为 null）；CORS 暴露这个头 |

## 3. 测试结果

**全量门禁**（提交 `2745348`，`DRA_REQUIRE_MODELS=1 python3 scripts/run_gates.py`）：**全绿**。build 通过；pytest **1046 passed / 0 skipped / 1 deselected**（deselected 的是 ST-LONG-01，只在 `-m long` 时运行）；vitest **954**；tsc 0；eslint 0。与上一轮相比 pytest 1028 → 1046（+18），vitest 922 → 954（+32）。`freeze_manifest.txt` 里三个模型的哈希都是 MATCH。工作树里 4 个未提交项都与门禁无关：`AGENTS.md`、用户开发数据库的两个文件、`docs/evidence/2026-10-23/`。证据在 `docs/evidence/2026-10-23/ui-minors-gate/`。

**先红后绿**（先写测试、看到失败，再实现）：

| 测试 | 修复前 |
|---|---|
| `usability.test.ts`（标签、提示说明、会话 ID、概率提示、停止徽标、摄像头按钮、选择栏、配置页） | 模块不存在，整文件失败 |
| `selection.test.ts`（describeSelection） | 4 条失败 |
| `display.test.ts`（alertHoldNote） | 失败 |
| M4：REPEAT 的基线 | 2 条失败 |
| M7：`-m "not longer"` | 失败 |
| M8：结构检查 | 失败 |
| M6：`test_api_tap.py` | 2 条失败 |
| M10：`test_perf_scripts.py` | 9 条失败 |
| Server-Timing：`liveLoopTiming.test.ts` 与 `client.test.ts` | 3 条失败 |
| M11：TMPDIR 带引号 | 修复前 clone 步骤退出码 2，修复后为 0（手工复现） |

**变异**：在隔离副本里运行，每项都变红。

| # | 变异 | 变红的测试 |
|---|---|---|
| U-M1 | 交换 Vision / Telemetry 主导的判断 | E3 `[V-fresh_T-fresh]` |
| U-M2 | 有分支过期时把告警抬高为 CAUTION | E3 `[V-expired_T-fresh]` |
| U-M3 | REPEAT 不用登记的元数据 | `test_a_repeat_carries_the_contributions_registered_with_the_observation` |
| U-M4 | describeSelection 把任何非空 id 都当成已固定 | selection.test.ts「滑出历史的窗口不算固定」 |
| U-M5 | 不显示提示说明 | usability.test.ts 两条 |
| U-M6 | Follow latest 什么都不做（端到端） | ST-SESSION-01 `test_07b` |
| U-M7 | AlertStatus 显示原始 token（端到端） | ST-SESSION-01 `test_05` |
| U-M8 | 循环丢掉 Server-Timing | liveLoopTiming.test.ts |

**其他运行**：
- ST-SESSION-01（真实浏览器）：10 passed；
- ST-LONG-01 冒烟（`DRA_LONG_MINUTES=2 -m long`）：1 passed，1,181 个窗口，计时覆盖率 0.9992；
- 修改后的截图：没有页面错误，控制台只有 3 条注入的网络中断。

## 4. 问题与风险

- **测试期望的改动**：
  - `modalityCard` 辅助函数改为读悬停提示，三处期望从 `0.50` 改为 `P = 0.50`；
  - 五方对账的 probability 也改为从提示读取；
  - Inspector 的期望改为按概率排序。

  这些改动都随界面改动而来，核对的内容没有减少，精确值仍然逐窗口对账。
- **CSS 布局没有自动化测试**，例如手机溢出、标签灰条。这部分只有截图证据（`ui-review/after/`）。
- **ST-LONG-01 的 15 分钟正式证据仍是 `2897000` 那一次**，本轮只做了 2 分钟冒烟。累积计时以后的完整数字，要等下次正式运行。
- **M11 的 Playwright 检查与清理只在代码里，冷启动没有完整重跑。** 已手工验证带引号的路径。
- **回放会话**：`fyp2/constructed-scenario` 改的是同一批文件（`App.tsx`、`SignalInspector.tsx`、`liveLoop.ts`、`client.ts`、`e2e_support.py`、`styles.css`），按约定由它在新的稳定提交上合并，有冲突就停下来报告。

## 5. 验收结论

**有条件通过。**

- 界面审查的各项改动，以及暂缓的 Minor（M1–M4、M6–M11、M13、Server-Timing）都已完成，先红后绿的证据与变异证据齐全，全量门禁全绿。
- **独立评审（2026-10-23，6 个维度，多智能体）**：找出 31 条问题。
  - 有 2 条被评为 Important，都已复现：
    - Prepared replay 模式下，选择栏一直显示「pinned」，每个 tick 都会撤销 Follow latest 和行固定（R9/R20）。根因是 `appendReplay` 原有的 `setSelectedWindowId`，这一行早于本轮。新的选择栏把它暴露了出来。
    - 告警说明的时长只描述了挂钟 FSM。Live 后端的 R10 FSM 还要求源时间跨度，所以「2 s」的说法在 Live 模式下不总是成立（R12/R19）。
  - 其余多为测试缺口和措辞问题。
  - 验证中途因额度中断，未全部完成。用户决定把评审的验证与修复交给 DeepSeek，问题清单在 `.superpowers/collab/review-2745348/findings.md`（不进 git）。
- **在 DeepSeek 修复并合并之前，本报告的结论只覆盖门禁与变异证据，不覆盖这 31 条。**

## 6. 下一任务就绪度

- 回放会话可以从新的稳定提交同步（会通知它提交号）。
- E2 / E5 runner：D06 已有决定，可以开工；需要用户给出开工指令。
- 冷启动可以在 `2745348` 上完整重跑，用来证明 M11 的两项新增步骤，大约需要 10 分钟。
