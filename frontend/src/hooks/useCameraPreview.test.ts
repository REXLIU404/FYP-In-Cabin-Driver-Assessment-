import { describe, expect, it } from "vitest";

import { diagnoseCapture, type CaptureProbe } from "./useCameraPreview";

// The capture reason codes are for DISPLAY and the log only (R5): a camera that
// stops, disconnects or is not ready never counts towards the D02 failure budget.
// They exist so that a silently dead camera no longer looks exactly like a
// deliberate "vision missing".
const READY: CaptureProbe = {
  hasStream: true,
  lastStop: null,
  readyState: 4,
  videoWidth: 640,
  trackState: "live",
  trackMuted: false,
};

describe("diagnoseCapture", () => {
  it("returns null when a frame can be drawn", () => {
    expect(diagnoseCapture(READY)).toBeNull();
    // HAVE_CURRENT_DATA (2) is the minimum the old code accepted too.
    expect(diagnoseCapture({ ...READY, readyState: 2 })).toBeNull();
  });

  it("a camera that was never started", () => {
    expect(
      diagnoseCapture({
        ...READY,
        hasStream: false,
        readyState: 0,
        videoWidth: 0,
        trackState: undefined,
      }),
    ).toBe("camera_not_started");
  });

  it("tells a deliberate Stop Camera from a camera that was taken away", () => {
    const gone = {
      ...READY,
      hasStream: false,
      readyState: 0,
      videoWidth: 0,
      trackState: undefined,
    };
    expect(diagnoseCapture({ ...gone, lastStop: "user" })).toBe(
      "stopped_by_user",
    );
    expect(diagnoseCapture({ ...gone, lastStop: "device" })).toBe(
      "device_disconnected",
    );
    expect(diagnoseCapture({ ...gone, lastStop: "start_failed" })).toBe(
      "start_failed",
    );
  });

  it("a track that has ended is a disconnection even before the hook has torn the stream down", () => {
    expect(diagnoseCapture({ ...READY, trackState: "ended" })).toBe(
      "device_disconnected",
    );
    expect(
      diagnoseCapture({
        ...READY,
        trackState: "ended",
        readyState: 0,
        videoWidth: 0,
      }),
    ).toBe("device_disconnected");
  });

  it("a stream that has no decodable picture yet is 'not_ready'", () => {
    expect(diagnoseCapture({ ...READY, readyState: 1 })).toBe("not_ready");
    expect(diagnoseCapture({ ...READY, videoWidth: 0 })).toBe("not_ready");
  });

  it("a muted track is reported as such", () => {
    expect(diagnoseCapture({ ...READY, trackMuted: true })).toBe("track_muted");
  });
});
