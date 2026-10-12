import type { FreshnessStatus } from "../types";
import {
  NO_INPUT_LABEL,
  formatPercent,
  formatProbability,
} from "../utils/format";
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
      <strong>
        {freshness === "missing" ? "—" : formatPercent(probability)}
      </strong>
      <div>
        <Pill label={freshness} tone={freshness} />
        <small>
          {freshness === "missing"
            ? NO_INPUT_LABEL
            : formatProbability(probability)}
        </small>
      </div>
    </div>
  );
}
