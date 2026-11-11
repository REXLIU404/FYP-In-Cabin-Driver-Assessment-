# 阶段 1 · 第 2 项（P1-2）技术报告：R08 更正 —— 「Live 到不了 stale」是错的

- 分支 `fyp2/live-system`，工作树 `/Users/liu/Desktop/FYP2-Live-System`，开工 HEAD `9db6e2a`（与简报要求一致，工作树干净）。
- 日期 2026-10-13。角色：实现者。未派发子 agent。

## 1. 任务编号与名称

P1-2-R08：R08 更正。用经 `POST /api/sessions/{sid}/infer` 的可反证测试（`IT-LIVE-AGE`）替换错误的 source-string 守卫，并更正计划与总结文档里其余过期文字（简报 A、B、C 三部分）。

## 2. 实现状态

| 简报条目 | 状态 |
|---|---|
| A.1 计划 Task 5 `UT-TIME-06` 末句更正 | 完成 |
| A.2 计划 Task 9 可达性表一行与紧随其后的段落更正 | 完成 |
| A.3 `TASK_1_TO_6_SUMMARY.md`：勘误节、第 7 节第 1、2 条删除线、「不应对外陈述」追加一条 | 完成 |
| A.4 `git grep` 全面搜索残留并逐处说明 | 完成，见第 4.4 节；搜出一处简报未点名的残留（`task-05.md:133`），已更正 |
| B.1 `UT-TIME-06` docstring 更正，断言不变 | 完成 |
| B.2 删除 source guard 测试 | 完成 |
| B.3 新增 `IT-LIVE-AGE`（边界、30 天旧帧、D13 行为快照，全部经 `/infer`，不依赖模型权重） | 完成 |
| 验收：M-a、M-b、M-c 各自让新测试变红 | 完成，三项全部变红（第 5.3 节） |
| C.1 四处残留的 `npx` 门禁命令 | 完成 |
| C.2 `ai/reference/risk_logic.py`「零 importer」过期说法 | 完成 |
| C.3 「三种语言逐值一致」 | 完成 |
| C.4 R4 修订记录表第 2 行 | 完成 |
| C.5 重新生成 SDD `global-constraints.md` | 完成，`cmp` 一致 |
| 四项门禁 | 全部 0 失败（第 6 节） |

## 3. 创建 / 修改的文件

提交内包含 5 个文件：

| 文件 | 性质 |
|---|---|
| `backend/tests/test_temporal_contract.py` | 修改：+131 / −9。改 `UT-TIME-06` docstring，删 1 条测试，新增 `IT-LIVE-AGE`（1 个 stub 类、1 个常量、2 个辅助函数、3 个测试函数共 9 个用例） |
| `docs/plans/2026-10-12-fyp2-live-system-completion.md` | 修改：A.1、A.2、C.1–C.4 |
| `docs/fyp2/implementation/TASK_1_TO_6_SUMMARY.md` | 修改：勘误节、第 7 节两条删除线、「不应对外陈述」追加一条 |
| `docs/fyp2/implementation/task-05.md` | 修改：第 133 行（第 4.4 节第 12 项） |
| `docs/fyp2/implementation/phase1-02-r08.md` | 新建：本报告 |

提交之外（git 忽略，不入库）：`.superpowers/sdd/2026-10-12-fyp2-live-system-completion/global-constraints.md` 已整体重新生成。

未触碰：`backend/app/`（没有改任何实现）、`docs/fyp2/review/`、`ml/outputs/`、主仓库。

## 4. 实现摘要

### 4.1 事实依据（我自己核对过源码）

- `backend/app/inference.py:107-108`：`vstatus` / `tstatus` 由 `freshness(<provider 给的状态>, provenance.get("captured_at") or w.timestamp, now, tolerance)` 与 telemetry 的对应写法算出。provider 说 `fresh` 不起决定作用，证据时间戳距 `now` 超过 3 s（严格 `>`）就是 `stale`。
- `backend/app/routers/windows.py:87-109`：`/infer` 把 provider 的 `provenance`（含请求里的 `captured_at` / `telemetry_timestamp`）原样交给 `run_inference`，路由不传 `now`，所以 `now` 取 `inference` 模块里的 `datetime.now(timezone.utc)`。
- `backend/tests/test_live_inference.py:114-117`：旧 `captured_at` 经 `/infer` 得到 `stale` 与 `DEGRADED`（该测试带 `requires_models`）。

因此简报给出的更正结论成立：D13 在 Live 主运行时可达。

### 4.2 测试（B 部分）

**`UT-TIME-06`（B.1）**：断言一字未改，docstring 删去「It is unreachable from the Live runtime…」两句，改为说明它在 Live 可达及原因，并指向 `IT-LIVE-AGE`。

**source guard（B.2）**：`test_ut_time_06_source_guard_the_trained_provider_never_emits_stale` 整条删除。在原位置留一段注释说明它为何被删，避免有人再写回去。

**`IT-LIVE-AGE`（B.3）**。位置在被删测试原处，三个测试函数：

1. `test_it_live_age_freshness_boundary_is_rederived_from_the_evidence_timestamp_through_infer`：branch（vision / telemetry）× 年龄（2999 / 3000 / 3001 ms）共 6 个用例，每个用例独立会话。年龄 2999、3000 ms 为 `fresh` 且 `FULL`，3001 ms 为 `stale` 且 `DEGRADED`；另一路固定为年龄 0 的 fresh 对照，所以状态翻转只能归因于被测分支自己的时间戳。同时断言 `provenance` 里回显的时间戳等于测试构造的时间戳。
2. `test_it_live_age_a_30_day_old_frame_is_stale_and_degraded_but_still_assessed`：vision / telemetry 各一例，30 天旧的一路为 `stale`，对照一路 `fresh`，`SystemHealth == "DEGRADED"`，`assessment_available is True`，`RiskScore == 100.0`、`RiskLevel == "High"`，且落库的记录与响应一致。
3. `test_it_live_age_stale_only_stream_still_reaches_high_alert_through_infer_known_limitation_d13`：同一会话连续 3 个请求，两路证据时间戳都是「服务端时刻前 30 天」，时间戳递增且互不相等（所以乱序守卫放行、也不是 `UT-TIME-05` 的相等时间戳情形），服务端时钟每次推进 1000 ms，`AlertSeverity` 依次为 `CAUTION, CAUTION, HIGH_ALERT`。名字含 `known_limitation`，docstring 写明这是 D13 的行为快照、不是期望行为。

**Stub（扩展方式）**：保持 `_StubProvider` 一字不动（既有 `UT-TIME-05` 与 `test_out_of_order_guard_survives_a_gap` 行为不变）。新增第二个小类 `_RequestDrivenStubProvider`，复刻 `trained.py` 的状态逻辑：请求带 `image_base64` 则 vision 为 fresh 且概率 1.0，带 `telemetry_features` 则 telemetry 为 fresh 且概率 1.0，否则 missing；从不报告 `stale`。这样既能让 telemetry 为 fresh（供下一项的 telemetry 对称测试复用），又保证「stale」只能由流水线从时间戳算出。

**时钟控制**：复用文件里已有的 `fake_clock` fixture，它把 **`app.inference` 模块里的** `datetime` 换成一个子类，`now()` 返回受控时刻，继承了 `fromisoformat`。没有改 `app.schemas` 的时钟。帧时间戳取 2025 年的过去时刻（`T0 = 2025-01-01T12:00Z`），服务端时刻 = 帧时刻 + 年龄，所以 `normalize_timestamp` 用真实时钟做的「不得超前 5 s」检查不会触发。期望值全部是测试里的字面量，没有从实现 import 任何常量。

### 4.3 文档（A、C 部分）

沿用计划已有的更正风格：错误原文保留 `~~删除线~~`，紧接「**R4 更正（Codex R08）**」。

- A.1：计划 Task 5 `UT-TIME-06` 末句。
- A.2：计划 Task 9 可达性表那一行（`~~❌ 不可达~~ ✅ 可达`，触发条件写为「`captured_at` / `telemetry_timestamp` 距服务端处理时刻超过 3 s」）；以及紧随其后那段里的两句错误话（「没有任何机制」「这同时解释了为什么 D13 不是主运行时的在役缺陷」）加删除线，其后追加一段更正，带上三处证据（`inference.py:107-108`、`test_live_inference.py:114-117`、`IT-LIVE-AGE`）。
- A.3：`TASK_1_TO_6_SUMMARY.md` 在引言之后插入「勘误（2026-10-13，Codex R08）」一节，分「哪两条说法错了 / 正确事实 / 证据 / 影响」四小节；第 7 节第 1 条中「该路径在 Live 主运行时不可达…」那一句和第 2 条整条加删除线并指向勘误节；「不应对外陈述的说法」清单追加「D13 只在 replay 可达 / Live 到不了 stale」。勘误里写明 Codex 将 R08 定为 P0、D13（R09）定为 P0/P1，D13 的政策仍待用户裁定。
- C.1：Task 2 第 348、367 行，Task 6 第 613 行，Task 10 的门禁代码块全部改为 Global Constraints 的精确形式（`./node_modules/.bin/*`，vitest 带 `--no-cache`，pytest 带一次性 `TMPDIR`）。Task 6 那条原为 `eslint ai frontend`，按简报要求统一为 `eslint .`。
- C.2：Global Constraints 里 `ai/reference/risk_logic.py` 的「零 importer，不会有任何测试因它漂移而失败」改为事实陈述：`test_fusion_vectors.py` 经 importlib 加载它，`test_temporal_contract.py` 再从前者 import 它。失败数我重新测过，见第 5.3 节：简报与审阅给的是 25，那是 `e326449` 上的数；现在 `9db6e2a` 上是 27，计划里两个数及其对应提交都写明了。
- C.3：「三种语言逐值一致」改为「两种语言（Python、TypeScript）、三份实现逐值一致」。
- C.4：R4 修订记录表第 2 行写明 F4 已完成（`f289d66`、`9632812`），F1 仍在本批待做。
- C.5：SDD `global-constraints.md` 整体替换为计划第 15–148 行的逐字内容，首行注释的日期说明更新为「2026-10-13，阶段 1 F4 生成，P1-2 更新」。

### 4.4 A.4 全面搜索：每一处命中的处置

范围 `docs/ backend/ ai/ frontend/`，排除 `docs/fyp2/review/`。用了两轮 `git grep -n -i -E`：第一轮英文与「到不了 / 不可达 / 死路 / 没有任何机制 / 只输出 fresh / replay 路径 / fresh/missing / unreachable / never emits stale」等；第二轮补中文「回放」措辞（「回放可达 / 仅回放 / 只在回放 / Live…不会…stale」等）。**第二轮才发现第 12 项**，只用第一轮会漏。

| # | 位置 | 内容 | 处置 |
|---|---|---|---|
| 1 | 计划 Global Constraints，D13 段（R1 旧段落） | 已有删除线 + R4 更正 | 无需再改（本项之前已处理） |
| 2 | 计划 Task 5 `UT-TIME-06` 末句 | 「在 Live 主运行时不可达」 | **已更正**（A.1） |
| 3 | 计划 Task 9 可达性表「任一路 stale」行 | 「❌ 不可达」 | **已更正**（A.2） |
| 4 | 计划 Task 9 表后段落 | 「没有任何机制」「为什么 D13 不是在役缺陷」 | **已更正**（A.2） |
| 5 | 计划 R1 修订记录 #8 | 已有删除线 + R4 更正 | 无需再改 |
| 6 | 计划「剩余技术风险」表「Live 永远到不了 stale」行 | 已有删除线 + R4 更正 | 无需再改 |
| 7 | 计划 R4 修订记录表第 1 行 | 标题复述了这个错误说法，正文说明将要做的修复 | 不是主张；不改。注意它仍是「审阅修复批次中」的将来时，见第 7 节 |
| 8 | 计划第 44 行、第 750 行「replay 路径」 | 与 stale 可达性无关（讲 `ai/src` 纯函数的用途、`preparedSessionInput.ts` 的归属） | 无需更正 |
| 9 | 计划第 103、942 行「不可达 / 死代码」 | 讲 10000 ms 退避上限在 3 次投递下达不到 | 无关，无需更正 |
| 10 | `TASK_1_TO_6_SUMMARY.md` 第 7 节第 1 条 | 「该路径在 Live 主运行时不可达…」 | **已更正**（A.3，删除线 + 指向勘误） |
| 11 | `TASK_1_TO_6_SUMMARY.md` 第 7 节第 2 条 | 整条错误 | **已更正**（A.3，整条删除线） |
| 12 | `docs/fyp2/implementation/task-05.md:133` | 「另有源码守卫 `test_ut_time_06_source_guard_…`：`trained.py` 若开始输出 `stale`，该守卫变红，提示 D13 不再是仅回放可达」 | **已更正**（简报未点名，但属 A.4 的范围）：原句加删除线，追加 R4 更正，说明守卫已删除、被 `IT-LIVE-AGE` 取代 |
| 13 | `TASK_1_TO_6_SUMMARY.md` NaN 缺口两处「不可达」 | 讲 NaN 在当前入口进不来 | 与 stale 无关，无需更正 |
| 14 | `TASK_1_TO_6_SUMMARY.md` 勘误节自身与新增的「不应对外陈述」一条 | 引用错误说法以便更正 | 有意保留 |
| 15 | `test_temporal_contract.py` 原第 607、623、624 行 | docstring 与已删测试 | **已更正**（B.1、B.2） |
| 16 | `test_temporal_contract.py` 新增注释里的「unreachable」「never reports 'stale'」 | 前者描述已删守卫、后者描述 stub 的行为 | 有意保留 |
| 17 | `phase1-01-f4.md:60,83`、`phase1-01-f4-acceptance.zh.md:7` | F4 的报告，叙述「该主张已被推翻」及其检索方法 | 历史记录，不改 |
| 18 | `02_TEST_CASE_INVENTORY_AND_CRITIQUE.md:57`、`audit_manifest.json:1544`、`05_RUBRIC_TRACEABILITY_AND_REPORT_MAP.md:20` | 「fresh/missing」指输入来源，「replay path」指架构图画法 | 与 Live 能否到 stale 无关，无需更正 |
| 19 | `01_MODULE_AND_ARCHITECTURE_INVENTORY.md:59`、`03_EVALUATION_COVERAGE_MATRIX.md:105`、`08_OPEN_DECISIONS_FOR_SUPERVISOR.md:27` | 讲 D13：旧证据永不变 missing、可累积告警时长 | 已读，没有任何一处主张 Live 不可达，无需更正 |

搜索范围之外、我只做了查看没有改：`.planning/system-track/task_plan.md:42`（控制者的待办勾选框）、`.planning/system-track/progress.md:40`，以及 git 忽略的 `.superpowers/sdd/.../task-5-brief.md:21`（Task 5 的旧 brief，仍抄着那句错话）。见第 7 节。

## 5. 执行的测试（精确命令）

### 5.1 四项门禁（改动完成后，在真实工作树运行）

```
cd /Users/liu/Desktop/FYP2-Live-System
export PYTHONDONTWRITEBYTECODE=1
(cd backend && TMPDIR=$(mktemp -d) PYTHONPATH=. ../.venv/bin/python -m pytest tests -q -p no:cacheprovider)
./node_modules/.bin/vitest run --no-cache
./node_modules/.bin/tsc --noEmit
./node_modules/.bin/eslint .
```

另在 `backend/` 下用 `-k "live_age or ut_time_06"` 单独跑过新增与相关测试：12 个全过（`UT-TIME-06` 3 个 + 新增 9 个）。

### 5.2 其他验收检查

- SDD 约束文件与计划一致：`cmp <(sed -n '15,148p' docs/plans/2026-10-12-fyp2-live-system-completion.md) <(sed -n '2,$p' .superpowers/sdd/2026-10-12-fyp2-live-system-completion/global-constraints.md)`，退出码 0，无输出。该文件首行含「P1-2 更新」。
- 重新生成前，我把旧文件备份到 scratchpad，并 `diff` 确认新旧只差两处（C.2、C.3 的改动）。

### 5.3 变异验证

全部在隔离副本里做：`git archive HEAD | tar -x`，`.venv` 做符号链接，再把改好的 `test_temporal_contract.py` 拷进去。副本路径 `/var/folders/0k/dtzqmkm53vqgg530vd7h3fmr0000gn/T/tmp.w4s7cMF5JQ`。每次变异后用备份文件还原，并 `diff` 确认与真实工作树的 `inference.py` 逐字相同。真实工作树从未被变异，`git status` 只有预期的 4 个修改文件。

副本里未变异时，新的 `test_temporal_contract.py` 整个文件：79 passed。旧版（`HEAD`）同一文件在副本里是 71 passed，71 − 1 + 9 = 79。下表的「failed / passed」都是这一个文件的计数，不是整个套件。

简报要求的三个变异：

| 变异 | 改动 | 结果（整个 `test_temporal_contract.py`） | 新测试的红灯 |
|---|---|---|---|
| **M-a** | `inference.py:107` 改为只用 `w.timestamp`，不再用 `provenance.get("captured_at")` | 7 failed / 72 passed | 边界 `[3001-stale-DEGRADED-vision]`、30 天 `[vision]`、D13 快照，共 3 个变红；其余旧测试 4 个（`UT-TIME-02` 经 `run_inference` 一个，`UT-TIME-06` 三个）也变红 |
| **M-b** | `freshness()` 的 `>` 改为 `>=` | 6 failed / 73 passed | 边界 `[3000-fresh-FULL-vision]`、`[3000-fresh-FULL-telemetry]` 变红（简报点名的 3.000 s 用例）；旧的 4 个 `UT-TIME-02` 测试也变红 |
| **M-c** | `freshness()` 永不返回 `"stale"` | 12 failed / 67 passed | 新测试 5 个变红：边界 `3001` 的 vision 与 telemetry、30 天 vision 与 telemetry、D13 快照；其余 7 个是旧的 `UT-TIME-02`（4 个）与 `UT-TIME-06`（3 个） |

我额外做的变异（简报没要求，用来证明每条新用例都有杀手）：

| 变异 | 改动 | 新测试结果 |
|---|---|---|
| M-d | `inference.py:108` 不再用 `provenance.get("telemetry_timestamp")` | telemetry 的 `3001` 边界、30 天 `[telemetry]`、D13 快照变红 |
| M-e | 超过 1 天的证据返回 `"missing"`（相当于实现了一个最大证据年龄） | 30 天两例与 D13 快照变红。这是预期的「行为变化绊线」：一旦 D13 被修，这几条快照必须有意识地改写 |
| M-f | `ALERT_SUSTAIN_MS` 2000 改为 3000 | D13 快照变红 |
| M-g | 容差有效值 2.5 s（`> tolerance - 0.5`） | 边界 `2999` 与 `3000`，vision 与 telemetry，共 4 个变红 |
| M-h | 容差有效值 3.5 s（`> tolerance + 0.5`） | 边界 `3001` 的 vision 与 telemetry 共 2 个变红 |

**「旧守卫抓不到真实问题」的对照（简报验收的最后一条）：**

把 `HEAD` 版的旧 `test_temporal_contract.py` 放进副本，施加 M-c：

- 旧 source guard 单独运行：**1 passed**（变异下仍绿，印证它抓不到真实问题；接上模型文件后依然是 1 passed）。
- 旧文件里所有触碰 `POST /infer` 的测试（`UT-TIME-05`、`test_out_of_order_guard_survives_a_gap`、source guard）：**3 passed**，即旧套件在 Live 路径上没有任何不依赖模型的测试能抓住 M-c。
- 旧套件里唯一断言 Live 路径出现 `stale` 的测试是 `test_live_inference.py::test_missing_expired_and_out_of_order_inputs`，它依赖真实模型。副本里模型缺失时它被跳过；我把真实 `ml/outputs` 以只读符号链接挂进副本后重跑，M-c 下该测试 **FAILED**，未变异时 passed。
- 新测试在 M-c 下全部变红，且不需要模型文件。

**但简报里「旧的测试集会全绿」按字面不成立，请见第 7 节第 1 条。**

另外我独立复测了 C.2 里那个「审阅实测 25 个」的数字：在 `e326449` 的归档上把 `ai/reference/risk_logic.py` 的 `round_half_up` 改成内置 `round`，pytest 为 **25 failed / 474 passed / 7 skipped**（与审阅一致）；在 `9db6e2a` 的干净归档（未放入任何我的改动）上，未变异为 503 passed / 7 skipped（模型文件缺失所致），同样的变异为 **27 failed / 476 passed / 7 skipped**。F4 追加的舍入用例使失败数从 25 增到 27。我第一次在变异副本里测出的 31 是错的：那个副本里我放了一份旧测试文件做对照，它也加载参考实现，重复计入了失败，所以重新在干净归档上测了。

## 6. PASS / FAIL / SKIP 计数

| 门禁 | 改动前（`9db6e2a`） | 改动后 | 结果 |
|---|---|---|---|
| pytest | 510 passed / 0 failed / 0 skipped | **518 passed / 0 failed / 0 skipped** | 0 失败 |
| vitest | 未在改动前单独运行 | **397 passed / 0 failed**（15 个文件） | 0 失败 |
| `tsc --noEmit` | — | exit 0 | 0 错误 |
| `eslint .` | — | exit 0 | 0 问题 |

**pytest 510 → 518 的逐项解释：**

- −1：删除 `test_ut_time_06_source_guard_the_trained_provider_never_emits_stale`。
- +6：`test_it_live_age_freshness_boundary_…` 参数化，branch 2 × 年龄 3。
- +2：`test_it_live_age_a_30_day_old_frame_…` 参数化，branch 2。
- +1：`test_it_live_age_stale_only_stream_…_known_limitation_d13`。
- 合计 −1 + 6 + 2 + 1 = **+8**，510 + 8 = 518，与实测吻合。

**关于基线的说明：** 阶段 1 开工基线（`e326449`）是 pytest 506 / vitest 394。到 `9db6e2a` 为 510 / 397，增量来自 F4 的提交 `9632812`（按其 diff：给 `ai/fixtures/ema_parity_vectors.json` 加了用例，并在 `ai/src/emaParity.test.ts` 加了 10 行；这个拆分是我从提交内容推断的，没有逐条核对）。我实测了改动前 pytest 为 510。vitest 我没有在改动前单独跑，但本项没有改动任何 TypeScript 文件，397 即 `9db6e2a` 的数。

## 7. 遗留问题

1. **简报验收里「用 M-c 跑旧的测试集会全绿」按字面不成立。** 成立的是更窄的版本：旧 source guard 本身在 M-c 下是绿的，旧套件里不依赖模型的、经 `/infer` 的测试在 M-c 下全绿（3 个）。但整个旧文件在 M-c 下有 7 个红：`UT-TIME-02` 的 4 个与 `UT-TIME-06` 的 3 个，它们是直接驱动 `freshness()` / `run_inference` 的单元测试，不经过 Live 路径。另外整个旧套件里 `test_audit_regressions.py::test_old_capture_timestamp_cannot_be_full_health` 在 M-c 下也变红，它走的是 `/windows`（replay 路径）。所以结论应当表述为：「旧守卫以及旧套件在 Live 路径上不依赖模型的测试，抓不到 M-c；能抓到的要么是单元层、要么是 replay 路径、要么要模型」，而不是整套全绿。
2. **D13 的政策仍未裁定。** 本项只更正事实并补上可反证的 Live 路径测试，没有改任何实现。`IT-LIVE-AGE` 的 D13 快照记录的是当前（不理想）行为；M-e 证明一旦实现最大证据年龄，这些快照会变红，那时需要有意识地改写它们，而不是让它们悄悄通过。最大证据年龄 / stale-only 守卫、相等时间戳（R10）、`DominantEvidence` 语义（R14）都仍是待用户裁定项。
3. **计划 R4 修订记录表第 1 行（R08）仍是将来时**（「审阅修复批次中：…加勘误…改为…」）。提交之后它就过期了。我没改，因为提交哈希在提交前不可知，也不在简报范围内。建议控制者在本项提交后补一句「已完成（P1-2，`<hash>`）」。`.planning/system-track/task_plan.md:42` 的 R08 待办框同理，不在我可写的范围，没动。
4. **git 忽略的 `.superpowers/sdd/.../task-5-brief.md:21` 仍抄着旧计划那句「该路径在 Live 主运行时不可达」。** Task 5 已完成，且该文件在简报要求的搜索范围之外，我没改。如果以后还会从它派发工作，应当补一行引用块。
5. **计划里还有简报没列出的 `npx` 残留，我按简报只改了列出的四处**：Task 1 第 283、298 行（已完成任务的验证记录与基线命令）、第 575 行（散文里把 `npx tsc --noEmit` 当反例引用）、DoD 表里 Task 1/2/6 的三行（描述当时的验证结果）。它们不会被 Task 10 的 brief 带出去，所以没动；如果希望计划里一个 `npx` 都不剩，需要另行指示。
6. **计划 Task 3 正文第 419 行也有同一类过期说法**：「这个模块零 importer、零测试覆盖…不会有任何测试报警」。简报 C.2 只点名 Global Constraints，所以我没改；它是 Task 3 写作当时的理由，现在读起来与 Global Constraints 的新表述矛盾。建议控制者决定是否也加一条更正。
7. **`IT-LIVE-AGE` 的 30 天用例我同时做了 vision 与 telemetry 两个 branch**（简报只要求 vision）。这是对简报的小幅超出，目的是让 stub 与辅助函数确实可以给下一项复用，并让 M-d 有杀手。如不需要可只保留 vision 一例。
8. **测试数据里的 `image_base64` 是字符串 `"stub-frame"`**，并非真实图像。stub 不解码，`LiveInput` 对它只校验长度，所以这是有意的；它意味着 `IT-LIVE-AGE` 不覆盖真实的图像预处理。

## 8. 证据路径

- 测试：`/Users/liu/Desktop/FYP2-Live-System/backend/tests/test_temporal_contract.py`（`IT-LIVE-AGE` 段在 `UT-EMA-PARITY-01` 之前）。
- 计划：`/Users/liu/Desktop/FYP2-Live-System/docs/plans/2026-10-12-fyp2-live-system-completion.md`（改动处：第 21、59、348、367、523–524、614、769–773、821–828、974 行附近）。
- 勘误：`/Users/liu/Desktop/FYP2-Live-System/docs/fyp2/implementation/TASK_1_TO_6_SUMMARY.md`（文首「勘误」节）。
- Task 5 报告更正：`/Users/liu/Desktop/FYP2-Live-System/docs/fyp2/implementation/task-05.md`（第 133 行）。
- SDD 约束副本（git 忽略）：`/Users/liu/Desktop/FYP2-Live-System/.superpowers/sdd/2026-10-12-fyp2-live-system-completion/global-constraints.md`。
- 变异用隔离副本：`/var/folders/0k/dtzqmkm53vqgg530vd7h3fmr0000gn/T/tmp.w4s7cMF5JQ`（HEAD 归档 + 新测试文件；`tests/test_temporal_contract_old.py` 是 HEAD 版旧测试文件，仅用于对照；`ml/outputs` 已换成指向真实目录的只读符号链接，原目录改名为 `ml/outputs.tracked`）。另有一个 `e326449` 的归档副本用于复测 25 这个数字，位于同一 `/var/folders/.../T/` 下。
- 备份与差异（scratchpad）：`/private/tmp/claude-501/-Users-liu-Desktop-FYP-In-Cabin-Driver-Assessment--1--claude-worktrees-exciting-keller-fdf913/a1949e26-b3d7-4f7f-bd9f-059bf8cb6f0e/scratchpad/`（`plan.diff`、`global-constraints.before.md`、`inference.py.orig`、`risk_logic.py.orig`）。

## 9. 下一项依赖

- **P1-3 telemetry 对称测试（T-GAP）** 可以直接复用本项留下的模块级设施：`_RequestDrivenStubProvider`（telemetry 可为 fresh）、`_live_age_session(client, monkeypatch, sid)`、`_live_age_request(request_id, vision_stamp, telemetry_stamp)`、`TELEMETRY_FEATURES`，以及文件里已有的 `fake_clock`。注意：请求同时带图像与遥测时，两路都会参与 `captured_at` / `telemetry_timestamp` 两个水位线，写 telemetry gap 测试时要让两路时间戳按预期递增，否则会撞 409。
- **IT-EPS（P1-4）与后续项** 不依赖本项的代码，但它们的 brief 若从计划生成，现在拿到的是已更正、且与 Global Constraints 一致的门禁命令。
- **Task 10 的 brief** 若从计划生成，将不再带出 `npx`，也不再带出「Live 到不了 stale」。`ST-FAIL-01` 的 stale 步骤现在可以用旧 `captured_at` 经 `/infer` 构造，计划里已经这样写了。
