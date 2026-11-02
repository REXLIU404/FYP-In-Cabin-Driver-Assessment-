"""ST-COLDSTART-01's SUMMARY.md must say what happened to the scratch checkout, which lives
under a fresh mktemp directory. These tests run the REAL script with its steps stubbed to
succeed (the same way the review did): the summary and the cleanup code are unchanged, so the
slow clone/venv/npm/gates steps are not executed."""
import os
import re
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "coldstart_check.sh"
SOURCE = SCRIPT.read_text()


def _stubbed(dest: Path) -> None:
    """The script with every step call replaced by one recorded success: the summary and the
    trailing cleanup run exactly as in the real PASS."""
    src = re.sub(r'COMMIT="\$\(git -C "\$SRC" rev-parse "\$\{1:-HEAD\}"\)"',
                 'COMMIT="stubbed-commit"', SOURCE)
    src = re.sub(r'note "ST-COLDSTART-01 commit.*?\nsummary PASS',
                 'STEPS+=("| stub | PASS | 0 | 0 |")\nsummary PASS', src, flags=re.DOTALL)
    dest.write_text(src)


def _run(tmp_path: Path, env_extra: dict) -> Path:
    out = tmp_path / "out"
    script = tmp_path / "coldstart_check.sh"
    _stubbed(script)
    env = {k: v for k, v in os.environ.items() if k not in ("COLDSTART_KEEP", "COLDSTART_OUT")}
    env.update({"TMPDIR": str(tmp_path), "COLDSTART_OUT": str(out), "PYTHON": sys.executable}, **env_extra)
    done = subprocess.run(["bash", str(script)], env=env, capture_output=True, text=True, timeout=120)
    assert done.returncode == 0, done.stdout + done.stderr
    return out


def test_a_passing_default_run_records_that_the_scratch_checkout_was_removed(tmp_path):
    """Review R1: the default PASS removes the scratch checkout right after the summary is
    written, so SUMMARY.md must say the path no longer exists."""
    out = _run(tmp_path, {})
    summary = (out / "SUMMARY.md").read_text()
    assert "(removed after PASS)" in summary
    assert "(kept: COLDSTART_KEEP=1)" not in summary
    assert not list(tmp_path.glob("coldstart.*")), "the scratch checkout must be gone"


def test_a_passing_run_with_coldstart_keep_records_that_it_was_kept(tmp_path):
    """Review R1: with COLDSTART_KEEP=1 the checkout survives, and SUMMARY.md must say so -
    the two runs must not produce the same summary."""
    out = _run(tmp_path, {"COLDSTART_KEEP": "1"})
    summary = (out / "SUMMARY.md").read_text()
    assert "(kept: COLDSTART_KEEP=1)" in summary
    assert "(removed after PASS)" not in summary
    assert list(tmp_path.glob("coldstart.*")), "the scratch checkout must be kept"
