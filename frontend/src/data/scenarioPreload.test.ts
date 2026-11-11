import { describe, expect, it, vi } from "vitest";

import type { ScenarioManifest } from "../../../ai/src/scenarioTimeline";
import { preloadFrames } from "./scenarioPreload";

/**
 * Task 6 (constructed scenario) - the frame preloader. All frames of a scenario are
 * fetched up front, turned into data URLs ordered by their manifest `n`, and handed
 * to the playback clock. One failed frame fails the whole scenario load, with the
 * file name in the error, so the player never starts with a hole in the middle.
 */
const manifest = (): ScenarioManifest => ({
  schema: "constructed-scenario/1",
  scenario_id: "tiny",
  scenario_sha256: "s".repeat(64),
  generated_at: "2025-01-01T00:00:00Z",
  frame_period_ms: 200,
  telemetry_period_ms: 2000,
  duration_ms: 600,
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
      duration_ms: 600,
      driver_id: "p050",
      vision_class: "c0",
      vision_label: "safe_driving",
      telemetry_label: "Safe",
      first_frame: 0,
      frame_count: 3,
      frame_cycles: 0,
      first_telemetry: 0,
      telemetry_count: 0,
    },
  ],
  frames: [
    {
      n: 0,
      file: "f0.jpg",
      source_file: "s0.jpg",
      driver_id: "p050",
      class_id: "c0",
      vision_label: "safe_driving",
      segment_index: 0,
      sha256: "x".repeat(64),
    },
    {
      n: 1,
      file: "f1.jpg",
      source_file: "s1.jpg",
      driver_id: "p050",
      class_id: "c0",
      vision_label: "safe_driving",
      segment_index: 0,
      sha256: "x".repeat(64),
    },
    {
      n: 2,
      file: "f2.jpg",
      source_file: "s2.jpg",
      driver_id: "p050",
      class_id: "c0",
      vision_label: "safe_driving",
      segment_index: 0,
      sha256: "x".repeat(64),
    },
  ],
  telemetry: [],
});

const blobOf = (name: string) => new Blob([`bytes-of-${name}`], { type: "image/jpeg" });
const dataUrlOf = (name: string) => `data:image/jpeg;base64,${btoa(`bytes-of-${name}`)}`;

describe("preloadFrames", () => {
  it("returns one data URL per manifest frame, ordered by the frame's n", async () => {
    const urls = await preloadFrames(
      manifest(),
      async (file) => blobOf(file),
      vi.fn(),
    );
    expect(urls).toEqual([dataUrlOf("f0.jpg"), dataUrlOf("f1.jpg"), dataUrlOf("f2.jpg")]);
  });

  it("reports progress once per loaded frame with the running total", async () => {
    const onProgress = vi.fn();
    await preloadFrames(manifest(), async (file) => blobOf(file), onProgress);
    expect(onProgress.mock.calls).toEqual([
      [1, 3],
      [2, 3],
      [3, 3],
    ]);
  });

  it("rejects when any frame fails, naming the file, and reports no further progress", async () => {
    const onProgress = vi.fn();
    const failing = vi.fn(async (file: string) => {
      if (file === "f1.jpg") throw new Error("network down");
      return blobOf(file);
    });
    await expect(preloadFrames(manifest(), failing, onProgress)).rejects.toThrow(
      /f1\.jpg/,
    );
    expect(onProgress.mock.calls).toEqual([[1, 3]]);
  });

  it("keeps its own Blob type when the fetch answer says so", async () => {
    const urls = await preloadFrames(
      manifest(),
      async (file) =>
        new Blob([`png-of-${file}`], { type: "image/png" }),
      vi.fn(),
    );
    expect(urls[0]).toBe(`data:image/png;base64,${btoa("png-of-f0.jpg")}`);
  });
});
