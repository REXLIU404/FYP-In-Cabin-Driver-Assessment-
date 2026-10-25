# 当前模型进入系统的方法学与结论边界

## 1 现有结果是否支持 ResNet18 与 XGBoost 的候选优先顺序

### Takeaway

**PASS：现有证据足以把 validation-fixed ResNet18 与 XGBoost 确定为本科 FYP 后续受控集成、离线影子比较的优先研究候选；不构成工程接线已完成或自动替换 stable 的结论。** P4-B 是已冻结身份的评估，不能再用 Test/E1 选择 trial、seed、阈值或新的 HPO 方向。这里的“足以”是基于项目现有任务与证据作出的研究判断，不是文献提供的统一准确率门槛。

本研究于 2026-10-23 读取 `fyp2/ml-training`、HEAD `335da4e3de203836c045452f84cc291bcd352a26` 的现有 JSON 与文档；该工作区包含已披露的未提交证据。权威原 prompt 与 R4 通过本仓库 `git show fyp2/live-system:docs/fyp2/review/CODEX_ML_TRACK_PROMPT.md` 和 `git show fyp2/live-system:docs/fyp2/review/CODEX_ML_TRACK_ADDENDUM_R4.md` 完整读取，没有进入另一物理工作区。P4-B completion 是当时评估状态的记录，本轮另行批准的 P5 packaging 不会使该记录变成部署批准。[本地权威入口与冻结分析 context](/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/docs/fyp2/ml/ML_RESULTS_REVIEW_CONTEXT.md)；[P4-B completion](/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/ml/outputs/runs/p4b_20261022/completion.json)

### Cited Findings

- **冻结依据先于 P4。** 视觉 selection log 固定 RN `search_004` 与 MN `search_006`、seed42，并明确 `confirmation_cannot_reselect=true`。RN validation macro-F1 为 0.940615，三 seed mean±std 为 0.924798±0.027114；MN 分别为 0.916220 与 0.893663±0.015950。确认 seed 的波动是需要披露的观察，不能挑最高 seed43 替换 seed42。[视觉 selection log](/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/ml/outputs/runs/p3_vision_20261018/selection_log.json)
- **XGB preference 不能写成分类显著胜过 RF。** Validation 的 XGB/RF macro-F1 仅差约 4.94e-13；两者均约 0.998889。XGB validation log-loss 0.004926 低于 RF 0.008044，支持在近似并列分类表现下优先研究既有范围内的 XGB；较低 log-loss 本身不是已验证校准结论。RF/LR 按既定 R4 只作 benchmark。[遥测 selection log](/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/ml/outputs/runs/p3_telemetry_20261018/selection_log.json)；[冻结前独立分析 context](/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/docs/fyp2/ml/ML_RESULTS_REVIEW_CONTEXT.md)
- **冻结后的 Clean Test 支持继续研究 RN，但不支持候选全面升级。** RN Accuracy/Macro-F1=0.901559/0.889236，MN-HPO=0.873120/0.867654，MN-STABLE=0.898824/0.874641；因此 RN 相对 MN-STABLE 的 Accuracy 只高约 0.27345 个百分点，且 MN-HPO 未超过 MN-STABLE。XGB-HPO/RF 均错 5/4500、LR 错 9/4500、XGB-STABLE 错 3/4500；不能以本次 HPO 名义宣称自动升级。[P4-B evaluation_metrics.json](/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/ml/outputs/runs/p4b_20261022/evaluation_metrics.json)
- **产物完整性与性能外推是不同证据。** P4-B completion 记录 388449 条正式预测、`MACHINE_EVALUATION_COMPLETED`、`candidate_package=false`、`deployment_eligible=false`。独立缓存审计记录 309/309 PASS、failures=[]、最大指标绝对差 2.22e-16，明确 `CACHE_ONLY_NO_MODEL_LOAD_NO_PREDICT_NO_RAW_INPUT_OPEN`；另有 closure PASS。它们支持现有结果可追溯及缓存复算一致，不能解释为独立重训、重新完整推理或真实系统部署验证。[completion](/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/ml/outputs/runs/p4b_20261022/completion.json)；[独立缓存审计](/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/ml/outputs/runs/p4b_20261022/verification/independent_cached_audit.json)；[closure integrity](/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/ml/outputs/runs/p4b_20261022/verification/closure_integrity.json)
- **Primary 方法学依据：** Cawley 与 Talbot（JMLR 2010）说明，有限样本上的模型选择目标本身也可能被过拟合，其影响可与不同算法之间的差异相当；该论点并不局限于 cross-validation。它支持把 validation 用于选择、把选择后的 Test 用于评价，并披露选择乐观性。[On Over-fitting in Model Selection and Subsequent Selection Bias in Performance Evaluation](https://jmlr.org/papers/v11/cawley10a.html)

### Inferences

- **建议保持原优先顺序，不重新选型。** RN 的 validation 优势和 P4 clean 表现共同支持“值得进入候选系统比较”，而非“已证实最佳部署模型”。XGB 是既定架构范围中的研究优先对象，与 RF 近似持平的解释应保留。这里没有重写 selection log，也没有从 Test 反推新排名规则。[视觉 selection](/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/ml/outputs/runs/p3_vision_20261018/selection_log.json)；[遥测 selection](/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/ml/outputs/runs/p3_telemetry_20261018/selection_log.json)；[P4 metrics](/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/ml/outputs/runs/p4b_20261022/evaluation_metrics.json)
- **BLOCK 以下措辞：**“RN/XGB 已全面超过旧模型”“HPO 保证提升”“Test 证明应改选某 seed”“309 检查通过等于真实驾驶准确率验证”。建议改为：“Validation-fixed RN/XGB 被保留为优先研究候选；P4 提供冻结模型在该源域上的描述性 clean、稳定性和 model-only runtime 证据。”[P4 limitations/metrics](/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/ml/outputs/runs/p4b_20261022/evaluation_metrics.json)；[模型选择偏差原论文](https://jmlr.org/papers/v11/cawley10a.html)

### Gaps

- 本轮没有独立重训或整套数值实验复跑；缓存复算不是相同类型的复现。不能补造跨运行 bitwise 保证。[独立缓存审计范围](/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/ml/outputs/runs/p4b_20261022/verification/independent_cached_audit.json)
- 没有基于目标系统效用的实证比较，因此当前材料不能给出“RN 净收益大于其成本”或“XGB-HPO 应替代 stable”的最终结论；这不阻碍把候选包交给现有后续评估阶段。[P4 metrics 与 runtime](/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/ml/outputs/runs/p4b_20261022/evaluation_metrics.json)

## 2 E1 缺少人工 QC 和有限司机覆盖如何限制结论

### Takeaway

**PASS：P4-B 在 user-amended 范围内完成了输出稳定性评估。BLOCK：把 QC removal 写成 QC PASS，或把低 flip/L1 写成正确性、保留动作标签、自然域鲁棒性或安全提升。** 四位 test 司机、历史 Test 曝光及合成 telemetry 限制外推强度，但并不把已经保存的源域描述性结果自动作废。

### Cited Findings

- **人工标签证据没有取得。** `qc.status/pilot/formal/conditioned_f1/human_label_validity/inter_rater_agreement` 均为 `REMOVED_FROM_SCOPE`；stress 项保留 `LABEL_VALIDITY_UNVERIFIED`、`f1_eligible=false`、`human_validated=false`。原标签 corruption F1 未计算，不能补称 recognizability 或 inter-rater 通过。[P4 qc 与 stress flags](/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/ml/outputs/runs/p4b_20261022/evaluation_metrics.json)；[规范进度首节对 user amendment 的解释](/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/docs/fyp2/ml/ML_TRACK_PROGRESS.md)
- **E1 没有统一赢家。** 最高强度 brightness_down 的 RN/MN-HPO flip 为 10.4457%/5.7424%，motion_blur 为 48.3183%/41.0172%；grayscale_blend 为 16.2428%/28.8488%，rotation_crop 为 11.3208%/17.8835%。因此 RN 在部分条件较稳定、在另一些条件变化更大；这些数值比较的是输出变化，而不是哪一模型在变换后答对更多。[P4 vision stress metrics](/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/ml/outputs/runs/p4b_20261022/evaluation_metrics.json)
- **弱类与司机差异不能被 pooled 均值掩盖。** 3657 帧仅来自 p012/p026/p035/p050 四位 test 司机，支持数为 823/1196/848/790。RN 逐司机 macro-F1=0.748208/0.924132/0.955527/0.851932；pooled c9 F1=0.605941，但 p050 c9 F1=0、support=70。现有 leave-one-driver-out 指标是从缓存剔除一组后重算，没有重训。[P4 driver_metrics](/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/ml/outputs/runs/p4b_20261022/evaluation_metrics.json)；[独立审计 driver counts 与方法](/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/ml/outputs/runs/p4b_20261022/verification/independent_cached_audit.json)
- **历史曝光与直接调参应区分。** 当前记录明确披露 Test split 曾多次评估，同时“未发现直接用 Test 选参的代码”；没有依据声称 Test 从未见过，也没有依据将其改写成已证实的 test-driven leakage。Telemetry 来源为 synthetic，driver/trip/generator independence 未知；D2 是 label-conditioned stress，D3 是 combined positive-bias and record-level missingness stress，不能当作自然驾驶分布移位实验。[P4 limitations 与 telemetry metadata](/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/ml/outputs/runs/p4b_20261022/evaluation_metrics.json)；[规范进度首节](/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/docs/fyp2/ml/ML_TRACK_PROGRESS.md)
- **Primary 论文把两类指标明确区分。** Hendrycks 与 Dietterich（ICLR 2019）对 ImageNet-C 用 error-based corruption 指标，对 ImageNet-P 用预测变化的 Flip Probability 等 stability 指标；后者的比较对象是模型相邻或 clean/perturbed 预测，并非真实标签。论文还区分 corruption 与 perturbation robustness。项目 E1 可借用这种概念区别，但当前 6×3 设计、L1 指标及未做 QC 不等于完整复现 ImageNet-C/P benchmark。[Benchmarking Neural Network Robustness to Common Corruptions and Perturbations](https://arxiv.org/html/1903.12261)
- **官方 grouped-data 指南支持按司机解释。** scikit-learn 文档指出，同一主体内多条记录可能相互依赖，i.i.d. 假设因此不成立；若关心对未见主体的泛化，应将主体作为 group，并让配对训练/评价 group 分离。这支持现有 driver-disjoint 设计与 group-aware 描述，不支持把 3657 帧当成 3657 名独立人物。[scikit-learn: Cross-validation iterators for grouped data](https://scikit-learn.org/stable/modules/cross_validation.html#cross-validation-iterators-for-grouped-data)
- **Primary 反例反对简单归因。** Recht 等（ICML 2019）按原流程构建新的 ImageNet/CIFAR-10 测试集后仍观察到准确率下降，但其结果指向图像更难，而非把下降一律归因于 adaptivity；因此“历史曝光值得披露”不等于“当前结果已经被证实因泄漏失效”。该论文的具体跌幅不能用于预测本项目会下降多少。[Do ImageNet Classifiers Generalize to ImageNet?](https://proceedings.mlr.press/v97/recht19a.html)

### Inferences

- **稳定不意味着正确。** 始终输出一个错误类别的模型也可以得到零 flip；遮挡、裁切若移除动作判据，原标签不再可直接视为有效。故保留现有 output-stability 结论与 QC removal 记录是自洽的。项目若未来重新研究标签保真或人工可识别性，应另有明确范围；本轮没有把被移除 QC 偷加回 P5 准入门槛。[E1 flags 与局限](/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/ml/outputs/runs/p4b_20261022/evaluation_metrics.json)；[Hendrycks 与 Dietterich](https://arxiv.org/html/1903.12261)
- **可用于论文的表述：**“在四名源域 test 司机与冻结模型下，进行了配对 clean 评价及人工标签保真未验证的扰动输出稳定性分析；所有逐司机、逐条件结果均保留。”不能改成“经 3657 个独立样本证明对所有司机鲁棒”或“消除驾驶风险”。四司机上的描述性差异可报告，但不建立总体统计显著优越性。[driver/stress metrics](/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/ml/outputs/runs/p4b_20261022/evaluation_metrics.json)；[grouped-data 指南](https://scikit-learn.org/stable/modules/cross_validation.html#cross-validation-iterators-for-grouped-data)
- **合成分布接近满分不等于真实 telemetry 能力。** LR 也接近满分，与 XGB/RF 的天花板表现一起，支持“这些模型能很好拟合该合成任务”的有限结论；没有真实传感器数据不能量化自然域表现，更不能把 D2/D3 直接命名为实车噪声。[clean 与 limitations](/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/ml/outputs/runs/p4b_20261022/evaluation_metrics.json)

### Gaps

- 缺少人工 recognizability、标签保真率与 inter-rater 数据，不能得出 corruption-labelled Accuracy/F1 或人类可识别性结论；该缺口是当前结果的结论限制，不是已批准 P5 packaging 的新阻断条件。[qc](/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/ml/outputs/runs/p4b_20261022/evaluation_metrics.json)
- 缺少更多独立司机、clip/事件级泛化与真实 trip/generator 的独立性证据；因此不报告 frame-bootstrap CI、p-value、司机总体显著性或真实驾驶 99.9% 准确率。[P4 limitations](/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/ml/outputs/runs/p4b_20261022/evaluation_metrics.json)

## 3 受控系统集成与真实使用之间还差什么 是否必须继续 fine tuning

### Takeaway

**PASS：冻结模型可作为有明确局限的研究候选继续 P5 isolated packaging；研究证据已足够支持后续系统工作。实际接入仍依赖系统侧实现，目前不能判为 integration PASS。BLOCK：把 model-only runtime、源域 Accuracy 或缓存审计升级为真实 camera 可靠性、端到端性能或部署批准。** 当前没有证据证明额外 fine-tuning 是 P5 的必要前置步骤；同样没有证据证明它对目标域无用或已经解决目标域问题。

### Cited Findings

- **P4 的性能测量边界明确。** MN-HPO/RN-HPO 的 CPU ORT session-only p95 分别为 7.2472/25.42145ms；batch1、同一 validation bank、固定线程和交错 AB/BA 轮次。它不包含 camera capture/encoding、网络、融合、SQLite 或 UI，也不是 capture-to-render latency。较小 MN 候选在这项实测中更快；不把 ONNX 文件大小替代时延或模型独占 RAM。[P4 runtime](/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/ml/outputs/runs/p4b_20261022/evaluation_metrics.json)；[runtime closure 重算与边界](/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/ml/outputs/runs/p4b_20261022/verification/closure_integrity.json)
- **系统轨道仍有明确归属。** R4 把本 ML 轨道限定到 E1；融合、EMA、Alert FSM、E2–E5 和 Task 10A 属于系统轨道。候选 package 需要单独 runtime_manifest 与 evaluation_metrics，维持类别/输入/输出语义及路径/hash 契约；RF/LR 不进入候选包。P5 isolated packaging 与替换 stable 是不同动作。[context 中的权威来源与边界](/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/docs/fyp2/ml/ML_RESULTS_REVIEW_CONTEXT.md)；[P4 completion](/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/ml/outputs/runs/p4b_20261022/completion.json)
- **本轮协调的当前 contract 结论：**系统 Git source `fyp2/live-system@2745348` 已有 vision manifest schema/validator，但当前 provider 尚未消费 manifest，Task 10A provider/evaluator 未实现，XGB 也没有候选 importer。因此本次 package 范围为两个 vision 包复制既有 ONNX；XGB 仅 `research_evidence`。这些系统事实由本轮协调者在核查后转述；runtime notes 由同轮另一位研究者完成供 writer 交叉检查，本方法学审阅没有重复读取另一物理工作区。可分别记录 `package PASS / integration BLOCKED / provider forward NOT_RUN`；P5 不承担实现这些系统工作。[同轮 runtime 独立审阅](</Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/docs/fyp2/ml/research_notes/FYP2 模型 系统准入 审查/runtime_compatibility.md>)
- **Primary 自然分布移位证据：** Koh 等（ICML 2021）的 WILDS 在十个反映实际应用分布移位的数据集上研究源/目标域差异，标准训练在域外表现显著低于域内，已有 shift 方法也没有消除差距。其结果说明源域分数不能代替目标域观察；不提供本项目必须达到的 Accuracy、司机人数或重新训练预算。[WILDS: A Benchmark of in-the-Wild Distribution Shifts](https://proceedings.mlr.press/v139/koh21a.html)
- **当前已存在训练/HPO，不应描述成尚未学习的现成模型。** 被选 RN/MN 的 config 记录 ImageNet pretrained recipe、固定 learning_rate/weight_decay、max_epochs 与执行 provenance；selection log 记录已完成 search 和确认训练。额外 fine-tuning 应与已完成的训练阶段区分。[RN selected config](/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/ml/outputs/runs/p3_vision_20261018/search/resnet18/search_004/attempt_01/config.json)；[MN selected config](/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/ml/outputs/runs/p3_vision_20261018/search/mobilenet_v3_large/search_006/attempt_01/config.json)；[视觉 selection log](/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/ml/outputs/runs/p3_vision_20261018/selection_log.json)

### Inferences

- **当前足以回答的系统问题：**模型已能被确定为值得打成自足、可追溯研究包的候选，P4 为后续受控比较提供合理基础。包结构是否正确由 P5 实际检查决定；provider 接线是否完成、未来 golden behavioral checks 和实际 camera 检查则属于后续系统工作。不能把“尚未证明真实使用能力”错误推成“本科原型不能继续做受控集成”，也不能把这些后续工作偷偷变为 P5 新 hard gate。文献并未给出所有 FYP 必须遵循的统一准入分数。[P4 completion](/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/ml/outputs/runs/p4b_20261022/completion.json)；[metrics](/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/ml/outputs/runs/p4b_20261022/evaluation_metrics.json)；[同轮 runtime 审阅](</Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/docs/fyp2/ml/research_notes/FYP2 模型 系统准入 审查/runtime_compatibility.md>)；[WILDS](https://proceedings.mlr.press/v139/koh21a.html)
- **真正不支持自动替换的原因：**P4 是离线评估而非替换授权，候选并未对所有 driver/condition/stable 指标占优，model-only runtime 存在精度/成本权衡，且尚无本候选在目标系统完整流程与目标 camera 分布上的结果。它们共同要求保留“后续评估后决定”的结论，而不是人为新增车规合规清单或延后已经批准的 P5。此处描述证据缺口，不宣告新的硬性 acceptance criteria。[P4 limitations/runtime](/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/ml/outputs/runs/p4b_20261022/evaluation_metrics.json)；[候选与系统阶段边界 context](/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/docs/fyp2/ml/ML_RESULTS_REVIEW_CONTEXT.md)
- **Fine-tuning 的裁定：尚无额外训练必要性的证据。** c9/个别司机弱项、synthetic telemetry 与潜在 camera domain shift 提供后续诊断问题，但它们不能单独证明“再训练一次就解决”或“必须再做 HPO 才能包装”。若未来目标域观察暴露可重复失败，补代表性数据、检查机位/标签/预处理、比较既定训练方案或 fine-tuning 都可成为独立后续研究选项；不能用当前已曝光 Test 继续调参后再把它称作最终无偏 Test。[局限及弱类 evidence](/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/ml/outputs/runs/p4b_20261022/evaluation_metrics.json)；[WILDS](https://proceedings.mlr.press/v139/koh21a.html)；[Cawley 与 Talbot](https://jmlr.org/papers/v11/cawley10a.html)
- **建议可直接用于汇报的结论：**“P4-B 在用户修订范围内完成；validation-fixed ResNet18 与 XGBoost 保留研究优先地位。本次 P5 包含两种 vision 的 isolated packaging，XGB 作为 research_evidence 交付；实际受控集成及离线影子 evaluator 仍待系统侧实现。当前源域 clean 结果与输出稳定性证据没有证明真实 camera/vehicle 泛化或部署优越性，因此 stable 保留，额外 fine-tuning 不被设为本阶段必做项。”[canonical progress 首节](/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/docs/fyp2/ml/ML_TRACK_PROGRESS.md)；[completion 与原阶段边界](/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/ml/outputs/runs/p4b_20261022/completion.json)；[同轮 runtime 审阅](</Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/docs/fyp2/ml/research_notes/FYP2 模型 系统准入 审查/runtime_compatibility.md>)

### Gaps

- 本研究没有候选在实际系统/目标 camera 或指定 edge 设备上的新测量，不能回答端到端 p95、真实误报/漏报率、事件级告警效用，或额外 fine-tuning 的收益。没有开展任何新 model forward、held-out 推理、训练/HPO、源码/模型/CSV/env 修改或系统轨道操作。[P4 当前测量边界](/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/ml/outputs/runs/p4b_20261022/evaluation_metrics.json)
- 可供其他 agent 独立 review 的具体问题：P5 package 是否保持冻结 trial/seed 与 preprocess/logits/class-order 语义；报告是否把 RN 的 pooled 优势错误扩大为所有司机/条件优势；是否把 synthetic 接近满分或低 flip 当成真实正确性；是否把用户移除的人工 QC 偷改为 PASS 或新硬门槛；是否把额外 fine-tuning 当作未经证据支持的必做项。它们是现有协议/表述的审查问题，不是新实验授权。[冻结 selection](/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/ml/outputs/runs/p3_vision_20261018/selection_log.json)；[P4 limits](/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/ml/outputs/runs/p4b_20261022/evaluation_metrics.json)；[既定 package 边界 context](/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/docs/fyp2/ml/ML_RESULTS_REVIEW_CONTEXT.md)
