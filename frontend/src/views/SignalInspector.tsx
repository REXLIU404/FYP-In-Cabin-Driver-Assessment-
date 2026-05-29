import { Flag, Search } from "lucide-react";
import { Pill } from "../components/Pill";
import { TelemetrySummary } from "../components/TelemetrySummary";
import type { RiskUpdate } from "../types";
import { getEvidenceType, getRelativeEvidence } from "../../../ai/src/evidence";
import { formatPercent, formatRiskScore } from "../utils/format";

interface SignalInspectorProps {
  history: RiskUpdate[];
  selectedRecord: RiskUpdate;
  thresholdLow: number;
  onSelectWindow: (windowId: number) => void;
  onToggleFlag: (windowId: number, flagged: boolean) => void;
}

export function SignalInspector({
  history,
  selectedRecord,
  thresholdLow,
  onSelectWindow,
  onToggleFlag,
}: SignalInspectorProps) {
  const evidenceType = getEvidenceType(selectedRecord, thresholdLow);
  const relativeEvidence = getRelativeEvidence(selectedRecord);

  return (
    <div className="page-grid page-grid--inspector">
      <section className="panel window-list-panel">
        <div className="section-header">
          <div>
            <p className="eyebrow">Signal Inspector</p>
            <h2>Window list</h2>
          </div>
          <Search size={20} />
        </div>
        <div className="window-list">
          {[...history].reverse().map((record) => (
            <button
              type="button"
              key={record.window_id}
              className={
                record.window_id === selectedRecord.window_id
                  ? "is-selected"
                  : undefined
              }
              onClick={() => onSelectWindow(record.window_id)}
            >
              <span>Window {record.window_id}</span>
            </button>
          ))}
        </div>
      </section>

      <section className="panel signal-panel">
        <div className="section-header">
          <div>
            <p className="eyebrow">Selected Window</p>
            <h2>1. Current window summary</h2>
          </div>
          <button
            type="button"
            className="button"
            onClick={() =>
              onToggleFlag(selectedRecord.window_id, !selectedRecord.flagged)
            }
          >
            <Flag size={16} />
            {selectedRecord.flagged ? "Unflag" : "Flag"}
          </button>
        </div>

        <div className="stat-list stat-list--compact">
          <div>
            <span>RiskScore</span>
            <strong>{formatRiskScore(selectedRecord.RiskScore)}</strong>
          </div>
          <div>
            <span>RiskLevel</span>
            <Pill
              label={selectedRecord.RiskLevel}
              tone={selectedRecord.RiskLevel}
            />
          </div>
          <div>
            <span>Evidence Type</span>
            <strong>{evidenceType}</strong>
          </div>
          <div>
            <span>Relative Evidence</span>
            <strong>{relativeEvidence}</strong>
          </div>
        </div>
      </section>

      <section className="panel signal-panel">
        <div className="section-header">
          <div>
            <p className="eyebrow">Vision Branch</p>
            <h2>2. Top visual probabilities</h2>
          </div>
        </div>

        <div className="bar-list">
          {selectedRecord.visual_top_classes.map((item) => (
            <div className="bar-row" key={item.label}>
              <span>{item.label}</span>
              <div className="bar-track">
                <div style={{ width: `${item.probability * 100}%` }} />
              </div>
              <strong>{item.probability.toFixed(2)}</strong>
            </div>
          ))}
        </div>
      </section>

      <section className="panel signal-panel">
        <div className="section-header">
          <div>
            <p className="eyebrow">Telemetry Branch</p>
            <h2>3. Vehicle-dynamics features</h2>
          </div>
        </div>
        <TelemetrySummary telemetry={selectedRecord.telemetry_features} />
      </section>

      <section className="panel signal-panel">
        <div className="section-header">
          <div>
            <p className="eyebrow">Branch Signals</p>
            <h2>4. Scores, freshness, latency</h2>
          </div>
        </div>

        <div className="stat-list stat-list--compact">
          <div>
            <span>P_distraction</span>
            <strong>{formatPercent(selectedRecord.P_distraction)}</strong>
          </div>
          <div>
            <span>Telemetry non-safe risk</span>
            <strong>{formatPercent(selectedRecord.P_telemetry_anomaly)}</strong>
          </div>
          <div>
            <span>Vision freshness</span>
            <Pill
              label={selectedRecord.modality_freshness.vision}
              tone={selectedRecord.modality_freshness.vision}
            />
          </div>
          <div>
            <span>Telemetry freshness</span>
            <Pill
              label={selectedRecord.modality_freshness.telemetry}
              tone={selectedRecord.modality_freshness.telemetry}
            />
          </div>
          <div>
            <span>Latency</span>
            <strong>{selectedRecord.latency_ms} ms</strong>
          </div>
          <div>
            <span>Flag</span>
            <strong>{selectedRecord.flagged ? "Flagged" : "None"}</strong>
          </div>
        </div>
      </section>
    </div>
  );
}
