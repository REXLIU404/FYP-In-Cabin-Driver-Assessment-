"""Task 10 / Step 3: a skipped "needs the trained models" test must be loud, and the
pre-release gate (``DRA_REQUIRE_MODELS=1``) must fail instead of skipping.

The behaviour lives in ``conftest.py`` (``pytest_runtest_makereport`` +
``pytest_terminal_summary``), so the tests run a real, separate pytest session in a
throw-away project that carries a copy of that conftest and a ``requires_models``
marker whose condition is True (models "missing") - independent of whether this
checkout has the model files.
"""
import ast
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

TESTS_DIR = Path(__file__).resolve().parent
BACKEND = TESTS_DIR.parent
REASON = "local trained artifacts not installed"

SYNTHETIC = f'''
import pytest

missing = pytest.mark.skipif(True, reason="{REASON}")
unrelated = pytest.mark.skip(reason="a different, ordinary reason")


@missing
def test_needs_models_a():
    raise AssertionError("must not run")


@missing
def test_needs_models_b():
    raise AssertionError("must not run")


@unrelated
def test_skipped_for_another_reason():
    raise AssertionError("must not run")


def test_plain():
    pass
'''

PRESENT = '''
import pytest

present = pytest.mark.skipif(False, reason="local trained artifacts not installed")


@present
def test_models_are_here():
    pass
'''


def run_session(tmp_path, test_source, require=None):
    project = tmp_path / "project"
    project.mkdir()
    shutil.copy(TESTS_DIR / "conftest.py", project / "conftest.py")
    (project / "test_synthetic.py").write_text(test_source)
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    env = {k: v for k, v in os.environ.items() if k != "DRA_REQUIRE_MODELS"}
    env.update(PYTHONPATH=str(BACKEND), PYTHONDONTWRITEBYTECODE="1", TMPDIR=str(scratch))
    if require is not None:
        env["DRA_REQUIRE_MODELS"] = require
    return subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "--rootdir",
                           str(project), str(project)], cwd=project, env=env, capture_output=True,
                          text=True, timeout=120)


def test_missing_models_are_counted_and_named_in_the_summary(tmp_path):
    done = run_session(tmp_path, SYNTHETIC)
    out = done.stdout
    assert done.returncode == 0, out  # skips alone do not fail the default run
    assert "2 MODEL-DEPENDENT TEST(S) NOT RUN (models missing)" in out
    assert "These tests were skipped, not passed" in out
    assert "SKIPPED  test_synthetic.py::test_needs_models_a" in out
    assert "SKIPPED  test_synthetic.py::test_needs_models_b" in out
    # Only the model skips are listed: an unrelated skip and a passing test are not.
    assert "test_skipped_for_another_reason" not in out.split("MODEL-DEPENDENT")[1]
    assert "test_plain" not in out.split("MODEL-DEPENDENT")[1]
    assert "Set DRA_REQUIRE_MODELS=1" in out
    assert re.search(r"1 passed, 3 skipped", out), out


def test_require_models_turns_each_model_skip_into_a_failure(tmp_path):
    done = run_session(tmp_path, SYNTHETIC, require="1")
    out = done.stdout
    assert done.returncode != 0, out
    assert "DRA_REQUIRE_MODELS=1 but the trained model artifacts are missing" in out
    errors = [line.split(" - ")[0] for line in out.splitlines() if line.startswith("ERROR ")]
    assert errors == ["ERROR test_synthetic.py::test_needs_models_a",
                      "ERROR test_synthetic.py::test_needs_models_b"]  # the unrelated skip is not one
    assert "each of the above was reported as a FAILURE" in out
    assert re.search(r"1 passed, 1 skipped, 2 errors", out), out  # no longer counted as skips


@pytest.mark.parametrize("value", ["0", "", "true", "yes"])
def test_only_the_value_1_arms_the_gate(tmp_path, value):
    done = run_session(tmp_path, SYNTHETIC, require=value)
    assert done.returncode == 0, done.stdout
    assert "2 MODEL-DEPENDENT TEST(S) NOT RUN" in done.stdout


def test_with_the_models_present_nothing_is_flagged_and_the_gate_passes(tmp_path):
    plain = run_session(_fresh(tmp_path, "plain"), PRESENT)
    assert plain.returncode == 0, plain.stdout
    assert "MODEL-DEPENDENT" not in plain.stdout
    gated = run_session(_fresh(tmp_path, "gated"), PRESENT, require="1")
    assert gated.returncode == 0, gated.stdout
    assert "MODEL-DEPENDENT" not in gated.stdout
    assert "DRA_REQUIRE_MODELS=1: no model-dependent test was skipped." in gated.stdout


def _fresh(tmp_path, name):
    path = tmp_path / name
    path.mkdir()
    return path


def _literal_reason(node) -> str | None:
    """The skipif's ``reason`` when it is a string literal; None for a missing or non-literal
    reason (``reason=SOME_VARIABLE`` has no literal the parser can read - review R14)."""
    for kw in node.keywords:
        if kw.arg == "reason":
            value = kw.value
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                return value.value
            return None
    return None


def _model_skipif_conditions(directory: Path) -> list[tuple[str, str, str]]:
    """(file, reason, condition source text) for every ``pytest.mark.skipif`` in ``directory``
    whose reason is the one the gate recognises - found by parsing the source. The condition
    is the source segment of the skipif call, so the guards can check the condition itself
    instead of the whole file (review R14). A marker whose reason is not a string literal is
    skipped: it can never be the gate's reason, and reaching into the expression used to crash
    the guard with AttributeError (review R14)."""
    found = []
    for path in sorted(Path(directory).glob("test_*.py")):
        source = path.read_text()
        for node in ast.walk(ast.parse(source)):
            if not (isinstance(node, ast.Call) and ast.unparse(node.func).endswith("mark.skipif")):
                continue
            reason = _literal_reason(node)
            if reason != REASON:
                continue
            found.append((path.name, reason, ast.get_source_segment(source, node) or ""))
    return found


def _names_all_three(condition: str, files: tuple[str, ...]) -> bool:
    """Whether every stable model file is named in the skipif condition source."""
    return all(name in condition for name in files)


def _requires_models_markers():
    """(file, reason) for every `... = pytest.mark.skipif(` in this directory whose condition
    mentions the model files, found by parsing the source."""
    found = []
    for path in sorted(TESTS_DIR.glob("test_*.py")):
        source = path.read_text()
        for node in ast.walk(ast.parse(source)):
            if not (isinstance(node, ast.Call) and ast.unparse(node.func).endswith("mark.skipif")):
                continue
            segment = ast.get_source_segment(source, node) or ""
            if "MODEL_ROOT" in segment or "ml/outputs" in segment:
                reason = next((kw.value.value for kw in node.keywords if kw.arg == "reason"), None)
                found.append((path.name, reason))
    return found


def test_every_model_skipif_checks_all_three_stable_model_files():
    """Deferred minor M8: a marker that checks only one file lets a test run - and fail confusingly -
    when another model is missing, instead of being reported as a model skip. The check is on the
    skipif condition itself, not the whole file: naming the other files somewhere else in the file
    must not count (review R14)."""
    files = ("mobilenetv3_large_vision.onnx", "mobilenetv3_large_vision.pt", "xgb_telemetry.json")
    found = _model_skipif_conditions(TESTS_DIR)
    assert {name for name, _, _ in found} >= {"test_live_inference.py",
                                              "test_unavailable_contract.py", "test_live_e2e.py"}
    for name, reason, condition in found:
        assert reason == REASON, (name, reason)
        # The files are named in the condition itself or in a module constant it reads.
        assert _names_all_three(condition, files), (name, condition)
        assert "onnx').exists()" not in condition and 'onnx").exists()' not in condition, (name, condition)


def test_a_non_literal_skipif_reason_is_skipped_instead_of_crashing(tmp_path):
    """Review R14: a marker that passes ``reason=SOME_VARIABLE`` has no literal for the guard
    to read. The old guard reached into ``kw.value.value`` and crashed with AttributeError;
    a non-literal reason cannot be the gate's reason, so the marker is simply skipped."""
    (tmp_path / "test_var_reason.py").write_text('''
import pytest

REASON = "local trained artifacts not installed"
missing = pytest.mark.skipif(True, reason=REASON)


@missing
def test_needs_models():
    pass
''')
    assert _model_skipif_conditions(tmp_path) == []


def test_the_guard_reads_the_condition_not_the_whole_file(tmp_path):
    """Review R14: the old guard asserted the file names against the WHOLE file, so a marker whose
    condition checks a single model file passed as long as the other two names appeared anywhere
    else in the file. The condition-level guard must flag it."""
    (tmp_path / "test_weak.py").write_text('''
import pytest
from pathlib import Path

missing = pytest.mark.skipif(
    not (Path("ml/outputs/vision/mobilenetv3_large_vision.onnx").exists()),
    reason="local trained artifacts not installed",
)


@missing
def test_needs_models():
    pass


# The other two stable files are named elsewhere in the file, not in the condition:
OTHER = ("mobilenetv3_large_vision.pt", "xgb_telemetry.json")
''')
    found = _model_skipif_conditions(tmp_path)
    assert [name for name, _, _ in found] == ["test_weak.py"]
    condition = found[0][2]
    # The whole file DOES name all three files, and the old guard would have let it through...
    assert all(name in (tmp_path / "test_weak.py").read_text()
               for name in ("mobilenetv3_large_vision.onnx",
                            "mobilenetv3_large_vision.pt", "xgb_telemetry.json"))
    # ...but the condition itself names only one.
    assert not _names_all_three(condition, ("mobilenetv3_large_vision.onnx",
                                            "mobilenetv3_large_vision.pt", "xgb_telemetry.json"))


def test_every_model_skipif_uses_the_reason_the_gate_recognises():
    """The gate recognises a model skip by its reason text. A marker spelled differently
    would be skipped silently and survive DRA_REQUIRE_MODELS=1."""
    found = _requires_models_markers()
    assert {name for name, _ in found} >= {"test_live_inference.py", "test_unavailable_contract.py", "test_live_e2e.py"}
    assert all(reason == REASON for _, reason in found), found
