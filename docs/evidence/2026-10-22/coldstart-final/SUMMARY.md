# ST-COLDSTART-01 - PASS

- Commit: `28970004f3df9d2dcf26fce7987778b2f1df6d81`
- Scratch checkout: `/var/folders/0k/dtzqmkm53vqgg530vd7h3fmr0000gn/T//coldstart.jk58Tu/repo`
- Python: `Python 3.13.3` (/Library/Frameworks/Python.framework/Versions/3.13/bin/python3); node `v24.1.0`; npm `11.4.2`
- Models linked from: `/Users/liu/Desktop/FYP2-Live-System/ml/outputs`

| Step | Result | Exit | Seconds |
|---|---|---|---|
| clone | PASS | 0 | 0 |
| python venv | PASS | 0 | 3 |
| pip install (requirements.lock.txt) | PASS | 0 | 84 |
| pip freeze | PASS | 0 | 0 |
| npm ci | PASS | 0 | 4 |
| link models (read-only) | PASS | 0 | 0 |
| gates (run_gates.py, DRA_REQUIRE_MODELS=1) | PASS | 0 | 280 |
| serve from the clean checkout | PASS | 0 | 4 |

Full output: `coldstart.log`; gate logs: `gates/`.
