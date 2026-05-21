# AI Layer

Prototype AI contract and deterministic inference logic for the in-cabin driver risk assessment system.

## Responsibilities

- Defines the shared runtime contract in `src/types.ts`.
- Computes late-fusion `RiskScore`, `RiskLevel`, `AlertSeverity`, `SystemHealth`, and weighted branch contributions.
- Provides evidence classification rules for `Vision-dominant`, `Telemetry-dominant`, `Combined evidence`, `Partial evidence`, and `Low observed risk`.
- Stores prepared prototype input data under `prototype-data/prepared_sessions/`.

## FYP2 Integration Boundary

The current implementation is deterministic prototype logic. Future MobileNetV3 and XGBoost inference can replace the prepared-session adapter while preserving the same `RiskUpdate` contract for the frontend and backend.
