# Development Schedule - In-Cabin Multi-Modal Driver Risk Assessment

Derived from `Final_Consolidated_Guidebook_v2.docx` and
`Final_MVP_Prototype_Guidebook.docx`, then reconciled against the current
checkout as of 2026-06-01.

> Calendar dates are anchored to a June 2026 planning start. Replace them with
> the real FYP1 submission and FYP2 semester dates if those dates change. The
> ordering and dependencies are the important part.

---

## 1. Current Position

| Area | Current evidence | Status | Next action |
|---|---|---|---|
| Frontend dashboard | Five views under `frontend/src/views/`; camera preview, trends, explanation, config, local session log | Implemented for FYP1 MVP | Keep UI stable; do not redesign during FYP1 closeout |
| Risk logic | `ai/src/riskLogic.ts`, `ai/src/evidence.ts`, `ai/src/alertFsm.ts`; frontend tests show 23/23 passing | Implemented and tested | Preserve 0-100 RiskScore, 30/60 thresholds, full DominantEvidence strings |
| AlertSeverity FSM | Wall-clock FSM in TypeScript runtime orchestration; FSM diagram and tests exist | Implemented in frontend/runtime layer | Do not claim backend wall-clock FSM unless added later |
| Session persistence | Frontend localStorage CRUD/export; backend FastAPI + SQLite CRUD/export; backend pytest passes | Implemented at two prototype layers | Add localStorage quota guard before FYP1 freeze |
| Backend service | `backend/app/` FastAPI, SQLAlchemy, SQLite, Pydantic schemas, MockAIProvider, CRUD/export | Tested prototype backend layer | Keep as additive FYP2 layer until frontend polling is added |
| Prepared replay | `ai/prototype-data/prepared_sessions/session_001/telemetry.csv` currently has 6 replay windows | Incomplete versus MVP guidebook target | Expand to 25-28 windows covering all required risk/evidence cases |
| EDA artifacts | Vision and telemetry EDA artifacts exist in the sibling EDA workspace, not fully copied into this prototype repo | Available but needs linkage/selection | Reference or copy final report figures intentionally; avoid duplicate stale artifacts |
| Real models | No `vision.onnx`, `.pt`, `telemetry.pkl`, or trained model metrics in this repo | FYP2 pending | Present as designed until trained artifacts and metrics exist |
| Frontend-backend connection | React still runs standalone; backend is not wired into UI | Pending | Add optional backend mode after FYP1 closeout, not before |

## 2. Progress Against Guidebook Sprints

| Guidebook sprint | Planned deliverable | Current status |
|---|---|---|
| S1 - Business + Data Understanding | Problem statement, data inventory, rubric mapping | Done for FYP1 report scope |
| S2 - Data Understanding | Vision EDA, telemetry EDA, gap analysis | EDA artifacts exist in the EDA workspace; select final figures for report/evidence |
| S3 - Data Preparation | Vision metadata/splits; telemetry feature engineering/splits | Data-prep artifacts exist outside this prototype repo; current prototype replay still needs 25-28-window expansion |
| S4 - Modelling | MobileNetV3 fine-tune; XGBoost multiclass model | Not started in this repo; no trained model artifacts |
| S5 - Fusion + Evaluation | Late fusion, thresholds, calibration, metric reporting | Rule-based fusion implemented and tested; real-model calibration not done |
| S6 - Evaluation + Deployment | Backend integration, alert FSM, session logging | Backend prototype and frontend FSM/logging are implemented; frontend-backend polling and backend alert-event persistence remain pending |
| S7 - Deployment | End-to-end testing, viva prep, report finalisation | FYP1 viva/report can proceed with prototype evidence; FYP2 full E2E waits for real models |

**Net position:** the frontend MVP and a backend prototype scaffold are already
implemented and tested. The immediate critical path is not model training; it is
FYP1 closeout: replay coverage, persistence guard, evidence refresh, and
report-safe wording. The FYP2 critical path is model training, provider wiring,
REST polling, evaluation, and optional WebSocket push.

---

## 3. Immediate FYP1 Closeout Schedule

This is the next development block before starting large FYP2 model work.

| Timebox | Owner | Tasks | Exit evidence |
|---|---|---|---|
| D0 half-day | orchestrator + guardrail-reviewer | Clean planning/docs wording; decide whether to keep `.claude/agents/` local or tracked; do not commit `.claude/settings.local.json` | Clean `git status`; no local-only config staged |
| D1 AM | frontend-dev | Add `MAX_SESSION_RECORDS = 500` quota guard to `frontend/src/utils/persistence.ts` | Updated code; no behaviour regression |
| D1 PM | risk-logic-dev + frontend-dev | Expand prepared replay to 25-28 windows covering Low, Medium, High, Vision-dominant, Telemetry-dominant, Combined evidence, Partial evidence, Low observed risk, DEGRADED, and final recovery | `telemetry.csv` has 25+ data rows; dashboard trends show richer session |
| D2 AM | qa-runner | Run `npm test`; run backend pytest; optionally run typecheck/build if time allows | Refreshed `docs/evidence/frontend-tests.txt` and `docs/evidence/backend-pytest.txt` |
| D2 PM | report-writer + guardrail-reviewer | Refresh Chapter 5 wording and evidence mapping; ensure backend is described as a tested prototype layer, not production | Report text aligns with current code/evidence |
| D3 | orchestrator + Codex review gate | Fix review findings, commit only intended files, push after user approval | Clean reviewed commit set |

Recommended Claude prompt for this block:

```text
@orchestrator

Mode: Claude writes code, Codex reviews at stop-time.
Task: Close FYP1 guidebook compliance gaps before FYP2 expansion.

Scope:
- May edit frontend/src/utils/persistence.ts
- May edit ai/prototype-data/prepared_sessions/session_001/**
- May edit frontend/src/data/preparedSessionInput.ts only if needed
- May edit ai/src/*.test.ts and docs/evidence/** after tests
- Do not edit backend/** unless required by tests
- Do not push

Required:
- Add MAX_SESSION_RECORDS = 500 localStorage quota guard
- Expand prepared replay to at least 25 windows covering all RiskLevel and DominantEvidence cases, DEGRADED, and recovery
- Run npm test
- Run backend pytest if evidence files are refreshed
- Stop for Codex review before commit
```

---

## 4. FYP2 Development Roadmap

This starts after the FYP1 closeout block or after the FYP1 report is submitted.

| Week | Focus | CRISP-DM phase | Owner(s) | Deliverable |
|---|---|---|---|---|
| W1 | Consolidate EDA assets and data manifests | Data Understanding / Preparation | ml-engineer + report-writer | Final selected vision/telemetry EDA figures; model-ready manifests linked from the active repo/report |
| W2 | MobileNetV3 vision branch | Modelling | ml-engineer | Trained vision model artifact; validation metrics; top-class output compatible with `visual_top_classes` |
| W3 | XGBoost telemetry branch | Modelling | ml-engineer | Trained telemetry model artifact; multiclass probabilities; `P_telemetry_anomaly = 1 - P(Safe)` |
| W4 | Fusion calibration and sensitivity checks | Evaluation | risk-logic-dev + ml-engineer | Threshold/weight sensitivity report; justification for retaining or adjusting 30/60 thresholds |
| W5 | Backend provider wiring | Deployment | backend-dev | Replace or wrap `MockAIProvider` with model provider interfaces; keep `fusion.py` contract stable |
| W6 | Frontend-backend REST polling | Deployment | frontend-dev + backend-dev | Optional backend mode using FastAPI polling while preserving localStorage fallback |
| W7 | E2E validation and backend alert events | Evaluation / Deployment | qa-runner + backend-dev | Full pipeline smoke test; optional `AlertEvent` persistence; refreshed Swagger/SQLite/export evidence |
| W8 | Report finalisation and viva rehearsal | Deployment | report-writer + guardrail-reviewer | Chapter 5/6 metrics from verified artifacts; viva-safe explanation script |

### Dependency Chain

```text
FYP1 closeout
  -> selected EDA/manifests
  -> train MobileNetV3 + XGBoost
  -> calibrate fusion thresholds/weights
  -> wire backend providers
  -> add frontend REST polling mode
  -> E2E validation + report/viva
```

### Parallel Work

- Report drafting can run in parallel, but numeric metrics must wait for
  verified model/evaluation artifacts.
- Frontend UI polish can run in parallel with model training only if it does not
  alter the `RiskUpdate` contract.
- WebSocket work should wait until REST polling is stable.

---

## 5. Guidebook Guardrails

- Decision-level late fusion only; no early or feature-level multimodal training.
- `RiskScore` remains on the 0-100 scale; thresholds remain 30/60 unless a
  documented calibration step justifies a change.
- `P_telemetry_anomaly` remains the legacy API/export field name and is defined
  as telemetry non-safe behaviour probability, `1 - P(Safe)`.
- `DominantEvidence` strings stay contract-compatible, especially
  `"Combined evidence"`.
- Fusion weights and thresholds are transparent design parameters, not learned
  safety-critical weights.
- SQLite remains the FYP database; do not switch to MySQL/PostgreSQL in scope.
- FastAPI native REST comes before optional WebSocket push.
- No vehicle-grade deployment, driver-side CAN-bus alerting, biometric identity,
  or medical diagnosis claims.
- Models are described as trained only after model artifacts and metrics are
  present. Until then, write "designed for FYP2 integration".

---

## 6. Commit Guidance

- Commit FYP1 closeout changes separately from FYP2 model/provider work.
- Do not commit local-only settings such as `.claude/settings.local.json`.
- Keep `docs/chapter5_report_ready/` local unless the user explicitly asks to
  publish generated report assembly artifacts.
- Evidence files under `docs/evidence/` can be tracked when they document a
  reproducible test or demo run.
