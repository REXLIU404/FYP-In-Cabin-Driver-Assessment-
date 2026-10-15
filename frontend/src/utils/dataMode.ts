import type { OperationMode } from "../types";

/**
 * The "Data mode" choices. Live is the system and is listed first; the prepared
 * replay is a retained legacy path (regression tests, backward compatibility) and is
 * labelled as such, so choosing it is a deliberate act and not a quiet default
 * (D03 / plan Task 9). Which mode a visit starts in is decided by `loadConfig`,
 * which always answers Live.
 */
export const DATA_MODE_OPTIONS: ReadonlyArray<{
  value: OperationMode;
  label: string;
}> = [
  { value: "LIVE_MODEL_RUNTIME", label: "Live trained models" },
  {
    value: "PREPARED_SESSION_RUNTIME",
    label: "Prepared replay (legacy, test-only)",
  },
];

/** The sentence under the controls for each mode. */
export const DATA_MODE_NOTE: Record<OperationMode, string> = {
  LIVE_MODEL_RUNTIME:
    "Vision: camera → trained MobileNetV3 · Telemetry: prepared raw features → trained XGBoost. Frontal-camera accuracy is experimental.",
  PREPARED_SESSION_RUNTIME:
    "Legacy / test-only replay, not the Live system: prepared probabilities and local risk logic, with no trained model and no backend. The camera preview does not drive it. It is kept for regression tests and backward compatibility, and the next page load starts on Live again. Evidence older than a fixed 3 s counts as expired here; the freshness setting applies to Live sessions only.",
};
