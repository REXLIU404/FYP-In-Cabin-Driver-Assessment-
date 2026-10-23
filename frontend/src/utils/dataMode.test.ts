import { describe, expect, it } from "vitest";

import appSource from "../App.tsx?raw";
import { DATA_MODE_NOTE, DATA_MODE_OPTIONS } from "./dataMode";

// Task 9 / K4: the replay is legacy and test-only, and the page says so where the
// choice is made. These pin the words the reader sees.
describe("Data mode: the prepared replay is labelled legacy / test-only", () => {
  const option = (value: string) =>
    DATA_MODE_OPTIONS.find((o) => o.value === value);

  it("offers exactly Live and the replay, Live first", () => {
    expect(DATA_MODE_OPTIONS.map((o) => o.value)).toEqual([
      "LIVE_MODEL_RUNTIME",
      "PREPARED_SESSION_RUNTIME",
    ]);
  });

  it("the options carry the exact labels the reader sees: legacy and test-only on the replay only", () => {
    expect(option("PREPARED_SESSION_RUNTIME")?.label).toBe(
      "Prepared replay (legacy, test-only)",
    );
    expect(option("LIVE_MODEL_RUNTIME")?.label).toBe("Live trained models");
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

  it("the Live note names the trained models", () => {
    expect(DATA_MODE_NOTE.LIVE_MODEL_RUNTIME).toMatch(/MobileNetV3/);
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
