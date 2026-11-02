# Gate run summary

- Result: **GREEN**: all 5 gate(s) passed.
- Generated (UTC): `2026-10-26T05:14:12Z`
- Repository: `ba018bb38b11e727a74223b49dde48d1cdf3359d` on `fyp2/live-system`, working tree dirty (4 entries)
- Command: `python3 scripts/run_gates.py --out docs/evidence/2026-10-26/integration-gate-ba018bb`

| # | Gate | Status | Exit | Duration (s) | Skipped | Log |
|---|------|--------|------|--------------|---------|-----|
| 01 | build | PASS | 0 | 4.29 | - | [01-build.log](01-build.log) |
| 02 | pytest | PASS | 0 | 192.82 | 0 | [02-pytest.log](02-pytest.log) |
| 03 | vitest | PASS | 0 | 2.65 | - | [03-vitest.log](03-vitest.log) |
| 04 | tsc | PASS | 0 | 1.66 | - | [04-tsc.log](04-tsc.log) |
| 05 | eslint | PASS | 0 | 1.31 | - | [05-eslint.log](05-eslint.log) |
