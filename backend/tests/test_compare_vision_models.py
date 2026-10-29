"""Pure-logic and stub-provider tests for scripts/compare_vision_models.py (Task 10A / DS-2).

The script is the Stage-2 paired comparison runner: one OS subprocess per vision identity,
the frozen stable200 sequence replayed through the real ``/infer`` pipeline on a synthetic
clock (100 ms per window) with a fresh temporary SQLite per child, then descriptive-only
summaries. These tests pin its pure parts (protocol gate, plan construction, input hash
recomputation, payload shape, window extraction, quantiles, sequence summaries, the
identical-results alarm) with synthetic data, plus one always-runnable integration test that
drives the REAL FastAPI pipeline with a stub provider and a patched clock (no model files
needed). The real 3-model run is evidence, not a test.

The protocol file itself (docs/fyp2/task10a/comparison_protocol.json) is tracked, so the
protocol-gate test reads it read-only; nothing here writes outside tmp_path.
"""
import csv
import hashlib
import importlib.util
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"


def load(name):
    spec = importlib.util.spec_from_file_location(f"_{name}", SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


verify = load("compare_vision_models")

T0 = "2026-10-25T00:00:00+00:00"
FEATURES = {"speed_kmph": 34.0, "accel_x": 0.3, "accel_y": 0.1, "brake_pressure": 12.0,
            "steering_angle": -2.0, "throttle": 30.0, "lane_deviation": 0.3, "headway_distance": 26.0}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def make_protocol(tmp_path, rows, *, status="APPROVED"):
    """A minimal protocol-shaped dict with ordered_samples, time basis and telemetry."""
    samples = [{"sequence_index": i, "source_id": r["source_id"], "class_id": r["class_id"],
                "filename": r["filename"], "bytes": None, "sha256": r["sha256"]}
               for i, r in enumerate(rows)]
    return {
        "status": status,
        "approval": {"status": "APPROVED", "approved_by": "user", "approval_record": "approval_record.json"},
        "input_set": {"n": len(samples), "per_class": 20, "ordered_samples": samples,
                      "data_root": str(tmp_path / "data"), "path_rule": "<data_root>/<class_id>/<filename>"},
        "time_basis": {"t0": T0, "interval_ms": 100},
        "telemetry_pairing": {"features": dict(FEATURES), "telemetry_source": "prepared_replay"},
        "fixed_configuration": {"runtime_config": {"weight_vision": 0.5, "weight_telemetry": 0.5,
                                                   "ema_alpha": 0.35, "threshold_low": 30,
                                                   "threshold_high": 60, "freshness_tolerance_s": 3},
                                "telemetry": {"model_id": "XGB-STABLE", "sha256": "b" * 64}},
        "compared_identities": [{"model_id": "m1", "env_value": "m1", "sha256": "1" * 64},
                                {"model_id": "m2", "env_value": "m2", "sha256": "2" * 64}],
    }


def make_rows(tmp_path, classes=("c0", "c0", "c1")):
    rows = []
    for i, class_id in enumerate(classes):
        filename = f"img_{i:02d}.jpg"
        raw = f"jpeg-bytes-{i}".encode()
        path = tmp_path / "data" / class_id / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        rows.append({"source_id": f"vision-v1:{class_id}/{filename}", "class_id": class_id,
                     "filename": filename, "sha256": sha256_bytes(raw)})
    return rows


# --------------------------------------------------------------------------- protocol gate
class TestProtocolGate:
    def _write(self, tmp_path, *, status="APPROVED", sha_override=None, mtime_ns=None):
        protocol_path = tmp_path / "protocol.json"
        protocol_path.write_text(json.dumps({"status": status, "approval": {"status": "APPROVED",
                                                                             "approved_by": "user"}}))
        actual = sha256_bytes(protocol_path.read_bytes())
        record = {"status": "APPROVED",
                  "approved_protocol": {"file": "comparison_protocol.json",
                                        "sha256": sha_override or actual}}
        record_path = tmp_path / "approval_record.json"
        record_path.write_text(json.dumps(record))
        if mtime_ns is not None:
            import os
            os.utime(protocol_path, ns=(mtime_ns, mtime_ns))
        return protocol_path, record_path

    def test_approved_frozen_protocol_passes(self, tmp_path):
        import time
        protocol_path, record_path = self._write(tmp_path)
        gate = verify.protocol_gate(protocol_path, record_path, run_start_epoch_ns=time.time_ns())
        assert gate["status"] == "PASS"
        assert gate["checks"]["protocol_status"] is True
        assert gate["checks"]["sha_match"] is True
        assert gate["checks"]["mtime_before_run"] is True

    def test_unapproved_protocol_is_blocked(self, tmp_path):
        import time
        protocol_path, record_path = self._write(tmp_path, status="DRAFT")
        gate = verify.protocol_gate(protocol_path, record_path, run_start_epoch_ns=time.time_ns())
        assert gate["status"] == "BLOCKED"
        assert any("status" in p for p in gate["problems"])

    def test_sha_binding_mismatch_is_blocked(self, tmp_path):
        import time
        protocol_path, record_path = self._write(tmp_path, sha_override="0" * 64)
        gate = verify.protocol_gate(protocol_path, record_path, run_start_epoch_ns=time.time_ns())
        assert gate["status"] == "BLOCKED"
        assert gate["checks"]["sha_match"] is False

    def test_protocol_mtime_not_before_run_is_blocked(self, tmp_path):
        import time
        run_start = time.time_ns()
        protocol_path, record_path = self._write(tmp_path, mtime_ns=run_start + 10_000_000_000)
        gate = verify.protocol_gate(protocol_path, record_path, run_start_epoch_ns=run_start)
        assert gate["status"] == "BLOCKED"
        assert gate["checks"]["mtime_before_run"] is False

    def test_the_real_committed_protocol_is_approved_and_sha_bound(self):
        gate = verify.protocol_gate(verify.REPO / "docs/fyp2/task10a/comparison_protocol.json",
                                    verify.REPO / "docs/fyp2/task10a/approval_record.json",
                                    run_start_epoch_ns=__import__("time").time_ns())
        assert gate["status"] == "PASS", gate["problems"]
        assert gate["protocol_sha256"] == \
            "b63050221c467ac7ed1ced0ae5e4af95ca734a7ba15fe4d7af94c948074c988f"


# ------------------------------------------------------------------------------ plan / time
class TestPlan:
    def test_iso_at_uses_integer_milliseconds(self):
        assert datetime.fromisoformat(verify.iso_at(T0, 0)) == datetime(2026, 10, 25, tzinfo=timezone.utc)
        assert datetime.fromisoformat(verify.iso_at(T0, 19900)) == \
            datetime(2026, 10, 25, tzinfo=timezone.utc) + timedelta(milliseconds=19900)

    def test_steps_carry_the_declared_identity_and_times(self, tmp_path):
        rows = make_rows(tmp_path, classes=("c0", "c0", "c1"))
        protocol = make_protocol(tmp_path, rows)
        steps = verify.build_steps(protocol)
        assert [s["request_id"] for s in steps] == ["task10a_w0001", "task10a_w0002", "task10a_w0003"]
        assert [s["vision_frame"] for s in steps] == [{"epoch": 1, "index": 1},
                                                      {"epoch": 1, "index": 2},
                                                      {"epoch": 1, "index": 3}]
        assert [s["telemetry_seq"] for s in steps] == [1, 2, 3]
        assert datetime.fromisoformat(steps[2]["t_iso"]) - datetime.fromisoformat(steps[0]["t_iso"]) == \
            timedelta(milliseconds=200)
        assert steps[0]["path"].endswith("c0/img_00.jpg")

    def test_base_plan_carries_the_fixed_telemetry_identity(self, tmp_path):
        # the child's identity check needs the approved XGB sha256; base_plan must supply it
        protocol = make_protocol(tmp_path, make_rows(tmp_path))
        plan = verify.base_plan(protocol, verify.build_steps(protocol))
        assert plan["expected_telemetry_sha256"] == "b" * 64
        assert plan["features"] == FEATURES
        assert plan["config"]["ema_alpha"] == 0.35

    def test_payload_shape_matches_the_live_input_contract(self, tmp_path):
        rows = make_rows(tmp_path)
        steps = verify.build_steps(make_protocol(tmp_path, rows))
        raw = b"original-jpeg-bytes"
        payload = verify.build_payload(steps[0], raw, FEATURES)
        assert payload["request_id"] == "task10a_w0001"
        assert payload["image_base64"] == __import__("base64").b64encode(raw).decode()
        assert payload["captured_at"] == steps[0]["t_iso"]
        assert payload["captured_at_source"] == "client_clock"
        assert payload["telemetry_timestamp"] == steps[0]["t_iso"]
        assert payload["telemetry_source"] == "prepared_replay"
        assert payload["telemetry_seq"] == 1
        assert payload["vision_frame"] == {"epoch": 1, "index": 1}
        assert payload["telemetry_features"] == FEATURES


# ------------------------------------------------------------------------- input verification
class TestInputVerification:
    def test_membership_and_source_id_hashes(self):
        rows = [{"filename": "c.jpg", "source_id": "x"}, {"filename": "a.jpg", "source_id": "z"},
                {"filename": "b.jpg", "source_id": "y"}]
        hashes = verify.compute_input_hashes(rows)
        assert hashes["membership_sha256"] == \
            "f51a71fe85231c5646ea13be59f4db05a3e4b7d0ff4ad0b1e2ff349924e77815"
        # sha256("x\\ny\\nz") - the sorted source_ids, no trailing newline
        assert hashes["source_ids_sha256"] == \
            "6d421ec4b623af3bdd47ad1d61a629eab8c11f7bf19a1e59576b5f2eede7befc"

    def test_image_manifest_rule(self, tmp_path):
        a, b = tmp_path / "a.jpg", tmp_path / "b.jpg"
        a.write_bytes(b"aaa")
        b.write_bytes(b"bbb")
        manifest = verify.compute_image_manifest([{"source_id": "s2", "path": str(b)},
                                                  {"source_id": "s1", "path": str(a)}])
        expected = sha256_bytes(("s1\t" + sha256_bytes(b"aaa") + "\ns2\t" + sha256_bytes(b"bbb")).encode())
        assert manifest["sha256"] == expected
        assert [img["source_id"] for img in manifest["images"]] == ["s1", "s2"]

    def test_image_manifest_rejects_a_missing_file(self, tmp_path):
        manifest = verify.compute_image_manifest([{"source_id": "s1", "path": str(tmp_path / "no.jpg")}])
        assert manifest["sha256"] is None
        assert manifest["problems"] and "no.jpg" in manifest["problems"][0]

    def test_features_hash_matches_the_approved_protocol(self):
        protocol = json.loads((verify.REPO / "docs/fyp2/task10a/comparison_protocol.json").read_text())
        features = protocol["telemetry_pairing"]["features"]
        assert verify.compute_features_hash(features) == \
            "0d9e4d8d116ee48f0288bbd8b714e8edeb9d5442937104119f9369b9043fd58b"
        assert verify.compute_features_hash(features) == protocol["telemetry_pairing"]["features_sha256"]

    def _workspace(self, tmp_path):
        rows = make_rows(tmp_path)
        protocol = make_protocol(tmp_path, rows)
        annotations = tmp_path / "annotations.csv"
        with annotations.open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=["source_id", "filename", "class_id"])
            writer.writeheader()
            for row in rows:
                writer.writerow({"source_id": row["source_id"], "filename": row["filename"],
                                 "class_id": row["class_id"]})
        metadata = tmp_path / "metadata.csv"
        metadata.write_text("filename,split\nimg_00.jpg,val\n")
        telemetry = tmp_path / "telemetry.csv"
        telemetry.write_text("window_id,speed_kmph\n1,34\n")
        hashes = verify.compute_input_hashes(rows)
        manifest = verify.compute_image_manifest(
            [{"source_id": r["source_id"], "path": str(tmp_path / "data" / r["class_id"] / r["filename"])}
             for r in rows])
        protocol["input_set"].update(membership_sha256=hashes["membership_sha256"],
                                     source_ids_sha256=hashes["source_ids_sha256"],
                                     image_bytes_manifest_sha256=manifest["sha256"],
                                     annotations_sha256=sha256_bytes(annotations.read_bytes()),
                                     metadata_sha256=sha256_bytes(metadata.read_bytes()))
        protocol["telemetry_pairing"].update(
            source_file_sha256=sha256_bytes(telemetry.read_bytes()),
            features_sha256=verify.compute_features_hash(FEATURES))
        return protocol, rows, annotations, metadata, telemetry

    def test_verify_protocol_inputs_passes_on_matching_files(self, tmp_path):
        protocol, rows, annotations, metadata, telemetry = self._workspace(tmp_path)
        result = verify.verify_protocol_inputs(
            protocol, data_root=protocol["input_set"]["data_root"], annotations_paths=[annotations],
            metadata_path=metadata, telemetry_csv_path=telemetry)
        assert result["ok"] is True, result["problems"]
        assert result["recomputed"]["membership_sha256"] == \
            protocol["input_set"]["membership_sha256"]
        assert result["recomputed"]["image_bytes_manifest_sha256"] == \
            protocol["input_set"]["image_bytes_manifest_sha256"]

    def test_verify_protocol_inputs_rejects_a_tampered_image_with_its_path(self, tmp_path):
        protocol, rows, annotations, metadata, telemetry = self._workspace(tmp_path)
        victim = tmp_path / "data" / rows[0]["class_id"] / rows[0]["filename"]
        victim.write_bytes(b"tampered")
        result = verify.verify_protocol_inputs(
            protocol, data_root=protocol["input_set"]["data_root"], annotations_paths=[annotations],
            metadata_path=metadata, telemetry_csv_path=telemetry)
        assert result["ok"] is False
        assert any(str(victim) in problem for problem in result["problems"])


# ------------------------------------------------------------------------ window extraction
def risk_update_response(*, window_id=1, probs=None, score=42.5, level="Medium", dominant="Combined evidence",
                         alert="NORMAL", available=True, health="FULL"):
    probs = probs or [0.4, 0.1, 0.07, 0.06, 0.05, 0.05, 0.05, 0.06, 0.08, 0.08]
    labels = ["safe_driving", "texting_right", "talking_phone_right", "texting_left", "talking_phone_left",
              "operating_radio", "drinking", "reaching_behind", "hair_and_makeup", "talking_to_passenger"]
    return {
        "session_id": "s", "window_id": window_id, "timestamp": T0,
        "assessment_available": available, "P_distraction": 0.55, "P_telemetry_anomaly": 0.3,
        "RiskScore": score, "RiskLevel": level, "DominantEvidence": dominant, "AlertSeverity": alert,
        "SystemHealth": health, "operation_mode": "LIVE_MODEL_RUNTIME",
        "modality_freshness": {"vision": "fresh", "telemetry": "fresh"}, "latency_ms": 5,
        "visual_top_classes": [{"label": label, "probability": p} for label, p in zip(labels, probs)],
        "telemetry_behavior_classes": [], "telemetry_feature_contributions": [], "telemetry_features": None,
        "explanation": "", "flagged": False,
        "provenance": {"vision_model_id": "m1", "vision_model_sha256": "1" * 64,
                       "telemetry_model_sha256": "t" * 64, "P_distraction_raw": 0.6,
                       "vision_obs": "new", "telemetry_obs": "new",
                       "vision_age_s": 0.0, "telemetry_age_s": 0.0,
                       "captured_at": T0, "telemetry_timestamp": T0},
    }


class TestExtraction:
    def test_probability_vector_maps_runtime_alias_to_c0(self):
        response = risk_update_response()
        probs, problems = verify.probability_vector(response["visual_top_classes"])
        assert problems == []
        assert list(probs) == [f"c{i}" for i in range(10)]
        assert probs["c0"] == pytest.approx(0.4)
        assert probs["c9"] == pytest.approx(0.08)

    def test_probability_vector_reports_a_wrong_c0_alias(self):
        classes = risk_update_response()["visual_top_classes"]
        classes[0]["label"] = "normal_driving"
        _, problems = verify.probability_vector(classes)
        assert any("safe_driving" in p for p in problems)

    def test_probability_vector_reports_a_wrong_count(self):
        _, problems = verify.probability_vector(risk_update_response()["visual_top_classes"][:9])
        assert any("10 class probabilities" in p for p in problems)

    def test_extract_window_keeps_the_contract_fields(self, tmp_path):
        steps = verify.build_steps(make_protocol(tmp_path, make_rows(tmp_path)))
        record = verify.extract_window(risk_update_response(window_id=1), steps[0])
        assert record["window_id"] == 1
        assert record["source_id"] == steps[0]["source_id"]
        assert record["synthetic_timestamp"] == steps[0]["t_iso"]
        assert record["RiskScore"] == 42.5
        assert record["argmax"] == 0
        assert record["P_distraction_raw"] == 0.6
        assert record["probabilities"]["c0"] == pytest.approx(0.4)
        assert record["problems"] == []

    def test_extract_window_flags_an_unavailable_assessment(self, tmp_path):
        steps = verify.build_steps(make_protocol(tmp_path, make_rows(tmp_path)))
        response = risk_update_response(available=False, score=None, level=None, dominant=None,
                                        alert=None, health="UNAVAILABLE")
        record = verify.extract_window(response, steps[0])
        assert record["assessment_available"] is False
        assert any("assessment_available" in p for p in record["problems"])


# ------------------------------------------------------------------------------ statistics
class TestStatistics:
    def test_linear_quantile_matches_numpy(self):
        np = pytest.importorskip("numpy")
        for values in ([1.0, 2.0, 3.0, 4.0], [5.0], list(range(1, 201)), [3.0, 1.0, 4.0, 1.0, 5.0]):
            for q in (0.0, 0.25, 0.5, 0.75, 0.95, 1.0):
                assert verify.linear_quantile(values, q) == pytest.approx(
                    float(np.quantile(values, q, method="linear")))

    def test_linear_quantile_of_nothing_is_none(self):
        assert verify.linear_quantile([], 0.5) is None

    def test_summarize_reports_the_declared_fields(self):
        summary = verify.summarize([10.0, 20.0, 30.0, 40.0])
        assert summary["n"] == 4
        assert summary["min"] == 10.0 and summary["max"] == 40.0
        assert summary["mean"] == 25.0
        assert summary["median"] == pytest.approx(25.0)
        assert summary["p95"] == pytest.approx(38.5)

    def test_summarize_skips_none_values(self):
        summary = verify.summarize([10.0, None, 30.0])
        assert summary["n"] == 2 and summary["min"] == 10.0 and summary["max"] == 30.0


# ------------------------------------------------------------------------------- sequences
def make_steps(tmp_path, classes=("c0", "c0", "c1", "c1")):
    return verify.build_steps(make_protocol(tmp_path, make_rows(tmp_path, classes)))


class TestSequences:
    def test_category_counts_count_none_as_null(self):
        assert verify.category_counts(["NORMAL", "CAUTION", "NORMAL", None]) == \
            {"NORMAL": 2, "CAUTION": 1, "null": 1}

    def test_transitions_carry_window_source_time_and_boundary(self, tmp_path):
        steps = make_steps(tmp_path)  # classes c0 c0 c1 c1 -> boundary at index 2
        sequence = ["NORMAL", "NORMAL", "CAUTION", "HIGH_ALERT"]
        result = verify.transitions(sequence, steps)
        assert result["initial"] == "NORMAL"
        assert len(result["transitions"]) == 2
        first, second = result["transitions"]
        # NORMAL -> CAUTION lands ON the class boundary (window 3, first c1 image)
        assert (first["window_id"], first["from"], first["to"], first["class_boundary"]) == \
            (3, "NORMAL", "CAUTION", True)
        assert first["source_id"] == steps[2]["source_id"] and first["t_iso"] == steps[2]["t_iso"]
        # CAUTION -> HIGH_ALERT is inside the c1 block
        assert (second["window_id"], second["from"], second["to"], second["class_boundary"]) == \
            (4, "CAUTION", "HIGH_ALERT", False)

    def test_class_boundaries_lists_the_first_window_of_each_block(self, tmp_path):
        steps = make_steps(tmp_path)
        assert verify.class_boundaries(steps)["window_ids"] == [1, 3]

    def test_aligned_differences_names_the_windows_that_differ(self, tmp_path):
        steps = make_steps(tmp_path)
        diffs = verify.aligned_differences(["Low", "Low", "Medium", "Medium"],
                                           ["Low", "Medium", "Medium", "High"])
        assert [d["window_id"] for d in diffs] == [2, 4]
        assert diffs[0]["a"] == "Low" and diffs[0]["b"] == "Medium"

    def test_per_window_probability_deltas_and_agreement(self, tmp_path):
        steps = make_steps(tmp_path)
        a = [verify.extract_window(risk_update_response(window_id=i + 1), step) for i, step in enumerate(steps)]
        other_probs = [0.4, 0.1, 0.07, 0.06, 0.05, 0.05, 0.05, 0.06, 0.08, 0.081]
        b = [verify.extract_window(risk_update_response(window_id=i + 1, probs=other_probs), step)
             for i, step in enumerate(steps)]
        summary = verify.per_window_prob_deltas(a, b)
        assert summary["n_compared"] == 4
        assert summary["max_abs_prob_delta"] == pytest.approx(0.001)
        assert summary["argmax_agreement"] == 1.0
        assert summary["argmax_disagreement_source_ids"] == []
        assert summary["per_window"][0]["max_abs_prob_delta"] == pytest.approx(0.001)

    def test_identical_results_detects_a_broken_runner(self):
        windows = {"m1": [{"probabilities": {"c0": 0.4}, "RiskScore": 1.0, "RiskLevel": "Low",
                           "DominantEvidence": "x", "AlertSeverity": "NORMAL", "P_distraction": 0.6}],
                   "m2": [{"probabilities": {"c0": 0.4}, "RiskScore": 1.0, "RiskLevel": "Low",
                           "DominantEvidence": "x", "AlertSeverity": "NORMAL", "P_distraction": 0.6}]}
        assert verify.identical_results(windows) is True

    def test_identical_results_is_false_when_one_probability_differs(self):
        windows = {"m1": [{"probabilities": {"c0": 0.4}, "RiskScore": 1.0, "RiskLevel": "Low",
                           "DominantEvidence": "x", "AlertSeverity": "NORMAL", "P_distraction": 0.6}],
                   "m2": [{"probabilities": {"c0": 0.4001}, "RiskScore": 1.0, "RiskLevel": "Low",
                           "DominantEvidence": "x", "AlertSeverity": "NORMAL", "P_distraction": 0.6}]}
        assert verify.identical_results(windows) is False

    def test_class_argmax_counts_uses_the_class_blocks(self, tmp_path):
        steps = make_steps(tmp_path)
        windows = [{"class_id": s["class_id"], "argmax": (0 if s["class_id"] == "c0" else 2)}
                   for s in steps]
        counts = verify.class_argmax_counts(windows)
        assert counts["c0"] == {"0": 2}
        assert counts["c1"] == {"2": 2}


# ----------------------------------------------------------- the whole child with a stub
class StubProvider:
    """Stands in for TrainedProvider in the integration test: deterministic valid windows."""

    def __init__(self, model_id, vision_sha, telemetry_sha):
        self.info = {"provider": "StubProvider",
                     "vision": {"model_id": model_id, "sha256": vision_sha, "run_id": None},
                     "telemetry": {"sha256": telemetry_sha},
                     "scope": "stub"}
        self.labels = ["safe_driving", "texting_right", "talking_phone_right", "texting_left",
                       "talking_phone_left", "operating_radio", "drinking", "reaching_behind",
                       "hair_and_makeup", "talking_to_passenger"]
        self._probs = [0.4, 0.1, 0.07, 0.06, 0.05, 0.05, 0.05, 0.06, 0.08, 0.08]

    def infer(self, data):
        from app.schemas import WindowInput
        window = WindowInput(
            P_distraction=1 - self._probs[0], P_telemetry_anomaly=0.3,
            vision_status="fresh", telemetry_status="fresh",
            visual_top_classes=[{"label": label, "probability": p}
                                for label, p in zip(self.labels, self._probs)],
            telemetry_behavior_classes=[{"label": "Safe", "probability": 0.7},
                                        {"label": "Aggressive", "probability": 0.2},
                                        {"label": "Distracted", "probability": 0.1}],
            telemetry_feature_contributions=[], telemetry_features=data.telemetry_features)
        provenance = {"provider": "StubProvider", "request_id": data.request_id,
                      "vision_source": "camera_frame", "telemetry_source": data.telemetry_source,
                      "vision_model_id": self.info["vision"]["model_id"],
                      "vision_model_sha256": self.info["vision"]["sha256"],
                      "telemetry_model_sha256": self.info["telemetry"]["sha256"],
                      "captured_at": data.captured_at, "telemetry_timestamp": data.telemetry_timestamp,
                      "P_distraction_raw": window.P_distraction, "P_telemetry_raw": 0.3,
                      "timing_ms": {"preprocess_ms": 0.1, "vision_ms": 0.1, "telemetry_ms": 0.1}}
        return window, provenance


class TestExecutePlanWithStubProvider:
    def test_five_windows_pass_through_the_real_pipeline(self, tmp_path, api_factory, monkeypatch):
        from app.providers import trained

        model_id = "stub_model"
        vision_sha, telemetry_sha = "a" * 64, "b" * 64
        monkeypatch.setattr(trained, "_provider", StubProvider(model_id, vision_sha, telemetry_sha))

        rows = make_rows(tmp_path, classes=("c0", "c0", "c0", "c1", "c1"))
        protocol = make_protocol(tmp_path, rows)
        steps = verify.build_steps(protocol)
        plan = verify.base_plan(protocol, steps)
        # execute_plan insists on the production contract: DRA_DATABASE_URL names the temp
        # SQLite inside work_dir. Under pytest the app's settings point at conftest's scratch
        # database, so the plan adopts exactly that pair (the api_factory override serves it).
        from app.config import settings
        db_file = settings.database_url.removeprefix("sqlite:///")
        assert db_file != settings.database_url
        plan.update(model_id=model_id, env_value=model_id,
                    expected_model_sha256=vision_sha,
                    session_id="task10a-cmp-stub", db_url=settings.database_url,
                    work_dir=str(Path(db_file).resolve().parent))
        result = verify.execute_plan(plan)

        assert result["status"] == "PASS", result["validity"]["problems"]
        assert result["window_count"] == 5
        assert [w["window_id"] for w in result["windows"]] == [1, 2, 3, 4, 5]
        assert [w["synthetic_timestamp"] for w in result["windows"]] == [s["t_iso"] for s in steps]
        assert result["window_ids"] == [1, 2, 3, 4, 5]
        assert len(result["windows"][0]["probabilities"]) == 10
        assert result["validity"]["checks"]["all_fresh"] is True
        assert result["validity"]["checks"]["all_age_zero"] is True
        assert result["validity"]["checks"]["all_available"] is True
        assert result["validity"]["checks"]["all_observations_new"] is True
        assert result["validity"]["checks"]["identity_ok"] is True
        assert result["validity"]["checks"]["timestamps_match"] is True
