import { describe, expect, it } from "vitest";

import liveLoopSource from "../../../ai/src/liveLoop.ts?raw";
import telemetryCsv from "../../../ai/prototype-data/prepared_sessions/session_001/telemetry.csv?raw";
import useLiveSessionSource from "../hooks/useLiveSession.ts?raw";
import preparedSessionInputSource from "./preparedSessionInput.ts?raw";
import {
  PREPARED_RAW_TELEMETRY,
  PREPARED_SESSION_WINDOWS,
  createPreparedTelemetryCursor,
  type PreparedRawTelemetryRow,
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

// R10-B (B1). The cursor numbers the prepared rows and stamps them with a LOGICAL event
// time (the replay has no sensor moment). Three rows with distinct speeds stand in for
// the table so every expectation is a short, hand-checkable literal; the real 25 rows
// are checked further down. T is the moment the session began.
describe("the Live telemetry cursor (R10-B)", () => {
  const T = 1_800_000_000_000;
  const row = (speed: number): PreparedRawTelemetryRow => ({
    timestamp: "",
    telemetry_features: {
      speed_kmph: speed,
      accel_x: 0,
      accel_y: 0,
      brake_pressure: 0,
      steering_angle: 0,
      throttle: 0,
      lane_deviation: 0,
      headway_distance: 0,
    },
    telemetry_age_s: 0,
  });
  const ROWS = [row(10), row(20), row(30)];
  const speedOf = (reading: { features: { speed_kmph: number } | null }) =>
    reading.features?.speed_kmph ?? null;
  const fresh = () => {
    const cursor = createPreparedTelemetryCursor(ROWS);
    cursor.reset(T);
    return cursor;
  };

  it("advances one row per 2000 ms of monitoring: 1999 ms is still the first sample, 2000 ms the second", () => {
    const cursor = fresh();
    expect(cursor.read(T)).toMatchObject({ seq: 0, acquiredAtMs: T });
    expect(cursor.read(T + 1999)).toMatchObject({ seq: 0, acquiredAtMs: T });
    expect(cursor.read(T + 2000)).toMatchObject({
      seq: 1,
      acquiredAtMs: T + 2000,
    });
    expect(cursor.read(T + 3999)).toMatchObject({ seq: 1 });
    expect(cursor.read(T + 4000)).toMatchObject({
      seq: 2,
      acquiredAtMs: T + 4000,
    });
  });

  it("the row is seq % 3 but the sequence number is NOT capped: it keeps counting past the table", () => {
    const cursor = fresh();
    const at = (ms: number) => cursor.read(T + ms);
    expect([speedOf(at(0)), at(0).seq]).toEqual([10, 0]);
    expect([speedOf(at(2000)), at(2000).seq]).toEqual([20, 1]);
    expect([speedOf(at(4000)), at(4000).seq]).toEqual([30, 2]);
    expect([speedOf(at(6000)), at(6000).seq]).toEqual([10, 3]); // wrapped row, seq 3
    expect([speedOf(at(8000)), at(8000).seq]).toEqual([20, 4]);
    expect([speedOf(at(50_000)), at(50_000).seq]).toEqual([20, 25]); // 25 % 3 = 1
    expect(at(50_000).acquiredAtMs).toBe(T + 50_000);
  });

  it("the acquisition time is arithmetic: the same sequence number has the same time however late inside its slot it is read", () => {
    const cursor = fresh();
    const early = cursor.read(T + 2000);
    const late = cursor.read(T + 3999);
    expect(late).toEqual(early);
    expect(late.acquiredAtMs).toBe(T + 2000); // not the moment of reading
  });

  it("pausing freezes it: however long the pause, a read returns the frozen sample", () => {
    const cursor = fresh();
    cursor.pause(T + 5000); // sequence 2
    expect(cursor.read(T + 5000)).toMatchObject({
      seq: 2,
      acquiredAtMs: T + 4000,
    });
    expect(cursor.read(T + 500_000)).toMatchObject({
      seq: 2,
      acquiredAtMs: T + 4000,
    });
    expect(cursor.read(T + 5_000_000)).toMatchObject({
      seq: 2,
      acquiredAtMs: T + 4000,
    });
  });

  it("resuming opens a NEW observation at once: one sequence past the frozen one, timed at the moment of resuming", () => {
    const cursor = fresh();
    cursor.pause(T + 5000); // frozen on sequence 2
    cursor.resume(T + 600_000);
    expect(cursor.read(T + 600_000)).toMatchObject({
      seq: 3,
      acquiredAtMs: T + 600_000,
    });
    expect(speedOf(cursor.read(T + 600_000))).toBe(10); // row 3 % 3
    expect(cursor.read(T + 601_999)).toMatchObject({
      seq: 3,
      acquiredAtMs: T + 600_000,
    });
    expect(cursor.read(T + 602_000)).toMatchObject({
      seq: 4,
      acquiredAtMs: T + 602_000,
    });
  });

  it("every resume has its own base time and start sequence", () => {
    const cursor = fresh();
    cursor.pause(T + 5000); // sequence 2
    cursor.resume(T + 600_000); // segment 2: sequence 3 from T + 600 s
    cursor.pause(T + 603_000); // sequence 4
    expect(cursor.read(T + 700_000)).toMatchObject({
      seq: 4,
      acquiredAtMs: T + 602_000,
    });
    cursor.resume(T + 700_000); // segment 3: sequence 5 from T + 700 s
    expect(cursor.read(T + 700_000)).toMatchObject({
      seq: 5,
      acquiredAtMs: T + 700_000,
    });
    expect(cursor.read(T + 704_500)).toMatchObject({
      seq: 7,
      acquiredAtMs: T + 704_000,
    });
  });

  it("the sequence is where the cursor froze, even if no one read it for a while before the pause", () => {
    // Nothing was read after t = 0, then monitoring paused at 5900 ms: the cursor had
    // reached sequence 2, so the resume is sequence 3.
    const cursor = fresh();
    cursor.read(T);
    cursor.pause(T + 5900);
    cursor.resume(T + 9000);
    expect(cursor.read(T + 9000).seq).toBe(3);
  });

  it("pause and resume are idempotent: a second pause keeps the first freeze, a second resume does not open another segment", () => {
    const cursor = fresh();
    cursor.pause(T + 5000);
    cursor.pause(T + 9000); // already paused: no effect
    cursor.resume(T + 20_000);
    cursor.resume(T + 21_000); // already running: no effect
    expect(cursor.read(T + 21_000)).toMatchObject({
      seq: 3,
      acquiredAtMs: T + 20_000,
    });
  });

  it("a reset starts a new session from sequence 0 at its own time, wherever the old one had got to", () => {
    const cursor = fresh();
    cursor.read(T + 30_000);
    cursor.pause(T + 30_000);
    cursor.reset(T + 90_000);
    expect(cursor.read(T + 90_000)).toMatchObject({
      seq: 0,
      acquiredAtMs: T + 90_000,
    });
    expect(cursor.read(T + 92_000)).toMatchObject({
      seq: 1,
      acquiredAtMs: T + 92_000,
    });
  });

  it("a resume with no session behind it behaves as the start of one (sequence 0)", () => {
    const cursor = createPreparedTelemetryCursor(ROWS);
    cursor.resume(T);
    expect(cursor.read(T)).toMatchObject({ seq: 0, acquiredAtMs: T });
  });

  it("a clock that steps backwards never moves the sequence back", () => {
    const cursor = fresh();
    expect(cursor.read(T + 4000).seq).toBe(2);
    expect(cursor.read(T + 1000)).toMatchObject({
      seq: 2,
      acquiredAtMs: T + 4000,
    });
    cursor.pause(T + 500);
    cursor.resume(T + 100_000);
    expect(cursor.read(T + 100_000).seq).toBe(3);
  });
});

describe("the Live telemetry cursor on the real prepared rows", () => {
  const T = 1_800_000_000_000;
  const cursor = () => {
    const c = createPreparedTelemetryCursor();
    c.reset(T);
    return c;
  };

  it("sequence n reads telemetry.csv row n + 1, one row per 2000 ms", () => {
    const c = cursor();
    const first = c.read(T);
    expect(first.seq).toBe(0);
    expect(first.features).toEqual(
      PREPARED_RAW_TELEMETRY[0].telemetry_features,
    );
    const stillFirst = c.read(T + 1999);
    expect(stillFirst.seq).toBe(0);
    expect(stillFirst.features).toEqual(
      PREPARED_RAW_TELEMETRY[0].telemetry_features,
    );
    const second = c.read(T + 2000);
    expect(second.seq).toBe(1);
    expect(second.features).toEqual(
      PREPARED_RAW_TELEMETRY[1].telemetry_features,
    );
  });

  it("rows 14 and 17 are still read: they carry no telemetry, and their sequence numbers still count", () => {
    const c = cursor();
    // Row 14 starts at 26 s (sequence 13), row 17 at 32 s (sequence 16).
    expect(c.read(T + 25_999)).toMatchObject({ seq: 12 });
    expect(c.read(T + 25_999).features).not.toBeNull();
    expect(c.read(T + 26_000)).toMatchObject({ seq: 13, features: null });
    expect(c.read(T + 27_999)).toMatchObject({ seq: 13, features: null });
    expect(c.read(T + 28_000).features).not.toBeNull();
    expect(c.read(T + 32_000)).toMatchObject({ seq: 16, features: null });
  });

  it("wraps its rows after the 25th (50 s) while the sequence goes on: 25, 26 ... and row 14 again at sequence 38", () => {
    const c = cursor();
    expect(c.read(T + 50_000)).toMatchObject({
      seq: 25,
      acquiredAtMs: T + 50_000,
    });
    expect(c.read(T + 50_000).features).toEqual(
      PREPARED_RAW_TELEMETRY[0].telemetry_features,
    );
    expect(c.read(T + 76_000)).toMatchObject({ seq: 38, features: null });
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
      /telemetry:\s*createPreparedTelemetryCursor\(\s*\)/,
    );
  });

  // The hook only NAMES the cursor (`telemetry: createPreparedTelemetryCursor()`); the
  // function that actually reads the rows lives in preparedSessionInput.ts, the same module
  // that defines PREPARED_SESSION_WINDOWS. Scanning the hook and the loop therefore
  // cannot see a cursor that has quietly been pointed back at the replay table, and
  // the two tables hold identical telemetry values, so no content test can either.
  // So the guard reads the cursor's own source.
  describe("the cursor the hook injects (createPreparedTelemetryCursor)", () => {
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
      "export const createPreparedTelemetryCursor",
    );

    it("the extracted statement is the whole cursor (so the checks below cannot pass on a truncated slice)", () => {
      expect(cursor).toMatch(
        /Math\.floor\(\s*\(nowMs - baseMs\) \/ PREPARED_TELEMETRY_PERIOD_MS/,
      );
      expect(cursor).toMatch(/rows\[seq % rows\.length\]\.telemetry_features/);
      expect(cursor).toMatch(/\};$/);
    });

    it("the period it steps by is the CSV's own 2000 ms", () => {
      expect(strip(preparedSessionInputSource)).toMatch(
        /export const PREPARED_TELEMETRY_PERIOD_MS = 2000;/,
      );
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
