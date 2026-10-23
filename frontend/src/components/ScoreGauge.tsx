import {
  UNAVAILABLE_LABEL,
  formatFixed,
  formatRiskScore,
} from "../utils/format";

interface ScoreGaugeProps {
  /** `null` is an unassessed window: the gauge renders empty, never at 0. */
  score: number | null;
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
  const degrees =
    score === null ? 0 : (Math.max(0, Math.min(100, score)) / 100) * 360;
  const color =
    score === null
      ? "#94a3b8"
      : getScoreColor(score, thresholdLow, thresholdHigh);

  return (
    <div
      className={
        score === null ? "risk-gauge risk-gauge--unavailable" : "risk-gauge"
      }
      aria-label={`${label}: ${formatRiskScore(score)}`}
    >
      <div
        className="risk-gauge__ring"
        style={{
          background: `conic-gradient(${color} ${degrees}deg, #e5e7eb ${degrees}deg)`,
        }}
      >
        <div className="risk-gauge__value">
          <span>{score === null ? "—" : formatFixed(score, 1)}</span>
          <small>{score === null ? UNAVAILABLE_LABEL : "/100"}</small>
        </div>
      </div>
      <div className="risk-gauge__label">{label}</div>
    </div>
  );
}
