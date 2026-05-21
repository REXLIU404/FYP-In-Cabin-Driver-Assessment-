# Prototype Tests

This folder records lightweight validation flows for the FYP1 prototype.

## Current Smoke Test

Run from the project root:

```bash
npm run build
npm run linc
```

Then start the app:

```bash
npm run dev
```

Check the five interfaces:

- Live Monitor: monitoring starts, latency is visible, and `RiskScore` remains on a 0-100 scale.
- Signal Inspector: ordered windows can be selected and flagged.
- Risk Trends: branch traces and risk distribution render.
- Explanation: evidence cards, contribution bars, and rule badges render without long text blocks.
- Configuration: runtime/session logging controls and JSON/CSV export remain available.
