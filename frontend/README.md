# Frontend Layer

React + TypeScript dashboard for the in-cabin driver risk assessment prototype.

## Scope: Live is the primary runtime

The dashboard renders what the backend saved. In the Live runtime the browser
supplies two inputs - a camera frame and a row of prepared **raw** telemetry - and
sends them to `POST /api/sessions/{id}/infer`; the trained models, the fusion, the
smoothing and the alert state are on the server, and the five views only display the
saved record. The browser recomputes no risk assessment.

The prepared-probability replay (P_distraction / P_telemetry_anomaly read from a CSV,
risk computed in the browser) is **retained as a legacy / test-only path**: it is the
"Prepared replay (legacy, test-only)" entry of the Data mode menu, it uses no trained
model and no backend, and it exists for regression tests and backward compatibility.
A reload always starts on Live (`loadConfig` never restores the stored mode); the
replay runs only when someone chooses it in the page. Nothing of it was removed.

The two paths read the prepared session differently, on purpose:

|                         | Live                                                                     | Legacy replay                                                                                 |
| ----------------------- | ------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------- |
| Reads                   | `PREPARED_RAW_TELEMETRY` (8 features per row, via `preparedTelemetryAt`) | `PREPARED_SESSION_WINDOWS` (adds P_distraction, P_telemetry_anomaly, visual_top_classes, ...) |
| Probabilities come from | the trained MobileNetV3 / XGBoost, on the backend                        | the prepared CSV, in the browser                                                              |
| Evidence-age limit      | the session's `freshness_tolerance_s`, judged by the backend             | a fixed 3 s in the replay data builder                                                        |
| Saved in                | SQLite                                                                   | localStorage                                                                                  |

`useLiveSession.ts` and `ai/src/liveLoop.ts` must not name `PREPARED_SESSION_WINDOWS`;
`src/data/preparedRawTelemetry.test.ts` fails if they do.

## Responsibilities

- Renders the five operator interfaces: Live Monitor, Signal Inspector, Risk Trends, Explanation, and Configuration.
- Manages browser runtime state, the camera, the Live acquisition loop (bounded retry, visible stop), and the retained replay's local session log.
- Reads the prepared session through `src/data/preparedSessionInput.ts`: `PREPARED_RAW_TELEMETRY` for Live, `PREPARED_SESSION_WINDOWS` for the legacy replay.
- Calls the AI layer contract in `../ai/src` for the shared types, the Live loop and the replay's risk logic.

## Key Paths

- `src/App.tsx`: monitoring runtime orchestration and view routing.
- `src/components/`: reusable dashboard components (`RuntimeNotices.tsx`: the stop panel and the camera notices).
- `src/views/`: feature-level interface screens.
- `src/hooks/`: browser camera, Live session and replay hooks.
- `src/data/`: the prepared session (raw telemetry for Live, probabilities for the replay).
- `src/utils/`: frontend formatting, persistence, and export helpers.
