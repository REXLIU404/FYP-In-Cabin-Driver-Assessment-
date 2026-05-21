import { Database, Timer, Video } from "lucide-react";
import { CameraPreview } from "../components/CameraPreview";
import { ModalityCard } from "../components/ModalityCard";
import { Pill } from "../components/Pill";
import { ScoreGauge } from "../components/ScoreGauge";
import { TelemetrySummary } from "../components/TelemetrySummary";
import { TrendChart } from "../components/TrendChart";
import type { useCameraPreview } from "../hooks/useCameraPreview";
import type { RiskUpdate } from "../types";
import { getEvidenceType } from "../../../ai/src/evidence";
import { formatTimestamp } from "../utils/format";

interface LiveMonitorProps {
  latest: RiskUpdate;
  history: RiskUpdate[];
  sessionId: string;
  recordCount: number;
  isMonitoring: boolean;
  camera: ReturnType<typeof useCameraPreview>;
  thresholdLow: number;
}

export function LiveMonitor({
  latest,
  history,
  sessionId,
  recordCount,
  isMonitoring,
  camera,
  thresholdLow,
}: LiveMonitorProps) {
  const evidenceType = getEvidenceType(latest, thresholdLow);

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
            <ScoreGauge score={latest.RiskScore} label="RiskScore" />
            <div className="risk-badges">
              <Pill label={latest.RiskLevel} tone={latest.RiskLevel} />
              <Pill label={evidenceType} />
              <Pill label={latest.AlertSeverity} tone={latest.AlertSeverity} />
            </div>
            <div className="modality-grid">
              <ModalityCard
                title="P_distraction"
                probability={latest.P_distraction}
                freshness={latest.modality_freshness.vision}
              />
              <ModalityCard
                title="P_telemetry_anomaly"
                probability={latest.P_telemetry_anomaly}
                freshness={latest.modality_freshness.telemetry}
              />
            </div>
          </div>
        </div>
      </section>

      <section className="panel">
        <div className="section-header">
          <div>
            <p className="eyebrow">Telemetry Summary</p>
            <h2>Structured input</h2>
          </div>
          <Database size={20} />
        </div>
        <TelemetrySummary telemetry={latest.telemetry_features} />
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
            <Pill label={latest.SystemHealth} tone={latest.SystemHealth} />
          </div>
          <div>
            <span>Vision freshness</span>
            <Pill
              label={latest.modality_freshness.vision}
              tone={latest.modality_freshness.vision}
            />
          </div>
          <div>
            <span>Telemetry freshness</span>
            <Pill
              label={latest.modality_freshness.telemetry}
              tone={latest.modality_freshness.telemetry}
            />
          </div>
          <div>
            <span>Latency</span>
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
        <TrendChart history={history.slice(-12)} />
      </section>
    </div>
  );
}
