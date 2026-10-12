import { describe, expect, it } from "vitest";

import { makeRecord } from "../testing/records";
import { buildSessionLogCSV, buildSessionLogJSON } from "./export";

// Both records come from the real producer. Window 1 is assessed; window 2 has
// neither branch, so its four nullable fields are null.
const available = makeRecord("fresh", "fresh", 1);
const unavailable = makeRecord("missing", "missing", 2);
const log = [available, unavailable];

const parseCsv = (csv: string) => {
  const [header, ...rows] = csv.split("\n").map((line) => line.split(","));
  return {
    header,
    rows: rows.map((cells) =>
      Object.fromEntries(header.map((name, i) => [name, cells[i]])),
    ),
  };
};

describe("UT-EXPORT-01: unavailable windows export as empty cells / null, never 0", () => {
  it("fixture sanity: the second record is a genuine unavailable window", () => {
    expect(available.assessment_available).toBe(true);
    expect(unavailable.assessment_available).toBe(false);
    expect(unavailable.RiskScore).toBeNull();
  });

  describe.each([true, false])(
    "includeEvidenceInterpretation=%s",
    (evidence) => {
      const { header, rows } = parseCsv(buildSessionLogCSV(log, evidence));

      it("the CSV header carries the three disambiguating columns", () => {
        expect(header).toContain("assessment_available");
        expect(header).toContain("system_health");
        expect(header).toContain("alert_severity");
      });

      it("the unavailable row has EMPTY cells for risk_score / risk_level / alert_severity", () => {
        const row = rows[1];
        expect(row.risk_score).toBe("");
        expect(row.risk_level).toBe("");
        expect(row.alert_severity).toBe("");
        expect(row.risk_score).not.toBe("0");
      });

      it("the disambiguating columns on the unavailable row always have a value", () => {
        const row = rows[1];
        expect(row.assessment_available).toBe("false"); // lowercase, as the backend
        expect(row.system_health).toBe("UNAVAILABLE");
      });

      it("the available row keeps its real values and is marked true", () => {
        const row = rows[0];
        expect(row.assessment_available).toBe("true");
        expect(row.system_health).toBe("FULL");
        expect(Number(row.risk_score)).toBe(available.RiskScore);
        expect(row.risk_level).toBe(available.RiskLevel);
        expect(row.alert_severity).toBe(available.AlertSeverity);
      });
    },
  );

  it("evidence mode: dominant_evidence is an empty cell on the unavailable row", () => {
    const { header, rows } = parseCsv(buildSessionLogCSV(log, true));
    expect(header).toContain("dominant_evidence");
    expect(rows[1].dominant_evidence).toBe("");
    expect(rows[0].dominant_evidence).not.toBe("");
  });

  it("evidence mode: a missing branch exports empty probability cells, not a fabricated 0", () => {
    // getTelemetryProbability() used to fall back to 0, which reads as P(Safe)=0
    // ("certainly unsafe") for a window with no telemetry at all.
    const { rows } = parseCsv(buildSessionLogCSV(log, true));
    expect(rows[1].p_telemetry_safe).toBe("");
    expect(rows[1].p_telemetry_aggressive).toBe("");
    expect(rows[1].p_telemetry_distracted).toBe("");
    expect(Number(rows[0].p_telemetry_safe)).toBe(0.7);
  });

  it("evidence mode: a missing branch exports empty cells for the top_* labels, not the literal 'unavailable'", () => {
    // The literal would be indistinguishable from "this window's assessment is
    // unavailable"; the unavailable representation is one rule: empty / null.
    const { rows } = parseCsv(buildSessionLogCSV(log, true));
    expect(rows[1].top_visual_class).toBe("");
    expect(rows[1].top_telemetry_behavior).toBe("");
    expect(rows[1].top_telemetry_feature).toBe("");
    expect(rows[1].top_telemetry_feature_contribution).toBe("");
    const second = JSON.parse(buildSessionLogJSON("s", log, true)).records[1];
    expect(second.top_visual_class).toBeNull();
    expect(second.top_telemetry_behavior).toBeNull();
  });

  it("evidence mode: freshness columns say why a branch probability of 0 is not a reading", () => {
    const { rows } = parseCsv(buildSessionLogCSV(log, true));
    expect(rows[1].vision_freshness).toBe("missing");
    expect(rows[1].telemetry_freshness).toBe("missing");
    expect(rows[0].vision_freshness).toBe("fresh");
  });

  it("JSON: the unavailable record still CONTAINS dominant_evidence (as null) and has the same shape", () => {
    const parsed = JSON.parse(buildSessionLogJSON("s", log, true));
    const [first, second] = parsed.records;
    // undefined would be dropped by JSON.stringify, silently changing the shape.
    expect(
      Object.prototype.hasOwnProperty.call(second, "dominant_evidence"),
    ).toBe(true);
    expect(second.dominant_evidence).toBeNull();
    expect(Object.keys(second).sort()).toEqual(Object.keys(first).sort());
    expect(second.risk_score).toBeNull();
    expect(second.risk_level).toBeNull();
    expect(second.alert_severity).toBeNull();
    expect(second.assessment_available).toBe(false);
    expect(second.system_health).toBe("UNAVAILABLE");
    expect(second.p_telemetry_safe).toBeNull();
    expect(first.assessment_available).toBe(true);
    expect(first.dominant_evidence).not.toBeNull();
  });

  it("the CSV header and the JSON record keys are the same list, in the same order", () => {
    for (const evidence of [true, false]) {
      const { header } = parseCsv(buildSessionLogCSV(log, evidence));
      const [first] = JSON.parse(
        buildSessionLogJSON("s", log, evidence),
      ).records;
      expect(header).toEqual(Object.keys(first));
    }
  });

  it("pre-existing evidence columns keep their positions (new ones are appended)", () => {
    const { header } = parseCsv(buildSessionLogCSV(log, true));
    expect(header.slice(0, 14)).toEqual([
      "window_id",
      "risk_score",
      "risk_level",
      "p_distraction",
      "p_telemetry_anomaly",
      "dominant_evidence",
      "top_visual_class",
      "top_telemetry_behavior",
      "top_telemetry_feature",
      "top_telemetry_feature_contribution",
      "p_telemetry_safe",
      "p_telemetry_aggressive",
      "p_telemetry_distracted",
      "latency_ms",
    ]);
  });

  it("an empty log still produces a header row", () => {
    expect(buildSessionLogCSV([], false).split("\n")).toHaveLength(1);
  });

  it("JSON without evidence interpretation still carries availability and null fields", () => {
    const parsed = JSON.parse(buildSessionLogJSON("s", log, false));
    const second = parsed.records[1];
    expect(second).toMatchObject({
      risk_score: null,
      risk_level: null,
      alert_severity: null,
      assessment_available: false,
      system_health: "UNAVAILABLE",
    });
    expect(parsed.record_count).toBe(2);
  });
});
