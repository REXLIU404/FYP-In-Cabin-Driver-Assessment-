# AGENTS.md

# Coding Agent Instructions — Driver Risk Assessment Project

This repository implements an FYP proof-of-concept:

> **Late-Fusion Multi-Modal Driver Risk Assessment Framework Using Vision-Based Distraction Detection and Telemetry-Based Anomaly Detection**

Read this file before modifying the project. Also read `PROJECT_MEMORY.md` before making architectural or wording decisions.

---

## 1. Project Context

The current project is **not** the old wearable / physiological-signal route.

The current implementation direction is:

```text
driver-facing visual input
→ vision branch
→ P_distraction

structured telemetry input
→ telemetry branch
→ P_telemetry_anomaly

P_distraction + P_telemetry_anomaly
→ decision-level late fusion
→ RiskScore + RiskLevel + DominantEvidence
→ dashboard + session log + export
```

The system is a **real-time-ready proof-of-concept**, not a certified vehicle-grade product.

---

## 2. Source of Truth

Use this priority order when project documents conflict:

1. `PROJECT_MEMORY.md`
2. `Final_Consolidated_Guidebook_v2.docx` (authoritative engineering spec)
3. `MVP_Prototype_Guidebook_v2.docx` (FYP1 deliverable scope)
4. Current codebase
5. Older report drafts or previous experimental notes

If older files mention AffectiveROAD, Empatica E4, Zephyr BioHarness, physiological fatigue
detection, workload/stress states, or feature-level wearable fusion, treat those as
**deprecated unless the user explicitly asks about the old route**.

---

## 3. Non-Negotiable Scope Rules

### Must do

- Keep the project focused on exactly two operational risk dimensions:
  - vision-based distraction-related risk
  - telemetry-based anomaly risk
- Use decision-level late fusion only.
- Keep branch outputs explicit:
  - `P_distraction`
  - `P_telemetry_anomaly`
- Keep risk output explicit:
  - `RiskScore`
  - `RiskLevel`
  - `DominantEvidence`
  - `AlertSeverity`
  - `SystemHealth`
- Preserve modular separation between frontend, backend, AI inference, and storage.
- Implement mock providers first when real models are not ready.
- Prefer deterministic demo scenarios for prototype testing.
- Add or update tests when changing risk logic.
- Guard `localStorage` writes against the 5 MB browser quota (see §10).

### Must not do

- Do not claim vehicle-grade deployment.
- Do not implement or describe driver-side notification, CAN bus control, SMS, or
  production safety alerting.
- Do not describe `RiskLevel` as supervised accident severity.
- Do not claim early fusion or feature-level multimodal training.
- Do not add face recognition, driver identity, biometric storage, or medical diagnosis
  features.
- Do not reintroduce Flask-SocketIO, APScheduler, Hydra, or OmegaConf unless explicitly
  requested and documented.
- Do not put model inference or fusion logic inside React components.
- Do not replace SQLite with MySQL or PostgreSQL for FYP scope — SQLite is the confirmed
  database choice (see §4 and §10). If a production multi-user upgrade is needed, note it
  in Future Work only.

---

## 4. Intended Tech Stack

### Frontend / MVP

- React 18
- TypeScript
- Vite
- **Recharts** (confirmed — not Chart.js)
- lucide-react for icons
- Browser camera preview via `getUserMedia`
- `localStorage` for MVP session persistence (max 500 records — see §10)
- JSON / CSV export from frontend

### Backend / FYP2

- Python 3.10+
- FastAPI
- Uvicorn (ASGI server)
- Pydantic v2
- Pydantic Settings (replaces Hydra — lighter, type-safe)
- SQLAlchemy 2.x
- **SQLite** (confirmed — zero-config embedded DB, no server process required; upgrade
  path to PostgreSQL via SQLAlchemy connection string change only)
- FastAPI native WebSocket only after REST polling endpoints are stable

### AI / ML

- PyTorch / TorchVision for vision branch
- MobileNetV3 as primary lightweight vision model
- XGBoost as primary telemetry model
- scikit-learn for baselines, metrics, and probability calibration
- SHAP optional for telemetry explanation (FYP2 stretch)
- OpenCV + Pillow for image preprocessing
- NumPy / Pandas for data handling

### Data Analysis & Evaluation

- Jupyter Notebook for EDA and evaluation experiments
- Matplotlib + Seaborn for report figures

---

## 5. Architecture Rules

### Frontend Dashboard Layer

The frontend may:

- render dashboard views
- collect user actions
- show camera preview (via `useCameraPreview` hook — not inline in components)
- run MVP mock replay loop via `useDemoReplay` hook
- call backend endpoints when backend exists
- store MVP session log in `localStorage`
- export JSON / CSV

The frontend must not:

- train models
- own authoritative backend session state once backend exists
- compute production AI inference
- hide fusion logic inside UI components — all risk logic lives in `src/utils/riskLogic.ts`

### Backend Service Layer

The backend may:

- validate requests
- manage sessions
- build inference windows
- call AI providers
- cache latest outputs
- persist records to SQLite
- expose REST endpoints
- expose WebSocket push in FYP2 final / stretch only

The backend must not:

- train models
- contain model internals
- render UI
- directly implement SHAP (belongs to the AI/explanation service layer)

### Core AI Inference Layer

The AI layer may:

- run vision inference
- run telemetry inference
- apply EMA temporal smoothing
- apply freshness-aware fusion
- generate risk interpretation
- generate explanation metadata
- return latency measurements

The AI layer must not:

- own frontend UI state
- own database persistence
- handle API authentication

### Session Store

The store may:

- persist inference records
- persist alert events
- persist error events
- persist settings snapshots
- support JSON / CSV export

The store must not:

- run inference
- decide risk
- render UI

---

## 6. Core Data Contract

Use this shape for `risk_update` unless a task explicitly changes the contract.
**All field names must stay stable across frontend, backend, tests, logs, and exports.**

```json
{
  "type": "risk_update",
  "session_id": "S001",
  "window_id": 128,
  "timestamp": "2026-05-04T16:59:00+08:00",
  "P_distraction": 0.82,
  "P_telemetry_anomaly": 0.46,
  "RiskScore": 0.64,
  "RiskLevel": "High",
  "DominantEvidence": "Vision-dominant",
  "AlertSeverity": "HIGH_ALERT",
  "SystemHealth": "FULL",
  "fusion_mode": "full_multimodal",
  "modality_freshness": {
    "vision": "fresh",
    "telemetry": "fresh"
  },
  "latency_ms": 47,
  "explanation": "High risk is mainly driven by visual distraction evidence.",
  "visual_top_classes": [
    { "label": "phone_use", "probability": 0.61 },
    { "label": "looking_away", "probability": 0.21 },
    { "label": "normal_driving", "probability": 0.18 }
  ],
  "telemetry_features": {
    "speed": 95,
    "acceleration": 2.8,
    "steering_angle": 14.2,
    "brake_usage": 0.78,
    "lane_deviation": 0.62,
    "road_type": "highway",
    "traffic_condition": "moderate"
  }
}
```

---

## 7. Risk Logic Specification

### Default Fusion

```text
RiskScore = w_v × P_distraction + w_t × P_telemetry_anomaly

Default: w_v = 0.5, w_t = 0.5
Constraint: w_v + w_t = 1.0 (enforced by Configuration slider)
```

Weights are **transparent design parameters**, not learned safety-critical weights.

### Risk-Level Mapping

```text
Low:    RiskScore < 0.30
Medium: 0.30 ≤ RiskScore < 0.60
High:   RiskScore ≥ 0.60
```

Boundary tests are **required** — add these as unit tests in `riskLogic.test.ts`:

| Input RiskScore | Expected RiskLevel |
|---|---|
| 0.299 | Low |
| 0.300 | Medium |
| 0.599 | Medium |
| 0.600 | High |

### Alert Severity (FSM)

```text
NORMAL    ← RiskLevel = Low
CAUTION   ← RiskLevel = Medium
HIGH_ALERT ← RiskLevel = High (sustained for > 2 seconds wall-clock time)
```

**CRITICAL — hold-time must use wall-clock milliseconds, not window count.**
If `Δt = 1s`, one High window = 1 s < 2 s threshold → should NOT trigger HIGH_ALERT.
If `Δt = 3s`, one High window = 3 s > 2 s threshold → SHOULD trigger HIGH_ALERT.
The FSM counter must track `Date.now()` elapsed time, not the number of replay cycles.

Recovery rule: alert auto-recovers after sustained Low risk for > 10 seconds (wall-clock).
There is no manual acknowledgement step.

### Dominant Evidence

```text
if |P_distraction - P_telemetry_anomaly| < 0.15:
    DominantEvidence = "Combined"
elif P_distraction > P_telemetry_anomaly:
    DominantEvidence = "Vision-dominant"
else:
    DominantEvidence = "Telemetry-dominant"
```

If one modality is missing or stale:

```text
DominantEvidence = "Partial evidence"
explanation = "One modality unavailable. Risk based on {available_modality} only."
```

### System Health

| State | Condition |
|---|---|
| `FULL` | Both modalities fresh |
| `DEGRADED` | One modality stale or missing |
| `UNAVAILABLE` | No valid modality or AI layer failure |

---

## 8. Frontend Page Requirements

The dashboard must keep exactly five views in the sidebar:

### 1. `LiveMonitor`

- Alert banner (AlertSeverity + SystemHealth composed into one FSM banner)
- Session info strip
- Camera preview (`useCameraPreview` hook — idle / requesting / live / denied / error states)
- Telemetry summary (5-cell grid: speed, acceleration, steering, brake, lane deviation)
- `P_distraction` modality card + freshness badge
- `P_telemetry_anomaly` modality card + freshness badge
- `RiskScore` gauge card
- `RiskLevel` badge
- `DominantEvidence` label
- Latency display (`latency_ms`)
- Recent trend sparkline (last N windows)

### 2. `SignalInspector`

- Window list panel (left) — indexed by `window_id` + timestamp
- Selected-window detail panel (right):
  - raw input preview (placeholder frame in MVP; canvas snapshot in FYP2)
  - visual branch top classes with probabilities
  - telemetry feature table
  - branch probabilities (`P_distraction`, `P_telemetry_anomaly`)
  - freshness status badges
  - `latency_ms`

### 3. `RiskTrends`

- Recharts `LineChart`: `RiskScore` + `P_distraction` + `P_telemetry_anomaly` traces
- Threshold reference lines at 0.30 and 0.60
- `RiskLevel` distribution `BarChart` (Low / Medium / High session counts)
- Recent records table with high-risk row highlighting (`RiskScore ≥ 0.60`)

### 4. `Explanation`

- Hero card: dominant-evidence text (Vision-dominant / Telemetry-dominant / Combined /
  Partial evidence / Low observed risk)
- Vision/telemetry contribution bar (weighted share: `w_v × P_d` vs `w_t × P_t`)
- Top visual classes list
- Telemetry feature contribution display
- Session-level dominant-evidence distribution chart
- For DEGRADED windows, show explicit copy: "One modality unavailable."

### 5. `Configuration`

- Operation mode selector (Demo Replay / Camera Live)
- `Δt` slider (replay interval in seconds)
- Fusion weight slider (`w_v` auto-balanced so `w_v + w_t = 1.0`)
- EMA α slider
- Low/Medium threshold slider (default 0.30)
- Medium/High threshold slider (default 0.60)
- Freshness tolerance `τ` slider
- Explanation toggle (detailed / summary mode)
- Reset session button (Delete from localStorage)
- Export JSON button
- Export CSV button (optional)

---

## 9. Mock Scenarios

Use deterministic mock scenarios for FYP1 UI and logic development.
Each scenario must produce stable, predictable payloads for screenshots, tests, and viva demos.

| Scenario | `P_distraction` | `P_telemetry_anomaly` | Expected RiskScore | RiskLevel | DominantEvidence | SystemHealth |
|---|---|---|---|---|---|---|
| `normal` | 0.12 | 0.15 | 0.135 | Low | Combined | FULL |
| `vision_dominant` | 0.75 | 0.30 | 0.525 | Medium | Vision-dominant | FULL |
| `vision_dominant_high` | 0.82 | 0.46 | 0.640 | High | Vision-dominant | FULL |
| `telemetry_dominant` | 0.28 | 0.72 | 0.500 | Medium | Telemetry-dominant | FULL |
| `telemetry_dominant_high` | 0.35 | 0.85 | 0.600 | High | Telemetry-dominant | FULL |
| `combined_medium` | 0.48 | 0.52 | 0.500 | Medium | Combined | FULL |
| `combined_high` | 0.68 | 0.72 | 0.700 | High | Combined | FULL |
| `degraded_vision_only` | 0.65 | — | 0.65 (vision only) | High | Partial evidence | DEGRADED |
| `degraded_telemetry_only` | — | 0.70 | 0.70 (telemetry only) | High | Partial evidence | DEGRADED |
| `unavailable` | — | — | — | — | — | UNAVAILABLE |
| `recovery` | 0.10 | 0.12 | 0.110 | Low | Combined | FULL |

The reference implementation ships **28 windows** covering all scenarios above,
including at least one DEGRADED window and a final recovery sequence returning to Low.

---

## 10. Persistence Requirements

### FYP1 MVP — localStorage

Use `localStorage` under key `session_log:{session_id}` to demonstrate CRUD:

| Operation | Action |
|---|---|
| Create | Append a new `risk_update` on each replay cycle |
| Read | Reload session log on page mount |
| Update | Flag or annotate a selected window (`flagged: true`) |
| Delete | Reset session log and remove key |
| Export | Download JSON (required) and CSV (optional) |

**CRITICAL — localStorage quota guard:**
Browser `localStorage` has a 5 MB quota. A long demo session can overflow it silently,
breaking the CRUD demonstration. Add this guard to `persistence.ts`:

```typescript
const MAX_SESSION_RECORDS = 500;

export function appendRecord(sessionId: string, record: RiskUpdate): void {
  const key = `session_log:${sessionId}`;
  const log: RiskUpdate[] = JSON.parse(localStorage.getItem(key) ?? "[]");
  if (log.length >= MAX_SESSION_RECORDS) {
    log.shift(); // remove oldest record
  }
  log.push(record);
  localStorage.setItem(key, JSON.stringify(log));
}
```

### FYP2 — SQLite via SQLAlchemy

**Database choice: SQLite (confirmed).** Reasons:
- Zero-config — no server process required for FYP prototype scope
- SQLAlchemy ORM abstracts the engine; upgrading to PostgreSQL later requires only one
  connection string change — all model definitions remain unchanged
- Aligned with report technical stack justification

```python
# FYP2 — SQLite connection (keep this)
DATABASE_URL = "sqlite:///./session_log.db"

# Future upgrade path only — do not implement in FYP scope
# DATABASE_URL = "postgresql+asyncpg://user:pass@localhost/driver_risk"

engine = create_engine(DATABASE_URL)
```

SQLAlchemy schema must align with the frontend `risk_update` payload field names.
See `Final_Consolidated_Guidebook_v2.docx §11.2` for the full `InferenceRecord` ORM model.

---

## 11. Testing Expectations

### Risk logic changes → update `riskLogic.test.ts`

- Default weighted fusion formula
- Threshold boundary mapping (0.299 / 0.300 / 0.599 / 0.600)
- Dominant evidence logic including Combined, Vision-dominant, Telemetry-dominant, Partial
- DEGRADED and UNAVAILABLE system health states
- FSM hold-time: 1 High window at Δt=1s must NOT trigger HIGH_ALERT
- FSM hold-time: 1 High window at Δt=3s MUST trigger HIGH_ALERT
- FSM recovery: 9 s at Low must NOT recover; 10.1 s MUST recover
- JSON export field completeness

### UI changes → verify manually

- All five pages render with no console errors
- Mock replay updates at configured `Δt`
- Fusion weight slider change propagates to RiskScore on Live Monitor immediately
- Risk score and trend update consistently
- Reset clears localStorage; refresh restores session
- Export JSON contains all session windows with correct field names

### Backend changes (FYP2) → add pytest tests

- Pydantic schemas match frontend `RiskUpdate` TypeScript types exactly
- REST endpoints return the correct payload shapes
- SQLite write → read → export round-trip
- Polling endpoint returns the latest cached payload
- WebSocket is added only after REST polling is tested and stable

---

## 12. Suggested Commands

Use commands that exist in the repository. If a command is missing, do not invent success.

### Frontend

```bash
cd frontend
npm install
npm run dev
npm run typecheck
npm run lint
npm test
```

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
pytest
```

### Root-level checks

```bash
git status
```

Add new scripts to `README.md` when introducing them.

---

## 13. Code Style

### TypeScript / React

- Use functional components with hooks.
- Keep shared types in `src/types/`.
- Keep reusable pure logic in `src/utils/` — especially `riskLogic.ts`.
- Keep mock data and scenario generators in `src/data/` or `src/mocks/`.
- Keep page-level components in `src/pages/`.
- Keep reusable UI components in `src/components/`.
- **Single source of truth for thresholds and weights** — define in `riskLogic.ts`,
  import everywhere. Never hardcode `0.30` or `0.60` in component files.
- Do not duplicate risk formulas across components.

### Python / Backend

- Use type hints on all function signatures.
- Use Pydantic v2 schemas for all API request and response payloads.
- Keep route handlers thin — call services, return payloads.
- Put business logic in `app/services/`.
- Keep provider interfaces stable.
- Avoid hardcoding dataset paths in service logic — use Pydantic Settings.

### AI Providers

Use interface-style wrappers. Start with mock, replace later with real models:

```text
VisionProvider.predict(frame)             → P_distraction
TelemetryProvider.predict(record)         → P_telemetry_anomaly
FusionService.fuse(branch_outputs, config) → risk_update
```

The `MockAIProvider` must support named scenarios so the UI, FSM logic, and export can
all be tested before model training is complete.

---

## 14. Documentation Rules

When updating report-related content or UI copy, use this approved phrase:

> real-time-ready proof-of-concept late-fusion driver risk assessment framework

Use these terms consistently — exact casing matters for viva and report:

- `P_distraction`
- `P_telemetry_anomaly`
- `RiskScore`
- `RiskLevel`
- `DominantEvidence`
- `AlertSeverity`
- `SystemHealth`
- `decision-level late fusion`
- `derived operational risk level`
- `modality_freshness`

Avoid these terms unless explicitly discussing excluded scope:

- supervised accident severity
- medical fatigue diagnosis
- driver identity recognition
- fully deployed vehicle-grade system
- early fusion training
- synchronized multimodal ground truth

**Honest scope copy required in UI:** The dashboard must not claim AI training or
vehicle-grade deployment. Recommended footer or about card text:

> MVP proof-of-concept. Risk values are derived from mock fusion input.
> Real model inference (MobileNetV3 + XGBoost) will be integrated in FYP2.

---

## 15. Before Completing Any Task

Before finalizing a change, verify all seven points:

1. Does it preserve the two-branch late-fusion architecture?
2. Does it keep frontend, backend, AI, and storage responsibilities separate?
3. Does it avoid unsupported claims about real-time deployment or accident severity?
4. Does it keep `risk_update` compatible with the dashboard, logging, and export?
5. Does it add or update tests where risk logic changed?
6. Does it maintain the FYP1 / FYP2 boundary (no backend code in FYP1 MVP)?
7. Can the change be explained clearly and accurately during viva?

---

## 16. Recommended Development Order

Follow this order to minimize blocked work and integration risk:

1. Freeze shared `RiskUpdate` TypeScript type and Pydantic schema.
2. Implement and unit-test all risk logic in `riskLogic.ts`.
3. Build mock scenario generator (`MockAIProvider` with named scenarios).
4. Build five-view React dashboard with mock replay.
5. Add `localStorage` CRUD + quota guard + JSON/CSV export.
6. Add browser camera preview (`useCameraPreview` state machine).
7. Add deterministic replay loop (`useDemoReplay` with `setInterval`).
8. Complete unit tests for risk logic, FSM, freshness, and export.
9. Scaffold FastAPI backend with Pydantic schemas matching frontend types.
10. Add SQLite persistence via SQLAlchemy (`InferenceRecord`, `AlertEvent` models).
11. Add REST polling endpoints; replace `localStorage` calls with `fetch`.
12. Integrate real MobileNetV3 vision branch wrapper.
13. Integrate real XGBoost telemetry branch wrapper.
14. Add FastAPI native WebSocket push (only after REST polling is stable).
15. Add SHAP or advanced explanation (stretch goal).
