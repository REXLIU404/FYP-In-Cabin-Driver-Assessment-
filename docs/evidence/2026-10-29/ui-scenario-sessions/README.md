# Saved-session picker is Live-only: screenshots (2026-10-29)

User request: the Constructed demo scenario mode must not offer "Saved live sessions". Commits `afd8724` and `808a5d5`; gate `../ui-scenario-sessions-gate/` (GREEN). The RED run of `afd8724` is in `../ui-scenario-sessions-gate-RED-afd8724/`.

| File | What it shows | In git |
|---|---|---|
| `01-live-picker-shown.png` | Live mode: Refresh saved sessions + Saved live sessions shown | yes |
| `02-scenario-picker-hidden.png` | Scenario mode (viva_v1 loaded): only Data mode and Scenario | **no**: it shows a State Farm frame, and dataset images are never committed. Regenerate with the script |
| `03-scenario-empty-hint.png` | Scenario mode, empty Signal Inspector: "Start the scenario to inspect its evidence." | yes |
| `04-back-to-live-picker-shown.png` | Back to Live: the picker is shown again | yes |

Run of `capture.py`: controls (refresh, picker) = (1, 1) in Live, (0, 0) in the scenario, (1, 1) back in Live; no console or page errors.
Reproduce: `.venv/bin/python docs/evidence/2026-10-29/ui-scenario-sessions/capture.py <out dir>` from the repository root (throw-away server and SQLite, random port; reads `demo/bundles/viva_v1`).

The screenshots are not a pass/fail judgement. The checks are `frontend/src/utils/dataMode.test.ts`, `frontend/src/hooks/useLiveSession.test.ts` (MODE_FILTER) and `backend/tests/test_constructed_scenario_e2e.py`.
