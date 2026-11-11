# Gate run summary

- Result: **RED**: 1 of 5 gate(s) FAILED: **vitest**
- Generated (UTC): `2026-10-29T09:57:35Z`
- Repository: `afd8724c298e4b4f8288996e0f6b1c3915c2fbb8` on `fyp2/live-system`, working tree dirty (4 entries)
- Command: `python3 scripts/run_gates.py --out docs/evidence/2026-10-29/ui-scenario-sessions-gate`

| # | Gate | Status | Exit | Duration (s) | Skipped | Log |
|---|------|--------|------|--------------|---------|-----|
| 01 | build | PASS | 0 | 3.9 | - | [01-build.log](01-build.log) |
| 02 | pytest | PASS | 0 | 206.95 | 0 | [02-pytest.log](02-pytest.log) |
| 03 | vitest | **FAIL** | 1 | 3.16 | - | [03-vitest.log](03-vitest.log) |
| 04 | tsc | PASS | 0 | 1.87 | - | [04-tsc.log](04-tsc.log) |
| 05 | eslint | PASS | 0 | 1.65 | - | [05-eslint.log](05-eslint.log) |

## Failed gates

- **vitest**: `FAIL`, see [03-vitest.log](03-vitest.log)

## Cause (added after the run)

One source guard, `useLiveSession.test.ts` MODE_FILTER, still pinned the earlier design (scenario runs listed with Live sessions via `isLiveLike`), which this commit deliberately changes. The guard was updated to pin the new rule (`isSavedLiveSession`) in the follow-up commit; see the GREEN gate directory `ui-scenario-sessions-gate/`.
