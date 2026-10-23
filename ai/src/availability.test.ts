import { describe, expect, it } from "vitest";
import {
  assertAvailabilityInvariant,
  branchExpiry,
  deriveAssessmentAvailable,
  describeBranchStatus,
  effectiveFusionDenominator,
  getDisplayState,
  isAssessmentAvailable,
  normalizeRiskUpdate,
  type StoredRiskUpdate,
} from "./availability";
import {
  DEFAULT_CONFIG,
  buildRiskUpdate,
  computeRiskContributions,
  computeRiskScore,
  mapAlertSeverity,
  mapRiskLevel,
  mapSystemHealth,
} from "./riskLogic";
import {
  determineEvidenceType,
  getActiveInputSummary,
  getEvidenceType,
  getMatchedEvidenceRule,
  getRelativeEvidence,
} from "./evidence";
import type {
  FreshnessStatus,
  PreparedSessionWindow,
  RiskUpdate,
} from "./types";
// Source text of the components the grep-style guards below inspect. `?raw` is
// resolved by Vite at test time, so no filesystem API (and no @types/node) is
// needed.
import alertBannerSource from "../../frontend/src/components/AlertBanner.tsx?raw";
import configurationViewSource from "../../frontend/src/views/ConfigurationView.tsx?raw";
import explanationViewSource from "../../frontend/src/views/ExplanationView.tsx?raw";
import exportSource from "../../frontend/src/utils/export.ts?raw";
import formatSource from "../../frontend/src/utils/format.ts?raw";
import liveMonitorModelSource from "../../frontend/src/views/liveMonitorModel.ts?raw";
import liveMonitorSource from "../../frontend/src/views/LiveMonitor.tsx?raw";
import modalityCardSource from "../../frontend/src/components/ModalityCard.tsx?raw";
import riskTrendsSource from "../../frontend/src/views/RiskTrends.tsx?raw";
import scoreGaugeSource from "../../frontend/src/components/ScoreGauge.tsx?raw";
import signalInspectorSource from "../../frontend/src/views/SignalInspector.tsx?raw";
import trendSeriesSource from "../../frontend/src/components/trendSeries.ts?raw";

const STATUSES: FreshnessStatus[] = ["fresh", "stale", "missing"];
const WEIGHT_PAIRS: Array<[number, number]> = [
  [0.5, 0.5],
  [1.0, 0.0],
  [0.0, 1.0],
];

// Freshness weights restated here on purpose: the expected availability below is
// derived from the contract (fresh 1.0 / stale 0.45 / missing 0.0), not read
// back from the implementation under test.
const CONTRACT_FRESHNESS_WEIGHT: Record<FreshnessStatus, number> = {
  fresh: 1.0,
  stale: 0.45,
  missing: 0.0,
};

const makeRecord = (
  vision: FreshnessStatus,
  telemetry: FreshnessStatus,
  wv = 0.5,
  wt = 0.5,
): RiskUpdate => {
  const window: PreparedSessionWindow = {
    timestamp: "2026-01-01T00:00:00.000Z",
    P_distraction: 0.1,
    P_telemetry_anomaly: 0.9,
    vision_status: vision,
    telemetry_status: telemetry,
    visual_top_classes: [],
    telemetry_behavior_classes: [],
    telemetry_feature_contributions: [],
    telemetry_features: null,
    latency_ms: 0,
  };
  return buildRiskUpdate(
    window,
    "avail",
    { ...DEFAULT_CONFIG, weightVision: wv, weightTelemetry: wt },
    undefined,
    0,
  );
};

describe("UT-AVAIL-01: availability iff RiskScore present iff health != UNAVAILABLE", () => {
  const cases = STATUSES.flatMap((vision) =>
    STATUSES.flatMap((telemetry) =>
      WEIGHT_PAIRS.map(([wv, wt]) => ({ vision, telemetry, wv, wt })),
    ),
  );

  it("enumerates 9 freshness combinations x 3 weight pairs = 27 cases", () => {
    expect(cases).toHaveLength(27);
  });

  it.each(cases)(
    "vision=$vision telemetry=$telemetry weights=($wv, $wt)",
    ({ vision, telemetry, wv, wt }) => {
      const r = makeRecord(vision, telemetry, wv, wt);
      const denominator =
        wv * CONTRACT_FRESHNESS_WEIGHT[vision] +
        wt * CONTRACT_FRESHNESS_WEIGHT[telemetry];
      const expectedAvailable = denominator > 1e-9;

      // Two separate equalities: a chained `a === b === c` would compare a
      // boolean against c and silently pass or fail for the wrong reason.
      expect(isAssessmentAvailable(r)).toBe(r.RiskScore !== null);
      expect(isAssessmentAvailable(r)).toBe(r.SystemHealth !== "UNAVAILABLE");
      // ... and the derived value must match the contract's own arithmetic.
      expect(isAssessmentAvailable(r)).toBe(expectedAvailable);
      expect(() => assertAvailabilityInvariant(r)).not.toThrow();

      if (!expectedAvailable) {
        expect(r.RiskScore).toBeNull();
        expect(r.RiskLevel).toBeNull();
        expect(r.DominantEvidence).toBeNull();
        expect(r.AlertSeverity).toBeNull();
        expect(r.SystemHealth).toBe("UNAVAILABLE");
      } else {
        expect(r.RiskScore).not.toBeNull();
        expect(r.RiskLevel).not.toBeNull();
        expect(r.DominantEvidence).not.toBeNull();
        expect(r.AlertSeverity).not.toBeNull();
        expect(r.SystemHealth).not.toBe("UNAVAILABLE");
      }
    },
  );
});

describe("effectiveFusionDenominator", () => {
  it("applies fresh 1.0 / stale 0.45 / missing 0.0 to the weights", () => {
    expect(effectiveFusionDenominator(0.5, 0.5, "fresh", "fresh")).toEqual({
      effVision: 0.5,
      effTelemetry: 0.5,
      denominator: 1,
    });
    const stale = effectiveFusionDenominator(0.6, 0.4, "stale", "fresh");
    expect(stale.effVision).toBeCloseTo(0.27, 12);
    expect(stale.effTelemetry).toBe(0.4);
    expect(stale.denominator).toBeCloseTo(0.67, 12);
    expect(
      effectiveFusionDenominator(0.5, 0.5, "missing", "missing").denominator,
    ).toBe(0);
  });

  it("a branch with zero weight contributes nothing even when fresh", () => {
    expect(
      effectiveFusionDenominator(1.0, 0.0, "missing", "fresh").denominator,
    ).toBe(0);
  });
});

describe("zero detection uses FUSION_EPSILON, not a literal === 0", () => {
  it("a denominator of exactly 1e-9 is unavailable (<=)", () => {
    expect(computeRiskScore(0.5, 0.5, 1e-9, 0, "fresh", "fresh")).toBeNull();
    expect(mapSystemHealth("fresh", "fresh", 1e-9, 0)).toBe("UNAVAILABLE");
  });

  it("a denominator just above 1e-9 is available", () => {
    expect(computeRiskScore(0.5, 0.5, 1.1e-9, 0, "fresh", "fresh")).toBe(50);
    expect(mapSystemHealth("fresh", "fresh", 1.1e-9, 0)).toBe("FULL");
  });

  it("near-zero (non-literal-zero) weights cannot bypass the contract", () => {
    // 1e-10 !== 0, so a `=== 0` test would divide by ~1e-10 and report a score.
    const r = makeRecord("fresh", "missing", 1e-10, 1 - 1e-10);
    expect(r.assessment_available).toBe(false);
    expect(r.RiskScore).toBeNull();
    expect(r.SystemHealth).toBe("UNAVAILABLE");
  });
});

describe("zero-weight boundary (fixture F-Z3): FULL vs DEGRADED looks at freshness only", () => {
  it("w_t = 0 with telemetry missing and vision fresh is AVAILABLE and DEGRADED", () => {
    const r = makeRecord("fresh", "missing", 1.0, 0.0);
    expect(r.assessment_available).toBe(true);
    expect(r.RiskScore).toBe(10);
    expect(r.SystemHealth).toBe("DEGRADED");
    expect(r.DominantEvidence).toBe("Partial evidence");
  });

  it("w_t = 0 with both branches fresh is FULL (weights never demote health)", () => {
    const r = makeRecord("fresh", "fresh", 1.0, 0.0);
    expect(r.assessment_available).toBe(true);
    expect(r.SystemHealth).toBe("FULL");
  });
});

describe("assertAvailabilityInvariant rejects every violation", () => {
  const ok = makeRecord("fresh", "fresh");
  const unavailable = makeRecord("missing", "missing");

  it("accepts a consistent available and a consistent unavailable record", () => {
    expect(() => assertAvailabilityInvariant(ok)).not.toThrow();
    expect(() => assertAvailabilityInvariant(unavailable)).not.toThrow();
  });

  it("available flag true but RiskScore null", () => {
    expect(() =>
      assertAvailabilityInvariant({ ...ok, RiskScore: null }),
    ).toThrow(/RiskScore/);
  });

  it("available flag false but RiskScore present", () => {
    expect(() =>
      assertAvailabilityInvariant({
        ...ok,
        assessment_available: false,
        SystemHealth: "UNAVAILABLE",
      }),
    ).toThrow(/RiskScore/);
  });

  it("available flag true but SystemHealth UNAVAILABLE", () => {
    expect(() =>
      assertAvailabilityInvariant({ ...ok, SystemHealth: "UNAVAILABLE" }),
    ).toThrow(/SystemHealth/);
  });

  it("available flag false but SystemHealth not UNAVAILABLE", () => {
    expect(() =>
      assertAvailabilityInvariant({ ...unavailable, SystemHealth: "DEGRADED" }),
    ).toThrow(/SystemHealth/);
  });

  it.each(["RiskLevel", "DominantEvidence", "AlertSeverity"] as const)(
    "unavailable record with a non-null %s",
    (field) => {
      const bad = { ...unavailable, [field]: "Low" } as unknown as RiskUpdate;
      expect(() => assertAvailabilityInvariant(bad)).toThrow(new RegExp(field));
    },
  );

  it.each(["RiskLevel", "DominantEvidence", "AlertSeverity"] as const)(
    "available record with a null %s",
    (field) => {
      expect(() =>
        assertAvailabilityInvariant({ ...ok, [field]: null }),
      ).toThrow(new RegExp(field));
    },
  );

  it("the classic fabricated safe reading 0 / Low / NORMAL / UNAVAILABLE", () => {
    const fabricated = {
      ...unavailable,
      RiskScore: 0,
      RiskLevel: "Low",
      DominantEvidence: "Partial evidence",
      AlertSeverity: "NORMAL",
    } as unknown as RiskUpdate;
    expect(() => assertAvailabilityInvariant(fabricated)).toThrow();
  });

  it("a record without the assessment_available flag is rejected", () => {
    const legacy = { ...ok } as Partial<RiskUpdate>;
    delete legacy.assessment_available;
    expect(() => assertAvailabilityInvariant(legacy as RiskUpdate)).toThrow(
      /assessment_available/,
    );
  });
});

describe("getDisplayState: available / stale / unavailable are three states", () => {
  const ok = makeRecord("fresh", "fresh");
  const unavailable = makeRecord("missing", "missing");

  it("available record, current -> available", () =>
    expect(getDisplayState(ok, { stale: false })).toBe("available"));
  it("available record, old -> stale", () =>
    expect(getDisplayState(ok, { stale: true })).toBe("stale"));
  it("unavailable record -> unavailable, whether or not it is old", () => {
    expect(getDisplayState(unavailable, { stale: false })).toBe("unavailable");
    expect(getDisplayState(unavailable, { stale: true })).toBe("unavailable");
  });
});

describe("null never reaches a relational operator (null < 30 is true in JS)", () => {
  it("mapRiskLevel(null) is null, not Low", () => {
    expect(mapRiskLevel(null)).toBeNull();
    expect(mapRiskLevel(null, 30, 60)).toBeNull();
  });

  it("mapAlertSeverity(null) is null, not NORMAL", () => {
    expect(mapAlertSeverity(null)).toBeNull();
  });

  it("determineEvidenceType with a null score is null, not 'Low observed risk'", () => {
    for (const systemHealth of ["FULL", "DEGRADED", "UNAVAILABLE"] as const) {
      expect(
        determineEvidenceType({
          pDistraction: 0.1,
          pTelemetry: 0.1,
          riskScore: null,
          systemHealth,
          thresholdLow: 30,
        }),
      ).toBeNull();
    }
  });

  it("UNAVAILABLE health with a (corrupt) numeric score is still null", () => {
    expect(
      determineEvidenceType({
        pDistraction: 0.1,
        pTelemetry: 0.1,
        riskScore: 5,
        systemHealth: "UNAVAILABLE",
        thresholdLow: 30,
      }),
    ).toBeNull();
  });

  it("getEvidenceType on an unavailable record is null", () => {
    expect(getEvidenceType(makeRecord("missing", "missing"), 30)).toBeNull();
  });

  it("getRelativeEvidence does not call an unavailable record 'partial'", () => {
    const text = getRelativeEvidence(makeRecord("missing", "missing"));
    expect(text).not.toMatch(/partial/i);
    expect(text).toMatch(/no usable evidence/i);
  });

  it("getActiveInputSummary still reports the raw freshness states", () => {
    expect(getActiveInputSummary(makeRecord("missing", "missing"))).toBe(
      "Vision missing / Telemetry missing",
    );
  });

  it("getActiveInputSummary says an EXPIRED branch expired, with its age, not 'missing'", () => {
    // Ruling A (D13): expired evidence scores as missing but is not the same thing as no
    // input, and the text for the reader must not pretend it is.
    const record: RiskUpdate = {
      ...makeRecord("missing", "fresh"),
      provenance: {
        vision_expired: true,
        vision_age_s: 30,
        telemetry_expired: false,
        telemetry_age_s: 0,
      },
    };
    expect(getActiveInputSummary(record)).toBe(
      "Vision expired (30 s) / Telemetry fresh",
    );
    // The same statuses with nothing expired keep the plain wording.
    expect(getActiveInputSummary(makeRecord("missing", "fresh"))).toBe(
      "Vision missing / Telemetry fresh",
    );
  });

  it("getMatchedEvidenceRule names the zero-denominator rule for null", () => {
    const rule = getMatchedEvidenceRule(null, 30);
    expect(rule.label).toBe("Unavailable");
    expect(rule.condition).toMatch(/denominator/i);
    expect(rule.condition).not.toMatch(/stale or missing/);
  });

  it("'Partial evidence' keeps its own, different rule text", () => {
    expect(getMatchedEvidenceRule("Partial evidence", 30).condition).toMatch(
      /stale or missing/,
    );
  });
});

describe("computeRiskContributions does not fabricate zero contributions", () => {
  it("zero denominator -> null (not {0, 0, 0})", () => {
    expect(
      computeRiskContributions(0.8, 0.9, 0.5, 0.5, "missing", "missing"),
    ).toBeNull();
    expect(
      computeRiskContributions(0.8, 0.9, 1.0, 0.0, "missing", "fresh"),
    ).toBeNull();
  });

  it("available -> contributions sum to the score", () => {
    const c = computeRiskContributions(0.1, 0.9, 0.5, 0.5, "fresh", "fresh");
    expect(c).toEqual({ vision: 5, telemetry: 45, total: 50 });
  });
});

describe("unavailable explanation names the cause and never mentions a level", () => {
  const LEVEL_WORDS = /\b(low|medium|high|safe|normal)\b/i;

  it("both inputs missing", () => {
    const r = makeRecord("missing", "missing");
    expect(r.explanation).toMatch(/vision/i);
    expect(r.explanation).toMatch(/telemetry/i);
    expect(r.explanation).toMatch(/missing/i);
    expect(r.explanation).not.toMatch(LEVEL_WORDS);
    expect(r.explanation).not.toMatch(/below the low-risk threshold/);
    expect(r.explanation).not.toMatch(/stale or missing/);
  });

  it("vision missing while telemetry carries zero weight", () => {
    const r = makeRecord("missing", "fresh", 1.0, 0.0);
    expect(r.assessment_available).toBe(false);
    expect(r.explanation).toMatch(/vision input is missing/i);
    expect(r.explanation).toMatch(/telemetry .*zero (fusion )?weight/i);
    expect(r.explanation).not.toMatch(LEVEL_WORDS);
  });

  it("telemetry missing while vision carries zero weight", () => {
    const r = makeRecord("fresh", "missing", 0.0, 1.0);
    expect(r.assessment_available).toBe(false);
    expect(r.explanation).toMatch(/telemetry input is missing/i);
    expect(r.explanation).toMatch(/vision .*zero (fusion )?weight/i);
    expect(r.explanation).not.toMatch(LEVEL_WORDS);
  });

  it("an available window keeps its level wording", () => {
    const r = makeRecord("fresh", "fresh");
    expect(r.explanation).toMatch(/medium risk output/);
  });
});

describe("deriveAssessmentAvailable: the legacy-record predicate", () => {
  // A record stored before the nullable contract has no `assessment_available`.
  // The two tempting one-liners both fail on it:
  //   !record.assessment_available        -> every legacy row "unavailable"
  //   record.assessment_available === false -> every legacy row "available"
  const legacy = (
    RiskScore: number | null,
    SystemHealth: "FULL" | "DEGRADED" | "UNAVAILABLE",
  ) => ({ RiskScore, SystemHealth });

  it("a legacy assessed row (42.0 / DEGRADED) is available", () =>
    expect(deriveAssessmentAvailable(legacy(42, "DEGRADED"))).toBe(true));
  it("a legacy genuine zero (0 / FULL) is available", () =>
    expect(deriveAssessmentAvailable(legacy(0, "FULL"))).toBe(true));
  it("a legacy fabricated zero (0 / UNAVAILABLE) is NOT available", () =>
    expect(deriveAssessmentAvailable(legacy(0, "UNAVAILABLE"))).toBe(false));
  it("a null score is not available whatever the health says", () =>
    expect(deriveAssessmentAvailable(legacy(null, "FULL"))).toBe(false));
  it("an explicit flag wins over derivation", () => {
    expect(
      deriveAssessmentAvailable({
        ...legacy(42, "FULL"),
        assessment_available: false,
      }),
    ).toBe(false);
    expect(
      deriveAssessmentAvailable({
        ...legacy(null, "UNAVAILABLE"),
        assessment_available: true,
      }),
    ).toBe(true);
  });
});

describe("normalizeRiskUpdate", () => {
  const canonicalAvailable = makeRecord("fresh", "fresh");
  const canonicalUnavailable = makeRecord("missing", "missing");
  const strip = (record: RiskUpdate): StoredRiskUpdate => {
    const copy: Partial<RiskUpdate> = { ...record };
    delete copy.assessment_available;
    return copy as StoredRiskUpdate;
  };

  it("a canonical record is returned unchanged", () => {
    expect(normalizeRiskUpdate(canonicalAvailable)).toEqual(canonicalAvailable);
    expect(normalizeRiskUpdate(canonicalUnavailable)).toEqual(
      canonicalUnavailable,
    );
  });

  it("a legacy assessed row gains assessment_available = true and keeps its values", () => {
    const out = normalizeRiskUpdate(strip(canonicalAvailable));
    expect(out).toEqual(canonicalAvailable);
  });

  it("a legacy fabricated 0/Low/NORMAL/UNAVAILABLE row becomes the canonical unavailable record", () => {
    const fabricated: StoredRiskUpdate = {
      ...strip(canonicalUnavailable),
      RiskScore: 0,
      RiskLevel: "Low",
      DominantEvidence: "Partial evidence",
      AlertSeverity: "NORMAL",
    };
    const out = normalizeRiskUpdate(fabricated);
    expect(out).toMatchObject({
      assessment_available: false,
      RiskScore: null,
      RiskLevel: null,
      DominantEvidence: null,
      AlertSeverity: null,
      SystemHealth: "UNAVAILABLE",
    });
    expect(() => assertAvailabilityInvariant(out)).not.toThrow();
  });

  it("a record that carries the flag is NOT rewritten - a backend bug stays visible", () => {
    const contradictory: RiskUpdate = {
      ...canonicalUnavailable,
      RiskScore: 12,
    };
    expect(normalizeRiskUpdate(contradictory).RiskScore).toBe(12);
    expect(() =>
      assertAvailabilityInvariant(normalizeRiskUpdate(contradictory)),
    ).toThrow(/RiskScore/);
  });
});

describe("IT-UI-01: the frontend renders the canonical record and recomputes nothing", () => {
  const strip = (source: string) =>
    // Comments may legitimately mention the forbidden strings; only code counts.
    source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:])\/\/.*$/gm, "$1");

  it('LiveMonitor.tsx and AlertBanner.tsx no longer contain SystemHealth === "UNAVAILABLE"', () => {
    for (const source of [liveMonitorSource, alertBannerSource]) {
      expect(source).not.toContain('SystemHealth === "UNAVAILABLE"');
    }
  });

  it("LiveMonitor.tsx does not fabricate a health value from the stale flag", () => {
    const code = strip(liveMonitorSource);
    expect(code).not.toMatch(/stale\s*\?\s*"UNAVAILABLE"/);
    // ...nor rewrite modality_freshness to "stale" when the record is merely old.
    expect(code).not.toMatch(/stale\s*&&[^;]*modality_freshness/);
  });

  it("both former rewrite sites use the shared three-state getDisplayState helper", () => {
    // LiveMonitor reaches it through its model, AlertBanner through the banner
    // class helper and directly.
    expect(liveMonitorSource).toContain("buildLiveMonitorModel");
    expect(liveMonitorModelSource).toContain("getDisplayState");
    expect(alertBannerSource).toContain("getDisplayState");
  });

  it("no view recomputes DominantEvidence with getEvidenceType", () => {
    for (const source of [
      liveMonitorSource,
      signalInspectorSource,
      riskTrendsSource,
      explanationViewSource,
    ]) {
      expect(strip(source)).not.toMatch(/getEvidenceType\s*\(/);
    }
  });

  it("risk display goes through formatFixed / roundHalfUp, never the binary-rounding method", () => {
    for (const source of [
      formatSource,
      exportSource,
      scoreGaugeSource,
      modalityCardSource,
      alertBannerSource,
      liveMonitorSource,
      signalInspectorSource,
      riskTrendsSource,
      explanationViewSource,
      configurationViewSource,
      trendSeriesSource,
    ]) {
      expect(strip(source)).not.toMatch(/\.toFixed\(/);
    }
  });
});

describe("branchExpiry / describeBranchStatus: expired is not the same as missing (ruling A, D13)", () => {
  const withProvenance = (
    vision: FreshnessStatus,
    telemetry: FreshnessStatus,
    provenance: RiskUpdate["provenance"],
  ): RiskUpdate => ({ ...makeRecord(vision, telemetry), provenance });

  it("a branch is expired only if it scored as missing AND the provenance says so", () => {
    const record = withProvenance("missing", "fresh", {
      vision_expired: true,
      vision_age_s: 4,
      telemetry_expired: false,
      telemetry_age_s: 1.5,
    });
    expect(branchExpiry(record, "vision")).toEqual({ expired: true, ageS: 4 });
    // A fresh branch with an age on record is not expired, and reports no age.
    expect(branchExpiry(record, "telemetry")).toEqual({
      expired: false,
      ageS: null,
    });
  });

  it("a branch that never arrived is missing but NOT expired", () => {
    const record = withProvenance("missing", "missing", {
      vision_expired: false,
      vision_age_s: null,
      telemetry_expired: false,
      telemetry_age_s: null,
    });
    expect(branchExpiry(record, "vision").expired).toBe(false);
    expect(branchExpiry(record, "telemetry").expired).toBe(false);
  });

  it("a record from before the ruling (no provenance, or none of the fields) expires nothing", () => {
    expect(
      branchExpiry(withProvenance("missing", "stale", undefined), "vision"),
    ).toEqual({ expired: false, ageS: null });
    expect(
      branchExpiry(
        withProvenance("missing", "stale", { provider: "MockAIProvider" }),
        "telemetry",
      ),
    ).toEqual({ expired: false, ageS: null });
  });

  it("an expired flag on a branch that is not missing is ignored (the status is the authority)", () => {
    const record = withProvenance("fresh", "fresh", {
      vision_expired: true,
      vision_age_s: 9,
    });
    expect(branchExpiry(record, "vision").expired).toBe(false);
  });

  it("an expired branch with no measurable age is still expired", () => {
    const record = withProvenance("missing", "fresh", {
      vision_expired: true,
      vision_age_s: null,
    });
    expect(branchExpiry(record, "vision")).toEqual({
      expired: true,
      ageS: null,
    });
  });

  it("describeBranchStatus: expired reads 'expired (N s)', everything else is the stored status", () => {
    const none = { expired: false, ageS: null };
    expect(describeBranchStatus("missing", none)).toBe("missing");
    expect(describeBranchStatus("fresh", none)).toBe("fresh");
    // A historical record's stale tier still renders as stale.
    expect(describeBranchStatus("stale", none)).toBe("stale");
    expect(describeBranchStatus("missing", { expired: true, ageS: 4 })).toBe(
      "expired (4 s)",
    );
    expect(
      describeBranchStatus("missing", { expired: true, ageS: 3.001 }),
    ).toBe("expired (3.001 s)");
    expect(describeBranchStatus("missing", { expired: true, ageS: null })).toBe(
      "expired",
    );
    // Not the same words as a branch that never arrived.
    expect(
      describeBranchStatus("missing", { expired: true, ageS: 4 }),
    ).not.toBe(describeBranchStatus("missing", none));
  });
});
