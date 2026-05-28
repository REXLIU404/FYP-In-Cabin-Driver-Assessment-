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

const telemetryBehaviorLabelMap: Record<string, string> = {
  Safe: "Safe",
  Aggressive: "Aggressive",
  Distracted: "Distracted",
};

const telemetryFeatureLabelMap: Record<string, string> = {
  speed_kmph: "Speed",
  accel_x: "Longitudinal Accel",
  accel_y: "Lateral Accel",
  brake_pressure: "Brake Pressure",
  steering_angle: "Steering Angle",
  throttle: "Throttle",
  lane_deviation: "Lane Deviation",
  headway_distance: "Headway Distance",
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

const getTopTelemetryBehavior = (record: RiskUpdate) =>
  [...record.telemetry_behavior_classes].sort(
    (a, b) => b.probability - a.probability,
  )[0];

const getTopTelemetryFeatureContributions = (record: RiskUpdate) =>
  [...(record.telemetry_feature_contributions ?? [])]
    .sort((a, b) => Math.abs(b.contribution) - Math.abs(a.contribution))
    .slice(0, 3);

const formatSignedContribution = (value: number) =>
  `${value >= 0 ? "+" : ""}${value.toFixed(2)}`;

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
  const telemetryBehavior = getTopTelemetryBehavior(selectedRecord);
  const telemetryFeatureContributions =
    getTopTelemetryFeatureContributions(selectedRecord);
  const maxTelemetryContribution = Math.max(
    0.01,
    ...telemetryFeatureContributions.map((item) => Math.abs(item.contribution)),
  );
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
            <span>Evidence Type</span>
            <strong>{formatEvidenceType(evidenceType)}</strong>
            <small>Relative Evidence: {relativeEvidence}</small>
          </div>

          <div className="summary-metric-grid">
            <div>
              <span>P_distraction</span>
              <strong>{formatProbability(selectedRecord.P_distraction)}</strong>
            </div>
            <div>
              <span>Telemetry Non-Safe Risk</span>
              <strong>
                {formatProbability(selectedRecord.P_telemetry_anomaly)}
              </strong>
            </div>
            <div>
              <span>RiskScore</span>
              <strong>{formatRiskScore(selectedRecord.RiskScore)}</strong>
            </div>
            <div>
              <span>RiskLevel</span>
              <Pill
                label={selectedRecord.RiskLevel}
                tone={selectedRecord.RiskLevel}
              />
            </div>
            <div>
              <span>AlertStatus</span>
              <Pill
                label={titleCaseToken(selectedRecord.AlertSeverity)}
                tone={selectedRecord.AlertSeverity}
              />
            </div>
            <div>
              <span>SystemHealth</span>
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
              <span>P_distraction</span>
              <strong>
                {formatProbability(selectedRecord.P_distraction)}
                <small>{formatPercent(selectedRecord.P_distraction)}</small>
              </strong>
            </div>
            <div>
              <span>Primary Distraction Cue</span>
              <strong>
                {visualCue
                  ? (visualLabelMap[visualCue.label] ?? visualCue.label)
                  : "unavailable"}
                {visualCue ? (
                  <small>{formatPercent(visualCue.probability)}</small>
                ) : null}
              </strong>
            </div>
            <div>
              <span>Freshness</span>
              <Pill
                label={selectedRecord.modality_freshness.vision}
                tone={selectedRecord.modality_freshness.vision}
              />
            </div>
            <div>
              <span>Contribution</span>
              <strong>{formatContribution(contributions.vision)}</strong>
            </div>
          </div>
        </section>

        <section className="panel contribution-panel">
          <div className="section-header">
            <div>
              <p className="eyebrow">RiskScore Contribution</p>
              <h2>Weighted contribution from each branch</h2>
            </div>
          </div>

          <div className="contribution-formula">
            RiskScore = {formatWeight(config.weightVision)} x Visual Distraction
            + {formatWeight(config.weightTelemetry)} x Telemetry Non-Safe
            Behaviour
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
            <span>Visual Distraction {Math.round(contributions.vision)}</span>
            <strong>+</strong>
            <span>Telemetry Non-Safe {Math.round(contributions.telemetry)}</span>
            <strong>=</strong>
            <span>RiskScore {formatRiskScore(selectedRecord.RiskScore)}</span>
          </div>

          <div className="contribution-labels">
            <span>Vision contribution {Math.round(contributions.vision)}</span>
            <span>
              Telemetry non-safe contribution {Math.round(contributions.telemetry)}
            </span>
            <span>
              Total RiskScore {formatRiskScore(selectedRecord.RiskScore)}
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
              <span>Current Behaviour</span>
              <strong>
                {telemetryBehavior
                  ? (telemetryBehaviorLabelMap[telemetryBehavior.label] ??
                    telemetryBehavior.label)
                  : "unavailable"}
              </strong>
            </div>
            <div>
              <span>Behaviour Score</span>
              <strong>
                {telemetryBehavior
                  ? formatPercent(telemetryBehavior.probability)
                  : "unavailable"}
              </strong>
            </div>
            <div>
              <span>Telemetry Non-Safe Risk</span>
              <strong>
                {formatProbability(selectedRecord.P_telemetry_anomaly)}
                <small>
                  {formatPercent(selectedRecord.P_telemetry_anomaly)}
                </small>
              </strong>
            </div>
            <div className="evidence-metrics__stacked">
              <span>Feature Contribution</span>
              {telemetryFeatureContributions.length > 0 ? (
                <div className="feature-contribution-list">
                  {telemetryFeatureContributions.map((item) => (
                    <div
                      className="feature-contribution-row"
                      key={item.feature}
                    >
                      <div className="feature-contribution-row__meta">
                        <strong>
                          {telemetryFeatureLabelMap[item.feature] ??
                            item.feature}
                        </strong>
                        <span>{formatSignedContribution(item.contribution)}</span>
                      </div>
                      <div className="feature-contribution-row__track">
                        <div
                          className={
                            item.contribution >= 0
                              ? "feature-contribution-row__bar"
                              : "feature-contribution-row__bar feature-contribution-row__bar--negative"
                          }
                          style={{
                            width: `${Math.max(
                              8,
                              (Math.abs(item.contribution) /
                                maxTelemetryContribution) *
                                100,
                            )}%`,
                          }}
                        />
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <strong>unavailable</strong>
              )}
            </div>
            <div>
              <span>Freshness</span>
              <Pill
                label={selectedRecord.modality_freshness.telemetry}
                tone={selectedRecord.modality_freshness.telemetry}
              />
            </div>
            <div>
              <span>Contribution</span>
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
