import type {
  FreshnessStatus,
  PreparedSessionWindow,
  TelemetryBehaviorProbability,
  TelemetryFeatureContribution,
  TelemetryFeatures,
  VisualClassProbability,
} from "../types";
import type { TelemetrySource } from "../../../ai/src/liveLoop";
import { roundHalfUp } from "../../../ai/src/riskLogic";
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
// Half UP on the decimal digits, the same rounding as the backend and the
// fusion layer. `Number(value.toFixed(3))` rounds the exact binary value, so a
// decimal tie such as 1 - 0.0635 = 0.9365 lands on 0.936 instead of 0.937.
const round3 = (value: number) => roundHalfUp(value, 3);

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
  // A branch that scores as missing carries P = 0.0 in the record - whether it never
  // arrived or EXPIRED (ruling A) - exactly as the backend's run_inference does. The
  // model output itself is not lost: the CSV row still holds it.
  if (
    !record.telemetry_available ||
    isExpired(record.telemetry_available, record.telemetry_age_s)
  ) {
    return 0;
  }
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

// The replay's evidence-age tolerance, in seconds: the same 3 s design threshold as
// the default `freshness_tolerance_s` on the backend - a design threshold, not a
// validated safety threshold.
//
// THE REPLAY IS FIXED AT 3 s; LIVE IS JUDGED BY THE BACKEND FROM THE SESSION'S OWN
// CONFIGURATION. This constant does NOT follow `AppConfig.freshnessTolerance`: the
// prepared windows are built once, at module load, before any configuration exists,
// so making them follow the setting would mean rebuilding the replay per setting
// change (and moving the pinned replay outputs, e.g. window 16 in
// missing_cases.csv). The replay is the retained legacy path, so it keeps one fixed,
// documented tolerance; the setting applies to Live sessions only.
const PREPARED_FRESHNESS_TOLERANCE_S = 3;

/**
 * Ruling A (D13): evidence whose age exceeds the tolerance (strictly: exactly 3 s is
 * still fresh) is EXPIRED. A `null` age means there is no capture time to measure, so
 * nothing expires. A branch that was never received (`available` false) is not
 * "expired" - it is absent.
 */
const isExpired = (available: boolean, ageSeconds: number | null) =>
  available &&
  ageSeconds !== null &&
  ageSeconds > PREPARED_FRESHNESS_TOLERANCE_S;

/**
 * An expired branch is `missing`, exactly like one that never arrived (weight 0); the
 * runtime no longer produces `stale`. The reason travels separately, in `expiry`.
 */
const freshnessStatus = (
  available: boolean,
  ageSeconds: number | null,
): FreshnessStatus =>
  !available || isExpired(available, ageSeconds) ? "missing" : "fresh";

// `telemetry_age_s` is 999 on a row with no telemetry: a sentinel, not an age.
const telemetryAge = (record: PreparedTelemetryRecord): number | null =>
  record.telemetry_available ? record.telemetry_age_s : null;

/**
 * The replay's one parsing path: telemetry CSV text -> ordered windows. The
 * shipped session is `buildPreparedWindows(telemetryCsv)`; it is exported so a
 * test can feed it a CSV whose probabilities sit on a decimal rounding tie.
 */
export const buildPreparedWindows = (csv: string): PreparedSessionWindow[] =>
  parseCsv(csv)
    .map(parsePreparedRecord)
    .sort((a, b) => a.window_id - b.window_id)
    .map((record) => ({
      timestamp: buildTimestamp(record.timestamp),
      P_distraction: inferDistraction(
        record.frame_file,
        record.vision_available,
      ),
      P_telemetry_anomaly: inferTelemetryAnomaly(record),
      // The prepared CSV carries no capture time for the frame, so vision has no age:
      // it can neither expire nor report an age (null), only be present or absent.
      vision_status: freshnessStatus(record.vision_available, null),
      telemetry_status: freshnessStatus(
        record.telemetry_available,
        telemetryAge(record),
      ),
      expiry: {
        vision_expired: isExpired(record.vision_available, null),
        vision_age_s: null,
        telemetry_expired: isExpired(
          record.telemetry_available,
          telemetryAge(record),
        ),
        telemetry_age_s: telemetryAge(record),
      },
      visual_top_classes:
        record.vision_available && record.frame_file
          ? (preparedVisualEvidence[record.frame_file] ?? [])
          : [],
      telemetry_behavior_classes: telemetryBehaviorClasses(record),
      telemetry_feature_contributions: telemetryFeatureContributions(record),
      telemetry_features: telemetryFeatures(record),
      latency_ms: 38 + record.window_id * 4,
    }));

export const PREPARED_SESSION_WINDOWS: PreparedSessionWindow[] =
  buildPreparedWindows(telemetryCsv);

/**
 * One row of the prepared session as the LIVE runtime sees it: the raw telemetry
 * and nothing else. No probability of any kind - the trained XGBoost produces
 * those, on the backend, from `telemetry_features`.
 */
export interface PreparedRawTelemetryRow {
  timestamp: string;
  /** The 8 features in their fixed order; `null` on a row with no telemetry (14, 17). */
  telemetry_features: TelemetryFeatures | null;
  /** The row's recorded age; `null` where there is no telemetry (the CSV's 999 sentinel). */
  telemetry_age_s: number | null;
}

/**
 * The prepared session reduced to its raw telemetry (plan Task 9, Step 1). Same
 * parsing path as the replay windows, so the two cannot disagree about a row.
 */
export const buildPreparedRawTelemetry = (
  csv: string,
): PreparedRawTelemetryRow[] =>
  parseCsv(csv)
    .map(parsePreparedRecord)
    .sort((a, b) => a.window_id - b.window_id)
    .map((record) => ({
      timestamp: buildTimestamp(record.timestamp),
      telemetry_features: telemetryFeatures(record),
      telemetry_age_s: telemetryAge(record),
    }));

/**
 * What the LIVE path reads. `PREPARED_SESSION_WINDOWS` - which carries
 * P_distraction, P_telemetry_anomaly, visual_top_classes and the other
 * prepared-probability fields - is for the retained legacy replay only (guarded by
 * preparedRawTelemetry.test.ts).
 */
export const PREPARED_RAW_TELEMETRY: PreparedRawTelemetryRow[] =
  buildPreparedRawTelemetry(telemetryCsv);

/** One prepared row per 2000 ms of effective monitoring time (the CSV's own cadence). */
export const PREPARED_TELEMETRY_PERIOD_MS = 2000;

/**
 * The Live telemetry cursor (R10). It yields one prepared raw row per 2000 ms of
 * EFFECTIVE monitoring time and gives every row a sequence number (`seq`, uncapped; the
 * row is `seq % rows.length`, so the replay wraps) and an acquisition time.
 *
 * Segments. A segment is one stretch of uninterrupted monitoring. `reset` opens the
 * first one of a session (seq 0, base time = now). `pause` freezes the cursor at the
 * sequence it had reached. `resume` opens a NEW segment at once: its first sample is
 * the sequence one past the frozen one and its time is the moment of resuming, so every
 * resume has its own base time and start sequence; the pause itself consumes no
 * sequence number.
 *
 * Acquisition time. `baseMs + (seq - startSeq) * 2000`: arithmetic, never the clock of
 * a tick, so the same sequence number carries byte-identical time in every request.
 * This is the replay's LOGICAL event time. It is not when a real sensor measured
 * anything - the prepared telemetry has no such moment - and the server uses it only
 * as the sample's canonical time for age and for the alert timer's source span.
 *
 * The rows come from `PREPARED_RAW_TELEMETRY` (never from the replay windows), and a
 * clock that steps backwards never moves the sequence back.
 */
export const createPreparedTelemetryCursor = (
  rows: readonly PreparedRawTelemetryRow[] = PREPARED_RAW_TELEMETRY,
): TelemetrySource => {
  let started = false;
  let running = false;
  let baseMs = 0;
  let startSeq = 0;
  let step = 0;

  const advance = (nowMs: number) => {
    step = Math.max(
      step,
      Math.floor((nowMs - baseMs) / PREPARED_TELEMETRY_PERIOD_MS),
    );
  };
  const begin = (nowMs: number, firstSeq: number) => {
    started = true;
    running = true;
    baseMs = nowMs;
    startSeq = firstSeq;
    step = 0;
  };

  return {
    reset: (nowMs) => begin(nowMs, 0),
    pause: (nowMs) => {
      if (!running) return;
      advance(nowMs);
      running = false;
    },
    resume: (nowMs) => {
      if (running) return;
      begin(nowMs, started ? startSeq + step + 1 : 0);
    },
    read: (nowMs) => {
      if (running) advance(nowMs);
      const seq = startSeq + step;
      return {
        features: rows[seq % rows.length].telemetry_features,
        seq,
        acquiredAtMs: baseMs + step * PREPARED_TELEMETRY_PERIOD_MS,
      };
    },
  };
};
