# mobilenet_v3_large candidate — MN-HPO42

Role: RETAINED_COMPARATOR frozen by validation; seed42, search_006.

This directory copies the original P4A FP32 ONNX unchanged. Original benchmark/export records retain candidate_package=false and deployment_eligible=false; those records describe the earlier export. This P5 delivery is a candidate package, not deployment approval.

Input: RGB, direct PIL bilinear224×224, no crop, divide255, ImageNet mean [0.485,0.456,0.406] / std [0.229,0.224,0.225], NCHW float32. Graph input/output names input/logits, dynamic batch N; manifest describes one request [1,3,224,224]→[1,10]. No graph softmax.

class_to_idx is the actual c0:0 through c9:9. Training c0 label is normal_driving; runtime safe_driving is an alias. Raw outputs are logits.

Evidence: full2868 saved validation predictions,3657 clean cached test predictions with source/driver IDs, clean per-class metrics, stress stability, six-round CPU ORT runtime, frozen validation selection and source hashes. P4A100 parity is original reused evidence; stable200 is only a saved-prediction diagnostic. No new forward/held-out inference, export, benchmark or training occurred.

Manifest/schema/hash/static graph checks can pass. Current provider does not consume this manifest; provider_load_forward=NOT_RUN, official stable200 behavior=NOT_RUN, system_integration=BLOCKED_NOT_IMPLEMENTED. Future Task10A integration is outside this delivery.

Limitations: four test drivers; historical test exposure; source-domain results do not establish frontal-camera, live capture-to-render, edge, vehicle-grade or safety performance. Stress label validity is unverified and manual QC is REMOVED_FROM_SCOPE. See evaluation_metrics.json for exact existing numbers and full limitations.

Reproduction: inspect artifact_manifest.json and evidence/source_hashes.json; validate using the pinned runtime_manifest.py/schema at commit2745348 and inspect graph statically. Source snapshots/config/environment are evidence, not active dependencies. P3 training, P4A export/parity and P4B numerical execution are historical, not rerun by P5. Dirty source snapshots support traceability, not a clean-commit or bitwise guarantee.
