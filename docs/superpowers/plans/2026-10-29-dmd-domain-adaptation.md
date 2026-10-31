# DMD 域适应微调 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 `stable_mobilenet_v3_large` 上做一次受试者隔离的 body 视角域适应微调，产出可被现有 candidate 机制加载的模型包与可写进报告的 UNEXPOSED 同集评估。

**Architecture:** 先用 ffmpeg 按标注区间对 19 个 DMD session 抽 1 FPS 帧（6 受试者），按受试者划分 train/val/test；再部分解冻 MobileNetV3（最后 2 个 stage + classifier）训练，BatchNorm 全程 eval；最后在 test 上做 zero-shot 与 fine-tuned 的同集对比，阈值在 val 上选，模型以 candidate 包形式接入现有 `DRA_ACTIVE_VISION` 机制。

**Tech Stack:** Python 3.13 / PyTorch 2.12 (MPS) / torchvision / ONNX 1.21 / onnxruntime / ffmpeg 9 / pytest

**Spec:** `docs/superpowers/specs/2026-10-29-dmd-domain-adaptation-design.md`

## Global Constraints

- 分支：`fyp2/dmd-adaptation`。只在本分支提交，**不 push**。
- 原始 DMD 数据根：`/Users/liu/Desktop/DMD`，**只读**，不得修改或移动。
- 抽帧产物目录：`/Users/liu/Desktop/fyp2/ml-training/FYP2-DMD-body-v1/`（git 外），**不得**写入
  `FYP2-DMD-zero-shot/` 或 `FYP2-DMD-expanded/`。
- 不修改 `backend/app/`、`frontend/`、`demo/scenarios/viva_v1.json`、
  `ai/prototype-data/prepared_sessions/session_001/telemetry.csv`。
- 工作区已有 4 个与本任务无关的改动（`backend/tests/test_build_dataset_replay.py`、
  `AGENTS.md`、`demo/scenarios/viva_compact.json`、一张 PNG），提交时**不得**把它们加入。
- 类别映射固定（`FYP2-DMD-zero-shot/manifests/label_mapping.json`）：
  `safe_drive→c0`、`texting_right→c1`、`phonecall_right→c2`、`texting_left→c3`、
  `phonecall_left→c4`、`radio→c5`、`drinking→c6`、`reach_backseat→c7`、
  `hair_and_makeup→c8`、`talking_to_passenger→c9`。
  排除：`reach_side`、`unclassified`、`change_gear`、`standstill_or_waiting`。
- 划分固定：train = `gA_1` + `gA_5` + `gB_6`；val = `gB_10`；test = `gC_13` + `gE_29`。
- 训练 30 轮上限，无 60 轮放宽；全部 BatchNorm2d 每 epoch 强制 `eval()`。
- 不做类别加权（主结果）；不做温度校准。
- 预处理与生产一致：RGB → 双线性 224×224 → /255 → ImageNet mean/std。
- 不做水平翻转、不做随机旋转。
- 现有测试必须全绿：`pytest`、`vitest`、`tsc`、`eslint`、`build`。

## File Structure

| 文件 | 职责 |
|---|---|
| `scripts/dmd_common.py` | 类别映射、划分表、session 解析、路径常量 |
| `scripts/dmd_sampling.py` | 标注区间 → 采样帧号（纯函数） |
| `scripts/dmd_extract.py` | 调 ffmpeg 抽帧，写 `sampling_manifest.csv` / `extraction_log.json` |
| `scripts/dmd_dataset.py` | PyTorch Dataset：读 manifest、增强、划分过滤 |
| `scripts/dmd_train.py` | 训练循环、BN 冻结与断言、保存 checkpoint |
| `scripts/dmd_threshold.py` | 在 val 上选阈值（纯函数） |
| `scripts/dmd_evaluate.py` | 10 类 / 二分类指标、混淆矩阵、JSON 输出 |
| `scripts/dmd_export_candidate.py` | ONNX 导出、runtime manifest、candidate 包 |
| `backend/tests/test_dmd_sampling.py` | 采样与划分的单元测试 |
| `backend/tests/test_dmd_dataset.py` | Dataset 与增强的单元测试 |
| `backend/tests/test_dmd_threshold.py` | 阈值选择的单元测试 |
| `backend/tests/test_dmd_export.py` | candidate 包通过 `validate_package` |

脚本沿用现有 `scripts/` 的扁平布局，测试通过 `importlib.util.spec_from_file_location`
加载（`scripts/` 不是 package，与 `test_build_dataset_replay.py` 一致）。

---

### Task 1: 类别映射与划分表

**Files:**
- Create: `scripts/dmd_common.py`
- Test: `backend/tests/test_dmd_sampling.py`（本任务只加第一个测试类）

**Interfaces:**
- Consumes: 无
- Produces:
  - `ACTION_TO_CLASS: dict[str, str]`（10 项）
  - `EXCLUDED_ACTIONS: frozenset[str]`
  - `SPLITS: dict[str, tuple[str, ...]]`
  - `subject_of(session_name: str) -> str`
  - `class_of(action: str) -> str | None`
  - `split_of(subject: str) -> str`

- [ ] **Step 1: 写失败测试**

```python
"""scripts/dmd_common.py: class mapping, subject parsing and the fixed split table."""
import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
COMMON = REPO / "scripts" / "dmd_common.py"


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
```

- [ ] **Step 2: 跑测试确认失败**

Run: `PYTHONPATH=backend .venv/bin/python -m pytest backend/tests/test_dmd_sampling.py -q`
Expected: FAIL — `FileNotFoundError`（`scripts/dmd_common.py` 不存在）

- [ ] **Step 3: 写实现**

```python
"""Shared constants for the DMD body-view domain adaptation.

The class mapping is the one the zero-shot evaluation already used
(`FYP2-DMD-zero-shot/manifests/label_mapping.json`); the split is subject-level so no
frame from a test subject can reach training, and every split keeps `c7`
(`reach_backseat`) because that action only appears in each subject's s3 session.
"""
from __future__ import annotations

ACTION_TO_CLASS = {
    "safe_drive": "c0",
    "texting_right": "c1",
    "phonecall_right": "c2",
    "texting_left": "c3",
    "phonecall_left": "c4",
    "radio": "c5",
    "drinking": "c6",
    "reach_backseat": "c7",
    "hair_and_makeup": "c8",
    "talking_to_passenger": "c9",
}

EXCLUDED_ACTIONS = frozenset(
    {"reach_side", "unclassified", "change_gear", "standstill_or_waiting"})

SPLITS = {
    "train": ("gA_1", "gA_5", "gB_6"),
    "val": ("gB_10",),
    "test": ("gC_13", "gE_29"),
}

CLASS_IDS = tuple(f"c{i}" for i in range(10))
CLASS_NAMES = (
    "safe_driving", "texting_right", "talking_phone_right", "texting_left",
    "talking_phone_left", "operating_radio", "drinking", "reaching_behind",
    "hair_makeup", "talking_to_passenger",
)


def subject_of(session_name: str) -> str:
    """``gA_5_s1_2019-03-08T10;57;00+01;00`` -> ``gA_5``."""
    return "_".join(session_name.split("_")[:2])


def class_of(action: str) -> str | None:
    """The runtime class id for a DMD driver action, or None when it is excluded."""
    return ACTION_TO_CLASS.get(action)


def split_of(subject: str) -> str:
    for name, subjects in SPLITS.items():
        if subject in subjects:
            return name
    raise KeyError(f"subject {subject!r} is not in the split table")
```

- [ ] **Step 4: 跑测试确认通过**

Run: `PYTHONPATH=backend .venv/bin/python -m pytest backend/tests/test_dmd_sampling.py -q`
Expected: 4 passed

- [ ] **Step 5: 提交**

```bash
git add scripts/dmd_common.py backend/tests/test_dmd_sampling.py
git commit -m "feat(dmd): class mapping and subject-level split table"
```

---

### Task 2: 标注区间到采样帧号

**Files:**
- Create: `scripts/dmd_sampling.py`
- Modify: `backend/tests/test_dmd_sampling.py`（追加测试）

**Interfaces:**
- Consumes: `scripts/dmd_common.py`（无直接依赖，独立纯函数）
- Produces:
  - `frame_indices(intervals: list[dict], step: int) -> list[int]`
  - `labelled_frames(actions: dict, step: int) -> tuple[dict[int, list[str]], dict[str, int]]`

- [ ] **Step 1: 写失败测试**

追加到 `backend/tests/test_dmd_sampling.py`：

```python
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
```

- [ ] **Step 2: 跑测试确认失败**

Run: `PYTHONPATH=backend .venv/bin/python -m pytest backend/tests/test_dmd_sampling.py -q -k "frame_indices or labelled_frames"`
Expected: FAIL — `FileNotFoundError`

- [ ] **Step 3: 写实现**

```python
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
```

- [ ] **Step 4: 跑测试确认通过**

Run: `PYTHONPATH=backend .venv/bin/python -m pytest backend/tests/test_dmd_sampling.py -q`
Expected: 9 passed

- [ ] **Step 5: 提交**

```bash
git add scripts/dmd_sampling.py backend/tests/test_dmd_sampling.py
git commit -m "feat(dmd): interval-aligned frame sampling with conflict dropping"
```
---

### Task 3: ffmpeg 抽帧与 manifest

**Files:**
- Create: `scripts/dmd_extract.py`
- Test: `backend/tests/test_dmd_sampling.py`（追加测抽帧，用合成视频）

**Interfaces:**
- Consumes: `dmd_common.ACTION_TO_CLASS` / `subject_of` / `split_of`；`dmd_sampling.labelled_frames`
- Produces:
  - `extract_session(video: Path, actions: dict, out_dir: Path, *, subject: str, session: str, step: int, fps: float, shift: int) -> list[dict]`
  - `body_frame_shift(annotation: dict, session: str, config: dict) -> tuple[int, str]`
  - `run(data_root: Path, out_root: Path, *, step: int = 30, fps: float = 30.0, overrides: Path | None = None) -> dict`
  - manifest 行字段：`subject, session, split, action, class_id, annotation_frame_idx,
    body_frame_idx, effective_shift, video, file`

- [ ] **Step 1: 写失败测试**

追加到 `backend/tests/test_dmd_sampling.py`：

```python
import json
import shutil
import subprocess

import pytest

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
    overrides.write_text(json.dumps({"gA_1_s1_test": 7}))
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
```

- [ ] **Step 2: 跑测试确认失败**

Run: `PYTHONPATH=backend .venv/bin/python -m pytest backend/tests/test_dmd_sampling.py -q -k extract or run_writes`
Expected: FAIL — `FileNotFoundError`

- [ ] **Step 3: 写实现**

```python
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
```

同时创建 `scripts/dmd_shift_overrides.json`（值来自 `DMD-data-prep/data/inventory/shift_overrides.json`
与 `FYP2-DMD-expanded/logs/sync_check.log`，复制进仓库以保证可复现）：

```json
{
  "overrides": {
    "gB_10_s3_2019-03-13T14;22;40+01;00": 20
  },
  "review": {
    "gB_6_s1_2019-03-11T13;55;14+01;00": "MISMATCH",
    "gB_6_s2_2019-03-11T13;46;14+01;00": "MISMATCH",
    "gC_13_s1_2019-03-04T10;26;12+01;00": "MISMATCH",
    "gC_13_s2_2019-03-04T10;11;37+01;00": "MISMATCH"
  }
}
```

- [ ] **Step 4: 跑测试确认通过**

Run: `PYTHONPATH=backend:scripts .venv/bin/python -m pytest backend/tests/test_dmd_sampling.py -q`
Expected: 13 passed（4 个抽帧测试在无 ffmpeg 时 skip）

- [ ] **Step 5: 在真实数据上跑一次**

```bash
PYTHONPATH=scripts .venv/bin/python scripts/dmd_extract.py \
  /Users/liu/Desktop/DMD /Users/liu/Desktop/fyp2/ml-training/FYP2-DMD-body-v1
```

Expected: `sessions: 19`；`sync_status_counts` 含 `OVERRIDDEN: 1`（gB_10_s3_0313）与
`MISMATCH: 4`；`by_split` 与 spec 3.2 的受试者一致；每个 session 的 `skipped` 为 0 或
给出原因。`extraction_log.json` 里每个 session 都有 `effective_shift` 与 `sync_status`。

- [ ] **Step 6: 人工核对 20 帧（按 body 帧号）**

从 manifest 随机抽 20 行，用 `body_frame_idx` 单独导出同一视频的同帧，与抽出的文件
比 `sha256` 应当一致；若不一致，说明 seek 精度问题，把 `_extract_one` 改成
`["ffmpeg","-v","error","-i",video,"-vf",f"select=eq(n\\,{body_idx})","-vsync","0",
"-frames:v","1",...]` 后重跑。同时人工看 5 对 `(annotation_frame_idx, body_frame_idx)`
在视频里的内容，确认后者才是动作发生的时刻。核对结果写进
`docs/evidence/2026-10-29/dmd-adaptation/extraction_check.md`。

- [ ] **Step 7: 提交**

```bash
git add scripts/dmd_extract.py scripts/dmd_shift_overrides.json backend/tests/test_dmd_sampling.py
git commit -m "feat(dmd): ffmpeg extraction with body sync shift and manifest log"
```

---

### Task 4: PyTorch Dataset

**Files:**
- Create: `scripts/dmd_dataset.py`
- Test: `backend/tests/test_dmd_dataset.py`

**Interfaces:**
- Consumes: manifest 行（Task 3）
- Produces:
  - `DMDFrames(manifest_csv: Path, split: str, transform)`
  - `DMDFrames.labels() -> list[int]`
  - `build_transform(train: bool) -> torchvision.transforms.Compose`

- [ ] **Step 1: 写失败测试**

```python
"""scripts/dmd_dataset.py: manifest-driven dataset, transforms and split filtering."""
import csv
import importlib.util
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
DATASET = REPO / "scripts" / "dmd_dataset.py"


def _load():
    spec = importlib.util.spec_from_file_location("dmd_dataset", DATASET)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_manifest(tmp_path, rows):
    path = tmp_path / "sampling_manifest.csv"
    with path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=[
            "subject", "session", "split", "action", "class_id",
            "annotation_frame_idx", "body_frame_idx", "effective_shift", "video", "file"])
        writer.writeheader()
        writer.writerows(rows)
    return path


def _tiny_jpeg(path):
    from PIL import Image
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (32, 32), (10, 20, 30)).save(path, "JPEG")


def test_dataset_filters_by_split_and_maps_class_to_index(tmp_path):
    d = _load()
    rows = []
    for i, (split, cls) in enumerate([("train", "c0"), ("train", "c7"),
                                      ("val", "c3"), ("test", "c9")]):
        rel = f"gA_1/s{i}/c/cls_{i}.jpg"
        _tiny_jpeg(tmp_path / "frames" / rel)
        rows.append({"subject": "gA_1", "session": f"s{i}", "split": split,
                     "action": "x", "class_id": cls, "annotation_frame_idx": i + 40,
                     "body_frame_idx": i, "effective_shift": 40,
                     "video": "v.mp4", "file": rel})
    manifest = _write_manifest(tmp_path, rows)
    train = d.DMDFrames(manifest, "train", transform=None, root=tmp_path / "frames")
    assert len(train) == 2
    assert train.labels() == [0, 7]
    assert len(d.DMDFrames(manifest, "test", transform=None,
                           root=tmp_path / "frames")) == 1


def test_train_transform_never_flips_horizontally():
    d = _load()
    names = [type(t).__name__ for t in d.build_transform(train=True).transforms]
    assert "RandomHorizontalFlip" not in names
    assert "RandomRotation" not in names
    assert "RandomResizedCrop" in names


def test_eval_transform_is_deterministic_resize_only():
    d = _load()
    names = [type(t).__name__ for t in d.build_transform(train=False).transforms]
    assert names[0] == "Resize"
    assert "RandomResizedCrop" not in names
```

- [ ] **Step 2: 跑测试确认失败**

Run: `PYTHONPATH=backend .venv/bin/python -m pytest backend/tests/test_dmd_dataset.py -q`
Expected: FAIL — `FileNotFoundError`

- [ ] **Step 3: 写实现**

```python
"""Manifest-driven dataset for the DMD body frames.

The split column is authoritative: a subject appears in exactly one split (Task 1), so
filtering by `split` is a subject-level holdout. Horizontal flip and rotation are
forbidden - left/right hand is label-bearing and the camera angle is fixed.
"""
from __future__ import annotations

import csv
from pathlib import Path

from PIL import Image
from torch.utils.data import Dataset

CLASS_IDS = tuple(f"c{i}" for i in range(10))
IMAGENET_MEAN = (0.485, 0.456, 0.406)
IMAGENET_STD = (0.229, 0.224, 0.225)


def build_transform(train: bool):
    from torchvision import transforms

    if train:
        return transforms.Compose([
            transforms.RandomResizedCrop(224, scale=(0.7, 1.0), ratio=(0.85, 1.18)),
            transforms.ColorJitter(brightness=0.2, contrast=0.2, saturation=0.2, hue=0.05),
            transforms.ToTensor(),
            transforms.Normalize(IMAGENET_MEAN, IMAGENET_STD),
        ])
    return transforms.Compose([
        transforms.Resize((224, 224), interpolation=transforms.InterpolationMode.BILINEAR),
        transforms.ToTensor(),
        transforms.Normalize(IMAGENET_MEAN, IMAGENET_STD),
    ])


class DMDFrames(Dataset):
    def __init__(self, manifest_csv: Path, split: str, transform=None, root: Path | None = None):
        if split not in ("train", "val", "test"):
            raise ValueError(f"unknown split {split!r}")
        self.root = Path(root) if root is not None else Path(manifest_csv).parent / "frames"
        self.transform = transform
        self.rows = [r for r in csv.DictReader(Path(manifest_csv).open())
                     if r["split"] == split]
        if not self.rows:
            raise ValueError(f"no rows for split {split!r} in {manifest_csv}")

    def __len__(self) -> int:
        return len(self.rows)

    def labels(self) -> list[int]:
        return [CLASS_IDS.index(r["class_id"]) for r in self.rows]

    def __getitem__(self, index: int):
        row = self.rows[index]
        image = Image.open(self.root / row["file"]).convert("RGB")
        tensor = self.transform(image) if self.transform is not None else image
        return tensor, CLASS_IDS.index(row["class_id"])
```

- [ ] **Step 4: 跑测试确认通过**

Run: `PYTHONPATH=backend .venv/bin/python -m pytest backend/tests/test_dmd_dataset.py -q`
Expected: 3 passed

- [ ] **Step 5: 提交**

```bash
git add scripts/dmd_dataset.py backend/tests/test_dmd_dataset.py
git commit -m "feat(dmd): manifest dataset with flip-free transforms"
```

---

### Task 5: 训练循环与 BatchNorm 冻结

**Files:**
- Create: `scripts/dmd_train.py`
- Test: `backend/tests/test_dmd_dataset.py`（追加 BN 断言测试）

**Interfaces:**
- Consumes: `DMDFrames` / `build_transform`（Task 4）
- Produces:
  - `load_stable_checkpoint(model, checkpoint: Path) -> dict`（读 `state_dict`，并校验 `arch` 与 `classes`）
  - `unfreeze_last_blocks(model, blocks: int = 2) -> None`
  - `lock_batchnorm(model) -> None`
  - `assert_batchnorm_locked(model) -> None`（不满足抛 `AssertionError`）
  - `train(...) -> dict`（history + best checkpoint 路径）

- [ ] **Step 1: 写失败测试**

追加到 `backend/tests/test_dmd_dataset.py`：

```python
TRAIN = REPO / "scripts" / "dmd_train.py"


def _load_train():
    spec = importlib.util.spec_from_file_location("dmd_train", TRAIN)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _tiny_model():
    import torch
    from torch import nn
    from torchvision.models import mobilenet_v3_large

    model = mobilenet_v3_large(weights=None, num_classes=10)
    return model


def test_lock_batchnorm_puts_every_bn_in_eval():
    import torch
    t = _load_train()
    model = _tiny_model()
    model.train()
    t.lock_batchnorm(model)
    bns = [m for m in model.modules() if isinstance(m, torch.nn.BatchNorm2d)]
    assert bns and all(not m.training for m in bns)


def test_assert_batchnorm_locked_raises_when_one_epoch_leaves_bn_training():
    import torch
    t = _load_train()
    model = _tiny_model()
    t.lock_batchnorm(model)
    t.assert_batchnorm_locked(model)
    next(m for m in model.modules() if isinstance(m, torch.nn.BatchNorm2d)).train()
    with pytest.raises(AssertionError, match="BatchNorm"):
        t.assert_batchnorm_locked(model)


def test_unfreeze_last_blocks_keeps_early_features_frozen():
    import torch
    t = _load_train()
    model = _tiny_model()
    t.unfreeze_last_blocks(model, blocks=2)
    assert all(not p.requires_grad for p in model.features[:-2].parameters())
    assert all(p.requires_grad for p in model.features[-2:].parameters())
    assert all(p.requires_grad for p in model.classifier.parameters())


def test_load_stable_checkpoint_rejects_a_bare_state_dict(tmp_path):
    import torch
    t = _load_train()
    torch.save(_tiny_model().state_dict(), tmp_path / "bare.pt")
    with pytest.raises(ValueError, match="state_dict"):
        t.load_stable_checkpoint(_tiny_model(), tmp_path / "bare.pt")


def test_load_stable_checkpoint_rejects_a_wrong_class_order(tmp_path):
    import torch
    t = _load_train()
    torch.save({"state_dict": _tiny_model().state_dict(),
                "arch": "mobilenet_v3_large", "classes": ["c1", "c0"]},
               tmp_path / "bad.pt")
    with pytest.raises(ValueError, match="class"):
        t.load_stable_checkpoint(_tiny_model(), tmp_path / "bad.pt")


def test_load_stable_checkpoint_accepts_the_real_stable_layout(tmp_path):
    import torch
    t = _load_train()
    model = _tiny_model()
    torch.save({"state_dict": model.state_dict(), "arch": "mobilenet_v3_large",
                "classes": [f"c{i}" for i in range(10)],
                "idx_to_name": {f"c{i}": f"n{i}" for i in range(10)}},
               tmp_path / "good.pt")
    raw = t.load_stable_checkpoint(model, tmp_path / "good.pt")
    assert raw["arch"] == "mobilenet_v3_large"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `PYTHONPATH=backend .venv/bin/python -m pytest backend/tests/test_dmd_dataset.py -q -k batchnorm or unfreeze`
Expected: FAIL — `FileNotFoundError`

- [ ] **Step 3: 写实现**

```python
"""Fine-tune the stable MobileNetV3 on DMD body frames.

Two rules this file exists to enforce:

* only ``features[-2:]`` and ``classifier`` train (a 2.2k-frame set cannot carry a full
  fine-tune without dragging the backbone off its source distribution);
* every ``BatchNorm2d`` stays in eval mode for the whole run. ``requires_grad=False``
  does NOT stop ``running_mean`` / ``running_var`` from being updated, so ``model.train()``
  would silently replace statistics learned on 15,899 State Farm images with three
  subjects' cabin lighting. The assertion is checked every epoch and aborts the run.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import torch
from torch import nn


def load_stable_checkpoint(model, checkpoint: Path) -> dict:
    """Load the stable checkpoint and verify its arch and class order.

    The stable file is NOT a bare state_dict: it is
    ``{"state_dict": ..., "classes": [...], "idx_to_name": {...}, "arch": "mobilenet_v3_large"}``.
    Passing it straight to ``load_state_dict`` raises a confusing RuntimeError; this
    function fails with a named reason instead.
    """
    raw = torch.load(checkpoint, map_location="cpu")
    if not isinstance(raw, dict) or "state_dict" not in raw:
        raise ValueError(
            "checkpoint must be the stable dict with a 'state_dict' key, not a bare state_dict")
    if raw.get("arch") != "mobilenet_v3_large":
        raise ValueError(f"checkpoint arch is {raw.get('arch')!r}, expected 'mobilenet_v3_large'")
    classes = list(raw.get("classes") or [])
    if classes != [f"c{i}" for i in range(10)]:
        raise ValueError(f"checkpoint class order is {classes}, expected c0..c9")
    model.load_state_dict(raw["state_dict"])
    return raw


def unfreeze_last_blocks(model, blocks: int = 2) -> None:
    """Freeze all, then unfreeze the last ``blocks`` feature blocks and the classifier.

    ``torchvision.mobilenet_v3_large().features`` is a Sequential of 17 blocks (0-16),
    so ``blocks=2`` means block 15 (last inverted residual) and block 16 (final 1x1 conv
    + BN + Hardswish). This is NOT two "stages" in the paper's sense.
    """
    for param in model.parameters():
        param.requires_grad = False
    for module in list(model.features.children())[-blocks:]:
        for param in module.parameters():
            param.requires_grad = True
    for param in model.classifier.parameters():
        param.requires_grad = True


def lock_batchnorm(model) -> None:
    for module in model.modules():
        if isinstance(module, nn.BatchNorm2d):
            module.eval()


def assert_batchnorm_locked(model) -> None:
    offenders = [m for m in model.modules()
                 if isinstance(m, nn.BatchNorm2d) and m.training]
    assert not offenders, (
        f"BatchNorm layers left in training mode after model.train(): {len(offenders)}")


def _epoch(model, loader, criterion, optimizer, device, train: bool) -> tuple[float, list[int], list[int]]:
    model.train() if train else model.eval()
    model.features[:-2].eval()
    lock_batchnorm(model)          # MUST be last: model.train() re-enables BN
    assert_batchnorm_locked(model)
    total, preds, labels = 0.0, [], []
    torch.set_grad_enabled(train)
    for images, target in loader:
        images, target = images.to(device), target.to(device)
        logits = model(images)
        loss = criterion(logits, target)
        if train:
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            optimizer.step()
        total += float(loss) * target.size(0)
        preds.extend(logits.argmax(1).tolist())
        labels.extend(target.tolist())
    torch.set_grad_enabled(True)
    return total / len(loader.dataset), preds, labels


def _macro_f1(preds: list[int], labels: list[int]) -> float:
    from sklearn.metrics import f1_score

    return float(f1_score(labels, preds, average="macro", zero_division=0))


def train(manifest_csv: Path, frames_root: Path, out_dir: Path, *, epochs: int = 30,
          batch_size: int = 32, patience: int = 8, seed: int = 42,
          checkpoint: Path | None = None) -> dict:
    """Train, early-stop on val macro-F1, save the best checkpoint. Returns history."""
    from torch.utils.data import DataLoader
    from torchvision.models import mobilenet_v3_large

    from dmd_dataset import DMDFrames, build_transform

    torch.manual_seed(seed)
    device = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
    model = mobilenet_v3_large(weights=None, num_classes=10)
    if checkpoint is not None:
        load_stable_checkpoint(model, checkpoint)
    unfreeze_last_blocks(model, blocks=2)
    model.to(device)

    params = [
        {"params": model.features[-2:].parameters(), "lr": 1e-4},
        {"params": model.classifier.parameters(), "lr": 1e-3},
    ]
    optimizer = torch.optim.AdamW(params, weight_decay=0.01)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)
    criterion = nn.CrossEntropyLoss()

    train_ds = DMDFrames(manifest_csv, "train", build_transform(True), frames_root)
    val_ds = DMDFrames(manifest_csv, "val", build_transform(False), frames_root)
    train_loader = DataLoader(train_ds, batch_size=batch_size, shuffle=True, num_workers=0)
    val_loader = DataLoader(val_ds, batch_size=batch_size, shuffle=False, num_workers=0)

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    history, best_f1, best_epoch, stale = [], -1.0, 0, 0
    for epoch in range(1, epochs + 1):
        started = time.perf_counter()
        train_loss, train_preds, train_labels = _epoch(
            model, train_loader, criterion, optimizer, device, train=True)
        val_loss, val_preds, val_labels = _epoch(
            model, val_loader, criterion, optimizer, device, train=False)
        scheduler.step()
        entry = {"epoch": epoch, "train_loss": train_loss, "val_loss": val_loss,
                 "val_macro_f1": _macro_f1(val_preds, val_labels),
                 "train_macro_f1": _macro_f1(train_preds, train_labels),
                 "seconds": round(time.perf_counter() - started, 1)}
        history.append(entry)
        print(json.dumps(entry), flush=True)
        if entry["val_macro_f1"] > best_f1:
            best_f1, best_epoch, stale = entry["val_macro_f1"], epoch, 0
            torch.save(model.state_dict(), out_dir / "best.pt")
        else:
            stale += 1
            if stale >= patience:
                break
    result = {"epochs_run": len(history), "best_epoch": best_epoch,
              "best_val_macro_f1": best_f1, "history": history,
              "device": str(device), "seed": seed, "batch_size": batch_size,
              "checkpoint": str(out_dir / "best.pt")}
    (out_dir / "training_history.json").write_text(json.dumps(result, indent=2))
    return result


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("manifest_csv", type=Path)
    parser.add_argument("frames_root", type=Path)
    parser.add_argument("out_dir", type=Path)
    parser.add_argument("--checkpoint", type=Path, required=True,
                        help="stable mobilenetv3_large_vision.pt")
    parser.add_argument("--epochs", type=int, default=30)
    args = parser.parse_args()
    train(args.manifest_csv, args.frames_root, args.out_dir,
          epochs=args.epochs, checkpoint=args.checkpoint)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: 跑测试确认通过**

Run: `PYTHONPATH=backend .venv/bin/python -m pytest backend/tests/test_dmd_dataset.py -q`
Expected: 9 passed

- [ ] **Step 5: 提交**

```bash
git add scripts/dmd_train.py backend/tests/test_dmd_dataset.py
git commit -m "feat(dmd): partial fine-tune with locked BatchNorm statistics"
```
---

### Task 6: 在验证集上选阈值

**Files:**
- Create: `scripts/dmd_threshold.py`
- Test: `backend/tests/test_dmd_threshold.py`

**Interfaces:**
- Consumes: 无（纯函数）
- Produces:
  - `select_threshold(distraction: list[float], labels: list[int], max_fpr: float = 0.10) -> dict`
  - 返回键：`threshold, fpr, recall, precision, balanced_accuracy, feasible`

- [ ] **Step 1: 写失败测试**

```python
"""scripts/dmd_threshold.py: pick the working point on val under an FPR budget."""
import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
THRESHOLD = REPO / "scripts" / "dmd_threshold.py"


def _load():
    spec = importlib.util.spec_from_file_location("dmd_threshold", THRESHOLD)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_picks_the_lowest_threshold_meeting_the_fpr_budget():
    t = _load()
    # 4 safe (label 0) and 4 distracted (label 1)
    probs = [0.05, 0.20, 0.35, 0.45,  0.55, 0.70, 0.85, 0.95]
    labels = [0, 0, 0, 0, 1, 1, 1, 1]
    # threshold 0.55 -> FPR 0/4, recall 4/4
    result = t.select_threshold(probs, labels, max_fpr=0.0)
    assert result["threshold"] == 0.55
    assert result["fpr"] == 0.0
    assert result["recall"] == 1.0
    assert result["feasible"] is True


def test_relaxes_recall_when_no_threshold_meets_the_budget():
    t = _load()
    probs = [0.10, 0.60, 0.65, 0.90]
    labels = [0, 0, 1, 1]
    # every threshold that catches a distracted sample also flags a safe one
    result = t.select_threshold(probs, labels, max_fpr=0.0)
    assert result["feasible"] is False
    assert result["fpr"] == 0.5     # the best achievable under the ordering


def test_reports_the_balanced_accuracy_of_the_chosen_point():
    t = _load()
    probs = [0.1, 0.2, 0.8, 0.9]
    labels = [0, 0, 1, 1]
    result = t.select_threshold(probs, labels, max_fpr=0.0)
    assert result["balanced_accuracy"] == 1.0
```

- [ ] **Step 2: 跑测试确认失败**

Run: `PYTHONPATH=backend .venv/bin/python -m pytest backend/tests/test_dmd_threshold.py -q`
Expected: FAIL — `FileNotFoundError`

- [ ] **Step 3: 写实现**

```python
"""Choose the binary working point on the validation split.

The risk score is ``P_distraction = 1 - P(c0)``; the zero-shot protocol used a fixed
0.5, which on domain-shifted input flags almost every safe frame. Because the loss is
NOT class-weighted here, the threshold is the only lever - and it is fitted on val
(gB_10) only, never on the test subjects.
"""
from __future__ import annotations


def _rates(threshold: float, probs: list[float], labels: list[int]) -> tuple[float, float, float]:
    positives = [p >= threshold for p in probs]
    tp = sum(1 for p, y in zip(positives, labels) if p and y == 1)
    fp = sum(1 for p, y in zip(positives, labels) if p and y == 0)
    fn = sum(1 for p, y in zip(positives, labels) if not p and y == 1)
    tn = sum(1 for p, y in zip(positives, labels) if not p and y == 0)
    tpr = tp / (tp + fn) if (tp + fn) else 0.0
    fpr = fp / (fp + tn) if (fp + tn) else 0.0
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    return tpr, fpr, precision


def select_threshold(distraction: list[float], labels: list[int],
                     max_fpr: float = 0.10) -> dict:
    """Lowest threshold whose FPR <= ``max_fpr``, maximising recall.

    When no threshold meets the budget the function returns the point with the smallest
    FPR (ties broken by higher recall) and sets ``feasible=False`` - callers must report
    that rather than pretending the budget was met.
    """
    if len(distraction) != len(labels):
        raise ValueError("distraction and labels must be the same length")
    if not distraction:
        raise ValueError("no samples")
    candidates = sorted(set(distraction) | {1.0})
    rows = []
    for threshold in candidates:
        recall, fpr, precision = _rates(threshold, distraction, labels)
        rows.append({"threshold": threshold, "recall": recall, "fpr": fpr,
                     "precision": precision,
                     "balanced_accuracy": (recall + (1 - fpr)) / 2})
    feasible = [r for r in rows if r["fpr"] <= max_fpr]
    if feasible:
        chosen = min(feasible, key=lambda r: (r["threshold"], -r["recall"]))
    else:
        chosen = min(rows, key=lambda r: (r["fpr"], -r["recall"]))
    return {**chosen, "feasible": bool(feasible), "max_fpr": max_fpr}
```

- [ ] **Step 4: 跑测试确认通过**

Run: `PYTHONPATH=backend .venv/bin/python -m pytest backend/tests/test_dmd_threshold.py -q`
Expected: 3 passed

- [ ] **Step 5: 提交**

```bash
git add scripts/dmd_threshold.py backend/tests/test_dmd_threshold.py
git commit -m "feat(dmd): FPR-budgeted threshold selection on the validation split"
```

---

### Task 7: 评估指标与同集对比

**Files:**
- Create: `scripts/dmd_evaluate.py`
- Test: `backend/tests/test_dmd_threshold.py`（追加指标测试）

**Interfaces:**
- Consumes: 模型 logits（任意来源：stable ONNX 或微调 checkpoint）
- Produces:
  - `multiclass_metrics(y_true: list[int], logits: list[list[float]]) -> dict`
  - `binary_metrics(y_true: list[int], distraction: list[float], threshold: float) -> dict`
  - `ece(probs: list[float], labels: list[int], bins: int = 10) -> float`

- [ ] **Step 1: 写失败测试**

追加到 `backend/tests/test_dmd_threshold.py`：

```python
EVAL = REPO / "scripts" / "dmd_evaluate.py"


def _load_eval():
    spec = importlib.util.spec_from_file_location("dmd_evaluate", EVAL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_multiclass_metrics_on_a_perfect_predictor():
    e = _load_eval()
    logits = [[10.0, 0.0, 0.0], [0.0, 10.0, 0.0], [0.0, 0.0, 10.0]]
    y = [0, 1, 2]
    result = e.multiclass_metrics(y, logits)
    assert result["accuracy"] == 1.0
    assert result["macro_f1"] == 1.0
    assert result["confusion_matrix"][0][0] == 1


def test_binary_metrics_reports_fpr_recall_and_auc():
    e = _load_eval()
    y = [0, 0, 1, 1]
    distraction = [0.1, 0.2, 0.8, 0.9]
    result = e.binary_metrics(y, distraction, threshold=0.5)
    assert result["recall"] == 1.0
    assert result["fpr"] == 0.0
    assert result["roc_auc"] == 1.0
    assert result["balanced_accuracy"] == 1.0


def test_ece_is_zero_for_a_perfectly_calibrated_binary_set():
    e = _load_eval()
    probs = [0.0, 0.0, 1.0, 1.0]
    labels = [0, 0, 1, 1]
    assert e.ece(probs, labels, bins=2) == 0.0
```

- [ ] **Step 2: 跑测试确认失败**

Run: `PYTHONPATH=backend .venv/bin/python -m pytest backend/tests/test_dmd_threshold.py -q -k metrics or ece`
Expected: FAIL — `FileNotFoundError`

- [ ] **Step 3: 写实现**

```python
"""Metrics shared by the zero-shot baseline and the adapted model.

Same definitions the zero-shot report used, so the two tables are comparable:
10-class accuracy / macro-F1 / per-class P-R-F1 / confusion matrix, and the binary
``P_distraction = 1 - P(c0)`` view with recall, FPR, rocAUC, prAUC, balanced accuracy,
Brier and 10-bin ECE.
"""
from __future__ import annotations


def multiclass_metrics(y_true: list[int], logits: list[list[float]],
                       num_classes: int = 10) -> dict:
    from sklearn.metrics import (accuracy_score, confusion_matrix, f1_score,
                                 precision_recall_fscore_support)

    preds = [max(range(len(row)), key=lambda i: row[i]) for row in logits]
    precision, recall, f1, support = precision_recall_fscore_support(
        y_true, preds, labels=list(range(num_classes)), zero_division=0)
    return {
        "accuracy": float(accuracy_score(y_true, preds)),
        "macro_f1": float(f1_score(y_true, preds, average="macro", zero_division=0)),
        "per_class": {
            f"c{i}": {"precision": float(precision[i]), "recall": float(recall[i]),
                      "f1": float(f1[i]), "support": int(support[i])}
            for i in range(num_classes)
        },
        "confusion_matrix": confusion_matrix(y_true, preds,
                                             labels=list(range(num_classes))).tolist(),
    }


def binary_metrics(y_true: list[int], distraction: list[float],
                   threshold: float) -> dict:
    from sklearn.metrics import (average_precision_score, brier_score_loss,
                                 roc_auc_score)

    positives = [p >= threshold for p in distraction]
    tp = sum(1 for p, y in zip(positives, y_true) if p and y == 1)
    fp = sum(1 for p, y in zip(positives, y_true) if p and y == 0)
    fn = sum(1 for p, y in zip(positives, y_true) if not p and y == 1)
    tn = sum(1 for p, y in zip(positives, y_true) if not p and y == 0)
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    fpr = fp / (fp + tn) if (fp + tn) else 0.0
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    return {
        "threshold": threshold,
        "recall": recall,
        "fpr": fpr,
        "precision": precision,
        "balanced_accuracy": (recall + (1 - fpr)) / 2,
        "roc_auc": float(roc_auc_score(y_true, distraction)),
        "pr_auc": float(average_precision_score(y_true, distraction)),
        "brier": float(brier_score_loss(y_true, distraction)),
        "ece": ece(distraction, y_true),
    }


def ece(probs: list[float], labels: list[int], bins: int = 10) -> float:
    """Expected calibration error of a probability against binary labels."""
    buckets: list[list[tuple[float, int]]] = [[] for _ in range(bins)]
    for p, y in zip(probs, labels):
        index = min(bins - 1, int(p * bins))
        buckets[index].append((p, y))
    total = len(probs)
    error = 0.0
    for bucket in buckets:
        if not bucket:
            continue
        confidence = sum(p for p, _ in bucket) / len(bucket)
        accuracy = sum(y for _, y in bucket) / len(bucket)
        error += abs(confidence - accuracy) * len(bucket) / total
    return float(error)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `PYTHONPATH=backend .venv/bin/python -m pytest backend/tests/test_dmd_threshold.py -q`
Expected: 6 passed

- [ ] **Step 5: 提交**

```bash
git add scripts/dmd_evaluate.py backend/tests/test_dmd_threshold.py
git commit -m "feat(dmd): zero-shot-compatible multiclass and binary metrics"
```

---

### Task 8: ONNX 导出与 candidate 包

**Files:**
- Create: `scripts/dmd_export_candidate.py`
- Test: `backend/tests/test_dmd_export.py`

**Interfaces:**
- Consumes: `best.pt`（Task 5）
- Produces:
  - `build_manifest(*, run_id, model_sha256, parent_sha256, smoke) -> dict`
  - `export(checkpoint: Path, out_dir: Path, *, parent_sha256: str, smoke_n: int = 1, sample_ids_sha256: str = "0"*64, smoke_selection: str = ...) -> dict`
  - 包内文件：`model.onnx` / `runtime_manifest.json` / `class_metadata.json` / `evaluation_metrics.json`

- [ ] **Step 1: 写失败测试**

```python
"""scripts/dmd_export_candidate.py: the package must satisfy the runtime contract."""
import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
EXPORT = REPO / "scripts" / "dmd_export_candidate.py"

sys.path.insert(0, str(REPO / "backend"))

from app.runtime_manifest import validate_package  # noqa: E402


def _load():
    spec = importlib.util.spec_from_file_location("dmd_export_candidate", EXPORT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_build_manifest_has_every_required_key_and_legal_provenance():
    e = _load()
    manifest = e.build_manifest(
        run_id="pkg", model_sha256="a" * 64, parent_sha256="b" * 64,
        smoke={"split": "val", "selection": "s", "n": 3,
               "sample_ids_sha256": "c" * 64, "rule": "per_class_mode_equals_label"})
    assert set(manifest) == {
        "manifest_version", "kind", "run_id", "architecture", "model", "input",
        "preprocess", "output", "classes", "class_to_idx", "safe_class",
        "contract_smoke_set", "provenance"}
    assert manifest["provenance"]["parent_model_sha256"] == "b" * 64
    assert not [k for k in manifest["provenance"] if "metric" in k.lower()]


def test_export_writes_a_package_that_validate_package_accepts(tmp_path):
    torch = pytest.importorskip("torch")
    from torchvision.models import mobilenet_v3_large

    e = _load()
    model = mobilenet_v3_large(weights=None, num_classes=10)
    checkpoint = tmp_path / "best.pt"
    torch.save(model.state_dict(), checkpoint)
    out_dir = tmp_path / "pkg"
    e.export(checkpoint, out_dir=out_dir, parent_sha256="b" * 64, smoke_n=1)
    manifest = json.loads((out_dir / "runtime_manifest.json").read_text())
    assert validate_package(manifest, out_dir) == []
    assert (out_dir / "model.onnx").is_file()
    assert (out_dir / "class_metadata.json").is_file()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `PYTHONPATH=backend .venv/bin/python -m pytest backend/tests/test_dmd_export.py -q`
Expected: FAIL — `FileNotFoundError`

- [ ] **Step 3: 写实现**

```python
"""Export the adapted checkpoint as a runtime candidate package.

The package layout is the one ``backend/app/vision_candidates.py`` already loads:
``model.onnx`` + ``runtime_manifest.json`` (manifest v1) + ``class_metadata.json``.
``provenance`` is a free-form object, but its key names may not look like evaluation
metrics - those belong in ``evaluation_metrics.json``.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

PREPROCESS = "rgb_resize_224_bilinear_no_crop_div255_imagenet"
CLASSES = [f"c{i}" for i in range(10)]


def _sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def build_manifest(*, run_id: str, model_sha256: str, parent_sha256: str,
                   smoke: dict) -> dict:
    return {
        "manifest_version": 1,
        "kind": "vision_classifier",
        "run_id": run_id,
        "architecture": "mobilenet_v3_large",
        "model": {"format": "onnx", "path": "model.onnx", "sha256": model_sha256},
        "input": {"color": "RGB", "dtype": "float32", "layout": "NCHW",
                  "shape": [1, 3, 224, 224]},
        "preprocess": PREPROCESS,
        "output": {"kind": "logits", "shape": [1, 10]},
        "classes": CLASSES,
        "class_to_idx": {name: index for index, name in enumerate(CLASSES)},
        "safe_class": "c0",
        "contract_smoke_set": smoke,
        "provenance": {
            "parent_model_sha256": parent_sha256,
            "source_dataset": "DMD body view (CC BY-NC-ND 4.0)",
            "training_labels": "DMD driver_actions mapped per label_mapping.json",
            "runtime_c0_alias": "safe_driving",
            "seed": 42,
            "graph_batch": "dynamic N",
            "input_name": "input",
            "output_name": "logits",
        },
    }


def export(checkpoint: Path, out_dir: Path, *, parent_sha256: str,
           smoke_n: int = 1, sample_ids_sha256: str = "0" * 64,
           smoke_selection: str = "gB_10 val frames grouped by class") -> dict:
    import torch
    from torchvision.models import mobilenet_v3_large

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    model = mobilenet_v3_large(weights=None, num_classes=10)
    model.load_state_dict(torch.load(checkpoint, map_location="cpu"))
    model.eval()

    onnx_path = out_dir / "model.onnx"
    torch.onnx.export(model, torch.zeros(1, 3, 224, 224), str(onnx_path),
                      input_names=["input"], output_names=["logits"],
                      dynamic_axes={"input": {0: "batch"}, "logits": {0: "batch"}},
                      opset_version=17)
    manifest = build_manifest(
        run_id=out_dir.name, model_sha256=_sha256(onnx_path),
        parent_sha256=parent_sha256,
        smoke={"split": "val", "selection": smoke_selection, "n": smoke_n,
               "sample_ids_sha256": sample_ids_sha256,
               "rule": "per_class_mode_equals_label"})
    (out_dir / "runtime_manifest.json").write_text(json.dumps(manifest, indent=2))
    (out_dir / "class_metadata.json").write_text(json.dumps({
        "classes": CLASSES,
        "class_to_idx": {name: index for index, name in enumerate(CLASSES)},
        "safe_class": "c0",
        "runtime_aliases": {"c0": "safe_driving"},
        "meaning": "Runtime alias does not rename the DMD training action.",
    }, indent=2))
    (out_dir / "evaluation_metrics.json").write_text(json.dumps({}, indent=2))
    return manifest
```

- [ ] **Step 4: 跑测试确认通过**

Run: `PYTHONPATH=backend .venv/bin/python -m pytest backend/tests/test_dmd_export.py -q`
Expected: 2 passed

- [ ] **Step 5: 提交**

```bash
git add scripts/dmd_export_candidate.py backend/tests/test_dmd_export.py
git commit -m "feat(dmd): export adapted model as a runtime candidate package"
```
---

### Task 9: 端到端执行与运行时验证

**Files:**
- Create: `scripts/dmd_infer_test.py`
- Modify: `docs/evidence/2026-10-29/dmd-adaptation/`（新建证据目录）

**Interfaces:**
- Consumes: `sampling_manifest.csv`（Task 3）、`best.pt`（Task 5）、`selected_threshold`（Task 6）
- Produces: `zero_shot_unexposed.json` / `adapted_unexposed.json` / `run_config.json`

- [ ] **Step 1: 写同一条 ONNX 推理路径**

两个模型必须走完全相同的预处理与推理代码，否则对比不成立。

```python
"""Run any vision classifier package over one split and dump logits + metrics.

Both the zero-shot baseline and the adapted model are evaluated through THIS function,
so the only difference between the two tables is the ONNX file.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)


def preprocess(path: Path) -> np.ndarray:
    from PIL import Image

    with Image.open(path) as image:
        image = image.convert("RGB").resize((224, 224), Image.Resampling.BILINEAR)
        values = np.asarray(image, dtype=np.float32) / 255.0
    values = (values - MEAN) / STD
    return np.ascontiguousarray(values.transpose(2, 0, 1)[None])


def infer(model_path: Path, frames_root: Path, files: list[str]) -> list[list[float]]:
    import onnxruntime as ort

    session = ort.InferenceSession(str(model_path), providers=["CPUExecutionProvider"])
    input_name = session.get_inputs()[0].name
    logits: list[list[float]] = []
    for rel in files:
        tensor = preprocess(Path(frames_root) / rel)
        logits.append(session.run(None, {input_name: tensor})[0][0].tolist())
    return logits


def softmax(row: list[float]) -> list[float]:
    """ONNX returns LOGITS; every probability metric must start from this."""
    import math

    top = max(row)
    exp = [math.exp(v - top) for v in row]
    total = sum(exp)
    return [v / total for v in exp]


def run(model_path: Path, manifest_csv: Path, frames_root: Path, split: str) -> dict:
    import csv

    from dmd_dataset import CLASS_IDS
    from dmd_evaluate import binary_metrics, multiclass_metrics

    rows = [r for r in csv.DictReader(Path(manifest_csv).open()) if r["split"] == split]
    files = [r["file"] for r in rows]
    labels = [CLASS_IDS.index(r["class_id"]) for r in rows]
    matrix = infer(model_path, frames_root, files)
    probs = [softmax(row) for row in matrix]        # ONNX output is LOGITS
    distraction = [1.0 - p[0] for p in probs]       # P_distraction = 1 - P(c0)
    return {"split": split, "n": len(rows), "files": files, "labels": labels,
            "logits": matrix, "probabilities": probs, "distraction": distraction,
            "multiclass": multiclass_metrics(labels, matrix)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("model_path", type=Path)
    parser.add_argument("manifest_csv", type=Path)
    parser.add_argument("frames_root", type=Path)
    parser.add_argument("--split", default="test")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.out.write_text(json.dumps(
        run(args.model_path, args.manifest_csv, args.frames_root, args.split), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: 抽帧并核对统计**

```bash
PYTHONPATH=scripts .venv/bin/python scripts/dmd_extract.py \
  /Users/liu/Desktop/DMD /Users/liu/Desktop/fyp2/ml-training/FYP2-DMD-body-v1
```

Expected: `sessions: 19`；`by_split` 的 train/val/test 与 spec 3.2 的受试者一致。把
`extraction_log.json` 复制进 `docs/evidence/2026-10-29/dmd-adaptation/`。

- [ ] **Step 3: 只在 val 上跑 zero-shot 基线（不碰 test）**

**开发期间不产生任何 test 指标。** 训练、选阈值、选超参都只看 train 与 val；test 在
Step 7 冻结之后统一评估一次（Step 8）。

```bash
mkdir -p docs/evidence/2026-10-29/dmd-adaptation
PYTHONPATH=backend:scripts .venv/bin/python scripts/dmd_infer_test.py \
  ml/outputs/vision/mobilenetv3_large_vision.onnx \
  /Users/liu/Desktop/fyp2/ml-training/FYP2-DMD-body-v1/sampling_manifest.csv \
  /Users/liu/Desktop/fyp2/ml-training/FYP2-DMD-body-v1/frames \
  --split val --out docs/evidence/2026-10-29/dmd-adaptation/zero_shot_val.json
```

- [ ] **Step 4: 训练**

```bash
PYTHONPATH=backend:scripts .venv/bin/python scripts/dmd_train.py \
  /Users/liu/Desktop/fyp2/ml-training/FYP2-DMD-body-v1/sampling_manifest.csv \
  /Users/liu/Desktop/fyp2/ml-training/FYP2-DMD-body-v1/frames \
  /Users/liu/Desktop/fyp2/ml-training/FYP2-DMD-body-v1/run \
  --checkpoint ml/outputs/vision/mobilenetv3_large_vision.pt
```

Expected: 30 轮内早停；`training_history.json` 每个 epoch 都有 `val_macro_f1`；无 BN 断言失败。
把 `training_history.json` 复制进证据目录。

- [ ] **Step 5: 导出 candidate 初版并对 val 推理**

`smoke_n=1` 是占位值（schema 要求 >= 1），Step 7 会用真实统计重导一次。

```bash
PYTHONPATH=backend:scripts .venv/bin/python -c "
import json, sys, hashlib
from pathlib import Path
sys.path.insert(0, 'scripts')
from dmd_export_candidate import export
manifest = export(
    Path('/Users/liu/Desktop/fyp2/ml-training/FYP2-DMD-body-v1/run/best.pt'),
    Path('ml/outputs/candidates/dmd_adapted_mobilenet_v3_20261029'),
    parent_sha256=hashlib.sha256(
        Path('ml/outputs/vision/mobilenetv3_large_vision.pt').read_bytes()).hexdigest(),
    smoke_n=1)
print(json.dumps(manifest['model'], indent=2))
"
PYTHONPATH=backend:scripts .venv/bin/python scripts/dmd_infer_test.py \
  ml/outputs/candidates/dmd_adapted_mobilenet_v3_20261029/model.onnx \
  /Users/liu/Desktop/fyp2/ml-training/FYP2-DMD-body-v1/sampling_manifest.csv \
  /Users/liu/Desktop/fyp2/ml-training/FYP2-DMD-body-v1/frames \
  --split val --out docs/evidence/2026-10-29/dmd-adaptation/adapted_val.json
```

- [ ] **Step 6: 在 val 上选阈值**

```bash
PYTHONPATH=backend:scripts .venv/bin/python -c "
import json, sys
sys.path.insert(0, 'scripts')
from dmd_threshold import select_threshold
val = json.load(open('docs/evidence/2026-10-29/dmd-adaptation/adapted_val.json'))
result = select_threshold(val['distraction'], [int(y != 0) for y in val['labels']])
open('docs/evidence/2026-10-29/dmd-adaptation/selected_threshold.json','w').write(
    json.dumps(result, indent=2))
print(json.dumps(result, indent=2))
"
```

若 `selected_threshold.json` 的 `feasible` 为 `false`，继续往下走，但 Task 10 必须写明
FPR 预算在同域数据上不可达；`feasible=True` 本身不证明模型有效，必须同时报告 recall。

- [ ] **Step 7: 冻结：用 val 的真实统计重导 candidate**

**这一步之后不允许再改 checkpoint、预处理、阈值或 ONNX。** 顺序固定：重导 → test →
run_config → 校包，任何一步发现异常都回到 Step 5，不得先看 test 再回头调。

```bash
PYTHONPATH=backend:scripts .venv/bin/python -c "
import hashlib, json, sys
from pathlib import Path
sys.path.insert(0, 'scripts')
from dmd_export_candidate import export
rows = [r for r in __import__('csv').DictReader(
    open('/Users/liu/Desktop/fyp2/ml-training/FYP2-DMD-body-v1/sampling_manifest.csv'))
        if r['split'] == 'val']
by_class = {}
for r in rows:
    by_class.setdefault(r['class_id'], []).append(f\"{r['subject']}/{r['file']}\")
ids = []
for cls in sorted(by_class):
    ids.extend(sorted(by_class[cls])[:20])
n = len(ids)
smoke_sha = hashlib.sha256(''.join(ids).encode()).hexdigest()
export(
    Path('/Users/liu/Desktop/fyp2/ml-training/FYP2-DMD-body-v1/run/best.pt'),
    Path('ml/outputs/candidates/dmd_adapted_mobilenet_v3_20261029'),
    parent_sha256=hashlib.sha256(
        Path('ml/outputs/vision/mobilenetv3_large_vision.pt').read_bytes()).hexdigest(),
    smoke_n=n, sample_ids_sha256=smoke_sha)
print(json.dumps({'smoke_n': n, 'sample_ids_sha256': smoke_sha}, indent=2))
"
```

- [ ] **Step 8: 冻结后统一评估 test**

两个模型走**同一条** `dmd_infer_test.py`，唯一差别是 ONNX 文件。输出必须包含两个测试受试者的分项。

```bash
PYTHONPATH=backend:scripts .venv/bin/python scripts/dmd_infer_test.py \
  ml/outputs/vision/mobilenetv3_large_vision.onnx \
  /Users/liu/Desktop/fyp2/ml-training/FYP2-DMD-body-v1/sampling_manifest.csv \
  /Users/liu/Desktop/fyp2/ml-training/FYP2-DMD-body-v1/frames \
  --split test --out docs/evidence/2026-10-29/dmd-adaptation/zero_shot_unexposed.json
PYTHONPATH=backend:scripts .venv/bin/python scripts/dmd_infer_test.py \
  ml/outputs/candidates/dmd_adapted_mobilenet_v3_20261029/model.onnx \
  /Users/liu/Desktop/fyp2/ml-training/FYP2-DMD-body-v1/sampling_manifest.csv \
  /Users/liu/Desktop/fyp2/ml-training/FYP2-DMD-body-v1/frames \
  --split test --out docs/evidence/2026-10-29/dmd-adaptation/adapted_unexposed.json
```

- [ ] **Step 9: 写 run_config.json**

```bash
PYTHONPATH=backend:scripts .venv/bin/python -c "
import json, hashlib, csv
sys.path.insert(0, 'scripts')
from pathlib import Path
from dmd_evaluate import binary_metrics
ev = Path('docs/evidence/2026-10-29/dmd-adaptation')
th = json.loads((ev/'selected_threshold.json').read_text())
def summarise(name, path):
    d = json.loads(path.read_text())
    labels = [int(y != 0) for y in d['labels']]
    return {'zero_shot': binary_metrics(labels, d['distraction'], 0.5)} if 'zero' in name \
        else {'at_0.5': binary_metrics(labels, d['distraction'], 0.5),
              'at_selected': binary_metrics(labels, d['distraction'], th['threshold'])}
cfg = {
  'selected_threshold': th,
  'zero_shot_test': summarise('zero', ev/'zero_shot_unexposed.json'),
  'adapted_test': summarise('adapted', ev/'adapted_unexposed.json'),
  'model_sha256': hashlib.sha256(Path('ml/outputs/candidates/dmd_adapted_mobilenet_v3_20261029/model.onnx').read_bytes()).hexdigest(),
  'manifest_rows': sum(1 for _ in csv.DictReader(open('/Users/liu/Desktop/fyp2/ml-training/FYP2-DMD-body-v1/sampling_manifest.csv'))),
}
(ev/'run_config.json').write_text(json.dumps(cfg, indent=2))
print(json.dumps(cfg, indent=2))
"
```

`run_config.json` 的 `model_sha256` 必须取重导后的文件。最后校验一次包：

```bash
PYTHONPATH=backend .venv/bin/python -c "
import json, sys
from pathlib import Path
sys.path.insert(0, 'backend')
from app.runtime_manifest import validate_package
pkg = Path('ml/outputs/candidates/dmd_adapted_mobilenet_v3_20261029')
errors = validate_package(json.loads((pkg/'runtime_manifest.json').read_text()), pkg)
print('ERRORS' if errors else 'OK', errors)
"
```

- [ ] **Step 10: 运行时验证（空闲端口 + 临时库）**

**不碰用户现有的 8000 端口与 `driver_risk.db`。** 端口由内核分配，数据库用 `mktemp` 临时目录，
结束后确认端口释放且临时库删除。

```bash
PORT=$(python3 -c "import socket;s=socket.socket();s.bind(('127.0.0.1',0));print(s.getsockname()[1]);s.close()")
TMPDIR_PROBE=$(mktemp -d)
DRA_DATABASE_URL="sqlite:///$TMPDIR_PROBE/probe.sqlite" \
DRA_ACTIVE_VISION=dmd_adapted_mobilenet_v3_20261029 \
  .venv/bin/python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port "$PORT" &
PID=$!
sleep 6
curl -s "http://127.0.0.1:$PORT/api/models" | python3 -m json.tool | head -30
kill "$PID"; wait "$PID" 2>/dev/null
lsof -iTCP:"$PORT" -sTCP:LISTEN || echo "port released"
ls "$TMPDIR_PROBE" && rm -rf "$TMPDIR_PROBE"
```

Expected: `vision.model_id` 为 `dmd_adapted_mobilenet_v3_20261029`，`sha256` 与包内
`runtime_manifest.json` 一致；`port released`；临时库目录已删。不带环境变量重启一次，
确认回到 `stable_mobilenet_v3_large`。

- [ ] **Step 11: PyTorch / ONNX / provider 三方预测一致性**

同一个 checkpoint 分别经 PyTorch、ONNX、以及后端 provider 推理，20 张固定图片上
top-1 必须完全一致，概率最大绝对误差 ≤ 1e-4。

```bash
PYTHONPATH=backend:scripts .venv/bin/python -c "
import json, sys
from pathlib import Path
sys.path.insert(0, 'scripts')
import torch, onnxruntime as ort, numpy as np
from torchvision.models import mobilenet_v3_large
from dmd_dataset import build_transform
from PIL import Image

ck = torch.load('/Users/liu/Desktop/fyp2/ml-training/FYP2-DMD-body-v1/run/best.pt', map_location='cpu')
model = mobilenet_v3_large(weights=None, num_classes=10)
model.load_state_dict(ck)
model.eval()
sess = ort.InferenceSession('ml/outputs/candidates/dmd_adapted_mobilenet_v3_20261029/model.onnx',
                           providers=['CPUExecutionProvider'])
root = Path('/Users/liu/Desktop/fyp2/ml-training/FYP2-DMD-body-v1/frames')
files = sorted(p for p in root.rglob('*.jpg'))[:20]
tf = build_transform(False)
worst, mismatches = 0.0, 0
for f in files:
    x = tf(Image.open(f).convert('RGB')).unsqueeze(0)
    with torch.no_grad():
        a = torch.softmax(model(x), 1)[0].numpy()
    b = sess.run(None, {'input': x.numpy().astype(np.float32)})[0][0]
    b = np.exp(b - b.max()) / np.exp(b - b.max()).sum()
    worst = max(worst, float(np.abs(a - b).max()))
    mismatches += int(a.argmax() != b.argmax())
print(json.dumps({'n': len(files), 'max_abs_diff': worst, 'top1_mismatches': mismatches}))
assert mismatches == 0 and worst <= 1e-4, 'PyTorch and ONNX disagree'
"
```

Expected: `top1_mismatches: 0`，`max_abs_diff` ≤ 1e-4。不一致就不要继续，先查预处理或
opset。

- [ ] **Step 12: 全量测试**

```bash
PYTHONPATH=backend .venv/bin/python -m pytest backend/tests -q
npm test
npx tsc --noEmit
npm run linc
npm run build
```

Expected: 全部 exit 0。

- [ ] **Step 13: 提交**

```bash
git add scripts/dmd_infer_test.py docs/evidence/2026-10-29/dmd-adaptation
git commit -m "feat(dmd): same-path ONNX evaluation and dated evidence"
```

---

### Task 10: 报告章节草稿

**Files:**
- Create: `docs/fyp2/dmd_adaptation_section_draft.md`

**Interfaces:**
- Consumes: Task 9 的全部 JSON
- Produces: 可并入第 5 章外部验证节的草稿

- [ ] **Step 1: 写草稿，逐项填真实数字**

必须包含的六节：

1. **协议**：6 受试者 / 19 session、1 FPS 区间采样、按受试者划分（train gA_1+gA_5+gB_6 /
   val gB_10 / test gC_13+gE_29）、CC BY-NC-ND 4.0 与"权重不发布"。
2. **零样本基线**：test 上的 10 类 acc / macro-F1、二分类 FPR @0.5 与 rocAUC。
3. **微调结果**：同一批帧上的同集对比；逐类 P/R/F1 表（10 行全列，不得省略 c7）。
4. **阈值**：val 选出的阈值、是否 feasible、以及 0.5 与 selected 两条阈值的 FPR–recall 对照。
5. **限制**：val 与 train 共享 group gB；gB_6 / gB_10 消耗了 UNEXPOSED 资格；c7 训练样本约
   33 个；BN 统计量未更新；结果只对 DMD body 视角成立。
6. **复现**：脚本路径、seed、checkpoint 与 ONNX 的 sha256、证据目录。

- [ ] **Step 2: 自查三项**

- 每个数字都能在 `docs/evidence/2026-10-29/dmd-adaptation/` 的 JSON 里找到出处；
- 没有任何一句话声称"安全提升"或"事故风险降低"；
- c7 的差指标如实写出，没有只挑好的类别。

- [ ] **Step 3: 提交**

```bash
git add docs/fyp2/dmd_adaptation_section_draft.md
git commit -m "docs(dmd): external validation section draft with dated evidence"
```

---

## Self-Review

**1. Spec coverage**

| Spec 章节 | 覆盖任务 |
|---|---|
| 3.1 抽帧规则（含 body 同步偏移）与类别映射 | Task 1（映射）、Task 2（采样）、Task 3（shift + manifest） |
| 3.2 划分与 holdout 消耗 | Task 1（`SPLITS`）、Task 4（按 split 过滤）、Task 10（限制节） |
| 3.3 预处理与增强 | Task 4（`build_transform`，含"不做翻转/旋转"的测试） |
| 4.2 解冻 + BN 冻结 | Task 5（`load_stable_checkpoint` / `unfreeze_last_blocks` / `lock_batchnorm` / 断言） |
| 4.3 30 轮上限 | Task 5（`epochs=30, patience=8`） |
| 4.4 不加权 + val 选阈值 | Task 5（`nn.CrossEntropyLoss()` 无权重）、Task 6 |
| 5.1 指标与双阈值 | Task 7（指标）、Task 9 Step 7（两条阈值汇总） |
| 5.2 同集对比（冻结后） | Task 9 Step 7/8（冻结 → 统一 test）、Task 10 |
| 6.1 candidate 包与 manifest | Task 8（`validate_package` 测试） |
| 6.2 证据目录 | Task 9 Step 2/4/7/10 |
| 6.3 报告草稿 | Task 10 |
| 7 风险与限制 | Task 10 Step 1 第 5 节 |
| 9 验收标准 1–8 | Task 3 Step 5/6（1）、Task 9 Step 3/6（2）、Task 9（4/5/6）、Task 5（7）、Task 10（8） |

无缺口。

**2. Placeholder scan**

已逐条检查：没有 TBD / TODO / "适当处理" / "类似 Task N"。`smoke_n=1` 是导出时的占位值
（schema 要求 >= 1），
但 Task 9 Step 6 之后必须用真实 val 统计重导一次（见下方修正项）。

**3. Type consistency**

- `DMDFrames(manifest_csv, split, transform, root)` 在 Task 4 定义，Task 5 以
  `DMDFrames(manifest_csv, "train", build_transform(True), frames_root)` 调用 — 一致。
- `select_threshold(distraction, labels, max_fpr)` 在 Task 6 定义，Task 9 Step 5 以
  `select_threshold(val['distraction'], [int(y != 0) for y in val['labels']])` 调用 — 一致。
- `binary_metrics(y_true, distraction, threshold)` 在 Task 7 定义，Task 9 Step 7 以同一签名调用 — 一致。
- `export(checkpoint, out_dir, parent_sha256=..., smoke_n=...)` 在 Task 8 定义，Task 9 Step 6 一致。

**修正项（已并入上文）**

- Task 9 Step 5 先用 `smoke_n=1` 占位导出以便跑 val；Step 7 用 val 的真实统计重导一次。
  重导才是最终提交的包，`run_config.json` 的 `model_sha256` 取重导后的文件，
  并用 `validate_package` 复校。

**针对 Codex review 的 6 项修正（2026-10-30）**

| # | 修正 | 落在 |
|---|---|---|
| 1 | 抽帧应用 `sync.frame_shift`（`body = annotation - shift`），负值丢弃；`gB_10_s3_0313` 用 override 20；manifest 同时存两个索引与 `effective_shift` | Task 3 |
| 2 | `load_stable_checkpoint` 读 `state_dict` 并校验 `arch` / `classes` | Task 5 |
| 3 | ONNX 输出是 logits，统一 `softmax` 后再算 `1 - P(c0)` | Task 9 Step 1 |
| 4 | “最后两个 stage” 改为 “最后两个 block（15、16）”，函数改名 `unfreeze_last_blocks` | Task 5 + spec 4.2 |
| 5 | 开发期只看 train/val；test 在 Step 7 冻结后统一评估，不做逐轮对照 | Task 9 Step 3/7/8 + spec 5.2 |
| 6 | 运行时验证改用内核分配的空闲端口与 `mktemp` 临时 SQLite，并核对端口释放与临时库清理 | Task 9 Step 10 |

另加一项 Codex 未提但同属必需的检查：PyTorch / ONNX 预测一致性（Task 9 Step 11）。
