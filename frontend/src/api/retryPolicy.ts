import type {
  FailureClass,
  FaultCategory,
  LiveFault,
  RetryPolicy,
} from "../../../ai/src/liveLoop";
import { ApiError, NotFromBackendError, isNoDetailMessage } from "./client";

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
 * 409 is overloaded (four server-side causes), so the detail decides. The
 * out-of-order case is the only one that is not a failure: a late frame is dropped.
 * An observation conflict - an identity the server already holds, sent again with
 * different content or time - is a client error that no re-send can fix, so it stops.
 * An unrecognised 409 stops the loop too - it is the safe reading of "same id,
 * different content". The texts are pinned by `test_retry_contract.py` and
 * `OBSERVATION_CONFLICT_DETAIL` on the backend side.
 */
function classifyConflict(detail: string): FailureClass {
  const text = detail.toLowerCase();
  if (text.includes("observation identity"))
    return failure("observation_conflict", false, true, 409);
  if (text.includes("out-of-order"))
    return failure("conflict_stale_frame", false, false, 409);
  if (text.includes("operation mode") || text.includes("live model session"))
    return failure("conflict_mode", false, true, 409);
  return failure("conflict_hash", false, true, 409);
}

/**
 * Classify a BACKEND answer by STATUS CODE. The response body is read only where the
 * status alone is ambiguous (409, and 422 for a clock that runs ahead of the server's).
 * A 500 is not told apart by its body: `model_runtime` answers JSON, a storage failure or
 * an unknown error answers plain text, and both are retryable, so a 500 is reported as
 * `model_runtime` whatever its cause.
 *
 * It is only ever called for an answer that carries the backend's `X-DRA-Backend` marker
 * (see `classifyFailure`): an error answer without it is not the backend's 500, it is a
 * proxy or gateway standing in for a backend that did not answer.
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
  // An error answer the backend did not send (the dev proxy's own 500 when nothing listens
  // on port 8000, a gateway's 502 / 503 / 504): no answer from the backend was obtained, which
  // is what `transport` means. Checked before `ApiError`, which it extends, and never filed
  // under the status it carries - a 500 here is not a model or storage error.
  if (err instanceof NotFromBackendError)
    return failure("transport", true, true);
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

/**
 * What the stop panel says. Every category has its own sentence.
 *
 * `advice` is the sentence for a stop the loop reached by itself (the automatic
 * budget spent, or an error a re-send cannot fix). A category whose advice speaks of
 * automatic re-sends also has `adviceAfterManualRetry`, used when the stop is a
 * manual retry that failed - see `faultAdvice`.
 */
export const FAULT_TEXT: Record<
  FaultCategory,
  {
    title: string;
    // Setup (model check, session, reconcile) processes no frame, so a title that speaks of
    // one needs its own setup wording.
    titleInSetup?: string;
    advice: string;
    adviceAfterManualRetry?: string;
    // Setup (model check, session, reconcile) has no automatic re-sends, so a category
    // whose plain advice says "re-sent automatically" needs its own setup sentence.
    adviceInSetup?: string;
  }
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
  observation_conflict: {
    title:
      "The same observation identity was sent again with different content",
    advice:
      "The server already holds this camera frame or telemetry sample and received it again with other image bytes, values or acquisition time. This is a bug in the client, not a network problem; sending it again cannot fix it. Start a new session and report it.",
  },
  models_unavailable: {
    title: "The trained models are not available on the server",
    advice:
      "The model files are missing or cannot be loaded. Retrying will not help until the deployment is fixed; fix it, then use Retry.",
  },
  model_runtime: {
    title: "The server failed while processing the frame",
    titleInSetup: "The server failed while starting the session",
    advice:
      "A model or storage error on the server (HTTP 500). The request was re-sent automatically and kept failing.",
    adviceAfterManualRetry:
      "The retry you triggered failed with a model or storage error on the server (HTTP 500).",
    adviceInSetup:
      "A model or storage error on the server (HTTP 500) while starting the session. Check the backend, then use Retry.",
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
    adviceAfterManualRetry:
      "The retry you triggered got no answer in time. Check the backend, then use Retry.",
    adviceInSetup:
      "The server did not answer in time while starting the session. Check the backend, then use Retry.",
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

/** The stop panel's heading: the category's title, in the setup wording when the fault happened in setup. */
export function faultTitle(
  fault: Pick<LiveFault, "category"> & { phase?: LiveFault["phase"] },
): string {
  const text = FAULT_TEXT[fault.category];
  return fault.phase === "setup" && text.titleInSetup
    ? text.titleInSetup
    : text.title;
}

/**
 * The line under the details, and what to call it. The panel used to print every
 * `fault.message` as "Server message", but most of what lands there is not the server's:
 *
 * - a fault with no HTTP status never heard from the backend (a refused connection, a
 *   timeout, or - by the `X-DRA-Backend` rule - a proxy's answer): the text is the browser's or
 *   the client's own, so it is labelled "Details";
 * - an HTTP error whose body had no `detail` carries the client's fallback
 *   ("API request failed (500)"), which says nothing the category line does not: no line.
 *
 * Only a `detail` the backend actually sent is a "Server message".
 */
export function faultDetail(
  fault: Pick<LiveFault, "status" | "message">,
): { label: "Server message" | "Details"; text: string } | null {
  if (!fault.message) return null;
  if (fault.status === undefined)
    return { label: "Details", text: fault.message };
  if (isNoDetailMessage(fault.message)) return null;
  return { label: "Server message", text: fault.message };
}

/**
 * The advice sentence for a stopped fault, chosen by WHY the loop stopped.
 *
 * A stop that a Retry the user triggered caused - `manualRetries > 0` (a manual
 * delivery that failed) or `fromManualRetry` (also the reconcile before it, which
 * adds no delivery) - is not a spent automatic budget. "Re-sent automatically and
 * kept failing" would contradict the delivery line beside it ("1 of 3 + 1 manual" is
 * one automatic send) or, for a failed reconcile, nothing was re-sent at all; so the
 * sentence names the retry the user triggered instead.
 */
export function faultAdvice(
  fault: Pick<LiveFault, "category" | "manualRetries" | "fromManualRetry"> & {
    phase?: LiveFault["phase"];
  },
): string {
  const text = FAULT_TEXT[fault.category];
  if (fault.phase === "setup" && text.adviceInSetup && !fault.fromManualRetry)
    return text.adviceInSetup;
  return (fault.manualRetries > 0 || fault.fromManualRetry) &&
    text.adviceAfterManualRetry
    ? text.adviceAfterManualRetry
    : text.advice;
}

/**
 * What Retry will do, for the stop panel. It must follow `newSessionOnRetry` in the
 * setup phase as well as the delivery phase: a New Session whose setup failed makes
 * Retry create a session, not resume the old one.
 */
export function retryNote(
  fault: Pick<LiveFault, "phase" | "newSessionOnRetry">,
): string {
  if (fault.phase === "setup")
    return fault.newSessionOnRetry
      ? "Retry repeats the setup: the model check, then a NEW session."
      : "Retry repeats the setup: the model check, then the session.";
  return fault.newSessionOnRetry
    ? "Retry will create a NEW session."
    : "Retry re-sends this same request to the same session.";
}
