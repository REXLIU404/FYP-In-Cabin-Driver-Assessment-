import { afterEach, describe, expect, it, vi } from "vitest";

import { assertAvailabilityInvariant } from "../../../ai/src/availability";
import { DEFAULT_CONFIG } from "../../../ai/src/riskLogic";
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
      1,
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

const livePayload = {
  request_id: "r-1",
  image_base64: "data:image/jpeg;base64,AAAA",
  captured_at: "2026-01-01T12:00:00.000Z",
  telemetry_features: null,
  telemetry_timestamp: null,
  telemetry_source: "missing" as const,
};

// A fetch that never answers on its own and rejects like the browser's when its
// signal aborts.
const hangingFetch = () =>
  vi.stubGlobal(
    "fetch",
    vi.fn(
      (_url: string, init: RequestInit) =>
        new Promise((_, reject) =>
          init.signal?.addEventListener("abort", () =>
            reject(new DOMException("The operation was aborted", "AbortError")),
          ),
        ),
    ),
  );

describe("api.infer tells the server which delivery this is", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("sends X-Attempt-Index on every delivery and keeps it out of the body", async () => {
    respondWith(legacyUnavailable);
    const controller = new AbortController();
    for (const attempt of [1, 2, 3, 4]) {
      await api.infer("s1", livePayload, controller.signal, attempt);
    }
    const sent = vi
      .mocked(fetch)
      .mock.calls.map(([, init]) => init as RequestInit);
    expect(
      sent.map(
        (init) => (init.headers as Record<string, string>)["X-Attempt-Index"],
      ),
    ).toEqual(["1", "2", "3", "4"]);
    expect(
      sent.every((init) => init.body === JSON.stringify(livePayload)),
    ).toBe(true);
    expect((sent[0].headers as Record<string, string>)["Content-Type"]).toBe(
      "application/json",
    );
  });
});

describe("a pause and a timeout are different errors (Step 5)", () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("aborting through the caller's signal rejects with an AbortError", async () => {
    hangingFetch();
    const controller = new AbortController();
    const pending = api.infer("s1", livePayload, controller.signal, 1);
    controller.abort();
    await expect(pending).rejects.toMatchObject({ name: "AbortError" });
  });

  it("the client's own 15 s deadline rejects with a TimeoutError, not an AbortError", async () => {
    vi.useFakeTimers();
    hangingFetch();
    const pending = api.infer(
      "s1",
      livePayload,
      new AbortController().signal,
      1,
    );
    const outcome = expect(pending).rejects.toMatchObject({
      name: "TimeoutError",
    });
    await vi.advanceTimersByTimeAsync(14_999);
    await vi.advanceTimersByTimeAsync(1);
    await outcome;
  });

  it("the deadline is not reported if the caller aborted first", async () => {
    vi.useFakeTimers();
    hangingFetch();
    const controller = new AbortController();
    const pending = api.infer("s1", livePayload, controller.signal, 1);
    const outcome = expect(pending).rejects.toMatchObject({
      name: "AbortError",
    });
    controller.abort();
    await vi.advanceTimersByTimeAsync(20_000);
    await outcome;
  });
});

describe("every call can be cancelled", () => {
  afterEach(() => vi.unstubAllGlobals());

  it.each([
    ["models", (s: AbortSignal) => api.models(s)],
    ["create", (s: AbortSignal) => api.create({ ...DEFAULT_CONFIG }, s)],
    ["sessions", (s: AbortSignal) => api.sessions(s)],
    ["session", (s: AbortSignal) => api.session("s1", s)],
    ["latest", (s: AbortSignal) => api.latest("s1", s)],
    ["windows", (s: AbortSignal) => api.windows("s1", 0, s)],
    ["flag", (s: AbortSignal) => api.flag("s1", 1, true, s)],
  ])(
    "%s rejects with an AbortError once the signal aborts",
    async (_name, call) => {
      hangingFetch();
      const controller = new AbortController();
      const pending = call(controller.signal);
      controller.abort();
      await expect(pending).rejects.toMatchObject({ name: "AbortError" });
    },
  );
});
