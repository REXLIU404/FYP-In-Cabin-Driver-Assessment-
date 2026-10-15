import { createElement } from "react";
import { describe, expect, it, vi } from "vitest";

import type { LiveFault } from "../../../ai/src/liveLoop";
import appSource from "../App.tsx?raw";
import { findElements, markup } from "../testing/markup";
import { retryHandler } from "../utils/runtimeNotices";
import {
  CameraStatusLine,
  CaptureMissNotice,
  FaultPanel,
} from "./RuntimeNotices";

// Task 9 / K10 (the React binding layer of Task 8, brought forward). The environment
// is node: no DOM, no click. What CAN be asserted is what the components render
// (react-dom/server, the same way branchStatusRender.test.ts does it) and, for the
// Retry button, what its onClick is bound to (call the component, read the returned
// tree). What cannot - that the button is really painted and clickable in a browser -
// is left to Task 10's Playwright run.

const fault = (over: Partial<LiveFault> = {}): LiveFault => ({
  category: "transport",
  message: "Failed to fetch",
  phase: "delivery",
  requestId: "req-7",
  retryCount: 3,
  manualRetries: 0,
  attemptIndex: 3,
  stopped: true,
  newSessionOnRetry: false,
  ...over,
});

const panel = (f: LiveFault, retrying = false, onRetry = () => undefined) =>
  markup(createElement(FaultPanel, { fault: f, retrying, onRetry }));

describe("FaultPanel: what Retry will do follows the phase AND newSessionOnRetry (K8 / K10)", () => {
  it("a delivery that stopped: Retry re-sends the same request to the same session", () => {
    const html = panel(fault());
    expect(html).toContain(
      "<p>Retry re-sends this same request to the same session.</p>",
    );
    expect(html).not.toMatch(/NEW session/);
  });

  it("a delivery whose session is gone (404): the panel says Retry creates a NEW session", () => {
    const html = panel(
      fault({ category: "not_found", status: 404, newSessionOnRetry: true }),
    );
    expect(html).toContain("<p>Retry will create a NEW session.</p>");
    expect(html).not.toMatch(/re-sends this same request/);
  });

  it("a setup that stopped on a normal Start: Retry repeats the setup and resumes", () => {
    const html = panel(
      fault({
        phase: "setup",
        requestId: null,
        retryCount: 0,
        attemptIndex: 0,
        category: "models_unavailable",
        status: 503,
      }),
    );
    expect(html).toContain(
      "<p>Retry repeats the setup: the model check, then the session.</p>",
    );
    expect(html).toContain("Failed during setup, before any request was sent");
    expect(html).not.toMatch(/NEW session/);
    // A setup fault has no request: no request id, no delivery line.
    expect(html).not.toMatch(/Request id/);
    expect(html).not.toMatch(/Deliveries:/);
  });

  it("a setup that stopped on New Session: the panel says Retry creates a NEW session", () => {
    const html = panel(
      fault({
        phase: "setup",
        requestId: null,
        retryCount: 0,
        attemptIndex: 0,
        newSessionOnRetry: true,
      }),
    );
    expect(html).toContain(
      "<p>Retry repeats the setup: the model check, then a NEW session.</p>",
    );
    expect(html).not.toMatch(
      /repeats the setup: the model check, then the session/,
    );
  });
});

describe("FaultPanel: the advice and the delivery line agree on why it stopped (K8)", () => {
  it("automatic budget spent: 3 of 3, and the sentence says it was re-sent automatically", () => {
    const html = panel(
      fault({ category: "model_runtime", status: 500, retryCount: 3 }),
    );
    expect(html).toContain("Deliveries: 3 of 3");
    expect(html).toContain(
      "The request was re-sent automatically and kept failing.",
    );
  });

  it("a manual retry failed after a 400 (1 of 3 + 1 manual): no claim of automatic re-sends", () => {
    const html = panel(
      fault({
        category: "model_runtime",
        status: 500,
        retryCount: 2,
        manualRetries: 1,
        attemptIndex: 2,
      }),
    );
    expect(html).toContain("Deliveries: 1 of 3 + 1 manual");
    expect(html).toContain("The retry you triggered failed as well.");
    expect(html).not.toMatch(/automatically/);
  });

  it("the same for a timeout that was retried by hand", () => {
    const html = panel(
      fault({ category: "timeout", retryCount: 4, manualRetries: 1 }),
    );
    expect(html).toContain("Deliveries: 3 of 3 + 1 manual");
    expect(html).toContain("The retry you triggered timed out as well.");
    expect(html).not.toMatch(/kept timing out/);
  });
});

describe("FaultPanel: structure", () => {
  it("while automatic retries are pending it is a status line with no button", () => {
    const html = panel(
      fault({ stopped: false, retryCount: 1, attemptIndex: 1 }),
    );
    expect(html).toContain('role="status"');
    expect(html).toContain(
      "Delivery 1 of 3 failed: The backend cannot be reached. Retrying automatically…",
    );
    expect(html).not.toContain("<button");
  });

  it("a stopped panel is an alert naming the category, status and request", () => {
    const html = panel(fault({ category: "model_runtime", status: 500 }));
    expect(html).toContain('role="alert"');
    expect(html).toContain('aria-label="Monitoring stopped"');
    expect(html).toContain(
      "Monitoring stopped: The server failed while processing the frame",
    );
    expect(html).toContain("Category: <code>model_runtime</code> (HTTP 500)");
    expect(html).toContain("Request id: <code>req-7</code>");
    expect(html).toContain("Server message: Failed to fetch");
  });

  it("the button reads Retry, and is disabled with 'Retrying…' while a retry is in flight", () => {
    expect(panel(fault())).toMatch(/<button[^>]*>.*Retry<\/button>/);
    expect(panel(fault())).not.toMatch(/<button[^>]*disabled/);
    const busy = panel(fault(), true);
    expect(busy).toMatch(/<button[^>]*disabled=""[^>]*>.*Retrying…<\/button>/);
  });
});

describe("the Retry button: its click is bound to onRetry, and onRetry to live.retry() (K10)", () => {
  const retryButton = (onRetry: () => void) => {
    // FaultPanel uses no hooks: calling it returns the tree it would render.
    const tree = FaultPanel({ fault: fault(), retrying: false, onRetry });
    const [button] = findElements(tree, (el) => el.type === "button");
    return button as unknown as {
      props: { onClick: () => void; disabled: boolean };
    };
  };

  it("clicking the button calls onRetry exactly once", () => {
    const onRetry = vi.fn();
    retryButton(onRetry).props.onClick();
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("the panel has exactly one button", () => {
    const tree = FaultPanel({
      fault: fault(),
      retrying: false,
      onRetry: () => undefined,
    });
    expect(findElements(tree, (el) => el.type === "button")).toHaveLength(1);
  });

  it("App's handler re-delivers through live.retry() and does not start a New Session", () => {
    const live = {
      retry: vi.fn(async () => undefined),
      start: vi.fn(async () => undefined),
    };
    retryHandler(live)();
    expect(live.retry).toHaveBeenCalledTimes(1);
    expect(live.start).not.toHaveBeenCalled();
  });

  it("the handler wired into the button reaches live.retry()", () => {
    const live = { retry: vi.fn(async () => undefined) };
    retryButton(retryHandler(live)).props.onClick();
    expect(live.retry).toHaveBeenCalledTimes(1);
  });
});

describe("the camera: an unplugged device and a deliberate Stop Camera read differently (K10)", () => {
  const notice = (reason: string) =>
    markup(createElement(CaptureMissNotice, { reason }));

  it("Stop Camera: 'the camera was stopped'", () => {
    expect(notice("stopped_by_user")).toContain(
      "No camera image is being sent (the camera was stopped).",
    );
  });

  it("an unexpected disconnect: 'the camera was disconnected'", () => {
    expect(notice("device_disconnected")).toContain(
      "No camera image is being sent (the camera was disconnected).",
    );
  });

  it("the two reason codes never render the same words", () => {
    expect(notice("stopped_by_user")).not.toBe(notice("device_disconnected"));
  });

  it("every reason the camera can give has words of its own", () => {
    const reasons = [
      "camera_not_started",
      "stopped_by_user",
      "device_disconnected",
      "start_failed",
      "not_ready",
      "track_muted",
      "capture_error",
    ];
    const texts = reasons.map(notice);
    expect(new Set(texts).size).toBe(reasons.length);
    for (const text of texts) expect(text).not.toMatch(/\(\w+_\w+\)/);
  });

  it("an unknown code is shown as it is rather than hidden", () => {
    expect(notice("no_frame")).toContain("(no_frame)");
  });

  it("the notice still says monitoring continues, with telemetry only (R5)", () => {
    expect(notice("stopped_by_user")).toContain(
      "Vision evidence is missing; monitoring continues with telemetry only.",
    );
    expect(notice("stopped_by_user")).toContain('role="status"');
  });

  const line = (
    event: { kind: "user" | "device" | "start_failed"; at: string } | null,
    over: {
      status?: "idle" | "live" | "error";
      actualFps?: number | null;
    } = {},
  ) =>
    markup(
      createElement(CameraStatusLine, {
        status: over.status ?? "idle",
        actualFps: over.actualFps ?? null,
        event,
      }),
    );
  const AT = "2026-01-01T12:00:00.000Z";

  it("the status line says who ended the stream", () => {
    expect(line({ kind: "user", at: AT })).toMatch(
      /^<span>Camera: idle · stopped by you at /,
    );
    expect(line({ kind: "device", at: AT }, { status: "error" })).toMatch(
      /^<span>Camera: error · disconnected at /,
    );
    expect(line({ kind: "start_failed", at: AT }, { status: "error" })).toMatch(
      /^<span>Camera: error · failed to start at /,
    );
  });

  it("a user stop and a disconnect differ on the status line too", () => {
    expect(line({ kind: "user", at: AT })).not.toBe(
      line({ kind: "device", at: AT }),
    );
  });

  it("with no event it shows the state and the frame rate, half-up to one decimal", () => {
    expect(line(null, { status: "live", actualFps: 29.95 })).toBe(
      "<span>Camera: live · 30.0 FPS</span>",
    );
    expect(line(null)).toBe("<span>Camera: idle</span>");
  });
});

// The one thing the tests above cannot see is App's own wiring of these components:
// which prop it hands them. A source guard - not a behaviour test - pins the bindings
// that matter (the end-to-end click in a real browser is Task 10's Playwright run).
describe("App wiring of the stop panel and the camera notices (source guard)", () => {
  const code = appSource
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/(^|[^:])\/\/.*$/gm, "$1");

  it("the stop panel's Retry is retryHandler(live): live.retry(), never start(true)", () => {
    expect(code).toMatch(
      /<FaultPanel[^>]*\bonRetry=\{retryHandler\(live\)\}[^>]*\/>/s,
    );
    expect(code).not.toMatch(/onRetry=\{\s*\(\)\s*=>/);
  });

  it("the capture notice is given the loop's lastCaptureMiss reason", () => {
    expect(code).toMatch(
      /<CaptureMissNotice\s+reason=\{live\.lastCaptureMiss\}\s*\/>/,
    );
  });

  it("the camera status line is given the camera's own status, rate and event", () => {
    expect(code).toMatch(
      /<CameraStatusLine[^>]*\bstatus=\{camera\.status\}[^>]*\bactualFps=\{camera\.actualFps\}[^>]*\bevent=\{camera\.event\}[^>]*\/>/s,
    );
  });
});
