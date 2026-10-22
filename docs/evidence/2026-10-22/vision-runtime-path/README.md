# Live vision: domain shift, not a pipeline bug (2026-10-22)

**Question.** On the user's laptop camera (frontal view) the live vision branch predicts almost only
`hair_makeup`, `talking_to_passenger` and `reaching_behind`, never `safe_driving`. Is the runtime
pipeline broken, or is this the viewpoint difference from State Farm (side view, passenger side)?

**1. What the live sessions recorded** (development database `backend/driver_risk.db`, read-only;
windows whose vision evidence was fresh; argmax of `visual_top_classes`):

| Session (created, UTC) | Vision-fresh windows | argmax counts | P_distraction min / median / max |
|---|---|---|---|
| 2026-10-20 05:47 `Sf95b5d9` | 2145 | hair_makeup 1796, talking_to_passenger 285, talking_phone_right 47, operating_radio 10, reaching_behind 7 | 0.881 / 1.000 / 1.000 |
| 2026-10-20 05:51 `S6f17063` | 448 | hair_makeup 390, reaching_behind 26, talking_phone_right 18, talking_to_passenger 12, operating_radio 1, talking_phone_left 1 | 0.918 / 1.000 / 1.000 |
| 2026-10-20 05:53 `Sdf2baa9` | 39 | reaching_behind 28, talking_phone_right 8, hair_makeup 2, talking_phone_left 1 | 0.982 / 0.992 / 0.996 |
| 2026-10-20 05:54 `S92fd1e8` | 1275 | hair_makeup 932, talking_to_passenger 161, reaching_behind 87, talking_phone_right 71, operating_radio 22, talking_phone_left 2 | 0.934 / 1.000 / 1.000 |
| 2026-10-22 04:21 `Sda2c4f5` | 72 | talking_to_passenger 61, hair_makeup 10, reaching_behind 1 | 0.925 / 1.000 / 1.000 |
| 2026-10-22 04:21 `S96398dc` | 9 | talking_to_passenger 9 | 1.000 / 1.000 / 1.000 |
| 2026-10-22 04:21 `S19e1f3a` | 1186 | hair_makeup 856, talking_to_passenger 187, reaching_behind 86, operating_radio 39, talking_phone_right 13, safe_driving 5 | 0.523 / 1.000 / 1.000 |

`safe_driving` was the top class 5 times in about 5,170 frames. Same picture as 2026-10-12 (394 frames, all c8).

**2. The same runtime path on in-domain images** (`runtime_path_parity.py`): every State Farm TEST image
(3,657, drivers disjoint from training) re-encoded the way the browser captures a frame (640 px wide,
JPEG quality 0.85, data URL), then `TrainedProvider.preprocess` and the frozen ONNX model, i.e. exactly what
`POST /infer` runs.

```
test images: 3657 in 79.2s
browser_like: accuracy 0.8983
original_bytes: accuracy 0.8988
predicted-class histogram (browser-like): {'safe_driving': 495, 'operating_radio': 442, 'drinking': 411, 'texting_left': 405, 'talking_phone_left': 403, 'reaching_behind': 392, 'talking_phone_right': 364, 'texting_right': 321, 'hair_makeup': 306, 'talking_to_passenger': 118}
true-class histogram: {'safe_driving': 431, 'texting_left': 407, 'operating_radio': 406, 'talking_phone_left': 395, 'drinking': 379, 'talking_phone_right': 361, 'texting_right': 350, 'reaching_behind': 337, 'talking_to_passenger': 311, 'hair_makeup': 280}
```

The offline evaluation (`docs/evidence/2026-09-28/vision-stratified-parity.json`) is 0.8988. The live path
reproduces it (0.8983 with the browser-style re-encode) and predicts all ten classes.

**Conclusion.** The runtime pipeline (capture encoding, preprocessing, model) is correct. The collapse on the
laptop camera is domain shift: the model was trained on a side view and does not transfer to a frontal one.
Nothing in this check changes code; it is evidence for the decision to demo vision with a labelled
dataset replay (user decision 2026-10-22), and a limitation to state in the report.

Command: `cd backend && PYTHONDONTWRITEBYTECODE=1 ../.venv/bin/python -I ../docs/evidence/2026-10-22/vision-runtime-path/runtime_path_parity.py`
(needs the data root `/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment-` and the frozen model files).

## 3. The decision test: do original `c0` test images come out as `safe_driving` through the live backend?

`three_paths.py`: every State Farm test image (original file bytes) through (1) direct ONNX with this script's
own preprocessing, (2) the backend's `TrainedProvider.preprocess` + ONNX session, (3) the real HTTP
`POST /infer` of a throw-away backend (free port, tmp database, `LIVE_MODEL_RUNTIME`, vision only, explicit
frame identity; every response 201 and `vision_obs = new`). Run 2026-10-22:

```
test images: 3657; HTTP statuses: {201: 3657}
[1 Direct ONNX]              accuracy 0.8988; c0 (safe_driving) recall 0.9211 on 431 images
  c0 predicted as: {'safe_driving': 397, 'talking_to_passenger': 31, 'operating_radio': 3}
[2 Runtime provider]         accuracy 0.8988; c0 (safe_driving) recall 0.9211 on 431 images
[3 Live backend HTTP /infer] accuracy 0.8988; c0 (safe_driving) recall 0.9211 on 431 images
per-class recall (identical in all three): safe_driving 0.921, texting_right 0.900, talking_phone_right 1.000,
  texting_left 0.980, talking_phone_left 0.975, operating_radio 0.990, drinking 0.989, reaching_behind 0.994,
  hair_makeup 0.832, talking_to_passenger 0.273
agreement direct vs provider: 3657 / 3657; provider vs HTTP: 3657 / 3657
```

**Reading.** The live backend recognises original `c0` images as `safe_driving` (0.921), and the three paths
agree on every single image, so neither the runtime provider nor the HTTP path loses anything. By the decision
tree, the cause is on the camera side: webcam domain shift (and the capture encoding, which section 2 shows costs
0.0005). Two model-side facts worth reporting regardless: `talking_to_passenger` recall is only 0.273 on the test
split, and it is one of the two classes the frontal camera collapses into.

**Why a frontal camera lands on `hair_makeup` / `talking_to_passenger`.** In State Farm the camera sits on the
passenger side, so a driver who looks INTO the camera is looking at the passenger (`c9`), and a hand near a face
turned toward the camera reads as `c8`. In `c0` the driver looks ahead through the windscreen, i.e. shows the
camera a profile, with the steering wheel and car interior in frame. A laptop camera in front of the user sees a
frontal face and a room, which is the `c8` / `c9` look and never the `c0` look.
