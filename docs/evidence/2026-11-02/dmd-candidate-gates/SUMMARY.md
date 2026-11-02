# Gate run summary

- Result: **GREEN**: all 5 gate(s) passed.
- Generated (UTC): `2026-11-02T10:47:43Z`
- Repository: `041f2e6ff2b3f0ef9d9e613cc31cb30489d31a89` on `fyp2/dmd-adaptation`, working tree dirty (8 entries)
- Command: `python3 scripts/run_gates.py --out docs/evidence/2026-11-02/dmd-candidate-gates`

| # | Gate | Status | Exit | Duration (s) | Skipped | Log |
|---|------|--------|------|--------------|---------|-----|
| 01 | build | PASS | 0 | 4.12 | - | [01-build.log](01-build.log) |
| 02 | pytest | PASS | 0 | 210.0 | 12 | [02-pytest.log](02-pytest.log) |
| 03 | vitest | PASS | 0 | 4.87 | - | [03-vitest.log](03-vitest.log) |
| 04 | tsc | PASS | 0 | 1.94 | - | [04-tsc.log](04-tsc.log) |
| 05 | eslint | PASS | 0 | 1.62 | - | [05-eslint.log](05-eslint.log) |

Note: pytest reports `12` skipped test(s). A skip proves nothing; the pytest log names them, and `DRA_REQUIRE_MODELS=1` turns a missing-model skip into a failure.
