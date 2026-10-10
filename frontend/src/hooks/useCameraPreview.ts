import { useCallback, useEffect, useRef, useState } from "react";
import type { CameraStatus } from "../types";

export function useCameraPreview() {
  const previewRef = useRef<HTMLVideoElement | null>(null);
  const captureRef = useRef<HTMLVideoElement | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const generation = useRef(0);
  const [status, setStatus] = useState<CameraStatus>("idle");
  const [actualFps, setActualFps] = useState<number | null>(null);

  const videoRef = useCallback((node: HTMLVideoElement | null) => {
    previewRef.current = node;
    if (node && streamRef.current) {
      node.srcObject = streamRef.current;
      void node.play().catch(() => undefined);
    }
  }, []);

  const stop = useCallback(() => {
    generation.current++;
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    if (previewRef.current) previewRef.current.srcObject = null;
    if (captureRef.current) captureRef.current.srcObject = null;
    captureRef.current = null;
    setActualFps(null);
    setStatus("idle");
  }, []);

  const start = useCallback(async () => {
    if (!navigator.mediaDevices?.getUserMedia) {
      setStatus("error");
      return;
    }
    stop();
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
          stop();
          setStatus("error");
        }
      });
      setActualFps(track.getSettings().frameRate ?? null);
      setStatus("live");
    } catch (error) {
      if (current !== generation.current) return;
      stop();
      const name = error instanceof DOMException ? error.name : "";
      setStatus(name === "NotAllowedError" ? "denied" : "error");
    }
  }, [stop]);

  const captureFrame = useCallback(() => {
    const video = captureRef.current;
    const track = streamRef.current?.getVideoTracks()[0];
    if (
      !video ||
      video.readyState < 2 ||
      !video.videoWidth ||
      track?.readyState !== "live" ||
      track.muted
    )
      return null;
    const canvas = canvasRef.current ?? document.createElement("canvas");
    canvasRef.current = canvas;
    canvas.width = 640;
    canvas.height = Math.round((640 * video.videoHeight) / video.videoWidth);
    canvas
      .getContext("2d")
      ?.drawImage(video, 0, 0, canvas.width, canvas.height);
    return {
      image_base64: canvas.toDataURL("image/jpeg", 0.85),
      captured_at: new Date().toISOString(),
    };
  }, []);

  useEffect(() => () => stop(), [stop]);
  return { videoRef, status, start, stop, captureFrame, actualFps };
}
