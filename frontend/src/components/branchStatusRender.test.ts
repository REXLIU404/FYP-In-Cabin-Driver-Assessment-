import { createElement } from "react";
import { describe, expect, it } from "vitest";

import { expiryRecords } from "../testing/expiryRecords";
import { markup, modalityCard } from "../testing/markup";
import { AlertBanner } from "./AlertBanner";
import { BranchStatusPill } from "./BranchStatusPill";
import { ModalityCard } from "./ModalityCard";

// Ruling A (D13), A6: an EXPIRED branch must not read the same as a branch that never
// arrived. These tests render the real components to static markup (react-dom/server
// in the node environment) and assert the words and the tone on the page, so a
// component that stops passing the expiry through goes red here.

const NOT_EXPIRED = { expired: false, ageS: null };

describe("BranchStatusPill: expired is not missing", () => {
  const pill = (
    status: "fresh" | "stale" | "missing",
    expiry: { expired: boolean; ageS: number | null },
  ) => markup(createElement(BranchStatusPill, { status, expiry }));

  it("an expired branch reads `expired (N s)` in its own tone", () => {
    expect(pill("missing", { expired: true, ageS: 4 })).toBe(
      '<span class="pill pill--expired">expired (4 s)</span>',
    );
  });

  it("the age is printed as recorded, to the producer's 3 decimals", () => {
    expect(pill("missing", { expired: true, ageS: 3.001 })).toBe(
      '<span class="pill pill--expired">expired (3.001 s)</span>',
    );
  });

  it("an expired branch with no measurable age still says expired", () => {
    expect(pill("missing", { expired: true, ageS: null })).toBe(
      '<span class="pill pill--expired">expired</span>',
    );
  });

  it("a branch that never arrived reads `missing`, in the missing tone", () => {
    expect(pill("missing", NOT_EXPIRED)).toBe(
      '<span class="pill pill--missing">missing</span>',
    );
  });

  it("fresh reads `fresh`", () => {
    expect(pill("fresh", NOT_EXPIRED)).toBe(
      '<span class="pill pill--fresh">fresh</span>',
    );
  });

  it("a HISTORICAL `stale` record still renders as `stale`", () => {
    expect(pill("stale", NOT_EXPIRED)).toBe(
      '<span class="pill pill--stale">stale</span>',
    );
  });

  it("expired and missing render differently", () => {
    expect(pill("missing", { expired: true, ageS: 4 })).not.toBe(
      pill("missing", NOT_EXPIRED),
    );
  });
});

describe("ModalityCard: the number, the pill and the tooltip agree on expired", () => {
  const card = (
    freshness: "fresh" | "stale" | "missing",
    probability: number,
    expiry: { expired: boolean; ageS: number | null },
  ) =>
    modalityCard(
      markup(
        createElement(ModalityCard, {
          title: "Visual Distraction",
          probability,
          freshness,
          expiry,
        }),
      ),
      "Visual Distraction",
    );

  it("expired: no number, an `expired (N s)` pill, and the tooltip says Expired", () => {
    expect(card("missing", 0, { expired: true, ageS: 4 })).toBe(
      "— | expired:expired (4 s) | Expired",
    );
  });

  it("never arrived: no number, a `missing` pill, and the tooltip says No input", () => {
    expect(card("missing", 0, NOT_EXPIRED)).toBe(
      "— | missing:missing | No input",
    );
  });

  it("fresh: the number, a `fresh` pill and the probability", () => {
    expect(card("fresh", 0.5, NOT_EXPIRED)).toBe(
      "50% | fresh:fresh | P = 0.50",
    );
  });

  it("a historical `stale` record still shows its number", () => {
    expect(card("stale", 0.42, NOT_EXPIRED)).toBe(
      "42% | stale:stale | P = 0.42",
    );
  });

  it("`expiry` is a REQUIRED prop: leaving it out is a type error, and a render that gets through fails loudly instead of printing `missing`", () => {
    // If `expiry` becomes optional again (with a "not expired" default), the
    // directive below is unused and `tsc --noEmit` fails - that is the guard.
    const forgotten = () =>
      markup(
        createElement(
          ModalityCard,
          // @ts-expect-error `expiry` is required
          { title: "Visual Distraction", probability: 0, freshness: "missing" },
        ),
      );
    expect(forgotten).toThrow(TypeError);
  });
});

describe("AlertBanner: the branch figures say expired where the branch expired", () => {
  const figures = (record: Parameters<typeof AlertBanner>[0]["latest"]) => {
    const html = markup(createElement(AlertBanner, { latest: record }));
    const match =
      /Visual distraction: ([^|]*?) \| Telemetry non-safe: ([^<]*)<\/span>/.exec(
        html,
      );
    return match ? [match[1], match[2]] : null;
  };

  it("vision expired, telemetry fresh", () => {
    expect(figures(expiryRecords.visionExpired())).toEqual(["Expired", "30%"]);
  });

  it("telemetry expired, vision fresh", () => {
    expect(figures(expiryRecords.telemetryExpired())).toEqual([
      "50%",
      "Expired",
    ]);
  });

  it("vision never arrived (not expired) reads No input, not Expired", () => {
    expect(figures(expiryRecords.visionNeverArrived())).toEqual([
      "No input",
      "30%",
    ]);
  });

  it("both fresh: both numbers", () => {
    expect(figures(expiryRecords.allFresh())).toEqual(["50%", "30%"]);
  });

  it("a historical `stale` record still shows its number", () => {
    expect(figures(expiryRecords.legacyStale())).toEqual(["50%", "30%"]);
  });

  it("both expired: there is no assessment, and the banner says so", () => {
    const html = markup(
      createElement(AlertBanner, { latest: expiryRecords.bothExpired() }),
    );
    expect(html).toContain("No assessment for the latest window");
    expect(html).toContain(
      '<span class="pill pill--UNAVAILABLE">UNAVAILABLE</span>',
    );
  });
});
