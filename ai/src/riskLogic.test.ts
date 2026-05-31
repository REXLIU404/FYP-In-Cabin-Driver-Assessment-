import { describe, expect, it } from "vitest";
import {
  computeRiskScore,
  mapRiskLevel,
  mapSystemHealth,
} from "./riskLogic";
import { determineEvidenceType } from "./evidence";

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

  it("both modalities missing -> 0 (no evidence)", () => {
    expect(computeRiskScore(0.8, 0.9, 0.5, 0.5, "missing", "missing")).toBe(0);
  });
});

describe("mapSystemHealth", () => {
  it("both fresh -> FULL", () =>
    expect(mapSystemHealth("fresh", "fresh")).toBe("FULL"));
  it("one stale/missing -> DEGRADED", () =>
    expect(mapSystemHealth("fresh", "missing")).toBe("DEGRADED"));
  it("both missing -> UNAVAILABLE", () =>
    expect(mapSystemHealth("missing", "missing")).toBe("UNAVAILABLE"));
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
