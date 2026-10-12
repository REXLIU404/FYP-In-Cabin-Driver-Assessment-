import { describe, expect, it } from "vitest";

import {
  UNAVAILABLE_LABEL,
  formatBranchPercent,
  formatBranchProbability,
  formatContribution,
  formatFixed,
  formatPercent,
  formatProbability,
  formatRiskScore,
} from "./format";

describe("formatRiskScore: one unavailable string for every call site", () => {
  it("null renders the unavailable label, never 0.0 / 100", () => {
    expect(formatRiskScore(null)).toBe(UNAVAILABLE_LABEL);
    expect(formatRiskScore(null)).not.toBe("0.0 / 100");
  });

  it("a genuine 0 is a reading and renders as 0.0 / 100", () => {
    expect(formatRiskScore(0)).toBe("0.0 / 100");
  });

  it("renders one decimal", () => {
    expect(formatRiskScore(70)).toBe("70.0 / 100");
    expect(formatRiskScore(62.5)).toBe("62.5 / 100");
  });
});

describe("display rounding is half-up on the decimal digits, like the backend", () => {
  it("formatFixed breaks exact decimal ties upward where toFixed does not", () => {
    // 0.285 is 0.28499999999999998 in binary: toFixed(2) gives "0.28", the
    // backend's round_half_up gives 0.29.
    expect((0.285).toFixed(2)).toBe("0.28");
    expect(formatFixed(0.285, 2)).toBe("0.29");
    expect((29.95).toFixed(1)).toBe("29.9");
    expect(formatFixed(29.95, 1)).toBe("30.0");
    expect(formatFixed(84.25, 1)).toBe("84.3");
  });

  it("pads trailing zeros and handles whole numbers", () => {
    expect(formatFixed(70, 1)).toBe("70.0");
    expect(formatFixed(0, 2)).toBe("0.00");
    expect(formatFixed(3.4, 0)).toBe("3");
    expect(formatFixed(3.5, 0)).toBe("4");
  });

  it("rounds negatives away from zero at a tie and never prints -0", () => {
    expect(formatFixed(-0.125, 2)).toBe("-0.13");
    expect(formatFixed(-0.001, 2)).toBe("0.00");
  });

  it("formatProbability uses two places", () => {
    expect(formatProbability(0.285)).toBe("0.29");
    expect(formatProbability(0)).toBe("0.00");
  });

  it("formatPercent rounds to an integer percent half-up", () => {
    expect(formatPercent(0.285)).toBe("29%");
    expect(formatPercent(0.07)).toBe("7%");
    expect(formatPercent(0)).toBe("0%");
    expect(formatPercent(1)).toBe("100%");
  });

  it("formatContribution is null-safe", () => {
    expect(formatContribution(null)).toBe(UNAVAILABLE_LABEL);
    expect(formatContribution(31.25)).toBe("31 / 100");
    expect(formatContribution(0)).toBe("0 / 100");
  });
});

describe("branch values do not present a missing input as a 0 reading", () => {
  it("a missing branch shows 'No input' instead of 0% / 0.00", () => {
    expect(formatBranchPercent(0, "missing")).toBe("No input");
    expect(formatBranchProbability(0, "missing")).toBe("No input");
  });

  it("fresh and stale branches show their value", () => {
    expect(formatBranchPercent(0.42, "fresh")).toBe("42%");
    expect(formatBranchPercent(0.42, "stale")).toBe("42%");
    expect(formatBranchProbability(0.42, "fresh")).toBe("0.42");
    // A real zero from a live branch is still a reading.
    expect(formatBranchPercent(0, "fresh")).toBe("0%");
  });
});
