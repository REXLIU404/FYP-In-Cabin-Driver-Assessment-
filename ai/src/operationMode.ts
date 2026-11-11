import type { OperationMode } from "./types";

/**
 * The ONE front-end judgement of "is this mode like Live" (rule E of the constructed
 * scenario plan): the acquisition loop, the R10 observation rules and the server's
 * ``is_live_like`` all treat these modes the same way. The constructed scenario replays
 * pre-generated dataset frames and telemetry through the trained models, exactly like a
 * camera session; the prepared replay is the legacy local-only path and is NOT live-like.
 */
export function isLiveLike(mode: OperationMode): boolean {
  return mode === "LIVE_MODEL_RUNTIME" || mode === "CONSTRUCTED_SCENARIO_RUNTIME";
}
