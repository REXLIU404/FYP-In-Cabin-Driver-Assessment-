import { describe, expect, it } from "vitest";

import { buildRiskUpdate, DEFAULT_CONFIG } from "../../../ai/src/riskLogic";
import missingCasesCsv from "../../../ai/prototype-data/prepared_sessions/session_001/missing_cases.csv?raw";
import telemetryCsv from "../../../ai/prototype-data/prepared_sessions/session_001/telemetry.csv?raw";
import type { RiskUpdate } from "../types";
import { PREPARED_SESSION_WINDOWS } from "./preparedSessionInput";

// missing_cases.csv is the documented per-window expected-outcome matrix for the
// prepared replay. Nothing used to read it, which is how it went stale: Task 2
// made "no evidence" null instead of Low, and Task 5 changed the replay numbers
// (EMA re-seeding, half-up rounding). This test makes the CSV the thing under
// test. Every expected value is a cell read from the file; every actual value
// comes from the real replay pipeline, folded exactly as the app and
// preparedSessionInput.test.ts fold it. The expectations are never generated
// from pipeline output, so a changed replay number fails here until the CSV row
// is corrected on purpose.
//
// W16 ("Telemetry stale" - the label is the input scenario, kept as written) has
// telemetry_age_s 4 > 3. Ruling A (D13) makes that telemetry EXPIRED: it scores as
// missing, so the window is the vision branch alone (P_distraction 0.6 -> 60.0 /
// High / DEGRADED / Partial evidence). It was 62.5 while the runtime still weighted
// a stale branch at 0.45. The expectation lives in the CSV, not here.
const records: RiskUpdate[] = [];
let previous: RiskUpdate | undefined;
PREPARED_SESSION_WINDOWS.forEach((window, index) => {
  const record = buildRiskUpdate(
    window,
    "session_001",
    DEFAULT_CONFIG,
    previous,
    index + 1,
  );
  records.push(record);
  previous = record;
});

// Plain comma split: the matrix has no quoted cells. A cell that ever needs a
// comma would shift every later column, and the cell-count test below catches it.
const lines = missingCasesCsv.split(/\r?\n/).filter((line) => line !== "");
const header = lines[0].split(",");
const cellRows = lines.slice(1).map((line) => line.split(","));
const matrix = cellRows.map(
  (cells): Record<string, string> =>
    Object.fromEntries(header.map((name, index) => [name, cells[index] ?? ""])),
);

// The unavailable representation shared with the R1 export contract: empty
// cell for the nullable fields, "UNAVAILABLE" health, lowercase false.
const nullIfEmpty = (cell: string) => (cell === "" ? null : cell);

describe("missing_cases.csv layout", () => {
  it("keeps the original columns in order and appends the two new ones", () => {
    expect(header).toEqual([
      "case",
      "window_id",
      "vision_available",
      "telemetry_available",
      "telemetry_age_s",
      "expected_risk_level",
      "expected_system_health",
      "expected_dominant_evidence",
      "expected_risk_score",
      "expected_assessment_available",
    ]);
  });

  it("has one cell per column on every line", () => {
    expect(cellRows.filter((cells) => cells.length !== header.length)).toEqual(
      [],
    );
  });

  it("covers exactly the nine documented windows", () => {
    expect(matrix.map((row) => Number(row.window_id))).toEqual([
      1, 7, 10, 14, 15, 16, 17, 19, 25,
    ]);
  });

  it("writes the score with one decimal place, or as an empty cell", () => {
    expect(
      matrix
        .map((row) => row.expected_risk_score)
        .filter((cell) => !/^(\d+\.\d)?$/.test(cell)),
    ).toEqual([]);
  });
});

// The matrix's input columns restate telemetry.csv. Checked here as well, so a
// change to the replay input cannot leave the matrix describing a row that no
// longer exists (e.g. W16's age moving from 4 to 9 still scores 62.5).
const telemetryLines = telemetryCsv
  .split(/\r?\n/)
  .filter((line) => line !== "");
const telemetryHeader = telemetryLines[0].split(",");
const telemetryRows = telemetryLines
  .slice(1)
  .map(
    (line): Record<string, string> =>
      Object.fromEntries(
        line.split(",").map((cell, index) => [telemetryHeader[index], cell]),
      ),
  );
const INPUT_COLUMNS = [
  "vision_available",
  "telemetry_available",
  "telemetry_age_s",
] as const;

describe("missing_cases.csv input columns equal telemetry.csv", () => {
  it.each(matrix.map((row) => [row.window_id, row] as const))(
    "W%s",
    (windowId, row) => {
      const source = telemetryRows.find((r) => r.window_id === windowId);
      if (source === undefined) {
        throw new Error(`window ${windowId} is not in telemetry.csv`);
      }
      const pick = (r: Record<string, string>) =>
        Object.fromEntries(INPUT_COLUMNS.map((name) => [name, r[name]]));
      expect(pick(row)).toEqual(pick(source));
    },
  );
});

describe("missing_cases.csv expectations equal the real replay output", () => {
  it.each(matrix.map((row) => [row.window_id, row.case, row] as const))(
    "W%s (%s)",
    (_windowId, _caseName, row) => {
      const record = records.find((r) => r.window_id === Number(row.window_id));
      if (record === undefined) {
        throw new Error(`window ${row.window_id} is not in the replay`);
      }
      // A boolean is read only from its exact spelling; anything else is a bad cell.
      expect(["true", "false"]).toContain(row.expected_assessment_available);

      expect({
        RiskScore: record.RiskScore,
        RiskLevel: record.RiskLevel,
        SystemHealth: record.SystemHealth,
        DominantEvidence: record.DominantEvidence,
        assessment_available: record.assessment_available,
      }).toEqual({
        RiskScore:
          row.expected_risk_score === ""
            ? null
            : Number(row.expected_risk_score),
        RiskLevel: nullIfEmpty(row.expected_risk_level),
        SystemHealth: row.expected_system_health,
        DominantEvidence: nullIfEmpty(row.expected_dominant_evidence),
        assessment_available: row.expected_assessment_available === "true",
      });
    },
  );
});
