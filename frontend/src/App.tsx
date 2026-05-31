import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Pause, Play, RotateCw } from "lucide-react";
import { AlertBanner } from "./components/AlertBanner";
import { Sidebar, type ViewKey } from "./components/Sidebar";
import {
  PREPARED_SESSION_METADATA,
  PREPARED_SESSION_WINDOWS,
} from "./data/preparedSessionInput";
import { useCameraPreview } from "./hooks/useCameraPreview";
import { useMonitoringSession } from "./hooks/useMonitoringSession";
import { useSessionLog } from "./hooks/useSessionLog";
import type { AppConfig } from "./types";
import { exportSessionLogCSV, exportSessionLogJSON } from "./utils/export";
import { loadActiveSession, loadConfig, saveConfig } from "./utils/persistence";
import { buildRiskUpdate } from "../../ai/src/riskLogic";
import {
  initAlertState,
  updateAlertState,
  type AlertFsmState,
} from "../../ai/src/alertFsm";
import { ConfigurationView } from "./views/ConfigurationView";
import { ExplanationView } from "./views/ExplanationView";
import { LiveMonitor } from "./views/LiveMonitor";
import { RiskTrends } from "./views/RiskTrends";
import { SignalInspector } from "./views/SignalInspector";
import "./styles.css";

export default function App() {
  const [activeView, setActiveView] = useState<ViewKey>("live");
  const [sessionId] = useState(
    () => loadActiveSession() ?? PREPARED_SESSION_METADATA.session_id,
  );
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false);
  const [config, setConfig] = useState<AppConfig>(() => loadConfig());
  const [cursor, setCursor] = useState(0);
  const [selectedWindowId, setSelectedWindowId] = useState(1);
  const camera = useCameraPreview();
  const { log, append, flag, reset } = useSessionLog(sessionId);
  const alertFsmRef = useRef<AlertFsmState>(initAlertState());

  const fallbackRecord = useMemo(
    () =>
      buildRiskUpdate(
        PREPARED_SESSION_WINDOWS[0],
        sessionId,
        config,
        undefined,
        1,
      ),
    [config, sessionId],
  );
  const history = log.length > 0 ? log : [fallbackRecord];
  const latest = history[history.length - 1];
  const selectedRecord =
    history.find((record) => record.window_id === selectedWindowId) ?? latest;

  const appendNextWindow = useCallback(() => {
    const window =
      PREPARED_SESSION_WINDOWS[cursor % PREPARED_SESSION_WINDOWS.length];
    const nextWindowId = log.length + 1;
    const record = buildRiskUpdate(
      window,
      sessionId,
      config,
      log[log.length - 1],
      nextWindowId,
    );
    // Alert State Manager: apply the wall-clock AlertSeverity FSM on top of the
    // per-window instantaneous severity (temporal hysteresis / anti-flicker).
    const fsm = updateAlertState(alertFsmRef.current, record.RiskLevel, Date.now());
    alertFsmRef.current = fsm;
    append({ ...record, AlertSeverity: fsm.severity });
    setSelectedWindowId(record.window_id);
    setCursor((current) => (current + 1) % PREPARED_SESSION_WINDOWS.length);
  }, [append, config, cursor, log, sessionId]);

  const monitoring = useMonitoringSession({
    deltaT: config.deltaT,
    onTick: appendNextWindow,
  });

  useEffect(() => {
    saveConfig(config);
  }, [config]);

  const updateConfig = (nextConfig: AppConfig) => setConfig(nextConfig);
  const showMonitoringBanner =
    activeView === "live" ||
    activeView === "inspector" ||
    activeView === "trends";

  const restartSession = () => {
    monitoring.pause();
    reset();
    alertFsmRef.current = initAlertState();
    setCursor(0);
    setSelectedWindowId(1);
    monitoring.start();
  };

  return (
    <div
      className={`app-shell ${
        isSidebarCollapsed ? "app-shell--sidebar-collapsed" : ""
      }`}
    >
      <Sidebar
        activeView={activeView}
        collapsed={isSidebarCollapsed}
        onToggleCollapsed={() => setIsSidebarCollapsed((current) => !current)}
        onViewChange={setActiveView}
      />

      <main className="main-shell">
        <header className="topbar">
          <div>
            <h1>In-Cabin Multi-Modal Driver Monitoring & Risk Assessment</h1>
          </div>
          <div className="topbar-actions">
            <button
              type="button"
              className="button button--primary"
              onClick={monitoring.start}
              disabled={monitoring.isMonitoring}
            >
              <Play size={16} />
              Start Monitoring
            </button>
            <button
              type="button"
              className="button"
              onClick={monitoring.pause}
              disabled={!monitoring.isMonitoring}
            >
              <Pause size={16} />
              Pause
            </button>
            <button type="button" className="button" onClick={restartSession}>
              <RotateCw size={16} />
              Restart Session
            </button>
          </div>
        </header>

        {showMonitoringBanner ? <AlertBanner latest={latest} /> : null}

        {activeView === "live" ? (
          <LiveMonitor
            latest={latest}
            history={history}
            sessionId={sessionId}
            recordCount={log.length}
            isMonitoring={monitoring.isMonitoring}
            camera={camera}
            thresholdLow={config.thresholdLow}
          />
        ) : null}

        {activeView === "inspector" ? (
          <SignalInspector
            history={history}
            selectedRecord={selectedRecord}
            thresholdLow={config.thresholdLow}
            onSelectWindow={setSelectedWindowId}
            onToggleFlag={(windowId, flagged) => flag(windowId, flagged)}
          />
        ) : null}

        {activeView === "trends" ? (
          <RiskTrends
            history={history}
            selectedWindowId={selectedRecord.window_id}
            thresholdLow={config.thresholdLow}
            onSelectWindow={setSelectedWindowId}
          />
        ) : null}

        {activeView === "explanation" ? (
          <ExplanationView
            selectedRecord={selectedRecord}
            history={history}
            config={config}
          />
        ) : null}

        {activeView === "configuration" ? (
          <ConfigurationView
            config={config}
            onConfigChange={updateConfig}
            isMonitoring={monitoring.isMonitoring}
            onStartMonitoring={monitoring.start}
            onPauseMonitoring={monitoring.pause}
            onRestartSession={restartSession}
            onExportJson={() =>
              exportSessionLogJSON(
                sessionId,
                log,
                config.enableEvidenceInterpretation,
              )
            }
            onExportCsv={() =>
              exportSessionLogCSV(
                sessionId,
                log,
                config.enableEvidenceInterpretation,
              )
            }
          />
        ) : null}
      </main>
    </div>
  );
}
