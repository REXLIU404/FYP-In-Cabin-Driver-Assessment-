import { describe, expect, it } from "vitest";

import { assertAvailabilityInvariant } from "../../../ai/src/availability";
import { initAlertState } from "../../../ai/src/alertFsm";
import { buildRiskUpdate, DEFAULT_CONFIG } from "../../../ai/src/riskLogic";
import { PREPARED_SESSION_WINDOWS } from "../data/preparedSessionInput";
import { makeRecord } from "../testing/records";
import type { RiskUpdate } from "../types";
import appSource from "../App.tsx?raw";
import { applyAlertState } from "./alertOverlay";

// Hard-coded on purpose (see global constraints): 2000 ms to HIGH_ALERT.
const HIGH = { P_distraction: 0.95, P_telemetry_anomaly: 0.95 } as const;

describe("applyAlertState: the FSM overlay must not overwrite a null AlertSeverity", () => {
  it("an unavailable record keeps AlertSeverity null even when the FSM holds a severity", () => {
    // Drive the FSM into HIGH_ALERT first, so a naive spread would write it.
    let state = initAlertState();
    state = applyAlertState(
      makeRecord("fresh", "fresh", 1, HIGH),
      state,
      0,
    ).state;
    state = applyAlertState(
      makeRecord("fresh", "fresh", 2, HIGH),
      state,
      2500,
    ).state;
    expect(state.severity).toBe("HIGH_ALERT");

    const unavailable = makeRecord("missing", "missing", 3);
    expect(unavailable.RiskLevel).toBeNull();
    const result = applyAlertState(unavailable, state, 3000);

    expect(result.record.AlertSeverity).toBeNull();
    // ...but the FSM memory survives, so recovery is not reset by a blackout.
    expect(result.state.severity).toBe("HIGH_ALERT");
    expect(() => assertAvailabilityInvariant(result.record)).not.toThrow();
  });

  it("the four-fields-null contract holds on the emitted record", () => {
    const { record } = applyAlertState(
      makeRecord("missing", "missing", 1),
      initAlertState(),
      0,
    );
    expect(record).toMatchObject({
      assessment_available: false,
      RiskScore: null,
      RiskLevel: null,
      DominantEvidence: null,
      AlertSeverity: null,
      SystemHealth: "UNAVAILABLE",
    });
  });

  it("an available record still receives the FSM severity (escalation after 2000 ms)", () => {
    let state = initAlertState();
    const first = applyAlertState(
      makeRecord("fresh", "fresh", 1, HIGH),
      state,
      0,
    );
    state = first.state;
    expect(first.record.AlertSeverity).toBe("CAUTION");
    const second = applyAlertState(
      makeRecord("fresh", "fresh", 2, HIGH),
      state,
      2000,
    );
    expect(second.record.AlertSeverity).toBe("HIGH_ALERT");
    expect(() => assertAvailabilityInvariant(second.record)).not.toThrow();
  });
});

// Task 9 / K3 (plan Step 4): the retained replay is not exempt from D01. App's
// appendReplay used to spread `AlertSeverity: fsm.severity` over every record, which
// compiles whatever the level is and silently overwrote the null of an unassessed
// window - and, with RiskLevel null, the FSM must also stop crediting that window to
// either timer. These two describes guard the call site: first the exact fold App
// performs (buildRiskUpdate -> applyAlertState, one prepared window per 2 s), then
// the source of the call site itself.
describe("the replay fold (what App.appendReplay does) keeps D01 on the unassessed window", () => {
  const T0 = Date.UTC(2026, 4, 6, 2, 0, 0);
  const folded: Array<{
    record: RiskUpdate;
    lowSince: number | null;
    highSince: number | null;
  }> = [];
  let previous: RiskUpdate | undefined;
  let state = initAlertState();
  PREPARED_SESSION_WINDOWS.forEach((window, index) => {
    const built = buildRiskUpdate(
      window,
      "session_001",
      DEFAULT_CONFIG,
      previous,
      index + 1,
    );
    const overlaid = applyAlertState(built, state, T0 + index * 2000);
    state = overlaid.state;
    previous = built;
    folded.push({
      record: overlaid.record,
      lowSince: state.lowSince,
      highSince: state.highSince,
    });
  });
  const at = (windowId: number) => folded[windowId - 1];

  it("window 17 has neither branch: RiskLevel and AlertSeverity are both null", () => {
    expect(at(17).record.assessment_available).toBe(false);
    expect(at(17).record.RiskLevel).toBeNull();
    expect(at(17).record.AlertSeverity).toBeNull();
  });

  it("the FSM starts no recovery timer on window 17 (it used to be read as Low and advance the 10 s timer)", () => {
    // Window 16 is High, so the machine is mid-High streak; the null window drops
    // both streaks instead of falling through to the Low branch.
    expect(at(16).record.RiskLevel).toBe("High");
    expect(at(17).lowSince).toBeNull();
    expect(at(17).highSince).toBeNull();
    // The first assessed window afterwards re-anchors its own streak.
    expect(at(18).highSince).toBe(T0 + 17 * 2000);
  });

  it("the severity comes back on the first assessed window after the gap", () => {
    expect(at(18).record.RiskLevel).toBe("High");
    expect(at(18).record.AlertSeverity).not.toBeNull();
  });

  it("every window obeys the availability invariant, and only window 17 has a null severity", () => {
    for (const { record } of folded) {
      expect(() => assertAvailabilityInvariant(record)).not.toThrow();
    }
    expect(
      folded
        .filter(({ record }) => record.AlertSeverity === null)
        .map(({ record }) => record.window_id),
    ).toEqual([17]);
  });
});

describe("the replay call site goes through applyAlertState (source guard)", () => {
  // Not a behaviour test: it reads App.tsx. The overlay is correct on its own; what
  // nothing else notices is a call site that stops using it and spreads the FSM's
  // never-null severity back onto the record.
  const code = appSource
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/(^|[^:])\/\/.*$/gm, "$1");

  it("appendReplay overlays the FSM with applyAlertState", () => {
    expect(code).toMatch(/applyAlertState\(/);
  });

  it("App.tsx never calls updateAlertState itself, and never assigns AlertSeverity", () => {
    expect(code).not.toMatch(/\bupdateAlertState\b/);
    expect(code).not.toMatch(/AlertSeverity\s*:/);
  });
});
