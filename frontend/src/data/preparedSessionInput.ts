import type {
  PreparedSessionWindow,
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
  speed: number;
  acceleration: number;
  steering_angle: number;
  brake_usage: number;
  lane_deviation: number;
  road_type: string;
  traffic_condition: string;
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
const clamp = (value: number) => Math.min(1, Math.max(0, value));
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

const inferTelemetryAnomaly = (record: PreparedTelemetryRecord): number => {
  if (!record.telemetry_available) return 0;

  const speedRisk = clamp((record.speed - 45) / 45);
  const accelerationRisk = clamp(Math.abs(record.acceleration) / 3);
  const steeringRisk = clamp(Math.abs(record.steering_angle) / 18);
  const brakeRisk = clamp(record.brake_usage);
  const laneRisk = clamp(record.lane_deviation);

  return round3(
    speedRisk * 0.08 +
      accelerationRisk * 0.18 +
      steeringRisk * 0.22 +
      brakeRisk * 0.24 +
      laneRisk * 0.28,
  );
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
  speed: toNumber(row.speed),
  acceleration: toNumber(row.acceleration),
  steering_angle: toNumber(row.steering_angle),
  brake_usage: toNumber(row.brake_usage),
  lane_deviation: toNumber(row.lane_deviation),
  road_type: row.road_type,
  traffic_condition: row.traffic_condition,
});

const telemetryFeatures = (
  record: PreparedTelemetryRecord,
): TelemetryFeatures | null => {
  if (!record.telemetry_available) return null;

  return {
    speed: record.speed,
    acceleration: record.acceleration,
    steering_angle: record.steering_angle,
    brake_usage: record.brake_usage,
    lane_deviation: record.lane_deviation,
    road_type: record.road_type,
    traffic_condition: record.traffic_condition,
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
    telemetry_features: telemetryFeatures(record),
    latency_ms: 38 + record.window_id * 4,
  }));
