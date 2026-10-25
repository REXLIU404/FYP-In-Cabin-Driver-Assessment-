"""Task 10 / R4: ``scripts/freeze_manifest.py`` must not fall back silently.

The manifest pins the dataset split files by hash. When ``FYP_DATA_ROOT`` is set and wrong,
quietly hashing some OTHER dataset (the repo root, the sibling repo) would produce a
manifest that looks complete and names the wrong files. So an explicit root is the only
candidate, and a wrong one is an error with a non-zero exit and an empty stdout.

Hermetic setup: the script is copied into a throw-away "repo" whose own root holds a valid
``eda_outputs/processed`` (a fallback that WOULD succeed), HOME points at an empty
directory (so the sibling-repo default cannot exist) and PATH is an empty directory (so
git / node / npm are "not found" instantly). The copy has no model checkpoints, so a run
that gets past the data-root check ends with exit status 1 ("models changed"); that is
what "not a data-root error" looks like here.
"""
import hashlib
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "freeze_manifest.py"
CSV_ROWS = b"a,b\n1,2\n3,4\n5,6\n"  # header + 3 data rows


@pytest.fixture
def fake_repo(tmp_path):
    repo = tmp_path / "repo"
    (repo / "scripts").mkdir(parents=True)
    shutil.copy(SCRIPT, repo / "scripts" / "freeze_manifest.py")
    (repo / "package.json").write_text('{"name": "fake"}')
    return repo


def _data_root(base: Path, marker: str) -> Path:
    processed = base / "eda_outputs" / "processed"
    processed.mkdir(parents=True)
    (processed / marker).write_bytes(CSV_ROWS)
    return base


def _run(repo: Path, tmp_path: Path, **env_extra):
    home, empty_path = tmp_path / "home", tmp_path / "empty-path"
    home.mkdir(exist_ok=True)
    empty_path.mkdir(exist_ok=True)
    env = {"PATH": str(empty_path), "HOME": str(home), "PYTHONDONTWRITEBYTECODE": "1", **env_extra}
    return subprocess.run([sys.executable, str(repo / "scripts" / "freeze_manifest.py")], env=env,
                          cwd=tmp_path, capture_output=True, text=True, timeout=60)


def test_a_valid_explicit_root_is_used_and_beats_the_fallbacks(fake_repo, tmp_path):
    _data_root(fake_repo, "fallback_marker.csv")  # the repo-root candidate WOULD also work
    chosen = _data_root(tmp_path / "chosen", "env_marker.csv")
    done = _run(fake_repo, tmp_path, FYP_DATA_ROOT=str(chosen))
    assert done.returncode == 1, done.stderr  # past the data-root check; models are absent here
    assert f"Data root: `{chosen.resolve()}`" in done.stdout
    row = re.search(r"\| `env_marker\.csv` \| `([0-9a-f]{64})` \| (\d+) \| (\d+) \|", done.stdout)
    assert row, done.stdout
    assert row.group(1) == hashlib.sha256(CSV_ROWS).hexdigest()
    assert (row.group(2), row.group(3)) == ("16", "3")
    assert "fallback_marker.csv" not in done.stdout


@pytest.mark.parametrize("shape", ["missing_dir", "empty_dir", "eda_outputs_without_processed", "a_file"])
def test_a_wrong_explicit_root_is_an_error_not_a_fallback(fake_repo, tmp_path, shape):
    _data_root(fake_repo, "fallback_marker.csv")  # a silent fallback would succeed here
    wrong = tmp_path / "wrong"
    if shape == "empty_dir":
        wrong.mkdir()
    elif shape == "eda_outputs_without_processed":
        (wrong / "eda_outputs").mkdir(parents=True)
    elif shape == "a_file":
        wrong.write_text("not a directory")
    done = _run(fake_repo, tmp_path, FYP_DATA_ROOT=str(wrong))
    assert done.returncode == 2, (done.stdout, done.stderr)
    assert done.stdout == ""  # no manifest at all, so a redirect cannot save a misleading one
    assert f"FYP_DATA_ROOT={wrong}" in done.stderr
    assert "does not contain eda_outputs/processed" in done.stderr
    assert "No other location was tried" in done.stderr


def test_an_empty_explicit_root_is_an_error_too(fake_repo, tmp_path):
    _data_root(fake_repo, "fallback_marker.csv")
    done = _run(fake_repo, tmp_path, FYP_DATA_ROOT="")
    assert done.returncode == 2, (done.stdout, done.stderr)
    assert done.stdout == ""
    assert "FYP_DATA_ROOT is set but empty" in done.stderr


def test_unset_keeps_the_candidate_search_unchanged(fake_repo, tmp_path):
    _data_root(fake_repo, "fallback_marker.csv")
    done = _run(fake_repo, tmp_path)
    assert done.returncode == 1, done.stderr
    assert f"Data root: `{fake_repo.resolve()}`" in done.stdout
    assert "fallback_marker.csv" in done.stdout


def test_unset_and_nothing_found_still_reports_not_found(fake_repo, tmp_path):
    done = _run(fake_repo, tmp_path)
    assert done.returncode == 1, done.stderr
    assert "**NOT FOUND.**" in done.stdout
    assert "FYP-In-Cabin-Driver-Assessment-" in done.stdout  # the sibling candidate was tried
    assert "warning: eda_outputs/processed not found" in done.stderr
