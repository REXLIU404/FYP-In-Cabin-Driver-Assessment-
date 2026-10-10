# FYP2 Master Repository Audit Prompt — Codex / Claude Code

> **Use:** Paste the entire English prompt below into **Codex or Claude Code while the agent is opened at the actual repository root**. This is an **evidence-driven AUDIT**, not permission to implement/retrain. Run one agent at a time (or use separate branches/worktrees) to avoid competing edits. The agent should write audit documentation under `docs/fyp2/` only.
>
> **Project:** In-Cabin Multimodal Driver Monitoring & Risk Assessment (University of Malaya, AP2/FYP2). **Hard milestone:** the complete working system should be feature-complete by **Week 7**, with report writing and deeper evaluation afterwards. Do not infer which academic week it is without evidence.

--- BEGIN MASTER PROMPT ---

# ROLE AND NON-NEGOTIABLE DIRECTIVES

Act as a **senior software verification engineer, ML evaluation methodologist, system architect, and skeptical FYP2 examiner**. Your job is to **inspect the REAL repository**, determine the truth of the present implementation, critically assess test cases and evaluation design, run only safe existing checks, and generate an actionable, evidence-backed FYP2 audit package. Your objective is not to give generic recommendations or claim work is done because it is described in a report.

**Audit-only boundary:**
1. **Do not alter application/model/training code, datasets, checkpoints, configuration, schemas, or existing test definitions** during this pass. Do not train or tune models, download datasets, install large dependencies, move/delete files, push/commit, use paid cloud resources, or invent results. Creating/updating `docs/fyp2/*.md`, a machine-readable audit manifest, and small diagnostic logs in `docs/fyp2/evidence/` is allowed. If even those cannot be written, print the audit in chat and explain the blocker.
2. Read the repository before deciding whether something exists. If the project directory is unavailable, ask for the repository/path; **do not fabricate an audit**.
3. Test execution may be performed only where **safe, lightweight, local, non-destructive, bounded by a reasonable timeout**. Before running tests, check for database writes, external services, paid API use, large training, or destructive scripts. Skip and mark BLOCKED where unsafe. Tests with fixtures should use ephemeral DBs or copies; do not corrupt production/user data.
4. Distinguish all statuses exactly: `NOT_FOUND`, `PLANNED_ONLY`, `IMPLEMENTED_UNTESTED`, `TEST_PRESENT_NOT_RUN`, `TEST_PASSED`, `TEST_FAILED`, `PARTIALLY_VERIFIED`, `BLOCKED`, `NOT_APPLICABLE`. Do not confuse code presence, a screenshot, a stale report claim, and a reproduced run.
5. For **every claim**, provide `relative/path:line-range` (or precise symbol), **test ID**, executed **command + environment**, observed result and timestamp, and evidence artifact path where applicable. If line numbers are unavailable, state symbol and source path. Mark old FYP1 values `FYP1_REPORTED` until reproduced.
6. No invented accuracy, latency, robustness, UAT respondent, sample count, random seed, configuration, or pass/fail. Tests that should exist but do not must say `MISSING_TEST` in the test inventory (separate from implementation status). Never falsely claim the user has obtained DMD access or true paired multimodal risk labels.
7. The user intends **hyperparameter tuning**. Treat tuning as a development requirement, not optional; evaluate search design and implementation without starting heavy training. Probability calibration is not currently mandatory; identify it as a limitation if not executed.
8. Use evidence first, conclusions second; separate **verified facts**, **methodological concerns**, **proposed tests**, and **design decisions requiring supervisor approval**. Be constructively critical and flag when an intended conclusion is unsupported by the available ground truth.

# PROJECT REFERENCE CONTEXT (DO NOT ASSUME REPO IS CURRENT)

FYP1 report claims: a MobileNetV3-Large 10-class State Farm vision baseline with driver-disjoint test accuracy **0.8988**, macro-F1 **0.8746**; an 8-feature XGBoost synthetic telemetry baseline with test accuracy/macro-F1 **0.9993**. Both were reportedly trained, but the FYP1 running prototype still used prepared probabilities / `MockAIProvider`. There were separate React/Vite dashboard and FastAPI/SQLAlchemy/SQLite persistence prototypes, a weighted late-fusion risk engine, EMA, five-state alert FSM, session storage/export, and five dashboard views. **Check every statement against current code and artifacts.**

Expected output contracts to verify, not to assume:
- Vision: 10-way class probabilities, safe class `c0`, `P_distraction = 1 - P(c0)` (pre/post EMA identified distinctly).
- Telemetry: three-way Safe/Aggressive/Distracted, `P_telemetry_anomaly = 1 - P(Safe)`; exact feature order/units: `speed_kmph`, `accel_x`, `accel_y`, `brake_pressure`, `steering_angle`, `throttle`, `lane_deviation`, `headway_distance`.
- Fusion baseline: `R = (w_v f_v P_v + w_t f_t P_t) / (w_v f_v + w_t f_t)` where applicable; display `RiskScore = 100*R`; `fresh=1.00`, `stale=0.45`, `missing=0.00` as specified in the FYP1 report. **Verify actual code**, including zero-denominator semantics. `0.45` is a freshness factor, **NOT** the final normalized share; for equal base weights with other modality fresh, stale effective share is `0.45/1.45 ≈ 0.3103`.
- Prototype risk levels reported: Low `<30`, Medium `30–59`, High `>=60`; inspect the *actual boundary conditions at 30 and 60*, and any conflict between report and code.
- FYP1 FSM reported: sustained High for `>=2.0 s` before `HIGH_ALERT`; sustained Low for `>=10.0 s` before full recovery. Examine exact code and fake-clock tests, resets, stale evidence and session changes.
- FYP1 Table 10: vision macro-F1 `>=0.80`, telemetry macro-F1 `>=0.85`, end-to-end latency `<=1.0 s`, log completeness `>=99%`, continuity on modality loss, and `ΔRisk <=0.15` as a proposed original target. **Do NOT blindly require `ΔRisk <=0.15` across all missing-modality scenarios**: the specified re-normalization can correctly create larger changes. Report drift distribution and target-attainment rate separately from mathematical correctness, and flag need to revise or condition this criterion.
- System scope: proof of concept / monitoring-ready **not** validated accident probability prediction, driver impairment diagnosis, or a vehicle-grade safety certified system.
- Academic rubric: system analysis & design **8 marks**; system development **8 marks**; system evaluation **8 marks**, including **unit, integration, system, UAT, and error handling**; conclusion/objectives **3 marks**; references **1 mark**; abstract <=300 words **2 marks**. Verify rubric source files if present.

# TASK 0 — REPOSITORY ORIENTATION & SAFE TEST DISCOVERY

1. Print repository root, Git branch/commit/status (if Git exists), framework structure, dependency files, tests, data/model dirs (metadata only where needed). Inspect `.gitignore`, README, scripts, CI, docs, package scripts, Python env. Do not reveal secrets or dump raw private data.
2. Find all entry points, deploy commands, existing unit/integration/system/E2E tests, fixtures, testing configuration, checkpoints (`.pt`, `.pth`, `.onnx`, `.pkl`, `.joblib`, `.json` models), data manifests, experiment history, logs and previous benchmark outputs. Establish what is available versus merely referred to.
3. Build an architecture map: React/Vite -> backend API -> orchestrator -> Vision adapter + Telemetry adapter -> Fusion/Risk -> persistence/export -> dashboard. Map **actual code paths**, not desired architecture. Detect duplicated frontend/backend risk computations and identify authoritative `risk_update` source.
4. Determine whether a real input (not a canned probability record) can traverse **actual trained-model inference** through API, fusion, dashboard and durable log; prove via code + safe smoke test if possible. Specifically find whether `MockAIProvider` remains default, fallback-only, or bypassed.

# TASK 1 — WEEK-7 DEVELOPMENT READINESS AUDIT

Evaluate this milestone sequence against **current evidence**, not elapsed calendar time:
- **W1:** repo audit; data splits/checkpoints and contracts reproducible; test/evaluation inventory.
- **W2:** end-to-end mock/replay skeleton working (React <-> FastAPI <-> fusion <-> database/export); error/loading states.
- **W3:** real FYP1 **MobileNetV3-Large and XGBoost baseline** inference integrated into normal runtime and dashboard, no fake predictions misrepresented as real.
- **W4:** ResNet18, RF, LR comparators, scripts, common validation protocol; controlled tuning begun.
- **W5:** limited-budget tuning of **all five** relevant models; selection on validation only; final primary checkpoint freeze/deployment.
- **W6:** robustness generators/experiments, fusion experiments, unit+integration+system tests and reliability/latency evidence.
- **W7:** full feature-complete reproducible demo + critical bug fixes + regression testing + evidence exports, report Chapter 5 mostly supported.

For each milestone: `required deliverable | actual evidence | status | blocker | dependency | next action | acceptance test | priority P0/P1/P2 | effort S/M/L`. Prioritize **running end-to-end system first**, but baseline real inference must not be postponed beyond the mid-project milestone.

# TASK 2 — MODEL BENCHMARK + HYPERPARAMETER TUNING REVIEW

Audit **MobileNetV3-Large vs ResNet18** for vision, and **XGBoost vs Random Forest vs Logistic Regression** for telemetry. For EACH model verify: real dataset paths/provenance, immutable and non-overlapping train/validation/test splits, subject-disjoint vision tests, seeds, checkpoints, preprocessing, class order, telemetry feature order and units, leakage avoidance, training script, tuning space, search budget/strategy, selection criterion, validation metrics, held-out test metrics, inference hardware/timing, serialization, reproducibility commands and raw outputs.

Hard review checks:
- Hyperparameter tuning **must use train/validation data only**; do not repeatedly choose parameters against test scores.
- Compare models on the same frozen splits and same metrics; note changes necessary for architecture; scaled LR features must use train-only fitting.
- Vision: check `c9` confusion, image augmentation label validity (do not horizontally flip left/right actions without remapping), participant leakage, duplicate frames.
- Telemetry: confirm `phone_usage` and `reaction_time` excluded from eight deployment features; synthetic dataset nearly separable; label leakage and calibration limitations.
- Metrics: accuracy + macro-F1 + per-class precision/recall + confusion matrices; relevant ROC/PR metrics if valid; inference latency p50/p95 on declared hardware. Check target macro-F1 criteria separately from current achieved numbers.
- If tuning is missing, propose **bounded** parameter budgets and exact run artifacts. Do not invent tuning results or launch searches without approval.
- DMD video external evaluation is possible by frame extraction for **frame classifiers**, but audit license/access, RGB/video viewpoint, interval/frame labels, mapping to State Farm classes, extraction rate, video/person grouping, near-duplicate frames, fair label coverage. **No 10-class quantitative cross-dataset claim if labels do not faithfully map.** If external labels are not aligned, propose a predeclared compatible subset or qualitative analysis. Do not claim video models are necessary simply because DMD supplies video.

# TASK 3 — CRITICALLY REVIEW THE FIVE EVALUATION CATEGORIES

**Do not just tick off existence.** For each experiment, test whether the research question, source labels, input construction, baseline, test oracle, metric, acceptance criterion, statistical unit, sample design, and claimed conclusion logically agree. Explicitly identify **circular tests**, **label invalidation**, **data leakage**, **tautological improvements**, **missing ground truth**, and **unfalsifiable success criteria**. Mark each case `SOUND`, `SOUND_WITH_RESTRICTIONS`, `NEEDS_REDRAFT`, or `INVALID`, with precise fix and priority.

## E1 — Modality-Specific Model Robustness

**E1-Vision:** on a fixed held-out **driver-disjoint** State Farm test set (or a reproducible balanced subset), compare MobileNetV3 and ResNet18, same samples/seeds/corruptions, against clean images. Exactly **6 types x 3 severities**:
  1. brightness INCREASE (glare/high exposure proxy),
  2. brightness DECREASE (low-light proxy),
  3. motion blur,
  4. random occlusion blocks,
  5. small rotation plus crop / viewpoint shift proxy,
  6. RGB grayscale/color-loss transformation (**NOT actual infrared**).
Audit corruption code and parameter ranges, seed, deterministic per-sample transformations, geometric/clipping validity, sample identity, output counts and provenance. Evaluate macro-F1, per-class recall, Δmacro-F1 from paired clean baseline, prediction flip rate, processing time if recorded. If category becomes unrecognizable, flag label validity rather than mindlessly scoring. External DMD results must be **separate** from corrupted-State-Farm results.

**E1-Telemetry:** use the original held-out **~4,500-row synthetic test split** as D0 and derive paired variants from it for XGBoost, RF, LR. All train-derived stats computed on TRAIN ONLY; fixed seed; no re-use for tuning.
- **D0 Clean:** the original synthetic test records, **`is_synthetic=true`**; `is_perturbed=false`.
- **D1 Noisy:** Gaussian per-feature perturbation at **0.1, 0.3, 0.5** times train feature SD. Validate physical bounds and units; avoid silently clipping or altering semantics.
- **D2 Overlap:** bring class means toward the train-set global mean at **three documented strengths**, using **train-only class/global means**. This may use original TEST labels to select shifts; it is **label-conditioned artificial stress**, never independent natural shift. Check whether original labels remain defensible after overlap; do not blindly interpret reduced F1 as real-world error.
- **D3 Drift+Missing:** controlled feature bias drift plus masked values; train-only medians for ALL models; document severity, missing count/rate and masks, distinguish feature missing from entire-modality missing. Inspect whether missingness definition and code match.
For D0 + 3 severities for each D1/D2/D3, a fully paired design is **4,500 x (1+3+3+3) = 45,000 records total** *per generation set* (shared by three classifiers), rather than only 4 domains x 4,500 if each domain has three separate full-size severity sets. Ask to resolve any mismatch. Export reproducible CSV(s), parameter JSON, seed, `source_record_id`, label/provenance, transform name+severity, `is_synthetic`, `is_perturbed`, feature-mask metadata, hashes/versions. Assess clean-vs-corrupt degradation (macro-F1 **only if label remains valid**), flip rate, probabilities; independently audit schema rejection/imputation behaviour.

## E2 — Fusion Effectiveness on normal inputs (NOT robustness)

Check whether there is a pre-specified **scenario-paired test set** representing low/low, high-vision/low-telemetry, low-vision/high-telemetry, high/high, middle/threshold and conflicting-evidence cases. For each pair, provenance MUST identify vision example and telemetry record; label pairing must be described as **constructed evaluation scenario**, not observed co-timed real driving or accident-severity ground truth.

Audit:
- deterministic formula agreement and both raw branch probabilities,
- RiskScore and RiskLevel output,
- DominantEvidence/Partial evidence rule consistency,
- **five frozen weight pairs**: (0.5,0.5), (0.6,0.4), (0.4,0.6), (0.7,0.3), (0.3,0.7),
- RiskScore distributions, RiskLevel frequencies/transition or change rate, rank/sensitivity/threshold boundary behaviour,
- explicit scenarios where averaging attenuates a high single-modality signal.

**CRITICAL:** without real paired multimodal ground-truth severity/outcomes, DO NOT claim higher **real-world high-risk detection accuracy**, accident prevention rate, or that fusion is always better. Evaluate *correct implementation, operational consistency and scenario-level complementarity*. If an operational scenario reference label is used, pre-register the construction/policy, prevent circular definitions from the same fusion formula, and label it clearly `constructed scenario reference`, not independent ground truth.

## E3 — Fusion Robustness (fresh/stale/missing; correctness of output)

Test one missing, both missing, one stale, both stale, delayed/asynchronous updates, mixed freshness, timestamp boundary, session reset. Validate expected freshness factors `fresh=1.0`, `stale=0.45`, `missing=0.0` **if supported by actual config/code**, and re-normalized weights; `0.45` is not a final post-normalization share. Check `denominator==0` semantics: should be a clearly unavailable/degraded result; **never silently produce risk=0/Low**.

Pass criteria: no invalid fabricated inference; output continuity under one missing input; formula+flags+dominant evidence+logging correct; two missing -> unavailable state. Quantify `|R_degraded - R_full|` **on [0,1] scale** and compliance rate with the **original Table-10 target `<=0.15`**, but DO NOT treat unconditional exceedance as formula failure. Example: `P_v=.1, P_t=.9, equal weights => full=.5, vision missing => .9, Δ=.4` can be correct. Recommend a clearly conditional revised criterion for supervisor review, never silently change official FYP1 targets.

## E4 — Runtime Robustness (stability, failure handling, recovery)

EMA and FSM must be evaluated separately and together under **timestamped deterministic input streams**:
- EMA on/off: risk-score variance/total variation or flip count, response lag after an injected persistent step; avoid assuming smoother is always better.
- FSM on/off, fake or controlled wall clock: spike `duration<2 s` must **not** reach `HIGH_ALERT`; sustained High `>=2 s` must reach it subject to code cadence; sustained Low `>=10 s` returns to NORMAL; examine thresholds precisely at boundaries and resuming/restarting sessions.
- Inference failure cases: bad file/invalid JSON/NaN/out-of-range, missing weights, model load exception, 1 / N consecutive inference errors, network timeout, DB unavailable, recovery after failure. Determine `N` from actual code/config; **do not invent that three failures is implemented**. The ideal outcome is no process crash, explicit degraded/unavailable state, bounded retry/recovery and honest logging. If no configured N policy exists, mark `MISSING_REQUIREMENT/NEEDS_DECISION` and propose one for later approval.
- Log completeness `>=99%` relative to **explicitly defined expected loggable cycles/requests**; trace errors too; no silent dropping or deadlocks.
- Check unit/system/integration tests including API response + UI error state + DB persistence, not just pure math helpers.

## E5 — Cross-Layer Robustness (single-branch degradation + fusion)

Design **paired counterfactual scenarios**: (A) clean telemetry + visually corrupted images (six corruptions/three strengths, select a manageable pre-registered subset); (B) clean vision + telemetry D1/D2/D3. Compare clean versus perturbed for **vision-only**, **telemetry-only** and **fusion**, keeping the *same sample IDs, class mappings, timeline, thresholds, weights and seeds*. Check scenario sampling and temporal independence.

Evaluate:
- `ΔRiskScore` and RiskLevel retention / transitions,
- externally or **independently predeclared** `scenario-high-risk retention` if such a non-circular oracle exists,
- false negatives or recall **only** if the associated labels genuinely support those quantities,
- disagreement patterns, high-risk attenuation by equal averaging and cases fusion gets worse,
- missing/stale flag correctness and alert stability where relevant.

**CRITICAL:** no true co-timed pair = no externally validated accident/operational severity classification accuracy. A smaller absolute risk-score change can happen by arithmetic averaging even when dangerous evidence is suppressed; therefore **never use smaller score drift alone to claim improved safety**. Report counterexamples and caveats explicitly.

# TASK 4 — TEST CASE REASONABLENESS / QUALITY REVIEW (DO NOT SKIP)

Examine ALL existing and proposed test cases, not merely file names. Build a test matrix with columns:
`ID | layer | requirement/objective | input origin + split | preconditions | precise steps | expected output/oracle | metric + unit | explicit pass threshold | current status | actual observed output | evidence source | methodological verdict | missing/weak assumption | proposed correction | priority`.

For every case ask:
1. Is the expected result derived independently from the code being tested (avoid simply comparing a function with itself)? For formula tests use manually specified numeric examples + expected hand-computed values; property-based tests for invariants.
2. Is the label reliable after perturbation? Is the test measuring performance, runtime reliability, business logic, or merely demonstrating a canned scenario?
3. Is a deterministic seed, fixed split and sample provenance provided? Does training/validation/test leakage occur?
4. Are 30/60 threshold boundaries, 2.0/10.0-second boundaries and freshness `stale=0.45` explicitly tested?
5. Are time units, score scales `[0,1]` vs `[0,100]`, NaN/inf, missing payload and both-missing handled?
6. Do negative tests assert visible error state, recoverability and persistence, not just `500` errors?
7. Does every criterion have a real oracle and measurable threshold? Where no scientifically defensible numeric threshold exists, mark **exploratory/descriptive** rather than fabricate a pass/fail threshold.
8. Are failures and regressions documented? Which tests should move to unit vs integration vs system vs UAT?

Produce a **minimum additional test-case pack** of concrete proposed tests with IDs: `UT-FUS`, `UT-TIME`, `UT-MODEL`, `IT-AI`, `IT-API`, `ST-REPLAY`, `ST-FAIL`, `PERF`, `UAT`, and `E1`–`E5`. Specify reproducible inputs/fixtures and honest output oracles. Do not add hundreds of redundant cases; prioritize robust boundary tests and Week-7 feasibility.

# TASK 5 — RUBRIC TRACEABILITY + FINAL REPORT CHANGE MAP

Map evidence to the AP2 rubric:
- Chapter 4 **System Analysis and Design (8 marks)**: functional/nonfunctional requirements, AI/system architecture, UML/use case/sequence/data flow, five interface views, design-to-test traceability.
- Chapter 5 **System Development (8 marks)**: actual implemented modules, comparative model development and **tuning**, inference/service integration, React UX/accessibility/error states, API/DB/session/export, evidence of system complexity.
- Chapter 6 **Results and Discussion (8 marks system evaluation + ML contribution)**: E1 model robustness, E2 fusion effectiveness, E3 fusion robustness, E4 runtime robustness, E5 cross-layer, plus **unit, integration, system, performance and UAT** results; no fake pass counts, no confusion between model validation and software test.
- Chapter 7 **Strengths, Limitations and Future Works (3 marks conclusion/objective attainment)**: explicit objective-by-objective evidence; unpaired data, synthetic telemetry, uncalibrated probabilities, any missing real-vehicle validation as applicable; no overclaim.
- Abstract <=300 words; references APA, currency check. Chapters 1–3 mostly update only what actual implementation/evaluation requires.

Proposed Chapter 6 outline for alignment (renumber if university style requires):
`6.1 Evaluation Setup; 6.2 Model Comparison and Tuning; 6.3 Modality-Specific Robustness (E1); 6.4 Fusion Effectiveness (E2); 6.5 Fusion Robustness (E3); 6.6 Runtime Robustness (E4); 6.7 Cross-Layer Robustness (E5); 6.8 Unit/Integration/System/Performance Testing; 6.9 UAT; 6.10 Discussion`.

Check **whether each future report claim has actual underlying evidence**. Provide a matrix: `proposed statement | source experiment/test | status | citation path | acceptable wording | prohibited overclaim`.

# TASK 6 — SAFE TEST EXECUTION, EVIDENCE AND OUTPUT DOCUMENTS

Only after reviewing scripts, run quick, safe available checks (with timeouts) and record exact execution details, stdout/stderr summary, environment versions, exit code. Potential examples, only if appropriate: targeted `pytest`, `npm test -- --run`, `npm run build`, schema validation. Do not start model training, download assets or run huge 45k-row stress evaluations automatically in an audit pass. Distinguish `test is present` from `test was executed and passed` and `entire system passed`.

Create/update **these actual files** under `docs/fyp2/` (no other files unless explicitly requested):
1. `00_AUDIT_EXECUTIVE_SUMMARY.md` — dated scope, repo commit, verified critical milestones, top 10 blockers, Week 7 risk assessment, no fabricated statuses.
2. `01_MODULE_AND_ARCHITECTURE_INVENTORY.md` — runtime paths, Mock vs Actual, model artifacts, frontend/backend source-of-truth, feature/label contracts.
3. `02_TEST_CASE_INVENTORY_AND_CRITIQUE.md` — discovered tests, command evidence, full test reasonableness verdict (`SOUND`, `SOUND_WITH_RESTRICTIONS`, `NEEDS_REDRAFT`, `INVALID`), minimal missing tests with explicit oracles.
4. `03_EVALUATION_COVERAGE_MATRIX.md` — E1–E5 each subcase, experiment ownership, source data/provenance, metrics, valid acceptance criteria, presence/execution/evidence, methodological caveats.
5. `04_ML_COMPARISON_AND_TUNING_AUDIT.md` — five models, split leakage, tuning status, frozen test, artifacts, external DMD feasibility.
6. `05_RUBRIC_TRACEABILITY_AND_REPORT_MAP.md` — Chapter 4–7 mappings, evidence-backed report statements, missing prerequisites.
7. `06_WEEK7_CRITICAL_PATH_AND_ACTION_PLAN.md` — P0/P1/P2 actions ordered by dependencies, weekly gates and minimal demo acceptance tests.
8. `07_EVIDENCE_MANIFEST.md` — every real command/results artifact, run date, device/version, origin, reproducibility, missing evidence, log definition.
9. `08_OPEN_DECISIONS_FOR_SUPERVISOR.md` — unresolved criteria or data issues needing approval (e.g., unconditional `ΔRisk<=0.15`, acceptable external-data absence, scenario-label interpretation, status when both modalities missing).

Quality requirements: clear Markdown tables with no phantom links. Distinguish `CURRENT_VERIFIED` from `FYP1_REPORTED` and `PLANNED`. If a file already exists, **preserve it**, append/merge without overwriting user annotations. Summarize all new files in the final response, with actual highest-impact findings and an actionable **next 72 hours** sequence.

# FINAL RESPONSE FORMAT

Write in **Chinese**, retaining precise English technical terms. Include:
1. **Present real project stage** (specific evidence; confidence level).
2. **Actual vs Mock Inference status** and end-to-end demonstration result.
3. **E1–E5 methodological verdicts**, including unsafe or unsupported acceptance criteria.
4. **Test-case gap analysis** by Unit / Integration / System / UAT / Error Handling.
5. **Week 7 go/no-go blockers and prioritized actions**.
6. The `docs/fyp2/` document paths written. No statement of success without underlying executed evidence.

--- END MASTER PROMPT ---
