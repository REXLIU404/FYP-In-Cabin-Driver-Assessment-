/**
 * The constructed scenario playback clock (plan Task 5).
 *
 * One playback = one manifest, one shared position. The position moves ONLY while the
 * playback is running, by the wall clock, and clamps at ``duration_ms - 1`` - the
 * scenario finishes there and keeps returning its last frame. The position decides
 * everything: the frame (``n = floor(pos / frame_period_ms)``), the telemetry row
 * (``k = floor(pos / telemetry_period_ms)``, taken BY POSITION, never by sequence
 * number) and the segment, so a frame and its telemetry at the same moment always land
 * in the same segment.
 *
 * The returned ``telemetry`` is a ``TelemetrySource`` for the live loop: the loop
 * resets it on a new session, pauses and resumes it with monitoring, and reads it once
 * per tick. ``captureFrame()`` uses the injected ``now()`` and yields ``LiveFrame``
 * entries whose acquisition time is the playback's own clock (``captured_at_source:
 * "replay_clock"``), never ahead of ``now`` and never behind by more than one period
 * after a long pause. Both carry the ground-truth ``replay`` block (scenario, segment,
 * the frame file / telemetry row and its label) for provenance - never for fusion.
 */
import type { LiveFrame, TelemetryReading, TelemetrySource } from "./liveLoop";
import type { TelemetryBehaviorLabel, TelemetryFeatures } from "./types";

export interface ScenarioSegment {
  index: number;
  title: string;
  start_ms: number;
  duration_ms: number;
  driver_id: string;
  vision_class: string;
  vision_label: string;
  telemetry_label: TelemetryBehaviorLabel;
  first_frame: number;
  frame_count: number;
  frame_cycles: number;
  first_telemetry: number;
  telemetry_count: number;
}

export interface ScenarioFrame {
  n: number;
  file: string;
  source_file: string;
  driver_id: string;
  class_id: string;
  vision_label: string;
  segment_index: number;
  sha256: string;
}

export interface ScenarioTelemetryRow {
  n: number;
  /** The row's index in the source telemetry CSV (ground truth, goes into provenance). */
  row: number;
  label: TelemetryBehaviorLabel;
  segment_index: number;
  features: TelemetryFeatures;
}

export interface ScenarioManifest {
  schema: "constructed-scenario/1";
  scenario_id: string;
  scenario_sha256: string;
  generated_at: string;
  frame_period_ms: number;
  telemetry_period_ms: number;
  duration_ms: number;
  sources: {
    split: "test";
    vision_metadata_sha256: string;
    telemetry_csv_sha256: string;
  };
  segments: ScenarioSegment[];
  frames: ScenarioFrame[];
  telemetry: ScenarioTelemetryRow[];
}

export interface PlaybackSnapshot {
  positionMs: number;
  segmentIndex: number;
  frameN: number;
  finished: boolean;
  running: boolean;
}

export function createScenarioPlayback(
  manifest: ScenarioManifest,
  frameImage: (n: number) => string | null,
  now: () => number,
): {
  telemetry: TelemetrySource;
  captureFrame(): LiveFrame | null;
  snapshot(): PlaybackSnapshot;
} {
  const framePeriod = manifest.frame_period_ms;
  const telemetryPeriod = manifest.telemetry_period_ms;
  const end = manifest.duration_ms - 1;

  let pos = 0;
  let base = 0;
  let posAtBase = 0;
  let epoch = 0;
  let seq = 0;
  let running = false;
  let lastK = 0;

  const positionAt = (t: number) =>
    Math.min(end, posAtBase + Math.max(0, t - base));

  /** The position follows the wall clock only while running; the telemetry row k
   * crossing one period up opens a new observation (seq + 1). */
  const advance = (t: number) => {
    if (!running) return;
    pos = positionAt(t);
    const k = Math.floor(pos / telemetryPeriod);
    if (k > lastK) {
      seq += 1;
      lastK = k;
    }
  };

  const segmentIndexAt = (p: number) => {
    let index = 0;
    for (const segment of manifest.segments)
      if (segment.start_ms <= p) index = segment.index;
    return index;
  };

  const frameN = () => Math.floor(pos / framePeriod);
  const teleK = () => Math.floor(pos / telemetryPeriod);

  const telemetry: TelemetrySource = {
    reset(t) {
      pos = 0;
      base = t;
      posAtBase = 0;
      epoch = t;
      seq = 0;
      lastK = 0;
      running = true;
    },
    pause(t) {
      advance(t); // the position runs up to the pause moment, then freezes (idempotent)
      running = false;
    },
    resume(t) {
      if (running) return; // a no-op while running
      base = t;
      posAtBase = pos;
      seq += 1; // a NEW observation begins at once
      running = true;
    },
    read(t) {
      advance(t);
      const k = teleK();
      const row = manifest.telemetry[k];
      const features = row ? row.features : null;
      return {
        features,
        seq,
        acquiredAtMs: base + Math.max(0, k * telemetryPeriod - posAtBase),
        ...(row
          ? {
              replay: {
                scenario_id: manifest.scenario_id,
                segment_index: segmentIndexAt(pos),
                telemetry_row: row.row,
                telemetry_label: row.label,
              },
            }
          : {}),
      } satisfies TelemetryReading;
    },
  };

  const captureFrame = (): LiveFrame | null => {
    advance(now());
    const n = frameN();
    const image = frameImage(n);
    if (image === null) return null;
    const frame = manifest.frames[n];
    return {
      image_base64: image,
      captured_at: new Date(
        base + Math.max(0, n * framePeriod - posAtBase),
      ).toISOString(),
      captured_at_source: "replay_clock",
      vision_frame: { epoch, index: n },
      replay: {
        scenario_id: manifest.scenario_id,
        segment_index: segmentIndexAt(pos),
        frame_file: frame.file,
        vision_label: frame.vision_label,
      },
    };
  };

  const snapshot = (): PlaybackSnapshot => ({
    positionMs: pos,
    segmentIndex: segmentIndexAt(pos),
    frameN: frameN(),
    finished: pos >= end,
    running,
  });

  return { telemetry, captureFrame, snapshot };
}
