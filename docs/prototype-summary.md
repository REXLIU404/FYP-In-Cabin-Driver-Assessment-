# FYP MVP Prototype Summary

## Source Understanding

The updated FYP report, final consolidated guidebook, and MVP prototype guidebook describe a frontend-only FYP1 MVP for in-cabin driver risk monitoring. The MVP combines two modality-level outputs:

- `P_distraction` from a driver-facing visual branch.
- `P_telemetry_anomaly` from a structured telemetry branch.

The core decision is weighted late fusion:

```text
RiskScore = (w_v * P_distraction + w_t * P_telemetry_anomaly) * 100
```

The prototype displays the fused score on a 0-100 scale, maps it into `Low`, `Medium`, and `High` risk levels using 30/60 thresholds, generates `DominantEvidence`, maps that to `AlertSeverity`, and stores timestamped records in `localStorage` for CRUD demonstration, trend review, inspection, and export.

## Completed Core Modules

1. Risk Logic Engine: [riskLogic.ts](/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/ai/src/riskLogic.ts)
   - `computeRiskScore()`, `mapRiskLevel()`, `mapAlertSeverity()`, `mapSystemHealth()`, `determineDominantEvidence()`, and `buildRiskUpdate()`.

2. Prepared Session Adapter: [preparedSessionInput.ts](/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/frontend/src/data/preparedSessionInput.ts)
   - Parses `ai/prototype-data/prepared_sessions/session_001/telemetry.csv`, constructs ordered monitoring windows, and supplies deterministic prototype inference outputs for the runtime contract.

3. Monitoring Session Engine: [App.tsx](/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/frontend/src/App.tsx)
   - Reads prepared session windows in timestamp order and advances them through `setInterval` using `deltaT`.

4. Camera Preview Module: [useCameraPreview.ts](/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/frontend/src/hooks/useCameraPreview.ts)
   - Uses `getUserMedia`, handles idle/requesting/live/denied/error, and releases tracks on stop.

5. Local Persistence Layer: [persistence.ts](/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/frontend/src/utils/persistence.ts)
   - Implements Create, Read, Update, and Delete with `localStorage`.

6. Five-Interface Dashboard: [App.tsx](/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/frontend/src/App.tsx)
   - Live Monitor, Signal Inspector, Risk Trends, Explanation, and Configuration.

7. Export Module: [export.ts](/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/frontend/src/utils/export.ts)
   - Exports session logs as JSON and CSV, with `Enable Evidence Interpretation` controlling whether evidence fields are included.

## How To Use

1. Install dependencies:

```bash
npm install
```

2. Run the prototype:

```bash
npm run dev
```

3. Open the printed local URL. The Vite script binds to `127.0.0.1`.

4. In the dashboard:
   - Use `Start Monitoring` to run prepared session windows automatically.
   - Use `Start Camera` in Live Monitor to request browser camera preview.
   - Use Signal Inspector to select and flag a window.
   - Use Risk Trends to inspect line charts, threshold lines, distribution, and recent records.
   - Use Configuration to change runtime settings, restart the session, enable evidence interpretation, and export JSON/CSV.

## Scope Boundary

This implementation is a frontend-first FYP1 MVP. Camera preview demonstrates the visual input interface, while risk values come from the prepared session dataset under `ai/prototype-data/prepared_sessions/session_001`. The `backend/` layer is currently an integration boundary, not a running service. The prototype does not include video upload, AI training, real MobileNetV3/XGBoost inference, FastAPI, WebSocket, SQLite, or vehicle-grade deployment.

## Export Schema

When `Enable Evidence Interpretation` is enabled, JSON and CSV exports include `window_id`, `risk_score`, `risk_level`, `p_distraction`, `p_telemetry_anomaly`, `dominant_evidence`, `top_visual_class`, `top_telemetry_cue`, and `latency_ms`.

When it is disabled, exports include only `window_id`, `risk_score`, and `risk_level`.
