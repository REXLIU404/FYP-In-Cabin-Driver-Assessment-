# Gate run summary

- Result: **GREEN**: all 5 gate(s) passed.
- Generated (UTC): `2026-10-30T06:33:47Z`
- Repository: `f15f539e78991672cc0ab92f26caa9f86a21ba06` on `(detached)`, working tree clean
- Command: `python3 scripts/run_gates.py --out docs/evidence/2026-10-30/stage5-coldstart-f15f539/gates`

| # | Gate | Status | Exit | Duration (s) | Skipped | Log |
|---|------|--------|------|--------------|---------|-----|
| 01 | build | PASS | 0 | 3.5 | - | [01-build.log](01-build.log) |
| 02 | pytest | PASS | 0 | 216.73 | 0 | [02-pytest.log](02-pytest.log) |
| 03 | vitest | PASS | 0 | 2.52 | - | [03-vitest.log](03-vitest.log) |
| 04 | tsc | PASS | 0 | 1.59 | - | [04-tsc.log](04-tsc.log) |
| 05 | eslint | PASS | 0 | 1.49 | - | [05-eslint.log](05-eslint.log) |
