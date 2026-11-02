# Gate run summary

- Result: **GREEN**: all 5 gate(s) passed.
- Generated (UTC): `2026-10-29T10:13:38Z`
- Repository: `75e10940e92c48ac6883cb8de3e6395616fe0689` on `fyp2/live-system`, working tree dirty (5 entries)
- Command: `python3 scripts/run_gates.py --out docs/evidence/2026-10-29/merge-ds3-gate`

| # | Gate | Status | Exit | Duration (s) | Skipped | Log |
|---|------|--------|------|--------------|---------|-----|
| 01 | build | PASS | 0 | 4.21 | - | [01-build.log](01-build.log) |
| 02 | pytest | PASS | 0 | 204.91 | 0 | [02-pytest.log](02-pytest.log) |
| 03 | vitest | PASS | 0 | 3.24 | - | [03-vitest.log](03-vitest.log) |
| 04 | tsc | PASS | 0 | 1.83 | - | [04-tsc.log](04-tsc.log) |
| 05 | eslint | PASS | 0 | 1.54 | - | [05-eslint.log](05-eslint.log) |
