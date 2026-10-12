import { describe, expect, it } from "vitest";

import { makeRecord } from "../testing/records";
import { UNAVAILABLE_LABEL } from "../utils/format";
import { buildTrendSeries, formatTrendTooltip } from "./trendSeries";

describe("UT-TREND-01: the trend series nulls the risk point exactly for unavailable windows", () => {
  const available = makeRecord("fresh", "fresh", 1);
  const unavailable = makeRecord("missing", "missing", 2);
  const series = buildTrendSeries([available, unavailable]);

  it("an unavailable window has a null risk point (a gap, not a 0)", () => {
    expect(series[1].window).toBe(2);
    expect(series[1].risk).toBeNull();
  });

  it("an available window keeps its RiskScore", () => {
    expect(series[0].risk).toBe(available.RiskScore);
  });

  it("an available window whose score is genuinely 0 is NOT nulled", () => {
    // 0 is a real reading; only assessment_available === false produces a gap.
    const zero = {
      ...makeRecord("fresh", "fresh", 3, {
        P_distraction: 0,
        P_telemetry_anomaly: 0,
      }),
    };
    expect(zero.assessment_available).toBe(true);
    expect(zero.RiskScore).toBe(0);
    expect(buildTrendSeries([zero])[0].risk).toBe(0);
  });

  it("the point is keyed on assessment_available, not on SystemHealth", () => {
    // The old predicate read SystemHealth === "UNAVAILABLE". A record whose
    // availability flag is false is a gap regardless of any other field.
    const flagged = { ...available, assessment_available: false };
    expect(buildTrendSeries([flagged])[0].risk).toBeNull();
    const healthy = {
      ...unavailable,
      assessment_available: true,
      RiskScore: 12,
    };
    expect(buildTrendSeries([healthy])[0].risk).toBe(12);
  });

  it("branch points are null only for a missing branch", () => {
    expect(series[0].vision).not.toBeNull();
    expect(series[0].telemetry).not.toBeNull();
    expect(series[1].vision).toBeNull();
    expect(series[1].telemetry).toBeNull();
  });
});

describe("UT-TREND-01: the tooltip never turns a null point into 0.0 / 100", () => {
  it("null and undefined risk points render the unavailable sentinel", () => {
    expect(formatTrendTooltip(null, "RiskScore")).toBe(UNAVAILABLE_LABEL);
    expect(formatTrendTooltip(undefined, "RiskScore")).toBe(UNAVAILABLE_LABEL);
    // Number(null) === 0 is what the old formatter passed to formatRiskScore.
    expect(Number(null)).toBe(0);
    expect(formatTrendTooltip(null, "RiskScore")).not.toBe("0.0 / 100");
  });

  it("a genuine score of 0 still renders as 0.0 / 100", () => {
    expect(formatTrendTooltip(0, "RiskScore")).toBe("0.0 / 100");
  });

  it("a real score renders to one decimal", () => {
    expect(formatTrendTooltip(62.5, "RiskScore")).toBe("62.5 / 100");
  });

  it("branch series use percent and also refuse to invent 0%", () => {
    expect(formatTrendTooltip(41.25, "P_distraction (%)")).toBe("41.3%");
    expect(formatTrendTooltip(null, "P_distraction (%)")).toBe(
      UNAVAILABLE_LABEL,
    );
    expect(formatTrendTooltip(null, "Telemetry non-safe (%)")).toBe(
      UNAVAILABLE_LABEL,
    );
    expect(formatTrendTooltip(0, "Telemetry non-safe (%)")).toBe("0.0%");
  });
});
