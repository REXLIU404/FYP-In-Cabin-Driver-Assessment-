import { describe, expect, it } from "vitest";

import { buildRiskUpdate, DEFAULT_CONFIG } from "../../../ai/src/riskLogic";
import type { RiskUpdate } from "../types";
import { PREPARED_SESSION_WINDOWS } from "./preparedSessionInput";

// Drive the real fusion pipeline (incl. EMA smoothing) over the prepared replay,
// exactly as the app does, then assert the session exercises every risk/evidence
// case the MVP guidebook requires. This guards the demo data against regressions.
const records: RiskUpdate[] = [];
let previous: RiskUpdate | undefined;
PREPARED_SESSION_WINDOWS.forEach((window, index) => {
  const record = buildRiskUpdate(
    window,
    "session_001",
    DEFAULT_CONFIG,
    previous,
    index + 1,
  );
  records.push(record);
  previous = record;
});

describe("prepared session replay coverage", () => {
  it("provides at least 25 monitoring windows", () => {
    expect(records.length).toBeGreaterThanOrEqual(25);
  });

  it("exercises every RiskLevel, plus null for the unassessable window", () => {
    // Window 17 has neither branch, so its RiskLevel is null - not a fabricated
    // "Low". The set is therefore the three levels AND null.
    const levels = new Set(records.map((r) => r.RiskLevel));
    expect(levels).toEqual(new Set(["Low", "Medium", "High", null]));
  });

  it("has exactly one unavailable window (window 17), with all four fields null", () => {
    const unavailable = records.filter((r) => !r.assessment_available);
    expect(unavailable).toHaveLength(1);
    const [window17] = unavailable;
    expect(window17.window_id).toBe(17);
    expect(window17).toMatchObject({
      RiskScore: null,
      RiskLevel: null,
      DominantEvidence: null,
      AlertSeverity: null,
      SystemHealth: "UNAVAILABLE",
    });
    // The other 24 windows are all assessed.
    expect(records.filter((r) => r.assessment_available)).toHaveLength(24);
  });

  it("pins the demo values that changed when the temporal layer was aligned to the backend", () => {
    // Task 5 moved 11 of 25 windows (7, 9, 16, 18-25): half-up rounding at
    // exact ties, plus the EMA re-seeding after a stale / missing / unavailable
    // window. These are the headline ones; the data was NOT edited to keep the
    // old numbers.
    const at = (id: number) => records[id - 1];
    expect([at(16).RiskScore, at(16).RiskLevel]).toEqual([62.5, "High"]);
    expect([at(18).RiskScore, at(18).RiskLevel]).toEqual([70, "High"]);
    expect(at(19).DominantEvidence).toBe("Vision-dominant");
    expect(at(7).RiskScore).toBe(31);
    expect(at(9).RiskScore).toBe(68.1);
  });

  it("exercises every DominantEvidence type", () => {
    const dominant = new Set(records.map((r) => r.DominantEvidence));
    for (const expected of [
      "Vision-dominant",
      "Telemetry-dominant",
      "Combined evidence",
      "Partial evidence",
      "Low observed risk",
    ]) {
      expect(dominant).toContain(expected);
    }
  });

  it("exercises every SystemHealth state", () => {
    const health = new Set(records.map((r) => r.SystemHealth));
    expect(health).toEqual(new Set(["FULL", "DEGRADED", "UNAVAILABLE"]));
  });

  it("ends with a sustained low-risk recovery tail (>= 5 windows, >= 10s @ dt=2s)", () => {
    let tail = 0;
    for (let i = records.length - 1; i >= 0; i -= 1) {
      if (records[i].RiskLevel === "Low") tail += 1;
      else break;
    }
    expect(tail).toBeGreaterThanOrEqual(5);
  });

  it("sustains High risk long enough to trip HIGH_ALERT (>= 2 consecutive windows)", () => {
    let maxRun = 0;
    let run = 0;
    for (const r of records) {
      run = r.RiskLevel === "High" ? run + 1 : 0;
      maxRun = Math.max(maxRun, run);
    }
    expect(maxRun).toBeGreaterThanOrEqual(2);
  });
});
