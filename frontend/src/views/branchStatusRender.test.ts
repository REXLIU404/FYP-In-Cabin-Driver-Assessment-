import { createElement } from "react";
import { describe, expect, it } from "vitest";

import { DEFAULT_CONFIG } from "../../../ai/src/riskLogic";
import type { useCameraPreview } from "../hooks/useCameraPreview";
import { expiryRecords } from "../testing/expiryRecords";
import {
  markup,
  modalityCard,
  pillsAfter,
  valuesAfter,
} from "../testing/markup";
import type { RiskUpdate } from "../types";
import { ExplanationView } from "./ExplanationView";
import { LiveMonitor } from "./LiveMonitor";
import { SignalInspector } from "./SignalInspector";

// Ruling A (D13), A6, wiring: every place a view shows a branch's state must pass the
// record's expiry through. These tests render the real views to static markup
// (react-dom/server, node environment) and read each branch's number and pill from
// under its own row label. Each scenario gives vision and telemetry DIFFERENT ages
// (4 s / 7.5 s), so a dropped or swapped prop changes the text it is checked against.
//
// The expected strings are literals; none is built from an implementation constant.

const camera = {
  videoRef: null,
  status: "idle",
  start() {},
  stop() {},
} as unknown as ReturnType<typeof useCameraPreview>;

const renderLive = (record: RiskUpdate) =>
  markup(
    createElement(LiveMonitor, {
      latest: record,
      history: [record],
      sessionId: "s",
      recordCount: 1,
      isMonitoring: true,
      camera,
      thresholdLow: 30,
      thresholdHigh: 60,
    }),
  );

const renderInspector = (record: RiskUpdate) =>
  markup(
    createElement(SignalInspector, {
      history: [record],
      selectedRecord: record,
      thresholdLow: 30,
      onSelectWindow() {},
      onToggleFlag() {},
    }),
  );

const renderExplanation = (record: RiskUpdate) =>
  markup(
    createElement(ExplanationView, {
      selectedRecord: record,
      history: [record],
      config: DEFAULT_CONFIG,
    }),
  );

describe("LiveMonitor: both modality cards and both freshness pills carry the expiry", () => {
  it("vision expired (4 s), telemetry fresh", () => {
    const html = renderLive(expiryRecords.visionExpired());
    expect(modalityCard(html, "Visual Distraction")).toBe(
      "— | expired:expired (4 s) | Expired",
    );
    expect(modalityCard(html, "Telemetry Non-Safe")).toBe(
      "30% | fresh:fresh | 0.30",
    );
    expect(pillsAfter(html, "Vision freshness")).toEqual([
      "expired:expired (4 s)",
    ]);
    expect(pillsAfter(html, "Telemetry freshness")).toEqual(["fresh:fresh"]);
  });

  it("telemetry expired (7.5 s), vision fresh", () => {
    const html = renderLive(expiryRecords.telemetryExpired());
    expect(modalityCard(html, "Visual Distraction")).toBe(
      "50% | fresh:fresh | 0.50",
    );
    expect(modalityCard(html, "Telemetry Non-Safe")).toBe(
      "— | expired:expired (7.5 s) | Expired",
    );
    expect(pillsAfter(html, "Vision freshness")).toEqual(["fresh:fresh"]);
    expect(pillsAfter(html, "Telemetry freshness")).toEqual([
      "expired:expired (7.5 s)",
    ]);
  });

  it("both expired: no assessment, and each branch still says why", () => {
    const html = renderLive(expiryRecords.bothExpired());
    expect(html).toContain("Assessment unavailable");
    expect(pillsAfter(html, "SystemHealth")).toEqual([
      "UNAVAILABLE:UNAVAILABLE",
    ]);
    expect(modalityCard(html, "Visual Distraction")).toBe(
      "— | expired:expired (4 s) | Expired",
    );
    expect(modalityCard(html, "Telemetry Non-Safe")).toBe(
      "— | expired:expired (7.5 s) | Expired",
    );
    expect(pillsAfter(html, "Vision freshness")).toEqual([
      "expired:expired (4 s)",
    ]);
    expect(pillsAfter(html, "Telemetry freshness")).toEqual([
      "expired:expired (7.5 s)",
    ]);
  });

  it("a branch that never arrived reads missing / No input, not expired", () => {
    const html = renderLive(expiryRecords.visionNeverArrived());
    expect(modalityCard(html, "Visual Distraction")).toBe(
      "— | missing:missing | No input",
    );
    expect(pillsAfter(html, "Vision freshness")).toEqual(["missing:missing"]);
  });

  it("a historical `stale` record still renders as stale, with its number", () => {
    const html = renderLive(expiryRecords.legacyStale());
    expect(modalityCard(html, "Visual Distraction")).toBe(
      "50% | stale:stale | 0.50",
    );
    expect(pillsAfter(html, "Vision freshness")).toEqual(["stale:stale"]);
  });
});

describe("SignalInspector: the branch numbers and freshness pills carry the expiry", () => {
  it("vision expired (4 s), telemetry fresh", () => {
    const html = renderInspector(expiryRecords.visionExpired());
    expect(valuesAfter(html, "P_distraction")).toEqual(["Expired"]);
    expect(valuesAfter(html, "Telemetry non-safe risk")).toEqual(["30%"]);
    expect(pillsAfter(html, "Vision freshness")).toEqual([
      "expired:expired (4 s)",
    ]);
    expect(pillsAfter(html, "Telemetry freshness")).toEqual(["fresh:fresh"]);
  });

  it("telemetry expired (7.5 s), vision fresh", () => {
    const html = renderInspector(expiryRecords.telemetryExpired());
    expect(valuesAfter(html, "P_distraction")).toEqual(["50%"]);
    expect(valuesAfter(html, "Telemetry non-safe risk")).toEqual(["Expired"]);
    expect(pillsAfter(html, "Vision freshness")).toEqual(["fresh:fresh"]);
    expect(pillsAfter(html, "Telemetry freshness")).toEqual([
      "expired:expired (7.5 s)",
    ]);
  });

  it("both expired", () => {
    const html = renderInspector(expiryRecords.bothExpired());
    expect(valuesAfter(html, "P_distraction")).toEqual(["Expired"]);
    expect(valuesAfter(html, "Telemetry non-safe risk")).toEqual(["Expired"]);
    expect(pillsAfter(html, "Vision freshness")).toEqual([
      "expired:expired (4 s)",
    ]);
    expect(pillsAfter(html, "Telemetry freshness")).toEqual([
      "expired:expired (7.5 s)",
    ]);
  });

  it("a branch that never arrived reads No input / missing, not expired", () => {
    const html = renderInspector(expiryRecords.visionNeverArrived());
    expect(valuesAfter(html, "P_distraction")).toEqual(["No input"]);
    expect(pillsAfter(html, "Vision freshness")).toEqual(["missing:missing"]);
  });

  it("a historical `stale` record still renders as stale, with its number", () => {
    const html = renderInspector(expiryRecords.legacyStale());
    expect(valuesAfter(html, "P_distraction")).toEqual(["50%"]);
    expect(pillsAfter(html, "Vision freshness")).toEqual(["stale:stale"]);
  });
});

describe("ExplanationView: every branch number and both Freshness pills carry the expiry", () => {
  // The vision card is rendered before the telemetry card, so the two "Freshness"
  // pills come out as [vision, telemetry]. P_distraction and Telemetry Non-Safe Risk
  // each appear twice: once in the summary grid, once in their evidence card.
  it("vision expired (4 s), telemetry fresh", () => {
    const html = renderExplanation(expiryRecords.visionExpired());
    expect(valuesAfter(html, "P_distraction")).toEqual(["Expired", "Expired"]);
    expect(valuesAfter(html, "Telemetry Non-Safe Risk")).toEqual([
      "0.30",
      "0.30",
    ]);
    expect(pillsAfter(html, "Freshness")).toEqual([
      "expired:expired (4 s)",
      "fresh:fresh",
    ]);
    expect(valuesAfter(html, "Active inputs")).toEqual([
      "Vision expired (4 s) / Telemetry fresh",
    ]);
  });

  it("telemetry expired (7.5 s), vision fresh", () => {
    const html = renderExplanation(expiryRecords.telemetryExpired());
    expect(valuesAfter(html, "P_distraction")).toEqual(["0.50", "0.50"]);
    expect(valuesAfter(html, "Telemetry Non-Safe Risk")).toEqual([
      "Expired",
      "Expired",
    ]);
    expect(pillsAfter(html, "Freshness")).toEqual([
      "fresh:fresh",
      "expired:expired (7.5 s)",
    ]);
    expect(valuesAfter(html, "Active inputs")).toEqual([
      "Vision fresh / Telemetry expired (7.5 s)",
    ]);
  });

  it("both expired", () => {
    const html = renderExplanation(expiryRecords.bothExpired());
    expect(valuesAfter(html, "P_distraction")).toEqual(["Expired", "Expired"]);
    expect(valuesAfter(html, "Telemetry Non-Safe Risk")).toEqual([
      "Expired",
      "Expired",
    ]);
    expect(pillsAfter(html, "Freshness")).toEqual([
      "expired:expired (4 s)",
      "expired:expired (7.5 s)",
    ]);
    expect(valuesAfter(html, "Active inputs")).toEqual([
      "Vision expired (4 s) / Telemetry expired (7.5 s)",
    ]);
  });

  it("a branch that never arrived reads No input / missing, not expired", () => {
    const html = renderExplanation(expiryRecords.visionNeverArrived());
    expect(valuesAfter(html, "P_distraction")).toEqual([
      "No input",
      "No input",
    ]);
    expect(pillsAfter(html, "Freshness")).toEqual([
      "missing:missing",
      "fresh:fresh",
    ]);
    expect(valuesAfter(html, "Active inputs")).toEqual([
      "Vision missing / Telemetry fresh",
    ]);
  });

  it("a historical `stale` record still renders as stale, with its number", () => {
    const html = renderExplanation(expiryRecords.legacyStale());
    expect(valuesAfter(html, "P_distraction")).toEqual(["0.50", "0.50"]);
    expect(pillsAfter(html, "Freshness")).toEqual([
      "stale:stale",
      "fresh:fresh",
    ]);
    expect(valuesAfter(html, "Active inputs")).toEqual([
      "Vision stale / Telemetry fresh",
    ]);
  });
});
