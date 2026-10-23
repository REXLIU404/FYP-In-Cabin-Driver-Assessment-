import { describe, expect, it } from "vitest";

import type { TimingInput } from "./liveLoop";
import {
  createTimingBuffer,
  parseServerTiming,
  segmentsOf,
} from "./liveTiming";

// Every expectation is a literal.
const input = (
  windowId: number,
  over: Partial<TimingInput> = {},
): TimingInput => ({
  sessionId: "s1",
  windowId,
  requestId: `req-${windowId}`,
  attemptIndex: 1,
  capturedAtMs: 1000,
  sentAtMs: 1030,
  receivedAtMs: 1180,
  ...over,
});

describe("segmentsOf: the three client segments", () => {
  it("captureToSend, network and render are the successive differences", () => {
    expect(
      segmentsOf(
        { capturedAtMs: 1000, sentAtMs: 1030, receivedAtMs: 1180 },
        1195,
      ),
    ).toEqual({ captureToSendMs: 30, networkMs: 150, renderMs: 15 });
  });

  it("renderMs is null until the window has been rendered", () => {
    expect(
      segmentsOf({ capturedAtMs: 1000, sentAtMs: 1030, receivedAtMs: 1180 }),
    ).toEqual({ captureToSendMs: 30, networkMs: 150, renderMs: null });
  });

  it("a clock that stepped backwards gives 0, never a negative latency", () => {
    expect(
      segmentsOf({ capturedAtMs: 1000, sentAtMs: 990, receivedAtMs: 980 }, 970),
    ).toEqual({ captureToSendMs: 0, networkMs: 0, renderMs: 0 });
  });
});

describe("parseServerTiming", () => {
  it("reads the six segments the backend writes, including a skipped one", () => {
    const header =
      'preprocess;dur=3.50, vision;dur=7.25, telemetry;dur=0.00;desc="skipped", ' +
      "fusion;dur=0.80, commit;dur=2.10, total;dur=15.90";
    expect(parseServerTiming(header)).toEqual({
      preprocess: 3.5,
      vision: 7.25,
      telemetry: 0,
      fusion: 0.8,
      commit: 2.1,
      total: 15.9,
    });
  });

  it("a quoted desc may contain commas, semicolons and even a fake dur=", () => {
    // Splitting without regard to quotes would read {y: 99} and lose the real `a`.
    expect(
      parseServerTiming('a;desc="x, y; dur=99";dur=1, b;desc="q";dur=2'),
    ).toEqual({ a: 1, b: 2 });
  });

  it("ignores a metric with no numeric dur, and sums a repeated name", () => {
    expect(
      parseServerTiming(
        "cache;desc=hit, db;dur=abc, db;dur=2, db;dur=3, x;dur",
      ),
    ).toEqual({ db: 5 });
  });

  it("is case-insensitive about the parameter name and tolerates spaces", () => {
    expect(parseServerTiming("total ; DUR = 4.5")).toEqual({ total: 4.5 });
  });

  it.each([null, undefined, "", "   ", "nothing;useful", ",,"])(
    "%j has no usable segments: null",
    (header) => {
      expect(parseServerTiming(header)).toBeNull();
    },
  );
});

describe("createTimingBuffer", () => {
  it("rejects a capacity that is not a positive integer", () => {
    for (const bad of [0, -1, 1.5, Number.NaN])
      expect(() => createTimingBuffer(bad)).toThrow(RangeError);
  });

  it("defaults to 500 windows", () => {
    expect(createTimingBuffer().capacity).toBe(500);
  });

  it("keeps entries oldest to newest and derives the segments on push", () => {
    const buffer = createTimingBuffer(5);
    buffer.push(input(1));
    buffer.push(
      input(2, { capturedAtMs: 2000, sentAtMs: 2005, receivedAtMs: 2105 }),
    );
    const [first, second] = buffer.snapshot();
    expect([first.windowId, second.windowId]).toEqual([1, 2]);
    expect(first).toMatchObject({
      captureToSendMs: 30,
      networkMs: 150,
      renderMs: null,
      renderedAtMs: null,
      server: null,
      requestId: "req-1",
      attemptIndex: 1,
    });
    expect(second).toMatchObject({ captureToSendMs: 5, networkMs: 100 });
  });

  it("is bounded: past its capacity the oldest entries are dropped", () => {
    const buffer = createTimingBuffer(3);
    for (let id = 1; id <= 8; id++) buffer.push(input(id));
    expect(buffer.size).toBe(3);
    expect(buffer.snapshot().map((e) => e.windowId)).toEqual([6, 7, 8]);
  });

  it("the default ring holds exactly 500 of 501 pushed windows", () => {
    const buffer = createTimingBuffer();
    for (let id = 1; id <= 501; id++) buffer.push(input(id));
    const kept = buffer.snapshot();
    expect(kept).toHaveLength(500);
    expect(kept[0].windowId).toBe(2);
    expect(kept[499].windowId).toBe(501);
  });

  it("order stays oldest-first while the ring is wrapping", () => {
    const buffer = createTimingBuffer(4);
    for (let id = 1; id <= 6; id++) buffer.push(input(id));
    expect(buffer.snapshot().map((e) => e.windowId)).toEqual([3, 4, 5, 6]);
    buffer.push(input(7));
    expect(buffer.snapshot().map((e) => e.windowId)).toEqual([4, 5, 6, 7]);
  });

  it("a second entry for the same window replaces the first instead of adding one", () => {
    const buffer = createTimingBuffer(5);
    buffer.push(input(1));
    buffer.push(input(2));
    buffer.push(
      input(1, { attemptIndex: 4, sentAtMs: 1100, receivedAtMs: 1200 }),
    );
    expect(buffer.size).toBe(2);
    const [one] = buffer.snapshot();
    expect(one).toMatchObject({ windowId: 1, attemptIndex: 4, networkMs: 100 });
  });

  it("the same window id in another session is a different window", () => {
    const buffer = createTimingBuffer(5);
    buffer.push(input(1, { sessionId: "a" }));
    buffer.push(input(1, { sessionId: "b" }));
    expect(buffer.snapshot().map((e) => e.sessionId)).toEqual(["a", "b"]);
  });

  it("takes the server stages from a Server-Timing header when one is given", () => {
    const buffer = createTimingBuffer(2);
    buffer.push(input(1, { serverTiming: "fusion;dur=0.80, total;dur=15.90" }));
    expect(buffer.snapshot()[0].server).toEqual({ fusion: 0.8, total: 15.9 });
  });
});

describe("markRendered", () => {
  it("closes renderMs of that window, once", () => {
    const buffer = createTimingBuffer(5);
    buffer.push(input(1));
    expect(buffer.markRendered("s1", 1, 1195)).toBe(true);
    expect(buffer.snapshot()[0]).toMatchObject({
      renderedAtMs: 1195,
      renderMs: 15,
    });
    expect(buffer.markRendered("s1", 1, 9999)).toBe(false); // already closed: not overwritten
    expect(buffer.snapshot()[0]).toMatchObject({
      renderedAtMs: 1195,
      renderMs: 15,
    });
  });

  it("ignores a window it never timed, and another session's window", () => {
    const buffer = createTimingBuffer(5);
    buffer.push(input(1));
    expect(buffer.markRendered("s1", 2, 1195)).toBe(false);
    expect(buffer.markRendered("other", 1, 1195)).toBe(false);
    expect(buffer.snapshot()[0].renderMs).toBeNull();
  });

  it("marks the window after the ring has wrapped", () => {
    const buffer = createTimingBuffer(2);
    for (let id = 1; id <= 3; id++) buffer.push(input(id));
    expect(buffer.markRendered("s1", 2, 1200)).toBe(true);
    expect(buffer.markRendered("s1", 1, 1200)).toBe(false); // already evicted
    expect(buffer.snapshot().map((e) => [e.windowId, e.renderMs])).toEqual([
      [2, 20],
      [3, null],
    ]);
  });
});

describe("snapshots cannot reach back into the buffer", () => {
  it("mutating the returned array does not change the buffer", () => {
    const buffer = createTimingBuffer(3);
    buffer.push(input(1));
    buffer.snapshot().length = 0;
    buffer.snapshot().push(buffer.snapshot()[0]);
    expect(buffer.snapshot()).toHaveLength(1);
  });

  it("entries are frozen", () => {
    const buffer = createTimingBuffer(3);
    buffer.push(input(1));
    const [entry] = buffer.snapshot();
    expect(Object.isFrozen(entry)).toBe(true);
    expect(() => {
      (entry as { networkMs: number }).networkMs = 0;
    }).toThrow(TypeError);
  });
});
