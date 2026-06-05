import { describe, expect, it } from "vitest";
import {
  ALERT_RECOVER_MS,
  ALERT_SUSTAIN_MS,
  initAlertState,
  updateAlertState,
} from "./alertFsm";

describe("AlertSeverity FSM", () => {
  it("starts in NORMAL", () => {
    expect(initAlertState().severity).toBe("NORMAL");
  });

  it("first High tick is CAUTION (not yet sustained)", () => {
    const s = updateAlertState(initAlertState(), "High", 1000);
    expect(s.severity).toBe("CAUTION");
    expect(s.highSince).toBe(1000);
  });

  it("escalates to HIGH_ALERT only after High persists >= sustain window", () => {
    let s = updateAlertState(initAlertState(), "High", 1000);
    // just before the threshold
    s = updateAlertState(s, "High", 1000 + ALERT_SUSTAIN_MS - 1);
    expect(s.severity).toBe("CAUTION");
    // at the threshold
    s = updateAlertState(s, "High", 1000 + ALERT_SUSTAIN_MS);
    expect(s.severity).toBe("HIGH_ALERT");
  });

  it("holds HIGH_ALERT while risk stays Low for less than recover window", () => {
    let s = { severity: "HIGH_ALERT", highSince: 0, lowSince: null } as const;
    let next = updateAlertState(s, "Low", 5000);
    expect(next.severity).toBe("HIGH_ALERT"); // 5s < 10s recover
    expect(next.lowSince).toBe(5000);
  });

  it("auto-recovers to NORMAL after Low persists >= recover window", () => {
    let s = updateAlertState(
      { severity: "HIGH_ALERT", highSince: 0, lowSince: null },
      "Low",
      0,
    );
    expect(s.severity).toBe("HIGH_ALERT");
    s = updateAlertState(s, "Low", ALERT_RECOVER_MS);
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
