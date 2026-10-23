import { AlertTriangle, CheckCircle2, WifiOff } from "lucide-react";
import { branchExpiry, getDisplayState } from "../../../ai/src/availability";
import type { RiskUpdate } from "../types";
import { alertBannerClass } from "../utils/display";
import { formatBranchPercent, formatRiskScore } from "../utils/format";
import { Pill } from "./Pill";

interface AlertBannerProps {
  latest: RiskUpdate;
  stale?: boolean;
}

export function AlertBanner({ latest, stale = false }: AlertBannerProps) {
  // Three states, not two: `unavailable` is a property of the record (it has no
  // assessment); `stale` is a judgement about the record's AGE. An unavailable
  // record wins - there is no assessment to call stale.
  const state = getDisplayState(latest, { stale });

  if (state === "unavailable") {
    return (
      <section className={alertBannerClass(latest, stale)}>
        <WifiOff size={22} />
        <div>
          <strong>No assessment for the latest window</strong>
          <span>
            Neither input branch contributed usable evidence, so no RiskScore,
            RiskLevel or alert is reported for it.
          </span>
        </div>
        <div className="banner-pills">
          <span className="badge-field">
            <span>System health</span>
            <Pill label={latest.SystemHealth} tone={latest.SystemHealth} />
          </span>
        </div>
      </section>
    );
  }

  if (state === "stale") {
    return (
      <section className={alertBannerClass(latest, stale)}>
        <WifiOff size={22} />
        <div>
          <strong>No current assessment</strong>
          <span>Last result is historical; waiting for fresh evidence.</span>
        </div>
      </section>
    );
  }

  // An available record carries a non-null severity; if a malformed one does
  // not, the pill and the class both resolve to the explicit unavailable tone.
  const severity = latest.AlertSeverity;
  const Icon = severity === "NORMAL" ? CheckCircle2 : AlertTriangle;

  return (
    <section className={alertBannerClass(latest, stale)}>
      <Icon size={22} />
      <div>
        <strong>Current Monitoring Status</strong>
        <span>
          RiskScore: {formatRiskScore(latest.RiskScore)} | Visual distraction:{" "}
          {formatBranchPercent(
            latest.P_distraction,
            latest.modality_freshness.vision,
            branchExpiry(latest, "vision").expired,
          )}{" "}
          | Telemetry non-safe:{" "}
          {formatBranchPercent(
            latest.P_telemetry_anomaly,
            latest.modality_freshness.telemetry,
            branchExpiry(latest, "telemetry").expired,
          )}
        </span>
      </div>
      <div className="banner-pills">
        <span className="badge-field">
          <span>Alert</span>
          <Pill label={severity} tone={severity} />
        </span>
        <span className="badge-field">
          <span>System health</span>
          <Pill label={latest.SystemHealth} tone={latest.SystemHealth} />
        </span>
      </div>
    </section>
  );
}
