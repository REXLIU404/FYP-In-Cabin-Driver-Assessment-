"""DMD candidate evidence, item F: the camera A/B check helper.

The camera itself is never opened here. These tests pin the pure parts the user relies on:
the three-phase plan, the per-frame payload, MJPEG splitting, the summary arithmetic and the
side-by-side comparison. A local stub HTTP server checks the client's URLs and payloads.
"""
import base64
import importlib.util
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "scripts"


def load_runner():
    path = SCRIPTS / "camera_ab_check.py"
    assert path.is_file(), f"missing runner {path}"
    spec = importlib.util.spec_from_file_location("_camera_ab_check", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_the_plan_has_the_three_declared_actions_of_60_seconds():
    runner = load_runner()
    plan = runner.phase_plan(60)
    assert [p["id"] for p in plan] == ["normal", "phone", "drinking"]
    assert [p["seconds"] for p in plan] == [60, 60, 60]
    assert all(p["instruction"] for p in plan)


def test_the_payload_is_vision_only_and_keeps_frame_identity():
    runner = load_runner()
    frame = b"\xff\xd8abc\xff\xd9"
    payload = runner.infer_payload(frame, request_id="cam_stable_normal_0001",
                                   captured_at="2026-11-02T10:00:00+00:00", frame_index=7)
    assert payload["request_id"] == "cam_stable_normal_0001"
    assert payload["image_base64"] == base64.b64encode(frame).decode("ascii")
    assert payload["captured_at"] == "2026-11-02T10:00:00+00:00"
    assert payload["captured_at_source"] == "client_clock"
    assert payload["vision_frame"] == {"epoch": 1, "index": 7}
    assert "telemetry_features" not in payload and "telemetry_timestamp" not in payload


def test_mjpeg_splitter_returns_complete_frames_and_keeps_a_partial_tail():
    runner = load_runner()
    first, second = b"\xff\xd8ONE\xff\xd9", b"\xff\xd8TWO\xff\xd9"
    frames, rest = runner.extract_jpegs(b"noise" + first + b"gap" + second + b"\xff\xd8PARTIAL")
    assert frames == [first, second]
    assert rest == b"\xff\xd8PARTIAL"


def test_phase_summary_counts_safe_top1_and_raw_distraction_rate():
    runner = load_runner()
    frames = [
        {"top_class": "safe_driving", "p_distraction_raw": 0.1, "p_distraction_smoothed": 0.7,
         "vision_model_id": "m", "vision_model_sha256": "h", "http_status": 201},
        {"top_class": "safe_driving", "p_distraction_raw": 0.2, "p_distraction_smoothed": 0.8,
         "vision_model_id": "m", "vision_model_sha256": "h", "http_status": 201},
        {"top_class": "talking_phone_right", "p_distraction_raw": 0.8, "p_distraction_smoothed": 0.9,
         "vision_model_id": "m", "vision_model_sha256": "h", "http_status": 201},
    ]
    summary = runner.compute_summary(frames)
    assert summary["n"] == 3
    assert summary["top1_counts"] == {"safe_driving": 2, "talking_phone_right": 1}
    assert summary["safe_driving_top1_rate"] == 0.6667
    assert summary["p_distraction_mean"] == 0.3667
    assert summary["p_distraction_median"] == 0.2
    assert summary["p_distraction_ge_0_5_rate"] == 0.3333
    assert summary["p_distraction_smoothed_mean"] == 0.8
    assert summary["p_distraction_basis"] == "provenance.P_distraction_raw"
    assert summary["model_identity"] == {"vision_model_id": "m", "vision_model_sha256": "h"}


def test_each_action_phase_runs_in_a_fresh_session(monkeypatch, tmp_path):
    runner = load_runner()
    created = []

    class FakeClient:
        def __init__(self, base_url, timeout=30):
            self.base_url = base_url

        def models(self):
            return {"vision": {"model_id": runner.STABLE_MODEL_ID, "sha256": "abc"}}

        def create_session(self, session_id):
            created.append(session_id)
            return {"id": session_id}

        def infer(self, session_id, frame, request_id, captured_at, frame_index, *, model_label):
            return {"top_class": "safe_driving", "top_probability": 0.9,
                    "p_distraction_raw": 0.1, "p_distraction_smoothed": 0.7,
                    "vision_model_id": runner.STABLE_MODEL_ID, "vision_model_sha256": "abc",
                    "http_status": 201}

    monkeypatch.setattr(runner, "BackendClient", FakeClient)
    monkeypatch.setattr(runner, "ffmpeg_frames", lambda device, fps, seconds: iter([b"\xff\xd8x\xff\xd9"]))
    monkeypatch.setattr("builtins.input", lambda *_: "")
    args = SimpleNamespace(out=tmp_path / "stable.json", base_url="http://stub", label="stable",
                           device="0", fps=1, seconds=1)
    assert runner.run_capture(args) == 0
    assert len(created) == len(set(created)) == 3
    result = json.loads(Path(args.out).read_text())
    assert [phase["summary"]["p_distraction_mean"] for phase in result["phases"]] == [0.1, 0.1, 0.1]
    assert result["session_ids"] == dict(zip(("normal", "phone", "drinking"), created))


def test_comparison_is_side_by_side_and_chooses_nothing():
    runner = load_runner()
    stable = {"label": "stable", "model_identity": {"vision_model_id": "stable"},
              "phases": [{"id": "normal", "summary": {"n": 60, "safe_driving_top1_rate": 0.5,
                                                     "p_distraction_median": 0.4, "p_distraction_ge_0_5_rate": 0.5}}]}
    dmd = {"label": "dmd", "model_identity": {"vision_model_id": "dmd"},
           "phases": [{"id": "normal", "summary": {"n": 60, "safe_driving_top1_rate": 0.9,
                                                  "p_distraction_median": 0.1, "p_distraction_ge_0_5_rate": 0.1}}]}
    comparison = runner.compare_results([stable, dmd])
    assert comparison["decision_rule"] == "DESCRIPTIVE_ONLY"
    row = comparison["phases"][0]
    assert row["id"] == "normal"
    assert row["models"]["stable"]["safe_driving_top1_rate"] == 0.5
    assert row["models"]["dmd"]["safe_driving_top1_rate"] == 0.9
    assert "winner" not in json.dumps(comparison).lower()


class _Stub(BaseHTTPRequestHandler):
    calls = []

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("content-length", 0))
        body = json.loads(self.rfile.read(length) or b"{}")
        self.calls.append((self.path, body))
        if self.path == "/api/sessions":
            self._json(201, {"id": body.get("session_id"), "total_windows": 0})
        elif self.path.endswith("/infer"):
            self._json(201, {"window_id": 1, "visual_top_classes": [
                {"label": "safe_driving", "probability": 0.9}, {"label": "texting_right", "probability": 0.05}],
                "P_distraction": 0.1,
                "provenance": {"vision_model_id": "stub_model", "vision_model_sha256": "abc",
                               "P_distraction_raw": 0.2}})
        else:
            self._json(404, {"detail": "no"})

    def _json(self, status, payload):
        data = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


def test_client_posts_the_session_then_one_vision_window():
    runner = load_runner()
    _Stub.calls = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Stub)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        client = runner.BackendClient(f"http://127.0.0.1:{server.server_port}", timeout=10)
        client.create_session("cam-stub-normal")
        result = client.infer("cam-stub-normal", b"\xff\xd8x\xff\xd9", "req_1",
                              "2026-11-02T10:00:00+00:00", 1, model_label="stub")
    finally:
        server.shutdown()
        thread.join(timeout=5)
    assert result["top_class"] == "safe_driving"
    assert result["p_distraction_raw"] == 0.2
    assert result["p_distraction_smoothed"] == 0.1
    assert _Stub.calls[0][0] == "/api/sessions"
    assert _Stub.calls[0][1]["operation_mode"] == "LIVE_MODEL_RUNTIME"
    assert _Stub.calls[1][0] == "/api/sessions/cam-stub-normal/infer"
    assert _Stub.calls[1][1]["vision_frame"] == {"epoch": 1, "index": 1}
    assert "telemetry_features" not in _Stub.calls[1][1]
