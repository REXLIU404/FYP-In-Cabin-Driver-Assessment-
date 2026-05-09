import type {
  AlertSeverity,
  FreshnessStatus,
  RiskLevel,
  SystemHealth,
} from "../types";

type BadgeTone =
  | AlertSeverity
  | RiskLevel
  | SystemHealth
  | FreshnessStatus
  | "flagged"
  | "neutral";

interface StatusBadgeProps {
  label: string;
  tone?: BadgeTone;
}

export function StatusBadge({ label, tone = "neutral" }: StatusBadgeProps) {
  return <span className={`pill pill--${tone}`}>{label}</span>;
}
