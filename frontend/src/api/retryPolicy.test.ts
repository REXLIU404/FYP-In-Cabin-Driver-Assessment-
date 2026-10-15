import { describe, expect, it } from "vitest";

import { ApiError } from "./client";
import {
  FAULT_TEXT,
  MAX_ATTEMPTS_PER_REQUEST,
  RETRY_POLICY,
  backoffMs,
  classifyFailure,
} from "./retryPolicy";

// Every expectation below is a literal. Nothing is derived from the module under
// test, so a changed constant or a re-labelled category cannot drag its own
// expectation along with it.

describe("the delivery budget (D02, user ruling Option 1)", () => {
  it("is exactly 3 deliveries per logical request: 1 first send + 2 automatic retries", () => {
    expect(MAX_ATTEMPTS_PER_REQUEST).toBe(3);
    expect(RETRY_POLICY.maxAttempts).toBe(3);
  });

  it("waits 2000 ms after the first failed delivery and 4000 ms after the second", () => {
    expect(backoffMs(1)).toBe(2000);
    expect(backoffMs(2)).toBe(4000);
    expect(RETRY_POLICY.backoffMs(1)).toBe(2000);
    expect(RETRY_POLICY.backoffMs(2)).toBe(4000);
  });

  it("has no third wait: the type accepts only 1 | 2", () => {
    const neverCalled = () => {
      // The third failed delivery stops the loop, so a third backoff cannot exist.
      // @ts-expect-error 3 is not assignable to 1 | 2
      backoffMs(3);
    };
    expect(neverCalled).toBeTypeOf("function");
  });
});

const http = (status: number, detail: string) =>
  classifyFailure(new ApiError(detail, status));

describe("classifyFailure: HTTP statuses that never succeed on a re-send", () => {
  it.each([
    [400, "Bad Request", "input"],
    [422, "Value error, image requires captured_at", "input"],
    [422, "Invalid image: cannot decode base64", "input"],
    [404, "session not found", "not_found"],
    [503, "Model artifacts are not installed", "models_unavailable"],
  ] as const)(
    "%i %s -> %s, not retryable, counted",
    (status, detail, category) => {
      expect(http(status, detail)).toEqual({
        category,
        status,
        retryable: false,
        counted: true,
      });
    },
  );

  it("a 422 whose message says the timestamp is in the future is clock skew, not bad input (T1)", () => {
    expect(
      http(422, "Value error, timestamp is in the future; check device clock"),
    ).toEqual({
      category: "clock_skew",
      status: 422,
      retryable: false,
      counted: true,
    });
  });

  it("a 422 with several joined messages still finds the clock-skew one", () => {
    expect(
      http(
        422,
        "Value error, image requires captured_at; Value error, timestamp is in the future; check device clock",
      ).category,
    ).toBe("clock_skew");
  });
});

describe("classifyFailure: the three kinds of 409 (T1, T2)", () => {
  it("a request_id reused for different content is a client bug: stop (conflict_hash)", () => {
    expect(http(409, "request_id already used for different input")).toEqual({
      category: "conflict_hash",
      status: 409,
      retryable: false,
      counted: true,
    });
  });

  it("an out-of-order evidence timestamp is NOT a failure: drop the frame, do not count (conflict_stale_frame)", () => {
    expect(http(409, "Out-of-order evidence timestamp")).toEqual({
      category: "conflict_stale_frame",
      status: 409,
      retryable: false,
      counted: false,
    });
  });

  it.each([
    "Input does not match session operation mode",
    "Create a live model session first",
  ])(
    "a session-mode mismatch is counted and stops (conflict_mode): %s",
    (detail) => {
      expect(http(409, detail)).toEqual({
        category: "conflict_mode",
        status: 409,
        retryable: false,
        counted: true,
      });
    },
  );

  it("an unrecognised 409 stops the loop: it is read as 'same id, different content'", () => {
    expect(http(409, "something the backend has never said")).toMatchObject({
      category: "conflict_hash",
      retryable: false,
      counted: true,
    });
  });
});

describe("classifyFailure: server-side failures that are worth another delivery", () => {
  it("a 500 is retryable whatever its body says: model_runtime answers JSON, storage answers plain text", () => {
    const plainText = http(500, "API request failed (500)");
    const jsonDetail = http(500, "Vision model failed during inference");
    expect(plainText).toEqual(jsonDetail);
    expect(plainText).toMatchObject({
      status: 500,
      retryable: true,
      counted: true,
    });
  });

  it.each([502, 504])("a %i is retryable (storage)", (status) => {
    expect(http(status, "Bad Gateway")).toEqual({
      category: "storage",
      status,
      retryable: true,
      counted: true,
    });
  });

  it("503 is the one 5xx that is NOT retryable: model files do not appear by themselves", () => {
    expect(http(503, "Service Unavailable").retryable).toBe(false);
  });
});

describe("classifyFailure: no HTTP answer", () => {
  it("a deadline is a timeout: retryable and counted", () => {
    expect(
      classifyFailure(new DOMException("Request timed out", "TimeoutError")),
    ).toEqual({ category: "timeout", retryable: true, counted: true });
  });

  it("a pause or unmount abort is 'aborted': not retryable, and NOT counted", () => {
    expect(
      classifyFailure(new DOMException("The user aborted", "AbortError")),
    ).toEqual({ category: "aborted", retryable: false, counted: false });
  });

  it("a rejected fetch (network down, connection reset) is transport: retryable and counted", () => {
    expect(classifyFailure(new TypeError("Failed to fetch"))).toEqual({
      category: "transport",
      retryable: true,
      counted: true,
    });
  });

  it("anything unrecognisable is treated as transport rather than ignored", () => {
    expect(classifyFailure("boom")).toMatchObject({
      category: "transport",
      retryable: true,
      counted: true,
    });
    expect(classifyFailure(undefined).category).toBe("transport");
  });

  it("routes the injected classifier of the loop to this function", () => {
    expect(RETRY_POLICY.classify(new TypeError("x")).category).toBe(
      "transport",
    );
  });
});

describe("FAULT_TEXT: what the stop panel says", () => {
  const categories = [
    "input",
    "clock_skew",
    "not_found",
    "conflict_hash",
    "conflict_mode",
    "conflict_stale_frame",
    "models_unavailable",
    "model_runtime",
    "storage",
    "timeout",
    "transport",
    "aborted",
  ] as const;

  it("every category has a title and advice", () => {
    for (const category of categories) {
      expect(FAULT_TEXT[category].title.length).toBeGreaterThan(0);
      expect(FAULT_TEXT[category].advice.length).toBeGreaterThan(0);
    }
    expect(Object.keys(FAULT_TEXT).sort()).toEqual([...categories].sort());
  });

  it("clock skew has its own, readable sentence instead of 'Inference request failed'", () => {
    const text = FAULT_TEXT.clock_skew;
    expect(text.title).toMatch(/clock/i);
    expect(text.advice).toMatch(/clock/i);
    expect(text.title).not.toMatch(/inference request failed/i);
  });

  it("a hash conflict and a dropped late frame do not share a sentence", () => {
    expect(FAULT_TEXT.conflict_hash.title).not.toBe(
      FAULT_TEXT.conflict_stale_frame.title,
    );
  });
});
