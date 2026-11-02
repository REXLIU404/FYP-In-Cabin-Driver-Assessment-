# Gate run summary

- Result: **GREEN**: all 5 gate(s) passed.
- Generated (UTC): `2026-11-02T11:24:39Z`
- Repository: `2bbd9daf1c678eee6f1ec8af23031cb49d6ea9b1` on `fyp2/dmd-adaptation`, working tree dirty (7 entries)
- Command: `python3 scripts/run_gates.py --out docs/evidence/2026-11-02/dmd-candidate-gates-r2`

| # | Gate | Status | Exit | Duration (s) | Skipped | Log |
|---|------|--------|------|--------------|---------|-----|
| 01 | build | PASS | 0 | 3.71 | - | [01-build.log](01-build.log) |
| 02 | pytest | PASS | 0 | 208.83 | 12 | [02-pytest.log](02-pytest.log) |
| 03 | vitest | PASS | 0 | 2.81 | - | [03-vitest.log](03-vitest.log) |
| 04 | tsc | PASS | 0 | 1.8 | - | [04-tsc.log](04-tsc.log) |
| 05 | eslint | PASS | 0 | 1.51 | - | [05-eslint.log](05-eslint.log) |

Note: pytest reports `12` skipped test(s). A skip proves nothing; the pytest log names them, and `DRA_REQUIRE_MODELS=1` turns a missing-model skip into a failure.
