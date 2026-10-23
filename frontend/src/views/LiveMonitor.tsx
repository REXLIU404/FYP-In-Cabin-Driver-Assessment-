import { Database, Timer, Video } from "lucide-react";
import { BranchStatusPill } from "../components/BranchStatusPill";
import { CameraPreview } from "../components/CameraPreview";
import { ModalityCard } from "../components/ModalityCard";
import { Pill } from "../components/Pill";
import { ScoreGauge } from "../components/ScoreGauge";
import { VehicleDynamics } from "../components/VehicleDynamics";
import { TrendChart } from "../components/TrendChart";
import type { useCameraPreview } from "../hooks/useCameraPreview";
import type { RiskUpdate } from "../types";
import { formatTimestamp } from "../utils/format";
import { buildLiveMonitorModel } from "./liveMonitorModel";

interface LiveMonitorProps {
  latest: RiskUpdate;
  history: RiskUpdate[];
  sessionId: string;
  recordCount: number;
  isMonitoring: boolean;
  camera: ReturnType<typeof useCameraPreview>;
  thresholdLow: number;
  thresholdHigh: number;
  stale?: boolean;
}

export function LiveMonitor({
  latest,
  history,
  sessionId,
  recordCount,
  isMonitoring,
  camera,
  thresholdLow,
  thresholdHigh,
  stale = false,
}: LiveMonitorProps) {
  // Everything below is the record's OWN value (see liveMonitorModel.ts): `stale`
  // describes the record's age and must not rewrite what the record says.
  const {
    displayState,
    systemHealth,
    vision: visionFreshness,
    telemetry: telemetryFreshness,
    visionExpiry,
    telemetryExpiry,
    evidenceType,
  } = buildLiveMonitorModel(latest, stale, thresholdLow);

  return (
    <div className="page-grid page-grid--live">
      <section className="panel panel--wide">
        <div className="section-header">
          <div>
            <p className="eyebrow">Live Monitor</p>
            <h2>Camera preview and current risk output</h2>
          </div>
          <Pill
            label={isMonitoring ? "Monitoring active" : "Monitoring paused"}
          />
        </div>

        <div className="session-strip">
          <div>
            <span>Session</span>
            <strong>{sessionId}</strong>
          </div>
          <div>
            <span>Window</span>
            <strong>{latest.window_id}</strong>
          </div>
          <div>
            <span>Timestamp</span>
            <strong>{formatTimestamp(latest.timestamp)}</strong>
          </div>
          <div>
            <span>Stored records</span>
            <strong>{recordCount}</strong>
          </div>
        </div>

        <div className="live-layout">
          <CameraPreview
            videoRef={camera.videoRef}
            status={camera.status}
            onStart={camera.start}
            onStop={camera.stop}
          />

          <div className="risk-summary">
            {displayState === "unavailable" ? (
              <div className="empty-state">
                <h2>Assessment unavailable</h2>
                <p>
                  This window has no usable evidence, so no RiskScore, RiskLevel
                  or alert is reported for it. Earlier windows remain available
                  in Signal Inspector.
                </p>
              </div>
            ) : displayState === "stale" ? (
              <div className="empty-state">
                <h2>Latest result is stale</h2>
                <p>
                  Waiting for fresh input. The last assessment is historical and
                  is not shown as current; it remains available in Signal
                  Inspector.
                </p>
              </div>
            ) : (
              <>
                <ScoreGauge
                  score={latest.RiskScore}
                  label="RiskScore"
                  thresholdLow={thresholdLow}
                  thresholdHigh={thresholdHigh}
                />
                <div className="risk-badges">
                  <Pill label={latest.RiskLevel} tone={latest.RiskLevel} />
                  <Pill label={evidenceType} />
                  <Pill
                    label={latest.AlertSeverity}
                    tone={latest.AlertSeverity}
                  />
                </div>
              </>
            )}
            <div className="modality-grid">
              <ModalityCard
                title="Visual Distraction"
                probability={latest.P_distraction}
                freshness={visionFreshness}
                expiry={visionExpiry}
              />
              <ModalityCard
                title="Telemetry Non-Safe"
                probability={latest.P_telemetry_anomaly}
                freshness={telemetryFreshness}
                expiry={telemetryExpiry}
              />
            </div>
          </div>
        </div>
      </section>

      <section className="panel">
        <div className="section-header">
          <div>
            <p className="eyebrow">Vehicle Signals</p>
            <h2>Prepared telemetry replay</h2>
            <p>
              Recorded scenario features, not live vehicle sensors. Values below
              belong to the latest saved window.
            </p>
          </div>
          <Database size={20} />
        </div>
        <VehicleDynamics telemetry={latest.telemetry_features} />
      </section>

      <section className="panel">
        <div className="section-header">
          <div>
            <p className="eyebrow">Runtime State</p>
            <h2>Health and latency</h2>
          </div>
          <Timer size={20} />
        </div>
        <div className="stat-list">
          <div>
            <span>SystemHealth</span>
            <Pill label={systemHealth} tone={systemHealth} />
          </div>
          <div>
            <span>Result age</span>
            {stale ? (
              <Pill label="Stale" tone="stale" />
            ) : (
              <Pill label="Current" tone="fresh" />
            )}
          </div>
          <div>
            <span>Vision freshness</span>
            <BranchStatusPill status={visionFreshness} expiry={visionExpiry} />
          </div>
          <div>
            <span>Telemetry freshness</span>
            <BranchStatusPill
              status={telemetryFreshness}
              expiry={telemetryExpiry}
            />
          </div>
          <div>
            <span>Server processing (before DB commit)</span>
            <strong>{latest.latency_ms} ms</strong>
          </div>
        </div>
      </section>

      <section className="panel panel--wide">
        <div className="section-header">
          <div>
            <p className="eyebrow">Recent Trend</p>
            <h2>RiskScore and branch probabilities</h2>
          </div>
          <Video size={20} />
        </div>
        <TrendChart
          history={history.slice(-12)}
          thresholdLow={thresholdLow}
          thresholdHigh={thresholdHigh}
        />
      </section>
    </div>
  );
}
