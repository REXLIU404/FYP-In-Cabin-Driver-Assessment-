# P0-D13 技术报告：实施裁定 A —— 证据过期按 missing 计分，并保留原因

- 分支 `fyp2/live-system`，工作树 `/Users/liu/Desktop/FYP2-Live-System`，开工 HEAD `ce817ed`（与简报一致）。
- 日期 2026-10-15。角色：实现者。**第二次运行**：第一次运行撞到会话限额，没有提交，在工作树里留下 36 个已修改文件和 2 个新文件；本次从该未提交状态继续，没有重写。未派发子 agent。
- 用户批准：2026-10-13 裁定 A；2026-10-15 批准提前到 Task 8 之后、Task 9 之前实施。

## 1. 任务编号与名称

P0-D13-RULING-A：实施裁定 A（D13 / Codex R09）。

裁定的六条要点（逐字语义，未改动）：

1. 证据年龄超过 `freshness_tolerance_s`（严格 `>`，3.000 s 仍 fresh）即**过期**，按 `missing` 计分，freshness factor 为 0。
2. **保留原因**：provenance 记录 `{modality}_expired` 与 `{modality}_age_s`，使「因过期而不可用」与「没有收到输入」可区分。
3. 两路都缺失或过期时，仍是 `assessment_available = false`、四个风险字段为 null、`SystemHealth = UNAVAILABLE`（D01 不变）。
4. **运行时不再产出 `stale`**。0.45 这一档只保留给历史 stale 记录的读取与渲染。
5. 界面上「最新显示结果已过时」的提示（`useLiveSession.ts` 的显示年龄、`LiveMonitor` 的 "Latest result is stale"）与读取、渲染带 `stale` 的历史记录的能力，两样都保留，且都不是 0.45 这个模型输入权重。
6. 阈值复用 `RuntimeConfig.freshness_tolerance_s`，默认 3 s，每个会话可配，取值范围 (0, 30]；只称「设计阈值」，不称经过验证的安全阈值。

## 2. 实现状态

**完成。** 简报 A1–A10 全部落地；D1–D8 全部变异在隔离副本里跑过，每一项都按要求变红。

接续审阅的结果：第一次运行留下的实现基本完整、与简报一致；逐条对照 A1–A10 后只发现**一处缺漏**并已补齐——`ExplanationView.tsx` 的两个「Freshness」徽章（Vision / Telemetry 证据卡）仍直接打印存储状态，过期分支在那里仍会显示成 `missing`（违反 A6）。已改为 `BranchStatusPill`。其余改动审阅后保留。

四项门禁（最终状态，见第 5、6 节）：pytest 704 passed、vitest 561 passed、tsc 0、eslint 0。

## 3. 创建 / 修改的文件

共 36 个已跟踪文件修改 + 2 个新文件 + 本报告（行数为 `git diff --numstat`）。

**实现（后端）**

| 文件 | 变化 |
|---|---|
| `backend/app/inference.py` | +57/−9：`freshness()` 改返回 `Freshness(status, expired, age_s)`；`run_inference` 写四个 provenance 字段 |
| `backend/app/fusion.py` | +9/−0：仅注释（`freshness_weight` 的 0.45 标为仅供历史记录） |
| `backend/app/schemas.py` | +5/−0：仅注释（`FreshnessStatus` 保留 `stale` 字面量的原因） |

**实现（共享逻辑层 `ai/`）**

| 文件 | 变化 |
|---|---|
| `ai/src/types.ts` | +33/−0：新增 `EvidenceExpiry`；`PreparedSessionWindow.expiry?`；`RiskUpdate.provenance` 的四个可选字段；`stale` 的历史说明 |
| `ai/src/availability.ts` | +57/−1：新增 `branchExpiry()`、`describeBranchStatus()`、`Branch`/`BranchExpiry`；`freshnessWeight` 的 0.45 逻辑原样保留并加注释 |
| `ai/src/riskLogic.ts` | +24/−0：`buildRiskUpdate` 把 `window.expiry` 写入 `provenance`（缺省 `NO_EXPIRY`）；注释 |
| `ai/src/evidence.ts` | +7/−2：`getActiveInputSummary` 对过期分支输出 "expired (N s)" |
| `ai/src/liveLoop.ts` | +4/−3：仅注释（更正「现行后端会存成 stale」的说法） |
| `ai/reference/risk_logic.py` | +9/−2：仅注释（0.45 标为仅供历史记录） |

**实现（前端）**

| 文件 | 变化 |
|---|---|
| `frontend/src/data/preparedSessionInput.ts` | +53/−7：`freshnessStatus` 过期返回 `missing`；`isExpired`；每个窗口带 `expiry`；过期遥测的 `P_telemetry_anomaly` 记 0 |
| `frontend/src/components/BranchStatusPill.tsx`（新） | +19：分支状态徽章 |
| `frontend/src/components/ModalityCard.tsx` | +10/−10：用 `BranchStatusPill` 与 `formatBranchProbability` |
| `frontend/src/components/AlertBanner.tsx` | +3/−1 |
| `frontend/src/views/LiveMonitor.tsx`、`liveMonitorModel.ts` | +10/−2、+10/−1：模型多出 `visionExpiry` / `telemetryExpiry` |
| `frontend/src/views/SignalInspector.tsx` | +12/−6 |
| `frontend/src/views/ExplanationView.tsx` | +20/−2（含本次补齐的两个徽章） |
| `frontend/src/utils/display.ts`、`format.ts` | +20/−1、+16/−3：`resolveBranchPill`、`EXPIRED_LABEL`，`formatBranch*` 增加 `expired` 参数 |
| `frontend/src/types.ts`、`styles.css` | +1/−0、+2/−1：导出 `EvidenceExpiry`；`.pill--expired` 复用 stale 的黄色 |

**夹具 / 数据**

| 文件 | 变化 |
|---|---|
| `ai/fixtures/fusion_vectors.json` | +5/−0：F-S1、F-S2、F-S3、F-M3、F-M4 加 `legacy` 说明字符串；**期望值未动** |
| `ai/fixtures/ema_parity_vectors.json` | +1/−0：`first-fresh-after-stale-reseeds` 加 `legacy`；期望值未动 |
| `ai/prototype-data/prepared_sessions/session_001/missing_cases.csv` | +1/−1：W16 的期望分数 62.5 → 60.0（health、dominant 经真实输出核对不变） |

**测试**

| 文件 | 变化 |
|---|---|
| `backend/tests/test_evidence_expiry.py`（新） | +464：IT-EXPIRY-REASON / SENSITIVITY / NO-STALE、provenance 字段单元测试、历史记录读取与导出 |
| `backend/tests/test_temporal_contract.py` | +223/−93 |
| `backend/tests/test_retry_contract.py` | +47/−37 |
| `backend/tests/test_live_inference.py`、`test_unavailable_contract.py`、`test_fusion_vectors.py` | +7/−1、+7/−2、+12/−1 |
| `ai/src/availability.test.ts`、`emaParity.test.ts`、`fusionVectors.test.ts` | +109、+24、+25/−1 |
| `frontend/src/data/preparedSessionInput.test.ts`、`missingCases.test.ts` | +106/−2、+5/−5 |
| `frontend/src/utils/display.test.ts`、`format.test.ts`、`frontend/src/views/viewModels.test.ts` | +46/−1、+20、+25/−1 |

**报告**：`docs/fyp2/implementation/p0-d13-ruling-a.md`（本文件）。

未触碰：`ml/outputs/`、`docs/fyp2/review/`、计划文件、`.planning/`、主仓库、任何真实数据库；没有启动 vite / uvicorn。

## 4. 实现摘要（A1–A10 逐项）

**A1　后端 freshness 判定。** `freshness()` 返回 `Freshness(status, expired, age_s)`，`status` 只可能是 `fresh` 或 `missing`。年龄严格大于阈值 → `missing` 且 `expired = true`；发送方声明 `stale` 的分支（例如经 `/windows` 提交的窗口）同样 `missing` + `expired = true`，没有时间戳时 `age_s` 为 null；声明 `missing` 的分支直接 `missing / expired=false / age_s=null`（没有输入，不会因一个较新的时间戳被「升级」）。比较用**精确年龄**而不是四舍五入后的 `age_s`：3.0004 s 判过期，同时报告 `age_s = 3.0`（差异小于 1 ms，有测试钉住）。

**A2　provenance 字段。** `run_inference` 对每条新记录、两路分支都写入 `vision_expired`、`vision_age_s`、`telemetry_expired`、`telemetry_age_s`，字段始终存在（默认 provenance、provider 自带 provenance、无输入窗口三种路径都有测试）。写法是 `provenance.update(...)`（赋值而非 `setdefault`）：这四项是 `run_inference` 的裁决，provider 若碰巧带同名键也不能覆盖（有测试）。`age_s = max(0, 处理时刻 − 采集时刻)`，用现有的 `fusion.round_half_up(…, 3)`（ROUND_HALF_UP）；无时间戳为 null。`expired` 只在因年龄或输入声明 stale 时为 true。时钟偏差规则（超前 5 s 以上拒成 422）**未改**；5 s 以内的超前时间戳年龄记 0（有测试）。

**A3　EMA。** 过期 vision 的 `vstatus` 就是 `missing`：当次 `pd = 0.0`，`previous_vision` 因 `vstatus != "fresh"` 被置空，下一个 fresh 帧重新播种。该行实现代码本身没有改（语义与现行 missing 相同），只加了注释；新增 `test_ema_reseeds_on_the_first_fresh_window_after_an_expired_one`（两种来源：旧采集时间、声明 stale）。TS 侧 `buildRiskUpdate` 的 `previousVisionUsable` 要求上一条 vision 为 `fresh`，过期同样触发重新播种，代码不变。

**A4　prepared replay。** `freshnessStatus` 由 `age > 3 → stale` 改为 `→ missing`；每个窗口新增 `expiry`（四个字段），`buildRiskUpdate` 原样写入 `provenance`。CSV 的 `telemetry_age_s = 999` 是「没有遥测」的哨兵值，不当作年龄（`telemetryAge()` 对不可用分支返回 null）；replay 的 vision 没有采集时间，故 `vision_age_s = null`、永不过期。过期遥测的 `P_telemetry_anomaly` 记为 0，与后端 `run_inference` 对 missing 分支记 0.0 一致（原始模型输出仍在 CSV 里）。阈值是文件内常量 3 s（见第 7 节）。W16：遥测 4 s > 3 → 过期 → 只剩 vision（0.6）→ 60.0 / High / DEGRADED / Partial evidence。

**A5　三份融合实现。** `ai/src/availability.ts` 的 `freshnessWeight`、`backend/app/fusion.py` 的 `freshness_weight`、`ai/reference/risk_logic.py` 的 `freshness_weight` 里的 0.45 分支**逻辑原样保留**，加注释「runtime 不再产出 stale，此档仅供历史记录」。两份夹具中带 stale 的用例加 `legacy` 说明字符串，不删、不改期望值。并新增四条守卫测试（fusion 夹具的 Python / TS 各一条，EMA 夹具的 Python / TS 各一条）：「恰好使用 stale 档的那些行才带 `legacy`，且 `legacy` 是非空说明」。

**A6　UI。** 新增 `branchExpiry(record, branch)`（仅当分支状态为 `missing` **且** provenance 标 `expired = true` 才算过期；旧记录没有这些字段则视为未过期）与 `describeBranchStatus`（过期显示 `expired (N s)`，无年龄则 `expired`，其余原样）。接入全部显示分支状态的地方：`LiveMonitor`（`ModalityCard` + 两个 freshness 徽章）、`SignalInspector`（数值 + 徽章）、`ExplanationView`（数值 + 两个证据卡徽章，**本次补齐徽章**）、`AlertBanner`（数值）、`getActiveInputSummary`。数值位置：缺失显示 "No input"，过期显示 "Expired"，数字都不显示。「Latest result is stale」提示（`App.tsx` / `LiveMonitor.tsx` / `useLiveSession.ts`）**未改**。历史 `stale` 记录仍按原样渲染（`describeBranchStatus("stale")` 返回 `stale`，`formatBranchPercent(0.42, "stale", true)` 仍显示 42%，均有测试）。

**A7　现有测试的同步修改（逐条说明改了什么、为什么）。**

| 测试 | 原先钉的 | 现在断言 | 为什么 |
|---|---|---|---|
| `test_temporal_contract.py` UT-TIME-02 `freshness_boundary`（3 例）、`the_tolerance_comes_from_the_config`、`a_missing_branch_is_never_promoted…`、`utc_offsets_are_equivalent`（3 例） | `freshness()` 返回字符串；3001 ms → `"stale"` | 返回 `Freshness`；断言 `.status / .expired / .age_s`；3001 ms → `missing` + `expired` | 函数签名随 A1 改变；边界值（2999 / 3000 fresh，3001 过期）**一个没变**，utc 用例额外核对各种时间写法的年龄一致 |
| UT-TIME-02 `through_run_inference_and_health` | 3001 ms：两路 stale、DEGRADED | 3001 ms：两路 missing、`assessment_available = false`、UNAVAILABLE，两路 expired | 该用例两路共用同一个时间戳，现在两路同时过期，无可融合证据，按 D01 即 UNAVAILABLE |
| IT-LIVE-AGE 边界（6 例）、30 天（2 例） | 3001 ms / 30 天 → `stale`、DEGRADED | → `missing` + `expired = true` + `age_s`（3.001 / 2592000.0），DEGRADED，30 天用例的分数 100.0（只有另一路计分） | 需求行为（A7 第一条） |
| UT-TIME-06（3 例）与 IT-LIVE-AGE D13 快照 | `known_limitation_d13`：只有 stale 证据的数据流升到 HIGH_ALERT | 改名去掉 `known_limitation`：只有过期证据的数据流**永远到不了 HIGH_ALERT**——每个窗口 UNAVAILABLE、`AlertSeverity` null、`high_since`/`low_since` 为 null、`unavailable_since` 已挂起、`last_severity` 从未写入；UT-TIME-06 跑 10 个窗口（跨 9 s）、IT-LIVE-AGE 跑 5 个窗口（跨 4 s），都超过 2 s 持续期 | 需求行为。另加对照：过期 vision 旁边的 fresh 遥测仍会在 2 s 后升到 HIGH_ALERT（过期只移除旧分支，不禁用告警） |
| 两条 gap 测试（`captured_at` 版与 telemetry 版） | 第 1 步靠「只有 stale 证据仍得 High」成立（2025 年的时间戳在真实时钟下算 stale） | 第 1、2 步各用 fake clock 把服务器时刻设到该帧自己的采集时刻，使证据真正 fresh | 真实时钟下 1.7 年前的证据现在过期，无 High 连击可观察；测试意图（gap 清空连击但不清水位线）不变 |
| UT-TIME-05（同一 `captured_at` 重复提交仍累积） | known limitation | **保持 known limitation，断言未改**；docstring 写明「裁定 A 已实施，不能关闭它：这些帧只有 0–2 s 老，不会过期；关闭它需要 R10（观察身份），R10 尚未裁定」 | A7 明确要求 |
| `test_ut_ema_parity_01_run_inference_matches_the_shared_oracle` | 对全部 11 个用例，含 `first-fresh-after-stale-reseeds` | 只对 10 个非 legacy 用例；legacy 用例改由「运行时不产出 legacy stale 档」测试覆盖（声明 stale 的分支 → missing、expired、`age_s` null）；参考规格测试 `…reference_specification_agrees` 与 TS 一半仍跑全部 11 个 | 运行时不再能复现 0.45 档的期望值；纯函数与参考实现仍实现该档 |
| `test_retry_contract.py` IT-RETRY-STALE（3 例）与 `…keep_accumulating_sustained_high_known_limitation` | 6 s / 12 s 后到达的重发：stale、DEGRADED、High；三个窗口升到 HIGH_ALERT | 改名去掉 `known_limitation`：2 s 内到达仍是 FULL；6 s / 12 s 后两路都过期 → UNAVAILABLE、四个风险字段 null、`age_s` 为 6.0 / 12.0；三个迟到的重发 `AlertSeverity` 全为 null，计时挂起、不再累积 | Task 8 的预告（计划中已写明阶段 5 会变）；需求行为 |
| `test_live_inference.py::test_missing_expired_and_out_of_order_inputs` | 2000-01-01 的旧 `captured_at` → vision `stale`、DEGRADED | → vision `missing`，`vision_expired = true`，`vision_age_s > 7e8`，遥测 fresh，DEGRADED，仍有评估 | 需求行为（该测试需模型权重，本机有权重，已实际运行） |
| `test_unavailable_contract.py` `stale-vision` 对照 | 声明 stale 的 vision 得 65.2 | 改名 `declared-stale-vision-expires`，得 90.0（只剩遥测）；并断言 `vision_expired` 仅声明 stale 时为真 | 输入声明 stale 同样视为过期（A1） |
| `test_fusion_vectors.py` 夹具形状测试 | 每行的键集合恰好 8 个 | 允许可选键 `legacy`，其余键仍必须齐全 | 夹具新增 legacy 标记 |
| `missing_cases.csv` W16 / `missingCases.test.ts` / `preparedSessionInput.test.ts` 的 `at(16)` | 62.5 | 60.0 | 按真实输出更新 CSV；**未放宽任何断言**（`missingCases.test.ts` 仅改注释，期望值读自 CSV） |

其余 pytest / vitest 用例在 0.45 或 stale 语义变化后均未变红：它们测的是纯函数或历史记录（`fusion_vectors`、参考实现、`riskLogic.test.ts` 的 "stale branches are down-weighted to 0.45"、`availability.test.ts` 的 0.45 权重断言），按简报保持不变。

**A8　新增测试**（均在 `backend/tests/test_evidence_expiry.py`，不依赖模型权重：provider 打桩，时钟用 `test_temporal_contract` 的 fake clock，期望值全是字面量）：

- **IT-EXPIRY-REASON**：经 `/infer`，一路过期 + 一路没送 → UNAVAILABLE，provenance 为 `(True, 10.0)` 对 `(False, None)`，与「什么都没送」`(False, None)/(False, None)` 区分；镜像用例与两路都过期；一路过期 + 一路 fresh → DEGRADED、分数等于只用 fresh 那一路（vision 过期得 20.0、telemetry 过期得 80.0，对照组为同一证据另一路缺席的会话，且不是 0.45 档的 37.4，也不是两路的 50.0）；两路都 fresh 的对照。
- **IT-EXPIRY-SENSITIVITY**：会话 `freshness_tolerance_s` = 2 / 3 / 5，年龄 1.9 / 2.0 / 2.1 / 2.9 / 3.0 / 3.1 / 4.9 / 5.0 / 5.1 s，两路分支各一遍（54 例），逐一断言 fresh 或 expired，预期集合手写（边界 2.0 / 3.0 / 5.0 本身为 fresh，证明 `>` 严格）；另测默认值 3 s、取值范围 (0, 30]（0、−1、30.001、31 → 422；0.001、3、30 → 201）。**这是配置正确性测试，不是阈值合理性的证据**：PERF-01 对「采集 → 融合」实测延迟的复核属于 Task 10，测试文件头与本报告均写明。
- **IT-EXPIRY-NO-STALE**：`/infer` 9 个年龄（0 … 30 天，含 2.999 / 3.0 / 3.001 s）与 `/windows` 16 种声明 × 年龄组合；每个都检查返回记录、窗口列表、`risk/latest`、导出中 `modality_freshness` 的取值只属于 `{fresh, missing}`。
- **历史记录**：预先写入 DB 的带 `stale`、无过期字段的旧记录，经窗口列表、`risk/latest`、JSON 导出、CSV 导出、flag 读取全部原样返回（不报 500，历史不被改写）；旁边新写入的窗口不带 `stale`。
- 另有 provenance 字段单元测试（始终写入、覆盖 provider 同名键、ROUND_HALF_UP 到 3 位、年龄不为负、精确年龄比较等）。TS 侧：replay 的 3 s 严格边界（0 / 2.999 / 3 / 3.001 / 4 / 3600）、每条记录有四个字段、窗口 14 / 15 / 17「没收到但没过期」、整个样例会话恰好只有窗口 16 过期；`branchExpiry` / `describeBranchStatus` / `resolveBranchPill` / `formatBranch*` / `buildLiveMonitorModel` 的文字与语气区分。

**A9　文档。** 只写了本报告；没有改计划 / 路线图 / `CLAUDE.md`。受影响的报告章节与其他文档见第 7 节。

**A10　已知剩余缺口。** 见第 7 节，如实写出，未在本项修。

## 5. 执行的测试（精确命令）

门禁（真实工作树，最终状态）：

```
cd /Users/liu/Desktop/FYP2-Live-System
export PYTHONDONTWRITEBYTECODE=1
(cd backend && TMPDIR=$(mktemp -d) PYTHONPATH=. ../.venv/bin/python -m pytest tests -q -p no:cacheprovider)
./node_modules/.bin/vitest run --no-cache
./node_modules/.bin/tsc --noEmit
./node_modules/.bin/eslint .
```

测试清单对账用：在隔离副本里 `pytest --collect-only -q` 与 `vitest run --no-cache --reporter=json`，分别对 `git archive HEAD`（基线副本）与叠加了工作树改动的副本取测试 ID，求差集。

隔离副本（变异用；`rm -rf` 一概未用）：

```
D=$(mktemp -d) && git -C /Users/liu/Desktop/FYP2-Live-System archive HEAD | tar -x -C "$D"
ln -s .../.venv "$D/.venv"; ln -s .../node_modules "$D/node_modules"
# 三个模型文件以符号链接接入副本的 ml/outputs/（只读使用，使依赖模型的测试不 skip）
# 再把 git diff --name-only 与 ls-files --others 列出的 38 个文件复制叠上去
```

基线副本：`/var/folders/0k/dtzqmkm53vqgg530vd7h3fmr0000gn/T/tmp.hKUl9QebRm`；叠加副本（变异工作区）：`…/tmp.K6ZiXwsi7Y`。每次变异前用 `diff` 确认该文件与真实工作树一致，变异后从真实工作树拷回并再次 `diff` 确认一致。

### 5.1 变异结果（D1–D8，及额外变异）

| # | 变异（在隔离副本里改的那一行） | 结果 |
|---|---|---|
| D1 | `freshness()`：年龄超阈值时改回 `Freshness("stale", True, age_s)`（声明 stale 仍按 missing 处理） | pytest **58 failed** / 646 passed。变红的包括 IT-LIVE-AGE 边界与 30 天、IT-EXPIRY-NO-STALE（`/infer`）、UT-TIME-06 与 IT-LIVE-AGE 的 D13 需求测试、IT-RETRY-STALE、IT-EXPIRY-SENSITIVITY、IT-EXPIRY-REASON |
| D2 | `too_old = seconds > tolerance` → `>=` | **16 failed** / 688 passed。IT-LIVE-AGE 3000 ms 边界（`[3000-fresh-FULL-*]`）、UT-TIME-02 边界、SENSITIVITY（边界 2.0 / 3.0 / 5.0）、默认 3 s、NO-STALE 的 3.0 s 行 |
| D2-ts | replay：`ageSeconds > 3` → `>=` | vitest **1 failed**（`telemetry age 3 s -> fresh`），560 passed |
| D3a | 不写 `vision_expired` / `telemetry_expired`（只写 `*_age_s`） | **110 failed** / 594 passed。IT-EXPIRY-REASON 全部、SENSITIVITY 全部 54 例等 |
| D3b | 两个 `*_expired` 恒写 `False` | **63 failed** / 641 passed。IT-EXPIRY-REASON 的「过期 / 缺失可区分」用例等 |
| D4 | 阈值写死为 3（`too_old = seconds > 3`），忽略会话配置 | **13 failed** / 691 passed。SENSITIVITY 12 例（容差 2 与 5）+ UT-TIME-02 `tolerance_comes_from_the_config` |
| D5 | replay：过期改回返回 `"stale"` | vitest **9 failed** / 552 passed。含 **`missingCases.test.ts` W16**、`preparedSessionInput.test.ts` 的 `at(16)` 钉值与窗口 16 / 边界用例、`display.test.ts`、`viewModels.test.ts` |
| D6 | 输入声明的 `stale` 原样透传（`if too_old:` 去掉 `status == "stale" or`） | **10 failed** / 694 passed。IT-EXPIRY-NO-STALE（`/windows` 5 例）、`test_a_declared_stale_branch_is_expired…`、`declared-stale-vision-expires`、历史记录旁的新窗口、legacy 用例的运行时测试、reseed 测试 |
| D7 | 过期 vision 仍保留 `previous_vision`：`… else (scratch.get("previous_vision") if vision.expired else None)` | **2 failed** / 702 passed：`test_ema_reseeds_on_the_first_fresh_window_after_an_expired_one`（两种来源）——第三帧本应是 0.6 的新种子，变异后被平滑成 0.34 |
| D8a | 删除 `backend/app/fusion.py` 的 0.45 档 | **8 failed**：`test_fusion_vectors.py` 的 stale 行（compute_risk_score、map_risk_level、epsilon 边界系列） |
| D8b | 删除 `ai/src/availability.ts` 的 0.45 档 | vitest **9 failed**：`availability.test.ts` 的 0.45 权重、`fusionVectors.test.ts` F-S1 / F-S2、`emaParity.test.ts` legacy 用例、`riskLogic.test.ts` "stale branches are down-weighted"、`viewModels.test.ts` |
| D8c | 删除 `ai/reference/risk_logic.py` 的 0.45 档 | **11 failed**：参考实现与夹具端到端、`ut_ema_parity_01_the_reference_specification_agrees`、fusion 向量系列 |
| D9 | `buildRiskUpdate` 不写 `provenance` | vitest **6 failed**（四个字段 / 窗口 14·15·17 / 窗口 16 等） |
| D10 | `describeBranchStatus` 对过期仍返回原状态（UI 文字与 missing 一样） | vitest **4 failed**（`describeBranchStatus`、`resolveBranchPill`、`getActiveInputSummary`） |
| D12 | replay：过期遥测保留 `1 − p_safe` 概率 | vitest **1 failed**（窗口 16 的 `P_telemetry_anomaly` 应为 0） |
| D13 | 去掉 `max(0.0, …)`（年龄可为负） | **1 failed**：`test_age_is_never_negative_and_a_stamp_from_a_fast_clock_is_not_expired` |
| D14 | 年龄改用内建 `round(…, 3)` | **1 failed**：`test_age_is_rounded_half_up_to_three_decimals` |
| D15 | 用四舍五入后的 `age_s` 做过期判断 | **1 failed**：`test_the_expiry_decision_uses_the_exact_age_not_the_rounded_one` |

D2-ts、D9、D10、D12–D15 是简报表之外的额外变异，用来给本项新增的 TS 行为与 provenance 细节各自找到至少一个会变红的守卫。每次变异后均已还原并用 `diff` 确认与真实工作树一致；变异只在隔离副本里做，真实工作树的 `git status` 在全部变异之后仍是「36 个已修改 + 2 个未跟踪」，HEAD 仍为 `ce817ed`。

## 6. PASS / FAIL / SKIP 计数

最终门禁（本次会话在真实工作树上实际运行）：

| 门禁 | 结果 | 基线 | 变化 |
|---|---|---|---|
| pytest | **704 passed, 0 failed, 0 skipped**（1 条 starlette 弃用 warning，与本项无关） | 598 | +106 |
| vitest | **561 passed, 0 failed**（19 个文件） | 533 | +28 |
| `tsc --noEmit` | 退出码 **0**，无输出 | 0 | 0 |
| `eslint .` | 退出码 **0**，无输出 | 0 | 0 |

**测试数变化逐项解释。**

pytest：598 − 24 + 130 = 704。

- 删除 24 个测试 ID，全部是**改名 / 改参数的同位替换**（对应 130 个新增中的 24 个）：IT-RETRY-STALE 3 + accumulate 1；UT-TIME-02 `freshness_boundary` 3、`utc_offsets` 3；UT-TIME-06 3；IT-LIVE-AGE 边界 6、30 天 2、D13 快照 1；`stale-vision` 对照 1；EMA 对照的 legacy 用例（由 run_inference 版换成「运行时不产出 legacy 档」版）1。
- 新增 130，其中 24 是上述同位替换，**净新增 106**：`test_evidence_expiry.py` 101（REASON 4 个函数共 5 个 ID、SENSITIVITY 54 + 1 + 7、NO-STALE 9 + 16、历史记录 1、provenance 单元测试 8 个）；`test_fusion_vectors.py` 的 legacy 标记守卫 1；UT-TIME-06 对照（过期 vision + fresh 遥测仍告警）1；EMA 过期重新播种 2；EMA 夹具 legacy 标记守卫 1。

vitest：533 + 28 = 561，**无删除、无改名**；净新增 28：`availability.test.ts` 7、`emaParity.test.ts` 1、`fusionVectors.test.ts` 1、`preparedSessionInput.test.ts` 10、`display.test.ts` 4、`format.test.ts` 2、`viewModels.test.ts` 3。W16 相关的两条原有测试（`missingCases.test.ts`、`preparedSessionInput.test.ts` 的钉值）原地修改，ID 不变，数量不变。

## 7. 遗留问题

**A10 的两个已知剩余缺口（如实写出，本项不修）：**

1. **Live 遥测几乎永远不会过期。** Live 前端的 `telemetry_timestamp` 是**发送时刻**（每次请求取 `new Date()`），不是遥测样本的采集时刻。因此本项之后，裁定 A 对 Live 的**遥测**要等 R10 / Task 9 把它改为采集时间后才真正生效。vision 的 `captured_at` 是截帧时刻，对它即时生效。
2. **UT-TIME-05 仍是 known limitation，由 R10（观察身份）负责。** 同一 `captured_at` 在 3 s 内重复提交仍累积告警时间；裁定 A 关不掉它（测试 docstring 已写明）。

**其他如实记录：**

3. **阈值合理性没有被证明。** `freshness_tolerance_s` 默认 3 s 是设计阈值（由 2 s 遥测周期加 ≤ 1 s 端到端目标推出），不是验证过的安全阈值。IT-EXPIRY-SENSITIVITY 只证明「可配置」与「`>` 严格」；PERF-01 对采集到融合实测延迟的复核属于 Task 10。
4. **prepared replay 的阈值是文件内常量 3 s**，不随 `AppConfig.freshnessTolerance`（会话可配）变化：replay 窗口在模块加载时一次性构建。改动前同样写死为 `> 3`，行为一致；若要让 replay 也随会话阈值变化，需要把窗口构建延后到有配置之后，不在本项。
5. **导出未带过期原因。** `frontend/src/utils/export.ts` 的 `vision_freshness` / `telemetry_freshness` 两列只导出存储状态，过期分支导出为 `missing`，`expired` / `age_s` 不在导出列里（后端 `/export` 的 JSON 带完整 provenance）。简报 A6 只要求界面，且改列会改变导出形状，故未动；是否补两列留给控制者决定。
6. **解释文字未改。** `backend/app/fusion.py::build_explanation` 与 `ai/src/riskLogic.ts::buildExplanation` 的 "one modality is stale or missing"、`ai/src/evidence.ts` 规则条件 "one modality is stale or missing" 仍写「stale」；它们是与夹具共享的文字，改动会连带夹具期望，超出范围。读者可从分支徽章看出过期。
7. **界面接线没有组件渲染测试。**（**本条已在「修复轮 1」解决，见文末**：接线现在有静态渲染测试与变异守卫；下面是第一轮结束时的状态。）仓库没有 React 组件测试设施。逻辑（`branchExpiry`、`describeBranchStatus`、`resolveBranchPill`、`formatBranch*`、`buildLiveMonitorModel`）全部有单元测试且各有变异守卫；组件内的接线（把这些结果放进 JSX）由 `tsc` 与 `eslint` 保证类型与引用正确，**没有做浏览器冒烟**（简报没有要求，且不得启动 vite dev server / 对开发库启动 uvicorn）。本次补齐的 `ExplanationView` 两个徽章属于这一类，未被任何测试直接覆盖。
8. **预先存在的 prettier 偏差**：`ai/src/evidence.ts`、`frontend/src/data/preparedSessionInput.ts` 在 `ce817ed` 上就不符合 prettier（后者在一个大数组上，前者在两处无关行）；本项未顺手格式化，以免产生无关改动。本项新写的代码行未被 prettier 指出问题；`ExplanationView.tsx` 在基线上是干净的，已用 prettier 格式化。
9. **仍过时的文档**（按 A9 不由实现者修改，交控制者）：
   - `CLAUDE.md` 第 106–113 行写「implemented in phase 5 … the code still uses the 0.45 stale tier until then」，现已不成立；
   - `docs/FYP2_CLAUDE_DEVELOPMENT_HANDBOOK.zh.md` 第 95 行「freshness 权重 fresh=1、stale=0.45、missing=0」；
   - `.planning/system-track/task_plan.md` 第 80 行 R09 条目的状态；
   - 计划 Global Constraints 的「freshness 权重」一条、「D13」一段、IT-RETRY-STALE 与 UT-TIME-06 的描述、风险表 D13 行、路线图阶段 5 的 R09 条目；
   - 历史报告（`task-02/03/08.md`、`phase1-04/05`、`TASK_1_TO_6_SUMMARY.md`）里关于 0.45 / stale 的描述是**当时的事实**，建议保持，必要时加勘误指向本报告。
10. **以后写论文 / 报告时需要修改的章节**（A9）：Eq.2 的描述（FYP2 运行时 freshness 因子 m ∈ {1, 0}，0.45 档仅历史记录）；FYP1 §5.4.1 的 freshness 处理（stale 档已退出运行时）；限制一节（D13 已按裁定 A 处理，R10 / Live 遥测时间戳两个缺口仍在）；E3 的 staleness 测试（标为 legacy，对应夹具中的 `legacy` 行）。**不得**把 3 s 写成经过验证的阈值。
11. **简报与 context 的不一致**：context 文件说「裁定 A 在你的 Task 里不实施」，简报明确说此句对本项不适用；本项按简报实施。
12. 第一次运行的备份仍在 `.superpowers/sdd/2026-10-12-fyp2-live-system-completion/p0-d13-partial-run1/`，未改动。

## 8. 证据路径

- 实现：`/Users/liu/Desktop/FYP2-Live-System/backend/app/inference.py`（`Freshness`、`freshness()`、`run_inference`）；`ai/src/availability.ts`（`branchExpiry`、`describeBranchStatus`）；`frontend/src/data/preparedSessionInput.ts`（`isExpired`、`freshnessStatus`）；`frontend/src/components/BranchStatusPill.tsx`。
- 新增后端测试：`/Users/liu/Desktop/FYP2-Live-System/backend/tests/test_evidence_expiry.py`（IT-EXPIRY-REASON / SENSITIVITY / NO-STALE、历史记录）。
- 改写的测试：`backend/tests/test_temporal_contract.py`、`test_retry_contract.py`、`test_live_inference.py`、`test_unavailable_contract.py`、`test_fusion_vectors.py`；`ai/src/*.test.ts`；`frontend/src/**/*.test.ts`。
- 变异输出（本会话临时目录）：`/private/tmp/claude-501/-Users-liu-Desktop-FYP-In-Cabin-Driver-Assessment--1--claude-worktrees-exciting-keller-fdf913/43d73f6d-ed36-4f8a-b584-13c974ccd767/scratchpad/` 下的 `mut_D*.out`（pytest 失败列表）、`mutts_D*.json`（vitest JSON）、`ids_*.txt` 与 `vt_*.ids`（测试清单对账用）。
- 隔离副本：基线 `/var/folders/0k/dtzqmkm53vqgg530vd7h3fmr0000gn/T/tmp.hKUl9QebRm`，叠加副本 `…/tmp.K6ZiXwsi7Y`。
- 第一次运行的未提交状态备份：`/Users/liu/Desktop/FYP2-Live-System/.superpowers/sdd/2026-10-12-fyp2-live-system-completion/p0-d13-partial-run1/`。

## 9. 下一项依赖

- **Task 9（前端接入 Live / replay 架构，D11）** 依赖本项：Live 路径上的分支状态现在只有 `fresh` / `missing`，原因在 provenance；Task 9 把 `telemetry_timestamp` 改为遥测采集时间（R10 的一部分）之后，裁定 A 才对 Live 遥测生效——Task 9 / R10 应据此补一个「遥测过期」的端到端断言。
- **Task 10（端到端与单分支测试 / PERF-01）**：可以直接断言最终行为（过期 → missing + expired、UNAVAILABLE 时告警计时挂起）；并负责用实测的采集 → 融合延迟复核 3 s 这个设计阈值，**不得**把 IT-EXPIRY-SENSITIVITY 当作阈值合理性的证据。
- **R10（观察身份）**：关闭 UT-TIME-05 所钉的限制（同一证据在 3 s 内重复提交仍累积告警时间）。
- **控制者**：更新计划 / 路线图 / `CLAUDE.md` 中的状态（第 7 节第 9 条）；决定是否给导出补 `expired` / `age_s` 两列（第 7 节第 5 条）。

---

## 修复轮 1

- 开工 HEAD `5e72340`（与任务一致）。角色：实现者，修复轮 1 / 2。未派发子 agent。只修下面这一条发现，没有顺手改别的东西。
- 日期 2026-10-15。

### R1.1 评审发现（逐字）

> **Important**（`blocks_this_item: true`）
> where：`frontend/src/components/ModalityCard.tsx:11 (expiry?: optional), :20 (expiry = NOT_EXPIRED); wiring at frontend/src/views/LiveMonitor.tsx:131,137,182-190, ExplanationView.tsx:243,445, SignalInspector.tsx:151-180, AlertBanner.tsx:61-70`
>
> A6 的界面接线没有任何测试守护。我在隔离副本里做了四个接线回退：(E3) LiveMonitor 的遥测 ModalityCard 去掉 expiry={telemetryExpiry}；(E4) ExplanationView 的 vision Freshness 徽章改回 <Pill label={visionFreshness} tone={visionFreshness} />；(E5) SignalInspector 的遥测数值不再传 telemetryExpiry.expired；(E6) AlertBanner 的 vision 传 false。四项同时打上后 vitest 仍是 561 passed，tsc 0，eslint 0。实际后果：一个过期分支在这些位置会重新显示为 'missing' 或 'No input'，正是 A6 要禁止的情况，而且没有任何门禁会变红。ModalityCard 把 `expiry` 设成可选并给了 NOT_EXPIRED 默认值，所以漏传这个 prop 连类型检查都拦不住。实现者在报告 §7 第 7 条披露了这个缺口，但理由「仓库没有 React 组件测试设施」不完全成立：react-dom@18.3.1 已安装，在 node 环境里用 react-dom/server 的 renderToStaticMarkup 加 React.createElement，就能在 .test.ts 文件里做静态渲染断言，不需要新依赖。修法很便宜：把 ModalityCard 的 `expiry` 改成必填，再为 BranchStatusPill、ModalityCard 和至少一个视图加静态渲染测试，断言过期显示 'expired (4 s)'、缺失显示 'missing'。

评审说得对，我先确认了前提：`node_modules/react-dom` 是 18.3.1，`renderToStaticMarkup` 在 vitest 的 node 环境里可以直接渲染 `LiveMonitor`、`SignalInspector`、`ExplanationView`、`AlertBanner`（先写了一个一次性的探针渲染四个视图，看过真实标记后删除，没有提交）。不需要新依赖，不需要改 `vitest.config.ts` 的 `include`（测试仍是 `.test.ts`，用 `createElement` 而不是 JSX），`package.json` / 锁文件没有变化。

### R1.2 改了什么

| 文件 | 变化 |
|---|---|
| `frontend/src/components/ModalityCard.tsx` | `expiry` 由可选改为**必填**，删除 `NOT_EXPIRED` 默认值（+7/−5）。漏传现在是类型错误（TS2741），不再静默显示成 `missing` |
| `frontend/src/testing/markup.ts`（新） | 测试专用：`markup()`（`renderToStaticMarkup` 并去掉 `<!-- -->` 分隔符）、`pillsAfter()` / `valuesAfter()`（取紧跟在 `<span>行标签</span>` 之后的徽章 / 数值）、`modalityCard()`（取某张卡的「数字 \| 徽章 \| 小字」） |
| `frontend/src/testing/expiryRecords.ts`（新） | 测试专用：用真实生产者（`makeRecord` → `buildRiskUpdate`）造 6 种记录：vision 过期（4 s）、telemetry 过期（7.5 s）、两路都过期、vision 没收到（未过期）、两路 fresh、历史 `stale`（无 provenance 字段）。**两路年龄故意不同**（4 / 7.5），接线写反或写丢时，被检查的文字会变，而不是碰巧通过 |
| `frontend/src/components/branchStatusRender.test.ts`（新，18 个测试） | `BranchStatusPill` 7、`ModalityCard` 5、`AlertBanner` 6 |
| `frontend/src/views/branchStatusRender.test.ts`（新，15 个测试） | `LiveMonitor` 5、`SignalInspector` 5、`ExplanationView` 5 |
| 本报告 | §7 第 7 条加一句指向本节；追加本节 |

没有改任何视图的实现：评审指出的是「缺守卫」，不是「实现错了」，四个视图的接线本身是对的（测试在未变异的代码上直接通过，且变异后变红，见 R1.4）。

### R1.3 测试断言了什么

**组件层（直接给 props）。** `BranchStatusPill`：过期带年龄读 `<span class="pill pill--expired">expired (4 s)</span>`；年龄按生产者记录的三位小数原样打印（`expired (3.001 s)`）；没有可测年龄读 `expired`；没收到读 `pill--missing` / `missing`；fresh；**历史 `stale` 仍读 `stale`**；过期与缺失的标记不相同。`ModalityCard`：过期读「`—` \| `expired:expired (4 s)` \| `Expired`」，没收到读「`—` \| `missing:missing` \| `No input`」，fresh 读「`50%` \| `fresh:fresh` \| `0.50`」，历史 stale 读「`42%` \| `stale:stale` \| `0.42`」。另有一条类型层测试：漏传 `expiry` 带 `// @ts-expect-error`（若 `expiry` 再次变成可选，该指令变成「未使用」，`tsc --noEmit` 变红），并断言漏传的渲染会抛 `TypeError`，而不是印出 `missing`。

**接线层（每个视图，五个场景：vision 过期 / telemetry 过期 / 两路过期 / vision 没收到 / 历史 stale）。**

- `LiveMonitor`：两张 `ModalityCard`（数字 + 徽章 + 小字）、「Vision freshness」「Telemetry freshness」两个徽章、两路都过期时的「Assessment unavailable」与 `SystemHealth` 徽章。
- `SignalInspector`：「P_distraction」「Telemetry non-safe risk」两个数值、两个 freshness 徽章。
- `ExplanationView`：「P_distraction」「Telemetry Non-Safe Risk」各出现两次（汇总格 + 证据卡），用数组断言两处都对；两个「Freshness」徽章（vision 卡在前、telemetry 卡在后）；「Active inputs」文字。
- `AlertBanner`：「Visual distraction: … \| Telemetry non-safe: …」两个数字；两路都过期时显示「No assessment for the latest window」。

期望值全部是测试里的字面量（如 `"— | expired:expired (4 s) | Expired"`），没有从实现 import 常量来构造期望值。每个数值 / 徽章都是按「行标签」取的，所以「某处有个 `expired` 徽章」不能代替「vision 那一行是 `expired (4 s)`」。

### R1.4 执行的命令与输出

**门禁（真实工作树，最终状态）：**

```
cd /Users/liu/Desktop/FYP2-Live-System
export PYTHONDONTWRITEBYTECODE=1
(cd backend && TMPDIR=$(mktemp -d) PYTHONPATH=. ../.venv/bin/python -m pytest tests -q -p no:cacheprovider)
  -> 704 passed, 1 warning in 8.75s          # 1 条 starlette 弃用 warning，与本项无关
./node_modules/.bin/vitest run --no-cache
  -> Test Files  21 passed (21)
     Tests  594 passed (594)
./node_modules/.bin/tsc --noEmit            -> exit=0，无输出
./node_modules/.bin/eslint .                -> exit=0，无输出
```

两个新测试文件单独跑：`vitest run --no-cache frontend/src/components/branchStatusRender.test.ts frontend/src/views/branchStatusRender.test.ts` → 2 个文件、33 个测试全部通过。新文件另用 `prettier --check` 检查（先 `--write` 格式化过一次），`All matched files use Prettier code style!`。

**隔离副本与变异。** 副本：`git archive HEAD` 解包到 `/var/folders/0k/dtzqmkm53vqgg530vd7h3fmr0000gn/T/tmp.JloHK992Xv`，叠上本轮的 1 个修改文件与 4 个新文件，`node_modules` 以符号链接接入（与第一轮相同做法，`vitest --no-cache`）。变异脚本 `…/scratchpad/mutate_r1.py`：每个变异替换一处**精确出现一次**的字符串（出现次数不对即断言失败），在副本里跑两个新测试文件的 vitest 与 `tsc --noEmit`，然后从真实工作树拷回并 `diff` 确认还原。全部变异结束后，`diff -rq frontend ai backend docs` 对真实工作树与副本无差异；真实工作树的 `git status` 只有本轮的 1 个修改文件、4 个新文件。**没有在真实工作树里做任何变异。**

### R1.5 变异结果

先是评审发现里的四个回退（原样）：

| # | 变异（副本里） | 结果 |
|---|---|---|
| E3 | `LiveMonitor` 遥测 `ModalityCard` 去掉 `expiry={telemetryExpiry}` | **vitest 5 failed**（LiveMonitor 的 vision 过期 / telemetry 过期 / 两路过期 / …）；**`tsc` exit 2**：`LiveMonitor.tsx(133,16): error TS2741: Property 'expiry' is missing in type '{ title: string; probability: number; freshness: FreshnessStatus; }' but required in type 'ModalityCardProps'` —— 评审说「连类型检查都拦不住」，现在拦得住 |
| E3b | 同上，但改成传一个写死的 `{ expired: false, ageS: null }`（能过类型检查的版本） | vitest **2 failed**（telemetry 过期、两路过期），tsc 0 |
| E4 | `ExplanationView` vision「Freshness」徽章改回 `<Pill label={visionFreshness} tone={visionFreshness} />` | vitest **2 failed**（vision 过期、两路过期） |
| E5 | `SignalInspector` 遥测数值不再传 `telemetryExpiry.expired`（传 `false`） | vitest **2 failed**（telemetry 过期、两路过期） |
| E6 | `AlertBanner` vision 传 `false` | vitest **1 failed**（`AlertBanner … vision expired, telemetry fresh`） |
| E3-6 | E3b + E4 + E5 + E6 **同时**打上，然后跑**全量**门禁（评审的原实验） | 全量 vitest **7 failed / 587 passed（594）**；`tsc` 0；`eslint` 0。评审当时是「561 passed、tsc 0、eslint 0」，现在 vitest 变红 |

然后是其余每一个接线位置（让「每个位置都有守卫」成立，而不只是评审点名的四个）：

| # | 变异 | 结果 |
|---|---|---|
| L1 | LiveMonitor vision `ModalityCard` 的 expiry 写死未过期 | vitest 2 failed |
| L2 | LiveMonitor「Vision freshness」徽章 expiry 写死未过期 | vitest 2 failed |
| L3 | LiveMonitor「Telemetry freshness」徽章 expiry 写死未过期 | vitest 2 failed |
| L4 / L5 | `liveMonitorModel` 的 `visionExpiry` / `telemetryExpiry` 读成另一路（互换） | 各 vitest 3 failed |
| S1 | SignalInspector vision 数值传 `false` | vitest 2 failed |
| S2 / S3 | SignalInspector vision / telemetry freshness 徽章 expiry 写死未过期 | 各 vitest 2 failed |
| X1 | ExplanationView 汇总格 P_distraction 传 `false` | vitest 2 failed |
| X2 | ExplanationView 汇总格 Telemetry Non-Safe Risk 传 `false` | vitest 2 failed |
| X3 | ExplanationView vision 证据卡数值传 `false` | vitest 2 failed |
| X4 | ExplanationView telemetry 证据卡数值传 `false` | vitest 2 failed |
| X6 | ExplanationView telemetry「Freshness」徽章改回普通 `Pill` | vitest 2 failed |
| X7 | ExplanationView `telemetryExpiry` 读成 vision 分支 | vitest 3 failed |
| A1 | AlertBanner telemetry 传 `false` | vitest 1 failed |
| C1 | `BranchStatusPill` 忽略 expiry | vitest 14 failed |
| C2 | `ModalityCard` 小字传 `false` | vitest 4 failed |
| C3 | `ModalityCard` 徽章 expiry 写死未过期 | vitest 4 failed |
| C4 | `ModalityCard` 的 `expiry` 改回「可选 + 默认 NOT_EXPIRED」（原来的形状） | vitest 1 failed（那条「必填」测试）；**`tsc` exit 2**：`branchStatusRender.test.ts(111,11): error TS2578: Unused '@ts-expect-error' directive.` |
| P1 | `describeBranchStatus` 永远不说 expired | vitest 13 failed |
| P2 | `branchExpiry` 永远不报年龄 | vitest 9 failed |

**一次作废的结果，如实写出。** 第一遍运行时，我的变异脚本里「写死未过期」的常量写成了双层花括号，导致 E3b、L1、L2、L3、S2、S3、C1、C3 与 E3-6 的变异后源码是**语法错误**；它们当时显示的「RED」只是 `tsc` 报了 TS1136 / TS1005 解析错误，**不是**测试抓到了回归，这些结果作废。我修正了常量，并给脚本加了保护（出现 TS1xxx 语法错误的变异一律标为无效、不计入），然后把这 9 个变异重跑一遍；上面表里这 9 项的数字都是重跑后的真实结果。E3、E4、E5、E6、L4、L5、S1、X1–X4、X6、X7、A1、C2、C4、P1、P2 在第一遍就是有效变异（它们的 `tsc` 报错是 TS2741 / TS2578 这类语义错误，不是语法错误），未受影响。

### R1.6 测试数字的变化

| 门禁 | 第一轮结束 | 本轮结束 | 变化 |
|---|---|---|---|
| pytest | 704 | **704** | 0（本轮未碰后端） |
| vitest | 561 | **594** | **+33**：`branchStatusRender.test.ts`（components）18 + `branchStatusRender.test.ts`（views）15；没有删除、没有改名、没有改动任何既有测试 |
| tsc | 0 | 0 | 0 |
| eslint | 0 | 0 | 0 |

### R1.7 仍然覆盖不到的东西

1. **静态渲染没有 DOM、没有 CSS、不跑 effect / hook。** 它能证明「页面上这一行写的是 `expired (4 s)`，徽章 class 是 `pill--expired`」，不能证明颜色。`.pill--expired` 规则确实存在（`frontend/src/styles.css:536`），但没有测试检查它，也**没有做浏览器冒烟**（不得启动 vite dev server）。
2. 两个图表（`TrendChart`、`DistributionChart`，recharts 的 `ResponsiveContainer`）在服务端渲染下是空容器，图表里的内容不在本轮测试范围；与本条发现无关。
3. `App.tsx` 把 `stale`（显示年龄）传给 `LiveMonitor` / `AlertBanner` 的接线不在本轮范围；两个视图对 `stale` 的渲染本来就有别的测试。
4. 第 7 节第 7 条原先说「由 `tsc` 与 `eslint` 保证」，这个说法对接线不成立（`eslint` 不管 prop 值，旧的可选 prop 还让 `tsc` 放过了漏传）；现在接线由本轮的静态渲染测试保证，剩下的只是上面第 1 点的视觉部分。
5. 本轮没有碰第 7 节的其他遗留项（Live 遥测时间戳、UT-TIME-05、导出缺 `expired` / `age_s` 两列、解释文字里的「stale」措辞、过时文档），它们仍如第一轮所写。

### R1.8 证据路径

- 修改：`/Users/liu/Desktop/FYP2-Live-System/frontend/src/components/ModalityCard.tsx`
- 新增：`/Users/liu/Desktop/FYP2-Live-System/frontend/src/components/branchStatusRender.test.ts`、`/Users/liu/Desktop/FYP2-Live-System/frontend/src/views/branchStatusRender.test.ts`、`/Users/liu/Desktop/FYP2-Live-System/frontend/src/testing/markup.ts`、`/Users/liu/Desktop/FYP2-Live-System/frontend/src/testing/expiryRecords.ts`
- 变异脚本与输出（本会话临时目录）：`/private/tmp/claude-501/-Users-liu-Desktop-FYP-In-Cabin-Driver-Assessment--1--claude-worktrees-exciting-keller-fdf913/43d73f6d-ed36-4f8a-b584-13c974ccd767/scratchpad/` 下的 `mutate_r1.py`、`mut_r1.out`（第一遍，含作废项）、`mut_r1b.out`（9 项重跑）、`fullrun_r1.py` + `mut_r1_fullrun.out`（E3-6 全量）。
- 隔离副本：`/var/folders/0k/dtzqmkm53vqgg530vd7h3fmr0000gn/T/tmp.JloHK992Xv`（其中的 `mut_r1_results.json` 只保存最后一次运行，即 9 项重跑；第一遍的完整输出在 `mut_r1.out`）。
