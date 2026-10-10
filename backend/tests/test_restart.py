"""Persisted temporal state survives a real Python worker restart, per session."""
import json
import os
from pathlib import Path
import subprocess
import sys


def test_worker_restart_preserves_independent_session_state(tmp_path):
    root = Path(__file__).resolve().parents[2]
    env = {**os.environ, "DRA_DATABASE_URL": f"sqlite:///{tmp_path / 'restart.db'}",
           "PYTHONPATH": str(root / "backend")}
    setup = """
from fastapi.testclient import TestClient
from app.main import app
with TestClient(app) as c:
    for sid, alpha in [('one', .35), ('two', 1)]:
        r = c.post('/api/sessions', json={'session_id':sid, 'config':{'ema_alpha':alpha,'freshness_tolerance_s':30}})
        assert r.status_code == 201, r.text
    def post(sid, p):
        r = c.post('/api/sessions/'+sid+'/windows', json={'P_distraction':p,'P_telemetry_anomaly':0})
        assert r.status_code == 201, r.text
        return r.json()
    assert post('one',.2)['P_distraction'] == .2
    assert post('two',.9)['P_distraction'] == .9
    assert post('one',1)['P_distraction'] == .48
"""
    subprocess.run([sys.executable, "-c", setup], env=env, cwd=root,
                   check=True, capture_output=True, text=True, timeout=30)
    resume = """
import json
from fastapi.testclient import TestClient
from app.main import app
with TestClient(app) as c:
    def post(sid, p):
        r = c.post('/api/sessions/'+sid+'/windows', json={'P_distraction':p,'P_telemetry_anomaly':0})
        assert r.status_code == 201, r.text
        return r.json()
    print(json.dumps([post('one',0),post('two',.1)]))
"""
    result = subprocess.run([sys.executable, "-c", resume], env=env, cwd=root,
                            check=True, capture_output=True, text=True, timeout=30)
    one, two = json.loads(result.stdout)
    assert (one["window_id"], one["P_distraction"]) == (3, .312)
    assert (two["window_id"], two["P_distraction"]) == (2, .1)
