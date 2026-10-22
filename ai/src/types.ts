export type RiskLevel = "Low" | "Medium" | "High";
export type AlertSeverity = "NORMAL" | "CAUTION" | "HIGH_ALERT";
export type SystemHealth = "FULL" | "DEGRADED" | "UNAVAILABLE";
export type OperationMode = "PREPARED_SESSION_RUNTIME" | "LIVE_MODEL_RUNTIME";
/**
 * `stale` is HISTORICAL. Ruling A (D13): the runtime never produces it - evidence
 * older than `freshness_tolerance_s` is EXPIRED and recorded as `missing`, with the
 * reason in `provenance.{vision,telemetry}_expired` / `_age_s`. The literal stays so
 * that a record written before the ruling (a stored session, an old export) still
 * type-checks, reads and renders, and so that the pure fusion functions can still be
 * given the 0.45 tier.
 */
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

/**
 * Why a branch carried no weight, recorded for BOTH branches of every new record
 * (`RiskUpdate.provenance`). `*_expired` is true only when the branch had evidence
 * and it was rejected for its age (or declared stale); a branch that never arrived is
 * `false`. `*_age_s` is max(0, processing time - capture time) in seconds, 3 dp, or
 * null when there is no input or no capture time to measure.
 */
export interface EvidenceExpiry {
  vision_expired: boolean;
  vision_age_s: number | null;
  telemetry_expired: boolean;
  telemetry_age_s: number | null;
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
  /**
   * The replay's own expiry verdict (see `EvidenceExpiry`), decided where the window
   * is built. Optional so a hand-made window need not carry it; `buildRiskUpdate`
   * then records "not expired, age unknown".
   */
  expiry?: EvidenceExpiry;
}

export interface RiskUpdate {
  session_id: string;
  window_id: number;
  timestamp: string;
  P_distraction: number;
  P_telemetry_anomaly: number;
  /**
   * False when the effective fusion denominator is zero (no usable evidence).
   * Then RiskScore / RiskLevel / DominantEvidence / AlertSeverity are all null
   * and SystemHealth is "UNAVAILABLE" - never a fabricated 0 / Low / NORMAL.
   * Invariant: assessment_available === (RiskScore !== null)
   *                                  === (SystemHealth !== "UNAVAILABLE").
   */
  assessment_available: boolean;
  RiskScore: number | null;
  RiskLevel: RiskLevel | null;
  DominantEvidence: DominantEvidence | null;
  AlertSeverity: AlertSeverity | null;
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
  provenance?: {
    provider?: string;
    vision_source?: string;
    telemetry_source?: string;
    vision_model_sha256?: string;
    telemetry_model_sha256?: string;
    request_id?: string;
    captured_at?: string | null;
    telemetry_timestamp?: string | null;
    P_distraction_raw?: number;
    P_telemetry_raw?: number;
    /** Ruling A (D13): why a branch scored as missing. Absent on a pre-ruling record. */
    vision_expired?: boolean;
    vision_age_s?: number | null;
    telemetry_expired?: boolean;
    telemetry_age_s?: number | null;
    timing_ms?: Record<string, number>;
    /**
     * Live only, and only on a window that carries `telemetry_feature_contributions`: what they
     * MEAN. "xgboost_treeshap_neg_safe_margin" = TreeSHAP local attribution on the Safe-class
     * score, sign flipped so that a positive value pushes toward unsafe; log-odds; not causal,
     * not a dataset-level feature importance. `..._baseline` is -(the Safe-class bias), so that
     * sum(contributions) + baseline = -margin_Safe. Absent on a replay record, whose
     * contributions are the hand-written FYP1 table.
     */
    telemetry_contribution_method?: string;
    telemetry_contribution_baseline?: number;
    fusion_config?: {
      weight_vision: number;
      weight_telemetry: number;
      threshold_low: number;
      threshold_high: number;
      ema_alpha: number;
      freshness_tolerance_s: number;
    };
  };
}

export interface SessionMeta {
  id: string;
  created_at: string;
  total_windows: number;
  operation_mode?: OperationMode;
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
  inferenceFps: number;
}
