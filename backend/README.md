# Backend Layer

Backend integration boundary for the in-cabin driver assessment prototype.

## Current State

A FastAPI + SQLAlchemy + SQLite **walking skeleton** is implemented under `app/` (FYP2 layer):

- `app/main.py` — FastAPI app, CORS, lifespan table creation.
- `app/routers/` — CRUD for `sessions` and `windows`, plus `risk` (latest fused `RiskUpdate`) and `export` (JSON/CSV).
- `app/fusion.py` — Python port of the late-fusion logic, kept in sync with `../ai/reference/risk_logic.py`.
- `app/schemas.py` — Pydantic v2 models mirroring `../ai/src/types.ts`.
- `app/providers/mock_ai.py` — `MockAIProvider` that echoes prepared probabilities (NOT a trained model).

Models are still **not trained**, and the FYP1 React prototype runs fully standalone — it does not
yet call this backend. This layer is additive and exists to demonstrate the FYP2 integration boundary.

### Run

```bash
# from backend/
uvicorn app.main:app --reload --port 8000        # Swagger UI: http://127.0.0.1:8000/docs
PYTHONPATH=. ../.venv/bin/python -m pytest tests/test_api.py -v
```

## Intended Responsibilities

- Receive camera/telemetry input streams or prepared-session playback requests.
- Call the real vision and telemetry model services.
- Return the same `RiskUpdate` contract defined in `../ai/src/types.ts`.
- Persist session logs when the prototype moves beyond browser `localStorage`.
- Serve runtime data to the dashboard through REST or WebSocket endpoints.

## Contract Direction

Keep backend payloads aligned with the AI layer contract instead of creating a separate response shape. This keeps the frontend, backend, and AI layers replaceable without rewriting the dashboard views.
