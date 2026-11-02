#!/usr/bin/env python3
"""Run the release gates and keep the raw evidence: one log per gate plus SUMMARY.md.

Usage (run from anywhere; standard library only):

    python3 scripts/run_gates.py                      # all five gates
    python3 scripts/run_gates.py --only pytest,tsc    # a subset (names are comma separated)
    python3 scripts/run_gates.py --dry-run            # write the logs' headers, execute nothing
    python3 scripts/run_gates.py --out /tmp/gates     # default: docs/evidence/<UTC date>/gates

The gates are the commands of plan Task 10 Step 4, unchanged:

    01 build    npm run build
    02 pytest   (cd backend && TMPDIR=$(mktemp -d) PYTHONPATH=. ../.venv/bin/python -m pytest tests -q -p no:cacheprovider)
    03 vitest   ./node_modules/.bin/vitest run --no-cache
    04 tsc      ./node_modules/.bin/tsc --noEmit
    05 eslint   ./node_modules/.bin/eslint .

Each gate gets ``NN-<name>.log``: its argv, working directory, the environment variables
that matter, the tool versions, the exit code, the pytest skip count (``pytest`` gate only)
and the COMPLETE stdout and stderr. ``SUMMARY.md`` ties them together. The numbering is the
gate's place in the full list, so ``--only vitest`` still writes ``03-vitest.log``.

Exit status: 0 when every selected gate passed (or on --dry-run), 1 when any gate failed
or timed out, 2 for a usage error. A failed gate does not stop the others: the point is the
complete picture.

``--gates-file FILE`` replaces the built-in list with a JSON list of
``{"name", "argv", "cwd"?, "env"?}`` objects (used by the tests, and for a custom gate set).

This script writes evidence; it does not judge it. A real run's logs are archived by the
person who ran it, not generated into a commit by this script.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import signal
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DEFAULT_TIMEOUT_S = 1800

# Environment variables worth recording in a log: the ones that change what a gate does.
KEY_ENV = ("PYTHONDONTWRITEBYTECODE", "PYTHONPATH", "TMPDIR", "DRA_REQUIRE_MODELS",
           "DRA_DATABASE_URL", "FYP_DATA_ROOT", "NODE_ENV", "CI", "VIRTUAL_ENV")

# Tool name -> (argv relative to the repo, cwd).
VERSION_COMMANDS: dict[str, list[str]] = {
    "python (this script)": [],  # filled from sys.version
    "python (.venv)": [".venv/bin/python", "--version"],
    "pytest": [".venv/bin/python", "-m", "pytest", "--version"],
    "node": ["node", "--version"],
    "npm": ["npm", "--version"],
    "vitest": ["./node_modules/.bin/vitest", "--version"],
    "tsc": ["./node_modules/.bin/tsc", "--version"],
    "eslint": ["./node_modules/.bin/eslint", "--version"],
}


@dataclass(frozen=True)
class Gate:
    name: str
    argv: list[str]
    cwd: Path
    env: dict[str, str] = field(default_factory=dict)
    fresh_tmpdir: bool = False  # the pytest gate runs with TMPDIR=$(mktemp -d)


@dataclass
class GateResult:
    gate: Gate
    index: int
    status: str  # PASS | FAIL | TIMEOUT | DRY-RUN
    exit_code: int | None
    started: str
    finished: str
    duration_s: float
    env: dict[str, str]
    stdout: str = ""
    stderr: str = ""
    skipped: str | None = None  # pytest only: a count, or "unknown"
    log_name: str = ""

    @property
    def failed(self) -> bool:
        return self.status in ("FAIL", "TIMEOUT")


def builtin_gates(repo: Path = REPO) -> list[Gate]:
    return [
        Gate("build", ["npm", "run", "build"], repo),
        Gate("pytest", ["../.venv/bin/python", "-m", "pytest", "tests", "-q", "-p", "no:cacheprovider"],
             repo / "backend", {"PYTHONPATH": "."}, fresh_tmpdir=True),
        Gate("vitest", ["./node_modules/.bin/vitest", "run", "--no-cache"], repo),
        Gate("tsc", ["./node_modules/.bin/tsc", "--noEmit"], repo),
        Gate("eslint", ["./node_modules/.bin/eslint", "."], repo),
    ]


def load_gates_file(path: Path) -> list[Gate]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list) or not raw:
        raise ValueError("a gates file must be a non-empty JSON list")
    gates = []
    for item in raw:
        if not isinstance(item, dict) or not isinstance(item.get("name"), str) \
                or not re.fullmatch(r"[A-Za-z0-9_.-]+", item["name"]):
            raise ValueError("every gate needs a 'name' of letters, digits, '_', '.' or '-' (it names the log file)")
        argv = item.get("argv")
        if not isinstance(argv, list) or not argv or not all(isinstance(a, str) for a in argv):
            raise ValueError(f"gate {item['name']!r}: 'argv' must be a non-empty list of strings")
        gates.append(Gate(item["name"], argv, Path(item.get("cwd") or REPO),
                          {str(k): str(v) for k, v in (item.get("env") or {}).items()}))
    if len({g.name for g in gates}) != len(gates):
        raise ValueError("gate names must be unique")
    return gates


# --------------------------------------------------------------------------- versions
def _first_line(text: str) -> str:
    lines = text.strip().splitlines()
    return lines[0].strip() if lines else ""


def _version_of(name: str, argv: list[str], repo: Path) -> tuple[str, str]:
    command = [str(repo / argv[0]) if argv[0].startswith((".venv", "./")) else argv[0], *argv[1:]]
    try:
        done = subprocess.run(command, cwd=repo, capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError) as exc:
        return name, f"unavailable ({type(exc).__name__}: {exc})"
    out = _first_line(done.stdout) or _first_line(done.stderr)  # pytest --version writes to stderr on some versions
    return name, out if done.returncode == 0 and out else f"unavailable (exit {done.returncode}: {out})"


def collect_versions(repo: Path = REPO) -> dict[str, str]:
    """Version string of every tool a gate uses. Concurrent: a few slow `--version`s."""
    versions = {"python (this script)": sys.version.split()[0]}
    commands = {n: a for n, a in VERSION_COMMANDS.items() if a}
    with ThreadPoolExecutor(max_workers=len(commands)) as pool:
        for name, text in pool.map(lambda item: _version_of(item[0], item[1], repo), commands.items()):
            versions[name] = text
    return {name: versions[name] for name in VERSION_COMMANDS}


# ------------------------------------------------------------------------- execution
_SUMMARY_LINE = re.compile(r"\b(?:passed|failed|errors?|skipped|deselected|no tests ran)\b.*\bin [\d.]+s\b")


def count_pytest_skips(stdout: str) -> str:
    """The number of skipped tests from pytest's final summary line (the LAST line that
    looks like one), "0" when that line names no skips, "unknown" when there is no
    summary line at all (pytest crashed, or was not run to completion)."""
    summary = [line for line in stdout.splitlines() if _SUMMARY_LINE.search(line)]
    if not summary:
        return "unknown"
    found = re.search(r"(\d+) skipped", summary[-1])
    return found.group(1) if found else "0"


def _decode(data: bytes | None) -> str:
    return (data or b"").decode("utf-8", errors="replace")


def _utc(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def effective_env(gate: Gate, tmpdir: str | None = None) -> dict[str, str]:
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env.update(gate.env)
    if tmpdir:
        env["TMPDIR"] = tmpdir
    return env


def run_gate(gate: Gate, index: int, *, timeout_s: float, dry_run: bool) -> GateResult:
    started = datetime.now(timezone.utc)
    tmpdir = tempfile.mkdtemp(prefix="dra-gate-pytest-") if gate.fresh_tmpdir and not dry_run else None
    env = effective_env(gate, tmpdir)
    shown = {key: env.get(key, "(unset)") for key in KEY_ENV}
    if gate.fresh_tmpdir and dry_run:
        shown["TMPDIR"] = "(a fresh mktemp -d directory is created at run time)"
    result = GateResult(gate, index, "DRY-RUN", None, _utc(started), _utc(started), 0.0, shown)
    if dry_run:
        return result

    clock = time.perf_counter()
    status, code, out, err = "PASS", None, b"", b""
    try:
        proc = subprocess.Popen(gate.argv, cwd=gate.cwd, env=env, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, start_new_session=hasattr(os, "killpg"))
    except OSError as exc:
        status, code, err = "FAIL", 127, f"could not start {gate.argv[0]!r}: {type(exc).__name__}: {exc}\n".encode()
    else:
        try:
            out, err = proc.communicate(timeout=timeout_s)
            code = proc.returncode
            status = "PASS" if code == 0 else "FAIL"
        except subprocess.TimeoutExpired:
            if hasattr(os, "killpg"):
                os.killpg(proc.pid, signal.SIGKILL)  # the whole tree: npm -> node -> workers
            else:  # pragma: no cover - non-POSIX
                proc.kill()
            out, err = proc.communicate()
            status, code = "TIMEOUT", None
            err += f"\n[run_gates] killed after the {timeout_s:g} s timeout\n".encode()
    result.status, result.exit_code = status, code
    result.stdout, result.stderr = _decode(out), _decode(err)
    result.duration_s = round(time.perf_counter() - clock, 2)
    result.finished = _utc(datetime.now(timezone.utc))
    if gate.name == "pytest":
        result.skipped = count_pytest_skips(result.stdout)
    return result


# ----------------------------------------------------------------------- evidence files
def log_text(result: GateResult, versions: dict[str, str]) -> str:
    gate = result.gate
    exit_text = ("(not executed: dry run)" if result.status == "DRY-RUN"
                 else "(timeout)" if result.exit_code is None else str(result.exit_code))
    lines = [
        f"GATE: {gate.name}",
        f"STATUS: {result.status}",
        f"EXIT CODE: {exit_text}",
        f"STARTED (UTC): {result.started}",
        f"FINISHED (UTC): {result.finished}",
        f"DURATION (s): {result.duration_s}",
        f"ARGV: {json.dumps(gate.argv)}",
        f"CWD: {gate.cwd}",
        "ENV (selected):",
        *[f"  {key}={value}" for key, value in result.env.items()],
        "TOOL VERSIONS:",
        *[f"  {name}: {value}" for name, value in versions.items()],
    ]
    if result.skipped is not None:
        lines.append(f"PYTEST SKIPPED: {result.skipped}")
    lines += ["----- STDOUT -----", result.stdout.rstrip("\n"), "----- END STDOUT -----",
              "----- STDERR -----", result.stderr.rstrip("\n"), "----- END STDERR -----", ""]
    return "\n".join(lines)


def git_state(repo: Path) -> str:
    def git(*args: str) -> str | None:
        try:
            done = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, timeout=30)
        except (OSError, subprocess.SubprocessError):
            return None
        return done.stdout.strip() if done.returncode == 0 else None
    head, branch, dirty = git("rev-parse", "HEAD"), git("branch", "--show-current"), git("status", "--porcelain")
    if head is None:
        return "unknown (not a git checkout or git is unavailable)"
    entries = len([line for line in (dirty or "").splitlines() if line.strip()])
    return f"`{head}` on `{branch or '(detached)'}`, working tree {'dirty (' + str(entries) + ' entries)' if entries else 'clean'}"


def summary_text(results: list[GateResult], *, command: str, repo: Path, dry_run: bool, now: datetime) -> str:
    failed = [r for r in results if r.failed]
    if dry_run:
        verdict = "DRY RUN: no gate was executed, so this says nothing about the code."
    elif failed:
        verdict = f"**RED**: {len(failed)} of {len(results)} gate(s) FAILED: " + ", ".join(f"**{r.gate.name}**" for r in failed)
    else:
        verdict = f"**GREEN**: all {len(results)} gate(s) passed."
    lines = [
        "# Gate run summary", "",
        f"- Result: {verdict}",
        f"- Generated (UTC): `{_utc(now)}`",
        f"- Repository: {git_state(repo)}",
        f"- Command: `{command}`", "",
        "| # | Gate | Status | Exit | Duration (s) | Skipped | Log |",
        "|---|------|--------|------|--------------|---------|-----|",
    ]
    for r in results:
        status = f"**{r.status}**" if r.failed else r.status
        exit_cell = "-" if r.exit_code is None else str(r.exit_code)
        lines.append(f"| {r.index:02d} | {r.gate.name} | {status} | {exit_cell} | {r.duration_s} | "
                     f"{r.skipped if r.skipped is not None else '-'} | [{r.log_name}]({r.log_name}) |")
    skipped = next((r.skipped for r in results if r.gate.name == "pytest"), None)
    if skipped not in (None, "0"):
        lines += ["", f"Note: pytest reports `{skipped}` skipped test(s). A skip proves nothing; "
                      "the pytest log names them, and `DRA_REQUIRE_MODELS=1` turns a missing-model skip into a failure."]
    if failed:
        lines += ["", "## Failed gates", ""] + [f"- **{r.gate.name}**: `{r.status}`, see [{r.log_name}]({r.log_name})" for r in failed]
    return "\n".join(lines) + "\n"


# ------------------------------------------------------------------------------- main
def default_out_dir(repo: Path, now: datetime) -> Path:
    return repo / "docs" / "evidence" / now.strftime("%Y-%m-%d") / "gates"


def main(argv: list[str] | None = None, *, versions_fn=collect_versions) -> int:
    parser = argparse.ArgumentParser(description="Run the release gates and write raw logs plus SUMMARY.md.")
    parser.add_argument("--out", type=Path, help="output directory (default: docs/evidence/<UTC date>/gates)")
    parser.add_argument("--only", action="append", default=[], metavar="NAME[,NAME]", help="run only these gates")
    parser.add_argument("--dry-run", action="store_true", help="write the log headers; execute nothing")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_S, help="seconds allowed per gate")
    parser.add_argument("--gates-file", type=Path, help="JSON list of gates replacing the built-in five")
    args = parser.parse_args(argv)

    try:
        gates = load_gates_file(args.gates_file) if args.gates_file else builtin_gates()
    except (OSError, ValueError) as exc:
        print(f"error: cannot read the gates file: {exc}", file=sys.stderr)
        return 2
    numbered = list(enumerate(gates, start=1))
    if args.only:
        wanted = [name.strip() for chunk in args.only for name in chunk.split(",") if name.strip()]
        unknown = [name for name in wanted if name not in {g.name for g in gates}]
        if unknown or not wanted:
            print(f"error: unknown gate(s) {unknown or args.only}; known: {', '.join(g.name for g in gates)}", file=sys.stderr)
            return 2
        numbered = [(i, g) for i, g in numbered if g.name in wanted]

    now = datetime.now(timezone.utc)
    out_dir = args.out or default_out_dir(REPO, now)
    out_dir.mkdir(parents=True, exist_ok=True)
    versions = versions_fn(REPO)
    red = sys.stdout.isatty()

    results = []
    for index, gate in numbered:
        print(f"[{index:02d}] {gate.name}: {'(dry run) ' if args.dry_run else ''}{' '.join(gate.argv)}", flush=True)
        result = run_gate(gate, index, timeout_s=args.timeout, dry_run=args.dry_run)
        result.log_name = f"{index:02d}-{gate.name}.log"
        (out_dir / result.log_name).write_text(log_text(result, versions), encoding="utf-8")
        label = f"\033[31m{result.status}\033[0m" if red and result.failed else result.status
        print(f"     -> {label}" + ("" if result.exit_code is None else f" (exit {result.exit_code})")
              + (f", {result.skipped} skipped" if result.skipped not in (None, "0") else ""), flush=True)
        results.append(result)

    used = sys.argv[1:] if argv is None else argv
    command = " ".join(["python3 scripts/run_gates.py", *used])
    (out_dir / "SUMMARY.md").write_text(
        summary_text(results, command=command, repo=REPO, dry_run=args.dry_run, now=now), encoding="utf-8")
    failed = [r for r in results if r.failed]
    print(f"Logs and SUMMARY.md: {out_dir}")
    if failed:
        print(("\033[31m" if red else "") + "RED: failed: " + ", ".join(r.gate.name for r in failed)
              + ("\033[0m" if red else ""))
        return 1
    print("DRY RUN: nothing was executed." if args.dry_run else "GREEN: all gates passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
