import { afterEach, describe, expect, it, vi } from "vitest";

import { api as realApi, ApiError } from "../../frontend/src/api/client";
import { RETRY_POLICY, faultAdvice } from "../../frontend/src/api/retryPolicy";
import {
  PREPARED_RAW_TELEMETRY,
  createPreparedTelemetryCursor,
  type PreparedRawTelemetryRow,
} from "../../frontend/src/data/preparedSessionInput";
import { makeRecord } from "../../frontend/src/testing/records";
import {
  createLiveLoop,
  type LiveFrame,
  type LiveLoopApi,
  type LivePayload,
  type TelemetrySource,
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

// The cursor behind tests that are not about the cursor: every sequence number reads
// the same row, either a sample or a row with no telemetry.
const constantRows = (
  features: TelemetryFeatures | null,
): PreparedRawTelemetryRow[] => [
  { timestamp: "", telemetry_features: features, telemetry_age_s: 0 },
];

type Step = "ok" | "unavailable" | "hang" | "deferred" | Error;
type Models = { ready: boolean };

interface RigOptions {
  /** What successive `infer` calls do. Once exhausted, every call succeeds. */
  script?: Step[];
  /**
   * `camera`: frames with an explicit (epoch, index). `fallback`: frames with no
   * identity, timed by the page clock. `none`: no frame. `throws`: the camera throws.
   */
  frame?: "camera" | "fallback" | "none" | "throws";
  telemetry?: boolean;
  /** Replaces the constant rows the cursor reads. */
  telemetryRows?: PreparedRawTelemetryRow[];
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
    if (options.frame === "fallback")
      return {
        image_base64: `frame-${frames}`,
        captured_at: new Date(time.now).toISOString(),
        captured_at_source: "client_clock",
      };
    return {
      image_base64: `frame-${frames}`,
      captured_at: new Date(time.now).toISOString(),
      captured_at_source: "callback",
      vision_frame: { epoch: 1000, index: frames },
    };
  });
  // The REAL cursor on a table the test chose, wrapped in spies so a test can count
  // how often the loop resets, pauses, resumes and reads it.
  const cursor = createPreparedTelemetryCursor(
    options.telemetryRows ??
      constantRows(options.telemetry === false ? null : TELEMETRY),
  );
  const telemetry = {
    reset: vi.fn((nowMs: number) => cursor.reset(nowMs)),
    pause: vi.fn((nowMs: number) => cursor.pause(nowMs)),
    resume: vi.fn((nowMs: number) => cursor.resume(nowMs)),
    read: vi.fn((nowMs: number) => cursor.read(nowMs)),
  } satisfies TelemetrySource;
  const newRequestId = vi.fn(() => `req-${++requestIds}`);
  const loop = createLiveLoop<Models>({
    api: api as LiveLoopApi<Models>,
    policy: RETRY_POLICY,
    getConfig: () => CONFIG,
    captureFrame,
    captureMissReason: () => options.missReason ?? "stopped_by_user",
    telemetry,
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
    telemetry,
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
    [
      new ApiError(
        "Observation identity already registered with different content or acquisition time",
        409,
      ),
      "observation_conflict",
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
      captured_at_source: "callback",
      vision_frame: { epoch: 1000, index: 1 },
      telemetry_features: TELEMETRY,
      telemetry_seq: 0,
      telemetry_source: "prepared_replay",
    });
    // The frame, the telemetry and the id were produced once, not once per delivery.
    expect(r.captureFrame).toHaveBeenCalledTimes(1);
    expect(r.telemetry.read).toHaveBeenCalledTimes(1);
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

describe("a New Session that fails in setup keeps its intent (H1)", () => {
  it("api.create failing while another session runs: Retry creates the NEW session, it does not resume the running one", async () => {
    const r = rig();
    await r.begin();
    expect(r.get().sessionId).toBe("sess-1");
    expect(r.api.create).toHaveBeenCalledTimes(1);

    // The user clicks New Session while sess-1 is running, and create fails.
    r.api.create.mockRejectedValueOnce(transportError());
    await r.loop.start(true);
    expect(r.api.create).toHaveBeenCalledTimes(2);
    expect(r.get()).toMatchObject({
      running: false,
      busy: false,
      sessionId: "sess-1",
      fault: {
        phase: "setup",
        category: "transport",
        stopped: true,
        newSessionOnRetry: true,
      },
    });

    const inferBefore = r.api.infer.mock.calls.length;
    await r.loop.retry();
    await r.time.advance(0);
    // A third create, no reconcile of sess-1, and the data goes to the new session.
    expect(r.api.create).toHaveBeenCalledTimes(3);
    expect(r.api.session).not.toHaveBeenCalled();
    expect(r.get().sessionId).toBe("sess-2");
    expect(r.get().fault).toBeNull();
    expect(r.get().running).toBe(true);
    expect(r.calls.slice(inferBefore).map((c) => c.sid)).toEqual(["sess-2"]);
  });

  it("the same when the failure came earlier, in the model check", async () => {
    const r = rig();
    await r.begin();
    r.state.modelsError = new ApiError(
      "Model artifacts are not installed",
      503,
    );
    await r.loop.start(true);
    expect(r.api.create).toHaveBeenCalledTimes(1);
    expect(r.get().fault).toMatchObject({
      phase: "setup",
      category: "models_unavailable",
      newSessionOnRetry: true,
    });

    r.state.modelsError = undefined; // the operator fixed the deployment
    await r.loop.retry();
    await r.time.advance(0);
    expect(r.api.create).toHaveBeenCalledTimes(2);
    expect(r.api.session).not.toHaveBeenCalled();
    expect(r.get().sessionId).toBe("sess-2");
    expect(r.get().running).toBe(true);
  });

  it("a plain Start that fails to resume keeps its session: Retry resumes it, it creates nothing", async () => {
    const r = rig();
    await r.begin();
    r.loop.pause();
    r.api.session.mockRejectedValueOnce(new ApiError("Bad Gateway", 502));
    await r.loop.start();
    expect(r.get().fault).toMatchObject({
      phase: "setup",
      category: "storage",
      stopped: true,
      newSessionOnRetry: false,
    });

    const inferBefore = r.api.infer.mock.calls.length;
    await r.loop.retry();
    await r.time.advance(0);
    expect(r.api.create).toHaveBeenCalledTimes(1);
    expect(r.api.session).toHaveBeenCalledTimes(2);
    expect(r.get().sessionId).toBe("sess-1");
    expect(r.get().running).toBe(true);
    expect(r.calls.slice(inferBefore).map((c) => c.sid)).toEqual(["sess-1"]);
  });
});

describe("a failed New Session leaves the running session in place (H1)", () => {
  it("a plain Start after the failure resumes that session instead of creating one", async () => {
    const r = rig();
    await r.begin();
    r.api.create.mockRejectedValueOnce(transportError());
    await r.loop.start(true);
    expect(r.get().fault?.stopped).toBe(true);

    const inferBefore = r.api.infer.mock.calls.length;
    await r.loop.start();
    await r.time.advance(0);
    expect(r.api.create).toHaveBeenCalledTimes(2); // the first start and the failed one
    expect(r.api.session).toHaveBeenCalledTimes(1);
    expect(r.get().sessionId).toBe("sess-1");
    expect(r.calls.slice(inferBefore).map((c) => c.sid)).toEqual(["sess-1"]);
  });
});

describe("the stop panel's delivery counts (H4)", () => {
  it("an automatic stop has used 3 deliveries and no manual one", async () => {
    const r = rig({ script: threeTransportErrors() });
    await r.begin();
    await r.time.advance(6000);
    expect(r.get().fault).toMatchObject({
      stopped: true,
      retryCount: 3,
      manualRetries: 0,
    });
  });

  it("while automatic retries are pending no manual delivery has happened", async () => {
    const r = rig({ script: threeTransportErrors() });
    await r.begin();
    expect(r.get().fault).toMatchObject({
      stopped: false,
      retryCount: 1,
      manualRetries: 0,
    });
  });

  it("each failed manual retry adds one manual delivery on top of the 3 automatic ones", async () => {
    const r = rig({
      script: [...threeTransportErrors(), transportError(), transportError()],
    });
    await r.begin();
    await r.time.advance(6000);
    await r.loop.retry();
    await r.time.advance(0);
    expect(r.get().fault).toMatchObject({ retryCount: 4, manualRetries: 1 });
    await r.loop.retry();
    await r.time.advance(0);
    expect(r.get().fault).toMatchObject({ retryCount: 5, manualRetries: 2 });
  });

  it("a 400 stops after ONE automatic delivery; a failed manual retry is the second delivery and the first manual one", async () => {
    const r = rig({
      script: [
        new ApiError("Bad Request", 400),
        new ApiError("Bad Request", 400),
        new ApiError("Bad Request", 400),
      ],
    });
    await r.begin();
    expect(r.get().fault).toMatchObject({
      stopped: true,
      retryCount: 1,
      manualRetries: 0,
    });
    await r.loop.retry();
    await r.time.advance(0);
    expect(r.get().fault).toMatchObject({
      stopped: true,
      retryCount: 2,
      manualRetries: 1,
    });
    await r.loop.retry();
    await r.time.advance(0);
    expect(r.get().fault).toMatchObject({
      stopped: true,
      retryCount: 3,
      manualRetries: 2,
    });
  });

  it("a reconcile that fails before the manual delivery adds no manual delivery", async () => {
    const r = rig({
      script: [
        new ApiError("Bad Request", 400),
        new ApiError("Bad Request", 400),
      ],
    });
    await r.begin();
    r.api.session.mockRejectedValueOnce(new ApiError("Bad Gateway", 502));
    await r.loop.retry();
    await r.time.advance(0);
    expect(r.api.infer).toHaveBeenCalledTimes(1);
    expect(r.get().fault).toMatchObject({
      stopped: true,
      retryCount: 1,
      manualRetries: 0,
    });
    // The next retry does deliver, and fails: that is the first manual delivery.
    await r.loop.retry();
    await r.time.advance(0);
    expect(r.api.infer).toHaveBeenCalledTimes(2);
    expect(r.get().fault).toMatchObject({
      stopped: true,
      retryCount: 2,
      manualRetries: 1,
    });
  });
});

// R10-B (B5, Task 9 leftover). A Retry that fails while it RECONCILES sends nothing, so
// `manualRetries` stays where it was and the stop panel kept saying "re-sent
// automatically" about a request nobody re-sent. The fault now records that the failure
// came from the manual retry.
describe("a failed manual retry is told apart from a spent automatic budget (B5)", () => {
  const serverError = () => new ApiError("Internal Server Error", 500);
  const threeServerErrors = (): Step[] => [
    serverError(),
    serverError(),
    serverError(),
  ];
  const AUTOMATIC =
    "A model or storage error on the server (HTTP 500). The request was re-sent automatically and kept failing.";
  const MANUAL =
    "A model or storage error on the server (HTTP 500). The retry you triggered failed as well.";

  it("the loop's own stop is not from a manual retry, and says so in its advice", async () => {
    const r = rig({ script: threeServerErrors() });
    await r.begin();
    await r.time.advance(6000);
    const fault = r.get().fault;
    expect(fault).toMatchObject({
      category: "model_runtime",
      stopped: true,
      retryCount: 3,
      manualRetries: 0,
      fromManualRetry: false,
    });
    expect(faultAdvice(fault!)).toBe(AUTOMATIC);
  });

  it("a reconcile that fails during Retry marks the fault, and no delivery was added", async () => {
    const r = rig({ script: threeServerErrors() });
    await r.begin();
    await r.time.advance(6000);
    r.api.session.mockRejectedValueOnce(serverError());
    await r.loop.retry();
    await r.time.advance(0);
    const fault = r.get().fault;
    expect(r.api.infer).toHaveBeenCalledTimes(3); // nothing was re-sent
    expect(fault).toMatchObject({
      category: "model_runtime",
      stopped: true,
      retryCount: 3,
      manualRetries: 0,
      fromManualRetry: true,
    });
    // The category is the same as before; only the reason differs, and so does the advice.
    expect(faultAdvice(fault!)).toBe(MANUAL);
  });

  it("a manual delivery that fails is from the manual retry too", async () => {
    const r = rig({ script: [...threeServerErrors(), serverError()] });
    await r.begin();
    await r.time.advance(6000);
    await r.loop.retry();
    await r.time.advance(0);
    expect(r.get().fault).toMatchObject({
      stopped: true,
      retryCount: 4,
      manualRetries: 1,
      fromManualRetry: true,
    });
    expect(faultAdvice(r.get().fault!)).toBe(MANUAL);
  });

  it("the mark does not outlive the stop: after Start Monitoring a new automatic stop is the loop's own again", async () => {
    const r = rig({ script: threeServerErrors() });
    await r.begin();
    await r.time.advance(6000);
    r.api.session.mockRejectedValueOnce(serverError());
    await r.loop.retry();
    await r.time.advance(0);
    expect(r.get().fault?.fromManualRetry).toBe(true);

    r.api.infer.mockRejectedValueOnce(serverError());
    r.api.infer.mockRejectedValueOnce(serverError());
    r.api.infer.mockRejectedValueOnce(serverError());
    await r.loop.start();
    await r.time.advance(6000);
    expect(r.get().fault).toMatchObject({
      stopped: true,
      retryCount: 3,
      manualRetries: 0,
      fromManualRetry: false,
    });
    expect(faultAdvice(r.get().fault!)).toBe(AUTOMATIC);
  });

  it("a setup fault is not from a manual retry", async () => {
    const r = rig({
      modelsError: new ApiError("Model artifacts are not installed", 503),
    });
    await r.loop.start();
    expect(r.get().fault).toMatchObject({
      phase: "setup",
      fromManualRetry: false,
    });
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

  it("a delivery counts when it is SENT: a manual one that a pause cancelled in flight is still in retryCount / manualRetries (K8)", async () => {
    // Three automatic failures stop the loop; Retry sends delivery 4, which hangs;
    // the user pauses (cancelling it); Retry again sends delivery 5, which fails.
    // The panel's counts are deliveries sent (5, 2 of them manual), not failures (4).
    const r = rig({
      script: [...threeTransportErrors(), "hang", transportError()],
    });
    await r.begin();
    await r.time.advance(6000);
    expect(r.get().fault).toMatchObject({ retryCount: 3, manualRetries: 0 });

    const firstRetry = r.loop.retry();
    await r.time.advance(0);
    expect(r.calls.map((c) => c.attemptIndex)).toEqual([1, 2, 3, 4]);
    r.loop.pause(); // cancels delivery 4 in flight; the stop panel and request stay
    await firstRetry;
    expect(r.get().fault).toMatchObject({ stopped: true, retryCount: 3 });

    await r.loop.retry();
    await r.time.advance(0);
    expect(r.calls.map((c) => c.attemptIndex)).toEqual([1, 2, 3, 4, 5]);
    expect(r.get().fault).toMatchObject({
      stopped: true,
      retryCount: 5,
      manualRetries: 2,
      attemptIndex: 5,
    });
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
    expect(r.calls[0].payload).toStrictEqual({
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
      captured_at_source: "callback",
      vision_frame: { epoch: 1000, index: 9 },
    });
    await r.time.advance(500);
    expect(r.get().lastCaptureMiss).toBeNull();
    expect(r.calls[1].payload.image_base64).toBe("frame-back");
  });
});

// Task 9 / K2, rewritten for R10. R5 says the loop never skips a tick: when the cursor
// lands on a row with no telemetry (rows 14 and 17 of the 25) the request is still sent,
// with `telemetry_features: null` / `telemetry_source: "missing"` - and, since R10, with
// NO `telemetry_seq` (the server answers 422 to a sequence number without telemetry).
// These tests drive the PRODUCTION cursor and the real prepared rows through the loop, so
// a loop (or a cursor) that skipped or stopped on those rows is caught on the real data,
// not on a stand-in. 2 inferences per second and an instant API: tick i happens at
// i x 500 ms, so it reads sequence floor(i / 4) = row floor(i / 4) + 1 (one row per 2000
// ms), and that sample's time is the session start + floor(i / 4) x 2000 ms, whatever
// moment inside the slot the tick fell on.
describe("the prepared telemetry cursor never skips or stops the loop (R5 on the real rows)", () => {
  const TICKS_PER_CYCLE = 100; // 25 rows x 2000 ms / 500 ms
  // Ticks on row 14 are 52..55 and on row 17 are 64..67 (0-based tick numbers).
  const MISSING_TICKS = [52, 53, 54, 55, 64, 65, 66, 67];
  const SESSION_START = "2026-01-01T12:00:00.000Z";

  const runOneCycle = async (frame: "camera" | "none") => {
    const r = rig({ frame, telemetryRows: PREPARED_RAW_TELEMETRY });
    await r.begin();
    await r.time.advance(49_500);
    return r;
  };

  it("with the camera on, every tick of a full 50 s cycle is sent - including rows 14 and 17", async () => {
    const r = await runOneCycle("camera");
    expect(r.calls).toHaveLength(TICKS_PER_CYCLE);
    r.calls.forEach((call, tick) => {
      if (MISSING_TICKS.includes(tick)) {
        expect(call.payload).toMatchObject({
          telemetry_features: null,
          telemetry_timestamp: null,
          telemetry_source: "missing",
          image_base64: `frame-${tick + 1}`,
        });
        expect("telemetry_seq" in call.payload).toBe(false);
      } else {
        expect(call.payload.telemetry_source).toBe("prepared_replay");
        expect(call.payload.telemetry_features).not.toBeNull();
        expect(call.payload.telemetry_seq).toBe(Math.floor(tick / 4));
        expect(call.payload.telemetry_timestamp).toBe(
          new Date(
            Date.parse(SESSION_START) + Math.floor(tick / 4) * 2000,
          ).toISOString(),
        );
      }
    });
    // ...and the loop is still up at the end: nothing counted, nothing stopped.
    expect(r.get().running).toBe(true);
    expect(r.get().fault).toBeNull();
    expect(r.get().history).toHaveLength(TICKS_PER_CYCLE);
  });

  it("pins sequence numbers and times at hand-computed ticks", async () => {
    const r = await runOneCycle("camera");
    const at = (tick: number) => [
      r.calls[tick].payload.telemetry_seq,
      r.calls[tick].payload.telemetry_timestamp,
    ];
    expect(at(0)).toEqual([0, "2026-01-01T12:00:00.000Z"]);
    expect(at(3)).toEqual([0, "2026-01-01T12:00:00.000Z"]); // 1500 ms in: still the first sample
    expect(at(4)).toEqual([1, "2026-01-01T12:00:02.000Z"]);
    expect(at(51)).toEqual([12, "2026-01-01T12:00:24.000Z"]); // row 13, 25.5 s
    expect(at(56)).toEqual([14, "2026-01-01T12:00:28.000Z"]); // row 15, 28 s
    expect(at(99)).toEqual([24, "2026-01-01T12:00:48.000Z"]); // the last row, 49.5 s
  });

  it("the tick after row 14 is back on real telemetry (the loop recovers by itself)", async () => {
    const r = await runOneCycle("camera");
    expect(r.calls[51].payload.telemetry_features).not.toBeNull(); // row 13
    expect(r.calls[55].payload.telemetry_features).toBeNull(); // row 14
    expect(r.calls[56].payload.telemetry_features).not.toBeNull(); // row 15
    expect(r.calls[63].payload.telemetry_features).not.toBeNull(); // row 16
    expect(r.calls[64].payload.telemetry_features).toBeNull(); // row 17
    expect(r.calls[68].payload.telemetry_features).not.toBeNull(); // row 18
  });

  it("with the camera OFF the cycle is just as complete: rows 14 and 17 send neither image nor telemetry", async () => {
    const r = await runOneCycle("none");
    expect(r.calls).toHaveLength(TICKS_PER_CYCLE);
    r.calls.forEach((call, tick) => {
      expect(call.payload.image_base64).toBeNull();
      expect(call.payload.captured_at).toBeNull();
      expect("vision_frame" in call.payload).toBe(false);
      expect("captured_at_source" in call.payload).toBe(false);
      expect(call.payload.telemetry_features === null).toBe(
        MISSING_TICKS.includes(tick),
      );
    });
    expect(r.get().running).toBe(true);
    expect(r.get().fault).toBeNull();
    expect(r.get().imagelessRequests).toBe(TICKS_PER_CYCLE);
  });

  it("the cycle wraps in ROWS but not in sequence numbers: the next cycle's first tick is row 1 again, as sequence 25", async () => {
    const r = rig({ frame: "camera", telemetryRows: PREPARED_RAW_TELEMETRY });
    await r.begin();
    await r.time.advance(50_000);
    expect(r.calls).toHaveLength(TICKS_PER_CYCLE + 1);
    expect(r.calls[TICKS_PER_CYCLE].payload.telemetry_features).toEqual(
      r.calls[0].payload.telemetry_features,
    );
    // Sent as 25, not as 25 % 25: the server's identity is the number itself.
    expect(r.calls[0].payload.telemetry_seq).toBe(0);
    expect(r.calls[TICKS_PER_CYCLE].payload.telemetry_seq).toBe(25);
    expect(r.calls[TICKS_PER_CYCLE].payload.telemetry_timestamp).toBe(
      "2026-01-01T12:00:50.000Z",
    );
  });
});

// R10-B (B1, B3). The identity and the time of what a request carries.
describe("a request carries the observation identity and an arithmetic telemetry time (R10-B)", () => {
  it("every tick inside one 2000 ms slot sends the SAME sequence number and the SAME time; the next slot moves both", async () => {
    const r = rig();
    await r.begin();
    await r.time.advance(2000); // ticks at 0, 500, 1000, 1500, 2000
    expect(r.calls).toHaveLength(5);
    const samples = r.calls.map((call) => [
      call.payload.telemetry_seq,
      call.payload.telemetry_timestamp,
    ]);
    expect(samples).toEqual([
      [0, "2026-01-01T12:00:00.000Z"],
      [0, "2026-01-01T12:00:00.000Z"], // sent at +500 ms: the time is NOT the sending time
      [0, "2026-01-01T12:00:00.000Z"],
      [0, "2026-01-01T12:00:00.000Z"],
      [1, "2026-01-01T12:00:02.000Z"],
    ]);
    // Same sequence number, same bytes for the two fields the server compares.
    const field = (i: number) =>
      JSON.stringify([
        r.calls[i].payload.telemetry_seq,
        r.calls[i].payload.telemetry_timestamp,
        r.calls[i].payload.telemetry_features,
      ]);
    expect(field(1)).toBe(field(0));
    expect(field(3)).toBe(field(0));
  });

  it("the vision half of the request is the frame's own tuple: its time, its source and its (epoch, index)", async () => {
    const r = rig();
    await r.begin();
    await r.time.advance(500);
    expect(r.calls[1].payload).toMatchObject({
      image_base64: "frame-2",
      captured_at: "2026-01-01T12:00:00.500Z",
      captured_at_source: "callback",
      vision_frame: { epoch: 1000, index: 2 },
    });
  });

  it("a fallback frame (no identity) is sent with no vision_frame and its source client_clock", async () => {
    const r = rig({ frame: "fallback" });
    await r.begin();
    expect(r.calls[0].payload).toMatchObject({
      image_base64: "frame-1",
      captured_at: "2026-01-01T12:00:00.000Z",
      captured_at_source: "client_clock",
      telemetry_seq: 0,
    });
    expect("vision_frame" in r.calls[0].payload).toBe(false);
    // And on the wire: the key is absent, not null.
    expect(Object.keys(JSON.parse(r.calls[0].body)).sort()).toEqual([
      "captured_at",
      "captured_at_source",
      "image_base64",
      "request_id",
      "telemetry_features",
      "telemetry_seq",
      "telemetry_source",
      "telemetry_timestamp",
    ]);
  });

  it("no image: the request carries no vision_frame and no captured_at_source (the server answers 422 to a frame id without an image)", async () => {
    const r = rig({ frame: "none" });
    await r.begin();
    expect(Object.keys(JSON.parse(r.calls[0].body)).sort()).toEqual([
      "captured_at",
      "image_base64",
      "request_id",
      "telemetry_features",
      "telemetry_seq",
      "telemetry_source",
      "telemetry_timestamp",
    ]);
    expect(JSON.parse(r.calls[0].body)).toMatchObject({
      image_base64: null,
      captured_at: null,
      telemetry_seq: 0,
    });
  });

  it("null telemetry: the request carries no telemetry_seq (the server answers 422 to a sequence number without telemetry)", async () => {
    const r = rig({ telemetry: false });
    await r.begin();
    expect(Object.keys(JSON.parse(r.calls[0].body)).sort()).toEqual([
      "captured_at",
      "captured_at_source",
      "image_base64",
      "request_id",
      "telemetry_features",
      "telemetry_source",
      "telemetry_timestamp",
      "vision_frame",
    ]);
    expect(JSON.parse(r.calls[0].body)).toMatchObject({
      telemetry_features: null,
      telemetry_timestamp: null,
      telemetry_source: "missing",
      vision_frame: { epoch: 1000, index: 1 },
    });
  });

  it("a retry re-sends the first capture's tuple and sequence number byte for byte, and never reads the cursor again", async () => {
    const r = rig({ script: threeTransportErrors() });
    await r.begin();
    await r.time.advance(6000);
    expect(r.calls).toHaveLength(3);
    expect(r.calls[1].body).toBe(r.calls[0].body);
    expect(r.calls[2].body).toBe(r.calls[0].body);
    expect(r.calls[2].payload).toMatchObject({
      captured_at: "2026-01-01T12:00:00.000Z",
      vision_frame: { epoch: 1000, index: 1 },
      telemetry_seq: 0,
      telemetry_timestamp: "2026-01-01T12:00:00.000Z",
    });
    // 6 s later the wall clock is on sequence 3, but the retries did not look.
    expect(r.telemetry.read).toHaveBeenCalledTimes(1);

    await r.loop.retry(); // the manual delivery re-sends the same frozen request too
    await r.time.advance(0);
    expect(r.calls).toHaveLength(4);
    expect(r.calls[3].body).toBe(r.calls[0].body);
    expect(r.telemetry.read).toHaveBeenCalledTimes(1);
  });
});

describe("the telemetry cursor follows the session and the pauses (R10-B)", () => {
  it("a new session numbers its telemetry from 0 again, at the moment it began", async () => {
    const r = rig();
    await r.begin();
    await r.time.advance(5000); // sequence 2 by now
    expect(r.calls[r.calls.length - 1].payload.telemetry_seq).toBe(2);
    const before = r.calls.length;
    await r.loop.start(true); // New Session, 5 s in
    await r.time.advance(0);
    expect(r.calls[before].sid).toBe("sess-2");
    expect(r.calls[before].payload).toMatchObject({
      telemetry_seq: 0,
      telemetry_timestamp: "2026-01-01T12:00:05.000Z",
    });
  });

  it("a pause freezes the cursor and a resume opens a NEW observation one past it, timed at the moment of resuming", async () => {
    const r = rig();
    await r.begin();
    await r.time.advance(3000); // ticks up to +3000 ms: the cursor reached sequence 1
    expect(r.calls[r.calls.length - 1].payload.telemetry_seq).toBe(1);
    r.loop.pause();
    const sent = r.calls.length;
    await r.time.advance(600_000); // ten minutes of pause
    expect(r.calls).toHaveLength(sent); // nothing went out, nothing moved

    await r.loop.start(); // resume the same session at +603 s
    await r.time.advance(0);
    expect(r.calls[sent].sid).toBe("sess-1");
    expect(r.calls[sent].payload).toMatchObject({
      telemetry_seq: 2, // frozen at 1, plus one - not 301
      telemetry_timestamp: "2026-01-01T12:10:03.000Z", // the resume instant
    });
    await r.time.advance(1999);
    expect(r.calls[r.calls.length - 1].payload).toMatchObject({
      telemetry_seq: 2,
      telemetry_timestamp: "2026-01-01T12:10:03.000Z",
    });
    await r.time.advance(1); // +2000 ms after the resume
    expect(r.calls[r.calls.length - 1].payload).toMatchObject({
      telemetry_seq: 3,
      telemetry_timestamp: "2026-01-01T12:10:05.000Z",
    });
  });

  it("each resume starts its own segment: two pauses give two new base times and two new start sequences", async () => {
    const r = rig();
    await r.begin();
    await r.time.advance(2500); // sequence 1
    r.loop.pause();
    await r.time.advance(10_000);
    await r.loop.start(); // +12.5 s: sequence 2, base +12.5 s
    await r.time.advance(4500); // +17 s: 4.5 s into the segment = sequence 4
    expect(r.calls[r.calls.length - 1].payload).toMatchObject({
      telemetry_seq: 4,
      telemetry_timestamp: "2026-01-01T12:00:16.500Z",
    });
    r.loop.pause();
    await r.time.advance(1000);
    await r.loop.start(); // +18 s: one past 4
    await r.time.advance(0);
    expect(r.calls[r.calls.length - 1].payload).toMatchObject({
      telemetry_seq: 5,
      telemetry_timestamp: "2026-01-01T12:00:18.000Z",
    });
  });

  it("after a fault stopped the loop, a successful manual Retry puts the cursor back in motion with a new observation", async () => {
    const r = rig({ script: [...threeTransportErrors(), "ok"] });
    await r.begin();
    await r.time.advance(6000); // stopped at +6 s: the cursor froze on sequence 3
    expect(r.get().fault?.stopped).toBe(true);
    await r.time.advance(10_000); // +16 s
    await r.loop.retry();
    await r.time.advance(0);
    // The delivery itself is the frozen request, byte for byte...
    expect(r.calls).toHaveLength(4);
    expect(r.calls[3].body).toBe(r.calls[0].body);
    expect(r.calls[3].payload.telemetry_seq).toBe(0);
    // ...and the next tick is a new observation: frozen sequence + 1, timed at the retry.
    await r.time.advance(500);
    expect(r.calls).toHaveLength(5);
    expect(r.calls[4].payload).toMatchObject({
      telemetry_seq: 4,
      telemetry_timestamp: "2026-01-01T12:00:16.000Z",
    });
  });

  it("a dropped late frame (not a failure) does not restart or freeze the cursor", async () => {
    const r = rig({
      script: [new ApiError("Out-of-order evidence timestamp", 409)],
    });
    await r.begin();
    await r.time.advance(1500);
    expect(r.get().droppedFrames).toBe(1);
    expect(
      r.calls.map((call) => [
        call.payload.telemetry_seq,
        call.payload.telemetry_timestamp,
      ]),
    ).toEqual([
      [0, "2026-01-01T12:00:00.000Z"],
      [0, "2026-01-01T12:00:00.000Z"],
      [0, "2026-01-01T12:00:00.000Z"],
      [0, "2026-01-01T12:00:00.000Z"],
    ]);
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
        captured_at_source: "capture_time",
        vision_frame: { epoch: 1000, index: 5 },
      }),
      telemetry: createPreparedTelemetryCursor(constantRows(TELEMETRY)),
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
    const sent = JSON.parse(infers[0].body ?? "{}");
    expect(sent.request_id).toBe("wire-1");
    // What the server reads to tell a new observation from a repeat really is on the wire.
    expect(sent).toMatchObject({
      captured_at_source: "capture_time",
      vision_frame: { epoch: 1000, index: 5 },
      telemetry_seq: 0,
      telemetry_timestamp: "2026-01-01T12:00:00.000Z",
    });
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
