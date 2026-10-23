import type { BranchExpiry } from "../../../ai/src/availability";
import type { FreshnessStatus } from "../types";
import { resolveBranchPill } from "../utils/display";
import { Pill } from "./Pill";

interface BranchStatusPillProps {
  status: FreshnessStatus;
  expiry: BranchExpiry;
}

/**
 * One branch's freshness as a pill. An EXPIRED branch (ruling A, D13) reads
 * "expired (N s)" in its own tone, so it no longer looks like a branch that never
 * sent anything ("missing"); every other status is shown as stored.
 */
export function BranchStatusPill({ status, expiry }: BranchStatusPillProps) {
  const { label, tone } = resolveBranchPill(status, expiry);
  return <Pill label={label} tone={tone} />;
}
