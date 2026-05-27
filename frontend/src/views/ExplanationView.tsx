import { BarChart3, FileText, Scale } from "lucide-react";
import { DistributionChart } from "../components/DistributionChart";
import { Pill } from "../components/Pill";
import type { AppConfig, DominantEvidence, RiskUpdate } from "../types";
import {
  formatContribution,
  formatPercent,
  formatProbability,
  formatRiskScore,
} from "../utils/format";
import {
  evidenceTypes,
  formatEvidenceType,
  getActiveInputSummary,
  getEvidenceType,
  getMatchedEvidenceRule,
  getRelativeEvidence,
} from "../../../ai/src/evidence";
import { computeRiskContributions } from "../../../ai/src/riskLogic";

interface ExplanationViewProps {
  selectedRecord: RiskUpdate;
  history: RiskUpdate[];
  config: AppConfig;
}

const evidenceChartLabels: Record<DominantEvidence, string> = {
  "Vision-dominant": "Vision",
  "Telemetry-dominant": "Telemetry",
  "Combined evidence": "Combined",
  "Partial evidence": "Partial",
  "Low observed risk": "Low risk",
};

const visualLabelMap: Record<string, string> = {
  safe_driving: "Safe Driving",
  normal_driving: "Safe Driving",
  texting_right: "Texting (Right)",
  phone_right: "Phone Call (Right)",
  texting_left: "Texting (Left)",
  phone_left: "Phone Call (Left)",
  operating_radio: "Operating Radio",
  drinking: "Drinking",
  reaching_behind: "Reaching Behind",
  hair_makeup: "Hair and Makeup",
  talking_to_passenger: "Talking to Passenger",
};

const telemetryLabelMap: Record<string, string> = {
  lane_deviation: "Lane Offset Deviation",
  brake_usage: "Brake Pressure Anomaly",
  acceleration: "Excessive Acceleration",
  steering_angle: "Erratic Steering",
};

const titleCaseToken = (value: string) =>
  value
    .toLowerCase()
    .split("_")
    .map((token) => token.charAt(0).toUpperCase() + token.slice(1))
    .join(" ");

const getTopVisualCue = (record: RiskUpdate) => {
  const visualCues = record.visual_top_classes.filter(
    (item) => !["safe_driving", "normal_driving"].includes(item.label),
  );
  const candidates =
    visualCues.length > 0 ? visualCues : record.visual_top_classes;
  return [...candidates].sort((a, b) => b.probability - a.probability)[0];
};

const getTelemetrySignals = (record: RiskUpdate) => {
  const telemetry = record.telemetry_features;

  if (!telemetry) {
    return [];
  }

  return [
    { label: "lane_deviation", value: telemetry.lane_deviation },
    { label: "brake_usage", value: telemetry.brake_usage },
    {
      label: "acceleration",
      value: Math.min(1, telemetry.acceleration / 3),
    },
    {
      label: "steering_angle",
      value: Math.min(1, Math.abs(telemetry.steering_angle) / 18),
    },
  ];
};

export function ExplanationView({
  selectedRecord,
  history,
  config,
}: ExplanationViewProps) {
  const contributions = computeRiskContributions(
    selectedRecord.P_distraction,
    selectedRecord.P_telemetry_anomaly,
    config.weightVision,
    config.weightTelemetry,
    selectedRecord.modality_freshness.vision,
    selectedRecord.modality_freshness.telemetry,
  );
  const visualCue = getTopVisualCue(selectedRecord);
  const telemetrySignals = getTelemetrySignals(selectedRecord);
  const telemetryCue = [...telemetrySignals].sort(
    (a, b) => b.value - a.value,
  )[0];
  const evidenceType = getEvidenceType(selectedRecord, config.thresholdLow);
  const matchedRule = getMatchedEvidenceRule(evidenceType, config.thresholdLow);
  const relativeEvidence = getRelativeEvidence(selectedRecord);
  const activeInputs = getActiveInputSummary(selectedRecord);
  const evidenceDistribution = evidenceTypes.map((type) => ({
    label: evidenceChartLabels[type],
    count: history.filter(
      (record) => getEvidenceType(record, config.thresholdLow) === type,
    ).length,
  }));
  const formatWeight = (weight: number) => Number(weight.toFixed(2)).toString();

  return (
    <div className="page-grid page-grid--explanation">
      <div className="explanation-main-stack">
        <section className="panel explanation-summary">
          <div className="section-header">
            <div>
              <p className="eyebrow">Explanation</p>
              <h2>Current Window Explanation</h2>
            </div>
            <FileText size={20} />
          </div>

          <div className="evidence-type-block">
            <span>Dominant Risk Factor</span>
            <strong>{formatEvidenceType(evidenceType)}</strong>
            <small>Relative Modality Split: {relativeEvidence}</small>
          </div>

          <div className="summary-metric-grid">
            <div>
              <span>Driver Inattention</span>
              <strong>{formatProbability(selectedRecord.P_distraction)}</strong>
            </div>
            <div>
              <span>Vehicle Anomaly</span>
              <strong>
                {formatProbability(selectedRecord.P_telemetry_anomaly)}
              </strong>
            </div>
            <div>
              <span>Overall Risk Score</span>
              <strong>{formatRiskScore(selectedRecord.RiskScore)}</strong>
            </div>
            <div>
              <span>Safety Risk Level</span>
              <Pill
                label={selectedRecord.RiskLevel}
                tone={selectedRecord.RiskLevel}
              />
            </div>
            <div>
              <span>Warning Status</span>
              <Pill
                label={titleCaseToken(selectedRecord.AlertSeverity)}
                tone={selectedRecord.AlertSeverity}
              />
            </div>
            <div>
              <span>Sensor Integrity</span>
              <Pill
                label={titleCaseToken(selectedRecord.SystemHealth)}
                tone={selectedRecord.SystemHealth}
              />
            </div>
          </div>
        </section>

        <section className="panel evidence-card evidence-card--vision">
          <div className="section-header">
            <div>
              <p className="eyebrow">Vision Evidence Card</p>
              <h2>Vision Evidence</h2>
            </div>
          </div>

          <div className="evidence-metrics">
            <div>
              <span>Driver Inattention</span>
              <strong>
                {formatProbability(selectedRecord.P_distraction)}
                <small>{formatPercent(selectedRecord.P_distraction)}</small>
              </strong>
            </div>
            <div>
              <span>Primary Distraction Cue</span>
              <strong>
                {visualCue ? (visualLabelMap[visualCue.label] ?? visualCue.label) : "unavailable"}
                {visualCue ? (
                  <small>{formatPercent(visualCue.probability)}</small>
                ) : null}
              </strong>
            </div>
            <div>
              <span>Camera Status</span>
              <Pill
                label={selectedRecord.modality_freshness.vision}
                tone={selectedRecord.modality_freshness.vision}
              />
            </div>
            <div>
              <span>Score Contribution</span>
              <strong>{formatContribution(contributions.vision)}</strong>
            </div>
          </div>
        </section>

        <section className="panel contribution-panel">
          <div className="section-header">
            <div>
              <p className="eyebrow">Risk Score Synthesis</p>
              <h2>Weighted contribution from each branch</h2>
            </div>
          </div>

          <div className="contribution-formula">
            Risk Score = ({formatWeight(config.weightVision)} × Inattention) + ({formatWeight(config.weightTelemetry)} × Vehicle Anomaly)
          </div>

          <div
            className="contribution-bar"
            aria-label="Vision and telemetry contribution to RiskScore"
          >
            <div
              className="contribution-bar__vision"
              style={{ width: `${contributions.vision}%` }}
            />
            <div
              className="contribution-bar__telemetry"
              style={{ width: `${contributions.telemetry}%` }}
            />
            <div className="contribution-bar__remainder" />
          </div>

          <div className="contribution-equation">
            <span>Visual Inattention {Math.round(contributions.vision)}</span>
            <strong>+</strong>
            <span>Vehicle Anomaly {Math.round(contributions.telemetry)}</span>
            <strong>=</strong>
            <span>Overall Risk Score {formatRiskScore(selectedRecord.RiskScore)}</span>
          </div>

          <div className="contribution-labels">
            <span>Inattention Contribution: {Math.round(contributions.vision)}</span>
            <span>
              Vehicle Anomaly Contribution: {Math.round(contributions.telemetry)}
            </span>
            <span>
              Total Risk Score: {formatRiskScore(selectedRecord.RiskScore)}
            </span>
          </div>
        </section>
      </div>

      <aside className="explanation-side-stack">
        <section className="panel decision-rule-panel">
          <div className="section-header">
            <div>
              <p className="eyebrow">Decision Rule</p>
              <h2>Matched Evidence Rule</h2>
            </div>
            <Scale size={20} />
          </div>

          <div className="rule-list">
            <div>
              <span>{matchedRule.label}</span>
              <strong>{matchedRule.condition}</strong>
            </div>
            <div>
              <span>Active inputs</span>
              <strong>{activeInputs}</strong>
            </div>
          </div>

          <div className="decision-badges">
            {evidenceTypes.map((type) => (
              <span
                className={`rule-badge ${type === evidenceType ? "is-active" : ""}`}
                key={type}
              >
                {type}
              </span>
            ))}
          </div>
        </section>

        <section className="panel evidence-card evidence-card--telemetry">
          <div className="section-header">
            <div>
              <p className="eyebrow">Telemetry Evidence Card</p>
              <h2>Telemetry Evidence</h2>
            </div>
          </div>

          <div className="evidence-metrics">
            <div>
              <span>Vehicle Anomaly</span>
              <strong>
                {formatProbability(selectedRecord.P_telemetry_anomaly)}
                <small>
                  {formatPercent(selectedRecord.P_telemetry_anomaly)}
                </small>
              </strong>
            </div>
            <div>
              <span>Primary Telemetry Driver</span>
              <strong>
                {telemetryCue ? (telemetryLabelMap[telemetryCue.label] ?? telemetryCue.label) : "unavailable"}
                {telemetryCue ? (
                  <small>{formatPercent(telemetryCue.value)}</small>
                ) : null}
              </strong>
            </div>
            <div>
              <span>Telemetry Status</span>
              <Pill
                label={selectedRecord.modality_freshness.telemetry}
                tone={selectedRecord.modality_freshness.telemetry}
              />
            </div>
            <div>
              <span>Score Contribution</span>
              <strong>{formatContribution(contributions.telemetry)}</strong>
            </div>
          </div>
        </section>

        <section className="panel session-evidence-panel">
          <div className="section-header">
            <div>
              <p className="eyebrow">Session Evidence Distribution</p>
              <h2>Evidence types in current session</h2>
            </div>
            <BarChart3 size={20} />
          </div>
          <DistributionChart data={evidenceDistribution} />
        </section>
      </aside>
    </div>
  );
}
