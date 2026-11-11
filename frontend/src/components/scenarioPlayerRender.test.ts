import { createElement } from "react";
import { describe, expect, it } from "vitest";

import { markup } from "../testing/markup";
import type { ScenarioPlayerModel } from "../views/scenarioPlayerModel";
import { ScenarioPlayer } from "./ScenarioPlayer";

// Static render (react-dom/server, node environment - the same approach as
// runtimeNotices.test.ts): what can be asserted is the markup the player paints.
// The expected strings are literals.

const model = (over: Partial<ScenarioPlayerModel> = {}): ScenarioPlayerModel => ({
  badge: "CONSTRUCTED SCENARIO",
  caption:
    "Segment 2/7 · Vision only · texting_right · driver p026 · State Farm test split",
  truth: "texting_right",
  model: "texting_right 0.97",
  segments: [
    { title: "Baseline", state: "done" },
    { title: "Vision only", state: "current" },
    { title: "Both", state: "todo" },
    { title: "Recovery", state: "todo" },
    { title: "Telemetry only", state: "todo" },
    { title: "Both", state: "todo" },
    { title: "Recovery", state: "todo" },
  ],
  elapsed: "0:34 / 2:16",
  finished: false,
  ...over,
});

const render = (
  over: Partial<ScenarioPlayerModel> = {},
  frameSrc: string | null = "data:image/jpeg;base64,AAAA",
  finishedText: string | null = null,
) =>
  markup(
    createElement(ScenarioPlayer, {
      model: model(over),
      frameSrc,
      finishedText,
    }),
  );

describe("ScenarioPlayer (static render)", () => {
  it("the CONSTRUCTED SCENARIO badge is always there", () => {
    expect(render()).toContain(
      '<span class="scenario-badge">CONSTRUCTED SCENARIO</span>',
    );
  });

  it("there are no Start / Stop Camera buttons", () => {
    const html = render();
    expect(html).not.toContain("Start Camera");
    expect(html).not.toContain("Stop Camera");
  });

  it("the progress bar has exactly 7 blocks and only the current one carries the current class", () => {
    const html = render();
    expect(html.match(/class="scenario-progress-block/g)).toHaveLength(7);
    expect(html.match(/scenario-progress-block--current/g)).toHaveLength(1);
  });

  it("the caption row shows truth vs model", () => {
    const html = render();
    expect(html).toContain("Truth: texting_right");
    expect(html).toContain("Model: texting_right 0.97");
  });

  it("once finished, the finished line replaces the caption", () => {
    const html = render({ finished: true }, null, "Scenario finished (136 s, 7 segments)");
    expect(html).toContain("Scenario finished (136 s, 7 segments)");
    expect(html).not.toContain("Segment 2/7");
  });

  it("a missing frame paints the placeholder, not a broken image", () => {
    const html = render({}, null);
    expect(html).not.toContain("<img");
    expect(html).toContain("No scenario frame");
  });
});
