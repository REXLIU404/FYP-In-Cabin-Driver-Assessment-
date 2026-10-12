# Task 6 实现报告 —— 前端展示层：消灭捏造读数

## 1. Task ID and name

- **Task 6**：前端展示层 —— 前端只渲染后端给出的 canonical 记录，不再捏造、重算任何读数
- 工作树 `/Users/liu/Desktop/FYP2-Live-System`，分支 `fyp2/live-system`，基线 HEAD `9befa55`
- 范围外、零改动：`backend/`、`ml/`（含 `ml/outputs/`）、故障事件（Task 7）。唯一触碰 `ai/src` 的地方是 `availability.ts` 的两个小增补（见第 3 节）。

## 2. Implementation status

**DONE_WITH_CONCERNS。** 三道门禁全部达标：`tsc` 0 错、vitest 全绿（0 failed）、pytest 504/0 不变。concerns 见第 7 节，其中最需要知情的是：没有 DOM 测试环境，所以 JSX 本身（组件内的条件渲染）只做了手工浏览器验证，自动化测试覆盖的是抽出来的纯函数。

| 项 | 状态 |
|---|---|
| 五个「tsc 抓不到」的静默失败点 | 全部修复；每一个都用**变异测试**证明有测试会为它变红（第 7 节逐项列出） |
| Task 5 移交的五项 | 全部处理（第 7 节 B 组） |
| 两个不可信边界归一化（localStorage、API client） | 完成；同一个 `normalizeRiskUpdate` |
| 删除捏造的 `SystemHealth` / freshness 改写 | 完成；available / stale / unavailable 三态 |
| 不再重算 canonical 字段（IT-UI-01） | 完成；`resolveDominantEvidence` 读记录自己的值 |
| CSV / JSON 导出与后端 unavailable 表示一致 | 完成；`UT-EXPORT-01` |
| unavailable 样式 tone | 完成；`.pill--unavailable`、`.alert-banner--unavailable`、`tr.is-unavailable` |
| `ExplanationView` unavailable 守卫 | 完成（含手工浏览器验证） |
| `ConfigurationView` 零权重行内提示 | 完成 |
| 必需测试 `UT-PERS-MIGRATE-01` / `UT-EXPORT-01` / `UT-DIST-01` / `UT-TREND-01` / grep 断言 | 全部完成 |

## 3. Files created or modified

**修改（21）**

| 文件 | 说明 |
|---|---|
| `ai/src/availability.ts` | 新增 `StoredRiskUpdate` 类型、`deriveAssessmentAvailable`、`normalizeRiskUpdate`（两个边界共用） |
| `ai/src/availability.test.ts` | +14 项：legacy 判定式、`normalizeRiskUpdate`、`IT-UI-01` grep 守卫（`?raw` 读源码，无需 `@types/node`） |
| `frontend/src/App.tsx` | `:66` 的 FSM 覆盖改走 `applyAlertState`（RiskLevel 为 null 时 `AlertSeverity` 保持 null） |
| `frontend/src/api/client.ts` | `infer / latest / windows / flag` 四个返回风险记录的端点经 `normalizeRiskUpdate` |
| `frontend/src/utils/persistence.ts` | `loadSessionLog` 归一化；非记录形状的条目被丢弃而不是崩溃 |
| `frontend/src/utils/format.ts` | `formatFixed`（`roundHalfUp`）；`formatRiskScore / formatContribution` 接受 null；`formatBranch*`；`UNAVAILABLE_LABEL` |
| `frontend/src/utils/export.ts` | 抽出 `buildSessionLogJSON/CSV` 纯函数；加 `alert_severity / system_health / assessment_available`；`dominant_evidence` 永远有键；缺失分支的 `p_telemetry_*` 与 `top_*` 为 null（空单元格）；追加 freshness 两列 |
| `frontend/src/components/Pill.tsx` / `StatusBadge.tsx` | label / tone 可为 null → 显式 `unavailable` tone（`pill--null` 不可能出现） |
| `frontend/src/components/AlertBanner.tsx` | 三态；不再比较 `SystemHealth`；class 由 `alertBannerClass` 给出 |
| `frontend/src/components/ScoreGauge.tsx` | `score: number \| null`；null 画空环 |
| `frontend/src/components/ModalityCard.tsx` | `toFixed` -> `formatProbability` |
| `frontend/src/components/TrendChart.tsx` | 用 `buildTrendSeries` / `formatTrendTooltip`；`Tooltip filterNull={false}` |
| `frontend/src/views/LiveMonitor.tsx` | 删除 `health` 与 freshness 改写；`buildLiveMonitorModel`；三态；新增 "Result age" 行 |
| `frontend/src/views/SignalInspector.tsx` | 读记录的 `DominantEvidence`；窗口列表标出 unavailable；缺失分支显示 "No input" |
| `frontend/src/views/RiskTrends.tsx` | 用 `distribution` / `riskRowClassName`；证据列读记录字段 |
| `frontend/src/views/ExplanationView.tsx` | 用 `buildExplanationModel`；unavailable 提示；无等式；distribution 含 Unavailable 桶 |
| `frontend/src/views/ConfigurationView.tsx` | 权重为 0 时行内提示；权重显示走 `formatFixed` |
| `frontend/src/styles.css` | `.pill--unavailable`、`.alert-banner--unavailable`、`tbody tr.is-unavailable`、`.risk-gauge--unavailable`、`.config-grid__notice` |
| `frontend/src/data/preparedSessionInput.test.ts` | `:31` 改为 4 元集（含 `null`）；新增「恰好一个 unavailable 窗口（17）」与 Task 5 回放值钉子 |
| `frontend/src/utils/persistence.test.ts` | `UT-PERS-MIGRATE-01`（+10 项，假 `window.localStorage`） |

**新建（15 个代码 / 测试文件 + 本报告）**

| 文件 | 说明 |
|---|---|
| `frontend/src/utils/display.ts` | `resolvePill`、`resolveDominantEvidence`、`evidenceDistribution`、`zeroWeightNotice`、`alertBannerClass` |
| `frontend/src/utils/alertOverlay.ts` | `applyAlertState`（`App.tsx:66` 的修复，可测） |
| `frontend/src/components/trendSeries.ts` | `buildTrendSeries`、`formatTrendTooltip`（`TrendChart` 的 series builder） |
| `frontend/src/views/riskDistribution.ts` | `distribution`、`riskRowClassName`（`RiskTrends` 的 `distribution()`） |
| `frontend/src/views/liveMonitorModel.ts` | `buildLiveMonitorModel`（三态与「health 必须等于记录自己的值」） |
| `frontend/src/views/explanationModel.ts` | `buildExplanationModel`（unavailable 守卫、贡献度对账） |
| `frontend/src/testing/records.ts` | 仅测试用的构造器：经真实 `buildRiskUpdate` 产生记录；`toLegacyRow` 还原旧格式行；`replayRecords` 跑 25 窗口回放 |
| `frontend/src/utils/export.test.ts` | `UT-EXPORT-01`（18 项） |
| `frontend/src/utils/format.test.ts` | 11 项 |
| `frontend/src/utils/display.test.ts` | 15 项 |
| `frontend/src/utils/alertOverlay.test.ts` | 3 项 |
| `frontend/src/api/client.test.ts` | 5 项（`vi.stubGlobal("fetch", ...)`） |
| `frontend/src/components/trendChart.test.ts` | `UT-TREND-01`（9 项） |
| `frontend/src/views/riskTrends.test.ts` | `UT-DIST-01`（10 项） |
| `frontend/src/views/viewModels.test.ts` | live / banner / explanation 三个视图模型（16 项） |
| `docs/fyp2/implementation/task-06.md` | 本报告 |

**与 brief 文件清单的偏差**：brief 写的是 `views/riskTrends.test.ts` 对应 `RiskTrends.tsx` 里的 `distribution()`。我把抽出的纯函数放在 `views/riskDistribution.ts`，**不是** `riskTrends.ts` —— 后者与 `RiskTrends.tsx` 在 macOS 大小写不敏感文件系统上冲突，`tsc` 当场报 `TS1149 / TS1261`（已复现并改名）。`views/riskTrends.test.ts` 的文件名保持 brief 所定。

## 4. Implementation summary

**核心设计：把可测逻辑抽成纯函数，组件只做渲染。** vitest 跑在 `node` 环境，没有 jsdom，`*.test.tsx` 不会被收集，我没有加依赖。每个静默失败点都有一个对应的纯函数 + 变异验证过的测试。

**两个不可信边界，同一个归一化函数。** `normalizeRiskUpdate(raw)`：记录自带 `assessment_available` 就**原样放行**（后端是 canonical 产出方，悄悄「修」一条自相矛盾的记录会掩盖后端 bug）；没有该字段（legacy）则用 `RiskScore != null && SystemHealth !== "UNAVAILABLE"` 推导，推导为不可用时把四个字段置 null。判定式是唯一正确的那个，两个诱人的一行写法在 legacy 行上朝相反方向出错：`!record.assessment_available` 把所有历史行标成 UNAVAILABLE（UI 里历史整段消失），`=== false` 把所有行标成可用（含历史上存成 `0/Low/NORMAL/UNAVAILABLE` 的窗口 17）。两种错误写法都做了变异（M7a / M7b），分别让 8 项与 10 项变红。`persistence.ts` 的 `loadSessionLog` 与 `client.ts` 的四个风险记录端点都走它；`appendRecord / flagWindow` 经 `loadSessionLog` 读，所以写回时 legacy 日志被顺带迁移。

**停止前端重算 canonical 字段。** grep 证实原先没有任何视图读 `record.DominantEvidence`。现在 `resolveDominantEvidence(record, thresholdLow)`：字段为 `undefined`（缺失）才回落到 `getEvidenceType` 重算；`null` 是合法的已存储答案，**不会**被重算「复活」成一个非空标签（`display.test.ts` 有专门用例）。`LiveMonitor / SignalInspector / RiskTrends / ExplanationView` 全部改用它，`IT-UI-01` 的 grep 守卫禁止这四个视图再出现 `getEvidenceType(`。

**available / stale / unavailable 三态。** `liveMonitorModel.ts` 与 `AlertBanner.tsx` 统一用 `getDisplayState`。`stale` 是前端对记录**年龄**的判断（`Date.now() - timestamp > tolerance`，依赖客户端与服务端时钟一致），`assessment_available` 是记录**自身**的属性。删除了 `const health = stale ? "UNAVAILABLE" : latest.SystemHealth` 以及把 `modality_freshness` 改写成 `"stale"` 的两段：显示的 `SystemHealth` 与 freshness 现在逐字等于记录自己的值；年龄单独用 "Result age: Current/Stale" 一行表达。stale 的记录不再显示成 current 的得分（沿用原行为：不展示过期分数），但标题与文案和 unavailable 不同。

**`ExplanationView`（最糟的一个）。** 它经 `selectedRecord` 进入，所以用户能在 Signal Inspector 选中 unavailable 窗口再切过来。`buildExplanationModel`：unavailable 记录 -> 无贡献度、无证据类型；视图顶部给出说明，AlertStatus 显示显式 unavailable tone，**不再**打印 `"Visual Distraction 0 + Telemetry Non-Safe 0 = RiskScore 0.0 / 100"`。守卫放在**记录**的可用性上而不只是算术上：一个由零权重造成的 unavailable 记录，若在另一组权重下查看，裸调 `computeRiskContributions` 仍会给出非空拆分（有用例，M15 变红）。

**分支贡献度不是记录里存的字段**，只能由记录自己的概率、freshness 与权重推导，所以它仍是「推导」而不是「读取」。我加了两道闸：unavailable 记录永不推导；推导结果与记录**存储的 RiskScore 对不上**（`|total − RiskScore| > 0.1`）就丢弃并说明原因。第二道闸是浏览器里发现的：回放记录没有 `provenance.fusion_config`，视图用的是「当前配置」权重，我先前把滑块调成 1.00/0.00 后，窗口 16 显示成 `Visual Distraction 60 + Telemetry 0 = RiskScore 62.5`（互相矛盾）。现在显示的是「权重与记录产生时不同，拆分对不上存储的 RiskScore」。这是**预先存在**的缺陷（原代码同样如此），只是被我顺手堵上。

**导出。** 表示与后端 `export.py` 一致：四字段 -> JSON `null` / CSV 空单元格；`assessment_available` -> 小写 `true/false`；`SystemHealth` -> `UNAVAILABLE`。`assessment_available` 与 `system_health` 在**每一种**导出里都有（关闭 evidence interpretation 也有），因为空单元格自身有歧义。JSON 里 `dominant_evidence` 永远有键（null，而不是被 `JSON.stringify` 丢掉的 `undefined`）。新列一律**追加**在原有列之后，位置依赖者不受影响。另外两处与「捏造读数」同类的清理：缺失分支的 `p_telemetry_safe/aggressive/distracted` 以前是 `?? 0`（`P(Safe)=0` 读作「肯定不安全」），现在是 null/空；`top_visual_class / top_telemetry_behavior / top_telemetry_feature` 的字面量 `"unavailable"` 改成 null/空，以免与「该窗口评估不可用」混淆。`P_distraction / P_telemetry_anomaly` 按契约仍是 `0.0`，所以追加了 `vision_freshness / telemetry_freshness` 两列说明何时这个 0 不是读数（契约里写的「用 modality_freshness + 导出列消化」）。

**样式。** `null` 插进模板字符串得到 `pill--null` / `alert-banner--null`，不匹配任何规则，于是退回基础（绿色，「一切正常」）样式。`resolvePill` 保证 tone 永远不是字符串 `"null"`；新增 `.pill--unavailable`（灰色虚线，既非绿也非黄也非红）、`.alert-banner--unavailable`、`is-unavailable` 行样式。

**展示舍入。** `formatFixed` 基于 `roundHalfUp`（十进制数字串上的 half-up，与后端 `round_half_up` 一致）；`formatPercent` 先对小数部分 `roundHalfUp(v, 2)` 再放大，避免 `v*100` 的二进制噪声压在平局前面。`format.test.ts` 钉死 `(0.285).toFixed(2) === "0.28"` 而 `formatFixed(0.285, 2) === "0.29"`、`29.95 -> "30.0"`。

**手工浏览器验证（回放路径，vite 起在本工作树）。** 种入 3 条 legacy 行（含一条 `0/Low/NORMAL/UNAVAILABLE`）-> Risk Trends 里该行是 `is-unavailable`，四格都是 "Unavailable"；跑完 25 窗口回放 -> 存储的窗口 17 为 `[null,null,null,"UNAVAILABLE",false]`（FSM 覆盖修复生效）；窗口 17 经 Signal Inspector 选中后切到 Explanation -> 无等式、AlertStatus 为虚线 unavailable pill、evidence 分布含 Unavailable 桶；Live Monitor 以 unavailable 为最新记录 -> 灰色虚线横幅、`SystemHealth` 为记录自己的 UNAVAILABLE、"Result age: Current"；Configuration 里把 Telemetry 权重拖到 0 -> 行内提示出现（拖回之前没有）。

## 5. Tests executed (exact commands)

均在 `/Users/liu/Desktop/FYP2-Live-System` 下执行。**`npx tsc` / `npx eslint` 在此环境被 RTK 包装器改写**（输出被压成一行摘要，`eslint` 还会直接拒绝），所以门禁用的是直接调用 `./node_modules/.bin/...` 的退出码。

```bash
# 1. 基线（改动前，HEAD 9befa55）
export TMPDIR=$(mktemp -d)
(cd backend && PYTHONPATH=. ../.venv/bin/python -m pytest tests -q)    # -> 504 passed
npx vitest run --no-cache                                              # -> Tests 1 failed | 276 passed (277)
npx tsc --noEmit                                                       # -> 34 errors，全在 frontend/
./node_modules/.bin/eslint ai frontend; echo $?                        # -> 0

# 2. 红测试确认：新测试在实现之前
npx vitest run --no-cache
#   -> persistence.test.ts 8 failed；format.test.ts 9 failed；client.test.ts 4 failed；
#      display / export / trendChart / riskTrends / alertOverlay / availability 因模块不存在整文件加载失败

# 3. 最终门禁
export TMPDIR=$(mktemp -d)
./node_modules/.bin/vitest run --no-cache
#   -> Test Files 15 passed (15); Tests 390 passed (390)
./node_modules/.bin/tsc --noEmit; echo "tsc exit $?"                  # -> tsc exit 0
npx tsc --noEmit | grep -c "error TS"                                  # -> 0
./node_modules/.bin/eslint ai frontend; echo "eslint exit $?"          # -> eslint exit 0
(git diff --name-only; git ls-files --others --exclude-standard) \
  | grep -E "^(ai|frontend)/.*\.(ts|tsx|css)$" | xargs ./node_modules/.bin/prettier --check
#   -> All matched files use Prettier code style!
(cd backend && PYTHONPATH=. ../.venv/bin/python -m pytest tests -q)    # -> 504 passed, 1 warning in 5.35s
node node_modules/vite/bin/vite.js build --outDir <scratch>/dist --emptyOutDir
#   -> ✓ built in 1.47s（仅有既存的 chunk > 500 kB 警告）

# 4. 变异验证（脚本在 scratchpad，未入库）：对每个静默失败点重新引入旧写法，期望有测试变红
python3 <scratch>/mut/run.py         # 结果文件 <scratch>/mut/mutation-results.txt
#   M1..M17 全部至少有 1 项测试变红；0 个「NO TEST FAILED」；每次运行后校验文件 sha256 已还原
```

变异清单（节选，全部在第 7 节引用）：M1 `AlertSeverity: state.severity` 覆盖 null（2 红）；M2 `distribution` 退回旧过滤、去掉 Unavailable 桶（4 红）；M3 行不再标 `is-unavailable`（1 红）；M4 去掉 `?? "unavailable"` 兜底（1 红）；M5 趋势点退回 `SystemHealth === "UNAVAILABLE"` 判据（1 红）；M6 `systemHealth: stale ? "UNAVAILABLE" : ...`（1 红）；M7a / M7b 两种错误的 legacy 判定式（8 / 10 红）；M8 导出的 `dominant_evidence` 变 `undefined`（1 红）；M9 `p_telemetry_*` 退回 `?? 0`（2 红）；M10 在 `AlertBanner.tsx` 重新写入 `SystemHealth === "UNAVAILABLE"`（1 红）；M11 在视图里重新引入 `getEvidenceType(`（1 红）；M12 去掉 tooltip 的 null 守卫（2 红）；M13 / M14 跳过两个边界的归一化（6 / 2 红）；M15 / M16 去掉解释页的 unavailable 守卫与对账（2 / 1 红）；M17 `resolveDominantEvidence` 总是重算（3 红）。

## 6. PASS / FAIL / SKIP counts

| 门禁 | 基线 | 现在 | 说明 |
|---|---|---|---|
| **pytest** | 504 passed / 0 failed | **504 passed / 0 failed / 0 skipped** | 未触碰后端，不变 |
| **vitest** | 276 passed / **1 failed** | **390 passed / 0 failed / 0 skipped**（15 文件） | +113 项（277 -> 390）。基线唯一失败 `preparedSessionInput.test.ts:31` 已修（改为 4 元集，非「改数据迁就旧断言」） |
| **tsc** | **34 errors**，全在 `frontend/` | **0 errors**（退出码 0） | `ai/` 与 `frontend/` 均 0 |
| eslint | 0 | 0 | 直接调用二进制 |
| prettier | — | 触碰过的 36 个 `.ts / .tsx / .css` 文件全部符合 | 3 个文件（`format.ts`、`persistence.test.ts`、`ExplanationView.tsx`）在 HEAD 就不符合，这次顺带格式化（`ExplanationView` 仅 3 处折行） |
| vite build | — | 通过 | |

新增测试分布：`availability` +14、`persistence` +10、`export` 18、`format` 11、`display` 15、`viewModels` 16、`riskTrends` 10、`trendChart` 9、`client` 5、`alertOverlay` 3、`preparedSessionInput` +2。

## 7. Remaining issues

### A. 五个「tsc 抓不到」的静默失败点：逐项如何验证已修

`tsc --noEmit` 干净**不是**完成信号：下面五个在修复前后 tsc 的输出完全一样。每一个都是靠「把旧写法重新引入、看哪个测试变红」来验证的，而不是靠读代码。

1. **`RiskTrends.tsx:22` —— `record.RiskLevel === label`。** unavailable 记录从三个桶里消失，三个计数之和不再等于 `history.length`（回放上是 24 而不是 25）。修复：`distribution()` 抽到 `views/riskDistribution.ts`，增加第四个 `Unavailable` 桶。验证：`UT-DIST-01`（回放上 `Unavailable === 1`、四个桶之和恰为 25、桶顺序、空历史四个零）；变异 M2 -> 4 项变红。
2. **`RiskTrends.tsx:79` —— `record.RiskLevel === "High"`。** null 永远不等于 `"High"`，这个比较本身是对的；静默失败的是 unavailable 行没有任何区别于普通行的样式。修复：`riskRowClassName` 给 unavailable 行 `is-unavailable`，并且绝不给 `is-high-risk`；`styles.css` 有对应规则。验证：`riskRowClassName` 的 4 项测试；变异 M3 -> 1 项变红；浏览器里该行确为 `is-unavailable`。
3. **`AlertBanner.tsx:27` —— `latest.AlertSeverity === "NORMAL"`。** 对 null 为假，于是选 `AlertTriangle` 图标，并生成 `alert-banner--null`（无匹配规则 -> 基础绿色横幅，即「一切正常」）。修复：横幅改走 `getDisplayState` 三态，class 由 `alertBannerClass` 给出，null 严重度解析为 `alert-banner--unavailable`，不可能出现 `--null`。验证：`alertBannerClass` 的 4 项测试（含「畸形 available 记录带 null 严重度也不能产生 `--null`」）；变异 M4 -> 1 项变红；M4c（同时去掉提前返回与兜底）-> 2 项变红；grep 守卫禁止 `AlertBanner.tsx / LiveMonitor.tsx` 出现 `SystemHealth === "UNAVAILABLE"`（M10 -> 变红）。
4. **`TrendChart.tsx:28` —— 已经可空的三元，键在旧判据上。** `record.SystemHealth === "UNAVAILABLE" ? null : record.RiskScore` 编译无误，但判据是旧的（SystemHealth），不是记录自己的 `assessment_available`。修复：`buildTrendSeries` 以 `isAssessmentAvailable(record)` 为键；tooltip 的 `formatTrendTooltip` 对 null 返回 unavailable 标记而不是 `Number(null) === 0` 导出的 `"0.0 / 100"`；`Tooltip filterNull={false}`，让 null 点真正走到 formatter。验证：`UT-TREND-01`（当且仅当 `assessment_available === false` 置 null；真实的 0 分**不**被置 null；tooltip 对 null / undefined 返回 sentinel）；变异 M5 -> 1 项变红、M12 -> 2 项变红。
5. **`App.tsx:66` —— `AlertSeverity: fsm.severity` 覆盖 null。** Task 5 把 `updateAlertState` 放宽到接受 null，`:62` 的 tsc 错误随之消失，但 `:66` 会产出 `RiskLevel: null` 而 `AlertSeverity: "CAUTION"` 的记录。修复：抽成 `applyAlertState`，`AlertSeverity: record.RiskLevel === null ? null : state.severity`，`App.tsx` 改用它。验证：`alertOverlay.test.ts`（先把 FSM 推到 `HIGH_ALERT`，再喂 unavailable 记录，断言发射值为 null、FSM 内部记忆仍为 `HIGH_ALERT`、`assertAvailabilityInvariant` 通过）；变异 M1 -> 2 项变红；浏览器回放后存储的窗口 17 为 `AlertSeverity: null`。

### B. Task 5 移交的五项

1. `App.tsx:66`：见 A.5。
2. `preparedSessionInput.test.ts:31`：改为 4 元集 `{Low, Medium, High, null}`，并新增断言「恰好一个 unavailable 窗口（17），四字段为 null，其余 24 个均可用」。
3. 回放演示值：我 grep 了 `ai / frontend / backend/tests / prototype-tests`，**没有任何测试或夹具钉过旧值**（`35.6`、`47.3` 零命中），所以没有断言需要「改成新值」；我反而新增了钉子防止回退：W16 `62.5 High`、W18 `70 High`、W19 `Vision-dominant`、W7 `31`、W9 `68.1`（数值取自对回放的实际运行，不是抄来的）。**没有改回放数据。** 报告 / 截图里引用旧回放数值的地方仍需刷新（不在本 task 范围）。
4. `roundHalfUp`：所有风险相关展示（`formatRiskScore / formatProbability / formatPercent / formatContribution`、`ScoreGauge`、`ModalityCard`、`ExplanationView`、`ConfigurationView`、tooltip）改走 `formatFixed`；`IT-UI-01` 的 grep 守卫对这些文件禁止 `.toFixed(`。
5. `captured_at / telemetry_timestamp` 的 state-key 豁免：无需实现，**未触碰相关文档**。

### C. 其余遗留 / 需知情

1. **没有 DOM 测试，JSX 本身未被自动化覆盖。** 抽出来的纯函数（series builder、`distribution`、行 class、banner class、三个视图模型、导出、归一化）全部有测试，但「组件里 `displayState === "stale" ? ... : ...` 这类三元是否接对」只做了手工浏览器验证（第 4 节末段）。这是 brief 明确接受的范围（「组件级渲染断言本阶段有意不做」）。
2. **Live 模式没有端到端跑过**（没有起后端）。API 边界的归一化只用 stub 的 `fetch` 验证。
3. **展示舍入没有覆盖遥测原始特征。** `TelemetrySummary.tsx`、`VehicleDynamics.tsx`、`App.tsx` 里的 FPS / 请求耗时仍用 `toFixed / Math.round`：它们显示的是前端独有的原始遥测数值与性能计数，后端没有对应值，不存在「与后端在平局上不一致」的问题；`preparedSessionInput.ts` 的 `round3` 是回放数据构造，改它会改变回放输入（不得改数据）。grep 守卫只覆盖风险展示相关文件。
4. **前端导出的列名仍是 snake_case**（`risk_score` 等），后端是 PascalCase（`RiskScore` 等）。「与后端一致」我按 R1 表理解为**unavailable 的表示**一致（空单元格 / `null` / 小写 `false` / `UNAVAILABLE`），不是列名一致；列名是 brief 的 `UT-EXPORT-01` 自己用的名字。
5. **归一化对「自带标志但自相矛盾」的记录有意不修**（例如 `assessment_available: false` 却 `RiskScore: 12`）：原样放行，后端 bug 保持可见，`assertAvailabilityInvariant` 会抓到它。UI 对这类记录按 `assessment_available` 渲染，不会崩。
6. **legacy 迁移后的 unavailable 行保留旧的 `explanation` 字符串**（旧流水线写的、可能描述「partial evidence」）。该字段目前没有任何视图显示。
7. **预先存在的前端缺陷（已顺手堵上一个）：** 回放记录没有 `provenance.fusion_config`，`ExplanationView` 用「当前配置」权重；配置改动后旧记录的拆分可能与其存储的 RiskScore 对不上。现在对不上时显示说明而不是互相矛盾的等式。回放记录若要被「按其产生时的权重」解释，需要把 `fusion_config` 写进回放记录（后端记录已有）；这是后续工作，不在本 task。
8. **D13 仍是已知限制**，本 task 不修：前端的 `stale` 仍是依赖客户端 / 服务端时钟一致的前端判断。本报告不声称系统已完整处理过期证据。
9. **操作失误已纠正：** 第一次用 `preview_start` 起 dev server，它按会话的主工作目录（不是本工作树）定位，起到了协调者的另一个工作树上，我发现页面里没有我的新代码（`normalizeRiskUpdate` 不在其源码里）后立刻停掉了，改用直接起在本工作树的 vite（`cacheDir` 指向 scratchpad）。这个误起的 server 可能在共享的（只读仓库的）`node_modules/.vite` 里留下了依赖预构建缓存；那是缓存，不是源码，未入库。除此之外没有写过 `/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1`。

## 8. Evidence paths

- 实现：`ai/src/availability.ts`；`frontend/src/utils/{format,display,alertOverlay,export,persistence}.ts`；`frontend/src/api/client.ts`；`frontend/src/components/{Pill,AlertBanner,ScoreGauge,TrendChart,trendSeries}.ts*`；`frontend/src/views/{LiveMonitor,SignalInspector,RiskTrends,ExplanationView,ConfigurationView,riskDistribution,liveMonitorModel,explanationModel}.ts*`；`frontend/src/styles.css`
- 测试：`ai/src/availability.test.ts`（`IT-UI-01`）、`frontend/src/utils/persistence.test.ts`（`UT-PERS-MIGRATE-01`）、`frontend/src/utils/export.test.ts`（`UT-EXPORT-01`）、`frontend/src/views/riskTrends.test.ts`（`UT-DIST-01`）、`frontend/src/components/trendChart.test.ts`（`UT-TREND-01`）、`frontend/src/views/viewModels.test.ts`、`frontend/src/utils/{format,display,alertOverlay}.test.ts`、`frontend/src/api/client.test.ts`、`frontend/src/data/preparedSessionInput.test.ts`
- 取证命令：`./node_modules/.bin/vitest run --no-cache`；`./node_modules/.bin/tsc --noEmit; echo $?`；`./node_modules/.bin/eslint ai frontend; echo $?`；`cd backend && PYTHONPATH=. ../.venv/bin/python -m pytest tests -q`
- 变异验证脚本与结果（未入库）：scratchpad 下 `mut/run.py`、`mut/mutation-results.txt`

## 9. Next task dependencies

- **Task 7（故障事件）**：`api/client.ts` 的 `request()` 仍对非风险端点保留 `as T`；风险记录端点已归一化。Task 7 若在 `useLiveSession` 加重试 / 停止态，注意 `history` 里的记录已经是 canonical（`assessment_available` 必有）。`useLiveSession` 当前的 `[404, 409, 422, 503].includes(err.status)` 重试策略与「D02 失败策略」表不一致，属于 Task 7 的范围，本 task 未动。
- **Task 8 / 9**：`frontend/src/utils/export.ts` 现在导出 `buildSessionLogJSON / buildSessionLogCSV` 纯函数，可直接断言；新增导出列一律**追加**。`frontend/src/testing/records.ts` 是可复用的测试构造器（经真实 `buildRiskUpdate`）。
- **Task 10（最终门禁）**：本 task 的三个数字是 pytest 504/0、vitest 390/0、tsc 0。`IT-UI-01` 的 grep 守卫（`ai/src/availability.test.ts`）会在以后有人把 `getEvidenceType(` 或 `.toFixed(` 重新写进这些视图时变红。
