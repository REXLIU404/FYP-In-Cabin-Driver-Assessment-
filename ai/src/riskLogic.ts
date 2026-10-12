import type {
  AlertSeverity,
  AppConfig,
  DominantEvidence,
  FreshnessStatus,
  PreparedSessionWindow,
  RiskLevel,
  RiskUpdate,
  SystemHealth,
} from "./types";
import { determineEvidenceType } from "./evidence";
import {
  FUSION_EPSILON,
  effectiveFusionDenominator,
  freshnessWeight,
} from "./availability";

export const DEFAULT_CONFIG: AppConfig = {
  operationMode: "LIVE_MODEL_RUNTIME",
  inferenceFps: 10,
  deltaT: 2,
  weightVision: 0.5,
  weightTelemetry: 0.5,
  emaAlpha: 0.35,
  thresholdLow: 30,
  thresholdHigh: 60,
  freshnessTolerance: 3,
  enableEvidenceInterpretation: true,
};

const round3 = (value: number) => Number(value.toFixed(3));
const round1 = (value: number) => Number(value.toFixed(1));
const clamp = (value: number) => Math.min(1, Math.max(0, value));
const alertSeverityMap: Record<RiskLevel, AlertSeverity> = {
  Low: "NORMAL",
  Medium: "CAUTION",
  High: "HIGH_ALERT",
};

/**
 * Freshness-weighted late fusion on a 0-100 scale, rounded to 1 decimal place.
 *
 * Returns `null` - never 0 - when the effective fusion denominator is zero
 * (both branches missing, or every branch that has evidence carries zero
 * weight): there is nothing to fuse, and 0 would read as "safe".
 */
export const computeRiskScore = (
  pD: number,
  pT: number,
  weightVision = 0.5,
  weightTelemetry = 0.5,
  visionStatus: FreshnessStatus = "fresh",
  telemetryStatus: FreshnessStatus = "fresh",
): number | null => {
  const { effVision, effTelemetry, denominator } = effectiveFusionDenominator(
    weightVision,
    weightTelemetry,
    visionStatus,
    telemetryStatus,
  );

  if (denominator <= FUSION_EPSILON) return null;

  return round1(
    ((effVision * clamp(pD) + effTelemetry * clamp(pT)) / denominator) * 100,
  );
};

/**
 * Per-branch share of the fused score. `null` when the assessment is
 * unavailable (zero effective denominator): there are no contributions to
 * report, and `{0, 0, 0}` would be a fabricated reading.
 */
export const computeRiskContributions = (
  pD: number,
  pT: number,
  weightVision = 0.5,
  weightTelemetry = 0.5,
  visionStatus: FreshnessStatus = "fresh",
  telemetryStatus: FreshnessStatus = "fresh",
): { vision: number; telemetry: number; total: number } | null => {
  const { effVision, effTelemetry, denominator } = effectiveFusionDenominator(
    weightVision,
    weightTelemetry,
    visionStatus,
    telemetryStatus,
  );

  if (denominator <= FUSION_EPSILON) return null;

  const vision = ((effVision * clamp(pD)) / denominator) * 100;
  const telemetry = ((effTelemetry * clamp(pT)) / denominator) * 100;

  return {
    vision: round1(vision),
    telemetry: round1(telemetry),
    total: round1(vision + telemetry),
  };
};

/**
 * Maps a (rounded) score to a level. The null check comes FIRST: in JavaScript
 * `null < 30` is `true`, so letting null reach the comparison would report an
 * unavailable window as "Low".
 */
export const mapRiskLevel = (
  score: number | null,
  low = DEFAULT_CONFIG.thresholdLow,
  high = DEFAULT_CONFIG.thresholdHigh,
): RiskLevel | null => {
  if (score === null) return null;
  return score < low ? "Low" : score < high ? "Medium" : "High";
};

export const mapAlertSeverity = (
  level: RiskLevel | null,
): AlertSeverity | null => (level === null ? null : alertSeverityMap[level]);

/**
 * Health is derived from the effective fusion denominator, not from counting
 * `missing` flags:
 *   denominator <= FUSION_EPSILON          -> UNAVAILABLE
 *   else any branch not "fresh"            -> DEGRADED
 *   else                                   -> FULL
 * The FULL / DEGRADED boundary looks only at freshness, never at the weights.
 */
export const mapSystemHealth = (
  visionStatus: FreshnessStatus,
  telemetryStatus: FreshnessStatus,
  weightVision = 0.5,
  weightTelemetry = 0.5,
): SystemHealth => {
  const { denominator } = effectiveFusionDenominator(
    weightVision,
    weightTelemetry,
    visionStatus,
    telemetryStatus,
  );
  if (denominator <= FUSION_EPSILON) return "UNAVAILABLE";
  if (visionStatus !== "fresh" || telemetryStatus !== "fresh")
    return "DEGRADED";
  return "FULL";
};

export const determineDominantEvidence = (
  pD: number,
  pT: number,
  visionStatus: FreshnessStatus,
  telemetryStatus: FreshnessStatus,
  riskScore: number | null,
  lowThreshold = DEFAULT_CONFIG.thresholdLow,
  gap = 0.15,
  weightVision = 0.5,
  weightTelemetry = 0.5,
): DominantEvidence | null => {
  return determineEvidenceType({
    pDistraction: pD,
    pTelemetry: pT,
    riskScore,
    systemHealth: mapSystemHealth(
      visionStatus,
      telemetryStatus,
      weightVision,
      weightTelemetry,
    ),
    thresholdLow: lowThreshold,
    gap,
  });
};

const asPercent = (value: number) => `${Math.round(value * 100)}%`;

/**
 * Names which side(s) left the effective fusion denominator at zero. Only
 * called for unavailable windows, where every branch is either missing or
 * carries zero fusion weight.
 */
const describeUnavailableCause = (
  visionStatus: FreshnessStatus,
  telemetryStatus: FreshnessStatus,
  weightVision: number,
  weightTelemetry: number,
) => {
  if (visionStatus === "missing" && telemetryStatus === "missing") {
    return "both the vision and telemetry inputs are missing";
  }
  const branchReason = (
    name: string,
    status: FreshnessStatus,
    weight: number,
  ) => {
    if (status === "missing") return `the ${name} input is missing`;
    if (weight * freshnessWeight(status) <= FUSION_EPSILON)
      return `the ${name} branch has zero fusion weight`;
    return null;
  };
  const reasons = [
    branchReason("vision", visionStatus, weightVision),
    branchReason("telemetry", telemetryStatus, weightTelemetry),
  ].filter((reason): reason is string => reason !== null);
  return reasons.join(" and ");
};

const buildExplanation = (
  dominant: DominantEvidence | null,
  riskLevel: RiskLevel | null,
  pD: number,
  pT: number,
  visionStatus: FreshnessStatus,
  telemetryStatus: FreshnessStatus,
  weightVision: number,
  weightTelemetry: number,
) => {
  // Availability first. The unavailable text deliberately names no level.
  if (dominant === null || riskLevel === null) {
    return `No risk assessment is available because ${describeUnavailableCause(
      visionStatus,
      telemetryStatus,
      weightVision,
      weightTelemetry,
    )}, so the effective fusion denominator is zero and there is no evidence to fuse.`;
  }
  if (dominant === "Vision-dominant") {
    return `Vision evidence is driving the ${riskLevel.toLowerCase()} risk output because P_distraction (${asPercent(pD)}) is materially higher than P_telemetry_anomaly (${asPercent(pT)}).`;
  }
  if (dominant === "Telemetry-dominant") {
    return `Telemetry non-safe behaviour evidence is driving the ${riskLevel.toLowerCase()} risk output because P_telemetry_anomaly (${asPercent(pT)}) is materially higher than P_distraction (${asPercent(pD)}).`;
  }
  if (dominant === "Combined evidence") {
    return `Vision and telemetry evidence are both contributing to the ${riskLevel.toLowerCase()} risk output.`;
  }
  if (dominant === "Partial evidence") {
    return `The output is based on partial modality evidence because one input branch is stale or missing.`;
  }
  return "The selected monitoring window is below the low-risk threshold.";
};

export const buildRiskUpdate = (
  window: PreparedSessionWindow,
  sessionId: string,
  config: AppConfig,
  previousRecord: RiskUpdate | undefined,
  windowId: number,
): RiskUpdate => {
  const currentDistraction =
    window.vision_status === "missing" ? 0 : window.P_distraction;
  const smoothedDistraction =
    previousRecord && window.vision_status === "fresh"
      ? round3(
          config.emaAlpha * currentDistraction +
            (1 - config.emaAlpha) * previousRecord.P_distraction,
        )
      : round3(currentDistraction);
  const telemetryAnomaly = round3(window.P_telemetry_anomaly);
  const score = computeRiskScore(
    smoothedDistraction,
    telemetryAnomaly,
    config.weightVision,
    config.weightTelemetry,
    window.vision_status,
    window.telemetry_status,
  );
  // Round happens inside computeRiskScore, so the level is mapped from the
  // ROUNDED score (e.g. 29.951 -> 30 -> Medium).
  const level = mapRiskLevel(score, config.thresholdLow, config.thresholdHigh);
  const systemHealth = mapSystemHealth(
    window.vision_status,
    window.telemetry_status,
    config.weightVision,
    config.weightTelemetry,
  );
  const dominant = determineDominantEvidence(
    smoothedDistraction,
    telemetryAnomaly,
    window.vision_status,
    window.telemetry_status,
    score,
    config.thresholdLow,
    undefined,
    config.weightVision,
    config.weightTelemetry,
  );

  return {
    session_id: sessionId,
    window_id: windowId,
    timestamp: window.timestamp,
    P_distraction: smoothedDistraction,
    P_telemetry_anomaly: telemetryAnomaly,
    assessment_available: score !== null,
    RiskScore: score,
    RiskLevel: level,
    DominantEvidence: dominant,
    AlertSeverity: mapAlertSeverity(level),
    SystemHealth: systemHealth,
    operation_mode: config.operationMode,
    modality_freshness: {
      vision: window.vision_status,
      telemetry: window.telemetry_status,
    },
    latency_ms: window.latency_ms,
    visual_top_classes: window.visual_top_classes,
    telemetry_behavior_classes: window.telemetry_behavior_classes,
    telemetry_feature_contributions: window.telemetry_feature_contributions,
    telemetry_features: window.telemetry_features,
    explanation: buildExplanation(
      dominant,
      level,
      smoothedDistraction,
      telemetryAnomaly,
      window.vision_status,
      window.telemetry_status,
      config.weightVision,
      config.weightTelemetry,
    ),
  };
};
