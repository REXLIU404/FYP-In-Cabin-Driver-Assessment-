# G-W2-A gate evidence — RETROACTIVE (补档)

- **Gate:** G-W2-A (sprint plan `01_FYP2_Parallel_Sprint_Plan_W2_W7_v3`, §6; planned Friday 2026-10-16).
- **Gate commit:** `cbe573f` (`fyp2/live-system`, 2026-10-14 05:41 +0800) — the commit the 2026-10-15 W2 independent check verified.
- **Produced:** 2026-10-19, **after** the gate date, because the W2 logs had only been kept in a scratchpad. Run on an isolated `git archive cbe573f` copy with `scripts/run_gates.py` copied in from `ce45f53` (that script did not exist at `cbe573f`), `.venv` and `node_modules` linked to this worktree's, the three model files linked read-only. `SUMMARY.md` therefore names a throw-away commit `7ca480e` on `master`: that is the `git init` of the archive copy, whose content is exactly `cbe573f` plus `scripts/run_gates.py`. The "working tree dirty (1 entries)" line is the log directory being written.
- **Result:** GREEN — build PASS, pytest **584 passed / 0 skipped**, vitest **427 passed**, tsc 0, eslint 0; `freeze_manifest.txt`: models unchanged vs frozen baseline (`b3a42e8d…` / `196ca7b1…` / `9802cb06…`). Matches the 2026-10-15 independent check (pytest 584 / 0 skipped, vitest 427).

| Gate check (§6) | Where it is covered at `cbe573f` |
|---|---|
| No fabricated 0 / Low / NORMAL; single-modality degradation; zero effective weight → unavailable | `UT-FUS-03`, `UT-FUS-ZERO-WEIGHT`, `UT-AVAIL-01`, `EX-NULL-01`, `ST-STATUS-01` (all present, in `02-pytest.log` / `03-vitest.log` totals) |
| Trend / export / temporal contract | `UT-TREND-01`, `UT-EXPORT-01`, `UT-TIME-01..05` (present) |
| Full pytest / vitest / tsc / eslint | `02-pytest.log` … `05-eslint.log` |
| Baseline snapshot | `freeze_manifest.txt` |
| Acceptance reports | `docs/fyp2/implementation/task-0{1..6}-acceptance.zh.md`, `task-07-acceptance.zh.md`, `phase1-0{1..6}-*-acceptance.zh.md` |

The Track B half (G-W2-B) lives in the ML repository: `ml/outputs/runs/w2_preparation_20261015/` and `docs/fyp2/ml/ML_TRACK_PROGRESS.md`.
