"""Read-only comparison of browser downloads, DB, camera trace and source."""
import collections
import csv
import hashlib
import json
import sqlite3
import subprocess
from datetime import datetime
from pathlib import Path

base = Path(__file__).parent
root = Path('/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1')
sid = 'S8d4e616a597b4dd5973d31a9ad417049'
downloads = Path('/Users/liu/Downloads')
json_file = downloads / (sid+' (1).json')
csv_file = downloads / (sid+' (1).csv')
db = sqlite3.connect('file:/tmp/fyp2-browser-oct10/validation.db?mode=ro', uri=True)

def records(session_id):
    result = []
    for payload, flagged in db.execute('select payload, flagged from inference_records where session_id=? order by window_id', (session_id,)):
        row = json.loads(payload)
        row['flagged'] = bool(flagged)
        result.append(row)
    return result

saved = records(sid)
exported = json.loads(json_file.read_text())['records']
csv_rows = list(csv.DictReader(csv_file.open()))
assert len(saved) == len(exported) == len(csv_rows) == 811
assert saved == exported
numeric = ['window_id', 'P_distraction', 'P_telemetry_anomaly', 'RiskScore', 'latency_ms']
nested = ['provenance', 'modality_freshness', 'visual_top_classes', 'telemetry_behavior_classes', 'telemetry_feature_contributions', 'telemetry_features']
for expected, actual in zip(exported, csv_rows):
    for key in numeric:
        assert float(expected[key]) == float(actual[key]), key
    for key in nested:
        assert expected[key] == json.loads(actual[key]), key
    for key in ['session_id', 'timestamp', 'operation_mode', 'RiskLevel', 'DominantEvidence', 'AlertSeverity', 'SystemHealth', 'explanation']:
        assert str(expected[key]) == actual[key], key
    assert expected['flagged'] == (actual['flagged'] == 'True')
    for key in ['vision_source', 'telemetry_source', 'vision_model_sha256', 'telemetry_model_sha256', 'request_id']:
        assert expected['provenance'].get(key, '') == actual[key], key
assert next(x for x in saved if x['window_id'] == 753)['flagged']

model_paths = {'vision_model_sha256': root/'ml/outputs/vision/mobilenetv3_large_vision.onnx',
               'telemetry_model_sha256': root/'ml/outputs/telemetry/xgb_telemetry.json'}
model_hashes = {k: hashlib.sha256(p.read_bytes()).hexdigest() for k,p in model_paths.items()}
for record in saved:
    assert all(record['provenance'][key] == digest for key,digest in model_hashes.items())
    status = record['modality_freshness']
    factor = {'fresh': 1, 'stale': .45, 'missing': 0}
    cfg = record['provenance']['fusion_config']
    wv = cfg['weight_vision'] * factor[status['vision']]
    wt = cfg['weight_telemetry'] * factor[status['telemetry']]
    score = round(100*(wv*record['P_distraction']+wt*record['P_telemetry_anomaly'])/(wv+wt), 1) if wv+wt else 0
    assert record['RiskScore'] == score

diagnostic_sid = 'S05a3faf1461640c2855f6830a7282f2d'
diagnostic = records(diagnostic_sid)
trace = [json.loads(line) for line in (base/'frame_hash_trace.jsonl').read_text().splitlines()]
assert len(diagnostic) == len(trace) == 394
for record, row in zip(diagnostic, trace):
    assert record['window_id'] == row['window_id']
    assert record['provenance']['request_id'] == row['request_id']
    assert datetime.fromisoformat(record['provenance']['captured_at'].replace('Z', '+00:00')) == datetime.fromisoformat(row['captured_at'].replace('Z', '+00:00'))
    assert record['visual_top_classes'] == row['visual_probabilities']
    assert record['provenance']['P_distraction_raw'] == row['vision_raw']
assert len({r['image_sha256'] for r in trace}) == 394

before = json.loads((base.parent/'2026-10-10-browser/source-before.json').read_text())['files']
scoped = {p:v for p,v in before.items() if p.startswith(('backend/app/', 'frontend/src/', 'ai/src/', 'ml/vision/', 'ml/telemetry/'))}
changed = [p for p,v in scoped.items() if not (root/p).is_file() or hashlib.sha256((root/p).read_bytes()).hexdigest() != v['sha256']]
assert not changed, changed
camera_rows = [r for r in saved if r['provenance']['vision_source'] == 'camera_frame']
report = {'checked_utc_date':'2026-10-12', 'source_root':str(root),
          'source_head':subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD'],text=True).strip(),
          'db':'/tmp/fyp2-browser-oct10/validation.db', 'main_session':sid,
          'main_session_records':len(saved), 'camera_records':len(camera_rows),
          'camera_argmax_counts':dict(collections.Counter(max(r['visual_top_classes'],key=lambda x:x['probability'])['label'] for r in camera_rows)),
          'system_health_counts':dict(collections.Counter(r['SystemHealth'] for r in saved)),
          'json_equals_db_all_fields':True, 'csv_equals_json_all_exported_fields':True,
          'flag_753_persisted_and_exported':True, 'independent_fusion_formula_checked_records':len(saved),
          'download_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [json_file,csv_file]},
          'model_sha256':model_hashes, 'diagnostic_session':diagnostic_sid,
          'trace_equals_db_request_window_timestamp_probabilities':True,
          'diagnostic_record_count':len(diagnostic), 'diagnostic_unique_image_hashes':394,
          'unchanged_application_and_training_source_files_checked':len(scoped),
          'changed_application_and_training_source_files':changed,
          'limits':['No saved camera images or controlled ground-truth labels.', 'No formal end-to-end latency percentile, edge-device or long-duration benchmark.', 'No app code or training changes.']}
(base/'verification_manifest.json').write_text(json.dumps(report,indent=2)+'\n')
(base/'selected_window_753.json').write_text(json.dumps(next(x for x in saved if x['window_id']==753),indent=2)+'\n')
(base/'diagnostic_window_394.json').write_text(json.dumps(diagnostic[-1],indent=2)+'\n')
print(json.dumps(report,indent=2))
