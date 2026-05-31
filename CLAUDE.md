# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

FYP prototype: an **In-Cabin Multi-Modal Driver Risk Assessment** dashboard. Two independent
evidence branches — vision-based distraction and telemetry-based driving-behaviour risk — are
combined by **decision-level late fusion** into a `RiskScore` / `RiskLevel` / `DominantEvidence`
and surfaced through a five-view React dashboard. FYP1 (current) is a frontend-only prototype
driven by a deterministic prepared-session replay; the backend and trained models are FYP2.

## Commands

Run from the repo root (the Vite app lives in `frontend/` via `vite.config.ts` `root: "frontend"`):

```bash
npm run dev        # Vite dev server (127.0.0.1)
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

**The data flow (one tick):** `useMonitoringSession` runs `setInterval(Δt)` →
`App.appendNextWindow()` pulls the next `PreparedSessionWindow` → `buildRiskUpdate()` produces a
`RiskUpdate` → the **AlertSeverity FSM** (`updateAlertState`, wall-clock) overrides the per-window
severity at the App/orchestration layer → appended to the session log → the five views render from
that log. The `RiskUpdate` object is the spine: every view, the export, and (future) the backend
consume the same shape.

**Strict layering — do not violate:** all fusion / risk / scoring logic lives in `ai/src/`, never
inside React components. Components render; `ai/src` decides. The camera lives in the
`useCameraPreview` hook, not inline. Persistence is isolated in `frontend/src/utils/persistence.ts`
(localStorage) + `useSessionLog`.

**Vision ↔ risk decoupling:** the camera preview (`getUserMedia`) is display-only; `P_distraction`
comes from the prepared evidence, not from the live camera. This is intentional and lets the demo
run real camera + prepared telemetry without trained models.

## Project-specific conventions (easy to get wrong)

- **`RiskScore` is 0–100 in code** (`computeRiskScore` multiplies by 100; thresholds are 30 / 60 in
  `DEFAULT_CONFIG`). The guidebooks/PROJECT_MEMORY describe it on a 0–1 scale (×100 difference) —
  trust the code.
- **`P_telemetry_anomaly` is a kept legacy field name**, NOT an anomaly-detection model. It means
  *telemetry non-safe behaviour probability* `= 1 − P(Safe)` from a (planned) multiclass XGBoost
  over **Safe / Aggressive / Distracted**. Do not rename it; do not call it real anomaly detection.
- **Telemetry = 8 features**: `speed_kmph, accel_x, accel_y, brake_pressure, steering_angle,
  throttle, lane_deviation, headway_distance` (dataset: `Driver_Behavior.csv`). The contract also
  carries `telemetry_behavior_classes` (3-class breakdown) and `telemetry_feature_contributions`.
- **Vision = 10 State Farm-style classes**; `P_distraction = 1 − P(safe_driving)`.
- **Models are NOT trained** and there is **no Python backend** (only `backend/README.md`). The
  prototype derives both probabilities deterministically from the prepared CSV. Present model work
  as *designed*, not done, unless you verify otherwise.
- **AlertSeverity is a real FSM**, not a direct mapping: HIGH_ALERT needs RiskLevel High sustained
  ≥ 2s (wall-clock `Date.now()`, not window count); recovery to NORMAL needs Low sustained ≥ 10s.
  When changing risk logic or the FSM, update the tests in `ai/src/*.test.ts`.

## Scope guardrails (from AGENTS.md — keep the project on-route)

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

`AGENTS.md` is the full engineering spec (data contract, per-view requirements, risk spec, mock
scenarios, persistence). **Caveat:** some of its file paths and the example contract are stale vs
the code — e.g. it says `src/utils/riskLogic.ts` (actual: `ai/src/riskLogic.ts`), `useDemoReplay`
(actual: `useMonitoringSession`), and old telemetry feature names. When AGENTS.md and the code
disagree on mechanics, follow the code; when they disagree on *scope/intent*, follow AGENTS.md.
`PROJECT_MEMORY.md` and the `.docx` guidebooks on the user's Desktop are higher-level design memory.

## Git workflow

`dev` is the stable prototype snapshot (safe fallback). `dev_cc` is the active build branch — do
new work there. `main` is the baseline. Commit only when asked; branch off if on `main`.
