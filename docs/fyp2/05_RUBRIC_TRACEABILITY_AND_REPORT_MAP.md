# Rubric Traceability and Report Change Map

> 审计日期：2026-10-10（Asia/Kuala_Lumpur）；实跑检查时间见各 evidence 日志（主要为 2026-10-09）。审计对象是用户确认的桌面主仓库 `/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1`，branch `dev_cc`，HEAD `17c4b41bcfe517c8311b7f6fc2a327f616a916fe` **加未提交内容**。本文所有应用源码相对路径都相对此根目录，不相对当前旧工作树。输出工作树 HEAD `ae550415237fc1f67bf0de50c643a6d8bd6aca60`。命令 ID、环境、时间、退出码、指纹见 [07 证据索引](07_EVIDENCE_MANIFEST.md) 与 [source inventory](evidence/source_inventory.json)。

证据层次：`CURRENT_VERIFIED`=本次源码/产物检查或明确限定范围的实跑；`FYP1_REPORTED`=未在本次对应范围复现的继承指标；`PLANNED`=建议，未执行。旧实验日志标明 historical，不算本次运行。实现状态与测试执行状态分别记录；`MISSING_TEST` 是测试缺口标记，不是实现状态。未发现只适用于已扫描范围。


## Rubric provenance and interpretation

The supplied v2 master/spec/map state: analysis/design8, development8, evaluation8, conclusion/objectives3, references1, abstract≤300 words2. An **original University/AP2 marking sheet or final thesis** was not found in the audited primary repository. These are therefore **user-supplied rubric requirements**, not independently authenticated official marks. No earned score is awarded by this audit. The two DOCX files in the audit package are companion specifications, not evidence of an original university rubric.

Ch1–3: preserve established problem/background/literature, updating actual model set, dataset limits, evaluation terminology and methodology. No generated abstract, literature-currency claim or APA compliance verdict without the real manuscript/reference list.

## Chapter/evidence map

| Chapter / requirement / supplied weight | Current evidence and source | Status | Missing prerequisite and safe report action |
|---|---|---|---|
| 4.1 Functional/nonfunctional requirements | v2 specs; API schemas; tests in02 | `PARTIALLY_VERIFIED` | Add test IDs and explicit unavailable/error/logging/latency requirements; do not call proposed criteria measured |
| 4.2 AI/fusion/freshness/EMA/FSM | `trained.py:23–135`, `fusion.py:12–76`, `inference.py:13–73` | `CURRENT_VERIFIED` code; numerical diagnostics partly fail | Describe 3 severities plus timer state; distinguish raw vs EMA output; disclose both-missing flaw until fixed |
| 4.3 High-level architecture | actual paths in01; `App.tsx:50–79`, `useLiveSession.ts:137–179` | `CURRENT_VERIFIED` static | Diagram separate TS/localStorage replay and backend canonical live; do not draw a single API-backed replay path |
| 4.4 UML/use case/sequence/data flow | earlier diagrams/screenshots exist in docs/evidence; updated audit diagram01 | `PARTIALLY_VERIFIED` | Revise diagrams to exact live/replay/error flows; screenshot or old diagram alone does not validate implementation |
| 4.5 Five interfaces/accessibility | view files, build, historical screenshots; manual prototype checklist | `PARTIALLY_VERIFIED` | Current browser/keyboard/readability check and error states, no inferred user satisfaction |
| **Ch4 total8** | design artifacts + code trace | no marks awarded | Update against code, not implementation metrics in design chapter |
| 5.1 Environment | current evidence source inventory, ENV-VERSIONS, BUILD-RUNNER | `CURRENT_VERIFIED` subset | Exact CPU/memory unavailable; Python deps not locked; add install/artifact manifest later |
| 5.2 Data preparation | sibling split metadata/hash audit, notebook data loading | `PARTIALLY_VERIFIED` | No near-duplicate pixel audit or historic immutability proof; telemetry source-ID/generator units incomplete |
| 5.3 Model development/HPO | two baseline notebooks; real model files; five-model audit04 | `PARTIALLY_VERIFIED` baseline; full HPO `PLANNED_ONLY` | ResNet18/RF/LR and bounded tuning all5 mandatory; describe search/selection here, results in6.2 |
| 5.4 Actual inference/fusion/temporal | real local ONNX/XGB API tests | `TEST_PASSED` limited integration | Fix no-evidence contract, reconcile legacy FSM claim and error handling |
| 5.5 API/React/UX | client + useLiveSession error/loading/backoff; historical browser logs | `PARTIALLY_VERIFIED` | Fresh browser/API/DB identity trace and network/model/DB failure recovery |
| 5.6 Session/export | CRUD/idempotency/flag/restart/migration/export tests | `TEST_PASSED` listed assertions | Long-session count/log completeness/error-event evidence still absent |
| **Ch5 total8** | meaningful real runtime exists | not complete sign-off | Do not carry forward old “not integrated” text or claim all tuning done |
| 6.1 Setup | hashes/env/test preconditions in07 | `PARTIALLY_VERIFIED` | Pre-register units, sample design, independence, seed and raw outputs for planned experiments |
| 6.2 Comparison/tuning | XGB full current test; MobileNet inherited full test + current subset | `PARTIALLY_VERIFIED` | No five-model matched results; no HPO outcome claim |
| 6.3 E1 | historical val dim/Gaussian blur pilot | `PARTIALLY_VERIFIED` pilot only | New paired held-out6×3 and telemetry D0–D3 from03 |
| 6.4 E2 | fusion code + small formula tests | `PARTIALLY_VERIFIED` | Constructed pair/5 weights results; independent scenario interpretation |
| 6.5 E3 | missing/stale diagnostics, two unavailable failures | `PARTIALLY_VERIFIED` | Include failures and ΔR distribution/old target attainment; never force unconditional≤.15 |
| 6.6 E4 | clocked FSM/EMA tests, load errors | `PARTIALLY_VERIFIED` | Ablations, runtime faults, recovery, defined completeness denominator |
| 6.7 E5 | v2 design only | `PLANNED_ONLY` | Same source pairs/counterfactuals, dilution and negative cases |
| 6.8 Software/performance | 60 test results, build/lint; diagnostics separate | `PARTIALLY_VERIFIED` | Current browser system/error handling and capture→render latency/endurance |
| 6.9 UAT | no actual respondent/task/feedback evidence | `NOT_FOUND` | Recruit/consent and execute real tasks, anonymized results; no fabricated n |
| 6.10 Discussion | evidence limits in00/03/04 | supported audit discussion | Explain model-vs-system/field scope and uncertainty; do not award safety claims |
| **Ch6 evaluation8** | ML cannot replace unit/integration/system/UAT/error categories | incomplete | Keep missing results explicitly pending |
| 7.1 Objective1 fusion framework | current formula+adapters+small tests | `PARTIALLY_VERIFIED` | Framework implemented; no independent real-world risk advantage established |
| 7.1 Objective2 severity-aware score | levels30/60 + timing tests; no-evidence defect | `PARTIALLY_VERIFIED` | Operational levels, not accident severity ground truth |
| 7.1 Objective3 repeated inference/reliability | loop and DB state implemented; restart/concurrency pass | `PARTIALLY_VERIFIED` | No sustained endurance/log99%/full fault recovery evidence |
| 7.2–7.4 strengths/limits/future /3 | live baseline wiring and versioned outputs supported | bounded narrative | Unpaired data, synthetic telemetry, c9, camera viewpoint, probability calibration, missing target hardware; future synchronized data/external validation |
| Abstract≤300 words /2; APA references /1 | actual final abstract/list absent | `NOT_FOUND` for manuscript verification | Check final artifacts later; no current compliance assertion |

## Claim-to-evidence wording matrix

| Proposed statement | Experiment/test | Status / citation | Acceptable wording | Prohibited overclaim |
|---|---|---|---|---|
| System uses trained models | EX-PY-14; service smoke | `TEST_PASSED`; `test_live_inference.py:42–81`, PYTEST | Local live API executed existing ONNX/XGB and persisted/exported outputs for deterministic fixtures | Fully validated road monitoring system or both real sensors |
| Full camera-to-dashboard demo works | historical browser logs, static UI code | `PARTIALLY_VERIFIED`; `docs/evidence/2026-10-05/browser-views-exports-check.log` | Prior simulated-camera demonstration exists; current backend verified; browser run not repeated | This audit freshly demonstrated physical-camera E2E |
| Vision baseline macro-F1=.8746 | full3657 historical benchmark | `FYP1_REPORTED`, historical09-28 artifact inspected; current20-smoke | Stored full source-test result .8746; current smoke confirms limited reload/parity | Full vision metric reproduced this audit or frontal accuracy=.8746 |
| XGB macro-F1=.999333 | ML-TELEMETRY | `CURRENT_VERIFIED`; telemetry_recheck.json | Same4500-row synthetic test reproduced with best iteration | 99.93% accurate on real roads |
| Split is subject-disjoint | metadata audit | `CURRENT_VERIFIED`; data_artifact_audit.json | No driver-ID overlap in current CSV;18/4/4 drivers | No possible leakage/duplicates anywhere or immutable training provenance proved |
| 60 tests pass | PYTEST+VITEST | `TEST_PASSED`; logs,02 |60 existing automated cases passed; audit flags weak/invalid oracles and gaps | All rubric categories, UI and UAT passed |
| FSM is correct | exact guarded sequences | `PARTIALLY_VERIFIED`; PYTEST/DIAGNOSTICS | tested2s/10s sequences and gap reset behave as asserted | Five-state machine independently verified in all failure conditions |
| Missing fusion robust | E3 diagnostics | `PARTIALLY_VERIFIED`; DIAGNOSTICS | one-missing/stale arithmetic works in selected cases; both-missing and zero-weight need repair | Every missing case maintains ΔR≤.15 or no-evidence is safe |
| Fusion better/safe | E2/E5 planned | `PLANNED_ONLY` | Will examine scenario consistency, complementarity and attenuation | Improved accident prevention/high-risk accuracy without paired truth |
| Models tuned | M1 | `PLANNED_ONLY`;04 | bounded search plan for all5; current fixed baselines | early stopping/env knobs equal completed5-model HPO |
| Performance target reached | PERF-01/02 | `NOT_FOUND` required artifacts | model-only timings available; E2E/completeness measurement pending | server precommit latency proves capture→render≤1s or≥99% completeness |
| UAT successful | UAT-01..05 | `NOT_FOUND` real results | proposed tasks, no actual participants/results | invented sample count, satisfaction or acceptance percentage |

Reference scope: no external literature review was requested or performed. Local evidence, not unverified web claims, supports this implementation audit. Supervisor should confirm rubric and revision decisions in08 before final report freeze.
