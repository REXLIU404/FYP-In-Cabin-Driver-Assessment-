import { describe, expect, it, vi } from "vitest";

import shapesSource from "../../backend/tests/fixtures/live_payload_shapes.json?raw";
import { RETRY_POLICY } from "../../frontend/src/api/retryPolicy";
import { makeRecord } from "../../frontend/src/testing/records";
import {
  buildLivePayload,
  createLiveLoop,
  type LiveFrame,
  type LiveLoopApi,
  type LivePayload,
  type TelemetryReading,
  type TelemetrySource,
} from "./liveLoop";
import { DEFAULT_CONFIG } from "./riskLogic";
import type { AppConfig, SessionMeta, TelemetryFeatures } from "./types";

// R10-B (B7), the front-end half of the wire contract. The bodies below are written
// ONCE, as literal JSON, in backend/tests/fixtures/live_payload_shapes.json. The back
// end (backend/tests/test_r10b_payload_contract.py) posts them to the real /infer route
// and asserts it accepts the shapes in "accepted" with a 201 and rejects those in
// "rejected" with a 422. This file asserts the other direction: the payload builder - and
// the loop that calls it - produce exactly the "accepted" shapes from the inputs below,
// and can never produce a "rejected" one. A change to either side that the other does not
// follow turns one of the two suites red.
const shapes = JSON.parse(shapesSource) as {
  accepted: Record<string, Record<string, unknown>>;
  rejected: Record<string, Record<string, unknown>>;
};

const T0 = Date.UTC(2025, 0, 1, 12, 0, 0); // 2025-01-01T12:00:00.000Z
const EPOCH = 1735732800000; // the camera start, in epoch milliseconds

const ROW_1: TelemetryFeatures = {
  speed_kmph: 34,
  accel_x: 0.3,
  accel_y: 0.1,
  brake_pressure: 12,
  steering_angle: -2,
  throttle: 30,
  lane_deviation: 0.3,
  headway_distance: 26,
};
const ROW_2: TelemetryFeatures = {
  speed_kmph: 36,
  accel_x: 0.42,
  accel_y: 0.12,
  brake_pressure: 15,
  steering_angle: -3.1,
  throttle: 33,
  lane_deviation: 0.35,
  headway_distance: 24,
};

const FRAME_241: LiveFrame = {
  image_base64: "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAAEB",
  captured_at: "2025-01-01T11:59:59.970Z",
  captured_at_source: "capture_time",
  vision_frame: { epoch: EPOCH, index: 241 },
};
const FRAME_242: LiveFrame = {
  image_base64: "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAAIC",
  captured_at: "2025-01-01T11:59:59.980Z",
  captured_at_source: "callback",
  vision_frame: { epoch: EPOCH, index: 242 },
};
const FRAME_FALLBACK: LiveFrame = {
  image_base64: "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAAMD",
  captured_at: "2025-01-01T12:00:00.000Z",
  captured_at_source: "client_clock",
};
const SAMPLE_0: TelemetryReading = {
  features: ROW_1,
  seq: 0,
  acquiredAtMs: T0,
};
const SAMPLE_1: TelemetryReading = {
  features: ROW_2,
  seq: 1,
  acquiredAtMs: T0 + 2000,
};
// The cursor sits on a row with no telemetry (row 14 is sequence 13) - and still has a
// sequence number, which the request must not carry.
const NO_SAMPLE: TelemetryReading = {
  features: null,
  seq: 13,
  acquiredAtMs: T0 + 26_000,
};

// name in the fixture -> [request id, frame, reading]
const CASES: Array<[string, string, LiveFrame | null, TelemetryReading]> = [
  ["frame_and_telemetry", "contract-frame-telemetry", FRAME_241, SAMPLE_0],
  ["no_frame", "contract-no-frame", null, SAMPLE_1],
  ["no_telemetry", "contract-no-telemetry", FRAME_242, NO_SAMPLE],
  ["fallback_mode", "contract-fallback", FRAME_FALLBACK, SAMPLE_0],
  ["nothing", "contract-nothing", null, NO_SAMPLE],
];

// What goes over the wire is the JSON text, so compare the parsed JSON: a key that
// holds undefined is not sent, and a key that holds null is.
const wire = (payload: LivePayload) =>
  JSON.parse(JSON.stringify(payload)) as Record<string, unknown>;

describe("the payload builder produces exactly the shapes the back end accepts", () => {
  it("the fixture holds the five accepted and the two rejected shapes", () => {
    expect(Object.keys(shapes.accepted)).toEqual(CASES.map(([name]) => name));
    expect(Object.keys(shapes.rejected)).toEqual([
      "no_frame_but_vision_frame",
      "no_telemetry_but_telemetry_seq",
    ]);
  });

  it.each(CASES)("%s", (name, requestId, frame, reading) => {
    expect(wire(buildLivePayload(requestId, frame, reading))).toEqual(
      shapes.accepted[name],
    );
  });

  it("a frame with an identity and a sample: the identity, the source, the sequence number and the sample's own time travel", () => {
    expect(
      wire(buildLivePayload("contract-frame-telemetry", FRAME_241, SAMPLE_0)),
    ).toMatchObject({
      captured_at: "2025-01-01T11:59:59.970Z", // the VISION time
      telemetry_timestamp: "2025-01-01T12:00:00.000Z", // the TELEMETRY time
      vision_frame: { epoch: 1735732800000, index: 241 },
      telemetry_seq: 0,
    });
  });
});

describe("the payload builder cannot produce a shape the back end rejects", () => {
  const frames: Array<[string, LiveFrame | null]> = [
    ["an explicit frame", FRAME_241],
    ["a fallback frame", FRAME_FALLBACK],
    ["no frame", null],
  ];
  const readings: Array<[string, TelemetryReading]> = [
    ["a sample", SAMPLE_0],
    ["a row with no telemetry", NO_SAMPLE],
  ];

  describe.each(frames)("with %s", (_frameName, frame) => {
    it.each(readings)("and %s", (_readingName, reading) => {
      const body = wire(buildLivePayload("r-1", frame, reading));
      // 422 rule 1: no image, no vision_frame (and no source for a time that is not there).
      if (body.image_base64 === null) {
        expect(body).not.toHaveProperty("vision_frame");
        expect(body).not.toHaveProperty("captured_at_source");
        expect(body.captured_at).toBeNull();
      }
      // The converse: an explicit frame is sent with its identity, a fallback frame without.
      expect("vision_frame" in body).toBe(frame?.vision_frame !== undefined);
      // 422 rule 2: no telemetry, no telemetry_seq.
      if (body.telemetry_features === null) {
        expect(body).not.toHaveProperty("telemetry_seq");
        expect(body.telemetry_timestamp).toBeNull();
        expect(body.telemetry_source).toBe("missing");
      } else {
        expect(typeof body.telemetry_seq).toBe("number");
      }
      // And nothing outside the schema, which the back end forbids (extra keys are a 422).
      expect(Object.keys(body).filter((key) => !ALLOWED.has(key))).toEqual([]);
    });
  });

  it("each rejected fixture shape is an accepted shape plus the one offending key", () => {
    const strip = (shape: Record<string, unknown>, key: string) => {
      const { [key]: _removed, request_id: _id, ...rest } = shape;
      void _removed;
      void _id;
      return rest;
    };
    expect(
      strip(shapes.rejected.no_frame_but_vision_frame, "vision_frame"),
    ).toEqual(strip(shapes.accepted.no_frame, "vision_frame"));
    expect(
      strip(shapes.rejected.no_telemetry_but_telemetry_seq, "telemetry_seq"),
    ).toEqual(strip(shapes.accepted.no_telemetry, "telemetry_seq"));
  });
});

const ALLOWED = new Set([
  "request_id",
  "image_base64",
  "captured_at",
  "captured_at_source",
  "vision_frame",
  "telemetry_features",
  "telemetry_timestamp",
  "telemetry_seq",
  "telemetry_source",
]);

describe("the loop sends the same shapes", () => {
  // The loop with everything scripted: a camera and a cursor that return fixed values,
  // a clock that stands still, timers that never fire (so exactly one tick happens).
  const firstBody = async (
    frame: LiveFrame | null,
    reading: TelemetryReading,
    requestId: string,
  ) => {
    const bodies: string[] = [];
    const meta: SessionMeta = {
      id: "s-1",
      created_at: "2025-01-01T12:00:00+00:00",
      total_windows: 0,
    };
    const api: LiveLoopApi<unknown> = {
      models: async () => ({}),
      create: async () => meta,
      session: async () => meta,
      latest: async () => makeRecord("fresh", "fresh", 1),
      windows: async () => [],
      infer: async (_sid, payload) => {
        bodies.push(JSON.stringify(payload));
        return makeRecord("fresh", "fresh", 1);
      },
    };
    const telemetry: TelemetrySource = {
      reset: vi.fn(),
      pause: vi.fn(),
      resume: vi.fn(),
      read: () => reading,
    };
    const loop = createLiveLoop({
      api,
      policy: RETRY_POLICY,
      getConfig: (): AppConfig => DEFAULT_CONFIG,
      captureFrame: () => frame,
      telemetry,
      newRequestId: () => requestId,
      now: () => T0,
      timers: { setTimeout: () => 0, clearTimeout: () => undefined },
    });
    await loop.start();
    await new Promise<void>((resolve) => setTimeout(resolve, 0));
    loop.pause();
    return bodies;
  };

  it.each(CASES)("%s", async (name, requestId, frame, reading) => {
    const bodies = await firstBody(frame, reading, requestId);
    expect(bodies).toHaveLength(1);
    expect(JSON.parse(bodies[0])).toEqual(shapes.accepted[name]);
  });
});
