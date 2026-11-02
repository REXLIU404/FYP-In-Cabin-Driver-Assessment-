import { describe, expect, it } from "vitest";

import shapesSource from "../../backend/tests/fixtures/constructed_payload_shapes.json?raw";
import {
  buildLivePayload,
  type LiveFrame,
  type LivePayload,
  type TelemetryReading,
} from "./liveLoop";

/**
 * Task 5 (constructed scenario) - the replay block in ``buildLivePayload``, the front-end
 * half of the wire contract. The bodies are written ONCE, as literal JSON, in
 * ``backend/tests/fixtures/constructed_payload_shapes.json``; the back end posts them to
 * the real /infer route (``test_constructed_payload_contract.py``) and asserts they are a
 * 201 in a constructed session and a 422 in a Live one. This file asserts the builder
 * produces exactly those shapes - and no replay key at all for a plain Live request.
 */
const shapes = JSON.parse(shapesSource) as Record<string, Record<string, unknown>>;

const T0 = Date.UTC(2025, 0, 1, 12, 0, 0); // 2025-01-01T12:00:00.000Z

const ROW: TelemetryReading["features"] = {
  speed_kmph: 34,
  accel_x: 0.3,
  accel_y: 0.1,
  brake_pressure: 12,
  steering_angle: -2,
  throttle: 30,
  lane_deviation: 0.3,
  headway_distance: 26,
};

const FRAME_WITH_REPLAY: LiveFrame = {
  image_base64:
    "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/2wBDAQkJCQwLDBgNDRgyIRwhMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjL/wAARCAAwAEADASIAAhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUFBAQAAAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/8QAHwEAAwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREAAgECBAQDBAcFBAQAAQJ3AAECAxEEBSExBhJBUQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElKU1RVVldYWVpjZGVmZ2hpanN0dXZ3eHl6goOEhYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3uLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk5ebn6Onq8vP09fb3+Pn6/9oADAMBAAIRAxEAPwCCiiivdPFCiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooA//2Q==",
  captured_at: "2025-01-01T11:59:59.970Z",
  captured_at_source: "replay_clock",
  vision_frame: { epoch: T0, index: 3 },
  replay: {
    scenario_id: "viva_v1",
    segment_index: 0,
    frame_file: "0003_img_3.jpg",
    vision_label: "safe_driving",
  },
};

const FRAME_NO_TELEMETRY: LiveFrame = {
  image_base64:
    "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/2wBDAQkJCQwLDBgNDRgyIRwhMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjL/wAARCAAwAEADASIAAhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUFBAQAAAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/8QAHwEAAwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREAAgECBAQDBAcFBAQAAQJ3AAECAxEEBSExBhJBUQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElKU1RVVldYWVpjZGVmZ2hpanN0dXZ3eHl6goOEhYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3uLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk5ebn6Onq8vP09fb3+Pn6/9oADAMBAAIRAxEAPwB9FFFe6eKFFFFABRRRQAUUUUAFFFFABRRRQAUUUUAFFFFABRRRQAUUUUAFFFFABRRRQB//2Q==",
  captured_at: "2025-01-01T11:59:59.980Z",
  captured_at_source: "replay_clock",
  vision_frame: { epoch: T0, index: 4 },
  replay: {
    scenario_id: "viva_v1",
    segment_index: 1,
    frame_file: "0004_img_4.jpg",
    vision_label: "texting_right",
  },
};

const READING_WITH_REPLAY: TelemetryReading = {
  features: ROW,
  seq: 0,
  acquiredAtMs: T0,
  replay: {
    scenario_id: "viva_v1",
    segment_index: 0,
    telemetry_row: 0,
    telemetry_label: "Safe",
  },
};

const READING_NO_FRAME: TelemetryReading = {
  features: ROW,
  seq: 1,
  acquiredAtMs: T0 + 2000,
  replay: {
    scenario_id: "viva_v1",
    segment_index: 2,
    telemetry_row: 1,
    telemetry_label: "Aggressive",
  },
};

const PLAIN_READING: TelemetryReading = {
  features: ROW,
  seq: 13,
  acquiredAtMs: T0 + 26_000,
};

const PLAIN_FRAME: LiveFrame = {
  image_base64: "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAAED",
  captured_at: "2025-01-01T12:00:00.000Z",
  captured_at_source: "client_clock",
};

// What goes over the wire is the JSON text, so compare the parsed JSON: a key that
// holds undefined is not sent, and a key that holds null is.
const wire = (payload: LivePayload) =>
  JSON.parse(JSON.stringify(payload)) as Record<string, unknown>;

describe("the payload builder produces exactly the shapes the back end accepts", () => {
  it("the fixture holds the three constructed shapes", () => {
    expect(Object.keys(shapes)).toEqual([
      "frame_and_telemetry",
      "no_frame",
      "no_telemetry",
    ]);
  });

  it("frame and telemetry, both labelled: the complete replay block", () => {
    expect(
      wire(buildLivePayload("constructed-frame-telemetry", FRAME_WITH_REPLAY, READING_WITH_REPLAY)),
    ).toEqual(shapes.frame_and_telemetry);
  });

  it("no frame: only the telemetry fields ride", () => {
    expect(wire(buildLivePayload("constructed-no-frame", null, READING_NO_FRAME))).toEqual(
      shapes.no_frame,
    );
  });

  it("no telemetry: only the frame fields ride", () => {
    expect(
      wire(buildLivePayload("constructed-no-telemetry", FRAME_NO_TELEMETRY, {
        features: null,
        seq: 13,
        acquiredAtMs: T0 + 26_000,
      })),
    ).toEqual(shapes.no_telemetry);
  });

  it("scenario_id and segment_index come from the frame when there is one", () => {
    const body = wire(buildLivePayload("r-1", FRAME_NO_TELEMETRY, READING_WITH_REPLAY));
    expect(body.replay).toMatchObject({
      scenario_id: "viva_v1",
      segment_index: 1, // the frame's segment, not the reading's 0
      frame_file: "0004_img_4.jpg",
      vision_label: "texting_right",
      telemetry_row: 0, // the reading's own fields still ride
      telemetry_label: "Safe",
    });
  });
});

describe("a plain Live request carries no replay key", () => {
  it("with a frame and telemetry", () => {
    expect(wire(buildLivePayload("live-1", PLAIN_FRAME, PLAIN_READING))).not.toHaveProperty(
      "replay",
    );
  });

  it("with neither", () => {
    expect(
      wire(buildLivePayload("live-2", null, { features: null, seq: 13, acquiredAtMs: T0 })),
    ).not.toHaveProperty("replay");
  });
});
