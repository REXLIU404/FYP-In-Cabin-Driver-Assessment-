# Changelog

## 2026-05-07

- Rebuilt the React MVP visual styling toward the supplied standalone DMS dashboard reference: light operator dashboard shell, white sidebar, compact navigation, subtle card borders, smaller typography, and indigo active state.
- Changed `RiskScore` from a 0-1 display scale to a 0-100 risk scale across risk logic, gauge, charts, tables, selected-window details, exports, and default thresholds.
- Preserved branch probability fields (`P_distraction`, `P_telemetry_anomaly`, visual class probabilities) as 0-1 model probabilities, while plotting branch traces as percentages for comparison with the 0-100 RiskScore axis.
- Added persisted-config migration so older saved threshold values like `0.30` and `0.60` are converted to `30` and `60`.
- Updated the Explanation view to use configured fusion weights, show `RiskScore / 100`, include structured telemetry contribution proxy bars, and clarify that explanations are generated from vision and telemetry evidence rather than text tokens.
- Added the Chinese implementation guide at `docs/explanation-implementation-guide.zh.md` for implementing explanation with vision and telemetry models in MVP and FYP2.
- Added an inline SVG favicon to avoid the browser 404 seen during local smoke testing.
