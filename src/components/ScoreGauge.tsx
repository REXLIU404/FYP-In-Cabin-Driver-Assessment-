import { formatRiskScore } from "../utils/format";

interface ScoreGaugeProps {
  score: number;
  label: string;
}

const getScoreColor = (score: number) => {
  if (score >= 60) {
    return "#dc2626";
  }

  if (score >= 30) {
    return "#d97706";
  }

  return "#15803d";
};

export function ScoreGauge({ score, label }: ScoreGaugeProps) {
  const degrees = (Math.max(0, Math.min(100, score)) / 100) * 360;
  const color = getScoreColor(score);

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
