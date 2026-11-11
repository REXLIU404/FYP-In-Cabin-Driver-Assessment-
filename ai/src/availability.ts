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

/**
 * Freshness weights: fresh 1.0, missing 0.0 - and stale 0.45, HISTORICAL ONLY.
 *
 * Ruling A (D13): the runtime no longer produces `stale`. Evidence older than
 * `freshness_tolerance_s` is EXPIRED and arrives here as `missing` (weight 0), with
 * the reason kept in the record's provenance (`{modality}_expired` / `_age_s`). The
 * 0.45 tier is retained, unchanged, only so that records written before the ruling
 * keep reading and rendering. It is a legacy compatibility weight, not a model input
 * the pipeline can reach, and not a validated number.
 */
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

export type Branch = "vision" | "telemetry";

export interface BranchExpiry {
  /** The branch had evidence and it was rejected for its age (ruling A, D13). */
  expired: boolean;
  /** Seconds, as recorded; null when not expired or when no age was measurable. */
  ageS: number | null;
}

/**
 * Why one branch carried no weight, read from the record's provenance. A branch is
 * "expired" only if it scored as `missing` AND the provenance says it expired: a
 * branch that never arrived is `missing` but not expired, and a record written before
 * ruling A has no such fields at all (nothing expired, as far as it can say).
 */
export const branchExpiry = (
  record: Pick<RiskUpdate, "modality_freshness" | "provenance">,
  branch: Branch,
): BranchExpiry => {
  const provenance = record.provenance;
  const flag =
    branch === "vision"
      ? provenance?.vision_expired
      : provenance?.telemetry_expired;
  const age =
    branch === "vision"
      ? provenance?.vision_age_s
      : provenance?.telemetry_age_s;
  const expired =
    flag === true && record.modality_freshness[branch] === "missing";
  return { expired, ageS: expired && typeof age === "number" ? age : null };
};

/**
 * The branch status as text: the stored status, except that an expired branch says so
 * ("expired (4 s)") instead of reading the same as one that never arrived
 * ("missing"). The age is printed as recorded - the producer already rounded it to
 * 3 dp, half up.
 */
export const describeBranchStatus = (
  status: FreshnessStatus,
  expiry: BranchExpiry,
): string => {
  if (!expiry.expired) return status;
  return expiry.ageS === null ? "expired" : `expired (${expiry.ageS} s)`;
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

/**
 * A risk record as it may arrive from an UNTRUSTED boundary (localStorage, or a
 * response from an older backend): everything in `RiskUpdate` except that
 * `assessment_available` may be absent.
 */
export type StoredRiskUpdate = Omit<RiskUpdate, "assessment_available"> & {
  assessment_available?: boolean;
};

/**
 * Availability of a record that may predate the `assessment_available` flag.
 *
 * If the record carries the flag, that is the answer. Otherwise it is derived
 * from the two fields that existed before it: `RiskScore !== null` AND
 * `SystemHealth !== "UNAVAILABLE"`.
 *
 * The derivation is the only correct one. The two tempting one-liners fail in
 * opposite directions on a legacy row:
 *   !record.assessment_available          -> every legacy row is "unavailable"
 *                                            (stored history vanishes from the UI)
 *   record.assessment_available === false -> every legacy row is "available",
 *                                            including a both-missing window that
 *                                            was stored as 0 / Low / NORMAL /
 *                                            UNAVAILABLE.
 */
export const deriveAssessmentAvailable = (
  record: Pick<StoredRiskUpdate, "RiskScore" | "SystemHealth"> & {
    assessment_available?: boolean;
  },
): boolean =>
  typeof record.assessment_available === "boolean"
    ? record.assessment_available
    : record.RiskScore != null && record.SystemHealth !== "UNAVAILABLE";

/**
 * The single normalisation applied at every untrusted boundary (the localStorage
 * reader and the API client).
 *
 * A record that already carries `assessment_available` is returned as it is:
 * the backend is the canonical producer, and quietly "repairing" a record that
 * contradicts its own flag would hide a backend bug. Only a legacy record (no
 * flag) is migrated: availability is derived (see above) and, for an unassessable
 * window, the four nullable fields are set to null in place of the fabricated
 * `0 / Low / NORMAL / "Partial evidence"` the old pipeline stored.
 */
export const normalizeRiskUpdate = (raw: StoredRiskUpdate): RiskUpdate => {
  const flag = raw.assessment_available;
  if (typeof flag === "boolean") return { ...raw, assessment_available: flag };

  if (deriveAssessmentAvailable(raw)) {
    return { ...raw, assessment_available: true };
  }
  return {
    ...raw,
    assessment_available: false,
    RiskScore: null,
    RiskLevel: null,
    DominantEvidence: null,
    AlertSeverity: null,
  };
};
