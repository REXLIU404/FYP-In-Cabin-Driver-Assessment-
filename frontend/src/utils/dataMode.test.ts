import { describe, expect, it } from "vitest";

import type { SessionMeta } from "../types";

import appSource from "../App.tsx?raw";
import liveSessionSource from "../hooks/useLiveSession.ts?raw";
import {
  DATA_MODE_NOTE,
  DATA_MODE_OPTIONS,
  emptyResultsHint,
  firstResultHint,
  isSavedLiveSession,
  offersSavedLiveSessions,
} from "./dataMode";

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

  it("the constructed scenario shows no mode note (the CONSTRUCTED SCENARIO badges name it)", () => {
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

  // User decision 2026-10-30: the Live note carries no accuracy disclaimer.
  it("the Live note is exactly the pipeline sentence, without the 'experimental' remark", () => {
    expect(DATA_MODE_NOTE.LIVE_MODEL_RUNTIME).toBe(
      "Vision: camera → trained vision model (named on the line below) · Telemetry: prepared raw features → trained XGBoost.",
    );
  });
});

// The saved-session picker belongs to Live: the constructed scenario is a demo aid, so its
// controls offer no saved sessions, and its runs are not listed as Live sessions either
// (one loaded under Live would open without the CONSTRUCTED SCENARIO marker).
describe("Data mode: saved sessions are Live-only", () => {
  it("only Live offers the saved-session picker", () => {
    expect(offersSavedLiveSessions("LIVE_MODEL_RUNTIME")).toBe(true);
    expect(offersSavedLiveSessions("CONSTRUCTED_SCENARIO_RUNTIME")).toBe(false);
    expect(offersSavedLiveSessions("PREPARED_SESSION_RUNTIME")).toBe(false);
  });

  it("the saved list keeps Live sessions and drops scenario, replay and unlabelled ones", () => {
    const meta = (operation_mode?: SessionMeta["operation_mode"]) => ({
      id: "s",
      created_at: "2026-10-29T00:00:00Z",
      total_windows: 1,
      operation_mode,
    });
    expect(isSavedLiveSession(meta("LIVE_MODEL_RUNTIME"))).toBe(true);
    expect(isSavedLiveSession(meta("CONSTRUCTED_SCENARIO_RUNTIME"))).toBe(
      false,
    );
    expect(isSavedLiveSession(meta("PREPARED_SESSION_RUNTIME"))).toBe(false);
    expect(isSavedLiveSession(meta(undefined))).toBe(false);
  });

  // The empty views must not point at a picker the mode does not show (review of afd8724).
  it("the empty-results hint mentions saved sessions only where the picker exists", () => {
    expect(emptyResultsHint("LIVE_MODEL_RUNTIME")).toBe(
      "Start monitoring or load a saved session to inspect its evidence.",
    );
    expect(emptyResultsHint("CONSTRUCTED_SCENARIO_RUNTIME")).toBe(
      "Start the scenario to inspect its evidence.",
    );
    expect(emptyResultsHint("PREPARED_SESSION_RUNTIME")).toBe(
      "Start monitoring to inspect its evidence.",
    );
  });

  it("the waiting text mentions the camera only in Live", () => {
    expect(firstResultHint("LIVE_MODEL_RUNTIME")).toBe(
      "Start monitoring to create a session. Camera permissions and model readiness are checked before results appear.",
    );
    expect(firstResultHint("CONSTRUCTED_SCENARIO_RUNTIME")).toBe(
      "Start monitoring to play the scenario. Model readiness is checked before results appear.",
    );
    expect(firstResultHint("CONSTRUCTED_SCENARIO_RUNTIME")).not.toMatch(
      /camera/i,
    );
  });

  it("App renders the waiting text for the current mode", () => {
    expect(appSource).toMatch(/\{firstResultHint\(config\.operationMode\)\}/);
    expect(appSource).not.toMatch(/Camera permissions and model readiness/);
  });

  // Source guards: the page uses these rules, not a private copy. The hook's list filter
  // is pinned with its other wiring requirements (hooks/useLiveSession.test.ts, MODE_FILTER).
  it("App shows the picker and its refresh button under offersSavedLiveSessions", () => {
    expect(appSource).toMatch(
      /offersSavedLiveSessions\(config\.operationMode\) && \(\s*<>\s*<button[\s\S]*?Refresh saved sessions[\s\S]*?aria-label="Saved live sessions"/,
    );
  });

  it("App renders the empty-results hint for the current mode", () => {
    expect(appSource).toMatch(/\{emptyResultsHint\(config\.operationMode\)\}/);
    expect(appSource).not.toMatch(/load a saved session to inspect/);
  });

  // Changing the Data mode leaves the session: the next mode must not show the previous
  // mode's windows under its own label, nor a saved-session error raised in Live (the
  // scenario mode has no control to retry or clear it).
  it("changing the Data mode clears the session and its error before the config changes", () => {
    expect(appSource).toMatch(
      /aria-label="Data mode"[\s\S]*?onChange=\{\(event\) => \{\s*live\.clearSession\(\);[^}]*?updateConfig\(/,
    );
  });

  it("the hook's clearSession clears the error and the loop's session", () => {
    expect(liveSessionSource).toMatch(
      /const clearSession = useCallback\(\(\) => \{\s*setError\(null\);\s*loop\.clear\(\);\s*\}, \[loop\]\);/,
    );
  });
});

// Source guard, not a behaviour test: the page must render the labels above and not a
// private copy of the old wording.
// Review of e26e32a: the other ways one mode's session or source could show under the
// other mode's label. Source guards on App (the behaviour is in the browser tests).
describe("Data mode: no path mixes the two modes (source guard)", () => {
  it("the Data mode select is locked while the camera permission prompt is open", () => {
    expect(appSource).toMatch(
      /aria-label="Data mode"\s*value=\{config\.operationMode\}\s*disabled=\{\s*monitoring \|\| live\.busy \|\| camera\.status === "requesting"\s*\}/,
    );
  });

  it("leaving Live stops the camera", () => {
    expect(appSource).toMatch(
      /aria-label="Data mode"[\s\S]*?onChange=\{\(event\) => \{\s*live\.clearSession\(\);\s*if \(event\.target\.value !== "LIVE_MODEL_RUNTIME"\)\s*camera\.stop\(\);/,
    );
  });

  it("choosing another scenario leaves the session too", () => {
    expect(appSource).toMatch(
      /aria-label="Scenario"[\s\S]*?onChange=\{\(event\) => \{\s*if \(!event\.target\.value\) return;(?:\s*\/\/[^\n]*)*\s*live\.clearSession\(\);\s*void scenario\.select\(event\.target\.value\);/,
    );
  });

  it("Start after a finished scenario plays it again in a new session", () => {
    expect(appSource).toMatch(
      /const fresh = restart \|\| \(isScenario && scenarioFinished === true\);/,
    );
    expect(appSource).toMatch(/await live\.start\(fresh\);/);
  });

  it("the scenario mode never shows the camera preview, even before a scenario is loaded", () => {
    expect(appSource).toMatch(
      /\) : isScenario \? \(\s*<div className="camera-placeholder scenario-placeholder">\s*<strong>Choose a scenario to load its frames\.<\/strong>\s*<\/div>\s*\) : \(\s*<CameraPreview/,
    );
  });
});

// Review of ead8895 / 37e7229: the remaining ways a session could start or resume in
// the wrong mode or on a finished scenario.
describe("Data mode: no session starts in the wrong mode (source guard)", () => {
  it("New Session waits for a loaded scenario, like Start", () => {
    expect(appSource).toMatch(
      /onClick=\{\(\) => void start\(true\)\}\s*disabled=\{[^}]*\(isScenario && scenario\.status !== "ready"\)/,
    );
  });

  it("a mode change while the camera prompt was open starts nothing", () => {
    expect(appSource).toMatch(/const startedIn = config\.operationMode;/);
    expect(appSource).toMatch(
      /await camera\.start\(\);[^}]*if \(modeRef\.current !== startedIn\) return;/,
    );
  });

  // Retry keeps its meaning (resend the frozen request: runtimeNotices.test.ts); a resume
  // of a finished run is paused by the effect, which reads the playback, not the display.
  it("a finished playback pauses any resumed run, read from the playback itself", () => {
    expect(appSource).toMatch(
      /if \(isScenario && liveRunning && loadedPlayback\?\.snapshot\(\)\.finished\)\s*pauseLive\(\);/,
    );
    expect(appSource).toMatch(/onRetry=\{retryHandler\(live\)\}/);
  });

  it("the player uses a snapshot only from the playback now loaded", () => {
    expect(appSource).toMatch(/snapshotSource === scenario\.playback/);
  });
});

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
