# Gate run summary

- Result: **RED**: 1 of 5 gate(s) FAILED: **pytest**
- Generated (UTC): `2026-10-26T05:07:24Z`
- Repository: `5edd868a47806ea17fabf03d5f9c296109ae6989` on `fyp2/live-system`, working tree dirty (6 entries)
- Command: `python3 scripts/run_gates.py --out docs/evidence/2026-10-26/task10a-cl1-gate`

| # | Gate | Status | Exit | Duration (s) | Skipped | Log |
|---|------|--------|------|--------------|---------|-----|
| 01 | build | PASS | 0 | 3.85 | - | [01-build.log](01-build.log) |
| 02 | pytest | **FAIL** | 1 | 206.36 | 0 | [02-pytest.log](02-pytest.log) |
| 03 | vitest | PASS | 0 | 2.64 | - | [03-vitest.log](03-vitest.log) |
| 04 | tsc | PASS | 0 | 1.77 | - | [04-tsc.log](04-tsc.log) |
| 05 | eslint | PASS | 0 | 1.5 | - | [05-eslint.log](05-eslint.log) |

## Failed gates

- **pytest**: `FAIL`, see [02-pytest.log](02-pytest.log)
