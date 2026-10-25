import { Download, Settings } from "lucide-react";
import type { AppConfig } from "../types";
import { roundHalfUp } from "../../../ai/src/riskLogic";
import { zeroWeightNotice } from "../utils/display";
import { formatFixed } from "../utils/format";

interface ConfigurationViewProps {
  config: AppConfig;
  onConfigChange: (config: AppConfig) => void;
  isMonitoring: boolean;
  onExportJson: () => void;
  onExportCsv: () => void;
}

const clamp = (value: number, min: number, max: number) =>
  Math.min(max, Math.max(min, value));

export function ConfigurationView({
  config,
  onConfigChange,
  isMonitoring,
  onExportJson,
  onExportCsv,
}: ConfigurationViewProps) {
  const patchConfig = (patch: Partial<AppConfig>) =>
    onConfigChange({ ...config, ...patch });

  const updateVisionWeight = (value: number) => {
    const weightVision = clamp(value, 0, 1);
    patchConfig({
      weightVision,
      weightTelemetry: roundHalfUp(1 - weightVision, 2),
    });
  };

  const weightNotice = zeroWeightNotice(
    config.weightVision,
    config.weightTelemetry,
  );

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
          <p>
            Changing settings pauses monitoring. The next Start Monitoring (top
            of the page) creates a session with the new configuration.
          </p>
          <label className="field">
            <span>Target inference FPS (camera preview requests 30 FPS)</span>
            <input
              type="number"
              min="1"
              max="30"
              value={config.inferenceFps}
              disabled={isMonitoring}
              onChange={(e) =>
                patchConfig({
                  inferenceFps: clamp(Number(e.target.value) || 1, 1, 30),
                })
              }
            />
          </label>
        </section>

        <section className="config-section">
          <h3>Risk Fusion Parameters</h3>
          <div className="config-grid">
            <label className="field">
              <span>Vision Weight: {formatFixed(config.weightVision, 2)}</span>
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
              <span>
                Telemetry Weight: {formatFixed(config.weightTelemetry, 2)}
              </span>
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

            {weightNotice === null ? null : (
              <p className="runtime-warning config-grid__notice" role="status">
                {weightNotice}
              </p>
            )}

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
            {config.operationMode === "PREPARED_SESSION_RUNTIME" ? (
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
            ) : (
              <p>
                Exports contain all persisted model evidence, source labels,
                model versions and the session fusion configuration.
              </p>
            )}
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
