import { describe, expect, it } from "vitest";

import { buildRiskUpdate, DEFAULT_CONFIG } from "../../../ai/src/riskLogic";
import type { RiskUpdate } from "../types";
import {
  PREPARED_SESSION_WINDOWS,
  buildPreparedWindows,
} from "./preparedSessionInput";

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
    // old numbers. Ruling A (D13) then moved window 16 again, 62.5 -> 60: its
    // telemetry is 4 s old (> 3 s), so it is EXPIRED and scores as missing, and the
    // window is the vision branch alone (0.6 -> 60.0) instead of a 0.45-weighted blend.
    const at = (id: number) => records[id - 1];
    expect([at(16).RiskScore, at(16).RiskLevel]).toEqual([60, "High"]);
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

// Ruling A (D13) on the replay: evidence older than the 3 s tolerance (strictly: exactly
// 3 s is still fresh) is EXPIRED and scores as `missing`; the runtime no longer produces
// `stale`. Each window records why in `expiry` (copied into `provenance` by the
// pipeline) - for both branches, always - so "expired" is distinguishable from "never
// received".
describe("prepared replay: expired evidence is missing, and the reason is kept", () => {
  const at = (id: number) => records[id - 1];

  it("window 16: telemetry 4 s old is missing and EXPIRED, with its age", () => {
    expect(at(16).modality_freshness).toEqual({
      vision: "fresh",
      telemetry: "missing",
    });
    expect(at(16).provenance).toEqual({
      vision_expired: false,
      vision_age_s: null,
      telemetry_expired: true,
      telemetry_age_s: 4,
    });
    expect(at(16).SystemHealth).toBe("DEGRADED");
    // An expired branch carries P = 0 like a missing one (the backend does the same), so
    // the 4-s-old reading's 1 - p_safe = 0.68 cannot reach the record or the score.
    expect(at(16).P_telemetry_anomaly).toBe(0);
  });

  it("a branch that was never received is missing but NOT expired (windows 14, 15, 17)", () => {
    // Window 14 has no telemetry (the CSV's 999 is a sentinel, never reported as an age),
    // window 15 no frame, window 17 neither.
    expect(at(14).modality_freshness.telemetry).toBe("missing");
    expect(at(14).provenance).toEqual({
      vision_expired: false,
      vision_age_s: null,
      telemetry_expired: false,
      telemetry_age_s: null,
    });
    expect(at(15).modality_freshness.vision).toBe("missing");
    expect(at(15).provenance?.vision_expired).toBe(false);
    expect(at(17).provenance).toEqual({
      vision_expired: false,
      vision_age_s: null,
      telemetry_expired: false,
      telemetry_age_s: null,
    });
  });

  it("exactly one window in the shipped session is expired (16), and none is stale", () => {
    expect(
      records
        .filter(
          (r) =>
            r.provenance?.vision_expired || r.provenance?.telemetry_expired,
        )
        .map((r) => r.window_id),
    ).toEqual([16]);
    for (const r of records) {
      expect(["fresh", "missing"]).toContain(r.modality_freshness.vision);
      expect(["fresh", "missing"]).toContain(r.modality_freshness.telemetry);
    }
  });

  it("every record carries the four expiry fields, for both branches", () => {
    for (const r of records) {
      expect(Object.keys(r.provenance ?? {}).sort()).toEqual([
        "telemetry_age_s",
        "telemetry_expired",
        "vision_age_s",
        "vision_expired",
      ]);
    }
  });

  describe("the 3 s boundary is strict (> 3)", () => {
    const HEADER =
      "window_id,timestamp,frame_file,vision_available,telemetry_available,telemetry_age_s,speed_kmph,accel_x,accel_y,brake_pressure,steering_angle,throttle,lane_deviation,headway_distance,p_safe,p_aggressive,p_distracted";
    const row = (age: string) =>
      `1,10:00:01,frame_safe_a.jpg,1,1,${age},34,0.3,0.1,12,-2.0,30,0.3,26,0.2,0.04,0.02`;
    const window1 = (age: string) =>
      buildPreparedWindows([HEADER, row(age)].join("\n"))[0];

    it.each([
      ["0", "fresh", false, 0],
      ["2.999", "fresh", false, 2.999],
      ["3", "fresh", false, 3],
      ["3.001", "missing", true, 3.001],
      ["4", "missing", true, 4],
      ["3600", "missing", true, 3600],
    ] as const)(
      "telemetry age %s s -> %s (expired %s)",
      (age, status, expired, ageS) => {
        const w = window1(age);
        expect(w.telemetry_status).toBe(status);
        expect(w.expiry).toEqual({
          vision_expired: false,
          vision_age_s: null,
          telemetry_expired: expired,
          telemetry_age_s: ageS,
        });
      },
    );
  });
});

// The replay turns 1 - p_safe into P_telemetry_anomaly through the one parsing
// path, buildPreparedWindows. The shipped CSV has two-decimal p_safe values, where
// toFixed(3) and half-up agree, so a regression to toFixed would not move a single
// shipped number - it needs a CSV with p_safe on a four-decimal tie.
describe("replay probabilities are rounded half-up, not by the binary value", () => {
  const HEADER =
    "window_id,timestamp,frame_file,vision_available,telemetry_available,telemetry_age_s,speed_kmph,accel_x,accel_y,brake_pressure,steering_angle,throttle,lane_deviation,headway_distance,p_safe,p_aggressive,p_distracted";
  const row = (windowId: number, pSafe: string, telemetryAvailable = 1) =>
    `${windowId},10:00:0${windowId},frame_safe_a.jpg,1,${telemetryAvailable},0,34,0.3,0.1,12,-2.0,30,0.3,26,${pSafe},0.04,0.02`;
  const parse = (...rows: string[]) =>
    buildPreparedWindows([HEADER, ...rows].join("\n"));

  it("inputs are ones where toFixed(3) rounds the tie DOWN", () => {
    // Guard on the test itself: if these stopped disagreeing the next test
    // could no longer tell the two roundings apart.
    expect(Number((1 - 0.0635).toFixed(3))).toBe(0.936);
    expect(Number((1 - 0.3135).toFixed(3))).toBe(0.686);
    expect(Number((1 - 0.9385).toFixed(3))).toBe(0.061);
    // 0.4895 also defeats Math.round(v * 1000) / 1000 (1 - 0.4895 is 0.5105).
    expect(Number((1 - 0.4895).toFixed(3))).toBe(0.51);
    expect(Math.round((1 - 0.4895) * 1000) / 1000).toBe(0.51);
  });

  it("P_telemetry_anomaly = 1 - p_safe breaks decimal ties upward", () => {
    // Exact decimal arithmetic: 1 - 0.0635 = 0.9365 -> 0.937, 1 - 0.3135 =
    // 0.6865 -> 0.687, 1 - 0.9385 = 0.0615 -> 0.062, 1 - 0.4895 = 0.5105 ->
    // 0.511; 0.94 is no tie (0.06).
    const windows = parse(
      row(1, "0.0635"),
      row(2, "0.3135"),
      row(3, "0.9385"),
      row(4, "0.4895"),
      row(5, "0.94"),
    );
    expect(windows.map((w) => w.P_telemetry_anomaly)).toEqual([
      0.937, 0.687, 0.062, 0.511, 0.06,
    ]);
  });

  it("P_distraction (vision branch) and a window without telemetry are unchanged", () => {
    const windows = parse(row(1, "0.0635"), row(2, "0.0635", 0));
    expect(windows.map((w) => w.P_distraction)).toEqual([0.07, 0.07]);
    expect(windows[1].P_telemetry_anomaly).toBe(0);
  });
});
