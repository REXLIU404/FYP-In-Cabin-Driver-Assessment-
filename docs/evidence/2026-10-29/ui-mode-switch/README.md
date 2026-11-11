# A Data mode change leaves the session; no "not live" wording: screenshots (2026-10-29)

Commit `e26e32a`. Fresh-clone gate: `../mode-switch-coldstart-e26e32a/` (ST-COLDSTART-01 PASS; pytest 1359 passed / 0 skipped / 8 deselected, vitest 1043). It ran in a clean clone because the integration working tree held another session's uncommitted files at the time.

| File | What it shows | In git |
|---|---|---|
| `01-live-vehicle-signals.png` | Live: Vehicle Signals with no disclaimer sentence | yes |
| `02-after-switch-to-scenario.png` | Live session paused, Data mode switched to the scenario: the Live session is gone from the screen | **no** (State Farm frame) |
| `03-scenario-running.png` | Scenario running: badge `CONSTRUCTED SCENARIO`, no "not live" anywhere | **no** (State Farm frame) |
| `04-scenario-vehicle-signals.png` | Scenario telemetry panel without the sentence | yes |
| `05-after-switch-to-live.png` | Scenario paused, switched back to Live: the scenario run is gone, no topbar badge | yes |

Run of `capture.py`: after Live -> scenario the Live session id is not on the page and there is no session strip; the badge reads `CONSTRUCTED SCENARIO` and the page has no "not live"; after scenario -> Live the scenario session id is not on the page, no topbar badge, no session strip; no console or page errors.
Reproduce: `.venv/bin/python docs/evidence/2026-10-29/ui-mode-switch/capture.py <out dir>` from the repository root.
Checks (pass/fail): `ai/src/liveLoop.test.ts` (clear), `frontend/src/utils/dataMode.test.ts`, render tests, `backend/tests/test_constructed_scenario_e2e.py::test_switching_the_data_mode_leaves_the_session`.
