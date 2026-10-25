# Gate run summary

- Result: **GREEN**: all 5 gate(s) passed.
- Generated (UTC): `2026-10-22T15:07:11Z`
- Repository: `28970004f3df9d2dcf26fce7987778b2f1df6d81` on `(detached)`, working tree clean
- Command: `python3 scripts/run_gates.py --out docs/evidence/2026-10-22/coldstart-final/gates`

| # | Gate | Status | Exit | Duration (s) | Skipped | Log |
|---|------|--------|------|--------------|---------|-----|
| 01 | build | PASS | 0 | 8.44 | - | [01-build.log](01-build.log) |
| 02 | pytest | PASS | 0 | 259.49 | 0 | [02-pytest.log](02-pytest.log) |
| 03 | vitest | PASS | 0 | 4.5 | - | [03-vitest.log](03-vitest.log) |
| 04 | tsc | PASS | 0 | 3.83 | - | [04-tsc.log](04-tsc.log) |
| 05 | eslint | PASS | 0 | 2.7 | - | [05-eslint.log](05-eslint.log) |
