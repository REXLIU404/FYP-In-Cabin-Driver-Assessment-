"""Turn DMD annotation intervals into the frame numbers we extract.

Sampling is interval-aligned: each interval contributes ``frame_start``,
``frame_start + step``, ... up to ``frame_end`` inclusive. A frame claimed by two
different driver actions is ambiguous ground truth, so it is DROPPED and counted -
never assigned to whichever action happens to be read first.
"""
from __future__ import annotations

DRIVER_PREFIX = "driver_actions/"


def frame_indices(intervals: list[dict], step: int) -> list[int]:
    """Sorted, de-duplicated sample frame numbers for one action's intervals."""
    if step <= 0:
        raise ValueError("step must be positive")
    out: set[int] = set()
    for interval in intervals:
        start, end = int(interval["frame_start"]), int(interval["frame_end"])
        out.update(range(start, end + 1, step))
    return sorted(out)


def labelled_frames(actions: dict, step: int) -> tuple[dict[int, list[str]], dict[str, int]]:
    """``{frame: [action names]}`` plus ``{"conflicts": n, "kept": n}``.

    Only ``driver_actions/*`` entries participate; every other action type (gaze,
    hands, talking) is ignored. A frame with more than one driver action is dropped.
    """
    claims: dict[int, list[str]] = {}
    for action in actions.values():
        kind = action.get("type", "")
        if not kind.startswith(DRIVER_PREFIX):
            continue
        name = kind.split("/", 1)[1]
        for frame in frame_indices(action.get("frame_intervals", []), step):
            claims.setdefault(frame, []).append(name)
    frames = {f: names for f, names in claims.items() if len(names) == 1}
    conflicts = sum(1 for names in claims.values() if len(names) > 1)
    return frames, {"conflicts": conflicts, "kept": len(frames)}
