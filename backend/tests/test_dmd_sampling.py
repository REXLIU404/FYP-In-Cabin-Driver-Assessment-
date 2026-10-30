"""scripts/dmd_common.py / dmd_sampling.py / dmd_extract.py: sampling, splits, extraction."""
import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
COMMON = REPO / "scripts" / "dmd_common.py"
# scripts/ is not a package: the modules import each other by bare name.
sys.path.insert(0, str(REPO / "scripts"))


def _load():
    spec = importlib.util.spec_from_file_location("dmd_common", COMMON)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_mapping_has_the_ten_classes_and_excludes_the_rest():
    m = _load()
    assert m.ACTION_TO_CLASS == {
        "safe_drive": "c0", "texting_right": "c1", "phonecall_right": "c2",
        "texting_left": "c3", "phonecall_left": "c4", "radio": "c5",
        "drinking": "c6", "reach_backseat": "c7", "hair_and_makeup": "c8",
        "talking_to_passenger": "c9",
    }
    assert m.EXCLUDED_ACTIONS == frozenset(
        {"reach_side", "unclassified", "change_gear", "standstill_or_waiting"})


def test_subject_is_parsed_from_the_session_name():
    m = _load()
    assert m.subject_of("gA_5_s1_2019-03-08T10;57;00+01;00") == "gA_5"
    assert m.subject_of("gB_10_s3_2019-03-13T14;22;40+01;00") == "gB_10"


def test_split_table_covers_six_subjects_and_disjoint():
    m = _load()
    assert m.SPLITS == {
        "train": ("gA_1", "gA_5", "gB_6"),
        "val": ("gB_10",),
        "test": ("gC_13", "gE_29"),
    }
    seen = [s for v in m.SPLITS.values() for s in v]
    assert len(seen) == len(set(seen)) == 6
    assert all(m.split_of(s) == name for name, subs in m.SPLITS.items() for s in subs)


def test_class_of_returns_none_for_excluded_actions():
    m = _load()
    assert m.class_of("reach_backseat") == "c7"
    assert m.class_of("reach_side") is None
    assert m.class_of("change_gear") is None


SAMPLING = REPO / "scripts" / "dmd_sampling.py"


def _load_sampling():
    spec = importlib.util.spec_from_file_location("dmd_sampling", SAMPLING)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_frame_indices_starts_at_frame_start_and_steps():
    s = _load_sampling()
    intervals = [{"frame_start": 100, "frame_end": 160}]
    assert s.frame_indices(intervals, step=30) == [100, 130, 160]


def test_frame_indices_drops_tail_shorter_than_a_step():
    s = _load_sampling()
    assert s.frame_indices([{"frame_start": 0, "frame_end": 29}], step=30) == [0]


def test_frame_indices_unions_and_sorts_multiple_intervals():
    s = _load_sampling()
    intervals = [{"frame_start": 60, "frame_end": 90},
                 {"frame_start": 0, "frame_end": 10}]
    assert s.frame_indices(intervals, step=30) == [0, 60, 90]


def test_labelled_frames_keeps_single_label_and_reports_conflicts():
    s = _load_sampling()
    actions = {
        "0": {"type": "driver_actions/safe_drive",
              "frame_intervals": [{"frame_start": 0, "frame_end": 10}]},
        "1": {"type": "driver_actions/radio",
              "frame_intervals": [{"frame_start": 5, "frame_end": 40}]},
        "2": {"type": "gaze_on_road/looking_road",
              "frame_intervals": [{"frame_start": 0, "frame_end": 99}]},
    }
    frames, stats = s.labelled_frames(actions, step=5)
    # frames 5 and 10 are claimed by BOTH safe_drive and radio -> dropped, counted
    assert frames == {0: ["safe_drive"],
                      15: ["radio"], 20: ["radio"], 25: ["radio"],
                      30: ["radio"], 35: ["radio"], 40: ["radio"]}
    assert stats == {"conflicts": 2, "kept": 7}


def test_labelled_frames_ignores_non_driver_actions():
    s = _load_sampling()
    actions = {"0": {"type": "hands_using_wheel/both",
                     "frame_intervals": [{"frame_start": 0, "frame_end": 99}]}}
    frames, stats = s.labelled_frames(actions, step=30)
    assert frames == {}
    assert stats == {"conflicts": 0, "kept": 0}


EXTRACT = REPO / "scripts" / "dmd_extract.py"


def _load_extract():
    spec = importlib.util.spec_from_file_location("dmd_extract", EXTRACT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def synthetic_video(tmp_path):
    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg not installed")
    video = tmp_path / "gA_1_s1_test_rgb_body.mp4"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-f", "lavfi",
         "-i", "testsrc=duration=2:size=64x64:rate=30", "-pix_fmt", "yuv420p", str(video)],
        check=True)
    return video


def test_extract_session_applies_the_body_sync_shift(synthetic_video, tmp_path):
    e = _load_extract()
    actions = {
        "0": {"type": "driver_actions/safe_drive",
              "frame_intervals": [{"frame_start": 10, "frame_end": 40}]},
    }
    rows = e.extract_session(
        synthetic_video, actions, tmp_path / "out",
        subject="gA_1", session="gA_1_s1_test", step=10, fps=30.0, shift=5)
    # annotation 10/20/30/40 -> body 5/15/25/35 (body_idx = annotation_idx - shift)
    assert [(r["annotation_frame_idx"], r["body_frame_idx"]) for r in rows] == [
        (10, 5), (20, 15), (30, 25), (40, 35)]
    assert {r["effective_shift"] for r in rows} == {5}
    for row in rows:
        assert (tmp_path / "out" / row["file"]).is_file()
        assert (tmp_path / "out" / row["file"]).stat().st_size > 0
    assert rows[0]["split"] == "train"


def test_negative_body_index_is_dropped_not_clamped(synthetic_video, tmp_path):
    e = _load_extract()
    actions = {"0": {"type": "driver_actions/safe_drive",
                     "frame_intervals": [{"frame_start": 0, "frame_end": 20}]}}
    # shift 15 kills annotation frames 0 and 10 (body -15, -5); 20 survives (body 5)
    rows = e.extract_session(
        synthetic_video, actions, tmp_path / "out",
        subject="gA_1", session="gA_1_s1_test", step=10, fps=30.0, shift=15)
    assert [r["annotation_frame_idx"] for r in rows] == [20]
    assert [r["body_frame_idx"] for r in rows] == [5]


def test_extract_session_skips_excluded_actions(synthetic_video, tmp_path):
    e = _load_extract()
    actions = {"0": {"type": "driver_actions/reach_side",
                     "frame_intervals": [{"frame_start": 0, "frame_end": 59}]}}
    rows = e.extract_session(
        synthetic_video, actions, tmp_path / "out",
        subject="gA_1", session="gA_1_s1_test", step=10, fps=30.0, shift=0)
    assert rows == []


def test_run_reads_frame_shift_and_honours_the_override(tmp_path, synthetic_video):
    e = _load_extract()
    root = tmp_path / "dmd"
    session_dir = root / "dmd" / "gA" / "1" / "s1"
    session_dir.mkdir(parents=True)
    shutil.copy(synthetic_video, session_dir / "gA_1_s1_test_rgb_body.mp4")
    (session_dir / "gA_1_s1_test_rgb_ann_distraction.json").write_text(json.dumps(
        {"openlabel": {
            "streams": {"body_camera": {"stream_properties": {
                "sync": {"frame_shift": 12}}}},
            "actions": {"0": {"type": "driver_actions/safe_drive",
                              "frame_intervals": [{"frame_start": 20, "frame_end": 40}]}} }}))
    overrides = tmp_path / "overrides.json"
    overrides.write_text(json.dumps({"overrides": {"gA_1_s1_test": 7}}))
    summary = e.run(root, tmp_path / "out", step=10, fps=30.0, overrides=overrides)
    assert summary["sessions"] == 1
    assert summary["sessions_detail"][0]["effective_shift"] == 7
    assert summary["sessions_detail"][0]["sync_status"] == "OVERRIDDEN"
    manifest = (tmp_path / "out" / "sampling_manifest.csv").read_text().splitlines()
    assert manifest[0].split(",") == [
        "subject", "session", "split", "action", "class_id",
        "annotation_frame_idx", "body_frame_idx", "effective_shift", "video", "file"]
    assert len(manifest) == 4   # 20/30/40 -> body 13/23/33
    log = json.loads((tmp_path / "out" / "extraction_log.json").read_text())
    assert log["sessions_detail"][0]["subject"] == "gA_1"
