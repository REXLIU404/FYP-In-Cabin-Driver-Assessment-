#!/usr/bin/env python3
"""Check a Task 10A runtime manifest (and, with --package-dir, its model file).

    python3 scripts/validate_runtime_manifest.py ml/outputs/runs/<run_id>/runtime_manifest.json \
        --package-dir ml/outputs/runs/<run_id>

Exit 0 and "valid" when it passes; exit 1 and one line per problem otherwise. Needs jsonschema
(in backend/requirements.lock.txt). Loads no model and runs nothing.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.runtime_manifest import validate_manifest, validate_package  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate a Task 10A runtime manifest.")
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--package-dir", type=Path, help="also check the model file inside this package")
    args = parser.parse_args(argv)
    try:
        manifest = json.loads(args.manifest.read_text())
    except ValueError as exc:
        print(f"{args.manifest}: not valid JSON ({exc})")
        print("1 problem(s)")
        return 1
    errors = validate_package(manifest, args.package_dir) if args.package_dir else validate_manifest(manifest)
    for error in errors:
        print(error)
    print("valid" if not errors else f"{len(errors)} problem(s)")
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
