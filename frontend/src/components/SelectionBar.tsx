import { LocateFixed } from "lucide-react";

interface SelectionBarProps {
  windowId: number;
  /** true: the person clicked this window; false: the view follows the newest window. */
  pinned: boolean;
  onFollowLatest: () => void;
}

/**
 * Which window Signal Inspector, Risk Trends and Explanation are showing, and whether it is pinned.
 * Without it a click silently froze the views on an old window with no way back but another click.
 */
export function SelectionBar({
  windowId,
  pinned,
  onFollowLatest,
}: SelectionBarProps) {
  return (
    <div className={`selection-bar ${pinned ? "selection-bar--pinned" : ""}`}>
      <span>
        Showing <strong>Window {windowId}</strong> ·{" "}
        {pinned
          ? "pinned; newer windows keep arriving"
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
