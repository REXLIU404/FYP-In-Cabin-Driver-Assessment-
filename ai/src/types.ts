export type RiskLevel = "Low" | "Medium" | "High";
export type AlertSeverity = "NORMAL" | "CAUTION" | "HIGH_ALERT";
export type SystemHealth = "FULL" | "DEGRADED" | "UNAVAILABLE";
export type OperationMode = "PREPARED_SESSION_RUNTIME";
export type FreshnessStatus = "fresh" | "stale" | "missing";

export type DominantEvidence =
  | "Vision-dominant"
  | "Telemetry-dominant"
  | "Combined evidence"
  | "Partial evidence"
  | "Low observed risk";

export interface VisualClassProbability {
  label: string;
  probability: number;
}

export type TelemetryBehaviorLabel = "Safe" | "Aggressive" | "Distracted";

export interface TelemetryBehaviorProbability {
  label: TelemetryBehaviorLabel;
  probability: number;
}

export interface TelemetryFeatureContribution {
  feature: keyof TelemetryFeatures;
  contribution: number;
}

export interface TelemetryFeatures {
  speed_kmph: number;
  accel_x: number;
  accel_y: number;
  brake_pressure: number;
  steering_angle: number;
  throttle: number;
  lane_deviation: number;
  headway_distance: number;
}

export interface PreparedSessionWindow {
  timestamp: string;
  P_distraction: number;
  P_telemetry_anomaly: number;
  vision_status: FreshnessStatus;
  telemetry_status: FreshnessStatus;
  visual_top_classes: VisualClassProbability[];
  telemetry_behavior_classes: TelemetryBehaviorProbability[];
  telemetry_feature_contributions: TelemetryFeatureContribution[];
  telemetry_features: TelemetryFeatures | null;
  latency_ms: number;
}

export interface RiskUpdate {
  session_id: string;
  window_id: number;
  timestamp: string;
  P_distraction: number;
  P_telemetry_anomaly: number;
  RiskScore: number;
  RiskLevel: RiskLevel;
  DominantEvidence: DominantEvidence;
  AlertSeverity: AlertSeverity;
  SystemHealth: SystemHealth;
  operation_mode: OperationMode;
  modality_freshness: {
    vision: FreshnessStatus;
    telemetry: FreshnessStatus;
  };
  latency_ms: number;
  visual_top_classes: VisualClassProbability[];
  telemetry_behavior_classes: TelemetryBehaviorProbability[];
  telemetry_feature_contributions?: TelemetryFeatureContribution[];
  telemetry_features: TelemetryFeatures | null;
  explanation: string;
  flagged?: boolean;
}

export interface SessionMeta {
  id: string;
  created_at: string;
  total_windows: number;
}

export interface AppConfig {
  operationMode: OperationMode;
  deltaT: number;
  weightVision: number;
  weightTelemetry: number;
  emaAlpha: number;
  thresholdLow: number;
  thresholdHigh: number;
  freshnessTolerance: number;
  enableEvidenceInterpretation: boolean;
}
