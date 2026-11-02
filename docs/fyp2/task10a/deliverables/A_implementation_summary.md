# Task 10A Deliverable A: Implementation Summary

- Scope: plan `docs/plans/2026-10-25-task-10a-candidate-integration.md` section 10, item A ("exact changed files, affected
  functions/classes, model-loading workflow, compatibility decisions").
- Branch / HEAD read: `fyp2/live-system` @ `fe7852a` (worktree `/Users/liu/Desktop/FYP2-Live-System-Integration`).
  System baseline before Task 10A: `2745348` (plan section 0).
- Sources: read-only `git log` / `git show --stat` / `git diff 2745348` over the commits listed below, plus the files cited
  next to each statement. This is an engineering record, not report prose.
- Stage verdicts (already decided, not re-derived here): Stage 1 VERIFIED_PASS (Codex), Stage 2 VERIFIED_PASS (fresh
  re-audit), Stage 3 and Stage 5 VERIFIED_PASS (fresh re-audit 2026-10-30, `docs/fyp2/task10a/stage3_stage5_reaudit.md`),
  Stage 4 VERIFIED_PASS (Codex CX-A3). Release decision U-5 (2026-10-30): option A, active vision model stays stable
  MobileNetV3-Large; ResNet18 `search_004`/seed42 remains an admitted, switchable candidate; no configuration changed;
  written signature pending (`docs/fyp2/task10a/release_decision.md` sections 3-4).

## 1. Which commits are Task 10A

`git log 871d309^..HEAD` on this branch also contains the Constructed demo scenario work (`14f1b4e` .. `cde7ab1`, merged
into the same branch) and the DS-0 / DS-3 review-fix lanes (`5edd868`, `75e1094`) and the 10-29/10-30 frontend mode fixes
(`afd8724` .. `9255c83`). Those are **not** Task 10A and are excluded below. `docs/fyp2/task10a/stage1_audit_table.md`
lists `5edd868` (DS-0) as "not part of 10A, but in the baseline".

### 1.1 Code commits (source and tests)

| Commit | Date | Purpose | Files changed (from `git show --stat`) |
|---|---|---|---|
| `871d309` | 2026-10-26 | Task 1.1: active-vision config switch, candidates ignore rule | `.gitignore` (+3), `backend/app/config.py` (+5), `backend/tests/test_vision_candidates.py` (+15) |
| `09b4b8d` | 2026-10-26 | Task 1.2: manifest-driven candidate loader | `backend/app/vision_candidates.py` (+126, new), `backend/tests/conftest.py`, `backend/tests/test_long_marker.py`, `backend/tests/test_vision_candidates.py` (+177) |
| `4ca3c69` | 2026-10-26 | Task 1.3: wire loader into `TrainedProvider`; provenance; UI model name | `backend/app/providers/trained.py` (39 lines changed), `backend/tests/test_live_inference.py` (+2), `backend/tests/test_vision_candidates.py` (+128), `frontend/src/App.tsx`, `frontend/src/api/client.ts`, `frontend/src/utils/dataMode.ts`, `frontend/src/utils/dataMode.test.ts`, `frontend/src/utils/modelInfo.ts` (+12, new), `frontend/src/utils/modelInfo.test.ts` (+48, new) |
| `90b5e2e` | 2026-10-26 | Fault-test stand-in provider carries `info['vision']['model_id']` (full gate on `4ca3c69` had 23 failures, `KeyError 'model_id'`) | `backend/tests/test_fault_events.py` (+3 / -1) |
| `b60235a` (merged as `777cd05`) | 2026-10-26 | Task 1.4: official stable200 provider verification runner (DS-1) | `scripts/verify_stable200.py` (+670, new), `backend/tests/test_verify_stable200.py` (+321, new), evidence under `docs/evidence/2026-10-26/stable200/` and `ds-stable200-gate/` |
| `6df94ef` (merged as `dd7b9d5`) | 2026-10-29 | Stage 2: paired vision comparison runner (DS-2) | `scripts/compare_vision_models.py` (+1014, new), `backend/tests/test_compare_vision_models.py` (+497, new), evidence under `docs/evidence/2026-10-29/comparison/` and `ds-compare-gate/` |
| `bf76ddf` | 2026-10-29 | Stage-2 runner fixes for audit A2 F-1..F-4 | `scripts/compare_vision_models.py` (+45 / -7; commit total +105 / -7), `backend/tests/test_compare_vision_models.py` (+58), `docs/evidence/2026-10-29/comparison/README.md` |
| `fe5c41d` | 2026-10-29 | Stage 3 (CL-3): `--active-vision` for perf01/perf02 with loaded-model identity check | `backend/tests/e2e_support.py` (+23), `backend/tests/test_perf_scripts.py` (+60 / -1), `scripts/perf01.py` (+10 / -5), `scripts/perf02.py` (+12 / -5) |
| `1cd5660` | 2026-10-30 | Stage 3 R-1 closure: perf01 keeps raw per-window timings, bound by hash | `scripts/perf01.py` (+24 / -1), `backend/tests/test_perf_scripts.py` (+20) |
| `f15f539` | 2026-10-30 | Audit follow-up O-7: strengthened raw-timings test (plus doc records) | `backend/tests/test_perf_scripts.py` (+10 / -1); docs listed in 1.2 |

Not changed by any Task 10A commit: fusion / EMA / Alert FSM code (`ai/src/`, `backend/app/fusion.py`), the XGBoost /
telemetry lines of `backend/app/providers/trained.py` (section 4.3), the stable model files under `ml/outputs/vision/`.

### 1.2 Record / evidence commits (no source change)

| Commit | Task 10A records written |
|---|---|
| `3ab55ad` | `docs/fyp2/task10a/README.md`, `approval_record.json`, `comparison_protocol.draft.json`, `comparison_protocol.json`, `preflight_report.md`, `tolerance_predeclaration.md`, `tolerance_predeclaration.preapproval_20261026.md` (+19 evidence files) |
| `ba018bb`, `44b93d7` | evidence correction: mislabelled gate directory removed, clean gate reruns (`docs/evidence/2026-10-26/`) |
| `94c6d14` | gate after merging DS-1 (`docs/evidence/2026-10-26/merge-ds1-gate/`) |
| `00b0e5d` | `docs/fyp2/task10a/stage1_audit_table.md` + 11 files in `docs/evidence/2026-10-26/task10a-stage1/` |
| `c0c6d43`, `a4f4998`, `314dac8` | Stage-2 gate and official runs; `docs/fyp2/task10a/stage2_audit_table.md` |
| `ffde897`, `695dad9` | user decision U-1 recorded; Stage-2 re-audit slips R-1, R-2 fixed in `stage2_audit_table.md` |
| `e04f662` | `docs/fyp2/task10a/stage3_audit_table.md`, `stage4_demo_path_note.md` + 29 evidence files (`docs/evidence/2026-10-29/perf-stage3/`, `stage3-gate/`) |
| `637a0ff` | `docs/fyp2/task10a/release_decision.md`, `stage5_audit_table.md`, `stage3_audit_table.md`; `docs/evidence/2026-10-30/stage3-raw/`, `stage5-rollback-drill/` |
| `f15f539`, `a46f80d` | U-5 recorded in `release_decision.md`; `stage3_r1_stage5_audit.md`; fresh-clone gate `docs/evidence/2026-10-30/stage5-coldstart-f15f539/` |
| `f5fb90f` | FUD-1 / FUD-5 recorded in `stage3_audit_table.md`, `stage5_audit_table.md` |
| `fe7852a` | `stage3_stage5_reaudit.md` (VERIFIED_PASS), minor fixes in `release_decision.md`, `stage3_audit_table.md`, `stage5_audit_table.md` |

Not committed (by design, plan section 1 rule 6): the candidate packages under `ml/outputs/candidates/` (git-ignored by
`871d309`'s `.gitignore` rule `ml/outputs/candidates/`).

## 2. Affected functions and classes

| File | Symbol | Change |
|---|---|---|
| `backend/app/config.py` | `Settings.active_vision: str = "stable"` | New. Env `DRA_ACTIVE_VISION`. Read once when the provider is first built. |
| `backend/app/config.py` | `Settings.vision_candidates_root: Path` | New. Default `<repo>/ml/outputs/candidates`. Env `DRA_VISION_CANDIDATES_ROOT` (commit message `871d309`). |
| `backend/app/vision_candidates.py` | `CandidateVision` (dataclass) | New: `model_id`, `run_id`, `package_dir`, `session`, `input_name`, `labels`, `info`. |
| `backend/app/vision_candidates.py` | `load_candidate(model_id, candidates_root, *, threads=1)` | New: the whole candidate validation + load + warm-up (section 3). |
| `backend/app/vision_candidates.py` | `_package_dir`, `_labels`, `_read_json`, `_unavailable` | New private helpers (index lookup, label construction, JSON read, late import of `ModelUnavailable`). |
| `backend/app/runtime_manifest.py` | `validate_package`, `SUPPORTED_PREPROCESS` | **Reused unchanged** (not in any Task 10A diff). |
| `backend/app/providers/trained.py` | `TrainedProvider.candidate_name = "VisionCandidateONNX+XGBoost"` | New class attribute. |
| `backend/app/providers/trained.py` | `TrainedProvider.__init__` | Branch on `settings.active_vision`; candidate label check; `info["vision"]` gains `model_id` / `run_id` / `source`. |
| `backend/app/providers/trained.py` | `TrainedProvider.infer` (provenance dict) | One line added: `"vision_model_id": self.info["vision"]["model_id"]`. |
| `backend/app/providers/trained.py` | `get_provider`, `ModelUnavailable` | Not changed. |
| `frontend/src/api/client.ts` | `ModelStatus.vision` | Optional `model_id`, `run_id`, `source` added. |
| `frontend/src/utils/modelInfo.ts` | `describeVisionModel(vision)` | New: `"<arch> (stable)"`, `"<arch> · candidate <model_id>"`, or the architecture alone for an older backend without `source`. |
| `frontend/src/App.tsx` | run-info line, "Loaded model versions" | Shows `Vision model: …` from `/api/models` instead of the hard-coded `MobileNetV3:` label. |
| `frontend/src/utils/dataMode.ts` | `DATA_MODE_NOTE.LIVE_MODEL_RUNTIME` | `4ca3c69` removed the architecture name. (The sentence was edited again later by `37e7229`, a non-10A frontend commit.) |
| `backend/tests/conftest.py` | `OPT_IN_MARKERS = ("long", "candidates")`, collection hook | New `candidates` marker: deselected unless `-m candidates`, so default gates report 0 skipped. |
| `backend/tests/e2e_support.py` | `vision_env`, `check_vision_identity`, `loaded_vision` | New (`fe5c41d`): server env for a model id; stop the run if `/api/models` reports a different model. |
| `scripts/perf01.py` | `collect`, `main`, new `measured_ids`, `RAW_TIMINGS_FILE`, `RAW_TIMING_FIELDS` | `--active-vision` (`fe5c41d`); raw timings file (`1cd5660`, section 6). |
| `scripts/perf02.py` | `run`, `main` | `--active-vision`; identity checked at start and again after the restart (`fe5c41d`). |
| `scripts/verify_stable200.py` | new script (e.g. `run`, `run_worker`, `spawn_worker`, `compare_set`, `evaluate_class_rule`, `stable_softmax64`, `membership_sha256`) | Official stable200 provider verification, one child process per model. |
| `scripts/compare_vision_models.py` | new script (e.g. `run`, `protocol_gate`, `verify_protocol_inputs`, `execute_plan`, `worker_env`, `post_run_protocol_check`, `paired_summary`) | Stage-2 paired comparison through the real `/infer` pipeline; `post_run_protocol_check` and per-model input re-verification added by `bf76ddf`. |

## 3. Model-loading workflow

Read from `backend/app/config.py`, `backend/app/providers/trained.py`, `backend/app/vision_candidates.py`.

1. **Config.** `Settings.active_vision` (env `DRA_ACTIVE_VISION`, default `"stable"`) and
   `Settings.vision_candidates_root` (default `ml/outputs/candidates`). Switching is by environment variable at provider
   construction only; there is no runtime hot-swap API (plan section 2, D4). The provider is a process singleton built
   on first use by `get_provider()`, so a switch needs a fresh process.
2. **Shared runtime contract (both paths).** `TrainedProvider.__init__` reads the stable `vision/metrics.json` and
   `telemetry/metrics.json` from `settings.model_root`, checks class order `c0..c9` and `Safe/Aggressive/Distracted`,
   and builds `self.labels = ["safe_driving", *class_names[1:]]` and the telemetry feature order. This happens before
   the vision branch, so the runtime label contract is the same for stable and candidate.
3. **Stable path (`active_vision == "stable"`).** Opens `ml/outputs/vision/mobilenetv3_large_vision.onnx` with ORT
   CPU, checks a float32 `[3, 224, 224]` input. These lines are the pre-10A lines, re-indented under the `if`.
4. **Candidate path (anything else)** - `load_candidate(settings.active_vision, settings.vision_candidates_root,
   threads=settings.inference_threads)`:
   1. `_package_dir`: `<root>/index.json` must exist and contain the model id; its `package` value must be a bare
      directory name inside the root (no path separators, not `.`/`..`).
   2. Read `<package>/runtime_manifest.json`; `validate_package(manifest, package_dir)` (shared validator: schema,
      `class_to_idx`, `run_id` == directory, containment, model sha256 of the real file).
   3. Runtime-contract checks the validator does not pin: `classes == c0..c9` in order, `safe_class == "c0"`,
      `preprocess == SUPPORTED_PREPROCESS` (`rgb_resize_224_bilinear_no_crop_div255_imagenet`,
      `backend/app/runtime_manifest.py:16`).
   4. `_labels`: `class_metadata.json` `classes` / `safe_class` must equal the manifest's; each of `c0..c9` needs a
      non-empty `training_labels` entry; labels = `runtime_aliases` over `training_labels`; `labels[0]` must be
      `safe_driving`.
   5. ORT `InferenceSession` on CPU (`intra_op_num_threads = threads`, `inter_op_num_threads = 1`); input must be
      `tensor(float)` with shape `[*, 3, 224, 224]`.
   6. Warm-up: one forward on zeros `(1, 3, 224, 224)`; output must be `(1, 10)` and finite.
   7. Returns `CandidateVision` with `info = {architecture, model_id, run_id, source: "candidate:<run_id>",
      sha256: manifest model sha256, runtime, classes, input, mean, std}`.
   Back in `TrainedProvider.__init__`: `candidate.labels` must equal `self.labels`, else `ModelUnavailable`; then
   `self.vision` / `self.input_name` come from the candidate and `self.name = "VisionCandidateONNX+XGBoost"`. The stable
   ONNX is not opened on this path (commit `4ca3c69`: "a test runs with it absent").
5. **Telemetry.** XGBoost booster loaded from `telemetry/xgb_telemetry.json` exactly as before (section 4.3).
6. **Provider warm-up.** The existing provider warm-up (zeros forward, `(1, 10)` finite logits) runs for whichever
   vision session is active.
7. **Provenance / identity.**
   - `info["vision"]` for stable: `model_id "stable_mobilenet_v3_large"`, `run_id None`, `source "stable"`, `sha256` =
     sha256 of the stable ONNX bytes computed at load. For a candidate: `candidate.info` (sha256 from the manifest,
     already checked against the file in step 4.2).
   - `/api/models` returns `info` (`backend/app/main.py:103-109`).
   - Every window's provenance records `vision_model_id` next to the existing `vision_model_sha256` and
     `telemetry_model_sha256`.
   - Observed values: stable `b3a42e8dd4553355b1fd7d9e7fe3d28e318decb894e76eb029489b7ff2e90bcf`, provider
     `MobileNetV3ONNX+XGBoost`; ResNet18 candidate `5e226722e0712824c78aa0976afa6fa5b8dc6100b147a7f523a09048171d8cf3`,
     `source candidate:p5_resnet18_search004_seed42_20261023`, provider `VisionCandidateONNX+XGBoost`
     (`docs/evidence/2026-10-26/task10a-stage1/SUMMARY.json`). Telemetry XGBoost `9802cb06…` in both
     (`docs/evidence/2026-10-30/stage5-rollback-drill/README.md`).
8. **Failure.** Every refusal in step 4 raises `ModelUnavailable` with a plain reason. `get_provider()` re-raises any
   construction failure as `ModelUnavailable("Trained models are unavailable; check local model artifacts and inference
   dependencies")` chained to the original (`backend/app/providers/trained.py:218-226`); `/api/models` maps it to HTTP
   503 and `/infer` to HTTP 503 with category `models_unavailable` (`backend/app/routers/windows.py:298-300`). Note from
   reading the code: the HTTP detail carries the generic wrapper message; the candidate-specific reason is on the
   exception chain. Whether that reason also reaches the server log was not checked for this record.

## 4. Compatibility decisions

### 4.1 Labels come from the runtime aliases (correction C-2)

The real P5 `class_metadata.json` has no `class_names`; labels are built from `training_labels` with `runtime_aliases`
on top, and `c0` must read `safe_driving` (`09b4b8d` message; `stage1_audit_table.md` section 4). The provider then
requires candidate labels == runtime labels from the stable `vision/metrics.json`, so `P_distraction = 1 - P(c0)` and
the UI class names are identical across models. Softmax is applied by the provider once, as before.

### 4.2 Stable path unchanged; stable stays default

- `active_vision` defaults to `"stable"`, pinned by `test_default_active_vision_is_stable` and
  `test_the_stable_default_is_unchanged_and_says_so` (`backend/tests/test_vision_candidates.py`).
- Default start: `/api/models` vision `stable_mobilenet_v3_large`, sha256 `b3a42e8d…`, `source = stable`
  (`docs/evidence/2026-10-26/task10a-stage1/startup-default.json`).
- The stable artifact `ml/outputs/vision/mobilenetv3_large_vision.onnx` is never overwritten; the rollback drill hashed
  94 files under `ml/outputs` before and after with no change (`docs/evidence/2026-10-30/stage5-rollback-drill/README.md`).
- U-5 (option A) kept the default; no configuration was changed (`docs/fyp2/task10a/release_decision.md`).
- Limitation recorded by the audit (O-8, same README): the provider computes the stable sha256 but does not compare it
  to a frozen value; that comparison is made by the drill script, not at load. Only the candidate's sha256 is enforced
  at load.

### 4.3 XGBoost / telemetry unchanged

`git diff 2745348 -- backend/app/providers/trained.py`: 39 changed lines, all vision-side; telemetry/XGB lines `[]`
(`docs/evidence/2026-10-26/task10a-stage1/SUMMARY.json`, diff saved as `trained_py_diff_vs_2745348.diff`). Reading the
same diff at `fe7852a` shows the same hunks: `candidate_name`, the vision branch, `vision_info`, and the provenance
`vision_model_id` line. The telemetry research preference `xgboost_02` was not imported or loaded (plan section 0).

### 4.4 No silent fallback

A refused candidate raises; the stable model is never loaded in its place while reporting candidate inference (plan
section 1 rule 3). Tests: `test_a_refused_candidate_raises_and_never_falls_back`, `test_a_tampered_hash_is_refused`,
`test_a_schema_violation_is_refused`, `test_a_class_order_other_than_c0_to_c9_is_refused`,
`test_c0_must_carry_the_runtime_alias_safe_driving`, `test_a_model_whose_output_is_not_ten_logits_fails_its_warm_up`,
`test_unknown_model_id_is_refused`, `test_a_missing_index_is_refused`, `test_a_package_path_outside_the_root_is_refused`
(`backend/tests/test_vision_candidates.py`, 16 test functions in total). Red/green for the hash check: with the sha256
comparison removed in an isolated copy, 2 tests fail (`tamper-red-sha-check-removed.log`, exit 1); with it, 7 pass
(`tamper-green.log`, exit 0) (`docs/evidence/2026-10-26/task10a-stage1/`).

### 4.5 Honest naming and opt-in real-package tests

- A candidate provider reports `VisionCandidateONNX+XGBoost`, not MobileNetV3; the UI repeats `/api/models`
  (correction C-5, `4ca3c69`).
- Real P5 package tests carry the `candidates` marker and run only with `-m candidates`
  (`docs/evidence/2026-10-26/task10a-stage1/pytest-m-candidates.log`); default gates stay at 0 skipped (correction C-4).

## 5. Fusion, risk and FSM

No Task 10A commit touches fusion, EMA, the Alert FSM, evidence-expiry handling or probability interpretation. A
candidate changes only the vision probabilities that enter the unchanged pipeline. `RiskLevel` remains a derived
operational level, not accident severity. Stage-2 differences between models (e.g. RiskLevel differs in 5/200 windows,
`docs/fyp2/task10a/release_decision.md` section 2) have no risk ground truth and do not show that either model makes the
risk output better; a higher Macro-F1 is not evidence of safer driving.

## 6. perf01 raw-timings change (`1cd5660`, test strengthened in `f15f539`)

- Problem (CX-A3 finding R-1): the Stage-3 audit could not recompute the 2026-10-29 p50/p95 because `perf01.json` held
  only the summary (`docs/evidence/2026-10-30/stage3-raw/README.md`).
- Change in `scripts/perf01.py`:
  - `measured_ids(raw, windows, warmup)` = `sorted(raw["timings"])[warmup:warmup + windows]`, now used by both
    `analyse` and the new writer, so the file and the statistics cover the same windows.
  - Writes `perf01_timings.json`: one row per measured window with fields `windowId, capturedAtMs, renderedAtMs,
    captureToSendMs, networkMs, renderMs, attemptIndex`.
  - `perf01.json` gains `raw_timings = {file, windows, sha256 of the file bytes, capture_to_render: "renderedAtMs -
    capturedAtMs per row", quantile_rule: "sorted values; median = statistics.median; p95 = value at index min(n - 1,
    round(0.95 * (n - 1))) (e2e_support.summarise)"}`.
- Tests (`backend/tests/test_perf_scripts.py`): the file's rows recompute exactly the reported capture->render
  statistics; `f15f539` (O-7) makes per-window durations differ and gives the warm-up out-of-range durations so the
  equality is not trivial. Focused run: 29 passed (`docs/evidence/2026-10-30/stage3-raw/focused-test-GREEN.log`);
  against `e07ef42` (before `1cd5660`): `KeyError: 'raw_timings'`, 1 failed (`focused-test-RED-e07ef42.log`).
- Runs made with this code (six, alternating, 600 windows each, 2026-10-30): capture->render median / p95 (ms) stable
  27/31, 28/31, 28/31; ResNet18 42/45, 41/44, 41/43. Recompute with a separate script (`recompute_raw.py`, its own quantile rule, not the repository's code): 6/6 sha256
  bound, 6/6 equal to the summary, `ALL OK`, exit 0 (`docs/evidence/2026-10-30/stage3-raw/recompute.log`, `README.md`). Example binding: stable-r1
  `raw_timings.sha256 = 9f0bd8a3c4d8cdde4f68872d76209d1068c926b5202b5e8df2e364a65f450ede`, 600 windows
  (`docs/evidence/2026-10-30/stage3-raw/stable-r1/perf01.json`).
- Scope of these numbers: one Apple M2 development machine, Chromium fake camera, prepared telemetry; not target
  hardware or a real camera. Server-side stage timings (Server-Timing) remain summary-only; only capture->render is
  recomputable from raw rows (`release_decision.md` section 2). The 2026-10-29 Stage-3 files are kept as historical,
  summary-only.

## 7. Not done / not claimed

- No active-model change: ResNet18 is admitted and switchable via `DRA_ACTIVE_VISION=resnet18_search004_seed42`, not
  enabled. The U-5 written signature is still pending (`release_decision.md` section 3).
- No runtime hot-swap; switching needs a process restart.
- No frozen-hash enforcement for the stable model at load (section 4.2).
- No retraining, export, telemetry-model change, or commit of model artifacts.
- No claim of real-camera reliability, target-hardware performance, vehicle-grade deployment or safety benefit;
  frontal-camera accuracy of the candidate was not measured (`release_decision.md` section 2).
