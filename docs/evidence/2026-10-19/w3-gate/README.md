# G-W3-A gate evidence — closed early

- **Gate:** G-W3-A (sprint plan v3 §6; planned Friday 2026-10-23). Closed on Monday 2026-10-19 with the user's approval, because every Week 3 Track A item was already done.
- **Gate commit:** `ce45f53` (`fyp2/live-system`). Logs produced in the real worktree by `scripts/run_gates.py --out docs/evidence/2026-10-19/w3-gate`; "working tree dirty (1 entries)" in `SUMMARY.md` is this evidence directory being written.
- **Result:** GREEN — build PASS, pytest **922 passed / 0 skipped**, vitest **870 passed**, tsc 0, eslint 0; `freeze_manifest.txt`: models unchanged vs frozen baseline.

| Gate check (§6) | Evidence |
|---|---|
| Task 8 accepted (bounded retry, frozen payload, visible stop) | `docs/fyp2/implementation/task-08-acceptance.zh.md`; `liveLoop.test.ts`, `retryPolicy.test.ts`, `IT-RETRY-IDENTITY`, `IT-RETRY-EMPTY`, `IT-RETRY-TEXTS` |
| Ruling A: expired evidence scores as missing, reason kept; both expired → UNAVAILABLE | `p0-d13-ruling-a-acceptance.zh.md`; `IT-RETRY-STALE` and `IT-LIVE-AGE` (updated), `IT-EXPIRY-REASON` / `IT-EXPIRY-SENSITIVITY` / `IT-EXPIRY-NO-STALE` (the plan's `IT-EXPIRY-01`), F1 matrix test `frontend/src/data/missingCases.test.ts` |
| Live is the default mode; replay labelled legacy; Live path never imports prepared probability | `task-09-acceptance.zh.md` (source-level scope guard in `preparedRawTelemetry.test.ts`) |
| Deterministic telemetry cursor (K1, moved into R10) | `r10b-frontend-acceptance.zh.md` |
| Full pytest / vitest / tsc / eslint + build | `01-build.log` … `05-eslint.log` |

Ahead of plan (Week 4 content already done at this commit): R10 approved and implemented (`r10a-backend-acceptance.zh.md`, `r10b-frontend-acceptance.zh.md`); Task 10 part 1 (`task-10-part1-acceptance.zh.md`: typecheck gate, skip reporting, stage timing, `FYP_DATA_ROOT` guard, export guard). Still open for Week 4: Task 10 part 2 (`ST-LIVE-E2E-01`, `ST-BRANCH-*`).

Track B (G-W3-B) is in the ML repository (`docs/fyp2/ml/ML_TRACK_PROGRESS.md`: Week 3 P1 `VERIFIED_PASS`, commit `644a930`; vision search budget `APPROVAL_PENDING`).
