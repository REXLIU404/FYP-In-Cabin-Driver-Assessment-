# Gate run summary

- Result: **GREEN**: all 5 gate(s) passed.
- Generated (UTC): `2026-10-29T09:34:49Z`
- Repository: `fe5c41d1ee795aba801faf82ee42ac9d685780a4` on `fyp2/live-system`, working tree dirty (6 entries)
- Command: `python3 scripts/run_gates.py --out docs/evidence/2026-10-29/stage3-gate`

| # | Gate | Status | Exit | Duration (s) | Skipped | Log |
|---|------|--------|------|--------------|---------|-----|
| 01 | build | PASS | 0 | 4.08 | - | [01-build.log](01-build.log) |
| 02 | pytest | PASS | 0 | 219.73 | 0 | [02-pytest.log](02-pytest.log) |
| 03 | vitest | PASS | 0 | 2.62 | - | [03-vitest.log](03-vitest.log) |
| 04 | tsc | PASS | 0 | 1.81 | - | [04-tsc.log](04-tsc.log) |
| 05 | eslint | PASS | 0 | 1.56 | - | [05-eslint.log](05-eslint.log) |
