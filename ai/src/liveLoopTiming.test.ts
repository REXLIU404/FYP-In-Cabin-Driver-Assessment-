import { describe, expect, it } from "vitest";

import { RETRY_POLICY } from "../../frontend/src/api/retryPolicy";
import { createPreparedTelemetryCursor } from "../../frontend/src/data/preparedSessionInput";
import { makeRecord } from "../../frontend/src/testing/records";
import { createLiveLoop, type LiveLoopApi, type LivePayload } from "./liveLoop";
import { createTimingBuffer } from "./liveTiming";
import { DEFAULT_CONFIG } from "./riskLogic";
import type {
  AppConfig,
  RiskUpdate,
  SessionMeta,
  TelemetryFeatures,
} from "./types";

// The Live loop records, per answered window, how long capture -> send, the request, and
// (once the UI says so) the render took. The loop's clock and timers are injected, so
// every duration below is a virtual-time literal.

const flush = () => new Promise<void>((resolve) => setTimeout(resolve, 0));

class FakeTime {
  readonly start = Date.UTC(2026, 0, 1, 12, 0, 0);
  now = this.start;
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
type Models = { ready: boolean };
type Step = { fail: Error } | { after: number } | "hang";

function rig(options: {
  /** What successive `infer` calls do; once exhausted, answer after 0 ms. */
  script?: Step[];
  /** Virtual time the camera takes to produce a frame (JPEG encode). */
  captureMs?: number;
  fps?: number;
  /** Do not inject a latency recorder. */
  noRecorder?: boolean;
}) {
  const time = new FakeTime();
  const script = [...(options.script ?? [])];
  const config: AppConfig = {
    ...DEFAULT_CONFIG,
    inferenceFps: options.fps ?? 2,
  };
  const sessions = ["sess-1", "sess-2", "sess-3"];
  let windowId = 0;
  const api = {
    models: async (): Promise<Models> => ({ ready: true }),
    create: async (): Promise<SessionMeta> => {
      windowId = 0; // a new session numbers its windows from 1 again
      return {
        id: sessions.shift() ?? "sess-n",
        created_at: "2026-01-01T12:00:00+00:00",
        total_windows: 0,
      };
    },
    session: async (sid: string): Promise<SessionMeta> => ({
      id: sid,
      created_at: "2026-01-01T12:00:00+00:00",
      total_windows: 0,
    }),
    latest: async (): Promise<RiskUpdate> => makeRecord("fresh", "fresh", 1),
    windows: async (): Promise<RiskUpdate[]> => [],
    infer: (
      _sid: string,
      _payload: LivePayload,
      signal: AbortSignal,
    ): Promise<RiskUpdate> => {
      const step = script.shift() ?? { after: 0 };
      if (step === "hang")
        return new Promise<RiskUpdate>((_, reject) =>
          signal.addEventListener(
            "abort",
            () => reject(new DOMException("aborted", "AbortError")),
            { once: true },
          ),
        );
      if ("fail" in step) return Promise.reject(step.fail);
      return new Promise<RiskUpdate>((resolve) =>
        time.setTimeout(() => {
          windowId += 1;
          resolve(makeRecord("fresh", "fresh", windowId));
        }, step.after),
      );
    },
  };
  let requestIds = 0;
  const loop = createLiveLoop<Models>({
    api: api as LiveLoopApi<Models>,
    policy: RETRY_POLICY,
    getConfig: () => config,
    captureFrame: () => {
      time.now += options.captureMs ?? 0;
      return {
        image_base64: "frame",
        captured_at: new Date(time.now).toISOString(),
        captured_at_source: "callback",
        vision_frame: { epoch: 1000, index: 1 },
      };
    },
    // These tests time the requests; the cursor only has to hand out a sample.
    telemetry: createPreparedTelemetryCursor([
      { timestamp: "", telemetry_features: TELEMETRY, telemetry_age_s: 0 },
    ]),
    newRequestId: () => `req-${++requestIds}`,
    now: () => time.now,
    timers: time,
    ...(options.noRecorder ? {} : { timings: createTimingBuffer() }),
  });
  return {
    loop,
    time,
    async begin() {
      await loop.start();
      await time.advance(0);
    },
  };
}

const transportError = () => new TypeError("Failed to fetch");

describe("the loop records capture -> send -> response for every answered window", () => {
  it("captureToSend, network and (after markRendered) render are the measured gaps", async () => {
    // Tick begins at +0, the camera takes 20 ms, the server answers 150 ms after the send.
    const r = rig({ script: [{ after: 150 }], captureMs: 20 });
    await r.begin();
    expect(r.loop.getTimings()).toEqual([]); // nothing answered yet
    await r.time.advance(150); // the camera already took 20 of the 170 ms

    const [entry] = r.loop.getTimings();
    expect(entry).toMatchObject({
      sessionId: "sess-1",
      windowId: 1,
      requestId: "req-1",
      attemptIndex: 1,
      capturedAtMs: r.time.start,
      sentAtMs: r.time.start + 20,
      receivedAtMs: r.time.start + 170,
      captureToSendMs: 20,
      networkMs: 150,
      renderMs: null,
      renderedAtMs: null,
      server: null,
    });

    await r.time.advance(15); // the UI commits 15 ms after the response (+170 -> +185)
    r.loop.markRendered(1);
    expect(r.loop.getTimings()[0]).toMatchObject({
      renderedAtMs: r.time.start + 185,
      renderMs: 15,
      networkMs: 150,
    });
  });

  it("a window that needed a retry is timed from the original capture, with its attempt index", async () => {
    // First delivery fails at once; the 2000 ms backoff follows; the second is answered after 100 ms.
    const r = rig({
      script: [{ fail: transportError() }, { after: 100 }],
      captureMs: 20,
    });
    await r.begin();
    await r.time.advance(2120);

    const [entry] = r.loop.getTimings();
    expect(entry).toMatchObject({
      windowId: 1,
      attemptIndex: 2,
      captureToSendMs: 2020, // 20 ms capture + 2000 ms backoff: the frame really was this old
      networkMs: 100, // the delivery that succeeded, not the failed one
    });
  });

  it("a failed or cancelled delivery leaves nothing behind", async () => {
    const stopped = rig({
      script: [
        { fail: transportError() },
        { fail: transportError() },
        { fail: transportError() },
      ],
    });
    await stopped.begin();
    await stopped.time.advance(600_000);
    expect(stopped.loop.getState().fault?.stopped).toBe(true);
    expect(stopped.loop.getTimings()).toEqual([]);

    const paused = rig({ script: ["hang"] });
    await paused.begin();
    paused.loop.pause();
    await paused.time.advance(60_000);
    expect(paused.loop.getTimings()).toEqual([]);
  });

  it("markRendered ignores a window that was never timed, and never overwrites", async () => {
    const r = rig({ script: [{ after: 10 }], captureMs: 0 });
    await r.begin();
    await r.time.advance(10);
    r.loop.markRendered(99);
    expect(r.loop.getTimings()[0].renderMs).toBeNull();
    await r.time.advance(5);
    r.loop.markRendered(1);
    await r.time.advance(50);
    r.loop.markRendered(1);
    expect(r.loop.getTimings()[0].renderMs).toBe(5);
  });

  it("windows of different sessions are kept apart; markRendered follows the current session", async () => {
    const r = rig({ script: [{ after: 10 }, { after: 10 }] });
    await r.begin();
    await r.time.advance(10);
    await r.loop.start(true); // New Session: window numbering restarts at 1
    await r.time.advance(10);
    expect(r.loop.getTimings().map((t) => [t.sessionId, t.windowId])).toEqual([
      ["sess-1", 1],
      ["sess-2", 1],
    ]);
    r.loop.markRendered(1);
    const [first, second] = r.loop.getTimings();
    expect(first.renderMs).toBeNull();
    expect(second.renderMs).not.toBeNull();
  });

  it("the buffer is bounded: after 520 answered windows exactly the newest 500 remain", async () => {
    const r = rig({ fps: 30 });
    await r.begin();
    await r.time.advance(34 * 520);
    const state = r.loop.getState();
    expect(state.total).toBeGreaterThan(500);
    const kept = r.loop.getTimings();
    expect(kept).toHaveLength(500);
    expect(kept[kept.length - 1].windowId).toBe(state.total);
    expect(kept[0].windowId).toBe(state.total - 499);
    expect(kept.map((t) => t.windowId)).toEqual(
      Array.from({ length: 500 }, (_, i) => state.total - 499 + i),
    );
  }, 30_000);

  it("without an injected recorder the loop records nothing and markRendered is harmless", async () => {
    const r = rig({ script: [{ after: 10 }], noRecorder: true });
    await r.begin();
    await r.time.advance(10);
    expect(r.loop.getState().total).toBe(1); // the window was answered...
    r.loop.markRendered(1);
    expect(r.loop.getTimings()).toEqual([]); // ...and simply not timed
  });

  it("getTimings hands out a copy", async () => {
    const r = rig({ script: [{ after: 10 }] });
    await r.begin();
    await r.time.advance(10);
    (r.loop.getTimings() as unknown[]).length = 0;
    expect(r.loop.getTimings()).toHaveLength(1);
  });
});
