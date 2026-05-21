export type {
  AlertSeverity,
  AppConfig,
  DominantEvidence,
  FreshnessStatus,
  OperationMode,
  PreparedSessionWindow,
  RiskLevel,
  RiskUpdate,
  SessionMeta,
  SystemHealth,
  TelemetryFeatures,
  VisualClassProbability,
} from "../../ai/src/types";

export type CameraStatus = "idle" | "requesting" | "live" | "denied" | "error";

export interface DistributionDatum {
  label: string;
  count: number;
}
