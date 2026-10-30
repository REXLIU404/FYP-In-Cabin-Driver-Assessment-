# DS-3 review follow-ups: screenshots and computed-style checks (2026-10-30)

Live mode only (Chromium fake camera), so no dataset image appears; all four screenshots are committed.
Reproduce: `.venv/bin/python docs/evidence/2026-10-30/ds3-followups/capture.py <out dir>` from the repository root.

Run output:
- Live note: `Vision: camera → trained vision model (named on the line below) · Telemetry: prepared raw features → trained XGBoost.` (no "experimental" remark; user decision 2026-10-30)
- Badge labels as rendered: `AlertSeverity, SystemHealth, RiskLevel, DominantEvidence, AlertSeverity` (written form, no upper-casing)
- DominantEvidence tooltip: the new text from `frontend/src/utils/contractTooltips.ts`
- Signal Inspector has "Evidence Type": False; Risk Trends headers: `Window, Time, RiskScore, RiskLevel, AlertSeverity, DominantEvidence, Flag`
- R29: `.brand-copy` computed `display` = `none` with the sidebar collapsed at 800 px and 700 px, and expanded at 800 px
- No console or page errors

The pass/fail checks are `frontend/src/views/usability.test.ts`, `frontend/src/utils/dataMode.test.ts` and `backend/tests/test_live_e2e.py`.
