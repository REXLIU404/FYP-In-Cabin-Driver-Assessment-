import type { CameraStop } from "../hooks/useCameraPreview";

/**
 * Why no camera image is being sent, in words. Two of these are easy to confuse and
 * must not read alike: `stopped_by_user` (the person pressed Stop Camera) and
 * `device_disconnected` (the stream died on its own - unplugged, permission revoked).
 * Display only: neither is a D02 failure and neither stops monitoring (R5).
 */
export const CAPTURE_MISS_TEXT: Record<string, string> = {
  camera_not_started: "the camera has not been started",
  stopped_by_user: "the camera was stopped",
  device_disconnected: "the camera was disconnected",
  start_failed: "the camera could not be started",
  not_ready: "the camera has no picture yet",
  track_muted: "the camera is muted",
  capture_error: "the frame could not be captured",
};

/** The camera event on the status line: the same split, by who ended the stream. */
export const CAMERA_EVENT_TEXT: Record<CameraStop, string> = {
  user: "stopped by you",
  device: "disconnected",
  start_failed: "failed to start",
};

/** The words for a capture-miss reason code; an unknown code is shown as it is. */
export const captureMissText = (reason: string): string =>
  CAPTURE_MISS_TEXT[reason] ?? reason;

/**
 * What the stop panel's Retry button does: it hands the frozen request back to the
 * loop's own `retry()` - the same session, the same payload. It is NOT `start(true)`
 * (New Session), which would abandon the request and the session. Kept as a function
 * so a test can click it without a DOM.
 */
export const retryHandler = (live: { retry(): Promise<void> }) => (): void => {
  void live.retry();
};
