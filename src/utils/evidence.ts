import type { DominantEvidence, RiskUpdate, SystemHealth } from "../types";

export const EVIDENCE_GAP = 0.15;

export const evidenceTypes: DominantEvidence[] = [
  "Vision-dominant",
  "Telemetry-dominant",
  "Combined evidence",
  "Partial evidence",
  "Low observed risk",
];

interface EvidenceInputs {
  pDistraction: number;
  pTelemetry: number;
  riskScore: number;
  systemHealth: SystemHealth;
  thresholdLow: number;
  gap?: number;
}

export const determineEvidenceType = ({
  pDistraction,
  pTelemetry,
  riskScore,
  systemHealth,
  thresholdLow,
  gap = EVIDENCE_GAP,
}: EvidenceInputs): DominantEvidence => {
  if (systemHealth !== "FULL") return "Partial evidence";
  if (riskScore < thresholdLow) return "Low observed risk";
  if (Math.abs(pDistraction - pTelemetry) < gap) return "Combined evidence";
  return pDistraction > pTelemetry
    ? "Vision-dominant"
    : "Telemetry-dominant";
};

export const getEvidenceType = (
  record: RiskUpdate,
  thresholdLow: number,
  gap = EVIDENCE_GAP,
) =>
  determineEvidenceType({
    pDistraction: record.P_distraction,
    pTelemetry: record.P_telemetry_anomaly,
    riskScore: record.RiskScore,
    systemHealth: record.SystemHealth,
    thresholdLow,
    gap,
  });

export const formatEvidenceType = (evidenceType: DominantEvidence) =>
  evidenceType.toUpperCase();

export const getRelativeEvidence = (record: RiskUpdate) => {
  if (record.SystemHealth !== "FULL") return "Partial input availability";

  const difference = record.P_distraction - record.P_telemetry_anomaly;

  if (Math.abs(difference) < 0.03) return "Vision and telemetry balanced";
  return difference > 0
    ? "Vision stronger than telemetry"
    : "Telemetry stronger than vision";
};

export const getActiveInputSummary = (record: RiskUpdate) => {
  const vision = record.modality_freshness.vision;
  const telemetry = record.modality_freshness.telemetry;

  if (vision === "fresh" && telemetry === "fresh") {
    return "Vision + Telemetry available";
  }

  return `Vision ${vision} / Telemetry ${telemetry}`;
};

export const getMatchedEvidenceRule = (
  evidenceType: DominantEvidence,
  thresholdLow: number,
  gap = EVIDENCE_GAP,
) => {
  if (evidenceType === "Low observed risk") {
    return {
      label: "Low observed risk",
      condition: `RiskScore < ${thresholdLow} / 100`,
    };
  }

  if (evidenceType === "Vision-dominant") {
    return {
      label: "Vision-dominant",
      condition: `P_distraction - P_telemetry_anomaly >= ${gap.toFixed(2)}`,
    };
  }

  if (evidenceType === "Telemetry-dominant") {
    return {
      label: "Telemetry-dominant",
      condition: `P_telemetry_anomaly - P_distraction >= ${gap.toFixed(2)}`,
    };
  }

  if (evidenceType === "Combined evidence") {
    return {
      label: "Combined evidence",
      condition: `abs(P_distraction - P_telemetry_anomaly) < ${gap.toFixed(
        2,
      )}`,
    };
  }

  return {
    label: "Partial evidence",
    condition: "one modality is stale or missing",
  };
};
