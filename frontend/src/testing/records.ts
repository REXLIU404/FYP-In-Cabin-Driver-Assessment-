// Test-only builders. Nothing in the app imports this file; it exists so the
// pure-function tests (the vitest environment is `node`, no DOM) can produce
// records through the REAL producer (`buildRiskUpdate`) instead of hand-typing
// objects that could drift from the contract.
import { buildRiskUpdate, DEFAULT_CONFIG } from "../../../ai/src/riskLogic";
import { PREPARED_SESSION_WINDOWS } from "../data/preparedSessionInput";
import type {
  FreshnessStatus,
  PreparedSessionWindow,
  RiskUpdate,
} from "../types";

export const makeWindow = (
  vision: FreshnessStatus,
  telemetry: FreshnessStatus,
  over: Partial<PreparedSessionWindow> = {},
): PreparedSessionWindow => ({
  timestamp: "2026-05-06T08:00:00.000Z",
  P_distraction: vision === "missing" ? 0 : 0.5,
  P_telemetry_anomaly: telemetry === "missing" ? 0 : 0.3,
  vision_status: vision,
  telemetry_status: telemetry,
  visual_top_classes:
    vision === "missing" ? [] : [{ label: "texting_right", probability: 0.5 }],
  telemetry_behavior_classes:
    telemetry === "missing"
      ? []
      : [
          { label: "Safe", probability: 0.7 },
          { label: "Aggressive", probability: 0.2 },
          { label: "Distracted", probability: 0.1 },
        ],
  telemetry_feature_contributions: [],
  telemetry_features: null,
  latency_ms: 40,
  ...over,
});

/** A record produced by the real fusion pipeline (no previous record, no EMA). */
export const makeRecord = (
  vision: FreshnessStatus,
  telemetry: FreshnessStatus,
  windowId = 1,
  over: Partial<PreparedSessionWindow> = {},
): RiskUpdate =>
  buildRiskUpdate(
    makeWindow(vision, telemetry, over),
    "test-session",
    DEFAULT_CONFIG,
    undefined,
    windowId,
  );

/**
 * What a record looked like in localStorage BEFORE the nullable contract: no
 * `assessment_available`, and an unassessable window stored as a fabricated
 * `0 / Low / NORMAL / UNAVAILABLE`.
 */
export const toLegacyRow = (record: RiskUpdate): Record<string, unknown> => {
  const { assessment_available, ...rest } = record;
  void assessment_available;
  return record.assessment_available
    ? rest
    : {
        ...rest,
        RiskScore: 0,
        RiskLevel: "Low",
        DominantEvidence: "Partial evidence",
        AlertSeverity: "NORMAL",
      };
};

/** The 25-window prepared replay, run through the real pipeline as App does. */
export const replayRecords = (): RiskUpdate[] => {
  const records: RiskUpdate[] = [];
  let previous: RiskUpdate | undefined;
  PREPARED_SESSION_WINDOWS.forEach((window, index) => {
    const record = buildRiskUpdate(
      window,
      "session_001",
      DEFAULT_CONFIG,
      previous,
      index + 1,
    );
    records.push(record);
    previous = record;
  });
  return records;
};
