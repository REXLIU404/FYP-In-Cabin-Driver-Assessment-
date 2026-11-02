# Week 7 Critical Path and Action Plan

> 审计日期：2026-10-10（Asia/Kuala_Lumpur）；实跑检查时间见各 evidence 日志（主要为 2026-10-09）。审计对象是用户确认的桌面主仓库 `/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1`，branch `dev_cc`，HEAD `17c4b41bcfe517c8311b7f6fc2a327f616a916fe` **加未提交内容**。本文所有应用源码相对路径都相对此根目录，不相对当前旧工作树。输出工作树 HEAD `ae550415237fc1f67bf0de50c643a6d8bd6aca60`。命令 ID、环境、时间、退出码、指纹见 [07 证据索引](07_EVIDENCE_MANIFEST.md) 与 [source inventory](evidence/source_inventory.json)。

证据层次：`CURRENT_VERIFIED`=本次源码/产物检查或明确限定范围的实跑；`FYP1_REPORTED`=未在本次对应范围复现的继承指标；`PLANNED`=建议，未执行。旧实验日志标明 historical，不算本次运行。实现状态与测试执行状态分别记录；`MISSING_TEST` 是测试缺口标记，不是实现状态。未发现只适用于已扫描范围。


## Readiness decision

**NO-GO for claiming the full W7 milestone today.** This is an evidence-based readiness decision, not a prediction that the deadline is impossible and not a claim about the current academic week. The normal baseline backend is already integrated, so do not restart from a Mock-only architecture. Complete P0 correctness/recovery/package proof before expanding model scope. W3 must remain an early gate, not be postponed until W7.

Effort S=roughly≤1 focused day, M=2–3 days, L=4+ days or external dependency. Estimates are planning assumptions for one developer, not measured durations/promises. HPO wall-time depends on available hardware. Roles are proposals, not assigned agents.

| Gate | Required deliverable | Actual evidence | Status | Blocker | Dependency | Next action | Acceptance test | Priority / effort |
|---|---|---|---|---|---|---|---|---|
| W1 | repo/data/checkpoint/contracts/test inventory reproducible | nine audit docs; source/split hashes; provider loads;60 cases | `PARTIALLY_VERIFIED` | source dirty; models ignored; units/immutable provenance gaps | approved snapshot | freeze release manifest, define feature units and no-evidence representation | UT-MODEL01/02 + clean start on fixed artifacts | P0/M |
| W2 | transparent mock/replay React↔API↔DB/export + UX | API replay CRUD passed; browser replay is TS/localStorage; live API client exists | `PARTIALLY_VERIFIED` | exact API-backed replay demo not present; no fresh browser suite | W1 contract | choose backend-backed replay or explicitly approve separate demo architecture and verify live integrated skeleton | ST-REPLAY01, IT-UI01, IT-DB01 | P0/M |
| W3 | actual MobileNetV3+XGB input→UI→durable log | live backend model integration PASSED; static React consumer; historical simulated-camera UI | `PARTIALLY_VERIFIED` | no fresh repeatable full-browser trace; error/no-evidence defects | W1+W2 | preserve baseline path; fix P0 then record source-ID model/API/UI/export chain | IT-AI01, IT-UI01, ST-REPLAY01 | P0/M |
| W4 | ResNet18/RF/LR common baselines and controlled tuning scripts |2 baseline notebooks, unrelated B0/Small/probe scripts | `PLANNED_ONLY` required comparator set | comparator scripts/checkpoints absent | frozen splits, contracts, W3 running | add comparator pipelines after this audit and implementation authorization | all5 run/config/val outputs; train-only LR pipeline | P1/L |
| W5 | bounded HPO all5, validation selection, freeze/deploy final | no full5-model search records | `PLANNED_ONLY` | budget/search/selection artifacts absent | W4 | implement finite budget04, select on validation, preserve original checkpoints | traceable trials/configs/seeds, held-out test only after freeze | P1/L |
| W6 | E1–E5 generators/smoke; unit/integration/system/error; latency/logging |60 tests+small diagnostics; historical limited E1 pilot | `PARTIALLY_VERIFIED` | required generators/scenarios/oracles/perf/error recovery absent | W3 stable; W4/W5 model IDs for final experiments | prepare/validate generators early; run bounded smoke then approved experiments | pack02/03, PERF01/02, failure and recovery exports | P0 reliability +P1 evaluation/L |
| W7 | feature-complete reproducible demo, regressions, evidence exports, Ch5 nearly complete | major runtime modules present; no clean-release/full signoff evidence | `BLOCKED` gate | unresolved B01–B05, W4–W6 deliverables and UAT plan/results distinction | preceding gates | freeze only after P0 zero and full acceptance evidence; document any scope reduction approved by supervisor | demo checklist below + final manifest | P0/L |

## Dependency-ordered work packages

| Order / ID | Work and evidence basis | Depends on | Completion evidence | Owner / priority / effort |
|---|---|---|---|---|
|1 A01 | resolve zero-denominator/unavailable contract; B01/B02, DIAGNOSTICS | supervisor D01 | API/schema/UI/export semantics agreed; regression outputs for all missing/zero-weight cases | SYS+QA/P0/M |
|2 A02 | preserve source/model/split hashes, reproducible package; dirty source inventory | none; can prepare alongside A01 | source version + artifact distribution/load verification + dependency lock + setup log on clean disposable environment | SYS/P0/M |
|3 A03 | add exact independent cross-language formula/EMA/FSM/freshness/reset tests | A01 | UT-FUS/UT-TIME complete; source-specific discrepancies explained | SYS+QA/P0/M |
|4 A04 | implement observable error events and test model-run/network/storage failure/recovery | D02 error policy; A01 | ST-FAIL and ST-RECOVER API+UI+DB traces; no fake model fallback | SYS+QA/P0/M |
|5 A05 | reproducible baseline E2E browser+DB/export/restart demo | A02–A04 | ST-REPLAY01, IT-UI01, IT-DB01; recorded request/frame/model IDs and exact command | QA/P0/M |
|6 A06 | bounded all5 comparator/HPO scripts and validation selection | W1 immutable splits, D03 budget; do not delay A05 | actual trials and validation selection, not placeholders; deploy selected primary checkpoint with rollback copy | ML-V+ML-T/P1/L |
|7 A07 | E1 exact generators; D1–D3 train-only stats/mask; label quality protocol | D04 units/bounds, A06 final IDs | parameter+source manifests, paired row counts/hashes, sample QC | ML-V+ML-T/P1/L |
|8 A08 | E2/E3/E5 pairs,5 weights, missing variants, non-circular oracle | D05/D06 policy, A07 variants | per-pair outputs incl negative/attenuation examples; Δtarget attainment separated from formula | SYS+REPORT/P1/M |
|9 A09 | latency/completeness and sustained fault testing | D07 metrics, A04/A05 | raw timing/event ledger, p50/p95 and completeness denominator, no head-count-based claims | QA/P1/M |
|10 A10 | actual UAT + report update, mark unresolved external DMD | stable A05, D08–D10 | consented tasks/feedback and real results; Ch4–7 claims matrix complete | REPORT+QA/P1/M–L |
|11 A11 | optional target hardware/packaging refinements | hardware confirmed; core gates complete | measured device gains; no random-weight accuracy claims | SYS/P2/L |

E1–E5 and UAT planning can progress while model scripts are prepared, but final comparative results must use frozen selected model identities. DMD access must not consume the critical path; agreed absence/restriction belongs in report limitations. Probability calibration is a limitation, not a new mandatory milestone.

## Minimal W7 demonstration sign-off

All boxes currently **unchecked for full end-to-end sign-off**, even when component tests already pass:

- [ ] Reconstruct app+weights using a recorded clean start without training/download surprises; record source/model/dependency hashes and database location.
- [ ] Fresh image fixture plus 8-feature record invoke real models; mode/input source visible;10/3 probabilities and raw/post-EMA values traceable; same request reaches UI and saved export.
- [ ] Start/pause/resume/restart/session switch preserve or reset state according to explicit policy; no cross-session contamination.
- [ ] All5 views read correct saved data; flag persists; JSON/CSV include entire session, not just latest500 UI items; unavailable is not a safe numeric result.
- [ ] One/both missing, stale/asynchronous, invalid input, model failure, network timeout and DB failure expose honest status and demonstrate recovery.
- [ ] Regression pack green with valid oracles; rejected/error events logged; accepted request counts reconcile; source no unresolved P0.
- [ ] Five-model/HPO and E1–E5 scripts/traceability ready per weekly gates; distinguish smoke, full experiments, blocked external data and actual UAT.
- [ ] Capture→render latency and logging targets measured under approved boundary; Ch5 can cite actual implementation and Ch6 manifest can locate every result.

## Next72 hours, dependency-based and unexecuted

**0–24h:** approve A01 contract and D02 fault policy; freeze hashes/package inventory; implement no-evidence fixes in a later authorized development pass and independent boundary tests. Exit: no more zero-denominator Low semantics, explicit error contract.

**24–48h:** A04–A05 repeatable baseline demo and fault/recovery; include DB/export/restart and browser mode truth. Exit: fresh trace and regression logs, remaining P0 openly listed.

**48–72h:** A06 bounded search configuration and scripts; A07/A08 deterministic tiny generation samples; PERF/UAT runbooks. Exit: predeclared artifacts and smoke-ready evaluation pipelines, **not** a fabricated claim that all tuning/results/UAT were finished in72h.

No implementation in this plan was started by the audit. Finishing audit documents does not check the W7 sign-off boxes.

---

## 增补：Live-only 范围落地（FYP2 阶段 3 · Task 9，2026-10-15）

> **以上正文是 2026-10-10 审计时的快照，其结论原样保留、不因本节而改**：NO-GO 的就绪判断、各 Gate 的状态、依赖有序工作包、W7 签收清单（全部仍为未勾选）都以正文为准。本节只记录一项范围决定及它对正文里个别条目的影响。

**决定（计划 D03 / D11 的落地）**：Live Monitoring 是唯一的主运行时。prepared-probability replay **保留**，降级为 legacy / test-only：它用于回归测试与向后兼容，不再是验收路径，也没有被删除。

对正文条目的影响：

1. **`ST-REPLAY01`（W2、W3、A05 引用的那一项；计划里写作 `ST-REPLAY-01`）在本阶段由 Live 端到端取代。** 被验收的链路是：摄像头帧 + prepared **raw** telemetry → `POST /api/sessions/{id}/infer` → MobileNetV3 + XGBoost → 后端 freshness / EMA / late fusion / Alert FSM → SQLite → 五个视图（只渲染已保存的记录）。手工验收清单见 [`prototype-tests/README.md`](../../prototype-tests/README.md)；脚本化的 Live 端到端是计划中的 Task 10（`backend/tests/test_live_e2e.py`），**写本节时尚不存在**。
2. **W2 的「选择 backend-backed replay，或明确批准独立的 demo 架构」一项**，现按后者的收窄形式落实：浏览器里的 replay 保持独立、显式标注为 legacy / test-only，不进入验收。
3. **Live 路径只读 prepared 的 raw telemetry（8 个特征，`PREPARED_RAW_TELEMETRY`），不读任何 prepared probability。** 带 `P_distraction`、`P_telemetry_anomaly`、`visual_top_classes` 的 `PREPARED_SESSION_WINDOWS` 只留给 replay；有静态测试守住这条边界。
4. **回访用户不会被存储的设置悄悄带回 replay**：每次加载都从 Live 开始，replay 只有在页面里被明确选择时才进入。

**本节没有改变的事实**（仍如正文与阶段 1–2 的报告所述）：
- 没有任何 W7 签收框因本节变为已勾选；
- Live 遥测的游标语义（2 s 节拍、暂停冻结、可注入时钟）与遥测采集时间戳并入 R10，不在本次落地内，Live 遥测的 `telemetry_timestamp` 仍是发送时刻；
- 3 s 证据年龄上限是设计阈值，不是验证过的安全阈值；
- 前向摄像头精度、目标硬件性能与现场验证均未建立。
