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

export interface TelemetryFeatures {
  speed: number;
  acceleration: number;
  steering_angle: number;
  brake_usage: number;
  lane_deviation: number;
  road_type: string;
  traffic_condition: string;
}

export interface PreparedSessionWindow {
  timestamp: string;
  P_distraction: number;
  P_telemetry_anomaly: number;
  vision_status: FreshnessStatus;
  telemetry_status: FreshnessStatus;
  visual_top_classes: VisualClassProbability[];
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
