# Backend Layer

Backend integration boundary for the in-cabin driver assessment prototype.

## Current State

This repository currently runs as a frontend-first FYP1 MVP. No FastAPI, WebSocket, database, or model-serving backend has been implemented yet.

## Intended Responsibilities

- Receive camera/telemetry input streams or prepared-session playback requests.
- Call the real vision and telemetry model services.
- Return the same `RiskUpdate` contract defined in `../ai/src/types.ts`.
- Persist session logs when the prototype moves beyond browser `localStorage`.
- Serve runtime data to the dashboard through REST or WebSocket endpoints.

## Contract Direction

Keep backend payloads aligned with the AI layer contract instead of creating a separate response shape. This keeps the frontend, backend, and AI layers replaceable without rewriting the dashboard views.
