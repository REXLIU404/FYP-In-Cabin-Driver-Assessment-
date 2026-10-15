/**
 * The Live acquisition loop: one logical request per tick, delivered at most
 * `policy.maxAttempts` times with a bounded backoff, then a visible stop.
 *
 * Pure module. It imports nothing from `frontend/` and touches no React, no
 * document and no global clock: the API, the frame source, the telemetry source,
 * the id generator, the wall clock and the timers are all injected
 * (`LiveLoopDeps`), so the whole state machine runs under a virtual clock in the
 * node test environment. The error classifier and the retry budget are injected
 * too (`RetryPolicy`) because recognising an `ApiError` is a frontend concern; the
 * production wiring is `RETRY_POLICY` in `frontend/src/api/retryPolicy.ts`.
 *
 * Rules this module enforces (plan Task 8, rulings D02 / R5 / R7):
 *
 *  - The payload of a logical request (request_id, frame, captured_at, telemetry,
 *    telemetry_timestamp) is built ONCE, before the first delivery, and every
 *    redelivery - automatic or manual - re-sends it unchanged. The server's
 *    idempotency key is a hash of that payload and its out-of-order guard compares
 *    the evidence timestamps, so a re-stamped retry would be a 409.
 *  - Every delivery carries its own attempt index (1, 2, 3 automatic; 4, 5 ...
 *    manual). The fault table is keyed on (session, request_id, attempt_index), so
 *    a restart from 1 would be folded into the first row and lost.
 *  - A failure is COUNTED only if it is a failure of the `infer` request itself.
 *    A pause / unmount abort, a dropped late frame and everything about the camera
 *    are not.
 *  - A missing frame is not a failure: the request is sent without an image, and
 *    with neither image nor telemetry the server answers 201 + UNAVAILABLE.
 *  - Stopping is a visible state (`fault.stopped`) that nothing clears
 *    automatically; only a successful delivery, `start()` or `loadSession()` does.
 *
 * Freshness consequence (T5, stated on purpose): a retry re-sends the FIRST
 * capture's `captured_at` / `telemetry_timestamp` byte for byte. After the 2 s + 4 s
 * backoffs the third delivery is at least 6 s old, and a delivery that follows a
 * 10 s timeout is older than the 3 s tolerance already at the second attempt. Under
 * ruling A (D13) the backend stores such a window as EXPIRED: both branches score as
 * missing (`provenance.*_expired` / `*_age_s` say why), so it is a 201 with no
 * assessment, UNAVAILABLE, and it advances no alert timer. It used to be stored as
 * stale / DEGRADED and kept accumulating sustained-High.
 */
import type {
  AppConfig,
  RiskUpdate,
  SessionMeta,
  TelemetryFeatures,
} from "./types";

export type FaultCategory =
  | "input"
  | "clock_skew"
  | "not_found"
  | "conflict_hash"
  | "conflict_mode"
  | "conflict_stale_frame"
  | "models_unavailable"
  | "model_runtime"
  | "storage"
  | "timeout"
  | "transport"
  | "aborted";

export interface FailureClass {
  category: FaultCategory;
  status?: number;
  /** May the same request be delivered again automatically? */
  retryable: boolean;
  /** Does it count against the delivery budget? Aborts and dropped frames do not. */
  counted: boolean;
}

export interface RetryPolicy {
  /**
   * Total deliveries of one logical request: the first send plus the automatic
   * retries. `backoffMs` is only defined for the first two failures, so this
   * must not exceed 3.
   */
  maxAttempts: number;
  /** Wait after the Nth failed delivery before delivery N + 1. */
  backoffMs(attemptIndex: 1 | 2): number;
  classify(err: unknown): FailureClass;
}

export interface LiveFrame {
  image_base64: string;
  captured_at: string;
}

export interface LivePayload {
  request_id: string;
  image_base64: string | null;
  captured_at: string | null;
  telemetry_features: TelemetryFeatures | null;
  telemetry_timestamp: string | null;
  telemetry_source: "prepared_replay" | "missing";
}

export interface LiveLoopApi<TModels> {
  models(signal: AbortSignal): Promise<TModels>;
  create(config: AppConfig, signal: AbortSignal): Promise<SessionMeta>;
  session(sid: string, signal: AbortSignal): Promise<SessionMeta>;
  latest(sid: string, signal: AbortSignal): Promise<RiskUpdate>;
  windows(
    sid: string,
    after: number,
    signal: AbortSignal,
  ): Promise<RiskUpdate[]>;
  infer(
    sid: string,
    payload: LivePayload,
    signal: AbortSignal,
    attemptIndex: number,
  ): Promise<RiskUpdate>;
}

export interface LiveLoopTimers {
  setTimeout(fn: () => void, ms: number): unknown;
  clearTimeout(handle: unknown): void;
}

export interface LiveLoopDeps<TModels> {
  api: LiveLoopApi<TModels>;
  policy: RetryPolicy;
  getConfig(): AppConfig;
  /** `null` = no usable frame right now (camera stopped, not ready, track ended). */
  captureFrame(): LiveFrame | null;
  /**
   * Why the last `captureFrame()` returned null. Asked only after a null, and used
   * for display and the log only: it never changes what the loop does.
   */
  captureMissReason?(): string | null;
  /** The telemetry reading for `elapsedMs` since the session started, or `null`. */
  telemetryAt(elapsedMs: number): TelemetryFeatures | null;
  newRequestId(): string;
  /** Wall clock in epoch milliseconds. */
  now(): number;
  timers: LiveLoopTimers;
}

export interface LiveFault {
  category: FaultCategory;
  status?: number;
  /** The server's own words (or the transport error's message). */
  message: string;
  /** "setup": models / create / reconcile. "delivery": an `infer` request. */
  phase: "setup" | "delivery";
  /** The logical request the fault belongs to; `null` before any was built. */
  requestId: string | null;
  /**
   * Deliveries of that request SENT so far, automatic and manual together. A delivery
   * is counted when it is sent, not when it fails: one that a Pause cancelled while
   * in flight is included, so this is not strictly a count of failures.
   */
  retryCount: number;
  /**
   * How many of those `retryCount` deliveries were started by `retry()`; the rest
   * were the loop's own. Counted the same way - when sent - so a manual delivery
   * that a Pause cancelled is included. The split cannot be derived from
   * `retryCount`: an error that a re-send cannot fix stops the loop after fewer than
   * `maxAttempts` automatic deliveries.
   */
  manualRetries: number;
  /** X-Attempt-Index of the delivery that failed last (0 for a setup fault). */
  attemptIndex: number;
  /** `false` while an automatic retry is still pending; `true` once the loop stopped. */
  stopped: boolean;
  /**
   * `retry()` will create a NEW session instead of resuming this one: the session
   * is gone (404), or the failed setup was a New Session (`start(true)`).
   */
  newSessionOnRetry: boolean;
}

export interface LiveLoopState<TModels> {
  sessionId: string;
  history: RiskUpdate[];
  total: number;
  running: boolean;
  /** Setup (models / create / reconcile) or loading a saved session. */
  busy: boolean;
  /** A manual `retry()` is in flight. */
  retrying: boolean;
  fault: LiveFault | null;
  /** Late frames the server refused as out-of-order and the loop discarded. */
  droppedFrames: number;
  /** Requests sent without an image since the loop started (display only). */
  imagelessRequests: number;
  /** Why the most recent request had no image; `null` if it had one (display only). */
  lastCaptureMiss: string | null;
  models: TModels | null;
  requestMs: number | null;
  effectiveFps: number | null;
}

export interface LiveLoop<TModels> {
  getState(): LiveLoopState<TModels>;
  subscribe(listener: () => void): () => void;
  start(restart?: boolean): Promise<void>;
  pause(): void;
  /** Re-deliver the frozen request once (or re-run setup / create a new session). */
  retry(): Promise<void>;
  /** Show a saved session read-only. Resolves to an error message, or `null`. */
  loadSession(sid: string): Promise<string | null>;
  /** Swap one history entry for a newer copy of the same window (a flag toggle). */
  replaceRecord(record: RiskUpdate): void;
}

/** Per-attempt abort deadline of one `infer` delivery. */
export const ATTEMPT_TIMEOUT_MS = 10_000;
/** Deadline of the setup calls (models / create / reconcile). */
export const SETUP_TIMEOUT_MS = 15_000;
const HISTORY_LIMIT = 500;

interface PendingRequest {
  sessionId: string;
  payload: LivePayload;
  /** Deliveries started so far; the next one carries `deliveries + 1`. */
  deliveries: number;
  /** How many of those were started by `retry()` rather than by the loop itself. */
  manualDeliveries: number;
}

interface Attempt {
  signal: AbortSignal;
  timedOut(): boolean;
  end(): void;
}

const messageOf = (err: unknown, fallback: string) =>
  err instanceof Error && err.message ? err.message : fallback;

export function createLiveLoop<TModels = unknown>(
  deps: LiveLoopDeps<TModels>,
): LiveLoop<TModels> {
  const { api, policy, timers } = deps;
  let state: LiveLoopState<TModels> = {
    sessionId: "",
    history: [],
    total: 0,
    running: false,
    busy: false,
    retrying: false,
    fault: null,
    droppedFrames: 0,
    imagelessRequests: 0,
    lastCaptureMiss: null,
    models: null,
    requestMs: null,
    effectiveFps: null,
  };
  const listeners = new Set<() => void>();
  const patch = (next: Partial<LiveLoopState<TModels>>) => {
    state = { ...state, ...next };
    listeners.forEach((listener) => listener());
  };

  // Every await is followed by a `generation` check: pause, a new start() and
  // unmount all bump it, and whatever resolves afterwards is discarded.
  let generation = 0;
  let inFlight: AbortController | null = null;
  let attemptTimer: unknown = null;
  let tickTimer: unknown = null;
  let activeSid = "";
  let configKey = "";
  let startedAt = 0;
  let pending: PendingRequest | null = null;
  let completions: number[] = [];

  const clearTickTimer = () => {
    if (tickTimer !== null) timers.clearTimeout(tickTimer);
    tickTimer = null;
  };
  const cancel = () => {
    generation++;
    inFlight?.abort();
    inFlight = null;
    if (attemptTimer !== null) timers.clearTimeout(attemptTimer);
    attemptTimer = null;
    clearTickTimer();
  };

  /** One abortable call with its own deadline; `timedOut()` tells it from a pause. */
  const beginAttempt = (ms: number): Attempt => {
    const controller = new AbortController();
    let timedOut = false;
    inFlight = controller;
    const handle = timers.setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, ms);
    attemptTimer = handle;
    return {
      signal: controller.signal,
      timedOut: () => timedOut,
      end() {
        // Only this attempt's own handles: a later attempt may already be running
        // by the time a cancelled one settles.
        timers.clearTimeout(handle);
        if (attemptTimer === handle) attemptTimer = null;
        if (inFlight === controller) inFlight = null;
      },
    };
  };
  /** A deadline that fired is a timeout, whatever the aborted call rejected with. */
  const failureOf = (attempt: Attempt, err: unknown) => {
    const error = attempt.timedOut()
      ? new DOMException("Request timed out", "TimeoutError")
      : err;
    return { error, failure: policy.classify(error) };
  };

  const intervalMs = () =>
    1000 / Math.max(1, Math.min(30, deps.getConfig().inferenceFps));
  /** One request in flight, no queued frames: the next tick follows the last delivery. */
  const scheduleTick = (g: number, delay: number) => {
    clearTickTimer();
    tickTimer = timers.setTimeout(
      () => {
        tickTimer = null;
        void tick(g);
      },
      Math.max(0, delay),
    );
  };

  const reconcile = async (sid: string, signal: AbortSignal) => {
    const meta = await api.session(sid, signal);
    const latest = meta.total_windows ? await api.latest(sid, signal) : null;
    const history = latest
      ? await api.windows(sid, Math.max(0, latest.window_id - 500), signal)
      : [];
    return { history, total: meta.total_windows };
  };

  /** A frame, or the reason there is none. A camera that throws has no frame. */
  const sampleFrame = (): { frame: LiveFrame | null; miss: string | null } => {
    try {
      const frame = deps.captureFrame();
      if (frame) return { frame, miss: null };
      return { frame: null, miss: deps.captureMissReason?.() ?? "no_frame" };
    } catch {
      return { frame: null, miss: "capture_error" };
    }
  };

  async function tick(g: number): Promise<void> {
    if (g !== generation) return;
    const begun = deps.now();
    const { frame, miss } = sampleFrame();
    const telemetry = deps.telemetryAt(begun - startedAt);
    // The one and only place a payload is built. Redeliveries reuse `pending`.
    pending = {
      sessionId: activeSid,
      deliveries: 0,
      manualDeliveries: 0,
      payload: {
        request_id: deps.newRequestId(),
        image_base64: frame?.image_base64 ?? null,
        captured_at: frame?.captured_at ?? null,
        telemetry_features: telemetry,
        telemetry_timestamp: telemetry
          ? new Date(deps.now()).toISOString()
          : null,
        telemetry_source: telemetry ? "prepared_replay" : "missing",
      },
    };
    if (frame === null)
      patch({
        imagelessRequests: state.imagelessRequests + 1,
        lastCaptureMiss: miss,
      });
    else if (state.lastCaptureMiss !== null) patch({ lastCaptureMiss: null });
    await deliver(g, false);
  }

  async function deliver(g: number, manual: boolean): Promise<void> {
    const request = pending;
    if (!request || g !== generation) return;
    const attemptIndex = ++request.deliveries;
    if (manual) request.manualDeliveries++;
    const sentAt = deps.now();
    const attempt = beginAttempt(ATTEMPT_TIMEOUT_MS);
    let record: RiskUpdate;
    try {
      record = await api.infer(
        request.sessionId,
        request.payload,
        attempt.signal,
        attemptIndex,
      );
    } catch (err) {
      // Pause, a new start() or unmount: the user stopped it, nothing failed.
      if (g !== generation) return;
      const { error, failure } = failureOf(attempt, err);
      onFailure(g, request, attemptIndex, sentAt, failure, error, manual);
      return;
    } finally {
      attempt.end();
    }
    if (g !== generation) return;
    pending = null;
    const completed = deps.now();
    completions.push(completed);
    if (completions.length > 20) completions.shift();
    patch({
      history: [
        ...state.history.filter((r) => r.window_id !== record.window_id),
        record,
      ].slice(-HISTORY_LIMIT),
      total: record.window_id,
      requestMs: completed - sentAt,
      effectiveFps:
        completions.length > 1
          ? (1000 * (completions.length - 1)) / (completed - completions[0])
          : state.effectiveFps,
      fault: null,
      retrying: false,
      running: true,
    });
    scheduleTick(g, intervalMs() - (completed - sentAt));
  }

  function onFailure(
    g: number,
    request: PendingRequest,
    attemptIndex: number,
    sentAt: number,
    failure: FailureClass,
    err: unknown,
    manual: boolean,
  ): void {
    if (!failure.counted) {
      // Not a failure of the request: a late frame the server refused, or an
      // abort nobody asked for. Discard the frame and carry on with the next tick.
      pending = null;
      patch({
        droppedFrames:
          state.droppedFrames +
          (failure.category === "conflict_stale_frame" ? 1 : 0),
        fault: null,
        retrying: false,
        running: true,
      });
      scheduleTick(g, intervalMs() - (deps.now() - sentAt));
      return;
    }
    const newSessionOnRetry = failure.category === "not_found";
    if (newSessionOnRetry) activeSid = "";
    const fault: LiveFault = {
      category: failure.category,
      status: failure.status,
      message: messageOf(err, "Inference request failed"),
      phase: "delivery",
      requestId: request.payload.request_id,
      retryCount: request.deliveries,
      manualRetries: request.manualDeliveries,
      attemptIndex,
      stopped: false,
      newSessionOnRetry,
    };
    if (
      !manual &&
      failure.retryable &&
      request.deliveries < policy.maxAttempts
    ) {
      patch({ fault, effectiveFps: null });
      clearTickTimer();
      tickTimer = timers.setTimeout(
        () => {
          tickTimer = null;
          void deliver(g, false);
          // deliveries is 1 or 2 here: maxAttempts is 3 and the last failure stops.
        },
        policy.backoffMs(request.deliveries as 1 | 2),
      );
      return;
    }
    // Budget spent, a non-retryable error, or a manual retry that failed again.
    // The request stays frozen in `pending` for the next manual retry.
    patch({
      fault: { ...fault, stopped: true },
      running: false,
      retrying: false,
      effectiveFps: null,
    });
  }

  const stopInSetup = (attempt: Attempt, err: unknown, restart: boolean) => {
    const { error, failure } = failureOf(attempt, err);
    // A New Session that failed in setup still means "a new session" on Retry; the
    // running session stays where it is (`activeSid` is kept) until a create works.
    const newSessionOnRetry = restart || failure.category === "not_found";
    if (failure.category === "not_found") activeSid = "";
    patch({
      busy: false,
      running: false,
      retrying: false,
      effectiveFps: null,
      fault: {
        category: failure.category,
        status: failure.status,
        message: messageOf(error, "Backend unavailable"),
        phase: "setup",
        requestId: null,
        retryCount: 0,
        manualRetries: 0,
        attemptIndex: 0,
        stopped: true,
        newSessionOnRetry,
      },
    });
  };

  async function start(restart = false): Promise<void> {
    cancel();
    const g = generation;
    pending = null;
    completions = [];
    patch({
      busy: true,
      running: false,
      retrying: false,
      fault: null,
      droppedFrames: 0,
      imagelessRequests: 0,
      lastCaptureMiss: null,
    });
    const attempt = beginAttempt(SETUP_TIMEOUT_MS);
    try {
      const models = await api.models(attempt.signal);
      if (g !== generation) return;
      patch({ models });
      const config = deps.getConfig();
      if (!activeSid || restart || configKey !== JSON.stringify(config)) {
        const created = await api.create(config, attempt.signal);
        if (g !== generation) return;
        activeSid = created.id;
        configKey = JSON.stringify(config);
        startedAt = deps.now();
        patch({ sessionId: created.id, history: [], total: 0 });
      } else {
        // Reconcile any last request committed after the browser paused/aborted.
        const snapshot = await reconcile(activeSid, attempt.signal);
        if (g !== generation) return;
        patch(snapshot);
      }
    } catch (err) {
      if (g === generation) stopInSetup(attempt, err, restart);
      return;
    } finally {
      attempt.end();
    }
    patch({ busy: false, running: true });
    void tick(g);
  }

  function pause(): void {
    cancel();
    const stopped = state.fault?.stopped === true;
    // A stopped request stays frozen so that Retry still has something to resend.
    if (!stopped) pending = null;
    patch({
      running: false,
      busy: false,
      retrying: false,
      fault: stopped ? state.fault : null,
    });
  }

  async function retry(): Promise<void> {
    const fault = state.fault;
    if (!fault?.stopped || state.busy || state.retrying) return;
    if (fault.phase === "setup" || fault.newSessionOnRetry || !pending) {
      // Nothing to resume: redo the setup. A fault that asks for a new session
      // (a 404, or a New Session that failed in setup) repeats it as a restart, so
      // it creates a session even while another one is still the active one.
      await start(fault.newSessionOnRetry);
      return;
    }
    cancel();
    const g = generation;
    patch({ retrying: true });
    const attempt = beginAttempt(SETUP_TIMEOUT_MS);
    try {
      // The interrupted attempts may have been committed by the server.
      const snapshot = await reconcile(pending.sessionId, attempt.signal);
      if (g !== generation) return;
      patch(snapshot);
    } catch (err) {
      if (g === generation) {
        const { error, failure } = failureOf(attempt, err);
        if (failure.category === "not_found") activeSid = "";
        patch({
          retrying: false,
          fault: {
            ...fault,
            category: failure.category,
            status: failure.status,
            message: messageOf(error, "Backend unavailable"),
            newSessionOnRetry: failure.category === "not_found",
          },
        });
      }
      return;
    } finally {
      attempt.end();
    }
    await deliver(g, true);
  }

  async function loadSession(sid: string): Promise<string | null> {
    cancel();
    pending = null;
    const g = generation;
    patch({ running: false, retrying: false, busy: true, fault: null });
    const attempt = beginAttempt(SETUP_TIMEOUT_MS);
    try {
      const snapshot = await reconcile(sid, attempt.signal);
      if (g !== generation) return null;
      // Historical sessions are read-only for acquisition; start creates a new one.
      activeSid = "";
      configKey = "";
      patch({ sessionId: sid, ...snapshot, busy: false });
      return null;
    } catch (err) {
      if (g !== generation) return null;
      patch({ busy: false });
      return messageOf(err, "Cannot load session");
    } finally {
      attempt.end();
    }
  }

  function replaceRecord(record: RiskUpdate): void {
    if (!state.history.some((r) => r.window_id === record.window_id)) return;
    patch({
      history: state.history.map((r) =>
        r.window_id === record.window_id ? record : r,
      ),
    });
  }

  return {
    getState: () => state,
    subscribe(listener) {
      listeners.add(listener);
      return () => void listeners.delete(listener);
    },
    start,
    pause,
    retry,
    loadSession,
    replaceRecord,
  };
}
