"""Task 4 (constructed scenario) - the read-only scenario bundle API.

``GET /api/scenarios`` lists the generated bundles under ``settings.scenario_root`` with an
integrity verdict per bundle (schema, every listed frame present and matching its sha256),
``/api/scenarios/{id}/manifest`` serves the manifest, and
``/api/scenarios/{id}/frames/{file}`` serves ONE frame - only files the manifest lists, so
nothing else under the root (a stray manifest copy, a scenario JSON) is ever reachable.

Bundles are built by the Task 3 builder on a tiny synthetic dataset (the
``test_build_dataset_replay`` helpers); the API is pointed at them through
``settings.scenario_root``. Nothing here touches the real data root or any database.
"""
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app

from test_build_dataset_replay import Dataset, _load_builder, build


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def scenario_root(tmp_path, monkeypatch):
    root = tmp_path / "bundles"
    monkeypatch.setattr(settings, "scenario_root", root)
    return root


@pytest.fixture
def good_bundle(scenario_root, tmp_path):
    """Builds the ``tiny`` bundle (1 segment x 2 s: 10 frames, 1 telemetry row) and returns
    (bundle dir, manifest dict)."""
    builder = _load_builder()
    dataset = Dataset(tmp_path / "data")
    dataset.add_vision("p050", "c0", "test", [f"img_{i}.jpg" for i in range(12)])
    dataset.add_telemetry("Safe", count=3)
    scenario = {
        "scenario_id": "tiny",
        "seed": 7,
        "frame_period_ms": 200,
        "telemetry_period_ms": 2000,
        "segments": [
            {"title": "Baseline", "duration_s": 2, "driver_id": "p050",
             "vision_class": "c0", "telemetry_label": "Safe"},
        ],
    }
    scenario_file = tmp_path / "scenario.json"
    scenario_file.write_text(json.dumps(scenario), encoding="utf-8")
    manifest = build(builder, dataset, scenario, scenario_file, out=scenario_root)
    return scenario_root / "tiny", manifest


# ---------------------------------------------------------------------------------- the list
def test_no_root_lists_nothing(client, scenario_root):
    # scenario_root points at a directory that does not exist
    assert client.get("/api/scenarios").json() == []


def test_a_good_bundle_is_listed_ok(client, good_bundle):
    _, manifest = good_bundle
    listing = client.get("/api/scenarios").json()
    assert len(listing) == 1
    entry = listing[0]
    assert entry["id"] == "tiny"
    assert entry["segments"] == 1
    assert entry["duration_ms"] == 2000
    assert entry["generated_at"] == manifest["generated_at"]
    assert entry["status"] == "ok"
    assert entry["error"] is None


def test_a_missing_frame_makes_the_bundle_invalid_with_its_reason(client, good_bundle):
    bundle_dir, manifest = good_bundle
    victim = manifest["frames"][3]["file"]  # take the real name; the builder sorts its own way
    (bundle_dir / "frames" / victim).unlink()
    listing = client.get("/api/scenarios").json()
    assert listing[0]["status"] == "invalid"
    assert f"{victim} is missing" in listing[0]["error"]


def test_a_changed_frame_makes_the_bundle_invalid_with_its_reason(client, good_bundle):
    bundle_dir, manifest = good_bundle
    victim = manifest["frames"][3]["file"]
    (bundle_dir / "frames" / victim).write_bytes(b"tampered")
    listing = client.get("/api/scenarios").json()
    assert listing[0]["status"] == "invalid"
    assert f"{victim} does not match its sha256" in listing[0]["error"]


# ---------------------------------------------------------------------------------- the manifest
def test_the_manifest_is_served(client, good_bundle):
    _, manifest = good_bundle
    response = client.get("/api/scenarios/tiny/manifest")
    assert response.status_code == 200
    assert response.json() == manifest


def test_an_unknown_scenario_is_404(client):
    assert client.get("/api/scenarios/nope/manifest").status_code == 404
    assert client.get("/api/scenarios/nope/frames/0000_img_0.jpg").status_code == 404


# ---------------------------------------------------------------------------------- the frames
def test_a_listed_frame_is_served_as_jpeg(client, good_bundle):
    bundle_dir, manifest = good_bundle
    frame = manifest["frames"][0]
    response = client.get(f"/api/scenarios/tiny/frames/{frame['file']}")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/jpeg"
    assert response.content == (bundle_dir / "frames" / frame["file"]).read_bytes()


def test_a_file_not_in_the_manifest_is_404(client, good_bundle):
    bundle_dir, manifest = good_bundle
    # A file that really exists on disk but is not listed: the whitelist must refuse it
    # (encoded traversal is already rejected by the router, so this is the case the
    # whitelist actually guards).
    stray = bundle_dir / "frames" / "9999_stray.jpg"
    stray.write_bytes(b"jpeg-ish")
    assert client.get("/api/scenarios/tiny/frames/9999_stray.jpg").status_code == 404


@pytest.mark.parametrize("traversal", [
    "..%2Fmanifest.json",
    "%2E%2E%2Fmanifest.json",
    "..%2F..%2Fmanifest.json",
    "%2e%2e%2fmanifest.json",
])
def test_path_traversal_is_404(client, good_bundle, traversal):
    response = client.get(f"/api/scenarios/tiny/frames/{traversal}")
    assert response.status_code == 404
    assert "constructed-scenario/1" not in response.text  # never the manifest


# ---------------------------------------------------------------------------------- the marker
def test_scenario_answers_carry_the_backend_marker(client, good_bundle):
    bundle_dir, manifest = good_bundle
    frame = manifest["frames"][0]
    for url in ("/api/scenarios", "/api/scenarios/tiny/manifest",
                f"/api/scenarios/tiny/frames/{frame['file']}",
                "/api/scenarios/nope/manifest"):
        response = client.get(url)
        assert response.headers.get("x-dra-backend") == "1", url
