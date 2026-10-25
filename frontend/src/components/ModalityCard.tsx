import type { BranchExpiry } from "../../../ai/src/availability";
import type { FreshnessStatus } from "../types";
import { formatBranchProbability, formatPercent } from "../utils/format";
import { BranchStatusPill } from "./BranchStatusPill";

interface ModalityCardProps {
  title: string;
  probability: number;
  freshness: FreshnessStatus;
  /**
   * Ruling A (D13): whether the branch had evidence and it was too old. REQUIRED, with
   * no default: an optional prop with a "not expired" default let a caller forget to
   * pass it, and an expired branch then read as "missing" with nothing to catch it.
   */
  expiry: BranchExpiry;
}

export function ModalityCard({
  title,
  probability,
  freshness,
  expiry,
}: ModalityCardProps) {
  // The percent is shown once; the exact probability (or why there is none) is the tooltip.
  // A second "0.50" printed beside "50%" read as a different quantity.
  const exact = formatBranchProbability(probability, freshness, expiry.expired);
  return (
    <div className="modality-card">
      <span>{title}</span>
      <strong title={freshness === "missing" ? exact : `P = ${exact}`}>
        {freshness === "missing" ? "—" : formatPercent(probability)}
      </strong>
      <div>
        <BranchStatusPill status={freshness} expiry={expiry} />
      </div>
    </div>
  );
}
