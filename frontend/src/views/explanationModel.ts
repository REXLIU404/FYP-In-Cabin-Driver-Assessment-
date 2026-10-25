import { getDisplayState } from "../../../ai/src/availability";
import { computeRiskContributions } from "../../../ai/src/riskLogic";
import type { AppConfig, DominantEvidence, RiskUpdate } from "../types";
import { resolveDominantEvidence } from "../utils/display";

/** Why there is no per-branch split to show (null when there is one). */
export type ContributionIssue =
  | "no_assessment" // the record itself has no RiskScore to split
  | "no_evidence_under_weights" // the weights in scope leave a zero denominator
  | "weights_differ"; // the split would not add up to the record's stored RiskScore

export interface ExplanationModel {
  unavailable: boolean;
  /** null whenever `contributionIssue` is set. */
  contributions: { vision: number; telemetry: number; total: number } | null;
  contributionIssue: ContributionIssue | null;
  evidenceType: DominantEvidence | null;
}

// Both numbers are one-decimal roundings of the same quantity, so they agree to
// within one step; anything wider means the weights are not the record's own.
const RECONCILE_TOLERANCE = 0.1 + 1e-9;

/**
 * The Explanation view is reached through `selectedRecord`, so a user can select
 * an unassessed window in Signal Inspector and switch to it. For such a record
 * there is no RiskScore to explain: no contributions, no evidence type, and no
 * "Visual Distraction 0 + Telemetry Non-Safe 0 = RiskScore 0.0 / 100" equation.
 *
 * The per-branch split is NOT a stored field of the record: it is derived from
 * the record's own probabilities and freshness and the fusion weights in scope
 * (App passes the record's saved `fusion_config`; a replay record has none, so
 * the current configuration applies). Two guards keep it from contradicting the
 * canonical score the record carries:
 *  - it is never derived for an unassessed record, even if the weights in scope
 *    would leave a non-zero denominator (a record made unavailable by zero
 *    weights, viewed under another weight pair);
 *  - it is dropped when it does not reconcile with the stored RiskScore, i.e. the
 *    weights in scope are not the ones the record was produced with.
 */
export const buildExplanationModel = (
  record: RiskUpdate,
  config: AppConfig,
): ExplanationModel => {
  const unavailable =
    getDisplayState(record, { stale: false }) === "unavailable";
  const evidenceType = resolveDominantEvidence(record, config.thresholdLow);

  if (unavailable) {
    return {
      unavailable,
      contributions: null,
      contributionIssue: "no_assessment",
      evidenceType,
    };
  }

  const split = computeRiskContributions(
    record.P_distraction,
    record.P_telemetry_anomaly,
    config.weightVision,
    config.weightTelemetry,
    record.modality_freshness.vision,
    record.modality_freshness.telemetry,
  );
  const issue: ContributionIssue | null =
    split === null
      ? "no_evidence_under_weights"
      : record.RiskScore === null ||
          Math.abs(split.total - record.RiskScore) > RECONCILE_TOLERANCE
        ? "weights_differ"
        : null;

  return {
    unavailable,
    contributions: issue === null ? split : null,
    contributionIssue: issue,
    evidenceType,
  };
};
