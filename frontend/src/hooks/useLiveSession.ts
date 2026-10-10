import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError, type ModelStatus } from "../api/client";
import { PREPARED_SESSION_WINDOWS } from "../data/preparedSessionInput";
import type { AppConfig, RiskUpdate, SessionMeta } from "../types";

type Frame = { image_base64: string; captured_at: string } | null;

export function useLiveSession(config: AppConfig, captureFrame: () => Frame) {
  const [sessionId, setSessionId] = useState("");
  const [history, setHistory] = useState<RiskUpdate[]>([]);
  const [sessions, setSessions] = useState<SessionMeta[]>([]);
  const [total, setTotal] = useState(0);
  const [running, setRunning] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [models, setModels] = useState<ModelStatus | null>(null);
  const [requestMs, setRequestMs] = useState<number | null>(null);
  const [effectiveFps, setEffectiveFps] = useState<number | null>(null);
  const [now, setNow] = useState(Date.now());
  const runId = useRef(0);
  const abort = useRef<AbortController | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout>>();
  const activeSid = useRef("");
  const configKey = useRef("");
  const startedAt = useRef(0);

  const pause = useCallback(() => {
    runId.current++;
    abort.current?.abort();
    clearTimeout(timer.current);
    setRunning(false);
    setBusy(false);
  }, []);

  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => {
      clearInterval(timer);
      pause();
    };
  }, [pause]);

  const refreshSessions = useCallback(async () => {
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
      pause();
      setBusy(true);
      setError(null);
      const generation = runId.current;
      try {
        const meta = await api.session(sid);
        let records: RiskUpdate[] = [];
        if (meta.total_windows > 0) {
          const latest = await api.latest(sid);
          records = await api.windows(sid, Math.max(0, latest.window_id - 500));
        }
        if (generation !== runId.current) return;
        setSessionId(sid);
        setHistory(records);
        setTotal(meta.total_windows);
        // Historical sessions are read-only for acquisition; start creates a new session.
        activeSid.current = "";
        configKey.current = "";
      } catch (err) {
        if (generation === runId.current)
          setError(err instanceof Error ? err.message : "Cannot load session");
      } finally {
        if (generation === runId.current) setBusy(false);
      }
    },
    [pause],
  );

  const start = useCallback(
    async (restart = false) => {
      pause();
      const generation = runId.current;
      const current = () => runId.current === generation;
      const controller = new AbortController();
      abort.current = controller;
      setBusy(true);
      setError(null);
      const setupTimeout = setTimeout(() => controller.abort(), 15000);
      let sid = activeSid.current;
      try {
        const status = await api.models(controller.signal);
        if (!current()) return;
        setModels(status);
        if (!sid || restart || configKey.current !== JSON.stringify(config)) {
          const created = await api.create(config, controller.signal);
          if (!current()) return;
          sid = created.id;
          activeSid.current = sid;
          configKey.current = JSON.stringify(config);
          startedAt.current = Date.now();
          setSessionId(sid);
          setHistory([]);
          setTotal(0);
        } else {
          // Reconcile any last request committed after the browser paused/aborted.
          const meta = await api.session(sid);
          const latest = meta.total_windows ? await api.latest(sid) : null;
          const records = latest
            ? await api.windows(sid, Math.max(0, latest.window_id - 500))
            : [];
          if (!current()) return;
          setHistory(records);
          setTotal(meta.total_windows);
        }
      } catch (err) {
        if (current()) {
          setError(err instanceof Error ? err.message : "Backend unavailable");
          setBusy(false);
        }
        return;
      } finally {
        clearTimeout(setupTimeout);
      }
      if (!current()) return;
      setBusy(false);
      setRunning(true);
      const completions: number[] = [];
      let failures = 0;
      const tick = async () => {
        if (!current()) return;
        const begin = performance.now();
        const controller = new AbortController();
        abort.current = controller;
        const timeout = setTimeout(() => controller.abort(), 10000);
        try {
          const frame = captureFrame();
          // Replay raw telemetry at its original 2-second cadence, independently of camera inference rate.
          const index =
            Math.floor((Date.now() - startedAt.current) / 2000) %
            PREPARED_SESSION_WINDOWS.length;
          const telemetry = PREPARED_SESSION_WINDOWS[index].telemetry_features;
          const record = await api.infer(
            sid,
            {
              request_id: crypto.randomUUID(),
              image_base64: frame?.image_base64 ?? null,
              captured_at: frame?.captured_at ?? null,
              telemetry_features: telemetry,
              telemetry_timestamp: telemetry ? new Date().toISOString() : null,
              telemetry_source: telemetry ? "prepared_replay" : "missing",
            },
            controller.signal,
          );
          if (!current()) return;
          setHistory((old) =>
            [
              ...old.filter((r) => r.window_id !== record.window_id),
              record,
            ].slice(-500),
          );
          setTotal(record.window_id);
          const completed = performance.now();
          setRequestMs(completed - begin);
          completions.push(completed);
          if (completions.length > 20) completions.shift();
          if (completions.length > 1)
            setEffectiveFps(
              (1000 * (completions.length - 1)) / (completed - completions[0]),
            );
          setError(null);
          failures = 0;
        } catch (err) {
          if (!current()) return;
          failures++;
          setEffectiveFps(null);
          setError(
            err instanceof Error ? err.message : "Inference request failed",
          );
          if (
            err instanceof ApiError &&
            [404, 409, 422, 503].includes(err.status)
          ) {
            if (err.status === 404) activeSid.current = "";
            setRunning(false);
            return;
          }
        } finally {
          clearTimeout(timeout);
        }
        if (current()) {
          // One request in flight, no queued frames; each tick captures the newest available frame.
          const interval =
            1000 / Math.max(1, Math.min(30, config.inferenceFps));
          timer.current = setTimeout(
            () => void tick(),
            failures
              ? Math.min(1000 * 2 ** failures, 10000)
              : Math.max(0, interval - (performance.now() - begin)),
          );
        }
      };
      void tick();
    },
    [captureFrame, config, pause],
  );

  const flag = useCallback(
    async (id: number, flagged: boolean) => {
      try {
        const record = await api.flag(sessionId, id, flagged);
        setHistory((old) => old.map((r) => (r.window_id === id ? record : r)));
      } catch (err) {
        setError(err instanceof Error ? err.message : "Flag update failed");
      }
    },
    [sessionId],
  );

  const exportSession = useCallback(
    async (format: "json" | "csv") => {
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
    [sessionId],
  );

  const latest = history[history.length - 1];
  const stale = Boolean(
    latest &&
    now - Date.parse(latest.timestamp) > config.freshnessTolerance * 1000,
  );
  return {
    sessionId,
    history,
    total,
    running,
    busy,
    error,
    models,
    requestMs,
    effectiveFps,
    stale,
    start,
    pause,
    flag,
    refreshSessions,
    sessions,
    loadSession,
    exportSession,
  };
}
