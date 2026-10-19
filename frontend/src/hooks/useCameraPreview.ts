import { useCallback, useEffect, useRef, useState } from "react";
import type { LiveFrame } from "../../../ai/src/liveLoop";
import type { CameraStatus } from "../types";

/** Why there is no picture. For display and the log only: never a D02 failure. */
export type CaptureMiss =
  | "camera_not_started"
  | "stopped_by_user"
  | "device_disconnected"
  | "start_failed"
  | "not_ready"
  | "track_muted";

/** Why the stream is gone, when it is. */
export type CameraStop = "user" | "device" | "start_failed";

export interface CaptureProbe {
  hasStream: boolean;
  lastStop: CameraStop | null;
  /** `HTMLVideoElement.readyState` of the capture element (0 when there is none). */
  readyState: number;
  videoWidth: number;
  trackState: "live" | "ended" | undefined;
  trackMuted: boolean;
}

/**
 * `null` when a frame can be drawn, otherwise the reason it cannot. The old code
 * returned a bare `null`, so a camera that died silently looked exactly like a
 * deliberate "vision missing"; the monitoring loop still sends the request either
 * way (R5), but the person can now be told which it was.
 */
export function diagnoseCapture(probe: CaptureProbe): CaptureMiss | null {
  if (!probe.hasStream) {
    if (probe.lastStop === "user") return "stopped_by_user";
    if (probe.lastStop === "device") return "device_disconnected";
    if (probe.lastStop === "start_failed") return "start_failed";
    return "camera_not_started";
  }
  if (probe.trackState === "ended") return "device_disconnected";
  if (probe.readyState < 2 || !probe.videoWidth) return "not_ready";
  if (probe.trackMuted) return "track_muted";
  return null;
}

export type CaptureResult =
  | { frame: LiveFrame; reason: null }
  | { frame: null; reason: CaptureMiss };

/**
 * The part of `VideoFrameCallbackMetadata` a frame's identity and time come from.
 * `captureTime` is on the `performance.now()` timeline and only some sources provide it.
 */
export interface FrameCallbackMetadata {
  presentedFrames: number;
  captureTime?: number;
}

/**
 * The epoch of a camera start (R10): strictly greater than every earlier one, so the
 * server never sees a frame identity step backwards. It is the start time in whole
 * milliseconds, which stays larger than the epochs of earlier page loads (a counter
 * that began at 0 on each load would put a reloaded page BEHIND the session it
 * resumes, and every frame would be refused as out of order); `previous + 1` covers a
 * clock that stands still or steps back and two starts in the same millisecond.
 */
export const nextCameraEpoch = (previous: number, nowMs: number): number =>
  Math.max(Math.floor(nowMs), previous + 1);

/**
 * How long after registering for frame callbacks the first one may take. A browser that
 * never calls back (no support, or a `<video>` it does not render) is then served by the
 * fallback mode.
 */
export const FRAME_CALLBACK_DEADLINE_MS = 1000;

/**
 * `waiting`  registered, no callback yet, still inside the deadline.
 * `explicit` frames carry their `(epoch, index)` and are captured in the callback.
 * `fallback` the server identifies frames by their bytes. Final for this camera start:
 *            the server's identity watermark must not see explicit and fallback frames
 *            alternate, so a callback that arrives later is ignored.
 */
export type FrameCaptureMode = "waiting" | "explicit" | "fallback";

export interface FrameCaptureDeps {
  /** From `nextCameraEpoch`, once per camera start. */
  epoch: number;
  /** `false` when the `<video>` has no `requestVideoFrameCallback`. */
  callbacksSupported: boolean;
  /** Wall clock in epoch milliseconds (`Date.now`). */
  now(): number;
  /** `performance.timeOrigin`: converts a `captureTime` to epoch milliseconds. */
  timeOrigin: number;
  /** Draw the current video picture and encode it, or `null` when it cannot. */
  draw(): string | null;
}

export interface FrameCapture {
  /** Called from `requestVideoFrameCallback`: capture NOW and remember the tuple. */
  onFrame(metadata: FrameCallbackMetadata): void;
  /** What the next request carries: the newest cached tuple, a fallback capture, or `null`. */
  take(): LiveFrame | null;
  mode(): FrameCaptureMode;
}

/**
 * The frame source of one camera start.
 *
 * Explicit mode. Every callback draws the picture immediately and caches ONE tuple:
 * the bytes with the `(epoch, presentedFrames)` and the acquisition time that belong
 * to them. `take()` hands out the newest tuple and never draws, so a tick that comes
 * before the next camera frame gets the same tuple again (the server counts it as a
 * REPEAT), and no tuple can pair one capture's metadata with another's bytes.
 * Acquisition time: `performance.timeOrigin + captureTime` when the browser provides
 * a capture time (source `capture_time`), else the moment the callback ran (`callback`).
 *
 * Fallback mode. `take()` draws at the tick, with no frame identity and the page clock
 * as its time (`client_clock`); the server identifies the frame by its bytes.
 */
export function createFrameCapture(deps: FrameCaptureDeps): FrameCapture {
  const registeredAt = deps.now();
  let mode: FrameCaptureMode = deps.callbacksSupported ? "waiting" : "fallback";
  let latest: LiveFrame | null = null;

  // Past the deadline without a single callback: fall back, for good.
  const settle = (nowMs: number) => {
    if (
      mode === "waiting" &&
      nowMs - registeredAt >= FRAME_CALLBACK_DEADLINE_MS
    )
      mode = "fallback";
  };
  const drawn = (): string | null => {
    try {
      return deps.draw();
    } catch {
      return null; // a tainted canvas or a lost context: no picture this time
    }
  };

  return {
    mode: () => mode,
    onFrame(metadata) {
      const callbackAt = deps.now();
      settle(callbackAt);
      if (mode === "fallback") return;
      const image = drawn();
      if (image === null) return;
      // A capture time that cannot be turned into a date is no capture time.
      const capturedMs =
        typeof metadata.captureTime === "number"
          ? deps.timeOrigin + metadata.captureTime
          : Number.NaN;
      const hasCaptureTime = !Number.isNaN(new Date(capturedMs).getTime());
      const tuple: LiveFrame = {
        image_base64: image,
        captured_at: new Date(
          hasCaptureTime ? capturedMs : callbackAt,
        ).toISOString(),
        captured_at_source: hasCaptureTime ? "capture_time" : "callback",
        vision_frame: { epoch: deps.epoch, index: metadata.presentedFrames },
      };
      latest = tuple;
      mode = "explicit";
    },
    take() {
      settle(deps.now());
      if (mode === "explicit") return latest;
      if (mode === "waiting") return null;
      const image = drawn();
      if (image === null) return null;
      return {
        image_base64: image,
        captured_at: new Date(deps.now()).toISOString(),
        captured_at_source: "client_clock",
      };
    },
  };
}

/** The current picture as a 640-wide JPEG data URL, or `null` if there is none to draw. */
const drawFrame = (
  video: HTMLVideoElement,
  canvas: HTMLCanvasElement,
): string | null => {
  if (!video.videoWidth) return null;
  canvas.width = 640;
  canvas.height = Math.round((640 * video.videoHeight) / video.videoWidth);
  const context = canvas.getContext("2d");
  if (!context) return null;
  context.drawImage(video, 0, 0, canvas.width, canvas.height);
  return canvas.toDataURL("image/jpeg", 0.85);
};

/**
 * The capture `<video>` has to be in the document. Chromium presents no frames for a
 * detached element, so `requestVideoFrameCallback` never fires on it. Measured once, on
 * a canvas stream in Chromium 152 (not on a camera): 0 callbacks in 1.5 s detached, 45
 * attached and hidden. It is 1x1, transparent, inert and out of the accessibility tree.
 */
const hideCaptureElement = (video: HTMLVideoElement) => {
  video.setAttribute("aria-hidden", "true");
  video.tabIndex = -1;
  video.style.cssText =
    "position:fixed;left:0;top:0;width:1px;height:1px;opacity:0;pointer-events:none";
};

/** A camera event worth showing; it never stops monitoring. */
export interface CameraEvent {
  kind: CameraStop;
  at: string;
}

export function useCameraPreview() {
  const previewRef = useRef<HTMLVideoElement | null>(null);
  const captureRef = useRef<HTMLVideoElement | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const generation = useRef(0);
  const framesRef = useRef<FrameCapture | null>(null);
  const frameCallbackRef = useRef<number | null>(null);
  const lastEpoch = useRef(0);
  const lastStop = useRef<CameraStop | null>(null);
  const [status, setStatus] = useState<CameraStatus>("idle");
  const [actualFps, setActualFps] = useState<number | null>(null);
  const [event, setEvent] = useState<CameraEvent | null>(null);

  const videoRef = useCallback((node: HTMLVideoElement | null) => {
    previewRef.current = node;
    if (node && streamRef.current) {
      node.srcObject = streamRef.current;
      void node.play().catch(() => undefined);
    }
  }, []);

  /** `cause` is why the stream is being released; null for internal housekeeping. */
  const release = useCallback((cause: CameraStop | null) => {
    const hadStream = streamRef.current !== null;
    generation.current++;
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    if (previewRef.current) previewRef.current.srcObject = null;
    if (captureRef.current) {
      if (frameCallbackRef.current !== null)
        captureRef.current.cancelVideoFrameCallback?.(frameCallbackRef.current);
      captureRef.current.srcObject = null;
      captureRef.current.remove();
    }
    frameCallbackRef.current = null;
    framesRef.current = null;
    captureRef.current = null;
    if (cause === null) lastStop.current = null;
    else if (cause !== "user" || hadStream) {
      // Pressing Stop Camera with nothing running is not an event.
      lastStop.current = cause;
      setEvent({ kind: cause, at: new Date().toISOString() });
    }
    setActualFps(null);
    setStatus("idle");
  }, []);

  const stop = useCallback(() => release("user"), [release]);

  const start = useCallback(async () => {
    if (!navigator.mediaDevices?.getUserMedia) {
      lastStop.current = "start_failed";
      setEvent({ kind: "start_failed", at: new Date().toISOString() });
      setStatus("error");
      return;
    }
    release(null);
    setEvent(null);
    const current = generation.current;
    setStatus("requesting");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: {
          width: { ideal: 640 },
          height: { ideal: 480 },
          frameRate: { ideal: 30, max: 30 },
        },
        audio: false,
      });
      if (current !== generation.current) {
        stream.getTracks().forEach((track) => track.stop());
        return;
      }
      streamRef.current = stream;
      const capture = document.createElement("video");
      capture.muted = true;
      capture.playsInline = true;
      capture.srcObject = stream;
      hideCaptureElement(capture);
      document.body.appendChild(capture);
      captureRef.current = capture;
      await capture.play();
      if (current !== generation.current) return;
      // The frame source of THIS camera start: a new epoch, a new cache, a new mode.
      const epoch = nextCameraEpoch(lastEpoch.current, Date.now());
      lastEpoch.current = epoch;
      const canvas = canvasRef.current ?? document.createElement("canvas");
      canvasRef.current = canvas;
      const frames = createFrameCapture({
        epoch,
        callbacksSupported:
          typeof capture.requestVideoFrameCallback === "function",
        now: () => Date.now(),
        timeOrigin: performance.timeOrigin,
        draw: () => drawFrame(capture, canvas),
      });
      framesRef.current = frames;
      if (typeof capture.requestVideoFrameCallback === "function") {
        const onFrame: VideoFrameRequestCallback = (_now, metadata) => {
          if (current !== generation.current) return;
          // Register the next callback first: whatever happens below, the chain goes on.
          frameCallbackRef.current = capture.requestVideoFrameCallback(onFrame);
          frames.onFrame(metadata);
        };
        frameCallbackRef.current = capture.requestVideoFrameCallback(onFrame);
      }
      if (previewRef.current) {
        previewRef.current.srcObject = stream;
        await previewRef.current.play().catch(() => undefined);
      }
      const track = stream.getVideoTracks()[0];
      track.addEventListener("ended", () => {
        if (current === generation.current) {
          // The device went away (unplugged, permission revoked): record it and show
          // it. Monitoring is NOT told to stop - requests carry on without an image.
          release("device");
          setStatus("error");
        }
      });
      lastStop.current = null;
      setActualFps(track.getSettings().frameRate ?? null);
      setStatus("live");
    } catch (error) {
      if (current !== generation.current) return;
      release("start_failed");
      const name = error instanceof DOMException ? error.name : "";
      setStatus(name === "NotAllowedError" ? "denied" : "error");
    }
  }, [release]);

  const captureFrame = useCallback((): CaptureResult => {
    const video = captureRef.current;
    const track = streamRef.current?.getVideoTracks()[0];
    const miss = diagnoseCapture({
      hasStream: Boolean(video && track),
      lastStop: lastStop.current,
      readyState: video?.readyState ?? 0,
      videoWidth: video?.videoWidth ?? 0,
      trackState: track?.readyState,
      trackMuted: track?.muted ?? false,
    });
    if (miss || !video) return { frame: null, reason: miss ?? "not_ready" };
    // The frame source decides what a request carries; this hook never draws here.
    const frame = framesRef.current?.take() ?? null;
    return frame
      ? { frame, reason: null }
      : { frame: null, reason: "not_ready" };
  }, []);

  useEffect(() => () => release(null), [release]);
  return { videoRef, status, start, stop, captureFrame, actualFps, event };
}
