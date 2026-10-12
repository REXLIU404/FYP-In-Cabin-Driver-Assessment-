import type { DominantEvidence, RiskUpdate } from "../types";

const downloadText = (filename: string, text: string, mimeType: string) => {
  const blob = new Blob([text], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
};

const dominantEvidenceLabel: Record<DominantEvidence, string> = {
  "Vision-dominant": "vision_dominant",
  "Telemetry-dominant": "telemetry_dominant",
  "Combined evidence": "combined",
  "Partial evidence": "partial",
  "Low observed risk": "low_observed_risk",
};

const getTopVisualClass = (record: RiskUpdate) => {
  const top = [...record.visual_top_classes].sort(
    (a, b) => b.probability - a.probability,
  )[0];

  return top?.label ?? null;
};

// null (not 0) when the class is absent: a window without telemetry has no
// P(Safe), and 0 would read as "certainly not safe".
const getTelemetryProbability = (record: RiskUpdate, label: string) =>
  record.telemetry_behavior_classes.find((item) => item.label === label)
    ?.probability ?? null;

const getTopTelemetryBehavior = (record: RiskUpdate) =>
  [...record.telemetry_behavior_classes].sort(
    (a, b) => b.probability - a.probability,
  )[0]?.label ?? null;

const getTopTelemetryFeatureContribution = (record: RiskUpdate) =>
  [...(record.telemetry_feature_contributions ?? [])].sort(
    (a, b) => Math.abs(b.contribution) - Math.abs(a.contribution),
  )[0];

type Cell = string | number | boolean | null;

// Column order is the export contract. New columns are APPENDED after the
// pre-existing ones so positional readers keep working.
const BASE_COLUMNS = [
  "window_id",
  "risk_score",
  "risk_level",
  "alert_severity",
  "system_health",
  "assessment_available",
] as const;

const EVIDENCE_COLUMNS = [
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
  "alert_severity",
  "system_health",
  "assessment_available",
  "vision_freshness",
  "telemetry_freshness",
] as const;

// The unavailable representation is a cross-stack contract shared with the
// backend export (backend/app/routers/export.py):
//   RiskScore / RiskLevel / DominantEvidence / AlertSeverity -> JSON null, CSV empty cell
//   assessment_available                                     -> lowercase true / false
//   SystemHealth                                             -> "UNAVAILABLE"
// An empty cell is ambiguous on its own (it could also be a missing field), so
// `assessment_available` and `system_health` are in EVERY export, evidence
// interpretation on or off, and always hold a value.
const baseExportRecord = (
  record: RiskUpdate,
): Record<(typeof BASE_COLUMNS)[number], Cell> => ({
  window_id: record.window_id,
  risk_score: record.RiskScore,
  risk_level: record.RiskLevel,
  alert_severity: record.AlertSeverity,
  system_health: record.SystemHealth,
  assessment_available: record.assessment_available,
});

const evidenceExportRecord = (
  record: RiskUpdate,
): Record<(typeof EVIDENCE_COLUMNS)[number], Cell> => ({
  window_id: record.window_id,
  risk_score: record.RiskScore,
  risk_level: record.RiskLevel,
  p_distraction: record.P_distraction,
  p_telemetry_anomaly: record.P_telemetry_anomaly,
  // Always present as a key. `dominantEvidenceLabel[null]` is `undefined`, and
  // JSON.stringify drops an undefined member, which would give an unavailable
  // record a different shape from an available one.
  dominant_evidence:
    record.DominantEvidence == null
      ? null
      : dominantEvidenceLabel[record.DominantEvidence],
  top_visual_class: getTopVisualClass(record),
  top_telemetry_behavior: getTopTelemetryBehavior(record),
  top_telemetry_feature:
    getTopTelemetryFeatureContribution(record)?.feature ?? null,
  top_telemetry_feature_contribution:
    getTopTelemetryFeatureContribution(record)?.contribution ?? null,
  p_telemetry_safe: getTelemetryProbability(record, "Safe"),
  p_telemetry_aggressive: getTelemetryProbability(record, "Aggressive"),
  p_telemetry_distracted: getTelemetryProbability(record, "Distracted"),
  latency_ms: record.latency_ms,
  alert_severity: record.AlertSeverity,
  system_health: record.SystemHealth,
  assessment_available: record.assessment_available,
  // A missing branch carries P = 0.0 in the record; these two columns say when
  // that 0 is not a reading.
  vision_freshness: record.modality_freshness.vision,
  telemetry_freshness: record.modality_freshness.telemetry,
});

const formatRecords = (
  records: RiskUpdate[],
  includeEvidenceInterpretation: boolean,
): { columns: readonly string[]; rows: Array<Record<string, Cell>> } =>
  includeEvidenceInterpretation
    ? { columns: EVIDENCE_COLUMNS, rows: records.map(evidenceExportRecord) }
    : { columns: BASE_COLUMNS, rows: records.map(baseExportRecord) };

export const buildSessionLogJSON = (
  sessionId: string,
  records: RiskUpdate[],
  includeEvidenceInterpretation: boolean,
): string =>
  JSON.stringify(
    {
      session_id: sessionId,
      record_count: records.length,
      evidence_interpretation_enabled: includeEvidenceInterpretation,
      records: formatRecords(records, includeEvidenceInterpretation).rows,
    },
    null,
    2,
  );

// null / undefined -> empty cell; booleans stay lowercase (String(false)).
const csvCell = (value: Cell | undefined) => {
  if (value === null || value === undefined) return "";
  const text = String(value);
  return /[",\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
};

export const buildSessionLogCSV = (
  records: RiskUpdate[],
  includeEvidenceInterpretation: boolean,
): string => {
  const { columns, rows } = formatRecords(
    records,
    includeEvidenceInterpretation,
  );
  return [
    columns.join(","),
    ...rows.map((row) => columns.map((key) => csvCell(row[key])).join(",")),
  ].join("\n");
};

export const exportSessionLogJSON = (
  sessionId: string,
  records: RiskUpdate[],
  includeEvidenceInterpretation: boolean,
) => {
  downloadText(
    `${sessionId}_session_log.json`,
    buildSessionLogJSON(sessionId, records, includeEvidenceInterpretation),
    "application/json",
  );
};

export const exportSessionLogCSV = (
  sessionId: string,
  records: RiskUpdate[],
  includeEvidenceInterpretation: boolean,
) => {
  downloadText(
    `${sessionId}_session_log.csv`,
    buildSessionLogCSV(records, includeEvidenceInterpretation),
    "text/csv",
  );
};
