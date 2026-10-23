import {
  useCallback,
  useEffect,
  useRef,
  useState,
  useSyncExternalStore,
} from "react";
import { createLiveLoop } from "../../../ai/src/liveLoop";
import { createTimingBuffer } from "../../../ai/src/liveTiming";
import { api, type ModelStatus } from "../api/client";
import { RETRY_POLICY } from "../api/retryPolicy";
import { createPreparedTelemetryCursor } from "../data/preparedSessionInput";
import type { AppConfig, SessionMeta } from "../types";
import type { CaptureResult } from "./useCameraPreview";

/**
 * React binding for the Live acquisition loop (`ai/src/liveLoop.ts`).
 *
 * All the decisions - the frozen payload, the 3-delivery budget, the backoff, the
 * stop - live in the pure loop; this hook only supplies the browser's pieces (the
 * API client, the camera, the prepared telemetry, `crypto`, the real timers) and
 * subscribes the component to the loop's state.
 *
 * Two kinds of message are kept apart on purpose:
 *   `fault`  the acquisition loop's own state (retrying / stopped). Only the loop
 *            changes it, so nothing else can overwrite or clear it.
 *   `error`  everything else (saved sessions, flag, export). It is cleared by the
 *            next action of that kind - never by a successful tick.
 */
export function useLiveSession(
  config: AppConfig,
  captureFrame: () => CaptureResult,
) {
  const configRef = useRef(config);
  const captureRef = useRef(captureFrame);
  const lastMiss = useRef<string | null>(null);
  useEffect(() => {
    configRef.current = config;
    captureRef.current = captureFrame;
  });

  const [loop] = useState(() =>
    createLiveLoop<ModelStatus>({
      api,
      policy: RETRY_POLICY,
      getConfig: () => configRef.current,
      captureFrame: () => {
        const sample = captureRef.current();
        lastMiss.current = sample.reason;
        return sample.frame;
      },
      captureMissReason: () => lastMiss.current,
      // Replay the prepared RAW telemetry (PREPARED_RAW_TELEMETRY - never the
      // prepared-probability windows) at its original 2-second cadence,
      // independently of the camera's inference rate. The cursor numbers every
      // sample and stamps it with its logical event time; the loop resets, pauses
      // and resumes it with the session. One cursor per loop, hence per hook.
      telemetry: createPreparedTelemetryCursor(),
      newRequestId: () => crypto.randomUUID(),
      now: () => Date.now(),
      // Bounded (500 windows) per-window latency: capture -> send -> response -> render.
      timings: createTimingBuffer(),
      timers: {
        setTimeout: (fn, ms) => setTimeout(fn, ms),
        clearTimeout: (handle) =>
          clearTimeout(handle as ReturnType<typeof setTimeout>),
      },
    }),
  );
  const live = useSyncExternalStore(loop.subscribe, loop.getState);

  // Close the newest window's `renderMs` once React has committed it. A window the
  // loop did not time (a saved session, a reconcile) is ignored by `markRendered`.
  const newestWindowId =
    live.history.length > 0
      ? live.history[live.history.length - 1].window_id
      : null;
  useEffect(() => {
    if (newestWindowId !== null) loop.markRendered(newestWindowId);
  }, [loop, newestWindowId]);

  // A read-only view of the per-window latency buffer for the end-to-end tests
  // (`page.evaluate("window.__draLiveTimings")`). A getter, so each read is a fresh copy.
  useEffect(() => {
    const host = window as unknown as Record<string, unknown>;
    Object.defineProperty(host, "__draLiveTimings", {
      configurable: true,
      get: () => loop.getTimings(),
    });
    return () => {
      delete host.__draLiveTimings;
    };
  }, [loop]);

  const [sessions, setSessions] = useState<SessionMeta[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [now, setNow] = useState(Date.now());

  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => {
      clearInterval(timer);
      loop.pause();
    };
  }, [loop]);

  const refreshSessions = useCallback(async () => {
    setError(null);
    try {
      setSessions(
        (await api.sessions()).filter(
          (s) => s.operation_mode === "LIVE_MODEL_RUNTIME",
        ),
      );
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Cannot load saved sessions",
      );
    }
  }, []);

  const loadSession = useCallback(
    async (sid: string) => {
      setError(null);
      const message = await loop.loadSession(sid);
      if (message) setError(message);
    },
    [loop],
  );

  const flag = useCallback(
    async (id: number, flagged: boolean) => {
      setError(null);
      try {
        loop.replaceRecord(
          await api.flag(loop.getState().sessionId, id, flagged),
        );
      } catch (err) {
        setError(err instanceof Error ? err.message : "Flag update failed");
      }
    },
    [loop],
  );

  const exportSession = useCallback(
    async (format: "json" | "csv") => {
      setError(null);
      const sessionId = loop.getState().sessionId;
      if (!sessionId) {
        setError("Start or select a session first");
        return;
      }
      try {
        const response = await fetch(api.exportUrl(sessionId, format));
        if (!response.ok) throw new Error("Session export failed");
        const url = URL.createObjectURL(await response.blob());
        const anchor = document.createElement("a");
        anchor.href = url;
        anchor.download = `${sessionId}.${format}`;
        anchor.click();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Session export failed");
      }
    },
    [loop],
  );

  const latest = live.history[live.history.length - 1];
  const stale = Boolean(
    latest &&
    now - Date.parse(latest.timestamp) > config.freshnessTolerance * 1000,
  );
  return {
    sessionId: live.sessionId,
    history: live.history,
    total: live.total,
    running: live.running,
    busy: live.busy,
    retrying: live.retrying,
    fault: live.fault,
    error,
    models: live.models,
    requestMs: live.requestMs,
    effectiveFps: live.effectiveFps,
    droppedFrames: live.droppedFrames,
    imagelessRequests: live.imagelessRequests,
    lastCaptureMiss: live.lastCaptureMiss,
    stale,
    start: loop.start,
    pause: loop.pause,
    retry: loop.retry,
    flag,
    refreshSessions,
    sessions,
    loadSession,
    exportSession,
  };
}
