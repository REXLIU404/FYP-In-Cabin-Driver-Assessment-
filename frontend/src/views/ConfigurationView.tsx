import { Download, Pause, Play, RotateCw, Settings } from "lucide-react";
import type { AppConfig } from "../types";

interface ConfigurationViewProps {
  config: AppConfig;
  onConfigChange: (config: AppConfig) => void;
  isMonitoring: boolean;
  onStartMonitoring: () => void;
  onPauseMonitoring: () => void;
  onRestartSession: () => void;
  onExportJson: () => void;
  onExportCsv: () => void;
}

const clamp = (value: number, min: number, max: number) =>
  Math.min(max, Math.max(min, value));

export function ConfigurationView({
  config,
  onConfigChange,
  isMonitoring,
  onStartMonitoring,
  onPauseMonitoring,
  onRestartSession,
  onExportJson,
  onExportCsv,
}: ConfigurationViewProps) {
  const patchConfig = (patch: Partial<AppConfig>) =>
    onConfigChange({ ...config, ...patch });

  const updateVisionWeight = (value: number) => {
    const weightVision = clamp(value, 0, 1);
    patchConfig({
      weightVision,
      weightTelemetry: Number((1 - weightVision).toFixed(2)),
    });
  };

  return (
    <section className="panel configuration-panel">
      <div className="section-header">
        <div>
          <p className="eyebrow">Configuration</p>
          <h2>Runtime configuration and output</h2>
        </div>
        <Settings size={20} />
      </div>

      <div className="config-sections">
        <section className="config-section">
          <h3>Runtime Configuration</h3>
          <div className="action-strip">
            <button
              type="button"
              className="button button--primary"
              onClick={onStartMonitoring}
              disabled={isMonitoring}
            >
              <Play size={16} />
              Start Monitoring
            </button>
            <button
              type="button"
              className="button"
              onClick={onPauseMonitoring}
              disabled={!isMonitoring}
            >
              <Pause size={16} />
              Pause
            </button>
            <button type="button" className="button" onClick={onRestartSession}>
              <RotateCw size={16} />
              Restart Session
            </button>
          </div>
        </section>

        <section className="config-section">
          <h3>Risk Fusion Parameters</h3>
          <div className="config-grid">
            <label className="field">
              <span>Vision Weight: {config.weightVision.toFixed(2)}</span>
              <input
                type="range"
                min="0"
                max="1"
                step="0.05"
                value={config.weightVision}
                onChange={(event) =>
                  updateVisionWeight(Number(event.target.value))
                }
              />
            </label>

            <label className="field">
              <span>Telemetry Weight: {config.weightTelemetry.toFixed(2)}</span>
              <input
                type="range"
                min="0"
                max="1"
                step="0.05"
                value={config.weightTelemetry}
                onChange={(event) =>
                  updateVisionWeight(1 - Number(event.target.value))
                }
              />
            </label>

            <label className="field">
              <span>Low / Medium Threshold</span>
              <input
                type="number"
                min="0"
                max="100"
                step="5"
                value={config.thresholdLow}
                onChange={(event) =>
                  patchConfig({ thresholdLow: Number(event.target.value) })
                }
              />
            </label>

            <label className="field">
              <span>Medium / High Threshold</span>
              <input
                type="number"
                min="0"
                max="100"
                step="5"
                value={config.thresholdHigh}
                onChange={(event) =>
                  patchConfig({ thresholdHigh: Number(event.target.value) })
                }
              />
            </label>
          </div>
        </section>

        <section className="config-section">
          <h3>Output Options</h3>
          <div className="output-options">
            <label className="checkbox-field">
              <input
                type="checkbox"
                checked={config.enableEvidenceInterpretation}
                onChange={(event) =>
                  patchConfig({
                    enableEvidenceInterpretation: event.target.checked,
                  })
                }
              />
              <span>Enable Evidence Interpretation</span>
            </label>
            <div className="action-strip">
              <button
                type="button"
                className="button button--primary"
                onClick={onExportJson}
              >
                <Download size={16} />
                Export JSON
              </button>
              <button type="button" className="button" onClick={onExportCsv}>
                Export CSV
              </button>
            </div>
          </div>
        </section>
      </div>
    </section>
  );
}
