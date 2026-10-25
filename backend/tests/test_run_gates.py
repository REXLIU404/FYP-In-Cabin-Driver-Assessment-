"""Task 10 / R02: ``scripts/run_gates.py`` keeps raw evidence for every gate and cannot
report green when a gate failed.

The gates themselves are NOT run here (that is a full test-suite run inside a test-suite
run). The log format, the pass/fail logic and the exit status are exercised with small
Python programs as stand-in gates, passed through ``--gates-file`` (the same option a
custom gate set would use), and the built-in gate list is checked in ``--dry-run``.
Tool versions are injected for the in-process tests so that they do not depend on what is
installed; the subprocess tests use the real ones.
"""
import importlib.util
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "run_gates.py"
REPO = SCRIPT.parent.parent

_spec = importlib.util.spec_from_file_location("run_gates", SCRIPT)
run_gates = importlib.util.module_from_spec(_spec)
sys.modules["run_gates"] = run_gates  # dataclasses resolve their own module through sys.modules
_spec.loader.exec_module(run_gates)

FAKE_VERSIONS = {
    "python (this script)": "9.9.9", "python (.venv)": "Python 9.9.9", "pytest": "pytest 9.9.0",
    "node": "v99.0.0", "npm": "99.1.0", "vitest": "vitest/9.9.0 test", "tsc": "Version 9.9.1",
    "eslint": "v9.9.2",
}
PY = sys.executable


def fake_versions(_repo):
    return dict(FAKE_VERSIONS)


def program(code):
    return [PY, "-c", code]


OK = program("import sys; print('hello out'); print('hello err', file=sys.stderr)")
BAD = program("import sys; print('before'); print('boom', file=sys.stderr); sys.exit(3)")


def write_gates(tmp_path, gates):
    path = tmp_path / "gates.json"
    path.write_text(json.dumps(gates))
    return str(path)


def run_main(tmp_path, gates, *extra, name="gates-out"):
    out = tmp_path / name
    code = run_gates.main(["--gates-file", write_gates(tmp_path, gates), "--out", str(out), *extra],
                          versions_fn=fake_versions)
    return code, out


def parse_log(text):
    head, _, rest = text.partition("----- STDOUT -----\n")
    stdout, _, rest = rest.partition("\n----- END STDOUT -----\n----- STDERR -----\n")
    stderr = rest.partition("\n----- END STDERR -----")[0]
    fields = dict(re.findall(r"^([A-Z][A-Za-z ()]*): (.*)$", head, flags=re.M))
    env = dict(re.findall(r"^  ([A-Z_]+)=(.*)$", head, flags=re.M))
    versions = dict(re.findall(r"^  ([a-z][^:\n]*): (.*)$", head.partition("TOOL VERSIONS:")[2], flags=re.M))
    return {"fields": fields, "env": env, "versions": versions, "stdout": stdout, "stderr": stderr}


# ----------------------------------------------------------------------- log content
def test_every_gate_log_has_argv_cwd_env_versions_exit_code_and_both_streams(tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    code, out = run_main(tmp_path, [
        {"name": "good", "argv": OK, "cwd": str(work)},
        {"name": "bad", "argv": BAD, "cwd": str(work), "env": {"PYTHONPATH": "/somewhere"}},
    ])
    assert code == 1
    assert sorted(p.name for p in out.iterdir()) == ["01-good.log", "02-bad.log", "SUMMARY.md"]

    bad = parse_log((out / "02-bad.log").read_text())
    f = bad["fields"]
    assert (f["GATE"], f["STATUS"], f["EXIT CODE"]) == ("bad", "FAIL", "3")
    assert json.loads(f["ARGV"]) == BAD
    assert f["CWD"] == str(work)
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", f["STARTED (UTC)"])
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", f["FINISHED (UTC)"])
    assert float(f["DURATION (s)"]) >= 0.0
    assert bad["env"]["PYTHONPATH"] == "/somewhere"
    assert bad["env"]["PYTHONDONTWRITEBYTECODE"] == "1"
    for key in ("DRA_REQUIRE_MODELS", "FYP_DATA_ROOT", "TMPDIR", "DRA_DATABASE_URL"):
        assert key in bad["env"], key  # recorded even when unset: "(unset)" is information
    assert bad["versions"] == FAKE_VERSIONS
    assert (bad["stdout"], bad["stderr"]) == ("before", "boom")

    good = parse_log((out / "01-good.log").read_text())
    assert (good["fields"]["STATUS"], good["fields"]["EXIT CODE"]) == ("PASS", "0")
    assert (good["stdout"], good["stderr"]) == ("hello out", "hello err")
    assert "PYTEST SKIPPED" not in good["fields"]  # only the pytest gate has one


def test_the_log_keeps_the_complete_output_not_a_tail(tmp_path):
    code, out = run_main(tmp_path, [{"name": "big", "argv": program(
        "print('x' * 300000); import sys; print('y' * 200000, file=sys.stderr)")}])
    assert code == 0
    log = parse_log((out / "01-big.log").read_text())
    assert (len(log["stdout"]), len(log["stderr"])) == (300000, 200000)


def test_a_gate_that_cannot_start_is_a_failure_with_exit_127(tmp_path):
    code, out = run_main(tmp_path, [{"name": "ghost", "argv": ["/nonexistent/definitely-not-here", "--x"]}])
    assert code == 1
    log = parse_log((out / "01-ghost.log").read_text())
    assert (log["fields"]["STATUS"], log["fields"]["EXIT CODE"]) == ("FAIL", "127")
    assert "could not start '/nonexistent/definitely-not-here'" in log["stderr"]


def test_a_gate_that_exceeds_the_timeout_is_killed_and_fails(tmp_path):
    code, out = run_main(tmp_path, [
        {"name": "hang", "argv": program("import time; print('started', flush=True); time.sleep(60)")},
        {"name": "after", "argv": OK},
    ], "--timeout", "1")
    assert code == 1
    log = parse_log((out / "01-hang.log").read_text())
    assert (log["fields"]["STATUS"], log["fields"]["EXIT CODE"]) == ("TIMEOUT", "(timeout)")
    assert "killed after the 1 s timeout" in log["stderr"]
    assert log["stdout"] == "started"  # what it had printed before the kill is kept
    assert parse_log((out / "02-after.log").read_text())["fields"]["STATUS"] == "PASS"
    assert "**TIMEOUT**" in (out / "SUMMARY.md").read_text()


# ---------------------------------------------------------------------- exit and summary
def test_one_failing_gate_makes_the_run_red_and_the_exit_status_non_zero(tmp_path):
    code, out = run_main(tmp_path, [{"name": "a", "argv": OK}, {"name": "b", "argv": BAD}, {"name": "c", "argv": OK}])
    assert code == 1
    summary = (out / "SUMMARY.md").read_text()
    assert "- Result: **RED**: 1 of 3 gate(s) FAILED: **b**" in summary
    assert "| 02 | b | **FAIL** | 3 |" in summary
    assert "| 01 | a | PASS | 0 |" in summary and "| 03 | c | PASS | 0 |" in summary
    assert "GREEN" not in summary
    assert "[02-b.log](02-b.log)" in summary


def test_a_failure_does_not_stop_the_gates_after_it(tmp_path):
    code, out = run_main(tmp_path, [{"name": "first", "argv": BAD}, {"name": "second", "argv": OK}])
    assert code == 1
    assert parse_log((out / "02-second.log").read_text())["fields"]["STATUS"] == "PASS"


def test_all_passing_is_green_and_exits_zero(tmp_path):
    code, out = run_main(tmp_path, [{"name": "a", "argv": OK}, {"name": "b", "argv": OK}])
    assert code == 0
    summary = (out / "SUMMARY.md").read_text()
    assert "- Result: **GREEN**: all 2 gate(s) passed." in summary
    assert "RED" not in summary and "FAIL" not in summary


def test_the_summary_names_the_command_and_has_a_repository_line(tmp_path):
    _, out = run_main(tmp_path, [{"name": "a", "argv": OK}])
    summary = (out / "SUMMARY.md").read_text()
    assert re.search(r"- Command: `python3 scripts/run_gates.py --gates-file \S+ --out \S+`", summary)
    # A git checkout names its HEAD; an exported copy (no .git) says so instead of guessing.
    assert re.search(r"- Repository: (`[0-9a-f]{40}` on `\S+`, working tree (clean|dirty \(\d+ entries\))"
                     r"|unknown \(not a git checkout or git is unavailable\))", summary)


def test_git_state_names_head_branch_and_dirtiness_of_a_checkout(tmp_path, monkeypatch):
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path.parent))
    repo = tmp_path / "checkout"
    repo.mkdir()
    git = ["git", "-c", "user.email=t@example.invalid", "-c", "user.name=t"]
    for args in (["init", "-q", "-b", "main"], ["commit", "-q", "--allow-empty", "-m", "base"]):
        subprocess.run([*git, *args], cwd=repo, check=True, capture_output=True)
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True).stdout.strip()
    assert run_gates.git_state(repo) == f"`{head}` on `main`, working tree clean"
    (repo / "scratch.txt").write_text("x")
    assert run_gates.git_state(repo) == f"`{head}` on `main`, working tree dirty (1 entries)"


def test_git_state_of_a_directory_that_is_not_a_checkout_says_unknown(tmp_path, monkeypatch):
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path.parent))
    assert run_gates.git_state(tmp_path) == "unknown (not a git checkout or git is unavailable)"


# ------------------------------------------------------------------------- pytest skips
@pytest.mark.parametrize("stdout,expected", [
    ("....\n697 passed, 7 skipped, 1 warning in 8.45s\n", "7"),
    ("....\n704 passed, 1 warning in 8.59s\n", "0"),
    ("1 failed, 5 passed, 2 skipped in 0.12s\n", "2"),
    ("============ 3 passed, 12 skipped in 1.00s ============\n", "12"),
    ("no tests ran in 0.01s\n", "0"),
    ("Traceback (most recent call last):\nKeyError\n", "unknown"),
    ("", "unknown"),
    # the conftest banner mentions a count too, but only the final summary line counts
    ("!!! 7 MODEL-DEPENDENT TEST(S) NOT RUN !!!\n  SKIPPED  tests/x.py::t\n697 passed, 7 skipped in 8.45s\n", "7"),
    ("3 skipped in 0.1s\nsome later chatter\n5 passed in 0.3s\n", "0"),  # the LAST summary line wins
])
def test_count_pytest_skips(stdout, expected):
    assert run_gates.count_pytest_skips(stdout) == expected


def test_the_pytest_gate_records_its_skip_count_in_log_and_summary(tmp_path):
    code, out = run_main(tmp_path, [
        {"name": "pytest", "argv": program("print('697 passed, 7 skipped, 1 warning in 8.45s')")},
        {"name": "other", "argv": program("print('7 skipped')")},
    ])
    assert code == 0
    assert parse_log((out / "01-pytest.log").read_text())["fields"]["PYTEST SKIPPED"] == "7"
    assert "PYTEST SKIPPED" not in (out / "02-other.log").read_text()
    summary = (out / "SUMMARY.md").read_text()
    assert re.search(r"\| 01 \| pytest \| PASS \| 0 \| [\d.]+ \| 7 \| \[01-pytest\.log\]", summary)
    assert re.search(r"\| 02 \| other \| PASS \| 0 \| [\d.]+ \| - \|", summary)  # no skip count for other gates
    assert "pytest reports `7` skipped test(s)" in summary


def test_a_pytest_gate_with_no_summary_line_reports_unknown_not_zero(tmp_path):
    _, out = run_main(tmp_path, [{"name": "pytest", "argv": program("print('collected nothing useful')")}])
    assert parse_log((out / "01-pytest.log").read_text())["fields"]["PYTEST SKIPPED"] == "unknown"


# ------------------------------------------------------------------- dry run and --only
def test_dry_run_executes_nothing_and_says_so(tmp_path):
    marker = tmp_path / "ran.txt"
    gates = [{"name": "touch", "argv": program(f"open({str(marker)!r}, 'w').write('ran')")}]
    code, out = run_main(tmp_path, gates, "--dry-run")
    assert code == 0
    assert not marker.exists()
    log = parse_log((out / "01-touch.log").read_text())
    assert (log["fields"]["STATUS"], log["fields"]["EXIT CODE"]) == ("DRY-RUN", "(not executed: dry run)")
    summary = (out / "SUMMARY.md").read_text()
    assert "DRY RUN: no gate was executed" in summary and "GREEN" not in summary


def test_the_built_in_gates_are_the_documented_commands(tmp_path):
    out = tmp_path / "out"
    # --timeout is a safety net: if a regression made --dry-run EXECUTE the real gates, the
    # pytest gate would re-run this very test; the timeout kills that chain after 5 s.
    assert run_gates.main(["--dry-run", "--timeout", "5", "--out", str(out)], versions_fn=fake_versions) == 0
    logs = {p.name: parse_log(p.read_text()) for p in out.glob("*.log")}
    assert sorted(logs) == ["01-build.log", "02-pytest.log", "03-vitest.log", "04-tsc.log", "05-eslint.log"]
    expected = {
        "01-build.log": (["npm", "run", "build"], REPO),
        "02-pytest.log": (["../.venv/bin/python", "-m", "pytest", "tests", "-q", "-p", "no:cacheprovider"],
                          REPO / "backend"),
        "03-vitest.log": (["./node_modules/.bin/vitest", "run", "--no-cache"], REPO),
        "04-tsc.log": (["./node_modules/.bin/tsc", "--noEmit"], REPO),
        "05-eslint.log": (["./node_modules/.bin/eslint", "."], REPO),
    }
    for name, (argv, cwd) in expected.items():
        fields = logs[name]["fields"]
        assert json.loads(fields["ARGV"]) == argv, name
        assert fields["CWD"] == str(cwd), name
        assert logs[name]["env"]["PYTHONDONTWRITEBYTECODE"] == "1", name
    assert logs["02-pytest.log"]["env"]["PYTHONPATH"] == "."
    assert "mktemp" in logs["02-pytest.log"]["env"]["TMPDIR"]  # a fresh directory per run
    assert all(log["versions"] == FAKE_VERSIONS for log in logs.values())


def test_only_runs_a_subset_and_keeps_each_gates_number(tmp_path):
    gates = [{"name": "a", "argv": OK}, {"name": "b", "argv": OK}, {"name": "c", "argv": OK}]
    code, out = run_main(tmp_path, gates, "--only", "c", name="one")
    assert code == 0
    assert sorted(p.name for p in out.iterdir()) == ["03-c.log", "SUMMARY.md"]
    assert "| 03 | c |" in (out / "SUMMARY.md").read_text()
    code, out = run_main(tmp_path, gates, "--only", "a,c", name="two")
    assert code == 0
    assert sorted(p.name for p in out.iterdir()) == ["01-a.log", "03-c.log", "SUMMARY.md"]
    code, out = run_main(tmp_path, gates, "--only", "a", "--only", "b", name="three")  # repeated option
    assert code == 0
    assert sorted(p.name for p in out.iterdir()) == ["01-a.log", "02-b.log", "SUMMARY.md"]


def test_an_unknown_gate_name_is_a_usage_error_and_writes_nothing(tmp_path, capsys):
    code, out = run_main(tmp_path, [{"name": "a", "argv": OK}], "--only", "nope")
    assert code == 2
    assert not out.exists()
    assert "unknown gate(s) ['nope']; known: a" in capsys.readouterr().err


@pytest.mark.parametrize("bad", [
    [], {"name": "a"}, [{"name": "a"}], [{"name": "a b", "argv": ["x"]}], [{"name": "a", "argv": []}],
    [{"name": "a", "argv": ["x"]}, {"name": "a", "argv": ["y"]}],
])
def test_a_malformed_gates_file_is_a_usage_error(tmp_path, bad, capsys):
    out = tmp_path / "out"
    code = run_gates.main(["--gates-file", write_gates(tmp_path, bad), "--out", str(out)], versions_fn=fake_versions)
    assert code == 2 and not out.exists()
    assert "cannot read the gates file" in capsys.readouterr().err


# ----------------------------------------------------------- the real command-line entry
def cli(tmp_path, gates, *extra):
    out = tmp_path / "cli-out"
    done = subprocess.run([PY, str(SCRIPT), "--gates-file", write_gates(tmp_path, gates), "--out", str(out), *extra],
                          capture_output=True, text=True, timeout=120)
    return done, out


def test_the_process_exits_non_zero_when_a_gate_failed(tmp_path):
    done, out = cli(tmp_path, [{"name": "ok", "argv": OK}, {"name": "bad", "argv": BAD}, {"name": "ok2", "argv": OK}])
    assert done.returncode == 1, (done.stdout, done.stderr)
    assert "RED: failed: bad" in done.stdout
    assert "**RED**" in (out / "SUMMARY.md").read_text()
    # the real tool versions were collected, not the injected ones
    versions = parse_log((out / "01-ok.log").read_text())["versions"]
    assert versions["python (this script)"] == sys.version.split()[0]
    assert set(versions) == set(FAKE_VERSIONS)


def test_the_process_exits_zero_when_every_gate_passed(tmp_path):
    done, out = cli(tmp_path, [{"name": "ok", "argv": OK}])
    assert done.returncode == 0, (done.stdout, done.stderr)
    assert "GREEN: all gates passed." in done.stdout
    assert "**GREEN**" in (out / "SUMMARY.md").read_text()


REAL_VERSION_FORMS = {
    "python (.venv)": (r"Python 3\.\d+", REPO / ".venv" / "bin" / "python"),
    "pytest": (r"pytest \d+\.\d+", REPO / ".venv" / "bin" / "python"),
    "vitest": (r"vitest/\d+\.\d+", REPO / "node_modules" / ".bin" / "vitest"),
    "tsc": (r"Version \d+\.\d+", REPO / "node_modules" / ".bin" / "tsc"),
    "eslint": (r"v\d+\.\d+", REPO / "node_modules" / ".bin" / "eslint"),
}


def test_a_dry_run_of_the_real_gate_list_exits_zero_and_lists_the_real_tool_versions(tmp_path):
    """Whatever tool this checkout has is reported with its real version; one it lacks (an
    exported copy has no node_modules) is reported as unavailable, never left blank."""
    out = tmp_path / "dry"
    done = subprocess.run([PY, str(SCRIPT), "--dry-run", "--timeout", "5", "--out", str(out)],  # see the safety-net note above
                          capture_output=True, text=True, timeout=120)
    assert done.returncode == 0, (done.stdout, done.stderr)
    versions = parse_log((out / "04-tsc.log").read_text())["versions"]
    assert set(versions) == set(FAKE_VERSIONS)
    for tool, (form, binary) in REAL_VERSION_FORMS.items():
        if binary.exists():
            assert re.fullmatch(form + r".*", versions[tool]), (tool, versions[tool])
        else:
            assert versions[tool].startswith("unavailable ("), (tool, versions[tool])
    for tool, command in (("node", "node"), ("npm", "npm")):
        if shutil.which(command):
            assert re.fullmatch(r"v?\d+\.\d+.*", versions[tool]), (tool, versions[tool])


def test_a_tool_the_checkout_lacks_is_reported_unavailable_not_omitted_or_fatal(tmp_path):
    versions = run_gates.collect_versions(tmp_path)  # an empty directory: no .venv, no node_modules
    assert list(versions) == list(FAKE_VERSIONS)  # every tool still has a line, in the same order
    for tool in ("python (.venv)", "pytest", "vitest", "tsc", "eslint"):
        assert versions[tool].startswith("unavailable ("), (tool, versions[tool])
    assert versions["python (this script)"] == sys.version.split()[0]
