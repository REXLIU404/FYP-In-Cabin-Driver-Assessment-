import { describe, expect, it } from "vitest";
import casesJson from "../fixtures/ema_parity_vectors.json";
import { DEFAULT_CONFIG, buildRiskUpdate } from "./riskLogic";
import type {
  FreshnessStatus,
  PreparedSessionWindow,
  RiskUpdate,
  SystemHealth,
} from "./types";

/**
 * UT-EMA-PARITY-01 - TypeScript half.
 *
 * `ai/fixtures/ema_parity_vectors.json` is the shared oracle; the Python half is
 * `test_ut_ema_parity_01_*` in backend/tests/test_temporal_contract.py, which runs
 * the SAME input sequences through `run_inference`. The expectations were derived
 * independently, with exact decimal arithmetic and no implementation code, so the
 * two suites agreeing with the file means they agree with each other.
 *
 * It pins the three places where the ports used to disagree about P_distraction:
 *   1. the first window - the backend emits provider precision, this port rounded;
 *   2. the first fresh window after a stale / missing / unavailable one - the
 *      backend re-seeds, this port kept smoothing from the stale window's value;
 *   3. a run of consecutive fresh windows - plain EMA, rounded half up to 3 dp.
 * plus two rounding ties and the (unrounded) telemetry probability. Python is the
 * canonical producer, so this port was changed to match it.
 */
interface ParityCase {
  id: string;
  description: string;
  config: {
    ema_alpha: number;
    weight_vision: number;
    weight_telemetry: number;
  };
  windows: Array<{
    vision_status: FreshnessStatus;
    P_distraction: number;
    telemetry_status: FreshnessStatus;
    P_telemetry_anomaly: number;
  }>;
  expect: Array<{
    P_distraction: number;
    P_telemetry_anomaly: number;
    assessment_available: boolean;
    RiskScore: number | null;
    SystemHealth: SystemHealth;
  }>;
}

const cases = casesJson as unknown as ParityCase[];

const toWindow = (
  w: ParityCase["windows"][number],
  index: number,
): PreparedSessionWindow => ({
  timestamp: new Date(Date.UTC(2026, 0, 1, 12, 0, index)).toISOString(),
  P_distraction: w.P_distraction,
  P_telemetry_anomaly: w.P_telemetry_anomaly,
  vision_status: w.vision_status,
  telemetry_status: w.telemetry_status,
  visual_top_classes: [],
  telemetry_behavior_classes: [],
  telemetry_feature_contributions: [],
  telemetry_features: null,
  latency_ms: 0,
});

describe("UT-EMA-PARITY-01 (TypeScript half; shared oracle ema_parity_vectors.json)", () => {
  it("covers the first window, the first fresh window after a stale one, and a fresh run", () => {
    const ids = cases.map((c) => c.id);
    expect(ids).toContain("first-window-keeps-provider-precision");
    expect(ids).toContain("first-fresh-after-stale-reseeds");
    expect(ids).toContain("consecutive-fresh-run");
    expect(new Set(ids).size).toBe(ids.length);
  });

  describe.each(cases)("$id", (c) => {
    it("emits the oracle's value for every window", () => {
      const config = {
        ...DEFAULT_CONFIG,
        emaAlpha: c.config.ema_alpha,
        weightVision: c.config.weight_vision,
        weightTelemetry: c.config.weight_telemetry,
      };
      let previous: RiskUpdate | undefined;
      c.windows.forEach((w, index) => {
        const record = buildRiskUpdate(
          toWindow(w, index),
          "parity",
          config,
          previous,
          index + 1,
        );
        const want = c.expect[index];
        expect(
          {
            P_distraction: record.P_distraction,
            P_telemetry_anomaly: record.P_telemetry_anomaly,
            assessment_available: record.assessment_available,
            RiskScore: record.RiskScore,
            SystemHealth: record.SystemHealth,
          },
          `${c.id} window ${index + 1}`,
        ).toEqual(want);
        previous = record;
      });
    });
  });
});
