import { createElement } from "react";
import { describe, expect, it, vi } from "vitest";

import type { useCameraPreview } from "../hooks/useCameraPreview";
import { AlertBanner } from "../components/AlertBanner";
import { CameraPreview } from "../components/CameraPreview";
import { SelectionBar } from "../components/SelectionBar";
import { findElements, markup, pillsAfter } from "../testing/markup";
import { makeRecord } from "../testing/records";
import type { AppConfig, RiskUpdate } from "../types";
import { DEFAULT_CONFIG } from "../../../ai/src/riskLogic";
import { ConfigurationView } from "./ConfigurationView";
import { LiveMonitor } from "./LiveMonitor";
import { SignalInspector } from "./SignalInspector";

// UI review 2026-10-23 (user friendliness). Static markup in the node environment, as in
// branchStatusRender.test.ts. Every expected string is a literal.

const camera = (status = "idle") =>
  ({
    videoRef: null,
    status,
    start() {},
    stop() {},
  }) as unknown as ReturnType<typeof useCameraPreview>;

const record = (over: Partial<RiskUpdate> = {}): RiskUpdate => ({
  ...makeRecord("fresh", "fresh", 7),
  ...over,
});

const renderLive = (
  latest: RiskUpdate,
  over: Partial<Parameters<typeof LiveMonitor>[0]> = {},
) =>
  markup(
    createElement(LiveMonitor, {
      latest,
      history: [latest],
      sessionId: "5aded42d572f742b9b3298ae4e0f2ab40",
      recordCount: 1,
      isMonitoring: true,
      camera: camera(),
      thresholdLow: 30,
      thresholdHigh: 60,
      ...over,
    }),
  );

const textOf = (html: string) =>
  html
    .replace(/<[^>]+>/g, " ")
    .replace(/\s+/g, " ")
    .trim();

describe("Live Monitor: every status chip says what it is", () => {
  it("the risk level, evidence and alert badges each sit under their own label", () => {
    const html = renderLive(
      record({
        RiskLevel: "Medium",
        AlertSeverity: "CAUTION",
        DominantEvidence: "Combined evidence",
      }),
    );
    expect(pillsAfter(html, "Risk level")).toEqual(["Medium:Medium"]);
    expect(pillsAfter(html, "Evidence")).toEqual(["neutral:Combined evidence"]);
    expect(pillsAfter(html, "Alert")).toEqual(["CAUTION:CAUTION"]);
  });

  it("the banner labels its alert and system-health pills", () => {
    const html = markup(
      createElement(AlertBanner, {
        latest: record({
          AlertSeverity: "HIGH_ALERT",
          SystemHealth: "DEGRADED",
        }),
      }),
    );
    expect(pillsAfter(html, "Alert")).toEqual(["HIGH_ALERT:HIGH_ALERT"]);
    expect(pillsAfter(html, "System health")).toEqual(["DEGRADED:DEGRADED"]);
  });
});

describe("Live Monitor: an alert that does not match the level is explained (FSM hysteresis)", () => {
  it("Low with CAUTION: the alert is held until Low has lasted 10 s", () => {
    const html = renderLive(
      record({ RiskLevel: "Low", AlertSeverity: "CAUTION" }),
    );
    expect(textOf(html)).toContain(
      "Alert held at CAUTION: it returns to NORMAL only after RiskLevel has stayed Low for 10 s.",
    );
  });

  it("High with CAUTION: HIGH_ALERT needs High for 2 s", () => {
    const html = renderLive(
      record({ RiskLevel: "High", AlertSeverity: "CAUTION" }),
    );
    expect(textOf(html)).toContain(
      "Escalation pending: HIGH_ALERT follows only if RiskLevel stays High for 2 s.",
    );
  });

  it("a level and alert that agree carry no note", () => {
    const html = renderLive(
      record({ RiskLevel: "Medium", AlertSeverity: "CAUTION" }),
    );
    expect(html).not.toContain("alert-note");
  });
});

describe("Live Monitor: plain words and no duplicated numbers", () => {
  it("the session id keeps its full text (copyable, title) but is shown on one line", () => {
    const html = renderLive(record());
    expect(html).toContain(
      '<strong class="session-id" title="5aded42d572f742b9b3298ae4e0f2ab40">5aded42d572f742b9b3298ae4e0f2ab40</strong>',
    );
  });

  it("server time is labelled in plain words", () => {
    const html = renderLive(record({ latency_ms: 5 }));
    expect(textOf(html)).toContain("Server processing time 5 ms");
    expect(html).not.toContain("before DB commit</span>");
  });

  it("a branch card shows the percent once; the exact probability is in its tooltip", () => {
    const html = renderLive(record());
    expect(html).toContain(
      '<div class="modality-card"><span>Visual Distraction</span><strong title="P = 0.50">50%</strong>',
    );
    expect(html).not.toMatch(/<small>0\.50<\/small>/);
  });

  it("a monitoring run that stopped on a fault does not read 'paused'", () => {
    const html = renderLive(record(), { isMonitoring: false, stopped: true });
    expect(textOf(html)).toContain("Monitoring stopped");
    expect(textOf(html)).not.toContain("Monitoring paused");
  });
});

describe("Camera preview: only the action that applies is offered", () => {
  const buttons = (status: string) =>
    findElements(
      CameraPreview({
        videoRef: null,
        status: status as never,
        onStart() {},
        onStop() {},
      }),
      (el) => el.type === "button",
    ).map((el) => ({
      text: textOf(markup(el)),
      disabled: Boolean((el.props as { disabled?: boolean }).disabled),
    }));

  it("idle: Start Camera only", () => {
    expect(buttons("idle")).toEqual([
      { text: "Start Camera", disabled: false },
    ]);
  });

  it("live: Stop Camera only", () => {
    expect(buttons("live")).toEqual([{ text: "Stop Camera", disabled: false }]);
  });

  it("requesting: Start Camera, disabled", () => {
    expect(buttons("requesting")).toEqual([
      { text: "Start Camera", disabled: true },
    ]);
  });
});

describe("Selection bar: following the newest window vs a pinned one (deferred minor M1)", () => {
  it("following: says so and offers nothing to undo", () => {
    const onFollowLatest = vi.fn();
    const tree = SelectionBar({ windowId: 12, pinned: false, onFollowLatest });
    expect(textOf(markup(tree))).toBe(
      "Showing Window 12 · following the newest window",
    );
    expect(findElements(tree, (el) => el.type === "button")).toHaveLength(0);
  });

  it("pinned: says so, and Follow latest releases the pin", () => {
    const onFollowLatest = vi.fn();
    const tree = SelectionBar({ windowId: 3, pinned: true, onFollowLatest });
    expect(textOf(markup(tree))).toBe(
      "Showing Window 3 · pinned; newer windows keep arriving Follow latest",
    );
    const [button] = findElements(tree, (el) => el.type === "button");
    (button.props as { onClick: () => void }).onClick();
    expect(onFollowLatest).toHaveBeenCalledTimes(1);
  });
});

describe("Signal Inspector: visual classes, highest probability first", () => {
  it("the bar order follows the probability, not the class order", () => {
    const selected = record({
      visual_top_classes: [
        { label: "safe_driving", probability: 0.1 },
        { label: "texting_right", probability: 0.7 },
        { label: "drinking", probability: 0.2 },
      ],
    });
    const html = markup(
      createElement(SignalInspector, {
        history: [selected],
        selectedRecord: selected,
        thresholdLow: 30,
        onSelectWindow() {},
        onToggleFlag() {},
      }),
    );
    const labels = [
      ...html.matchAll(/<div class="bar-row"><span title="([^"]*)">/g),
    ].map((m) => m[1]);
    expect(labels).toEqual(["texting_right", "drinking", "safe_driving"]);
  });
});

describe("Configuration: no second set of run controls", () => {
  it("Start / Pause / Restart live in the top bar only; export stays here", () => {
    const tree = ConfigurationView({
      config: DEFAULT_CONFIG as AppConfig,
      onConfigChange() {},
      isMonitoring: false,
      onExportJson() {},
      onExportCsv() {},
    });
    const buttons = findElements(tree, (el) => el.type === "button").map((el) =>
      textOf(markup(el)),
    );
    expect(buttons).toEqual(["Export JSON", "Export CSV"]);
  });
});
