# Gate run summary

- Result: **GREEN**: all 5 gate(s) passed.
- Generated (UTC): `2026-10-29T04:04:08Z`
- Repository: `cde7ab1c7bcd78dac2de4530c8b4b74db69744ed` on `fyp2/live-system`, working tree dirty (4 entries)
- Command: `python3 scripts/run_gates.py --out docs/evidence/2026-10-29/constructed-scenario-merge-gate`

| # | Gate | Status | Exit | Duration (s) | Skipped | Log |
|---|------|--------|------|--------------|---------|-----|
| 01 | build | PASS | 0 | 4.17 | - | [01-build.log](01-build.log) |
| 02 | pytest | PASS | 0 | 203.28 | 0 | [02-pytest.log](02-pytest.log) |
| 03 | vitest | PASS | 0 | 2.55 | - | [03-vitest.log](03-vitest.log) |
| 04 | tsc | PASS | 0 | 1.69 | - | [04-tsc.log](04-tsc.log) |
| 05 | eslint | PASS | 0 | 1.53 | - | [05-eslint.log](05-eslint.log) |
