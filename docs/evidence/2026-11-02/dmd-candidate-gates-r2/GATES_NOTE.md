# Review round 2 gate note

- HEAD at run start: `2bbd9daf1c678eee6f1ec8af23031cb49d6ea9b1`
- Branch: `fyp2/dmd-adaptation`
- Command: `DRA_REQUIRE_MODELS=1 python3 scripts/run_gates.py --out docs/evidence/2026-11-02/dmd-candidate-gates-r2`
- Result: 5/5 gates PASS (`SUMMARY.md`), including build, backend pytest, vitest,
  tsc and eslint.
- Backend pytest: **1442 passed, 12 skipped, 11 deselected**; the log contains
  `DRA_REQUIRE_MODELS=1: no model-dependent test was skipped.` The 12 skips are the
  `DRA_DMD_TORCH=1` tests and pass separately: **12 passed** (`dmd-torch-tests.log`).
- `ml/tests`: **302 passed** (`ml-tests.log`).
- `SUMMARY.md` reports a dirty working tree of 7 entries at run time. Two were
  pre-existing modifications unrelated to this review round
  (`frontend/src/api/client.ts`, `frontend/src/api/client.test.ts`); they were
  **not** staged or committed. The remaining entries were untracked report/plan
  files and this evidence directory. The gate result therefore describes that
  working-tree state, not only HEAD.
