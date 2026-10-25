"""Every State Farm TEST image (original file bytes) through three paths, per-class recall:
  1. Direct ONNX   - this script's own preprocessing (PIL RGB, bilinear 224x224, /255, ImageNet mean/std)
                      and its own onnxruntime session; nothing imported from the backend.
  2. Runtime provider - backend TrainedProvider.preprocess + its ONNX session (what /infer calls).
  3. Live backend  - real HTTP: a throw-away uvicorn (free port, tmp database), LIVE_MODEL_RUNTIME session,
                      POST /infer per image (vision only, explicit frame identity), argmax of visual_top_classes.
Read-only on the dataset and models; the user's backend on :8000 and its database are not touched."""
import base64, collections, csv, datetime as dt, io, json, os, socket, subprocess, sys, tempfile, time, uuid
import numpy as np, onnxruntime as ort, httpx
from PIL import Image
BACKEND = "/Users/liu/Desktop/FYP2-Live-System/backend"
sys.path.insert(0, BACKEND)
from app.providers.trained import TrainedProvider
ROOT = "/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment-"
ONNX = "/Users/liu/Desktop/FYP2-Live-System/ml/outputs/vision/mobilenetv3_large_vision.onnx"
rows = [r for r in csv.DictReader(open(f"{ROOT}/eda_outputs/processed/vision/vision_metadata_with_split.csv")) if r["split"] == "test"]
truth = [int(r["class_id"].lstrip("c")) for r in rows]
raw = [open(r["image_path"], "rb").read() for r in rows]
urls = ["data:image/jpeg;base64," + base64.b64encode(b).decode() for b in raw]

# 1. Direct ONNX
sess = ort.InferenceSession(ONNX, providers=["CPUExecutionProvider"]); inp = sess.get_inputs()[0].name
MEAN = np.array([0.485, 0.456, 0.406], np.float32); STD = np.array([0.229, 0.224, 0.225], np.float32)
def direct(b):
    with Image.open(io.BytesIO(b)) as im:
        x = np.asarray(im.convert("RGB").resize((224, 224), Image.Resampling.BILINEAR), np.float32) / 255.0
    x = ((x - MEAN) / STD).transpose(2, 0, 1)[None]
    return int(np.argmax(sess.run(None, {inp: np.ascontiguousarray(x)})[0][0]))
pred_direct = [direct(b) for b in raw]

# 2. Runtime provider
p = TrainedProvider(); LABELS = p.labels
pred_provider = [int(np.argmax(p.vision.run(None, {p.input_name: p.preprocess(u)})[0][0])) for u in urls]

# 3. Live backend over HTTP
work = tempfile.mkdtemp(prefix="three-paths-")
with socket.socket() as s:
    s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]
env = {k: v for k, v in os.environ.items() if not k.startswith("DRA_")}
env.update(DRA_DATABASE_URL=f"sqlite:///{work}/probe.db", PYTHONDONTWRITEBYTECODE="1", PYTHONPATH=BACKEND)
log = open(f"{work}/uvicorn.log", "wb")
proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port), "--app-dir", BACKEND],
                        cwd=work, env=env, stdout=log, stderr=subprocess.STDOUT)
base = f"http://127.0.0.1:{port}"
try:
    for _ in range(120):
        try:
            if httpx.get(base + "/api/health", timeout=1).status_code == 200: break
        except httpx.HTTPError: pass
        time.sleep(0.25)
    c = httpx.Client(base_url=base, timeout=30)
    sid = c.post("/api/sessions", json={"operation_mode": "LIVE_MODEL_RUNTIME", "description": "three-path probe"}).json()["id"]
    epoch = int(time.time() * 1000); pred_http = []; statuses = collections.Counter()
    for i, u in enumerate(urls):
        now = dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")
        body = {"request_id": str(uuid.uuid4()), "image_base64": u, "captured_at": now, "captured_at_source": "callback",
                "vision_frame": {"epoch": epoch, "index": i}, "telemetry_features": None, "telemetry_timestamp": None,
                "telemetry_source": "missing"}
        r = c.post(f"/api/sessions/{sid}/infer", json=body); statuses[r.status_code] += 1
        rec = r.json(); cls = rec["visual_top_classes"]
        assert rec["provenance"]["vision_obs"] == "new", rec["provenance"]
        best = max(cls, key=lambda k: k["probability"])["label"]
        pred_http.append(LABELS.index(best))
finally:
    proc.terminate(); proc.wait(timeout=15)

def report(name, pred):
    per = {}
    for k in range(10):
        idx = [i for i, t in enumerate(truth) if t == k]
        per[LABELS[k]] = sum(pred[i] == k for i in idx) / len(idx)
    acc = float(np.mean([a == b for a, b in zip(pred, truth)]))
    c0 = collections.Counter(LABELS[pred[i]] for i, t in enumerate(truth) if t == 0)
    print(f"\n[{name}] accuracy {acc:.4f}; c0 (safe_driving) recall {per['safe_driving']:.4f} on {truth.count(0)} images")
    print("  c0 predicted as:", dict(c0.most_common()))
    print("  per-class recall:", {k: round(v, 3) for k, v in per.items()})
print(f"test images: {len(rows)}; HTTP statuses: {dict(statuses)}; session {sid}")
report("1 Direct ONNX", pred_direct)
report("2 Runtime provider", pred_provider)
report("3 Live backend HTTP /infer", pred_http)
print("\nagreement direct vs provider:", sum(a == b for a, b in zip(pred_direct, pred_provider)), "/", len(rows),
      "; provider vs HTTP:", sum(a == b for a, b in zip(pred_provider, pred_http)), "/", len(rows))
