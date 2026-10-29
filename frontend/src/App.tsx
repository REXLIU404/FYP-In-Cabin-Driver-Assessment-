import { useCallback, useEffect, useRef, useState } from "react";
import { Pause, Play, RotateCw } from "lucide-react";
import { AlertBanner } from "./components/AlertBanner";
import { CameraPreview } from "./components/CameraPreview";
import { ScenarioPlayer } from "./components/ScenarioPlayer";
import { SelectionBar } from "./components/SelectionBar";
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
import { scenarioCapture, useScenarioReplay } from "./hooks/useScenarioReplay";
import type { AppConfig } from "./types";
import {
  DATA_MODE_NOTE,
  DATA_MODE_OPTIONS,
  emptyResultsHint,
  offersSavedLiveSessions,
} from "./utils/dataMode";
import { runtimeStaleNoticeShown } from "./utils/display";
import { describeSelection, selectRecord } from "./utils/selection";
import { describeVisionModel } from "./utils/modelInfo";
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
import { isLiveLike } from "../../ai/src/operationMode";
import type { PlaybackSnapshot } from "../../ai/src/scenarioTimeline";
import { applyAlertState } from "./utils/alertOverlay";
import { ConfigurationView } from "./views/ConfigurationView";
import { ExplanationView } from "./views/ExplanationView";
import { LiveMonitor } from "./views/LiveMonitor";
import { RiskTrends } from "./views/RiskTrends";
import { SignalInspector } from "./views/SignalInspector";
import { buildScenarioPlayerModel } from "./views/scenarioPlayerModel";
import "./styles.css";

export default function App() {
  const [activeView, setActiveView] = useState<ViewKey>("live");
  const [replayId] = useState(
    () => loadActiveSession() ?? PREPARED_SESSION_METADATA.session_id,
  );
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false);
  const [config, setConfig] = useState<AppConfig>(() => loadConfig());
  const [cursor, setCursor] = useState(0);
  // null follows the newest window; a number is a window the person pinned (utils/selection.ts).
  const [selectedWindowId, setSelectedWindowId] = useState<number | null>(null);
  const camera = useCameraPreview();
  const replayLog = useSessionLog(replayId);
  const scenario = useScenarioReplay();
  const isLive = config.operationMode === "LIVE_MODEL_RUNTIME";
  const isLiveLikeMode = isLiveLike(config.operationMode);
  const isScenario =
    config.operationMode === "CONSTRUCTED_SCENARIO_RUNTIME";
  // The constructed scenario session feeds the SAME live loop with the playback's
  // frame source and telemetry source; Live keeps the camera and the default
  // prepared cursor. The scenario start never touches the camera.
  const scenarioPlayback = isScenario ? scenario.playback : null;
  const live = useLiveSession(
    config,
    scenarioPlayback
      ? scenarioCapture(scenarioPlayback)
      : camera.captureFrame,
    scenarioPlayback ? () => scenarioPlayback.telemetry : undefined,
  );
  const alertFsmRef = useRef<AlertFsmState>(initAlertState());
  // The player view follows the playback clock (250 ms): the current frame and the
  // snapshot the display model is built from. The loop drives the actual session;
  // this state is display-only.
  const [scenarioFrameSrc, setScenarioFrameSrc] = useState<string | null>(null);
  const [scenarioSnapshot, setScenarioSnapshot] =
    useState<PlaybackSnapshot | null>(null);
  useEffect(() => {
    if (!isScenario || !scenario.playback) return;
    const capture = scenarioCapture(scenario.playback);
    const tick = () => {
      const sample = capture();
      setScenarioFrameSrc(sample.frame ? sample.frame.image_base64 : null);
      setScenarioSnapshot(scenario.playback?.snapshot() ?? null);
    };
    tick();
    const timer = setInterval(tick, 250);
    return () => clearInterval(timer);
  }, [isScenario, scenario.playback]);
  // The scenario finishes at the end of the last segment: stop the session there
  // (no loop), exactly as the plan requires. `live.pause` is the loop's own stable
  // function, and only the finished FLAG is watched: depending on the whole `live`
  // object (or the whole snapshot) here would re-run this effect on every render,
  // pause again and re-render forever (React "Maximum update depth").
  const pauseLive = live.pause;
  const scenarioFinished = scenarioSnapshot?.finished;
  useEffect(() => {
    if (isScenario && scenarioFinished) pauseLive();
  }, [isScenario, scenarioFinished, pauseLive]);

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
    // The view follows the newest window by default (selectedWindowId stays null); a tick
    // must not pin it, or the selection bar reads 'pinned' without a click and a real pin
    // would be overwritten on the next tick (review R9/R20).
    setCursor((old) => (old + 1) % PREPARED_SESSION_WINDOWS.length);
  }, [config, cursor, replayId, replayLog]);
  const replay = useMonitoringSession({
    deltaT: config.deltaT,
    onTick: appendReplay,
  });
  const monitoring = isLiveLikeMode ? live.running : replay.isMonitoring;
  const history = isLiveLikeMode ? live.history : replayLog.log;
  const latest = history[history.length - 1];
  const selectedRecord = selectRecord(history, selectedWindowId);
  const selection = describeSelection(history, selectedWindowId);
  // The banner is rendered on these views. It takes over the stale warning only in ITS OWN
  // 'stale' state: for an unassessed latest window getDisplayState says 'unavailable', which
  // says nothing about age, so the runtime panel still repeats the stale notice then
  // (utils/display.ts runtimeStaleNoticeShown).
  const bannerShown =
    latest !== undefined &&
    ["live", "inspector", "trends"].includes(activeView);
  const sessionId = isLiveLikeMode ? live.sessionId : replayId;
  // Another session (new, or loaded from the saved list) opens on its newest window: drop the pin.
  // Reset during render, not in an effect, so no frame shows the old pin against the new history.
  const [selectionSession, setSelectionSession] = useState(sessionId);
  if (selectionSession !== sessionId) {
    setSelectionSession(sessionId);
    setSelectedWindowId(null);
  }
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
  // Everything the player displays, in one object (plan Task 7). The numbers in the
  // finished line come from the manifest, never hard-coded.
  const scenarioPlayerProps =
    isScenario && scenario.manifest && scenarioSnapshot
      ? {
          model: buildScenarioPlayerModel(
            scenario.manifest,
            scenarioSnapshot,
            latest,
          ),
          frameSrc: scenarioFrameSrc,
          finishedText: `Scenario finished (${Math.round(scenario.manifest.duration_ms / 1000)} s, ${scenario.manifest.segments.length} segments)`,
        }
      : null;

  useEffect(() => {
    saveConfig(config);
  }, [config]);

  const pause = () => {
    replay.pause();
    live.pause();
  };
  const start = async (restart = false) => {
    if (isLiveLikeMode) {
      replay.pause();
      // Only Live touches the camera; the constructed scenario feeds the loop its
      // own preloaded frames.
      if (isLive && camera.status !== "live") await camera.start();
      await live.start(restart);
    } else {
      live.pause();
      if (restart) {
        replayLog.reset();
        alertFsmRef.current = initAlertState();
        setCursor(0);
        setSelectedWindowId(null);
      }
      replay.start();
    }
  };
  const updateConfig = (next: AppConfig) => {
    pause();
    setConfig(next);
    setSelectedWindowId(null);
  };
  const exportLog = (format: "json" | "csv") => {
    if (isLiveLikeMode) {
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
            {isScenario && (
              <span className="topbar-mode">CONSTRUCTED SCENARIO</span>
            )}
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
                (isLive && camera.status === "requesting") ||
                (isScenario && scenario.status !== "ready")
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
                onChange={(event) => {
                  live.clearError();
                  updateConfig({
                    ...config,
                    operationMode: event.target
                      .value as AppConfig["operationMode"],
                  });
                }}
              >
                {DATA_MODE_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>
            {offersSavedLiveSessions(config.operationMode) && (
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
            {isScenario && (
              <>
                <label className="field">
                  <span>Scenario</span>
                  <select
                    aria-label="Scenario"
                    value={scenario.selectedId ?? ""}
                    disabled={monitoring || live.busy}
                    onChange={(event) => {
                      if (event.target.value)
                        void scenario.select(event.target.value);
                    }}
                  >
                    <option value="">Select a scenario…</option>
                    {scenario.scenarios.map((s) => (
                      <option key={s.id} value={s.id}>
                        {s.id} · {Math.round(s.duration_ms / 1000)} s ·{" "}
                        {s.segments} segments
                      </option>
                    ))}
                  </select>
                </label>
                {scenario.status === "loading" && scenario.progress && (
                  <span className="scenario-progress-note" role="status">
                    Loading frames {scenario.progress.done}/
                    {scenario.progress.total}…
                  </span>
                )}
              </>
            )}
          </div>
          {DATA_MODE_NOTE[config.operationMode] && (
            <p>{DATA_MODE_NOTE[config.operationMode]}</p>
          )}
          {isScenario && scenario.scenarios.length === 0 && (
            <p className="runtime-warning" role="status">
              No scenario bundles found. Generate one with{" "}
              <code>python3 scripts/build_dataset_replay.py viva_v1</code> and
              refresh the page.
            </p>
          )}
          {isScenario && scenario.status === "invalid" && scenario.error && (
            <p className="runtime-error" role="alert">
              {scenario.error}
            </p>
          )}
          {isLiveLikeMode && (
            <div className="runtime-details">
              {isLive && (
                <CameraStatusLine
                  status={camera.status}
                  actualFps={camera.actualFps}
                  event={camera.event}
                />
              )}
              <span>
                Inference:{" "}
                {monitoring ? (live.effectiveFps?.toFixed(1) ?? "—") : "—"} FPS
                · target {config.inferenceFps}
              </span>
              <span>
                Request round trip: {live.requestMs?.toFixed(0) ?? "—"} ms
              </span>
              <span>
                Showing {history.length} of {live.total} saved windows · export
                includes all
              </span>
              {live.models && (
                <span>
                  Vision model: {describeVisionModel(live.models.vision)}
                </span>
              )}
              {live.droppedFrames > 0 && (
                <span>Late frames dropped: {live.droppedFrames}</span>
              )}
            </div>
          )}
          {isLiveLikeMode && live.models && (
            <details>
              <summary>Loaded model versions</summary>
              <p>
                Vision ({describeVisionModel(live.models.vision)}):{" "}
                <code>{live.models.vision.sha256}</code>
              </p>
              <p>
                XGBoost: <code>{live.models.telemetry.sha256}</code>
              </p>
            </details>
          )}
          {isLiveLikeMode && live.fault && (
            <FaultPanel
              fault={live.fault}
              retrying={live.retrying}
              onRetry={retryHandler(live)}
            />
          )}
          {isLiveLikeMode && live.error && (
            <p className="runtime-error" role="alert">
              {live.error}
            </p>
          )}
          {isLiveLikeMode && monitoring && live.lastCaptureMiss && (
            <CaptureMissNotice reason={live.lastCaptureMiss} />
          )}
          {isLiveLikeMode &&
            runtimeStaleNoticeShown(activeView, latest, live.stale) && (
              <p className="runtime-warning" role="status">
                Latest result is stale. Historical values are retained; there is
                no current risk assessment.
              </p>
            )}
        </section>

        {bannerShown && latest ? (
          <AlertBanner
            latest={latest}
            stale={isLiveLikeMode && live.stale}
          />
        ) : null}

        {selection &&
        ["inspector", "trends", "explanation"].includes(activeView) ? (
          <SelectionBar
            windowId={selection.windowId}
            pinned={selection.pinned}
            isMonitoring={monitoring}
            onFollowLatest={() => setSelectedWindowId(null)}
          />
        ) : null}

        {activeView === "live" &&
          (latest ? (
            <LiveMonitor
              latest={latest}
              history={history}
              sessionId={sessionId}
              recordCount={isLiveLikeMode ? live.total : history.length}
              isMonitoring={monitoring}
              stopped={isLiveLikeMode && Boolean(live.fault?.stopped)}
              camera={camera}
              thresholdLow={
                latest.provenance?.fusion_config?.threshold_low ??
                config.thresholdLow
              }
              thresholdHigh={
                latest.provenance?.fusion_config?.threshold_high ??
                config.thresholdHigh
              }
              stale={isLiveLikeMode && live.stale}
              mode={config.operationMode}
              scenario={scenarioPlayerProps ?? undefined}
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
              {scenarioPlayerProps ? (
                <ScenarioPlayer
                  model={scenarioPlayerProps.model}
                  frameSrc={scenarioPlayerProps.frameSrc}
                  finishedText={scenarioPlayerProps.finishedText}
                />
              ) : (
                <CameraPreview
                  videoRef={camera.videoRef}
                  status={camera.status}
                  onStart={() => void camera.start()}
                  onStop={camera.stop}
                />
              )}
            </section>
          ))}
        {activeView !== "live" &&
          activeView !== "configuration" &&
          !selectedRecord && (
            <section className="panel empty-state">
              <h2>No session results yet</h2>
              <p>{emptyResultsHint(config.operationMode)}</p>
            </section>
          )}
        {activeView === "inspector" && selectedRecord && (
          <SignalInspector
            history={history}
            selectedRecord={selectedRecord}
            thresholdLow={evidenceConfig.thresholdLow}
            onSelectWindow={setSelectedWindowId}
            onToggleFlag={(id, flagged) => {
              if (isLiveLikeMode) void live.flag(id, flagged);
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
            onExportJson={() => exportLog("json")}
            onExportCsv={() => exportLog("csv")}
          />
        )}
      </main>
    </div>
  );
}
