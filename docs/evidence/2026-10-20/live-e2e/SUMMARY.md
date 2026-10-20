# Gate run summary

- Result: **GREEN**: all 5 gate(s) passed.
- Generated (UTC): `2026-10-20T04:49:13Z`
- Repository: `ae1c1971ae14c028ccda0150fcc33d90c23a4ee7` on `fyp2/live-system`, working tree dirty (1 entries)
- Command: `python3 scripts/run_gates.py --out docs/evidence/2026-10-20/live-e2e`

| # | Gate | Status | Exit | Duration (s) | Skipped | Log |
|---|------|--------|------|--------------|---------|-----|
| 01 | build | PASS | 0 | 3.67 | - | [01-build.log](01-build.log) |
| 02 | pytest | PASS | 0 | 134.08 | 0 | [02-pytest.log](02-pytest.log) |
| 03 | vitest | PASS | 0 | 2.49 | - | [03-vitest.log](03-vitest.log) |
| 04 | tsc | PASS | 0 | 1.43 | - | [04-tsc.log](04-tsc.log) |
| 05 | eslint | PASS | 0 | 1.16 | - | [05-eslint.log](05-eslint.log) |
