import type { DominantEvidence, RiskUpdate } from "../types";

interface ExportOptions {
  includeEvidenceInterpretation: boolean;
}

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

  return top?.label ?? "unavailable";
};

const getTelemetryProbability = (record: RiskUpdate, label: string) =>
  record.telemetry_behavior_classes.find((item) => item.label === label)
    ?.probability ?? 0;

const getTopTelemetryBehavior = (record: RiskUpdate) =>
  [...record.telemetry_behavior_classes].sort(
    (a, b) => b.probability - a.probability,
  )[0]?.label ?? "unavailable";

const getTopTelemetryFeatureContribution = (record: RiskUpdate) =>
  [...(record.telemetry_feature_contributions ?? [])].sort(
    (a, b) => Math.abs(b.contribution) - Math.abs(a.contribution),
  )[0];

const baseExportRecord = (record: RiskUpdate) => ({
  window_id: record.window_id,
  risk_score: record.RiskScore,
  risk_level: record.RiskLevel,
});

const evidenceExportRecord = (record: RiskUpdate) => ({
  ...baseExportRecord(record),
  p_distraction: record.P_distraction,
  p_telemetry_anomaly: record.P_telemetry_anomaly,
  dominant_evidence: dominantEvidenceLabel[record.DominantEvidence],
  top_visual_class: getTopVisualClass(record),
  top_telemetry_behavior: getTopTelemetryBehavior(record),
  top_telemetry_feature:
    getTopTelemetryFeatureContribution(record)?.feature ?? "unavailable",
  top_telemetry_feature_contribution:
    getTopTelemetryFeatureContribution(record)?.contribution ?? "",
  p_telemetry_safe: getTelemetryProbability(record, "Safe"),
  p_telemetry_aggressive: getTelemetryProbability(record, "Aggressive"),
  p_telemetry_distracted: getTelemetryProbability(record, "Distracted"),
  latency_ms: record.latency_ms,
});

const formatRecords = (
  records: RiskUpdate[],
  { includeEvidenceInterpretation }: ExportOptions,
) =>
  includeEvidenceInterpretation
    ? records.map(evidenceExportRecord)
    : records.map(baseExportRecord);

export const exportSessionLogJSON = (
  sessionId: string,
  records: RiskUpdate[],
  includeEvidenceInterpretation: boolean,
) => {
  downloadText(
    `${sessionId}_session_log.json`,
    JSON.stringify(
      {
        session_id: sessionId,
        record_count: records.length,
        evidence_interpretation_enabled: includeEvidenceInterpretation,
        records: formatRecords(records, { includeEvidenceInterpretation }),
      },
      null,
      2,
    ),
    "application/json",
  );
};

const csvCell = (value: string | number | boolean) => {
  const text = String(value);
  return /[",\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
};

export const exportSessionLogCSV = (
  sessionId: string,
  records: RiskUpdate[],
  includeEvidenceInterpretation: boolean,
) => {
  const formatted = formatRecords(records, { includeEvidenceInterpretation });
  const header = includeEvidenceInterpretation
    ? [
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
      ]
    : ["window_id", "risk_score", "risk_level"];
  const rows = formatted.map((record) =>
    header
      .map((key) => csvCell(record[key as keyof typeof record] ?? ""))
      .join(","),
  );

  downloadText(
    `${sessionId}_session_log.csv`,
    [header.join(","), ...rows].join("\n"),
    "text/csv",
  );
};
