import { createElement } from "react";
import { describe, expect, it } from "vitest";

import { DEFAULT_CONFIG } from "../../../ai/src/riskLogic";
import { makeRecord } from "../testing/records";
import { markup } from "../testing/markup";
import type { RiskUpdate, TelemetryFeatureContribution } from "../types";
import { ExplanationView } from "./ExplanationView";

// TELEMETRY-CONTRIBUTIONS, the Explanation card's "Feature Contribution" row.
//
// A Live record's contributions are a TreeSHAP local attribution on the Safe-class score, sign
// flipped (a POSITIVE value pushes toward UNSAFE), in log-odds. The card shows the three largest
// by absolute value, signed, and - only for a record whose provenance names that method - says
// what they mean. A replay record (the hand-written FYP1 table, no method) must not carry that
// sentence: it would be false for it.
//
// The eight numbers are replay row 1 of the frozen backend fixture (window 2, P = 0.6768, in the
// model's feature order). Expected strings are literals; none is built from an implementation
// constant.

const METHOD = "xgboost_treeshap_neg_safe_margin";

const ROW_1: TelemetryFeatureContribution[] = [
  { feature: "speed_kmph", contribution: -0.007805497385561466 },
  { feature: "accel_x", contribution: -0.06131267920136452 },
  { feature: "accel_y", contribution: -0.19677716493606567 },
  { feature: "brake_pressure", contribution: -2.2957253456115723 },
  { feature: "steering_angle", contribution: -0.03638264909386635 },
  { feature: "throttle", contribution: -0.0015636219177395105 },
  { feature: "lane_deviation", contribution: -0.09544149041175842 },
  { feature: "headway_distance", contribution: 4.763640880584717 },
];

const NOTE =
  "Explains Telemetry Non-Safe Risk; + pushes toward unsafe. TreeSHAP local attribution in model-score (log-odds) units; not causal.";

const withContributions = (
  contributions: TelemetryFeatureContribution[],
  provenance?: RiskUpdate["provenance"],
): RiskUpdate => ({
  ...makeRecord("fresh", "fresh", 1, {
    telemetry_feature_contributions: contributions,
  }),
  provenance,
});

const liveRecord = (contributions = ROW_1): RiskUpdate =>
  withContributions(contributions, {
    provider: "MobileNetV3ONNX+XGBoost",
    telemetry_contribution_method: METHOD,
    telemetry_contribution_baseline: -0.11871296912431717,
  });

const render = (record: RiskUpdate) =>
  markup(
    createElement(ExplanationView, {
      selectedRecord: record,
      history: [record],
      config: DEFAULT_CONFIG,
    }),
  );

/** `"<label> <signed value>"` of every feature row, in document order. */
const featureRows = (html: string): string[] =>
  [
    ...html.matchAll(
      /<div class="feature-contribution-row__meta"><strong>([^<]*)<\/strong><span>([^<]*)<\/span><\/div>/g,
    ),
  ].map((match) => `${match[1]} ${match[2]}`);

/** The class of each row's bar, in document order. */
const barClasses = (html: string): string[] =>
  [...html.matchAll(/<div class="(feature-contribution-row__bar[^"]*)"/g)].map(
    (match) => match[1],
  );

const notes = (html: string): string[] =>
  [
    ...html.matchAll(
      /<small class="feature-contribution-note">([^<]*)<\/small>/g,
    ),
  ].map((match) => match[1]);

describe("ExplanationView: a Live record's feature contributions", () => {
  it("shows the three largest by absolute value, signed, to two decimals, largest first", () => {
    expect(featureRows(render(liveRecord()))).toEqual([
      "Headway Distance +4.76",
      "Brake Pressure -2.30",
      "Lateral Accel -0.20",
    ]);
  });

  it("is order-independent: the same eight in another order give the same three", () => {
    expect(featureRows(render(liveRecord([...ROW_1].reverse())))).toEqual([
      "Headway Distance +4.76",
      "Brake Pressure -2.30",
      "Lateral Accel -0.20",
    ]);
  });

  it("draws a positive value (toward unsafe) and a negative one (toward safe) differently", () => {
    expect(barClasses(render(liveRecord()))).toEqual([
      "feature-contribution-row__bar",
      "feature-contribution-row__bar feature-contribution-row__bar--negative",
      "feature-contribution-row__bar feature-contribution-row__bar--negative",
    ]);
  });

  it("says what the numbers mean: non-safe risk, + toward unsafe, TreeSHAP, log-odds, not causal", () => {
    expect(notes(render(liveRecord()))).toEqual([NOTE]);
  });

  it("rounds half away from zero in the displayed digits, as the rest of the dashboard does", () => {
    const html = render(
      liveRecord([
        { feature: "speed_kmph", contribution: 1.005 },
        { feature: "accel_x", contribution: -0.125 },
        { feature: "throttle", contribution: 0.0049 },
      ]),
    );
    expect(featureRows(html)).toEqual([
      "Speed +1.01",
      "Longitudinal Accel -0.13",
      "Throttle +0.00",
    ]);
  });

  it("with no contributions says unavailable and does not explain nothing", () => {
    const html = render(liveRecord([]));
    expect(featureRows(html)).toEqual([]);
    expect(notes(html)).toEqual([]);
    expect(html).toContain("<strong>unavailable</strong>");
  });
});

describe("ExplanationView: a replay record's feature contributions", () => {
  const replayTable: TelemetryFeatureContribution[] = [
    { feature: "brake_pressure", contribution: 0.22 },
    { feature: "accel_x", contribution: 0.18 },
    { feature: "throttle", contribution: 0.15 },
  ];

  it("keeps showing the table and carries no TreeSHAP sentence", () => {
    for (const record of [
      withContributions(replayTable, undefined),
      withContributions(replayTable, { provider: "MockAIProvider" }),
    ]) {
      const html = render(record);
      expect(featureRows(html)).toEqual([
        "Brake Pressure +0.22",
        "Longitudinal Accel +0.18",
        "Throttle +0.15",
      ]);
      expect(notes(html)).toEqual([]);
      expect(html).not.toContain("TreeSHAP");
      expect(html).not.toContain("log-odds");
    }
  });

  it("does not claim TreeSHAP for a method name it does not know", () => {
    const html = render(
      withContributions(replayTable, {
        telemetry_contribution_method: "some_other_method",
      }),
    );
    expect(notes(html)).toEqual([]);
    expect(html).not.toContain("TreeSHAP");
  });
});
