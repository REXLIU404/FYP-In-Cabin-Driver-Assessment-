import { AlertTriangle, CheckCircle2, WifiOff } from "lucide-react";
import type { RiskUpdate } from "../types";
import { formatPercent, formatRiskScore } from "../utils/format";
import { Pill } from "./Pill";

interface AlertBannerProps {
  latest: RiskUpdate;
  stale?: boolean;
}

export function AlertBanner({ latest, stale = false }: AlertBannerProps) {
  if (stale || latest.SystemHealth === "UNAVAILABLE") {
    return (
      <section className="alert-banner runtime-warning">
        <WifiOff size={22} />
        <div>
          <strong>No current assessment</strong>
          <span>
            {stale
              ? "Last result is historical; waiting for fresh evidence."
              : "Both input branches are missing."}
          </span>
        </div>
      </section>
    );
  }
  const Icon = latest.AlertSeverity === "NORMAL" ? CheckCircle2 : AlertTriangle;

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
