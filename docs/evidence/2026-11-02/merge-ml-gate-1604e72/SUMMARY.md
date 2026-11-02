# Gate run summary

- Result: **GREEN**: all 5 gate(s) passed.
- Generated (UTC): `2026-11-02T09:38:37Z`
- Repository: `1604e72a0e00bd45e57767bfda3d31756c218589` on `fyp2/live-system`, working tree dirty (1 entries)
- Command: `python3 scripts/run_gates.py --out docs/evidence/2026-11-02/merge-ml-gate-1604e72`

| # | Gate | Status | Exit | Duration (s) | Skipped | Log |
|---|------|--------|------|--------------|---------|-----|
| 01 | build | PASS | 0 | 3.85 | - | [01-build.log](01-build.log) |
| 02 | pytest | PASS | 0 | 204.74 | 12 | [02-pytest.log](02-pytest.log) |
| 03 | vitest | PASS | 0 | 2.82 | - | [03-vitest.log](03-vitest.log) |
| 04 | tsc | PASS | 0 | 1.7 | - | [04-tsc.log](04-tsc.log) |
| 05 | eslint | PASS | 0 | 1.53 | - | [05-eslint.log](05-eslint.log) |

Note: pytest reports `12` skipped test(s). A skip proves nothing; the pytest log names them, and `DRA_REQUIRE_MODELS=1` turns a missing-model skip into a failure.
