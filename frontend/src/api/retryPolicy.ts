import type {
  FailureClass,
  FaultCategory,
  LiveFault,
  RetryPolicy,
} from "../../../ai/src/liveLoop";
import { ApiError } from "./client";

export type { FailureClass, FaultCategory, RetryPolicy };

/**
 * D02 (user ruling, Option 1): one logical request is delivered at most 3 times -
 * the first send plus up to 2 automatic retries. The third failed delivery stops
 * the loop. This is a stated requirement, not a tuned value.
 */
export const MAX_ATTEMPTS_PER_REQUEST = 3;

/**
 * Wait after the Nth failed delivery before delivery N + 1: 2000 ms, then 4000 ms.
 * There is no third wait - the third failure stops the loop - so the type accepts
 * only 1 | 2. The 10 s cap is a defensive bound that 3 deliveries never reach.
 */
export function backoffMs(attemptIndex: 1 | 2): number {
  return Math.min(1000 * 2 ** attemptIndex, 10_000);
}

const named = (err: unknown, name: string) =>
  typeof err === "object" &&
  err !== null &&
  (err as { name?: unknown }).name === name;

const failure = (
  category: FaultCategory,
  retryable: boolean,
  counted: boolean,
  status?: number,
): FailureClass => ({ category, status, retryable, counted });

/**
 * 409 is overloaded (three server-side causes), so the detail decides. The
 * out-of-order case is the only one that is not a failure: a late frame is dropped.
 * An unrecognised 409 stops the loop - it is the safe reading of "same id, different
 * content". The texts are pinned by `test_retry_contract.py` on the backend side.
 */
function classifyConflict(detail: string): FailureClass {
  const text = detail.toLowerCase();
  if (text.includes("out-of-order"))
    return failure("conflict_stale_frame", false, false, 409);
  if (text.includes("operation mode") || text.includes("live model session"))
    return failure("conflict_mode", false, true, 409);
  return failure("conflict_hash", false, true, 409);
}

/**
 * Classify by STATUS CODE. The response body is read only where the status alone is
 * ambiguous (409, and 422 for a clock that runs ahead of the server's). A 500 is
 * not told apart by its body: `model_runtime` answers JSON, a storage failure or an
 * unknown error answers plain text, and both are retryable, so a 500 is reported as
 * `model_runtime` whatever its cause.
 */
function classifyHttp(status: number, detail: string): FailureClass {
  if (status === 409) return classifyConflict(detail);
  if (status === 422)
    return detail.toLowerCase().includes("timestamp is in the future")
      ? failure("clock_skew", false, true, status)
      : failure("input", false, true, status);
  if (status === 404) return failure("not_found", false, true, status);
  if (status === 503) return failure("models_unavailable", false, true, status);
  if (status === 500) return failure("model_runtime", true, true, status);
  if (status >= 500) return failure("storage", true, true, status);
  return failure("input", false, true, status); // 400 and every other 4xx
}

export function classifyFailure(err: unknown): FailureClass {
  if (err instanceof ApiError) return classifyHttp(err.status, err.message);
  if (named(err, "TimeoutError")) return failure("timeout", true, true);
  // The user paused, or the page unmounted: not a failure, so not counted.
  if (named(err, "AbortError")) return failure("aborted", false, false);
  // fetch rejected (network down, DNS, CORS, connection reset) or the body could
  // not be read: no valid HTTP answer was obtained.
  return failure("transport", true, true);
}

/** The production wiring of the injected policy (see ai/src/liveLoop.ts). */
export const RETRY_POLICY: RetryPolicy = {
  maxAttempts: MAX_ATTEMPTS_PER_REQUEST,
  backoffMs,
  classify: classifyFailure,
};

/**
 * The deliveries behind a stop, split into the loop's own and the user's. The split
 * is carried by the fault (`manualRetries`); it cannot be derived from `retryCount`,
 * because an error that a re-send cannot fix stops the loop after fewer than
 * `MAX_ATTEMPTS_PER_REQUEST` automatic deliveries.
 */
export function deliveryCounts(
  fault: Pick<LiveFault, "retryCount" | "manualRetries">,
): { automatic: number; manual: number } {
  return {
    automatic: fault.retryCount - fault.manualRetries,
    manual: fault.manualRetries,
  };
}

/** The stop panel's delivery line, e.g. "1 of 3 + 1 manual" (automatic of budget). */
export function deliveriesText(
  fault: Pick<LiveFault, "retryCount" | "manualRetries">,
): string {
  const { automatic, manual } = deliveryCounts(fault);
  return `${automatic} of ${MAX_ATTEMPTS_PER_REQUEST}${
    manual > 0 ? ` + ${manual} manual` : ""
  }`;
}

/** What the stop panel says. Every category has its own sentence. */
export const FAULT_TEXT: Record<
  FaultCategory,
  { title: string; advice: string }
> = {
  input: {
    title: "The server rejected the request as invalid",
    advice:
      "The same request would be rejected again. Check the camera frame and the telemetry input, then use Start Monitoring.",
  },
  clock_skew: {
    title: "This device's clock is ahead of the server's clock",
    advice:
      "The server refuses timestamps more than 5 seconds in the future. Correct the device clock (enable automatic time), then use Start Monitoring to capture a fresh request.",
  },
  not_found: {
    title: "The server no longer has this session",
    advice:
      "It was deleted or the server was reset. Retry creates a NEW session; the earlier windows stay with the old one.",
  },
  conflict_hash: {
    title: "The server saw the same request id with different content",
    advice:
      "This is a bug in the client, not a network problem. Start a new session and report it.",
  },
  conflict_mode: {
    title: "This session is not a live model session",
    advice:
      "The session was created in another mode. Use New Session to start a live one.",
  },
  conflict_stale_frame: {
    title: "A late frame was dropped",
    advice:
      "The server already holds newer evidence than this frame. Nothing to do; monitoring continues.",
  },
  models_unavailable: {
    title: "The trained models are not available on the server",
    advice:
      "The model files are missing or cannot be loaded. Retrying will not help until the deployment is fixed; fix it, then use Retry.",
  },
  model_runtime: {
    title: "The server failed while processing the frame",
    advice:
      "A model or storage error on the server (HTTP 500). The request was re-sent automatically and kept failing.",
  },
  storage: {
    title: "The server could not store the result",
    advice:
      "The server or a gateway in front of it answered with a 5xx error. Check the backend, then use Retry.",
  },
  timeout: {
    title: "The server did not answer in time",
    advice:
      "No answer within 10 seconds. The request was re-sent automatically and kept timing out. Check the backend, then use Retry.",
  },
  transport: {
    title: "The backend cannot be reached",
    advice:
      "The network request failed. Check that the backend is running and reachable, then use Retry.",
  },
  aborted: {
    title: "The request was cancelled",
    advice: "Monitoring was paused. Nothing failed.",
  },
};
