# Backend: trained inference and session persistence

FastAPI + SQLAlchemy + SQLite serve the existing MobileNetV3-Large ONNX and
XGBoost artifacts. React live mode calls this backend. Telemetry is explicitly
`prepared_replay`; camera frames are acquired live by the browser. The old
probability-input API remains available only to prepared-mode sessions.

From repository root:

```bash
.venv/bin/python -m pip install -r backend/requirements-inference.txt
.venv/bin/python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
PYTHONPATH=backend .venv/bin/python -m pytest backend/tests -q
```

`GET /api/health` is process health. `GET /api/models` loads/warmups actual local
weights, validates input/class/feature metadata, and returns SHA256/version info;
missing artifacts or load failures return 503. No downloads or mock fallback.
Swagger is at `/docs`. Build the frontend before starting to serve `dist/` on `/`.

| Route | Behavior |
|---|---|
| `POST /api/sessions` | Choose `LIVE_MODEL_RUNTIME` or `PREPARED_SESSION_RUNTIME`; immutable fusion config |
| `GET /api/sessions?offset=0&limit=100` | Counted, paginated sessions |
| `GET/DELETE /api/sessions/{id}` | Session metadata / delete session and records |
| `POST /api/sessions/{id}/infer` | JPEG/PNG base64 + capture timestamp + optional eight telemetry features/source/timestamp |
| `POST /api/sessions/{id}/windows` | Prepared probabilities, only for prepared sessions |
| `GET /api/sessions/{id}/windows?after=0&limit=500` | Cursor by monotonically increasing window ID |
| `GET /api/sessions/{id}/risk/latest` | Database-authoritative latest record |
| `PATCH /api/sessions/{id}/windows/{n}/flag?flagged=true` | Persist review flag |
| `DELETE /api/sessions/{id}/windows/{n}` | Delete record without reusing its ID |
| `GET /api/sessions/{id}/system-status` | Historical latest health plus this worker's model readiness; does not load models |
| `GET /api/sessions/{id}/export?format=json` | Stream all records; CSV also supported |

The live endpoint accepts **raw inputs, not client probabilities**. Required
`request_id` deduplicates identical requests; different content under the same
ID is a 409. Timestamps require timezones; out-of-order branch input is rejected.
Frames are capped at 2 MB decoded and 4096 pixels per side. Missing branches and
stale evidence have explicit states. Invalid images are 422, model failures 503.

Serving preprocess matches training: PIL RGB → bilinear resize 224×224 → /255 →
ImageNet normalization → float32 NCHW. XGBoost uses its saved feature ordering
and `best_iteration + 1`, not the extra trees retained after early stopping.

`app/inference.py` owns per-session EMA and sustained alert FSM. A short SQLite
write transaction atomically allocates the ID and updates temporal state; model
execution happens before that lock. WAL, busy timeout, unique constraints,
SQL counts and paginated/streaming reads support the local workload. `latest`
reads the DB so flags, deletes and worker restarts do not serve stale cache data.

Startup performs an additive migration; existing records are retained. Duplicate
legacy window IDs cause a clear startup error for reconciliation, never silent
data deletion. Camera images are not stored. JSON includes complete probabilities,
features and provenance; CSV encodes nested evidence as JSON columns. Models and
fusion parameters are traceable in each live result.

See [the runtime guide](../docs/LIVE_RUNTIME_GUIDE.zh.md) for configuration,
commands, input provenance, measured scope and remaining hardware validation.
