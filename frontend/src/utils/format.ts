import { asPercent, roundHalfUp } from "../../../ai/src/riskLogic";
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
 * Shown instead of NO_INPUT_LABEL when the branch DID send evidence but it was too old
 * (ruling A, D13): it carries no weight, like a missing one, but the reader is told why.
 */
export const EXPIRED_LABEL = "Expired";

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

// A probability shown as an integer percent. This IS the function that renders
// the percentages inside the stored explanation text (ai/src/riskLogic.ts), not
// a second copy of it, so the UI and the record cannot show 29% against 28%.
export const formatPercent = asPercent;

export const formatProbability = (value: number) => formatFixed(value, 2);

/** `null` is an unassessable window: say so, never print `0.0 / 100`. */
export const formatRiskScore = (value: number | null) =>
  value === null ? UNAVAILABLE_LABEL : `${formatFixed(value, 1)} / 100`;

export const formatContribution = (value: number | null) =>
  value === null ? UNAVAILABLE_LABEL : `${formatFixed(value, 0)} / 100`;

const noReading = (expired: boolean) =>
  expired ? EXPIRED_LABEL : NO_INPUT_LABEL;

/**
 * A branch whose input is missing carries P = 0.0 in the record (the contract
 * keeps the field non-null), but 0 is not a reading there. Consult
 * `modality_freshness` before printing the number. `expired` (from
 * `branchExpiry`) says the branch was not absent but too old, and changes the
 * words only: the number is withheld either way.
 */
export const formatBranchPercent = (
  value: number,
  freshness: FreshnessStatus,
  expired = false,
) => (freshness === "missing" ? noReading(expired) : formatPercent(value));

export const formatBranchProbability = (
  value: number,
  freshness: FreshnessStatus,
  expired = false,
) => (freshness === "missing" ? noReading(expired) : formatProbability(value));

export const formatTimestamp = (timestamp: string) =>
  new Intl.DateTimeFormat(undefined, {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(new Date(timestamp));
