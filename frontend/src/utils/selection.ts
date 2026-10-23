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
  return history.find((record) => record.window_id === selectedWindowId) ?? latest;
};
