"""R10-B (B7) - the wire contract with the front end's payload builder.

The request bodies are the literal JSON in ``fixtures/live_payload_shapes.json``. That file is
shared with the front end: ``ai/src/livePayloadContract.test.ts`` asserts that
``buildLivePayload`` (and the loop that calls it) produce exactly the ``accepted`` shapes from
their inputs, and can never produce a ``rejected`` one. This file asserts the other half: the
real ``POST /sessions/{id}/infer`` route (real router, real classification under the write lock,
real SQLite transaction; only the model probabilities are stubbed, as in ``test_r10_observations``)
accepts every ``accepted`` shape with a 201 and refuses every ``rejected`` shape with a 422.

Why the two 422 rules matter to the client: a 422 is not retryable and stops the live session, so
a front end that sent ``vision_frame`` without an image, or ``telemetry_seq`` without telemetry,
would turn a harmless piece of identity metadata into a dead session. Nothing here changes the
application code; the tests only pin what the two sides must agree on.

Test clock: the fixture's times are on 2025-01-01T12:00:00Z, which is ``at(0)`` of the shared
fake clock (``test_temporal_contract``). Each test moves the clock to the moment its request was
"sent", so the evidence is as fresh as it was on the browser.
"""
import json
from pathlib import Path

import pytest

from test_r10_observations import drive, state_of, window_count  # noqa: F401  (drive is a fixture)
from test_temporal_contract import fake_clock  # noqa: F401  (a fixture the drive fixture uses)

SHAPES = json.loads((Path(__file__).parent / "fixtures" / "live_payload_shapes.json").read_text())
ACCEPTED, REJECTED = SHAPES["accepted"], SHAPES["rejected"]

OFFENDING_KEYS = {
    "no_frame_but_vision_frame": ("no_frame", "vision_frame", "vision_frame requires an image"),
    "no_telemetry_but_telemetry_seq": (
        "no_telemetry", "telemetry_seq", "telemetry_seq requires telemetry feature values"),
}


def post(d, body, ms, attempt=1):
    d.clock.set(ms)
    return d.client.post(f"/api/sessions/{d.sid}/infer", json=body, headers={"X-Attempt-Index": str(attempt)})


def provenance_of(record, *keys):
    return {key: record["provenance"].get(key) for key in keys}


IDENTITY_KEYS = ("vision_obs", "telemetry_obs", "vision_frame_id", "telemetry_seq", "identity_source",
                 "vision_identity_source", "telemetry_identity_source", "captured_at_source")


# ------------------------------------------------------------------------ the accepted shapes
# name -> (the moment the request was sent, milliseconds after 12:00:00Z; what the server read from it)
EXPECTED = {
    # an explicit frame and a sample, both with their identity
    "frame_and_telemetry": (0, {
        "vision_obs": "new", "telemetry_obs": "new",
        "vision_frame_id": "1735732800000:241", "telemetry_seq": 0,
        "identity_source": "explicit", "vision_identity_source": "explicit",
        "telemetry_identity_source": "explicit", "captured_at_source": "capture_time"}),
    # no picture: no vision observation at all
    "no_frame": (2000, {
        "vision_obs": None, "telemetry_obs": "new",
        "vision_frame_id": None, "telemetry_seq": 1,
        "identity_source": "explicit", "vision_identity_source": None,
        "telemetry_identity_source": "explicit", "captured_at_source": None}),
    # a row with no telemetry: no telemetry observation at all
    "no_telemetry": (0, {
        "vision_obs": "new", "telemetry_obs": None,
        "vision_frame_id": "1735732800000:242", "telemetry_seq": None,
        "identity_source": "explicit", "vision_identity_source": "explicit",
        "telemetry_identity_source": None, "captured_at_source": "callback"}),
    # the fallback mode: the picture is identified by its bytes, so one branch is not explicit
    "fallback_mode": (0, {
        "vision_obs": "new", "telemetry_obs": "new",
        "vision_frame_id": None, "telemetry_seq": 0,
        "identity_source": "fallback", "vision_identity_source": "fallback",
        "telemetry_identity_source": "explicit", "captured_at_source": "client_clock"}),
    # neither: still a 201, with an UNAVAILABLE window
    "nothing": (0, {
        "vision_obs": None, "telemetry_obs": None,
        "vision_frame_id": None, "telemetry_seq": None,
        "identity_source": None, "vision_identity_source": None,
        "telemetry_identity_source": None, "captured_at_source": None}),
}


def test_the_fixture_and_the_expectations_cover_the_same_shapes():
    assert list(ACCEPTED) == list(EXPECTED) == [
        "frame_and_telemetry", "no_frame", "no_telemetry", "fallback_mode", "nothing"]
    assert list(REJECTED) == list(OFFENDING_KEYS)


@pytest.mark.parametrize("name", list(EXPECTED))
def test_every_shape_the_front_end_builds_is_accepted_and_read_as_intended(drive, name):
    sent_at, expected = EXPECTED[name]
    record = post(drive(), ACCEPTED[name], sent_at)
    assert record.status_code == 201, record.text
    assert provenance_of(record.json(), *IDENTITY_KEYS) == expected


def test_the_evidence_of_a_full_request_is_fresh_and_assessed(drive):
    record = post(drive(), ACCEPTED["frame_and_telemetry"], 0).json()
    assert record["assessment_available"] is True
    assert record["modality_freshness"] == {"vision": "fresh", "telemetry": "fresh"}
    # The two acquisition times are the ones the request carried, not the moment of receipt.
    assert record["provenance"]["captured_at"] == "2025-01-01T11:59:59.970000+00:00"
    assert record["provenance"]["telemetry_timestamp"] == "2025-01-01T12:00:00+00:00"


def test_a_request_without_either_input_is_a_201_with_an_unavailable_window(drive):
    record = post(drive(), ACCEPTED["nothing"], 0).json()
    assert record["assessment_available"] is False
    assert record["SystemHealth"] == "UNAVAILABLE"


def test_the_frozen_payload_re_sent_by_a_retry_is_the_same_window_not_a_conflict(drive, api_factory):
    d = drive()
    first = post(d, ACCEPTED["frame_and_telemetry"], 0)
    # The client lost the response and re-sends the byte-identical body 6 s later (attempt 3).
    retry = post(d, ACCEPTED["frame_and_telemetry"], 6000, attempt=3)
    assert (first.status_code, retry.status_code) == (201, 201)
    assert retry.json() == first.json()
    assert window_count(api_factory, d.sid) == 1


def test_two_ticks_inside_one_frame_and_one_sample_are_repeats_not_new_observations(drive, api_factory):
    # The loop ticks faster than the camera and the 2 s telemetry: the next request carries the
    # SAME (epoch, index), the same bytes and the same sample - only the request id is new.
    d = drive()
    post(d, ACCEPTED["frame_and_telemetry"], 0)
    again = post(d, {**ACCEPTED["frame_and_telemetry"], "request_id": "contract-next-tick"}, 500)
    assert again.status_code == 201, again.text
    assert provenance_of(again.json(), "vision_obs", "telemetry_obs") == {
        "vision_obs": "repeat", "telemetry_obs": "repeat"}
    assert window_count(api_factory, d.sid) == 2


def test_a_page_local_epoch_counter_that_restarted_at_zero_is_refused_as_out_of_order(drive, api_factory):
    # What the front end's epoch (the start time in milliseconds) prevents: after a reload a
    # counter that began at 0 would send epoch 1 behind the epoch the session already holds, and
    # every frame would be a 409 'Out-of-order evidence timestamp' - dropped, never counted.
    d = drive()
    post(d, ACCEPTED["frame_and_telemetry"], 0)
    behind = {**ACCEPTED["no_telemetry"], "request_id": "contract-reloaded",
              "vision_frame": {"epoch": 1, "index": 1}}
    response = post(d, behind, 100)
    assert response.status_code == 409
    assert response.json()["detail"] == "Out-of-order evidence timestamp"
    # ...whereas a later camera start (a larger epoch) simply continues the session.
    later = {**ACCEPTED["no_telemetry"], "request_id": "contract-restarted",
             "vision_frame": {"epoch": 1735732800000 + 60_000, "index": 1}}
    accepted = post(d, later, 200)
    assert accepted.status_code == 201, accepted.text
    assert accepted.json()["provenance"]["vision_frame_id"] == "1735732860000:1"
    assert window_count(api_factory, d.sid) == 2


# ------------------------------------------------------------------------ the rejected shapes
@pytest.mark.parametrize("name", list(OFFENDING_KEYS))
def test_a_frame_id_without_an_image_and_a_sequence_number_without_telemetry_are_a_422(drive, api_factory, name):
    _, _, message = OFFENDING_KEYS[name]
    d = drive()
    response = post(d, REJECTED[name], 2000)
    assert response.status_code == 422
    assert message in response.text
    assert window_count(api_factory, d.sid) == 0
    assert state_of(api_factory, d.sid).get("obs_t_seq") is None  # nothing was registered either


@pytest.mark.parametrize("name", list(OFFENDING_KEYS))
def test_each_rejected_shape_is_an_accepted_one_plus_exactly_the_offending_key(drive, name):
    accepted_name, key, _ = OFFENDING_KEYS[name]

    def core(body, drop):
        return {k: v for k, v in body.items() if k not in (drop, "request_id")}

    assert key in REJECTED[name] and key not in ACCEPTED[accepted_name]
    assert core(REJECTED[name], key) == core(ACCEPTED[accepted_name], key)
    # ...and with the key removed the very same body is accepted.
    sent_at = EXPECTED[accepted_name][0]
    without = {k: v for k, v in REJECTED[name].items() if k != key}
    assert post(drive(), without, sent_at).status_code == 201
