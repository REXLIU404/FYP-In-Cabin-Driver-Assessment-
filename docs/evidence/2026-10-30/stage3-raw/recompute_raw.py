"""Recompute every perf01 run's capture->render statistics from its raw timings file (R-1 check).
Independent of the repository code: the quantile rule is restated here. Run: python3 recompute_raw.py <stage3-raw dir>"""
import hashlib, json, statistics, sys
from pathlib import Path

def summ(values):
    o = sorted(values)
    p95 = o[min(len(o) - 1, int(round(0.95 * (len(o) - 1))))]
    return {"n": len(o), "min": round(o[0], 3), "median": round(statistics.median(o), 3), "p95": round(p95, 3), "max": round(o[-1], 3)}

ok = True
for d in sorted(Path(sys.argv[1]).glob("*-r*")):
    r = json.loads((d / "perf01.json").read_text())
    raw = (d / r["raw_timings"]["file"]).read_bytes()
    rows = json.loads(raw)
    sha_ok = hashlib.sha256(raw).hexdigest() == r["raw_timings"]["sha256"]
    same = summ([x["renderedAtMs"] - x["capturedAtMs"] for x in rows]) == r["stages"]["capture_to_render_ms"]
    ok &= sha_ok and same
    print(d.name, r["vision_model"]["model_id"], "rows", len(rows), "sha_ok", sha_ok, "recompute==summary", same,
          r["stages"]["capture_to_render_ms"])
print("ALL OK" if ok else "MISMATCH")
sys.exit(0 if ok else 1)
