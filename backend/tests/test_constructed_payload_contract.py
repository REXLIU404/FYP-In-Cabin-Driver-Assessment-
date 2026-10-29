"""Task 5 (constructed scenario) - the wire contract for the replay block.

The request bodies are the literal JSON in ``fixtures/constructed_payload_shapes.json``.
That file is shared with the front end: ``ai/src/scenarioPayload.test.ts`` asserts that
``buildLivePayload`` produces exactly these shapes from its inputs (and no ``replay`` key
at all for a plain Live request). This file asserts the other half: the real
``POST /sessions/{id}/infer`` route accepts every shape in a constructed-scenario session
with a 201 (and keeps the replay block verbatim in provenance), and refuses every shape
in a Live session with a 422 ``input_validation`` - the front end must never send a
replay block into a session that is not a constructed scenario.
"""
import json
from pathlib import Path

import pytest

from test_constructed_labels import replay_session  # noqa: F401  (replay_session is a fixture)

SHAPES = json.loads(
    (Path(__file__).parent / "fixtures" / "constructed_payload_shapes.json").read_text()
)


@pytest.mark.parametrize("name", list(SHAPES))
def test_every_constructed_shape_is_accepted_and_its_replay_block_kept(replay_session, name):
    env = replay_session
    response = env.client.post(f"/api/sessions/{env.sid}/infer", json=SHAPES[name])
    assert response.status_code == 201, response.text
    assert response.json()["provenance"]["replay"] == SHAPES[name]["replay"]


@pytest.mark.parametrize("name", list(SHAPES))
def test_every_constructed_shape_is_a_422_on_a_live_session(replay_session, name):
    env = replay_session
    created = env.client.post("/api/sessions", json={
        "session_id": f"{env.sid}-live", "operation_mode": "LIVE_MODEL_RUNTIME"})
    assert created.status_code == 201, created.text
    response = env.client.post(f"/api/sessions/{env.sid}-live/infer", json=SHAPES[name])
    assert response.status_code == 422
    assert "constructed scenario session" in response.text
