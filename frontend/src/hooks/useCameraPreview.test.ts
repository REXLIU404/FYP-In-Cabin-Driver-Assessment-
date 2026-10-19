import { describe, expect, it, vi } from "vitest";

import hookSource from "./useCameraPreview.ts?raw";
import {
  createFrameCapture,
  diagnoseCapture,
  nextCameraEpoch,
  type CaptureProbe,
  type FrameCaptureDeps,
} from "./useCameraPreview";

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

// ---------------------------------------------------------------------------------------
// R10-B (B2). The camera hands the loop a frame TUPLE: the bytes, the (epoch, index) and
// the acquisition time that belong to them, captured in one step. These tests are the pure
// logic only (tuple cache, epoch, fallback decision); that a real browser calls
// requestVideoFrameCallback, and whether it provides a captureTime, is measured in Task 10
// part 2.
// ---------------------------------------------------------------------------------------
describe("nextCameraEpoch: every camera start has a larger epoch than any before it", () => {
  it("is the start time in whole milliseconds", () => {
    expect(nextCameraEpoch(0, 1_800_000_000_123)).toBe(1_800_000_000_123);
    expect(nextCameraEpoch(0, 1_800_000_000_123.9)).toBe(1_800_000_000_123);
  });

  it("a page that was reloaded (its own counter back at 0) still starts above the epoch it gave before", () => {
    // A counter that began at 0 would give 1 both times and put the reloaded page
    // BEHIND the session it resumes: every frame refused as out of order.
    const before = nextCameraEpoch(0, 1_800_000_000_123);
    const afterReload = nextCameraEpoch(0, 1_800_000_060_000);
    expect(afterReload).toBeGreaterThan(before);
    expect(afterReload).toBe(1_800_000_060_000);
  });

  it("is strictly increasing within a page: two starts in one millisecond, and a clock that stepped back", () => {
    expect(nextCameraEpoch(1_800_000_000_123, 1_800_000_000_123)).toBe(
      1_800_000_000_124,
    );
    expect(nextCameraEpoch(1_800_000_000_124, 1_700_000_000_000)).toBe(
      1_800_000_000_125,
    );
  });
});

describe("createFrameCapture: explicit mode caches one tuple per frame callback", () => {
  // timeOrigin 1_700_000_000_000 is 2023-11-14T22:13:20.000Z; the callback runs at
  // 22:13:25.000Z. captureTime 1234.5 ms after the origin is 22:13:21.234Z.
  const setup = (over: Partial<FrameCaptureDeps> = {}) => {
    const clock = { now: 1_700_000_005_000 };
    let drawn = 0;
    const draw = vi.fn((): string | null => `jpeg-${++drawn}`);
    const capture = createFrameCapture({
      epoch: 1_800_000_000_000,
      callbacksSupported: true,
      now: () => clock.now,
      timeOrigin: 1_700_000_000_000,
      draw,
      ...over,
    });
    return { clock, draw, capture };
  };

  it("with a captureTime the acquisition time is timeOrigin + captureTime, and its source says so", () => {
    const { capture } = setup();
    capture.onFrame({ presentedFrames: 241, captureTime: 1234.5 });
    expect(capture.take()).toEqual({
      image_base64: "jpeg-1",
      captured_at: "2023-11-14T22:13:21.234Z",
      captured_at_source: "capture_time",
      vision_frame: { epoch: 1_800_000_000_000, index: 241 },
    });
    expect(capture.mode()).toBe("explicit");
  });

  it("without a captureTime the acquisition time is the moment of the callback, and its source says so", () => {
    const { capture } = setup();
    capture.onFrame({ presentedFrames: 7 });
    expect(capture.take()).toEqual({
      image_base64: "jpeg-1",
      captured_at: "2023-11-14T22:13:25.000Z",
      captured_at_source: "callback",
      vision_frame: { epoch: 1_800_000_000_000, index: 7 },
    });
  });

  it.each([Number.NaN, Number.POSITIVE_INFINITY, 1e20])(
    "a captureTime of %s is no capture time: the callback moment is used",
    (captureTime) => {
      const { capture } = setup();
      capture.onFrame({ presentedFrames: 7, captureTime });
      expect(capture.take()).toMatchObject({
        captured_at: "2023-11-14T22:13:25.000Z",
        captured_at_source: "callback",
      });
    },
  );

  it("the picture is drawn IN the callback and its time is the callback's, however late a tick asks for it", () => {
    const { capture, clock, draw } = setup();
    capture.onFrame({ presentedFrames: 3 });
    expect(draw).toHaveBeenCalledTimes(1);
    clock.now += 700; // a tick comes 700 ms later
    expect(capture.take()).toMatchObject({
      image_base64: "jpeg-1",
      captured_at: "2023-11-14T22:13:25.000Z",
    });
  });

  it("ticks between two camera frames get the SAME tuple and draw nothing: bytes, index and time stay together", () => {
    const { capture, draw } = setup();
    capture.onFrame({ presentedFrames: 10, captureTime: 1234.5 });
    const first = capture.take();
    expect(capture.take()).toEqual(first);
    expect(capture.take()).toEqual(first);
    expect(draw).toHaveBeenCalledTimes(1);
  });

  it("a newer callback replaces the tuple as a whole - the old index is never paired with the new bytes", () => {
    const { capture, draw } = setup();
    capture.onFrame({ presentedFrames: 10, captureTime: 1234.5 });
    capture.onFrame({ presentedFrames: 11, captureTime: 1267.5 });
    capture.take();
    capture.take();
    expect(capture.take()).toEqual({
      image_base64: "jpeg-2",
      captured_at: "2023-11-14T22:13:21.267Z",
      captured_at_source: "capture_time",
      vision_frame: { epoch: 1_800_000_000_000, index: 11 },
    });
    expect(draw).toHaveBeenCalledTimes(2); // once per callback, never per tick
  });

  it("a callback whose picture cannot be drawn leaves no tuple", () => {
    const { capture } = setup({ draw: () => null });
    capture.onFrame({ presentedFrames: 1 });
    expect(capture.take()).toBeNull();
    expect(capture.mode()).toBe("waiting");
  });

  it("a draw that throws (a tainted canvas) is a picture that cannot be drawn, not an error in the callback", () => {
    const { capture } = setup({
      draw: () => {
        throw new Error("The canvas has been tainted");
      },
    });
    expect(() => capture.onFrame({ presentedFrames: 1 })).not.toThrow();
    expect(capture.take()).toBeNull();
  });

  it("once explicit it stays explicit: a minute without callbacks keeps serving the last tuple (it will expire on the server)", () => {
    const { capture, clock } = setup();
    capture.onFrame({ presentedFrames: 5 });
    clock.now += 60_000;
    expect(capture.mode()).toBe("explicit");
    expect(capture.take()).toMatchObject({
      image_base64: "jpeg-1",
      vision_frame: { epoch: 1_800_000_000_000, index: 5 },
    });
    expect(capture.mode()).toBe("explicit");
  });
});

describe("createFrameCapture: no callbacks means the fallback mode, and the fallback is final", () => {
  const setup = (over: Partial<FrameCaptureDeps> = {}) => {
    const clock = { now: 1_700_000_005_000 };
    let drawn = 0;
    const draw = vi.fn((): string | null => `jpeg-${++drawn}`);
    const capture = createFrameCapture({
      epoch: 1_800_000_000_000,
      callbacksSupported: true,
      now: () => clock.now,
      timeOrigin: 1_700_000_000_000,
      draw,
      ...over,
    });
    return { clock, draw, capture };
  };

  it("within the first second a tick has no frame yet - and does not draw one", () => {
    const { capture, clock, draw } = setup();
    expect(capture.mode()).toBe("waiting");
    expect(capture.take()).toBeNull();
    clock.now += 999;
    expect(capture.take()).toBeNull();
    expect(capture.mode()).toBe("waiting");
    expect(draw).not.toHaveBeenCalled();
  });

  it("at exactly 1000 ms without a callback it falls back", () => {
    const { capture, clock } = setup();
    clock.now += 1000;
    expect(capture.take()).not.toBeNull();
    expect(capture.mode()).toBe("fallback");
  });

  it("a fallback frame is drawn at the tick, timed by the page clock, with no frame identity", () => {
    const { capture, clock, draw } = setup();
    clock.now += 1000;
    const first = capture.take();
    clock.now += 500;
    const second = capture.take();
    expect(first).toEqual({
      image_base64: "jpeg-1",
      captured_at: "2023-11-14T22:13:26.000Z",
      captured_at_source: "client_clock",
    });
    expect(second).toEqual({
      image_base64: "jpeg-2",
      captured_at: "2023-11-14T22:13:26.500Z",
      captured_at_source: "client_clock",
    });
    expect(Object.keys(second ?? {})).not.toContain("vision_frame");
    expect(draw).toHaveBeenCalledTimes(2);
  });

  it("a browser without requestVideoFrameCallback is in the fallback mode from the start", () => {
    const { capture, draw } = setup({ callbacksSupported: false });
    expect(capture.mode()).toBe("fallback");
    expect(capture.take()).toMatchObject({
      image_base64: "jpeg-1",
      captured_at_source: "client_clock",
    });
    expect(draw).toHaveBeenCalledTimes(1);
  });

  it("a first callback that arrives after the deadline is too late: the fallback it came after stands", () => {
    const { capture, clock } = setup();
    clock.now += 1000;
    capture.onFrame({ presentedFrames: 1, captureTime: 10 });
    expect(capture.mode()).toBe("fallback");
    expect(capture.take()).toMatchObject({
      captured_at_source: "client_clock",
    });
  });

  it("once in the fallback it never goes back to explicit identities, however many callbacks follow", () => {
    // The server's identity watermark must not see explicit and fallback frames
    // alternate within one camera start.
    const { capture, clock, draw } = setup();
    clock.now += 1000;
    capture.take(); // falls back
    for (let index = 1; index <= 5; index += 1) {
      clock.now += 33;
      capture.onFrame({ presentedFrames: index, captureTime: index });
      const frame = capture.take();
      expect(frame).not.toBeNull();
      expect(frame?.captured_at_source).toBe("client_clock");
      expect(Object.keys(frame ?? {})).not.toContain("vision_frame");
    }
    expect(capture.mode()).toBe("fallback");
    // The callbacks drew nothing: only the six takes did.
    expect(draw).toHaveBeenCalledTimes(6);
  });

  it("a fallback tick whose picture cannot be drawn has no frame", () => {
    const { capture } = setup({ callbacksSupported: false, draw: () => null });
    expect(capture.take()).toBeNull();
  });
});

// WIRING GUARD. The hook needs a DOM and a camera, and the repository runs its tests in
// node, so the hook cannot be rendered. Same approach as useLiveSession.test.ts: read the
// hook's source and fail if the few facts the pure logic relies on stop being true.
// Comments are blanked first, so commented-out code cannot satisfy a check.
const STRING_OR_COMMENT =
  /("(?:\\.|[^"\\\n])*"|'(?:\\.|[^'\\\n])*'|`(?:\\.|[^`\\])*`)|\/\*[\s\S]*?\*\/|\/\/[^\n]*/g;
const withoutComments = (source: string) =>
  source.replace(STRING_OR_COMMENT, (match, literal?: string) =>
    literal === undefined ? " " : match,
  );
const squash = (source: string) => withoutComments(source).replace(/\s+/g, " ");

type Wiring =
  | "EPOCH"
  | "EPOCH_KEPT"
  | "ATTACHED"
  | "DETACHED_ON_RELEASE"
  | "CALLBACK_CAPTURES"
  | "CALLBACK_REARMED_FIRST"
  | "TICK_DOES_NOT_DRAW"
  | "TICK_TAKES_THE_CACHE";

/** The wiring requirements the hook's source fails; an empty list is a pass. */
function wiringViolations(source: string): Wiring[] {
  const code = squash(source);
  const tick =
    /const captureFrame = useCallback\(\(\): CaptureResult => \{(.*?)\}, \[\]\);/.exec(
      code,
    );
  const body = tick?.[1] ?? "";
  const callback =
    /const onFrame: VideoFrameRequestCallback = \(_now, metadata\) => \{(.*?)\};/.exec(
      code,
    )?.[1] ?? "";
  const checks: Array<[Wiring, boolean]> = [
    // The epoch of a start comes from the real clock and the previous epoch...
    [
      "EPOCH",
      /const epoch = nextCameraEpoch\(lastEpoch\.current, Date\.now\(\)\);/.test(
        code,
      ),
    ],
    // ...and is remembered, so the next start is above it.
    ["EPOCH_KEPT", /lastEpoch\.current = epoch;/.test(code)],
    // The capture <video> is in the document: detached, Chromium never calls back.
    ["ATTACHED", /document\.body\.appendChild\(capture\)/.test(code)],
    ["DETACHED_ON_RELEASE", /captureRef\.current\.remove\(\)/.test(code)],
    // The callback is where the picture is drawn and the tuple cached...
    ["CALLBACK_CAPTURES", /frames\.onFrame\(metadata\)/.test(callback)],
    // ...and the chain is re-armed before that, so a throw cannot end it.
    [
      "CALLBACK_REARMED_FIRST",
      callback.indexOf("requestVideoFrameCallback(onFrame)") >= 0 &&
        callback.indexOf("requestVideoFrameCallback(onFrame)") <
          callback.indexOf("frames.onFrame(metadata)"),
    ],
    // A tick takes the cached tuple; it never draws and never stamps a time itself.
    [
      "TICK_DOES_NOT_DRAW",
      body !== "" && !/drawImage|toDataURL|new Date|Date\.now/.test(body),
    ],
    ["TICK_TAKES_THE_CACHE", /framesRef\.current\?\.take\(\)/.test(body)],
  ];
  return checks.filter(([, ok]) => !ok).map(([name]) => name);
}

describe("useCameraPreview: the hook is wired to the frame source the way the pure logic assumes", () => {
  it("the hook's source meets every wiring requirement", () => {
    expect(wiringViolations(hookSource)).toEqual([]);
  });

  const once = (source: string, from: string, to: string): string => {
    expect(
      source.split(from),
      `"${from}" must occur exactly once`,
    ).toHaveLength(2);
    return source.replace(from, () => to);
  };

  // The guard has to fail on the regressions it exists for. Each mutant edits the REAL
  // hook source in memory (exactly one occurrence, so a drifted source fails loudly).
  const MUTANTS: Array<{
    name: string;
    edit: (source: string) => string;
    breaks: Wiring;
  }> = [
    {
      name: "an epoch counter that starts at 0 on every page load",
      edit: (s) =>
        once(
          s,
          "const epoch = nextCameraEpoch(lastEpoch.current, Date.now());",
          "const epoch = lastEpoch.current + 1;",
        ),
      breaks: "EPOCH",
    },
    {
      name: "the epoch computed but not remembered",
      edit: (s) => once(s, "lastEpoch.current = epoch;", "void epoch;"),
      breaks: "EPOCH_KEPT",
    },
    {
      name: "the capture <video> left detached",
      edit: (s) => once(s, "document.body.appendChild(capture);", ""),
      breaks: "ATTACHED",
    },
    {
      name: "the capture <video> left in the document after release",
      edit: (s) => once(s, "captureRef.current.remove();", ""),
      breaks: "DETACHED_ON_RELEASE",
    },
    {
      name: "the callback no longer captures",
      edit: (s) => once(s, "frames.onFrame(metadata);", "void metadata;"),
      breaks: "CALLBACK_CAPTURES",
    },
    {
      name: "the callback re-arms itself only after capturing",
      edit: (s) =>
        once(
          once(
            s,
            "frameCallbackRef.current = capture.requestVideoFrameCallback(onFrame);\n          frames.onFrame(metadata);",
            "frames.onFrame(metadata);\n          frameCallbackRef.current = capture.requestVideoFrameCallback(onFrame);",
          ),
          "// Register the next callback first: whatever happens below, the chain goes on.",
          "",
        ),
      breaks: "CALLBACK_REARMED_FIRST",
    },
    {
      name: "a tick that draws a fresh picture of its own",
      edit: (s) =>
        once(
          s,
          "const frame = framesRef.current?.take() ?? null;",
          "const frame = framesRef.current?.take() ?? null;\n    void drawFrame(video, canvasRef.current as HTMLCanvasElement); canvasRef.current?.toDataURL();",
        ),
      breaks: "TICK_DOES_NOT_DRAW",
    },
    {
      name: "a tick that stamps its own time on the cached picture",
      edit: (s) =>
        once(
          s,
          "const frame = framesRef.current?.take() ?? null;",
          "const frame = framesRef.current?.take() ?? null;\n    void Date.now();",
        ),
      breaks: "TICK_DOES_NOT_DRAW",
    },
    {
      name: "a tick that does not take the cached tuple",
      edit: (s) =>
        once(
          s,
          "const frame = framesRef.current?.take() ?? null;",
          "const frame = null;",
        ),
      breaks: "TICK_TAKES_THE_CACHE",
    },
  ];

  it.each(MUTANTS)("$name", ({ edit, breaks }) => {
    const mutant = edit(hookSource);
    expect(mutant).not.toBe(hookSource);
    expect(wiringViolations(mutant)).toContain(breaks);
  });
});
