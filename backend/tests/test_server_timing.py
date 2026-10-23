"""Task 10 / R4 (PERF-01 groundwork): ``POST /infer`` reports its stages in a
``Server-Timing`` header.

``latency_ms`` in the stored record stops before ``db.commit()`` (it is in the record
that the commit makes durable, so it cannot include the commit). The header is where the
commit stage, and the whole-handler total, can be reported. This file pins the header's
shape, which stage each segment covers, and that ``latency_ms`` kept its meaning.

None of it needs model weights: ``live`` (from test_fault_events) is a REAL
``TrainedProvider`` over hand-written fake onnx / xgboost objects, so the segment names
are checked against what the real provider reports. Every expected number is a literal.
"""
import re
import time

import pytest

from test_fault_events import infer, live, make_payload  # noqa: F401  (live is a fixture)

SEGMENT_ORDER = ["preprocess", "vision", "telemetry", "fusion", "commit", "total"]


def parse(header):
    """{name: (dur_ms, desc or None)} from a Server-Timing value, in header order."""
    parsed = {}
    for item in header.split(", "):
        name, *params = item.split(";")
        fields = dict(param.split("=", 1) for param in params)
        parsed[name] = (float(fields["dur"]), fields.get("desc"))
    return parsed


def timing_of(response):
    assert response.status_code == 201, response.text
    return parse(response.headers["Server-Timing"])


class StubProvider:
    """Reports provider timings that are exactly known, so they can be asserted exactly."""

    def __init__(self, timing_ms, sleep_s=0.0):
        self.timing_ms = timing_ms
        self.sleep_s = sleep_s  # real model time, which latency_ms must contain

    def infer(self, data):
        from app.schemas import WindowInput
        time.sleep(self.sleep_s)
        window = WindowInput(P_distraction=0.5, P_telemetry_anomaly=0.5,
                             vision_status="fresh", telemetry_status="fresh")
        provenance = {"provider": "Stub", "request_id": data.request_id,
                      "vision_source": "camera_frame", "telemetry_source": "prepared_replay",
                      "captured_at": data.captured_at, "telemetry_timestamp": data.telemetry_timestamp,
                      "timing_ms": dict(self.timing_ms)}
        return window, provenance


# ------------------------------------------------------------------- pure formatting
def test_the_header_is_written_in_canonical_order_with_two_decimals():
    from app.timing import format_server_timing
    assert (format_server_timing({"total": 12.346, "preprocess": 1, "commit": 0.004})
            == "preprocess;dur=1.00, commit;dur=0.00, total;dur=12.35")


def test_a_skipped_segment_says_so_and_a_negative_duration_is_clamped():
    from app.timing import format_server_timing
    assert format_server_timing({"vision": 0.0, "fusion": -0.5}, skipped=["vision"]) == \
        'vision;dur=0.00;desc="skipped", fusion;dur=0.00'


def test_an_unknown_segment_name_is_a_programming_error():
    from app.timing import format_server_timing
    with pytest.raises(ValueError, match="unknown Server-Timing segment"):
        format_server_timing({"network": 1.0})


def test_provider_timings_map_to_segments_and_a_missing_branch_is_marked_skipped():
    from app.timing import SegmentTimer
    timer = SegmentTimer()
    timer.add_provider_timings({"preprocess_ms": 2.5, "vision_ms": 4.0})
    assert timer.header() == 'preprocess;dur=2.50, vision;dur=4.00, telemetry;dur=0.00;desc="skipped"'


def test_outside_a_request_measure_does_nothing():
    from app import timing
    with timing.measure("commit"):
        pass
    assert timing._active.get() is None


# ------------------------------------------------------------------------ the route
def test_a_full_request_reports_all_six_segments_in_order(live):
    sent = timing_of(infer(live, make_payload("t-full")))
    assert list(sent) == SEGMENT_ORDER
    for name in ("preprocess", "vision", "telemetry"):
        assert sent[name][1] is None, name  # both branches ran: nothing is marked skipped
    assert all(dur >= 0.0 for dur, _ in sent.values())
    assert sent["total"][0] >= sent["fusion"][0] + sent["commit"][0]


def test_the_provider_stage_times_are_passed_through_exactly(live, monkeypatch):
    from app.providers import trained
    monkeypatch.setattr(trained, "_provider",
                        StubProvider({"preprocess_ms": 3.5, "vision_ms": 7.25, "telemetry_ms": 1.5}))
    response = infer(live, make_payload("t-stub"))
    assert response.status_code == 201, response.text
    assert response.headers["Server-Timing"].startswith(
        "preprocess;dur=3.50, vision;dur=7.25, telemetry;dur=1.50, fusion;dur=")


@pytest.mark.parametrize("kwargs,skipped,ran", [
    ({"image": False}, {"preprocess", "vision"}, {"telemetry"}),
    ({"telemetry": False}, {"telemetry"}, {"preprocess", "vision"}),
    ({"image": False, "telemetry": False}, {"preprocess", "vision", "telemetry"}, set()),
])
def test_a_branch_that_did_not_run_is_reported_as_skipped_not_left_out(live, kwargs, skipped, ran):
    sent = timing_of(infer(live, make_payload("t-skip", **kwargs)))
    assert list(sent) == SEGMENT_ORDER
    for name in skipped:
        assert sent[name] == (0.0, '"skipped"'), name
    for name in ran:
        assert sent[name][1] is None, name


def test_the_commit_segment_is_timed_after_db_commit_and_latency_ms_still_ends_before_it(live, monkeypatch):
    """The model stage really takes 80 ms and the real Session.commit is delayed to 150 ms.
    The commit segment must show the 150 and the fusion segment must not; ``total`` must
    contain both; ``latency_ms`` (computed before the commit) must contain the model time
    and must NOT contain the commit."""
    from sqlalchemy.orm import Session
    from app.providers import trained
    monkeypatch.setattr(trained, "_provider", StubProvider({"vision_ms": 80.0}, sleep_s=0.08))
    real_commit = Session.commit

    def slow_commit(self):
        time.sleep(0.15)
        return real_commit(self)

    monkeypatch.setattr(Session, "commit", slow_commit)
    response = infer(live, make_payload("t-commit"))
    sent = timing_of(response)
    assert sent["commit"][0] >= 150.0
    assert sent["fusion"][0] < 80.0
    assert sent["total"][0] >= 230.0  # 80 ms of model + 150 ms of commit
    stored = response.json()["latency_ms"]
    assert 80 <= stored < 150, stored  # holds the model time, stops before db.commit()
    assert stored <= sent["total"][0] + 1  # and is part of the same request


def test_a_resend_answered_from_the_stored_record_reports_total_only(live):
    body = make_payload("t-resend")
    assert infer(live, body).status_code == 201
    again = infer(live, body, attempt=2)
    assert again.status_code == 201
    assert re.fullmatch(r"total;dur=\d+\.\d\d", again.headers["Server-Timing"]), again.headers["Server-Timing"]


def test_failures_and_the_replay_route_carry_no_server_timing(live):
    assert live.client.post("/api/sessions", json={"session_id": "replay-one"}).status_code == 201
    conflict = live.client.post("/api/sessions/replay-one/infer", json=make_payload("t-409"))
    assert conflict.status_code == 409
    assert "Server-Timing" not in conflict.headers

    invalid = infer(live, {"request_id": "t-422", "image_base64": "!!!", "captured_at": "2026-01-01T00:00:00+00:00"})
    assert invalid.status_code == 422
    assert "Server-Timing" not in invalid.headers

    window = live.client.post("/api/sessions/replay-one/windows",
                              json={"P_distraction": 0.2, "P_telemetry_anomaly": 0.2})
    assert window.status_code == 201
    assert "Server-Timing" not in window.headers
