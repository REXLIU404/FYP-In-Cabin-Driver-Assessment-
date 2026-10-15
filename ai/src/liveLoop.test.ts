import { afterEach, describe, expect, it, vi } from "vitest";

import { api as realApi, ApiError } from "../../frontend/src/api/client";
import { RETRY_POLICY } from "../../frontend/src/api/retryPolicy";
import { makeRecord } from "../../frontend/src/testing/records";
import {
  createLiveLoop,
  type LiveFrame,
  type LiveLoopApi,
  type LivePayload,
} from "./liveLoop";
import { DEFAULT_CONFIG } from "./riskLogic";
import type {
  AppConfig,
  RiskUpdate,
  SessionMeta,
  TelemetryFeatures,
} from "./types";

// ---------------------------------------------------------------------------
// A virtual clock. The loop gets its timers and its wall clock injected, so the
// whole state machine - 10 s deadlines, 2 s / 4 s backoffs, the tick interval -
// runs here without sleeping. Every duration below is a literal.
// ---------------------------------------------------------------------------
// A real macrotask: every pending promise continuation runs before it resolves.
const flush = () => new Promise<void>((resolve) => setTimeout(resolve, 0));

class FakeTime {
  now = Date.UTC(2026, 0, 1, 12, 0, 0);
  private nextHandle = 1;
  private timers = new Map<number, { at: number; fn: () => void }>();

  setTimeout = (fn: () => void, ms: number): unknown => {
    const handle = this.nextHandle++;
    this.timers.set(handle, { at: this.now + Math.max(0, ms), fn });
    return handle;
  };
  clearTimeout = (handle: unknown): void => {
    this.timers.delete(handle as number);
  };
  get pending(): number {
    return this.timers.size;
  }

  /** Move the clock forward, firing every timer that falls due, in order. */
  async advance(ms: number): Promise<void> {
    const target = this.now + ms;
    for (;;) {
      await flush();
      const due = [...this.timers.entries()]
        .filter(([, timer]) => timer.at <= target)
        .sort((a, b) => a[1].at - b[1].at)[0];
      if (!due) break;
      this.timers.delete(due[0]);
      this.now = Math.max(this.now, due[1].at);
      due[1].fn();
    }
    this.now = target;
    await flush();
  }
}

// One tick every 500 ms (2 inferences per second).
const CONFIG: AppConfig = { ...DEFAULT_CONFIG, inferenceFps: 2 };
const TELEMETRY: TelemetryFeatures = {
  speed_kmph: 52,
  accel_x: 0.7,
  accel_y: 0.2,
  brake_pressure: 20,
  steering_angle: 7.5,
  throttle: 40,
  lane_deviation: 0.21,
  headway_distance: 18,
};

type Step = "ok" | "unavailable" | "hang" | "deferred" | Error;
type Models = { ready: boolean };

interface RigOptions {
  /** What successive `infer` calls do. Once exhausted, every call succeeds. */
  script?: Step[];
  frame?: "camera" | "none" | "throws";
  telemetry?: boolean;
  missReason?: string;
  /** What the server already holds for a session (reconcile, loadSession). */
  saved?: RiskUpdate[];
  modelsError?: Error;
  /** `api.models` never answers (until aborted). */
  modelsHang?: boolean;
}

function rig(options: RigOptions = {}) {
  const time = new FakeTime();
  const script = [...(options.script ?? [])];
  const saved = options.saved ?? [];
  const sessionIds = ["sess-1", "sess-2", "sess-3"];
  const deferred: Array<(record: RiskUpdate) => void> = [];
  const calls: {
    sid: string;
    body: string;
    payload: LivePayload;
    attemptIndex: number;
  }[] = [];
  let windowId = 0;
  let frames = 0;
  let requestIds = 0;
  const state = { modelsError: options.modelsError };

  const meta = (id: string, total = 0): SessionMeta => ({
    id,
    created_at: "2026-01-01T12:00:00+00:00",
    total_windows: total,
  });
  const api = {
    models: vi.fn((signal: AbortSignal): Promise<Models> => {
      if (options.modelsHang)
        return new Promise<Models>((_, reject) =>
          signal.addEventListener(
            "abort",
            () => reject(new DOMException("aborted", "AbortError")),
            { once: true },
          ),
        );
      if (state.modelsError) return Promise.reject(state.modelsError);
      return Promise.resolve({ ready: true });
    }),
    create: vi.fn(
      async (): Promise<SessionMeta> => meta(sessionIds.shift() ?? "sess-n"),
    ),
    session: vi.fn(
      async (sid: string): Promise<SessionMeta> => meta(sid, saved.length),
    ),
    latest: vi.fn(async (): Promise<RiskUpdate> => saved[saved.length - 1]),
    windows: vi.fn(async (): Promise<RiskUpdate[]> => saved),
    infer: vi.fn(
      (
        sid: string,
        payload: LivePayload,
        signal: AbortSignal,
        attemptIndex: number,
      ): Promise<RiskUpdate> => {
        calls.push({
          sid,
          body: JSON.stringify(payload),
          payload: structuredClone(payload),
          attemptIndex,
        });
        const step = script.shift() ?? "ok";
        if (step instanceof Error) return Promise.reject(step);
        if (step === "hang")
          return new Promise<RiskUpdate>((_, reject) =>
            signal.addEventListener(
              "abort",
              () => reject(new DOMException("aborted", "AbortError")),
              { once: true },
            ),
          );
        if (step === "deferred")
          return new Promise<RiskUpdate>((resolve) => deferred.push(resolve));
        windowId += 1;
        return Promise.resolve(
          step === "unavailable"
            ? makeRecord("missing", "missing", windowId)
            : makeRecord("fresh", "fresh", windowId),
        );
      },
    ),
  };
  const captureFrame = vi.fn((): LiveFrame | null => {
    if (options.frame === "none") return null;
    if (options.frame === "throws") throw new Error("canvas is tainted");
    frames += 1;
    return {
      image_base64: `frame-${frames}`,
      captured_at: new Date(time.now).toISOString(),
    };
  });
  const telemetryAt = vi.fn((): TelemetryFeatures | null =>
    options.telemetry === false ? null : TELEMETRY,
  );
  const newRequestId = vi.fn(() => `req-${++requestIds}`);
  const loop = createLiveLoop<Models>({
    api: api as LiveLoopApi<Models>,
    policy: RETRY_POLICY,
    getConfig: () => CONFIG,
    captureFrame,
    captureMissReason: () => options.missReason ?? "stopped_by_user",
    telemetryAt,
    newRequestId,
    now: () => time.now,
    timers: time,
  });
  return {
    loop,
    time,
    api,
    calls,
    deferred,
    captureFrame,
    telemetryAt,
    newRequestId,
    state,
    get: () => loop.getState(),
    /** start() and let the first tick run. */
    async begin() {
      await loop.start();
      await time.advance(0);
    },
  };
}

const transportError = () => new TypeError("Failed to fetch");
const threeTransportErrors = (): Step[] => [
  transportError(),
  transportError(),
  transportError(),
];

describe("bounded retry: exactly 3 deliveries, then a visible stop", () => {
  it("delivers a failing request 3 times - not 4 - at +0 / +2000 / +6000 ms, then schedules nothing", async () => {
    const r = rig({ script: threeTransportErrors() });
    await r.begin();
    expect(r.api.infer).toHaveBeenCalledTimes(1);

    await r.time.advance(1999);
    expect(r.api.infer).toHaveBeenCalledTimes(1);
    await r.time.advance(1);
    expect(r.api.infer).toHaveBeenCalledTimes(2);

    await r.time.advance(3999);
    expect(r.api.infer).toHaveBeenCalledTimes(2);
    await r.time.advance(1);
    expect(r.api.infer).toHaveBeenCalledTimes(3);

    await r.time.advance(600_000);
    expect(r.api.infer).toHaveBeenCalledTimes(3);
    expect(r.time.pending).toBe(0);
    expect(r.get().running).toBe(false);
    expect(r.get().fault).toMatchObject({
      category: "transport",
      stopped: true,
      retryCount: 3,
      attemptIndex: 3,
      phase: "delivery",
      requestId: "req-1",
    });
  });

  it("shows the fault while retries are still pending, but not as stopped", async () => {
    const r = rig({ script: threeTransportErrors() });
    await r.begin();
    expect(r.get().fault).toMatchObject({
      category: "transport",
      stopped: false,
      retryCount: 1,
    });
    expect(r.get().running).toBe(true);
  });

  it("sends every delivery with its own attempt index: 1, 2, 3", async () => {
    const r = rig({ script: threeTransportErrors() });
    await r.begin();
    await r.time.advance(6000);
    expect(r.calls.map((call) => call.attemptIndex)).toEqual([1, 2, 3]);
  });

  it("counts per logical request: a request that recovered does not use up the next one's budget", async () => {
    const r = rig({
      script: [transportError(), "ok", ...threeTransportErrors()],
    });
    await r.begin();
    await r.time.advance(2000); // 2nd delivery of req-1 succeeds
    expect(r.get().fault).toBeNull();
    await r.time.advance(500); // next tick: req-2
    await r.time.advance(6000);
    expect(r.calls.map((c) => [c.payload.request_id, c.attemptIndex])).toEqual([
      ["req-1", 1],
      ["req-1", 2],
      ["req-2", 1],
      ["req-2", 2],
      ["req-2", 3],
    ]);
    expect(r.get().fault).toMatchObject({ stopped: true, retryCount: 3 });
  });

  it("a later success clears the fault and the loop keeps its configured pace", async () => {
    const r = rig({ script: [transportError(), "ok"] });
    await r.begin();
    await r.time.advance(2000);
    expect(r.get().fault).toBeNull();
    expect(r.get().history.map((rec) => rec.window_id)).toEqual([1]);
    await r.time.advance(499);
    expect(r.api.infer).toHaveBeenCalledTimes(2);
    await r.time.advance(1);
    expect(r.api.infer).toHaveBeenCalledTimes(3);
  });
});

describe("one failure is enough for errors that a re-send cannot fix", () => {
  it.each([
    [new ApiError("Value error, image requires captured_at", 422), "input"],
    [
      new ApiError("Model artifacts are not installed", 503),
      "models_unavailable",
    ],
    [
      new ApiError("request_id already used for different input", 409),
      "conflict_hash",
    ],
    [new ApiError("Create a live model session first", 409), "conflict_mode"],
    [
      new ApiError(
        "Value error, timestamp is in the future; check device clock",
        422,
      ),
      "clock_skew",
    ],
    [new ApiError("session not found", 404), "not_found"],
  ])("%s stops after exactly 1 delivery as %s", async (error, category) => {
    const r = rig({ script: [error] });
    await r.begin();
    await r.time.advance(600_000);
    expect(r.api.infer).toHaveBeenCalledTimes(1);
    expect(r.time.pending).toBe(0);
    expect(r.get().running).toBe(false);
    expect(r.get().fault).toMatchObject({
      category,
      stopped: true,
      retryCount: 1,
      attemptIndex: 1,
    });
  });

  it("a 404 says that Retry will create a NEW session; the others do not", async () => {
    const gone = rig({ script: [new ApiError("session not found", 404)] });
    await gone.begin();
    expect(gone.get().fault?.newSessionOnRetry).toBe(true);
    const bad = rig({ script: [new ApiError("Bad Request", 400)] });
    await bad.begin();
    expect(bad.get().fault?.newSessionOnRetry).toBe(false);
  });
});

describe("a late frame is dropped, not fatal (T2)", () => {
  it("an out-of-order 409 is neither counted nor retried, and the next tick carries on with a NEW request", async () => {
    const r = rig({
      script: [new ApiError("Out-of-order evidence timestamp", 409), "ok"],
    });
    await r.begin();
    expect(r.api.infer).toHaveBeenCalledTimes(1);
    expect(r.get().fault).toBeNull();
    expect(r.get().running).toBe(true);
    expect(r.get().droppedFrames).toBe(1);

    await r.time.advance(499);
    expect(r.api.infer).toHaveBeenCalledTimes(1);
    await r.time.advance(1);
    expect(r.api.infer).toHaveBeenCalledTimes(2);
    expect(r.calls[1].payload.request_id).toBe("req-2");
    expect(r.calls[1].attemptIndex).toBe(1);
    expect(r.get().history.map((rec) => rec.window_id)).toEqual([1]);
    expect(r.get().fault).toBeNull();
  });

  it("repeated late frames never add up to a stop", async () => {
    const late = () => new ApiError("Out-of-order evidence timestamp", 409);
    const r = rig({ script: [late(), late(), late(), late(), late()] });
    await r.begin();
    await r.time.advance(5000);
    expect(r.get().running).toBe(true);
    expect(r.get().fault).toBeNull();
    expect(r.get().droppedFrames).toBe(5);
  });
});

describe("the request is frozen (Review Focus #4)", () => {
  it("a 10 s timeout is retried with the SAME payload, byte for byte", async () => {
    const r = rig({ script: ["hang", "ok"] });
    await r.begin();
    await r.time.advance(9999);
    expect(r.api.infer).toHaveBeenCalledTimes(1);
    await r.time.advance(1); // the 10 s deadline fires
    expect(r.get().fault).toMatchObject({
      category: "timeout",
      stopped: false,
      retryCount: 1,
    });
    await r.time.advance(2000);

    expect(r.calls).toHaveLength(2);
    expect(r.calls[1].body).toBe(r.calls[0].body);
    expect(r.calls[1].payload).toEqual(r.calls[0].payload);
    expect(new Set(r.calls.map((c) => c.payload.request_id)).size).toBe(1);
    expect(r.calls[0].payload).toMatchObject({
      request_id: "req-1",
      image_base64: "frame-1",
      telemetry_features: TELEMETRY,
      telemetry_source: "prepared_replay",
    });
    // The frame, the telemetry and the id were produced once, not once per delivery.
    expect(r.captureFrame).toHaveBeenCalledTimes(1);
    expect(r.telemetryAt).toHaveBeenCalledTimes(1);
    expect(r.newRequestId).toHaveBeenCalledTimes(1);
    expect(r.get().fault).toBeNull();
  });

  it("the evidence timestamps of a retry are those of the first capture, not of the retry", async () => {
    const r = rig({ script: threeTransportErrors() });
    await r.begin();
    const stampedAt = new Date(r.time.now).toISOString();
    await r.time.advance(6000);
    for (const call of r.calls) {
      expect(call.payload.captured_at).toBe(stampedAt);
      expect(call.payload.telemetry_timestamp).toBe(stampedAt);
    }
  });
});

describe("a pause is not a failure", () => {
  it("aborts the in-flight request without counting it and without scheduling anything", async () => {
    const r = rig({ script: ["hang"] });
    await r.begin();
    expect(r.api.infer).toHaveBeenCalledTimes(1);
    r.loop.pause();
    await r.time.advance(0);
    // The request itself is cancelled, not just forgotten.
    expect(r.api.infer.mock.calls[0][2].aborted).toBe(true);
    expect(r.get().fault).toBeNull();
    expect(r.get().running).toBe(false);
    expect(r.time.pending).toBe(0);
    await r.time.advance(600_000);
    expect(r.api.infer).toHaveBeenCalledTimes(1);
  });

  it("leaves the next request its full budget of 3 deliveries", async () => {
    const r = rig({ script: ["hang", ...threeTransportErrors()] });
    await r.begin();
    r.loop.pause();
    await r.time.advance(0);
    await r.begin(); // start() again
    await r.time.advance(6000);
    expect(r.api.infer).toHaveBeenCalledTimes(4); // 1 aborted + 3 of the new request
    expect(r.get().fault).toMatchObject({ stopped: true, retryCount: 3 });
  });

  it("is told apart from a timeout: the same abort is a timeout only when the deadline fired", async () => {
    const paused = rig({ script: ["hang"] });
    await paused.begin();
    paused.loop.pause();
    await paused.time.advance(0);
    expect(paused.get().fault).toBeNull();

    const slow = rig({ script: ["hang"] });
    await slow.begin();
    await slow.time.advance(10_000);
    expect(slow.get().fault?.category).toBe("timeout");
  });

  it("pausing during a backoff cancels the pending retry", async () => {
    const r = rig({ script: [transportError()] });
    await r.begin();
    expect(r.time.pending).toBeGreaterThan(0);
    r.loop.pause();
    expect(r.time.pending).toBe(0); // the timer is cancelled, not merely ignored
    await r.time.advance(600_000);
    expect(r.api.infer).toHaveBeenCalledTimes(1);
    expect(r.get().fault).toBeNull();
    expect(r.time.pending).toBe(0);
  });

  it("a response that arrives after the pause is discarded", async () => {
    const r = rig({ script: ["deferred"] });
    await r.begin();
    r.loop.pause();
    r.deferred[0](makeRecord("fresh", "fresh", 7));
    await r.time.advance(0);
    expect(r.get().history).toEqual([]);
    expect(r.get().total).toBe(0);
    expect(r.time.pending).toBe(0);
  });
});

describe("setup failures stop before a session exists", () => {
  it("api.models answering 503 stops the loop without creating a session", async () => {
    const r = rig({
      modelsError: new ApiError("Model artifacts are not installed", 503),
    });
    await r.loop.start();
    await r.time.advance(600_000);
    expect(r.api.create).not.toHaveBeenCalled();
    expect(r.api.infer).not.toHaveBeenCalled();
    expect(r.get()).toMatchObject({
      running: false,
      busy: false,
      fault: {
        phase: "setup",
        category: "models_unavailable",
        stopped: true,
        requestId: null,
      },
    });
    expect(r.time.pending).toBe(0);
  });

  it("Retry re-runs the setup, and monitoring starts once the deployment is fixed", async () => {
    const r = rig({
      modelsError: new ApiError("Model artifacts are not installed", 503),
    });
    await r.loop.start();
    r.state.modelsError = undefined; // the operator fixed the deployment
    await r.loop.retry();
    await r.time.advance(0);
    expect(r.api.create).toHaveBeenCalledTimes(1);
    expect(r.api.infer).toHaveBeenCalledTimes(1);
    expect(r.get().fault).toBeNull();
    expect(r.get().running).toBe(true);
  });

  it("a setup that never answers hits its 15 s deadline and stops as a timeout", async () => {
    const r = rig({ modelsHang: true });
    const starting = r.loop.start();
    await r.time.advance(14_999);
    expect(r.get().fault).toBeNull();
    expect(r.get().busy).toBe(true);
    await r.time.advance(1);
    await starting;
    expect(r.get()).toMatchObject({
      busy: false,
      running: false,
      fault: { phase: "setup", category: "timeout", stopped: true },
    });
    expect(r.api.create).not.toHaveBeenCalled();
  });
});

describe("manual retry (T3)", () => {
  it("re-sends the SAME payload once, resumes the SAME session, and numbers the delivery 4", async () => {
    const committed = makeRecord("fresh", "fresh", 1);
    const r = rig({
      script: [...threeTransportErrors(), "ok"],
      saved: [committed],
    });
    await r.begin();
    await r.time.advance(6000);
    expect(r.get().fault).toMatchObject({ stopped: true, retryCount: 3 });
    expect(r.api.create).toHaveBeenCalledTimes(1);
    expect(r.api.session).not.toHaveBeenCalled();

    await r.loop.retry();
    await r.time.advance(0);

    expect(r.api.infer).toHaveBeenCalledTimes(4);
    expect(r.calls[3].attemptIndex).toBe(4);
    expect(r.calls[3].body).toBe(r.calls[0].body);
    expect(r.calls[3].payload.request_id).toBe("req-1");
    expect(r.calls[3].sid).toBe("sess-1");
    // Same session: no new create; the reconcile path ran exactly once.
    expect(r.api.create).toHaveBeenCalledTimes(1);
    expect(r.api.session).toHaveBeenCalledTimes(1);
    expect(r.api.latest).toHaveBeenCalledTimes(1);
    expect(r.api.windows).toHaveBeenCalledTimes(1);
    // The window the interrupted attempts may have committed appears exactly once.
    expect(r.get().history.map((rec) => rec.window_id)).toEqual([1]);
    expect(r.get().sessionId).toBe("sess-1");
  });

  it("on success the fault is gone and the loop resumes at the configured interval", async () => {
    const r = rig({ script: [...threeTransportErrors(), "ok"] });
    await r.begin();
    await r.time.advance(6000);
    await r.loop.retry();
    await r.time.advance(0);
    expect(r.get().fault).toBeNull();
    expect(r.get().running).toBe(true);
    expect(r.get().retrying).toBe(false);

    await r.time.advance(499);
    expect(r.api.infer).toHaveBeenCalledTimes(4);
    await r.time.advance(1);
    expect(r.api.infer).toHaveBeenCalledTimes(5);
    // A new logical request starts counting from 1 again.
    expect(r.calls[4].payload.request_id).toBe("req-2");
    expect(r.calls[4].attemptIndex).toBe(1);
  });

  it("on failure it stays stopped, shows the new count, and does not retry by itself", async () => {
    const r = rig({
      script: [...threeTransportErrors(), transportError(), "ok"],
    });
    await r.begin();
    await r.time.advance(6000);
    await r.loop.retry();
    await r.time.advance(600_000);

    expect(r.api.infer).toHaveBeenCalledTimes(4);
    expect(r.time.pending).toBe(0);
    expect(r.get().running).toBe(false);
    expect(r.get().retrying).toBe(false);
    expect(r.get().fault).toMatchObject({
      category: "transport",
      stopped: true,
      retryCount: 4,
      attemptIndex: 4,
    });

    // The next manual retry carries on counting: 5, never back to 1.
    await r.loop.retry();
    await r.time.advance(0);
    expect(r.calls.map((c) => c.attemptIndex)).toEqual([1, 2, 3, 4, 5]);
    expect(new Set(r.calls.map((c) => c.body)).size).toBe(1);
    expect(r.get().fault).toBeNull();
  });

  it("a manual retry that fails with a retryable error still schedules no automatic retry", async () => {
    // Stopped after ONE delivery (422), so the budget of 3 is not spent: only the
    // 'manual' rule keeps the failed retry from being retried automatically.
    const r = rig({
      script: [new ApiError("Bad Request", 400), transportError(), "ok"],
    });
    await r.begin();
    expect(r.get().fault).toMatchObject({ stopped: true, retryCount: 1 });
    await r.loop.retry();
    await r.time.advance(600_000);
    expect(r.api.infer).toHaveBeenCalledTimes(2);
    expect(r.time.pending).toBe(0);
    expect(r.get().fault).toMatchObject({
      category: "transport",
      stopped: true,
      retryCount: 2,
      attemptIndex: 2,
    });
    expect(r.get().running).toBe(false);
  });

  it("does nothing when there is no stopped fault", async () => {
    const r = rig();
    await r.begin();
    const before = r.api.infer.mock.calls.length;
    await r.loop.retry();
    await r.time.advance(0);
    expect(r.api.infer.mock.calls.length).toBe(before);
    expect(r.api.session).not.toHaveBeenCalled();
  });

  it("after a 404 it creates a new session instead, and later requests use it", async () => {
    const r = rig({ script: [new ApiError("session not found", 404)] });
    await r.begin();
    expect(r.api.create).toHaveBeenCalledTimes(1);
    expect(r.get().fault).toMatchObject({
      category: "not_found",
      newSessionOnRetry: true,
    });

    await r.loop.retry();
    await r.time.advance(0);
    expect(r.api.create).toHaveBeenCalledTimes(2);
    expect(r.api.session).not.toHaveBeenCalled();
    expect(r.get().sessionId).toBe("sess-2");
    expect(r.calls.map((c) => c.sid)).toEqual(["sess-1", "sess-2"]);
    expect(r.get().fault).toBeNull();
  });

  it("if the reconcile itself fails, the loop stays stopped and says why", async () => {
    const r = rig({ script: threeTransportErrors() });
    await r.begin();
    await r.time.advance(6000);
    r.api.session.mockRejectedValueOnce(new ApiError("session not found", 404));
    await r.loop.retry();
    await r.time.advance(0);
    expect(r.api.infer).toHaveBeenCalledTimes(3);
    expect(r.get().fault).toMatchObject({
      category: "not_found",
      stopped: true,
      newSessionOnRetry: true,
    });
    expect(r.get().retrying).toBe(false);
  });
});

describe("after a stop", () => {
  it("a pause keeps the stop panel and the frozen request, so Retry still works afterwards", async () => {
    const r = rig({ script: [...threeTransportErrors(), "ok"] });
    await r.begin();
    await r.time.advance(6000);
    r.loop.pause();
    expect(r.get().fault).toMatchObject({ stopped: true, retryCount: 3 });
    await r.loop.retry();
    await r.time.advance(0);
    expect(r.calls[3].attemptIndex).toBe(4);
    expect(r.calls[3].body).toBe(r.calls[0].body);
    expect(r.get().fault).toBeNull();
  });

  it("while a retry is reconciling it is busy, and a second click does nothing", async () => {
    const r = rig({ script: [...threeTransportErrors(), "ok"] });
    await r.begin();
    await r.time.advance(6000);
    let release: (meta: SessionMeta) => void = () => undefined;
    r.api.session.mockImplementationOnce(
      () =>
        new Promise<SessionMeta>((resolve) => {
          release = resolve;
        }),
    );
    const first = r.loop.retry();
    await r.time.advance(0);
    expect(r.get().retrying).toBe(true);
    await r.loop.retry();
    expect(r.api.session).toHaveBeenCalledTimes(1);
    release({
      id: "sess-1",
      created_at: "2026-01-01T12:00:00+00:00",
      total_windows: 0,
    });
    await first;
    await r.time.advance(0);
    expect(r.api.infer).toHaveBeenCalledTimes(4); // exactly one extra delivery
    expect(r.get().retrying).toBe(false);
  });

  it("Start Monitoring clears the panel and begins a FRESH request on the same session", async () => {
    const r = rig({ script: threeTransportErrors() });
    await r.begin();
    await r.time.advance(6000);
    expect(r.get().fault?.stopped).toBe(true);
    const starting = r.loop.start();
    // The old panel is gone as soon as the new run begins, not only once it succeeds.
    expect(r.get().fault).toBeNull();
    expect(r.get().busy).toBe(true);
    await starting;
    await r.time.advance(0);
    expect(r.get().fault).toBeNull();
    expect(r.calls[3].payload.request_id).toBe("req-2");
    expect(r.calls[3].attemptIndex).toBe(1);
    expect(r.api.create).toHaveBeenCalledTimes(1);
    expect(r.api.session).toHaveBeenCalledTimes(1);
  });
});

describe("the camera never stops the loop (R5)", () => {
  it("a null frame is sent anyway, without image or captured_at, and is not a failure", async () => {
    const r = rig({ frame: "none" });
    await r.begin();
    expect(r.api.infer).toHaveBeenCalledTimes(1);
    expect(r.calls[0].payload).toMatchObject({
      image_base64: null,
      captured_at: null,
      telemetry_features: TELEMETRY,
      telemetry_source: "prepared_replay",
    });
    expect(r.get().fault).toBeNull();
    expect(r.get().running).toBe(true);
    // The next tick is scheduled at the configured interval.
    await r.time.advance(499);
    expect(r.api.infer).toHaveBeenCalledTimes(1);
    await r.time.advance(1);
    expect(r.api.infer).toHaveBeenCalledTimes(2);
  });

  it("any number of frame-less ticks never add up to a stop; the reason is recorded for display only", async () => {
    const r = rig({ frame: "none", missReason: "device_disconnected" });
    await r.begin();
    await r.time.advance(5000);
    expect(r.api.infer).toHaveBeenCalledTimes(11);
    expect(r.get().running).toBe(true);
    expect(r.get().fault).toBeNull();
    expect(r.get().imagelessRequests).toBe(11);
    expect(r.get().lastCaptureMiss).toBe("device_disconnected");
  });

  it("with neither image nor telemetry the request is still sent, and its UNAVAILABLE window joins the history", async () => {
    const r = rig({ frame: "none", telemetry: false, script: ["unavailable"] });
    await r.begin();
    expect(r.calls[0].payload).toEqual({
      request_id: "req-1",
      image_base64: null,
      captured_at: null,
      telemetry_features: null,
      telemetry_timestamp: null,
      telemetry_source: "missing",
    });
    const [record] = r.get().history;
    expect(record.assessment_available).toBe(false);
    expect(record.RiskScore).toBeNull();
    expect(record.SystemHealth).toBe("UNAVAILABLE");
    expect(r.get().running).toBe(true);
    expect(r.get().fault).toBeNull();
    await r.time.advance(500);
    expect(r.api.infer).toHaveBeenCalledTimes(2);
  });

  it("a camera that throws is a camera without a frame, not a dead loop", async () => {
    const r = rig({ frame: "throws" });
    await r.begin();
    expect(r.calls[0].payload.image_base64).toBeNull();
    expect(r.get().fault).toBeNull();
    expect(r.get().running).toBe(true);
    expect(r.get().lastCaptureMiss).toBe("capture_error");
  });

  it("the miss is forgotten as soon as a frame is back", async () => {
    const r = rig({ frame: "none" });
    await r.begin();
    expect(r.get().lastCaptureMiss).toBe("stopped_by_user");
    r.captureFrame.mockReturnValue({
      image_base64: "frame-back",
      captured_at: new Date(r.time.now).toISOString(),
    });
    await r.time.advance(500);
    expect(r.get().lastCaptureMiss).toBeNull();
    expect(r.calls[1].payload.image_base64).toBe("frame-back");
  });
});

describe("saved sessions and the store contract", () => {
  it("loadSession shows a saved session read-only; Start then creates a new one", async () => {
    const saved = [
      makeRecord("fresh", "fresh", 1),
      makeRecord("fresh", "fresh", 2),
    ];
    const r = rig({ saved });
    await r.begin(); // a live session (sess-1) exists first
    r.loop.pause();
    expect(await r.loop.loadSession("old-1")).toBeNull();
    expect(r.get()).toMatchObject({
      sessionId: "old-1",
      total: 2,
      running: false,
      busy: false,
    });
    expect(r.get().history.map((rec) => rec.window_id)).toEqual([1, 2]);
    await r.begin();
    // Not a resume of sess-1 and never of the historical one: a NEW session.
    expect(r.api.create).toHaveBeenCalledTimes(2);
    expect(r.get().sessionId).toBe("sess-2");
  });

  it("loadSession reports a failure as a message and leaves the display alone", async () => {
    const r = rig();
    r.api.session.mockRejectedValueOnce(new Error("Cannot load session"));
    expect(await r.loop.loadSession("old-1")).toBe("Cannot load session");
    expect(r.get().sessionId).toBe("");
    expect(r.get().busy).toBe(false);
  });

  it("replaceRecord swaps one window by id (a flag toggle) and touches nothing else", async () => {
    const r = rig();
    await r.begin();
    await r.time.advance(500);
    expect(r.get().history.map((rec) => rec.window_id)).toEqual([1, 2]);
    r.loop.replaceRecord({ ...r.get().history[0], flagged: true });
    expect(r.get().history.map((rec) => rec.flagged)).toEqual([
      true,
      undefined,
    ]);
    r.loop.replaceRecord(makeRecord("fresh", "fresh", 99));
    expect(r.get().history.map((rec) => rec.window_id)).toEqual([1, 2]);
  });

  it("getState is stable between changes and subscribe notifies on each change", async () => {
    const r = rig();
    expect(r.get()).toBe(r.get());
    const listener = vi.fn();
    const unsubscribe = r.loop.subscribe(listener);
    await r.begin();
    expect(listener).toHaveBeenCalled();
    unsubscribe();
    listener.mockClear();
    await r.time.advance(2000);
    expect(listener).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
// The loop wired to the REAL api client, with only `fetch` replaced: this is the
// one place that proves what actually goes over the wire.
// ---------------------------------------------------------------------------
describe("wired to the real api client", () => {
  afterEach(() => vi.unstubAllGlobals());

  const json = (body: unknown, status = 200) =>
    new Response(JSON.stringify(body), {
      status,
      headers: { "Content-Type": "application/json" },
    });

  it("every delivery carries X-Attempt-Index (1, 2, 3, then 4 for the manual retry) and the same body", async () => {
    const answers: Array<"network" | RiskUpdate> = [
      "network",
      "network",
      "network",
      makeRecord("fresh", "fresh", 1),
    ];
    const requests: {
      url: string;
      method: string;
      headers: Record<string, string>;
      body?: string;
    }[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init: RequestInit = {}) => {
        requests.push({
          url,
          method: init.method ?? "GET",
          headers: (init.headers ?? {}) as Record<string, string>,
          body: init.body as string | undefined,
        });
        if (url === "/api/models")
          return json({ models_loaded: true, provider: "stub" });
        if (url === "/api/sessions" && init.method === "POST")
          return json(
            {
              id: "s-1",
              created_at: "2026-01-01T12:00:00+00:00",
              total_windows: 0,
            },
            201,
          );
        if (url === "/api/sessions/s-1/infer") {
          const next = answers.shift();
          if (next === "network") throw new TypeError("Failed to fetch");
          return json(next, 201);
        }
        if (url === "/api/sessions/s-1")
          return json({
            id: "s-1",
            created_at: "2026-01-01T12:00:00+00:00",
            total_windows: 0,
          });
        throw new Error(`unexpected request ${url}`);
      }),
    );
    const time = new FakeTime();
    let ids = 0;
    const loop = createLiveLoop({
      api: realApi,
      policy: RETRY_POLICY,
      getConfig: () => CONFIG,
      captureFrame: () => ({
        image_base64: "data:image/jpeg;base64,AAAA",
        captured_at: new Date(time.now).toISOString(),
      }),
      telemetryAt: () => TELEMETRY,
      newRequestId: () => `wire-${++ids}`,
      now: () => time.now,
      timers: time,
    });

    await loop.start();
    await time.advance(6000);
    expect(loop.getState().fault).toMatchObject({
      stopped: true,
      retryCount: 3,
    });
    await loop.retry();
    await time.advance(0);

    const infers = requests.filter((q) => q.url === "/api/sessions/s-1/infer");
    expect(infers).toHaveLength(4);
    expect(infers.map((q) => q.method)).toEqual([
      "POST",
      "POST",
      "POST",
      "POST",
    ]);
    expect(infers.map((q) => q.headers["X-Attempt-Index"])).toEqual([
      "1",
      "2",
      "3",
      "4",
    ]);
    expect(new Set(infers.map((q) => q.body)).size).toBe(1);
    expect(JSON.parse(infers[0].body ?? "{}").request_id).toBe("wire-1");
    expect(loop.getState().fault).toBeNull();
    // The manual retry reconciled the same session and never created another.
    expect(
      requests.filter((q) => q.url === "/api/sessions" && q.method === "POST"),
    ).toHaveLength(1);
    expect(requests.filter((q) => q.url === "/api/sessions/s-1")).toHaveLength(
      1,
    );
  });
});
