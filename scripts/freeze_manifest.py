#!/usr/bin/env python3
"""Freeze manifest: pin source, models, data splits and dependencies by hash/version.

Usage (no arguments required; run from anywhere):

    python3 scripts/freeze_manifest.py > manifest.md

Writes a Markdown report to stdout. It records

  1. git HEAD, branch and working-tree (dirty) state;
  2. SHA-256 + byte size of the model checkpoints under ``ml/outputs/`` (git-ignored
     binaries -- the repo stores only their hashes, never the weights) and whether each one
     still matches the frozen baseline hash embedded below;
  3. SHA-256 + row count of the ``eda_outputs/processed/**/*.csv`` split files;
  4. the package versions actually installed in ``.venv`` (not requirements lower bounds);
  5. node / npm versions and the installed JavaScript dependency versions;
  6. whether any development SQLite database exists in the repo.

Exit status: 0 when every baseline model checkpoint is present and matches its frozen hash,
1 otherwise (so the script doubles as the "models unchanged" gate for later tasks).

Environment:
  FYP_DATA_ROOT   directory that contains ``eda_outputs/``. When unset the script tries the
                  repo root, then the sibling repo ``~/Desktop/FYP-In-Cabin-Driver-Assessment-``
                  (the same default ``ml/README.md`` documents).

The script is read-only: it never writes to the repo, the data root or the model files.
Standard library only.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import platform
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# Frozen baseline. Measured independently by the controller and the audit record on
# 2026-10-12; this script recomputes them and reports MATCH / MISMATCH.
# ---------------------------------------------------------------------------
MODEL_BASELINE: dict[str, tuple[str, int]] = {
    "ml/outputs/vision/mobilenetv3_large_vision.onnx": (
        "b3a42e8dd4553355b1fd7d9e7fe3d28e318decb894e76eb029489b7ff2e90bcf",
        16849378,
    ),
    "ml/outputs/vision/mobilenetv3_large_vision.pt": (
        "196ca7b151d84e0c4a8eac87128da9dd8f22c894984a991ef611536bb523e7c7",
        17066477,
    ),
    "ml/outputs/telemetry/xgb_telemetry.json": (
        "9802cb06ca98f0c1befaf851fa7668cfec70e005cf8bb3884e49d7d45d7aec07",
        629723,
    ),
}
MODEL_SUFFIXES = {".onnx", ".pt", ".pth", ".pkl", ".joblib", ".ubj", ".safetensors"}
DEFAULT_SIBLING_DATA_ROOT = Path.home() / "Desktop" / "FYP-In-Cabin-Driver-Assessment-"
PRUNE_DIRS = {".git", "node_modules", ".venv", "dist", "__pycache__"}
DB_SUFFIXES = {".db", ".sqlite", ".sqlite3"}
# `pip freeze` never lists pip itself (on Python >= 3.12 it does list setuptools/wheel).
PIP_FREEZE_SKIPS = {"pip"}


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run(cmd: list[str], cwd: Path = REPO) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            cmd, cwd=cwd, capture_output=True, text=True, check=False, timeout=120
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return 127, f"{type(exc).__name__}: {exc}"
    return proc.returncode, (proc.stdout if proc.returncode == 0 else proc.stdout + proc.stderr).strip()


def md_table(header: list[str], rows: list[list[str]]) -> list[str]:
    out = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    for row in rows:
        out.append("| " + " | ".join(row) + " |")
    return out


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(REPO))
    except ValueError:
        return str(path)


# ---------------------------------------------------------------------------
# Sections
# ---------------------------------------------------------------------------
def section_git() -> list[str]:
    _, head = run(["git", "rev-parse", "HEAD"])
    _, branch = run(["git", "branch", "--show-current"])
    _, subject = run(["git", "log", "-1", "--format=%cI  %s"])
    _, status = run(["git", "status", "--porcelain"])
    dirty_lines = [line for line in status.splitlines() if line.strip()]
    lines = ["## 1. Source (git)", ""]
    lines += md_table(
        ["Item", "Value"],
        [
            ["HEAD", f"`{head}`"],
            ["Branch", f"`{branch}`"],
            ["HEAD commit", subject.replace("|", "\\|")],
            ["Working tree", "dirty" if dirty_lines else "clean"],
            ["Uncommitted entries", str(len(dirty_lines))],
        ],
    )
    if dirty_lines:
        lines += ["", "Uncommitted entries (`git status --porcelain`):", "", "```"]
        lines += dirty_lines
        lines += ["```"]
    return lines + [""]


def section_models() -> tuple[list[str], bool]:
    rows: list[list[str]] = []
    all_ok = True
    for relpath, (want_sha, want_bytes) in MODEL_BASELINE.items():
        path = REPO / relpath
        if not path.exists():  # also true for a dangling symlink
            rows.append([f"`{relpath}`", "-", "-", f"`{want_sha}`", "MISSING"])
            all_ok = False
            continue
        got_sha = sha256_of(path)
        got_bytes = path.stat().st_size
        ok = got_sha == want_sha and got_bytes == want_bytes
        all_ok &= ok
        target = os.path.realpath(path) if path.is_symlink() else "(regular file)"
        ignored = run(["git", "check-ignore", "-q", relpath])[0] == 0
        rows.append(
            [
                f"`{relpath}`",
                f"`{got_sha}`",
                f"{got_bytes}",
                f"`{want_sha}` / {want_bytes}",
                ("MATCH" if ok else "MISMATCH") + (", git-ignored" if ignored else ", NOT git-ignored"),
            ]
        )
    lines = ["## 2. Model checkpoints (`ml/outputs/`, git-ignored, hash-only)", ""]
    lines += md_table(
        ["File", "SHA-256 (recomputed)", "Bytes", "Frozen baseline (SHA-256 / bytes)", "Status"],
        rows,
    )
    lines += [""]
    links = []
    for relpath in MODEL_BASELINE:
        path = REPO / relpath
        if path.is_symlink():
            links.append(f"- `{relpath}` -> `{os.path.realpath(path)}`")
    if links:
        lines += ["Symlink targets (read-only, owned by the main repository):", ""] + links + [""]

    # Anything else that looks like a checkpoint but is not in the frozen baseline.
    extra: list[str] = []
    outputs = REPO / "ml" / "outputs"
    if outputs.is_dir():
        for path in sorted(outputs.rglob("*")):
            r = rel(path)
            if path.suffix.lower() in MODEL_SUFFIXES and r not in MODEL_BASELINE:
                extra.append(r)
    if extra:
        lines += ["Checkpoint-like files NOT covered by the baseline:", ""]
        lines += [f"- `{e}`" for e in extra] + [""]
    else:
        lines += ["No additional checkpoint-like files (`" + "`, `".join(sorted(MODEL_SUFFIXES)) + "`) under `ml/outputs/`.", ""]
    lines += [
        f"**Models unchanged vs frozen baseline: {'YES' if all_ok else 'NO'}**",
        "",
    ]
    return lines, all_ok


def resolve_data_root() -> tuple[Path | None, list[str]]:
    tried: list[str] = []
    candidates: list[Path] = []
    env = os.environ.get("FYP_DATA_ROOT")
    if env:
        candidates.append(Path(env).expanduser())
    candidates += [REPO, DEFAULT_SIBLING_DATA_ROOT]
    for cand in candidates:
        tried.append(str(cand))
        if (cand / "eda_outputs" / "processed").is_dir():
            return cand.resolve(), tried
    return None, tried


def count_csv_rows(path: Path) -> int:
    """Data rows (header excluded), counting records so quoted newlines are not miscounted."""
    with path.open("r", newline="", encoding="utf-8", errors="replace") as handle:
        reader = csv.reader(handle)
        total = sum(1 for _ in reader)
    return max(total - 1, 0)


def section_splits() -> list[str]:
    lines = ["## 3. Data splits (`eda_outputs/processed/**/*.csv`)", ""]
    root, tried = resolve_data_root()
    if root is None:
        lines += [
            "**NOT FOUND.** `eda_outputs/processed` was not located. Tried:",
            "",
        ] + [f"- `{t}`" for t in tried]
        lines += ["", "Set `FYP_DATA_ROOT` to the directory that contains `eda_outputs/`.", ""]
        print("warning: eda_outputs/processed not found; split hashes omitted", file=sys.stderr)
        return lines
    base = root / "eda_outputs" / "processed"
    files = sorted(base.rglob("*.csv"))
    lines += [f"Data root: `{root}` (not part of this repository; read-only).", ""]
    rows = []
    for path in files:
        rows.append(
            [
                f"`{path.relative_to(root / 'eda_outputs' / 'processed')}`",
                f"`{sha256_of(path)}`",
                str(path.stat().st_size),
                str(count_csv_rows(path)),
            ]
        )
    lines += md_table(["File (relative to `eda_outputs/processed/`)", "SHA-256", "Bytes", "Data rows"], rows)
    lines += ["", f"{len(files)} CSV files. Row counts exclude the header record.", ""]
    return lines


_VENV_PROBE = r"""
import importlib.metadata as md, json, re, sys
try:
    from packaging.requirements import Requirement
except Exception:
    Requirement = None
reqs = json.loads(sys.argv[1])
def norm(n): return re.sub(r"[-_.]+", "-", n).lower()
installed = {}
for d in md.distributions():
    n = d.metadata["Name"]
    if n: installed[norm(n)] = (n, d.version)
rows = []
for line in reqs:
    name = re.split(r"[\[<>=!~ ;@]", line, maxsplit=1)[0]
    got = installed.get(norm(name))
    ok = None
    if got and Requirement is not None:
        try: ok = Requirement(line).specifier.contains(got[1], prereleases=True)
        except Exception: ok = None
    rows.append([line, got[1] if got else None, ok])
print(json.dumps({
    "python": sys.version.split()[0],
    "executable": sys.executable,
    "prefix": sys.prefix,
    "count": len(installed),
    "rows": rows,
    "freeze": sorted(f"{norm(n)}=={v}" for n, v in installed.values()),
}))
"""


def read_requirement_lines(path: Path) -> list[str]:
    lines: list[str] = []
    if not path.exists():
        return lines
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if line and not line.startswith("-"):
            lines.append(line)
    return lines


def section_python() -> list[str]:
    lines = ["## 4. Python environment (`.venv`, actually installed)", ""]
    venv_python = REPO / ".venv" / "bin" / "python"
    if not venv_python.exists():
        return lines + ["**`.venv/bin/python` not found.**", ""]
    declared: list[str] = []
    sources: dict[str, str] = {}
    for fname in ("requirements.txt", "requirements-inference.txt"):
        for line in read_requirement_lines(REPO / "backend" / fname):
            declared.append(line)
            sources[line] = fname
    code, out = run([str(venv_python), "-I", "-c", _VENV_PROBE, json.dumps(declared)])
    if code != 0:
        return lines + [f"**Probe failed (exit {code}):** `{out[:300]}`", ""]
    data = json.loads(out.splitlines()[-1])
    lines += md_table(
        ["Item", "Value"],
        [
            ["Interpreter", f"`{rel(venv_python)}` -> `{data['executable']}`"],
            ["Python", f"`{data['python']}`"],
            ["Host platform", f"`{platform.platform()}`"],
            ["Installed distributions", str(data["count"])],
        ],
    )
    rows = []
    for spec, version, ok in data["rows"]:
        verdict = "n/a" if ok is None else ("ok" if ok else "VIOLATES SPEC")
        rows.append([f"`{spec}`", f"`{sources[spec]}`", f"`{version}`" if version else "NOT INSTALLED", verdict])
    lines += ["", "Declared requirements vs installed versions:", ""]
    lines += md_table(["Declared", "Declared in", "Installed", "Spec check"], rows)

    lock = REPO / "backend" / "requirements.lock.txt"
    lines += [""]
    if lock.exists():
        locked = {
            re.sub(r"[-_.]+", "-", m.group(1)).lower() + "==" + m.group(2)
            for m in (
                re.match(r"^([A-Za-z0-9_.\-]+)==(\S+)$", ln.strip())
                for ln in lock.read_text(encoding="utf-8").splitlines()
            )
            if m
        }
        # `pip freeze` omits pip itself; mirror that so the check is exact.
        current = {e for e in data["freeze"] if e.split("==", 1)[0] not in PIP_FREEZE_SKIPS}
        drift = sorted(locked ^ current)
        lines += [
            f"`backend/requirements.lock.txt`: {len(locked)} pins, sha256 `{sha256_of(lock)}`.",
            f"Lock vs live `.venv`: {'IN SYNC' if not drift else 'DRIFT (' + str(len(drift)) + ' entries)'}.",
        ]
        if drift:
            lines += [""] + [f"- `{d}`" for d in drift[:40]]
    else:
        lines += ["`backend/requirements.lock.txt` does not exist yet."]
    return lines + [""]


def section_node() -> list[str]:
    lines = ["## 5. Node toolchain", ""]
    _, node_v = run(["node", "--version"])
    _, npm_v = run(["npm", "--version"])
    lock = REPO / "package-lock.json"
    lines += md_table(
        ["Item", "Value"],
        [
            ["node", f"`{node_v}`"],
            ["npm", f"`{npm_v}`"],
            ["package-lock.json sha256", f"`{sha256_of(lock)}`" if lock.exists() else "MISSING"],
        ],
    )
    pkg = json.loads((REPO / "package.json").read_text(encoding="utf-8"))
    rows = []
    for group in ("dependencies", "devDependencies"):
        for name, spec in sorted(pkg.get(group, {}).items()):
            meta = REPO / "node_modules" / name / "package.json"
            version = "NOT INSTALLED"
            if meta.exists():
                version = json.loads(meta.read_text(encoding="utf-8")).get("version", "?")
            rows.append([f"`{name}`", group, f"`{spec}`", f"`{version}`"])
    lines += ["", "Declared (`package.json`) vs installed (`node_modules`):", ""]
    lines += md_table(["Package", "Group", "Declared", "Installed"], rows)
    return lines + [""]


def section_databases() -> list[str]:
    found: list[str] = []
    for dirpath, dirnames, filenames in os.walk(REPO):
        dirnames[:] = [d for d in dirnames if d not in PRUNE_DIRS]
        for name in filenames:
            if Path(name).suffix.lower() in DB_SUFFIXES:
                found.append(rel(Path(dirpath) / name))
    lines = ["## 6. Development database", ""]
    if found:
        lines += ["SQLite files present (back them up before any migration):", ""]
        lines += [f"- `{f}`" for f in sorted(found)]
    else:
        lines += [
            f"No `{'` / `'.join(sorted(DB_SUFFIXES))}` file exists anywhere in the working tree "
            "(`.git`, `node_modules`, `.venv`, `dist` excluded). There is no development "
            "database to back up; later schema migrations must be exercised on a throw-away copy.",
        ]
    return lines + [""]


def section_dep_files() -> list[str]:
    names = [
        "backend/requirements.txt",
        "backend/requirements-inference.txt",
        "backend/requirements.lock.txt",
        "package.json",
        "package-lock.json",
        "eslint.config.js",
        "tsconfig.json",
        "vite.config.ts",
        "vitest.config.ts",
    ]
    rows = []
    for name in names:
        path = REPO / name
        rows.append(
            [f"`{name}`", f"`{sha256_of(path)}`" if path.exists() else "MISSING", str(path.stat().st_size) if path.exists() else "-"]
        )
    lines = ["## 7. Dependency / config files", ""]
    lines += md_table(["File", "SHA-256", "Bytes"], rows)
    return lines + [""]


def main() -> int:
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    out: list[str] = [
        "# FYP2 freeze manifest",
        "",
        f"Generated (UTC): `{stamp}`  ",
        f"Generator: `scripts/freeze_manifest.py` (python `{sys.version.split()[0]}`)  ",
        f"Repository root: `{REPO}`",
        "",
    ]
    out += section_git()
    models, models_ok = section_models()
    out += models
    out += section_splits()
    out += section_python()
    out += section_node()
    out += section_databases()
    out += section_dep_files()
    sys.stdout.write("\n".join(out).rstrip() + "\n")
    return 0 if models_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
