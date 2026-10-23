# Prototype Tests

This folder holds the manual acceptance flow for the prototype. It was written for
FYP1 against the prepared-probability replay; **since FYP2 Task 9 the system under
test is Live**, and the flow below is the Week 7 acceptance checklist.

## What is under test

```
camera frame + prepared raw telemetry
   -> POST /api/sessions/{id}/infer
   -> trained MobileNetV3 (ONNX) + trained XGBoost
   -> freshness, EMA, late fusion, Alert FSM          (all on the backend)
   -> SQLite
   -> the five dashboard views                          (they only render the saved record)
```

Only the camera is a live sensor. The telemetry is a **prepared raw-feature replay**
(`ai/prototype-data/prepared_sessions/session_001/telemetry.csv`, 25 rows, one row per
2 s, wrapping) that goes through the trained XGBoost on the server like any other
input. It carries no probabilities.

The earlier five-view checklist walked the prepared-probability replay (now labelled
"Prepared replay (legacy, test-only)" in the Data mode menu). That route is no longer
the acceptance route: `ST-REPLAY-01` is **replaced by the Live end-to-end below** for
this phase. Nothing was deleted: the replay stays in the app for regression tests and
backward compatibility, and `npm test` still covers it. A reload always starts on
Live; the replay is entered only by choosing it in the page.

## Automated gates

Run from the repository root:

```bash
export PYTHONDONTWRITEBYTECODE=1
(cd backend && TMPDIR=$(mktemp -d) PYTHONPATH=. ../.venv/bin/python -m pytest tests -q -p no:cacheprovider)
./node_modules/.bin/vitest run --no-cache
./node_modules/.bin/tsc --noEmit
./node_modules/.bin/eslint .
```

`npm test` does not type-check; `tsc` has to be run on its own. Since Task 10 the
pytest run includes a scripted Live end-to-end (one uvicorn serving `dist/` and `/api`,
Chromium with a fake camera): `backend/tests/test_live_e2e.py` and
`backend/tests/test_live_single_branch.py`. `live_e2e.md` maps each step of the
checklist below to the test that automates it and lists what is still manual (a
physical camera, how the pages look, target hardware). Step 8, including a real
backend stopped mid-session and restarted on the same database, is automated by
`backend/tests/test_live_backend_reach.py`.

## Manual Live end-to-end checklist

Preconditions: the trained artifacts are in `ml/outputs/`; dependencies are installed
(`npm ci`, `.venv`); use a throwaway database so the run leaves nothing in a
development one.

```bash
npm run build
DRA_DATABASE_URL=sqlite:////tmp/week7-live.db \
  .venv/bin/python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000 (UI and API share this one origin). Keep with the
evidence: the command, the date, the model SHA-256 values shown under **Loaded model
versions**, and the database path.

1. **Backend ready.** `GET /api/models` answers `models_loaded: true` and names the
   MobileNetV3 and XGBoost versions. The page is on **Live trained models**.
2. **Start Monitoring.** Allow the camera. The status line shows the camera, the
   achieved inference rate and the request round trip.
3. **Accepted requests.** At least **N** `POST /api/sessions/{id}/infer` calls answer
   **201**, and each `request_id` is recorded (DevTools network tab, or the saved
   records). N is 30 for a smoke check. A full run lasts long enough for the
   telemetry cursor to pass rows 14 and 17 (26 s and 32 s) and for the session to
   exceed 500 windows (about 60 s at the default target of 10 requests/s; the
   achieved rate may be lower, so count the windows rather than the seconds).
4. **Five views read the backend's records.** Live Monitor, Signal Inspector, Risk
   Trends, Explanation and Configuration show values that equal
   `GET /api/sessions/{id}/risk/latest` and the saved window (same `window_id`, same
   RiskScore / RiskLevel / DominantEvidence / AlertSeverity / SystemHealth). A window
   without an assessment shows **Unavailable**, never `0` or `Low`.
5. **A flag survives.** Flag a window in Signal Inspector; the change goes out as
   `PATCH /api/sessions/{id}/windows/{window_id}/flag`. Reload, load the saved
   session: the flag is still set.
6. **Export covers the whole session.** In Live mode **Export JSON / CSV** in
   Configuration downloads the server's `GET /api/sessions/{id}/export`, which
   streams every persisted window. The number of records equals the session's
   `total_windows`, which is larger than the 500 windows the page keeps in view. Each
   record carries `assessment_available`, `SystemHealth`, `modality_freshness` and the
   `provenance`, including `vision_expired` / `vision_age_s` / `telemetry_expired` /
   `telemetry_age_s`.
7. **Pause, retry and restart follow the policy.**
   - _Pause_ stops the loop without an error; _Start Monitoring_ resumes the same
     session.
   - _New Session_ creates a new session; the earlier windows stay with the old one.
   - _Stop Camera_ does **not** stop monitoring: requests carry on without an image
     (vision `missing`, DEGRADED, "Partial evidence"), and the page says the camera
     was stopped. Unplugging the camera reads differently ("disconnected").
   - With the camera off, rows 14 and 17 of the telemetry have no input either: those
     windows are UNAVAILABLE (the four risk fields empty, alert timers suspended) and
     the loop recovers on the next row.
8. **An injected transport fault stops after three tries and can be recovered by
   hand.** Stop the backend while monitoring. The page shows `Delivery 1 of 3 failed…
Retrying automatically…`, then, after the third delivery, a **Monitoring stopped**
   panel with the category, the request id and `Deliveries: 3 of 3`. Restart the
   backend on the same database and press **Retry**: the same request is re-sent to
   the same session, monitoring resumes, and the saved windows have no duplicate
   `request_id` and no gap in `window_id`. (`GET /api/faults` lists what the server
   saw; a backend that was down saw nothing.)

What this checklist does not claim: field accuracy of the frontal camera, performance
on the target hardware, or that the 3 s freshness threshold is validated (it is a
design threshold).
