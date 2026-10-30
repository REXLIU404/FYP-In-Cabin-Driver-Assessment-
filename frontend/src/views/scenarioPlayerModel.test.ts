import { describe, expect, it } from "vitest";

import type {
  PlaybackSnapshot,
  ScenarioManifest,
} from "../../../ai/src/scenarioTimeline";
import { makeRecord } from "../testing/records";
import { buildScenarioPlayerModel } from "./scenarioPlayerModel";

// The expected strings are literals; none is built from an implementation constant
// (repository convention, plan Global Constraints).

type Segment = ScenarioManifest["segments"][number];

const segment = (over: Partial<Segment>): Segment => ({
  index: 0,
  title: "Baseline",
  start_ms: 0,
  duration_ms: 20000,
  driver_id: "p050",
  vision_class: "c0",
  vision_label: "safe_driving",
  telemetry_label: "Safe",
  first_frame: 0,
  frame_count: 100,
  frame_cycles: 0,
  first_telemetry: 0,
  telemetry_count: 10,
  ...over,
});

// The viva_v1 shape: 7 segments, 136 s total, so the expected literals match the
// real scenario the demo plays.
const manifest: ScenarioManifest = {
  schema: "constructed-scenario/1",
  scenario_id: "viva_v1",
  scenario_sha256: "scenario-sha",
  generated_at: "2026-10-26T00:00:00Z",
  frame_period_ms: 200,
  telemetry_period_ms: 2000,
  duration_ms: 136000,
  sources: {
    split: "test",
    vision_metadata_sha256: "vision-sha",
    telemetry_csv_sha256: "telemetry-sha",
  },
  segments: [
    segment({ index: 0, title: "Baseline", start_ms: 0, duration_ms: 20000 }),
    segment({
      index: 1,
      title: "Vision only",
      start_ms: 20000,
      duration_ms: 16000,
      driver_id: "p026",
      vision_class: "c1",
      vision_label: "texting_right",
    }),
    segment({
      index: 2,
      title: "Both",
      start_ms: 36000,
      duration_ms: 16000,
      driver_id: "p035",
      vision_class: "c4",
      vision_label: "talking_phone_left",
      telemetry_label: "Distracted",
    }),
    segment({
      index: 3,
      title: "Recovery",
      start_ms: 52000,
      duration_ms: 26000,
      driver_id: "p026",
    }),
    segment({
      index: 4,
      title: "Telemetry only",
      start_ms: 78000,
      duration_ms: 16000,
      driver_id: "p012",
      telemetry_label: "Aggressive",
    }),
    segment({
      index: 5,
      title: "Both",
      start_ms: 94000,
      duration_ms: 16000,
      driver_id: "p035",
      vision_class: "c7",
      vision_label: "reaching_behind",
      telemetry_label: "Distracted",
    }),
    segment({
      index: 6,
      title: "Recovery",
      start_ms: 110000,
      duration_ms: 26000,
    }),
  ],
  frames: [],
  telemetry: [],
};

const snapshot = (over: Partial<PlaybackSnapshot> = {}): PlaybackSnapshot => ({
  positionMs: 34000,
  segmentIndex: 1,
  frameN: 170,
  finished: false,
  running: true,
  ...over,
});

describe("buildScenarioPlayerModel", () => {
  // User decision 2026-10-29: the badge names the mode only; no "not live" wording.
  it("the badge is the constant CONSTRUCTED SCENARIO label, without 'not live'", () => {
    const { badge } = buildScenarioPlayerModel(manifest, snapshot(), undefined);
    expect(badge).toBe("CONSTRUCTED SCENARIO");
    expect(badge).not.toMatch(/not live/i);
  });

  // A snapshot from another, longer scenario must never crash the page (review of ead8895).
  it("an out-of-range segment index is clamped to the last segment, not thrown", () => {
    const last = manifest.segments.length - 1;
    const model = buildScenarioPlayerModel(
      manifest,
      snapshot({ segmentIndex: last + 5 }),
      undefined,
    );
    expect(model.truth).toBe(manifest.segments[last].vision_label);
  });

  it("the caption names the current segment: its theme, vision label, driver and the split", () => {
    expect(
      buildScenarioPlayerModel(manifest, snapshot(), undefined).caption,
    ).toBe(
      "Segment 2/7 · Vision only · texting_right · driver p026 · State Farm test split",
    );
  });

  it("the truth is the segment's vision label; the model line is the top visual class at 2 dp", () => {
    const latest = makeRecord("fresh", "fresh", 1, {
      visual_top_classes: [
        { label: "texting_right", probability: 0.9712 },
        { label: "safe_driving", probability: 0.0288 },
      ],
    });
    const model = buildScenarioPlayerModel(manifest, snapshot(), latest);
    expect(model.truth).toBe("texting_right");
    expect(model.model).toBe("texting_right 0.97");
  });

  it("without a latest record the model line is null (nothing to compare against)", () => {
    expect(
      buildScenarioPlayerModel(manifest, snapshot(), undefined).model,
    ).toBeNull();
  });

  it("elapsed is m:ss over the scenario total, from the playback position", () => {
    expect(
      buildScenarioPlayerModel(
        manifest,
        snapshot({ positionMs: 34000 }),
        undefined,
      ).elapsed,
    ).toBe("0:34 / 2:16");
    expect(
      buildScenarioPlayerModel(manifest, snapshot({ positionMs: 0 }), undefined)
        .elapsed,
    ).toBe("0:00 / 2:16");
  });

  it("the segments list the 7 titles with done / current / todo around the current one", () => {
    expect(
      buildScenarioPlayerModel(manifest, snapshot(), undefined).segments,
    ).toEqual([
      { title: "Baseline", state: "done" },
      { title: "Vision only", state: "current" },
      { title: "Both", state: "todo" },
      { title: "Recovery", state: "todo" },
      { title: "Telemetry only", state: "todo" },
      { title: "Both", state: "todo" },
      { title: "Recovery", state: "todo" },
    ]);
  });

  it("finished follows the snapshot", () => {
    expect(
      buildScenarioPlayerModel(manifest, snapshot(), undefined).finished,
    ).toBe(false);
    expect(
      buildScenarioPlayerModel(
        manifest,
        snapshot({ finished: true }),
        undefined,
      ).finished,
    ).toBe(true);
  });
});
