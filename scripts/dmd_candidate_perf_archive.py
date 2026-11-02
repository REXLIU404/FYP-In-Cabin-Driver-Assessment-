#!/usr/bin/env python3
"""Audit the six DMD-candidate perf01 runs from their raw per-window timings.

Independent of perf01's analysis code: the quantile rule is restated here exactly
(``p95 = sorted[min(n - 1, round(0.95 * (n - 1)))]``, ``statistics.median``), the raw
file's sha256 must equal ``perf01.json``'s ``raw_timings.sha256``, and the recomputed
capture->render summary must equal the recorded one.

Usage:
    python3 scripts/dmd_candidate_perf_archive.py --root docs/evidence/<date>/dmd-candidate/d-perf

Exit 0 when every run is hash-bound and reproduces its summary; 1 otherwise.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DEFAULT_ROOT = REPO / "docs" / "evidence" / "2026-11-02" / "dmd-candidate" / "d-perf"


def quantiles(values: list[float]) -> dict:
    ordered = sorted(values)
    p95 = ordered[min(len(ordered) - 1, int(round(0.95 * (len(ordered) - 1))))]
    return {"n": len(ordered), "min": round(ordered[0], 3), "median": round(statistics.median(ordered), 3),
            "p95": round(p95, 3), "max": round(ordered[-1], 3)}


def verify_run(directory: Path) -> dict:
    directory = Path(directory)
    perf = json.loads((directory / "perf01.json").read_text())
    raw_path = directory / perf["raw_timings"]["file"]
    raw = raw_path.read_bytes()
    rows = json.loads(raw)
    sha_ok = hashlib.sha256(raw).hexdigest() == perf["raw_timings"]["sha256"]
    recomputed = quantiles([row["renderedAtMs"] - row["capturedAtMs"] for row in rows])
    summary = perf["stages"]["capture_to_render_ms"]
    summary_matches = recomputed == summary
    return {
        "run": directory.name,
        "model_id": (perf.get("vision_model") or {}).get("model_id"),
        "active_vision": perf.get("active_vision"),
        "machine": perf.get("machine"),
        "windows_measured": perf.get("windows_measured"),
        "achieved_rate_hz": perf.get("achieved_rate_hz"),
        "raw_file": str(raw_path),
        "raw_rows": len(rows),
        "sha256_ok": sha_ok,
        "summary_matches": summary_matches,
        "summary": summary,
        "recomputed": recomputed,
        "server_timing_ms": perf["stages"].get("server_timing_ms"),
        "short_run": perf.get("short_run"),
        "console_errors": perf.get("console_errors"),
        "attempts_other_than_1": perf.get("attempts_other_than_1"),
        "ok": bool(sha_ok and summary_matches),
        "quality_ok": bool(perf.get("short_run") is False
                            and not (perf.get("console_errors") or [])
                            and perf.get("attempts_other_than_1") == 0),
    }


def verify_archive(root: Path) -> dict:
    root = Path(root)
    runs = [verify_run(d) for d in sorted(root.iterdir())
            if d.is_dir() and (d / "perf01.json").is_file()]
    return {"root": str(root), "runs": runs,
            "all_ok": bool(runs) and all(run["ok"] for run in runs),
            "all_quality_ok": bool(runs) and all(run["quality_ok"] for run in runs),
            "run_count": len(runs)}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)
    result = verify_archive(args.root)
    out = args.out or (args.root / "recompute.json")
    out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    for run in result["runs"]:
        c2r = run["recomputed"]
        server = (run["server_timing_ms"] or {}).get("vision") or {}
        print(f"{run['run']:<52} {run['model_id']:<40} rows {run['raw_rows']:>4}  "
              f"c2r p50 {c2r['median']:>7} p95 {c2r['p95']:>7}  "
              f"server vision median {server.get('median')} p95 {server.get('p95')}  "
              f"sha {run['sha256_ok']} recompute {run['summary_matches']}")
    print(f"{result['run_count']} run(s): integrity {'OK' if result['all_ok'] else 'MISMATCH'}, "
          f"quality {'OK' if result['all_quality_ok'] else 'CHECK'}")
    return 0 if result["all_ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
