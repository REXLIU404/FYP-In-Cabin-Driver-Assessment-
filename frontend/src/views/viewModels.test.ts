import { describe, expect, it } from "vitest";

import { DEFAULT_CONFIG } from "../../../ai/src/riskLogic";
import { makeRecord } from "../testing/records";
import { alertBannerClass } from "../utils/display";
import { buildExplanationModel } from "./explanationModel";
import { buildLiveMonitorModel } from "./liveMonitorModel";

describe("buildLiveMonitorModel: SystemHealth is the record's own value", () => {
  const assessed = makeRecord("fresh", "fresh", 1);
  const unavailable = makeRecord("missing", "missing", 2);

  it("an assessed but OLD record is `stale` - its health is not rewritten to UNAVAILABLE", () => {
    const model = buildLiveMonitorModel(assessed, true, 30);
    expect(model.displayState).toBe("stale");
    expect(model.systemHealth).toBe("FULL");
    expect(model.systemHealth).toBe(assessed.SystemHealth);
    expect(model.resultAge).toBe("stale");
  });

  it("an OLD record's freshness is not rewritten to `stale`", () => {
    const model = buildLiveMonitorModel(assessed, true, 30);
    expect(model.vision).toBe("fresh");
    expect(model.telemetry).toBe("fresh");
    const partial = makeRecord("fresh", "missing", 3);
    expect(buildLiveMonitorModel(partial, true, 30).telemetry).toBe("missing");
    expect(buildLiveMonitorModel(partial, true, 30).vision).toBe("fresh");
  });

  it("an unassessed record is `unavailable`, with its own UNAVAILABLE health, old or not", () => {
    for (const stale of [false, true]) {
      const model = buildLiveMonitorModel(unavailable, stale, 30);
      expect(model.displayState).toBe("unavailable");
      expect(model.systemHealth).toBe("UNAVAILABLE");
      expect(model.evidenceType).toBeNull();
    }
  });

  it("a current assessed record is `available` and reports its stored evidence type", () => {
    const model = buildLiveMonitorModel(assessed, false, 30);
    expect(model.displayState).toBe("available");
    expect(model.resultAge).toBe("current");
    expect(model.evidenceType).toBe(assessed.DominantEvidence);
  });

  it("available / stale / unavailable are three distinct states", () => {
    const states = new Set([
      buildLiveMonitorModel(assessed, false, 30).displayState,
      buildLiveMonitorModel(assessed, true, 30).displayState,
      buildLiveMonitorModel(unavailable, false, 30).displayState,
    ]);
    expect(states.size).toBe(3);
  });
});

describe("alertBannerClass: a null severity never becomes `alert-banner--null`", () => {
  const normal = makeRecord("fresh", "fresh", 1, {
    P_distraction: 0.05,
    P_telemetry_anomaly: 0.05,
  });
  const unavailable = makeRecord("missing", "missing", 2);

  it("an unassessed record gets the explicit unavailable banner, old or not", () => {
    expect(alertBannerClass(unavailable, false)).toContain(
      "alert-banner--unavailable",
    );
    expect(alertBannerClass(unavailable, true)).toContain(
      "alert-banner--unavailable",
    );
    expect(alertBannerClass(unavailable, false)).not.toContain("null");
  });

  it("an assessed record is tinted by its own AlertSeverity", () => {
    expect(normal.AlertSeverity).toBe("NORMAL");
    expect(alertBannerClass(normal, false)).toBe(
      "alert-banner alert-banner--NORMAL",
    );
  });

  it("an assessed but old record is the stale banner", () => {
    expect(alertBannerClass(normal, true)).toBe("alert-banner runtime-warning");
  });

  it("even a malformed `available` record with a null severity cannot produce --null", () => {
    const malformed = { ...normal, AlertSeverity: null };
    expect(alertBannerClass(malformed, false)).not.toContain("null");
  });
});

describe("buildExplanationModel: an unassessed window has nothing to explain", () => {
  const unavailable = makeRecord("missing", "missing", 1);

  it("no contributions, no evidence type - so no `= RiskScore 0.0 / 100` equation", () => {
    const model = buildExplanationModel(unavailable, DEFAULT_CONFIG);
    expect(model.unavailable).toBe(true);
    expect(model.contributions).toBeNull();
    expect(model.evidenceType).toBeNull();
  });

  it("a window made unavailable by ZERO WEIGHTS gets no split under a different weight pair", () => {
    // Produced with w_v=1, w_t=0: vision is missing and telemetry carries no
    // weight, so the denominator is 0 and the window has no score. Viewed under
    // the default 0.5/0.5 (no saved fusion_config), a bare
    // computeRiskContributions would still return a non-null split for it.
    const zeroWeights = makeRecord("missing", "fresh", 2);
    const recordedWith = {
      ...zeroWeights,
      assessment_available: false as const,
    };
    const model = buildExplanationModel(recordedWith, DEFAULT_CONFIG);
    expect(model.contributions).toBeNull();
  });

  it("a window under a DIFFERENT weight pair gets no split that contradicts its stored score", () => {
    // Produced under the default 0.5/0.5 (RiskScore stored as such); shown with
    // the weights now in scope set to 1/0, the split would total 60 next to a
    // stored 62.5. Printing "60 + 0 = RiskScore 62.5" would be a contradiction.
    const assessed = makeRecord("fresh", "stale", 5, {
      P_distraction: 0.6,
      P_telemetry_anomaly: 0.68,
    });
    expect(assessed.RiskScore).toBe(62.5);
    const model = buildExplanationModel(assessed, {
      ...DEFAULT_CONFIG,
      weightVision: 1,
      weightTelemetry: 0,
    });
    expect(model.unavailable).toBe(false);
    expect(model.contributions).toBeNull();
    expect(model.contributionIssue).toBe("weights_differ");
    // The same record under its own weights reconciles.
    expect(
      buildExplanationModel(assessed, DEFAULT_CONFIG).contributions?.total,
    ).toBe(62.5);
  });

  it("weights that leave no evidence to split are reported as such", () => {
    // Vision fresh, telemetry missing; viewed under w_v = 0 the denominator is 0.
    const assessed = makeRecord("fresh", "missing", 6);
    expect(assessed.assessment_available).toBe(true);
    const model = buildExplanationModel(assessed, {
      ...DEFAULT_CONFIG,
      weightVision: 0,
      weightTelemetry: 1,
    });
    expect(model.contributions).toBeNull();
    expect(model.contributionIssue).toBe("no_evidence_under_weights");
  });

  it("an unassessed window reports why there is no split", () => {
    expect(
      buildExplanationModel(unavailable, DEFAULT_CONFIG).contributionIssue,
    ).toBe("no_assessment");
  });

  it("an assessed window gets a split whose total is the stored RiskScore", () => {
    const assessed = makeRecord("fresh", "fresh", 3);
    const model = buildExplanationModel(assessed, DEFAULT_CONFIG);
    expect(model.unavailable).toBe(false);
    expect(model.contributions).not.toBeNull();
    expect(model.contributionIssue).toBeNull();
    expect(model.contributions?.total).toBe(assessed.RiskScore);
    expect(model.evidenceType).toBe(assessed.DominantEvidence);
  });

  it("evidence type is the record's stored value, even when recomputing would disagree", () => {
    const assessed = {
      ...makeRecord("fresh", "fresh", 4),
      DominantEvidence: "Telemetry-dominant" as const,
    };
    expect(buildExplanationModel(assessed, DEFAULT_CONFIG).evidenceType).toBe(
      "Telemetry-dominant",
    );
  });
});
