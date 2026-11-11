import type { RiskUpdate } from "../types";

/**
 * The window the Signal Inspector and the Explanation show. `null` follows the newest window,
 * so a running session and a freshly loaded one both open on their latest window; a number is a
 * window the person pinned by clicking it, kept while newer windows arrive. A pinned window that
 * has left the page's history (500 windows) falls back to the newest.
 */
export const selectRecord = (
  history: readonly RiskUpdate[],
  selectedWindowId: number | null,
): RiskUpdate | undefined => {
  const latest = history[history.length - 1];
  if (selectedWindowId === null) return latest;
  return (
    history.find((record) => record.window_id === selectedWindowId) ?? latest
  );
};

/**
 * What the selection bar says about the window on screen: which one, and whether the person pinned
 * it. A pin whose window has left the history is NOT reported as pinned - `selectRecord` already
 * shows the newest window then, and the bar must not claim a pin it cannot show.
 */
export const describeSelection = (
  history: readonly RiskUpdate[],
  selectedWindowId: number | null,
): { windowId: number; pinned: boolean } | null => {
  const shown = selectRecord(history, selectedWindowId);
  if (shown === undefined) return null;
  return {
    windowId: shown.window_id,
    pinned: selectedWindowId !== null && shown.window_id === selectedWindowId,
  };
};
