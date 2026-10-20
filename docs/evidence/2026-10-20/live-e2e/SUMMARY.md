# Gate run summary

- Result: **GREEN**: all 5 gate(s) passed.
- Generated (UTC): `2026-10-20T05:20:43Z`
- Repository: `87bdc3f15811cd532fdc3a7307520027d3ab3477` on `fyp2/live-system`, working tree dirty (5 entries)
- Command: `python3 scripts/run_gates.py --out docs/evidence/2026-10-20/live-e2e`

| # | Gate | Status | Exit | Duration (s) | Skipped | Log |
|---|------|--------|------|--------------|---------|-----|
| 01 | build | PASS | 0 | 3.49 | - | [01-build.log](01-build.log) |
| 02 | pytest | PASS | 0 | 134.03 | 0 | [02-pytest.log](02-pytest.log) |
| 03 | vitest | PASS | 0 | 2.7 | - | [03-vitest.log](03-vitest.log) |
| 04 | tsc | PASS | 0 | 1.5 | - | [04-tsc.log](04-tsc.log) |
| 05 | eslint | PASS | 0 | 1.19 | - | [05-eslint.log](05-eslint.log) |
