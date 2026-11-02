# Gate run note (2026-11-02)

Command:

```bash
DRA_REQUIRE_MODELS=1 python3 scripts/run_gates.py --out docs/evidence/2026-11-02/dmd-candidate-gates
```

Result: **GREEN**, all 5 gates passed (`SUMMARY.md`).

| Gate | Result | Detail |
|---|---|---|
| 01 build | PASS | `npm run build`, exit 0 |
| 02 pytest | PASS | **1438 passed, 12 skipped, 11 deselected**, 208.26 s |
| 03 vitest | PASS | exit 0 |
| 04 tsc | PASS | exit 0 |
| 05 eslint | PASS | exit 0 |

- `DRA_REQUIRE_MODELS=1: no model-dependent test was skipped.` — the 12 skips are **not** missing
  stable models; they are the DMD torch tests gated by `DRA_DMD_TORCH=1`
  (`tests/test_dmd_dataset.py`, `tests/test_dmd_export.py`). They were run separately:
  **12 passed** in `dmd-torch-tests.log`.
- The 11 deselected tests are the `long` / `candidates` opt-in markers (conftest), including the
  three real-package DMD runtime checks; those were run explicitly with `-m candidates` during
  item B (see `../dmd-candidate/b-runtime-compat/tests-candidates-GREEN.log`).
- `ml/tests`: **302 passed** in `ml-tests.log` (run separately with the repository venv).
- Gate `SUMMARY.md` records commit `041f2e6` and "working tree dirty (8 entries)". The dirty entries
  were untracked planning/report files and new evidence docs, not code changes; the pytest gate ran
  the committed test/script content. The only commit made during the gate run was
  `041f2e6` (a new errata file); it changed no code or test.
- Scope of the gate: this development machine and the repository venv; it is not a target-hardware
  or real-camera test.

## Files

| File | Content |
|---|---|
| `01-build.log` .. `05-eslint.log` | complete stdout/stderr and exit code per gate |
| `SUMMARY.md` | the runner's summary table |
| `ml-tests.log` | `PYTHONPATH=backend .venv/bin/python -m pytest ml/tests -q` → 302 passed |
| `dmd-torch-tests.log` | `DRA_DMD_TORCH=1` DMD dataset/export tests → 12 passed |
