import { describe, expect, it } from "vitest";

import appSource from "../App.tsx?raw";
import { DATA_MODE_NOTE, DATA_MODE_OPTIONS } from "./dataMode";

// Task 9 / K4 + Task 7: the replay is legacy and test-only, and the page says so where
// the choice is made; the constructed scenario (plan Task 7) REPLACES the replay in the
// selector. These pin the words the reader sees.
describe("Data mode: the choices and their labels", () => {
  const option = (value: string) =>
    DATA_MODE_OPTIONS.find((o) => o.value === value);

  it("offers exactly Live and the constructed scenario, Live first", () => {
    expect(DATA_MODE_OPTIONS.map((o) => o.value)).toEqual([
      "LIVE_MODEL_RUNTIME",
      "CONSTRUCTED_SCENARIO_RUNTIME",
    ]);
  });

  it("the options carry the exact labels the reader sees; the legacy replay is no longer listed", () => {
    expect(option("LIVE_MODEL_RUNTIME")?.label).toBe(
      "Live camera (trained models)",
    );
    expect(option("CONSTRUCTED_SCENARIO_RUNTIME")?.label).toBe(
      "Constructed demo scenario",
    );
    expect(option("PREPARED_SESSION_RUNTIME")).toBeUndefined();
  });

  it("the constructed scenario shows no mode note (the player banner says 'not live')", () => {
    expect(DATA_MODE_NOTE.CONSTRUCTED_SCENARIO_RUNTIME).toBe("");
  });

  it("the replay note says it is not the Live system, and that a reload goes back to Live", () => {
    const note = DATA_MODE_NOTE.PREPARED_SESSION_RUNTIME;
    expect(note).toMatch(/legacy/i);
    expect(note).toMatch(/test-only/i);
    expect(note).toMatch(/not the Live system/i);
    expect(note).toMatch(/starts on Live again/i);
    // The old wording presented it as a peer "demo mode".
    expect(note).not.toMatch(/^Demo mode/);
  });

  it("the replay note states its fixed 3 s tolerance (K9): the freshness setting is Live-only", () => {
    expect(DATA_MODE_NOTE.PREPARED_SESSION_RUNTIME).toMatch(
      /fixed 3 s.*freshness setting applies to Live sessions only/,
    );
  });

  it("the Live note names the trained models without hard-coding the vision architecture", () => {
    // Task 10A: the active vision model is chosen at backend start (stable or a candidate); the page
    // names it from /api/models (describeVisionModel), so this static note must not.
    expect(DATA_MODE_NOTE.LIVE_MODEL_RUNTIME).toMatch(/trained vision model/);
    expect(DATA_MODE_NOTE.LIVE_MODEL_RUNTIME).not.toMatch(/MobileNet|ResNet/i);
    expect(DATA_MODE_NOTE.LIVE_MODEL_RUNTIME).toMatch(/XGBoost/);
  });
});

// Source guard, not a behaviour test: the page must render the labels above and not a
// private copy of the old wording.
describe("Data mode: App renders these labels and notes (source guard)", () => {
  it("the select is built from DATA_MODE_OPTIONS and the note from DATA_MODE_NOTE", () => {
    expect(appSource).toMatch(/DATA_MODE_OPTIONS\.map\(/);
    expect(appSource).toMatch(/DATA_MODE_NOTE\[config\.operationMode\]/);
  });

  it("the old 'demo' wording is not hard-coded in App any more", () => {
    expect(appSource).not.toMatch(/Prepared replay demo/);
    expect(appSource).not.toMatch(/Demo mode:/);
  });
});
