# Task 10A Deliverables D and E: Final Verdict and Stable Runtime Status

- Type: engineering record (not report prose). Plan reference: `docs/plans/2026-10-25-task-10a-candidate-integration.md` §9 (Gates and Verdicts) and §10 D/E.
- State described: branch `fyp2/live-system`, HEAD `fe7852a` (2026-10-30 15:03 +0800), worktree `/Users/liu/Desktop/FYP2-Live-System-Integration`. Tracked files clean at `fe7852a`; `git status --short` (2026-10-31) shows only the untracked `docs/fyp2/task10a/deliverables/` directory that holds these records.
- Written 2026-10-31 from the files cited inline. No server, test, drill or git write was run to produce this record; every number below is copied from the cited file.

---

## D. Final Task 10A Verdict

### D.1 Verdict

**Task 10A: `VERIFIED_PASS`**, within the scope defined by the plan (candidate provider integration, stable200 provider verification, paired system comparison on a constructed input, runtime evaluation on one development machine, demo-path report guard, rollback drill and a user-made release decision). The written signature on the release decision is still pending (see D.4). The limitations in D.4 are part of the verdict; they are scope boundaries, not open defects.

The verdict rests on five stage verdicts, each from an independent auditor, not the implementer:

| Stage | Verdict | Auditor and date | Audit record |
|---|---|---|---|
| 1 Candidate Provider Integration | `VERIFIED_PASS` | Codex CX-A1, scope `fyp2/live-system@00b0e5d`, audit dated 2026-10-27 (evidence from the 2026-10-26 implementation day) | `/Users/liu/Desktop/FYP2-Live-System/.superpowers/collab/codex/stage1_audit.md` line 290 (git-ignored); user acceptance U-1 recorded 2026-10-29 in `docs/fyp2/task10a/stage2_audit_table.md` §5 (FUD-A) |
| 2 Paired System Comparison | `VERIFIED_PASS` (A2 re-audit after a first-round `PARTIAL`; F-1..F-4 fixed in `bf76ddf`) | fresh read-only subagent, 2026-10-29 | `docs/fyp2/task10a/stage2_audit_table.md` §5 |
| 3 Runtime Evaluation | `VERIFIED_PASS` (re-audit; earlier CX-A3 `PARTIAL` on R-1, then a further `PARTIAL` on O-1/O-5) | fresh read-only subagent, 2026-10-30 | `docs/fyp2/task10a/stage3_stage5_reaudit.md` §5; history in `stage3_audit_table.md` §5–§8 and `stage3_r1_stage5_audit.md` |
| 4 Target Camera (demo-path report guard) | `VERIFIED_PASS` | Codex CX-A3, 2026-10-29 | `/Users/liu/Desktop/FYP2-Live-System/.superpowers/collab/codex/stage3_audit.md` line 94 (git-ignored); note `docs/fyp2/task10a/stage4_demo_path_note.md` |
| 5 Release Decision (Steps 1–3 + recorded decision) | `VERIFIED_PASS` (re-audit after a first-round `PARTIAL` on O-2/O-3/O-4) | fresh read-only subagent, 2026-10-30 | `docs/fyp2/task10a/stage3_stage5_reaudit.md` §5; `stage5_audit_table.md` |

Preflight (Phase 0) was `GO` for dependencies only (`docs/fyp2/task10a/README.md`, `preflight_report.md`).

### D.2 Supporting gates (plan §9)

| Gate | Definition (plan §9) | Status | Evidence |
|---|---|---|---|
| A Model Artifact & Provider | manifests validate, artifacts load, real forward, class mapping, valid outputs | Satisfied | Both copied packages `valid` with the system CLI, exit 0 (`docs/evidence/2026-10-26/task10a-stage1/manifest-cli-*.log`); loader and provider warm-up assert (1, 10) finite outputs; 6 real-package tests passed (`.../task10a-stage1/pytest-m-candidates.log`); summary in `docs/fyp2/task10a/stage1_audit_table.md` §1 |
| B Stable200 | official provider test executed with pre-declared checks | Satisfied, all three identities PASS | `docs/evidence/2026-10-26/stable200/official_stable200_behavior.json` (overall PASS). Candidates vs saved PyTorch predictions: max abs prob delta 1.48e-6 (ResNet18) / 6.87e-6 (MobileNetV3 search_006), argmax 200/200; stable vs P4A parity cache: 1.54e-7 to 1.78e-7 over 100 sources, argmax 100/100. Tolerance `max_abs_prob_delta <= 1e-4`, argmax agreement 1.0, approved beforehand (FUD-01, `docs/fyp2/task10a/approval_record.json`). Figures from `stage1_audit_table.md` §1 |
| C Integration Regression | candidate support breaks nothing | Satisfied | Stage 1: pytest 1115 / 0 skipped / 7 deselected, vitest 972, build/tsc/eslint pass at `777cd05` (`docs/evidence/2026-10-26/merge-ds1-gate/`, cited in `stage1_audit_table.md` §3). Latest fresh-clone gate: `f15f539`, ST-COLDSTART-01 PASS, gates step exit 0 with `DRA_REQUIRE_MODELS=1` (`docs/evidence/2026-10-30/stage5-coldstart-f15f539/SUMMARY.md`); pytest 1360 / 0 skipped / 8 deselected, vitest 1061 (`stage5_audit_table.md`). Auditor's own non-e2e rerun at `f5fb90f`: 1310 passed, exit 0 (`stage3_stage5_reaudit.md` S3-e). Commits after `f15f539` (`a46f80d`, `f5fb90f`, `fe7852a`) are docs-only (`git diff --name-only f15f539 fe7852a`: every path under `docs/`) |
| D Runtime Failure Handling | bad model/manifest/hash/input, no silent fallback, candidate->stable recovery | Satisfied | Tamper green 7 passed / red (sha check removed) 2 failed (`docs/evidence/2026-10-26/task10a-stage1/tamper-*.log`); hash, schema, class-order, missing `safe_driving` label and warm-up failure raise `ModelUnavailable` -> 503 with no fallback (`stage1_audit_table.md` §2 item 4). Rollback drill 11/11 PASS (`docs/evidence/2026-10-30/stage5-rollback-drill/drill.log`), rerun by the auditor from a clone of `f5fb90f`: exit 0, 11/11, bit-identical RiskScore/P_distraction (`stage3_stage5_reaudit.md` S5-a) |
| E Evaluation Evidence | reproducible evidence with IDs, preconditions, results, environment, model identities/hashes | Satisfied | Stage 2: `docs/evidence/2026-10-29/comparison-official-bf76ddf/comparison_results.json` under protocol sha256 `b63050221c467ac7ed1ced0ae5e4af95ca734a7ba15fe4d7af94c948074c988f`, membership hash `601dc3ed...` recomputed (`stage2_audit_table.md` §1). Stage 3: `docs/evidence/2026-10-30/stage3-raw/` (six `perf01.json` + `perf01_timings.json`, sha256-bound, independently recomputed 6/6 per `stage3_stage5_reaudit.md` S3-c). Every run records the vision model id and sha256 |

### D.3 Headline results the verdict relies on (descriptive, not a ranking)

- Stage 2 (stable200, constructed order, fixed Safe telemetry row): ResNet18 vs stable argmax agreement 0.91, RiskLevel differs in 5/200 windows, AlertSeverity in 12/200; MobileNetV3 search_006 vs stable 0.90, 6/200, 13/200 (`docs/fyp2/task10a/stage2_audit_table.md` §2). Argmax agreement is agreement between models, not accuracy, and says nothing about which model is safer.
- Stage 3 (2026-10-30, 3 alternating rounds x 600 windows each, after 20 warm-up windows): capture->render p95 stable 31 / 31 / 31 ms, ResNet18 45 / 44 / 43 ms; server vision median stable 9.58 / 9.69 / 9.79 ms, ResNet18 26.61 / 26.56 / 26.58 ms (`docs/evidence/2026-10-30/stage3-raw/README.md`). The ResNet18 p95 is measured, not extrapolated.
- Stage 3 log completeness with fault injection: D1/D2 210/210 for both models, 1 `input_validation` fault, 0 duplicates (`docs/evidence/2026-10-29/perf-stage3/{stable,rn}/perf02.json`, via `stage3_audit_table.md` §2).
- Offline clean-test numbers used in the decision (`/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/ml/outputs/runs/p4b_20261022/evaluation_metrics.json`, opened read-only): MN-STABLE accuracy 0.8988 / Macro-F1 0.8746 / log loss 0.5745, binary diagnostic accuracy 0.9647, c0 false-positive proxy 0.0905; RN-HPO42 0.9016 / 0.8892 / 0.4509, 0.9590, 0.2019. The diagnostic is labelled `ADDITIONAL_OFFLINE_DIAGNOSTIC_NOT_LIVE_RISK` in that file. A higher Macro-F1 is not evidence of safer driving, and neither model's numbers measure fused-risk correctness.

### D.4 Remaining limitations (carried with the verdict)

1. **Frontal-camera accuracy is unmeasured for both candidates.** Only the stable model's domain shift on the laptop's frontal camera was measured: `safe_driving` was the top class 5 times in about 5,170 frames (`docs/evidence/2026-10-22/vision-runtime-path/README.md`). Neither ResNet18 search_004/seed42 nor MobileNetV3 search_006/seed42 was measured on a real camera (`release_decision.md` §1, row "两者都没有证明的": only the stable model's domain shift was measured; §2, last row, ResNet18 column: "未测"). The side camera (4-B) is informal only and is not evaluation evidence (`stage4_demo_path_note.md` §2).
2. **Single development machine.** The 2026-10-30 Stage 3 runs used for the decision: one development machine (Apple M2), Chromium fake camera, prepared telemetry, frozen models (`docs/evidence/2026-10-30/stage3-raw/README.md`, "Scope"). The 2026-10-29 runs were taken under load average 10 to 56 on 8 cores and are kept as historical, summary-only records (`stage3_audit_table.md` §3 item 1, §5).
3. **No target hardware.** No in-vehicle or target-hardware measurement exists (`stage3-raw/README.md`: "not target hardware or a real camera"; `release_decision.md` §1, row "两者都没有证明的"). No vehicle-grade or deployment claim is made.
4. **R-3 `.env` bypass (known limitation, not fixed).** Settings read `.env` from the process's current directory (`env_file=".env"`), so a `.env` in the start directory could set `DRA_*` variables, including `DRA_ACTIVE_VISION`, and would also bypass the Stage-2 runner's `worker_env` cleaning (`stage2_audit_table.md` §5; `release_decision.md` §4; auditor probe B9 in `stage3_stage5_reaudit.md` S5-e). Observed 2026-10-31: no `.env` at the integration worktree root or in `backend/` (`ls` returned "No such file or directory" for both).
5. **Written signature pending.** U-5 was decided in conversation on 2026-10-30; the signature line in `docs/fyp2/task10a/release_decision.md` §3 is still blank (`用户签字：____________________`). The re-audit lists it as a user item (`stage3_stage5_reaudit.md` §4, FUD-R2-4) and treats it as non-blocking (§5).
6. **Deleted 2026-10-29 void runs.** In the first 2026-10-29 Stage 3 session, rounds 2/3 ran twice concurrently because a background task was started twice; those results were deleted and used for no conclusion; r2/r3 were rerun separately (`stage3_audit_table.md` §3 item 2). Accepted as described by the implementer, with no objection from the user (FUD-3, `stage3_audit_table.md` §7). The Stage 5 decision cites only the 2026-10-30 runs.
7. Other scope limits recorded by the audits:
   - Stage 2 cannot reach High or HIGH_ALERT by design (one fixed Safe telemetry row, weights 0.5/0.5, RiskScore at most about 50); it is a constructed evaluation scenario and says nothing about the general benefit of multimodal fusion (`stage2_audit_table.md` §3; accepted by the user as FUD-B).
   - The server (uvicorn) logs of the six 2026-10-30 perf01 runs are not recoverable; health rests on exit 0, 0 console errors and `attempts_other_than_1` 0 (`stage3-raw/README.md`, "Not recoverable"; O-5 residual in `stage3_stage5_reaudit.md`).
   - There is no synchronized multimodal ground truth, so fused-risk accuracy is unmeasured for every model (`release_decision.md` §1). RiskLevel is an operational level derived from RiskScore thresholds 30/60, not an accident-severity label.
   - UAT is not done and is not claimed (plan §13, "Pending — do not claim UAT").
   - The telemetry research preference `xgboost_02` was not imported or loaded; telemetry stays the stable XGBoost (`release_decision.md` header; plan §0).

### D.5 Planned / not done in Task 10A

- Not done: real-camera evaluation of the candidates; target-hardware latency; UAT; any change of the active model; any push.
- User items outside the engineering record: written signature (`release_decision.md` §3); DOCX edits to 6.2.3 and Table 23 per `release_decision.md` §5 (not verified here).

---

## E. Stable Runtime Status

| Item | Status | Evidence |
|---|---|---|
| Stable system operational | Yes. Stable MobileNetV3-Large (sha256 `b3a42e8dd4553355b1fd7d9e7fe3d28e318decb894e76eb029489b7ff2e90bcf`) + stable XGBoost (`9802cb06ca98f0c1befaf851fa7668cfec70e005cf8bb3884e49d7d45d7aec07`) loaded, `/api/health` 200, `/infer` 201 with provenance naming the stable model (rollback step of the drill, 2026-10-30 05:45:48Z) | `docs/evidence/2026-10-30/stage5-rollback-drill/drill.log` |
| Default is stable | Yes. `active_vision: str = "stable"` at `backend/app/config.py:34`; the provider takes the stable path when `settings.active_vision == "stable"` (`backend/app/providers/trained.py:74`). Default start reports `stable_mobilenet_v3_large`, `source = stable` | `docs/evidence/2026-10-26/task10a-stage1/startup-default.json` (via `stage1_audit_table.md` §1) |
| Candidates available by explicit switch | Yes. `DRA_ACTIVE_VISION=resnet18_search004_seed42` loads the ResNet18 package from `ml/outputs/candidates/p5_resnet18_search004_seed42_20261023/`, checked against its runtime manifest (sha256 `5e226722e0712824c78aa0976afa6fa5b8dc6100b147a7f523a09048171d8cf3`). `mobilenet_v3_large_search006_seed42` is the retained comparator (Stage 1/2 only). In the integration worktree `ml/outputs/candidates` and `.venv` are git-ignored symbolic links to `/Users/liu/Desktop/FYP2-Live-System/` (observed with `ls -la`, 2026-10-31) | `release_decision.md` §4; `drill.log` (candidate-active step) |
| Rollback drilled | Yes. Candidate active -> fresh process with `DRA_ACTIVE_VISION` unset -> stable with the frozen sha256; 94 files under `ml/outputs` unchanged; port 8001 free at the end; 11/11 PASS, exit 0; rerun by the auditor at `f5fb90f`, 11/11, exit 0 | `docs/evidence/2026-10-30/stage5-rollback-drill/{README.md,drill.log}`; `stage3_stage5_reaudit.md` S5-a |
| Active-model change made | **None.** U-5 (2026-10-30): option A, stable MobileNetV3-Large stays active; ResNet18 search_004/seed42 remains an admitted, switchable candidate. No configuration was changed (the default was already stable); ResNet18 was not auto-activated (plan §8 Step 3) | `release_decision.md` status line and §3; `stage5_audit_table.md` row "不自动启用 ResNet18" |
| Stable artifacts overwritten | No. Stable ONNX path `ml/outputs/vision/mobilenetv3_large_vision.onnx` unchanged; candidates live in their own package directories; no model file committed | `release_decision.md` §4; `drill.log` ("no file under the model root changed"); no model artifact in `git ls-tree -r f5fb90f` (`stage3_stage5_reaudit.md` §2) |
| Telemetry provider | Unchanged stable XGBoost; `git diff 2745348 -- backend/app/providers/trained.py` touches vision lines only (`telemetry_or_xgb_lines: []`) | `docs/evidence/2026-10-26/task10a-stage1/SUMMARY.json`, `trained_py_diff_vs_2745348.diff` |

How to confirm at demo time (from `release_decision.md` §4; not run for this record): start from the repository root without `DRA_ACTIVE_VISION`, then `curl -s http://127.0.0.1:8000/api/models` and check `vision.model_id` = `stable_mobilenet_v3_large`, `vision.sha256` starting `b3a42e8d`. Check first that no `.env` exists in the start directory (limitation D.4 item 4).
