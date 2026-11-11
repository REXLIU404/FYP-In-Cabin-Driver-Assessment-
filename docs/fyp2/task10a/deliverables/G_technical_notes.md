# Task 10A Deliverable G: Technical Notes

Engineering notes for Task 10A (ML candidate integration into the Live System). These are not report chapter prose.
Branch `fyp2/live-system`, HEAD `fe7852a`. Unless stated otherwise, paths are relative to the repository root
(`/Users/liu/Desktop/FYP2-Live-System-Integration`). Status tags: **[DONE]** means completed and evidenced,
**[PLANNED]** means not done, **[OUT OF SCOPE]** means not attempted by design.

Final stage verdicts, as recorded:
- Stage 1: VERIFIED_PASS (Codex CX-A1, `/Users/liu/Desktop/FYP2-Live-System/.superpowers/collab/codex/stage1_audit.md`, git-ignored).
- Stage 2: VERIFIED_PASS (A2 re-audit, `docs/fyp2/task10a/stage2_audit_table.md` §5).
- Stage 3 and Stage 5: VERIFIED_PASS (fresh re-audit on 2026-10-30, `docs/fyp2/task10a/stage3_stage5_reaudit.md`).
- Stage 4: VERIFIED_PASS (Codex CX-A3, `/Users/liu/Desktop/FYP2-Live-System/.superpowers/collab/codex/stage3_audit.md` §5).
- U-5 (2026-10-30): option A. The active vision model stays the stable MobileNetV3-Large. ResNet18 `search_004`/seed42 remains an admitted candidate that can be switched in with `DRA_ACTIVE_VISION`. No configuration was changed. The user's written signature is still pending (`docs/fyp2/task10a/release_decision.md` §3).

---

## 1. Candidate Model Integration Design

**Identities in scope** (`docs/plans/2026-10-25-task-10a-candidate-integration.md` §0, "Frozen model identities"):
- Stable runtime (default and rollback reference): `stable_mobilenet_v3_large`, ONNX sha256 `b3a42e8d…` (`docs/evidence/2026-10-26/task10a-stage1/startup-default.json`; also `docs/fyp2/task10a/stage1_audit_table.md` §1).
- Vision candidate `resnet18_search004_seed42` (ResNet18 `search_004`/seed42/best_epoch3, role `VALIDATION_PREFERRED`). ONNX sha256 `5e226722e0712824c78aa0976afa6fa5b8dc6100b147a7f523a09048171d8cf3`.
- Vision comparator `mobilenet_v3_large_search006_seed42` (role `RETAINED_COMPARATOR`). ONNX sha256 `9ee60abb78007773cc625af80c313049c1970f63c1f041bed9f5b2539a384828`.
- Telemetry stays the stable XGBoost (`iteration_range=(0,91)` per plan §0; sha256 `9802cb06…` at both drill starts, `docs/evidence/2026-10-30/stage5-rollback-drill/README.md` and `drill.log`). The research-preferred `xgboost_02` is research evidence only; plan §0 forbids importing or loading it, and the provider's telemetry path was not changed (`docs/evidence/2026-10-26/task10a-stage1/SUMMARY.json`, `telemetry_or_xgb_lines: []`).

**Design decisions** (plan §2, D1 to D6):
- [DONE] D4, the switch mechanism. The active vision model is chosen once, by the environment variable `DRA_ACTIVE_VISION`, when the provider is built. There is no hot-swap API. The default is `active_vision: str = "stable"` (`backend/app/config.py:34`), and the candidate root is `vision_candidates_root` (`backend/app/config.py:35`, env `DRA_VISION_CANDIDATES_ROOT`).
- [DONE] D5, candidate location. Candidates are real directory copies (never symlinks) under `ml/outputs/candidates/<package_dir>/`, indexed by `ml/outputs/candidates/index.json`. They are git-ignored (plan Task 1.1) and were not committed: the re-audit found no `ml/outputs/candidates` path in `git ls-tree -r f5fb90f` (`stage3_stage5_reaudit.md` §2). The integration worktree does not hold these model files. It reaches them through git-ignored read-only links to the original worktree (`release_decision.md` §4; re-audit finding N-2 in `stage3_stage5_reaudit.md`).
- [DONE] Manifest-driven admission. A candidate is admitted only through its package's `runtime_manifest.json` (manifest v1), checked by the shared validator `validate_package` (schema, `class_to_idx`, `run_id`, containment, sha256). See `backend/app/vision_candidates.py:88`.
- [DONE] Additional runtime-contract checks in the loader (`backend/app/vision_candidates.py`):
  - classes must be exactly `c0..c9` with `safe_class == "c0"` (line 92);
  - `preprocess` must equal the provider's `SUPPORTED_PREPROCESS` (line 95);
  - `class_metadata.json` must agree with the manifest, and c0 must carry the runtime alias `safe_driving` (lines 65-78);
  - the index `package` entry must be a bare directory name inside the candidates root (lines 50-62).
- [DONE] Exact preprocessing. Candidates use the same `TrainedProvider.preprocess` as the stable model: bilinear resize to 224, ImageNet mean/std, NCHW float32 (`backend/app/providers/trained.py`). This means no Resize-256/CenterCrop for ResNet18 (plan §12, "Preprocessing").
- [DONE] No silent fallback. Every failed check raises `ModelUnavailable`, which becomes HTTP 503 `models_unavailable`. The stable model is never loaded in a candidate's place (`backend/app/vision_candidates.py` module docstring; `backend/app/providers/trained.py`, candidate branch of `__init__`).
- [DONE] Provenance. `info["vision"]` carries `model_id`, `run_id` (null for stable) and `source` (`stable` or `candidate:<run_id>`). Every window's provenance carries `vision_model_id` and `vision_model_sha256` (`backend/app/providers/trained.py`, the `provenance` dict in `infer`). In candidate mode the provider reports its name as `VisionCandidateONNX+XGBoost`, so it never claims MobileNetV3 (`stage1_audit_table.md` §4).
- [DONE] Fusion, EMA, the Alert FSM and the probability interpretation were not changed (red-line checks, `stage3_stage5_reaudit.md` §2: no diff in `ai/` or `backend/app` over the audited range; `trained.py` unchanged since the Stage-1-audited `00b0e5d`). `P_distraction = 1 − P(c0)` (`backend/app/vision_candidates.py`, `SAFE_ALIAS` comment), and softmax is applied once, as a single `np.exp(logits − max)` in `TrainedProvider.infer` (`backend/app/providers/trained.py`). R10 source-time rules and ruling A are not named separately in the re-audit; they live outside the changed vision code.
- [DONE] Release decision belongs to the user (plan §8). U-5 = A was recorded in `docs/fyp2/task10a/release_decision.md` §3. ResNet18 was not auto-activated, and the code default was not changed (`docs/fyp2/task10a/stage5_audit_table.md`).

**Stage-1 commits** (`docs/fyp2/task10a/stage1_audit_table.md`):
- `871d309` (Task 1.1, config switch)
- `09b4b8d` (Task 1.2, loader)
- `4ca3c69` (Task 1.3, provider wiring and the frontend model name)
- `90b5e2e` (`model_id` added to the fake provider)
- `777cd05` (DS-1 merge: Task 1.4 stable200 runner)

## 2. ONNX Runtime Provider Implementation

- [DONE] Loader `load_candidate(model_id, candidates_root, *, threads=1) -> CandidateVision` in `backend/app/vision_candidates.py`. Its steps:
  1. resolve the package from `index.json`;
  2. validate the manifest;
  3. run the runtime-contract checks;
  4. open `onnxruntime.InferenceSession(..., providers=["CPUExecutionProvider"])` with `intra_op_num_threads=threads` and `inter_op_num_threads=1`;
  5. assert a `tensor(float)` input of shape `[*, 3, 224, 224]`;
  6. run a warm-up forward on zeros, which must return finite `(1, 10)` logits.

  An ONNX load failure, a wrong input signature or a warm-up failure raises `ModelUnavailable` (lines 105-119).
- [DONE] Provider wiring in `TrainedProvider.__init__` (`backend/app/providers/trained.py`):
  - When `settings.active_vision == "stable"`, the hard-coded stable path `vision/mobilenetv3_large_vision.onnx` is used, unchanged.
  - Otherwise `load_candidate` is called, and the candidate's labels must equal the runtime labels `["safe_driving", *class_names[1:]]`.
  - A shared warm-up forward, which must return finite `(1, 10)` output, runs for both.
- [DONE] Inference path, the same for every identity. The steps are `preprocess`, then `vision.run`, a shape/finiteness check, and one numerically stable softmax (`exp(logits − max)`). A runtime failure or bad output raises `ModelRuntimeError`, which becomes HTTP 500 `model_runtime` with origin `vision_model` (`backend/app/providers/trained.py`, `infer`).
- [DONE] XGB path untouched. `git diff 2745348 -- backend/app/providers/trained.py` has 39 changed lines, all on the vision side. `telemetry_or_xgb_lines: []` (`docs/evidence/2026-10-26/task10a-stage1/trained_py_diff_vs_2745348.diff`, `SUMMARY.json`). On 2026-10-30 the re-audit confirmed that `trained.py` is unchanged since `00b0e5d` (`stage3_stage5_reaudit.md` §2).
- [DONE] Manifest CLI validation of both copied real packages: `valid`, exit 0 / 0 (`docs/evidence/2026-10-26/task10a-stage1/manifest-cli-p5_resnet18_search004_seed42_20261023.log`, `manifest-cli-p5_mobilenet_v3_large_search006_seed42_20261023.log`).
- [DONE] Official stable200 provider verification (Gate B), run on 2026-10-26 with `scripts/verify_stable200.py`. Overall `PASS`, exit 0, `blockers: []`. Source: `docs/evidence/2026-10-26/stable200/official_stable200_behavior.json`, summarised in `docs/evidence/2026-10-26/stable200/README.md`.
  - Approved tolerance (FUD-01): `max_abs_prob_delta ≤ 1e-4` and argmax agreement `1.0` (`docs/fyp2/task10a/tolerance_predeclaration.md`, sha256 `61e30579…`).
  - Membership sha256: `601dc3ed6b99e9030f6eb5287e711baf529ea6c0c5b2facab0acd9c3f9373be9`.
  - Results against the parity100 reference (100 sources), each with argmax 100/100:
    - stable: max abs delta 1.778e-7;
    - ResNet18: 1.540e-7;
    - MN `search_006`: 1.688e-7.
  - Results against the stable200 PyTorch saved predictions, each with argmax 200/200:
    - ResNet18: 1.479e-6;
    - MN `search_006`: 6.869e-6;
    - stable: `null` (`NO_STABLE200_REFERENCE`).
  - The per-class mode rule passed for all three.
  - Environment: onnxruntime 1.26.0, numpy 2.4.6, Python 3.13.3.
- [DONE] Evidence kept separate (`docs/evidence/2026-10-26/stable200/README.md`):
  - (a) the ML-side saved-prediction diagnostic, historical;
  - (b) P4A PyTorch/ORT parity, historical and not rerun;
  - (c) the fresh provider forward from 2026-10-26, new.

  stable200 is a provider-compatibility diagnostic. It does not measure driver-monitoring accuracy (plan §0).
- [DONE] Startup identity. With the variable unset, `/api/models` reports `stable_mobilenet_v3_large`, sha256 `b3a42e8d…`, `source = stable`. With the candidate active it reports the candidate (`docs/evidence/2026-10-26/task10a-stage1/startup-default.json`, `startup-resnet18.json`).

## 3. Compatibility and Regression Testing

**Unit and contract tests** (`backend/tests/test_vision_candidates.py`):
- [DONE] These tests always run (the config-default test plus 10 synthetic-package tests, `stage1_audit_table.md` §2):
  - `test_default_active_vision_is_stable`
  - unknown id, missing index, package outside the root
  - `test_a_tampered_hash_is_refused`
  - `test_a_schema_violation_is_refused`
  - `test_a_class_order_other_than_c0_to_c9_is_refused`
  - class-metadata agreement, the `safe_driving` alias, a non-10-logit warm-up failure, and a valid package that loads and forwards.
- [DONE] Provider-level tests:
  - `test_the_stable_default_is_unchanged_and_says_so`
  - `test_a_candidate_replaces_only_the_vision_model_and_never_touches_the_stable_one`
  - `test_a_refused_candidate_raises_and_never_falls_back`
- [DONE] Real-package tests, marked `candidates` and not run by default: `test_the_real_p5_packages_load_and_forward` and `test_switching_to_a_candidate_and_back_in_fresh_processes`. Result: 6 passed, exit 0 (`docs/evidence/2026-10-26/task10a-stage1/pytest-m-candidates.log`).
- [DONE] Hash-check red/green:
  - GREEN: 7 passed (`docs/evidence/2026-10-26/task10a-stage1/tamper-green.log`).
  - RED, with the sha256 comparison removed in an isolated copy: 2 failed (`tamper-red-sha-check-removed.log`).
  - The Codex Stage-1 audit reproduced both (`/Users/liu/Desktop/FYP2-Live-System/.superpowers/collab/codex/stage1_audit.md`, audit point 4).

**Paired system comparison** (Stage 2):
- [DONE] Protocol-first, descriptive-only comparison on stable200 under a fixed configuration, with one subprocess and a fresh temporary SQLite per model.
  - Protocol: `docs/fyp2/task10a/comparison_protocol.json`, sha256 `b6305022…`.
  - Results: `docs/evidence/2026-10-29/comparison-official-bf76ddf/comparison_results.json`.
  - Determinism: zero field differences across three runs (`94c6d14`, `c0c6d43`, `bf76ddf`) and one auditor rerun (`docs/fyp2/task10a/stage2_audit_table.md` §1).
- Descriptive results (`stage2_audit_table.md` §2):

  | Pair | argmax agreement | RiskLevel windows differing (of 200) | AlertSeverity windows differing (of 200) |
  |---|---|---|---|
  | ResNet18 vs stable | 0.91 | 5 | 12 |
  | MN `search_006` vs stable | 0.90 | 6 | 13 |

- The c9 argmax distributions differ between the models, so the results are not identical: stable `{0:6, 7:4, 9:10}`, ResNet18 `{0:3, 9:17}` (`stage2_audit_table.md` §1). Argmax agreement measures agreement between models. It is not accuracy.

**Runtime evaluation** (Stage 3):
- [DONE] Same-day runs on 2026-10-30, alternating stable and ResNet18, 3 rounds each, 600 windows per round (after 20 warm-up) at 9.77-9.79 Hz, on a quiet machine (load 2.3-4.1). Source: `docs/evidence/2026-10-30/stage3-raw/README.md`.

  | Metric | stable (r1 / r2 / r3) | ResNet18 (r1 / r2 / r3) |
  |---|---|---|
  | capture→render p95 | 31 / 31 / 31 ms | 45 / 44 / 43 ms |
  | server vision median | 9.58 / 9.69 / 9.79 ms | 26.61 / 26.56 / 26.58 ms |

  Every run exited 0 with 0 console errors. The quantiles recompute from the raw `perf01_timings.json`: 6/6 sha256-bound and equal to the summary (`recompute.log`). The ResNet18 p95 was measured, not extrapolated.
- [DONE] Log completeness with ResNet18 active (2026-10-29): D1 210/210, D2 210/210, 209 persisted, 1 `input_validation` fault, 0 duplicates; the stable control has the same D1/D2, persisted, fault and duplicate counts (`docs/evidence/2026-10-29/perf-stage3/{stable,rn}/perf02.json`; the denominator of 210 rather than 211 is explained in `docs/evidence/2026-10-29/perf-stage3/README.md` §2, referenced from `stage3_audit_table.md` §2).
- [DONE] Full regression gates, all exit 0:
  - Stage-1 merge gate at `777cd05`: pytest 1115 / vitest 972 (`docs/evidence/2026-10-26/merge-ds1-gate/`).
  - Stage-3 gate at `fe5c41d`: pytest 1355 passed / 0 skipped / 8 deselected, vitest 1022 (`docs/evidence/2026-10-29/stage3-gate/`).
  - Fresh-clone cold start at `f15f539`: pytest 1360 passed / 8 deselected, vitest 1061, build, tsc and eslint all PASS (`docs/evidence/2026-10-30/stage5-coldstart-f15f539/SUMMARY.md`, `gates/`).
  - HEAD `fe7852a` and its parent `f5fb90f` change only `docs/fyp2/task10a/*.md` (`git show --stat`).
- [DONE] Rollback drill on 2026-10-30, 11/11 checks, exit 0, on port 8001 with a throw-away SQLite (`docs/evidence/2026-10-30/stage5-rollback-drill/README.md`, `drill.json`, `drill.log`):
  - Candidate active: sha256 `5e226722…`, one `/infer` returning 201 with provenance naming the candidate.
  - Fresh process with the variable unset: the stable model, sha256 `b3a42e8d…`, one `/infer` returning 201.
  - 94 files under `ml/outputs` were unchanged before and after.
  - The stable sha256 is compared with the frozen value by the drill itself, not by the provider (README note O-8).
- [DONE] Demo path (Stage 4). The viva demo uses the Constructed demo scenario (dataset-frame replay through the same R10/EMA/FSM pipeline as Live). A read-only check of the report draft on 2026-10-29 found no replay numbers presented as Chapter-6 evaluation results (`docs/fyp2/task10a/stage4_demo_path_note.md` §3).

## 4. Model Integration Limitations

- **Offline metrics are not driving safety.** ML-track clean test, 3,657 images, 4 held-out drivers, from `/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/ml/outputs/runs/p4b_20261022/evaluation_metrics.json`:

  | Model | Accuracy | Macro-F1 | log loss | Binary diagnostic accuracy | c0 false-positive proxy |
  |---|---|---|---|---|---|
  | MN-STABLE | 0.8988 | 0.8746 | 0.5745 | 0.9647 | 0.0905 |
  | RN-HPO42 | 0.9016 | 0.8892 | 0.4509 | 0.9590 | 0.2019 |

  The binary diagnostic is labelled `ADDITIONAL_OFFLINE_DIAGNOSTIC_NOT_LIVE_RISK`. A higher Macro-F1 does not mean safer driving, and neither identity has been shown to give better fused risk output. There is no synchronised multimodal ground truth (`release_decision.md` §1).
- **Stage 2 is a constructed scenario.** It uses 10 class blocks of 20 frames and one fixed Safe telemetry row, so RiskScore peaks at about 50. High and HIGH_ALERT cannot be reached by design. The comparison does not show a general multimodal benefit, and it has no risk ground truth (`stage2_audit_table.md` §3). RiskLevel is a derived operational level, not accident severity.
- **One machine only.** Latency was measured on one development machine (Apple M2), with a Chromium fake camera, prepared telemetry and frozen models. It is not target hardware and not a real camera (`docs/evidence/2026-10-30/stage3-raw/README.md`). The 2026-10-29 Stage-3 numbers were taken under heavy load (load average 10-56) and are summary-only. They are historical and superseded (`stage3_audit_table.md` §3, §7).
- **Frontal camera.** Domain shift was measured for the stable model only: `safe_driving` was the top class in about 5 of ~5,170 frames (`docs/evidence/2026-10-22/vision-runtime-path/README.md`, cited in `release_decision.md` §2). ResNet18 was not measured on the frontal camera. The side camera (4-B) is informal and is not evaluation evidence (`stage4_demo_path_note.md` §2).
- **Small test population.** The test set has 4 held-out drivers and only 431 c0 frames, so both the A-side c0 advantage and the B-side overall gain rest on a small sample (`release_decision.md` §1).
- **Known configuration caveat (R-3).** The settings read the `.env` in the current directory at startup, so a repository-root `.env` could also set `DRA_ACTIVE_VISION`. No `.env` exists at present (`release_decision.md` §4).
- **Field-name caveat (F-5).** `mean_abs_prob_delta` in the Stage-2 results is the mean of per-window maximum absolute deltas. The field name was kept (`stage2_audit_table.md` §5).
- **Unrecoverable logs.** The perf01 uvicorn logs of the six 2026-10-30 runs were written to throw-away directories and cannot be recovered (`docs/evidence/2026-10-30/stage3-raw/README.md`).
- **[OUT OF SCOPE]** No new training, HPO, export or benchmark; no telemetry candidate (`xgboost_02` not loaded); no runtime hot-swap; no GPU or other ONNX execution provider (CPU only); no push.
- **[PLANNED / pending, not done]**
  - The user's written signature on `release_decision.md` §3.
  - Report DOCX edits to the last two sentences of 6.2.3 and to Table 23 (only the capture→render and Server total rows switch to the 2026-10-30 stable numbers; the other rows keep their 2026-10-22 sources), which the user makes (`release_decision.md` §5).
  - Any ResNet18 frontal-camera measurement, target-hardware latency, Live E2E/UAT or deployment acceptance. None of these has been executed, and none is claimed.
