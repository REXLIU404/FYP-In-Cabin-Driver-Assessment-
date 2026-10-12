import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { assertAvailabilityInvariant } from "../../../ai/src/availability";
import { makeRecord, toLegacyRow } from "../testing/records";
import type { RiskUpdate } from "../types";
import {
  MAX_SESSION_RECORDS,
  appendRecord,
  flagWindow,
  loadSessionLog,
  nextWindowId,
} from "./persistence";

const rec = (id: number): RiskUpdate =>
  ({ window_id: id }) as unknown as RiskUpdate;

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

// A minimal in-memory localStorage. vitest runs in `node`, so `window` does not
// exist; persistence.ts only needs `typeof window !== "undefined"` and a
// `localStorage` with get/set/remove.
const installStorage = (seed: Record<string, unknown> = {}) => {
  const store = new Map<string, string>(
    Object.entries(seed).map(([key, value]) => [key, JSON.stringify(value)]),
  );
  vi.stubGlobal("window", {
    localStorage: {
      getItem: (key: string) => store.get(key) ?? null,
      setItem: (key: string, value: string) => void store.set(key, value),
      removeItem: (key: string) => void store.delete(key),
    },
  });
  return store;
};
const LOG_KEY = "session_log:s1";

describe("UT-PERS-MIGRATE-01: legacy localStorage records normalise in both directions", () => {
  beforeEach(() => installStorage());
  afterEach(() => vi.unstubAllGlobals());

  // Legacy rows are derived from real producer output so every other field is
  // realistic; only the pre-contract shape differs.
  const legacyAvailable = {
    ...toLegacyRow(makeRecord("fresh", "missing", 1)),
    RiskScore: 42.0,
    RiskLevel: "Medium",
    AlertSeverity: "CAUTION",
    SystemHealth: "DEGRADED",
  };
  const legacyUnavailable = toLegacyRow(makeRecord("missing", "missing", 2));

  it("fixtures really are pre-contract rows", () => {
    expect(legacyAvailable).not.toHaveProperty("assessment_available");
    expect(legacyUnavailable).not.toHaveProperty("assessment_available");
    expect(legacyUnavailable).toMatchObject({
      RiskScore: 0,
      RiskLevel: "Low",
      AlertSeverity: "NORMAL",
      SystemHealth: "UNAVAILABLE",
    });
  });

  it("a 42.0 / Medium / DEGRADED row becomes available and keeps its values", () => {
    installStorage({ [LOG_KEY]: [legacyAvailable] });
    const [row] = loadSessionLog("s1");
    expect(row.assessment_available).toBe(true);
    expect(row.RiskScore).toBe(42);
    expect(row.RiskLevel).toBe("Medium");
    expect(row.AlertSeverity).toBe("CAUTION");
    expect(row.SystemHealth).toBe("DEGRADED");
    expect(() => assertAvailabilityInvariant(row)).not.toThrow();
  });

  it("a 0 / Low / NORMAL / UNAVAILABLE row becomes unavailable with all four fields null", () => {
    installStorage({ [LOG_KEY]: [legacyUnavailable] });
    const [row] = loadSessionLog("s1");
    expect(row.assessment_available).toBe(false);
    expect(row.RiskScore).toBeNull();
    expect(row.RiskLevel).toBeNull();
    expect(row.DominantEvidence).toBeNull();
    expect(row.AlertSeverity).toBeNull();
    // SystemHealth is kept: it is the disambiguating column.
    expect(row.SystemHealth).toBe("UNAVAILABLE");
    expect(() => assertAvailabilityInvariant(row)).not.toThrow();
  });

  it("does not wipe stored history: a whole legacy log keeps its available rows", () => {
    // Guards the `!record.assessment_available` mistake, which would mark every
    // legacy row unavailable and make the stored history vanish from the UI.
    const log = [1, 2, 3].map((id) => ({
      ...legacyAvailable,
      window_id: id,
    }));
    installStorage({ [LOG_KEY]: [...log, legacyUnavailable] });
    const loaded = loadSessionLog("s1");
    expect(loaded.map((r) => r.assessment_available)).toEqual([
      true,
      true,
      true,
      false,
    ]);
  });

  it("a legacy 0-score row that was genuinely assessed stays available", () => {
    // Derivation is from RiskScore !== null AND health, not from "is it falsy".
    const genuineZero = {
      ...legacyAvailable,
      RiskScore: 0,
      RiskLevel: "Low",
      AlertSeverity: "NORMAL",
      SystemHealth: "FULL",
    };
    installStorage({ [LOG_KEY]: [genuineZero] });
    const [row] = loadSessionLog("s1");
    expect(row.assessment_available).toBe(true);
    expect(row.RiskScore).toBe(0);
    expect(row.RiskLevel).toBe("Low");
  });

  it("a record that already carries the flag is passed through untouched", () => {
    const canonicalUnavailable = makeRecord("missing", "missing", 5);
    const canonicalAvailable = makeRecord("fresh", "fresh", 6);
    installStorage({ [LOG_KEY]: [canonicalUnavailable, canonicalAvailable] });
    expect(loadSessionLog("s1")).toEqual([
      canonicalUnavailable,
      canonicalAvailable,
    ]);
  });

  it("drops entries that are not record-shaped instead of crashing the UI", () => {
    installStorage({
      [LOG_KEY]: [null, 7, "x", { no: "window_id" }, legacyAvailable],
    });
    expect(loadSessionLog("s1")).toHaveLength(1);
  });

  it("a stored value that is not an array reads as an empty log", () => {
    installStorage({ [LOG_KEY]: { not: "an array" } });
    expect(loadSessionLog("s1")).toEqual([]);
  });

  it("writes migrate: appending to a legacy log persists the new shape", () => {
    const store = installStorage({ [LOG_KEY]: [legacyUnavailable] });
    appendRecord("s1", makeRecord("fresh", "fresh", 3));
    const stored = JSON.parse(store.get(LOG_KEY) ?? "[]");
    expect(stored).toHaveLength(2);
    expect(stored.map((r: RiskUpdate) => r.assessment_available)).toEqual([
      false,
      true,
    ]);
    expect(stored[0].RiskScore).toBeNull();
  });

  it("flagging a window in a legacy log keeps unavailable rows unavailable", () => {
    const store = installStorage({ [LOG_KEY]: [legacyUnavailable] });
    flagWindow("s1", 2, true);
    const [row] = JSON.parse(store.get(LOG_KEY) ?? "[]");
    expect(row.flagged).toBe(true);
    expect(row.assessment_available).toBe(false);
    expect(row.AlertSeverity).toBeNull();
  });
});
