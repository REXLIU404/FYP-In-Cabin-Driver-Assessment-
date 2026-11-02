# ST-COLDSTART-01 - PASS

- Commit: `fd2a8a5d231d99e6c7e29d4a69a1b76bdac7a06c`
- Scratch checkout: `/var/folders/0k/dtzqmkm53vqgg530vd7h3fmr0000gn/T//coldstart.8FeGcw/repo`
- Python: `Python 3.13.3` (/Library/Frameworks/Python.framework/Versions/3.13/bin/python3); node `v24.1.0`; npm `11.4.2`
- Models linked from: `/Users/liu/Desktop/FYP2-Live-System/ml/outputs`

| Step | Result | Exit | Seconds |
|---|---|---|---|
| clone | PASS | 0 | 0 |
| python venv | PASS | 0 | 3 |
| pip install (requirements.lock.txt) | PASS | 0 | 82 |
| pip freeze | PASS | 0 | 1 |
| npm ci | PASS | 0 | 3 |
| link models (read-only) | PASS | 0 | 0 |
| gates (run_gates.py, DRA_REQUIRE_MODELS=1) | PASS | 0 | 268 |
| serve from the clean checkout | PASS | 0 | 3 |

Full output: `coldstart.log`; gate logs: `gates/`.
