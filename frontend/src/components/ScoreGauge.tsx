import { formatRiskScore } from "../utils/format";

interface ScoreGaugeProps {
  score: number;
  label: string;
  thresholdLow?: number;
  thresholdHigh?: number;
}

const getScoreColor = (score: number, low: number, high: number) => {
  if (score >= high) {
    return "#dc2626";
  }

  if (score >= low) {
    return "#d97706";
  }

  return "#15803d";
};

export function ScoreGauge({
  score,
  label,
  thresholdLow = 30,
  thresholdHigh = 60,
}: ScoreGaugeProps) {
  const degrees = (Math.max(0, Math.min(100, score)) / 100) * 360;
  const color = getScoreColor(score, thresholdLow, thresholdHigh);

  return (
    <div
      className="risk-gauge"
      aria-label={`${label}: ${formatRiskScore(score)}`}
    >
      <div
        className="risk-gauge__ring"
        style={{
          background: `conic-gradient(${color} ${degrees}deg, #e5e7eb ${degrees}deg)`,
        }}
      >
        <div className="risk-gauge__value">
          <span>{score.toFixed(1)}</span>
          <small>/100</small>
        </div>
      </div>
      <div className="risk-gauge__label">{label}</div>
    </div>
  );
}
