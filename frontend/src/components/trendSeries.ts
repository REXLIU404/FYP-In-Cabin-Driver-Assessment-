import { isAssessmentAvailable } from "../../../ai/src/availability";
import { roundHalfUp } from "../../../ai/src/riskLogic";
import type { RiskUpdate } from "../types";
import {
  UNAVAILABLE_LABEL,
  formatFixed,
  formatRiskScore,
} from "../utils/format";

export interface TrendPoint {
  window: number;
  /** null for an unassessed window: a gap in the line, never a 0. */
  risk: number | null;
  /** null while the vision input is missing. */
  vision: number | null;
  /** null while the telemetry input is missing. */
  telemetry: number | null;
}

/**
 * A probability as a chart percent, to the 0.1 the tooltip prints. Half-up on the
 * DECIMAL probability (3 places = 0.1 %) first, scaled after - the order `asPercent`
 * uses. `P * 100` alone is a binary multiplication: 0.2855 becomes
 * 28.549999999999997 and the tie is gone before anything rounds it (shown as 28.5%,
 * should be 28.6%). The outer round only removes the binary dust of the scaling.
 */
const toPercentPoint = (probability: number): number =>
  roundHalfUp(roundHalfUp(probability, 3) * 100, 1);

/**
 * Chart series for a history. The risk point is keyed on the record's own
 * `assessment_available`, not on SystemHealth or on the score being falsy: a
 * genuine score of 0 is a reading and stays on the line, while an unassessed
 * window leaves a visible gap.
 */
export const buildTrendSeries = (history: RiskUpdate[]): TrendPoint[] =>
  history.map((record) => ({
    window: record.window_id,
    risk: isAssessmentAvailable(record) ? record.RiskScore : null,
    vision:
      record.modality_freshness.vision === "missing"
        ? null
        : toPercentPoint(record.P_distraction),
    telemetry:
      record.modality_freshness.telemetry === "missing"
        ? null
        : toPercentPoint(record.P_telemetry_anomaly),
  }));

/**
 * Tooltip text for one series entry. A null point must read as unavailable:
 * `Number(null)` is 0, which formatted as "0.0 / 100" - a safe-looking score
 * for a window that has none.
 */
export const formatTrendTooltip = (value: unknown, name: unknown): string => {
  if (value === null || value === undefined || value === "") {
    return UNAVAILABLE_LABEL;
  }
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return UNAVAILABLE_LABEL;
  return name === "RiskScore"
    ? formatRiskScore(numeric)
    : `${formatFixed(numeric, 1)}%`;
};
