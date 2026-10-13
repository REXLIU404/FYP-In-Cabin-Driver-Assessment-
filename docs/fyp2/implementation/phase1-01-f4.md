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
