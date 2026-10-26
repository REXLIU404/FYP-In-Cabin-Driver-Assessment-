import { createElement } from "react";
import { describe, expect, it } from "vitest";

import type { useCameraPreview } from "../hooks/useCameraPreview";
import { makeRecord } from "../testing/records";
import { markup } from "../testing/markup";
import type { OperationMode, RiskUpdate } from "../types";
import type { ScenarioPlayerModel } from "./scenarioPlayerModel";
import { LiveMonitor } from "./LiveMonitor";

// Static render (react-dom/server, node environment): in the constructed scenario
// mode the Live Monitor swaps the camera preview for the scenario player and
// renames the Vehicle Signals panel; in Live it stays exactly as it was. The
// expected strings are literals.

const camera = {
  videoRef: null,
  status: "idle",
  start() {},
  stop() {},
} as unknown as ReturnType<typeof useCameraPreview>;

const playerModel: ScenarioPlayerModel = {
  badge: "CONSTRUCTED SCENARIO · not live",
  caption:
    "Segment 1/7 · Baseline · safe_driving · driver p050 · State Farm test split",
  truth: "safe_driving",
  model: "safe_driving 0.91",
  segments: [
    { title: "Baseline", state: "current" },
    { title: "Vision only", state: "todo" },
    { title: "Both", state: "todo" },
    { title: "Recovery", state: "todo" },
    { title: "Telemetry only", state: "todo" },
    { title: "Both", state: "todo" },
    { title: "Recovery", state: "todo" },
  ],
  elapsed: "0:00 / 2:16",
  finished: false,
};

// The record's own provenance carries the dataset replay block with the
// ground-truth telemetry label (Task 2): the panel must read THAT, not a constant.
const scenarioRecord = (): RiskUpdate => {
  const record = makeRecord("fresh", "fresh", 1);
  return {
    ...record,
    provenance: {
      ...record.provenance,
      replay: {
        scenario_id: "viva_v1",
        segment_index: 0,
        telemetry_label: "Safe",
        telemetry_row: 3,
      },
    },
  };
};

const render = (mode: OperationMode, latest: RiskUpdate) =>
  markup(
    createElement(LiveMonitor, {
      latest,
      history: [latest],
      sessionId: "s",
      recordCount: 1,
      isMonitoring: true,
      camera,
      thresholdLow: 30,
      thresholdHigh: 60,
      mode,
      scenario:
        mode === "CONSTRUCTED_SCENARIO_RUNTIME"
          ? {
              model: playerModel,
              frameSrc: "data:image/jpeg;base64,AAAA",
              finishedText: null,
            }
          : undefined,
    }),
  );

describe("LiveMonitor (static render)", () => {
  it("Live mode keeps the camera preview with a <video> (unchanged)", () => {
    const html = render("LIVE_MODEL_RUNTIME", makeRecord("fresh", "fresh", 1));
    expect(html).toContain("<video");
    expect(html).toContain("Prepared telemetry replay");
    expect(html).not.toContain("CONSTRUCTED SCENARIO · not live");
  });

  it("the constructed scenario renders the player instead of the camera: no <video>, badge present", () => {
    const html = render("CONSTRUCTED_SCENARIO_RUNTIME", scenarioRecord());
    expect(html).not.toContain("<video");
    expect(html).toContain("CONSTRUCTED SCENARIO · not live");
    expect(html).not.toContain("Start Camera");
    expect(html).not.toContain("Stop Camera");
  });

  it("the constructed scenario renames Vehicle Signals to Scenario telemetry and shows the truth label", () => {
    const html = render("CONSTRUCTED_SCENARIO_RUNTIME", scenarioRecord());
    expect(html).toContain("Scenario telemetry");
    expect(html).toContain("Truth: Safe");
  });
});
