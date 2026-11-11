# Gate run summary

- Result: **GREEN**: all 5 gate(s) passed.
- Generated (UTC): `2026-10-26T05:07:50Z`
- Repository: `5edd868a47806ea17fabf03d5f9c296109ae6989` on `fyp2/live-system`, working tree dirty (6 entries)
- Command: `python3 scripts/run_gates.py --out docs/evidence/2026-10-26/merge-ds0-gate`

| # | Gate | Status | Exit | Duration (s) | Skipped | Log |
|---|------|--------|------|--------------|---------|-----|
| 01 | build | PASS | 0 | 7.82 | - | [01-build.log](01-build.log) |
| 02 | pytest | PASS | 0 | 181.9 | 0 | [02-pytest.log](02-pytest.log) |
| 03 | vitest | PASS | 0 | 3.13 | - | [03-vitest.log](03-vitest.log) |
| 04 | tsc | PASS | 0 | 1.55 | - | [04-tsc.log](04-tsc.log) |
| 05 | eslint | PASS | 0 | 1.21 | - | [05-eslint.log](05-eslint.log) |
