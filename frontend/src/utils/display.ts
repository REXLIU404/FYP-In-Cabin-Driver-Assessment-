import {
  FUSION_EPSILON,
  describeBranchStatus,
  getDisplayState,
  type BranchExpiry,
} from "../../../ai/src/availability";
import { ALERT_RECOVER_MS, ALERT_SUSTAIN_MS } from "../../../ai/src/alertFsm";
import { getEvidenceType, evidenceTypes } from "../../../ai/src/evidence";
import type {
  AlertSeverity,
  DistributionDatum,
  DominantEvidence,
  FreshnessStatus,
  RiskLevel,
  RiskUpdate,
  SystemHealth,
} from "../types";
import { UNAVAILABLE_LABEL } from "./format";

export type PillTone =
  | AlertSeverity
  | RiskLevel
  | SystemHealth
  | FreshnessStatus
  | "expired"
  | "flagged"
  | "neutral"
  | "unavailable";

/**
 * Resolves what a pill shows. `null` (an unassessed RiskLevel / AlertSeverity /
 * DominantEvidence) must never reach a template literal: it would produce
 * `pill--null`, which matches no CSS rule, so the pill would fall back to the
 * neutral base style and an unavailable window would LOOK like an ordinary one.
 *
 *   tone omitted           -> "neutral"   (a plain label)
 *   tone null              -> "unavailable"
 *   label null, no tone    -> "unavailable"
 */
export const resolvePill = (
  label: string | null,
  tone?: PillTone | null,
): { label: string; tone: PillTone } => ({
  label: label ?? UNAVAILABLE_LABEL,
  tone:
    tone === undefined
      ? label === null
        ? "unavailable"
        : "neutral"
      : (tone ?? "unavailable"),
});

/**
 * What a branch-freshness pill shows. An EXPIRED branch (ruling A, D13) reads
 * "expired (N s)" in its own `expired` tone, so it no longer looks like a branch
 * that never sent anything ("missing"); every other status is shown as stored.
 */
export const resolveBranchPill = (
  status: FreshnessStatus,
  expiry: BranchExpiry,
): { label: string; tone: PillTone } => ({
  label: describeBranchStatus(status, expiry),
  tone: expiry.expired ? "expired" : status,
});

/**
 * The record's own DominantEvidence. The backend (or the replay producer) is the
 * canonical source; a view must display it, not recompute it - recomputing from
 * the probabilities would resurrect a non-null label for a record whose stored
 * value is null. Recomputation is only a fallback for a record in which the
 * field is ABSENT (`undefined`); `null` is a real, stored answer.
 */
export const resolveDominantEvidence = (
  record: RiskUpdate,
  thresholdLow: number,
): DominantEvidence | null =>
  record.DominantEvidence === undefined
    ? getEvidenceType(record, thresholdLow)
    : record.DominantEvidence;

export const EVIDENCE_CHART_LABELS: Record<DominantEvidence, string> = {
  "Vision-dominant": "Vision",
  "Telemetry-dominant": "Telemetry",
  "Combined evidence": "Combined",
  "Partial evidence": "Partial",
  "Low observed risk": "Low risk",
};

/**
 * Evidence-type histogram. An unassessed record has no evidence type, so it gets
 * its own bucket: without it the buckets would no longer sum to
 * `history.length`.
 */
export const evidenceDistribution = (
  history: RiskUpdate[],
  thresholdLow: number,
): DistributionDatum[] => {
  const counts = new Map<DominantEvidence | null, number>();
  for (const record of history) {
    const type = resolveDominantEvidence(record, thresholdLow);
    counts.set(type, (counts.get(type) ?? 0) + 1);
  }
  return [
    ...evidenceTypes.map((type) => ({
      label: EVIDENCE_CHART_LABELS[type],
      count: counts.get(type) ?? 0,
    })),
    { label: UNAVAILABLE_LABEL, count: counts.get(null) ?? 0 },
  ];
};

/**
 * Inline notice for the fusion-weight sliders. Both sliders reach 0, which
 * silently removes a branch from the score; with a missing or zero-weighted
 * partner branch the effective denominator is zero and the window has no
 * assessment. Returns null while both weights are positive.
 */
export const zeroWeightNotice = (
  weightVision: number,
  weightTelemetry: number,
): string | null => {
  const zero: string[] = [];
  if (weightVision <= FUSION_EPSILON) zero.push("Vision");
  if (weightTelemetry <= FUSION_EPSILON) zero.push("Telemetry");
  if (zero.length === 0) return null;
  return (
    `${zero.join(" and ")} ${zero.length === 2 ? "weights are" : "weight is"} 0, so ` +
    `${zero.length === 2 ? "neither branch contributes" : "that branch no longer contributes"} to the RiskScore. ` +
    `A window whose remaining evidence is missing (or also zero-weighted) has no usable evidence: ` +
    `its RiskScore, RiskLevel and alert are reported as Unavailable rather than 0.`
  );
};

/**
 * Class list for the status banner. Three display states, in this order of
 * precedence: an unassessed record is `unavailable` whether or not it is old;
 * an assessed but old record is `stale`; otherwise the banner is tinted by the
 * record's own AlertSeverity. The interpolated severity can never be the string
 * "null": `alert-banner--null` matches no rule and would render the base (green,
 * "all clear") banner for a window that has no assessment.
 */
export const alertBannerClass = (
  record: RiskUpdate,
  stale: boolean,
): string => {
  const state = getDisplayState(record, { stale });
  if (state === "unavailable") return "alert-banner alert-banner--unavailable";
  if (state === "stale") return "alert-banner runtime-warning";
  return `alert-banner alert-banner--${record.AlertSeverity ?? "unavailable"}`;
};

/**
 * Why the alert on screen differs from the window's RiskLevel. The AlertSeverity FSM (ai/src/alertFsm.ts,
 * backend `_step_alert_fsm`) holds an alert until Low has lasted ALERT_RECOVER_MS and raises HIGH_ALERT
 * only after High has lasted ALERT_SUSTAIN_MS, so "Low + CAUTION" or "High + CAUTION" is correct but
 * looks like a contradiction without a word of explanation. Display text only: it decides nothing.
 */
export const alertHoldNote = (
  level: RiskLevel | null,
  severity: AlertSeverity | null,
): string | null => {
  if (level === null || severity === null) return null;
  const rank = { NORMAL: 0, CAUTION: 1, HIGH_ALERT: 2 } as const;
  const instantaneous = {
    Low: "NORMAL",
    Medium: "CAUTION",
    High: "HIGH_ALERT",
  } as const;
  if (level === "High" && severity !== "HIGH_ALERT") {
    return (
      `Escalation pending: HIGH_ALERT follows only if RiskLevel stays High for ` +
      `${ALERT_SUSTAIN_MS / 1000} s.`
    );
  }
  if (rank[severity] > rank[instantaneous[level]]) {
    return (
      `Alert held at ${severity}: it returns to NORMAL only after RiskLevel has stayed Low for ` +
      `${ALERT_RECOVER_MS / 1000} s.`
    );
  }
  return null;
};
