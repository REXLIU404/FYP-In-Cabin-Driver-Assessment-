import { useCallback, useEffect, useRef, useState } from "react";
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
  | { frame: { image_base64: string; captured_at: string }; reason: null }
  | { frame: null; reason: CaptureMiss };

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
    if (captureRef.current) captureRef.current.srcObject = null;
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
      captureRef.current = capture;
      await capture.play();
      if (current !== generation.current) return;
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
    const canvas = canvasRef.current ?? document.createElement("canvas");
    canvasRef.current = canvas;
    canvas.width = 640;
    canvas.height = Math.round((640 * video.videoHeight) / video.videoWidth);
    canvas
      .getContext("2d")
      ?.drawImage(video, 0, 0, canvas.width, canvas.height);
    return {
      frame: {
        image_base64: canvas.toDataURL("image/jpeg", 0.85),
        captured_at: new Date().toISOString(),
      },
      reason: null,
    };
  }, []);

  useEffect(() => () => release(null), [release]);
  return { videoRef, status, start, stop, captureFrame, actualFps, event };
}
