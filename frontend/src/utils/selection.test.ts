import { describe, expect, it } from "vitest";
import { makeRecord } from "../testing/records";
import { describeSelection, selectRecord } from "./selection";

const history = [1, 2, 3, 4].map((id) => makeRecord("fresh", "fresh", id));

describe("selectRecord: which window the Inspector and Explanation show", () => {
  it("follows the newest window when nothing is pinned (null)", () => {
    expect(selectRecord(history, null)?.window_id).toBe(4);
  });

  it("keeps a window the person pinned while newer ones arrive", () => {
    expect(selectRecord(history, 2)?.window_id).toBe(2);
    const grown = [...history, makeRecord("fresh", "fresh", 5)];
    expect(selectRecord(grown, 2)?.window_id).toBe(2);
  });

  it("falls back to the newest when the pinned window has left the page's history", () => {
    expect(selectRecord(history.slice(2), 1)?.window_id).toBe(4);
  });

  it("has nothing to show for an empty history", () => {
    expect(selectRecord([], null)).toBeUndefined();
    expect(selectRecord([], 3)).toBeUndefined();
  });
});

describe("describeSelection: what the selection bar says (deferred minor M1)", () => {
  it("nothing pinned: the newest window, following", () => {
    expect(describeSelection(history, null)).toEqual({
      windowId: 4,
      pinned: false,
    });
  });

  it("a pinned window still in the history: that window, pinned", () => {
    expect(describeSelection(history, 2)).toEqual({
      windowId: 2,
      pinned: true,
    });
  });

  it("a pinned window that has left the history no longer counts as pinned", () => {
    // selectRecord already shows the newest one; the bar must not claim a pin it cannot show.
    expect(describeSelection(history.slice(2), 1)).toEqual({
      windowId: 4,
      pinned: false,
    });
  });

  it("an empty history has nothing to describe", () => {
    expect(describeSelection([], null)).toBeNull();
    expect(describeSelection([], 2)).toBeNull();
  });
});
