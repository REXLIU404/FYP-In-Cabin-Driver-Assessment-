import { afterEach, describe, expect, it, vi } from "vitest";

import { assertAvailabilityInvariant } from "../../../ai/src/availability";
import { DEFAULT_CONFIG } from "../../../ai/src/riskLogic";
import { makeRecord, toLegacyRow } from "../testing/records";
import {
  ApiError,
  NotFromBackendError,
  api,
  isNoDetailMessage,
} from "./client";
import { classifyFailure } from "./retryPolicy";

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

describe("infer() hands the Server-Timing header to the caller (deferred final minor)", () => {
  afterEach(() => vi.unstubAllGlobals());

  const answer = (headers: Record<string, string>) =>
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          new Response(JSON.stringify(makeRecord("fresh", "fresh", 1)), {
            status: 201,
            headers: { "Content-Type": "application/json", ...headers },
          }),
      ),
    );
  const payload = {} as Parameters<typeof api.infer>[1];

  it("the header value, verbatim", async () => {
    answer({ "Server-Timing": "infer;dur=8.2, total;dur=12.5" });
    const seen = vi.fn();
    await api.infer("s1", payload, new AbortController().signal, 1, seen);
    expect(seen).toHaveBeenCalledWith("infer;dur=8.2, total;dur=12.5");
  });

  it("null when the answer has none", async () => {
    answer({});
    const seen = vi.fn();
    await api.infer("s1", payload, new AbortController().signal, 1, seen);
    expect(seen).toHaveBeenCalledWith(null);
  });
});

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
    let settled = false;
    void pending.then(
      () => (settled = true),
      () => (settled = true),
    );
    const outcome = expect(pending).rejects.toMatchObject({
      name: "TimeoutError",
    });
    await vi.advanceTimersByTimeAsync(14_999);
    // The lower bound: one millisecond before the deadline the call still waits.
    expect(settled).toBe(false);
    await vi.advanceTimersByTimeAsync(1);
    await outcome;
    expect(settled).toBe(true);
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

// FIX-BACKEND-REACH. With only `npm run dev` running (nothing on port 8000) the Vite proxy
// answers every /api call with an HTTP 500 of its own - text/plain, empty body - which used to
// be reported as "a model or storage error on the server". The backend stamps X-DRA-Backend on
// every response it sends; an error answer without it is not the backend's.
describe("an error answer is the backend's only if it carries X-DRA-Backend", () => {
  afterEach(() => vi.unstubAllGlobals());

  const answer = (
    status: number,
    opts: { marked: boolean; body?: string; type?: string },
  ) =>
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          new Response(opts.body ?? "", {
            status,
            headers: {
              "Content-Type": opts.type ?? "text/plain",
              ...(opts.marked ? { "X-DRA-Backend": "1" } : {}),
            },
          }),
      ),
    );

  const failureOf = async (call: () => Promise<unknown>) => {
    const err = await call().then(
      () => {
        throw new Error("expected the call to reject");
      },
      (e: unknown) => e,
    );
    return { err, failure: classifyFailure(err) };
  };

  it("the dev proxy's own 500 (text/plain, empty body, no marker) is transport - not model_runtime", async () => {
    answer(500, { marked: false });
    const { err, failure } = await failureOf(() => api.models());
    expect(failure).toEqual({
      category: "transport",
      retryable: true,
      counted: true,
    });
    expect(err).toBeInstanceOf(NotFromBackendError);
    expect((err as Error).message).toBe(
      "the API proxy or a gateway answered HTTP 500 and the backend did not; is the backend running?",
    );
  });

  it.each([404, 500, 502, 503, 504])(
    "an unmarked %i is transport, retryable and counted, with no status of its own",
    async (status) => {
      answer(status, { marked: false });
      const { failure } = await failureOf(() => api.sessions());
      expect(failure).toEqual({
        category: "transport",
        retryable: true,
        counted: true,
      });
    },
  );

  it("an unmarked answer is transport even when its body looks like the backend's JSON", async () => {
    answer(500, {
      marked: false,
      type: "application/json",
      body: JSON.stringify({ detail: "Vision model failed during inference" }),
    });
    const { failure } = await failureOf(() => api.models());
    expect(failure.category).toBe("transport");
  });

  it("the backend's own JSON 500 is still model_runtime", async () => {
    answer(500, {
      marked: true,
      type: "application/json",
      body: JSON.stringify({ detail: "Vision model failed during inference" }),
    });
    const { err, failure } = await failureOf(() => api.models());
    expect(failure).toEqual({
      category: "model_runtime",
      status: 500,
      retryable: true,
      counted: true,
    });
    expect(err).not.toBeInstanceOf(NotFromBackendError);
    expect((err as Error).message).toBe("Vision model failed during inference");
  });

  it("the backend's own plain-text 500 (unhandled exception) is still model_runtime, and its message is the client's fallback", async () => {
    answer(500, { marked: true, body: "Internal Server Error" });
    const { err, failure } = await failureOf(() => api.models());
    expect(failure.category).toBe("model_runtime");
    expect((err as Error).message).toBe("API request failed (500)");
    expect(isNoDetailMessage((err as Error).message)).toBe(true);
  });

  it.each([
    [404, "session not found", "not_found"],
    [409, "request_id already used for different input", "conflict_hash"],
    [422, "Value error, image requires captured_at", "input"],
    [503, "Model artifacts are not installed", "models_unavailable"],
  ] as const)(
    "a marked %i keeps its D02 category (%s -> %s)",
    async (status, detail, category) => {
      answer(status, {
        marked: true,
        type: "application/json",
        body: JSON.stringify({ detail }),
      });
      const { err, failure } = await failureOf(() => api.models());
      expect(failure.category).toBe(category);
      expect(failure.status).toBe(status);
      expect((err as Error).message).toBe(detail);
    },
  );

  it("a 2xx answer is a success whether or not it carries the marker", async () => {
    answer(200, { marked: false, type: "application/json", body: "[]" });
    await expect(api.sessions()).resolves.toEqual([]);
    answer(200, { marked: true, type: "application/json", body: "[]" });
    await expect(api.sessions()).resolves.toEqual([]);
  });

  it("only the client's own fallback sentence counts as 'no detail from the server'", () => {
    expect(isNoDetailMessage("API request failed (500)")).toBe(true);
    expect(isNoDetailMessage("API request failed (404)")).toBe(true);
    expect(isNoDetailMessage("Vision model failed during inference")).toBe(
      false,
    );
    expect(isNoDetailMessage("API request failed (500) while saving")).toBe(
      false,
    );
    expect(isNoDetailMessage("")).toBe(false);
  });

  it("the unmarked-answer error is an ApiError too, so nothing that catches ApiError loses it", () => {
    expect(new NotFromBackendError(500)).toBeInstanceOf(ApiError);
    expect(new NotFromBackendError(502).status).toBe(502);
  });
});
