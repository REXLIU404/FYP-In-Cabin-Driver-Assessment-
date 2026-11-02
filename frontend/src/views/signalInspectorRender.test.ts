import { createElement } from "react";
import { describe, expect, it } from "vitest";

import { makeRecord } from "../testing/records";
import { markup, valuesAfter } from "../testing/markup";
import type { RiskUpdate } from "../types";
import { SignalInspector } from "./SignalInspector";

// Static render (react-dom/server, node environment): a window whose provenance
// carries the dataset replay block (plan Task 7) shows its ground-truth labels;
// a record without the block shows no such section. The expected strings are
// literals.

const withReplay = (): RiskUpdate => {
  const record = makeRecord("fresh", "fresh", 1);
  return {
    ...record,
    provenance: {
      ...record.provenance,
      replay: {
        scenario_id: "viva_v1",
        segment_index: 2,
        frame_file: "f0042_p050_c0.jpg",
        vision_label: "texting_right",
        telemetry_label: "Safe",
        telemetry_row: 12,
      },
    },
  };
};

const render = (record: RiskUpdate) =>
  markup(
    createElement(SignalInspector, {
      history: [record],
      selectedRecord: record,
      thresholdLow: 30,
      onSelectWindow() {},
      onToggleFlag() {},
    }),
  );

describe("SignalInspector (static render): the dataset replay truth block", () => {
  it("a window with provenance.replay shows the truth group: vision, telemetry, frame and segment", () => {
    const html = render(withReplay());
    expect(valuesAfter(html, "Vision")).toEqual(["texting_right"]);
    expect(valuesAfter(html, "Telemetry")).toEqual(["Safe"]);
    expect(valuesAfter(html, "Frame")).toEqual(["f0042_p050_c0.jpg"]);
    // segment_index is 0-based in provenance; the UI shows it 1-based (spec 4.1).
    expect(valuesAfter(html, "Segment")).toEqual(["3"]);
  });

  it("a record without the block shows no truth section", () => {
    const html = render(makeRecord("fresh", "fresh", 1));
    expect(html).not.toContain("Dataset replay");
    expect(valuesAfter(html, "Frame")).toEqual([]);
  });
});
