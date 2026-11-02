import { updateAlertState, type AlertFsmState } from "../../../ai/src/alertFsm";
import type { RiskUpdate } from "../types";

/**
 * Overlays the wall-clock Alert State Manager on a freshly built record.
 *
 * The FSM replaces the per-window severity, but its memory (`state.severity`)
 * is never null. Copying it onto every record would give a window with no
 * assessment (`RiskLevel === null`) a non-null `AlertSeverity` - the record would
 * say "no RiskLevel" and "CAUTION" at once, breaking the four-fields-null
 * contract. The emitted severity is therefore null exactly when the level is.
 * `updateAlertState` accepting `null` compiles either way, so nothing but this
 * function stands between a spread and that contradiction.
 */
export const applyAlertState = (
  record: RiskUpdate,
  previous: AlertFsmState,
  now: number,
): { record: RiskUpdate; state: AlertFsmState } => {
  const state = updateAlertState(previous, record.RiskLevel, now);
  return {
    state,
    record: {
      ...record,
      AlertSeverity: record.RiskLevel === null ? null : state.severity,
    },
  };
};
