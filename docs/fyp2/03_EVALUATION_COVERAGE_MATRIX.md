# E1–E5 Evaluation Coverage and Validity Matrix

> 审计日期：2026-10-10（Asia/Kuala_Lumpur）；实跑检查时间见各 evidence 日志（主要为 2026-10-09）。审计对象是用户确认的桌面主仓库 `/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1`，branch `dev_cc`，HEAD `17c4b41bcfe517c8311b7f6fc2a327f616a916fe` **加未提交内容**。本文所有应用源码相对路径都相对此根目录，不相对当前旧工作树。输出工作树 HEAD `ae550415237fc1f67bf0de50c643a6d8bd6aca60`。命令 ID、环境、时间、退出码、指纹见 [07 证据索引](07_EVIDENCE_MANIFEST.md) 与 [source inventory](evidence/source_inventory.json)。

证据层次：`CURRENT_VERIFIED`=本次源码/产物检查或明确限定范围的实跑；`FYP1_REPORTED`=未在本次对应范围复现的继承指标；`PLANNED`=建议，未执行。旧实验日志标明 historical，不算本次运行。实现状态与测试执行状态分别记录；`MISSING_TEST` 是测试缺口标记，不是实现状态。未发现只适用于已扫描范围。


## Governing design and ownership

The v2 `FYP2_EVALUATION_AND_TESTCASE_SPEC.md` governs category names. The older `docs/PROJECT_ASSESSMENT_AND_TEST_PLAN.zh.md:108–115` uses E1=architecture, E2=frontal adaptation, E3=ROI, E4=temporal processing, E5=quantization. Those are **not** evidence of v2 E1–E5 completion. Preserve historical documents; add an explicit naming/version crosswalk in the report.

Owners below are proposed roles (not assigned people): ML-V vision; ML-T telemetry; SYS fusion/runtime; QA software/browser; REPORT methodology/provenance. All future runs are `PLANNED`; no stress dataset or experimental result was generated in this audit. Execution facts come from PYTEST/VITEST/DIAGNOSTICS/ML checks. Mathematical diagnostics do not constitute population robustness experiments.

## E1-V — fixed held-out paired vision corruption

Question: under matched corrupted samples, how do the two classifiers degrade? Statistical unit: paired image for descriptive changes, driver/clip cluster for inference, not independently sampled adjacent frames. Use all3657 test frames or a **predeclared proposed** stratified1000–1500 subset with IDs; train and validation images cannot substitute for final held-out robustness. Four test drivers constrain generalization. Use shared seed42 and per-ID deterministic corruption for both models. Include clean baseline for exactly the same selected samples.

| Subcase | Proposed strengths, oracle and provenance | Existing implementation / execution | Verdict, acceptance and correction | Owner / priority |
|---|---|---|---|---|
| E1-V0 clean | Correct class from frozen State Farm metadata; common class order | MobileNet benchmark present; current20-image smoke; full historical metrics. ResNet18 `NOT_FOUND` | `SOUND_WITH_RESTRICTIONS`; full paired sample/driver design required | ML-V/P1 |
| E1-V1 exposure increase | ×1.2/1.5/1.8; pixel clipping/recognizability QC | exact generator/results `PLANNED_ONLY`, `MISSING_TEST` | `SOUND_WITH_RESTRICTIONS`; glare proxy only | ML-V/P1 |
| E1-V2 exposure decrease | ×.8/.5/.3 | pilot .35 on validation1000 exists (`robustness_probe.py:22–40`); exact3 severities/test setup missing; pilot not rerun | `NEEDS_REDRAFT` for v2 coverage; do not relabel old .35 as .3 | ML-V/P1 |
| E1-V3 motion blur | kernel3/7/11, seeded direction | pilot Gaussian radius2 exists (`:40–41`); **not motion blur**, no3-level output | `NEEDS_REDRAFT`; implement/record true motion kernel and direction | ML-V/P1 |
| E1-V4 occlusion | approximate image area5/10/20%, position derived from sample ID+seed | `PLANNED_ONLY`; `MISSING_TEST` | `SOUND_WITH_RESTRICTIONS`; loss of essential hand/phone cues can invalidate labels | ML-V/P1 |
| E1-V5 rotation+crop | ±3°/±7°/±12°, explicit crop geometry/seed | `PLANNED_ONLY`; training RandomRotation8° is not evaluation evidence | `SOUND_WITH_RESTRICTIONS`; viewpoint proxy, no left/right relabeling accident | ML-V/P1 |
| E1-V6 grayscale blend | 30/60/100% | `PLANNED_ONLY`; `MISSING_TEST` | `SOUND_WITH_RESTRICTIONS`; RGB color loss **not IR/NIR validation** | ML-V/P1 |

Metrics: accuracy, macro-F1, class precision/recall/confusion, paired Δmacro-F1, flip rate; process time if actually recorded. Pass criteria concern reproducibility, identical sample IDs and honest label QC. **Model ranking and degradation are EXPLORATORY**, no preordained “must improve.” Report recognizability exclusions and retain affected cases as stress/flip results rather than silently dropping difficult cases. Save per-sample `sample_id,label,model,corruption,severity,predicted_label,probs,seed,transform_params`, hashes and generator version. Count design: N×(1+18) inputs, shared across two models; two sets of predictions, not duplicate source sampling.

## E1-T — synthetic telemetry stress

Question: effect of noise/overlap/drift/missing features on each of XGB/RF/LR. Unit: source_record_id paired across all variants; effective independent generator groups unknown. Current split has4500 rows with no stable source ID: derive versioned IDs before generation, never generate new test sets per model. Use same train-only median imputer for **all three** stress comparisons, including XGB, and preserve clean raw baseline separately.

| Subcase | Parameter/source/oracle | Presence & execution | Verdict / valid acceptance | Owner |
|---|---|---|---|---|
| D0 | Original held-out4500; `is_synthetic=true,is_perturbed=false` | Current XGB `TEST_PASSED` full test, RF/LR `NOT_FOUND`; source hash in ML-TELEMETRY | `SOUND_WITH_RESTRICTIONS`; synthetic performance only; inherited macro-F1≥.85 target can be assessed here | ML-T |
| D1 s1/s2/s3 | Gaussian noise σ=.1/.3/.5×train SD, same source IDs; explicit units and physical validity policy | `PLANNED_ONLY`; generator/parameter manifest `MISSING_TEST` | `SOUND_WITH_RESTRICTIONS`; do not silently clip; original labels require defensibility check | ML-T |
| D2 s1/s2/s3 | x'=x+λ(μ_train_global−μ_train_class_y), proposed λ=.25/.50/.75 | `PLANNED_ONLY`; no train-stat artifact/generator | `SOUND_WITH_RESTRICTIONS`; using test y to choose shift makes **label-conditioned artificial stress**. Claim of independent natural shift is `INVALID` | ML-T/REPORT |
| D3 s1/s2/s3 | proposed fixed-direction bias .25/.5/1×train SD; predeclare cell missing rates e.g.5/10/20% as a **decision**, not existing behavior | `PLANNED_ONLY`; no masks/generator. Current API rejects missing feature keys (`schemas.py:43–52`) | `SOUND_WITH_RESTRICTIONS`; feature-level missing/imputation differs from whole branch missing; schema rejection is a separate software test | ML-T/QA |

The specification is internally consistent on **4500×(1+3+3+3)=45000 records** including D0, one shared generation set for three classifiers. A four-domain18000-row design would be a changed design, not equivalent coverage; supervisor must approve that reduction. No such generated record count is claimed here.

Save source ID, original label, domain/severity, synthetic/perturbed flags, mask, actual perturbation and clipping counts, train-only statistics, seed, bounds policy, source/train split hashes and generator version. Metrics: macro-F1 only where labels remain valid, otherwise flip rate/probability/distribution change. Do not fit scaler/median/stats using test, and do not tune with these held-out corruptions. D2 F1 drop cannot by itself establish real-world generalization failure.

## E2 — normal-input fusion effectiveness, not robustness

| Subcase | Dataset/oracle and measurement | Current evidence/status | Verdict / fix |
|---|---|---|---|
| Low/low | proposed(.1,.1), equal fresh weights → score10/Low; predeclared hand calculation | pure formula implementation/tests; no sample-pair set | `SOUND` as unit oracle; `PLANNED_ONLY` dataset experiment |
| High V/low T | proposed(.9,.1), equal →50/Medium, vision dominant | code formula and evidence tests; no actual input IDs pairing | `SOUND_WITH_RESTRICTIONS`; explicitly show attenuated high V |
| Low V/high T | proposed(.1,.9) →50/Medium, telemetry dominant | DIAGNOSTICS clean formula, no full scenario experiment | same restriction; no safety superiority claim |
| High/high | proposed(.9,.9)→90/High; FSM initially CAUTION | first-high test passed (`test_audit_regressions.py:127–139`) | distinguish RiskLevel from sustained AlertSeverity |
| Mid/threshold | fixed probabilities whose fused score is29.9/30/59.9/60; rounding also tested separately | TS exact level tests + Python DIAGNOSTICS passed | `SOUND`; near-boundary integration and rounding parity still missing |
| Conflicting evidence | preserve source sample IDs, independent policy and both raw outputs | no scenario generator/independent severity oracle found | `SOUND_WITH_RESTRICTIONS`; detect dilution and disagreement |
| Five weights | (.5,.5),(.6,.4),(.4,.6),(.7,.3),(.3,.7), frozen across same pairs | config supports weights, full sweep/raw outputs `NOT_FOUND` | `PLANNED_ONLY`; no data-selected “best” test weight |

Owner SYS+ML-V+ML-T, P1. Proposed manageable design: 10 **constructed** source pairs per six stratum=60 pairs×5 weights=300 scalar outcomes per fixed model pair, count declared as plan only. Track `vision_sample_id,telemetry_record_id,labels,pairing_policy,replay_order/timestamp,raw probabilities,weights,expected_behavior`. If reuse reduces unique inputs, report actual unique image/record/driver counts and paired dependence.

Metrics: formula error (score units), score distribution, level frequencies/transition rate, rank/weight/threshold sensitivity, DominantEvidence/Partial consistency. Numeric formula expectations must be independent hand calculations, not a second call to the same fusion function. A policy-defined reference may be called **constructed scenario reference** only if predeclared independently of the formula. Real-world high-risk detection accuracy/accident prevention inference is `INVALID` without appropriate paired outcome ground truth.

## E3 — freshness/missing fusion output correctness

| ID | Current result / evidence | Required oracle & status | Verdict / outstanding work |
|---|---|---|---|
| E3-01 V missing | .1/.9→90, DIAGNOSTICS | correct single-T normalization `TEST_PASSED` in diagnostic; flags/logging need integrated assertion | `SOUND` |
| E3-02 T missing | .1/.9→10, DIAGNOSTICS; API .8/—→80 in CRUD | formula `TEST_PASSED`; single branch continuity partially verified | `SOUND` |
| E3-03 both missing | 0/Low/NORMAL, UNAVAILABLE; diagnostic requirement `TEST_FAILED` | unavailable result without normal numeric risk semantics across API/UI/export | current zero-risk test is `INVALID` as v2 acceptance; UI mitigation does not repair export |
| E3-04 V stale | expected(.45×.1+.9)/1.45×100=65.2 | `TEST_PASSED` small diagnostic | `SOUND`; effective stale share .45/1.45≈.3103, not .45 |
| E3-05 T stale | expected(.1+.45×.9)/1.45×100=34.8 | `TEST_PASSED` small diagnostic | `SOUND`; assert flags and persistence later |
| E3-06 both stale/boundary | both stale score50; age2.999/3 fresh,3.001 stale, DIAGNOSTICS | exact code `TEST_PASSED`; no upper stale-age expiry | `SOUND_WITH_RESTRICTIONS`; stale-only warning/escalation/expiry needs decision |
| E3-07 async/reset | old live timestamp409, separate sessions/restart tested; gap resets state | `PARTIALLY_VERIFIED`; delayed alternating stream/per-branch exact boundaries and session switching UI missing | `SOUND_WITH_RESTRICTIONS` |
| E3-08 zero effective weights | (1,0), V missing/T fresh→0/Low/DEGRADED | `TEST_FAILED` independent no-evidence oracle | health must follow effective denominator; B02 P0 |

Owner SYS+QA. Existing `.45` is verified, not assumed. Proposed experiment: same fixed scenario pairs and all9 freshness combinations plus async cases; keep model outputs/timeline/weights fixed. Quantify absolute ΔR on[0,1], distribution and count(rate)≤.15. `.1/.9` full.5→V missing.9 givesΔ.4: formula PASS, continuity PASS, original target NOT MET for this case. **Unconditional Δ≤.15 as correctness is NEEDS_REDRAFT.** Suggested conditional reporting by branch disagreement and retained evidence, supervisor approval needed; do not silently remove original Table10 target.

## E4 — runtime reliability and temporal behavior

| Subcase | Evidence / current status | Valid oracle, metrics and missing scope |
|---|---|---|
| EMA on/off | API .2→1 gives.48 with α=.35 (`test_second_window_uses_vision_ema`); full ablation `PLANNED_ONLY` | replay deterministic timestamped raw probability stream; α=1 versus.35; total variation/variance/flip **and** persistent-step response lag; smoother is not automatically better |
| FSM on/off | 2s/10s exact boundaries and gap reset pass backend tests/DIAGNOSTICS; TS sustained window tests pass | proposed compare instantaneous level mapping with FSM under identical injected1.9/2.1s high,9.9/10.1s low, interrupted streaks, session reset; include exact2/10 and cadence. No real-time sleeps |
| Bad image/JSON/probability | invalid base64422/no result; probability>1/negative latency/bad timestamp reject tests pass | `PARTIALLY_VERIFIED`; NaN/Inf/body shape/size/corrupt-but-decodable image/feature unit validation + UI + logs incomplete |
| Load failures | missing artifacts and four import-dependency cases503 pass | no fake fallback verified; model **runtime** exceptions and single-branch availability policy not covered |
| Consecutive N faults/recovery | source implements immediate stop on404/409/422/503; other errors unbounded count with bounded delay | `MISSING_REQUIREMENT/NEEDS_DECISION` for max N; no invented3-failure implementation. Count N only after policy defined |
| Network/DB failure | request timeout/backoff source present; database rollback source present | `IMPLEMENTED_UNTESTED` recovery scope; missing cross-layer failure injectors; assert error visible, latest explicitly historical, recovery without duplicate writes |
| Log completeness | records persisted for accepted calls; rejected errors not in inference_records; no fault table | numerator/denominator undefined for requested≥99% criterion → `NEEDS_REDRAFT` protocol. Define eligible cycles, committed unique requests, rejected/fault outcomes, intentional frame skips separately |

Owner SYS/QA, P0 faults, P1 experiments. Proposed clocked streams use a fixed origin, cadence≤1s during2s/10s guards, deterministic steps and gap cases. Statistical unit stream/session; do not treat correlated ticks as independent events. Failure-free unit assertions do not prove crash-free endurance. FSM exports3 states, five-state historical design needs reconciliation. Existing replay “5 samples at2s≥10s” assertion spans8s between first/last and does not run FSM; `NEEDS_REDRAFT`.

## E5 — cross-layer paired counterfactuals

| Path | Fixed construction | Current presence | Sound acceptance / prohibited inference |
|---|---|---|---|
| E5-A V corrupted + T clean | same source pairs, proposed predeclared2 pairs/stratum and all6×3 vision transforms for manageable smoke; keep T record/weights/time fixed | generator/raw output `PLANNED_ONLY`; `MISSING_TEST` | V-only/T-only/fusion clean-vs-corrupt score and level retention; include high-V attenuation counterexamples |
| E5-B V clean + T stressed | same paired V IDs, D1/D2/D3 at3 strengths from same T source IDs, no fresh resampling | `PLANNED_ONLY`; `MISSING_TEST` | same comparators; D2 invalid-label exclusions/report-only must propagate to scenario interpretation |

Owner SYS+ML-V+ML-T+REPORT, P1; overall `SOUND_WITH_RESTRICTIONS`. The proposed smoke subset is not a powered study; pre-register larger confirmatory sample design before claiming generality. Save each counterfactual and unique IDs/seed/label mapping/timeline/threshold/weights. Metrics: ΔRiskScore points, level transitions/retention, independently predeclared scenario-high-risk retention only with valid oracle. Recall/false negatives need valid relevant labels. Smaller fusion drift alone is arithmetically expected and **INVALID evidence of safer accident prediction**. If fusion is worse, report it unchanged.

## Separate mandatory evaluations

M1 five-model comparison/HPO: [04](04_ML_COMPARISON_AND_TUNING_AUDIT.md), incomplete. M2 DMD: access/mapping `BLOCKED`, separate from E1 corruptions. S1 software testing: [02](02_TEST_CASE_INVENTORY_AND_CRITIQUE.md); UAT not replaced by E1–E5. FYP1 targets vision F1≥.80, telemetry≥.85 are model criteria;≤1s and≥99% need separately scoped system measures. No category's existence is marked completed merely because the specification describes it.

### Stale-evidence temporal policy caveat

Static finding (`backend/app/inference.py:43–55`): only `UNAVAILABLE` bypasses normal severity progression. A repeated high score with stale evidence can still accumulate the 2-second High guard; age alone never turns stale into missing (`:13–18`). This audit has not executed a stale-only alert stream. This is `IMPLEMENTED_UNTESTED` behavior with a `MISSING_REQUIREMENT/NEEDS_DECISION` policy, not evidence that such escalation is correct. Add an independently clocked stale-only sequence and decide expiry/repetition handling before claiming temporal robustness.

---

## 增补：外部建议（ChatGPT）复核与采纳裁定（2026-10-22）

> **以上正文是 2026-10-10 审计快照，结论原样保留、不因本节而改**；其他文档对正文行号的引用保持有效。本节记录 2026-10-22 对一份外部建议（ChatGPT 针对 E1–E5 的五点修订提议）的复核结果，以及据此落入后续评估计划的增量决定。这些变更作用于 E1–E5 实验设计（仍为 `PLANNED`），不是对审计结论的否定。

### 裁定总表

| 建议 | 复核结论 | 处理 |
|---|---|---|
| E1 保留 + 概率可靠性作为独立诊断 | 合理，但只能作为**可选诊断**，不能作为通过门槛——06 已把概率校准定为 limitation、非强制里程碑 | 采纳（新增 E1 概率可靠性诊断约束，见下） |
| E2 五权重、30/60 分级照旧，只验公式/稀释/Dominant，不作风险准确性声明 | 与正文 E2 完全一致：五权重、29.9/30/59.9/60 边界、`explicitly show attenuated high V`、`no data-selected “best” test weight`、`INVALID` 声明均已含 | 无新增，正文原样 |
| E3 重写 ΔRisk≤0.15 通过标准 | 正文已先行修订：E3 段末已标 `NEEDS_REDRAFT`，`.1/.9` full→V missing 的 Δ=.4 反例与 D05「保留原目标、分别报告达成率」都在；ChatGPT 建议方向与之一致。但其 stale 建议未计入后来的 **D13 裁定 A** | 采纳，并按裁定 A 修正 stale 部分（见下） |
| E4 保留并加强边界；latency 明确统计范围 | 与正文及 D07 一致：EMA 的 variance/flip **与** response lag、FSM 2s/10s 受控时钟、stale-only 待决 caveat 均已含；latency 范围目前只写在 D07，E4 无显式条目 | 采纳（E4 增加 latency 范围交叉引用，见下） |
| E5 增加报告维度，不能只凭曲线更平稳 | 与正文 E5 一致：score/level retention、high-V attenuation 反例、`INVALID evidence of safer accident prediction` 均已含；其提议中的 **Missing-Input Behavior 属 E3 范围**，不并入 E5 | 无新增；范围澄清见下 |

### 落地变更

**E1 — 概率可靠性（新增可选诊断）**：在保留正文 E1-V / E1-T 全部指标的前提下，额外记录**仅诊断用途**的概率可靠性指标：NLL、Brier Score、Reliability Diagram / ECE。约束：

- 不作为任何 acceptance criterion，报告为 limitation 证据；
- 与正文标签有效性 QC 同一规则：D2/D3 等使标签失效的样本不得进入 NLL/Brier/ECE，只允许 flip rate / 分布变化；
- 校准评估数据与训练数据隔离（同正文 train-only statistics 纪律）；不要求现在做 Temperature Scaling；
- 与计划 Task 10A 的模型替换复检（ECE、Brier、RiskScore 分布，同一组固定成对输入）口径一致。

**E3 — stale 行按 D13 裁定 A 更新**：裁定 A（2026-10-13 批准、10-15 落地，见 `docs/fyp2/implementation/p0-d13-ruling-a.md`）后，运行时不再产出 `stale`：超过 `freshness_tolerance_s` 的证据判 expired，**按 missing 计分（权重 0）**，原因保留在 provenance（`{modality}_expired` / `{modality}_age_s`）。因此：

- E3-04/05/06 的 `.45` 公式**仅保留为历史记录读取/渲染的 legacy 兼容校验**，不再是运行时可达的模型输入；
- 「9 种 freshness 组合」实验的维度改为 fresh / missing / expired，expired 的期望分数与 missing 相同（权重 0），同时断言 provenance 原因字段；
- ChatGPT 建议中「Stale Data → 按约定 freshness 权重计算，并标记降级」的运行时含义已被裁定 A 取代：过期证据权重为 0 而非 0.45；
- 其「Both Missing → UNAVAILABLE，不得把缺乏证据当作 Low」与「Weight Zero / Invalid Denominator → 不产生虚假的正常风险结果」两点是审计当时的真实缺陷（B01/B02，对应 E3-03/E3-08），已由 Codex 独立审阅 R04/R05 确认修复（当前 `fusion.py` 对无证据窗口返回 None/UNAVAILABLE，四个风险字段为 null）。评估矩阵中不再列为待办，仅保留全链路（API/UI/export/FSM）的回归断言。

**E4 — latency 统计范围（交叉引用）**：latency 必须按 D07 定义为 **capture→render p95**，与模型 forward latency、Server-Timing 分段计时（capture→预处理→模型→commit→网络→render）分开报告，不得混同。EMA、FSM、故障恢复、日志完整性（eligible 请求分母）的要求不变。

**E2 / E5 — 范围澄清，无指标变更**：E5 只做正文的 V-only / T-only / fusion 配对反事实与稀释反例；Missing-Input 行为继续归 E3。E2 维持正文原样，不得在任何测试数据上选择「最优」权重。
