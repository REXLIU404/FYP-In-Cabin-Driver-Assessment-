import type { AppConfig, SessionMeta } from "../types";
import {
  normalizeRiskUpdate,
  type StoredRiskUpdate,
} from "../../../ai/src/availability";
import type { LivePayload } from "../../../ai/src/liveLoop";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "";
export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
}

/** The client's own deadline for one call. The loop's 10 s delivery deadline fires first. */
const REQUEST_TIMEOUT_MS = 15000;

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const controller = new AbortController();
  // The caller's signal (a pause, an unmount) and this deadline share ONE controller,
  // so the rejection alone cannot tell them apart. `timedOut` can: only the deadline
  // sets it, and it turns the browser's AbortError into a TimeoutError.
  let timedOut = false;
  const abort = () => controller.abort();
  if (options.signal?.aborted) abort();
  options.signal?.addEventListener("abort", abort, { once: true });
  const timeout = setTimeout(() => {
    timedOut = true;
    abort();
  }, REQUEST_TIMEOUT_MS);
  try {
    const response = await fetch(`${API_BASE}/api${path}`, {
      ...options,
      signal: controller.signal,
      headers: { "Content-Type": "application/json", ...options.headers },
    });
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      const detail = Array.isArray(body.detail)
        ? body.detail.map((item: { msg: string }) => item.msg).join("; ")
        : body.detail;
      throw new ApiError(
        detail || `API request failed (${response.status})`,
        response.status,
      );
    }
    // Untrusted boundary: the body is not validated here. Endpoints that return
    // risk records pass the result through `normalizeRiskUpdate` below; the
    // other response shapes (sessions, model status) are not safety-relevant.
    return (await response.json()) as T;
  } catch (err) {
    if (timedOut && !(err instanceof ApiError))
      throw new DOMException(
        `Request timed out after ${REQUEST_TIMEOUT_MS / 1000} s`,
        "TimeoutError",
      );
    throw err;
  } finally {
    clearTimeout(timeout);
    options.signal?.removeEventListener("abort", abort);
  }
}

export interface ModelStatus {
  models_loaded: boolean;
  provider: string;
  vision: { architecture: string; sha256: string };
  telemetry: { architecture: string; sha256: string };
  scope: string;
}
export type { LivePayload };
const asRecords = (raw: StoredRiskUpdate[]) =>
  raw.map((record) => normalizeRiskUpdate(record));

export const api = {
  models: (signal?: AbortSignal) => request<ModelStatus>("/models", { signal }),
  create: (config: AppConfig, signal?: AbortSignal) =>
    request<SessionMeta>("/sessions", {
      method: "POST",
      signal,
      body: JSON.stringify({
        operation_mode: "LIVE_MODEL_RUNTIME",
        description:
          "Live camera + prepared raw telemetry through trained models",
        config: {
          weight_vision: config.weightVision,
          weight_telemetry: config.weightTelemetry,
          threshold_low: config.thresholdLow,
          threshold_high: config.thresholdHigh,
          ema_alpha: config.emaAlpha,
          freshness_tolerance_s: config.freshnessTolerance,
        },
      }),
    }),
  /**
   * `attemptIndex` is 1 for the first delivery of a logical request and counts up
   * with every redelivery, automatic or manual. It travels as a header, NOT in the
   * body: the body is the idempotency key and must stay byte-identical.
   */
  infer: (
    sid: string,
    payload: LivePayload,
    signal: AbortSignal,
    attemptIndex: number,
  ) =>
    request<StoredRiskUpdate>(`/sessions/${encodeURIComponent(sid)}/infer`, {
      method: "POST",
      body: JSON.stringify(payload),
      headers: { "X-Attempt-Index": String(attemptIndex) },
      signal,
    }).then(normalizeRiskUpdate),
  sessions: (signal?: AbortSignal) =>
    request<SessionMeta[]>("/sessions?limit=100", { signal }),
  session: (sid: string, signal?: AbortSignal) =>
    request<SessionMeta>(`/sessions/${encodeURIComponent(sid)}`, { signal }),
  latest: (sid: string, signal?: AbortSignal) =>
    request<StoredRiskUpdate>(
      `/sessions/${encodeURIComponent(sid)}/risk/latest`,
      { signal },
    ).then(normalizeRiskUpdate),
  windows: (sid: string, after = 0, signal?: AbortSignal) =>
    request<StoredRiskUpdate[]>(
      `/sessions/${encodeURIComponent(sid)}/windows?after=${after}&limit=500`,
      { signal },
    ).then(asRecords),
  flag: (sid: string, id: number, flagged: boolean, signal?: AbortSignal) =>
    request<StoredRiskUpdate>(
      `/sessions/${encodeURIComponent(sid)}/windows/${id}/flag?flagged=${flagged}`,
      { method: "PATCH", signal },
    ).then(normalizeRiskUpdate),
  exportUrl: (sid: string, format: "json" | "csv") =>
    `${API_BASE}/api/sessions/${encodeURIComponent(sid)}/export?format=${format}`,
};
