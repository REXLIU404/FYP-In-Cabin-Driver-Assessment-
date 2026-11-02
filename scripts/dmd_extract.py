"""Extract 1 FPS DMD body frames for the annotated driver actions.

Two facts this file exists to handle:

* annotation frame numbers live on the FACE timeline. The body video is offset by
  ``openlabel.streams.body_camera.stream_properties.sync.frame_shift``; the body index is
  ``annotation - shift`` and a negative index is DROPPED, never clamped to 0.
* ``gB_10_s3_2019-03-13`` ships a shift of 14 but the cross-correlation recheck estimated
  18-20, so it is pinned to 20 in ``scripts/dmd_shift_overrides.json``. The same file
  records which sessions failed that recheck (MISMATCH) so the report can name them.
"""
from __future__ import annotations

import argparse
import csv
import json
import subprocess
from collections import Counter
from pathlib import Path

from dmd_common import ACTION_TO_CLASS, split_of, subject_of
from dmd_sampling import labelled_frames

MANIFEST_FIELDS = ("subject", "session", "split", "action", "class_id",
                   "annotation_frame_idx", "body_frame_idx", "effective_shift",
                   "video", "file")
DEFAULT_CONFIG = Path(__file__).with_name("dmd_shift_overrides.json")


def _extract_one(video: Path, body_idx: int, fps: float, out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-v", "error", "-ss", f"{body_idx / fps:.6f}", "-i", str(video),
         "-frames:v", "1", "-q:v", "2", str(out)],
        check=True)


def body_frame_shift(annotation: dict, session: str, config: dict) -> tuple[int, str]:
    """``(effective_shift, sync_status)`` with status OVERRIDDEN / MISMATCH / OFFICIAL."""
    official = int(annotation["streams"]["body_camera"]["stream_properties"]
                   ["sync"]["frame_shift"])
    overrides = config.get("overrides", {})
    if session in overrides:
        return int(overrides[session]), "OVERRIDDEN"
    return official, config.get("review", {}).get(session, "OFFICIAL")


def extract_session(video: Path, actions: dict, out_dir: Path, *, subject: str,
                    session: str, step: int, fps: float, shift: int) -> list[dict]:
    """Extract the sampled frames of ONE session; returns manifest-ready rows."""
    frames, _stats = labelled_frames(actions, step)
    split = split_of(subject)
    rows: list[dict] = []
    for annotation_idx in sorted(frames):
        action = frames[annotation_idx][0]
        class_id = ACTION_TO_CLASS.get(action)
        if class_id is None:
            continue
        body_idx = annotation_idx - shift
        if body_idx < 0:
            continue  # counted by run() as (sampled - written)
        rel = Path(subject) / session / class_id / f"{body_idx:08d}.jpg"
        try:
            _extract_one(video, body_idx, fps, out_dir / rel)
        except subprocess.CalledProcessError:
            continue
        rows.append({"subject": subject, "session": session, "split": split,
                     "action": action, "class_id": class_id,
                     "annotation_frame_idx": annotation_idx,
                     "body_frame_idx": body_idx, "effective_shift": shift,
                     "video": video.name, "file": rel.as_posix()})
    return rows


def _iter_sessions(data_root: Path):
    for path in sorted(data_root.rglob("*_rgb_ann_distraction.json")):
        video = path.with_name(path.name.replace(
            "_rgb_ann_distraction.json", "_rgb_body.mp4"))
        if video.exists():
            yield path, video


def run(data_root: Path, out_root: Path, *, step: int = 30, fps: float = 30.0,
        overrides: Path | None = None) -> dict:
    """Walk every annotated session under ``data_root`` and write manifest + log."""
    config = json.loads(Path(overrides or DEFAULT_CONFIG).read_text())
    out_root.mkdir(parents=True, exist_ok=True)
    all_rows: list[dict] = []
    log_sessions: list[dict] = []
    for ann_path, video in _iter_sessions(data_root):
        session = ann_path.name.replace("_rgb_ann_distraction.json", "")
        subject = subject_of(session)
        openlabel = json.loads(ann_path.read_text())["openlabel"]
        actions = openlabel.get("actions", {})
        shift, status = body_frame_shift(openlabel, session, config)
        rows = extract_session(video, actions, out_root / "frames", subject=subject,
                               session=session, step=step, fps=fps, shift=shift)
        _frames, stats = labelled_frames(actions, step)
        log_sessions.append({
            "subject": subject, "session": session, "video": video.name,
            "effective_shift": shift, "sync_status": status,
            "sampled": stats["kept"], "conflicts": stats["conflicts"],
            "written": len(rows), "skipped": stats["kept"] - len(rows),
            "by_class": dict(Counter(r["class_id"] for r in rows)),
        })
        all_rows.extend(rows)

    with (out_root / "sampling_manifest.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=MANIFEST_FIELDS)
        writer.writeheader()
        writer.writerows(all_rows)

    summary = {
        "data_root": str(data_root), "step": step, "fps": fps,
        "sessions": len(log_sessions), "frames": len(all_rows),
        "sync_status_counts": dict(Counter(s["sync_status"] for s in log_sessions)),
        "by_split": dict(Counter(r["split"] for r in all_rows)),
        "by_class": dict(Counter(r["class_id"] for r in all_rows)),
        "sessions_detail": log_sessions,
    }
    (out_root / "extraction_log.json").write_text(json.dumps(summary, indent=2))
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("data_root", type=Path)
    parser.add_argument("out_root", type=Path)
    parser.add_argument("--step", type=int, default=30)
    parser.add_argument("--fps", type=float, default=30.0)
    parser.add_argument("--overrides", type=Path, default=None)
    args = parser.parse_args()
    summary = run(args.data_root, args.out_root, step=args.step, fps=args.fps,
                  overrides=args.overrides)
    print(json.dumps({k: summary[k] for k in
                      ("sessions", "frames", "by_split", "sync_status_counts")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
