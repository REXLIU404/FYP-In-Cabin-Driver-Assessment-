# Evidence Manifest and Reproduction Ledger

> 审计日期：2026-10-10（Asia/Kuala_Lumpur）；实跑检查时间见各 evidence 日志（主要为 2026-10-09）。审计对象是用户确认的桌面主仓库 `/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1`，branch `dev_cc`，HEAD `17c4b41bcfe517c8311b7f6fc2a327f616a916fe` **加未提交内容**。本文所有应用源码相对路径都相对此根目录，不相对当前旧工作树。输出工作树 HEAD `ae550415237fc1f67bf0de50c643a6d8bd6aca60`。命令 ID、环境、时间、退出码、指纹见 [07 证据索引](07_EVIDENCE_MANIFEST.md) 与 [source inventory](evidence/source_inventory.json)。

证据层次：`CURRENT_VERIFIED`=本次源码/产物检查或明确限定范围的实跑；`FYP1_REPORTED`=未在本次对应范围复现的继承指标；`PLANNED`=建议，未执行。旧实验日志标明 historical，不算本次运行。实现状态与测试执行状态分别记录；`MISSING_TEST` 是测试缺口标记，不是实现状态。未发现只适用于已扫描范围。


## Scope, integrity and status vocabulary

The supplied master/spec/map were read from desktop `FYP2_Codex_ClaudeCode_Audit_Package_v2/`; their SHA256/line counts are included in [source_inventory.json](evidence/source_inventory.json). User explicitly selected the desktop working content as audit target. The output checkout is older, detached at ae55041: **none of the desktop runtime changes were copied into its application code**. No merge/checkout/commit/push was performed. New audit artifacts are all under docs/fyp2; temporary fixtures/builds/diagnostics were confined to OS temporary directories.

Canonical statuses: `NOT_FOUND`, `PLANNED_ONLY`, `IMPLEMENTED_UNTESTED`, `TEST_PRESENT_NOT_RUN`, `TEST_PASSED`, `TEST_FAILED`, `PARTIALLY_VERIFIED`, `BLOCKED`, `NOT_APPLICABLE`. `MISSING_TEST` denotes absent tests, `MISSING_REQUIREMENT/NEEDS_DECISION` unresolved policy, and methodological verdict is a separate `SOUND / SOUND_WITH_RESTRICTIONS / NEEDS_REDRAFT / INVALID` field. `CURRENT_VERIFIED / FYP1_REPORTED / PLANNED` indicate evidence origin, not execution pass/fail. Raw metadata strings such as NOT_RUN are descriptions of skipped measurements, not additional implementation statuses.

## Environment and safe-check preparation

- Source Python interpreter: `/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/.venv/bin/python`, Python3.13.3; macOS26.6.2 arm64. Precise processor model and physical memory were not obtained because sysctl was denied. No target-edge hardware was specified or measured.
- Libraries: pytest9.0.3, FastAPI0.136.3, SQLAlchemy2.0.50, pydantic2.13.4, httpx0.28.1, numpy2.4.6, pandas3.0.3, torch2.12.0, torchvision0.27.0, ORT1.26.0, XGBoost3.2.0, Pillow12.2.0, scikit-learn1.9.0. Actual installed versions, not lower-bound requirements, recorded in source inventory.
- Node24.1.0/npm11.4.2, Vitest2.1.9, Vite6.4.2 observed in logs. Native thread limits2 for checks, provider uses2 ONNX/XGB threads; no latency claim comparing concurrent heavy jobs.
- Before running, inspected package scripts, five backend test files, four TS test files, fixtures, config/database startup, provider and benchmark scripts. No package install, model training, download, actual camera activation, external service, paid call or user DB access.
- PYTEST uses a fresh TMPDIR because `test_api.py:5–17` destructively recreates its fixed temporary DB at collection. The override makes that DB disposable. Other tests use tmp_path. `PYTHONDONTWRITEBYTECODE=1`, `-p no:cacheprovider` prevent primary repo writes. All subprocess timeouts were30–120s, with known child timeouts in existing tests.
- Frontend folders/configs copied to an isolated temporary build directory; existing node_modules symlinked read-only. Vitest `--no-cache`; standard build cache failure preserved; runner config loader safely avoided that cache write. No configuration source was changed. These copies are disposable, not deliverables.

## Executed checks

Each linked log contains exact argv/cwd, UTC start, timeout, duration, explicit environment overrides, exit code and stdout/stderr. UTC+8 gives Malaysia local time. No date was inferred from file mtime. Exact diagnostic/helper source is retained as fenced text in [audit_commands.md](evidence/audit_commands.md); machine command entries are in [checks.json](evidence/checks.json).

| ID | UTC start | Timeout / duration sec | Exit | Status / observed result | Evidence |
|---|---|---|---:|---|---|
| ENV | 2026-10-09T11:45:20.779424+00:00 | 120 / 0.02 | 1 | `BLOCKED`; OS/arm64 captured; sysctl CPU/memory permission denied; chained node versions did not execute here | [ENV](evidence/ENV.log) |
| PYTEST | 2026-10-09T11:45:20.800412+00:00 | 120 / 18.455 | 0 | `TEST_PASSED`; 28 passed, 0 skipped, 1 Starlette/httpx deprecation warning; pytest reported12.83s | [PYTEST](evidence/PYTEST.log) |
| VITEST | 2026-10-09T11:45:39.278652+00:00 | 120 / 0.79 | 0 | `TEST_PASSED`; 4 files,32 cases passed in Node test environment; not browser E2E | [VITEST](evidence/VITEST.log) |
| BUILD | 2026-10-09T11:45:40.069510+00:00 | 120 / 1.671 | 1 | `BLOCKED`; tsc stage completed; Vite .vite-temp write denied under read-only primary node_modules | [BUILD](evidence/BUILD.log) |
| LINT | 2026-10-09T11:45:41.741404+00:00 | 120 / 1.231 | 0 | `TEST_PASSED`; eslint exit0; no application changes | [LINT](evidence/LINT.log) |
| ENV-VERSIONS | 2026-10-09T11:46:52.849249+00:00 | 120 / 0.093 | 0 | `TEST_PASSED`; Node24.1.0/npm11.4.2 | [ENV-VERSIONS](evidence/ENV-VERSIONS.log) |
| BUILD-RUNNER | 2026-10-09T11:46:52.943672+00:00 | 120 / 4.154 | 0 | `TEST_PASSED`; tsc + Vite6.4.2 build passed with --configLoader runner;610.82kB JS chunk warning | [BUILD-RUNNER](evidence/BUILD-RUNNER.log) |
| ML-TELEMETRY | 2026-10-09T11:46:57.098505+00:00 | 90 / 3.348 | 0 | `TEST_PASSED`; 4500 source-test records; accuracy .9993333333, macro-F1 .9993331847; model-only timing | [ML-TELEMETRY](evidence/ML-TELEMETRY.log) |
| ML-VISION-SMOKE | 2026-10-09T11:47:00.446806+00:00 | 90 / 3.086 | 0 | `PARTIALLY_VERIFIED`; 20 test images; parity16 across8 classes; no full vision performance reproduction | [ML-VISION-SMOKE](evidence/ML-VISION-SMOKE.log) |
| DIAGNOSTICS | 2026-10-09T17:03:04.247046+00:00 | 30 / 3.555 | 0 | `PARTIALLY_VERIFIED`; 26 cases:23 oracle matches,2 requirement failures,1 formula/target distinction. Process exit0 does not mean all cases passed | [DIAGNOSTICS](evidence/DIAGNOSTICS.log) |

### Exact command index

Commands below were actually executed, not future recommendations. Use fresh output paths for benchmark scripts (they reject existing output). To repeat safely, reconstruct temporary isolation from audit_commands.md, change output names, and retain local model/data hashes. Do not blindly re-run a bare pytest command against a shared temp directory.

- `ENV`: `/bin/zsh -c 'uname -m && sw_vers && sysctl -n machdep.cpu.brand_string hw.memsize && node --version && npm --version'`; cwd `/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1`.
- `PYTEST`: `/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/.venv/bin/python -m pytest backend/tests -vv -p no:cacheprovider --basetemp /var/folders/0k/dtzqmkm53vqgg530vd7h3fmr0000gn/T/fyp2-audit-pomj5ymd/pytest`; cwd `/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1`.
- `VITEST`: `npm test -- --no-cache`; cwd `/var/folders/0k/dtzqmkm53vqgg530vd7h3fmr0000gn/T/fyp2-audit-pomj5ymd/frontend-check`.
- `BUILD`: `npm run build`; cwd `/var/folders/0k/dtzqmkm53vqgg530vd7h3fmr0000gn/T/fyp2-audit-pomj5ymd/frontend-check`.
- `LINT`: `npm run linc`; cwd `/var/folders/0k/dtzqmkm53vqgg530vd7h3fmr0000gn/T/fyp2-audit-pomj5ymd/frontend-check`.
- `ENV-VERSIONS`: `/bin/zsh -c 'node --version && npm --version'`; cwd `/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1`.
- `BUILD-RUNNER`: `npm run build -- --configLoader runner`; cwd `/var/folders/0k/dtzqmkm53vqgg530vd7h3fmr0000gn/T/fyp2-audit-pomj5ymd/frontend-check`.
- `ML-TELEMETRY`: `/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/.venv/bin/python ml/experiments/telemetry_benchmark.py --output /Users/liu/.codex/worktrees/d39a/FYP-In-Cabin-Driver-Assessment--1/docs/fyp2/evidence/telemetry_recheck.json`; cwd `/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1`.
- `ML-VISION-SMOKE`: `/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/.venv/bin/python ml/experiments/vision_benchmark.py --mode evaluate --limit 20 --parity-samples 20 --output /Users/liu/.codex/worktrees/d39a/FYP-In-Cabin-Driver-Assessment--1/docs/fyp2/evidence/vision_smoke.json`; cwd `/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1`.
- `DIAGNOSTICS`: `/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/.venv/bin/python /tmp/fyp2_audit_diagnostics.py`; cwd `/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1`.

### Read-only discovery and metadata evidence

| ID / command or source | Result and timestamp provenance | Artifact |
|---|---|---|
| ORIENTATION: pwd, git status/log/branch, rg filenames, cat/nl of specified docs and application files | Old output checkout vs newer dirty desktop repository established; full status and144 file fingerprints captured at source_inventory.captured_utc | [source_inventory.json](evidence/source_inventory.json) |
| FAST-CONTEXT: semantic runtime/test discovery attempted | tool returned “Windsurf API Key not found”; no search answer used. Fallback rg/nl reads completed; no key extraction or credential changes attempted | findings.md records failure; application paths independently inspected |
| META: `.venv/bin/python /tmp/fyp2_audit_metadata.py` | tool exit0; source_inventory.captured_utc records capture, not a fabricated exact command-start time; read-only CSV metadata, no raw rows printed | [data_artifact_audit.json](evidence/data_artifact_audit.json); helper source in audit_commands.md |
| DISCOVERY-FINAL: `python3 /tmp/fyp2_finalize_evidence.py` | exit0; start/finish UTC stored;115 metadata paths incl git-ignored model/cache candidates;144 snapshot file hashes unchanged | [repository_discovery.json](evidence/repository_discovery.json) |
| Documentation validation | required files, local links, test counts, source line bounds, vocabulary, artifact hashes, source unchanged; final result captured after document generation | [document_validation.json](evidence/document_validation.json) |

No secret environment values, private raw dataset rows or user database contents were dumped. Inventory is intentionally scoped to project source/model/docs directories; NOT_FOUND claims are restricted to that scope, not the entire computer. Native fixed checks and source-reading commands differ: a read proves code/artifact presence, not execution correctness.

## Current vs inherited result artifacts

| Artifact/source | Origin | What it proves / what it does not |
|---|---|---|
| `ml/outputs/vision/metrics.json`, class report, notebook outputs | `FYP1_REPORTED` values inspected | prior3657-test accuracy .8988/macro-F1 .8746 and c9 weakness; no current full re-evaluation |
| `docs/evidence/2026-09-28/vision-benchmark.json` | historical reproduction inspected | full source-test + CPU timing and recorded hashes; not current edge hardware or UI latency |
| `evidence/vision_smoke.json` | `CURRENT_VERIFIED` partial |20 test images,16 parity samples/8 classes; never substitute its macro-F1 for full metric |
| `evidence/telemetry_recheck.json` | `CURRENT_VERIFIED` |4500 synthetic test classification and limited forward timing; no field accuracy |
| `docs/evidence/2026-09-28/robustness-probe.json` | historical val1000 pilot |dim.35/Gaussian radius2; not held-out6×3/E1 or real IR/viewpoint validation |
| `docs/evidence/2026-09-28/linear-probe.json`, `ml/experiments/cache/` | historical partial alternate work |image MobileNet head and B0 cached artifacts; no required telemetry LR/ResNet18/RF claim; no new alternate model run |
| `docs/evidence/2026-10-05/browser-*.log` | historical browser checks |simulated camera/modes/views/exports at old run; not UAT or fresh physical-camera demonstration |
| `docs/evidence/2026-10-09/http-runtime-check.json` | historical same-day HTTP result |synthetic JPEG real model result/export equality; current audit did not reissue that live HTTP session |
| `evidence/DIAGNOSTICS.log` | current pure-function diagnostics |23 cases match declared oracle; E3-03 and zero-weight availability fail. Δ=.4 counterexample correct formula, original target not met |

The prior memory hint that runtime was Mock-only was **not used as current evidence**; live source/tests contradict it. No memory-derived accuracy or runtime status is presented as independently verified.

## Completeness and latency definitions for future experiments

**Current measured completeness: NOT_FOUND.** A defensible proposed ledger separates:

1. Eligible loggable inference requests: unique submitted request IDs after client-side validation, including explicit server outcomes; exclude deliberate frames never submitted, but report skip counts separately.
2. Prediction persistence completeness = committed unique successful requests / successful requests for which a prediction record is required. Repeated idempotent calls are one logical request; report retries separately.
3. Outcome-event completeness = requests with a persisted success or error outcome / all eligible submitted requests, including model/API/DB/network failures as determined by reconciled client/server traces. Report unresolved timeouts instead of silently dropping them.
4. Original ≥99% criterion must be bound to an approved numerator/denominator (D07). Current DB stores inference records, not a structured fault table; do not calculate “100% completeness” by dividing stored rows by themselves.

Latency proposed endpoints: capture timestamp→confirmed display/render timestamp, with clock-sync assumptions; also raw client send/receive, preprocessing, model, fusion, DB commit and render segments. Current `latency_ms` ends before commit, and configured10FPS is a target, not throughput. Alert time-to-detect contains the≥2s FSM sustain rule and is different from≤1s processing latency. Agree p95 vs max interpretation with supervisor before pass/fail.

## Missing evidence / safe non-execution

`NOT_FOUND`: required comparator checkpoints/results, all5 tuning run history, final6×3 vision/D1–D3 telemetry generators, E2/E5 scenario provenance set and independent oracle, full latency/completeness/endurance results, UAT responses/participants, original official rubric. DMD access/license/local labels `BLOCKED` for external quantitative evaluation. Full browser re-test `TEST_PRESENT_NOT_RUN` for historical/manual flows; live UI implementation `PARTIALLY_VERIFIED`. Training/tuning/downloading/new dependencies were `NOT_APPLICABLE` to execution in this audit because explicitly outside authorization; requirements remain mandatory in the later development plan.

## Requirement-by-requirement audit completion map

This checks whether the **audit** has addressed the request, not whether the system passed development gates.

| Master requirement | Authoritative audit evidence / inspected outcome |
|---|---|
| Read all3 named files; inspect actual repository first | specification hashes in source inventory; scope confirmed by user; actual paths/sources01 |
| No code/model/data/config/test changes or training | docs-only worktree status;144 primary hashes unchanged; checked commands contain no training invocation; source test definitions retained |
| Task0 root/branch/commit/status/framework/dependencies/tests/artifacts/data/CI |01 + source inventory + repository_discovery + environment/check logs |
| Task0 real paths/source-of-truth/Mock-vs-live/input through persistence |01 static chain + real model API test; frontend limitation explicit, no invented full browser success |
| Task1 everyW1–W7 deliverable/evidence/status/blocker/dependency/action/test/priority/effort |06 per-week gate matrix;00 top10 and72h sequence |
| Task2 all5 models/data/preprocessing/split/leakage/seeds/checkpoints/selection/metrics/timing/export/reproduction |04 + META/ML checks + notebook cell references; absent models explicitlyNOT_FOUND |
| Task2 tuning mandatory/train-only/validation selection/LR scaler/c9/flip validity/8features/synthetic limits |04 actual-vs-proposed finite budgets;03 label validity and same-split design |
| Task2 DMD access/viewpoint/frame mapping/grouping/license/coverage |04 and08 D08; no access or10-class claims invented |
| Task3 E1-V all6types×3; paired clean/test/sample/seeds/QC |03 seven-row table and protocol; exact pilot mismatch identified |
| Task3 E1-T D0/D1/D2/D3/statistics/masks/units/45000counts/provenance/label-conditioned concern |03 D0–D3 table;04 feature gaps;08 D04/D12 |
| Task3 E2 pair strata/provenance/5weights/formula/level/dominant/sensitivity/attenuation/ground truth |03 and proposed tests02; research claims bounded |
| Task3 E3 all missing/stale/async/boundary/reset/zero denominator/.45/Δ distribution vs target |03 + DIAGNOSTICS independent values and two failed availability cases |
| Task3 E4 EMA/FSM separately+together/time boundaries/faults/N/recovery/logging/UI+DB |02/03 exact tests and gaps;01 actual retry code;07 denominator and timing;08 D02/D07 |
| Task3 E5 paired counterfactuals/3comparators/fixed IDs/metrics/oracle/negative cases |03 E5; no drift-only safety inference |
| Task4 all existing/proposed tests examined, full schema/verdicts/oracle/circularity/gaps |02 individual60-case review, manual+legacy proposed cases, minimum pack; machine test_cases full fields |
| Task4 required minimal IDs UT-FUS/UT-TIME/UT-MODEL/IT-AI/IT-API/ST-REPLAY/ST-FAIL/PERF/UAT/E1–E5 |02 proposed pack and03 protocols; all clearlyunexecuted |
| Task5 rubricCh4–7/objectives/abstract/references/claim wording source and prohibited overclaim |05 traceability/wording matrix; official rubric/manuscript absence explicit |
| Task6 onlysafe lightweight bounded existing checks, commands/env/output/exit/date/evidence |this ledger/checks.json/logs; malformed/unsafe paths skipped or isolated; no heavy stress run |
| Nine named documents + machine manifest + preserve existing annotations |00–08 present; originally no docs/fyp2 files; plan notes appended; final validator covers required names |
| Chinese final response: actual stage/confidence, actual-vs-Mock, E1–E5 verdicts, software gaps,W7/actions/paths | final handoff must match00–08; no project-complete claim |

[Machine audit manifest](audit_manifest.json) also retains the full per-test schema, all commands, diagnostic case results and artifact hashes. This manifest intentionally does not hash itself, avoiding a circular digest.
