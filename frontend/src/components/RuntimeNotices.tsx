import { RotateCw } from "lucide-react";
import type { LiveFault } from "../../../ai/src/liveLoop";
import {
  MAX_ATTEMPTS_PER_REQUEST,
  deliveriesText,
  faultAdvice,
  faultDetail,
  faultTitle,
  retryNote,
} from "../api/retryPolicy";
import type { CameraEvent } from "../hooks/useCameraPreview";
import type { CameraStatus } from "../types";
import { formatFixed } from "../utils/format";
import { CAMERA_EVENT_TEXT, captureMissText } from "../utils/runtimeNotices";

/**
 * The visible stop (D02). While automatic retries are pending it is a plain status
 * line; once the loop has stopped it is a panel that nothing clears by itself -
 * only a successful delivery, Start Monitoring or loading a session does.
 */
export function FaultPanel({
  fault,
  retrying,
  onRetry,
}: {
  fault: LiveFault;
  retrying: boolean;
  onRetry: () => void;
}) {
  const title = faultTitle(fault);
  const detail = faultDetail(fault);
  if (!fault.stopped)
    return (
      <p className="runtime-warning" role="status">
        Delivery {fault.retryCount} of {MAX_ATTEMPTS_PER_REQUEST} failed:{" "}
        {title}. Retrying automatically…
      </p>
    );
  return (
    <section
      className="runtime-error"
      role="alert"
      aria-label="Monitoring stopped"
    >
      <strong>Monitoring stopped: {title}</strong>
      <p>{faultAdvice(fault)}</p>
      <div className="runtime-details">
        <span>
          Category: <code>{fault.category}</code>
          {fault.status ? ` (HTTP ${fault.status})` : ""}
        </span>
        {fault.phase === "setup" ? (
          <span>Failed during setup, before any request was sent</span>
        ) : (
          <>
            <span>
              Request id: <code>{fault.requestId}</code>
            </span>
            <span>Deliveries: {deliveriesText(fault)}</span>
          </>
        )}
      </div>
      {detail && (
        <p>
          {detail.label}: {detail.text}
        </p>
      )}
      <p>{retryNote(fault)}</p>
      <button
        type="button"
        className="button"
        onClick={onRetry}
        disabled={retrying}
      >
        <RotateCw size={16} />
        {retrying ? "Retrying…" : "Retry"}
      </button>
    </section>
  );
}

/** Why requests carry no image right now. Monitoring continues (R5). */
export function CaptureMissNotice({ reason }: { reason: string }) {
  return (
    <p className="runtime-warning" role="status">
      No camera image is being sent ({captureMissText(reason)}). Vision evidence
      is missing; monitoring continues with telemetry only.
    </p>
  );
}

/** The camera's state and, if it ended, who ended it. */
export function CameraStatusLine({
  status,
  actualFps,
  event,
}: {
  status: CameraStatus;
  actualFps: number | null;
  event: CameraEvent | null;
}) {
  return (
    <span>
      Camera: {status}
      {actualFps ? ` · ${formatFixed(actualFps, 1)} FPS` : ""}
      {event
        ? ` · ${CAMERA_EVENT_TEXT[event.kind]} at ${new Date(event.at).toLocaleTimeString()}`
        : ""}
    </span>
  );
}
