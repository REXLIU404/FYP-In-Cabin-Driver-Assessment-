import { describe, expect, it } from "vitest";
import vectorsJson from "../fixtures/fusion_vectors.json";
import {
  DEFAULT_CONFIG,
  buildRiskUpdate,
  computeRiskScore,
  determineDominantEvidence,
  mapRiskLevel,
  mapSystemHealth,
  roundHalfUp,
} from "./riskLogic";
import type {
  DominantEvidence,
  FreshnessStatus,
  PreparedSessionWindow,
  RiskLevel,
  SystemHealth,
} from "./types";

/**
 * Cross-language numeric oracle.
 *
 * `ai/fixtures/fusion_vectors.json` is the single source of truth for the 25
 * verified fusion vectors; `backend/tests/test_fusion_vectors.py` reads the same
 * file. Every expectation below comes from that JSON only - no constant is
 * imported from the implementation to build an expectation, so a drift in
 * either port turns exactly one side red.
 *
 * The thresholds (30 / 60) and the evidence gap (0.15) are hard-coded literals
 * from the contract, not imports.
 */
interface FusionVector {
  id: string;
  pd: number;
  pt: number;
  wv: number;
  wt: number;
  vision: FreshnessStatus;
  telemetry: FreshnessStatus;
  expect: {
    available: boolean;
    score: number | null;
    level: RiskLevel | null;
    health: SystemHealth;
    dominant: DominantEvidence | null;
  };
}

const vectors = vectorsJson as unknown as FusionVector[];

const THRESHOLD_LOW = 30;
const THRESHOLD_HIGH = 60;
const EVIDENCE_GAP = 0.15;

describe("fusion_vectors.json shape (contract shared with the Python port)", () => {
  it("holds the 25 verified rows with unique ids", () => {
    expect(vectors).toHaveLength(25);
    expect(new Set(vectors.map((v) => v.id)).size).toBe(25);
  });

  it("every row carries the full field set", () => {
    for (const v of vectors) {
      expect(Object.keys(v).sort()).toEqual(
        ["expect", "id", "pd", "pt", "telemetry", "vision", "wt", "wv"].sort(),
      );
      expect(Object.keys(v.expect).sort()).toEqual(
        ["available", "dominant", "health", "level", "score"].sort(),
      );
    }
  });

  it("an unavailable row nulls score/level/dominant together and only then", () => {
    for (const v of vectors) {
      const e = v.expect;
      expect(e.available).toBe(e.score !== null);
      expect(e.available).toBe(e.level !== null);
      expect(e.available).toBe(e.dominant !== null);
      expect(e.available).toBe(e.health !== "UNAVAILABLE");
    }
  });
});

describe.each(vectors)("fusion vector $id", (v) => {
  const score = computeRiskScore(v.pd, v.pt, v.wv, v.wt, v.vision, v.telemetry);

  it("computeRiskScore", () => {
    expect(score).toBe(v.expect.score);
  });

  it("mapRiskLevel", () => {
    expect(mapRiskLevel(score, THRESHOLD_LOW, THRESHOLD_HIGH)).toBe(
      v.expect.level,
    );
  });

  it("mapSystemHealth", () => {
    expect(mapSystemHealth(v.vision, v.telemetry, v.wv, v.wt)).toBe(
      v.expect.health,
    );
  });

  it("determineDominantEvidence", () => {
    expect(
      determineDominantEvidence(
        v.pd,
        v.pt,
        v.vision,
        v.telemetry,
        score,
        THRESHOLD_LOW,
        EVIDENCE_GAP,
        v.wv,
        v.wt,
      ),
    ).toBe(v.expect.dominant);
  });

  it("buildRiskUpdate agrees with the fixture end to end", () => {
    const window: PreparedSessionWindow = {
      timestamp: "2026-01-01T00:00:00.000Z",
      P_distraction: v.pd,
      P_telemetry_anomaly: v.pt,
      vision_status: v.vision,
      telemetry_status: v.telemetry,
      visual_top_classes: [],
      telemetry_behavior_classes: [],
      telemetry_feature_contributions: [],
      telemetry_features: null,
      latency_ms: 0,
    };
    const record = buildRiskUpdate(
      window,
      "fixture",
      { ...DEFAULT_CONFIG, weightVision: v.wv, weightTelemetry: v.wt },
      undefined,
      0,
    );

    expect(record.assessment_available).toBe(v.expect.available);
    expect(record.RiskScore).toBe(v.expect.score);
    expect(record.RiskLevel).toBe(v.expect.level);
    expect(record.SystemHealth).toBe(v.expect.health);
    expect(record.DominantEvidence).toBe(v.expect.dominant);
    // AlertSeverity is null exactly when the assessment is unavailable.
    expect(record.AlertSeverity === null).toBe(!v.expect.available);
  });
});

describe("rounding order is load-bearing (F-T5)", () => {
  // The exact fused value is 29.951: below 30 before rounding, 30 after. The
  // level must be mapped from the ROUNDED score, so the row lands in Medium.
  // Mapping the unrounded value would give Low / "Low observed risk".
  const t5 = vectors.find((v) => v.id === "F-T5");

  it("fixture row F-T5 exists and expects Medium at exactly 30", () => {
    expect(t5).toBeDefined();
    expect(t5?.expect.score).toBe(30);
    expect(t5?.expect.level).toBe("Medium");
    expect(t5?.expect.dominant).toBe("Combined evidence");
  });

  it("the unrounded value would have been Low (so the row has teeth)", () => {
    const unrounded = ((0.5 * 0.29951 + 0.5 * 0.29951) / 1) * 100;
    expect(unrounded).toBeLessThan(THRESHOLD_LOW);
  });
});

describe("rounding mode: half up on the decimal representation (F-R1..F-R4)", () => {
  // Exact decimal ties. Python's round() gave 84.2 / 29.9 / 22.2 for these and the
  // old toFixed gave 29.9 for the 29.95 pair, so each row separates the ports.
  // The raw score is hard-coded so a change in how it is computed cannot hide.
  const ties: Record<
    string,
    { raw: number; bankers: number; expected: number }
  > = {
    "F-R1": { raw: 84.25, bankers: 84.2, expected: 84.3 },
    "F-R2": { raw: 29.95, bankers: 29.9, expected: 30 },
    "F-R3": { raw: 29.95, bankers: 29.9, expected: 30 },
    "F-R4": { raw: 22.25, bankers: 22.2, expected: 22.3 },
  };

  it.each(Object.keys(ties))("%s is an exact tie that rounds up", (id) => {
    const v = vectors.find((row) => row.id === id);
    expect(v).toBeDefined();
    if (!v) return;
    const { raw, bankers, expected } = ties[id];
    const unrounded = ((v.wv * v.pd + v.wt * v.pt) / (v.wv + v.wt)) * 100;
    expect(unrounded).toBe(raw);
    expect(bankers).not.toBe(expected);
    expect(
      computeRiskScore(v.pd, v.pt, v.wv, v.wt, v.vision, v.telemetry),
    ).toBe(expected);
    expect(expected).toBe(v.expect.score);
  });

  it("a tie can change the level: 29.95 is Medium, not Low (F-R2)", () => {
    expect(computeRiskScore(0.2995, 0.2995)).toBe(30);
    expect(mapRiskLevel(30, THRESHOLD_LOW, THRESHOLD_HIGH)).toBe("Medium");
  });

  it.each([
    [84.25, 1, 84.3],
    [0.125, 2, 0.13],
    [2.675, 2, 2.68],
    [1.005, 2, 1.01],
    [0.4125, 3, 0.413],
    [0.4124999, 3, 0.412],
    [0.0005, 3, 0.001],
    [0.0004999, 3, 0],
    [1e-7, 3, 0],
    [5e-7, 6, 0.000001],
    [0, 1, 0],
    [100, 1, 100],
    // 17 digits: parsing 27.849999999999998e1 lands exactly on the tie (278.5).
    [27.849999999999998, 1, 27.8],
  ])("roundHalfUp(%s, %i) = %s", (value, places, expected) => {
    expect(roundHalfUp(value, places)).toBe(expected);
  });
});
