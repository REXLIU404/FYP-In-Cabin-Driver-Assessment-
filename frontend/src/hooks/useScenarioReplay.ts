import { useCallback, useEffect, useRef, useState } from "react";
import {
  createScenarioPlayback,
  type ScenarioManifest,
} from "../../../ai/src/scenarioTimeline";
import { api, type ScenarioListItem } from "../api/client";
import { preloadFrames } from "../data/scenarioPreload";
import type { CaptureResult } from "./useCameraPreview";

export type ScenarioLoadStatus = "idle" | "loading" | "ready" | "invalid";

/**
 * The constructed scenario behind the data-mode switch (plan Task 6): the list of
 * bundles, the selected one and, once its frames are preloaded, the playback clock
 * that feeds the live loop. Selecting a scenario loads it end to end - manifest,
 * every frame, the clock - so the player either starts complete or not at all.
 */
export function useScenarioReplay() {
  const [scenarios, setScenarios] = useState<ScenarioListItem[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [status, setStatus] = useState<ScenarioLoadStatus>("idle");
  const [progress, setProgress] = useState<{
    done: number;
    total: number;
  } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [playback, setPlayback] = useState<ReturnType<
    typeof createScenarioPlayback
  > | null>(null);
  const generation = useRef(0);

  useEffect(() => {
    let cancelled = false;
    api
      .scenarios()
      .then((list) => {
        if (!cancelled) setScenarios(list);
      })
      .catch((err: unknown) => {
        if (!cancelled)
          setError(
            err instanceof Error ? err.message : "Cannot load the scenarios",
          );
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const select = useCallback(async (id: string) => {
    generation.current += 1;
    const g = generation.current;
    setSelectedId(id);
    setStatus("loading");
    setProgress(null);
    setError(null);
    setPlayback(null);
    try {
      const manifest: ScenarioManifest = await api.scenarioManifest(id);
      if (g !== generation.current) return;
      const urls = await preloadFrames(
        manifest,
        async (file) => {
          const response = await fetch(api.scenarioFrameUrl(id, file));
          if (!response.ok)
            throw new Error(`the frame request failed (${response.status})`);
          return response.blob();
        },
        (done, total) => setProgress({ done, total }),
      );
      if (g !== generation.current) return;
      setPlayback(
        createScenarioPlayback(
          manifest,
          (n) => urls[n] ?? null,
          () => Date.now(),
        ),
      );
      setStatus("ready");
    } catch (err) {
      if (g !== generation.current) return;
      setError(
        err instanceof Error ? err.message : "The scenario could not be loaded",
      );
      setStatus("invalid");
    }
  }, []);

  return {
    scenarios,
    selectedId,
    select,
    status,
    progress,
    error,
    playback,
  };
}

/**
 * The frame source of a constructed scenario session, in the camera hook's shape:
 * the playback's frame, or the one reason that is not the camera's - a preloaded
 * image is missing (plan Task 6).
 */
export const scenarioCapture = (
  playback: ReturnType<typeof createScenarioPlayback>,
): (() => CaptureResult) => () => {
  const frame = playback.captureFrame();
  return frame
    ? { frame, reason: null }
    : { frame: null, reason: "scenario_frame_unavailable" };
};
