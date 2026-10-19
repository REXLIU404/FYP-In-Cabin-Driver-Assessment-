import { describe, expect, it } from "vitest";

import { ApiError } from "./client";
import {
  FAULT_TEXT,
  MAX_ATTEMPTS_PER_REQUEST,
  RETRY_POLICY,
  backoffMs,
  classifyFailure,
  deliveriesText,
  deliveryCounts,
  faultAdvice,
  retryNote,
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

  it.each([
    "Value error, vision_frame requires an image",
    "Value error, telemetry_seq requires telemetry feature values",
  ])(
    "the server's 422 for an identity without its evidence is input and is never retried (R10): %s",
    (detail) => {
      expect(http(422, detail)).toEqual({
        category: "input",
        status: 422,
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

  // R10. The server's text is OBSERVATION_CONFLICT_DETAIL (backend/app/routers/windows.py);
  // it is restated here as a literal on purpose.
  const OBSERVATION_CONFLICT =
    "Observation identity already registered with different content or acquisition time";

  it("an observation identity sent again with different content or time is a client error: stop, never retry (observation_conflict)", () => {
    expect(http(409, OBSERVATION_CONFLICT)).toEqual({
      category: "observation_conflict",
      status: 409,
      retryable: false,
      counted: true,
    });
    expect(
      RETRY_POLICY.classify(new ApiError(OBSERVATION_CONFLICT, 409)),
    ).toEqual({
      category: "observation_conflict",
      status: 409,
      retryable: false,
      counted: true,
    });
  });

  it("the three other 409 texts are not taken for an observation conflict, and it is not taken for them", () => {
    expect(
      http(409, "request_id already used for different input").category,
    ).toBe("conflict_hash");
    expect(http(409, "Out-of-order evidence timestamp").category).toBe(
      "conflict_stale_frame",
    );
    expect(http(409, "Create a live model session first").category).toBe(
      "conflict_mode",
    );
    expect(http(409, OBSERVATION_CONFLICT).category).not.toBe("conflict_hash");
    expect(http(409, OBSERVATION_CONFLICT).category).not.toBe(
      "conflict_stale_frame",
    );
  });

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
    expect(plainText).toEqual({
      category: "model_runtime",
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
    "observation_conflict",
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

  it("an observation conflict says it is the observation identity that was sent twice - never 'the same request id' (R10)", () => {
    const text = FAULT_TEXT.observation_conflict;
    expect(text.title).toBe(
      "The same observation identity was sent again with different content",
    );
    expect(text.advice).toBe(
      "The server already holds this camera frame or telemetry sample and received it again with other image bytes, values or acquisition time. This is a bug in the client, not a network problem; sending it again cannot fix it. Start a new session and report it.",
    );
    expect(`${text.title} ${text.advice}`).not.toMatch(/request id/i);
    // ...and it does not borrow either of the other 409 sentences.
    expect(text.title).not.toBe(FAULT_TEXT.conflict_hash.title);
    expect(text.title).not.toBe(FAULT_TEXT.conflict_stale_frame.title);
    expect(text.advice).not.toBe(FAULT_TEXT.conflict_hash.advice);
  });

  it("a hash conflict and a dropped late frame do not share a sentence", () => {
    expect(FAULT_TEXT.conflict_hash.title).not.toBe(
      FAULT_TEXT.conflict_stale_frame.title,
    );
  });
});

describe("deliveryCounts / deliveriesText: what the stop panel says about deliveries (H4)", () => {
  // retryCount = every failed delivery of the request, automatic and manual
  // together; manualRetries = how many of them were manual (the loop counts both).
  // A stop on a non-retryable error happens after FEWER than 3 automatic deliveries,
  // so the manual share cannot be read off retryCount alone.
  it.each([
    // retryCount, manualRetries, automatic, manual, text
    [1, 0, 1, 0, "1 of 3"], // a 400: stopped after the first delivery
    [2, 0, 2, 0, "2 of 3"], // a timeout, then a 400
    [3, 0, 3, 0, "3 of 3"], // the budget is spent
    [2, 1, 1, 1, "1 of 3 + 1 manual"], // a 400, then a failed manual retry
    [3, 1, 2, 1, "2 of 3 + 1 manual"], // timeout, 400, then a failed manual retry
    [3, 2, 1, 2, "1 of 3 + 2 manual"], // a 400, then two failed manual retries
    [4, 1, 3, 1, "3 of 3 + 1 manual"], // budget spent, one manual retry failed
    [6, 3, 3, 3, "3 of 3 + 3 manual"],
  ] as const)(
    "retryCount %i with %i manual -> %i automatic + %i manual: %s",
    (retryCount, manualRetries, automatic, manual, text) => {
      const fault = { retryCount, manualRetries };
      expect(deliveryCounts(fault)).toEqual({ automatic, manual });
      expect(deliveriesText(fault)).toBe(text);
    },
  );

  it("a 400 followed by a failed manual retry is NOT '2 of 3': that would read as one automatic retry", () => {
    expect(deliveriesText({ retryCount: 2, manualRetries: 1 })).not.toBe(
      "2 of 3",
    );
  });
});

// Task 9 / K8. The stop panel prints the delivery line ("Deliveries: ...") and an
// advice sentence side by side. For model_runtime and timeout the advice used to say
// "re-sent automatically and kept failing" whatever the reason for the stop - which
// contradicts the line above it when the stop is a MANUAL retry that failed (e.g.
// "1 of 3 + 1 manual": the loop sent it once). The sentence now follows the reason.
describe("faultAdvice: the sentence follows why the loop stopped (K8)", () => {
  it("automatic budget spent (no manual delivery): 're-sent automatically and kept failing'", () => {
    expect(
      faultAdvice({
        category: "model_runtime",
        manualRetries: 0,
        fromManualRetry: false,
      }),
    ).toBe(
      "A model or storage error on the server (HTTP 500). The request was re-sent automatically and kept failing.",
    );
    expect(
      faultAdvice({
        category: "timeout",
        manualRetries: 0,
        fromManualRetry: false,
      }),
    ).toBe(
      "No answer within 10 seconds. The request was re-sent automatically and kept timing out. Check the backend, then use Retry.",
    );
  });

  it("a manual retry that failed: it speaks of the retry the user triggered, and does not claim automatic re-sends", () => {
    expect(
      faultAdvice({
        category: "model_runtime",
        manualRetries: 1,
        fromManualRetry: false,
      }),
    ).toBe(
      "The retry you triggered failed with a model or storage error on the server (HTTP 500).",
    );
    expect(
      faultAdvice({
        category: "timeout",
        manualRetries: 2,
        fromManualRetry: false,
      }),
    ).toBe(
      "The retry you triggered got no answer in time. Check the backend, then use Retry.",
    );
    for (const category of ["model_runtime", "timeout"] as const) {
      expect(
        faultAdvice({ category, manualRetries: 1, fromManualRetry: false }),
      ).not.toMatch(/automatically/i);
    }
  });

  it("the two reasons never share a sentence", () => {
    for (const category of ["model_runtime", "timeout"] as const) {
      expect(
        faultAdvice({ category, manualRetries: 0, fromManualRetry: false }),
      ).not.toBe(
        faultAdvice({ category, manualRetries: 1, fromManualRetry: false }),
      );
    }
  });

  // R10-B (B5). A Retry whose RECONCILE fails sends nothing, so `manualRetries` stays 0;
  // only the flag says the user's retry is what failed.
  it("a failed reconcile during a manual Retry reads as the retry the user triggered - the flag alone decides", () => {
    expect(
      faultAdvice({
        category: "model_runtime",
        manualRetries: 0,
        fromManualRetry: true,
      }),
    ).toBe(
      "The retry you triggered failed with a model or storage error on the server (HTTP 500).",
    );
    expect(
      faultAdvice({
        category: "timeout",
        manualRetries: 0,
        fromManualRetry: true,
      }),
    ).toBe(
      "The retry you triggered got no answer in time. Check the backend, then use Retry.",
    );
    for (const category of ["model_runtime", "timeout"] as const) {
      expect(
        faultAdvice({ category, manualRetries: 0, fromManualRetry: true }),
      ).not.toMatch(/automatically/i);
      // ...and the flag is what separates it from the automatic stop.
      expect(
        faultAdvice({ category, manualRetries: 0, fromManualRetry: true }),
      ).not.toBe(
        faultAdvice({ category, manualRetries: 0, fromManualRetry: false }),
      );
    }
  });

  it("a manual delivery that failed reads the same with or without the flag", () => {
    for (const category of ["model_runtime", "timeout"] as const) {
      expect(
        faultAdvice({ category, manualRetries: 1, fromManualRetry: true }),
      ).toBe(
        faultAdvice({ category, manualRetries: 1, fromManualRetry: false }),
      );
    }
  });

  it("every other category reads the same whatever the reason", () => {
    for (const category of [
      "input",
      "clock_skew",
      "not_found",
      "conflict_hash",
      "conflict_mode",
      "conflict_stale_frame",
      "observation_conflict",
      "models_unavailable",
      "storage",
      "transport",
      "aborted",
    ] as const) {
      // Invariance, not a copy of the table: the sentence must not depend on why
      // the loop stopped, and it must say something.
      const automatic = faultAdvice({
        category,
        manualRetries: 0,
        fromManualRetry: false,
      });
      expect(automatic.length).toBeGreaterThan(0);
      expect(
        faultAdvice({ category, manualRetries: 3, fromManualRetry: false }),
      ).toBe(automatic);
      expect(
        faultAdvice({ category, manualRetries: 0, fromManualRetry: true }),
      ).toBe(automatic);
    }
  });

  it("the table's own automatic advice is the literal sentence", () => {
    expect(FAULT_TEXT.model_runtime.advice).toBe(
      "A model or storage error on the server (HTTP 500). The request was re-sent automatically and kept failing.",
    );
    expect(FAULT_TEXT.timeout.advice).toBe(
      "No answer within 10 seconds. The request was re-sent automatically and kept timing out. Check the backend, then use Retry.",
    );
  });
});

describe("faultAdvice in the setup phase (R10-B review, controller fix)", () => {
  // Setup (model check, session, reconcile) never re-sends automatically, so it must not
  // say it did; and the manual-retry sentence no longer quotes a fixed 10 s deadline
  // (the reconcile deadline is 15 s) nor says "as well" (the earlier stop may have been
  // another category).
  it("a setup stop does not claim automatic re-sends", () => {
    expect(
      faultAdvice({
        category: "model_runtime",
        manualRetries: 0,
        fromManualRetry: false,
        phase: "setup",
      }),
    ).toBe(
      "A model or storage error on the server (HTTP 500) while starting the session. Check the backend, then use Retry.",
    );
    expect(
      faultAdvice({
        category: "timeout",
        manualRetries: 0,
        fromManualRetry: false,
        phase: "setup",
      }),
    ).toBe(
      "The server did not answer in time while starting the session. Check the backend, then use Retry.",
    );
  });

  it("a delivery stop keeps the automatic sentence", () => {
    expect(
      faultAdvice({
        category: "timeout",
        manualRetries: 0,
        fromManualRetry: false,
        phase: "delivery",
      }),
    ).toBe(
      "No answer within 10 seconds. The request was re-sent automatically and kept timing out. Check the backend, then use Retry.",
    );
  });

  it("a manual retry that failed in setup speaks of the retry, with no fixed deadline", () => {
    const text = faultAdvice({
      category: "timeout",
      manualRetries: 0,
      fromManualRetry: true,
      phase: "setup",
    });
    expect(text).toBe(
      "The retry you triggered got no answer in time. Check the backend, then use Retry.",
    );
    expect(text).not.toMatch(/10 seconds|as well|automatically/);
  });
});

describe("retryNote: what the stop panel says Retry will do (K8)", () => {
  it("a delivery that stopped: Retry re-sends the same request to the same session", () => {
    expect(retryNote({ phase: "delivery", newSessionOnRetry: false })).toBe(
      "Retry re-sends this same request to the same session.",
    );
  });

  it("a delivery whose session is gone (404): Retry creates a NEW session", () => {
    expect(retryNote({ phase: "delivery", newSessionOnRetry: true })).toBe(
      "Retry will create a NEW session.",
    );
  });

  it("setup that stopped on a normal Start: Retry repeats the setup and resumes", () => {
    expect(retryNote({ phase: "setup", newSessionOnRetry: false })).toBe(
      "Retry repeats the setup: the model check, then the session.",
    );
  });

  it("setup that stopped on a New Session: Retry creates a NEW session (it used to say only 'repeats the setup')", () => {
    const note = retryNote({ phase: "setup", newSessionOnRetry: true });
    expect(note).toBe(
      "Retry repeats the setup: the model check, then a NEW session.",
    );
    expect(note).toMatch(/NEW session/);
    expect(note).not.toBe(
      retryNote({ phase: "setup", newSessionOnRetry: false }),
    );
  });
});
