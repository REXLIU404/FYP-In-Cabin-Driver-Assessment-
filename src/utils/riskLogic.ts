import type {
  AlertSeverity,
  AppConfig,
  DominantEvidence,
  FreshnessStatus,
  PreparedSessionWindow,
  RiskLevel,
  RiskUpdate,
  SystemHealth,
} from "../types";
import { determineEvidenceType } from "./evidence";

export const DEFAULT_CONFIG: AppConfig = {
  operationMode: "PREPARED_SESSION_RUNTIME",
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

const freshnessWeight = (status: FreshnessStatus) => {
  if (status === "missing") return 0;
  if (status === "stale") return 0.45;
  return 1;
};

export const computeRiskScore = (
  pD: number,
  pT: number,
  weightVision = 0.5,
  weightTelemetry = 0.5,
  visionStatus: FreshnessStatus = "fresh",
  telemetryStatus: FreshnessStatus = "fresh",
) => {
  const effectiveVision = weightVision * freshnessWeight(visionStatus);
  const effectiveTelemetry = weightTelemetry * freshnessWeight(telemetryStatus);
  const total = effectiveVision + effectiveTelemetry;

  if (total === 0) return 0;

  return round1(
    ((effectiveVision * clamp(pD) + effectiveTelemetry * clamp(pT)) / total) *
      100,
  );
};

export const computeRiskContributions = (
  pD: number,
  pT: number,
  weightVision = 0.5,
  weightTelemetry = 0.5,
  visionStatus: FreshnessStatus = "fresh",
  telemetryStatus: FreshnessStatus = "fresh",
) => {
  const effectiveVision = weightVision * freshnessWeight(visionStatus);
  const effectiveTelemetry = weightTelemetry * freshnessWeight(telemetryStatus);
  const total = effectiveVision + effectiveTelemetry;

  if (total === 0) {
    return { vision: 0, telemetry: 0, total: 0 };
  }

  const vision = ((effectiveVision * clamp(pD)) / total) * 100;
  const telemetry = ((effectiveTelemetry * clamp(pT)) / total) * 100;

  return {
    vision: round1(vision),
    telemetry: round1(telemetry),
    total: round1(vision + telemetry),
  };
};

export const mapRiskLevel = (
  score: number,
  low = DEFAULT_CONFIG.thresholdLow,
  high = DEFAULT_CONFIG.thresholdHigh,
): RiskLevel => (score < low ? "Low" : score < high ? "Medium" : "High");

export const mapAlertSeverity = (level: RiskLevel): AlertSeverity =>
  alertSeverityMap[level];

export const mapSystemHealth = (
  visionStatus: FreshnessStatus,
  telemetryStatus: FreshnessStatus,
): SystemHealth => {
  if (visionStatus === "missing" && telemetryStatus === "missing")
    return "UNAVAILABLE";
  if (visionStatus !== "fresh" || telemetryStatus !== "fresh")
    return "DEGRADED";
  return "FULL";
};

export const determineDominantEvidence = (
  pD: number,
  pT: number,
  visionStatus: FreshnessStatus,
  telemetryStatus: FreshnessStatus,
  riskScore: number,
  lowThreshold = DEFAULT_CONFIG.thresholdLow,
  gap = 0.15,
): DominantEvidence => {
  return determineEvidenceType({
    pDistraction: pD,
    pTelemetry: pT,
    riskScore,
    systemHealth: mapSystemHealth(visionStatus, telemetryStatus),
    thresholdLow: lowThreshold,
    gap,
  });
};

const asPercent = (value: number) => `${Math.round(value * 100)}%`;

const buildExplanation = (
  dominant: DominantEvidence,
  riskLevel: RiskLevel,
  pD: number,
  pT: number,
) => {
  if (dominant === "Vision-dominant") {
    return `Vision evidence is driving the ${riskLevel.toLowerCase()} risk output because P_distraction (${asPercent(pD)}) is materially higher than P_telemetry_anomaly (${asPercent(pT)}).`;
  }
  if (dominant === "Telemetry-dominant") {
    return `Telemetry anomaly evidence is driving the ${riskLevel.toLowerCase()} risk output because P_telemetry_anomaly (${asPercent(pT)}) is materially higher than P_distraction (${asPercent(pD)}).`;
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
  const level = mapRiskLevel(score, config.thresholdLow, config.thresholdHigh);
  const systemHealth = mapSystemHealth(
    window.vision_status,
    window.telemetry_status,
  );
  const dominant = determineDominantEvidence(
    smoothedDistraction,
    telemetryAnomaly,
    window.vision_status,
    window.telemetry_status,
    score,
    config.thresholdLow,
  );

  return {
    session_id: sessionId,
    window_id: windowId,
    timestamp: window.timestamp,
    P_distraction: smoothedDistraction,
    P_telemetry_anomaly: telemetryAnomaly,
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
    telemetry_features: window.telemetry_features,
    explanation: buildExplanation(
      dominant,
      level,
      smoothedDistraction,
      telemetryAnomaly,
    ),
  };
};
