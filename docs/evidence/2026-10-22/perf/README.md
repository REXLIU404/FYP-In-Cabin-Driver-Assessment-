# G-W6-A gate evidence (sprint plan v3 W6) - E2-E5 runners excepted

- **Code commit:** `2897000` (`fyp2/live-system`). This is the final code of the W5/W6 system-test plan, after the independent whole-branch review and its fix pass.
- **Regression:** the full gates on a **fresh clone** of `2897000` (ST-COLDSTART-01, `docs/evidence/2026-10-22/coldstart-final/`), with `DRA_REQUIRE_MODELS=1`.

| Gate | Result |
|---|---|
| build | PASS |
| pytest | **1028 passed, 0 skipped**, 1 deselected (ST-LONG-01, run separately below) |
| vitest | 922 passed |
| tsc | 0 |
| eslint | 0 |
| serve from the clean clone | health 200, model hashes `b3a42e8d` / `9802cb06`, dashboard 200 |
| servers left behind | none (checked by the script) |

**Measurement scope:** one development machine (Apple M2, 8 cores, 24 GB), Chromium 148 with the fake camera (20 fps pattern), the frozen models, the app's own loop (target 10 requests/s, one in flight). These numbers say nothing about target hardware, a physical camera or real faces.

| G-W6-A check | Evidence |
|---|---|
| Regression all green | The table above. Every earlier browser test is included: parts 2a / 2b, FIX-BACKEND-REACH, ST-SESSION-01 |
| Long-session persistence / export (`ST-LONG-01`) | `long-session/` (commit `2897000`): 15 min, **8,867 windows** at 9.85 Hz. Database, session total, every page of `GET /windows`, JSON and CSV export all hold exactly 1..N. 112 sampled windows agree field by field across the five homes. The page keeps 500. No fault, re-send, stop panel or console error. Recorded: round trip p50 24-33 ms per minute; render p50 3 ms; **JS heap (CDP) 16.4-29.1 MB with no upward trend**; DOM nodes 1,058-1,418; database 43.4 MB |
| `PERF-01`: capture -> render p50 / p95 | `perf01.json` (commit `4f38cfc`), 600 windows at 9.8 Hz after 20 warm-up. capture -> render p50 28 ms, **p95 39 ms**. The target <= 1 s is judged on p95 per the matrix addendum (E4, D07): **met**. Max 280 ms, information only. Network incl. server p50 24 / p95 35 ms; render p50 3 / p95 5 ms. Server-Timing medians: total 16.7, vision 8.6, preprocess 2.6, telemetry 1.1, commit 0.9, fusion 0.1 ms (read off the network) |
| Review the 3 s threshold + 2 / 3 / 5 s sensitivity | Same file. Windows whose telemetry evidence was older than 2 s: **0.89%** (5 of 560); 3 s and 5 s: 0%. Vision age p95 0.082 s. **Telemetry age is 0-2 s by construction**: the prepared replay's acquisition time is the start of its 2 s sample, so it is not a sensor age. 3 s remains a design threshold, not a validated safety threshold |
| `PERF-02`: logging completeness, two denominators | `perf02.json` (commit `66327ee`). Injected faults: two deliveries lost in transit; the backend stopped mid-session and restarted on the same database and port, then Retry; one request rejected with 422. 211 logical requests; 210 stored windows + 1 `input_validation` fault. **D1 (server-seen) 211/211 = 100%; D2 (all logical requests) 211/211 = 100%.** No duplicate request id. 2 unavailable windows counted as accepted (CNT default) |
| E2-E5 runners smoked | **NOT DONE.** The pairing rule for constructed scenarios awaits the supervisor's decision D06. Done towards E3 / E4: the E3 freshness grid (`backend/tests/test_e3_freshness_grid.py`) and the measurements above |

## Corrections made after the independent review

- **JS heap.** The first ST-LONG-01 run (`5040e9d`) reported the JS heap "flat at 23.1 MB". That was an artefact: `performance.memory` without `--enable-precise-memory-info` is bucketed, and all 15 samples read exactly 23,100,000. The test now reads `Performance.getMetrics` through CDP (`349ee61`), and the 15-minute run was redone (`2897000`). The figures above are from the redone run.
- **PERF-01 figures.** The message of commit `4f38cfc` quotes four figures from an earlier run: 1.07%, 0.078 s, 26 ms and 4 ms. The committed `perf01.json` says 0.89%, 0.082 s, 24 ms and 3 ms. Only the JSON counts. Runs after `e03ed41` carry their caveats in the JSON itself.
