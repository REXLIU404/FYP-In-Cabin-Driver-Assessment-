# In-Cabin Multi-Modal Driver Monitoring & Risk Assessment

React/TypeScript + FastAPI/SQLite research prototype with **live camera inference
using the existing trained MobileNetV3-Large ONNX model** and **prepared telemetry
replay through the trained XGBoost model**. Only the camera is a live sensor.

The backend owns EMA, freshness-aware late fusion, sustained alerts, session
state and persistence. The five dashboard views consume those saved results.

## Scope: Live is the system

- **Live is the only primary runtime.** Camera frames and the prepared raw
  telemetry (8 features per row, no probabilities) go to
  `POST /api/sessions/{id}/infer`; the trained MobileNetV3 and XGBoost produce the
  probabilities, and the backend fuses, smooths, alerts and saves them. The Live
  code reads only the prepared _raw telemetry_ (`PREPARED_RAW_TELEMETRY`).
- **The prepared-probability replay is kept, as legacy / test-only.** It is listed
  in the Data mode menu as "Prepared replay (legacy, test-only)", uses no trained
  model and no backend, and exists for regression tests and backward compatibility.
  Nothing was removed. It is entered only by choosing it in the page; every reload
  starts on Live again.
- **What is not claimed.** Frontal-camera accuracy, edge-hardware performance and
  field validation are not established. The 3 s evidence-age limit is a design
  threshold, not a validated safety threshold. `RiskLevel` is a derived operating
  level, not an accident-severity label.

## Run the complete system

From the repository root, using the existing environment and local trained
artifacts in `ml/outputs/` (no alternate model download required):

```bash
# Install only if dependencies are missing:
.venv/bin/python -m pip install -r backend/requirements-inference.txt
npm ci

# Build and serve UI + API on one localhost origin:
npm run build
.venv/bin/python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000, select **Live trained models**, click **Start
Monitoring**, and allow camera access. For development, run the same backend on
8000 and `npm run dev` separately; Vite proxies `/api` to it.

- [Runtime guide, inputs and limitations (中文)](docs/LIVE_RUNTIME_GUIDE.zh.md)
- [Completed work, verified tests and next steps (中文)](docs/IMPLEMENTATION_PROGRESS.zh.md)
- [Initial audit and accuracy/edge experiment plan (中文)](docs/PROJECT_ASSESSMENT_AND_TEST_PLAN.zh.md)
- [Backend API and persistence](backend/README.md)
- [Browser/frontend evidence](docs/evidence/2026-10-05/) and [final backend/HTTP evidence](docs/evidence/2026-10-09/)

The default target is 10 inference requests/second with one request in flight;
camera capture requests 30 FPS. Neither setting guarantees achieved throughput.
Frontal-camera accuracy and target edge hardware remain to be measured. Existing
source-dataset results are not field validation. Additional model experiments
are paused at the user's request.

## Repository

```text
frontend/       React views, camera capture, API client, Live controller (+ retained legacy replay)
backend/        FastAPI, trained ONNX/XGBoost provider, fusion/FSM, SQLite, exports
ai/             Shared TypeScript contract and demo/reference risk logic
ml/             Training notebooks, existing artifacts, reproducible experiments
docs/           Runtime guide, progress, initial assessment and measured evidence
prototype-tests/ Manual Live end-to-end acceptance checklist
```

## Checks

```bash
npm test
npm run linc
npm run build
PYTHONPATH=backend .venv/bin/python -m pytest backend/tests -q
```

The full backend suite uses the local trained artifacts. The preprocessing parity
check additionally needs the existing training environment's torch/torchvision;
those libraries are not required for online serving. Browser evidence uses a
simulated camera with real model execution and a separate temporary database.

The screenshots below show the earlier prepared-demo layout; current runtime
screenshots are in [output/playwright](output/playwright/).

## Interface Screenshots

### Live Monitor

Displays the current monitoring window, fused risk score, branch probabilities,
alert status, system health, latency, and recent trend.

![Live Monitor](docs/ui-screenshots/live-monitor.png)

### Signal Inspector

Supports window-level review of historical monitoring records, including visual
evidence, telemetry features, freshness, latency, and flag status.

![Signal Inspector](docs/ui-screenshots/signal-inspector.png)

### Risk Trends

Shows session-level risk progression, branch probability traces, risk-level
distribution, and historical records.

![Risk Trends](docs/ui-screenshots/risk-trends.png)

### Explanation

Explains the current risk output using matched evidence rules, branch evidence,
and weighted contribution breakdown.

![Explanation](docs/ui-screenshots/explanation.png)

### Configuration

Provides runtime controls for monitoring, fusion weights, risk thresholds,
evidence interpretation export, and JSON/CSV session log export.

![Configuration](docs/ui-screenshots/configuration.png)
