import { resolvePill, type PillTone } from "../utils/display";

interface PillProps {
  /** `null` renders the unavailable label (an unassessed window). */
  label: string | null;
  /** `null` selects the explicit unavailable tone; omitted means neutral. */
  tone?: PillTone | null;
}

export function Pill({ label, tone }: PillProps) {
  const resolved = resolvePill(label, tone);
  return (
    <span className={`pill pill--${resolved.tone}`}>{resolved.label}</span>
  );
}
