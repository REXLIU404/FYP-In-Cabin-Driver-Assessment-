# Backend Completion Plan (FYP2 layer, no model training)

Tracks the work to bring `backend/app/` to guidebook §6.2 / §4.3 completeness **without** training
models (models stay FYP2 W2–W3 per `docs/DEVELOPMENT_SCHEDULE.md`). MockAIProvider remains the
stand-in. Every coding slice ends with the Codex stop-time review gate.

## Contract lock
The shared `RiskUpdate` contract (`backend/app/schemas.py` ↔ `ai/src/types.ts`) must NOT change here.
New endpoints add **backend-only** response schemas only.

## Backlog

### Slice 1 — Orchestrator extraction + System Status + export hardening  ← in progress
- [x] Extract Inference Orchestrator (`app/inference.py`): window → MockAI → fusion → `RiskUpdate`,
      reused by `windows.py` (and future system-status / fusion loop).
- [x] `GET /api/sessions/{id}/system-status` (System Status Manager) — backend-only schema; honestly
      reports `models_loaded: false`, AI provider name, cache state, DB scheme, last health/severity.
- [x] Harden `export` `format` param: explicit `400` on anything other than `json`/`csv`.
- [x] Extend pytest to cover system-status + invalid export format.

### Slice 2 — Result Logging completeness
- [ ] `AlertEvent` ORM table (session_id, window_id, from_severity, to_severity, timestamp).
- [ ] Persist a row whenever consecutive windows change AlertSeverity (transition log).
- [ ] `GET /api/sessions/{id}/alert-events` (backend-only schema).
- [ ] Optional error-event log row when MockAI/fusion raises.

### Slice 3 — Dashboard response generator
- [ ] `GET /api/sessions/{id}/trends?fields=RiskScore,RiskLevel` — compact series for Risk Trends view
      (reuses persisted records; no new contract).

### Slice 4 — Session lifecycle (optional, scope-permitting)
- [ ] `status` column on `SessionMeta` (`active|paused|closed`) + `PATCH /sessions/{id}/status`.

### Out of scope here (later sprints)
- asyncio fixed-interval fusion loop (§6.3) — needs live input mode (FYP2 Stage B/C).
- WebSocket push (§5 Stage C) — after REST polling is stable.
- Replacing MockAIProvider with real ONNX/XGBoost providers — FYP2 W5 (needs trained artifacts).
