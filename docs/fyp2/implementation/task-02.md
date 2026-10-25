# Task 2 实现报告 —— `ai/src` 契约核心：可空 RiskScore 与分母驱动的 health

## 1. Task ID and name

- **Task 2**：`ai/src` 契约核心 —— 可空 `RiskScore` 与分母驱动的 `SystemHealth`
- 工作树 `/Users/liu/Desktop/FYP2-Live-System`，分支 `fyp2/live-system`，基线 HEAD `6553a46`
- 范围：仅 `ai/src/` 与 `ai/fixtures/`。`frontend/`、`backend/`、`ai/reference/` 零改动；`ml/outputs/` 未触碰。
- 修的两个 P0：(1) 无证据窗口曾序列化为 `0 / "Low" / "NORMAL"`（捏造的安全读数）；(2) `SystemHealth` 曾靠数 `missing` 标志推导，而非来自有效融合分母。

## 2. Implementation status

**DONE_WITH_CONCERNS。** `ai/` 范围内全绿、`ai/` 范围内 `tsc` 零错误；两项偏离「DoD 全绿」的事实见第 7 节：

1. `npx vitest run --no-cache` 全仓库有 **1 条失败**，是 `frontend/src/data/preparedSessionInput.test.ts:31`。这正是 Task 6 Step 6 预言的「唯一被 D01 硬破坏的断言」（prepared 窗口 17 现在合法地给出 `RiskLevel = null`）。该文件在 `frontend/`，受「不得触碰 `frontend/`」约束，所以我没有改它。
2. `tsc --noEmit` 报 **35 条错误，全部在 `frontend/`**（预期内，Task 6 的工作面），`ai/` 下 0 条。

| Step | 内容 | 状态 |
|---|---|---|
| 1 | 夹具 + 失败测试 | 完成 |
| 2 | 确认红 | 完成（见第 5 节：首次运行 `32 failed | 78 passed`，`availability.test.ts` 因模块不存在整文件失败） |
| 3 | `availability.ts` + `types.ts` | 完成 |
| 4 | `riskLogic.ts` + `evidence.ts` | 完成 |
| 5 | 更新既有断言 | 完成（`riskLogic.test.ts`） |
| 6 | 跑 vitest + tsc | 完成；`tsc` 清单见第 7 节 |
| 7 | 单次本地 commit | 完成，SHA 见控制者收到的返回值 |

## 3. Files created or modified

| 文件 | 动作 | 说明 |
|---|---|---|
| `ai/src/availability.ts` | 新建 | `FUSION_EPSILON`、`freshnessWeight`、`effectiveFusionDenominator`、`isAssessmentAvailable`、`assertAvailabilityInvariant`、`getDisplayState` |
| `ai/src/availability.test.ts` | 新建 | `UT-AVAIL-01`（27 例）+ 分母 / epsilon / F-Z3 边界 / 不变式负例 / null 不进关系运算 / 解释文案，共 66 项 |
| `ai/fixtures/fusion_vectors.json` | 新建 | 21 行跨语言夹具，**顶层是数组**，行字段 `id, pd, pt, wv, wt, vision, telemetry, expect{available,score,level,health,dominant}` |
| `ai/src/fusionVectors.test.ts` | 新建 | 读 JSON，对每行断言 4 个纯函数 + `buildRiskUpdate` 端到端；共 110 项 |
| `ai/src/types.ts` | 修改 | `RiskUpdate` 增 `assessment_available: boolean`；`RiskScore/RiskLevel/DominantEvidence/AlertSeverity` 加 `| null` |
| `ai/src/riskLogic.ts` | 修改 | 见第 4 节 |
| `ai/src/evidence.ts` | 修改 | 见第 4 节 |
| `ai/src/riskLogic.test.ts` | 修改 | `:29-31` 改 `toBeNull()`；补零权重 / null 用例；`mapSystemHealth` 块补零分母；16 → 28 项 |
| `docs/fyp2/implementation/task-02.md` | 新建 | 本报告 |

`frontend/src/types.ts` 只是 re-export，未改动；可空性自动传播（这就是 tsc 报 35 条的原因）。

## 4. Implementation summary

**单一分母来源。** `effectiveFusionDenominator(wv, wt, vs, ts)` 返回 `{effVision, effTelemetry, denominator}`，权重表 `fresh=1.0 / stale=0.45 / missing=0.0`。`computeRiskScore`、`computeRiskContributions`、`mapSystemHealth`、解释文案全部读它，不可能各算各的。判零一律 `denominator <= FUSION_EPSILON`（`1e-9`），不用 `=== 0`。

**公式用 `eff_v / eff_t` 分母**（不是审计文档里只在等权下成立的 `/1.45` 写法）。

**`null < 30` 是 `true` —— 可用性判断排在所有关系运算之前：**
- `mapRiskLevel`：第一行 `if (score === null) return null`。
- `determineEvidenceType`：第一行 `if (riskScore === null || systemHealth === "UNAVAILABLE") return null`，然后才是 `systemHealth !== "FULL"` 与 `riskScore < thresholdLow`。
- `mapAlertSeverity(null) -> null`（原来 `alertSeverityMap[null]` 会得到 `undefined`）。

**先 round 再映射。** `computeRiskScore` 内部 `round1`，`mapRiskLevel` 吃的永远是已 round 的值；`F-T5`（`29.951 -> 30 -> Medium`）钉死这个顺序。

**`SystemHealth` 规则：** 分母 `<= epsilon` -> `UNAVAILABLE`；否则任一支非 `fresh` -> `DEGRADED`；否则 `FULL`。FULL/DEGRADED 边界只看 freshness，不看权重（`F-Z3`：`(1.0, 0.0)`、vision fresh、telemetry missing -> 分母 `1.0`，available，`10 / DEGRADED / "Partial evidence"`）。`mapSystemHealth` 新增两个权重参数，**默认 `0.5 / 0.5`**，`riskLogic.test.ts` 里三处两参调用无需改动。

**`buildRiskUpdate`：** 产出 `assessment_available = (score !== null)` 与四个同时为 null 的字段；`SystemHealth` / `DominantEvidence` 都用 `config.weightVision/weightTelemetry` 计算（所以零权重配置下 health 与 score 一致）。

**`buildExplanation`：** 新增 unavailable 分支，排第一。文案点名原因（`both the vision and telemetry inputs are missing` / `the vision input is missing and the telemetry branch has zero fusion weight` 等），**不含任何 level 词**（测试用 `/\b(low|medium|high|safe|normal)\b/i` 断言）。

**`evidence.ts` 周边：** `getRelativeEvidence` 对不可用记录返回 `"No usable evidence"`（原先会谎称 `"Partial input availability"`）；`getMatchedEvidenceRule(null)` 返回独立规则 `Unavailable / effective fusion denominator ... <= 1e-9 (no usable evidence)`，不再复用 `"one modality is stale or missing"`。

**`availability.ts` 公共面：**
```ts
export const FUSION_EPSILON = 1e-9;
export const effectiveFusionDenominator(wv, wt, visionStatus, telemetryStatus): { effVision; effTelemetry; denominator };
export const isAssessmentAvailable(record): boolean;            // 读记录自带的 assessment_available
export const assertAvailabilityInvariant(record): void;         // 违反则 throw，信息列出每一条违规
export const getDisplayState(record, { stale }): "available" | "stale" | "unavailable";  // unavailable 优先于 stale
```

**不变式（`assertAvailabilityInvariant` 强制）：** `assessment_available === (RiskScore !== null) === (SystemHealth !== "UNAVAILABLE")`；为 `false` 时四个可空字段同时为 `null`；为 `true` 时这四个字段都**非** null（全有或全无，见第 7 节 #6）。实现里是两条独立等式，没有写 `a === b === c`（那会变成「布尔对比 c」，静默判错）。

## 5. Tests executed (exact commands)

**红阶段**（实现前，`fusion_vectors.json` 与两个新测试已就位）：
```
$ npx vitest run --no-cache ai/src/fusionVectors.test.ts ai/src/availability.test.ts
AssertionError: expected 'DEGRADED' to be 'UNAVAILABLE'   (F-Z1/F-Z2 style rows)
 Test Files  2 failed (2)
      Tests  32 failed | 78 passed (110)
```
（`availability.test.ts` 因 `./availability` 不存在整文件加载失败；`fusionVectors.test.ts` 的 32 条失败是 `F-U1` 返回 `0`、`F-Z1/F-Z2` 返回 `DEGRADED` 等。）

**绿阶段 —— `ai/` 范围：**
```
$ npx vitest run --no-cache ai/src
 ✓ ai/src/alertFsm.test.ts (7 tests)
 ✓ ai/src/riskLogic.test.ts (28 tests)
 ✓ ai/src/fusionVectors.test.ts (110 tests)
 ✓ ai/src/availability.test.ts (66 tests)
 Test Files  4 passed (4)
      Tests  211 passed (211)
```

**全仓库：**
```
$ npx vitest run --no-cache
 ✓ ai/src/alertFsm.test.ts (7 tests)
 ✓ ai/src/riskLogic.test.ts (28 tests)
 ✓ frontend/src/utils/persistence.test.ts (3 tests)
 ✓ ai/src/availability.test.ts (66 tests)
 ✓ ai/src/fusionVectors.test.ts (110 tests)
 ❯ frontend/src/data/preparedSessionInput.test.ts (6 tests | 1 failed)
   × prepared session replay coverage > exercises every RiskLevel
     → expected Set{ 'Low', 'Medium', 'High', null } to deeply equal Set{ 'Low', 'Medium', 'High' }
 Test Files  1 failed | 5 passed (6)
      Tests  1 failed | 219 passed (220)
```

**类型检查**（RTK 钩子会把输出压成一行，所以用 `rtk proxy` 取原始输出）：
```
$ rtk proxy npx tsc --noEmit > /private/tmp/claude-501/out/tsc.txt 2>&1 ; echo exit=$?
exit=2        # 35 条 error，全部在 frontend/；ai/ 下 0 条
```
HEAD 基线是 `No errors found`，所以这 35 条全部由本 task 引入（预期内）。

**其它：** `rtk proxy npx eslint ai` -> exit 0；`prettier --check` 对新建文件与 `riskLogic.ts`、`types.ts` 通过（`evidence.ts` 与 `riskLogic.test.ts` 在 HEAD 就不符合 prettier，我没有为此重排无关行）。

**变异检验（证明测试有牙）：** 每次只改一处、跑 `ai/src`、再 `cp` 还原并 `cmp` 确认字节一致。
| 变异 | 结果 |
|---|---|
| M1 `evidence.ts` 去掉 `riskScore === null \|\|`（只留 health 判断） | `1 failed \| 210 passed` —— 抓到「null score + FULL/DEGRADED health -> 'Low observed risk'」 |
| M2 `computeRiskScore` 用 `denominator === 0` 代替 epsilon | `2 failed \| 209 passed` —— 抓到 `1e-10` 权重绕过 |
| M3 去掉 `round1`（用未舍入分数映射等级） | `12 failed \| 199 passed` |
| M4 `mapSystemHealth` 退回「两路都 missing 才 UNAVAILABLE」 | `13 failed \| 198 passed` —— 抓到 `F-Z1/F-Z2` |
| 还原后 | `211 passed (211)`，`cmp` 确认 `riskLogic.ts` / `evidence.ts` 与改前一致 |

## 6. PASS / FAIL / SKIP counts

| 范围 | PASS | FAIL | SKIP |
|---|---|---|---|
| `ai/src`（4 文件） | **211** | 0 | 0 |
| 全仓库 vitest（6 文件） | 219 | **1**（`frontend/.../preparedSessionInput.test.ts:31`，Task 6 所有） | 0 |
| `tsc --noEmit` | —— | **35 条 error**（全在 `frontend/`），`ai/` 下 0 | —— |
| `eslint ai` | 通过（exit 0） | 0 | —— |

分文件：`alertFsm` 7、`riskLogic` 28（原 16）、`availability` 66、`fusionVectors` 110（3 条形状 + 21 行 x 5 + F-T5 的 2 条）、`persistence` 3、`preparedSessionInput` 5 通过 / 1 失败。

## 7. Remaining issues

### 7.1 需要控制者拍板或知晓的偏离

1. **vitest 不是全绿（1 条）。** `frontend/src/data/preparedSessionInput.test.ts:31` 的 `new Set(records.map(r => r.RiskLevel))` 现在含 `null`。原因是 prepared 窗口 17（两路都缺失）现在合法地不可用 —— 这恰好是端到端证据，说明改动在真实 replay 数据上生效了。该文件在 `frontend/`，我按规则没动。Task 6 Step 6 已经预言了这条。
2. **我把 `computeRiskContributions` 也改成了可空**（返回 `{vision, telemetry, total} | null`，零分母时为 `null`，不再是 `{0,0,0}`）。简报的行号范围没列它，但 `{0,0,0}` 是同一类捏造读数（ExplanationView 会据此打印 `... = RiskScore 0.0 / 100`）。代价：多出 **8 条** tsc 错误（下表 `ExplanationView.tsx` 的 TS18047，行 221/246/250/256/258/264/266/389）。若控制者不要这项扩展，把返回值改回 `{0,0,0}` 即可，tsc 总数降到 27。
3. **`determineDominantEvidence` / `determineEvidenceType` 签名有微调：** `riskScore` 改为 `number | null`；`determineDominantEvidence` 在原参数**之后**追加 `weightVision = 0.5, weightTelemetry = 0.5`（health 现在由分母决定，需要权重）。原有位置参数顺序不变。
4. **`ai/src/alertFsm.ts` 未改。** `updateAlertState(prev, level: RiskLevel, now)` 仍只接受非空 level，所以 `App.tsx:62` 报错。不可用窗口该如何影响 FSM（保持 streak？重置？跳过？）是 Task 5/6 的设计决定，不应由我在类型层面静默决定。
5. **夹具顶层是数组**（`json.load` 直接得 `list`）。Task 3 的 pytest 按此读取。`score` 对整数值写作 `50` 而非 `50.0`（JSON 等价）。
6. **不变式比字面略严：** 简报只写「为 false 时四个字段同时为 null」；我把「为 true 时四个字段都非 null」也一并强制了（读作「null together」的全有或全无）。若后续 task 有「available 但 AlertSeverity 暂为 null」的设计，需要放宽这一条。
7. **`isAssessmentAvailable` 直接读记录的 `assessment_available`。** 缺该字段的旧记录会被判为 `false`。Task 6 的读取边界归一化（`RiskScore`/`SystemHealth` 推导）必须先于它。`getRelativeEvidence` 为稳健起见改用 `RiskScore === null || SystemHealth === "UNAVAILABLE"`，对旧记录同样正确。
8. **关于 epsilon 的一个事实：** 简报里举的 `(5e-7, 0.999999)` 在 vision fresh / telemetry missing 下分母是 `5e-7 > 1e-9`，按契约**本来就是 available**，所以它并不能区分 `=== 0` 与 `<= epsilon`。我的 epsilon 测试用的是 `1e-10`（M2 变异证明它能抓）以及恰好 `1e-9`（`<=`，不可用）与 `1.1e-9`（可用）。Task 3 的 Python 侧边界测试请用这几个值，不要用 `5e-7`。
9. **fixture 的 JSON import 没有 `@types/node`**，所以用 `import ... from "../fixtures/fusion_vectors.json"`（`resolveJsonModule` 已开）而非 `fs`；用 `as unknown as FusionVector[]` 收窄类型，没有 `any`。

### 7.2 `tsc --noEmit` 完整错误清单（Task 6 的工作表）

命令：`rtk proxy npx tsc --noEmit`，exit 2。HEAD 基线为零错误。去重键 `file:line:col`。

| # | 位置 | 错误码 | 信息 |
|---|---|---|---|
| 1 | `frontend/src/App.tsx:62:7` | TS2345 | Argument of type 'RiskLevel \| null' is not assignable to parameter of type 'RiskLevel'. |
| 2 | `frontend/src/components/AlertBanner.tsx:35:39` | TS2345 | Argument of type 'number \| null' is not assignable to parameter of type 'number'. |
| 3 | `frontend/src/components/AlertBanner.tsx:41:15` | TS2322 | Type 'string \| null' is not assignable to type 'string'. |
| 4 | `frontend/src/components/AlertBanner.tsx:41:44` | TS2322 | Type 'AlertSeverity \| null' is not assignable to type 'PillTone \| undefined'. |
| 5 | `frontend/src/utils/export.ts:57:44` | TS2538 | Type 'null' cannot be used as an index type. |
| 6 | `frontend/src/views/ExplanationView.tsx:142:41` | TS2345 | Argument of type 'DominantEvidence \| null' is not assignable to parameter of type 'DominantEvidence'. |
| 7 | `frontend/src/views/ExplanationView.tsx:159:40` | TS2345 | Argument of type 'number \| null' is not assignable to parameter of type 'number'. |
| 8 | `frontend/src/views/ExplanationView.tsx:164:17` | TS2322 | Type 'string \| null' is not assignable to type 'string'. |
| 9 | `frontend/src/views/ExplanationView.tsx:165:17` | TS2322 | Type 'RiskLevel \| null' is not assignable to type 'PillTone \| undefined'. |
| 10 | `frontend/src/views/ExplanationView.tsx:171:39` | TS2345 | Argument of type 'string \| null' is not assignable to parameter of type 'string'. |
| 11 | `frontend/src/views/ExplanationView.tsx:172:17` | TS2322 | Type 'AlertSeverity \| null' is not assignable to type 'PillTone \| undefined'. |
| 12 | `frontend/src/views/ExplanationView.tsx:221:43` | TS18047 | 'contributions' is possibly 'null'. |
| 13 | `frontend/src/views/ExplanationView.tsx:246:34` | TS18047 | 'contributions' is possibly 'null'. |
| 14 | `frontend/src/views/ExplanationView.tsx:250:34` | TS18047 | 'contributions' is possibly 'null'. |
| 15 | `frontend/src/views/ExplanationView.tsx:256:50` | TS18047 | 'contributions' is possibly 'null'. |
| 16 | `frontend/src/views/ExplanationView.tsx:258:50` | TS18047 | 'contributions' is possibly 'null'. |
| 17 | `frontend/src/views/ExplanationView.tsx:260:46` | TS2345 | Argument of type 'number \| null' is not assignable to parameter of type 'number'. |
| 18 | `frontend/src/views/ExplanationView.tsx:264:51` | TS18047 | 'contributions' is possibly 'null'. |
| 19 | `frontend/src/views/ExplanationView.tsx:266:59` | TS18047 | 'contributions' is possibly 'null'. |
| 20 | `frontend/src/views/ExplanationView.tsx:269:48` | TS2345 | Argument of type 'number \| null' is not assignable to parameter of type 'number'. |
| 21 | `frontend/src/views/ExplanationView.tsx:389:43` | TS18047 | 'contributions' is possibly 'null'. |
| 22 | `frontend/src/views/LiveMonitor.tsx:99:19` | TS2322 | Type 'number \| null' is not assignable to type 'number'. |
| 23 | `frontend/src/views/LiveMonitor.tsx:105:25` | TS2322 | Type 'string \| null' is not assignable to type 'string'. |
| 24 | `frontend/src/views/LiveMonitor.tsx:105:50` | TS2322 | Type 'RiskLevel \| null' is not assignable to type 'PillTone \| undefined'. |
| 25 | `frontend/src/views/LiveMonitor.tsx:106:25` | TS2322 | Type 'string \| null' is not assignable to type 'string'. |
| 26 | `frontend/src/views/LiveMonitor.tsx:108:21` | TS2322 | Type 'string \| null' is not assignable to type 'string'. |
| 27 | `frontend/src/views/LiveMonitor.tsx:109:21` | TS2322 | Type 'AlertSeverity \| null' is not assignable to type 'PillTone \| undefined'. |
| 28 | `frontend/src/views/RiskTrends.tsx:85:40` | TS2345 | Argument of type 'number \| null' is not assignable to parameter of type 'number'. |
| 29 | `frontend/src/views/RiskTrends.tsx:87:27` | TS2322 | Type 'string \| null' is not assignable to type 'string'. |
| 30 | `frontend/src/views/RiskTrends.tsx:87:52` | TS2322 | Type 'RiskLevel \| null' is not assignable to type 'PillTone \| undefined'. |
| 31 | `frontend/src/views/RiskTrends.tsx:91:23` | TS2322 | Type 'string \| null' is not assignable to type 'string'. |
| 32 | `frontend/src/views/RiskTrends.tsx:92:23` | TS2322 | Type 'AlertSeverity \| null' is not assignable to type 'PillTone \| undefined'. |
| 33 | `frontend/src/views/SignalInspector.tsx:75:38` | TS2345 | Argument of type 'number \| null' is not assignable to parameter of type 'number'. |
| 34 | `frontend/src/views/SignalInspector.tsx:80:15` | TS2322 | Type 'string \| null' is not assignable to type 'string'. |
| 35 | `frontend/src/views/SignalInspector.tsx:81:15` | TS2322 | Type 'RiskLevel \| null' is not assignable to type 'PillTone \| undefined'. |

共 35 条（去重键 file:line:col；原始输出 61 行，其余 26 行是 `Type 'null' is not assignable...` 续行）。


**按根因归并（35 条逐条归类，合计 35；Task 6 修一处可消多条）：**

| 根因 | 条数 | 表中位置（file:line:col） |
|---|---|---|
| A. `formatRiskScore(value: number)`（`utils/format.ts:5`）吃到 `RiskScore: number \| null` | 6 | `AlertBanner:35:39`、`ExplanationView:159:40 / 260:46 / 269:48`、`RiskTrends:85:40`、`SignalInspector:75:38` |
| B. `ScoreGauge` 的 `score` prop 吃到 `number \| null` | 1 | `LiveMonitor:99:19` |
| C. `Pill` / `titleCaseToken` 吃到 `RiskLevel \| null`（label 与 tone 各一条） | 8 | `ExplanationView:164:17 / 165:17`、`LiveMonitor:105:25 / 105:50`、`RiskTrends:87:27 / 87:52`、`SignalInspector:80:15 / 81:15` |
| D. `Pill` / `titleCaseToken` 吃到 `AlertSeverity \| null`（label 与 tone 各一条） | 8 | `AlertBanner:41:15 / 41:44`、`ExplanationView:171:39 / 172:17`、`LiveMonitor:108:21 / 109:21`、`RiskTrends:91:23 / 92:23` |
| E. `getEvidenceType()` / `DominantEvidence` 的 `null` 流入 `formatEvidenceType`、`Pill label`、`Record<DominantEvidence,string>` 索引 | 3 | `ExplanationView:142:41`、`LiveMonitor:106:25`、`utils/export.ts:57:44` |
| F. `updateAlertState(prev, level: RiskLevel, now)` 吃到 `RiskLevel \| null`（见 7.1 #4） | 1 | `App.tsx:62:7` |
| G. `computeRiskContributions()` 现返回 `\| null`（见 7.1 #2，可选扩展） | 8 | `ExplanationView:221:43 / 246:34 / 250:34 / 256:50 / 258:50 / 264:51 / 266:59 / 389:43` |

### 7.3 tsc **不会**报、但 null 流入后会静默出错的位置（Task 6 要靠 grep 找，不能靠 tsc）

| 位置 | 问题 |
|---|---|
| `components/AlertBanner.tsx:30` | `` `alert-banner--${latest.AlertSeverity}` `` —— 模板字符串吞下 `null`，得到 `alert-banner--null`，无任何 CSS 规则匹配，不可用窗口会和普通窗口长得一样 |
| `views/RiskTrends.tsx:22` | `record.RiskLevel === label` 的 `distribution()` —— `null` 记录静默掉出所有桶，没有 Unavailable 桶 |
| `views/RiskTrends.tsx:79` | `record.RiskLevel === "High"` 行样式，`null` 静默不命中 |
| `components/TrendChart.tsx:28` | 已有 `SystemHealth === "UNAVAILABLE" ? null : RiskScore`，类型上仍编译，但应改读 `assessment_available` |
| `utils/export.ts:49-50` | `risk_score: record.RiskScore` / `risk_level: record.RiskLevel` —— 类型上通过；CSV 序列化 `null` 的方式必须按「空单元格」统一规则处理 |
| `views/LiveMonitor.tsx:45` | `stale ? "UNAVAILABLE" : latest.SystemHealth` 伪造 health（Task 6 Step 4 已点名） |
| `views/ExplanationView.tsx:100-107` / `:116,:123` | 前端重算 `computeRiskContributions` / `getEvidenceType`（Task 6 Step 5 已点名） |
| `frontend/src/data/preparedSessionInput.test.ts:31` | 唯一失败的断言（7.1 #1） |

## 8. Evidence paths

- 夹具：`/Users/liu/Desktop/FYP2-Live-System/ai/fixtures/fusion_vectors.json`
- 实现：`/Users/liu/Desktop/FYP2-Live-System/ai/src/availability.ts`、`riskLogic.ts`、`evidence.ts`、`types.ts`
- 测试：`/Users/liu/Desktop/FYP2-Live-System/ai/src/availability.test.ts`、`fusionVectors.test.ts`、`riskLogic.test.ts`
- 原始 `tsc` 输出（61 行 / 35 条 error）：`/private/tmp/claude-501/out/tsc.txt`（临时文件，已全文附在下方附录）
- 需求：`.superpowers/sdd/2026-10-12-fyp2-live-system-completion/task-2-brief.md`、`fusion-vectors-table.md`、`global-constraints.md`

夹具与权威表的一致性：写入 JSON 时由脚本从 `fusion-vectors-table.md` 逐行机械解析生成，再由第二段脚本独立重新解析表格并逐字段比对，结果 `fixture matches table: 21/21`。我没有「更正」任何一行。

## 9. Next task dependencies

- **Task 3**（Python 两份移植）：读 `ai/fixtures/fusion_vectors.json`（顶层数组，字段见第 3 节）。`compute_risk_score` 零分母返回 `None`；`map_risk_level` 必须先判 `None`（Python 对 `None < 30` 抛 `TypeError`，与 TS 静默 `true` 方向相反）；`map_system_health` 增加权重参数默认 `0.5/0.5`；`determine_dominant_evidence` 第一分支判 unavailable。epsilon 边界请用 `1e-10` / `1e-9` / `1.1e-9`（见 7.1 #8）。解释文案可参考本实现的 `describeUnavailableCause` 措辞，但 Python 与 TS 文案不需要逐字一致，只需不含 level 词。
- **Task 5**（Alert FSM / EMA）：需要决定不可用窗口如何喂给 `updateAlertState`（7.1 #4）；`AlertSeverity` 在不可用记录上必须保持 `null`。
- **Task 6**（前端）：按 7.2 / 7.3 的清单工作；`availability.ts` 的 `getDisplayState`、`isAssessmentAvailable` 已就绪；读取边界归一化必须在 `isAssessmentAvailable` 之前（7.1 #7）；Task 6 要往 `availability.test.ts` 追加的 grep 断言可直接追加到该文件末尾。

---

## 附录：`rtk proxy npx tsc --noEmit` 原始输出（全文）

```
frontend/src/App.tsx(62,7): error TS2345: Argument of type 'RiskLevel | null' is not assignable to parameter of type 'RiskLevel'.
  Type 'null' is not assignable to type 'RiskLevel'.
frontend/src/components/AlertBanner.tsx(35,39): error TS2345: Argument of type 'number | null' is not assignable to parameter of type 'number'.
  Type 'null' is not assignable to type 'number'.
frontend/src/components/AlertBanner.tsx(41,15): error TS2322: Type 'string | null' is not assignable to type 'string'.
  Type 'null' is not assignable to type 'string'.
frontend/src/components/AlertBanner.tsx(41,44): error TS2322: Type 'AlertSeverity | null' is not assignable to type 'PillTone | undefined'.
  Type 'null' is not assignable to type 'PillTone | undefined'.
frontend/src/utils/export.ts(57,44): error TS2538: Type 'null' cannot be used as an index type.
frontend/src/views/ExplanationView.tsx(142,41): error TS2345: Argument of type 'DominantEvidence | null' is not assignable to parameter of type 'DominantEvidence'.
  Type 'null' is not assignable to type 'DominantEvidence'.
frontend/src/views/ExplanationView.tsx(159,40): error TS2345: Argument of type 'number | null' is not assignable to parameter of type 'number'.
  Type 'null' is not assignable to type 'number'.
frontend/src/views/ExplanationView.tsx(164,17): error TS2322: Type 'string | null' is not assignable to type 'string'.
  Type 'null' is not assignable to type 'string'.
frontend/src/views/ExplanationView.tsx(165,17): error TS2322: Type 'RiskLevel | null' is not assignable to type 'PillTone | undefined'.
  Type 'null' is not assignable to type 'PillTone | undefined'.
frontend/src/views/ExplanationView.tsx(171,39): error TS2345: Argument of type 'string | null' is not assignable to parameter of type 'string'.
  Type 'null' is not assignable to type 'string'.
frontend/src/views/ExplanationView.tsx(172,17): error TS2322: Type 'AlertSeverity | null' is not assignable to type 'PillTone | undefined'.
  Type 'null' is not assignable to type 'PillTone | undefined'.
frontend/src/views/ExplanationView.tsx(221,43): error TS18047: 'contributions' is possibly 'null'.
frontend/src/views/ExplanationView.tsx(246,34): error TS18047: 'contributions' is possibly 'null'.
frontend/src/views/ExplanationView.tsx(250,34): error TS18047: 'contributions' is possibly 'null'.
frontend/src/views/ExplanationView.tsx(256,50): error TS18047: 'contributions' is possibly 'null'.
frontend/src/views/ExplanationView.tsx(258,50): error TS18047: 'contributions' is possibly 'null'.
frontend/src/views/ExplanationView.tsx(260,46): error TS2345: Argument of type 'number | null' is not assignable to parameter of type 'number'.
  Type 'null' is not assignable to type 'number'.
frontend/src/views/ExplanationView.tsx(264,51): error TS18047: 'contributions' is possibly 'null'.
frontend/src/views/ExplanationView.tsx(266,59): error TS18047: 'contributions' is possibly 'null'.
frontend/src/views/ExplanationView.tsx(269,48): error TS2345: Argument of type 'number | null' is not assignable to parameter of type 'number'.
  Type 'null' is not assignable to type 'number'.
frontend/src/views/ExplanationView.tsx(389,43): error TS18047: 'contributions' is possibly 'null'.
frontend/src/views/LiveMonitor.tsx(99,19): error TS2322: Type 'number | null' is not assignable to type 'number'.
  Type 'null' is not assignable to type 'number'.
frontend/src/views/LiveMonitor.tsx(105,25): error TS2322: Type 'string | null' is not assignable to type 'string'.
  Type 'null' is not assignable to type 'string'.
frontend/src/views/LiveMonitor.tsx(105,50): error TS2322: Type 'RiskLevel | null' is not assignable to type 'PillTone | undefined'.
  Type 'null' is not assignable to type 'PillTone | undefined'.
frontend/src/views/LiveMonitor.tsx(106,25): error TS2322: Type 'string | null' is not assignable to type 'string'.
  Type 'null' is not assignable to type 'string'.
frontend/src/views/LiveMonitor.tsx(108,21): error TS2322: Type 'string | null' is not assignable to type 'string'.
  Type 'null' is not assignable to type 'string'.
frontend/src/views/LiveMonitor.tsx(109,21): error TS2322: Type 'AlertSeverity | null' is not assignable to type 'PillTone | undefined'.
  Type 'null' is not assignable to type 'PillTone | undefined'.
frontend/src/views/RiskTrends.tsx(85,40): error TS2345: Argument of type 'number | null' is not assignable to parameter of type 'number'.
  Type 'null' is not assignable to type 'number'.
frontend/src/views/RiskTrends.tsx(87,27): error TS2322: Type 'string | null' is not assignable to type 'string'.
  Type 'null' is not assignable to type 'string'.
frontend/src/views/RiskTrends.tsx(87,52): error TS2322: Type 'RiskLevel | null' is not assignable to type 'PillTone | undefined'.
  Type 'null' is not assignable to type 'PillTone | undefined'.
frontend/src/views/RiskTrends.tsx(91,23): error TS2322: Type 'string | null' is not assignable to type 'string'.
  Type 'null' is not assignable to type 'string'.
frontend/src/views/RiskTrends.tsx(92,23): error TS2322: Type 'AlertSeverity | null' is not assignable to type 'PillTone | undefined'.
  Type 'null' is not assignable to type 'PillTone | undefined'.
frontend/src/views/SignalInspector.tsx(75,38): error TS2345: Argument of type 'number | null' is not assignable to parameter of type 'number'.
  Type 'null' is not assignable to type 'number'.
frontend/src/views/SignalInspector.tsx(80,15): error TS2322: Type 'string | null' is not assignable to type 'string'.
  Type 'null' is not assignable to type 'string'.
frontend/src/views/SignalInspector.tsx(81,15): error TS2322: Type 'RiskLevel | null' is not assignable to type 'PillTone | undefined'.
  Type 'null' is not assignable to type 'PillTone | undefined'.
```
