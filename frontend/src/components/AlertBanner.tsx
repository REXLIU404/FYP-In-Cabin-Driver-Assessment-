import { AlertTriangle, CheckCircle2, WifiOff } from "lucide-react";
import type { RiskUpdate } from "../types";
import { formatPercent, formatRiskScore } from "../utils/format";
import { Pill } from "./Pill";

interface AlertBannerProps {
  latest: RiskUpdate;
}

export function AlertBanner({ latest }: AlertBannerProps) {
  const Icon =
    latest.SystemHealth === "UNAVAILABLE"
      ? WifiOff
      : latest.AlertSeverity === "NORMAL"
        ? CheckCircle2
        : AlertTriangle;

  return (
    <section className={`alert-banner alert-banner--${latest.AlertSeverity}`}>
      <Icon size={22} />
      <div>
        <strong>Current Monitoring Status</strong>
        <span>
          RiskScore: {formatRiskScore(latest.RiskScore)} | Visual distraction:{" "}
          {formatPercent(latest.P_distraction)} | Telemetry non-safe:{" "}
          {formatPercent(latest.P_telemetry_anomaly)}
        </span>
      </div>
      <div className="banner-pills">
        <Pill label={latest.AlertSeverity} tone={latest.AlertSeverity} />
        <Pill label={latest.SystemHealth} tone={latest.SystemHealth} />
      </div>
    </section>
  );
}
