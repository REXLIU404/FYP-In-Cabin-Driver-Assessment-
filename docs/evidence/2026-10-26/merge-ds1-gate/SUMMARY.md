# Gate run summary

- Result: **GREEN**: all 5 gate(s) passed.
- Generated (UTC): `2026-10-26T09:37:09Z`
- Repository: `777cd05abfa335e189d88f89550694b4fad04665` on `fyp2/live-system`, working tree dirty (4 entries)
- Command: `python3 scripts/run_gates.py --out docs/evidence/2026-10-26/merge-ds1-gate`

| # | Gate | Status | Exit | Duration (s) | Skipped | Log |
|---|------|--------|------|--------------|---------|-----|
| 01 | build | PASS | 0 | 3.69 | - | [01-build.log](01-build.log) |
| 02 | pytest | PASS | 0 | 173.78 | 0 | [02-pytest.log](02-pytest.log) |
| 03 | vitest | PASS | 0 | 2.84 | - | [03-vitest.log](03-vitest.log) |
| 04 | tsc | PASS | 0 | 1.56 | - | [04-tsc.log](04-tsc.log) |
| 05 | eslint | PASS | 0 | 1.24 | - | [05-eslint.log](05-eslint.log) |
