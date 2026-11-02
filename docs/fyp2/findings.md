# Audit findings ledger

- Named master/spec/map files exist only in desktop checkout's FYP2_Codex_ClaudeCode_Audit_Package_v2 directory.
- Worktree and desktop HEAD differ. Desktop includes uncommitted trained provider, live frontend hook, backend regression tests, experiment scripts and past evidence logs; must verify these rather than importing prior memory's Mock-only conclusion.
- Master requires 00–08 documents, evidence manifest, exact status vocabulary, E1–E5 methodological review, all five model tuning, software tests/UAT, Week 7 gates and next 72 hours. Existing documents must be preserved.
- Prior memory is discovery guidance only, never current implementation proof.
- fast-context attempted first but failed: Windsurf API key unavailable. Fallback is rg and line-numbered reads.
- Primary audit scope: desktop working content; output worktree remains separate. No user reply yet after clarification opportunity; proceed with disclosed recommended assumption.
- Current trained provider loads local ONNX and XGBoost; /infer calls it, /windows replays supplied probabilities without calling mock class. No live fallback to canned predictions found.
- UI live path consumes backend risk_update and SQLite exports. UI replay is a separate TypeScript/localStorage pipeline, not API-backed replay.
- Both missing currently yields 0/Low/NORMAL plus UNAVAILABLE (fusion.py:37–38, inference.py:38–65). Existing test checks UNAVAILABLE only; frontend riskLogic test explicitly expects 0.
- CRUD test drops tables in tempfile.gettempdir()/dra_test.db at collection; isolate TMPDIR before execution. Other API fixtures use tmp_path and dependency overrides without global lifespan.
- Live integration tests use solid-color image fixtures: useful adapter/persistence wiring checks, not driver classification validity; expected predictions come from the same provider and are not an independent ML oracle.
- Runtime retries: frontend stops immediately on 404/409/422/503; other errors back off to 10 seconds without maximum N. No three-failure policy found.

- User confirmed desktop audit scope. LiveMonitor.tsx:88–113 and AlertBanner.tsx:12–25 suppress unavailable score visually; API/export still contain 0/Low/NORMAL. Do not claim live main UI silently shows Low.
- Zero effective weight also occurs when configured weights are (1,0), vision missing and telemetry present; health is DEGRADED while score is 0. Needs unavailable policy independent of presence flags.
- Vision source metadata now checked: 15899/2868/3657 rows and 18/4/4 drivers, zero driver intersection, no duplicate/missing image paths. Pixel/near-duplicate checks not run.
- Telemetry split sizes 21000/4500/4500, zero exact complete-row overlap, no missing values; no immutable source-record IDs in split CSVs. Eight feature schema excludes phone_usage and reaction_time.
- Full telemetry recheck accuracy .9993333333333333, macro-F1 .999333184740477. Vision 20-sample smoke: accuracy .9, macro-F1 .6575757575757576 with absent classes; cannot compare to full-test .8746. Parity budget 20 actually covers 16 samples / 8 classes.
- Only old validation dim/gaussian blur robustness probe exists, not E1 6x3 held-out benchmark; old E1–E5 names in PROJECT_ASSESSMENT_AND_TEST_PLAN differ from v2 specification.
- Actual FSM exports three alert states, with high/low timers; five-state FYP1 claim not implemented as five named states.
- Frontend recovery-tail test equates >=5 samples at 2s to >=10s; first-to-last span is 8s, and it never invokes the temporal FSM.
