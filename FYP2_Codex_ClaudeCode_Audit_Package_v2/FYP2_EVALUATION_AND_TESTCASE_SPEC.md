# FYP2 Evaluation Categories & Test-Case Acceptance Specification (v2)

**定位**：FYP2 设计与审计基准，不是已完成的测试报告。必须根据实际 repository/config 修正实施细节；所有“待验证”状态不可当作 PASS。**Week 7** 目标：功能完成、真实 baseline inference 接通、关键系统测试可运行；更大规模实验的分析可以继续在后续完成，但测试脚本和追踪机制应提前建立。

## 0. 从 FYP1 继承的范围与已知限制

- Baseline vision：State Farm 10-class、MobileNetV3-Large、driver-disjoint test accuracy 0.8988 / macro-F1 0.8746（**FYP1 报告结果，需在当前仓库复核**）。
- Baseline telemetry：8-feature synthetic dataset、XGBoost accuracy/macro-F1 0.9993（**合成数据高度可分，并非真实道路性能保证**）。
- 正式运行主分支：MobileNetV3 + XGBoost；对照模型：ResNet18 + Random Forest + Logistic Regression。**5 个模型均需在可控预算内做调参**；不做大规模无上限搜索。
- FYP1 报告的运行 prototype 仍使用 prepared probabilities / MockAIProvider；必须检查现在是否已替换。
- 不计划强制做 Probability Calibration；未做时必须说明概率解释、跨分支可比性的局限。不得将 RiskScore 当作真实事故概率。
- 两个训练集独立，缺少真实同步风险级标签；人工组合场景只能检验受控场景下的逻辑与鲁棒性，不能直接证明真实事故预警性能提升。

## 1. 五个独立 Evaluation Categories

| ID | Category | Research Question | Input/Experiment | Primary Metrics | 有条件的成功标准 / 正确结论 |
|---|---|---|---|---|---|
| **E1-V** | Vision model robustness | 输入质量降低时分类是否受影响，哪个模型相对稳健？ | 6 corruption × 3 severity，同一干净独立测试集；MobileNetV3/ResNet18 | macro-F1、ΔF1、per-class recall、prediction flip rate | 实验可重现、同样本对比；不预设必须优于竞争模型；严重破坏语义时不能硬算正确率 |
| **E1-T** | Telemetry model robustness | 结构化数据噪声、重叠、漂移及缺失对预测影响？ | D0 + D1/D2/D3 各 3 强度；XGBoost/RF/LR | macro-F1（仅有效标签）、flip rate、confidence change、invalid input handling | 所有模型用同一测试变体；可重现；D2 明确 label-conditioned synthetic stress，不能当外部真实数据 |
| **E2** | Fusion effectiveness | 正常条件下双模态权重、风险等级、解释是否合理？ | Clean scenario pairs + 5 weight settings | formula match、risk-level distribution、weight sensitivity、dominant evidence | 逻辑可解释、计算正确、边界正确；没有独立 severity truth 不给“真实风险分类准确率” |
| **E3** | Fusion robustness | 一个模态 missing/stale 时是否正确再归一化、标 partial？ | one/both missing; one/both stale; asynchronous timestamps | continuity、normalization error、state correctness、ΔRisk分布 | 缺一模态输出仍可用；both-missing 不虚构 Low 风险；报告原 ΔRisk≤0.15 的遵守比例而非不合理硬门槛 |
| **E4** | Runtime robustness | EMA、FSM、异常和恢复是否稳定？ | deterministic temporal streams; failing inference/API/storage | alert flip、response lag、FSM guards、recovery、log completeness | `<2s` 高尖峰不进入 HIGH_ALERT；`>=10s` 持续低风险才恢复；日志≥99%（分母明确），不崩溃 |
| **E5** | Cross-layer robustness | 单分支退化时，清洁的另一个分支是否有助于维持信息和预警？ | degraded V+clean T；clean V+degraded T，配对固定场景 | score/level retention、high-risk retention（仅独立预设场景 oracle）、false negative（仅真实有效标签）、attenuation cases | 可以证实/反驳互补性，不可凭评分波动更小就认定降低真实事故风险 |

**补充项（与 E1–E5 独立）**：M1 五模型 Comparison & Hyperparameter Tuning；M2 DMD cross-dataset（仅标签映射、访问、分组满足时）；S1 unit / integration / system / performance / UAT / error handling。不要把 E1-E5 当成替代 UAT/Software Testing。

## 2. E1 Vision：6 × 3 扰动参数与审计点

| Corruption | Level 1 | Level 2 | Level 3 | 审计注意 |
|---|---|---|---|---|
| Brightness increase | ×1.2 | ×1.5 | ×1.8 | pixel clipping 可能失去语义；只是强曝光 proxy |
| Brightness decrease | ×0.8 | ×0.5 | ×0.3 | 低光不可辨样本另做质控 |
| Motion blur | kernel 3 | kernel 7 | kernel 11 | 运动方向固定或 seed 显式；同图可复现 |
| Random occlusion | ~5% image | ~10% | ~20% | 位置按 sample ID+seed 确定，同模型同位置 |
| Rotation + crop | ±3° | ±7° | ±12° | 避免手部方向 label 无意变化；记录裁剪 |
| RGB grayscale blend | 30% | 60% | 100% | **不是 IR/NIR camera 的真实分布** |

设计约束：使用 State Farm 的 **held-out driver-disjoint TEST 集**，不要用训练图生成测试图；可固定 1,000–1,500 张分层抽样子集降低成本。使用相同样本、相同扰动参数与随机种子评价两个模型。至少输出 `sample_id,original_label,model,corruption,severity,predicted_label,probs,seed` 以及 aggregate table。不要因为扰动导致 ground-truth 视觉行为不可识别，就强行把原标签当作可靠监督。最好进行抽样人工质量审查。

**DMD 视频**：可以抽帧用于 frame-level image classifier，不用改成视频模型；但要审查摄像头视角、视频与帧标注对齐、action time intervals、class mapping、subject/video grouping、近重复、数据许可。若只有 binary-compatible 类别就只对该**明确 subset**评估二分类，不能硬套 10-class；DMD 测试不能用于目标域调参后还被称为 zero-shot external test。

## 3. E1 Telemetry：D0–D3 数据生成与有效性

| Domain | 具体条件 | 每个强度行数（建议） | 特殊约束 |
|---|---|---:|---|
| D0 Clean | 原始 held-out synthetic test | 4,500 | `is_synthetic=true`, `is_perturbed=false` |
| D1 Noisy | Gaussian sigma = `0.1 / 0.3 / 0.5 × std(train feature)` | 每级 4,500 | 样本ID/单位/物理边界；原 label 有效性审核 |
| D2 Overlap | `x' = x + λ(μ_train_global - μ_train_class_y)`；例如 λ=`0.25/0.50/0.75` | 每级 4,500 | 需读取测试标签来选择位移方向，是**label-conditioned** stress；原标签可能不再成立；统计量只由 train 求 |
| D3 Drift+Missing | 固定方向偏置（如 `0.25/0.5/1.0 × std_train`）并 mask 特征、train-only median 填补 | 每级 4,500 | 缺失率 vs 缺失特征数需定义，不要含糊；生成缺失 mask；针对三模型共用同一填补策略 |

如果所有严重程度都保留相同 4,500 行基础样本，则共有 **45,000 条派生记录**（包含 D0），三模型复用，不需要每个模型重新生成。保存 CSV/Parquet + `generator_parameters.json`；必要字段：`source_record_id, original_label, domain, severity, is_synthetic, is_perturbed, seed, transform_params, ...eight_features`。附原数据版本/校验和、train-split statistics、软件版本、生成代码 commit。注意不能让 test 参与均值/标准差拟合或调参。若 D2 标签失效，报告分布变化/预测翻转而非错误宣称“Accuracy下降证明真实泛化差”。

## 4. E2 Fusion Effectiveness：干净正常条件下的受控配对

**Scenario Pair Generator**：明确记录 `vision_sample_id, telemetry_record_id, vision_label, telemetry_label, selected_pairing_policy, timestamp_or_replay_order, user_predeclared_expected_behavior`。人工配对必须标记为 **constructed**，不是 observed co-timed events。建议 6 种场景：low/low；vision-high/telemetry-low；vision-low/telemetry-high；high/high；medium/threshold；disagreement。权重 5 组：`(.5,.5),(.6,.4),(.4,.6),(.7,.3),(.3,.7)`。

**测试 oracle**：确定性公式结果应由**独立测试代码或手算已知值**生成，不能调用待测 fusion 函数本身；核对 RiskScore、RiskLevel、DominantEvidence；阈值=30/60 的边界值要测试。统计 score/level 分布、权重敏感性、跨阈值变化率、误抑制强单模态证据的案例。不要宣称有无真实配对标签支持的“Fusion Accuracy/Recall”。

## 5. E3 Fusion Robustness：missing、stale、异步

| Test ID | 输入 | 预期/标准（优先做确定性测试） |
|---|---|---|
| E3-01 | V missing, T fresh | 继续输出依据 T 的数值；`partial`/missing 标记正确；按 f_v=0 计算 |
| E3-02 | T missing, V fresh | 同上，用 V 输出 |
| E3-03 | V/T both missing | `unavailable` / invalid，没有伪造 RiskScore=0 的正常 Low Risk；安全降级 |
| E3-04 | V stale, T fresh | `f_v=0.45`（若配置如此），`f_t=1`，有效权重按分母归一化；partial 标记 |
| E3-05 | V fresh, T stale | 对称用例 |
| E3-06 | both stale / latency boundary | 根据系统真实 policy 检查输出，不能偷偷视为 fresh |
| E3-07 | async delayed packets / session reset | 不跨 session 混用旧分数；时间戳判断与时区/时间单位一致 |

**FYP1 Target `ΔRisk≤0.15` 冲突示例**：若 `P_v=.1, P_t=.9`, `w_v=w_t=.5`, full RiskScore 0–1 = 0.5；V missing 后 = 0.9，则 `ΔRisk=0.4`；数学上正确但未达早期目标。必须同时记录 `continuity PASS`, `formula PASS`, `original target NOT MET in this case`；建议导师确认目标适用边界，并在报告中完整披露 target attainment rate/分布。不能把单次 drift 超标误记为公式 bug，也不能默默删掉 FYP1 目标。

## 6. E4 Runtime Robustness：时序、故障与恢复

| Test ID | Scene | Oracle / Metric |
|---|---|---|
| E4-EMA-01 | 间歇尖峰及稳定高风险阶跃，EMA ON/OFF | compare risk-score total variation/alert flip + response delay；不要预设哪项一定改善 |
| E4-FSM-01 | High spike 1.9 s 与 2.1 s | 不足 2 s 不得进入 `HIGH_ALERT`；满足持续时间后按 cadence 正确进入 |
| E4-FSM-02 | 低风险 9.9 s 与 10.1 s | 不足 10 s 不完全恢复；满足 guard 后按设计恢复 |
| E4-FAIL-01 | invalid image, payload, NaN, out-of-range, wrong feature order | reject/flag；无无声产生有效 score；UI 明确错误 |
| E4-FAIL-02 | model unavailable/loading error/API timeout | no crash / degraded path / observable status；可恢复 |
| E4-FAIL-03 | N consecutive failures, then recovery | N 必须来自明确 config/design；未实现则标 OPEN DECISION；验证降级与恢复日志 |
| E4-LOG-01 | repeated session updates incl. faults | `log_completeness = persisted_expected_updates / expected_loggable_updates`；说明是否期望失败也有独立 error logs，目标 >=99% |

所有 EMA/FSM 测试需要 **controlled/fake clock 或精确 replay timestamps**，不能依赖慢速人工点击来判定 2s/10s。需要记录 input timestamp/cadence、actual transition times、timing error、FSM current state。

## 7. E5 Cross-Layer Robustness：跨层对照和结论限制

| Path | Input Pairing | Comparators | Key Outputs |
|---|---|---|---|
| V-degraded/T-clean | 同一视觉样本 6×3 扰动 + 固定 clean telemetry | V-only(clean/noisy), Fusion(clean/noisy), optional T-only | score drift、risk-level retention、high-risk retention **若定义了有效独立 oracle** |
| V-clean/T-degraded | 固定 clean vision + D1/D2/D3 的同源 telemetry record | T-only(clean/stressed), Fusion(clean/stressed), optional V-only | same + mean attenuation/failure cases |

必须固定 pairing policy、权重、threshold、seeds、frame/record IDs，列出 scenario ground-truth 的来源。**没有真实同步多模态风险严重程度标签**：可讨论 operational indicator 一致性、互补证据与潜在遗漏，不可称实际交通事故高风险识别提升。比较 `ΔRisk` 更低时也要检查 **high evidence dilution**：简单平均会天然减少单分支波动。若出现“fusion worse”，原样报告、分析原因；实验不是为预设正确结论服务。

## 8. 除 E1–E5 外，Rubric 强制的软件测试

| Level | 最小必测 | Sample concrete case IDs | Evidence |
|---|---|---|---|
| Unit | Vision/telemetry output contract; fusion formula+thresholds; freshness; EMA/FSM | UT-MODEL-01, UT-FUS-01..05, UT-TIME-01..03 | test code + execution log + assertions |
| Integration | trained-model adapter->orchestrator->fusion; API->SQLite; backend->dashboard; export | IT-AI-01, IT-API-01, IT-UI-01, IT-DB-01 | trace ID / logs / screenshots |
| System | full session/replay; missing both; corrupt input; export/restart; recovery | ST-REPLAY-01, ST-FAIL-01, ST-RECOVER-01 | run log, schema snapshot, PASS/FAIL |
| Performance | p50/p95 inference and E2E latency, 1.0s target, log completeness ≥99% | PERF-01, PERF-02 | hardware/env + raw timestamp pairs + denominators |
| UAT | users complete representative tasks on real integrated system | UAT-01..05 | script, participants (without sensitive data), actual results/feedback, not a questionnaire template |
| Error handling | model failure, invalid payload, timeout, storage errors, graceful degradation | ST-ERR-01..05 | API response + UI state + log + retry success |

**严格的 Test Case Schema**：`id / related requirement & objective / preconditions / input data source & split / steps / expected independently checkable output / metric unit / pass threshold or EXPLORATORY / actual results / run command / executed date / status / source path / methodological concern`。若 pass threshold 根本不成立，修正为 exploratory/report-only，而不是杜撰一个数字。

## 9. Week-7 Development 与 Report 对应

| Week | Critical path | Acceptance Gate | Evidence / Report |
|---|---|---|---|
| W1 | Audit, artifact validation, schema freeze | checkpoint loadable; maps known; audit docs | 4.x design consistency, 5.1/5.2 |
| W2 | Full system skeleton using transparent mocks | end-to-end UI/API/DB/export replay | 5.4–5.6 architecture and implementation |
| W3 | Integrate actual FYP1 MobileNetV3/XGBoost inference | real image+record -> output -> dashboard -> persisted log | 5.3–5.5 |
| W4 | ResNet18/RF/LR baselines, tuning scripts | 5 models reproducibly train/evaluate; validator split frozen | 5.3, 6.2 pending |
| W5 | Controlled HPO of 5 models; freeze final | validation-selected checkpoint, no test leakage | 5.3, 6.2 experiment artifacts |
| W6 | E1–E5 scripts/smoke plus software tests | generators run, traceable CSV/JSON; unit/integration/system/error tests | 6.2–6.8 evidence preparation |
| W7 | Feature freeze, demo, regression | production path uses actual model; no P0 bugs; full replay demo | Chapter 5 near final; Chapter 6 evidence index |

学校四个核心章节：**Chapter 4 System Analysis and Design**（existing design updated against code）；**Chapter 5 System Development**（implementation + tuning + adapters + dashboard/error UX）；**Chapter 6 Results and Discussion**（E1–E5 + model comparison + unit/integration/system/performance/UAT）；**Chapter 7 Strengths, Limitations and Future Works**（objective fulfillment + explicitly bounded claims）。前 1–3 章只做与最后实现相关的必要更新。

## 10. Agent 应当输出的核心结论

审计完成后，必须回答：
1. 真实 inference 是否从输入走到 Dashboard 和 SQLite？哪些节点还是 Mock？
2. 当前 5 models training/tuning、数据划分、原始模型对比是否存在真实证据？
3. E1–E5 每项的 **可执行性、有效性、测量指标、合理的 pass criteria、是否完成、有无 evidence** 是什么？
4. Unit/Integration/System/UAT/Error Handling 是否达到 Rubric 的类别要求（不能用 E1–E5 替代）？
5. Week 7 还有哪些 P0 blockers？下一步 72 小时按依赖关系如何安排？

> **研究完整性底线**： synthetic stress ≠ independent external validation；grayscale ≠ genuine IR；constructed scenario pairs ≠ true paired risk ground truth；formulas passing ≠ proven safety gain；a test file existing ≠ executed passing evidence。所有这些都必须在审计报告中清楚区分。
