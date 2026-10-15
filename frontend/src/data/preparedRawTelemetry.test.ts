import { describe, expect, it } from "vitest";

import liveLoopSource from "../../../ai/src/liveLoop.ts?raw";
import telemetryCsv from "../../../ai/prototype-data/prepared_sessions/session_001/telemetry.csv?raw";
import useLiveSessionSource from "../hooks/useLiveSession.ts?raw";
import preparedSessionInputSource from "./preparedSessionInput.ts?raw";
import {
  PREPARED_RAW_TELEMETRY,
  PREPARED_SESSION_WINDOWS,
  preparedTelemetryAt,
} from "./preparedSessionInput";

// Task 9 / K6. The Live runtime reads the prepared session ONLY for its raw
// telemetry (the 8 features that go to the trained XGBoost). The other half of that
// file - P_distraction, P_telemetry_anomaly, visual_top_classes, the behaviour
// probabilities - is a prepared-PROBABILITY object that belongs to the retained
// legacy replay. Two things keep the Live claim honest: the raw table below is
// exactly telemetry.csv (nothing derived), and no Live source file names the
// probability object.

// The CSV is read the way missingCases.test.ts (F1) reads it: `?raw`, split on
// lines, split on commas. The parser is the test's own, not the implementation's.
const lines = telemetryCsv.split(/\r?\n/).filter((line) => line !== "");
const header = lines[0].split(",");
const csvRows = lines
  .slice(1)
  .map(
    (line): Record<string, string> =>
      Object.fromEntries(
        line.split(",").map((cell, index) => [header[index], cell]),
      ),
  );

// The 8 features in their fixed order (global constraints), restated here.
const FEATURES = [
  "speed_kmph",
  "accel_x",
  "accel_y",
  "brake_pressure",
  "steering_angle",
  "throttle",
  "lane_deviation",
  "headway_distance",
] as const;

describe("PREPARED_RAW_TELEMETRY is telemetry.csv, row for row", () => {
  it("sanity: the file under test has the 25 documented rows", () => {
    expect(csvRows).toHaveLength(25);
    expect(PREPARED_RAW_TELEMETRY).toHaveLength(25);
  });

  it.each(csvRows.map((row) => [Number(row.window_id), row] as const))(
    "row %i: timestamp, the 8 features (or null) and the age equal the CSV cells",
    (windowId, row) => {
      const actual = PREPARED_RAW_TELEMETRY[windowId - 1];
      const available = row.telemetry_available === "1";
      // 10:00:SS at +08:00 is 02:00:SS in UTC; every row of the session is in minute 00.
      const [, minute, second] = row.timestamp.split(":");
      expect(actual.timestamp).toBe(`2026-05-06T02:${minute}:${second}.000Z`);
      expect(actual.telemetry_features).toEqual(
        available
          ? Object.fromEntries(
              FEATURES.map((name) => [name, Number(row[name])]),
            )
          : null,
      );
      // 999 on a row without telemetry is a sentinel, never reported as an age.
      expect(actual.telemetry_age_s).toBe(
        available ? Number(row.telemetry_age_s) : null,
      );
      if (available) {
        expect(Object.keys(actual.telemetry_features ?? {})).toEqual([
          ...FEATURES,
        ]);
      }
    },
  );

  it("pins the cells the Live scenarios rely on, as literals", () => {
    expect(PREPARED_RAW_TELEMETRY[0].telemetry_features).toEqual({
      speed_kmph: 34,
      accel_x: 0.3,
      accel_y: 0.1,
      brake_pressure: 12,
      steering_angle: -2,
      throttle: 30,
      lane_deviation: 0.3,
      headway_distance: 26,
    });
    // Rows 14 and 17 carry no telemetry (R5: Live still sends them, as `missing`).
    const missing = PREPARED_RAW_TELEMETRY.flatMap((row, index) =>
      row.telemetry_features === null ? [index + 1] : [],
    );
    expect(missing).toEqual([14, 17]);
    // Row 16's telemetry is 4 s old: the replay expires it, the raw row only reports it.
    expect(PREPARED_RAW_TELEMETRY[15].telemetry_age_s).toBe(4);
  });

  it("carries nothing but the three raw fields - no probability of any kind", () => {
    for (const row of PREPARED_RAW_TELEMETRY) {
      expect(Object.keys(row).sort()).toEqual([
        "telemetry_age_s",
        "telemetry_features",
        "timestamp",
      ]);
    }
  });

  it("agrees with the replay windows on the telemetry they both read", () => {
    // One parsing path feeds both, so the two cannot drift apart.
    expect(PREPARED_RAW_TELEMETRY.map((row) => row.telemetry_features)).toEqual(
      PREPARED_SESSION_WINDOWS.map((window) => window.telemetry_features),
    );
    expect(PREPARED_RAW_TELEMETRY.map((row) => row.timestamp)).toEqual(
      PREPARED_SESSION_WINDOWS.map((window) => window.timestamp),
    );
  });
});

describe("preparedTelemetryAt: the Live cursor reads the raw table (rule unchanged: one row per 2000 ms, wrapping)", () => {
  // The advance rule is exactly what useLiveSession did before this task; R10 will
  // replace it. What changed is only where the rows come from.
  it("maps elapsed time to a row at the original 2 s cadence", () => {
    expect(preparedTelemetryAt(0)).toEqual(
      PREPARED_RAW_TELEMETRY[0].telemetry_features,
    );
    expect(preparedTelemetryAt(1999)).toEqual(
      PREPARED_RAW_TELEMETRY[0].telemetry_features,
    );
    expect(preparedTelemetryAt(2000)).toEqual(
      PREPARED_RAW_TELEMETRY[1].telemetry_features,
    );
    // Row 14 starts at 26 s, row 17 at 32 s: both have no telemetry.
    expect(preparedTelemetryAt(25_999)).not.toBeNull();
    expect(preparedTelemetryAt(26_000)).toBeNull();
    expect(preparedTelemetryAt(27_999)).toBeNull();
    expect(preparedTelemetryAt(28_000)).not.toBeNull();
    expect(preparedTelemetryAt(32_000)).toBeNull();
  });

  it("wraps after the 25th row (50 s)", () => {
    expect(preparedTelemetryAt(50_000)).toEqual(
      PREPARED_RAW_TELEMETRY[0].telemetry_features,
    );
    expect(preparedTelemetryAt(50_000 + 26_000)).toBeNull();
  });
});

// SCOPE GUARD (Task 9, D03). Not a behaviour test: it reads the SOURCE of the Live
// path and fails if it ever names the replay's prepared-probability object again.
// Without it, a later edit could re-import PREPARED_SESSION_WINDOWS "for the
// telemetry" and the Live-only claim would quietly stop being true.
describe("scope guard: the Live path does not use the prepared-probability replay data", () => {
  const strip = (source: string) =>
    source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:])\/\/.*$/gm, "$1");

  const livePath = {
    "frontend/src/hooks/useLiveSession.ts": useLiveSessionSource,
    "ai/src/liveLoop.ts": liveLoopSource,
  };

  it.each(Object.entries(livePath))(
    "%s never mentions PREPARED_SESSION_WINDOWS or the replay builder",
    (_file, source) => {
      const code = strip(source);
      expect(code).not.toMatch(/\bPREPARED_SESSION_WINDOWS\b/);
      expect(code).not.toMatch(/\bbuildPreparedWindows\b/);
    },
  );

  it("the telemetry injection point (the hook) takes its rows from the raw source", () => {
    // Positive check, so the guard above cannot pass because the source was deleted
    // or the telemetry was re-pointed at something else.
    expect(strip(useLiveSessionSource)).toMatch(
      /telemetryAt:\s*preparedTelemetryAt\b/,
    );
  });

  // The hook only NAMES the cursor (`telemetryAt: preparedTelemetryAt`); the function
  // that actually reads the rows lives in preparedSessionInput.ts, the same module
  // that defines PREPARED_SESSION_WINDOWS. Scanning the hook and the loop therefore
  // cannot see a cursor that has quietly been pointed back at the replay table, and
  // the two tables hold identical telemetry values, so no content test can either.
  // So the guard reads the cursor's own source.
  describe("the cursor the hook injects (preparedTelemetryAt)", () => {
    // The text of the one top-level statement that begins at `marker`: up to the first
    // `;` outside every (), [] and {}. If no such `;` exists the rest of the file is
    // returned, which can only make the guard stricter, never blinder.
    const statementStartingAt = (code: string, marker: string): string => {
      const start = code.indexOf(marker);
      expect(
        start,
        `${marker} was not found in preparedSessionInput.ts; update this guard`,
      ).toBeGreaterThanOrEqual(0);
      let depth = 0;
      for (let index = start; index < code.length; index += 1) {
        const char = code[index];
        if ("([{".includes(char)) depth += 1;
        else if (")]}".includes(char)) depth -= 1;
        else if (char === ";" && depth === 0) {
          return code.slice(start, index + 1);
        }
      }
      return code.slice(start);
    };

    const cursor = statementStartingAt(
      strip(preparedSessionInputSource),
      "export const preparedTelemetryAt",
    );

    it("the extracted statement is the whole cursor (so the checks below cannot pass on a truncated slice)", () => {
      expect(cursor).toMatch(/Math\.floor\(elapsedMs \/ 2000\)/);
      expect(cursor).toMatch(/\.telemetry_features\s*;$/);
    });

    it("reads PREPARED_RAW_TELEMETRY", () => {
      expect(cursor).toMatch(/\bPREPARED_RAW_TELEMETRY\b/);
    });

    it("never mentions PREPARED_SESSION_WINDOWS or the replay builder", () => {
      expect(cursor).not.toMatch(/\bPREPARED_SESSION_WINDOWS\b/);
      expect(cursor).not.toMatch(/\bbuildPreparedWindows\b/);
    });
  });

  it("the pure loop imports nothing from the data layer at all", () => {
    expect(strip(liveLoopSource)).not.toMatch(/\bpreparedSessionInput\b/);
    const imports = [...liveLoopSource.matchAll(/from\s+"([^"]+)"/g)].map(
      (match) => match[1],
    );
    expect(imports).toEqual(["./types"]);
  });
});
