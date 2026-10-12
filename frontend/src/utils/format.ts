import { roundHalfUp } from "../../../ai/src/riskLogic";
import type { FreshnessStatus } from "../types";

/**
 * The one string for "this window has no assessment". Every display site that
 * can receive a null RiskScore / RiskLevel / DominantEvidence / AlertSeverity
 * uses it, so an unavailable window never renders as a plausible reading.
 */
export const UNAVAILABLE_LABEL = "Unavailable";

/** Shown for a branch probability whose input branch is missing. */
export const NO_INPUT_LABEL = "No input";

/**
 * Fixed-point text with the SAME rounding as the backend (`round_half_up`):
 * half-up on the decimal digits, not on the binary value. The built-in binary
 * method disagrees at exact decimal ties (0.285 -> 0.28, 29.95 -> 29.9), which
 * is how a displayed RiskScore could differ from the stored one.
 */
export const formatFixed = (value: number, places: number): string => {
  if (!Number.isFinite(value)) return String(value);
  const rounded = roundHalfUp(value, places);
  const [whole, fraction = ""] = String(rounded).split(".");
  return places > 0 ? `${whole}.${fraction.padEnd(places, "0")}` : whole;
};

// A probability shown as an integer percent: round to 2 decimal places of the
// fraction (half-up), then scale. Scaling first (value * 100) would put binary
// noise in front of the tie.
export const formatPercent = (value: number) =>
  `${Math.round(roundHalfUp(value, 2) * 100)}%`;

export const formatProbability = (value: number) => formatFixed(value, 2);

/** `null` is an unassessable window: say so, never print `0.0 / 100`. */
export const formatRiskScore = (value: number | null) =>
  value === null ? UNAVAILABLE_LABEL : `${formatFixed(value, 1)} / 100`;

export const formatContribution = (value: number | null) =>
  value === null ? UNAVAILABLE_LABEL : `${formatFixed(value, 0)} / 100`;

/**
 * A branch whose input is missing carries P = 0.0 in the record (the contract
 * keeps the field non-null), but 0 is not a reading there. Consult
 * `modality_freshness` before printing the number.
 */
export const formatBranchPercent = (
  value: number,
  freshness: FreshnessStatus,
) => (freshness === "missing" ? NO_INPUT_LABEL : formatPercent(value));

export const formatBranchProbability = (
  value: number,
  freshness: FreshnessStatus,
) => (freshness === "missing" ? NO_INPUT_LABEL : formatProbability(value));

export const formatTimestamp = (timestamp: string) =>
  new Intl.DateTimeFormat(undefined, {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(new Date(timestamp));
