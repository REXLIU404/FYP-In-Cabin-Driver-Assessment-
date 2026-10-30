# Stage 5 Step 1: rollback drill (2026-10-30)

`drill.py` (run at `1cd5660`, exit 0, `drill.log` / `drill.json`): the README's start command
(`python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8001`), port 8001, a throw-away SQLite
per start, no DRA_* variable inherited from the shell.

1. Candidate active (`DRA_ACTIVE_VISION=resnet18_search004_seed42`): `/api/models` models_loaded, vision
   `resnet18_search004_seed42` sha256 `5e226722...` (= its runtime manifest), telemetry XGBoost `9802cb06...`; one normal
   forward (Live session + one `/infer`, 201, assessed, provenance names the candidate).
2. Rollback: a FRESH process with `DRA_ACTIVE_VISION` unset: models_loaded, vision `stable_mobilenet_v3_large` sha256
   `b3a42e8d...` (= the frozen stable ONNX on disk), telemetry `9802cb06...`; one normal forward (201, assessed,
   provenance names the stable model).
3. No file under `ml/outputs` changed during the drill (94 files hashed before and after); port 8001 free at the end.

Result: PASS, 11/11 checks. The uvicorn logs show a graceful shutdown for both processes ("Application shutdown
complete", "Finished server process"); their return code -15 is uvicorn 0.48 re-raising the SIGTERM it handled.
Nothing was retrained or overwritten: rollback is the environment switch alone.
