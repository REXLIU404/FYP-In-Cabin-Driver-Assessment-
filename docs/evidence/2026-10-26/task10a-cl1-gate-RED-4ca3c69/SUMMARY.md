# Gate run summary

- Result: **RED**: 1 of 5 gate(s) FAILED: **pytest**
- Generated (UTC): `2026-10-26T04:53:16Z`
- Repository: `4ca3c69e6fae38c76635b360754ba0468755d0dd` on `fyp2/live-system`, working tree dirty (4 entries)
- Command: `python3 scripts/run_gates.py --out docs/evidence/2026-10-26/task10a-cl1-gate`

| # | Gate | Status | Exit | Duration (s) | Skipped | Log |
|---|------|--------|------|--------------|---------|-----|
| 01 | build | PASS | 0 | 5.45 | - | [01-build.log](01-build.log) |
| 02 | pytest | **FAIL** | 1 | 175.08 | 0 | [02-pytest.log](02-pytest.log) |
| 03 | vitest | PASS | 0 | 3.04 | - | [03-vitest.log](03-vitest.log) |
| 04 | tsc | PASS | 0 | 1.88 | - | [04-tsc.log](04-tsc.log) |
| 05 | eslint | PASS | 0 | 1.55 | - | [05-eslint.log](05-eslint.log) |

## Failed gates

- **pytest**: `FAIL`, see [02-pytest.log](02-pytest.log)
