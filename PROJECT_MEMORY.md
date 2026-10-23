# PROJECT_MEMORY.md

# In-Cabin Multi-Modal Driver Risk Assessment — Project Memory

**Project title:** Late-Fusion Multi-Modal Driver Risk Assessment Framework Using Vision-Based Distraction Detection and Telemetry-Based Anomaly Detection  
**Current status:** FYP1 / MVP-oriented proof-of-concept  
**Author:** Yerong Liu  
**Purpose of this document:** Keep the report, prototype, viva explanation, coding work, and AI-agent instructions aligned with the current agreed project design.

---

## 1. Current Project Positioning

This project is a **real-time-ready proof-of-concept driver risk assessment framework**. It does not try to detect every possible driver state. It focuses on two observable and dataset-defensible operational risk dimensions:

1. **Vision-based distraction-related risk**
   - Input: driver-facing image / sampled frame / browser camera preview / demo replay frame
   - Branch output: `P_distraction`

2. **Telemetry-based anomaly risk**
   - Input: structured vehicle or trip-level telemetry record / JSON / replay telemetry
   - Branch output: `P_telemetry_anomaly`

The two branch outputs are combined through **decision-level late fusion** to produce:

- `RiskScore`
- `RiskLevel` = `Low | Medium | High`
- `DominantEvidence`
- `AlertSeverity`
- `SystemHealth`
- session-level trend and log records

The project should be described as:

> A late-fusion multi-modal driver risk assessment framework that combines driver-facing visual distraction evidence and structured telemetry anomaly evidence into an interpretable operational risk score.

---

## 2. Important Direction Lock

The current main project is **not** the older wearable/AffectiveROAD route.

Do **not** describe the current implementation as:

- physiological wearable monitoring
- Empatica E4 / Zephyr BioHarness system
- supervised sleepiness-like + workload/stress state estimation
- feature-level physiological fusion
- medical fatigue or health diagnosis

The current final route is:

```text
Vision input / sampled frame
→ Vision branch
→ P_distraction

Structured telemetry JSON / replay record
→ Telemetry branch
→ P_telemetry_anomaly

P_distraction + P_telemetry_anomaly
→ decision-level late fusion
→ RiskScore + RiskLevel + DominantEvidence
→ dashboard + log + export
```

---

## 3. Project Background

Road safety remains a major public-safety problem, and driver-related human factors are a major contributor to crashes. Existing driver monitoring systems often depend on a single evidence source, such as camera-based driver-state detection or vehicle telemetry analysis. However, each source is incomplete on its own.

A vision system can observe in-cabin driver behaviour such as phone use, drinking, reaching behind, or talking to passengers, but it cannot directly observe vehicle dynamics such as acceleration, harsh braking, lane deviation, speed, or route anomaly. A telemetry system can capture operational movement and trip-level anomaly evidence, but it cannot explain what the driver is visually doing inside the cabin.

This motivates a multi-modal framework that treats vision and telemetry as **complementary evidence streams**. Because the selected public datasets are not synchronised paired multi-modal samples, the project does not use early fusion or feature-level multimodal training. Instead, each modality is trained or implemented independently, and the outputs are fused at the decision level.

---

## 4. Problem Statements and Objectives

| Problem | Project Objective | Design Response |
|---|---|---|
| Single-modality fragility in driver risk monitoring | Design a late-fusion multi-modal driver risk representation framework | Vision branch + telemetry branch + decision-level fusion |
| Detection without actionable risk-level output | Develop a severity-aware operational risk scoring mechanism | Weighted `RiskScore`, Low/Medium/High mapping, modality-based explanation |
| Lack of real-time-ready inference and pipeline design | Design a real-time-ready inference pipeline | Efficient model choices, fixed-interval updates, modular frontend/backend/AI/storage design |

---

## 5. Project Scope

### 5.1 In Scope

| Area | In-scope decision |
|---|---|
| Visual input | Browser camera preview, uploaded video, sampled frames, or demo replay frames |
| Telemetry input | Structured JSON records or replay telemetry records |
| Vision branch | Produces `P_distraction` |
| Telemetry branch | Produces `P_telemetry_anomaly` |
| Fusion | Weighted decision-level late fusion |
| Risk interpretation | `RiskScore`, `RiskLevel`, `DominantEvidence`, `AlertSeverity`, `SystemHealth` |
| Dashboard | Five-view React dashboard |
| Persistence | Session log, localStorage in MVP; SQLite in FYP2 |
| Export | JSON / CSV session log export |
| Evaluation | Branch metrics, fusion behaviour, risk distribution, latency, log completeness |

### 5.2 Out of Scope

| Out-of-scope item | Reason |
|---|---|
| Vehicle-grade deployment | Not certified for production automotive use |
| Driver-side notification | No in-vehicle alert, SMS, push notification, CAN bus actuation |
| Supervised accident severity prediction | No validated accident severity labels |
| Medical fatigue diagnosis | The project focuses on distraction/anomaly risk, not medical diagnosis |
| Driver identity / biometrics | No face recognition, identity storage, or biometric profiling |
| Early / feature-level multimodal training | Selected datasets are not synchronised paired samples |
| Fully synchronised live streams | MVP relies on sampled frames and record-level telemetry/replay |

---

## 6. Expected Deliverables

### 6.1 FYP1 / MVP Deliverables

1. A working proof-of-concept dashboard with five views:
   - Live Monitor
   - Signal Inspector
   - Risk Trends
   - Explanation
   - Configuration

2. A modular risk-update data contract:
   - `P_distraction`
   - `P_telemetry_anomaly`
   - `RiskScore`
   - `RiskLevel`
   - `DominantEvidence`
   - `AlertSeverity`
   - `SystemHealth`
   - `latency_ms`
   - `modality_freshness`

3. A deterministic demo replay loop:
   - fixed interval `Δt`
   - mock or recorded payload updates
   - session-level risk trend

4. Risk logic implementation:
   - weighted late fusion
   - risk threshold mapping
   - dominant evidence rule
   - freshness / degraded mode handling
   - alert anti-flicker logic where feasible

5. Persistence and export:
   - localStorage CRUD for FYP1
   - JSON export of session log
   - optional CSV export

6. Report and viva evidence:
   - screenshots of five views
   - data contract examples
   - risk-score and risk-level examples
   - latency / update evidence
   - explanation examples
   - roadmap to FYP2 backend and real model integration

### 6.2 FYP2 Target Deliverables

1. Real MobileNetV3 or equivalent vision branch wrapper.
2. Real XGBoost telemetry anomaly branch wrapper.
3. FastAPI backend with REST endpoints and optional native WebSocket.
4. SQLite persistence via SQLAlchemy.
5. Backend-driven polling first, then optional WebSocket push.
6. More complete evaluation:
   - vision metrics
   - telemetry metrics
   - risk distribution
   - weight sensitivity analysis
   - latency summary
   - log completeness

---

## 7. System Architecture Memory

The system uses a strict layered architecture:

```text
Input Sources
→ React Frontend Dashboard
→ Backend Service Layer
→ Core AI Inference Layer
→ Session Log / Result Store
→ Frontend Dashboard / API Client
```

| Layer | Responsibility | Must NOT Do |
|---|---|---|
| Frontend Dashboard | Render dashboard, collect user actions, show camera preview, display payloads | Model inference, fusion, risk scoring |
| Backend Services | Validate requests, manage sessions, build windows, call AI layer, cache/log outputs | Model training, SHAP computation, analytical reasoning |
| Core AI Inference | Vision inference, telemetry inference, smoothing, freshness-aware fusion, risk interpretation | UI rendering, API authentication, persistence ownership |
| Session Log / Result Store | Persist inference records, alert events, settings snapshots, errors, exports | Inference or UI interaction |

---

## 8. Five Dashboard Views

| View | Purpose | Minimum content |
|---|---|---|
| Live Monitor | Main monitoring view | latest frame/camera preview, telemetry summary, branch scores, `RiskScore`, `RiskLevel`, `DominantEvidence`, alert, freshness |
| Signal Inspector | Inspect selected window | raw input preview, processed feature summary, branch probabilities, freshness, latency |
| Risk Trends | Session-level review | risk score trend, branch traces, risk-level transitions, alert events |
| Explanation | Lightweight interpretation | vision-dominant / telemetry-dominant / combined / partial-evidence explanation; top visual probabilities; telemetry feature importance |
| Configuration | Runtime setup | input source, replay control, polling interval, weights, thresholds, freshness tolerance, explanation options |

---

## 9. Modelling and Fusion Memory

### 9.1 Vision Branch

Recommended wording:

> The vision branch estimates distraction-related visual evidence from driver-facing images or sampled frames.

Recommended technical design:

- Dataset role: State Farm-style distracted driver images
- Training target: 10-class visual behaviour classification if labels are available
- Final risk output:
  - `P_distraction = 1 - P(c0)`
  - or `P_distraction = sum(P(c1)...P(c9))`
- Primary model: MobileNetV3
- Baselines: ResNet50, EfficientNet-B0, ViT only as optional comparison
- Runtime handling:
  - frame sampling
  - frame-level inference
  - rolling mean / EMA smoothing
- Do not claim temporal video modelling unless using true ordered sequence labels.

### 9.2 Telemetry Branch

Recommended wording:

> The telemetry branch estimates anomaly-related operational evidence from structured vehicle and trip-level telemetry features.

Recommended technical design:

- Dataset role: DBRA24-style structured telemetry records
- Target: `anomalous_event`
- Primary model: XGBoost
- Baselines: Random Forest, Logistic Regression
- Input feature groups:
  - speed / acceleration
  - steering / heading
  - braking / rpm
  - lane deviation
  - road type / weather / traffic condition
- Remove leakage-prone fields:
  - `anomalous_event` as input
  - route labels that directly encode anomaly target
  - identifiers as model features
- Output:
  - `P_telemetry_anomaly = model.predict_proba(X)[:, 1]`

### 9.3 Fusion Layer

Default formula:

```text
RiskScore = w_v × P_distraction + w_t × P_telemetry_anomaly
```

Default prototype setting:

```text
w_v = 0.5
w_t = 0.5
RiskScore = 0.5 × P_distraction + 0.5 × P_telemetry_anomaly
```

Important wording:

> Fusion weights are transparent design parameters, not learned safety-critical weights, because synchronised multimodal severity labels are not available.

### 9.4 Risk-Level Mapping

Default thresholds:

```text
Low Risk:    RiskScore < 0.30
Medium Risk: 0.30 ≤ RiskScore < 0.60
High Risk:   RiskScore ≥ 0.60
```

Important wording:

> `RiskLevel` is an operational derived risk level, not supervised accident severity.

### 9.5 Dominant Evidence

Recommended rule:

```text
if abs(P_distraction - P_telemetry_anomaly) < epsilon:
    DominantEvidence = "Combined"
elif P_distraction > P_telemetry_anomaly:
    DominantEvidence = "Vision-dominant"
else:
    DominantEvidence = "Telemetry-dominant"
```

Add partial-evidence labels when one modality is stale or missing.

---

## 10. Runtime and Communication Memory

### FYP1 / MVP

- React standalone prototype.
- `setInterval(Δt)` drives demo replay and mock fusion updates.
- localStorage stores session records.
- Export JSON/CSV from frontend.
- No backend required yet.

### FYP2 Early

- FastAPI backend.
- React polls `/api/risk/latest` every `Δt`.
- Backend owns session state, cache, logging, and persistence.
- SQLite stores inference records.

### FYP2 Final / Stretch

- FastAPI native WebSocket pushes `risk_update`.
- REST endpoints remain for API clients and exports.
- WebSocket migration is additive, not a redesign.

Do not reintroduce Flask-SocketIO or APScheduler unless the design is deliberately changed and documented.

---

## 11. Current Prototype: Next Development Steps

### Priority 1 — Freeze the data contract

Create a shared `RiskUpdate` type/schema before building UI logic.

Minimum payload:

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
  "explanation": "High risk is mainly driven by visual distraction evidence."
}
```

### Priority 2 — Implement core risk logic first

Implement and test:

- `computeRiskScore(P_distraction, P_telemetry_anomaly, weights)`
- `mapRiskLevel(RiskScore)`
- `getDominantEvidence(P_distraction, P_telemetry_anomaly)`
- `getSystemHealth(modality_freshness)`
- `generateExplanation(payload)`
- optional `updateAlertFSM(previousState, currentRiskLevel, duration)`

Test boundary cases:

- `0.299 → Low`
- `0.300 → Medium`
- `0.599 → Medium`
- `0.600 → High`
- missing telemetry → `DEGRADED`
- equal branch scores → `Combined`

### Priority 3 — Build the five-view frontend with mock replay

Build the dashboard using mock deterministic scenarios first:

- `normal`
- `vision_dominant`
- `telemetry_dominant`
- `combined`
- `degraded_vision_only`
- `degraded_telemetry_only`
- `unavailable`

This allows UI, fusion, trend, logging, and export to be tested before real models are ready.

### Priority 4 — Add localStorage persistence and export

MVP must demonstrate CRUD-like behaviour:

- Create: append risk update
- Read: load session log on page mount
- Update: flag or annotate selected window
- Delete: reset session log
- Export: download JSON or CSV

### Priority 5 — Add browser camera preview

Use camera preview for the visual input interface, even if the risk value is still mock-driven. This supports the “visual input processing” demonstration without requiring real vision inference in FYP1.

### Priority 6 — Prepare model integration wrappers

Use stable interfaces:

```text
VisionProvider.predict(frame) -> P_distraction
TelemetryProvider.predict(record_or_window) -> P_telemetry_anomaly
FusionService.fuse(branch_outputs) -> risk_update
```

Start with `MockAIProvider`, then replace with real MobileNetV3 and XGBoost wrappers in FYP2.

### Priority 7 — FYP2 backend migration

After the frontend MVP is stable:

1. Create FastAPI project.
2. Add Pydantic schemas matching frontend types.
3. Add endpoints:
   - `POST /api/sessions`
   - `GET /api/sessions/{id}/risk/latest`
   - `GET /api/sessions/{id}/trend`
   - `GET /api/sessions/{id}/explanation/{window_id}`
   - `GET /api/sessions/{id}/export`
4. Add SQLite persistence.
5. Keep polling first.
6. Add WebSocket push only after polling works.

---

## 12. Evaluation Evidence to Prepare

| Evaluation area | Evidence |
|---|---|
| Vision branch | accuracy, precision, recall, F1, confusion matrix |
| Telemetry branch | accuracy, precision, recall, F1, ROC-AUC/PR-AUC if imbalanced |
| Fusion layer | risk-score distribution, risk-level counts, dominant-evidence distribution |
| Weight sensitivity | compare 0.5/0.5, 0.6/0.4, 0.4/0.6, 0.7/0.3, 0.3/0.7 |
| Pipeline | update interval, latency summary, no-future-data statement |
| Dashboard | screenshots of all five views |
| Persistence | localStorage or SQLite records, export file correctness |
| Robustness | degraded mode, missing modality, alert anti-flicker |

---

## 13. Rubric Alignment Memory

| Rubric area | What to show |
|---|---|
| Objectives | Three objectives are clear, measurable, and mapped to system components |
| Problem statement | Three problems directly match the project design |
| Literature review | Review algorithms, methods, systems, and fusion/risk-scoring theories |
| Methodology | Hybrid Agile + CRISP-DM; design meets all objectives |
| Requirements | FR/NFR table, stakeholder/user needs, module requirements |
| Analysis and Design | Architecture diagram, use case diagram, sequence diagram, DFD, five-view mockups |
| Technical Implementation | At least two working core modules, CRUD/persistence, ability to explain and modify code |
| Stakeholder collaboration | Supervisor logbook and, if possible, LOI or domain feedback |
| Presentation | Explain project as risk assessment, not just classification |
| Q&A | Defend late fusion, equal weights, derived risk level, and real-time-ready scope |

---

## 14. Key Guardrails for Writing and Coding

Always say:

- “real-time-ready proof-of-concept”
- “operational risk score”
- “derived risk level”
- “decision-level late fusion”
- “vision-based distraction evidence”
- “telemetry-based anomaly evidence”
- “transparent design parameters”
- “dashboard-oriented monitoring output”

Avoid saying:

- “fully deployed real-time vehicle system”
- “certified safety system”
- “supervised accident severity prediction”
- “medical fatigue diagnosis”
- “driver identity recognition”
- “early fusion”
- “synchronised multimodal training data”
- “weights learned as true safety importance”

---

## 15. Recommended Repository Structure

```text
driver-risk-assessment/
├── README.md
├── PROJECT_MEMORY.md
├── AGENTS.md
├── .env.example
├── docs/
│   ├── report/
│   ├── design/
│   └── viva/
├── frontend/
│   ├── package.json
│   ├── src/
│   │   ├── App.tsx
│   │   ├── types/
│   │   ├── data/
│   │   ├── utils/
│   │   ├── hooks/
│   │   ├── components/
│   │   └── pages/
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── schemas.py
│   │   ├── routers/
│   │   ├── services/
│   │   └── models/
├── ai/
│   ├── vision/
│   ├── telemetry/
│   ├── fusion/
│   └── providers/
├── tests/
└── data/
    ├── sample/
    └── demo_replay/
```

---

## 16. One-Sentence Viva Answer

> My project is a real-time-ready late-fusion driver risk assessment framework. It combines vision-based distraction probability and telemetry-based anomaly probability into an interpretable operational risk score, risk level, and dominant-evidence explanation, then visualises the result through a five-view monitoring dashboard.
