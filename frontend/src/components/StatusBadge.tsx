import { resolvePill, type PillTone } from "../utils/display";

interface StatusBadgeProps {
  label: string | null;
  tone?: PillTone | null;
}

export function StatusBadge({ label, tone }: StatusBadgeProps) {
  const resolved = resolvePill(label, tone);
  return (
    <span className={`pill pill--${resolved.tone}`}>{resolved.label}</span>
  );
}
