import { isAssessmentAvailable } from "../../../ai/src/availability";
import type { DistributionDatum, RiskLevel, RiskUpdate } from "../types";
import { UNAVAILABLE_LABEL } from "../utils/format";

const riskLevels: RiskLevel[] = ["Low", "Medium", "High"];

/**
 * RiskLevel histogram with an explicit Unavailable bucket. Without it the three
 * level counts silently stop summing to `history.length`: an unassessed window
 * has `RiskLevel === null`, which equals none of Low / Medium / High, so a bare
 * `filter(r => r.RiskLevel === label)` drops it.
 */
export const distribution = (history: RiskUpdate[]): DistributionDatum[] => {
  const assessed = (record: RiskUpdate) =>
    isAssessmentAvailable(record) && record.RiskLevel !== null;
  return [
    ...riskLevels.map((label) => ({
      label,
      count: history.filter(
        (record) => assessed(record) && record.RiskLevel === label,
      ).length,
    })),
    {
      label: UNAVAILABLE_LABEL,
      count: history.filter((record) => !assessed(record)).length,
    },
  ];
};

/** Row styling for the history table. An unassessed row is marked, not blank. */
export const riskRowClassName = (
  record: RiskUpdate,
  selectedWindowId: number,
): string =>
  [
    record.window_id === selectedWindowId ? "is-selected" : "",
    isAssessmentAvailable(record) && record.RiskLevel === "High"
      ? "is-high-risk"
      : "",
    isAssessmentAvailable(record) ? "" : "is-unavailable",
  ]
    .filter(Boolean)
    .join(" ");
