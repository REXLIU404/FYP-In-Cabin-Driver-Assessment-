# Figma Wireframe Fit Analysis

## Input Reviewed

- Local file: `/Users/liu/Downloads/Driver Risk Dashboard UI Wireframes.fig`
- Extracted archive contents: `canvas.fig`, `thumbnail.png`, `meta.json`
- Export metadata: `Driver Risk Dashboard UI Wireframes`, exported on `2026-05-06`

The local `.fig` file does not expose a readable JSON node tree. It contains a binary `canvas.fig` file and a low-resolution thumbnail strip. Because no Figma URL with `node-id` was provided, Figma MCP inspection and Code Connect mapping cannot be completed yet.

## Suitability Verdict

The Figma wireframe direction is suitable for the project MVP. It matches the guidebook's five-view dashboard concept:

- Live Monitor
- Signal Inspector
- Risk Trends
- Explanation
- Configuration

The wireframe also uses an appropriate FYP dashboard pattern: dark left navigation, light analytical workspace, chart-heavy monitoring pages, risk/status panels, and settings-oriented controls.

## Required Improvements Applied In Code

The thumbnail wireframe is useful as layout direction but is incomplete as an implementation spec. The MVP guidebook requires several behaviours that are not fully visible in the wireframe thumbnail, so the implemented UI adds:

- browser camera preview with permission, live, denied, and error states
- deterministic prepared-session monitoring flow
- localStorage CRUD for `session_log:{session_id}`
- high-risk row highlighting
- threshold reference lines at `30` and `60` on the 0-100 RiskScore scale
- RiskLevel distribution chart
- selected-window flag update
- reset session, JSON export, and CSV export
- explicit MVP scope wording: risk values come from prepared session windows, while
  camera preview is separate and upload video is not implemented

## Code Connect Status

Code Connect was not created because the provided design is a local `.fig` export, not a live Figma URL. The Code Connect workflow requires:

- a Figma URL containing `node-id`
- published Figma components
- access to component metadata through Figma MCP

If a live Figma design URL is provided later, map candidates should start with the implemented reusable components: `Sidebar`, `Pill`, `AlertBanner`, `RiskScoreGauge`, `CameraPreview`, `TrendChart`, and `DistributionChart`.
