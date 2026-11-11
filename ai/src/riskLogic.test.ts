import { describe, expect, it } from "vitest";
import {
  DEFAULT_CONFIG,
  asPercent,
  buildRiskUpdate,
  computeRiskScore,
  mapRiskLevel,
  mapSystemHealth,
} from "./riskLogic";
import { determineEvidenceType } from "./evidence";
import type { PreparedSessionWindow } from "./types";

describe("mapRiskLevel boundaries (thresholds 30 / 60 on a 0-100 score)", () => {
  it("29.9 -> Low", () => expect(mapRiskLevel(29.9)).toBe("Low"));
  it("30.0 -> Medium", () => expect(mapRiskLevel(30)).toBe("Medium"));
  it("59.9 -> Medium", () => expect(mapRiskLevel(59.9)).toBe("Medium"));
  it("60.0 -> High", () => expect(mapRiskLevel(60)).toBe("High"));
  it("0 -> Low / 100 -> High", () => {
    expect(mapRiskLevel(0)).toBe("Low");
    expect(mapRiskLevel(100)).toBe("High");
  });
});

describe("computeRiskScore (freshness-weighted late fusion)", () => {
  it("equal inputs, equal weights -> 50", () => {
    expect(computeRiskScore(0.5, 0.5)).toBe(50);
  });

  it("missing telemetry falls back to vision only (re-normalised)", () => {
    expect(computeRiskScore(0.8, 0.2, 0.5, 0.5, "fresh", "missing")).toBe(80);
  });

  it("both modalities missing -> null (no evidence is not a 0 reading)", () => {
    expect(
      computeRiskScore(0.8, 0.9, 0.5, 0.5, "missing", "missing"),
    ).toBeNull();
  });

  it("w_v=1, w_t=0 with vision missing -> null (zero effective weight)", () => {
    expect(
      computeRiskScore(0.8, 0.9, 1.0, 0.0, "missing", "fresh"),
    ).toBeNull();
  });

  it("w_v=0, w_t=1 with telemetry missing -> null (zero effective weight)", () => {
    expect(
      computeRiskScore(0.8, 0.9, 0.0, 1.0, "fresh", "missing"),
    ).toBeNull();
  });

  it("zero weight on the surviving branch is still null, never 0", () => {
    // Vision fresh but weight 0, telemetry missing: nothing carries weight.
    expect(computeRiskScore(0.8, 0.9, 0.0, 1.0, "fresh", "missing")).not.toBe(0);
  });

  it("zero weight on a missing branch is harmless (F-Z3: available)", () => {
    expect(computeRiskScore(0.1, 0.9, 1.0, 0.0, "fresh", "missing")).toBe(10);
  });

  it("stale branches are down-weighted to 0.45 and re-normalised", () => {
    // (0.5*0.45*0.1 + 0.5*0.9) / (0.5*0.45 + 0.5) = 0.65172 -> 65.2
    expect(computeRiskScore(0.1, 0.9, 0.5, 0.5, "stale", "fresh")).toBe(65.2);
  });
});

describe("mapRiskLevel with an unavailable score", () => {
  it("null -> null (not Low: null < 30 is true in JS)", () => {
    expect(mapRiskLevel(null)).toBeNull();
  });
});

describe("mapSystemHealth", () => {
  it("both fresh -> FULL", () =>
    expect(mapSystemHealth("fresh", "fresh")).toBe("FULL"));
  it("one stale/missing -> DEGRADED", () =>
    expect(mapSystemHealth("fresh", "missing")).toBe("DEGRADED"));
  it("both missing -> UNAVAILABLE", () =>
    expect(mapSystemHealth("missing", "missing")).toBe("UNAVAILABLE"));
  it("stale + stale -> DEGRADED (stale still carries 0.45 weight)", () =>
    expect(mapSystemHealth("stale", "stale")).toBe("DEGRADED"));

  // Zero-denominator cases: health follows the effective denominator, not a
  // count of `missing` flags.
  it("w_v=1 w_t=0, vision missing, telemetry fresh -> UNAVAILABLE", () =>
    expect(mapSystemHealth("missing", "fresh", 1.0, 0.0)).toBe("UNAVAILABLE"));
  it("w_v=0 w_t=1, vision fresh, telemetry missing -> UNAVAILABLE", () =>
    expect(mapSystemHealth("fresh", "missing", 0.0, 1.0)).toBe("UNAVAILABLE"));
  it("w_v=1 w_t=0, vision fresh, telemetry missing -> DEGRADED (available)", () =>
    expect(mapSystemHealth("fresh", "missing", 1.0, 0.0)).toBe("DEGRADED"));
  it("zero weight with both branches fresh -> FULL (weights never demote)", () =>
    expect(mapSystemHealth("fresh", "fresh", 1.0, 0.0)).toBe("FULL"));
  it("both weights zero -> UNAVAILABLE even when both fresh", () =>
    expect(mapSystemHealth("fresh", "fresh", 0.0, 0.0)).toBe("UNAVAILABLE"));
});

describe("determineEvidenceType (dominant-evidence decision tree)", () => {
  const base = { riskScore: 70, systemHealth: "FULL" as const, thresholdLow: 30 };

  it("equal branches -> Combined evidence", () => {
    expect(
      determineEvidenceType({ ...base, pDistraction: 0.5, pTelemetry: 0.5 }),
    ).toBe("Combined evidence");
  });
  it("vision much higher -> Vision-dominant", () => {
    expect(
      determineEvidenceType({ ...base, pDistraction: 0.8, pTelemetry: 0.2 }),
    ).toBe("Vision-dominant");
  });
  it("telemetry much higher -> Telemetry-dominant", () => {
    expect(
      determineEvidenceType({ ...base, pDistraction: 0.2, pTelemetry: 0.8 }),
    ).toBe("Telemetry-dominant");
  });
  it("degraded system -> Partial evidence", () => {
    expect(
      determineEvidenceType({
        ...base,
        systemHealth: "DEGRADED",
        pDistraction: 0.8,
        pTelemetry: 0.2,
      }),
    ).toBe("Partial evidence");
  });
  it("below low threshold -> Low observed risk", () => {
    expect(
      determineEvidenceType({
        ...base,
        riskScore: 20,
        pDistraction: 0.1,
        pTelemetry: 0.1,
      }),
    ).toBe("Low observed risk");
  });
});

describe("asPercent: integer percent, half-up on the decimal digits", () => {
  it("breaks the exact decimal ties that Math.round(v * 100) gets wrong", () => {
    // The trap: each product lands just under the tie in binary.
    expect(Math.round(0.285 * 100)).toBe(28);
    expect(Math.round(0.565 * 100)).toBe(56);
    expect(Math.round(0.145 * 100)).toBe(14);
    expect(asPercent(0.285)).toBe("29%");
    expect(asPercent(0.565)).toBe("57%");
    expect(asPercent(0.145)).toBe("15%");
  });

  it("leaves values that are not on a tie alone", () => {
    expect(asPercent(0)).toBe("0%");
    expect(asPercent(1)).toBe("100%");
    expect(asPercent(0.07)).toBe("7%");
    expect(asPercent(0.4)).toBe("40%");
    expect(asPercent(0.284)).toBe("28%");
    expect(asPercent(0.286)).toBe("29%");
  });
});

describe("the stored explanation text rounds its percentages half-up", () => {
  const freshWindow = (pD: number, pT: number): PreparedSessionWindow => ({
    timestamp: "2026-01-01T12:00:00.000Z",
    P_distraction: pD,
    P_telemetry_anomaly: pT,
    vision_status: "fresh",
    telemetry_status: "fresh",
    visual_top_classes: [],
    telemetry_behavior_classes: [],
    telemetry_feature_contributions: [],
    telemetry_features: null,
    latency_ms: 0,
  });

  it("Vision-dominant text: 0.565 -> 57% and 0.285 -> 29%", () => {
    const record = buildRiskUpdate(
      freshWindow(0.565, 0.285),
      "s",
      DEFAULT_CONFIG,
      undefined,
      1,
    );
    expect(record.DominantEvidence).toBe("Vision-dominant");
    expect(record.explanation).toContain("P_distraction (57%)");
    expect(record.explanation).toContain("P_telemetry_anomaly (29%)");
  });

  it("Telemetry-dominant text: 0.565 -> 57% and 0.145 -> 15%", () => {
    const record = buildRiskUpdate(
      freshWindow(0.145, 0.565),
      "s",
      DEFAULT_CONFIG,
      undefined,
      1,
    );
    expect(record.DominantEvidence).toBe("Telemetry-dominant");
    expect(record.explanation).toContain("P_telemetry_anomaly (57%)");
    expect(record.explanation).toContain("P_distraction (15%)");
  });
});
