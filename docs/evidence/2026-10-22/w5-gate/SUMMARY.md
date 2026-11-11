# Gate run summary

- Result: **GREEN**: all 5 gate(s) passed.
- Generated (UTC): `2026-10-22T14:15:00Z`
- Repository: `5040e9d8b1603d098168f126c15db12349e8a179` on `fyp2/live-system`, working tree dirty (5 entries)
- Command: `python3 scripts/run_gates.py --out docs/evidence/2026-10-22/w5-gate`

| # | Gate | Status | Exit | Duration (s) | Skipped | Log |
|---|------|--------|------|--------------|---------|-----|
| 01 | build | PASS | 0 | 3.69 | - | [01-build.log](01-build.log) |
| 02 | pytest | PASS | 0 | 169.7 | 0 | [02-pytest.log](02-pytest.log) |
| 03 | vitest | PASS | 0 | 2.44 | - | [03-vitest.log](03-vitest.log) |
| 04 | tsc | PASS | 0 | 1.5 | - | [04-tsc.log](04-tsc.log) |
| 05 | eslint | PASS | 0 | 1.25 | - | [05-eslint.log](05-eslint.log) |
