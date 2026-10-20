# G-W4-A gate evidence (Task 10 part 2b)

- **Gate:** G-W4-A (sprint plan v3, Week 4 Track A): the Live system end to end, in the browser, on the frozen models.
- **Gate commit:** `ae1c197` (`fyp2/live-system`). Logs were produced in the real worktree, on committed code, by
  `DRA_REQUIRE_MODELS=1 python3 scripts/run_gates.py --out docs/evidence/2026-10-20/live-e2e`. "working tree dirty (1 entries)" in
  `SUMMARY.md` (and in `freeze_manifest.txt`) is this evidence directory being written, not uncommitted code.
- **Result:** GREEN. build PASS; pytest **951 passed, 0 skipped** (`DRA_REQUIRE_MODELS=1`: "no model-dependent test was skipped");
  vitest **870 passed**; tsc 0; eslint 0; `freeze_manifest.txt`: all three model files MATCH the frozen baseline.
  Baseline before this item was pytest 934 / vitest 870; the +17 are the four `ST-BRANCH-*` tests (3 + 5 + 5 + 4).

| G-W4-A check | Where it is proven | Report |
|---|---|---|
| Browser -> API -> DB -> latest -> UI -> JSON / CSV agree, row by row (keyed by `window_id`; every window's `request_id` is the one the browser sent, unique, and present in all five homes) | `backend/tests/test_live_e2e.py::TestStLiveE2E01::test_04_five_homes_agree_on_every_field_of_every_window` (5 fps camera, NEW and REPEAT frames) and `::test_05_the_latest_panel_shows_risk_latest` (IT-UI-01); `::test_01_…` (request id == provenance request id, DB holds exactly the windows received); `::test_e3_rvfc_behaviour_on_the_fake_camera_is_recorded` (the same reconciliation on the default 20 fps camera, every frame NEW); the reconciliation tail of every ST-BRANCH test (`assert_reconciled` + `assert_ui_shows_latest`): `TestStBranchTSmoke::test_03`, `TestStBranchTContinuity::test_05`, `TestStBranchV::test_05`, `TestStBranchZero::test_04`. Artifacts of one E1 run: `session-export.json`, `session-export.csv` (60 windows each, same ids), `screenshots/01-05`. Mutation B-M10 (CSV drops the `request_id` column) turns E3 and E1 red | `task-10-part2a.md`, `task-10-part2b.md` |
| Single-branch behaviour is correct | `backend/tests/test_live_single_branch.py`: `ST-BRANCH-T-SMOKE` (score = `round_half_up(100 x P_t, 1)`, P_t equal to the frozen XGBoost value of its replay row), `ST-BRANCH-T-CONTINUITY` (no camera from the first request, a full 25-row lap and the wrap, R10 alert sequence, rows 13 / 16 UNAVAILABLE and recovery, loop never stops), `ST-BRANCH-V` (vision only, NEW-only EMA, reseed after Stop / Start Camera), `ST-BRANCH-ZERO` (Vision Weight 1.00: after Stop Camera nothing is scored). Frozen table: `backend/tests/fixtures/telemetry_pt_by_row.json` (bound to `xgb_telemetry.json` 9802cb06, made by `make_telemetry_pt_fixture.py`). Mutations B-M1..B-M9 in `mutations.txt` | `task-10-part2b.md` |
| Failure and recovery still hold | `ST-FAIL-01..04`, `ST-RECOVER-01`, `IT-OUTCOME-01` in `backend/tests/test_fault_events.py`; `IT-RETRY-IDENTITY` in `backend/tests/test_retry_contract.py`; the three E2 tests of `test_live_e2e.py` (`test_e2_transport_faults_stop_the_loop_and_retry_resumes_the_same_session`, `test_e2_a_failed_new_session_makes_retry_create_a_new_session`, `test_e2_an_unexpected_camera_loss_and_stop_camera_read_differently_and_neither_stops_the_loop`). All in the 951 passed of `02-pytest.log` | `task-07*-acceptance.zh.md`, `task-08-acceptance.zh.md`, `task-10-part2a-acceptance.zh.md` |
| No duplicate writes | E1 `test_01` (unique request ids; the database holds exactly the windows the browser received); E2 transport test (after Retry the first request id has exactly 1 row; no second session); `IT-RETRY-IDENTITY` (a re-send after a lost response changes nothing; same id with another payload is 409); every ST-BRANCH run (`assert_clean_run`: window ids 1..N without a gap, request ids unique, every `X-Attempt-Index` 1, `fault_events` 0) | `task-08-acceptance.zh.md`, `task-10-part2b.md` |
| Model hashes unchanged | `freeze_manifest.txt` (onnx `b3a42e8d…`, pt `196ca7b1…`, xgb `9802cb06…`, all MATCH); E1 `test_02_contract` (every window's provenance SHA-256, `GET /api/models` and the disk SHA-256 of the three files against the frozen literals); `Frozen.verify()` in the ST-BRANCH tests (fixture hash == disk == literal); `DRA_REQUIRE_MODELS=1` so no model-dependent test could be skipped | `task-01-acceptance.zh.md` |

## Files

| File | What it is |
|---|---|
| `SUMMARY.md`, `01-build.log` … `05-eslint.log` | `run_gates.py` output: argv, env, tool versions, exit code, skip count (0) and the complete stdout / stderr of each gate |
| `freeze_manifest.txt` | `scripts/freeze_manifest.py`: git state, model hashes (all MATCH), data split hashes, dependency versions |
| `e2e-evidence-run.log` | `DRA_E2E_EVIDENCE_DIR=<this dir> pytest tests/test_live_e2e.py -v -s`: 12 passed, with the `E3-MEASUREMENT` line |
| `screenshots/01-live-monitor.png` … `05-configuration.png` | the five views at the end of the E1 run (fake camera pattern; 60 windows) |
| `session-export.json`, `session-export.csv` | the bytes the page downloaded for that session (equal, byte for byte, to the server's export; checked by `test_06`) |
| `.gitattributes` | keeps those two exports byte for byte as downloaded (the CSV exporter writes CRLF; the machine's `core.autocrlf=input` would otherwise rewrite it) |
| `rvfc-measurement.json` | E3: `requestVideoFrameCallback` behaviour and capture timings on the fake camera (recorded, no threshold) |
| `mutations.txt` | Task 10 part 2b mutation runs in isolated copies: patch, red tests, first assertion, byte-compare of the restore |

## What this does not show

The browser tests use Chromium's fake camera (a moving pattern), the frozen trained models and the prepared telemetry replay.
They say nothing about a physical camera, real lighting or faces, the frontal-camera accuracy of the models, or performance on
the target hardware (E3 records timings and asserts no threshold; PERF-01 is separate). `prototype-tests/live_e2e.md` lists
what a person still has to check by hand.
