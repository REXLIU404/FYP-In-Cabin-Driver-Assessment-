import { beforeEach, describe, expect, it } from "vitest";

import { isLiveLike } from "./operationMode";
import {
  createScenarioPlayback,
  type ScenarioManifest,
} from "./scenarioTimeline";

/**
 * Task 5 (constructed scenario) - the playback clock behind the replay. Two segments of
 * 4 s each (frame period 200 ms, telemetry period 2 s), a clock the tests step by hand.
 */
const T0 = 1_700_000_000_000;

const FEATURES = {
  speed_kmph: 34,
  accel_x: 0.3,
  accel_y: 0.1,
  brake_pressure: 12,
  steering_angle: -2,
  throttle: 30,
  lane_deviation: 0.3,
  headway_distance: 26,
};

function tinyManifest(): ScenarioManifest {
  return {
    schema: "constructed-scenario/1",
    scenario_id: "tiny",
    scenario_sha256: "s".repeat(64),
    generated_at: "2025-01-01T00:00:00Z",
    frame_period_ms: 200,
    telemetry_period_ms: 2000,
    duration_ms: 8000,
    sources: {
      split: "test",
      vision_metadata_sha256: "v".repeat(64),
      telemetry_csv_sha256: "t".repeat(64),
    },
    segments: [
      {
        index: 0,
        title: "Baseline",
        start_ms: 0,
        duration_ms: 4000,
        driver_id: "p050",
        vision_class: "c0",
        vision_label: "safe_driving",
        telemetry_label: "Safe",
        first_frame: 0,
        frame_count: 20,
        frame_cycles: 0,
        first_telemetry: 0,
        telemetry_count: 2,
      },
      {
        index: 1,
        title: "Vision only",
        start_ms: 4000,
        duration_ms: 4000,
        driver_id: "p026",
        vision_class: "c1",
        vision_label: "texting_right",
        telemetry_label: "Safe",
        first_frame: 20,
        frame_count: 20,
        frame_cycles: 0,
        first_telemetry: 2,
        telemetry_count: 2,
      },
    ],
    frames: Array.from({ length: 40 }, (_, n) => ({
      n,
      file: `f${n}.jpg`,
      source_file: `s${n}.jpg`,
      driver_id: n < 20 ? "p050" : "p026",
      class_id: n < 20 ? "c0" : "c1",
      vision_label: n < 20 ? "safe_driving" : "texting_right",
      segment_index: n < 20 ? 0 : 1,
      sha256: "x".repeat(64),
    })),
    telemetry: Array.from({ length: 4 }, (_, k) => ({
      n: k,
      row: k,
      label: "Safe" as const,
      segment_index: k < 2 ? 0 : 1,
      features: FEATURES,
    })),
  };
}

let clock = T0;
const playback = (image: (n: number) => string | null = (n) => `img-${n}`) =>
  createScenarioPlayback(tinyManifest(), image, () => clock);

beforeEach(() => {
  clock = T0;
});

describe("isLiveLike", () => {
  it("covers exactly the live-like modes", () => {
    expect(isLiveLike("LIVE_MODEL_RUNTIME")).toBe(true);
    expect(isLiveLike("CONSTRUCTED_SCENARIO_RUNTIME")).toBe(true);
    expect(isLiveLike("PREPARED_SESSION_RUNTIME")).toBe(false);
  });
});

describe("the position drives segments, frames and telemetry", () => {
  it("segments, frames and telemetry rows follow the position", () => {
    const p = playback();
    p.telemetry.reset(T0);
    const cases = [
      [0, 0, 0, 0],
      [199, 0, 0, 0],
      [200, 0, 1, 0],
      [3999, 0, 19, 1],
      [4000, 1, 20, 2],
    ] as const;
    for (const [t, seg, frameN, teleK] of cases) {
      clock = T0 + t;
      const reading = p.telemetry.read(T0 + t);
      expect(reading.features).not.toBeNull();
      expect(reading.replay).toMatchObject({
        segment_index: seg,
        telemetry_row: teleK,
      });
      const snap = p.snapshot();
      expect(snap.positionMs).toBe(t);
      expect(snap.segmentIndex).toBe(seg);
      expect(snap.frameN).toBe(frameN);
    }
  });

  it("segment boundaries coincide for frames and telemetry", () => {
    const p = playback();
    p.telemetry.reset(T0);
    for (const [t, seg] of [
      [3999, 0],
      [4000, 1],
    ] as const) {
      clock = T0 + t;
      const frame = p.captureFrame();
      const reading = p.telemetry.read(T0 + t);
      expect(frame?.replay?.segment_index).toBe(seg);
      expect(reading.replay?.segment_index).toBe(seg);
    }
  });
});

describe("pause, resume and the wall clock", () => {
  it("a paused playback does not move", () => {
    const p = playback();
    p.telemetry.reset(T0);
    clock = T0 + 1000;
    p.telemetry.read(T0 + 1000);
    clock = T0 + 2000;
    p.telemetry.pause(T0 + 2000);
    clock = T0 + 5000;
    p.telemetry.read(T0 + 5000);
    const snap = p.snapshot();
    expect(snap.positionMs).toBe(2000);
    expect(snap.frameN).toBe(10);
    expect(snap.running).toBe(false);
  });

  it("ages stay below one period after a long pause", () => {
    const p = playback();
    p.telemetry.reset(T0);
    clock = T0 + 1000;
    p.telemetry.read(T0 + 1000);
    clock = T0 + 11_000;
    p.telemetry.pause(T0 + 11_000); // the position clamps at duration_ms - 1
    clock = T0 + 21_000;
    p.telemetry.resume(T0 + 21_000);
    const frame = p.captureFrame();
    const reading = p.telemetry.read(T0 + 21_000);
    const frameAge = T0 + 21_000 - Date.parse(frame!.captured_at);
    expect(frameAge).toBeGreaterThanOrEqual(0);
    expect(frameAge).toBeLessThan(200);
    const teleAge = T0 + 21_000 - reading.acquiredAtMs;
    expect(teleAge).toBeGreaterThanOrEqual(0);
    expect(teleAge).toBeLessThan(2000);
  });

  it("resume while running is a no-op", () => {
    const p = playback();
    p.telemetry.reset(T0);
    clock = T0 + 1000;
    const before = p.telemetry.read(T0 + 1000);
    clock = T0 + 1500;
    p.telemetry.resume(T0 + 1500);
    clock = T0 + 1500;
    const after = p.telemetry.read(T0 + 1500);
    expect(after.seq).toBe(before.seq);
  });

  it("resume opens a new telemetry observation (seq + 1) on the row of the current position", () => {
    const p = playback();
    p.telemetry.reset(T0);
    clock = T0 + 1000;
    const before = p.telemetry.read(T0 + 1000);
    clock = T0 + 1500;
    p.telemetry.pause(T0 + 1500);
    clock = T0 + 11_500;
    p.telemetry.resume(T0 + 11_500);
    const reading = p.telemetry.read(T0 + 11_500);
    expect(reading.seq).toBe(before.seq + 1);
    expect(reading.replay?.telemetry_row).toBe(0); // the row of the current position
  });
});

describe("frame identity, acquisition times and the finish", () => {
  it("frame identity only grows and the epoch advances on reset and on resume", () => {
    const p = playback();
    p.telemetry.reset(T0);
    let last = -1;
    for (const t of [0, 400, 1200, 3999, 4000, 7999]) {
      clock = T0 + t;
      const frame = p.captureFrame()!;
      expect(frame.vision_frame!.index).toBeGreaterThanOrEqual(last);
      last = frame.vision_frame!.index;
      expect(frame.vision_frame!.epoch).toBe(T0);
      expect(frame.captured_at_source).toBe("replay_clock");
    }
    // A pause freezes the position, so a resume re-opens the capture ON THE SAME
    // frame: its identity must be new - a bigger epoch - or the server's R10
    // protocol would refuse the re-sent (epoch, index) with its new acquisition
    // time as an observation conflict.
    clock = T0 + 8000;
    p.telemetry.pause(T0 + 8000);
    clock = T0 + 9000;
    p.telemetry.resume(T0 + 9000);
    const resumed = p.captureFrame()!;
    expect(resumed.vision_frame!.epoch).toBe(T0 + 9000);
    expect(resumed.vision_frame!.index).toBe(last);
    p.telemetry.reset(T0 + 100);
    clock = T0 + 100;
    const fresh = p.captureFrame()!;
    expect(fresh.vision_frame!.epoch).toBe(T0 + 100);
    expect(fresh.vision_frame!.index).toBe(0);
  });

  it("acquisition times never run ahead of now", () => {
    const p = playback();
    let state = 12345;
    const rnd = () => {
      state = (state * 1103515245 + 12345) % 2 ** 31;
      return state / 2 ** 31;
    };
    p.telemetry.reset(T0);
    let t = T0;
    for (let i = 0; i < 200; i++) {
      t += Math.floor(rnd() * 700);
      clock = t;
      const roll = rnd();
      if (roll < 0.2) p.telemetry.pause(t);
      else if (roll < 0.35) p.telemetry.resume(t);
      else if (roll < 0.6) {
        const frame = p.captureFrame();
        if (frame) expect(Date.parse(frame.captured_at)).toBeLessThanOrEqual(t);
      }
      const reading = p.telemetry.read(t);
      expect(reading.acquiredAtMs).toBeLessThanOrEqual(t);
    }
  });

  it("the scenario finishes at its duration and then keeps returning the last frame", () => {
    const p = playback();
    p.telemetry.reset(T0);
    clock = T0 + 7999;
    p.telemetry.read(T0 + 7999);
    expect(p.snapshot().finished).toBe(true);
    expect(p.captureFrame()!.vision_frame!.index).toBe(39);
    clock = T0 + 10_000_000; // well past the end: clamped, still the last frame
    expect(p.captureFrame()!.vision_frame!.index).toBe(39);
    expect(p.snapshot().positionMs).toBe(7999);
  });

  it("a missing image yields no frame", () => {
    const p = playback((n) => (n === 5 ? null : `img-${n}`));
    p.telemetry.reset(T0);
    clock = T0 + 1000; // n = 5
    expect(p.captureFrame()).toBeNull();
  });
});
