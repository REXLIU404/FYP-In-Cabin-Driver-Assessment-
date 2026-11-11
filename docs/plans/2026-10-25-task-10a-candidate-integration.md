# Task 10A — ML Candidate Integration, Verification and Report Evidence

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Integrate the two delivered P5 Vision candidates into the completed Live System with manifest-driven, hash-verified loading; keep the stable MobileNetV3+XGBoost runtime as the default; produce real provider-forward verification (stable200), a controlled paired comparison, runtime measurements and FYP2 report-ready evidence.

**Architecture:** Minimal extension of the existing `TrainedProvider`: a new manifest-driven candidate loader (`backend/app/vision_candidates.py`) reuses the existing `runtime_manifest` validator; a settings switch (`DRA_ACTIVE_VISION`, default `stable`) selects which vision model the provider loads at startup. Fusion, EMA, Alert FSM, telemetry path, API schemas and frontend remain unchanged. Candidate packages are copied (never symlinked) into `ml/outputs/candidates/` and are never committed.

**Tech Stack:** Python 3.13 (FastAPI, pydantic-settings, onnxruntime 1.26, xgboost 3.2), pytest; TypeScript/Vite/React for regression gates only.

**Spec (authoritative, read in this order):**
1. `docs/fyp2/11_SYSTEM_INTEGRATION_STAGE_PLAN_AND_AUDIT.md` — user's five-stage integration and audit checklist (Stage 1–5, audit points, red lines). **This plan implements those stages.**
2. `docs/fyp2/ml/ML_TRACK_PROGRESS.md` — ML track P0–P5 verdicts and candidate identities.
3. `docs/fyp2/ml/ML_RESULTS_REVIEW_CONTEXT.md` — frozen selection rationale and validation numbers.
4. `docs/fyp2/ml/reports/FYP2 模型 系统准入 审查.md` — research-level admission review.
5. `AGENTS.md` (repo root) — project conventions, FSM R10 rules, evidence-expiry ruling A, scope guardrails.

---

## 0. Workspaces and Authoritative State

Two worktrees of the same git repo; treat them separately:

| Worktree | Path | Branch / HEAD | Your access |
|---|---|---|---|
| Live System (work here) | `/Users/liu/Desktop/FYP2-Live-System` | `fyp2/live-system` @ `2745348f3d4587e14c1d4a7e53a2bfc4d72225d5` | Read + write (task-scoped) |
| ML track (evidence only) | `/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1` | `fyp2/ml-training` @ `335da4e3de203836c045452f84cc291bcd352a26`, **dirty worktree** | **Read-only. Never edit, stage, commit or clean anything here.** |

**Established facts (do not re-derive or reopen):**

- Live System Track **Tasks 1–10 are complete**; W5/W6 system tests S1–S10 are complete; final review fixes are complete. HEAD `2745348` is the current system baseline.
- ML Track **P0–P5 are complete**: P5 is `VERIFIED_PASS` within its documented copy-only packaging scope. This does **not** mean the Live System has executed the candidates: `provider_load_forward=NOT_RUN`, `official_stable200_behavior=NOT_RUN`, system candidate admission `BLOCKED_BY_TASK10A_IMPLEMENTATION`.
- The current provider hardcodes the stable model: `backend/app/providers/trained.py:56` loads `root / "vision/mobilenetv3_large_vision.onnx"` and does not consume any manifest.
- The stable models in the Live System worktree are **symlinks into the ML worktree** (`ml/outputs/vision/mobilenetv3_large_vision.onnx` -> the ML worktree). The manifest validator correctly rejects out-of-package symlinks; that is why Phase 1 copies candidate packages as real directories.
- ML evidence paths below resolve only in the ML worktree; use the absolute ML-worktree prefix, or `git show fyp2/ml-training:<path>`.

### Frozen model identities

| Role | Identity | Notes |
|---|---|---|
| Stable runtime (default, rollback reference) | Existing MobileNetV3-Large ONNX + existing XGBoost (`iteration_range=(0,91)`) | Never overwrite. Stays default until the user's explicit Stage 5 release decision. |
| Vision candidate | ResNet18 `search_004` / seed42 / best_epoch3, role `VALIDATION_PREFERRED` | ONNX sha256 `5e226722e0712824c78aa0976afa6fa5b8dc6100b147a7f523a09048171d8cf3` |
| Vision comparator | MobileNetV3-Large `search_006` / seed42 / best_epoch6, role `RETAINED_COMPARATOR` | ONNX sha256 `9ee60abb78007773cc625af80c313049c1970f63c1f041bed9f5b2539a384828` |
| Telemetry research preference | XGBoost `xgboost_02` / seed42 | **Research evidence only.** P5 did not deliver a runtime candidate. Do not import, deploy or load it; do not change the telemetry provider. |

Candidate package roots (ML worktree):
- `ml/outputs/runs/p5_candidates_20261023/p5_resnet18_search004_seed42_20261023/` (ZIP sha256 `9fb9551f49aeb3582dfc7cb76c9050b7690a8856621944eb363fecd73ea35029`)
- `ml/outputs/runs/p5_candidates_20261023/p5_mobilenet_v3_large_search006_seed42_20261023/` (ZIP sha256 `ae887dabe3588969576ecfb54fead41d0f03bd02267028a8a80f73311811ae13`)

Each package contains `runtime_manifest.json` (manifest v1), `model.onnx`, `class_metadata.json`, `evaluation_metrics.json`, `artifact_manifest.json`, `predictions_test_clean.csv`, `validation/` (incl. `stable200_annotations.csv`, `stable200_saved_predictions.csv`), `evidence/`, `model_card.md`.

### stable200 (the official deterministic provider smoke set)

- 200 validation samples: each of the 10 classes sorted by filename, first 20 per class. Membership hash (pinned in both manifests' `contract_smoke_set.sample_ids_sha256`): `601dc3ed6b99e9030f6eb5287e711baf529ea6c0c5b2facab0acd9c3f9373be9`.
- Only a `SAVED_VALIDATION_PREDICTION_DIAGNOSTIC` exists today (ML-side, from saved P3 val predictions). **The official provider execution is your evidence gap to close in Phase 1** (`official_stable200_behavior=NOT_RUN` must become RUN, per identity).
- It is a provider-behaviour/compatibility diagnostic. Do **not** claim it establishes real-world driver-monitoring accuracy.

---

## 1. Global Constraints (red lines — violating any one fails the stage)

1. No new training, HPO, export or benchmark; no reselecting trials/seeds using P4 Test or E1 results.
2. RF/LR are never loaded at runtime. The XGB load path and behaviour are unchanged; audit with `git diff 2745348 -- backend/app/providers/trained.py` (XGB/telemetry lines must not change).
3. No SQLite replacement; no prepared-probabilities fallback. A candidate that fails validation/loading must raise (`ModelUnavailable` -> HTTP 503 `models_unavailable`); **never silently fall back to stable while reporting candidate inference succeeded.**
4. Do not redesign fusion, EMA, Alert FSM or probability interpretation to accommodate a candidate. Preserve: R10 FSM source-time rules (2 s High / 10 s Low sustained streaks, repeats do not advance, modality support check) and evidence-expiry ruling A (age > `freshness_tolerance_s` -> missing, factor 0, provenance keeps `{modality}_expired` / `{modality}_age_s`). `RiskScore` stays 0–100; `P_distraction = 1 - P(c0)`; softmax applied exactly once.
5. Every completion claim must be backed by **same-day fresh command output** (exit code + key lines) under `docs/evidence/<YYYY-MM-DD>/`; old logs must not be re-presented as new reruns.
6. Do not commit model artifacts (candidate copies stay untracked under `ml/outputs/candidates/`). Commits are task-scoped on `fyp2/live-system`; **no push**.
7. Preserve unrelated dirty state (e.g. `AGENTS.md`, `backend/driver_risk.db-*`, `docs/evidence/2026-10-23/`, `scripts/__pycache__/`). Never touch the user's backend on port 8000 or the real `driver_risk.db`; tests and runners use temporary databases and port 8001.
8. Preserve the user's current rulings: D06 decision (2026-10-23, commit `87d8668`: constructed evaluation scenarios, pre-declared operational reference policy, complementarity/attenuation, limitations disclosed in the report); 10-25 camera ruling (demo runs the dataset-replay path C as primary; side-camera B is informal only, never evaluation evidence).
9. Do not claim Live E2E, real-camera reliability, UAT or deployment acceptance without corresponding executed tests. Do not equate higher Macro-F1 with safer driving.
10. If a required artifact is missing or unreachable, **stop and report the exact missing dependency** (`BLOCKED`). Never fabricate a model, a metric or a measurement.

---

## 2. Decisions pre-locked (user may override before execution; otherwise proceed with these)

- **D1 Branch:** continue on `fyp2/live-system` with task-scoped commits, no push. (Accepted by the Stage-1 audit point.)
- **D2 Stage-2 comparison input set:** stable200 (membership already pinned, hash `601dc3ed…`). P4A 100-source/211-position parity stays a historical annex, not the comparison input.
- **D3 stable200 timing:** `official_stable200_behavior` is produced in **Phase 1** (Stage 1), because provider verification needs it.
- **D4 Active-model switch mechanism:** environment variable at provider construction (no runtime hot-swap API). `DRA_ACTIVE_VISION=stable` (default) or one of the two candidate model ids.
- **D5 Candidate location in the Live System worktree:** real directory copies under `ml/outputs/candidates/<package_dir>/`, indexed by `ml/outputs/candidates/index.json`; never symlinks.
- **D6 Phase-gate audit mechanism:** every phase ends with a **fresh, read-only audit subagent** (not the implementing session, not the user) verifying the stage's checklist points and rerunning key commands itself. The reusable auditor prompt is section 15. The user spot-checks the audit report, holds the D1–D5 overrides and any red-line judgment call, and alone makes the Stage-5 release decision.

---

## 3. Phase 0 — Preflight (read-only, no code changes)

Goal: confirm the state above, verify every dependency, and produce a GO/BLOCKED preflight report before writing code.

**Files:** none modified. Report written to `docs/fyp2/task10a/preflight_report.md`.

- [ ] **Step 1 — Git state.** From `/Users/liu/Desktop/FYP2-Live-System`: `git rev-parse HEAD` (= `2745348…`), `git status --short`, `git worktree list`, `git diff --cached --name-only`. Record the exact dirty-file list; protect it for the whole run.
- [ ] **Step 2 — Verify ML artifacts exist (read-only, ML worktree).** Confirm both P5 package dirs, both `runtime_manifest.json`, both `model.onnx` (sha256s above), `validation/stable200_annotations.csv`, `validation/stable200_saved_predictions.csv`, `class_metadata.json`. Record `shasum -a 256` of the two `model.onnx` files.
- [ ] **Step 3 — Validate both manifests with the system CLI, unchanged.** Copy `backend/app/runtime_manifest.py`, `backend/app/runtime_manifest.schema.json`, `scripts/validate_runtime_manifest.py` verbatim into an isolated temp dir (preserving relative layout), point it at each real package. Expect `valid / exit 0` for both. Save stdout/stderr.
- [ ] **Step 4 — Resolve the stable200 image data root.** From `<RN package>/validation/stable200_annotations.csv` determine the 200 member IDs (class + filename). Find the actual image files via the data root recorded in `<package>/evidence/source_config.json` and `ml/outputs/runs/p4b_20261022/execution_spec.json` (`data_root` field). If the images are not reachable from the Live System worktree, record the exact missing path and mark stable200 verification `BLOCKED` **before** coding (report it; do not invent images).
- [ ] **Step 5 — XGB untouched baseline.** `git diff 2745348 -- backend/app/providers/trained.py` must be empty (or contain only your later Task-1.3 vision-side edits). Save this baseline output now.
- [ ] **Step 6 — Preflight verdict.** Write `docs/fyp2/task10a/preflight_report.md` with: verified facts, missing/blocked items, and `GO` or `BLOCKED` (+ exact reasons). If `GO`, continue to Phase 1. If any blocker is a scope conflict or a missing critical artifact, **stop and report** per restriction 10.

---

## 4. Phase 1 — Stage 1: Candidate Provider Integration

After Phase 1, **STOP** and deliver the Stage-1 audit table (see Task 1.5) for the user. Do not start Phase 2 before the user's Stage-1 audit.

### Task 1.1: Copy candidates + registry index + config switch

**Files:**
- Create (untracked, never committed): `ml/outputs/candidates/p5_resnet18_search004_seed42_20261023/**`, `ml/outputs/candidates/p5_mobilenet_v3_large_search006_seed42_20261023/**`, `ml/outputs/candidates/index.json`
- Modify: `.gitignore` (add `ml/outputs/candidates/`)
- Modify: `backend/app/config.py`

**Interfaces:**
- Produces: `index.json` schema `{ "<model_id>": {"package": "<dir_name>", "role": "VALIDATION_PREFERRED|RETAINED_COMPARATOR", "architecture": "...", "source_zip_sha256": "<64 hex>"} }`
- Produces: `Settings.active_vision: str = "stable"` (env `DRA_ACTIVE_VISION`) and `Settings.vision_candidates_root: Path = <repo>/ml/outputs/candidates` (env `DRA_VISION_CANDIDATES_ROOT`).

- [ ] **Step 1 — Copy packages as real directories.**
```bash
mkdir -p ml/outputs/candidates
cp -R "/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/ml/outputs/runs/p5_candidates_20261023/p5_resnet18_search004_seed42_20261023" ml/outputs/candidates/
cp -R "/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/ml/outputs/runs/p5_candidates_20261023/p5_mobilenet_v3_large_search006_seed42_20261023" ml/outputs/candidates/
```
- [ ] **Step 2 — Verify copies.** `shasum -a 256` of each copied `model.onnx` must equal the frozen ONNX sha256s in section 0. Any mismatch -> delete the copy and re-copy; if it persists, stop and report.
- [ ] **Step 3 — Write `ml/outputs/candidates/index.json`** with the two entries: model ids `resnet18_search004_seed42` and `mobilenet_v3_large_search006_seed42`, roles/architectures/ZIP sha256s as in section 0.
- [ ] **Step 4 — `.gitignore`.** Append the line `ml/outputs/candidates/`; `git status` must no longer list the copies.
- [ ] **Step 5 — Config fields.**
```python
# backend/app/config.py — inside class Settings, next to model_root:
    model_root: Path = Path(__file__).resolve().parents[2] / "ml" / "outputs"
    # Task 10A: active vision identity. "stable" = existing hardcoded MobileNetV3 path
    # (unchanged behaviour); otherwise a model id from ml/outputs/candidates/index.json.
    active_vision: str = "stable"
    vision_candidates_root: Path = Path(__file__).resolve().parents[2] / "ml" / "outputs" / "candidates"
```
- [ ] **Step 6 — Failing test first** (new file `backend/tests/test_vision_candidates.py`):
```python
def test_default_active_vision_is_stable():
    # Assert on the class defaults; no instance is constructed, no env is read.
    from backend.app.config import Settings
    assert Settings.model_fields["active_vision"].default == "stable"
    assert Settings.model_fields["vision_candidates_root"].default.name == "candidates"
```
Run: `PYTHONPATH=backend .venv/bin/python -m pytest backend/tests/test_vision_candidates.py -q`
Expected: FAIL (fields do not exist yet). Then apply Step 5, rerun: PASS.
- [ ] **Step 7 — Commit.**
```bash
git add .gitignore backend/app/config.py backend/tests/test_vision_candidates.py
git commit -m "feat(task10a): active-vision config switch and candidates ignore rule"
```
(Note: `backend/tests/test_vision_candidates.py` will grow in Tasks 1.2–1.3; committing the first slice here is fine.)

### Task 1.2: Manifest-driven candidate loader (`backend/app/vision_candidates.py`)

**Files:**
- Create: `backend/app/vision_candidates.py`
- Test: `backend/tests/test_vision_candidates.py`

**Interfaces:**
- Consumes: `runtime_manifest.validate_manifest`, `runtime_manifest.validate_package`, `runtime_manifest.SUPPORTED_PREPROCESS` (from `backend/app/runtime_manifest.py`); `Settings.active_vision`, `Settings.vision_candidates_root`; `ModelUnavailable` (from `backend.app.providers.trained` — import it there or move it here; move `ModelUnavailable`/`ModelRuntimeError`/`InvalidFrame` into `backend/app/faults.py` is NOT required — importing `ModelUnavailable` from `providers.trained` is acceptable and avoids touching shared error semantics).
- Produces (exact names):
```python
@dataclass
class CandidateVision:
    model_id: str            # e.g. "resnet18_search004_seed42"
    run_id: str              # package dir name, e.g. "p5_resnet18_search004_seed42_20261023"
    package_dir: Path        # resolved package directory
    session: ort.InferenceSession
    input_name: str
    labels: list[str]        # ["safe_driving", *class_names[1:]], len 10, order c0..c9
    info: dict               # vision info fragment for provider self.info["vision"]

def load_candidate(model_id: str, candidates_root: Path) -> CandidateVision: ...
```

- [ ] **Step 1 — Write the failing tests** (append to `backend/tests/test_vision_candidates.py`). Unit tests use a tiny synthetic package in a `tmp_path`; real-package tests skip when `ml/outputs/candidates/index.json` is absent.

```python
import json, hashlib
import numpy as np
import pytest
from pathlib import Path
from backend.app.vision_candidates import load_candidate, CandidateVision  # to be created
from backend.app.providers.trained import ModelUnavailable

def _make_identity_onnx(path: Path):
    """Deterministic synthetic classifier: X(1,3,224,224) -> Reshape -> MatMul zeros -> (1,10) logits.
    All-zero logits give uniform probs 0.1 after softmax; P_distraction = 0.9. Enough for
    shape/finite/softmax contract tests without any real model file."""
    import onnx
    from onnx import TensorProto, helper
    weight = np.zeros((3 * 224 * 224, 10), dtype=np.float32)
    graph = helper.make_graph(
        [helper.make_node("Reshape", ["X", "shape"], ["flat"]),
         helper.make_node("MatMul", ["flat", "W"], ["logits"])],
        "identity10",
        [helper.make_tensor_value_info("X", TensorProto.FLOAT, [1, 3, 224, 224])],
        [helper.make_tensor_value_info("logits", TensorProto.FLOAT, [1, 10])],
        initializer=[
            helper.make_tensor("W", TensorProto.FLOAT, weight.shape, weight.tobytes(), raw=True),
            helper.make_tensor("shape", TensorProto.INT64, [2],
                               np.array([1, 3 * 224 * 224], dtype=np.int64).tobytes(), raw=True),
        ],
    )
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 13)])
    onnx.checker.check_model(model)
    onnx.save(model, str(path))

def _write_package(root: Path, *, sha: str | None = None, classes: list[str] | None = None,
                   onnx_builder=None) -> Path:
    pkg = root / "p5_synthetic_test_20260101"
    (pkg / "model.onnx").write_bytes(b"fake")
    if onnx_builder is not None:
        onnx_builder(pkg / "model.onnx")
    digest = sha or hashlib.sha256((pkg / "model.onnx").read_bytes()).hexdigest()
    classes = classes or [f"c{i}" for i in range(10)]
    manifest = {
        "manifest_version": 1, "kind": "vision_classifier", "run_id": pkg.name,
        "architecture": "synthetic",
        "model": {"path": "model.onnx", "format": "onnx", "sha256": digest},
        "input": {"shape": [1, 3, 224, 224], "dtype": "float32", "layout": "NCHW", "color": "RGB"},
        "preprocess": "rgb_resize_224_bilinear_no_crop_div255_imagenet",
        "output": {"kind": "logits", "shape": [1, 10]},
        "classes": classes,
        "class_to_idx": {name: i for i, name in enumerate(classes)},
        "safe_class": "c0",
        "contract_smoke_set": {"split": "val", "selection": "synthetic", "n": 200,
                               "sample_ids_sha256": "0" * 64, "rule": "per_class_mode_equals_label"},
    }
    (pkg / "runtime_manifest.json").write_text(json.dumps(manifest))
    (pkg / "class_metadata.json").write_text(json.dumps({
        "class_names": {f"c{i}": n for i, n in enumerate(
            ["normal_driving", "texting_right", "phone_right", "texting_left", "phone_left",
             "radio", "drinking", "reaching", "hair_makeup", "talking"])}}))
    (root / "index.json").write_text(json.dumps(
        {"synthetic_test": {"package": pkg.name, "role": "TEST", "architecture": "synthetic",
                            "source_zip_sha256": "0" * 64}}))
    return pkg

def test_unknown_model_id_reports_missing(tmp_path):
    with pytest.raises(ModelUnavailable, match="not in"):
        load_candidate("nope", tmp_path)

def test_tampered_hash_rejected(tmp_path):
    pkg = _write_package(tmp_path)
    manifest = json.loads((pkg / "runtime_manifest.json").read_text())
    manifest["model"]["sha256"] = "f" * 64
    (pkg / "runtime_manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ModelUnavailable, match="sha256 mismatch"):
        load_candidate("synthetic_test", tmp_path)

def test_bad_schema_rejected(tmp_path):
    pkg = _write_package(tmp_path)
    manifest = json.loads((pkg / "runtime_manifest.json").read_text())
    del manifest["output"]
    (pkg / "runtime_manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ModelUnavailable):
        load_candidate("synthetic_test", tmp_path)

def test_class_order_enforced(tmp_path):
    _write_package(tmp_path, classes=[f"c{i}" for i in range(10)][::-1])
    with pytest.raises(ModelUnavailable):  # class_to_idx mismatch caught by the shared validator
        load_candidate("synthetic_test", tmp_path)

def test_candidate_forward_and_probabilities(tmp_path):
    pytest.importorskip("onnx")  # synthetic-ONNX unit test; real-package tests cover real models
    import onnxruntime as ort
    pkg = _write_package(tmp_path, onnx_builder=_make_identity_onnx)
    candidate = load_candidate("synthetic_test", tmp_path)
    assert candidate.model_id == "synthetic_test"
    assert candidate.labels == ["safe_driving", "texting_right", "phone_right", "texting_left",
                                "phone_left", "radio", "drinking", "reaching", "hair_makeup", "talking"]
    logits = np.asarray(candidate.session.run(None, {candidate.input_name:
                         np.zeros((1, 3, 224, 224), np.float32)})[0], dtype=np.float32)
    assert logits.shape == (1, 10) and np.isfinite(logits).all()
    probs = np.exp(logits - logits.max()) / np.exp(logits - logits.max()).sum()
    assert abs(float(probs.sum()) - 1.0) < 1e-6
    assert abs((1 - float(probs[0, 0])) - 0.9) < 1e-6  # uniform probs -> P_distraction = 0.9
    assert candidate.info["sha256"] == hashlib.sha256((pkg / "model.onnx").read_bytes()).hexdigest()
```
**Loader behaviour contract (what the tests pin down):**
- Unknown model id -> `ModelUnavailable("vision candidate '<id>' is not in <root>/index.json")`.
- Manifest/schema/hash/path failures -> `ModelUnavailable` with the validator's plain-language error text included in the message (no traceback leakage, no fallback).
- `manifest["preprocess"] == SUPPORTED_PREPROCESS` else `ModelUnavailable`.
- ORT session: `CPUExecutionProvider`, `intra_op_num_threads = settings.inference_threads`, `inter_op_num_threads = 1` (same as stable). Warm-up run on `np.zeros((1,3,224,224), np.float32)`: output shape `(1,10)` and finite, else `ModelUnavailable` (mirror `trained.py:81-83`).
- `labels`: load `<package>/class_metadata.json`; require 10 names keyed by `c0..c9` in manifest order; `labels = ["safe_driving"] + [names[1:]]` (mirror `trained.py:62`).
- `info`: `{"architecture": manifest["architecture"], "model_id": model_id, "run_id": run_id, "sha256": manifest["model"]["sha256"], "runtime": "onnxruntime_cpu", "classes": labels, "input": "RGB NCHW float32 224x224", "mean": [0.485,0.456,0.406], "std": [0.229,0.224,0.225], "source": f"candidate:{run_id}"}`.

- [ ] **Step 2 — Run tests to verify they fail** (import error / not defined).
- [ ] **Step 3 — Implement `load_candidate`** to satisfy the contract above, reusing `validate_package` (which already checks schema, run_id==dir name, path containment, SHA-256) and the checks `validate_manifest` cannot express. Do **not** duplicate metric-word or path rules.
- [ ] **Step 4 — Run tests to verify they pass.** Then run the existing manifest tests: `PYTHONPATH=backend .venv/bin/python -m pytest backend/tests/test_runtime_manifest.py -q` — must stay green.
- [ ] **Step 5 — Commit.**
```bash
git add backend/app/vision_candidates.py backend/tests/test_vision_candidates.py
git commit -m "feat(task10a): manifest-driven vision candidate loader"
```

### Task 1.3: Wire the loader into `TrainedProvider`

**Files:**
- Modify: `backend/app/providers/trained.py` (vision-loading block only; telemetry lines untouched)
- Test: `backend/tests/test_vision_candidates.py`, `backend/tests/test_r10b_payload_contract.py` (add the new provenance key)

**Interfaces:**
- Consumes: `load_candidate`, `CandidateVision`; `settings.active_vision`, `settings.vision_candidates_root`.
- Produces: `TrainedProvider.info["vision"]` gains `"model_id"`, `"run_id"`, `"source"` (`"stable"` or `f"candidate:{run_id}"`; `"run_id": null` for stable). Window `provenance` gains `"vision_model_id": <model_id>` (additive; DB payload is free-form JSON — migration-safe).

- [ ] **Step 1 — Failing tests.** Note: `TrainedProvider` reads the **module-level singleton** `backend.app.config.settings`; tests mutate it via `monkeypatch` (auto-restored) rather than constructing fresh instances.
```python
def test_provider_default_is_stable():  # needs the real stable model -> skip pattern as other model tests
    import hashlib
    from backend.app.config import settings
    from backend.app.providers.trained import TrainedProvider
    assert settings.active_vision == "stable"
    provider = TrainedProvider()
    assert provider.info["vision"]["model_id"] == "stable_mobilenet_v3_large"
    assert provider.info["vision"]["source"] == "stable"
    assert provider.info["vision"]["run_id"] is None
    assert provider.info["vision"]["sha256"] == hashlib.sha256(
        (settings.model_root / "vision/mobilenetv3_large_vision.onnx").read_bytes()).hexdigest()

def test_provider_loads_candidate_and_records_identity(monkeypatch):
    # skips when ml/outputs/candidates/index.json is absent (cold-start gates stay green)
    from backend.app import config
    from backend.app.providers.trained import TrainedProvider
    monkeypatch.setattr(config.settings, "active_vision", "resnet18_search004_seed42")
    provider = TrainedProvider()
    assert provider.info["vision"]["model_id"] == "resnet18_search004_seed42"
    assert provider.info["vision"]["source"].startswith("candidate:")
    assert provider.info["vision"]["sha256"] == "5e226722e0712824c78aa0976afa6fa5b8dc6100b147a7f523a09048171d8cf3"

def test_candidate_failure_does_not_fall_back(tmp_path, monkeypatch):
    # tampered synthetic package: construction must raise ModelUnavailable, and the stable
    # path must never be touched (the stable model file is not even read).
    from backend.app import config
    from backend.app.providers.trained import TrainedProvider, ModelUnavailable
    pkg = _write_package(tmp_path)
    manifest = json.loads((pkg / "runtime_manifest.json").read_text())
    manifest["model"]["sha256"] = "f" * 64
    (pkg / "runtime_manifest.json").write_text(json.dumps(manifest))
    monkeypatch.setattr(config.settings, "active_vision", "synthetic_test")
    monkeypatch.setattr(config.settings, "vision_candidates_root", tmp_path)
    with pytest.raises(ModelUnavailable, match="sha256 mismatch"):
        TrainedProvider()
```
- [ ] **Step 2 — Implement** the minimal vision-loading branch in `TrainedProvider.__init__`:
```python
        root = settings.model_root
        if settings.active_vision == "stable":
            vision_path = root / "vision/mobilenetv3_large_vision.onnx"
            # Keep the CURRENT code verbatim: the metrics.json class check (trained.py:58-66),
            # the ORT session + input-shape check + warm-up (trained.py:67-83). Only the
            # info dict construction changes (adds model_id/run_id/source).
            vision_info = {"architecture": "mobilenet_v3_large",
                           "model_id": "stable_mobilenet_v3_large", "run_id": None, "source": "stable",
                           "sha256": ..., "runtime": "onnxruntime_cpu", "classes": self.labels,
                           "input": "RGB NCHW float32 224x224", "mean": [...], "std": [...]}
        else:
            candidate = load_candidate(settings.active_vision, settings.vision_candidates_root)
            self.vision, self.input_name, self.labels = candidate.session, candidate.input_name, candidate.labels
            vision_info = candidate.info
        self.info = {"provider": self.name, "vision": vision_info, "telemetry": {...UNCHANGED...}, "scope": ...}
```
Keep the `class order` / `feature order` checks and the warm-up check for both branches. The XGB block and every line that mentions telemetry must remain byte-identical.
- [ ] **Step 3 — Provenance.** In `infer()`, add to the `provenance` dict: `"vision_model_id": self.info["vision"]["model_id"]`. Extend `test_r10b_payload_contract.py` with one assertion that the window payload carries a string `vision_model_id` equal to the provider's info value.
- [ ] **Step 4 — Rollback test.** Same-day test: `DRA_ACTIVE_VISION=resnet18_search004_seed42` -> provider loads RN; fresh process (new Settings) with `DRA_ACTIVE_VISION=stable` (or unset) -> provider loads stable MN with its known sha256. Record both loads in one log.
- [ ] **Step 5 — Full regression.** `PYTHONPATH=backend .venv/bin/python -m pytest backend/tests -q` — expect the current 1028 passed **plus** the new tests, 0 failures. If any existing test asserted an exact provenance key set, extend that single test (additive key) and note it in the Stage-1 report.
- [ ] **Step 6 — Commit.**
```bash
git add backend/app/providers/trained.py backend/tests/test_vision_candidates.py backend/tests/test_r10b_payload_contract.py
git commit -m "feat(task10a): active-vision selection in TrainedProvider with provenance"
```

### Task 1.4: Official stable200 provider verification (closes `official_stable200_behavior=NOT_RUN`)

**Files:**
- Create: `scripts/verify_stable200.py`
- Evidence: `docs/evidence/<YYYY-MM-DD>/stable200/official_stable200_behavior.json` (+ run logs)

**Interfaces:**
- Consumes: `<package>/validation/stable200_annotations.csv` (200 member IDs: class + filename), the image data root resolved in Phase 0 Step 4, `stable200_saved_predictions.csv` (per-sample saved class probabilities from the ML track), `TrainedProvider` (via env `DRA_ACTIVE_VISION`).
- Produces: one JSON per identity, plus a merged `official_stable200_behavior.json`:
```json
{"date": "...", "input_set": {"name": "stable200", "n": 200,
  "membership_sha256": "601dc3ed6b99e9030f6eb5287e711baf529ea6c0c5b2facab0acd9c3f9373be9",
  "rule": "per class, filename-sorted, first 20"},
 "runs": [
   {"model_id": "stable_mobilenet_v3_large", "sha256": "...", "n_compared": 200,
    "argmax_agreement": <0..1>, "max_abs_prob_delta": <float>, "declared_tolerance": 1e-5, "pass": true,
    "exit_code": 0, "execution": "provider_forward_fresh"},
   {"model_id": "resnet18_search004_seed42", ..., "declared_tolerance": 1e-4, ...},
   {"model_id": "mobilenet_v3_large_search006_seed42", ..., "declared_tolerance": 1e-4, ...}]}
```

- [ ] **Step 1 — Pre-declare tolerances IN the script docstring and output** (before any comparison runs): stable-MN vs its saved predictions `max_abs_prob_delta <= 1e-5` and argmax agreement `1.0`, justified by the existing parity evidence (128-sample PyTorch/ONNX max prob diff ≈ 4.17e-6; P4A parity 100 sources/211 positions); RN/MN-HPO42 vs their own saved validation predictions `max_abs_prob_delta <= 1e-4` and argmax agreement `1.0`, justified by the same export pipeline plus float64 storage rounding. A preprocessing or class-order error produces deltas orders of magnitude larger — these tolerances detect that while not demanding bit-equality.
- [ ] **Step 2 — Implement the runner.** For each identity: resolve the 200 image files from `stable200_annotations.csv` + data root; run them through the **real provider path** (`TrainedProvider.preprocess` -> `self.vision.run` -> softmax -> 10 probs) in a subprocess with `DRA_ACTIVE_VISION=<model_id>` (stable = default); compare per-sample argmax and max abs prob delta against `stable200_saved_predictions.csv`; write the per-identity JSON with exit code. Then merge into `official_stable200_behavior.json`. The saved-prediction CSV is reference data read from the **copied** package (read-only) — never modified.
- [ ] **Step 3 — Run it, same-day.**
```bash
DRA_VISION_CANDIDATES_ROOT=ml/outputs/candidates PYTHONPATH=backend .venv/bin/python scripts/verify_stable200.py --out docs/evidence/$(date +%Y-%m-%d)/stable200/
```
Expected: three `pass: true` runs, exit 0. If stable-MN argmax agreement < 1.0 or any identity fails its declared tolerance: **do not hand-wave** — record `pass: false`, diff the failing samples, and report the discrepancy in the Stage-1 audit (a real mismatch is a finding, not a reason to loosen the tolerance).
- [ ] **Step 4 — Record the distinction explicitly** in the evidence README: (a) ML-side `SAVED_VALIDATION_PREDICTION_DIAGNOSTIC` (historical), (b) P4A PyTorch-ONNX parity (historical), (c) **this** fresh provider forward (new). These are three different things; do not merge them into one claim.
- [ ] **Step 5 — Commit script + evidence README (not the large JSON if huge — JSON is evidence, keep untracked or add as the project convention allows).**
```bash
git add scripts/verify_stable200.py
git commit -m "feat(task10a): official stable200 provider verification runner"
```

### Task 1.5: Stage-1 audit evidence + STOP

- [ ] **Step 1 — Default-startup log.** Start uvicorn on port **8001** with `DRA_ACTIVE_VISION` unset, capture startup; assert the log/readiness shows the stable `mobilenetv3_large_vision.onnx` sha256 and `model_id=stable_mobilenet_v3_large`. Then stop the server (no leftover processes).
- [ ] **Step 2 — XGB untouched proof.** `git diff 2745348 -- backend/app/providers/trained.py` — save the diff; confirm every hunk is vision-side only and telemetry/XGB lines are unchanged.
- [ ] **Step 3 — Same-day full gates.** `PYTHONPATH=backend .venv/bin/python -m pytest backend/tests -q` (expect 1028 + new, 0 failed), `npx vitest run --no-cache` (922), `npx tsc --noEmit`, `npm run linc`, `npm run build`. Save fresh logs under `docs/evidence/<date>/task10a-stage1/`.
- [ ] **Step 4 — Fill the user's Stage-1 audit table** (from `docs/fyp2/11_SYSTEM_INTEGRATION_STAGE_PLAN_AND_AUDIT.md`, Stage 1 审计点): provider code committed after `2745348`; both manifests valid via the system CLI; real forward happened (stable200 + warm-up asserts); hash tampering red/green evidence; default remains MN-STABLE; XGB diff unchanged — each row pointing at a same-day artifact path.
- [ ] **Step 5 — STOP. Fill the Stage-1 audit table, then dispatch the phase-gate audit subagent (section 15).** Do not begin Phase 2 until the subagent returns `VERIFIED_PASS`; on `PARTIAL`/`BLOCKED`/`FAILED`, forward the subagent's findings to the user instead of continuing.

---

## 5. Phase 2 — Stage 2: Paired System Comparison

Precondition: user's Stage-1 audit passed. Goal: fixed replay input, RN candidate vs stable MN frame-by-frame, everything else (fusion/EMA/FSM/DB) unchanged.

**Files:**
- Create: `docs/fyp2/task10a/comparison_protocol.json` (**written BEFORE the runner runs — the D06 pre-declaration requirement**)
- Create: `scripts/compare_vision_models.py`
- Evidence: `docs/evidence/<date>/comparison/comparison_results.json`

- [ ] **Step 1 — Protocol file first.** It must contain, verbatim:
  - input set: stable200 (membership sha256 `601dc3ed…`, rule per-class filename top-20); input images hash-verified before the run;
  - fixed configuration: `w_v=0.5, w_t=0.5`, `ema_alpha=0.35`, `freshness_tolerance_s=3.0`, thresholds 30/60, telemetry = stable XGB (`iteration_range=(0,91)`), replay telemetry features identical across runs;
  - compared identities: `stable_mobilenet_v3_large`, `resnet18_search004_seed42`, `mobilenet_v3_large_search006_seed42`;
  - comparison quantities: RiskScore distribution per window, RiskLevel sequence, DominantEvidence, alert FSM state transitions, per-class argmax sequence;
  - isolation: fresh in-process state and a fresh temporary SQLite per model run (no cross-run EMA/FSM/DB leakage); record how isolation is implemented;
  - decision rule: **descriptive only; no single-score threshold; the replacement decision belongs to the user (Stage 5) and is recorded with reasons.**
  Record the protocol file's sha256 in the runner output.
- [ ] **Step 2 — Implement the runner.** Subprocess per model identity (`DRA_ACTIVE_VISION=...`): replay the same 200 frames + same telemetry rows through the backend inference stack (provider -> `backend.app.inference` window pipeline -> temp SQLite), export per-window rows (window number, RiskScore, RiskLevel, DominantEvidence, alert state, argmax, probs). Merge into `comparison_results.json` with per-model sequences.
- [ ] **Step 3 — Run; verify protocol-first ordering** (protocol file mtime < runner output mtime; input hash recomputed from the same files equals the protocol value).
- [ ] **Step 4 — Sanity checks against P4 facts.** c9 is a known weak class (RN pooled c9 F1 0.6059; MN candidate pooled c9 F1 0.6698; p050 c9 F1=0 for RN) — per-class argmax counts must show c9 differences, not identical distributions. If both models produce identical everything, the comparison is broken — investigate before reporting.
- [ ] **Step 5 — STOP. Dispatch the phase-gate audit subagent (section 15)** with the protocol sha, isolation mechanism, results table and the P4-consistency cross-check. Do not pick a winner; do not switch the active model; do not begin Phase 3 until the subagent returns `VERIFIED_PASS`.

---

## 6. Phase 3 — Stage 3: Runtime Evaluation

Precondition: user's Stage-2 audit passed. Goal: capture-to-render latency for MN and RN, health, regression, log completeness — with the candidate integrated.

- [ ] **Step 1 — Latency measurement, both models, same-day.** Run the perf02-pattern capture (Playwright) against an isolated instance on port 8001, once with stable MN active, once with `DRA_ACTIVE_VISION=resnet18_search004_seed42`, temp DBs. Produce two dated JSONs with the same field structure as `docs/evidence/2026-10-22/perf/perf02.json`. Known references to cite verbatim from the existing files (do not quote from memory): MN model-only p50/p95 in `ml/outputs/runs/p4b_20261022/` runtime tables; system capture->render p50/p95 with MN active in `docs/evidence/2026-10-22/perf/perf01.json`. The RN capture->render p95 **must be measured, never extrapolated** from RN model-only 25.4 ms.
- [ ] **Step 2 — Full same-day regression.** `pytest backend/tests` (1028 + new), `npx vitest run --no-cache` (922), `npx tsc --noEmit`, `npm run linc`, `npm run build` — all exit 0, fresh logs archived.
- [ ] **Step 3 — Log completeness.** Re-run the perf02 D1/D2 accounting under the RN-active instance: 211/211 logged windows, 1 fault `input_validation`, 0 duplicates — matching the existing baseline shape.
- [ ] **Step 4 — Health.** No new error-level logs in the RN run; DB authoritative-latest and idempotency tests pass (they are part of the pytest suite).
- [ ] **Step 5 — STOP. Dispatch the phase-gate audit subagent (section 15)** with the Stage-3 audit table (latency JSONs dated, RN p95 measured, tests same-day, health). Do not begin Phase 4 until the subagent returns `VERIFIED_PASS`.

---

## 7. Phase 4 — Stage 4: Target Camera (per the 10-25 camera ruling)

- **4-C (primary demo path, dataset replay):** no new experiments. Deliver: one demo session on the replay path (replay frames -> full RiskUpdate chain) with traceable session records. **Report guard:** any hit-rate/RiskLevel numbers from demo replay must NOT appear as Chapter-6 evaluation results.
- **4-B (side camera):** user-informal only. No labels, no subject split, no evaluation evidence, no Chapter-6 numbers. Frontal-camera limited recognition stays a measured limitation (evidence: `docs/evidence/2026-10-22/vision-runtime-path/README.md`).
- Deliverable: a short dated note recording which path the demo used and that no replay numbers were promoted into evaluation claims.
- [ ] **Stage-4 audit:** the report-guard checks (demo used replay path; no replay numbers quoted as Ch-6 evaluation) go through the same phase-gate audit subagent (section 15) together with the Stage-3 dispatch or separately.

---

## 8. Phase 5 — Stage 5: Release Decision (the USER decides)

- [ ] **Step 1 — Rollback drill (agent-executed, subagent-audited).** With candidates installed, set active vision back to stable (unset `DRA_ACTIVE_VISION`), start on port 8001, assert hash check + warm-up forward OK, exit 0. Save the drill log. This proves rollback works without retraining or touching stable artifacts (R3: versioned release, never overwrite stable products). The drill log is verified by the phase-gate audit subagent (section 15).
- [ ] **Step 2 — Decision record template.** Produce `docs/fyp2/task10a/release_decision.md` with fields: chosen Active model, reasons, cited Stage-2/3 same-day evidence paths, date, **user's signature line** (the user fills this). Include the rollback switch instructions.
- [ ] **Step 3 — Do NOT auto-activate ResNet18.** The active model changes only when the user records the decision.

---

## 9. Gates and Verdicts (mapped to the stages)

| Gate | Definition | Satisfied by |
|---|---|---|
| A — Model Artifact & Provider | manifests validate, artifacts load, real provider forward executes, class mapping correct, outputs valid | Phase 1 Tasks 1.1–1.3 |
| B — Stable200 | official deterministic provider test actually executed with pre-declared checks evaluated | Phase 1 Task 1.4 |
| C — Integration Regression | candidate support breaks nothing: stable provider, fusion, unavailable guards, EMA/FSM, API, logging/export, frontend | Phase 1 Task 1.3 Step 5 + Phase 3 Step 2 |
| D — Runtime Failure Handling | missing/corrupted model, invalid manifest/hash, bad input, load/forward failure, candidate->stable recovery, failure provenance | Tasks 1.2–1.3 tests + Phase 5 rollback drill |
| E — Evaluation Evidence | reproducible test + comparison evidence with IDs, preconditions, results, environment, model identities/hashes | Phases 1–3 evidence dirs |

Per-phase and per-gate verdicts use exactly: `VERIFIED_PASS` / `PARTIAL` / `BLOCKED` / `FAILED`, with the supporting gates and remaining limitations stated. A stage is not `VERIFIED_PASS` if any red line in section 1 was violated, even if all tests are green.

---

## 10. Final Deliverables (from the merged brief)

**A. Implementation Summary** — exact changed files, affected functions/classes, model-loading workflow, compatibility decisions.
**B. Verification Matrix** — per gate: expected behaviour, actual result, evidence path, PASS/FAIL/BLOCKED.
**C. Candidate Comparison** — separate offline research evidence / provider compatibility / model-only latency / system-level runtime evidence; never equate Macro-F1 with safer driving.
**D. Final Task 10A Verdict** — `VERIFIED_PASS`/`PARTIAL`/`BLOCKED`/`FAILED` + which gates support it + remaining limitations.
**E. Stable Runtime Status** — stable system still operational, candidates available for explicit evaluation, whether any active-model change was made (default: none).
**F. FYP2 Report Evidence Map** — table `Rubric Criterion | Report Section | Implemented Feature | Test Evidence | Figure/Table Recommendation | Evidence Status`; real paths and actual records only; no invented screenshots, measurements, UAT responses or results.
**G. Report-Ready Technical Notes** — concise English notes for: Candidate Model Integration Design; ONNX Runtime Provider Implementation; Compatibility and Regression Testing; Model Integration Limitations. Mark completed vs planned work explicitly.

---

## 11. Test Matrix (expected result / evidence artifact / acceptance criteria)

| Test | Expected | Evidence artifact | Acceptance |
|---|---|---|---|
| manifest valid (both real packages, system CLI) | valid, exit 0 | Phase 0 Step 3 stdout/stderr | Stage-1 audit point 2 |
| tampered hash rejected | `ModelUnavailable`, stable untouched | `test_tampered_hash_rejected` green (same-day) | red/green pair saved |
| schema violation rejected | `ModelUnavailable` | `test_bad_schema_rejected` | red/green pair saved |
| c0–c9 order enforced | non-identity class_to_idx rejected | `test_class_order_enforced` | red/green pair saved |
| real forward (RN, MN candidate, stable) | (1,10) finite logits; probs sum 1; `P_distraction=1-p0` | warm-up asserts + stable200 runs | Gate A/B |
| default = stable MN | startup sha256 = stable ONNX | Phase 1 Task 1.5 Step 1 log | Stage-1 audit point 5 |
| candidate switch + rollback | RN loads; stable restores, hashes verified | Task 1.3 Step 4 log | Stage-1 audit point 2 + Stage 5 rollback drill |
| XGB untouched | diff hunks vision-only | `git diff 2745348 -- trained.py` | Stage-1 audit point 6 |
| stable200 (3 identities) | argmax agreement 1.0; max prob delta ≤ declared tolerance | `official_stable200_behavior.json` | Gate B; no tolerance loosening without user |
| comparison isolation | per-model fresh state/DB | protocol + results JSON | Stage-2 audit point 3 |
| P4-consistency of comparison | c9 weak-class signal visible | results JSON cross-check | Stage-2 audit point 4 |
| latency MN vs RN | RN capture->render p95 measured | dated perf JSONs | Stage-3 audit point 2 (no extrapolation) |
| full regression | pytest 1028+ / vitest 922 / tsc / eslint / build exit 0 | same-day logs | Stage-3 audit point 2 |
| log completeness under RN | 211/211, 1 fault, 0 duplicates | perf02-style run | Stage-3 audit point 4 |
| failure paths | missing model / bad input / forward error -> 503/500 with provenance, no silent fallback | Gate D tests | Stage-1 deliverable 4 |

---

## 12. Model Integration Risk Assessment

- **Class mapping:** c0's training name is `normal_driving`, runtime alias `safe_driving`; candidates must build the same 10-label alias list from `class_metadata.json`. A wrong alias only relabels the UI, but a wrong index silently breaks `P_distraction = 1 - P(c0)` — hence the explicit order tests and stable200 argmax check.
- **Preprocessing:** candidates' export contract is direct bilinear resize-224 / ImageNet norm — the SAME `TrainedProvider.preprocess`. Do not substitute torchvision default transforms (Resize-256 + CenterCrop) for ResNet18; the manifest `preprocess` const and loader assertion pin this.
- **Probability:** ONNX outputs are logits; softmax must be applied exactly once (the provider already does). The saved predictions to compare against are probabilities — compare post-softmax values only.
- **Latency:** RN model-only p95 ≈ 25.4 ms vs MN ≈ 7.2 ms; capture->render with RN is expected near 57 ms but must be measured. Fusion, DB and UI remain unchanged — any regression would come from the vision path alone.
- **State management:** EMA/FSM sessions are per-session server state; comparisons must use fresh state per model run or one run leaks into the next (protocol requirement). R10 source-time rules and ruling-A expiry must behave identically for every active model.
- **Rollback:** env-based switch with stable as default; no artifact overwrites; rollback drill executed as evidence. Never "temporarily" point the stable path at a candidate.
- **Provenance/logging:** every window must carry the actual `vision_model_id` and sha256 of the model that produced it, so historical records remain interpretable after switching models.
- **Failure handling:** a missing/tampered candidate must produce `ModelUnavailable` (503 `models_unavailable`) — never a silent stable fallback that mislabels candidate inference as successful.

---

## 13. FYP2 Report Evidence Map (UM WIA3003/WIB3003 Academic Project II)

Rubric anchor: Chapters 4, 5, 6 carry 8 marks each.

| Rubric criterion | Report section | Supporting implementation | Test evidence | Status |
|---|---|---|---|---|
| Functional/non-functional requirements; architecture | Ch 4 | provider interfaces, manifest contract v1, switch/rollback design | `runtime_manifest.schema.json`, `vision_candidates.py`, Stage-1 audit | New in Task 10A |
| Model switching & rollback design (+ diagram) | Ch 4 | `active_vision` switch, rollback drill | Task 1.3 Step 4, Phase 5 Step 1 logs | New in Task 10A |
| Technical implementation of modules | Ch 5 | manifest loader, ORT provider, integration with completed backend/frontend/fusion/FSM | unit + integration tests | Existing Tasks 1–10 + new Task 10A |
| ONNX Runtime & manifest validation | Ch 5 | `validate_manifest`/`validate_package`, loader graph/warm-up checks | `test_runtime_manifest.py` (existing), `test_vision_candidates.py` | Existing + new |
| Unit/integration/system tests | Ch 6 | test matrix (section 11) | same-day pytest/vitest logs | Partially existing, extended |
| Error handling & recovery | Ch 6 | Gate D failure paths + rollback | Gate D tests, rollback drill log | New |
| UAT | Ch 6 | user-executable UAT protocol + evidence template (pending) | none yet | **Pending — do not claim UAT** |
| Candidate comparison & runtime | Ch 6 | stable200, paired comparison, latency | Phases 1–3 evidence | New |

Do not fold the demo-replay numbers into Ch 6 evaluation claims (Phase 4 guard). E2–E5 remain separate system-track items; Task 10A does not replace them.

---

## 14. Execution Restrictions and Stop Conditions

- Work only within Task 10A and the smallest necessary integration changes. Tasks 1–10 are complete; do not reopen them.
- Never edit the ML worktree (`/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1`); read only.
- Never overwrite stable checkpoints or frozen ML evidence; never modify frozen selection logs or P4/P5 results.
- No retraining, HPO, extra export, benchmark expansion or new experiments beyond this plan.
- Do not alter the telemetry research candidate's runtime status (no XGB importer).
- No commit of model files; no push; no reset/clean/delete of unrelated files; preserve dirty state.
- Do not run anything against the user's port-8000 backend or the real `driver_risk.db`; use port 8001 + temp DBs.
- Every completion claim carries same-day command output (exit code + key lines).
- Stop and report `BLOCKED` with exact missing dependencies if any required artifact is unreachable. Never fabricate.
- After Phase 1 (Stage 1), Phase 2 (Stage 2), Phase 3 (Stage 3) and Phase 4 (Stage 4 report guards): STOP, fill the stage's audit table, and dispatch the **phase-gate audit subagent** (section 15). Continue to the next phase only on the subagent's `VERIFIED_PASS`. The user spot-checks the subagent reports, holds D1–D5 overrides and any red-line judgment call (e.g., tolerance loosening), and alone makes the Stage-5 release decision.

Finish with the Task 10A verdict (section 10-D) and a separate final-release recommendation. Do not automatically activate ResNet18 as the default model.

---

## 15. Phase-Gate Audit Protocol (subagent-based)

Every phase ends with an **independent audit by a fresh, read-only subagent** — never by the implementing session, and never skipped. The implementing session prepares the inputs and dispatch; the subagent produces the verdict.

### What the implementing session prepares before dispatching

1. The stage's filled audit table: one row per audit point of the corresponding Stage N table in `docs/fyp2/11_SYSTEM_INTEGRATION_STAGE_PLAN_AND_AUDIT.md`, each row citing an evidence path + the claimed exit code.
2. The stage's evidence directory path (must exist and be dated the run day).
3. The current git HEAD and the implementer's commit list for the phase.

### Reusable auditor subagent prompt (fill `N`, `STAGE-NAME`, `PHASE-SECTION`, `EVIDENCE-DIR`, `COMMITS` and attach the implementer's audit table)

```markdown
# Phase-Gate Audit — FYP2 Task 10A, Stage N (STAGE-NAME)

You are an INDEPENDENT READ-ONLY auditor subagent. You did NOT implement this work; do not
trust any summary written by the implementing session.

## Inputs (all read-only)
- Plan: /Users/liu/Desktop/FYP2-Live-System/docs/plans/2026-10-25-task-10a-candidate-integration.md
  (read PHASE-SECTION and the red lines in section 1)
- User checklist: /Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/docs/fyp2/11_SYSTEM_INTEGRATION_STAGE_PLAN_AND_AUDIT.md
  (read the Stage N table and the red lines in section 0.5)
- Implementer's self-audit table (attached) and evidence dir EVIDENCE-DIR
- Implementer's commits for this phase: COMMITS

## Rules
1. READ-ONLY: never edit, stage, commit, reset, clean or delete anything in either worktree.
   If a command you run needs a writable working area, use an isolated copy under /tmp.
2. Never touch the user's backend on port 8000 or the real driver_risk.db. Any server you
   need runs on port 8001 with a temporary database.
3. For EVERY audit point in the Stage N table: open the cited evidence file yourself, confirm
   it exists and its freshness matches the claimed run day, then RERUN the key verification
   command yourself (e.g. the manifest validator, a focused pytest file, `git diff 2745348 --
   backend/app/providers/trained.py`). The exit code you record must come from YOUR run today,
   not from an old log.
4. Check the checklist's section 0.5 red lines and the plan's section 1 constraints one by one
   (no training/HPO/export, RF/LR never loaded, XGB load path unchanged, no SQLite swap, no
   silent fallback, no model overwrites, no push, same-day evidence only).
5. Cross-check the plan's phase section against what was actually committed; flag any scope
   creep (e.g. touched files outside the phase's file list).
6. Anything that needs human judgment (e.g. relaxing a declared tolerance, overriding D1-D5)
   must be reported as FOR_USER_DECISION — never decided by you.

## Output (exact structure)
1. Verdict table: audit point | implementer claim | your verification (file opened / command
   rerun + your exit code) | PASS / FAIL / BLOCKED
2. Red-line checklist: one line each, PASS or VIOLATION with evidence.
3. Scope-creep findings (if any).
4. FOR_USER_DECISION items (if any).
5. Final Stage N verdict — exactly one of: VERIFIED_PASS / PARTIAL / BLOCKED / FAILED —
   plus open findings. Do not continue to any next phase and do not modify the plan.
```

### Gate rule

- The next phase starts **only** on `VERIFIED_PASS`.
- On `PARTIAL` / `BLOCKED` / `FAILED`: the implementing session fixes the findings in a new task-scoped commit, re-runs the same-day gates, and dispatches a **fresh** audit subagent again. The user is informed with the subagent's report; the user may also resolve `FOR_USER_DECISION` items at any point.
- After the final phase, attach all subagent reports to deliverable B (Verification Matrix).
