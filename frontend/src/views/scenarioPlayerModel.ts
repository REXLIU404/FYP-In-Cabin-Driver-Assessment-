import type {
  PlaybackSnapshot,
  ScenarioManifest,
} from "../../../ai/src/scenarioTimeline";
import type { RiskUpdate } from "../types";

export interface ScenarioPlayerModel {
  /** The constant not-live label over the frame. */
  badge: string;
  /** The current segment, e.g. "Segment 2/7 · Vision only · texting_right · driver p026 · State Farm test split". */
  caption: string;
  /** The current segment's ground-truth vision label (what the frame really shows). */
  truth: string;
  /** The trained model's top visual class on the latest record, e.g. "texting_right 0.97"; null without one. */
  model: string | null;
  segments: Array<{
    title: string;
    state: "done" | "current" | "todo";
  }>;
  /** Playback position over the scenario total, e.g. "0:34 / 2:16". */
  elapsed: string;
  finished: boolean;
}

const NOT_LIVE_BADGE = "CONSTRUCTED SCENARIO · not live";

/** "0:34" for 34000 ms: minutes are not padded, seconds are (m:ss). */
const mmss = (ms: number): string =>
  `${Math.floor(ms / 60_000)}:${String(Math.floor(ms / 1000) % 60).padStart(2, "0")}`;

/**
 * What the scenario player shows (plan Task 7): a display model over the playback
 * snapshot and the latest record. Pure - no playback state is read or changed here;
 * App takes the snapshot from the clock and the latest record from the live history.
 */
export const buildScenarioPlayerModel = (
  manifest: ScenarioManifest,
  snapshot: PlaybackSnapshot,
  latest: RiskUpdate | undefined,
): ScenarioPlayerModel => {
  const current = manifest.segments[snapshot.segmentIndex];
  const top = latest?.visual_top_classes.reduce<{
    label: string;
    probability: number;
  } | null>(
    (best, item) => (best && best.probability >= item.probability ? best : item),
    null,
  );
  return {
    badge: NOT_LIVE_BADGE,
    caption: `Segment ${snapshot.segmentIndex + 1}/${manifest.segments.length} · ${current.title} · ${current.vision_label} · driver ${current.driver_id} · State Farm test split`,
    truth: current.vision_label,
    model: top ? `${top.label} ${top.probability.toFixed(2)}` : null,
    segments: manifest.segments.map((segment) => ({
      title: segment.title,
      state:
        segment.index < snapshot.segmentIndex
          ? "done"
          : segment.index === snapshot.segmentIndex
            ? "current"
            : "todo",
    })),
    elapsed: `${mmss(snapshot.positionMs)} / ${mmss(manifest.duration_ms)}`,
    finished: snapshot.finished,
  };
};
