# Gate run summary

- Result: **RED**: 1 of 5 gate(s) FAILED: **pytest**
- Generated (UTC): `2026-10-29T04:35:17Z`
- Repository: `dd7b9d50ca3bae5419a01e4373f406cd31902de2` on `fyp2/live-system`, working tree dirty (4 entries)
- Command: `python3 scripts/run_gates.py --out docs/evidence/2026-10-29/merge-ds2-gate`

| # | Gate | Status | Exit | Duration (s) | Skipped | Log |
|---|------|--------|------|--------------|---------|-----|
| 01 | build | PASS | 0 | 4.14 | - | [01-build.log](01-build.log) |
| 02 | pytest | **FAIL** | 1 | 202.3 | 0 | [02-pytest.log](02-pytest.log) |
| 03 | vitest | PASS | 0 | 2.63 | - | [03-vitest.log](03-vitest.log) |
| 04 | tsc | PASS | 0 | 1.62 | - | [04-tsc.log](04-tsc.log) |
| 05 | eslint | PASS | 0 | 1.51 | - | [05-eslint.log](05-eslint.log) |

## Failed gates

- **pytest**: `FAIL`, see [02-pytest.log](02-pytest.log)
