import { afterEach, describe, expect, it, vi } from "vitest";

import { assertAvailabilityInvariant } from "../../../ai/src/availability";
import { makeRecord, toLegacyRow } from "../testing/records";
import { api } from "./client";

const respondWith = (body: unknown) =>
  vi.stubGlobal(
    "fetch",
    vi.fn(
      async () =>
        new Response(JSON.stringify(body), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
    ),
  );

const legacyAvailable = {
  ...toLegacyRow(makeRecord("fresh", "fresh", 1)),
  RiskScore: 42.0,
  RiskLevel: "Medium",
  AlertSeverity: "CAUTION",
  SystemHealth: "DEGRADED",
};
const legacyUnavailable = toLegacyRow(makeRecord("missing", "missing", 2));

// api/client.ts is the second untrusted boundary (the first is localStorage):
// it used to hand `response.json()` to the UI behind an unchecked `as T`.
describe("api client normalises RiskUpdate payloads at the network boundary", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("latest(): a legacy available row gains assessment_available = true", async () => {
    respondWith(legacyAvailable);
    const row = await api.latest("s1");
    expect(row.assessment_available).toBe(true);
    expect(row.RiskScore).toBe(42);
  });

  it("latest(): a legacy 0/Low/NORMAL/UNAVAILABLE row becomes unavailable with null fields", async () => {
    respondWith(legacyUnavailable);
    const row = await api.latest("s1");
    expect(row.assessment_available).toBe(false);
    expect(row.RiskScore).toBeNull();
    expect(row.RiskLevel).toBeNull();
    expect(row.DominantEvidence).toBeNull();
    expect(row.AlertSeverity).toBeNull();
    expect(row.SystemHealth).toBe("UNAVAILABLE");
    expect(() => assertAvailabilityInvariant(row)).not.toThrow();
  });

  it("windows(): every element is normalised", async () => {
    respondWith([legacyAvailable, legacyUnavailable]);
    const rows = await api.windows("s1");
    expect(rows.map((r) => r.assessment_available)).toEqual([true, false]);
  });

  it("infer() and flag(): the single-record endpoints are normalised too", async () => {
    respondWith(legacyUnavailable);
    const controller = new AbortController();
    const inferred = await api.infer(
      "s1",
      {
        request_id: "r",
        image_base64: null,
        captured_at: null,
        telemetry_features: null,
        telemetry_timestamp: null,
        telemetry_source: "missing",
      },
      controller.signal,
    );
    expect(inferred.assessment_available).toBe(false);
    const flagged = await api.flag("s1", 2, true);
    expect(flagged.assessment_available).toBe(false);
  });

  it("a canonical record from the backend is passed through unchanged", async () => {
    const canonical = makeRecord("missing", "missing", 4);
    respondWith(canonical);
    expect(await api.latest("s1")).toEqual(canonical);
  });
});
