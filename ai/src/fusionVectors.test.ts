import { describe, expect, it } from "vitest";
import vectorsJson from "../fixtures/fusion_vectors.json";
import {
  DEFAULT_CONFIG,
  buildRiskUpdate,
  computeRiskScore,
  determineDominantEvidence,
  mapRiskLevel,
  mapSystemHealth,
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
 * `ai/fixtures/fusion_vectors.json` is the single source of truth for the 21
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
  it("holds the 21 verified rows with unique ids", () => {
    expect(vectors).toHaveLength(21);
    expect(new Set(vectors.map((v) => v.id)).size).toBe(21);
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
