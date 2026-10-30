/**
 * The plain-words tooltip behind each contract name (review R23): one copy for the banner,
 * Live Monitor, Signal Inspector, Risk Trends and Explanation. Each says what the values
 * mean, not only which ones exist; the DominantEvidence and SystemHealth wording follows
 * ai/src/evidence.ts and docs/fyp2/10_SYSTEM_PARAMETERS_EXPLAINED.zh.md.
 */
export const CONTRACT_TOOLTIP = {
  RiskLevel: "Fused risk level: Low, Medium or High.",
  DominantEvidence:
    "What the assessment rests on: Vision-dominant or Telemetry-dominant when one branch is clearly higher, Combined evidence when both are close, Partial evidence when only one branch is available, Low observed risk when RiskScore is below the low threshold.",
  AlertSeverity: "Alert state: NORMAL, CAUTION or HIGH_ALERT.",
  SystemHealth:
    "Input availability: FULL means both inputs are fresh, DEGRADED means one input is missing or expired, UNAVAILABLE means there is no current assessment. It does not measure accuracy.",
} as const;
