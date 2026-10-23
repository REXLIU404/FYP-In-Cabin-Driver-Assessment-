# 阶段 1 · 第 5 项（P1-5）技术报告：修正过期的回放期望矩阵 missing_cases.csv，并让它不能再悄悄过期（F1 / Codex R30）

- 分支 `fyp2/live-system`，工作树 `/Users/liu/Desktop/FYP2-Live-System`，开工 HEAD `9f60b72`（与任务要求一致，工作树干净）。
- 日期 2026-10-14。角色：实现者。未派发子 agent。

## 1. 任务编号与名称

P1-5-F1：把 `ai/prototype-data/prepared_sessions/session_001/missing_cases.csv`（回放的逐窗口期望风险 / 证据矩阵）按真实回放流水线的输出重新核对并修正，扩展列以表达「无评估」新契约，并新增一个 vitest 测试逐行断言该 CSV 等于流水线对同一 `window_id` 的真实输出，使矩阵不能再悄悄过期。

## 2. 实现状态

| 简报条目 | 状态 |
|---|---|
| 1. 以真实流水线输出为准，重新核对全部 9 行（不只改 3 行） | 完成：9 行逐行与 25 窗口的真实输出比对，**恰好 3 行错误**（W16、W17、W19），其余 6 行本来就对（第 4.1 节） |
| 2. 新增 `expected_risk_score`（1 位小数；不可用为空单元格）与 `expected_assessment_available`（小写 `true`/`false`），追加在末尾；不可用行：level / dominant 为空单元格、health 为 `UNAVAILABLE`、available 为 `false`；保留现有列及顺序 | 完成 |
| `case` 文字只在与真实行为不符时才改，改了要说明 | 完成：只改了 W19 一行（第 4.2 节说明） |
| 3. 新增 vitest 测试：读 CSV，逐行断言等于流水线对该 `window_id` 的真实输出（level、score、health、dominant、assessment_available） | 完成：`frontend/src/data/missingCases.test.ts`，13 个测试（4 个布局 + 9 个逐行） |
| 4. 期望来自 CSV 本身，实际来自流水线，不得反过来 | 完成：断言左侧（实际）取自 `buildRiskUpdate` 折叠出的记录，右侧（期望）只取自 CSV 单元格；测试里没有 import 任何实现常量来构造期望 |
| 5. 用一句注释点明 W16 依赖现行 stale 档、阶段 5 会改；不跳过、不放宽 W16 断言 | 完成：测试文件头部注释；W16 与其它行用同一条断言，没有任何放宽（第 4.4 节） |
| 验收：W16 改回 `Medium` → 变红 | 完成（M1，第 5.3 节） |
| 验收：W17 改回 `Low` / `Partial evidence` → 变红 | 完成（M2） |
| 验收：删掉任意一行 → 能发现 | 完成：删首行、中间行、末行三种都变红（M3a/b/c） |
| 验收：四项门禁 0 失败；解释 vitest 数字变化 | 完成：vitest 405 → 418（第 6 节） |

## 3. 创建 / 修改的文件

提交内包含 3 个文件：

| 文件 | 性质 |
|---|---|
| `ai/prototype-data/prepared_sessions/session_001/missing_cases.csv` | 修改：+10 / −10（表头 + 9 行全部重写以追加两列；其中 3 行的既有列内容有改动，W19 的 `case` 文字有改动） |
| `frontend/src/data/missingCases.test.ts` | 新建：117 行 |
| `docs/fyp2/implementation/phase1-05-f1.md` | 新建：本报告 |

未触碰：`ai/src/`、`frontend/src/data/preparedSessionInput.ts`（含其中提到 `missing_cases.csv` 的注释）、`backend/`、`docs/fyp2/review/`、`ml/outputs/`、主仓库、计划文档与任何 SDD 登记文件（登记留给控制者）。

## 4. 实现摘要

### 4.1 逐行核对（以真实回放流水线输出为准）

真实输出的取得方式：在 `git archive HEAD` 的隔离副本里放一个临时的 dump 测试，用与 `preparedSessionInput.test.ts` **同一种折叠方式**（`PREPARED_SESSION_WINDOWS.forEach` → `buildRiskUpdate(window, "session_001", DEFAULT_CONFIG, previous, index + 1)`，把上一条记录传给下一条以走 EMA 链）打印全部 25 个窗口。真实工作树里没有留下这个 dump 文件。

| W | 场景（case） | 旧矩阵：level / health / dominant | 真实输出：score / level / health / dominant / available | 结论 |
|---|---|---|---|---|
| 1 | Calm baseline (low risk) | Low / FULL / Low observed risk | 6.5 / Low / FULL / Low observed risk / true | 原本就对，补分数 |
| 7 | Visual distraction emerging | Medium / FULL / Vision-dominant | 31 / Medium / FULL / Vision-dominant / true | 原本就对，补分数 |
| 10 | Aggressive telemetry high risk | High / FULL / Telemetry-dominant | 74.3 / High / FULL / Telemetry-dominant / true | 原本就对，补分数 |
| 14 | Telemetry missing (vision only) | Medium / DEGRADED / Partial evidence | 48.9 / Medium / DEGRADED / Partial evidence / true | 原本就对，补分数 |
| 15 | Vision missing (telemetry only) | High / DEGRADED / Partial evidence | 70 / High / DEGRADED / Partial evidence / true | 原本就对，补分数 |
| **16** | Telemetry stale | **Medium** / DEGRADED / Partial evidence | 62.5 / **High** / DEGRADED / Partial evidence / true | **level 错**（stale 档仍使分数过 60） |
| **17** | Both modalities missing | **Low** / UNAVAILABLE / **Partial evidence** | **null / null** / UNAVAILABLE / **null** / **false** | **level 与 dominant 错**：旧行还在编码被本分支消除的「Low」捏造读数 |
| **19** | Combined evidence | Medium / FULL / **Combined evidence** | 45 / Medium / FULL / **Vision-dominant** / true | **dominant 错**（P_distraction 0.56 对 P_telemetry 0.34，差 0.22 超过 gap 0.15） |
| 25 | Recovery sustained low | Low / FULL / Low observed risk | 8 / Low / FULL / Low observed risk / true | 原本就对，补分数 |

另外我手工比对了每行的输入列（`vision_available` / `telemetry_available` / `telemetry_age_s`）与 `telemetry.csv` 对应窗口的同名列，9 行全部一致，输入列没有改动。

### 4.2 CSV 的改动

- 表头：保留原 8 列及其顺序，末尾追加 `expected_risk_score`、`expected_assessment_available`（共 10 列）。
- 分数：1 位小数（`31.0`、`70.0`、`45.0`、`8.0`……）；不可用行为空单元格。
- 布尔：小写 `true` / `false`。
- W17 行：`Both modalities missing,17,0,0,999,,UNAVAILABLE,,,false`——level、dominant、score 三个空单元格，health 为 `UNAVAILABLE`，available 为 `false`，与 R1 约定的导出表示一致（`frontend/src/utils/export.ts` 的注释与 `backend/app/routers/export.py`）。
- W16：`Medium` → `High`，补 `62.5`。W19：`Combined evidence` → `Vision-dominant`，补 `45.0`。
- **`case` 文字只改了 W19**：`Combined evidence` → `Both branches active (vision leads)`。原因：该文字是场景名，原意是演示「Combined evidence」类型，但真实行为是 Vision-dominant；保留原文字会让同一行的 `case` 与 `expected_dominant_evidence` 互相矛盾。其余 8 行 `case` 文字与真实行为相符，未动（W16「Telemetry stale」仍准确：`telemetry_age_s` 4 > 3 → stale）。
- 副作用，见第 7 节：矩阵现在不再含有任何 `Combined evidence` 行（回放里唯一的 Combined evidence 窗口是 W18，不在矩阵内）。我没有新增行，因为简报要求「保留现有」。

### 4.3 新测试 `frontend/src/data/missingCases.test.ts`

构造：`import missingCasesCsv from ".../missing_cases.csv?raw"`（`preparedSessionInput.ts` 已在用同一机制导入 `telemetry.csv`，vitest 与 `tsc` 均可解析），用与 `preparedSessionInput.test.ts` 相同的折叠方式得到 `records`。解析 CSV 用最朴素的逗号切分（矩阵里没有带引号的单元格；若某个单元格将来需要逗号，下面的「每行单元格数」测试会报警）。

两个 `describe`：

**`missing_cases.csv layout`（4 个测试）**
1. 表头逐字等于 10 个列名的字面量（原 8 列顺序不变，两个新列在末尾）。
2. 每个数据行的单元格数等于列数（防止 case 文字里混入逗号而整体错位）。
3. `window_id` 序列逐字等于 `[1, 7, 10, 14, 15, 16, 17, 19, 25]`（任何一行被删除、新增或改号都会被发现）。
4. `expected_risk_score` 每个单元格都匹配 `^(\d+\.\d)?$`——恰好 1 位小数，或空单元格。

**`missing_cases.csv expectations equal the real replay output`（9 个测试，`it.each`，每行一个）**
- 按 `record.window_id === Number(row.window_id)` 找到流水线记录（找不到就抛错）。
- 先断言 `expected_assessment_available` 的字面量只能是 `"true"` 或 `"false"`。
- 再用 `toEqual` 比较 `{RiskScore, RiskLevel, SystemHealth, DominantEvidence, assessment_available}`：
  - 实际：取自 `record`；
  - 期望：`expected_risk_score` 空 → `null`，否则 `Number(...)`；`expected_risk_level` / `expected_dominant_evidence` 空 → `null`，否则原字符串；`expected_system_health` 原字符串；`expected_assessment_available === "true"`。
- 用 `toEqual` 一个对象而不是五条独立断言，是为了让失败时一次性给出完整的 `- Expected / + Received` 差异（第 5.3 节附了两个实际失败输出）。
- 测试标题用 `it.each` 的 `%s` 格式（`W16 (Telemetry stale)`），失败时可直接定位到行。

### 4.4 与裁定 A 的关系

测试文件头部注释写明：W16 钉的是**现行**行为（`telemetry_age_s` 4 > 3 → stale 0.45 档 → High / 62.5）；阶段 5 实施裁定 A 后过期证据按 missing 计分，W16 的分数会变为 60.0，health / dominant 也可能随之变化，届时本测试会如实变红，应更新 CSV 行，不得跳过或放宽。

我用一个变异做了粗略演练（M18：在隔离副本里把 `freshnessStatus` 的 `stale` 改成 `missing`）：W16 唯一变化的是分数 **62.5 → 60**，level 仍为 High，health 仍为 DEGRADED，dominant 仍为 Partial evidence。这只说明「分数会变」这一半成立；裁定 A 的真实实现（除 missing 外还要标记 expired）可能让 health / dominant 也变，需要阶段 5 当时重新计算，我没有声称它们不变。

## 5. 执行的测试（精确命令）

### 5.1 新测试单独运行（真实工作树）

```
cd /Users/liu/Desktop/FYP2-Live-System
./node_modules/.bin/vitest run --no-cache frontend/src/data/missingCases.test.ts --reporter=verbose
```
结果：`Test Files 1 passed (1)`，`Tests 13 passed (13)`。

### 5.2 取得真实输出与 vitest 基线（隔离副本，均未触碰真实工作树）

- 真实输出 dump：`D=$(mktemp -d) && git archive HEAD | tar -x -C "$D"`，链接 `.venv`、`node_modules`，在 `$D/frontend/src/data/` 放一个临时 `zz_dump.test.ts`（打印 25 窗口的 `window_id | RiskScore | RiskLevel | SystemHealth | DominantEvidence | assessment_available | 两个 freshness | P_distraction | P_telemetry_anomaly`），然后 `cd "$D" && ./node_modules/.bin/vitest run --no-cache frontend/src/data/zz_dump.test.ts`。第 4.1 节的表格即来自这次输出。
- vitest 基线：另一个干净的 `git archive HEAD` 副本（不含我的任何文件），`./node_modules/.bin/vitest run --no-cache`，结果 `Test Files 15 passed (15)`，`Tests 405 passed (405)`。

### 5.3 验收与附加变异（隔离副本）

隔离副本是 `git archive HEAD` 的内容，再把我的两个新文件（`missing_cases.csv`、`missingCases.test.ts`）拷进去；先确认未变异时 `vitest run --no-cache frontend/src/data/missingCases.test.ts` 为 `13 passed`。每个变异用同一个小脚本做：断言待替换字符串在文件中恰好出现一次 → 替换 → 运行上述命令 → 把文件从真实工作树（我的两个文件）或干净基线副本（其它文件）还原 → 用 `filecmp` 确认还原后字节一致。**共 25 次变异运行（M1–M22，其中 M3 为 a/b/c 三次，另有 M15b），脚本打印的还原核对全部为 `identical: True`**；此外为取得 M1、M18 的完整差异文本各重跑一次，手工还原后用 `cmp` 确认一致。

| # | 变异（改的文件与内容） | 观察到的结果 |
|---|---|---|
| **M1**（验收） | CSV：W16 `High` → `Medium` | `1 failed \| 12 passed`；变红的是 `W16 (Telemetry stale)`，差异为 `- "RiskLevel": "Medium"` / `+ "RiskLevel": "High"` |
| **M2**（验收） | CSV：W17 改回 level=`Low`、dominant=`Partial evidence` | `1 failed \| 12 passed`；变红的是 `W17 (Both modalities missing)` |
| **M3a**（验收） | CSV：删掉 W10 行（中间） | `1 failed \| 11 passed (12)`；变红的是 `covers exactly the nine documented windows`（`[1,7,14,15,16,17,19,25]` ≠ 期望） |
| **M3b**（验收） | CSV：删掉 W25 行（末行） | 同上，`[1,7,10,14,15,16,17,19]` |
| **M3c**（验收） | CSV：删掉 W1 行（首行） | 同上，`[7,10,14,15,16,17,19,25]` |
| M4 | CSV：W19 dominant 改回 `Combined evidence` | `1 failed`；`W19 (Both branches active (vision leads))` |
| M5 | CSV：W16 分数 `62.5` → `60.0` | `1 failed`；`W16`，`RiskScore: 62.5` ≠ `60` |
| M6 | CSV：W7 分数写成 `31`（数值相等，仅格式不对） | `1 failed \| 12 passed`；**只有**「1 位小数」那条布局测试变红，逐行相等测试仍绿——证明格式检查不是多余的 |
| M7 | CSV：W17 `false` → `true` | `1 failed`；`W17` |
| M8 | CSV：W17 level 写成文字 `null` 而非空单元格 | `1 failed`；`W17` |
| M9 | CSV：W17 分数写 `0.0`（捏造读数）而非空 | `1 failed`；`W17`，`null` ≠ `0` |
| M10 | CSV：W17 health `UNAVAILABLE` → `DEGRADED` | `1 failed`；`W17` |
| M11 | CSV：W1 布尔写成 `True` | `1 failed`；`W1`，`expected ['true','false'] to include 'True'` |
| M12 | CSV：W1 分数 `6.5` → `6.6` | `1 failed`；`W1` |
| M13 | CSV：新增一个**正确**的 W18 行 | `1 failed \| 13 passed (14)`；只有 window 序列测试变红——如实记录：新增行必须同时更新测试里的 id 字面量（有意为之，见第 7 节第 2 条） |
| M14 | CSV 表头：交换 `vision_available` 与 `telemetry_available` | `1 failed`；表头测试 |
| M15 | CSV 表头：把 `expected_assessment_available` 改名 | `10 failed \| 3 passed`；表头测试 + 全部 9 个逐行测试 |
| M15b | CSV 表头：两个新列顺序对调（值没动） | `11 failed \| 2 passed`；表头、1 位小数、全部 9 个逐行测试 |
| M16 | CSV：W1 的 case 文字里混入逗号 | `4 failed \| 9 passed`；「每行单元格数」「window 序列」「1 位小数」与 W1 逐行测试 |
| M17 | `preparedSessionInput.ts`：stale 阈值 `> 3` → `> 5`（W16 变 fresh） | `1 failed`；`W16`，`RiskScore: 64` ≠ `62.5` |
| M18 | `preparedSessionInput.ts`：`age > 3` 改判 `missing`（粗略模拟裁定 A） | `1 failed`；`W16`，`60` ≠ `62.5`，其余三个字段不变（见第 4.4 节） |
| M19 | `telemetry.csv`：W10 `p_safe` `0.18` → `0.19` | `1 failed`；`W10`，`73.8` ≠ `74.3` |
| M20 | `riskLogic.ts`：`thresholdHigh` `60` → `65` | `1 failed`；`W16`（62.5 变 Medium） |
| M21 | `riskLogic.ts`：分数舍入 `round1` 改为 0 位 | `4 failed`；`W1`、`W10`、`W14`、`W16`（如 `74` ≠ `74.3`） |
| M22 | `riskLogic.ts`：不可用时 `return null` 改为 `return 0`（旧的捏造读数） | `1 failed`；`W17`，`RiskScore: +0` ≠ `null` |

其中 M1–M3 是简报的三条验收，M4–M16 逐一守护新增的每一条断言与每一个新列，M17–M22 证明「实际值」确实来自真实流水线（改回放输入、改阈值、改舍入、改不可用语义，矩阵测试都会随之变红）。

### 5.4 四项门禁（真实工作树，提交前）

```
cd /Users/liu/Desktop/FYP2-Live-System
export PYTHONDONTWRITEBYTECODE=1
(cd backend && TMPDIR=$(mktemp -d) PYTHONPATH=. ../.venv/bin/python -m pytest tests -q -p no:cacheprovider)
./node_modules/.bin/vitest run --no-cache
./node_modules/.bin/tsc --noEmit
./node_modules/.bin/eslint .
```

另外检查了格式：`./node_modules/.bin/prettier --ignore-path /dev/null --check frontend/src/data/missingCases.test.ts frontend/src/data/preparedSessionInput.test.ts` → `All matched files use Prettier code style!`（仓库的 `.prettierignore` 把 `frontend/` 整个排除了，所以不加 `--ignore-path /dev/null` 的检查是空检查）。

## 6. PASS / FAIL / SKIP 计数

| 门禁 | 结果 |
|---|---|
| pytest（真实工作树，有模型文件） | **525 passed, 0 failed, 0 skipped**，1 个 `StarletteDeprecationWarning`（既有，与本项无关） |
| vitest | **418 passed / 0 failed**（16 个测试文件） |
| `tsc --noEmit` | 退出码 0 |
| `eslint .` | 退出码 0 |

**数字变化的解释**

- **vitest 405 → 418，+13，15 → 16 个测试文件**。405 / 15 是我在干净的 `git archive HEAD` 副本上实测的基线（第 5.2 节），不是推算。+13 全部来自新文件 `missingCases.test.ts`：4 个布局测试 + 9 个逐行测试（矩阵 9 行，每行一个 `it.each` 用例）。没有删除、替换或修改任何既有测试；`preparedSessionInput.test.ts` 仍是 11 个测试。
- **pytest 525，与 P1-4 报告的 525 持平**。本项没有改动任何 `backend/` 文件，`backend/`、`ml/`、`scripts/`、`prototype-tests/` 下也没有任何文件引用 `missing_cases`（`grep -rln 'missing_cases'` 无输出），所以 pytest 数量不应变化。我没有在 `HEAD` 上单独重跑一次 pytest 基线，这里的「持平」依据是上面两点加上 P1-4 报告的同一数字。
- tsc、eslint 均为 0。

## 7. 遗留问题

1. **矩阵的输入列没有被测试对照 `telemetry.csv`**。简报要求的是对 level / score / health / dominant / available 五项的逐行断言，我按此实现。`vision_available` / `telemetry_available` / `telemetry_age_s` 三个输入列目前与 `telemetry.csv` 一致（我手工核对过，第 4.1 节），但没有测试守护；不过它们若与回放输入脱节，期望输出列几乎必然跟着不相等，因此实际风险较低。
2. **窗口集合被钉成字面量**，新增或删除任意一行都必须同步改测试里的 id 数组（M13 实测）。这是为了满足「删掉任意一行必须能发现」。代价是新增矩阵行时多一步；这是有意的取舍。
3. **矩阵现在没有 `Combined evidence` 行**（原 W19 行是唯一一个自称 Combined evidence 的行，真实行为却是 Vision-dominant）。回放里真正的 Combined evidence 窗口是 W18（70.0 / High / FULL）。简报要求保留现有行，我没有新增；如果希望矩阵覆盖五种 dominant 类型，可以在后续追加 W18 并同步更新窗口 id 字面量。
4. **`frontend/src/data/preparedSessionInput.ts` 第 91–92 行的注释**仍写「See …/missing_cases.csv for the per-window expected risk/evidence matrix」。这句话现在是真的，而且有了测试守护；简报引用的是「:87」，当前文件里已经是 91–92 行。我没有改这行注释（不属于简报要求），可由控制者决定是否补一句「由 missingCases.test.ts 守护」。
5. **阶段 5 裁定 A 落地时本测试预期变红**（第 4.4 节）。M18 只演示了分数 62.5 → 60 这一半，health / dominant 是否变化取决于实现。
6. **窗口号约定**：流水线记录的 `window_id` 是 `index + 1`（App 与既有测试都如此），而矩阵的 `window_id` 对应的是按 `telemetry.csv` 的 `window_id` 排序后的第 N 个窗口。两者目前一致，因为 `telemetry.csv` 的 `window_id` 恰为 1..25 连续。本测试沿用与既有测试同样的假设，没有额外断言这一点。
7. **其它文档里的历史描述未改**：`docs/fyp2/implementation/TASK_1_TO_6_SUMMARY.md` 第 6 节 F1 仍按「未解决」描述旧矩阵；`.planning/system-track/task_plan.md:46` 的 F1 复选框、SDD 登记文件与计划文档的 F1 条目均未改，登记留给控制者。
8. 隔离副本按规则保留未删除（第 8 节）。

## 8. 证据路径

- 修正后的矩阵：`/Users/liu/Desktop/FYP2-Live-System/ai/prototype-data/prepared_sessions/session_001/missing_cases.csv`
- 新测试：`/Users/liu/Desktop/FYP2-Live-System/frontend/src/data/missingCases.test.ts`（布局测试约第 51–86 行，逐行测试约第 88–116 行，头部注释含 W16 / 裁定 A 说明）
- 回放流水线：`/Users/liu/Desktop/FYP2-Live-System/frontend/src/data/preparedSessionInput.ts`、`/Users/liu/Desktop/FYP2-Live-System/ai/src/riskLogic.ts`；既有对照测试：`frontend/src/data/preparedSessionInput.test.ts`
- 隔离副本（均在 `/var/folders/0k/dtzqmkm53vqgg530vd7h3fmr0000gn/T/` 下）：
  - `tmp.LCF6JaPmg9`：真实输出 dump（含临时 `zz_dump.test.ts`，仅存在于该副本）
  - `tmp.yBpodSQmNh`：干净 `HEAD` 基线副本（vitest 405 / 15 个文件）
  - `tmp.ltZxO73WvJ`：变异副本（最终状态已还原，与真实工作树的两个新文件及 `HEAD` 其余文件字节一致）
- 本报告：`/Users/liu/Desktop/FYP2-Live-System/docs/fyp2/implementation/phase1-05-f1.md`

## 9. 下一项依赖

- 本项不依赖也不阻塞其它阶段 1 项：只改一个数据文件并新增一个测试，没有改动任何实现、契约或其它 fixture。
- 对评审者：请在自己的隔离副本里独立复现简报的三条验收——W16 改回 `Medium`、W17 改回 `Low` / `Partial evidence`、删掉任一行——均应变红；再抽查 M6（只改格式）、M13（新增正确行）、M18（裁定 A 模拟）这三个最能说明测试边界的变异。
- 阶段 5 实施裁定 A 时：`missingCases.test.ts` 的 W16 行预期变红；请按实际流水线输出重算该行（至少分数 62.5 → 60.0，并核对 level / health / dominant），不要放宽断言。
