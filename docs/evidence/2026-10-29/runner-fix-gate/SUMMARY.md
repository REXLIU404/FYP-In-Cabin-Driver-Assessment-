# Gate run summary

- Result: **GREEN**: all 5 gate(s) passed.
- Generated (UTC): `2026-10-29T05:07:34Z`
- Repository: `bf76ddffc9f2f69a034b23357348a06a7076a30b` on `fyp2/live-system`, working tree dirty (7 entries)
- Command: `python3 scripts/run_gates.py --out docs/evidence/2026-10-29/runner-fix-gate`

| # | Gate | Status | Exit | Duration (s) | Skipped | Log |
|---|------|--------|------|--------------|---------|-----|
| 01 | build | PASS | 0 | 3.72 | - | [01-build.log](01-build.log) |
| 02 | pytest | PASS | 0 | 202.57 | 0 | [02-pytest.log](02-pytest.log) |
| 03 | vitest | PASS | 0 | 3.36 | - | [03-vitest.log](03-vitest.log) |
| 04 | tsc | PASS | 0 | 2.7 | - | [04-tsc.log](04-tsc.log) |
| 05 | eslint | PASS | 0 | 1.6 | - | [05-eslint.log](05-eslint.log) |
