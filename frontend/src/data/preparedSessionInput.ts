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

const preparedVisualEvidence: Record<string, VisualClassProbability[]> = {
  "frame_0001.jpg": visualClasses(
    0.88,
    0.02,
    0.01,
    0.01,
    0.01,
    0.03,
    0.01,
    0.01,
    0.01,
    0.01,
  ),
  "frame_0002.jpg": visualClasses(
    0.78,
    0.04,
    0.03,
    0.02,
    0.02,
    0.06,
    0.02,
    0.01,
    0.01,
    0.01,
  ),
  "frame_0003.jpg": visualClasses(
    0.55,
    0.07,
    0.05,
    0.04,
    0.03,
    0.08,
    0.04,
    0.05,
    0.03,
    0.06,
  ),
  "frame_0004.jpg": visualClasses(
    0.22,
    0.25,
    0.18,
    0.08,
    0.07,
    0.06,
    0.04,
    0.05,
    0.02,
    0.03,
  ),
  "frame_0006.jpg": visualClasses(
    0.28,
    0.1,
    0.08,
    0.14,
    0.11,
    0.08,
    0.06,
    0.09,
    0.03,
    0.03,
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

const preparedTelemetryFeatureContributions: Record<
  number,
  TelemetryFeatureContribution[]
> = {
  1: [
    { feature: "headway_distance", contribution: 0.12 },
    { feature: "brake_pressure", contribution: 0.06 },
    { feature: "lane_deviation", contribution: -0.03 },
  ],
  2: [
    { feature: "headway_distance", contribution: 0.1 },
    { feature: "steering_angle", contribution: 0.07 },
    { feature: "lane_deviation", contribution: 0.05 },
  ],
  3: [
    { feature: "brake_pressure", contribution: 0.22 },
    { feature: "accel_x", contribution: 0.18 },
    { feature: "throttle", contribution: 0.15 },
  ],
  5: [
    { feature: "speed_kmph", contribution: 0.16 },
    { feature: "steering_angle", contribution: 0.11 },
    { feature: "throttle", contribution: 0.1 },
  ],
  6: [
    { feature: "brake_pressure", contribution: 0.24 },
    { feature: "steering_angle", contribution: 0.2 },
    { feature: "headway_distance", contribution: 0.14 },
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
