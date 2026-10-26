import type { OperationMode } from "../types";

/**
 * The one source of the mode's user-facing name (rule: all interface copy reads
 * from a constant, so a rename - e.g. "Constructed demo scenario" - changes one
 * line). Tests pin the literal separately.
 */
export const CONSTRUCTED_MODE_LABEL = "Constructed demo scenario";

/**
 * The "Data mode" choices. Live is the system and is listed first; the constructed
 * scenario replays pre-generated test frames and telemetry through the trained
 * models (plan Task 7). The prepared replay is a retained legacy path (regression
 * tests, backward compatibility) and is NO LONGER LISTED - its code and tests stay
 * (D03 / plan Task 9). Which mode a visit starts in is decided by `loadConfig`,
 * which always answers Live.
 */
export const DATA_MODE_OPTIONS: ReadonlyArray<{
  value: OperationMode;
  label: string;
}> = [
  { value: "LIVE_MODEL_RUNTIME", label: "Live camera (trained models)" },
  { value: "CONSTRUCTED_SCENARIO_RUNTIME", label: CONSTRUCTED_MODE_LABEL },
];

/** The sentence under the controls for each mode. */
export const DATA_MODE_NOTE: Record<OperationMode, string> = {
  LIVE_MODEL_RUNTIME:
    "Vision: camera → trained vision model (named on the line below) · Telemetry: prepared raw features → trained XGBoost. Frontal-camera accuracy is experimental.",
  PREPARED_SESSION_RUNTIME:
    "Legacy / test-only replay, not the Live system: prepared probabilities and local risk logic, with no trained model and no backend. The camera preview does not drive it. It is kept for regression tests and backward compatibility, and the next page load starts on Live again. Evidence older than a fixed 3 s counts as expired here; the freshness setting applies to Live sessions only.",
  // The constructed scenario shows no note (plan Task 7): the player banner says
  // "not live" instead. App renders the note only when it is non-empty.
  CONSTRUCTED_SCENARIO_RUNTIME: "",
};
