#!/usr/bin/env python3
"""Camera A/B check for the stable and DMD-candidate vision models (user-operated).

The agent never runs the camera. The user starts one backend, checks the model identity,
then runs this script; it prompts before each of three 60 s actions, captures one JPEG per
second with ffmpeg, sends every frame through the real ``POST /infer`` and saves the raw
per-frame answers. Each action uses a new session, so EMA and fusion state do not carry
across the transition between actions. A second run uses the other model. A compare mode
prints the two runs side by side.

    # terminal 1 (stable)
    .venv/bin/python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
    # terminal 2
    .venv/bin/python scripts/camera_ab_check.py --label stable --out .../f-camera-check/stable.json

    # restart the backend with DRA_ACTIVE_VISION=dmd_adapted_mobilenet_v3_20261029
    .venv/bin/python scripts/camera_ab_check.py --label dmd --out .../f-camera-check/dmd.json
    .venv/bin/python scripts/camera_ab_check.py --compare stable.json dmd.json --out comparison.json

Measures, per phase: top-1 class counts, the fraction whose top-1 is ``safe_driving``,
raw P_distraction mean/median and the fraction at or above 0.5. Raw means
``provenance.P_distraction_raw``, before the product's EMA smoothing; the smoothed mean is
stored beside it for reference. DESCRIPTIVE ONLY: one 60 s clip per action cannot establish
real-world accuracy or a safety benefit.

Camera capture needs ffmpeg with avfoundation (macOS). List devices with:
    ffmpeg -f avfoundation -list_devices true -i ""
Exit codes: 0 complete run, 1 partial/invalid run, 2 usage or backend/model error.
"""
from __future__ import annotations

import argparse
import base64
import json
import statistics
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib import error, request

REPO = Path(__file__).resolve().parent.parent
DEFAULT_OUT_DIR = REPO / "docs" / "evidence" / datetime.now().strftime("%Y-%m-%d") / "dmd-candidate" / "f-camera-check"
DEFAULT_BASE_URL = "http://127.0.0.1:8000"
STABLE_MODEL_ID = "stable_mobilenet_v3_large"
DMD_MODEL_ID = "dmd_adapted_mobilenet_v3_20261029"
EXPECTED = {"stable": STABLE_MODEL_ID, "dmd": DMD_MODEL_ID}


def phase_plan(seconds: int = 60) -> list[dict]:
    return [
        {"id": "normal", "seconds": seconds,
         "instruction": "正常坐姿，双手放在方向盘/桌面，目视前方，不拿手机、不喝水"},
        {"id": "phone", "seconds": seconds,
         "instruction": "拿起手机并低头看屏幕（保持动作），不要遮挡整张脸"},
        {"id": "drinking", "seconds": seconds,
         "instruction": "拿起杯子或水瓶，做出喝水的动作（保持动作）"},
    ]


def infer_payload(frame: bytes, *, request_id: str, captured_at: str, frame_index: int) -> dict:
    return {"request_id": request_id,
            "image_base64": base64.b64encode(frame).decode("ascii"),
            "captured_at": captured_at, "captured_at_source": "client_clock",
            "vision_frame": {"epoch": 1, "index": frame_index}}


def extract_jpegs(buffer: bytes) -> tuple[list[bytes], bytes]:
    """Split a byte stream into complete JPEGs; the trailing partial starts at its SOI."""
    frames, index = [], 0
    while True:
        start = buffer.find(b"\xff\xd8", index)
        if start < 0:
            return frames, b""
        end = buffer.find(b"\xff\xd9", start + 2)
        if end < 0:
            return frames, buffer[start:]
        frames.append(buffer[start:end + 2])
        index = end + 2


def compute_summary(frames: list[dict]) -> dict:
    valid = [f for f in frames if f.get("http_status") == 201 and f.get("top_class")]
    n = len(valid)
    counts = Counter(f["top_class"] for f in valid)
    distractions = [float(f["p_distraction_raw"]) for f in valid]
    smoothed = [float(f["p_distraction_smoothed"]) for f in valid]
    identities = {(f.get("vision_model_id"), f.get("vision_model_sha256")) for f in valid}
    identity = ({"vision_model_id": next(iter(identities))[0], "vision_model_sha256": next(iter(identities))[1]}
                if len(identities) == 1 else
                {"vision_model_id": sorted({i[0] for i in identities}),
                 "vision_model_sha256": sorted({i[1] for i in identities})})
    return {
        "n": n,
        "valid_n": n,
        "http_status_counts": dict(Counter(f.get("http_status") for f in frames)),
        "top1_counts": dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))),
        "safe_driving_top1_rate": round(counts.get("safe_driving", 0) / n, 4) if n else None,
        "p_distraction_mean": round(sum(distractions) / n, 4) if n else None,
        "p_distraction_median": round(statistics.median(distractions), 4) if n else None,
        "p_distraction_ge_0_5_rate": round(sum(p >= 0.5 for p in distractions) / n, 4) if n else None,
        "p_distraction_basis": "provenance.P_distraction_raw",
        "p_distraction_smoothed_mean": round(sum(smoothed) / n, 4) if n else None,
        "model_identity": identity,
    }


def compare_results(results: list[dict]) -> dict:
    plan = phase_plan()
    phases = []
    for phase in plan:
        row = {"id": phase["id"], "instruction": phase["instruction"], "models": {}}
        for result in results:
            summary = next((p["summary"] for p in result.get("phases", []) if p["id"] == phase["id"]), None)
            row["models"][result["label"]] = summary
        phases.append(row)
    return {"decision_rule": "DESCRIPTIVE_ONLY",
            "not_a_claim": "one 60 s clip per action cannot establish real-world accuracy or safety benefit",
            "models": {r["label"]: r.get("model_identity") for r in results},
            "phases": phases}


class BackendClient:
    def __init__(self, base_url: str, timeout: float = 30):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _call(self, method: str, path: str, payload: dict | None = None) -> tuple[int, dict]:
        data = None if payload is None else json.dumps(payload).encode()
        req = request.Request(self.base_url + path, data=data, method=method,
                              headers={"content-type": "application/json"} if data else {})
        try:
            with request.urlopen(req, timeout=self.timeout) as response:
                return response.status, json.loads(response.read() or b"{}")
        except error.HTTPError as exc:
            body = exc.read().decode(errors="replace")
            raise RuntimeError(f"{method} {path} -> HTTP {exc.code}: {body[:500]}") from None
        except error.URLError as exc:
            raise RuntimeError(f"backend unreachable at {self.base_url}: {exc.reason}") from None

    def models(self) -> dict:
        status, body = self._call("GET", "/api/models")
        if status != 200:
            raise RuntimeError(f"GET /api/models -> HTTP {status}")
        return body

    def create_session(self, session_id: str) -> dict:
        status, body = self._call("POST", "/api/sessions", {
            "session_id": session_id, "operation_mode": "LIVE_MODEL_RUNTIME",
            "description": "camera A/B check (constructed user clip, descriptive only)"})
        if status != 201:
            raise RuntimeError(f"POST /api/sessions -> HTTP {status}: {body}")
        return body

    def infer(self, session_id: str, frame: bytes, request_id: str, captured_at: str,
              frame_index: int, *, model_label: str) -> dict:
        status, body = self._call("POST", f"/api/sessions/{session_id}/infer",
                                  infer_payload(frame, request_id=request_id,
                                                captured_at=captured_at, frame_index=frame_index))
        if status != 201:
            raise RuntimeError(f"POST /infer -> HTTP {status}: {body}")
        classes = body.get("visual_top_classes") or []
        top = max(classes, key=lambda item: item["probability"]) if classes else None
        provenance = body.get("provenance") or {}
        model_id = provenance.get("vision_model_id")
        expected = EXPECTED.get(model_label)
        if expected and model_id != expected:
            raise RuntimeError(f"backend loaded {model_id!r}, expected {expected!r} for label {model_label!r}")
        return {"http_status": status, "request_id": request_id, "captured_at": captured_at,
                "top_class": top["label"] if top else None,
                "top_probability": top["probability"] if top else None,
                "p_distraction_raw": provenance.get("P_distraction_raw"),
                "p_distraction_smoothed": body.get("P_distraction"),
                "visual_top_classes": classes,
                "vision_model_id": model_id,
                "vision_model_sha256": provenance.get("vision_model_sha256")}


def ffmpeg_frames(device: str, fps: int, seconds: int):
    """Yield JPEG frames from ffmpeg's avfoundation camera; one frame per 1/fps second."""
    command = ["ffmpeg", "-hide_banner", "-loglevel", "error",
               "-f", "avfoundation", "-framerate", "30", "-i", str(device),
               "-r", str(fps), "-t", str(seconds),
               "-pix_fmt", "yuvj420p", "-q:v", "3",
               "-f", "image2pipe", "-vcodec", "mjpeg", "-"]
    try:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except FileNotFoundError:
        raise RuntimeError("ffmpeg not found; install it (brew install ffmpeg) or fix PATH") from None
    buffer, produced = b"", 0
    try:
        while produced < seconds * fps:
            chunk = process.stdout.read(4096)
            if not chunk:
                break
            buffer += chunk
            frames, buffer = extract_jpegs(buffer)
            for frame in frames:
                produced += 1
                yield frame
                if produced >= seconds * fps:
                    break
        if produced < seconds * fps:
            stderr = (process.stderr.read() or b"").decode(errors="replace")[-800:]
            raise RuntimeError(f"camera produced {produced} frames, expected {seconds * fps}; ffmpeg: {stderr}")
    finally:
        if process.poll() is None:
            process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()


def _write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def run_capture(args) -> int:
    out = Path(args.out)
    client = BackendClient(args.base_url)
    models = client.models()
    vision = models.get("vision") or {}
    expected = EXPECTED.get(args.label)
    if expected and vision.get("model_id") != expected:
        print(f"ERROR: backend reports {vision.get('model_id')!r}; label {args.label!r} expects {expected!r}.",
              file=sys.stderr)
        print("Start the backend with the matching DRA_ACTIVE_VISION and try again.", file=sys.stderr)
        return 2
    result = {"schema": "camera_ab_check/1", "label": args.label, "base_url": args.base_url,
              "session_ids": {}, "started_utc": datetime.now(timezone.utc).isoformat(),
              "camera": {"device": args.device, "fps": args.fps, "seconds_per_phase": args.seconds},
              "backend_vision": vision, "phases": [], "status": "IN_PROGRESS"}
    print(f"Backend: {vision.get('model_id')} sha256 {vision.get('sha256')}")
    print("A single 60 s clip per action is descriptive; it cannot establish real-world accuracy or safety.")
    frame_index = 0
    try:
        for phase in phase_plan(args.seconds):
            print(f"\n=== {phase['id']}: {phase['instruction']} ({phase['seconds']} s) ===")
            input("Press Enter when ready, then perform the action continuously... ")
            session_id = f"cam-{args.label}-{phase['id']}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
            client.create_session(session_id)
            result["session_ids"][phase["id"]] = session_id
            started = datetime.now(timezone.utc)
            frames = []
            for frame in ffmpeg_frames(args.device, args.fps, args.seconds):
                frame_index += 1
                captured_at = datetime.now(timezone.utc).isoformat()
                request_id = f"cam_{args.label}_{phase['id']}_{frame_index:05d}"
                record = client.infer(session_id, frame, request_id, captured_at, frame_index,
                                      model_label=args.label)
                record["phase"] = phase["id"]
                frames.append(record)
                if len(frames) % 10 == 0:
                    print(f"  {len(frames)}/{phase['seconds']} frames; last top-1 {record['top_class']} "
                          f"raw P_distraction {record['p_distraction_raw']:.3f}")
            summary = compute_summary(frames)
            result["phases"].append({"id": phase["id"], "instruction": phase["instruction"],
                                     "started_utc": started.isoformat(),
                                     "ended_utc": datetime.now(timezone.utc).isoformat(),
                                     "frames": frames, "summary": summary})
            _write(out, result)
            print(f"  {phase['id']}: n={summary['n']} top1={summary['top1_counts']} "
                  f"safe_top1={summary['safe_driving_top1_rate']} "
                  f"raw P_distraction median={summary['p_distraction_median']} "
                  f">=0.5={summary['p_distraction_ge_0_5_rate']}")
        result["status"] = "COMPLETE" if all(p["summary"]["n"] == args.seconds for p in result["phases"]) else "PARTIAL"
    except KeyboardInterrupt:
        result["status"] = "INTERRUPTED"
        print("\nInterrupted; partial results saved.", file=sys.stderr)
    except Exception as exc:
        result["status"] = "ERROR"
        result["error"] = f"{type(exc).__name__}: {exc}"
        print(f"ERROR: {exc}", file=sys.stderr)
    finally:
        result["finished_utc"] = datetime.now(timezone.utc).isoformat()
        _write(out, result)
        print(f"\nSaved {out} (status {result['status']})")
    return 0 if result["status"] == "COMPLETE" else 1


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--label", choices=sorted(EXPECTED), help="which model this run records")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--out", type=Path, default=None,
                        help=f"result JSON (default: {DEFAULT_OUT_DIR}/<label>.json)")
    parser.add_argument("--device", default="0", help="avfoundation video device (default 0)")
    parser.add_argument("--fps", type=int, default=1)
    parser.add_argument("--seconds", type=int, default=60)
    parser.add_argument("--compare", nargs=2, type=Path, metavar=("A", "B"),
                        help="compare two result JSONs instead of capturing")
    args = parser.parse_args(argv)
    if args.compare:
        results = [json.loads(path.read_text()) for path in args.compare]
        comparison = compare_results(results)
        out = args.out or (args.compare[0].parent / "comparison.json")
        _write(Path(out), comparison)
        print(json.dumps(comparison, indent=2, ensure_ascii=False))
        return 0
    if not args.label:
        parser.error("--label is required unless --compare is used")
    if args.out is None:
        args.out = DEFAULT_OUT_DIR / f"{args.label}.json"
    return run_capture(args)


if __name__ == "__main__":
    sys.exit(main())
