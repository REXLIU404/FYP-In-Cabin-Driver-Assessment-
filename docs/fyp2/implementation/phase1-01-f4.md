# 阶段 1 · 第 1 项技术报告：F4 —— 把 ROUND_HALF_UP 写回计划与 SDD 全局约束

## 1. 任务编号与名称

- 任务编号：阶段 1 · P1-1 · **F4**
- 名称：把 ROUND_HALF_UP 写回计划与 SDD 全局约束
- 起点：分支 `fyp2/live-system`，HEAD `e326449`（开工前已确认，工作树干净）
- 性质：**只改文档，不改任何代码**

背景：Task 5 把三份融合实现（`ai/src/riskLogic.ts`、`backend/app/fusion.py`、`ai/reference/risk_logic.py`）的舍入统一成 ROUND_HALF_UP，这是控制者在派发时口头下达的裁定，从未写回计划。结果是计划的 Global Constraints 与 SDD 的 `global-constraints.md` 都没有舍入规则，而 Task 5 的 brief 甚至写着「不要顺手整理 EMA 的舍入」。由计划生成的 Task 7–10 brief 若不携带舍入模式，后续实现可能重新引入 `round()` / `toFixed`，导致跨语言分歧回归。Codex 审阅 R30 确认这是有意的数值改变。

## 2. 实现状态

**DONE**（简报要求的四项文档改动全部完成，验收逐条核对过，见第 5、6 节）。

| 简报条目 | 状态 |
|---|---|
| 1. 计划 Global Constraints 新增舍入规则条 | 完成 |
| 2. 计划「门禁命令」条改为精确命令并说明原因 | 完成 |
| 3. 重新生成 SDD `global-constraints.md`（git 忽略） | 完成，与计划该节逐字一致 |
| 4. 给 Task 5 brief 顶部加一行说明（git 忽略） | 完成，原文未改 |

## 3. 创建 / 修改的文件

进入提交的文件（2 个）：

- 修改：`docs/plans/2026-10-12-fyp2-live-system-completion.md`（`git diff --stat`：14 行新增、1 行删除，仅 `## Global Constraints` 一节内）
- 新建：`docs/fyp2/implementation/phase1-01-f4.md`（本报告）

**不进入提交**的文件（被主仓库 `.git/info/exclude` 中的 `.superpowers/` 规则忽略，这是预期）：

- 重写：`.superpowers/sdd/2026-10-12-fyp2-live-system-completion/global-constraints.md`（119 行 → 135 行）
- 修改：`.superpowers/sdd/2026-10-12-fyp2-live-system-completion/task-5-brief.md`（59 行 → 60 行，仅在顶部插入 1 行）

没有触碰任何代码、测试、`ml/outputs/`、`docs/fyp2/review/`、主仓库。

## 4. 实现摘要

### 4.1 计划：新增舍入规则条（紧接「RiskScore 量纲 0–100」之后）

新条目包含简报要求的全部事实：

- 舍入模式统一为 **ROUND_HALF_UP**：RiskScore 保留 **1 位**小数，EMA 平滑值保留 **3 位**小数。
- 实现位置（写入前已逐一在源码中核实存在）：
  - Python：`backend/app/fusion.py:40` 与 `ai/reference/risk_logic.py:46` 的 `round_half_up(value, places)`，做法是 `Decimal(str(value)).quantize(..., rounding=ROUND_HALF_UP)`；
  - TypeScript：`ai/src/riskLogic.ts:46` 导出的 `roundHalfUp(value, places)`。
- 禁止：在 score、概率、EMA 值上使用 Python 内置 `round()`（banker's rounding），或 JS 的 `toFixed` / `Math.round(v*100)`；前端显示 score、概率、EMA 值一律用 `roundHalfUp`。
- 有意的数值改变（Codex R30 确认）：相对旧 Python 改变约 17.0% 的分数网格，相对旧 TS 约 13.0%，556 个网格点的 RiskLevel 改变。三种语言现在逐值一致。数字已与 `docs/fyp2/implementation/task-05-acceptance.zh.md:54`、`task-05.md:110` 交叉核对（170,228 格 = 17.0%，130,174 格 = 13.0%，1,001×1,001 网格，556 格等级改变），条目里加注了「1,001×1,001 网格」以免被误当作运行分布上的比例。
- 来源：Task 5 的控制者裁定（SDD ledger），Codex R30 确认，阶段 1 F4 写回。
- 额外一句（简报第 4 项的计划侧对应）：Task 5 小节及其 SDD brief 中「不要顺手整理 EMA 的舍入」是旧指示，已被本条取代。这样计划不会在不动 Task 5 小节原文的前提下自相矛盾。

### 4.2 计划：门禁命令条

旧写法 `npx vitest run`、`npx tsc --noEmit`、`npx eslint ai frontend`、`cd backend && ...` 替换为 `phase1-context.md` 里的精确五行命令（`export PYTHONDONTWRITEBYTECODE=1`、带一次性 `TMPDIR` 与 `-p no:cacheprovider` 的 pytest、`./node_modules/.bin/vitest run --no-cache`、`./node_modules/.bin/tsc --noEmit`、`./node_modules/.bin/eslint .`），并写明原因：本机 `rtk` 包装器会改写 `npx`；`--no-cache` 避免 vitest 经 `node_modules` 符号链接写入只读主仓库。保留了原有的「`npm test` 不做类型检查，`tsc` 必须单独跑」。

### 4.3 SDD `global-constraints.md`

整体替换为计划 `## Global Constraints` 一节（第 15 行标题至第 148 行，即 `## Review Focus` 之前，含末尾的 `---` 分隔与空行），文件第 1 行加一行 HTML 注释，写明生成来源、日期 2026-10-13、阶段 1 F4，以及它取代了缺少舍入规则、且保留 D13 可达性旧主张的 10-12 旧副本。计划里该段 D13 旧主张本来就已用删除线标注并附 R4 更正，照抄即可，因此新文件中该主张只以 `~~...~~` 形式出现。

为了让「不再出现未被删除线标注的『到不了 stale』主张」的检索不被我自己的注释命中，第 1 行注释没有复述那句话，只写「已被 R4 推翻的 D13 可达性主张」。

### 4.4 Task 5 brief

只在文件最顶部插入 1 行引用块，说明该 brief 关于舍入的指示（原第 42 行「不要顺手『整理』EMA 的舍入」，现为第 43 行）已被 ROUND_HALF_UP 裁定取代，以计划 Global Constraints 的舍入条为准，「以下原文保持不变」。原文 59 行与改动前逐字相同（已用 `diff` 对比备份验证）。

## 5. 执行的测试（精确命令）

### 5.1 四项门禁（改动完成后各跑一次，均在 `/Users/liu/Desktop/FYP2-Live-System`）

```
export PYTHONDONTWRITEBYTECODE=1
(cd backend && TMPDIR=$(mktemp -d) PYTHONPATH=. ../.venv/bin/python -m pytest tests -q -p no:cacheprovider)
./node_modules/.bin/vitest run --no-cache
./node_modules/.bin/tsc --noEmit
./node_modules/.bin/eslint .
```

### 5.2 验收检查（均为我实际运行的命令）

- 逐字一致：`diff <(sed -n '15,148p' docs/plans/2026-10-12-fyp2-live-system-completion.md) <(sed -n '2,$p' .superpowers/sdd/2026-10-12-fyp2-live-system-completion/global-constraints.md)`，无输出，退出码 0。
- 关键词检索（计划 `## Global Constraints` 一节 / SDD 文件）：`ROUND_HALF_UP` 2 / 2 处，`round_half_up` 1 / 1 处，`roundHalfUp` 2 / 2 处。
- `npx` 检索：该节与 SDD 文件里各只出现 1 处，位于「原因」说明句中（「本机 `rtk` 包装器会改写 `npx`」，简报明确要求这样写）；**没有任何门禁命令以 `npx` 开头**。
- 未删除线的旧主张：对 SDD 文件检索「到不了 stale」，仅命中第 36 行，该行是 `~~...~~` 删除线包裹的 R1 旧段落（其后紧跟 R4 更正）。
- 负对照：把 SDD 文件副本里的 `ROUND_HALF_UP` 替换为 `ROUND_HALF_EVEN` 后，同一条 `diff` 报告有差异。这说明逐字一致检查本身能发现漂移。副本放在 scratchpad，没有动真实文件。
- `git diff --stat`：仅 `docs/plans/2026-10-12-fyp2-live-system-completion.md`，14 insertions / 1 deletion。

### 5.3 变异验证

简报没有列出任何变异（本项不改代码、不新增测试）。因此没有执行简报要求的变异。上面的负对照是我为验证检查手段自身而加的，不替代变异。

## 6. PASS / FAIL / SKIP 计数

| 门禁 | 观察到的结果 | 基线（`e326449`） | 变化 |
|---|---|---|---|
| pytest | **506 passed, 1 warning**；0 failed，0 skipped；退出码 0 | 506 / 0 | 无 |
| vitest | **15 个文件、394 tests passed**；退出码 0 | 394 / 0 | 无 |
| tsc --noEmit | 无输出，退出码 0 | 0 | 无 |
| eslint . | 无输出，退出码 0 | 0 | 无 |

测试数没有变化，符合预期：本项只改文档，没有新增或替换任何测试。pytest 的那条 warning 是 `starlette.testclient` 对 `httpx` 的弃用提示，与本项无关。

## 7. 遗留问题

1. **现有代码里有一处违反新规则的写法，本项未改（按简报只改文档）**：`ai/src/riskLogic.ts:201` 的 `asPercent = (value) => \`${Math.round(value * 100)}%\``，用于 `ai/src/riskLogic.ts:254`、`:257` 的解释文字里显示 `P_distraction` / `P_telemetry_anomaly`。新规则禁止在概率上使用 `Math.round(v*100)`。对照：`frontend/src/utils/format.ts:31` 已经用 `Math.round(roundHalfUp(value, 2) * 100)`。建议单独开一项把 `asPercent` 改为经 `roundHalfUp`，并补一个落在半点上的测试。注意这可能改变解释文字里的个别百分比，需要同步相关测试。
2. **计划 Task 5 小节原文（现为第 545 行）仍保留「不要顺手整理 EMA 的舍入」**。简报没有授权修改 Task 5 小节，所以我保留了它（它是已执行任务的历史记录），只在新的舍入条里写明它已被取代。若希望计划内部彻底无矛盾，需要另行决定是否给该句加删除线。
3. **「前端显示」的范围**：计划里我把「前端显示一律用 `roundHalfUp`」限定为「前端显示 score、概率、EMA 值」。`frontend/src/components/TelemetrySummary.tsx`、`VehicleDynamics.tsx` 对原始遥测传感读数（速度、加速度、刹车等）使用 `toFixed` / `Math.round`，它们不是 score、概率或 EMA 值，不在禁止范围内。如果审阅者希望规则覆盖所有数值显示，需要另行裁定。
4. 计划后半部分的 R4 记录（现为第 968 行）仍把 F4 描述为「进入审阅修复批次」，没有标注 F4 已完成。简报没有要求更新它，所以没动；完成登记应由控制者在 SDD ledger（`progress.md`，git 忽略）里做。
5. 计划 Global Constraints 里 EMA 分歧表使用的 `file:line` 引用是 R1 时点的，部分行号已随 Task 5 之后的代码移动而过期。本项未处理。
6. `.superpowers/` 被主仓库的 `.git/info/exclude` 忽略，这意味着两个 SDD 文件的改动不在版本控制里。已把改动前的备份留在 scratchpad（见第 8 节），需要回滚时可恢复。

## 8. 证据路径

- 计划（已提交内容）：`/Users/liu/Desktop/FYP2-Live-System/docs/plans/2026-10-12-fyp2-live-system-completion.md`
- SDD 约束文件（git 忽略）：`/Users/liu/Desktop/FYP2-Live-System/.superpowers/sdd/2026-10-12-fyp2-live-system-completion/global-constraints.md`
- Task 5 brief（git 忽略）：`/Users/liu/Desktop/FYP2-Live-System/.superpowers/sdd/2026-10-12-fyp2-live-system-completion/task-5-brief.md`
- 门禁原始输出与改动前备份（scratchpad，目录 `/private/tmp/claude-501/-Users-liu-Desktop-FYP-In-Cabin-Driver-Assessment--1--claude-worktrees-exciting-keller-fdf913/a1949e26-b3d7-4f7f-bd9f-059bf8cb6f0e/scratchpad/`）：
  - `gate-pytest.log`、`gate-vitest.log`、`gate-tsc.log`、`gate-eslint.log`
  - `global-constraints.old.md`（改动前的 SDD 旧副本）、`task-5-brief.orig.md`（改动前的 Task 5 brief）、`gc-negctl.md`（负对照副本）
- 舍入数字的出处：`docs/fyp2/implementation/task-05-acceptance.zh.md:54`、`docs/fyp2/implementation/task-05.md:110`、`docs/fyp2/implementation/TASK_1_TO_6_SUMMARY.md:190`；Codex R30：`docs/fyp2/review/CODEX_INDEPENDENT_AUDIT_REVIEW_2026-10-13.md:100`
- 实现位置核实：`backend/app/fusion.py:40`、`ai/reference/risk_logic.py:46`、`ai/src/riskLogic.ts:46`、`backend/app/inference.py:120`（EMA 经 `fusion.round_half_up(..., 3)`）

## 9. 下一项依赖

- F4 不依赖其他项，也不被其他项的代码依赖。
- 之后由计划生成的 Task 7–10 brief 以及任何重新生成的 SDD 约束文件，都会带上舍入规则与精确门禁命令。
- 建议把遗留问题 1（`asPercent` 的 `Math.round(v*100)`）作为独立后续项排期，否则新规则与现有代码存在一处已知不一致。
- 本阶段后续各项（R08、T-gap、I-teps、F1）的 brief 已在同目录，不依赖本项产出。

---

# 修复轮 1

起点：HEAD `f289d66`（开工前已确认，工作树干净）。审阅者提出 1 条 Important，要求修复；其余无。

## R1.1 审阅发现（逐字）

> （Important，`ai/src/riskLogic.ts:61`）F4 现在把「EMA 保留 3 位、ROUND_HALF_UP、禁止 JS toFixed、三种实现逐值一致」写进了计划 Global Constraints，但 TS 侧 EMA 舍入没有任何测试守着。复现：在隔离副本里把 `const round3 = (value: number) => roundHalfUp(value, 3);` 改成 `Number(value.toFixed(3))`，vitest 仍然 15 个文件 / 394 条全绿。原因是共享夹具的 EMA 平局用例 `half-up-tie-in-the-ema`（`ai/fixtures/ema_parity_vectors.json:328`，0.0625）在二进制里可以精确表示，toFixed 遇到它也会进位，所以这条用例只能区分 banker's 和 half-up，区分不了 toFixed 和 roundHalfUp。具体出错的输入：alpha=0.35，previous=0.0，current=0.11，EMA=0.0385。Python `round_half_up` 得 0.039，toFixed 得 0.038。只要有人按新规则明令禁止的写法回退，跨语言 P_distraction 就会分歧，而没有任何测试会变红。

审阅者标注该问题是旧问题、不由 F4 引入、不在「只改文档」范围内，建议单独开一项。本轮按控制者指令修复它。注意范围：本轮**只改了测试夹具与一个测试文件，没有改任何生产代码**（`ai/src/riskLogic.ts`、`backend/app/*` 一字未动）。

## R1.2 先复现（结论与审阅者一致）

在隔离副本（`git archive HEAD` 解出，`.venv`、`node_modules` 为符号链接）里，只改 `ai/src/riskLogic.ts:61`，夹具与测试保持 HEAD 原样：

```
const round3 = (value: number) => Number(value.toFixed(3));
./node_modules/.bin/vitest run --no-cache
 Test Files  15 passed (15)
      Tests  394 passed (394)
```

确认全绿，发现属实。同时在 node / Python 里验证了审阅者给的输入：

```
node:   raw 0.0385  toFixed3 0.038  Math.round(v*1000)/1000 0.039  String 0.0385
python: raw 0.0385  py round 0.038  half_up 0.039  exact 0.038499999999999999500399638918679556809365749359130859375
```

根因：打印为 `0.0385` 的那个 double，精确值比 0.0385 略小。`toFixed` 与 Python 内置 `round` 看的是精确二进制值，所以得 0.038；`round_half_up` / `roundHalfUp` 看的是最短十进制表示 `0.0385`，所以得 0.039。已有的 0.0625 平局在二进制里精确，因此任何方法遇到它都进位，区分不了。

## R1.3 修改了什么

1. `ai/fixtures/ema_parity_vectors.json`（TS 与 Python 共用的 oracle）：在 `half-up-tie-in-the-ema` 之后新增 2 个用例，每个 2 个窗口（第 1 个窗口是种子，第 2 个是平滑窗口），`ema_alpha` 0.35，权重 0.6 / 0.4，`P_telemetry_anomaly` 0.1：

   | id | 种子 | 第 2 窗口输入 | 十进制精确 EMA | 期望 `P_distraction` | 期望 `RiskScore` | `toFixed(3)` | `Math.round(v*1000)/1000` | Python `round` |
   |---|---|---|---|---|---|---|---|---|
   | `half-up-tie-in-the-ema-below-in-binary` | 0.0 | 0.11 | 0.0385 | 0.039 | 6.3 | 0.038（错） | 0.039（对） | 0.038（错） |
   | `half-up-tie-in-the-ema-after-a-nonzero-seed` | 0.24 | 0.99 | 0.5025 | 0.503 | 34.2 | 0.502（错） | 0.502（错） | 0.502（错） |

   第 1 个用例是审阅者给出的输入，抓 `toFixed`；它抓不到 `Math.round(v*1000)/1000`（0.0385 * 1000 恰好得 38.5）。所以又按同样的方法在 alpha=0.35 的 2 位小数网格上做穷举搜索（`previous` 取 0.00 至 0.99、`current` 取 0.01 至 0.99，每档 0.01，alpha 取 0.35 与 0.5），挑出对 `toFixed` 与 `Math.round` 两者都出错的输入，得到第 2 个用例。期望值是**字面量**，由只用 `decimal.Decimal` 的脚本独立推导（脚本不 import 任何实现代码）：

   ```
   A seed 0.0 cur 0.11 ema_exact 0.0385 ema 0.039 score1 exact 4.00 -> 4.0 score2 exact 6.3400 -> 6.3
   B seed 0.24 cur 0.99 ema_exact 0.5025 ema 0.503 score1 exact 18.400 -> 18.4 score2 exact 34.1800 -> 34.2
   ```

   两个用例的 `RiskScore` 本身都不是平局（6.34、34.18），因此这两个用例只考 EMA 舍入，不混入分数舍入的歧义。夹具里的 `description` 写明了每种错误写法的结果；这些说法已用 node / Python 实测核对（见上表）。

2. `ai/src/emaParity.test.ts`：在 "covers ..." 之后新增 1 个测试 "keeps the two ties that toFixed / Math.round get wrong"，断言这两个 id 仍在夹具里。理由：没有它，有人把这两个用例从夹具删掉，测试仍会全绿（`describe.each` 只对剩下的用例跑）。

Python 一侧**无需改任何测试文件**：`test_ut_ema_parity_01_*` 是对同一夹具的参数化测试，新用例自动被 `run_inference` 与 `ai/reference/risk_logic.py` 两条路径各跑一遍。

## R1.4 执行的命令与输出

### 针对修改的测试

```
./node_modules/.bin/vitest run --no-cache ai/src/emaParity.test.ts
 ✓ ai/src/emaParity.test.ts (13 tests) 4ms
 Test Files  1 passed (1)
      Tests  13 passed (13)

(cd backend && TMPDIR=$(mktemp -d) PYTHONPATH=. ../.venv/bin/python -m pytest tests/test_temporal_contract.py -q -p no:cacheprovider -k "ema_parity")
23 passed, 48 deselected in 0.22s
```

### 变异验证（均在隔离副本里做，真实工作树未触碰）

| # | 变异 | 针对的测试夹具 | 观察到的结果 |
|---|---|---|---|
| M0 | `ai/src/riskLogic.ts:61` -> `Number(value.toFixed(3))` | HEAD 原夹具与测试（复现审阅发现） | vitest 15 个文件 / **394 passed**，**全绿**（发现属实） |
| M1 | 同 M0 | 新夹具 + 新测试 | `Test Files 1 failed \| 14 passed (15)`，`Tests 2 failed \| 395 passed (397)`。两处失败：`half-up-tie-in-the-ema-below-in-binary window 2: expected { P_distraction: 0.038, ...} to deeply equal { P_distraction: 0.039, ...}`；`half-up-tie-in-the-ema-after-a-nonzero-seed window 2: expected { P_distraction: 0.502, ...} to deeply equal { P_distraction: 0.503, ...}`（后者 `RiskScore` 还从 34.2 变成 34.1） |
| M2a | `ai/src/riskLogic.ts:61` -> `Math.round(value * 1000) / 1000` | HEAD 原夹具与测试 | **394 passed，全绿**（说明只有 0.0385 那个用例不够，需要第 2 个） |
| M2b | 同 M2a | 新夹具 + 新测试 | `Tests 1 failed \| 396 passed (397)`，失败的是 `half-up-tie-in-the-ema-after-a-nonzero-seed window 2: expected { P_distraction: 0.502, ...} to deeply equal { P_distraction: 0.503, ...}`。`below-in-binary` 仍通过（预期，见上表） |
| M3 | 从夹具里删掉这两个新用例（保留其余 9 个） | 新测试 | `Tests 1 failed \| 394 passed (395)`，失败的是 "keeps the two ties that toFixed / Math.round get wrong"：`expected [ ...(9) ] to include 'half-up-tie-in-the-ema-below-in-binary'` |
| M4 | `backend/app/inference.py:120` 的 `fusion.round_half_up(..., 3)` -> 内置 `round(..., 3)` | 新夹具（Python 一侧） | `3 failed, 20 passed, 48 deselected`：`...matches_the_shared_oracle[half-up-tie-in-the-ema]`、`[half-up-tie-in-the-ema-below-in-binary]`、`[half-up-tie-in-the-ema-after-a-nonzero-seed]`。注：旧的 0.0625 用例本来就抓得住内置 `round`；新用例是额外多一层。 |
| 还原 | 把实现行、夹具、测试都还原为真实工作树的版本 | | `diff -r /Users/liu/Desktop/FYP2-Live-System/ai/src ai/src` 无差异；`vitest` **15 个文件 / 397 passed**，全绿 |

M0 / M2a 与 M1 / M2b 的对照说明新增内容正是让这两个变异变红的东西；M3 说明删除夹具用例本身也会变红。

### 四项门禁（真实工作树，改动之后）

```
export PYTHONDONTWRITEBYTECODE=1
(cd backend && TMPDIR=$(mktemp -d) PYTHONPATH=. ../.venv/bin/python -m pytest tests -q -p no:cacheprovider)
  -> 510 passed, 1 warning in 5.89s            (退出码 0)
./node_modules/.bin/vitest run --no-cache
  -> Test Files 15 passed (15) / Tests 397 passed (397)   (退出码 0)
./node_modules/.bin/tsc --noEmit
  -> 无输出                                    (退出码 0)
./node_modules/.bin/eslint .
  -> 无输出                                    (退出码 0)
```

额外：`./node_modules/.bin/prettier --check ai/src/emaParity.test.ts ai/fixtures/ema_parity_vectors.json` -> `All matched files use Prettier code style!`

## R1.5 测试数变化（逐项解释）

| 门禁 | 修复前 | 修复后 | 变化 | 解释 |
|---|---|---|---|---|
| pytest | 506 | **510** | +4 | 夹具新增 2 个用例；Python 有 2 个按用例参数化的测试（`..._run_inference_matches_the_shared_oracle`、`..._the_reference_specification_agrees`），2 x 2 = +4。没有新增或改动任何 Python 测试代码。 |
| vitest | 394 | **397** | +3 | 夹具新增 2 个用例，`describe.each` 每个用例 1 个测试，+2；新增 1 个 "keeps the two ties ..." 测试，+1。 |
| tsc | 0 | 0 | 无 | |
| eslint | 0 | 0 | 无 | |

pytest 的那条 warning 与之前相同（`starlette.testclient` 对 `httpx` 的弃用提示）。

## R1.6 修改的文件

- 修改：`ai/fixtures/ema_parity_vectors.json`（+78 行，新增 2 个用例）
- 修改：`ai/src/emaParity.test.ts`（+10 行，含注释）
- 修改：`docs/fyp2/implementation/phase1-01-f4.md`（本节）

## R1.7 遗留问题 / 说明

1. 生产代码没有改。`riskLogic.ts` 的 `round3` 一直是对的，缺的只是守卫。
2. "presence 守卫" 只加在 TS 测试里。Python 的 `test_ut_ema_parity_01_covers_the_three_required_situations` 没有加这两个 id。删除夹具用例会让 TS 测试变红（M3 已验证），所以保护已经成立；若希望 Python 一侧也对称，可另行加一行断言。
3. 本轮没有处理报告第 7 节的原有遗留问题（尤其是 `ai/src/riskLogic.ts` 的 `asPercent` 仍使用 `Math.round(value * 100)`，与新规则不一致）。它不属于本次审阅发现。
4. 夹具里 EMA 的输入是 2 位小数网格上的"十进制精确平局"。它抓得住 `toFixed` 与 `Math.round(v*1000)/1000` 这两类回退，但并不证明对所有输入逐位一致；这两个用例只是把已知的两类回退钉死，不替代全网格比较。

## R1.8 证据路径

- 门禁原始输出（scratchpad `/private/tmp/claude-501/-Users-liu-Desktop-FYP-In-Cabin-Driver-Assessment--1--claude-worktrees-exciting-keller-fdf913/a1949e26-b3d7-4f7f-bd9f-059bf8cb6f0e/scratchpad/`）：`fix1-pytest.log`、`fix1-vitest.log`、`fix1-tsc.log`、`fix1-eslint.log`
- 穷举搜索与独立推导脚本：同目录 `search.mjs`、`search.py`、`oracle.py`
- 变异用的隔离副本路径：同目录 `mutdir.txt`（内容为 `mktemp -d` 产生的目录）
