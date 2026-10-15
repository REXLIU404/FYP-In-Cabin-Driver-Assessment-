import { useCallback, useEffect, useRef, useState } from "react";
import { Pause, Play, RotateCw } from "lucide-react";
import { AlertBanner } from "./components/AlertBanner";
import { CameraPreview } from "./components/CameraPreview";
import {
  CameraStatusLine,
  CaptureMissNotice,
  FaultPanel,
} from "./components/RuntimeNotices";
import { Sidebar, type ViewKey } from "./components/Sidebar";
import {
  PREPARED_SESSION_METADATA,
  PREPARED_SESSION_WINDOWS,
} from "./data/preparedSessionInput";
import { useCameraPreview } from "./hooks/useCameraPreview";
import { useMonitoringSession } from "./hooks/useMonitoringSession";
import { useLiveSession } from "./hooks/useLiveSession";
import { useSessionLog } from "./hooks/useSessionLog";
import type { AppConfig } from "./types";
import { DATA_MODE_NOTE, DATA_MODE_OPTIONS } from "./utils/dataMode";
import { exportSessionLogCSV, exportSessionLogJSON } from "./utils/export";
import { retryHandler } from "./utils/runtimeNotices";
import {
  loadActiveSession,
  loadConfig,
  nextWindowId,
  saveConfig,
} from "./utils/persistence";
import { buildRiskUpdate } from "../../ai/src/riskLogic";
import { initAlertState, type AlertFsmState } from "../../ai/src/alertFsm";
import { applyAlertState } from "./utils/alertOverlay";
import { ConfigurationView } from "./views/ConfigurationView";
import { ExplanationView } from "./views/ExplanationView";
import { LiveMonitor } from "./views/LiveMonitor";
import { RiskTrends } from "./views/RiskTrends";
import { SignalInspector } from "./views/SignalInspector";
import "./styles.css";

export default function App() {
  const [activeView, setActiveView] = useState<ViewKey>("live");
  const [replayId] = useState(
    () => loadActiveSession() ?? PREPARED_SESSION_METADATA.session_id,
  );
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false);
  const [config, setConfig] = useState<AppConfig>(() => loadConfig());
  const [cursor, setCursor] = useState(0);
  const [selectedWindowId, setSelectedWindowId] = useState(1);
  const camera = useCameraPreview();
  const replayLog = useSessionLog(replayId);
  const live = useLiveSession(config, camera.captureFrame);
  const isLive = config.operationMode === "LIVE_MODEL_RUNTIME";
  const alertFsmRef = useRef<AlertFsmState>(initAlertState());

  const appendReplay = useCallback(() => {
    const window =
      PREPARED_SESSION_WINDOWS[cursor % PREPARED_SESSION_WINDOWS.length];
    const record = buildRiskUpdate(
      window,
      replayId,
      { ...config, operationMode: "PREPARED_SESSION_RUNTIME" },
      replayLog.log[replayLog.log.length - 1],
      nextWindowId(replayLog.log),
    );
    // The FSM overlays a severity on assessed windows only: an unassessed window
    // (RiskLevel null) keeps AlertSeverity null instead of inheriting the held one.
    const overlaid = applyAlertState(record, alertFsmRef.current, Date.now());
    alertFsmRef.current = overlaid.state;
    replayLog.append(overlaid.record);
    setSelectedWindowId(record.window_id);
    setCursor((old) => (old + 1) % PREPARED_SESSION_WINDOWS.length);
  }, [config, cursor, replayId, replayLog]);
  const replay = useMonitoringSession({
    deltaT: config.deltaT,
    onTick: appendReplay,
  });
  const monitoring = isLive ? live.running : replay.isMonitoring;
  const history = isLive ? live.history : replayLog.log;
  const latest = history[history.length - 1];
  const selectedRecord =
    history.find((record) => record.window_id === selectedWindowId) ?? latest;
  const sessionId = isLive ? live.sessionId : replayId;
  const savedFusion = selectedRecord?.provenance?.fusion_config;
  const evidenceConfig = savedFusion
    ? {
        ...config,
        weightVision: savedFusion.weight_vision,
        weightTelemetry: savedFusion.weight_telemetry,
        thresholdLow: savedFusion.threshold_low,
        thresholdHigh: savedFusion.threshold_high,
        emaAlpha: savedFusion.ema_alpha,
        freshnessTolerance: savedFusion.freshness_tolerance_s,
      }
    : config;

  useEffect(() => {
    saveConfig(config);
  }, [config]);

  const pause = () => {
    replay.pause();
    live.pause();
  };
  const start = async (restart = false) => {
    if (isLive) {
      replay.pause();
      if (camera.status !== "live") await camera.start();
      await live.start(restart);
    } else {
      live.pause();
      if (restart) {
        replayLog.reset();
        alertFsmRef.current = initAlertState();
        setCursor(0);
        setSelectedWindowId(1);
      }
      replay.start();
    }
  };
  const updateConfig = (next: AppConfig) => {
    pause();
    setConfig(next);
    setSelectedWindowId(1);
  };
  const exportLog = (format: "json" | "csv") => {
    if (isLive) {
      void live.exportSession(format);
      return;
    }
    if (format === "json")
      exportSessionLogJSON(
        replayId,
        replayLog.log,
        config.enableEvidenceInterpretation,
      );
    else
      exportSessionLogCSV(
        replayId,
        replayLog.log,
        config.enableEvidenceInterpretation,
      );
  };

  return (
    <div
      className={`app-shell ${isSidebarCollapsed ? "app-shell--sidebar-collapsed" : ""}`}
    >
      <Sidebar
        activeView={activeView}
        collapsed={isSidebarCollapsed}
        onToggleCollapsed={() => setIsSidebarCollapsed((v) => !v)}
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
              onClick={() => void start()}
              disabled={
                monitoring ||
                live.busy ||
                live.retrying ||
                camera.status === "requesting"
              }
            >
              <Play size={16} />
              {live.busy ? "Loading models…" : "Start Monitoring"}
            </button>
            <button
              type="button"
              className="button"
              onClick={pause}
              disabled={!monitoring && !live.busy}
            >
              <Pause size={16} />
              Pause
            </button>
            <button
              type="button"
              className="button"
              onClick={() => void start(true)}
              disabled={
                live.busy || live.retrying || camera.status === "requesting"
              }
            >
              <RotateCw size={16} />
              New Session
            </button>
          </div>
        </header>

        <section className="panel runtime-panel">
          <div className="runtime-controls">
            <label className="field">
              <span>Data mode</span>
              <select
                aria-label="Data mode"
                value={config.operationMode}
                disabled={monitoring || live.busy}
                onChange={(event) =>
                  updateConfig({
                    ...config,
                    operationMode: event.target
                      .value as AppConfig["operationMode"],
                  })
                }
              >
                {DATA_MODE_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>
            {isLive && (
              <>
                <button
                  className="button"
                  onClick={() => void live.refreshSessions()}
                >
                  Refresh saved sessions
                </button>
                <label className="field">
                  <span>Saved live sessions</span>
                  <select
                    aria-label="Saved live sessions"
                    value=""
                    disabled={monitoring || live.busy}
                    onChange={(e) => {
                      if (e.target.value) void live.loadSession(e.target.value);
                    }}
                  >
                    <option value="">Select a session…</option>
                    {live.sessions.map((s) => (
                      <option key={s.id} value={s.id}>
                        {s.id} · {s.total_windows} windows
                      </option>
                    ))}
                  </select>
                </label>
              </>
            )}
          </div>
          <p>{DATA_MODE_NOTE[config.operationMode]}</p>
          {isLive && (
            <div className="runtime-details">
              <CameraStatusLine
                status={camera.status}
                actualFps={camera.actualFps}
                event={camera.event}
              />
              <span>
                Inference:{" "}
                {monitoring ? (live.effectiveFps?.toFixed(1) ?? "—") : "—"} FPS
                · target {config.inferenceFps}
              </span>
              <span>
                Request round trip: {live.requestMs?.toFixed(0) ?? "—"} ms
              </span>
              <span>
                Visible history: {history.length} / {live.total} persisted ·
                export includes all windows
              </span>
              {live.droppedFrames > 0 && (
                <span>Late frames dropped: {live.droppedFrames}</span>
              )}
            </div>
          )}
          {isLive && live.models && (
            <details>
              <summary>Loaded model versions</summary>
              <p>
                MobileNetV3: <code>{live.models.vision.sha256}</code>
              </p>
              <p>
                XGBoost: <code>{live.models.telemetry.sha256}</code>
              </p>
            </details>
          )}
          {isLive && live.fault && (
            <FaultPanel
              fault={live.fault}
              retrying={live.retrying}
              onRetry={retryHandler(live)}
            />
          )}
          {isLive && live.error && (
            <p className="runtime-error" role="alert">
              {live.error}
            </p>
          )}
          {isLive && monitoring && live.lastCaptureMiss && (
            <CaptureMissNotice reason={live.lastCaptureMiss} />
          )}
          {isLive && live.stale && (
            <p className="runtime-warning" role="status">
              Latest result is stale. Historical values are retained; there is
              no current risk assessment.
            </p>
          )}
        </section>

        {latest && ["live", "inspector", "trends"].includes(activeView) ? (
          <AlertBanner latest={latest} stale={isLive && live.stale} />
        ) : null}

        {activeView === "live" &&
          (latest ? (
            <LiveMonitor
              latest={latest}
              history={history}
              sessionId={sessionId}
              recordCount={isLive ? live.total : history.length}
              isMonitoring={monitoring}
              camera={camera}
              thresholdLow={
                latest.provenance?.fusion_config?.threshold_low ??
                config.thresholdLow
              }
              thresholdHigh={
                latest.provenance?.fusion_config?.threshold_high ??
                config.thresholdHigh
              }
              stale={isLive && live.stale}
            />
          ) : (
            <section className="panel empty-state">
              <h2>
                {live.busy
                  ? "Preparing inference…"
                  : "Waiting for the first result"}
              </h2>
              <p>
                Start monitoring to create a session. Camera permissions and
                model readiness are checked before results appear.
              </p>
              <CameraPreview
                videoRef={camera.videoRef}
                status={camera.status}
                onStart={() => void camera.start()}
                onStop={camera.stop}
              />
            </section>
          ))}
        {activeView !== "live" &&
          activeView !== "configuration" &&
          !selectedRecord && (
            <section className="panel empty-state">
              <h2>No session results yet</h2>
              <p>
                Start monitoring or load a saved session to inspect its
                evidence.
              </p>
            </section>
          )}
        {activeView === "inspector" && selectedRecord && (
          <SignalInspector
            history={history}
            selectedRecord={selectedRecord}
            thresholdLow={evidenceConfig.thresholdLow}
            onSelectWindow={setSelectedWindowId}
            onToggleFlag={(id, flagged) => {
              if (isLive) void live.flag(id, flagged);
              else replayLog.flag(id, flagged);
            }}
          />
        )}
        {activeView === "trends" && selectedRecord && (
          <RiskTrends
            history={history}
            selectedWindowId={selectedRecord.window_id}
            thresholdLow={evidenceConfig.thresholdLow}
            thresholdHigh={evidenceConfig.thresholdHigh}
            onSelectWindow={setSelectedWindowId}
          />
        )}
        {activeView === "explanation" && selectedRecord && (
          <ExplanationView
            selectedRecord={selectedRecord}
            history={history}
            config={evidenceConfig}
          />
        )}
        {activeView === "configuration" && (
          <ConfigurationView
            config={config}
            onConfigChange={updateConfig}
            isMonitoring={monitoring || live.busy}
            onStartMonitoring={() => void start()}
            onPauseMonitoring={pause}
            onRestartSession={() => void start(true)}
            onExportJson={() => exportLog("json")}
            onExportCsv={() => exportLog("csv")}
          />
        )}
      </main>
    </div>
  );
}
