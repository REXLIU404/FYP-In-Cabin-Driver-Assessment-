import type { AppConfig, SessionMeta, TelemetryFeatures } from "../types";
import {
  normalizeRiskUpdate,
  type StoredRiskUpdate,
} from "../../../ai/src/availability";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "";
export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const controller = new AbortController();
  const abort = () => controller.abort();
  if (options.signal?.aborted) abort();
  options.signal?.addEventListener("abort", abort, { once: true });
  const timeout = setTimeout(abort, 15000);
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
export interface LivePayload {
  request_id: string;
  image_base64: string | null;
  captured_at: string | null;
  telemetry_features: TelemetryFeatures | null;
  telemetry_timestamp: string | null;
  telemetry_source: "prepared_replay" | "missing";
}
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
  infer: (sid: string, payload: LivePayload, signal: AbortSignal) =>
    request<StoredRiskUpdate>(`/sessions/${encodeURIComponent(sid)}/infer`, {
      method: "POST",
      body: JSON.stringify(payload),
      signal,
    }).then(normalizeRiskUpdate),
  sessions: () => request<SessionMeta[]>("/sessions?limit=100"),
  session: (sid: string) =>
    request<SessionMeta>(`/sessions/${encodeURIComponent(sid)}`),
  latest: (sid: string) =>
    request<StoredRiskUpdate>(
      `/sessions/${encodeURIComponent(sid)}/risk/latest`,
    ).then(normalizeRiskUpdate),
  windows: (sid: string, after = 0) =>
    request<StoredRiskUpdate[]>(
      `/sessions/${encodeURIComponent(sid)}/windows?after=${after}&limit=500`,
    ).then(asRecords),
  flag: (sid: string, id: number, flagged: boolean) =>
    request<StoredRiskUpdate>(
      `/sessions/${encodeURIComponent(sid)}/windows/${id}/flag?flagged=${flagged}`,
      { method: "PATCH" },
    ).then(normalizeRiskUpdate),
  exportUrl: (sid: string, format: "json" | "csv") =>
    `${API_BASE}/api/sessions/${encodeURIComponent(sid)}/export?format=${format}`,
};
