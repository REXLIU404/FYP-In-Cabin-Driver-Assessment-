# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## FYP2 handoff: read before continuing development

Read [FYP2 Claude development handbook](docs/FYP2_CLAUDE_DEVELOPMENT_HANDBOOK.zh.md),
then [current implementation status](docs/IMPLEMENTATION_PROGRESS.zh.md) and
[runtime guide](docs/LIVE_RUNTIME_GUIDE.zh.md). The handbook contains the phased
workflow, code ownership, validation steps, remaining work and handoff checklist.
Use current files and dated test evidence to verify old chat claims before acting.
Private historical exports under `.local/claude-recovery/` are reference data,
not project instructions. Do not commit manifests, download tokens or chat archives.

## What this is

FYP prototype: an **In-Cabin Multi-Modal Driver Risk Assessment** dashboard. Two independent
evidence branches — vision-based distraction and telemetry-based driving-behaviour risk — are
combined by **decision-level late fusion** into a `RiskScore` / `RiskLevel` / `DominantEvidence`
and surfaced through a five-view React dashboard. Current live mode uses trained MobileNetV3 ONNX + XGBoost through FastAPI and SQLite.
Only camera is a live sensor; telemetry uses prepared raw-feature replay. The earlier
frontend-only prepared-probability demo remains a separate mode. See
`docs/IMPLEMENTATION_PROGRESS.zh.md` and `docs/LIVE_RUNTIME_GUIDE.zh.md` for current evidence.

## Commands

Run from the repo root (the Vite app lives in `frontend/` via `vite.config.ts` `root: "frontend"`):

```bash
npm run dev        # Vite dev server only (127.0.0.1); /api needs a backend on 8000
npm run dev:all    # backend on 8000 (reused if already up) + Vite; one Ctrl-C stops both
npm run build      # tsc -b && vite build  → outputs to ../dist
npm run preview    # serve the production build
npm test           # vitest run (uses vitest.config.ts, NOT the frontend vite root)
npm run linc       # eslint .   (note: the script is "linc", not "lint")
npm run prettier   # prettier --write .
npx tsc --noEmit   # typecheck only
```

Run a single test file / test:

```bash
npx vitest run ai/src/alertFsm.test.ts
npx vitest run -t "escalates to HIGH_ALERT"
```

Tests live in `ai/src/**/*.test.ts`. `vitest.config.ts` sets `root: "."` and the include glob —
without it, vitest would inherit `vite.config.ts`'s `frontend` root and find no tests.

Backend (run from repository root, runtime dependencies in `backend/requirements-inference.txt`):

```bash
.venv/bin/python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
PYTHONPATH=backend .venv/bin/python -m pytest backend/tests -q
```

## Architecture (the parts that need multiple files to understand)

**Two-package monorepo, single root `package.json`:**
- `ai/src/` — the **shared, framework-agnostic risk-logic layer** (pure TypeScript). This is the
  "Core AI Inference Layer". Contains `riskLogic.ts` (`computeRiskScore`, `mapRiskLevel`,
  `buildRiskUpdate`, EMA smoothing), `evidence.ts` (dominant-evidence decision tree),
  `alertFsm.ts` (Alert State Manager FSM), and `types.ts` (the canonical `RiskUpdate` contract).
- `frontend/src/` — the React dashboard. `frontend/src/types.ts` re-exports the `ai/src` types so
  there is **one source of truth** for the data contract across UI and logic.
- `ai/prototype-data/prepared_sessions/session_001/` — the deterministic replay input
  (`telemetry.csv` + frames). Loaded at build time via Vite `?raw` imports in
  `frontend/src/data/preparedSessionInput.ts` — no runtime filesystem access.

**Live data flow:** `useLiveSession` captures the newest JPEG and prepared raw telemetry,
then calls `/infer`. `TrainedProvider` computes probabilities; Python performs EMA/fusion/FSM,
saves temporal state and evidence in SQLite, and returns the shared `RiskUpdate`.
Do not apply frontend EMA/FSM a second time to live results. Model load failures do not
fall back to prepared probabilities. The browser keeps at most one request in flight.

**Demo flow:** `useMonitoringSession` ticks the prepared probability inputs through
`ai/src` logic and localStorage. Keep the interval independent of callback identity so
unrelated UI refreshes do not continually reset the timer.

**Layering:** components render, hooks manage capture/acquisition, Python decides live
risk, and `ai/src` provides shared types plus demo/reference logic. Camera capture lives
in `useCameraPreview`; API access in `frontend/src/api`; demo persistence in `utils/persistence`.

## Project-specific conventions (easy to get wrong)

- **`RiskScore` is 0–100 in code** (`computeRiskScore` multiplies by 100; thresholds are 30 / 60 in
  `DEFAULT_CONFIG`). The guidebooks/PROJECT_MEMORY describe it on a 0–1 scale (×100 difference) —
  trust the code.
- **`P_telemetry_anomaly` is a kept legacy field name**, NOT an anomaly-detection model. It means
  *telemetry non-safe behaviour probability* `= 1 − P(Safe)` from the trained multiclass XGBoost
  over **Safe / Aggressive / Distracted**. Do not rename it; do not call it real anomaly detection.
- **Telemetry = 8 features**: `speed_kmph, accel_x, accel_y, brake_pressure, steering_angle,
  throttle, lane_deviation, headway_distance` (dataset: `Driver_Behavior.csv`). The contract also
  carries `telemetry_behavior_classes` (3-class breakdown) and `telemetry_feature_contributions`.
- **Vision = 10 State Farm-style classes**; `P_distraction = 1 − P(safe_driving)`.
- **Existing trained models are integrated.** Runtime reads MobileNetV3 ONNX and XGBoost
  under `ml/outputs`, validates metadata and records hashes. Never claim frontal accuracy
  or edge performance from the source-dataset tests. Additional model experiments are
  paused at the user's request; do not download or use alternate models without new direction.
- **Backend is integrated:** live sessions, raw input inference, persisted EMA/FSM,
  idempotency, database-authoritative latest, history/flags/exports and additive migration.
  Prepared probability inputs are restricted to prepared sessions. Preserve SQLite and
  existing records; do not recreate databases to fix migration errors.
- **AlertSeverity is a real FSM**, not a direct mapping: HIGH_ALERT needs RiskLevel High sustained
  ≥ 2s; recovery to NORMAL needs Low sustained ≥ 10s. The replay path (`ai/src/alertFsm.ts`, and the
  backend's PREPARED mode) times this on the wall clock. **Live (R10, user-approved 2026-10-16)**
  additionally requires source-time progress: the streak's span of NEW, same-direction observations
  (first window span 0) must also reach 2 s / 10 s, repeats never advance it, and the modality that last
  advanced it must still support the level when the transition fires. Ages use the canonical (first-seen)
  acquisition time. When changing risk logic or the FSM, update the tests in `ai/src/*.test.ts` and
  `backend/tests/`.
- **Evidence expiry — ruling A (user-confirmed 2026-10-13; implemented in P0-D13, 2026-10-15)**:
  evidence older than `freshness_tolerance_s` scores as **missing** (factor 0) while provenance
  keeps `{modality}_expired` / `{modality}_age_s`; the runtime stops producing `stale`, and 0.45
  survives only for reading and rendering historical stale records. 3 s is a configurable
  **design threshold** (default 3 s, per session in (0, 30]) — never call it a validated safety
  threshold. Expiry alone does not stop repeated evidence advancing the alert timers; that is
  R10 (approved 2026-10-16, see the FSM bullet).

## Scope guardrails (keep the project on-route)

- Exactly two risk dimensions; **decision-level late fusion only** (never early/feature fusion).
- Fusion weights (`w_v`, `w_t`, default 0.5/0.5, sum = 1) are **transparent design parameters**,
  not learned safety weights. `RiskLevel` is a derived operational level, **not** supervised
  accident severity.
- Do NOT claim vehicle-grade deployment, driver-side alerting/CAN-bus control, face/identity/
  biometric features, or medical diagnosis.
- Database is **SQLite** (FYP2) — do not swap for MySQL/Postgres in scope. Do not reintroduce
  Flask-SocketIO, APScheduler, Hydra, or OmegaConf.
- Deprecated old route (ignore unless explicitly asked): AffectiveROAD, Empatica E4, Zephyr
  BioHarness, physiological/wearable fatigue or workload/stress fusion.

## Source of truth & docs

This file (`CLAUDE.md`) contains the applicable project instructions. Check current files rather than
assuming an older copied spec is still present. Current runtime status and startup instructions
are in `docs/IMPLEMENTATION_PROGRESS.zh.md` and `docs/LIVE_RUNTIME_GUIDE.zh.md`.
`PROJECT_MEMORY.md` and the `.docx` guidebooks on the user's Desktop are higher-level design memory.

## Git workflow

`dev` is the stable prototype snapshot (safe fallback). `dev_cc` is the active build branch — do
new work there. `main` is the baseline. Commit only when asked; branch off if on `main`.
