import type { FreshnessStatus, RiskUpdate } from "./types";

/**
 * Availability contract for a fused risk assessment.
 *
 * A window is *available* exactly when the effective fusion denominator
 *
 *     denominator = w_v * fw(vision_status) + w_t * fw(telemetry_status)
 *
 * is strictly greater than FUSION_EPSILON. When it is not, there is no evidence
 * to fuse: RiskScore / RiskLevel / DominantEvidence / AlertSeverity are all
 * `null` and SystemHealth is "UNAVAILABLE". The pipeline must never invent a
 * "safe" reading (0 / Low / NORMAL) for a window it could not assess.
 *
 * Invariant (enforced by assertAvailabilityInvariant):
 *   assessment_available === (RiskScore !== null)
 *                         === (SystemHealth !== "UNAVAILABLE")
 *   and when false, the four nullable fields are null together.
 */

/**
 * Tolerance for "the effective denominator is zero". `RuntimeConfig` accepts
 * weights whose sum is off by up to 1e-6, so a literal `=== 0` test would let a
 * near-zero denominator through and divide by it.
 */
export const FUSION_EPSILON = 1e-9;

/** Freshness weights: fresh 1.0, stale 0.45, missing 0.0. */
export const freshnessWeight = (status: FreshnessStatus): number => {
  if (status === "missing") return 0;
  if (status === "stale") return 0.45;
  return 1;
};

/**
 * The one place the fusion denominator is computed. Score, health, dominant
 * evidence and the explanation all read this, so they cannot disagree.
 */
export const effectiveFusionDenominator = (
  weightVision: number,
  weightTelemetry: number,
  visionStatus: FreshnessStatus,
  telemetryStatus: FreshnessStatus,
): { effVision: number; effTelemetry: number; denominator: number } => {
  const effVision = weightVision * freshnessWeight(visionStatus);
  const effTelemetry = weightTelemetry * freshnessWeight(telemetryStatus);
  return { effVision, effTelemetry, denominator: effVision + effTelemetry };
};

/** The record's own availability flag (a property of the record, not its age). */
export const isAssessmentAvailable = (record: RiskUpdate): boolean =>
  record.assessment_available === true;

/**
 * Throws if the record violates the availability contract. Intended for tests
 * and for validating records at a trust boundary.
 */
export const assertAvailabilityInvariant = (record: RiskUpdate): void => {
  const problems: string[] = [];
  const available = record.assessment_available;

  if (typeof available !== "boolean") {
    problems.push(
      `assessment_available must be a boolean (got ${String(available)})`,
    );
  } else {
    if (available !== (record.RiskScore !== null)) {
      problems.push(
        `assessment_available=${available} but RiskScore=${String(record.RiskScore)}`,
      );
    }
    if (available !== (record.SystemHealth !== "UNAVAILABLE")) {
      problems.push(
        `assessment_available=${available} but SystemHealth=${record.SystemHealth}`,
      );
    }
    const nullable = {
      RiskScore: record.RiskScore,
      RiskLevel: record.RiskLevel,
      DominantEvidence: record.DominantEvidence,
      AlertSeverity: record.AlertSeverity,
    };
    for (const [field, value] of Object.entries(nullable)) {
      if (available && value === null) {
        problems.push(`${field} is null on an available assessment`);
      }
      if (!available && value !== null) {
        problems.push(
          `${field} is ${JSON.stringify(value)} on an unavailable assessment (must be null)`,
        );
      }
    }
  }

  if (problems.length > 0) {
    throw new Error(`Availability invariant violated: ${problems.join("; ")}`);
  }
};

/**
 * Three display states, not two. `stale` is a frontend judgement about the
 * record's *age*; `unavailable` is a property of the record itself. An
 * unavailable record has no assessment to dim, so it wins over `stale`.
 */
export const getDisplayState = (
  record: RiskUpdate,
  opts: { stale: boolean },
): "available" | "stale" | "unavailable" => {
  if (!isAssessmentAvailable(record)) return "unavailable";
  return opts.stale ? "stale" : "available";
};
