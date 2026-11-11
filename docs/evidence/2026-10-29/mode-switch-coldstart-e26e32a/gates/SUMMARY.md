# Gate run summary

- Result: **GREEN**: all 5 gate(s) passed.
- Generated (UTC): `2026-10-29T13:53:11Z`
- Repository: `e26e32a99578fa3c61eef2f2a648f8ea8328036b` on `(detached)`, working tree clean
- Command: `python3 scripts/run_gates.py --out docs/evidence/2026-10-29/mode-switch-coldstart-e26e32a/gates`

| # | Gate | Status | Exit | Duration (s) | Skipped | Log |
|---|------|--------|------|--------------|---------|-----|
| 01 | build | PASS | 0 | 3.47 | - | [01-build.log](01-build.log) |
| 02 | pytest | PASS | 0 | 214.47 | 0 | [02-pytest.log](02-pytest.log) |
| 03 | vitest | PASS | 0 | 2.42 | - | [03-vitest.log](03-vitest.log) |
| 04 | tsc | PASS | 0 | 1.57 | - | [04-tsc.log](04-tsc.log) |
| 05 | eslint | PASS | 0 | 1.45 | - | [05-eslint.log](05-eslint.log) |
