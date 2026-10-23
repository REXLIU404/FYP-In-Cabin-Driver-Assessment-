# 阶段 1 · 第 6 项（P1-6）技术报告：清除 TS 中违反 ROUND_HALF_UP 规则的两处代码（F4 评审新增）

- 分支 `fyp2/live-system`，工作树 `/Users/liu/Desktop/FYP2-Live-System`，开工 HEAD `05dc8cd`（与任务要求一致，工作树干净）。
- 日期 2026-10-14。角色：实现者。未派发子 agent。

## 1. 任务编号与名称

P1-6-TSROUND：`ai/src/riskLogic.ts` 的 `asPercent`（explanation 文案里的百分比）与 `frontend/src/data/preparedSessionInput.ts` 的 `round3`（回放概率）改为 ROUND_HALF_UP，并让 explanation 文案与 UI 的百分比格式化共用同一种舍入；顺带更新 `ai/src/emaParity.test.ts` 文件头注释。本项在 F1（第 5 项）之前执行，因为它可能影响回放数值。

## 2. 实现状态

| 简报条目 | 状态 |
|---|---|
| 1. `asPercent` 改 half-up，且与 UI 百分比格式化共用同一种舍入 | 完成：`asPercent` 改为导出，`format.ts` 的 `formatPercent` 直接等于它（只有一份实现，第 4.1 节） |
| 2. `round3` 改为 `roundHalfUp(value, 3)` | 完成 |
| 3. 停止条件：回放钉死值一个都不能变 | 通过，没有触发 `NEEDS_CONTEXT`（核对方法见第 4.4 节） |
| 4a. explanation 文案与 UI 在 0.285 / 0.565 / 0.145 上给出同一百分比（29 / 57 / 15），期望为字面量 | 完成（`riskLogic.test.ts` +4、`format.test.ts` +1） |
| 4b. 让回放舍入的回退可被抓住：搜索使 `toFixed(3)` 与 half-up 不同的 `p_safe`，经公开解析路径钉住 | 完成：找到输入并经 `buildPreparedWindows` 钉住（第 4.3 节）；`preparedSessionInput.test.ts` +3 |
| 5. 更新 `emaParity.test.ts` 文件头注释 | 完成：「两个平局用例」改为四个，并逐一列出夹具 id |
| 验收：`asPercent` 改回 `Math.round(value * 100)` → 新测试变红 | 完成（M1，5 个测试变红） |
| 验收：`round3` 改回 `toFixed(3)` → 新测试变红 | 完成（M3，1 个测试变红） |
| 验收：四项门禁 0 失败；钉死值未变并写明核对方法 | 完成（第 5、6 节；第 4.4 节） |

## 3. 创建 / 修改的文件

提交内包含 8 个文件（7 个修改 + 本报告）：

| 文件 | 性质 |
|---|---|
| `ai/src/riskLogic.ts` | 修改：`asPercent` 由私有的 `Math.round(value * 100)` 改为导出的 half-up 实现（+12 / −1） |
| `frontend/src/utils/format.ts` | 修改：`formatPercent = asPercent`，删去自己那份 `Math.round(roundHalfUp(value, 2) * 100)` |
| `frontend/src/data/preparedSessionInput.ts` | 修改：`round3` 改用 `roundHalfUp`；把解析路径抽成导出的 `buildPreparedWindows(csv)`，`PREPARED_SESSION_WINDOWS = buildPreparedWindows(telemetryCsv)`（diff 看起来大是因为 `.map(...)` 链整体缩进了两格，逻辑未动） |
| `ai/src/riskLogic.test.ts` | 修改：新增 `asPercent` 与 explanation 文案两组测试（+4 个用例） |
| `frontend/src/utils/format.test.ts` | 修改：`formatPercent` 字面量加 0.565 / 0.145；新增「UI 百分比与 explanation 百分比同一舍入」测试（+1 个用例） |
| `frontend/src/data/preparedSessionInput.test.ts` | 修改：新增「回放概率 half-up」一组（+3 个用例）；已有 8 个用例的期望一字未改 |
| `ai/src/emaParity.test.ts` | 修改：仅文件头注释（「两个平局」→ 四个平局，列出 id） |
| `docs/fyp2/implementation/phase1-06-tsround.md` | 新建：本报告 |

未触碰：`backend/`、`docs/fyp2/review/`、`ml/outputs/`、主仓库、计划文档（登记工作留给控制者）、`ai/prototype-data/` 下的 CSV 与夹具。

## 4. 实现摘要

### 4.1 `asPercent` 与 UI 共用一份实现（及理由）

```ts
// ai/src/riskLogic.ts
export const asPercent = (value: number): string =>
  `${roundHalfUp(roundHalfUp(value, 2) * 100, 0)}%`;
// frontend/src/utils/format.ts
export const formatPercent = asPercent;
```

做法选择：简报给了两条路 —— (a) `ai/src` 提供百分比舍入、`format.ts` 复用；(b) 两边各自调 `roundHalfUp`，再用测试锁一致。我选 (a)。理由：分层允许 `frontend → ai/src`，反方向不允许；(a) 让「两处不一致」在结构上不可能（只有一个函数），测试只需再钉住字面量，而 (b) 仍保留两份实现，要靠测试防漂移。

算法与原 `format.ts` 相同：先对「小数」做 2 位 half-up，再 ×100。不能先 ×100：`0.285 * 100 = 28.499999999999996`、`0.565 * 100 = 56.49999999999999`、`0.145 * 100 = 14.499999999999998`，二进制噪声会跑到平局前面（`Math.round` 分别给 28 / 56 / 14）。第二次舍入 `roundHalfUp(x * 100, 0)` 作用在「已经是整数附近的值」上（如 `28.999999999999996`），只是把噪声收回整数，因此原先 `format.ts` 里的 `Math.round(...)` 也一并换掉，仓库里不再有「对概率 `Math.round(v*100)`」这种形式。

行为等价性（我实际算过，不是推断）：在 `[0, 1]` 上以 1e-6 为步长的 1,000,001 个点上，新 `asPercent` 与旧 `format.ts` 公式零分歧；`NaN`、`Infinity`、`-0.285`、`0`、`1`、`1.5` 上也一致。唯一变化的是 explanation 文案在平局处的数字（28→29、56→57、14→15）。

### 4.2 `round3`

`const round3 = (value: number) => roundHalfUp(value, 3);`，并加了一行注释说明为何不能用 `toFixed`。`inferDistraction`（`1 − P(safe_driving)`）与 `inferTelemetryAnomaly`（`1 − p_safe`）两处调用点不变。

为了能「经回放的公开解析路径」测试，把 `parseCsv(...).map(parsePreparedRecord).sort(...).map(...)` 抽成导出函数 `buildPreparedWindows(csv: string)`，出货会话就是 `buildPreparedWindows(telemetryCsv)`。这是对简报的最小延伸（简报要求优先走公开解析路径，否则退而测抽出的函数）；没有改变任何解析逻辑。

### 4.3 能区分两种舍入的输入（搜索记录）

搜索对象：`P_telemetry_anomaly = 1 − p_safe`，`p_safe` 取 `k / 10^d` 的字面量（`Number((k/10^d).toFixed(d))`，等同 CSV 解析出来的值），`d ∈ {2, 3, 4}`，k 遍历 0..10^d（共 101 + 1001 + 10001 个输入），比较 `Number(v.toFixed(3))` 与 `roundHalfUp(v, 3)`。

| 小数位 d | 输入个数 | `toFixed(3)` 与 half-up 不同的个数 |
|---|---|---|
| 2 | 101 | 0 |
| 3 | 1001 | 0 |
| 4 | 10001 | 286（全部是第 4 位小数为 5 的平局，`p_safe ∈ [0.0635, 0.9405]`） |

结论：2、3 位小数里找不到；4 位小数里有。所以出货 CSV（`p_safe` 只有 2 位小数）确实不可能暴露 `toFixed` 的错误，这也是旧套件放过它的原因。再对「`Math.round(v*1000)/1000` 这种常见变体」做同样搜索：它在这些输入上只错 13 个，其中与 `toFixed` 同时错的 6 个（如 `p_safe = 0.4895`）。最终选的四个输入，每个都用 Python `Decimal(…).quantize(Decimal("0.001"), ROUND_HALF_UP)` 独立复算：

| `p_safe` | `1 − p_safe`（精确十进制） | half-up（测试期望） | `toFixed(3)` | `Math.round(v*1000)/1000` |
|---|---|---|---|---|
| 0.0635 | 0.9365 | **0.937** | 0.936 | 0.937 |
| 0.3135 | 0.6865 | **0.687** | 0.686 | 0.687 |
| 0.9385 | 0.0615 | **0.062** | 0.061 | 0.062 |
| 0.4895 | 0.5105 | **0.511** | 0.51 | 0.51 |
| 0.94（对照，非平局） | 0.06 | 0.06 | 0.06 | 0.06 |

测试里还有一个「守卫」用例，直接断言 `Number((1 - 0.0635).toFixed(3))` 等是 0.936 / 0.686 / 0.061 / 0.51、`Math.round((1 - 0.4895) * 1000) / 1000` 是 0.51，防止将来这些输入不再区分两种舍入、测试悄悄失效。

### 4.4 停止条件的核对方法（回放数值一个都没变）

1. **全量回放转储对比**：在两个隔离副本里各跑一个临时测试（只在副本里，没进真实工作树），把 `PREPARED_SESSION_WINDOWS`（25 个窗口，含 `P_distraction`、`P_telemetry_anomaly`、状态、各类概率等全部字段）和逐窗经 `buildRiskUpdate` 得到的 25 条 `RiskUpdate`（含 `RiskScore`、`RiskLevel`、`DominantEvidence`、`AlertSeverity`、`SystemHealth`、`explanation` 文案）写成 JSON。副本 A = `git archive HEAD`（改动前）；副本 B = `git archive HEAD` + 覆盖我改后的三个源文件。两份 JSON 的 SHA-256 完全相同：`d7986f83282d1b99818be033c44dd41b5d17e0f8577318918e25a6c5c2f528d6`（`cmp` 输出 IDENTICAL）。比较过的概率值：25 窗口 × 2 个字段 = 50 个（含缺失分支的 0）。这同时说明真实回放里没有任何 explanation 百分比落在平局上，文案也没变。
2. **钉死的期望一字未改**：`git diff frontend/src/data/preparedSessionInput.test.ts` 里唯一被删的一行是 `import { PREPARED_SESSION_WINDOWS } from ...`（换成多行 import）；原有 8 个用例（`16 → 62.5/High`、`18 → 70/High`、`19 → Vision-dominant`、`7 → 31`、`9 → 68.1` 等）的断言没有被动。
3. 四项门禁里 `preparedSessionInput.test.ts` 的 11 个用例（8 旧 + 3 新）全绿。

## 5. 执行的测试（精确命令）

### 5.1 门禁（真实工作树，改动前 = 改动后各跑一次）

```
cd /Users/liu/Desktop/FYP2-Live-System
export PYTHONDONTWRITEBYTECODE=1
(cd backend && TMPDIR=$(mktemp -d) PYTHONPATH=. ../.venv/bin/python -m pytest tests -q -p no:cacheprovider)
./node_modules/.bin/vitest run --no-cache
./node_modules/.bin/tsc --noEmit
./node_modules/.bin/eslint .
```

### 5.2 变异验证（全部在隔离副本 C 里做）

副本 C：`git archive HEAD` 后把我改后的 7 个文件覆盖进去，`git init` 并提交为基线，`node_modules` 与 `.venv` 符号链接到真实工作树；每次变异用一个 python 脚本做「恰好一处替换」，跑 `./node_modules/.bin/vitest run --no-cache`，再 `git checkout -- .` 还原，并确认 `git status --short` 为 0 行。副本路径（未删除）：

- A（改动前基线）`/var/folders/0k/dtzqmkm53vqgg530vd7h3fmr0000gn/T/tmp.H7CHybPPJf`
- B（改动后，只用于回放转储）`/var/folders/0k/dtzqmkm53vqgg530vd7h3fmr0000gn/T/tmp.JMJaagTmYN`
- C（变异）`/var/folders/0k/dtzqmkm53vqgg530vd7h3fmr0000gn/T/tmp.nN6dNzOmKp`

| 编号 | 变异（只改副本 C） | 观察到的结果 |
|---|---|---|
| M1 | `asPercent` 的实现改回 `` `${Math.round(value * 100)}%` `` | 5 failed / 400 passed：`asPercent … breaks the exact decimal ties`（`expected '28%' to be '29%'`）、`formatPercent rounds to an integer percent half-up`、`UI percent … one rounding`、两条 explanation 文案用例（`expected … to contain 'P_distraction (57%)'` 等）。还原后 git status 0 行 |
| M5 | `asPercent` 去掉内层 `roundHalfUp(value, 2)`：`roundHalfUp(value * 100, 0)` | 5 failed / 400 passed（同一组五个用例）。说明「先对小数舍入再放大」这一步也被测试守住了 |
| M2 | `format.ts` 的 `formatPercent` 退回自己的 `Math.round(value * 100)`（`asPercent` 不动，即 UI 一侧漂移） | 2 failed / 403 passed：`formatPercent rounds to an integer percent half-up`、`UI percent … one rounding` |
| M3 | `round3` 改回 `Number(value.toFixed(3))`（简报的验收变异） | 1 failed / 404 passed：`replay probabilities are rounded half-up … P_telemetry_anomaly = 1 - p_safe breaks decimal ties upward` |
| M6（第一次） | `round3` 改成 `Math.round(value * 1000) / 1000` —— 当时测试还只有 0.0635 / 0.3135 / 0.9385 三个输入 | **405 passed，变异存活**：这三个输入上该变体恰好与 half-up 一致 |
| M6（补 0.4895 后） | 同上变异，重跑 | 1 failed / 404 passed（同 M3 的那个用例）。因此补了 `p_safe = 0.4895` 这一行，让两种常见回退都能被抓住 |
| M4a | explanation 的 Vision-dominant 句里 `pD` 一处改成 `Math.round(pD * 100)` | 2 failed / 403 passed：Vision-dominant 文案用例、`UI percent … one rounding` |
| M4b | 同句里 `pT` 一处同样改动 | 2 failed / 403 passed：同上两个 |
| M4c | Telemetry-dominant 句里 `pT` 一处同样改动 | 2 failed / 403 passed：Telemetry-dominant 文案用例、`UI percent … one rounding` |
| M4d | Telemetry-dominant 句里 `pD` 一处同样改动 | 2 failed / 403 passed：同上两个 |

M4a–d 证明四个调用点（两句话 × 两个分支）都各有一个平局值覆盖：Vision 句 `pD = 0.565`、`pT = 0.285`；Telemetry 句 `pT = 0.565`、`pD = 0.145`。

每次变异后均已还原，副本 C 的 `git status --short` 为 0 行。真实工作树没有做任何变异。

## 6. PASS / FAIL / SKIP 计数

| 门禁 | 开工基线（`05dc8cd`，我自己先跑过） | 改动后 |
|---|---|---|
| pytest | 525 passed, 1 warning | 525 passed, 1 warning（0 failed，输出里没有 skipped） |
| vitest | 397 passed / 0 failed（15 个文件） | **405 passed / 0 failed**（15 个文件） |
| tsc --noEmit | exit 0 | exit 0 |
| eslint . | exit 0 | exit 0 |

vitest 397 → 405 的 +8 全部来自本项新增的用例，没有替换或删除任何已有用例：

| 文件 | 新增 | 用例 |
|---|---|---|
| `ai/src/riskLogic.test.ts` | +4 | `asPercent` 平局（0.285 / 0.565 / 0.145 → 29 / 57 / 15）；`asPercent` 非平局不受影响；Vision-dominant 文案；Telemetry-dominant 文案 |
| `frontend/src/utils/format.test.ts` | +1 | UI 百分比与 explanation 百分比一致；另给既有 `formatPercent` 用例加了 0.565 / 0.145 两条字面量（同一用例内，不增加用例数） |
| `frontend/src/data/preparedSessionInput.test.ts` | +3 | 守卫（输入确实让 `toFixed` 向下舍）；`P_telemetry_anomaly = 1 − p_safe` 平局向上；视觉分支与无遥测窗口不变 |

pytest 数字不变（525）是因为本项没有改后端，也没有改后端测试。

## 7. 遗留问题

1. **出货回放里这个 bug 本来就不会触发**：出货 CSV 的 `p_safe` 只有两位小数，`toFixed(3)` 与 half-up 零分歧（第 4.3 节搜索 d=2、3 均为 0），所以本项对回放数值零影响（第 4.4 节哈希相同）。新测试守的是「将来 CSV / 回放数据出现 4 位小数平局」这个回归，而不是修复一个当前可见的数值错误。
2. **explanation 文案只在平局处变化**，且已落库 / 已导出的旧记录里存的是旧字符串（如 `28%`），不做迁移；新生成的记录才是 `29%`。这是一个已存储字符串，不是可重算字段。
3. **仓库里仍有 `toFixed` / `Math.round`，但都不在「score、概率、EMA 值」范围内**，我没有改，供控制者判断是否也要纳入规则：`ai/src/evidence.ts:106/113/120` 的 `gap.toFixed(2)`（渲染可配置的证据差阈值，默认 0.15，非概率）；`frontend/src/components/TelemetrySummary.tsx`、`VehicleDynamics.tsx` 里对原始传感量（speed、accel、brake、throttle 等）的 `toFixed` / `Math.round`；`App.tsx` 的 FPS 与往返时延显示；`useCameraPreview.ts` 的画布高度。`SignalInspector.tsx` 里的 `* 100` 是条形宽度，不产生文本。~~`trendSeries.ts` 里的 `* 100` 是图表坐标，不产生文本。~~ **控制者更正（评审发现）**：`trendSeries.ts:32` 的 `record.P_distraction * 100` / `P_telemetry_anomaly * 100` 会经 `formatTrendTooltip`（`TrendChart.tsx:61` 的 Tooltip formatter）渲染成 `formatFixed(…, 1)%` 文本，先放大再舍入，会让二进制噪声越过平局（评审实测 0.2855 → "28.5%"，十进制 half-up 应为 28.6%）。只在 ≥ 4 位小数且恰在平局上的概率触发（Live 的 provider 精度值或 EMA 首个种子值），出货回放的 3 位小数值不受影响。已列为遗留，在 Task 9（前端范围）修。
4. `prettier --check` 对 `frontend/src/data/preparedSessionInput.ts`（`visualClasses` 的几张数据表）与 `ai/src/riskLogic.test.ts` 有**开工前就存在**的告警（HEAD 的副本同样告警）。我没有重排它们，以免产生与本项无关的大 diff；我新增的代码本身通过 prettier（逐文件核对过差异，剩余差异全部是旧行）。prettier 不在门禁里。
5. 主仓库注入的旧 `CLAUDE.md` 与现状不符，已按 context 文件以本工作树为准；本项没有依赖它。

## 8. 证据路径

- 本报告：`/Users/liu/Desktop/FYP2-Live-System/docs/fyp2/implementation/phase1-06-tsround.md`
- 被改动的源码：`/Users/liu/Desktop/FYP2-Live-System/ai/src/riskLogic.ts`、`/Users/liu/Desktop/FYP2-Live-System/frontend/src/utils/format.ts`、`/Users/liu/Desktop/FYP2-Live-System/frontend/src/data/preparedSessionInput.ts`
- 新增 / 改动的测试：`ai/src/riskLogic.test.ts`、`frontend/src/utils/format.test.ts`、`frontend/src/data/preparedSessionInput.test.ts`、`ai/src/emaParity.test.ts`（均在上述工作树下）
- 回放转储（改动前 / 后，SHA-256 相同）：scratchpad `before.json`、`after.json`，以及转储脚本 `dump.test.ts`，路径前缀 `/private/tmp/claude-501/-Users-liu-Desktop-FYP-In-Cabin-Driver-Assessment--1--claude-worktrees-exciting-keller-fdf913/a1949e26-b3d7-4f7f-bd9f-059bf8cb6f0e/scratchpad/`
- 输入搜索脚本：同目录 `search.mjs`、`search2.mjs`、`search3.mjs`；百分比等价性核对：`pct.mjs`；变异脚本：`mutate.py`
- 隔离副本 A / B / C：见第 5.2 节

## 9. 下一项依赖

- **P1-5（F1，把回放数值钉进 CSV）可以放心开工**：本项已证明出货回放的全部数值与改动前逐字节相同（第 4.4 节），所以 F1 钉的数值与现状一致，不会因为本项而漂移。
- 本项新增的导出 `asPercent` 与 `buildPreparedWindows` 是之后其他项可复用的入口：以后若要在别处渲染概率百分比，请调用 `asPercent` / `formatPercent`，不要再写 `Math.round(v * 100)`。
- 计划文档里 F4 评审新增条目（asPercent / round3）的登记由控制者处理；我没有改计划文档。
