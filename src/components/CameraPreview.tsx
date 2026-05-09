import { Camera, CameraOff, RefreshCw, Square } from "lucide-react";
import type { RefObject } from "react";
import type { CameraStatus } from "../types";

interface CameraPreviewProps {
  videoRef: RefObject<HTMLVideoElement>;
  status: CameraStatus;
  onStart: () => void;
  onStop: () => void;
}

const statusText: Record<CameraStatus, string> = {
  idle: "Camera preview idle",
  requesting: "Requesting camera permission",
  live: "Browser camera preview live",
  denied: "Camera permission denied",
  error: "Camera preview unavailable",
};

export function CameraPreview({
  videoRef,
  status,
  onStart,
  onStop,
}: CameraPreviewProps) {
  const isLive = status === "live";

  return (
    <div className={`camera-preview camera-preview--${status}`}>
      <video
        ref={videoRef}
        muted
        playsInline
        aria-label="Browser camera preview"
      />
      {!isLive ? (
        <div className="camera-placeholder">
          {status === "denied" || status === "error" ? (
            <CameraOff size={34} />
          ) : (
            <Camera size={34} />
          )}
          <strong>{statusText[status]}</strong>
        </div>
      ) : null}
      <div className="camera-actions">
        <button
          type="button"
          className="button button--primary"
          onClick={onStart}
        >
          <RefreshCw size={16} />
          Start Camera
        </button>
        <button type="button" className="button" onClick={onStop}>
          <Square size={16} />
          Stop Camera
        </button>
      </div>
    </div>
  );
}
