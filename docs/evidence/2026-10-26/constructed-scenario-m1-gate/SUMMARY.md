# Gate run summary

- Result: **GREEN**: all 5 gate(s) passed.
- Generated (UTC): `2026-10-26T12:32:08Z`
- Repository: `cb4f65bf82cdc954570dcdb4d25e251b0e535b41` on `fyp2/constructed-scenario`, working tree dirty (1 entries)
- Command: `python3 scripts/run_gates.py --out docs/evidence/2026-10-26/constructed-scenario-m1-gate`

| # | Gate | Status | Exit | Duration (s) | Skipped | Log |
|---|------|--------|------|--------------|---------|-----|
| 01 | build | PASS | 0 | 3.58 | - | [01-build.log](01-build.log) |
| 02 | pytest | PASS | 0 | 171.91 | 0 | [02-pytest.log](02-pytest.log) |
| 03 | vitest | PASS | 0 | 2.61 | - | [03-vitest.log](03-vitest.log) |
| 04 | tsc | PASS | 0 | 1.51 | - | [04-tsc.log](04-tsc.log) |
| 05 | eslint | PASS | 0 | 1.28 | - | [05-eslint.log](05-eslint.log) |
