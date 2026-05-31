# Chapter 5 Evidence Index (Day 3 capture)

Each artifact maps to a figure slot in `Chapter5_Technical_Implementation_SPEC.docx`.

| File | Report slot | What it shows |
|------|-------------|---------------|
| `frontend-tests.txt` | §5.4.4 / validation | 23/23 vitest pass — AlertSeverity FSM (7) + risk-logic boundaries (16) |
| `backend-pytest.txt` | §5.5 | Backend end-to-end test: CRUD + fusion + degradation + export (1 passed) |
| `swagger.png` | Fig 5.9 (§5.5) | FastAPI Swagger UI — all CRUD endpoints + schemas |
| `sqlite-dump.txt` | Fig 5.9 (§5.5) | SQLite schema + persisted inference_records rows |
| `sample-export.json` | Fig 5.9 (§5.5) | Backend JSON export of a session |
| `sample-export.csv` | Fig 5.9 (§5.5) | Backend CSV export of a session |
| `inference-pipeline.png` | Fig 5.5 (§5.4.1) | Real-time-ready inference/fusion pipeline (one Δt cycle) |

UI screenshots for §5.3 / §5.4 figures live in `../ui-screenshots/` (live-monitor, signal-inspector,
risk-trends, explanation, configuration).

## Evidence highlights (one Day-3 backend run, session S001)

The single run exercises every risk pathway:

| window | P_d | P_t | RiskScore | Level | DominantEvidence | Alert | Health |
|---|---|---|---|---|---|---|---|
| 1 | 0.12 | 0.18 | 15.0 | Low | Low observed risk | NORMAL | FULL |
| 2 | 0.22 | 0.28 | 25.0 | Low | Low observed risk | NORMAL | FULL |
| 3 | 0.35 | 0.82 | 58.5 | Medium | Telemetry-dominant | CAUTION | FULL (flagged) |
| 4 | 0.78 | 0.00 | 78.0 | High | Partial evidence | HIGH_ALERT | DEGRADED |

Window 4 demonstrates graceful degradation: telemetry missing → score uses vision only
(0.78 → 78.0) and is re-normalised, not pulled toward zero.

## How to reproduce

```bash
# Frontend logic tests (repo root)
npm test

# Backend tests
cd backend && PYTHONPATH=. ../.venv/bin/python -m pytest tests/test_api.py -v

# Run backend + open Swagger
cd backend && PYTHONPATH=. ../.venv/bin/python -m uvicorn app.main:app --port 8000
#   → http://127.0.0.1:8000/docs

# Run the frontend prototype (repo root)
npm run dev   # → http://127.0.0.1:5173
```
