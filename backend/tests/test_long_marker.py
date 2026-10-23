"""ST-LONG-01 lives behind the ``long`` marker: a full gate run must not start a 15-minute
browser session, and must not count it as SKIPPED either (the gates require 0 skipped). So a
``long`` test is DESELECTED unless the run asks for it with ``-m long``.

The behaviour is in ``conftest.py``; like test_model_gate.py, these tests run a real, separate
pytest session in a throw-away project that carries a copy of that conftest."""
import os
import shutil
import subprocess
import sys
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
BACKEND = TESTS_DIR.parent

SYNTHETIC = '''
import pytest

@pytest.mark.long
def test_a_long_one():
    pass

def test_plain():
    pass
'''


def run(tmp_path, *args):
    project = tmp_path / "project"
    project.mkdir()
    shutil.copy(TESTS_DIR / "conftest.py", project / "conftest.py")
    (project / "test_synthetic.py").write_text(SYNTHETIC)
    env = {k: v for k, v in os.environ.items() if k != "DRA_REQUIRE_MODELS"}
    env.update(PYTHONPATH=str(BACKEND), PYTHONDONTWRITEBYTECODE="1")
    return subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "--rootdir", str(project),
                           str(project), *args], cwd=project, env=env, capture_output=True, text=True, timeout=120)


def test_a_long_test_is_deselected_not_skipped_in_a_normal_run(tmp_path):
    done = run(tmp_path)
    assert done.returncode == 0, done.stdout
    assert "1 passed, 1 deselected" in done.stdout, done.stdout
    assert "skipped" not in done.stdout


def test_a_marker_expression_that_merely_contains_the_letters_long_does_not_start_it(tmp_path):
    """Deferred minor M7: the check is on the marker NAME, not a substring. ``-m "not longer"`` selects
    every test without a ``longer`` marker - the long one included - so only the conftest stands
    between it and a 15-minute run."""
    done = run(tmp_path, "-m", "not longer")
    assert done.returncode == 0, done.stdout
    assert "1 passed, 1 deselected" in done.stdout, done.stdout


def test_minus_m_long_runs_only_the_long_tests(tmp_path):
    done = run(tmp_path, "-m", "long")
    assert done.returncode == 0, done.stdout
    assert "1 passed, 1 deselected" in done.stdout, done.stdout
