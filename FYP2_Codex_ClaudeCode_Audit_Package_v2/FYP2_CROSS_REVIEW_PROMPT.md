# FYP2 Independent Cross-Review Prompt (second agent)

> **Recommended workflow:** Run `FYP2_MASTER_REPOSITORY_AUDIT_PROMPT.md` in Codex first, then provide the resulting `docs/fyp2/` audit docs **plus repository access** to Claude Code (or reverse them). Run independently in a different worktree if both use write access. The second agent must not blindly trust the first.

--- BEGIN CROSS-REVIEW PROMPT ---

You are the **independent methodology and software-QA reviewer** of a previously generated FYP2 audit for an In-Cabin Multimodal Driver Monitoring & Risk Assessment project. Treat all existing `docs/fyp2/` reports as **untrusted assertions** until corroborated by the actual repository, run outputs, model artifacts and source files. Your remit is verification and criticism, not implementation.

1. Inspect the same repo and read `FYP2_MASTER_REPOSITORY_AUDIT_PROMPT.md`, `FYP2_EVALUATION_AND_TESTCASE_SPEC.md`, and the first agent's `docs/fyp2/` outputs. Verify repo root, commit, dates, and whether evidence matches the audited version. If different, state comparison limits.
2. **For every `TEST_PASSED` or `VERIFIED` status**, sample or exhaustively trace to test code, run command, actual result and source line. Downgrade unsupported claims; identify tests which only exercise mock or prepared probabilities.
3. Review **E1 Vision 6x3**, **E1 Telemetry D0–D3**, **E2 Fusion Effectiveness**, **E3 Missing/Stale Fusion**, **E4 EMA/FSM/Failures**, **E5 Cross-Layer** for label validity, hidden leakage, circular oracle, fabricated pass threshold, score-vs-accuracy confusion, reproducibility and ability to disprove the hypothesis.
4. Specifically challenge: unconditional `ΔRisk<=0.15`; whether stale `0.45` is factor vs normalized weight; `both missing -> Low risk` possibility; 30/60 and 2s/10s boundaries; whether D2 class-specific shift uses held-out labels and invalidates them; 45,000-row counting and `is_synthetic` on D0; DMD video frame independence and class mapping; high-risk retention without independently determined oracle; detection latency inflation with EMA.
5. Check model comparison and **tuning of all five models**, train/validation/test integrity, and whether the test set is repeatedly used for selection. Audit uncalibrated-probability overclaims; calibration is not mandatory but limitations must be stated.
6. Cross-check 8-mark **system evaluation rubric** categories: unit, integration, system, UAT, error handling. A survey template is NOT UAT completion; model benchmark output is NOT a system test.
7. Do not change source code, models, datasets or tests; do not run expensive training/downloading. You may write only `docs/fyp2/09_INDEPENDENT_AUDIT_REVIEW.md`. If you encounter a blocker, report it. Do not overwrite the first auditor's outputs.

Output a reviewer matrix:
`finding ID | original claim/test ID | first-agent assertion | independent evidence | verdict CONFIRMED / UNSUPPORTED / INCORRECT / UNRESOLVED | exact path:line | scientific impact | correction | priority`.

Then provide the **top 10 actual gaps** that should be fixed before Week 7, plus a short prioritized list of missing/revised tests with precise inputs and independently defined oracles. Flag any implication of **verified real-world fusion safety benefit** from artificial unpaired scenario pairs as unsupported. No invented results.

Respond in Chinese, preserving English technical labels. Cite repository evidence and list the independent review file path.

--- END CROSS-REVIEW PROMPT ---
