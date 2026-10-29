import { LocateFixed } from "lucide-react";

interface SelectionBarProps {
  windowId: number;
  /** true: the person clicked this window; false: the view follows the newest window. */
  pinned: boolean;
  /** true: monitoring is running, so newer windows really do keep arriving (review R9). */
  isMonitoring: boolean;
  onFollowLatest: () => void;
}

/**
 * Which window Signal Inspector, Risk Trends and Explanation are showing, and whether it is pinned.
 * Without it a click silently froze the views on an old window with no way back but another click.
 * "newer windows keep arriving" is only true while monitoring runs: after Pause or Stop the pinned
 * bar says just "pinned" (review R9).
 */
export function SelectionBar({
  windowId,
  pinned,
  isMonitoring,
  onFollowLatest,
}: SelectionBarProps) {
  return (
    <div className={`selection-bar ${pinned ? "selection-bar--pinned" : ""}`}>
      <span>
        Showing <strong>Window {windowId}</strong> ·{" "}
        {pinned
          ? isMonitoring
            ? "pinned; newer windows keep arriving"
            : "pinned"
          : "following the newest window"}
      </span>
      {pinned ? (
        <button type="button" className="button" onClick={onFollowLatest}>
          <LocateFixed size={16} />
          Follow latest
        </button>
      ) : null}
    </div>
  );
}
