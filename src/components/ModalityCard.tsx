import type { FreshnessStatus } from "../types";
import { formatPercent } from "../utils/format";
import { Pill } from "./Pill";

interface ModalityCardProps {
  title: string;
  probability: number;
  freshness: FreshnessStatus;
}

export function ModalityCard({
  title,
  probability,
  freshness,
}: ModalityCardProps) {
  return (
    <div className="modality-card">
      <span>{title}</span>
      <strong>{formatPercent(probability)}</strong>
      <div>
        <Pill label={freshness} tone={freshness} />
        <small>{probability.toFixed(2)}</small>
      </div>
    </div>
  );
}
