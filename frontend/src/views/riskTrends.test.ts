import { describe, expect, it } from "vitest";

import { replayRecords, makeRecord } from "../testing/records";
import { distribution, riskRowClassName } from "./riskDistribution";

const asCounts = (history: Parameters<typeof distribution>[0]) =>
  Object.fromEntries(distribution(history).map((d) => [d.label, d.count]));

describe("UT-DIST-01: distribution() over the 25-window prepared replay", () => {
  const records = replayRecords();
  const counts = asCounts(records);

  it("the replay has 25 windows, exactly one of them unavailable (window 17)", () => {
    expect(records).toHaveLength(25);
    const unavailable = records.filter((r) => !r.assessment_available);
    expect(unavailable.map((r) => r.window_id)).toEqual([17]);
  });

  it("returns the four buckets Low, Medium, High, Unavailable in that order", () => {
    expect(distribution(records).map((d) => d.label)).toEqual([
      "Low",
      "Medium",
      "High",
      "Unavailable",
    ]);
  });

  it("Unavailable === 1", () => {
    expect(counts.Unavailable).toBe(1);
  });

  it("the four counts sum to exactly 25 (not 24)", () => {
    const total = counts.Low + counts.Medium + counts.High + counts.Unavailable;
    expect(total).toBe(25);
    expect(total).toBe(records.length);
  });

  it("each level bucket matches an independent count over the records", () => {
    for (const level of ["Low", "Medium", "High"] as const) {
      expect(counts[level]).toBe(
        records.filter((r) => r.RiskLevel === level).length,
      );
    }
  });

  it("an empty history yields four zero buckets", () => {
    expect(asCounts([])).toEqual({
      Low: 0,
      Medium: 0,
      High: 0,
      Unavailable: 0,
    });
  });
});

describe("riskRowClassName: unavailable rows are not styled like ordinary ones", () => {
  const high = makeRecord("fresh", "fresh", 1, {
    P_distraction: 0.9,
    P_telemetry_anomaly: 0.9,
  });
  const low = makeRecord("fresh", "fresh", 2, {
    P_distraction: 0.05,
    P_telemetry_anomaly: 0.05,
  });
  const unavailable = makeRecord("missing", "missing", 3);

  it("a High row carries is-high-risk", () => {
    expect(high.RiskLevel).toBe("High");
    expect(riskRowClassName(high, 99)).toContain("is-high-risk");
  });

  it("a Low row carries neither marker", () => {
    expect(low.RiskLevel).toBe("Low");
    const cls = riskRowClassName(low, 99);
    expect(cls).not.toContain("is-high-risk");
    expect(cls).not.toContain("is-unavailable");
  });

  it("an unavailable row carries is-unavailable and never is-high-risk", () => {
    const cls = riskRowClassName(unavailable, 99);
    expect(cls).toContain("is-unavailable");
    expect(cls).not.toContain("is-high-risk");
  });

  it("the selected row is marked", () => {
    expect(riskRowClassName(low, 2)).toContain("is-selected");
    expect(riskRowClassName(low, 1)).not.toContain("is-selected");
  });
});
