# Frontend Layer

React + TypeScript dashboard for the in-cabin driver risk assessment prototype.

## Responsibilities

- Renders the five operator interfaces: Live Monitor, Signal Inspector, Risk Trends, Explanation, and Configuration.
- Manages browser runtime state, camera preview, local session logging, and JSON/CSV export.
- Reads prepared monitoring windows through `src/data/preparedSessionInput.ts`.
- Calls the AI layer contract in `../ai/src` for risk fusion and evidence rules.

## Key Paths

- `src/App.tsx`: monitoring runtime orchestration and view routing.
- `src/components/`: reusable dashboard components.
- `src/views/`: feature-level interface screens.
- `src/hooks/`: browser camera and session-log hooks.
- `src/utils/`: frontend formatting, persistence, and export helpers.
