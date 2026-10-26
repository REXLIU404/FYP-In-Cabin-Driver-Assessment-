import type { ScenarioPlayerModel } from "../views/scenarioPlayerModel";

interface ScenarioPlayerProps {
  /** The display model built from the playback snapshot and the latest record. */
  model: ScenarioPlayerModel;
  /** The current frame as a data URL, or null when the preloaded image is missing. */
  frameSrc: string | null;
  /** Shown instead of the caption once the scenario finished, e.g. "Scenario finished (136 s, 7 segments)". */
  finishedText: string | null;
}

/**
 * The constructed scenario player (plan Task 7), in the exact spot and size of the
 * camera preview. It only displays: the not-live badge, the current frame, the
 * segment caption, the truth-vs-model line and the 7-block progress bar. Playback is
 * driven elsewhere (the live loop), so there are deliberately no Start / Stop Camera
 * controls here.
 */
export function ScenarioPlayer({
  model,
  frameSrc,
  finishedText,
}: ScenarioPlayerProps) {
  return (
    <div className="scenario-player">
      <div className="scenario-player-stage">
        <span className="scenario-badge">{model.badge}</span>
        {frameSrc !== null ? (
          <img src={frameSrc} alt="Scenario frame" />
        ) : (
          <div className="camera-placeholder">
            <strong>No scenario frame</strong>
          </div>
        )}
      </div>
      <p className="scenario-caption">
        {model.finished && finishedText !== null ? finishedText : model.caption}
      </p>
      <p className="scenario-truth">
        Truth: {model.truth} · Model: {model.model ?? "—"}
      </p>
      <div className="scenario-progress" aria-label="Scenario progress">
        {model.segments.map((segment) => (
          <span
            key={segment.title}
            title={segment.title}
            className={`scenario-progress-block scenario-progress-block--${segment.state}`}
          />
        ))}
        <span className="scenario-elapsed">{model.elapsed}</span>
      </div>
    </div>
  );
}
