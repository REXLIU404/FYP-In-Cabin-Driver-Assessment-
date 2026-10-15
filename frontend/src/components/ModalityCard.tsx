import type { BranchExpiry } from "../../../ai/src/availability";
import type { FreshnessStatus } from "../types";
import { formatBranchProbability, formatPercent } from "../utils/format";
import { BranchStatusPill } from "./BranchStatusPill";

interface ModalityCardProps {
  title: string;
  probability: number;
  freshness: FreshnessStatus;
  /** Ruling A (D13): the branch had evidence and it was too old. */
  expiry?: BranchExpiry;
}

const NOT_EXPIRED: BranchExpiry = { expired: false, ageS: null };

export function ModalityCard({
  title,
  probability,
  freshness,
  expiry = NOT_EXPIRED,
}: ModalityCardProps) {
  return (
    <div className="modality-card">
      <span>{title}</span>
      <strong>
        {freshness === "missing" ? "—" : formatPercent(probability)}
      </strong>
      <div>
        <BranchStatusPill status={freshness} expiry={expiry} />
        <small>
          {formatBranchProbability(probability, freshness, expiry.expired)}
        </small>
      </div>
    </div>
  );
}
