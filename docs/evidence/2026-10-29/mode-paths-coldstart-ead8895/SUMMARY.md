# ST-COLDSTART-01 - PASS

- Commit: `ead889514165d1994056525570d98abe4ed1088a`
- Scratch checkout: `/var/folders/0k/dtzqmkm53vqgg530vd7h3fmr0000gn/T//coldstart.G3aah5/repo` (removed after PASS)
- Python: `Python 3.13.9` (python3); node `v24.1.0`; npm `11.4.2`
- Models linked from: `/Users/liu/Desktop/FYP2-Live-System/ml/outputs`

| Step | Result | Exit | Seconds |
|---|---|---|---|
| clone | PASS | 0 | 0 |
| python venv | PASS | 0 | 1 |
| pip install (requirements.lock.txt) | PASS | 0 | 53 |
| pip freeze | PASS | 0 | 1 |
| npm ci | PASS | 0 | 1 |
| link models (read-only) | PASS | 0 | 0 |
| playwright chromium starts | PASS | 0 | 2 |
| gates (run_gates.py, DRA_REQUIRE_MODELS=1) | PASS | 0 | 227 |
| serve from the clean checkout | PASS | 0 | 2 |

Full output: `coldstart.log`; gate logs: `gates/`.
