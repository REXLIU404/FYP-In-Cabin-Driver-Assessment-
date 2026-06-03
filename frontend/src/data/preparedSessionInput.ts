import type {
  PreparedSessionWindow,
  TelemetryBehaviorProbability,
  TelemetryFeatureContribution,
  TelemetryFeatures,
  VisualClassProbability,
} from "../types";
import metadataRaw from "../../../ai/prototype-data/prepared_sessions/session_001/session_metadata.json?raw";
import telemetryCsv from "../../../ai/prototype-data/prepared_sessions/session_001/telemetry.csv?raw";

interface PreparedSessionMetadata {
  session_id: string;
  description: string;
  delta_t_seconds: number;
  start_time: string;
  frame_source: string;
  telemetry_source: string;
}

interface PreparedTelemetryRecord {
  window_id: number;
  timestamp: string;
  frame_file: string;
  vision_available: boolean;
  telemetry_available: boolean;
  telemetry_age_s: number;
  speed_kmph: number;
  accel_x: number;
  accel_y: number;
  brake_pressure: number;
  steering_angle: number;
  throttle: number;
  lane_deviation: number;
  headway_distance: number;
  p_safe: number;
  p_aggressive: number;
  p_distracted: number;
}

export const PREPARED_SESSION_METADATA = JSON.parse(
  metadataRaw,
) as PreparedSessionMetadata;

const parseCsv = (source: string) => {
  const [headerLine, ...rows] = source.trim().split(/\r?\n/);
  const headers = headerLine.split(",");

  return rows.map((row) => {
    const values = row.split(",");
    return Object.fromEntries(
      headers.map((header, index) => [header, values[index] ?? ""]),
    );
  });
};

const toNumber = (value: string) => Number(value);
const toBoolean = (value: string) => value === "1";
const round3 = (value: number) => Number(value.toFixed(3));

const visualClasses = (
  safe: number,
  textingRight: number,
  phoneRight: number,
  textingLeft: number,
  phoneLeft: number,
  radio: number,
  drinking: number,
  reaching: number,
  makeup: number,
  passenger: number,
): VisualClassProbability[] => [
  { label: "safe_driving", probability: safe },
  { label: "texting_right", probability: textingRight },
  { label: "phone_right", probability: phoneRight },
  { label: "texting_left", probability: textingLeft },
  { label: "phone_left", probability: phoneLeft },
  { label: "operating_radio", probability: radio },
  { label: "drinking", probability: drinking },
  { label: "reaching_behind", probability: reaching },
  { label: "hair_makeup", probability: makeup },
  { label: "talking_to_passenger", probability: passenger },
];

// Each frame maps to ONE deterministic vision distribution, so P_distraction
// (= 1 - safe_driving) is fixed per frame. Probabilities sum to 1. Frame names
// are semantic prototypes (the UI shows the live camera, not these frames), so
// they need no backing image file. See ai/prototype-data/.../missing_cases.csv
// for the per-window expected risk/evidence matrix these produce.
const preparedVisualEvidence: Record<string, VisualClassProbability[]> = {
  // calm, eyes-on-road (P_distraction ~= 0.07)
  "frame_safe_a.jpg": visualClasses(
    0.93, 0.0076, 0.0078, 0.0078, 0.0078, 0.0078, 0.0078, 0.0078, 0.0078, 0.0078,
  ),
  // mostly attentive (P_distraction ~= 0.13)
  "frame_safe_b.jpg": visualClasses(
    0.87, 0.0118, 0.0118, 0.0118, 0.0118, 0.0238, 0.0118, 0.0118, 0.0118, 0.0236,
  ),
  // mild distraction (P_distraction ~= 0.30)
  "frame_mild.jpg": visualClasses(
    0.7, 0.0214, 0.0214, 0.0214, 0.0214, 0.0644, 0.0214, 0.0214, 0.0429, 0.0643,
  ),
  // texting, hand off wheel (P_distraction ~= 0.60)
  "frame_texting.jpg": visualClasses(
    0.4, 0.2, 0.04, 0.12, 0.04, 0.04, 0.04, 0.04, 0.04, 0.04,
  ),
  // phone to ear (P_distraction ~= 0.70)
  "frame_phone.jpg": visualClasses(
    0.3, 0.0467, 0.2331, 0.0467, 0.14, 0.0467, 0.0467, 0.0467, 0.0467, 0.0467,
  ),
  // severe, head turned (P_distraction ~= 0.82)
  "frame_severe.jpg": visualClasses(
    0.18, 0.154, 0.1537, 0.1025, 0.1025, 0.0512, 0.0512, 0.1025, 0.0512, 0.0512,
  ),
};

const inferDistraction = (
  frameFile: string,
  visionAvailable: boolean,
): number => {
  if (!visionAvailable) return 0;
  const classes = preparedVisualEvidence[frameFile] ?? [];
  const safe = classes.find(
    (item) => item.label === "safe_driving" || item.label === "normal_driving",
  );
  return round3(1 - (safe?.probability ?? 1));
};

const telemetryBehaviorClasses = (
  record: PreparedTelemetryRecord,
): TelemetryBehaviorProbability[] => {
  if (!record.telemetry_available) return [];

  return [
    { label: "Safe", probability: record.p_safe },
    { label: "Aggressive", probability: record.p_aggressive },
    { label: "Distracted", probability: record.p_distracted },
  ];
};

// Keyed by window_id; matches the scenario phases in telemetry.csv. Safe windows
// carry no dominant risk driver, so they are intentionally absent (-> []).
const preparedTelemetryFeatureContributions: Record<
  number,
  TelemetryFeatureContribution[]
> = {
  5: [
    { feature: "lane_deviation", contribution: 0.06 },
    { feature: "steering_angle", contribution: 0.05 },
    { feature: "throttle", contribution: 0.04 },
  ],
  8: [
    { feature: "brake_pressure", contribution: 0.22 },
    { feature: "accel_x", contribution: 0.18 },
    { feature: "throttle", contribution: 0.15 },
  ],
  9: [
    { feature: "brake_pressure", contribution: 0.24 },
    { feature: "accel_x", contribution: 0.19 },
    { feature: "throttle", contribution: 0.16 },
  ],
  10: [
    { feature: "brake_pressure", contribution: 0.26 },
    { feature: "steering_angle", contribution: 0.2 },
    { feature: "accel_x", contribution: 0.17 },
  ],
  11: [
    { feature: "steering_angle", contribution: 0.26 },
    { feature: "lane_deviation", contribution: 0.2 },
    { feature: "accel_x", contribution: 0.16 },
  ],
  12: [
    { feature: "accel_x", contribution: 0.18 },
    { feature: "throttle", contribution: 0.14 },
    { feature: "brake_pressure", contribution: 0.12 },
  ],
  13: [
    { feature: "accel_x", contribution: 0.12 },
    { feature: "steering_angle", contribution: 0.1 },
    { feature: "lane_deviation", contribution: 0.09 },
  ],
  16: [
    { feature: "steering_angle", contribution: 0.2 },
    { feature: "brake_pressure", contribution: 0.16 },
    { feature: "lane_deviation", contribution: 0.12 },
  ],
  18: [
    { feature: "brake_pressure", contribution: 0.18 },
    { feature: "accel_x", contribution: 0.14 },
    { feature: "throttle", contribution: 0.12 },
  ],
};

const telemetryFeatureContributions = (
  record: PreparedTelemetryRecord,
): TelemetryFeatureContribution[] => {
  if (!record.telemetry_available) return [];
  return preparedTelemetryFeatureContributions[record.window_id] ?? [];
};

const inferTelemetryAnomaly = (record: PreparedTelemetryRecord): number => {
  if (!record.telemetry_available) return 0;
  return round3(1 - record.p_safe);
};

const buildTimestamp = (time: string) =>
  new Date(`2026-05-06T${time}+08:00`).toISOString();

const parsePreparedRecord = (
  row: Record<string, string>,
): PreparedTelemetryRecord => ({
  window_id: toNumber(row.window_id),
  timestamp: row.timestamp,
  frame_file: row.frame_file,
  vision_available: toBoolean(row.vision_available),
  telemetry_available: toBoolean(row.telemetry_available),
  telemetry_age_s: toNumber(row.telemetry_age_s),
  speed_kmph: toNumber(row.speed_kmph),
  accel_x: toNumber(row.accel_x),
  accel_y: toNumber(row.accel_y),
  brake_pressure: toNumber(row.brake_pressure),
  steering_angle: toNumber(row.steering_angle),
  throttle: toNumber(row.throttle),
  lane_deviation: toNumber(row.lane_deviation),
  headway_distance: toNumber(row.headway_distance),
  p_safe: toNumber(row.p_safe),
  p_aggressive: toNumber(row.p_aggressive),
  p_distracted: toNumber(row.p_distracted),
});

const telemetryFeatures = (
  record: PreparedTelemetryRecord,
): TelemetryFeatures | null => {
  if (!record.telemetry_available) return null;

  return {
    speed_kmph: record.speed_kmph,
    accel_x: record.accel_x,
    accel_y: record.accel_y,
    brake_pressure: record.brake_pressure,
    steering_angle: record.steering_angle,
    throttle: record.throttle,
    lane_deviation: record.lane_deviation,
    headway_distance: record.headway_distance,
  };
};

const freshnessStatus = (available: boolean, ageSeconds: number) => {
  if (!available) return "missing";
  return ageSeconds > 3 ? "stale" : "fresh";
};

const preparedRows = parseCsv(telemetryCsv).map(parsePreparedRecord);

export const PREPARED_SESSION_WINDOWS: PreparedSessionWindow[] = preparedRows
  .sort((a, b) => a.window_id - b.window_id)
  .map((record) => ({
    timestamp: buildTimestamp(record.timestamp),
    P_distraction: inferDistraction(record.frame_file, record.vision_available),
    P_telemetry_anomaly: inferTelemetryAnomaly(record),
    vision_status: freshnessStatus(record.vision_available, 0),
    telemetry_status: freshnessStatus(
      record.telemetry_available,
      record.telemetry_age_s,
    ),
    visual_top_classes:
      record.vision_available && record.frame_file
        ? (preparedVisualEvidence[record.frame_file] ?? [])
        : [],
    telemetry_behavior_classes: telemetryBehaviorClasses(record),
    telemetry_feature_contributions: telemetryFeatureContributions(record),
    telemetry_features: telemetryFeatures(record),
    latency_ms: 38 + record.window_id * 4,
  }));
