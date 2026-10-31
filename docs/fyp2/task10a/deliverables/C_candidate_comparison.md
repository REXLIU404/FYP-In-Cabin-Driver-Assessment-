# Task 10A Deliverable C: Candidate Comparison

- Record type: engineering record (plan §10 deliverable C). Not report prose.
- Prepared: 2026-10-31, from files on `fyp2/live-system` @ `fe7852a` (worktree `/Users/liu/Desktop/FYP2-Live-System-Integration`) and read-only ML-track files. No server, test or benchmark was run to produce this record; every number below was read from the file cited next to it.
- Plan: `docs/plans/2026-10-25-task-10a-candidate-integration.md` §10 C ("separate offline research evidence / provider compatibility / model-only latency / system-level runtime evidence; never equate Macro-F1 with safer driving").

## 0. Identities compared, and what is already decided

| Short name | Runtime model id | ONNX sha256 (prefix) | ML-track identity in p4b | Role |
|---|---|---|---|---|
| stable MN | `stable_mobilenet_v3_large` | `b3a42e8d…` | `MN-STABLE` | Active vision model (default, rollback reference) |
| RN | `resnet18_search004_seed42` | `5e226722…` | `RN-HPO42` | Vision candidate, role `VALIDATION_PREFERRED` |
| MN candidate | `mobilenet_v3_large_search006_seed42` | `9ee60abb…` | `MN-HPO42` | Retained comparator only |

Sources: model ids and sha256 from `docs/evidence/2026-10-26/stable200/official_stable200_behavior.json` (`models.*.model.onnx_sha256_actual`); roles from plan §0 "Frozen model identities".

Decided facts (not reopened here):
- Stage verdicts: Stage 1 VERIFIED_PASS (Codex, `/Users/liu/Desktop/FYP2-Live-System/.superpowers/collab/codex/stage1_audit.md` line 290, git-ignored); Stage 2 VERIFIED_PASS (A2 fresh re-audit, `docs/fyp2/task10a/stage2_audit_table.md` §5); Stage 3 and Stage 5 VERIFIED_PASS (fresh re-audit 2026-10-30, `docs/fyp2/task10a/stage3_stage5_reaudit.md` §5); Stage 4 VERIFIED_PASS (Codex CX-A3, `/Users/liu/Desktop/FYP2-Live-System/.superpowers/collab/codex/stage3_audit.md` §5, line 94, git-ignored).
- User decision U-5 (2026-10-30): option A. The active vision model stays stable MobileNetV3-Large. RN remains an admitted, switchable candidate via `DRA_ACTIVE_VISION`. No configuration was changed. The written signature is still pending (`docs/fyp2/task10a/release_decision.md` §3, signature line blank).
- Telemetry is not part of this comparison: every run uses the stable XGBoost (`telemetry_model_sha256` `9802cb06…` per `docs/fyp2/task10a/stage3_stage5_reaudit.md` S5-a). `xgboost_02` is research evidence only and is not loaded (plan §0 "Frozen model identities").

Interpretation guards that apply to every part below:
- Higher Macro-F1 (or accuracy, or lower log loss) on the offline test set is a classification result. It does **not** mean safer driving, and it does not measure the risk output of the system.
- The clean test set has **4 held-out drivers** (`p012`, `p026`, `p035`, `p050`), 3,657 frames, of which 431 are `c0`. The ML-track file itself lists "Only four State Farm test drivers; descriptive comparisons, no frame bootstrap or p-values." (`limitations[0]` in the ML metrics file, path in §1).
- `RiskLevel` is a derived operational level, not accident severity. Stage-2 RiskLevel differences are differences between models, not errors against a ground truth.
- The four parts are kept separate on purpose: they measure different things on different inputs and cannot be combined into one score.

---

## Part 1. Offline research evidence (ML track, read-only)

Source for all of Part 1 unless stated otherwise:
`/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/ml/outputs/runs/p4b_20261022/evaluation_metrics.json` (outside this repo; ML worktree, read-only; sha256 `4f1c517a…` per `docs/fyp2/task10a/stage3_stage5_reaudit.md` B7). Keys: `models.<id>.clean`, `models.<id>.driver_metrics`, `models.<id>.stress`.

### 1.1 Clean test metrics (n = 3,657, 4 drivers)

| Metric | stable MN (`MN-STABLE`) | RN (`RN-HPO42`) | MN candidate (`MN-HPO42`) |
|---|---|---|---|
| Accuracy | 0.8988 | 0.9016 | 0.8731 |
| Macro-F1 | 0.8746 | 0.8892 | 0.8677 |
| Log loss | 0.5745 | 0.4509 | 0.7405 |

Exact values: accuracy 0.8988241728192508 / 0.9015586546349467 / 0.873120043751709; macro_f1 0.8746408408872671 / 0.8892363766947888 / 0.8676544859032846; log_loss 0.5744531434764406 / 0.4508676411041781 / 0.7405023914063921.

RN minus stable MN: Macro-F1 +0.0146, accuracy +0.0027, log loss −0.1236 (computed from the values above). This is a small difference measured on 4 drivers; the file reports no confidence intervals or significance tests.

### 1.2 Per-class: c0 (normal/safe driving) and c9 (talking to passenger, the known weak class)

| Class | Metric | stable MN | RN | MN candidate |
|---|---|---|---|---|
| c0 (support 431) | recall | 0.9211 | 0.8329 | 0.8237 |
| c0 | precision | 0.8102 | 0.8407 | 0.7172 |
| c0 | F1 | 0.8621 | 0.8368 | 0.7667 |
| c9 (support 311) | recall | 0.2733 | 0.4920 | 0.5434 |
| c9 | precision | 0.7265 | 0.7887 | 0.6926 |
| c9 | F1 | 0.3972 | 0.6059 | 0.6090 |

Per-driver view (from `models.<id>.driver_metrics.drivers`), stable MN vs RN only:

| Driver (frames) | c0 recall stable / RN | c9 F1 stable / RN (c9 support) |
|---|---|---|
| p012 (823) | 1.0000 / 1.0000 | 0.0312 / 0.1389 (62) |
| p026 (1,196) | 0.7615 / 0.4923 | 0.7164 / 0.8194 (98) |
| p035 (848) | 0.9681 / 0.9362 | 0.2581 / 0.8088 (81) |
| p050 (790) | 1.0000 / 1.0000 | 0.0000 / 0.0000 (70) |

Reading: the c0 recall gap between the two models comes mostly from one driver (p026); c9 F1 is 0 for both models on p050. With 4 drivers, per-class differences move a lot with a single driver. RN's c9 weakness has not disappeared (RN pooled c9 F1 0.6059, p050 c9 F1 0).

### 1.3 Binary distraction diagnostic (both sides)

The system uses only `P_distraction = 1 − P(c0)`, so this view is the closest offline proxy for what reaches the RiskScore. The file labels it `interpretation: ADDITIONAL_OFFLINE_DIAGNOSTIC_NOT_LIVE_RISK`, threshold 0.5 (`models.<id>.clean.distraction_diagnostic`). It is an offline diagnostic, not a live-risk measure.

| | stable MN | RN | MN candidate |
|---|---|---|---|
| Binary accuracy | 0.9647 | 0.9590 | 0.9418 |
| c0 frames flagged as distracted (false alarm, `c0_false_positive_proxy`) | 9.05% (39/431) | 20.19% (87/431) | 18.33% (79/431, derived) |
| Distracted frames missed as safe | 2.79% (90/3,226, derived) | 1.95% (63/3,226, counted) | 134/3,226 (derived) |
| Total binary errors | 129 | 150 | 213 (derived) |

How each count was obtained:
- RN 87 and 63: counted row by row from `/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/ml/outputs/runs/p5_candidates_20261023/p5_resnet18_search004_seed42_20261023/predictions_test_clean.csv` (3,657 rows, `P_d = 1 − probability_c0`, false alarm `true=0 and P_d ≥ 0.5`, miss `true≠0 and P_d < 0.5`); re-counted for this record with the same result, and matching `docs/fyp2/task10a/stage3_stage5_reaudit.md` B8.
- stable MN 39 and 129: from the diagnostic rates, 0.090487 × 431 = 39.0 and 3,657 × (1 − 0.964725) = 129.0; misses 90 = 129 − 39 (derived; the p4b run has no per-row stable prediction file). Same derivation is recorded in `docs/fyp2/task10a/release_decision.md` §2 and was checked in `docs/fyp2/task10a/stage3_stage5_reaudit.md` B7.
- MN candidate 79 / 213 / 134: derived the same way from its diagnostic (0.183295 × 431; 3,657 × (1 − 0.941756)). Not counted row by row.

Reading, both sides stated: RN misses 27 fewer distracted frames (90 → 63) but raises about twice as many false alarms on normal driving (39 → 87); total errors are 129 (stable) vs 150 (RN). Which side matters more is a judgment, not a measurement (`docs/fyp2/task10a/release_decision.md` §1, item 1).

### 1.4 E1 perturbation stability (mixed)

Flip rate = share of frames whose argmax changes under a synthetic corruption (`models.<id>.stress.<condition>.flip_rate`). The file marks these as `label_validity: LABEL_VALIDITY_UNVERIFIED`, `human_validated: false`, `f1_eligible: false`: they describe prediction stability, not robustness on human-validated labels.

| Condition (severity 0/1/2) | stable MN | RN | MN candidate | Lower of stable vs RN |
|---|---|---|---|---|
| brightness_down 0 / 1 / 2 | 0.90 / 2.05 / 3.80 % | 1.15 / 3.83 / 10.45 % | 1.45 / 3.88 / 5.74 % | stable / stable / stable |
| brightness_up 0 / 1 / 2 | 1.89 / 3.53 / 4.84 % | 1.04 / 2.65 / 5.58 % | 2.16 / 3.77 / 6.21 % | RN / RN / stable |
| grayscale_blend 0 / 1 / 2 | 1.18 / 4.16 / 28.03 % | 1.18 / 3.64 / 16.24 % | 3.01 / 10.09 / 28.85 % | tie / RN / RN |
| motion_blur 0 / 1 / 2 | 5.11 / 24.20 / 56.99 % | 6.02 / 26.61 / 48.32 % | 4.76 / 16.46 / 41.02 % | stable / stable / RN |
| occlusion 0 / 1 / 2 | 5.85 / 12.06 / 26.74 % | 7.25 / 15.34 / 33.36 % | 6.81 / 14.74 / 31.36 % | stable / stable / stable |
| rotation_crop 0 / 1 / 2 | 6.26 / 9.35 / 17.34 % | 3.25 / 6.75 / 11.32 % | 8.89 / 11.65 / 17.88 % | RN / RN / RN |

Across the 18 conditions, RN has the lower flip rate in 8, stable MN in 9, and 1 is tied (counted for this record; same count as `docs/fyp2/task10a/stage3_stage5_reaudit.md` S5-c). Result: **mixed, no model is uniformly more stable.**

### 1.5 What Part 1 does not show

- Not live performance: the file's own limitation list states "offline benchmark does not establish live performance".
- Not frontal/target-camera accuracy. Only stable MN's domain shift on the frontal camera was measured (`safe_driving` was the top class 5 times in about 5,170 frames, `docs/evidence/2026-10-22/vision-runtime-path/README.md`); RN was not tested there (`docs/fyp2/task10a/release_decision.md` §2, last row).
- The historical test split has been evaluated repeatedly (file `limitations`). The same list states "no directly test-driven parameter selection code was found" and that the ResNet and XGB validation priorities remain frozen; this record does not claim more than that.

---

## Part 2. Provider compatibility (Stage 1, 2026-10-26)

Question answered: does each package load through the real system provider and reproduce its reference outputs? It says nothing about which model is better.

Evidence: `docs/evidence/2026-10-26/stable200/official_stable200_behavior.json` (overall_status PASS, run exit_code 0, 2026-10-26 13:38–13:39), `docs/evidence/2026-10-26/stable200/README.md`, `docs/evidence/2026-10-26/task10a-stage1/`. Pre-declared tolerance (user-approved FUD-01): per reference set `max_abs_prob_delta ≤ 1e-4` and `argmax_agreement = 1.0` (`docs/fyp2/task10a/tolerance_predeclaration.md`; `tolerance.approved_tolerance` in the JSON).

| Check | stable MN | RN | MN candidate |
|---|---|---|---|
| Manifest CLI (`scripts/validate_runtime_manifest.py`) | n/a (stable is not manifest-loaded) | `valid`, exit 0 | `valid`, exit 0 |
| ONNX sha256 matches expected | yes | yes | yes |
| Fresh provider forward vs P4A ORT parity (100 sources): max abs prob delta / argmax | 1.778e-7 / 100/100 | 1.540e-7 / 100/100 | 1.688e-7 / 100/100 |
| Fresh provider forward vs saved PyTorch stable200 predictions (200 images): max abs prob delta / argmax | null, `NO_STABLE200_REFERENCE` | 1.479e-6 / 200/200 | 6.869e-6 / 200/200 |
| Per-class mode rule on stable200 (each class's unique argmax mode equals its label) | pass | pass | pass |
| Provider name | `MobileNetV3ONNX+XGBoost` | `VisionCandidateONNX+XGBoost` | `VisionCandidateONNX+XGBoost` |
| Status | PASS | PASS | PASS |

Manifest logs: `docs/evidence/2026-10-26/task10a-stage1/manifest-cli-p5_resnet18_search004_seed42_20261023.log`, `docs/evidence/2026-10-26/task10a-stage1/manifest-cli-p5_mobilenet_v3_large_search006_seed42_20261023.log`. Real-package tests: `docs/evidence/2026-10-26/task10a-stage1/pytest-m-candidates.log` (6 passed). Tamper rejection without fallback: `docs/evidence/2026-10-26/task10a-stage1/tamper-green.log` (7 passed) and the red counterpart `tamper-red-sha-check-removed.log`. stable200 membership sha256 `601dc3ed…` recomputed and matched (`membership.membership_sha256_match: true`). Preprocess identity for both candidates: `rgb_resize_224_bilinear_no_crop_div255_imagenet`.

stable200 is a provider-behaviour diagnostic, not an accuracy estimate (plan §0).

---

## Part 3. Model-only latency (ORT benchmark, ML track)

Source: `/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/ml/outputs/runs/p4b_20261022/evaluation_metrics.json` key `runtime` (rounds also in `.../p4b_20261022/runtime_benchmark/*_round*.json`). Scope recorded in every round: `CPU_ORT_SESSION_RUN_ONLY_NOT_CAPTURE_TO_RENDER`. 6 rounds × 100 calls per identity.

| Identity | p50 (ms) | p95 (ms) | round p95 range (ms) | Throughput (/s) | ONNX bytes |
|---|---|---|---|---|---|
| RN (`RN-HPO42`) | 25.12 | 25.42 | 25.30 – 26.13 | 39.71 | 44,717,068 |
| MN candidate (`MN-HPO42`) | 6.95 | 7.25 | 7.21 – 7.57 | 141.95 | 16,849,370 |
| stable MN (`MN-STABLE`) | not benchmarked in p4b | — | — | — | — |

Limitation, stated plainly: the p4b runtime benchmark has **no entry for the stable MN model**. MN-HPO42 is the same architecture (MobileNetV3-Large) and is the closest model-only reference, but it is not the stable model. The stable model's per-window vision time inside the server is available only from Part 4 (server `vision` stage). No new benchmark was run for this record (plan §1 red line 1).

---

## Part 4. System-level runtime evidence

### 4.1 Stage 2 paired system comparison (2026-10-29, constructed scenario, descriptive)

Evidence: `docs/evidence/2026-10-29/comparison-official-bf76ddf/comparison_results.json` (current official run at `bf76ddf`; exit_code 0; run 2026-10-29 05:06:48–05:07:11 UTC; `validity.status` PASS; `identical_results` false). Protocol: `docs/fyp2/task10a/comparison_protocol.json`, sha256 `b6305022…` (`protocol_gate.status` PASS, `protocol_after_run.unchanged` true). Input: stable200, membership sha256 recomputed `601dc3ed…`. Fixed, identical across models: `w_v = w_t = 0.5`, `ema_alpha` 0.35, thresholds 30 / 60, `freshness_tolerance_s` 3, R10 FSM, stable XGB telemetry `9802cb06…` (`docs/fyp2/task10a/comparison_protocol.json` `fixed_configuration`); one subprocess and one fresh temporary SQLite per model (`docs/fyp2/task10a/stage2_audit_table.md` §1).

Paired differences vs stable MN (`paired_summaries`):

| Pair | argmax agreement (200 frames) | RiskLevel differs | AlertSeverity differs | DominantEvidence differs | RiskScore difference median / p95 / min / max |
|---|---|---|---|---|---|
| RN − stable MN | 0.91 | 5 / 200 | 12 / 200 | 5 / 200 | 0.0 / 7.9 / −14.0 / 16.1 |
| MN candidate − stable MN | 0.90 | 6 / 200 | 13 / 200 | 6 / 200 | 0.0 / 4.1 / −12.1 / 22.2 |

Per-model distributions (`models.<id>.summaries`):

| | stable MN | RN | MN candidate |
|---|---|---|---|
| RiskLevel counts | Low 27 / Medium 173 | Low 24 / Medium 176 | Low 23 / Medium 177 |
| AlertSeverity counts | NORMAL 9 / CAUTION 191 | NORMAL 21 / CAUTION 179 | NORMAL 22 / CAUTION 178 |
| DominantEvidence counts | Low observed risk 27 / Vision-dominant 173 | 24 / 176 | 23 / 177 |
| RiskScore mean / median / max | 43.76 / 50.0 / 50.0 | 44.66 / 50.0 / 50.0 | 44.04 / 50.0 / 50.0 |
| c9 block argmax counts (20 images) | {0: 6, 7: 4, 9: 10} | {0: 3, 9: 17} | {0: 3, 7: 7, 9: 10} |
| c0 block argmax counts (20 images) | {0: 17, 4: 2, 8: 1} | {0: 16, 3: 1, 8: 2, 9: 1} | {0: 19, 9: 1} |

Limits of Stage 2 (from `comparison_results.json` `failures_and_limitations` and `docs/fyp2/task10a/stage2_audit_table.md` §3):
- Constructed evaluation scenario (D06): 10 class blocks of 20 images in fixed order; transitions at block boundaries reflect the order and EMA carry-over, not real dwell time.
- One fixed Safe telemetry row (FUD-04): `telemetry_non_safe` is 0.00022 for every window, so RiskScore tops out at 50.0; **High and HIGH_ALERT are unreachable by design** in this scenario. It cannot show general multimodal benefit.
- Argmax agreement is agreement between models, not accuracy. There is no risk ground truth, so the 5 RiskLevel differences do not show which model gives a better risk output. Descriptive only: no winner, no single score.

### 4.2 Stage 3 runtime: same-day perf01, 2026-10-30 (current evidence for Stage 5)

Evidence: `docs/evidence/2026-10-30/stage3-raw/` (`README.md`, six `*/perf01.json` + `*/perf01_timings.json`, `runs.log`, `recompute.log`). Code at `1cd5660`; runs alternated stable / RN; each run 600 measured windows after a 20-window warm-up; Chromium fake camera, prepared telemetry, frozen models, one development machine (Apple M2), load 2.3–4.1 on 8 cores (`docs/evidence/2026-10-30/stage3-raw/README.md`). Raw per-window timings are sha256-bound to each summary and were recomputed independently by the re-auditor (6/6 equal, `docs/fyp2/task10a/stage3_stage5_reaudit.md` S3-c).

| Run | Model (from `/api/models`) | Rate (Hz) | capture→render median / p95 / max (ms) | Server total median / p95 (ms) | Server vision median / p95 (ms) |
|---|---|---|---|---|---|
| stable-r1 | stable MN `b3a42e8d…` | 9.78 | 27 / 31 / 127 | 17.70 / 19.65 | 9.575 / 10.57 |
| RN-r1 | RN `5e226722…` | 9.78 | 42 / 45 / 125 | 33.04 / 34.89 | 26.61 / 27.66 |
| stable-r2 | stable MN | 9.79 | 28 / 31 / 63 | 18.105 / 19.83 | 9.69 / 10.66 |
| RN-r2 | RN | 9.79 | 41 / 44 / 63 | 33.145 / 34.21 | 26.56 / 27.18 |
| stable-r3 | stable MN | 9.77 | 28 / 31 / 58 | 18.205 / 19.83 | 9.79 / 10.63 |
| RN-r3 | RN | 9.79 | 41 / 43 / 75 | 33.12 / 34.17 | 26.58 / 27.27 |

Values read from `docs/evidence/2026-10-30/stage3-raw/<run>/perf01.json` keys `achieved_rate_hz`, `stages.capture_to_render_ms`, `stages.server_timing_ms.total`, `stages.server_timing_ms.vision`. RN's capture→render p95 is measured (45 / 44 / 43 ms), not extrapolated from the 25.42 ms model-only figure. Both models meet the development target p95 ≤ 1 s by a wide margin; every run exit 0 with 0 console errors (`docs/evidence/2026-10-30/stage3-raw/README.md`). Server-stage timings exist as summaries only (no raw per-stage file). The perf01 server logs of these six runs were not kept (`docs/evidence/2026-10-30/stage3-raw/README.md`, "Not recoverable").

Earlier reference, for context only: the 2026-10-22 stable baseline `docs/evidence/2026-10-22/perf/perf01.json` has capture→render median 28 / p95 39 / max 280 ms (600 windows).

### 4.3 Stage 3 historical perf01 and current perf02, 2026-10-29

perf01, 2026-10-29 (historical, summary-only; superseded for the Stage-5 decision by §4.2 under user decision FUD-1, `docs/fyp2/task10a/stage3_audit_table.md` §7). Machine load was high (load average 10–56 on 8 cores), so absolute numbers are inflated. Source: `docs/evidence/2026-10-29/perf-stage3/README.md` §1.

| Run | capture→render median / p95 / max (ms) | Server vision median / p95 (ms) | Rate (Hz) |
|---|---|---|---|
| stable | 41 / 92 / 433 | 12.41 / 23.94 | 9.43 |
| rn | 61 / 123 / 408 | 37.17 / 71.59 | 9.15 |
| stable-r2 | 27 / 56 / 225 | 9.02 / 15.13 | 9.75 |
| rn-r2 | 50 / 75 / 221 | 30.835 / 45.31 | 9.71 |
| stable-r3 | 28 / 46 / 187 | 8.9 / 13.44 | 9.67 |
| rn-r3 | 50 / 77 / 254 | 31.1 / 45.15 | 9.75 |

perf02 log completeness with fault injection, 2026-10-29 (still the Stage-3 log-completeness evidence). Source: `docs/evidence/2026-10-29/perf-stage3/stable/perf02.json` and `docs/evidence/2026-10-29/perf-stage3/rn/perf02.json`.

| | stable MN | RN |
|---|---|---|
| D1 server-seen completeness | 210/210 (1.0) | 210/210 (1.0) |
| D2 all-logical completeness | 210/210 (1.0) | 210/210 (1.0) |
| Stored windows | 209 | 209 |
| Faults | 1 `input_validation` | 1 `input_validation` |
| Duplicate request ids in DB | 0 | 0 |
| HTTP status of answered requests | 201 × 209, 422 × 1 | 201 × 209, 422 × 1 |
| Model identity checked before and after restart | `stable_mobilenet_v3_large` `b3a42e8d…` both | `resnet18_search004_seed42` `5e226722…` both |

The denominator is 210 here versus 211 in the 2026-10-22 baseline; perf02's phase end conditions are "≥ N windows", so the total is not a fixed target (`docs/evidence/2026-10-29/perf-stage3/README.md` §2). The audited quantities are the completeness ratio, the fault count and duplicates.

### 4.4 What Part 4 does not show

- No target-hardware measurement and no real-camera measurement: one development machine, Chromium fake camera, prepared telemetry.
- No risk-accuracy measurement: there is no synchronized multimodal ground truth, so Stage 2 cannot say which model produces a better or safer risk output.
- No HIGH / HIGH_ALERT behaviour comparison (unreachable in the Stage-2 scenario).
- No Live E2E, UAT or deployment acceptance is claimed.

---

## 5. Summary of the comparison (no winner is declared by this record)

| Dimension | Evidence part | Direction | Caveat |
|---|---|---|---|
| 10-class Macro-F1 / accuracy / log loss | Part 1.1 | RN higher F1 (+0.0146) and accuracy (+0.0027), lower log loss (−0.1236) | 4 drivers; no CIs; not safer driving |
| c0 recall | Part 1.2 | stable MN higher (0.9211 vs 0.8329) | gap driven mostly by driver p026 |
| c9 F1 / recall | Part 1.2 | RN higher (0.6059 vs 0.3972) | both 0 F1 on p050 |
| Binary diagnostic false alarms / misses | Part 1.3 | stable MN fewer false alarms (39 vs 87); RN fewer misses (63 vs 90); total errors 129 vs 150 | offline diagnostic, not live risk; stable misses derived |
| E1 stability | Part 1.4 | mixed: RN lower in 8, stable in 9, tie 1 of 18 | labels unverified under corruption |
| Provider compatibility | Part 2 | all three PASS | not an accuracy result |
| Model-only latency | Part 3 | RN p95 25.42 ms vs MN candidate 7.25 ms | stable MN not benchmarked in p4b |
| System latency (10-30) | Part 4.2 | stable MN p95 31/31/31 ms vs RN 45/44/43 ms; server vision median 9.575 / 9.69 / 9.79 vs 26.61 / 26.56 / 26.58 ms | one dev machine, fake camera |
| Log completeness (10-29) | Part 4.3 | identical (210/210, 1 fault, 0 duplicates) | — |
| System outputs (stable200 scenario) | Part 4.1 | RN differs from stable in 5/200 RiskLevel, 12/200 AlertSeverity windows | constructed scenario; no ground truth; High unreachable |

The release decision based on this evidence is the user's (U-5 = A, stable MN stays active, 2026-10-30; written signature pending), recorded in `docs/fyp2/task10a/release_decision.md`. This record does not change it and does not change any configuration.

## 6. Not done / planned / not claimed

- Not done: model-only ORT benchmark of the stable MN model (Part 3 gap); frontal/target-camera evaluation of RN; target-hardware latency; risk-accuracy evaluation against synchronized ground truth; UAT.
- Pending (user): written signature on `docs/fyp2/task10a/release_decision.md` §3; DOCX edits (6.2.3 closing sentences, Table 23) listed in `docs/fyp2/task10a/release_decision.md` §5.
- Not claimed: that any model is safer; that Macro-F1 measures driving safety; vehicle-grade or safety-critical deployment; that RiskLevel represents accident severity.
