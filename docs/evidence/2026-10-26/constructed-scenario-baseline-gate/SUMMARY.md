# Gate run summary

- Result: **GREEN**: all 5 gate(s) passed.
- Generated (UTC): `2026-10-26T11:42:41Z`
- Repository: `911c1a469aa6fedb6ddfbac5908b620242d56128` on `fyp2/constructed-scenario`, working tree dirty (1 entries)
- Command: `python3 scripts/run_gates.py --out docs/evidence/2026-10-26/constructed-scenario-baseline-gate`

| # | Gate | Status | Exit | Duration (s) | Skipped | Log |
|---|------|--------|------|--------------|---------|-----|
| 01 | build | PASS | 0 | 3.82 | - | [01-build.log](01-build.log) |
| 02 | pytest | PASS | 0 | 171.21 | 0 | [02-pytest.log](02-pytest.log) |
| 03 | vitest | PASS | 0 | 2.5 | - | [03-vitest.log](03-vitest.log) |
| 04 | tsc | PASS | 0 | 1.55 | - | [04-tsc.log](04-tsc.log) |
| 05 | eslint | PASS | 0 | 1.25 | - | [05-eslint.log](05-eslint.log) |
