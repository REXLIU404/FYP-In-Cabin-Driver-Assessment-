# FYP2 Development Phase & Final Report Map — Week 7 Deadline

**状态：planned；待 Codex / Claude Code Repository Audit 后按真实证据更新。** 本文将「完整系统先行」解释为：**先完成带 transparent mock 的全部系统契约，再在 W3 接入真实 FYP1 baseline 模型**；并非 W7 才开始 AI integration。

## A. 依赖驱动的开发阶段

| Week | Priority | Development Goal | Verifiable Exit Criterion | Report Evidence |
|---|---|---|---|---|
| **W1** | P0 | Repo audit; data/model artifact inventory; API/probability schema freeze; safe tests | 审计完成，真实 model checkpoint 至少可独立运行；知道 current mock 路径与 critical blockers | Updated Ch4 design vs code，Ch5.1–5.2 |
| **W2** | P0 | Full system skeleton: React ↔ FastAPI ↔ mock adapters ↔ fusion ↔ database ↔ export; error/loading UI | 完整 replay/CRUD/demo 可运行；mock 显示明显状态，不伪装 trained inference | Ch5.4–5.6 |
| **W3** | P0 | Deploy FYP1 MobileNetV3 + XGBoost baseline adapters, real per-input inference | 实际 image+8-feature record → model outputs → RiskScore → API → Dashboard → persisted session；有 smoke log | Ch5.3–5.5 |
| **W4** | P1 | ResNet18, RF, LR comparator training + reproducible pipelines; launch bounded tuning | 五模型 train/val/test 固定、至少 baseline comparison 有实际结果，调参计划有日志 | Ch5.3 and Ch6.2 evidence |
| **W5** | P1 | Tune MobileNetV3/ResNet18/XGBoost/RF/LR on validation; freeze final models; deploy updated primary checkpoints | 记录搜索空间/次数、seed、best-validation checkpoint、模型比较；test set 未用于选择 | Ch5.3, Ch6.2 |
| **W6** | P0/P1 | Build/run E1–E5 minimum scripts; unit/integration/system+negative tests; p50/p95 logging | D0–D3/6x3/fusion/fault test 有真实可重现记录或明确 BLOCKED；CI tests 与故障记录 | Ch6 evaluation assets |
| **W7** | P0 | Feature freeze, complete demo, regression/error handling, packaging | 原型使用真实模型推理，关键功能稳定、可追溯、可演示；没有未解决 P0 | Ch5 implementation finalized + Ch6 evidence manifest |

**P0 must not wait:** source-of-truth risk_update, valid schema, threshold boundaries, freshness handling, both missing, inference adapter failure, session log integrity. 真实 DMD 外部数据申请与图像抽帧可并行但不能占用 Week 7 Critical Path。禁止为了追求更高精度而无限延长 HPO。

## B. 模型训练与调参拆解

| Branch | Main Model | Comparator(s) | Tunable Controls (examples, NOT executed configs) | Model Selection |
|---|---|---|---|---|
| Vision | MobileNetV3-Large | ResNet18 | LR, weight decay, freeze/unfreeze, augmentation, early stopping | driver-disjoint validation macro-F1 + inference latency |
| Telemetry | XGBoost | RF, LR | XGB depth/trees/lr; RF depth/trees/leaf; LR C/solver with train-only scaler | validation macro-F1 + per-class recall + latency |

所有实验明确 `run_id`, train/val/test hashes, config JSON/YAML, seed, git commit, metric artifact, checkpoint。模型比较的 **test** 必须最后一次执行；外部 DMD 无法下载或 label mapping 不合法时，报告 **NOT AVAILABLE**，不要改成 synthetic 并称 cross-dataset。

## C. Rubric 对应的 Final Report

### Chapter 4: System Analysis and Design (8 marks; update, not rewrite)

4.1 Functional & Nonfunctional Requirements (include test IDs + traceability).  
4.2 AI Branch & Fusion Design (Vision, Telemetry, freshness-weighted fusion, severity mapping, EMA/FSM).  
4.3 High-Level System Design (Frontend/Backend/AI modules, single canonical `risk_update`).  
4.4 UML/Behavioral Design (Use Case, Sequence, Data Flow).  
4.5 Interface Design (five screens; accessibility/interaction decisions).  
**Evidence:** updated architecture diagrams match actual shipped source, requirements mapped to tests. No implementation metrics here.

### Chapter 5: System Development (8 marks; substantial rewrite)

5.1 Development Environment & Tech Stack.  
5.2 Vision/Telemetry Data Preparation & Reproducibility.  
5.3 Model Development & Bounded Hyperparameter Tuning (MobileNetV3/ResNet18, XGBoost/RF/LR; configs, final selection, model export; avoid exhaustive results tables here).  
5.4 Actual Inference + Fusion + Freshness + Risk-Level + EMA/FSM Implementation.  
5.5 FastAPI/React Integration + error/loading/retry UX.  
5.6 Session persistence, export, runtime traceability.  
**Evidence:** runtime sequence, model load paths, API contracts, error UI, source code snippets where helpful, environment/version info.

### Chapter 6: Results and Discussion (8 marks for system evaluation; include ML evaluation)

6.1 Evaluation Setup and Data Provenance.  
6.2 Model Comparison and Tuning Results (primary vs comparators; final checkpoint selection; external DMD if valid).  
6.3 E1 Modality-Specific Robustness (Vision 6×3, Telemetry D0–D3).  
6.4 E2 Fusion Effectiveness (clean scenario pairs, five weight settings, no fake severity ground truth).  
6.5 E3 Fusion Robustness (missing/stale/normalization, ΔRisk distribution).  
6.6 E4 Runtime Robustness (EMA, FSM, inference/API/DB failure and recovery).  
6.7 E5 Cross-Layer Robustness (vision corrupt+clean telemetry; reverse; risk attenuation counterexamples).  
6.8 Unit/Integration/System/Performance Tests & Error Handling.  
6.9 User Acceptance Testing (actual participants/task evidence, not a fabricated study).  
6.10 Overall Discussion: what each objective supports, what **cannot** be claimed, trade-offs.  
**Evidence:** actual executed tables/charts, raw artifacts, reproducibility, test case IDs, failures and limitations. **Do not fake performance results**.

### Chapter 7: Strengths, Limitations and Future Works (3 marks conclusion)

7.1 Objective Fulfillment Table (Obj 1 fusion framework, Obj 2 severity-aware operational score, Obj 3 repeated inferencing and reliability).  
7.2 Strengths (only empirically observed).  
7.3 Limitations (unpaired modality datasets, synthetic telemetry, non-calibrated probabilities if still true, no real vehicle-grade safety claim, possible synthetic pairing).  
7.4 Future Works (real synchronized paired samples, external validation, reliability-aware/adaptive fusion, edge deployment, calibration if not performed).  
**Note:** Keep Ch1–3 mostly intact, update evaluation methodology when the actual experiment design changes; Abstract <=300 words; APA references.

## D. Rubric-driven evidence priorities

- **8/30 marks Ch4**: requirements completeness + full diagrams + UI design.
- **8/30 marks Ch5**: actual technical modules, UX quality, integration, complexity.
- **8/30 marks Ch6 system evaluation**: unit/integration/system tests, real UAT, robust error handling; model-level AI figures do not replace these software tests.
- **3/30 conclusion**: state which objectives were fulfilled, with test/evaluation IDs.
- **2 abstract + 1 references**: <=300-word abstract, APA and currency.

**Important distinctions for examiner/Viva:** D0 already synthetic; D2 overlap is label-conditioned and may invalidate labels; grayscale ≠ IR; external DMD video can be sampled as frames with careful label mapping and subject/clip grouping; missing one modality may produce mathematically correct `ΔRisk>0.15`; moving average lowers score noise but can delay alerts; “Fusion improves real-world high-risk detection” is **not demonstrated by artificial unpaired scenario comparisons**.

## E. Sign-off checklist

- [ ] Real baseline model inference path exercised end-to-end.
- [ ] Five-model comparison and bounded hyperparameter tuning documented without test leakage.
- [ ] Vision corruption 6×3 and Telemetry D0–D3 generator + raw results exist.
- [ ] E2–E5 scripts and scenario/test oracles pass methodological review.
- [ ] Unit, integration, system, negative/error handling tests actually run.
- [ ] Performance P95/1s and logging 99% criteria measured, not assumed.
- [ ] UAT execution evidenced or clearly NOT YET DONE.
- [ ] Week 7 full demo repeatable with a clean documented start.
- [ ] Ch4–7 contents aligned with actual repo evidence and rubric.
