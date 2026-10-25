import {
  branchExpiry,
  getDisplayState,
  type BranchExpiry,
} from "../../../ai/src/availability";
import type {
  DominantEvidence,
  FreshnessStatus,
  RiskUpdate,
  SystemHealth,
} from "../types";
import { resolveDominantEvidence } from "../utils/display";

export interface LiveMonitorModel {
  displayState: "available" | "stale" | "unavailable";
  /** The record's own SystemHealth - never rewritten by the age judgement. */
  systemHealth: SystemHealth;
  /** The record's own freshness - never rewritten to "stale" by record age. */
  vision: FreshnessStatus;
  telemetry: FreshnessStatus;
  /** Whether each branch scored as missing because its evidence EXPIRED (ruling A). */
  visionExpiry: BranchExpiry;
  telemetryExpiry: BranchExpiry;
  evidenceType: DominantEvidence | null;
  resultAge: "stale" | "current";
}

/**
 * What the Live Monitor shows about the latest record. `stale` is a front-end
 * judgement about the record's AGE (it depends on the client and server clocks
 * agreeing); `assessment_available` is a property of the record ITSELF. The old
 * view collapsed the two into one branch and fabricated `SystemHealth =
 * "UNAVAILABLE"` and `freshness = "stale"` for an old record. Here the values
 * pass through untouched and the age is reported on its own channel.
 */
export const buildLiveMonitorModel = (
  latest: RiskUpdate,
  stale: boolean,
  thresholdLow: number,
): LiveMonitorModel => ({
  displayState: getDisplayState(latest, { stale }),
  systemHealth: latest.SystemHealth,
  vision: latest.modality_freshness.vision,
  telemetry: latest.modality_freshness.telemetry,
  visionExpiry: branchExpiry(latest, "vision"),
  telemetryExpiry: branchExpiry(latest, "telemetry"),
  evidenceType: resolveDominantEvidence(latest, thresholdLow),
  resultAge: stale ? "stale" : "current",
});
