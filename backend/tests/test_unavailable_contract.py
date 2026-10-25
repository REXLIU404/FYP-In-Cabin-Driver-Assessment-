"""Task 4: the backend carries the nullable, availability-aware RiskUpdate contract
end to end - schema, persistence, legacy-row reads, status, cache and export.

Contract under test (mirrors ai/src/types.ts):

    assessment_available == (RiskScore is not None) == (SystemHealth != "UNAVAILABLE")

and, when it is False, RiskScore / RiskLevel / DominantEvidence / AlertSeverity are
all None together. A window with no usable evidence must never be reported as a
fabricated 0 / "Low" / "NORMAL".

Every test uses the tmp_path-scoped ``api`` / ``api_factory`` fixtures from conftest.
"""
import base64
import csv
import io
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

FOUR = ("RiskScore", "RiskLevel", "DominantEvidence", "AlertSeverity")
MODEL_ROOT = Path(__file__).resolve().parents[2] / "ml/outputs"
# All three stable files (test_model_gate.py checks every ``requires_models`` for it).
requires_models = pytest.mark.skipif(
    not all((MODEL_ROOT / name).exists() for name in ("vision/mobilenetv3_large_vision.onnx",
                                                      "vision/mobilenetv3_large_vision.pt",
                                                      "telemetry/xgb_telemetry.json")),
    reason="local trained artifacts not installed",
)


# --------------------------------------------------------------------- helpers
def window(pd=0.8, pt=0.2, v="fresh", t="fresh"):
    return {"P_distraction": pd, "P_telemetry_anomaly": pt, "vision_status": v, "telemetry_status": t}


def assert_identity(body):
    """The three-way identity, asserted on one and the same response body."""
    available = body["assessment_available"]
    assert isinstance(available, bool), body["assessment_available"]
    assert available == (body["RiskScore"] is not None) == (body["SystemHealth"] != "UNAVAILABLE")
    if not available:
        assert all(body[name] is None for name in FOUR), body


def assert_unavailable(body):
    assert body["assessment_available"] is False
    for name in FOUR:
        assert body[name] is None, name
    assert body["SystemHealth"] == "UNAVAILABLE"
    assert_identity(body)


def new_session(client, sid, weights=None, mode="PREPARED_SESSION_RUNTIME"):
    body = {"session_id": sid, "operation_mode": mode}
    if weights:
        body["config"] = {"weight_vision": weights[0], "weight_telemetry": weights[1]}
    response = client.post("/api/sessions", json=body)
    assert response.status_code == 201, response.text
    return sid


def _tag(weights):
    return "w" + "-".join(str(w).replace(".", "p") for w in weights)  # session ids forbid "."


def post_window(client, sid, **kwargs):
    response = client.post(f"/api/sessions/{sid}/windows", json=window(**kwargs))
    assert response.status_code == 201, response.text
    return response.json()


def risk_update_kwargs(**overrides):
    base = dict(
        session_id="s", window_id=1, timestamp="2026-10-12T00:00:00+00:00",
        P_distraction=0.5, P_telemetry_anomaly=0.5, RiskScore=50.0, RiskLevel="Medium",
        DominantEvidence="Combined evidence", AlertSeverity="CAUTION", SystemHealth="FULL",
        modality_freshness={"vision": "fresh", "telemetry": "fresh"}, latency_ms=0,
    )
    base.update(overrides)
    return base


CANONICAL_UNAVAILABLE = dict(
    assessment_available=False, RiskScore=None, RiskLevel=None, DominantEvidence=None,
    AlertSeverity=None, SystemHealth="UNAVAILABLE",
)


# --------------------------------------------------- schema: invariant + legacy
def test_available_record_derives_flag_and_keeps_enum_values():
    # Regression for the pydantic shadowing trap: declaring a field as
    # ``RiskLevel: Optional[RiskLevel] = None`` rebinds the Literal alias and
    # makes pydantic demand None for every value.
    from app.schemas import RiskUpdate
    ru = RiskUpdate(**risk_update_kwargs())
    assert ru.assessment_available is True
    assert (ru.RiskScore, ru.RiskLevel, ru.DominantEvidence, ru.AlertSeverity) == (
        50.0, "Medium", "Combined evidence", "CAUTION")
    assert ru.SystemHealth == "FULL"


def test_canonical_unavailable_record_is_accepted():
    from app.schemas import RiskUpdate
    ru = RiskUpdate(**risk_update_kwargs(**CANONICAL_UNAVAILABLE))
    assert ru.assessment_available is False
    assert all(getattr(ru, name) is None for name in FOUR)
    assert ru.SystemHealth == "UNAVAILABLE"


def test_assessment_available_is_serialised_before_the_numeric_fields():
    from app.schemas import RiskUpdate
    fields = list(RiskUpdate.model_fields)
    assert fields.index("timestamp") + 1 == fields.index("assessment_available")
    assert fields.index("assessment_available") < fields.index("P_distraction")


@pytest.mark.parametrize("shape", ["legacy-fabricated", "zero-weight-degraded"])
def test_missing_flag_is_derived_and_unavailable_shapes_are_normalised(shape):
    from app.schemas import RiskUpdate
    if shape == "legacy-fabricated":
        # What every pre-Task-4 no-evidence row stored.
        data = risk_update_kwargs(RiskScore=0.0, RiskLevel="Low", DominantEvidence="Partial evidence",
                                  AlertSeverity="NORMAL", SystemHealth="UNAVAILABLE")
    else:
        # Score is None but the producer still labelled the window DEGRADED
        # (denominator is zero because a weight is zero) and set NORMAL.
        data = risk_update_kwargs(RiskScore=None, RiskLevel=None, DominantEvidence=None,
                                  AlertSeverity="NORMAL", SystemHealth="DEGRADED")
    assert "assessment_available" not in data
    ru = RiskUpdate(**data)
    assert ru.assessment_available is False
    assert all(getattr(ru, name) is None for name in FOUR)
    assert ru.SystemHealth == "UNAVAILABLE"


@pytest.mark.parametrize("overrides", [
    dict(assessment_available=True, RiskScore=None),
    dict(assessment_available=True, SystemHealth="UNAVAILABLE"),
    dict(assessment_available=True, RiskLevel=None),
    dict(assessment_available=True, DominantEvidence=None),
    dict(assessment_available=True, AlertSeverity=None),
    {**CANONICAL_UNAVAILABLE, "RiskScore": 0.0},
    {**CANONICAL_UNAVAILABLE, "RiskLevel": "Low"},
    {**CANONICAL_UNAVAILABLE, "DominantEvidence": "Partial evidence"},
    {**CANONICAL_UNAVAILABLE, "AlertSeverity": "NORMAL"},
    {**CANONICAL_UNAVAILABLE, "SystemHealth": "DEGRADED"},
    {**CANONICAL_UNAVAILABLE, "SystemHealth": "FULL"},
], ids=["avail-no-score", "avail-unavailable-health", "avail-no-level", "avail-no-dominant",
        "avail-no-severity", "unavail-score", "unavail-level", "unavail-dominant",
        "unavail-severity", "unavail-degraded", "unavail-full"])
def test_explicit_flag_that_contradicts_the_fields_is_rejected(overrides):
    from app.schemas import RiskUpdate
    with pytest.raises(ValidationError):
        RiskUpdate(**risk_update_kwargs(**overrides))


# ------------------------------------------------------------- UT-FUS-03 (both)
def test_both_branches_missing_is_201_unavailable_and_reads_back_unchanged(api):
    client, sid = api
    created = post_window(client, sid, pd=0.0, pt=0.0, v="missing", t="missing")
    assert_unavailable(created)
    assert created["window_id"] == 1
    assert created["modality_freshness"] == {"vision": "missing", "telemetry": "missing"}
    # The stored record (not the in-process cache) must round-trip identically.
    assert client.get(f"/api/sessions/{sid}/windows").json() == [created]
    assert client.get(f"/api/sessions/{sid}/risk/latest").json() == created


@requires_models
def test_live_inference_with_no_inputs_is_201_unavailable(api):
    client, _ = api
    sid = new_session(client, "live-empty", mode="LIVE_MODEL_RUNTIME")
    response = client.post(f"/api/sessions/{sid}/infer", json={"request_id": "empty"})
    assert response.status_code == 201, response.text
    assert_unavailable(response.json())
    assert client.get(f"/api/sessions/{sid}/risk/latest").json() == response.json()


def test_latest_distinguishes_no_record_from_record_without_assessment(api):
    client, sid = api
    assert client.get(f"/api/sessions/{sid}/risk/latest").status_code == 404
    post_window(client, sid, v="missing", t="missing")
    latest = client.get(f"/api/sessions/{sid}/risk/latest")
    assert latest.status_code == 200
    assert latest.json()["assessment_available"] is False


# --------------------------------------------------------- UT-FUS-ZERO-WEIGHT
@pytest.mark.parametrize("weights, kwargs", [
    ((1.0, 0.0), dict(pd=0.0, pt=0.9, v="missing", t="fresh")),
    ((0.0, 1.0), dict(pd=0.9, pt=0.0, v="fresh", t="missing")),
], ids=["vision-only-weights", "telemetry-only-weights"])
def test_only_weighted_branch_missing_is_unavailable_not_a_server_error(api, weights, kwargs):
    # RuntimeConfig accepts (1.0, 0.0), so this is reachable from the public API:
    # the other branch is fresh but carries zero fusion weight, so the effective
    # denominator is 0 and there is nothing to fuse.
    client, _ = api
    sid = new_session(client, f"zero-{_tag(weights)}", weights)
    body = post_window(client, sid, **kwargs)
    assert_unavailable(body)
    assert client.get(f"/api/sessions/{sid}/risk/latest").json() == body


def test_zero_weight_branch_missing_while_weighted_branch_is_fresh_stays_available(api):
    # Pinned boundary (fixture F-Z3): FULL/DEGRADED looks at freshness only.
    client, _ = api
    sid = new_session(client, "zero-boundary", (1.0, 0.0))
    body = post_window(client, sid, pd=0.8, pt=0.0, v="fresh", t="missing")
    assert body["assessment_available"] is True
    assert body["RiskScore"] == 80.0
    assert body["SystemHealth"] == "DEGRADED"
    assert body["DominantEvidence"] == "Partial evidence"
    assert_identity(body)


@pytest.mark.parametrize("weights, kwargs, score", [
    # Ruling A: a vision branch DECLARED stale is expired, i.e. scored as missing (it was 65.2
    # when the runtime still weighted a stale branch at 0.45). Telemetry alone carries the score.
    ((0.5, 0.5), dict(pd=0.1, pt=0.9, v="stale", t="fresh"), 90.0),
    ((0.1, 0.9), dict(pd=0.0, pt=0.9, v="missing", t="fresh"), 90.0),
], ids=["declared-stale-vision-expires", "light-vision-weight"])
def test_partial_evidence_with_positive_denominator_stays_available(api, weights, kwargs, score):
    client, _ = api
    sid = new_session(client, f"control-{_tag(weights)}", weights)
    body = post_window(client, sid, **kwargs)
    assert body["assessment_available"] is True
    assert body["RiskScore"] == score
    assert body["SystemHealth"] == "DEGRADED"
    assert all(body[name] is not None for name in FOUR)
    assert body["modality_freshness"]["vision"] == "missing"
    # Only the DECLARED-stale branch is "expired"; a plain missing one never was received.
    assert body["provenance"]["vision_expired"] is (kwargs["v"] == "stale")
    assert_identity(body)


# ------------------------------------------------------------------------ IT-EPS
# Codex R05. The producer decides availability on one line,
# ``available = denominator > FUSION_EPSILON`` (FUSION_EPSILON = 1e-9). The fusion
# layer's own epsilon edge is pinned in test_fusion_vectors.py, but nothing drove
# the producer through the public API: ``>`` -> ``>=`` or ``> 0`` left the whole
# suite green. The consequence is not silent: a denominator in (0, 1e-9] under
# ``> 0``, or exactly 1e-9 under ``>=``, would make ``assessment_available``
# contradict ``RiskScore is None`` and the
# schema's ``after`` validator would turn /windows into a 500 instead of an
# unavailable record. RuntimeConfig accepts (eps, 1 - eps): the weights sum to 1
# within 1e-6.
#
# Two mirror directions, each with the ONLY fresh branch carrying the tiny weight
# (so the effective denominator is exactly that weight):
#   "vision-tiny":    w_v = eps, w_t = 1 - eps; vision fresh, telemetry missing
#   "telemetry-tiny": w_v = 1 - eps, w_t = eps; vision missing, telemetry fresh
# Expected values are literals; nothing is imported from the implementation.
EPS_CASES = {
    "vision-tiny": dict(
        weights=lambda eps: (eps, 1 - eps), tiny_key="weight_vision",
        window=dict(pd=0.8, pt=0.2, v="fresh", t="missing"),
        freshness={"vision": "fresh", "telemetry": "missing"}),
    "telemetry-tiny": dict(
        weights=lambda eps: (1 - eps, eps), tiny_key="weight_telemetry",
        window=dict(pd=0.2, pt=0.8, v="missing", t="fresh"),
        freshness={"vision": "missing", "telemetry": "fresh"}),
}


def _eps_run(client, direction, eps, label):
    """Create a fresh session with ``(eps, 1 - eps)`` weights (201 asserted inside
    ``new_session``), post the one window (201 asserted inside ``post_window``) and
    return ``(session_id, response_body)``. Every call uses its own session."""
    case = EPS_CASES[direction]
    sid = new_session(client, f"eps-{direction}-{label}", case["weights"](eps))
    body = post_window(client, sid, **case["window"])
    # The tiny weight really travelled through the public API into the producer.
    assert body["provenance"]["fusion_config"][case["tiny_key"]] == eps
    assert body["modality_freshness"] == case["freshness"]
    return sid, body


@pytest.mark.parametrize("direction", ["vision-tiny", "telemetry-tiny"])
@pytest.mark.parametrize("eps, label", [(1e-10, "below"), (1e-9, "at-boundary")],
                         ids=["1e-10", "1e-9"])
def test_effective_weight_at_or_below_epsilon_is_unavailable_not_a_server_error(
        api, direction, eps, label):
    # The boundary is ``<=``: a denominator of exactly 1e-9 is still "nothing to fuse".
    client, _ = api
    sid, body = _eps_run(client, direction, eps, label)
    assert body["assessment_available"] is False
    assert body["RiskScore"] is None
    assert body["RiskLevel"] is None
    assert body["DominantEvidence"] is None
    assert body["AlertSeverity"] is None
    assert body["SystemHealth"] == "UNAVAILABLE"
    assert_unavailable(body)
    # The stored record, not just the response, carries the same unavailable shape.
    assert client.get(f"/api/sessions/{sid}/risk/latest").json() == body
    assert client.get(f"/api/sessions/{sid}/windows").json() == [body]


@pytest.mark.parametrize("direction", ["vision-tiny", "telemetry-tiny"])
def test_effective_weight_just_above_epsilon_is_an_available_degraded_assessment(api, direction):
    client, _ = api
    sid, body = _eps_run(client, direction, 1.1e-9, "above")
    assert body["assessment_available"] is True
    assert body["SystemHealth"] == "DEGRADED"
    assert body["RiskScore"] == 80.0
    assert body["RiskLevel"] == "High"
    assert body["AlertSeverity"] == "CAUTION"  # first High window: not yet sustained
    assert body["DominantEvidence"] == "Partial evidence"
    assert_identity(body)
    assert client.get(f"/api/sessions/{sid}/risk/latest").json() == body


def _jpeg_b64():
    from PIL import Image
    buffer = io.BytesIO()
    Image.new("RGB", (640, 480), (80, 130, 180)).save(buffer, format="JPEG")
    return base64.b64encode(buffer.getvalue()).decode()


@requires_models
@pytest.mark.parametrize("weights, only", [((1.0, 0.0), "telemetry"), ((0.0, 1.0), "vision")],
                         ids=["weights-vision-only", "weights-telemetry-only"])
def test_live_zero_weight_class_with_the_weighted_branch_missing(api, weights, only):
    client, _ = api
    sid = new_session(client, f"live-zero-{only}", weights, mode="LIVE_MODEL_RUNTIME")
    now = datetime.now(timezone.utc).isoformat()
    body = {"request_id": f"zw-{only}"}
    if only == "telemetry":
        body.update(telemetry_features=dict(speed_kmph=52, accel_x=.7, accel_y=.2, brake_pressure=20,
                                            steering_angle=7.5, throttle=40, lane_deviation=.21,
                                            headway_distance=18),
                    telemetry_timestamp=now, telemetry_source="prepared_replay")
    else:
        body.update(image_base64=_jpeg_b64(), captured_at=now)
    response = client.post(f"/api/sessions/{sid}/infer", json=body)
    assert response.status_code == 201, response.text
    assert_unavailable(response.json())


# ------------------------------------------------------ legacy rows must be readable
def _legacy_payload(sid, window_id, available):
    payload = {
        "session_id": sid, "window_id": window_id, "timestamp": "2026-09-28T00:00:00+00:00",
        "P_distraction": 0.8 if available else 0.0, "P_telemetry_anomaly": 0.2 if available else 0.0,
        "RiskScore": 50.0 if available else 0.0, "RiskLevel": "Medium" if available else "Low",
        "DominantEvidence": "Vision-dominant" if available else "Partial evidence",
        "AlertSeverity": "CAUTION" if available else "NORMAL",
        "SystemHealth": "FULL" if available else "UNAVAILABLE",
        "operation_mode": "PREPARED_SESSION_RUNTIME",
        "modality_freshness": {"vision": "fresh" if available else "missing",
                               "telemetry": "fresh" if available else "missing"},
        "latency_ms": 0, "visual_top_classes": [], "telemetry_behavior_classes": [],
        "telemetry_feature_contributions": [], "telemetry_features": None,
        "explanation": "legacy", "flagged": False,
        "provenance": {"provider": "MockAIProvider"},
    }
    assert "assessment_available" not in payload  # pre-Task-4 shape
    return payload


def _insert_legacy(factory, sid):
    from app import models
    with factory() as db:
        for window_id, available in ((1, True), (2, False)):
            payload = _legacy_payload(sid, window_id, available)
            db.add(models.InferenceRecord(
                session_id=sid, window_id=window_id, timestamp=payload["timestamp"],
                p_distraction=payload["P_distraction"], p_telemetry_anomaly=payload["P_telemetry_anomaly"],
                risk_score=payload["RiskScore"], risk_level=payload["RiskLevel"],
                dominant_evidence=payload["DominantEvidence"], alert_severity=payload["AlertSeverity"],
                system_health=payload["SystemHealth"], latency_ms=0, flagged=False, payload=payload))
        db.commit()


def test_pre_existing_rows_without_the_flag_do_not_break_any_read(api, api_factory):
    client, sid = api
    _insert_legacy(api_factory, sid)
    listing = client.get(f"/api/sessions/{sid}/windows")
    assert listing.status_code == 200, listing.text
    first, second = listing.json()
    assert first["assessment_available"] is True and first["RiskScore"] == 50.0
    assert_identity(first)
    assert_unavailable(second)  # the fabricated 0 / Low / NORMAL row, normalised
    latest = client.get(f"/api/sessions/{sid}/risk/latest")
    assert latest.status_code == 200 and latest.json() == second
    flagged = client.patch(f"/api/sessions/{sid}/windows/2/flag?flagged=true")
    assert flagged.status_code == 200 and flagged.json()["flagged"] is True
    assert_unavailable(flagged.json())


# ------------------------------------------------------------------ ST-STATUS-01
def test_status_separates_no_record_from_record_without_assessment(api):
    client, sid = api
    fresh = client.get(f"/api/sessions/{sid}/system-status").json()
    assert fresh["latest_window_id"] is None
    assert fresh["latest_assessment_available"] is None
    assert fresh["latest_risk_score"] is None
    assert fresh["open_fault_events"] == 0

    post_window(client, sid, v="missing", t="missing")
    status = client.get(f"/api/sessions/{sid}/system-status").json()
    assert status["latest_window_id"] == 1
    assert status["latest_assessment_available"] is False
    assert status["latest_risk_score"] is None
    assert status["latest_alert_severity"] is None
    assert status["latest_system_health"] == "UNAVAILABLE"

    post_window(client, sid, pd=0.8, pt=0.2)
    status = client.get(f"/api/sessions/{sid}/system-status").json()
    assert status["latest_window_id"] == 2
    assert status["latest_assessment_available"] is True
    assert status["latest_risk_score"] == 50.0
    assert status["latest_alert_severity"] is not None


def test_status_tolerates_a_legacy_row_with_no_payload(api, api_factory):
    from app import models
    client, sid = api
    with api_factory() as db:
        db.add(models.InferenceRecord(session_id=sid, window_id=1, system_health="DEGRADED",
                                      payload=None))
        db.commit()
    response = client.get(f"/api/sessions/{sid}/system-status")
    assert response.status_code == 200, response.text
    assert response.json()["latest_window_id"] == 1
    assert response.json()["ai_provider"] == "MockAIProvider"


# --------------------------------------------------------------------- EX-NULL-01
ORIGINAL_COLUMNS = [
    "session_id", "window_id", "timestamp", "operation_mode", "P_distraction",
    "P_telemetry_anomaly", "RiskScore", "RiskLevel", "DominantEvidence", "AlertSeverity",
    "SystemHealth", "latency_ms", "flagged", "vision_source", "telemetry_source",
    "vision_model_sha256", "telemetry_model_sha256", "request_id", "provenance",
    "modality_freshness", "visual_top_classes", "telemetry_behavior_classes",
    "telemetry_feature_contributions", "telemetry_features", "explanation",
]


def _two_windows(client, sid):
    available = post_window(client, sid, pd=0.8, pt=0.2)
    unavailable = post_window(client, sid, pd=0.33, pt=0.44, v="missing", t="missing")
    assert_identity(available)
    assert_unavailable(unavailable)
    return available, unavailable


def test_json_export_carries_null_and_false_not_zero(api):
    client, sid = api
    _two_windows(client, sid)
    response = client.get(f"/api/sessions/{sid}/export?format=json")
    assert response.status_code == 200
    records = response.json()["records"]
    assert records[0]["assessment_available"] is True
    assert records[0]["RiskScore"] == 50.0
    assert records[1]["assessment_available"] is False
    for name in FOUR:
        assert records[1][name] is None
    assert records[1]["SystemHealth"] == "UNAVAILABLE"
    assert "assessment_available" not in records[1]["provenance"]
    # Booleans are JSON booleans on the wire, not 1/0.
    assert '"assessment_available": false' in response.text
    assert '"assessment_available": true' in response.text
    for record in records:
        assert_identity(record)


def test_csv_export_uses_empty_cells_and_lowercase_booleans(api):
    client, sid = api
    _two_windows(client, sid)
    response = client.get(f"/api/sessions/{sid}/export?format=csv")
    assert response.status_code == 200
    reader = csv.DictReader(io.StringIO(response.text))
    header = reader.fieldnames
    assert header[: len(ORIGINAL_COLUMNS)] == ORIGINAL_COLUMNS  # appended, never inserted
    assert "assessment_available" in header
    assert header.index("assessment_available") >= len(ORIGINAL_COLUMNS)
    assert "P_distraction_raw" in header and "P_telemetry_raw" in header
    one, two = list(reader)
    assert one["RiskScore"] == "50.0"
    assert one["assessment_available"] == "true"
    assert two["assessment_available"] == "false"
    for name in FOUR:
        assert two[name] == "", name  # empty cell, neither "0" nor "None"
    assert two["SystemHealth"] == "UNAVAILABLE"
    for row in (one, two):
        assert row["flagged"] in ("true", "false")
        assert row["assessment_available"] in ("true", "false")
    # The honest raw inputs of the unavailable window are exported next to the zeros.
    assert two["P_distraction"] == "0.0" and two["P_distraction_raw"] == "0.33"
    assert two["P_telemetry_anomaly"] == "0.0" and two["P_telemetry_raw"] == "0.44"
    # ...and a flagged record uses the same lowercase convention.
    client.patch(f"/api/sessions/{sid}/windows/2/flag?flagged=true")
    flagged = list(csv.DictReader(io.StringIO(client.get(f"/api/sessions/{sid}/export?format=csv").text)))
    assert [r["flagged"] for r in flagged] == ["false", "true"]


# ----------------------------------------------------------------- cache hygiene
def test_deleting_an_older_window_keeps_the_cache_for_the_newer_one(api):
    from app import cache
    client, sid = api
    post_window(client, sid, pd=0.1)
    post_window(client, sid, pd=0.2)
    assert cache.get_latest(sid).window_id == 2
    assert client.delete(f"/api/sessions/{sid}/windows/1").status_code == 204
    assert cache.get_latest(sid) is not None and cache.get_latest(sid).window_id == 2
    assert client.get(f"/api/sessions/{sid}/system-status").json()["cache_warm"] is True
    assert client.delete(f"/api/sessions/{sid}/windows/2").status_code == 204
    assert cache.get_latest(sid) is None
    assert client.get(f"/api/sessions/{sid}/system-status").json()["cache_warm"] is False
