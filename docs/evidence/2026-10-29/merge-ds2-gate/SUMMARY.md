# Gate run summary

- Result: **GREEN**: all 5 gate(s) passed.
- Generated (UTC): `2026-10-29T04:41:29Z`
- Repository: `fbc95937bb05140dac70f632e03888cddc04d021` on `fyp2/live-system`, working tree dirty (4 entries)
- Command: `python3 scripts/run_gates.py --out docs/evidence/2026-10-29/merge-ds2-gate`

| # | Gate | Status | Exit | Duration (s) | Skipped | Log |
|---|------|--------|------|--------------|---------|-----|
| 01 | build | PASS | 0 | 3.66 | - | [01-build.log](01-build.log) |
| 02 | pytest | PASS | 0 | 194.99 | 0 | [02-pytest.log](02-pytest.log) |
| 03 | vitest | PASS | 0 | 2.88 | - | [03-vitest.log](03-vitest.log) |
| 04 | tsc | PASS | 0 | 1.78 | - | [04-tsc.log](04-tsc.log) |
| 05 | eslint | PASS | 0 | 1.38 | - | [05-eslint.log](05-eslint.log) |
