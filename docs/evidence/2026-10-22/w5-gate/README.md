# G-W5-A gate evidence (hard gate, sprint plan v3 W5) - closed early

- **Gate commit:** `5040e9d` (`fyp2/live-system`). Planned date: Friday 2026-11-06; closed 2026-10-22.
- **Logs:** `run_gates.py --out docs/evidence/2026-10-22/w5-gate` with `DRA_REQUIRE_MODELS=1`, on committed code, in the real worktree whose `.venv` is now its own virtualenv built from `backend/requirements.lock.txt`. "working tree dirty" in `SUMMARY.md` is this directory being written.
- **Result:** GREEN.

| Gate | Result |
|---|---|
| build | PASS |
| pytest | **1021 passed, 0 skipped, 1 deselected**. The deselected one is ST-LONG-01, which runs only with `-m long`; its 15-minute run is archived separately |
| vitest | 922 passed |
| tsc | 0 |
| eslint | 0 |

`freeze_manifest.txt`: all three model files MATCH the frozen baseline.

| G-W5-A check | Evidence |
|---|---|
| Session lifecycle: start / pause / resume / switch / restart; a loaded session opens on its newest window | `ST-SESSION-01`: `backend/tests/test_live_session_lifecycle.py` (8 tests, `59f91a7`). Four product mutations, each red: selection pinned to window 1; Start after loading appends to the loaded session; resume restarts the telemetry cursor; a pin is not kept. The selection rule is in `frontend/src/utils/selection.ts` (`62f13fb`, 4 vitest) |
| Clean start from a fresh checkout | `ST-COLDSTART-01`: `scripts/coldstart_check.sh`, run on `fd2a8a5` and PASS (`docs/evidence/2026-10-22/coldstart/`). Clone, venv from the lock file, `npm ci`, models linked, full gates (pytest 987 / 0 skipped, vitest 922), then the dashboard served from the clean clone |
| The five views read backend records | `test_live_e2e.py::TestStLiveE2E01::test_05` / `test_06` (part 2a). `ST-SESSION-01` test_05: the Inspector and the Explanation of a loaded session |
| latest / flag / full export | `TestStLiveE2E01` test_04 (five homes, field by field), test_05 (`/risk/latest` = the Live Monitor), test_07 (flag through the UI to both exports and back). `TestStBranchTContinuity::test_06`: the export carries more than the page's 500 windows. `ST-LONG-01`: 7,794 windows, `docs/evidence/2026-10-22/perf/long-session/` |
| ST-LIVE-E2E-01 + full suite | `02-pytest.log` (includes every browser test of parts 2a / 2b, FIX-BACKEND-REACH and ST-SESSION-01) |
| No open P0 | P0-D13 closed (`p0-d13-ruling-a-acceptance.zh.md`); D01 / D02 closed in Tasks 2-8. Still open, all P1: R14 (DominantEvidence semantics, awaiting the user); E2 / E5 (pairing awaits supervisor decision D06); the Task 10A provider and evaluator (W6 stretch) |
| Feature freeze recorded | The Live system's user-visible features are frozen at this commit. **One user-approved exception:** the "Constructed scenario" mode (2026-10-22). It is developed on `fyp2/constructed-scenario` and merged only after its own full gate run. Results cited in the report stay Live-only |
| Task 10A manifest schema handed to Track B (W5 Monday) | `docs/fyp2/handoff/task-10a-runtime-manifest.md`, `backend/app/runtime_manifest.schema.json`, `scripts/validate_runtime_manifest.py` (`095424f`, 18 tests) |

Also in this gate (matrix addendum 2026-10-22): the E3 freshness grid, `backend/tests/test_e3_freshness_grid.py` (`12a0f98`, 14 tests). An expired branch scores exactly like a missing one, and its reason is kept.
