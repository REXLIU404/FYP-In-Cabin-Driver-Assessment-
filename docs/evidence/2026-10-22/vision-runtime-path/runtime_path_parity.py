"""State Farm test split through the LIVE runtime path: browser-like JPEG data URL (640 wide, q=0.85)
-> backend TrainedProvider.preprocess -> the frozen ONNX model. Read-only; prints accuracy and the
predicted-class histogram, and the same for the original file bytes (no re-encode)."""
import base64, collections, csv, io, sys, time
import numpy as np
from PIL import Image
sys.path.insert(0, "/Users/liu/Desktop/FYP2-Live-System/backend")
from app.providers.trained import TrainedProvider
ROOT = "/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment-"
p = TrainedProvider()
rows = [r for r in csv.DictReader(open(f"{ROOT}/eda_outputs/processed/vision/vision_metadata_with_split.csv")) if r["split"] == "test"]
def predict(data_url):
    x = p.preprocess(data_url)
    logits = np.asarray(p.vision.run(None, {p.input_name: x})[0][0], dtype=np.float64)
    return int(np.argmax(logits))
res = {"browser_like": [], "original_bytes": []}
pred_hist = collections.Counter(); t0 = time.time()
for i, r in enumerate(rows):
    path = r["image_path"] if r["image_path"].startswith("/") else f"{ROOT}/{r['image_path']}"
    raw = open(path, "rb").read()
    with Image.open(io.BytesIO(raw)) as im:
        im = im.convert("RGB"); w, h = im.size
        im = im.resize((640, round(640 * h / w)), Image.Resampling.BILINEAR)
        buf = io.BytesIO(); im.save(buf, "JPEG", quality=85)
    browser = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
    original = "data:image/jpeg;base64," + base64.b64encode(raw).decode()
    y = int(r["class_id"].lstrip("c"))
    pb = predict(browser); po = predict(original)
    res["browser_like"].append(pb == y); res["original_bytes"].append(po == y)
    pred_hist[p.labels[pb]] += 1
print(f"test images: {len(rows)} in {time.time()-t0:.1f}s")
for k, v in res.items(): print(f"{k}: accuracy {np.mean(v):.4f}")
print("predicted-class histogram (browser-like):", dict(pred_hist.most_common()))
print("true-class histogram:", dict(collections.Counter(p.labels[int(r["class_id"].lstrip("c"))] for r in rows).most_common()))
