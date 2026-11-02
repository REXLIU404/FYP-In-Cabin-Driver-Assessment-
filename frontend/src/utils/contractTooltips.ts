/**
 * The plain-words tooltip behind each contract name (review R23): one copy for the banner,
 * Live Monitor, Signal Inspector, Risk Trends and Explanation. Each says what the values
 * mean, not only which ones exist; the DominantEvidence and SystemHealth wording follows
 * ai/src/evidence.ts and docs/fyp2/10_SYSTEM_PARAMETERS_EXPLAINED.zh.md.
 */
export const CONTRACT_TOOLTIP = {
  RiskLevel: "Fused risk level: Low, Medium or High.",
  DominantEvidence:
    "What the assessment rests on, checked in this order: Partial evidence when an input is missing or expired; otherwise Low observed risk when RiskScore is below the low threshold; otherwise Combined evidence when both branches are close, or Vision-dominant / Telemetry-dominant when one branch is clearly higher.",
  AlertSeverity: "Alert state: NORMAL, CAUTION or HIGH_ALERT.",
  SystemHealth:
    "Input availability for this window: FULL means both inputs are fresh, DEGRADED means one input is missing or expired, UNAVAILABLE means the window has no assessment (no usable evidence). It does not measure accuracy.",
} as const;
