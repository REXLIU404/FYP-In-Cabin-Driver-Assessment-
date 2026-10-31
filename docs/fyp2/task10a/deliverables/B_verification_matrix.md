# Task 10A Deliverable B: Verification Matrix

- Scope: plan `docs/plans/2026-10-25-task-10a-candidate-integration.md`, section 9 (Gates A-E), section 10 item B, section 15 "Gate rule" (all subagent reports attached to deliverable B).
- Repository: `/Users/liu/Desktop/FYP2-Live-System-Integration`, branch `fyp2/live-system`, HEAD `fe7852a` (read with `git log --oneline`).
- Prepared: 2026-10-31, read-only compilation. No server, test or gate was run to produce this file; every result below is copied from the file cited next to it.
- Path conventions: plain paths are relative to the Integration repo. `LIVE/` = `/Users/liu/Desktop/FYP2-Live-System` (git-ignored audit files live there). `ML/` = `/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1` (read-only).
- Verdict vocabulary: auditors used `VERIFIED_PASS / PARTIAL / BLOCKED / FAILED` (plan section 9). The PASS/FAIL/BLOCKED column below is this matrix's summary of the final auditor verdict.

## 1. Final status per stage

| Stage | Final verdict | Auditor | Audit report | Earlier rounds |
|---|---|---|---|---|
| 1. Candidate Provider Integration | VERIFIED_PASS (2026-10-27) | Codex, CX-A1 (independent, read-only) | `LIVE/.superpowers/collab/codex/stage1_audit.md` (verdict at line 290) | none |
| 2. Paired System Comparison | VERIFIED_PASS (re-audit, 2026-10-29) | A2, fresh Claude subagent, read-only | No standalone report file found in either worktree; findings and verdicts recorded in `docs/fyp2/task10a/stage2_audit_table.md` §5 and `LIVE/.superpowers/collab/BOARD.md` (task row A2; entries 2026-10-29 13:11 and 16:55) | Round 1 PARTIAL (finding F-1) |
| 3. Runtime Evaluation | VERIFIED_PASS (re-audit, 2026-10-30) | Fresh read-only subagent | `docs/fyp2/task10a/stage3_stage5_reaudit.md` | CX-A3 PARTIAL (R-1), `LIVE/.superpowers/collab/codex/stage3_audit.md`; fresh subagent PARTIAL (O-1, O-5), `docs/fyp2/task10a/stage3_r1_stage5_audit.md` |
| 4. Target Camera (demo-path / report guard) | VERIFIED_PASS (2026-10-29) | Codex, CX-A3 | `LIVE/.superpowers/collab/codex/stage3_audit.md` §5 | none |
| 5. Release Decision (Steps 1-3 + recorded decision) | VERIFIED_PASS (re-audit, 2026-10-30) | Fresh read-only subagent | `docs/fyp2/task10a/stage3_stage5_reaudit.md` | Fresh subagent PARTIAL (O-2, O-3, O-4), `docs/fyp2/task10a/stage3_r1_stage5_audit.md` |

User decision U-5 (2026-10-30), recorded in `docs/fyp2/task10a/release_decision.md` (status line and §3): option A, the active vision model stays stable MobileNetV3-Large. ResNet18 `search_004`/seed42 stays an admitted, switchable candidate (`DRA_ACTIVE_VISION`). No configuration was changed (`active_vision = "stable"` is the code default, per `docs/fyp2/task10a/stage5_audit_table.md`). **The written signature is still pending.**

## 2. Gate matrix (plan section 9)

| Gate | Expected behaviour (plan §9 / §11) | Actual result | Evidence path | Result | Auditor / report |
|---|---|---|---|---|---|
| A: Model Artifact and Provider | Manifests validate, artifacts load, the real provider forward runs, class mapping is correct, outputs are valid | Both copied candidate packages print `valid` from the system CLI, exit 0 / 0. Real provider forward for 3 identities. Warm-up asserts (1, 10) finite output. The real-package tests (`-m candidates`) pass 6. Startup identities: stable `b3a42e8d…` (`MobileNetV3ONNX+XGBoost`), ResNet18 `5e226722…` (`VisionCandidateONNX+XGBoost`). CX-A1 reran the CLI on the LIVE package paths and got exit 0 / 0. | `docs/evidence/2026-10-26/task10a-stage1/manifest-cli-*.log`, `pytest-m-candidates.log`, `startup-default.json`, `startup-resnet18.json`, `SUMMARY.json`; `docs/fyp2/task10a/stage1_audit_table.md` §1 | PASS | CX-A1, `LIVE/.superpowers/collab/codex/stage1_audit.md` §1, §1.3 |
| B: Stable200 | The official deterministic provider test actually runs, and the pre-declared checks are evaluated | Overall PASS, exit 0, under the approved tolerance (`max_abs_prob_delta <= 1e-4` and argmax agreement = 1.0, FUD-01). parity100: stable 1.778e-7, RN 1.540e-7, MN-HPO42 1.688e-7, argmax 100/100 each. stable200 CSV: RN 1.479e-6 and MN-HPO42 6.869e-6, argmax 200/200. Stable has no stable200 reference (`NO_STABLE200_REFERENCE`, ruling C-3). Class rule: all unique modes equal the labels. CX-A1 ran a fresh forward of its own (`overall_status=PASS`, sha256 `92e8518a…`) and recomputed the results independently. | `docs/evidence/2026-10-26/stable200/official_stable200_behavior.json`, `README.md`; `docs/fyp2/task10a/tolerance_predeclaration.md`; `docs/fyp2/task10a/approval_record.json` | PASS | CX-A1, `stage1_audit.md` §1.1 |
| C: Integration Regression | Candidate support breaks nothing: stable provider, fusion, unavailable guards, EMA/FSM, API, logging/export, frontend | Every gate tied to a Task 10A milestone that was used as audit evidence is GREEN (§4). Stage 1: `777cd05`, pytest 1115 / vitest 972. Stage 3: `fe5c41d`, pytest 1355 / vitest 1022. Final fresh-clone gate: `f15f539`, pytest 1360 / vitest 1061, `DRA_REQUIRE_MODELS=1`. Auditor reruns: CX-A1 at `00b0e5d`, 5 gates GREEN (2026-10-27). CX-A3 C07 at `e04f662`: pytest 1355 passed, 8 deselected, 0 skipped. Re-audit B6 at `f5fb90f` (non-e2e): 1310 passed, 58 deselected. | `docs/evidence/2026-10-26/merge-ds1-gate/`, `docs/evidence/2026-10-29/stage3-gate/`, `docs/evidence/2026-10-30/stage5-coldstart-f15f539/` | PASS | CX-A1 §1.3 row C; CX-A3 `stage3_audit.md` §1; `stage3_stage5_reaudit.md` S3-e |
| D: Runtime Failure Handling | Missing or corrupted model, invalid manifest/hash, bad input, load or forward failure, candidate-to-stable recovery, failure provenance | Tampered package rejected with `model.sha256 mismatch` and no fallback to stable: GREEN 7 passed, RED 2 failed with the sha check removed. Hash, schema, class order, missing `safe_driving` and warm-up failure all raise `ModelUnavailable`, which returns 503. CX-A1 reproduced the RED/GREEN pair (2 passed exit 0 / 2 failed exit 1); an unknown candidate gives HTTP 503 and no silent fallback. Rollback drill: candidate active, then a fresh process with `DRA_ACTIVE_VISION` unset returns stable `b3a42e8d…`; 94 files under `ml/outputs` unchanged; 11/11, exit 0. Auditors reran the drill at `637a0ff` (A5) and at `f5fb90f` (B5): exit 0, 11/11. | `docs/evidence/2026-10-26/task10a-stage1/tamper-green.log`, `tamper-red-sha-check-removed.log`; `docs/evidence/2026-10-30/stage5-rollback-drill/` (`drill.log`, `drill.json`, `README.md`) | PASS | CX-A1 §1 row 4 and §1.3 row D; `stage3_r1_stage5_audit.md` S5-a; `stage3_stage5_reaudit.md` S5-a |
| E: Evaluation Evidence | Reproducible test and comparison evidence with IDs, preconditions, results, environment and model identities/hashes | Stable200: membership sha `601dc3ed…`, reference-file sha values pinned in the approved tolerance file. Stage 2: protocol gate 4/4, protocol hash unchanged after the run (`b6305022…`), input re-verified before each model, 0 field differences across 3 runs. Stage 3: six 10-30 `perf01_timings.json` files bound by sha256 and recomputed independently (6/6). Fresh-clone gates record Python 3.13.9, node v24.1.0, npm 11.4.2. Not verified: real camera, UAT, in-vehicle safety. | `docs/evidence/2026-10-26/stable200/README.md`; `docs/evidence/2026-10-29/comparison-official-bf76ddf/README.md`, `comparison_results.json`; `docs/evidence/2026-10-30/stage3-raw/README.md`; `docs/evidence/2026-10-30/stage5-coldstart-f15f539/SUMMARY.md` | PASS (within the stated scope) | CX-A1 §1.3 row E; A2 re-audit (via `stage2_audit_table.md` §5); `stage3_stage5_reaudit.md` S3-c |

## 3. Stage matrix (plan sections 4-8)

### Stage 1: Candidate Provider Integration (commits `871d309`, `09b4b8d`, `4ca3c69`, `90b5e2e`, merge `777cd05`; evidence `00b0e5d`)

| Audit point | Expected | Actual | Evidence | Result |
|---|---|---|---|---|
| Provider code committed after `2745348` | Commits on `fyp2/live-system` | CX-A1 checked `git merge-base --is-ancestor` for each commit, exit 0 | `docs/fyp2/task10a/stage1_audit_table.md` (commit table); CX-A1 check in `LIVE/.superpowers/collab/codex/stage1_audit.md` §1 row 1 | PASS |
| Both manifests valid (system CLI) | `valid`, exit 0 | exit 0 / 0 | `docs/evidence/2026-10-26/task10a-stage1/manifest-cli-*.log` | PASS |
| Real forward, compared with references | Within 1e-4, argmax 1.0 | See Gate B | `docs/evidence/2026-10-26/stable200/` | PASS |
| Hash check (red/green) | Tamper rejected; RED when the check is removed | 7 passed / 2 failed | `task10a-stage1/tamper-*.log` | PASS |
| Default remains stable MN | `/api/models` gives `stable_mobilenet_v3_large` | sha `b3a42e8d…`, `source = stable`; CX-A1 reproduced this on a free port with a temporary DB | `task10a-stage1/startup-default.json` | PASS |
| XGB untouched | Only vision-side hunks | 39 changed lines, `telemetry_or_xgb_lines: []` | `task10a-stage1/trained_py_diff_vs_2745348.diff`, `SUMMARY.json` | PASS |

Auditor: Codex CX-A1, target `00b0e5d`, 2026-10-27. Final: **VERIFIED_PASS**. Remaining items in the report: Minor corrections, and the 2026-10-26 gate-directory incident, which was disclosed and backed by fresh reruns (`stage1_audit.md` §3.2 and §5).

### Stage 2: Paired System Comparison (runner `6df94ef`, fix `bf76ddf`; official run `314dac8`)

| Audit point | Expected | Actual | Evidence | Result |
|---|---|---|---|---|
| Protocol written before the run, with the input hash | Protocol mtime earlier than the run; sha matches | `protocol_gate.checks` 4/4 true; `protocol_after_run.unchanged = true` | `docs/evidence/2026-10-29/comparison-official-bf76ddf/comparison_results.json`; `docs/fyp2/task10a/comparison_protocol.json` (sha `b6305022…`) | PASS |
| Input-set hash recomputable | `601dc3ed…` | Recomputed equal; source-id and image-bytes manifest hashes also recomputed | same | PASS |
| Run isolation | Fresh process and temporary SQLite per model | One subprocess per model, temp SQLite, synthetic clock; 0 field differences across `94c6d14`, `c0c6d43` and `bf76ddf` runs | `worker_spec_*.json`; `stage2_audit_table.md` §1 | PASS |
| Consistent with P4 (c9 is a weak class) | c9 argmax counts differ between models | stable `{0:6, 7:4, 9:10}`, RN `{0:3, 9:17}`, MN candidate `{0:3, 7:7, 9:10}`; `identical_results = false` | `stage2_audit_table.md` §1 | PASS |

Descriptive results only (no winner): argmax agreement with stable is 0.91 for RN and 0.90 for the MN candidate. RiskLevel differs in 5 and 6 of 200 windows. Source: `stage2_audit_table.md` §2. Argmax agreement measures agreement between models, not accuracy. Limitation: the fixed Safe telemetry row means this scenario cannot reach RiskLevel High or HIGH_ALERT. The user accepted the coverage as it is (FUD-B, `stage2_audit_table.md` §5).

Auditor: A2 (fresh Claude subagent). Round 1 was PARTIAL on F-1 (the protocol was not re-hashed after the run); F-1 to F-4 were fixed in `bf76ddf`. The re-audit on 2026-10-29 returned **VERIFIED_PASS**. R-1 and R-2 (document slips) were fixed in `695dad9`. R-3 is a known limitation: a future `backend/.env` could bypass `worker_env`.

### Stage 3: Runtime Evaluation (code `fe5c41d`, `1cd5660`)

| Audit point | Expected | Actual | Evidence | Result |
|---|---|---|---|---|
| Same-day latency JSON, MN and RN | Dated JSON with model identity | Six runs on 2026-10-30, alternating stable and RN, 600 windows each plus 20 warm-up, 9.77-9.79 Hz (`stage3-raw/README.md`) | `docs/evidence/2026-10-30/stage3-raw/*/perf01.json`, `runs.log` | PASS |
| RN capture-to-render p95 measured, not extrapolated | Measured value | RN p95 45 / 44 / 43 ms; stable p95 31 / 31 / 31 ms | `docs/evidence/2026-10-30/stage3-raw/README.md` | PASS |
| Quantiles recomputable from raw samples (R-1) | sha-bound raw timings | 6/6 sha256 bound; quantiles equal on independent recomputation (B1) | `stage3-raw/*/perf01_timings.json`, `recompute.log`; `stage3_stage5_reaudit.md` S3-c | PASS |
| Test goes red, then green | RED on old code, GREEN on new | RED at `e07ef42` (exit 1, `KeyError: 'raw_timings'`); GREEN with 29 passed; the strengthened test catches a constant-duration mutation (re-audit M1) | `stage3-raw/focused-test-RED-e07ef42.log`, `focused-test-GREEN.log`; `stage3_stage5_reaudit.md` S3-d | PASS |
| Full same-day regression | All gates exit 0 | `9255c83`: pytest 1359, vitest 1061. `f15f539`: pytest 1360, vitest 1061. Re-audit non-e2e: 1310 passed | `docs/evidence/2026-10-30/review-followups-coldstart-9255c83/`, `stage5-coldstart-f15f539/` | PASS |
| Log completeness with RN active | D1/D2 complete, 1 `input_validation` fault, 0 duplicates | D1/D2 210/210, 209 stored plus 1 fault, 0 duplicates. CX-A3's own rerun reached 211/211. The denominator is not fixed at 211 (see the README) | `docs/evidence/2026-10-29/perf-stage3/{stable,rn}/perf02.json` | PASS |
| Health | No new error-level logs | 10-30 runs: 6/6 `console_errors=[]`; 10-29: the 10 server logs are 0 bytes; the 10-30 perf01 server logs were not archived and cannot be recovered (O-5 residual) | `stage3_stage5_reaudit.md` S3-f; `stage3_audit_table.md` §1 and §6; `docs/evidence/2026-10-30/stage3-raw/README.md` | PASS (with O-5 residual) |

Audit history:
- CX-A3 (2026-10-29, target `e04f662`) returned PARTIAL on R-1: the 10-29 summary files contain no raw samples.
- A fresh subagent (2026-10-30, target `637a0ff`) returned PARTIAL. The two open items were O-1 (how R-1 is closed, needing user acceptance) and O-5 (log archiving).
- The user accepted the closure through 10-30 same-day re-measurement (FUD-1, `stage3_audit_table.md` §7).
- The re-audit (target `f5fb90f`) returned **VERIFIED_PASS**.

The 10-29 Stage-3 numbers are historical, summary-only records and are no longer the basis for Stage 3 or Stage 5.

### Stage 4: Target Camera (demo path and report guard)

| Audit point | Expected | Actual | Evidence | Result |
|---|---|---|---|---|
| The demo uses the replay path (4-C) through the full RiskUpdate chain | `CONSTRUCTED_SCENARIO_RUNTIME` on the Live/R10 path | Recorded in the note. CX-A3 ran its own full rehearsal (C12: 1 passed, exit 0) with a traceable temporary DB | `docs/fyp2/task10a/stage4_demo_path_note.md` §1; `docs/evidence/2026-10-29/constructed-scenario-merge-gate/ACCEPTANCE.md` | PASS |
| No replay numbers presented as Chapter-6 evaluation results | Only 6.7 mentions the constructed demo, and only to exclude it | CX-A3 C09 exit 0: Tables 16-20 and Table 23 traced to their sources; no demo hit-rate or RiskLevel numbers found as evaluation results | `stage4_demo_path_note.md` §3; DOCX sha `ea1778c1…` unchanged | PASS |
| Side camera (4-B) informal only | No evaluation evidence | Recorded as informal, user-only observation; the frontal-camera limitation stays | `stage4_demo_path_note.md` §2 | PASS |

Auditor: Codex CX-A3. Final: **VERIFIED_PASS** (`LIVE/.superpowers/collab/codex/stage3_audit.md` §5). This PASS does not cover real-camera accuracy, UAT, or UI commits made later.

### Stage 5: Release Decision (records `637a0ff`, `f15f539`, `f5fb90f`, `fe7852a`)

| Audit point | Expected | Actual | Evidence | Result |
|---|---|---|---|---|
| Rollback drill (Step 1) | Hash check and warm-up OK, exit 0 | 11/11, exit 0; rerun by both auditors with the same result, values identical to the original run | `docs/evidence/2026-10-30/stage5-rollback-drill/` | PASS |
| Decision record template (Step 2) | Active model, reasons, Stage-2/3 paths, date, signature line | Fields complete; paths open; numbers match their sources (re-audit B7/B8; for example binary errors 129 vs 150) | `docs/fyp2/task10a/release_decision.md` | PASS |
| No auto-activation of ResNet18 (Step 3) | Default stays stable | `active_vision = "stable"` unchanged; U-5 = A needs no configuration change | `backend/app/config.py` (checked by the auditor); `stage5_audit_table.md` | PASS |
| Report wording matches the decision | §5 wording for A | Wording supplied in `release_decision.md` §5; the DOCX edit belongs to the user and does not block | `stage3_stage5_reaudit.md` S5-h | PASS (record side only) |

Audit history:
- A fresh subagent (2026-10-30) returned PARTIAL on O-2 (the two options were presented asymmetrically), O-3 (wrong `.env` location) and O-4 (imprecise wording). All three were fixed in `f15f539`.
- The re-audit returned **VERIFIED_PASS**. Its Minor findings N-1 to N-5 are recorded as fixed in `fe7852a` (`stage5_audit_table.md`, last section). That is the implementer's record; no further audit has covered it.

Offline context cited by the decision record (read from `ML/ml/outputs/runs/p4b_20261022/evaluation_metrics.json`, sha256 `4f1c517a…`; clean test set):

| Model | Accuracy | Macro-F1 | Log loss |
|---|---|---|---|
| MN-STABLE | 0.8988 | 0.8746 | 0.5745 |
| RN-HPO42 | 0.9016 | 0.8892 | 0.4509 |
| MN-HPO42 | 0.8731 | 0.8677 | 0.7405 |

These are offline classification metrics. They are not evidence of safer driving or of better fused-risk accuracy. RiskLevel is an operational level, not accident severity.

## 4. Gate-run history (`scripts/run_gates.py`)

Sources:
- Result and commit come from each directory's `SUMMARY.md`.
- The pytest and vitest counts are not in `SUMMARY.md`; they come from the final summary line of `02-pytest.log` and `03-vitest.log` in the same directory.
- Every row runs 5 gates (build, pytest, vitest, tsc, eslint); "Skipped" is 0 for pytest in every row.
- Fresh-clone rows (ST-COLDSTART-01) keep their gate logs in `gates/`. Their top-level `SUMMARY.md` records a PASS for every step (clone, venv, pip, npm ci, model link, playwright, gates with `DRA_REQUIRE_MODELS=1`, serve).

| Gate directory | Commit / branch | Generated (UTC) | Result | pytest | vitest | Role |
|---|---|---|---|---|---|---|
| `2026-10-26/ds-review-fixes` | `7e64c4d` / `fyp2/ds-review-fixes` | 04:51:14 | GREEN | 1064 passed, 1 deselected | 968 | DS-0 review fixes (not Task 10A) |
| `2026-10-26/task10a-cl1-gate-RED-4ca3c69` | `4ca3c69` / `fyp2/live-system` | 04:53:16 | **RED** (pytest) | 23 failed, 1039 passed, 4 deselected | 958 | Task 1.3. Cause in the log: `KeyError: 'model_id'` at `app/providers/trained.py:197`; the `90b5e2e` commit message attributes it to the fault tests' stand-in provider. Fixed by `90b5e2e` |
| `2026-10-26/merge-ds0-gate` | `5edd868` / `fyp2/live-system` | 05:07:50 | GREEN | 1080 passed, 4 deselected | 972 | DS-0 merge (baseline). Its `README.md` marks it reference only, not clean evidence: a concurrent gate run shared the same worktree |
| `2026-10-26/integration-gate-ba018bb` | `ba018bb` / `fyp2/live-system` | 05:14:12 | GREEN | 1080 passed, 4 deselected | 972 | Clean rerun after the gate-directory incident (`44b93d7`) |
| `2026-10-26/task10a-cl1-gate` | `90b5e2e` / detached | 05:17:35 | GREEN | 1062 passed, 4 deselected | 958 | CL-1 (Tasks 1.1-1.3) clean rerun |
| `2026-10-26/ds-stable200-gate` | `3ab55ad` / `fyp2/ds-stable200` | 05:39:56 | GREEN | 1115 passed, 7 deselected | 972 | DS-1 branch (Task 1.4) |
| `2026-10-26/merge-ds1-gate` | `777cd05` / `fyp2/live-system` | 09:37:09 | GREEN | 1115 passed, 7 deselected | 972 | **Stage 1 Gate C evidence** |
| `2026-10-26/constructed-scenario-baseline-gate` | `911c1a4` / `fyp2/constructed-scenario` | 11:42:41 | GREEN | 1115 passed, 7 deselected | 972 | Constructed scenario (context) |
| `2026-10-26/constructed-scenario-m1-gate` | `cb4f65b` / `fyp2/constructed-scenario` | 12:32:08 | GREEN | 1298 passed, 7 deselected | 972 | Constructed scenario (context) |
| `2026-10-26/constructed-scenario-m2-gate` | `5c0461a` / `fyp2/constructed-scenario` | 15:27:44 | GREEN | 1308 passed, 8 deselected | 1022 | Constructed scenario (context) |
| `2026-10-29/constructed-scenario-merge-gate` | `cde7ab1` / `fyp2/live-system` | 04:04:08 | GREEN | 1308 passed, 8 deselected | 1022 | Stage 4 demo-path merge |
| `2026-10-29/ds-compare-gate` | `94c6d14` / `fyp2/ds-compare` | 04:20:03 | GREEN | 1148 passed, 7 deselected | 972 | DS-2 runner branch |
| `2026-10-29/merge-ds2-gate-RED-dd7b9d5-flaky` | `dd7b9d5` / `fyp2/live-system` | 04:35:17 | **RED** (pytest) | 1 failed, 1340 passed, 8 deselected | 1022 | DS-2 merge. The failing test, `test_constructed_scenario_e2e.py::test_a_long_pause_does_not_expire_the_evidence`, was flaky; fixed by `fbc9593` |
| `2026-10-29/merge-ds2-gate` | `fbc9593` / `fyp2/live-system` | 04:41:29 | GREEN | 1341 passed, 8 deselected | 1022 | Stage 2 integration |
| `2026-10-29/runner-fix-gate` | `bf76ddf` / `fyp2/live-system` | 05:07:34 | GREEN | 1347 passed, 8 deselected | 1022 | Stage 2 A2 fixes (F-1 to F-4) |
| `2026-10-29/ds-polish-gate` | `a4f4998` / `fyp2/ds-polish` | 05:09:13 | GREEN | 1343 passed, 8 deselected | 1030 | DeepSeek branch (context) |
| `2026-10-29/stage3-gate` | `fe5c41d` / `fyp2/live-system` | 09:34:49 | GREEN | 1355 passed, 8 deselected | 1022 | **Stage 3 same-day regression (10-29)** |
| `2026-10-29/ui-scenario-sessions-gate-RED-afd8724` | `afd8724` / `fyp2/live-system` | 09:57:35 | **RED** (vitest) | 1356 passed, 8 deselected | 1 failed, 1025 passed (1026) | UI fix. A source guard still pinned the earlier design; the guard was updated (cause written in `SUMMARY.md`) |
| `2026-10-29/ui-scenario-sessions-gate` | `808a5d5` / `fyp2/live-system` | 10:05:49 | GREEN | 1356 passed, 8 deselected | 1028 | UI fix |
| `2026-10-29/merge-ds3-gate` | `75e1094` / `fyp2/live-system` | 10:13:38 | GREEN | 1358 passed, 8 deselected | 1036 | DS-3 merge |
| `2026-10-29/mode-switch-coldstart-e26e32a/gates` | `e26e32a` / detached (fresh clone) | 13:53:11 | GREEN; coldstart PASS | 1359 passed, 8 deselected | 1043 | UI mode switch |
| `2026-10-29/mode-paths-coldstart-ead8895/gates` | `ead8895` / detached (fresh clone) | 14:05:34 | GREEN; coldstart PASS | 1359 passed, 8 deselected | 1049 | UI mode paths |
| `2026-10-30/ds3-followups-coldstart-37e7229/gates` | `37e7229` / detached (fresh clone) | 04:25:17 | GREEN; coldstart PASS | 1359 passed, 8 deselected | 1055 | DS-3 follow-ups |
| `2026-10-30/review-followups-coldstart-9255c83/gates` | `9255c83` / detached (fresh clone) | 04:41:33 | GREEN; coldstart PASS | 1359 passed, 8 deselected | 1061 | Stage 3 R-1 baseline gate |
| `2026-10-30/stage5-coldstart-f15f539/gates` | `f15f539` / detached (fresh clone) | 06:33:47 | GREEN; coldstart PASS | 1360 passed, 8 deselected | 1061 | **Final fresh-clone gate (Stage 3/5 re-audit)** |

Totals: 25 gate runs, 22 GREEN and 3 RED. Each RED directory is kept under its `-RED-` name and was followed by a GREEN rerun after a separate fix commit.

Not listed above, because they are not `run_gates.py` directories: `2026-10-26/task10a-stage1/`, `2026-10-26/stable200/`, `2026-10-29/comparison*/`, `2026-10-29/perf-stage3/`, `2026-10-30/stage3-raw/`, `2026-10-30/stage5-rollback-drill/`. They are cited in §2 and §3.

Auditor-side gate runs (outside the repo, recorded in the reports):
- CX-A1, `00b0e5d`, 2026-10-27T04:20:44Z: GREEN, 5/5. An earlier sandboxed attempt was RED (pytest 1 failed, 1071 passed, 43 errors), caused by a localhost bind `PermissionError`; the report discloses it (`stage1_audit.md` §1.2).
- CX-A3 C07, `e04f662`: 5 gates exit 0, pytest 1355 passed, 8 deselected, 0 skipped.
- Fresh subagent, `f5fb90f`: non-e2e pytest 1310 passed (`DRA_REQUIRE_MODELS=1`).

## 5. Remaining limitations and open items (not failures)

- **Planned, not done:** the written signature on `release_decision.md`. The DOCX edits to 6.2.3 and Table 23 belong to the user; the re-audit verified the record side only (`stage3_stage5_reaudit.md` S5-h).
- **Stage 2 report archiving:** the A2 round-1 and re-audit reports were not archived as standalone files. Only the summaries in `stage2_audit_table.md` §5 and `LIVE/.superpowers/collab/BOARD.md` exist.
- **Stage 2 scope:** the run uses the fixed Safe telemetry row, so RiskLevel High and HIGH_ALERT are not exercised (FUD-B, accepted as is). The RiskLevel distribution is Low/Medium only. The comparison is descriptive and there is no risk ground truth.
- **Stage 3 residuals:**
  - The 10-30 perf01 server logs cannot be recovered (O-5 residual).
  - The 10-29 runs are summary-only and historical.
  - Measurements come from one development machine (Apple M2) with a Chromium fake camera, not target hardware or a real camera (`stage3-raw/README.md`).
- **Gate order:** Stage 5 started before Stage 3 reached VERIFIED_PASS. The user confirmed this was authorised (FUD-5; `stage3_stage5_reaudit.md` O-9 = ACCEPTED-BY-USER).
- **Not covered by any gate:** frontal or real-camera accuracy, UAT, target-hardware performance, and fused-risk accuracy (`release_decision.md` §1; CX-A1 §1.3 row E).
- **Disclosed incident:** on 2026-10-26 another session deleted and overwrote a gate directory. `ba018bb` removed the mislabelled directory and `44b93d7` added the clean reruns (`integration-gate-ba018bb/`, `task10a-cl1-gate/`); CX-A1 §3.2 says the disclosure must be kept.

## 6. Attached audit reports (plan §15 Gate rule)

| # | Report | Auditor | Date | Target | Verdict(s) | Path |
|---|---|---|---|---|---|---|
| 0 | Phase 0 preflight (dependency check, not a phase gate) | Codex CX-0 | 2026-10-26 | dependencies | GO (dependencies only) | `docs/fyp2/task10a/preflight_report.md` |
| 1 | Stage 1 phase-gate audit | Codex CX-A1 | 2026-10-27 | `00b0e5d` | Stage 1 VERIFIED_PASS | `LIVE/.superpowers/collab/codex/stage1_audit.md` (git-ignored; prompt `LIVE/.superpowers/collab/codex/STAGE1_AUDIT_PROMPT.md`) |
| 2 | Stage 2 audit, round 1 | A2, fresh Claude subagent | 2026-10-29 | official run on `c0c6d43` (recorded in `a4f4998`, per BOARD 12:47 entry and `stage2_audit_table.md` §4) / runner `6df94ef` | PARTIAL (F-1) | No standalone file; summary in `docs/fyp2/task10a/stage2_audit_table.md` §5 and `LIVE/.superpowers/collab/BOARD.md` (13:11 entry) |
| 3 | Stage 2 re-audit | A2, fresh Claude subagent | 2026-10-29 | `bf76ddf` run (`314dac8`) | Stage 2 VERIFIED_PASS | No standalone file; summary in `stage2_audit_table.md` §5, BOARD (16:55 entry), commit `695dad9` |
| 4 | Stage 3 and Stage 4 phase-gate audit | Codex CX-A3 | 2026-10-29 | `e04f662` | Stage 3 PARTIAL (R-1); Stage 4 VERIFIED_PASS | `LIVE/.superpowers/collab/codex/stage3_audit.md` (git-ignored; prompt `LIVE/.superpowers/collab/codex/STAGE3_AUDIT_PROMPT.md`) |
| 5 | Stage 3 (R-1 closure) and Stage 5 audit | Fresh read-only subagent | 2026-10-30 | `637a0ff` | Stage 3 PARTIAL; Stage 5 PARTIAL | `docs/fyp2/task10a/stage3_r1_stage5_audit.md` (a file with the same name also exists at `LIVE/.superpowers/collab/stage3_r1_stage5_audit.md`) |
| 6 | Stage 3 and Stage 5 re-audit | Fresh read-only subagent | 2026-10-30 | `f5fb90f` | Stage 3 VERIFIED_PASS; Stage 5 VERIFIED_PASS | `docs/fyp2/task10a/stage3_stage5_reaudit.md` |

Implementer self-audit tables (inputs to the audits, not audits themselves): `docs/fyp2/task10a/stage1_audit_table.md`, `stage2_audit_table.md`, `stage3_audit_table.md`, `stage4_demo_path_note.md`, `stage5_audit_table.md`.
