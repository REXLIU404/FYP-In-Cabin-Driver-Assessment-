# Live end-to-end: what the automated tests cover, and what a person still has to do

`prototype-tests/README.md` holds the manual Live acceptance checklist (Week 7). Since Task 10
(parts 2a and 2b) most of it is scripted. This file maps **each manual step to the automated test
that covers it**, says exactly what that test asserts, and lists what is still manual.

The automated tests use a **fake camera** (Chromium's `--use-fake-device-for-media-stream`, a
moving test pattern), the **frozen trained models** and the prepared telemetry replay. They do not
prove anything about a physical camera, real lighting, a real face or the target hardware.

## Running them

```bash
export PYTHONDONTWRITEBYTECODE=1
(cd backend && TMPDIR=$(mktemp -d) PYTHONPATH=. ../.venv/bin/python -m pytest tests -m e2e -p no:cacheprovider -v)
```

- `-m e2e` selects the browser tests (`test_live_e2e.py`, `test_live_single_branch.py`); they are
  also part of the plain full run. They need `npm`, the Playwright Chromium and the three model files.
- Each pytest session first runs `npm run build` and then starts **one** uvicorn that serves the API
  and the built `dist/` on a throw-away SQLite database. The development database is never touched.
- Without the model files they are **skipped loudly** (a banner lists them); with
  `DRA_REQUIRE_MODELS=1` each skip is a failure. A missing `npm` or browser is a failure, never a skip.
- `DRA_E2E_EVIDENCE_DIR=<dir>` makes `test_live_e2e.py` leave the screenshots of the five views, the
  session's JSON / CSV export and the rVFC measurement there (the G-W4-A archive). Unset, nothing is written
  outside the test's tmp directory.
- Duration (measured on the development machine, 8 cores): the 12 tests of `test_live_e2e.py` take about 40 s, the 18 of
  `test_live_single_branch.py` about 90 s (the T-CONTINUITY run alone is a full 56 s replay lap and wrap).

## Manual step -> automated test

IDs below are the steps of the manual checklist in `prototype-tests/README.md`.

| # | Manual step | Automated by | What the automation asserts | Still manual |
|---|---|---|---|---|
| 1 | Backend ready; `GET /api/models`; page is on Live | `TestStLiveE2E01::test_02_contract` | `GET /api/models` reports the vision and telemetry SHA-256 of the frozen baseline; every window is `LIVE_MODEL_RUNTIME`; the page starts in Live mode (Start Monitoring creates a Live session with no mode change) | The "Loaded model versions" text under the status panel is not read |
| 2 | Start Monitoring, allow the camera, status line | `TestStLiveE2E01` (fake camera, permission granted by the context); `test_e2_an_unexpected_camera_loss_…` and `TestStBranchTContinuity::test_01` read the camera status line | Start Monitoring works; the camera line says `idle · stopped by you`, `error · disconnected`, or (`error` or `denied`) `· failed to start` as it should | The browser's real permission prompt; the inference-rate and round-trip numbers on the status line are not asserted (E3 records timings, with no threshold) |
| 3 | At least N accepted `infer` requests, every `request_id` recorded; a run long enough for rows 14 and 17 and for more than 500 windows | `TestStLiveE2E01::test_01`; `TestStBranchTContinuity` (a run of about 56 s that passes both empty rows, wraps into the second lap and is held until it has more than 510 windows) | 201 for every request; `window_id` 1..N without a gap; unique `request_id`; every `X-Attempt-Index` 1; the database holds exactly what the browser received; telemetry positions 13 and 16 appear and the replay wraps; `test_06`: more than 500 windows | Watching the DevTools network tab |
| 4 | Five views read the backend's records; an unassessed window says "Unavailable" | `TestStLiveE2E01::test_05` (Live Monitor = `GET /risk/latest`, IT-UI-01), `test_06` (Signal Inspector, Risk Trends, Explanation, Configuration against the recorded windows); part 2b repeats the Live Monitor oracle on single-branch and unavailable windows (`ST-BRANCH-*`, the last window of `ST-BRANCH-ZERO` is unavailable) | Every number the page shows equals the stored window in the dashboard's display format (independent half-up rounding); the unavailable banner and the "No input" branch cards read as specified | The Signal Inspector / Risk Trends / Explanation views for an **unavailable** window are covered only by the vitest display tests, not in the browser |
| 5 | A flag survives | `TestStLiveE2E01::test_07` | Flag through the UI -> `PATCH …/flag` -> database -> API -> JSON export -> CSV export -> Risk Trends; Unflag restores all five | Reloading the page and loading the saved session to see the flag again |
| 6 | Export covers the whole session | `TestStLiveE2E01::test_06` (the downloaded files equal the server's export byte for byte), the reconciliation of every run (`assert_reconciled`) and `TestStBranchTContinuity::test_06` | JSON and CSV contain every persisted window, all 21 contract fields, provenance key by key, floats exactly; in a session of more than 500 windows the Signal Inspector lists exactly the newest 500 while both exports carry windows 1..N | Opening the files in a spreadsheet; the visible-history counter text |
| 7a | Pause; Start resumes the same session | Pause is the quiesce step of every run (`LiveRun.settle`) | Pause stops the loop without a fault | Pressing Start Monitoring again after a Pause and checking the session id stays |
| 7b | New Session | `test_e2_a_failed_new_session_makes_retry_create_a_new_session` | A failed New Session shows the setup panel; Retry creates a new session with windows numbered from 1; the old one gets nothing more | — |
| 7c | Stop Camera does not stop monitoring; unplugging reads differently | `test_e2_an_unexpected_camera_loss_…`, `TestStBranchTSmoke`, `TestStBranchV`, `TestStBranchZero` | Requests carry on without an image; vision `missing`, `DEGRADED`, "Partial evidence"; the two camera texts differ and neither shows a stop panel; the single-branch score is the branch's own probability | Physically unplugging a camera |
| 7d | With the camera off, rows 14 and 17 are UNAVAILABLE and the loop recovers | `TestStBranchTContinuity` | Those windows have all four risk fields null, `SystemHealth = UNAVAILABLE`, no alert; the next row is `DEGRADED` again; the latched `HIGH_ALERT` is kept | — |
| 8 | Transport fault: stop after three tries, recover by hand | `test_e2_transport_faults_stop_the_loop_and_retry_resumes_the_same_session` | The stop panel text (`Deliveries: 3 of 3`, request id); Retry re-sends the same request (`X-Attempt-Index` 4, byte-identical), keeps the session, stores the request once, and the loop resumes | Stopping and restarting the real backend process on the same database; `GET /api/faults` (server side: `test_fault_events.py`) |

## Automated coverage the manual list never had

| Test | What it proves |
|---|---|
| `TestStBranchTSmoke` (ST-BRANCH-T-SMOKE) | After Stop Camera each window scores `round_half_up(100 x P_telemetry_anomaly, 1)`, with `P_telemetry_anomaly` **equal to the frozen XGBoost value of its replay row** (`backend/tests/fixtures/telemetry_pt_by_row.json`, bound to the model's SHA-256) |
| `TestStBranchTContinuity` (ST-BRANCH-T-CONTINUITY) | From a camera that never started: no gap, no stop, no retry, no fault; replay rows map to `telemetry_seq % 25` across the wrap; the alert sequence follows the R10 rule (NORMAL, CAUTION, HIGH_ALERT in the second High sample, latch kept through Low runs and unavailable windows) |
| `TestStBranchV` (ST-BRANCH-V) | Vision only: score = `round_half_up(100 x P_distraction, 1)`; the EMA chain moves on NEW frames only, REPEATs show the value they were registered with, and Stop Camera -> Start Camera reseeds the chain |
| `TestStBranchZero` (ST-BRANCH-ZERO) | With Vision Weight 1.00 / Telemetry 0.00, a Stop Camera window is UNAVAILABLE and never `100 x P_t` |
| `test_e3_rvfc_behaviour_on_the_fake_camera_is_recorded` | `requestVideoFrameCallback` behaviour and capture timings (recorded, no threshold) and, since part 2b, the five-way reconciliation on the default 20 fps camera |

## Still manual (nothing in the automation can stand in for it)

1. **A physical camera**: the permission prompt, whether the browser provides `captureTime`, the frame rate,
   the capture cost on real faces (the fake picture is a small synthetic pattern), lighting and viewpoint.
2. **How the pages look**: layout, readability, colours, the wording of every notice.
3. **Real stop and restart of the backend process** (README step 8) and a reload followed by *Load saved session*
   (steps 5, 7a).
4. **Performance on the target hardware**: the automation records timings on a development machine and
   asserts no threshold (PERF-01 is separate).
5. **Frontal-camera accuracy of the models**: out of scope here and not claimed by any test.

`prototype-tests/README.md` keeps the manual checklist; this file is the map from it to the automated tests.
