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

// Task 9 / K5 (P1-6 leftover). The tooltip percent used to come from `P x 100` handed to
// formatFixed(..., 1): the multiplication happens in binary, so a probability sitting
// exactly on a decimal tie (0.2855) arrives as 28.549999999999997 and rounds DOWN. The
// rule is half-up on the DECIMAL digits, scaled afterwards - the same order as
// asPercent. These go through the whole path the chart uses: record -> series point ->
// tooltip formatter.
describe("the branch tooltips round half-up on the probability, not on P x 100 (K5)", () => {
  const tooltipFor = (
    over: { P_distraction?: number; P_telemetry_anomaly?: number },
    branch: "vision" | "telemetry",
  ) => {
    const [point] = buildTrendSeries([makeRecord("fresh", "fresh", 1, over)]);
    return formatTrendTooltip(
      point[branch],
      branch === "vision" ? "P_distraction (%)" : "Telemetry non-safe (%)",
    );
  };

  it("guard on the test itself: these inputs really are ones where P x 100 lands below the tie", () => {
    expect(0.2855 * 100).toBeLessThan(28.55);
    expect(0.1455 * 100).toBeLessThan(14.55);
  });

  it("P_distraction 0.2855 reads 28.6%, not 28.5%", () => {
    expect(tooltipFor({ P_distraction: 0.2855 }, "vision")).toBe("28.6%");
  });

  it("P_distraction 0.1455 reads 14.6%, not 14.5%", () => {
    expect(tooltipFor({ P_distraction: 0.1455 }, "vision")).toBe("14.6%");
  });

  it("ties that other rounding recipes get wrong also read half-up (0.5005 -> 50.1%, 0.0015 -> 0.2%)", () => {
    // Math.round(P * 1000) / 10 gives 50 for 0.5005; (P * 100).toFixed(1) gives 0.1 for
    // 0.0015. The decimal-digit rounding gets both right.
    expect(Math.round(0.5005 * 1000) / 10).toBe(50);
    expect((0.0015 * 100).toFixed(1)).toBe("0.1");
    expect(tooltipFor({ P_distraction: 0.5005 }, "vision")).toBe("50.1%");
    expect(tooltipFor({ P_telemetry_anomaly: 0.0015 }, "telemetry")).toBe(
      "0.2%",
    );
  });

  it("the telemetry branch rounds the same way", () => {
    expect(tooltipFor({ P_telemetry_anomaly: 0.2855 }, "telemetry")).toBe(
      "28.6%",
    );
    expect(tooltipFor({ P_telemetry_anomaly: 0.1455 }, "telemetry")).toBe(
      "14.6%",
    );
  });

  it("values off a tie are unchanged, and the ends of the range are exact", () => {
    expect(tooltipFor({ P_distraction: 0.2854 }, "vision")).toBe("28.5%");
    expect(tooltipFor({ P_distraction: 0.2856 }, "vision")).toBe("28.6%");
    expect(tooltipFor({ P_distraction: 0 }, "vision")).toBe("0.0%");
    expect(tooltipFor({ P_distraction: 1 }, "vision")).toBe("100.0%");
    expect(tooltipFor({ P_distraction: 0.5 }, "vision")).toBe("50.0%");
  });

  it("a stored 3-decimal probability maps to its exact percent, with no binary dust on the coordinate", () => {
    // P x 100 gives 7.000000000000001, 28.999999999999996 and 56.99999999999999 here.
    const coordinate = (p: number) =>
      buildTrendSeries([
        makeRecord("fresh", "fresh", 1, { P_distraction: p }),
      ])[0].vision;
    expect(coordinate(0.07)).toBe(7);
    expect(coordinate(0.29)).toBe(29);
    expect(coordinate(0.57)).toBe(57);
    expect(coordinate(0.286)).toBe(28.6);
  });
});
