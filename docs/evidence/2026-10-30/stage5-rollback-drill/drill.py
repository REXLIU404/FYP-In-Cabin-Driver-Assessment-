"""Task 10A Stage 5 Step 1: the rollback drill (plan section 8).

With the candidates installed, start the backend with the ResNet18 candidate active, then roll back by
starting a FRESH process with DRA_ACTIVE_VISION unset. Each start uses the README's own command
(``python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8001``) from the repository
root, port 8001, and a throw-away SQLite database (never port 8000, never backend/driver_risk.db*).

Asserted for each start, from GET /api/models: models_loaded is true (the provider computes the
artifact sha256 and runs a warm-up forward on load, and refuses to load otherwise), the vision model
id and sha256 are the expected ones, and the telemetry model is the stable XGBoost. Then one normal
forward through the API (the checklist's "hash check -> normal forward"): a Live session and one
/infer window with a deterministic JPEG and a telemetry row; the stored window must be assessed and
name the expected vision model and sha256 in its provenance. Asserted around the
drill: no file under ml/outputs changed (no stable artifact was overwritten), and port 8001 is free
again at the end. Exit 0 only if every assertion holds.

Run from the repository root: .venv/bin/python docs/evidence/2026-10-30/stage5-rollback-drill/drill.py <out dir>
"""
import hashlib
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import base64
import io
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
OUT = Path(sys.argv[1])
PORT = 8001
CANDIDATE = "resnet18_search004_seed42"
STABLE_SHA = "b3a42e8dd4553355b1fd7d9e7fe3d28e318decb894e76eb029489b7ff2e90bcf"
XGB_SHA = "9802cb06ca98f0c1befaf851fa7668cfec70e005cf8bb3884e49d7d45d7aec07"
MODEL_ROOT = REPO / "ml" / "outputs"
log_lines: list[str] = []


def log(line: str) -> None:
    stamped = f"{datetime.now(timezone.utc).isoformat(timespec='seconds')} {line}"
    log_lines.append(stamped)
    print(stamped, flush=True)


def tree_hashes(root: Path) -> dict[str, str]:
    """sha256 of every regular file under the model root (symlinks resolved), by relative path."""
    out = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            out[str(path.relative_to(root))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return out


def port_free(port: int) -> bool:
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


def candidate_sha() -> str:
    index = json.loads((MODEL_ROOT / "candidates" / "index.json").read_text())
    if CANDIDATE not in index:
        raise SystemExit(f"candidate {CANDIDATE} not found in candidates/index.json")
    package = MODEL_ROOT / "candidates" / index[CANDIDATE]["package"]
    manifest = json.loads((package / "runtime_manifest.json").read_text())
    return manifest["model"]["sha256"]


def post(path: str, body: dict) -> tuple[int, dict]:
    request = urllib.request.Request(f"http://127.0.0.1:{PORT}{path}", data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.status, json.loads(response.read())


def one_window(step: str) -> dict:
    """A normal forward through the API: a Live session and one window (deterministic image)."""
    from PIL import Image
    buffer = io.BytesIO()
    Image.new("RGB", (640, 480), (80, 130, 180)).save(buffer, format="JPEG")
    now = datetime.now(timezone.utc).isoformat()
    sid = f"drill-{step}"
    created, _ = post("/api/sessions", {"session_id": sid, "operation_mode": "LIVE_MODEL_RUNTIME"})
    status, window = post(f"/api/sessions/{sid}/infer", {
        "request_id": f"{step}-1", "image_base64": base64.b64encode(buffer.getvalue()).decode(),
        "captured_at": now, "telemetry_timestamp": now, "telemetry_source": "prepared_replay",
        "telemetry_features": {"speed_kmph": 52, "accel_x": .7, "accel_y": .2, "brake_pressure": 20,
                               "steering_angle": 7.5, "throttle": 40, "lane_deviation": .21,
                               "headway_distance": 18}})
    log(f"[{step}] forward: session {created}, /infer {status}; RiskScore={window.get('RiskScore')} "
        f"P_distraction={window.get('P_distraction')} vision_model_id={window['provenance'].get('vision_model_id')} "
        f"vision_model_sha256={window['provenance'].get('vision_model_sha256')}")
    return {"session_status": created, "infer_status": status, "window": window}


def start(step: str, active_vision: str | None) -> dict:
    assert port_free(PORT), f"port {PORT} is in use before {step}"
    work = Path(tempfile.mkdtemp(prefix=f"rollback-{step}-"))
    env = {k: v for k, v in os.environ.items() if not k.startswith("DRA_")}
    env["DRA_DATABASE_URL"] = f"sqlite:///{work / 'drill.db'}"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    if active_vision is not None:
        env["DRA_ACTIVE_VISION"] = active_vision
    command = [str(REPO / ".venv" / "bin" / "python"), "-m", "uvicorn", "app.main:app", "--app-dir", "backend",
               "--host", "127.0.0.1", "--port", str(PORT)]
    log(f"[{step}] start: DRA_ACTIVE_VISION={active_vision if active_vision is not None else '(unset)'} "
        f"db={env['DRA_DATABASE_URL']} cmd={' '.join(command[1:])}")
    server_log = (OUT / f"{step}.uvicorn.log").open("wb")
    process = subprocess.Popen(command, cwd=REPO, env=env, stdout=server_log, stderr=subprocess.STDOUT)
    try:
        deadline = time.monotonic() + 120
        models = None
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise AssertionError(f"[{step}] uvicorn exited early with {process.returncode}")
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/api/models", timeout=60) as response:
                    models = json.loads(response.read())
                break
            except OSError:
                time.sleep(0.5)
        assert models is not None, f"[{step}] /api/models did not answer within 120 s"
        with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/api/health", timeout=10) as response:
            health = response.status
        log(f"[{step}] /api/health {health}; models_loaded={models.get('models_loaded')} "
            f"provider={models.get('provider')} vision={models['vision'].get('model_id')} "
            f"sha256={models['vision'].get('sha256')} telemetry_sha256={models['telemetry'].get('sha256')}")
        forward = one_window(step)
        return {"step": step, "DRA_ACTIVE_VISION": active_vision, "health": health, "models": models,
                "forward": forward}
    finally:
        process.terminate()
        try:
            code = process.wait(timeout=30)
        except subprocess.TimeoutExpired:
            process.kill()
            code = process.wait()
        server_log.close()
        log(f"[{step}] stopped (exit {code}); port {PORT} free: {port_free(PORT)}")


def forward_ok(started: dict, model_id: str, sha: str) -> bool:
    f = started["forward"]
    w = f["window"]
    return (f["session_status"] == 201 and f["infer_status"] == 201 and w.get("RiskScore") is not None
            and 0.0 <= w.get("P_distraction", -1) <= 1.0 and len(w.get("visual_top_classes", [])) == 10
            and w["provenance"].get("vision_model_id") == model_id
            and w["provenance"].get("vision_model_sha256") == sha)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, text=True).stdout.strip()
    log(f"rollback drill at {head}; model root {MODEL_ROOT}")
    before = tree_hashes(MODEL_ROOT)
    expected_candidate = candidate_sha()
    disk_stable = hashlib.sha256((MODEL_ROOT / "vision" / "mobilenetv3_large_vision.onnx").read_bytes()).hexdigest()
    log(f"on disk: stable ONNX sha256 {disk_stable}; candidate manifest sha256 {expected_candidate}; "
        f"{len(before)} files under the model root")
    checks = []

    def check(name: str, ok: bool) -> None:
        checks.append({"check": name, "ok": bool(ok)})
        log(f"CHECK {'PASS' if ok else 'FAIL'}: {name}")

    check("stable ONNX on disk has the frozen sha256", disk_stable == STABLE_SHA)
    a = start("1-candidate-active", CANDIDATE)
    check("candidate start: models loaded (hash + warm-up forward)", a["models"].get("models_loaded") is True)
    check("candidate start: vision is the ResNet18 candidate",
          a["models"]["vision"].get("model_id") == CANDIDATE and a["models"]["vision"].get("sha256") == expected_candidate)
    check("candidate start: telemetry is the stable XGBoost", a["models"]["telemetry"].get("sha256") == XGB_SHA)
    check("candidate start: one normal forward, assessed, by the candidate", forward_ok(a, CANDIDATE, expected_candidate))
    b = start("2-rollback-stable", None)
    check("rollback start: models loaded (hash + warm-up forward)", b["models"].get("models_loaded") is True)
    check("rollback start: vision is the stable MobileNetV3 with the frozen sha256",
          b["models"]["vision"].get("model_id") == "stable_mobilenet_v3_large"
          and b["models"]["vision"].get("sha256") == STABLE_SHA)
    check("rollback start: telemetry is the stable XGBoost", b["models"]["telemetry"].get("sha256") == XGB_SHA)
    check("rollback start: one normal forward, assessed, by the stable model",
          forward_ok(b, "stable_mobilenet_v3_large", STABLE_SHA))
    after = tree_hashes(MODEL_ROOT)
    check("no file under the model root changed (nothing overwritten)", before == after)
    check(f"port {PORT} is free at the end", port_free(PORT))
    passed = all(c["ok"] for c in checks)
    log(f"RESULT: {'PASS' if passed else 'FAIL'} ({sum(c['ok'] for c in checks)}/{len(checks)} checks)")
    (OUT / "drill.json").write_text(json.dumps({"head": head, "port": PORT, "checks": checks, "passed": passed,
                                                "starts": [a, b]}, indent=2, sort_keys=True))
    (OUT / "drill.log").write_text("\n".join(log_lines) + "\n")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
