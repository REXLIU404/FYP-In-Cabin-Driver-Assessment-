import { createElement } from "react";
import { describe, expect, it, vi } from "vitest";

// @types/node is not a project dependency and vitest swallows every .css import
// (even "?raw"), so the R30 source guard reads the stylesheet through node's fs,
// whose only missing piece is the typing below.
// @ts-expect-error - no @types/node in this repo
import { readFileSync } from "node:fs";

import type { useCameraPreview } from "../hooks/useCameraPreview";
import { AlertBanner } from "../components/AlertBanner";
import { CameraPreview } from "../components/CameraPreview";
import { SelectionBar } from "../components/SelectionBar";
import { expiryRecords } from "../testing/expiryRecords";
import { findElements, markup, pillsAfter } from "../testing/markup";
import { makeRecord } from "../testing/records";
import type { AppConfig, RiskUpdate } from "../types";
import { DEFAULT_CONFIG } from "../../../ai/src/riskLogic";
import { ConfigurationView } from "./ConfigurationView";
import { ExplanationView } from "./ExplanationView";
import { LiveMonitor } from "./LiveMonitor";
import { RiskTrends } from "./RiskTrends";
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
    expect(pillsAfter(html, "RiskLevel")).toEqual(["Medium:Medium"]);
    expect(pillsAfter(html, "DominantEvidence")).toEqual([
      "neutral:Combined evidence",
    ]);
    expect(pillsAfter(html, "AlertSeverity")).toEqual(["CAUTION:CAUTION"]);
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
    expect(pillsAfter(html, "AlertSeverity")).toEqual([
      "HIGH_ALERT:HIGH_ALERT",
    ]);
    expect(pillsAfter(html, "SystemHealth")).toEqual(["DEGRADED:DEGRADED"]);
  });

  it("the unavailable banner labels its system-health pill too (review R2)", () => {
    const html = markup(
      createElement(AlertBanner, { latest: expiryRecords.bothExpired() }),
    );
    expect(pillsAfter(html, "SystemHealth")).toEqual([
      "UNAVAILABLE:UNAVAILABLE",
    ]);
    expect(pillsAfter(html, "AlertSeverity")).toEqual([]);
  });
});

describe("contract names everywhere, values untouched, plain words in the tooltip (review R23)", () => {
  it("the banner labels AlertSeverity / SystemHealth and shows the recorded values", () => {
    const html = markup(
      createElement(AlertBanner, {
        latest: record({
          AlertSeverity: "HIGH_ALERT",
          SystemHealth: "DEGRADED",
        }),
      }),
    );
    expect(pillsAfter(html, "AlertSeverity")).toEqual([
      "HIGH_ALERT:HIGH_ALERT",
    ]);
    expect(pillsAfter(html, "SystemHealth")).toEqual(["DEGRADED:DEGRADED"]);
    expect(html).toContain(
      'title="Alert state: NORMAL, CAUTION or HIGH_ALERT."',
    );
    expect(html).toContain(
      'title="Input availability for this window: FULL means both inputs are fresh, DEGRADED means one input is missing or expired, UNAVAILABLE means the window has no assessment (no usable evidence). It does not measure accuracy."',
    );
  });

  it("Explanation uses the same four names and the contract values, not title-cased ones", () => {
    const selected = record();
    const html = markup(
      createElement(ExplanationView, {
        selectedRecord: selected,
        history: [selected],
        config: DEFAULT_CONFIG as AppConfig,
      }),
    );
    expect(pillsAfter(html, "RiskLevel")).toEqual(["Medium:Medium"]);
    // Was 'Caution' / 'Full' before review R23: the contract value stays as recorded.
    // The label itself must be the recorded value: a title-cased "Caution" fails here.
    expect(selected.AlertSeverity).toMatch(/^(NORMAL|CAUTION|HIGH_ALERT)$/);
    expect(pillsAfter(html, "AlertSeverity")).toEqual([
      `${selected.AlertSeverity}:${selected.AlertSeverity}`,
    ]);
    expect(pillsAfter(html, "SystemHealth")).toEqual(["FULL:FULL"]);
    expect(html).toContain("<span>DominantEvidence</span>");
    expect(html).not.toContain("AlertStatus");
    expect(html).not.toContain("Evidence Type");
    // The evidence type is the contract string, not formatEvidenceType's upper-case copy.
    expect(html).toContain("Vision-dominant");
    expect(html).not.toContain("VISION-DOMINANT");
  });

  it("the Live Monitor explains each contract name in a tooltip", () => {
    const html = renderLive(record());
    expect(html).toContain('title="Fused risk level: Low, Medium or High."');
    expect(html).toContain(
      'title="What the assessment rests on, checked in this order: Partial evidence when an input is missing or expired; otherwise Low observed risk when RiskScore is below the low threshold; otherwise Combined evidence when both branches are close, or Vision-dominant / Telemetry-dominant when one branch is clearly higher."',
    );
    expect(html).toContain(
      'title="Alert state: NORMAL, CAUTION or HIGH_ALERT."',
    );
    expect(html).toContain(
      'title="Input availability for this window: FULL means both inputs are fresh, DEGRADED means one input is missing or expired, UNAVAILABLE means the window has no assessment (no usable evidence). It does not measure accuracy."',
    );
  });
});

// Review of the DS-3 merge (75e1094): R23 left two views on the old names, and two
// tooltips only listed the values instead of saying what they mean.
describe("contract names in Signal Inspector and Risk Trends too; tooltips say what the values mean", () => {
  const DOMINANT_TIP =
    "What the assessment rests on, checked in this order: Partial evidence when an input is missing or expired; otherwise Low observed risk when RiskScore is below the low threshold; otherwise Combined evidence when both branches are close, or Vision-dominant / Telemetry-dominant when one branch is clearly higher.";
  const HEALTH_TIP =
    "Input availability for this window: FULL means both inputs are fresh, DEGRADED means one input is missing or expired, UNAVAILABLE means the window has no assessment (no usable evidence). It does not measure accuracy.";

  it("Signal Inspector labels the field DominantEvidence, with the tooltip", () => {
    const selected = record();
    const html = markup(
      createElement(SignalInspector, {
        history: [selected],
        selectedRecord: selected,
        thresholdLow: 30,
        onSelectWindow: () => {},
        onToggleFlag: () => {},
      }),
    );
    expect(html).toContain(
      `<div title="${DOMINANT_TIP}"><span>DominantEvidence</span>`,
    );
    expect(html).not.toContain("Evidence Type");
  });

  it("Risk Trends heads the columns AlertSeverity and DominantEvidence, with the tooltips", () => {
    const selected = record();
    const html = markup(
      createElement(RiskTrends, {
        history: [selected],
        selectedWindowId: selected.window_id,
        thresholdLow: 30,
        thresholdHigh: 60,
        onSelectWindow: () => {},
      }),
    );
    expect(html).toContain(
      '<th title="Alert state: NORMAL, CAUTION or HIGH_ALERT.">AlertSeverity</th>',
    );
    expect(html).toContain(`<th title="${DOMINANT_TIP}">DominantEvidence</th>`);
    expect(html).not.toContain("<th>Alert</th>");
    expect(html).not.toContain("Evidence Type");
  });

  it("the SystemHealth tooltip says FULL is about fresh inputs, not accuracy", () => {
    const html = renderLive(record());
    expect(html).toContain(`title="${HEALTH_TIP}"`);
    expect(html).not.toContain("Which branch dominates");
    expect(html).not.toContain("Runtime health:");
  });

  it("contract names are shown as written, not upper-cased by the stylesheet", () => {
    const stylesSource = readFileSync(
      new URL("../styles.css", import.meta.url),
      "utf8",
    );
    const rule = stylesSource.match(
      /\.badge-field > span:first-child \{[^}]*\}/,
    );
    expect(rule).toBeTruthy();
    expect(rule![0]).not.toContain("text-transform: uppercase");
  });
});

describe("Live Monitor: an alert that does not match the level is explained (FSM hysteresis)", () => {
  it("Low with CAUTION: the alert is held until Low has lasted 10 s", () => {
    const html = renderLive(
      record({ RiskLevel: "Low", AlertSeverity: "CAUTION" }),
    );
    expect(textOf(html)).toContain(
      "Alert held at CAUTION: it returns to NORMAL only after RiskLevel has stayed Low for 10 s (Live: 10 s of server time and of new observations).",
    );
    // The Alert chip shows the record's FSM severity, not a severity mapped from RiskLevel
    // (which would read NORMAL right beside the hold note - review R3).
    expect(pillsAfter(html, "AlertSeverity")).toEqual(["CAUTION:CAUTION"]);
    expect(pillsAfter(html, "RiskLevel")).toEqual(["Low:Low"]);
  });

  it("High with CAUTION: HIGH_ALERT needs High for 2 s", () => {
    const html = renderLive(
      record({ RiskLevel: "High", AlertSeverity: "CAUTION" }),
    );
    expect(textOf(html)).toContain(
      "Escalation pending: HIGH_ALERT follows only if RiskLevel stays High for 2 s (Live: 2 s of server time and of new observations).",
    );
    expect(pillsAfter(html, "AlertSeverity")).toEqual(["CAUTION:CAUTION"]);
    expect(pillsAfter(html, "RiskLevel")).toEqual(["High:High"]);
  });

  it("a level and alert that agree carry no note", () => {
    const html = renderLive(
      record({ RiskLevel: "Medium", AlertSeverity: "CAUTION" }),
    );
    expect(html).not.toContain("alert-note");
  });

  it("the hold note stays off the stale panel: a historical alert is not presented as current (review R4)", () => {
    const html = renderLive(
      record({ RiskLevel: "Low", AlertSeverity: "CAUTION" }),
      { stale: true },
    );
    expect(html).not.toContain("alert-note");
    expect(textOf(html)).toContain("Latest result is stale");
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

  it("in Prepared replay the latency row is labelled synthetic, with no server claim (review R26)", () => {
    const html = renderLive(record({ latency_ms: 126 }), {
      mode: "PREPARED_SESSION_RUNTIME",
    });
    expect(textOf(html)).toContain("Prepared latency (synthetic) 126 ms");
    expect(html).not.toContain("Time the server spent");
    expect(textOf(html)).not.toContain("Server processing time");
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

  it("a plain Pause (no fault) reads 'paused', not 'stopped' (review R5)", () => {
    const html = renderLive(record(), { isMonitoring: false });
    expect(textOf(html)).toContain("Monitoring paused");
    expect(textOf(html)).not.toContain("Monitoring stopped");
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

  it("requesting: Stop Camera only, so a pending permission request can be cancelled (review R13)", () => {
    expect(buttons("requesting")).toEqual([
      { text: "Stop Camera", disabled: false },
    ]);
  });

  it.each(["denied", "error"] as const)(
    "%s: Start Camera stays enabled for a retry (review R6)",
    (status) => {
      expect(buttons(status)).toEqual([
        { text: "Start Camera", disabled: false },
      ]);
    },
  );

  // .camera-placeholder is absolutely positioned to fill .camera-preview. The
  // constructed-scenario placeholder reuses it outside any .camera-preview, so without
  // its own box it is positioned against the page and covers the whole dashboard.
  it("the constructed-scenario placeholder is its own box, not a page overlay", () => {
    const stylesSource = readFileSync(
      new URL("../styles.css", import.meta.url),
      "utf8",
    );
    const rule = stylesSource.match(
      /\.camera-placeholder\.scenario-placeholder \{[^}]*\}/,
    );
    expect(rule).toBeTruthy();
    expect(rule![0]).toContain("position: relative");
    expect(rule![0]).toContain("min-height: 330px");
  });
});

describe("Selection bar: following the newest window vs a pinned one (deferred minor M1)", () => {
  it("following: says so and offers nothing to undo", () => {
    const onFollowLatest = vi.fn();
    const tree = SelectionBar({
      windowId: 12,
      pinned: false,
      isMonitoring: true,
      onFollowLatest,
    });
    expect(textOf(markup(tree))).toBe(
      "Showing Window 12 · following the newest window",
    );
    expect(findElements(tree, (el) => el.type === "button")).toHaveLength(0);
  });

  it("pinned while monitoring: says newer windows keep arriving, and Follow latest releases the pin", () => {
    const onFollowLatest = vi.fn();
    const tree = SelectionBar({
      windowId: 3,
      pinned: true,
      isMonitoring: true,
      onFollowLatest,
    });
    expect(textOf(markup(tree))).toBe(
      "Showing Window 3 · pinned; newer windows keep arriving Follow latest",
    );
    const [button] = findElements(tree, (el) => el.type === "button");
    (button.props as { onClick: () => void }).onClick();
    expect(onFollowLatest).toHaveBeenCalledTimes(1);
  });

  it("pinned after Pause: says 'pinned' only - no windows are arriving (review R9)", () => {
    const onFollowLatest = vi.fn();
    const tree = SelectionBar({
      windowId: 3,
      pinned: true,
      isMonitoring: false,
      onFollowLatest,
    });
    expect(textOf(markup(tree))).toBe(
      "Showing Window 3 · pinned Follow latest",
    );
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
  const renderConfig = () =>
    ConfigurationView({
      config: DEFAULT_CONFIG as AppConfig,
      onConfigChange() {},
      isMonitoring: false,
      onExportJson() {},
      onExportCsv() {},
    });

  it("Start / Pause / Restart live in the top bar only; export stays here", () => {
    const buttons = findElements(
      renderConfig(),
      (el) => el.type === "button",
    ).map((el) => textOf(markup(el)));
    expect(buttons).toEqual(["Export JSON", "Export CSV"]);
  });

  it("the note says what Start Monitoring does in each data mode (review R11/R27)", () => {
    const html = textOf(markup(renderConfig()));
    expect(html).toContain(
      "In Live mode the next Start Monitoring (top of the page) creates a session with the new configuration",
    );
    expect(html).toContain(
      "in Prepared replay it continues the same replay with the new settings (New Session starts over)",
    );
  });
});

describe("Risk Trends: the pin hint names the views the pin applies to (review R21)", () => {
  it("the hint is the three pin-aware views, not 'every view'", () => {
    const html = textOf(
      markup(
        createElement(RiskTrends, {
          history: [record()],
          selectedWindowId: 1,
          thresholdLow: 30,
          thresholdHigh: 60,
          onSelectWindow() {},
        }),
      ),
    );
    expect(html).toContain(
      "Click a row to pin that window in Signal Inspector, Risk Trends and Explanation.",
    );
    expect(html).not.toContain("in every view");
  });
});

describe("badge-field labels: AA contrast on every banner tint (review R30)", () => {
  const stylesSource = readFileSync(
    new URL("../styles.css", import.meta.url),
    "utf8",
  );

  it("the label colour is the darker slate, not the 4.3:1 muted grey", () => {
    const rule = stylesSource.match(
      /\.badge-field > span:first-child \{[^}]*\}/,
    );
    expect(rule).toBeTruthy();
    expect(rule![0]).toContain("color: #475569");
    expect(rule![0]).not.toContain("var(--muted)");
  });
});

describe("narrow layout: brand text gives way, the nav scrollbar stays visible (review R29)", () => {
  const stylesSource = readFileSync(
    new URL("../styles.css", import.meta.url),
    "utf8",
  );
  // The media query block itself, not the whole file: the rule must live at this width.
  const block = (width: number) =>
    stylesSource.match(
      new RegExp(`@media \\(max-width: ${width}px\\) \\{([\\s\\S]*?)\\n\\}`),
    )?.[1] ?? "";

  it("at <=900 px the brand text is hidden, freeing the row for the view buttons", () => {
    expect(block(900)).toMatch(/\.brand-copy[^{]*\{[^}]*display:\s*none/);
  });

  // Review of the DS-3 merge: a later rule in the same block showed it again for a
  // collapsed sidebar (681-900 px).
  it("no rule in the <=900 px block shows the brand text again, collapsed or not", () => {
    expect(block(900)).not.toMatch(
      /\.brand-copy[^{]*\{[^}]*display:\s*(block|flex|inline|grid)/,
    );
  });

  it("the one-row nav shows a thin scrollbar instead of hiding it", () => {
    expect(block(900)).toContain("scrollbar-width: thin");
    expect(block(900)).not.toContain("scrollbar-width: none");
  });
});
