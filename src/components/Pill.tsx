import type {
  AlertSeverity,
  FreshnessStatus,
  RiskLevel,
  SystemHealth,
} from "../types";

type PillTone =
  | AlertSeverity
  | RiskLevel
  | SystemHealth
  | FreshnessStatus
  | "flagged"
  | "neutral";

interface PillProps {
  label: string;
  tone?: PillTone;
}

export function Pill({ label, tone = "neutral" }: PillProps) {
  return <span className={`pill pill--${tone}`}>{label}</span>;
}
