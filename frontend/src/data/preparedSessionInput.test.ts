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

  it("exercises every RiskLevel", () => {
    const levels = new Set(records.map((r) => r.RiskLevel));
    expect(levels).toEqual(new Set(["Low", "Medium", "High"]));
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
