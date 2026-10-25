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

/**
 * Every response of this backend carries this header (backend/app/main.py). An error answer
 * WITHOUT it was not the backend's: with no backend on port 8000 the Vite dev proxy answers
 * `/api` calls with an HTTP 500 of its own, and a gateway in front of a stopped backend answers
 * 502 / 503 / 504. The backend's own 500 (`model_runtime`) must not be confused with that.
 */
const BACKEND_MARKER_HEADER = "X-DRA-Backend";

/**
 * A non-2xx answer that does not carry the backend's marker: something between the page and the
 * backend answered, the backend did not. It is the same situation as a refused connection, so
 * `retryPolicy.classifyFailure` files it under `transport` - never under the status code it
 * happens to carry. The status stays here only for the message.
 */
export class NotFromBackendError extends ApiError {
  constructor(status: number) {
    super(
      `the API proxy or a gateway answered HTTP ${status} and the backend did not; is the backend running?`,
      status,
    );
  }
}

/** What `request` says when the server sent no `detail`: the client's own words, not the server's. */
const noDetailMessage = (status: number) => `API request failed (${status})`;

/** Is `message` the client's own fallback for an error answer with no `detail`? */
export const isNoDetailMessage = (message: string) =>
  /^API request failed \(\d{3}\)$/.test(message);

/** The client's own deadline for one call. The loop's 10 s delivery deadline fires first. */
const REQUEST_TIMEOUT_MS = 15000;

async function request<T>(
  path: string,
  options: RequestInit = {},
  /** Sees a successful response before its body is read (e.g. for a response header). */
  onOk?: (response: Response) => void,
): Promise<T> {
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
      if (!response.headers.has(BACKEND_MARKER_HEADER))
        throw new NotFromBackendError(response.status);
      const body = await response.json().catch(() => ({}));
      const detail = Array.isArray(body.detail)
        ? body.detail.map((item: { msg: string }) => item.msg).join("; ")
        : body.detail;
      throw new ApiError(
        detail || noDetailMessage(response.status),
        response.status,
      );
    }
    onOk?.(response);
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
    onServerTiming?: (header: string | null) => void,
  ) =>
    request<StoredRiskUpdate>(
      `/sessions/${encodeURIComponent(sid)}/infer`,
      {
        method: "POST",
        body: JSON.stringify(payload),
        headers: { "X-Attempt-Index": String(attemptIndex) },
        signal,
      },
      (response) => onServerTiming?.(response.headers.get("Server-Timing")),
    ).then(normalizeRiskUpdate),
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
