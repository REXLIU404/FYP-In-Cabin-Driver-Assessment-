import { describe, expect, it } from "vitest";
import { initAlertState, updateAlertState } from "./alertFsm";
import type { AlertFsmState } from "./alertFsm";
import type { RiskLevel } from "./types";

/**
 * The 2 s sustain and the 10 s recovery are HARD-CODED here (2000 / 10000 ms) on
 * purpose. These tests used to import ALERT_SUSTAIN_MS / ALERT_RECOVER_MS, so a
 * change to either constant moved the expectation together with the
 * implementation and nothing went red (audit EX-TS-19/21).
 */
const feed = (
  steps: Array<[RiskLevel | null, number]>,
  from: AlertFsmState = initAlertState(),
) => {
  let state = from;
  const trace: string[] = [];
  for (const [level, at] of steps) {
    state = updateAlertState(state, level, at);
    trace.push(state.severity);
  }
  return { state, trace };
};

describe("AlertSeverity FSM", () => {
  it("starts in NORMAL", () => {
    expect(initAlertState().severity).toBe("NORMAL");
  });

  it("first High tick is CAUTION (not yet sustained)", () => {
    const s = updateAlertState(initAlertState(), "High", 1000);
    expect(s.severity).toBe("CAUTION");
    expect(s.highSince).toBe(1000);
  });

  it("escalates to HIGH_ALERT only after High persists >= 2000 ms", () => {
    let s = updateAlertState(initAlertState(), "High", 1000);
    // just before the threshold
    s = updateAlertState(s, "High", 1000 + 2000 - 1);
    expect(s.severity).toBe("CAUTION");
    // at the threshold
    s = updateAlertState(s, "High", 1000 + 2000);
    expect(s.severity).toBe("HIGH_ALERT");
  });

  it("holds HIGH_ALERT while risk stays Low for less than the recover window", () => {
    const s = { severity: "HIGH_ALERT", highSince: 0, lowSince: null } as const;
    const next = updateAlertState(s, "Low", 5000);
    expect(next.severity).toBe("HIGH_ALERT"); // 5 s < 10 s recover
    expect(next.lowSince).toBe(5000);
  });

  it("auto-recovers to NORMAL after Low persists >= 10000 ms", () => {
    let s = updateAlertState(
      { severity: "HIGH_ALERT", highSince: 0, lowSince: null },
      "Low",
      0,
    );
    expect(s.severity).toBe("HIGH_ALERT");
    s = updateAlertState(s, "Low", 10000);
    expect(s.severity).toBe("NORMAL");
  });

  it("Medium maps to CAUTION and clears the High streak", () => {
    const high = updateAlertState(initAlertState(), "High", 0);
    const med = updateAlertState(high, "Medium", 500);
    expect(med.severity).toBe("CAUTION");
    expect(med.highSince).toBeNull();
  });

  it("a brief High spike followed by Medium never reaches HIGH_ALERT", () => {
    let s = updateAlertState(initAlertState(), "High", 0); // CAUTION
    s = updateAlertState(s, "Medium", 500); // CAUTION, streak cleared
    s = updateAlertState(s, "High", 1000); // streak restarts -> CAUTION
    expect(s.severity).toBe("CAUTION");
  });
});

describe("UT-TIME-01 FSM boundaries (wall clock, hard-coded 2000 / 10000 ms)", () => {
  it("High sustain: 0 and 1900 ms are CAUTION, 2000 and 2100 ms are HIGH_ALERT", () => {
    const { trace } = feed([
      ["High", 0],
      ["High", 1900],
      ["High", 2000],
      ["High", 2100],
    ]);
    expect(trace).toEqual(["CAUTION", "CAUTION", "HIGH_ALERT", "HIGH_ALERT"]);
  });

  it("Low recovery from 2100: 9.9 s still HIGH_ALERT, 10.0 s is NORMAL", () => {
    const latched = feed([
      ["High", 0],
      ["High", 2000],
      ["High", 2100],
    ]).state;
    expect(latched.severity).toBe("HIGH_ALERT");
    const { trace } = feed(
      [
        ["Low", 2100], // the Low streak starts here
        ["Low", 12000], // 9.9 s
        ["Low", 12100], // 10.0 s
      ],
      latched,
    );
    expect(trace).toEqual(["HIGH_ALERT", "HIGH_ALERT", "NORMAL"]);
  });

  it("an interrupted High streak restarts: Medium@1000 clears it, 1.9 s is CAUTION, 2.0 s is HIGH_ALERT", () => {
    const { trace } = feed([
      ["High", 0],
      ["Medium", 1000], // CAUTION, streak cleared
      ["High", 1500],
      ["High", 3400], // 1.9 s since 1500
      ["High", 3500], // 2.0 s since 1500
    ]);
    expect(trace).toEqual([
      "CAUTION",
      "CAUTION",
      "CAUTION",
      "CAUTION",
      "HIGH_ALERT",
    ]);
  });
});

describe("a window with no assessment (level === null) suspends the FSM", () => {
  it("UT-TIME-04: High@0 -> unavailable@1000 -> High@2000 does NOT escalate", () => {
    // 2000 ms of wall clock separate the first and last High window, but the
    // second of them was a dead interval: it must not count toward the sustain.
    const { trace, state } = feed([
      ["High", 0],
      [null, 1000],
      ["High", 2000],
    ]);
    expect(trace).toEqual(["CAUTION", "CAUTION", "CAUTION"]);
    expect(state.highSince).toBe(2000); // re-anchored to the resume window
  });

  it("the sustain restarts at the resume window: 1.9 s is CAUTION, 2.0 s is HIGH_ALERT", () => {
    const { trace } = feed([
      ["High", 0],
      [null, 1000],
      ["High", 2000],
      ["High", 3900],
      ["High", 4000],
    ]);
    expect(trace).toEqual([
      "CAUTION",
      "CAUTION",
      "CAUTION",
      "CAUTION",
      "HIGH_ALERT",
    ]);
  });

  it("never invents severity: null on a fresh machine stays NORMAL and starts no timer", () => {
    const s = updateAlertState(initAlertState(), null, 5000);
    expect(s).toEqual({ severity: "NORMAL", highSince: null, lowSince: null });
  });

  it("an active HIGH_ALERT is neither cleared nor escalated by missing evidence", () => {
    const latched: AlertFsmState = {
      severity: "HIGH_ALERT",
      highSince: 0,
      lowSince: null,
    };
    let s = latched;
    // A minute of no-evidence windows: previously this fell into the Low branch
    // and started the 10 s recovery timer, silently clearing the alert.
    for (let at = 0; at <= 60000; at += 1000) {
      s = updateAlertState(s, null, at);
      expect(s.severity).toBe("HIGH_ALERT");
      expect(s.lowSince).toBeNull();
    }
  });

  it("the dead interval is not credited to the Low recovery either", () => {
    // Low@0 starts the recovery. A 9 s blackout follows. Low@10000 is 10 s of
    // wall clock after Low@0 but only a fresh streak: still HIGH_ALERT.
    const { trace } = feed(
      [
        ["Low", 0],
        [null, 1000],
        [null, 9000],
        ["Low", 10000], // would be NORMAL if the blackout were credited
        ["Low", 19900], // 9.9 s after the resume window
        ["Low", 20000], // 10.0 s after the resume window
      ],
      { severity: "HIGH_ALERT", highSince: 0, lowSince: null },
    );
    expect(trace).toEqual([
      "HIGH_ALERT",
      "HIGH_ALERT",
      "HIGH_ALERT",
      "HIGH_ALERT",
      "HIGH_ALERT",
      "NORMAL",
    ]);
  });

  it("the internal severity is never null, whatever the input", () => {
    let s = initAlertState();
    for (const level of ["High", null, "Medium", null, "Low", null] as const) {
      s = updateAlertState(s, level, 1);
      expect(s.severity).not.toBeNull();
    }
  });
});
