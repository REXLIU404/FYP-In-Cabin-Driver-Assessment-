import { describe, expect, it } from "vitest";
import { makeRecord } from "../testing/records";
import { selectRecord } from "./selection";

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
