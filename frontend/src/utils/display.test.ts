import { describe, expect, it } from "vitest";

import { branchExpiry } from "../../../ai/src/availability";
import { makeRecord, replayRecords } from "../testing/records";
import type { RiskUpdate } from "../types";
import {
  evidenceDistribution,
  resolveBranchPill,
  resolveDominantEvidence,
  resolvePill,
  zeroWeightNotice,
} from "./display";
import { UNAVAILABLE_LABEL } from "./format";

describe("resolvePill: null never reaches a CSS class", () => {
  it("a null label and tone resolve to the explicit unavailable tone", () => {
    expect(resolvePill(null, null)).toEqual({
      label: UNAVAILABLE_LABEL,
      tone: "unavailable",
    });
  });

  it("a null label with no tone also resolves to unavailable, not neutral", () => {
    expect(resolvePill(null)).toEqual({
      label: UNAVAILABLE_LABEL,
      tone: "unavailable",
    });
  });

  it("a real label keeps its tone; an omitted tone is neutral", () => {
    expect(resolvePill("High", "High")).toEqual({
      label: "High",
      tone: "High",
    });
    expect(resolvePill("Monitoring paused")).toEqual({
      label: "Monitoring paused",
      tone: "neutral",
    });
  });

  it("the tone it returns is never the string 'null'", () => {
    for (const pill of [
      resolvePill(null, null),
      resolvePill(null),
      resolvePill("x", null),
    ]) {
      expect(`pill--${pill.tone}`).not.toContain("null");
    }
  });
});

describe("resolveDominantEvidence reads the record, it does not recompute", () => {
  const unavailable = makeRecord("missing", "missing", 1);

  it("an unavailable record resolves to null", () => {
    expect(resolveDominantEvidence(unavailable, 30)).toBeNull();
  });

  it("returns the record's own value even when recomputation would disagree", () => {
    const record: RiskUpdate = {
      ...makeRecord("fresh", "fresh", 2),
      DominantEvidence: "Telemetry-dominant",
    };
    // P_distraction > P_telemetry here, so a recompute would say Vision-dominant.
    expect(record.P_distraction).toBeGreaterThan(record.P_telemetry_anomaly);
    expect(resolveDominantEvidence(record, 30)).toBe("Telemetry-dominant");
  });

  it("does NOT resurrect a label for a record whose stored value is null", () => {
    // Recomputing from the other fields would produce a non-null label.
    const record: RiskUpdate = {
      ...makeRecord("fresh", "fresh", 3),
      DominantEvidence: null,
    };
    expect(resolveDominantEvidence(record, 30)).toBeNull();
  });

  it("falls back to recomputation only when the field is absent (legacy hand-built record)", () => {
    const base = makeRecord("fresh", "fresh", 4);
    const legacy = { ...base } as Partial<RiskUpdate>;
    delete legacy.DominantEvidence;
    expect(resolveDominantEvidence(legacy as RiskUpdate, 30)).toBe(
      base.DominantEvidence,
    );
  });
});

describe("evidenceDistribution counts every record exactly once", () => {
  const history = [
    makeRecord("fresh", "fresh", 1),
    makeRecord("fresh", "missing", 2),
    makeRecord("missing", "missing", 3),
    makeRecord("missing", "missing", 4),
  ];
  const buckets = evidenceDistribution(history, 30);
  const total = buckets.reduce((sum, b) => sum + b.count, 0);

  it("has an Unavailable bucket holding the unavailable records", () => {
    expect(buckets.find((b) => b.label === "Unavailable")?.count).toBe(2);
  });

  it("the buckets sum to history.length", () => {
    expect(total).toBe(history.length);
  });

  it("a Partial evidence record lands in Partial", () => {
    expect(buckets.find((b) => b.label === "Partial")?.count).toBe(1);
  });
});

describe("zeroWeightNotice: a slider at 0 is not silent", () => {
  it("is null while both weights are positive", () => {
    expect(zeroWeightNotice(0.5, 0.5)).toBeNull();
    expect(zeroWeightNotice(0.05, 0.95)).toBeNull();
  });

  it("names the branch whose weight reached zero", () => {
    expect(zeroWeightNotice(1, 0)).toMatch(/telemetry/i);
    expect(zeroWeightNotice(0, 1)).toMatch(/vision/i);
  });

  it("warns that a zero weight can make a window unavailable", () => {
    expect(zeroWeightNotice(1, 0)).toMatch(/unavailable/i);
  });

  it("treats a weight below the fusion epsilon as zero", () => {
    expect(zeroWeightNotice(1 - 1e-12, 1e-12)).not.toBeNull();
  });
});

describe("resolveBranchPill: an expired branch no longer looks like a missing one (ruling A, D13)", () => {
  const none = { expired: false, ageS: null };

  it("missing keeps the 'missing' words and tone", () => {
    expect(resolveBranchPill("missing", none)).toEqual({
      label: "missing",
      tone: "missing",
    });
  });

  it("expired says 'expired (N s)' in its own tone", () => {
    expect(resolveBranchPill("missing", { expired: true, ageS: 4 })).toEqual({
      label: "expired (4 s)",
      tone: "expired",
    });
    expect(resolveBranchPill("missing", { expired: true, ageS: null })).toEqual(
      { label: "expired", tone: "expired" },
    );
  });

  it("fresh, and a historical stale record, are shown as stored", () => {
    expect(resolveBranchPill("fresh", none)).toEqual({
      label: "fresh",
      tone: "fresh",
    });
    expect(resolveBranchPill("stale", none)).toEqual({
      label: "stale",
      tone: "stale",
    });
  });

  it("the shipped replay's window 16 (telemetry 4 s old) reads expired; window 14 (no telemetry) reads missing", () => {
    const records = replayRecords();
    const expiry = (id: number) => branchExpiry(records[id - 1], "telemetry");
    expect(
      resolveBranchPill(records[15].modality_freshness.telemetry, expiry(16)),
    ).toEqual({ label: "expired (4 s)", tone: "expired" });
    expect(
      resolveBranchPill(records[13].modality_freshness.telemetry, expiry(14)),
    ).toEqual({ label: "missing", tone: "missing" });
  });
});
