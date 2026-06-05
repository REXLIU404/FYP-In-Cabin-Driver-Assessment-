import { describe, expect, it } from "vitest";

import type { RiskUpdate } from "../types";
import { MAX_SESSION_RECORDS, nextWindowId } from "./persistence";

const rec = (id: number): RiskUpdate => ({ window_id: id }) as unknown as RiskUpdate;

describe("nextWindowId", () => {
  it("starts at 1 for an empty log", () => {
    expect(nextWindowId([])).toBe(1);
  });

  it("increments from the most recent record's id", () => {
    expect(nextWindowId([rec(1), rec(2), rec(3)])).toBe(4);
  });

  it("keeps increasing after the storage cap drops older records", () => {
    // A capped log holds MAX_SESSION_RECORDS items whose ids are far past the
    // cap size. A length-based id would wrongly repeat (cap + 1); the id must
    // come from the most recent record instead.
    const latestId = MAX_SESSION_RECORDS + 120;
    const capped = Array.from({ length: MAX_SESSION_RECORDS }, (_, i) =>
      rec(latestId - (MAX_SESSION_RECORDS - 1 - i)),
    );
    expect(capped).toHaveLength(MAX_SESSION_RECORDS);
    expect(nextWindowId(capped)).toBe(latestId + 1);
    expect(nextWindowId(capped)).not.toBe(capped.length + 1);
  });
});
