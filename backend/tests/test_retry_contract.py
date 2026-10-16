"""Task 8 - what the server must guarantee for the client's bounded retry to be safe.

The client (``ai/src/liveLoop.ts``) re-sends ONE frozen payload, byte for byte, up to
three times automatically and once more per manual Retry, each time with a larger
``X-Attempt-Index``. These tests pin the server half of that bargain. None of them
needs model weights: the provider is stubbed with the request-driven stub of
``test_temporal_contract`` and the clock is its fake clock.

IT-RETRY-IDENTITY  the response was lost AFTER the commit: the re-send is answered from the
                   stored record, the database gains no row and the temporal state does not
                   move; the same id with different content is a 409.
IT-RETRY-STALE     a re-send that is processed long after the capture. Its evidence has
                   EXPIRED (ruling A): it scores as missing, so a late re-send of a window whose
                   both branches are old is UNAVAILABLE and never advances the alert timers.
IT-RETRY-TEXTS     the 409 / 422 detail texts that the client classifies on.
IT-RETRY-EMPTY     an all-empty LiveInput is a 201 UNAVAILABLE window, so a camera that has
                   stopped never makes the request fail (R5). The real-model counterpart is
                   ``test_live_inference_with_no_inputs_is_201_unavailable`` in
                   ``test_unavailable_contract.py``; this one runs without weights.

Every number in an expectation below is a literal.
"""
import json
from datetime import datetime, timedelta, timezone

import pytest

from app import models

# Sibling test module: the fake clock, the request-driven stub provider and the request
# builders that IT-LIVE-AGE already uses. ``fake_clock`` is a fixture; importing it is
# what makes it visible to the tests below.
from test_temporal_contract import (  # noqa: F401  (fake_clock is used as a fixture)
    TELEMETRY_FEATURES,
    _live_age_request,
    _live_age_session,
    at,
    fake_clock,
)


def infer(client, sid, body, attempt):
    """One delivery of ``body``, the way the client sends it."""
    return client.post(f"/api/sessions/{sid}/infer", json=body,
                       headers={"X-Attempt-Index": str(attempt)})


def snapshot(api_factory, sid):
    """Everything a re-send must not touch: the persisted temporal state, the window
    counter and every stored record, read through a fresh connection."""
    with api_factory() as db:
        session = db.get(models.SessionMeta, sid)
        records = (db.query(models.InferenceRecord).filter_by(session_id=sid)
                   .order_by(models.InferenceRecord.window_id).all())
        return {
            # round-trip through JSON: a deep, detached copy of the persisted column
            "runtime_state": json.loads(json.dumps(session.runtime_state)),
            "next_window_id": session.next_window_id,
            "records": [(r.window_id, r.request_id, r.request_hash, r.timestamp, r.risk_score,
                         r.alert_severity, json.dumps(r.payload, sort_keys=True)) for r in records],
        }


def fault_count(api_factory, sid):
    from sqlalchemy import text
    with api_factory() as db:
        return db.execute(text("SELECT COUNT(*) FROM fault_events WHERE session_id = :sid"),
                          {"sid": sid}).scalar_one()


# ----------------------------------------------------------- IT-RETRY-IDENTITY
@pytest.mark.parametrize("replay_after_ms,attempt", [(0, 2), (6000, 3), (12_000, 4)])
def test_it_retry_identity_a_resend_after_a_lost_response_changes_nothing(
        api, api_factory, fake_clock, monkeypatch, replay_after_ms, attempt):
    """The first POST commits; its response is lost. The client re-sends the same UUID and
    the same bytes (attempt 2 right away, attempt 3 after the 2 s + 4 s backoffs, attempt 4
    after a manual Retry). The database must hold exactly ONE row for that request_id, and
    the temporal state - the EMA chain, the High streak, the evidence watermarks, the window
    counter - must equal its value after the first commit: the state advances once."""
    client, _ = api
    sid = _live_age_session(client, monkeypatch, f"retry-identity-{replay_after_ms}")
    fake_clock.set(0)
    body = _live_age_request("lost-response", at(0), at(0))
    first = infer(client, sid, body, 1)
    assert first.status_code == 201, first.text
    committed = snapshot(api_factory, sid)
    # There is something to protect: a High segment is open and both watermarks are set.
    assert committed["runtime_state"]["captured_at"] == at(0).isoformat()
    assert committed["runtime_state"]["telemetry_timestamp"] == at(0).isoformat()
    assert committed["runtime_state"]["high_srv_us"] is not None
    assert committed["next_window_id"] == 1
    assert len(committed["records"]) == 1

    fake_clock.set(replay_after_ms)
    replay = infer(client, sid, body, attempt)

    assert replay.status_code == 201, replay.text
    assert replay.json() == first.json()  # the stored record, window 1, not a second window
    assert replay.json()["window_id"] == 1
    # The replay is NOT re-judged against the clock: still fresh, though now 6-12 s old.
    assert replay.json()["modality_freshness"] == {"vision": "fresh", "telemetry": "fresh"}
    assert snapshot(api_factory, sid) == committed
    assert fault_count(api_factory, sid) == 0  # a replay is not a failure
    with api_factory() as db:
        assert db.query(models.InferenceRecord).filter_by(session_id=sid, request_id="lost-response").count() == 1

    # Numbering has no hole: the next NEW request is window 2.
    fake_clock.set(replay_after_ms + 500)
    fresh = {**_live_age_request("next", at(replay_after_ms + 500), at(replay_after_ms + 500)),
             "image_base64": "next-frame"}
    nxt = infer(client, sid, fresh, 1)
    assert nxt.status_code == 201, nxt.text
    assert nxt.json()["window_id"] == 2


def test_it_retry_identity_the_replay_does_not_depend_on_the_attempt_header(api, api_factory, fake_clock, monkeypatch):
    """A client that sends no header at all (or a different number) gets the same answer:
    the header is bookkeeping for the fault table, not part of the request's identity."""
    client, _ = api
    sid = _live_age_session(client, monkeypatch, "retry-identity-header")
    fake_clock.set(0)
    body = _live_age_request("header-free", at(0), at(0))
    first = infer(client, sid, body, 1)
    committed = snapshot(api_factory, sid)
    bare = client.post(f"/api/sessions/{sid}/infer", json=body)  # no header
    assert bare.status_code == 201 and bare.json() == first.json()
    assert infer(client, sid, body, 999).json() == first.json()
    assert snapshot(api_factory, sid) == committed


@pytest.mark.parametrize("change", [
    {"image_base64": "another-frame"},
    {"captured_at": at(1).isoformat()},
    {"telemetry_features": {**TELEMETRY_FEATURES, "speed_kmph": 99}},
    {"telemetry_timestamp": at(1).isoformat()},
], ids=["image", "captured_at", "telemetry_values", "telemetry_timestamp"])
def test_it_retry_identity_the_same_uuid_with_a_different_payload_is_409_and_changes_nothing(
        api, api_factory, fake_clock, monkeypatch, change):
    """This is why the client freezes the whole payload: re-capturing under the old id is a
    409, and a 409 of this kind is not retryable."""
    client, _ = api
    sid = _live_age_session(client, monkeypatch, "retry-identity-conflict")
    fake_clock.set(0)
    body = _live_age_request("same-id", at(0), at(0))
    assert infer(client, sid, body, 1).status_code == 201
    committed = snapshot(api_factory, sid)

    fake_clock.set(2000)
    conflict = infer(client, sid, {**body, **change}, 2)

    assert conflict.status_code == 409
    assert conflict.json()["detail"] == "request_id already used for different input"
    assert snapshot(api_factory, sid) == committed


# ------------------------------------------------------------- IT-RETRY-STALE
# (The id keeps its name: "stale" is what a late re-send used to be stored as. Under ruling A the
# late window is EXPIRED - see the docstrings.)
@pytest.mark.parametrize("arrives_after_ms,attempt,fresh,health,available,age_s", [
    (2000, 2, True, "FULL", True, 2.0),            # one 2 s backoff: still inside the 3 s tolerance
    (6000, 3, False, "UNAVAILABLE", False, 6.0),   # 2 s + 4 s backoffs: the third delivery is 6 s old
    (12_000, 2, False, "UNAVAILABLE", False, 12.0),  # a 10 s timeout, then the 2 s backoff
])
def test_it_retry_stale_a_resend_processed_late_is_expired_and_unavailable(
        api, fake_clock, monkeypatch, arrives_after_ms, attempt, fresh, health, available, age_s):
    """Earlier deliveries never committed (a timeout, a dropped connection). The retry re-sends
    the first capture's ``captured_at`` / ``telemetry_timestamp`` byte for byte, so by the time
    it is processed its evidence is ``arrives_after_ms`` old. The server re-derives freshness
    from those stamps (3 s tolerance, strict ``>``). Inside the tolerance the window is a normal
    FULL one. Past it BOTH branches have expired - scored as missing, with
    ``vision_expired`` / ``telemetry_expired`` and the age in the provenance - so nothing is
    left to fuse: assessment_available is False, UNAVAILABLE, all four risk fields null.
    (Under the old tier this was stale / DEGRADED with a High score.)"""
    client, _ = api
    sid = _live_age_session(client, monkeypatch, f"retry-stale-{arrives_after_ms}")
    body = _live_age_request("late-retry", at(0), at(0))  # captured at t = 0
    fake_clock.set(arrives_after_ms)

    response = infer(client, sid, body, attempt)

    assert response.status_code == 201, response.text
    record = response.json()
    status = "fresh" if fresh else "missing"
    assert record["modality_freshness"] == {"vision": status, "telemetry": status}
    assert record["SystemHealth"] == health
    assert record["assessment_available"] is available
    provenance = record["provenance"]
    assert (provenance["vision_expired"], provenance["telemetry_expired"]) == (not fresh, not fresh)
    assert (provenance["vision_age_s"], provenance["telemetry_age_s"]) == (age_s, age_s)
    if available:
        assert record["RiskScore"] == 100.0 and record["RiskLevel"] == "High"
    else:
        assert (record["RiskScore"], record["RiskLevel"], record["DominantEvidence"],
                record["AlertSeverity"]) == (None, None, None, None)
    # The stamps are the first capture's, not the retry's.
    assert provenance["captured_at"] == at(0).isoformat()
    assert provenance["telemetry_timestamp"] == at(0).isoformat()


def test_it_retry_stale_late_resends_do_not_accumulate_sustained_high(
        api, api_factory, fake_clock, monkeypatch):
    """Three logical requests captured 2 s apart (t = 0, 2000, 4000), every one of them delivered
    6 s after its capture (server time 6000, 8000, 10000). Each is expired on both branches, so
    each is UNAVAILABLE with a null AlertSeverity and the server-side High streak - which runs on
    the server's clock, not on the evidence's age - is never started: the sequence that used to
    reach HIGH_ALERT on the second window stays silent however many late re-sends arrive."""
    client, _ = api
    sid = _live_age_session(client, monkeypatch, "retry-stale-accumulates")
    records = []
    for index, captured in enumerate((0, 2000, 4000)):
        fake_clock.set(captured + 6000)
        body = {**_live_age_request(f"late-{index}", at(captured), at(captured)),
                "image_base64": f"late-frame-{index}"}  # three DIFFERENT frames, each captured at its own time
        response = infer(client, sid, body, 3)
        assert response.status_code == 201, response.text
        records.append(response.json())
    for record in records:
        assert record["modality_freshness"] == {"vision": "missing", "telemetry": "missing"}
        assert (record["provenance"]["vision_expired"], record["provenance"]["telemetry_expired"]) == (True, True)
        assert record["SystemHealth"] == "UNAVAILABLE"
        assert record["RiskLevel"] is None
    assert [r["AlertSeverity"] for r in records] == [None, None, None]
    state = snapshot(api_factory, sid)["runtime_state"]
    assert state["high_srv_us"] is None and state["low_srv_us"] is None  # the timers are suspended
    assert "last_severity" not in state  # nothing was ever latched


# ------------------------------------------------------------ IT-RETRY-TEXTS
def test_it_retry_texts_the_409_and_422_details_the_client_classifies_on(api, fake_clock, monkeypatch):
    """``frontend/src/api/retryPolicy.ts`` tells the causes of a 409, and a clock-skew 422,
    apart by the response text. If a message is reworded the client silently misclassifies:
    a late frame would stop the session again. The expected strings are the ones in
    ``retryPolicy.test.ts``."""
    client, replay_sid = api
    sid = _live_age_session(client, monkeypatch, "retry-texts")
    fake_clock.set(0)
    body = _live_age_request("first", at(1000), at(1000))
    assert infer(client, sid, body, 1).status_code == 201

    hash_conflict = infer(client, sid, {**body, "image_base64": "different"}, 2)
    assert (hash_conflict.status_code, hash_conflict.json()["detail"]) == (
        409, "request_id already used for different input")

    # An older captured_at than the one already accepted: a late frame. It is a different frame
    # (another image) - a repeat of the accepted one would be judged by its first acquisition time,
    # not by the stamp it re-sends - and its telemetry reading is older than the accepted one too.
    late = infer(client, sid, {**_live_age_request("late", at(0), at(0)), "image_base64": "late-frame"}, 1)
    assert (late.status_code, late.json()["detail"]) == (409, "Out-of-order evidence timestamp")

    # A replay-mode session addressed as a live one, and the reverse.
    wrong_mode = client.post(f"/api/sessions/{replay_sid}/infer", json=_live_age_request("m1", at(2000), at(2000)))
    assert (wrong_mode.status_code, wrong_mode.json()["detail"]) == (409, "Create a live model session first")
    window = client.post(f"/api/sessions/{sid}/windows", json={"P_distraction": 0.5, "P_telemetry_anomaly": 0.5})
    assert (window.status_code, window.json()["detail"]) == (409, "Input does not match session operation mode")

    # A device clock more than 5 s ahead of the server: the client joins the ``msg`` fields.
    ahead = (datetime.now(timezone.utc) + timedelta(seconds=60)).isoformat()
    skew = client.post(f"/api/sessions/{sid}/infer",
                       json={"request_id": "skew", "image_base64": "stub-frame", "captured_at": ahead})
    assert skew.status_code == 422
    assert "timestamp is in the future" in "; ".join(item["msg"] for item in skew.json()["detail"])


# ------------------------------------------------------------- IT-RETRY-EMPTY
def test_it_retry_empty_an_all_empty_request_is_a_201_unavailable_window_and_the_next_one_is_assessed(
        api, fake_clock, monkeypatch):
    """The camera has been stopped and the telemetry is missing too: the client still sends the
    request (R5), and the server answers 201 with a window that has no assessment - not a 422 -
    so nothing counts against the delivery budget. The next request, with evidence, is a
    normal assessed window."""
    client, _ = api
    sid = _live_age_session(client, monkeypatch, "retry-empty")
    fake_clock.set(0)
    empty = infer(client, sid, {"request_id": "empty"}, 1)
    assert empty.status_code == 201, empty.text
    record = empty.json()
    assert record["assessment_available"] is False
    assert (record["RiskScore"], record["RiskLevel"], record["DominantEvidence"], record["AlertSeverity"]) == (
        None, None, None, None)
    assert record["SystemHealth"] == "UNAVAILABLE"
    assert record["modality_freshness"] == {"vision": "missing", "telemetry": "missing"}
    assert client.get(f"/api/sessions/{sid}/risk/latest").json() == record

    fake_clock.set(500)
    nxt = infer(client, sid, _live_age_request("with-evidence", at(500), at(500)), 1)
    assert nxt.status_code == 201, nxt.text
    assert nxt.json()["window_id"] == 2 and nxt.json()["assessment_available"] is True
