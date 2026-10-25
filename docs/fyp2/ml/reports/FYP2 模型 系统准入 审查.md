# 现有模型足以进入受控候选阶段

**当前五模型结果足以支持本科 FYP 的候选研究与后续受控集成；现有证据没有要求先追加 fine-tuning。** ResNet18 与 XGBoost 保持 validation 阶段冻结的研究偏好，MobileNetV3-Large 保留为较快的配对视觉候选，RF/LR 保留为 benchmark。这个判断不批准替换现有 stable，也不表示候选已接入系统。P4 已完成源域 clean、配对输出稳定性与 CPU model-only 测量；P5 交付包、系统 provider 接线、目标 camera 验证分别回答不同问题。当前系统尚未实现候选 manifest 加载与离线 evaluator，因此“研究候选成立”和“系统集成仍阻塞”可以同时成立。下一步有价值的工作是交付可追溯候选并完成既定系统评估，而不是依据已曝光的 Test 再选择 seed 或启动一轮 HPO。([冻结选择与审查背景](/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/docs/fyp2/ml/ML_RESULTS_REVIEW_CONTEXT.md)、[P4 completion](/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/ml/outputs/runs/p4b_20261022/completion.json))

审查收尾日期：**2026-10-25**。ML 来源为 `fyp2/ml-training@335da4e3de203836c045452f84cc291bcd352a26` 及已披露的未提交证据；系统结论限定于只读 Git 对象 `fyp2/live-system@2745348f3d4587e14c1d4a7e53a2bfc4d72225d5`。本报告综合已有实验及已核验的 primary 文献，复用10月24日已完成的 P5 检查，不开展新训练、推理或 Test 调参；run_id 保留 `p5_candidates_20261023`。

**Git 来源说明：**工作树仍为 dirty，staging 为空。额外条目包括仅新增 `backend.dev.log` 忽略规则的 `.gitignore` 变更，以及 backend SQLite 的 `driver_risk.db-wal/-shm`；日志记录 Uvicorn 启动、HTTP 读取与正常 shutdown，但启动者未确认，不归因于用户或任何 agent。三项范围外条目原样保留。P5 的 copy-only 打包与本次文档收尾没有修改 backend，也没有新模型 forward；这些事实不能证明整个工作树 clean。([闭合时 Git 记录](/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/ml/outputs/runs/p5_candidates_20261023/verification/final_closure.json)、[规范进度中的来源说明](/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/docs/fyp2/ml/ML_TRACK_PROGRESS.md))

## 七个身份说明取舍，不能把 HPO 写成普遍升级

视觉选择已固定为 RN `search_004/seed42`、MN `search_006/seed42`；其 validation macro-F1 分别为 **0.940615、0.916220**，确认训练不得重新选择 seed。遥测 XGB `xgboost_02` 与 RF 的 validation macro-F1 近似并列，XGB 较低的 validation log-loss 支持既定范围内的研究偏好，不能据此宣称分类显著更好或校准已验证。Cawley 与 Talbot 说明，有限验证样本上的选择目标也会被过拟合；本项目由此坚持 validation 选型、冻结后 Test 描述评价，不利用 P4 结果反向改写选择。([视觉 selection](/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/ml/outputs/runs/p3_vision_20261018/selection_log.json)、[遥测 selection](/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/ml/outputs/runs/p3_telemetry_20261018/selection_log.json)、[模型选择偏差原论文](https://jmlr.org/papers/v11/cawley10a.html))

| P4 Clean Test 身份 | Accuracy | Macro-F1 | Log loss | 本次角色 |
|---|---:|---:|---:|---|
| RN-HPO42：ResNet18 `search_004` | 0.901559 | 0.889236 | 0.450868 | validation 冻结视觉研究偏好 |
| MN-HPO42：MobileNetV3-Large `search_006` | 0.873120 | 0.867654 | 0.740502 | 配对视觉候选 |
| MN-STABLE：既有 MobileNetV3 | 0.898824 | 0.874641 | 0.574453 | 稳定参照，保留原件 |
| XGB-HPO42：`xgboost_02` | 0.998889 | 0.998889 | 0.003670 | 遥测研究偏好；research_evidence |
| RF-HPO42：`random_forest_06` | 0.998889 | 0.998889 | 0.007535 | benchmark-only |
| LR-HPO42：`logistic_regression_06` | 0.998000 | 0.997999 | 0.007199 | benchmark-only |
| XGB-STABLE：既有 XGBoost | 0.999333 | 0.999333 | 0.003712 | 稳定参照，保留原件 |

表中视觉为同一 **3657 帧、10 类**，遥测为同一 **4500 条、3 类**；完整指标来自 [P4 evaluation_metrics.json](/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/ml/outputs/runs/p4b_20261022/evaluation_metrics.json)。RN 相对 MN-STABLE 的 Accuracy 仅高 **0.27345 个百分点**；MN-HPO 未超过 stable。XGB-HPO/RF 均错 **5/4500**，LR 错 **9/4500**，XGB-STABLE 错 **3/4500**。因此五模型比较支持有依据地保留研究对象，也显示自动升级缺少依据；合成 telemetry 的天花板表现只证明该合成任务上的能力。

精度与计算成本也有取舍：同一 validation bank、固定 CPU ORT 配置、六轮交错测量中，MN/RN 的 session-only p95 为 **7.2472/25.42145 ms**，ONNX 大小为 **16,849,370/44,717,068 bytes**。这支持保留 MN 的速度对照价值，但计时不含预处理、camera、网络、fusion、SQLite 与 UI。ONNX Runtime 官方说明线程调度影响时延波动，因此这些数值只描述已测主机与配置，不能作为 Live capture-to-render 或 edge 性能。([P4 runtime](/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/ml/outputs/runs/p4b_20261022/evaluation_metrics.json)、[ONNX Runtime 性能说明](https://onnxruntime.ai/docs/performance/tune-performance/troubleshooting.html))

## E1 证明输出变化可描述，尚未证明真实场景正确

**E1 没有全面赢家。** 最高强度暗化下 RN/MN-HPO flip 为 **10.4457%/5.7424%**，强模糊为 **48.3183%/41.0172%**；灰度为 **16.2428%/28.8488%**，rotation/crop 为 **11.3208%/17.8835%**。brightness_up 的 flip 与 L1 相对顺序不同，强模糊还使 MN 的 c0 预测增加 **1291 条**、RN 的 c6 增加 **885 条**。Flip、概率 L1 和分布变化提供互补描述，无法合并成“更安全”的排名。Hendrycks 与 Dietterich 区分 error-based corruption 指标与 prediction-change stability 指标；本项目借用这种概念区别，并非完整复现 ImageNet-C/P。([P4 stress metrics](/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/ml/outputs/runs/p4b_20261022/evaluation_metrics.json)、[corruption 与 perturbation 原论文](https://arxiv.org/html/1903.12261))

用户移除的人工 QC 仍为 **REMOVED_FROM_SCOPE，绝非 PASS**；`LABEL_VALIDITY_UNVERIFIED / f1_eligible=false / human_validated=false` 保留，不计算原标签 corruption F1。恒定错误输出也能得到零 flip，遮挡与裁切还会改变动作判据。D2 是 label-conditioned stress，D3 是 combined positive-bias and record-level missingness stress，均不足以代表自然驾驶噪声。([P4 协议与验收边界](/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/docs/fyp2/ml/ML_TRACK_PROGRESS.md)、[完整 metrics](/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/ml/outputs/runs/p4b_20261022/evaluation_metrics.json))

3657 帧来自 **四名** test 司机，不能当作3657名独立参与者。RN pooled c9 F1 为 **0.605941**，p050 的 c9 F1 为 **0（support=70）**；逐司机表现也不一致。Grouped-data 官方指南支持按主体分组解释；本次 leave-one-driver-out 只是缓存剔除后的重算，没有重训或总体显著性检验。历史 Test 多次曝光、synthetic telemetry 的 driver/trip/generator 独立性未知、DMD BLOCKED 与实际 camera 视角未验证均继续披露；现有记录未发现直接用 Test 选参的代码，不能将“历史曝光”改写成已证实泄漏。([driver 与 limitations](/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/ml/outputs/runs/p4b_20261022/evaluation_metrics.json)、[grouped-data 指南](https://scikit-learn.org/stable/modules/cross_validation.html#cross-validation-iterators-for-grouped-data))

## P5 包可以交付，系统准入仍取决于 Task 10A

| 证据层次 | 当前判断 | 可支持的结论 |
|---|---|---|
| 冻结研究候选 | SUPPORTED | RN/XGB 保持 validation 偏好，MN 保留配对 |
| P4 机器评估 | VERIFIED_PASS（user-amended scope） | 源域 clean、E1 输出稳定性与 model-only runtime |
| P5 两视觉包 | VERIFIED_PASS（copy-only package 范围） | 实际包、静态合同、软件与追溯检查通过 |
| 当前 provider 加载候选并 forward | NOT_RUN | 静态包验证不等于模型加载 |
| 系统候选集成 | BLOCKED_BY_TASK10A_IMPLEMENTATION | 当前 provider/evaluator 未接线 |
| 候选 Live E2E／目标 camera／部署 | NOT_RUN／NOT_VALIDATED | 不能从已有离线结果外推 |

截至系统 `2745348`，正式 vision manifest v1 与 schema/file/hash validator 已交接，但 `TrainedProvider` 仍读取固定 MN/XGB 路径和旧 metrics，尚未消费 manifest；XGB 没有正式候选 importer。因此本轮交付边界是 **两视觉 package + XGB research_evidence**，RF/LR 不入包，stable 不替换。后续 provider 与离线 evaluator 属于既定系统 Task 10A，不被追加为 P5 静态包验收的 hard gate。此判断来自精确 Git 版本的[独立 runtime 审查](</Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/docs/fyp2/ml/research_notes/FYP2 模型 系统准入 审查/runtime_compatibility.md>)。

本轮已生成 [RN 候选包](/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/ml/outputs/runs/p5_candidates_20261023/p5_resnet18_search004_seed42_20261023.zip)与 [MN 候选包](/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/ml/outputs/runs/p5_candidates_20261023/p5_mobilenet_v3_large_search006_seed42_20261023.zip)，各含40份被 inventory 记录的文件及 inventory 本身；[final_package_check.json](/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/ml/outputs/runs/p5_candidates_20261023/verification/final_package_check.json)记录两包 schema/path/hash 与 graph 检查 **PASS**。完整 ML 软件回归 **302 passed in 36.00s**，原样系统 CLI 在隔离 snapshot 验证两包均 `valid / exit0`；独立审查 **59/59 PASS、failures=[]**，核对 ZIP CRC/安全路径、来源副本、逐行缓存与 clean 重算。369份受保护旧文件、14份源码快照、315份环境 metadata 指纹及144项包版本 inventory 保持一致；环境检查不等于整个 venv 全字节哈希。新增训练、HPO、forward、held-out inference、导出及 benchmark 均为0。P5 的四维验收据此为 **VERIFIED_PASS，限定 copy-only delivery、软件/静态检查及 artifact/source traceability**，不主张 clean-commit 或完整独立数值复跑。XGB 仅交付 [research evidence](/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/ml/outputs/runs/p5_candidates_20261023/telemetry_research_evidence)，无 checkpoint 或 runtime manifest。([测试日志](/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/ml/outputs/runs/p5_candidates_20261023/verification/full_ml_suite.log)、[CLI 命令](/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/ml/outputs/runs/p5_candidates_20261023/verification/validator_commands.json)、[独立审查](/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/ml/outputs/runs/p5_candidates_20261023/verification/independent_review.json)、[最终闭合](/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/ml/outputs/runs/p5_candidates_20261023/verification/final_closure.json)、[完整本地交付研究记录](</Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/docs/fyp2/ml/research_notes/FYP2 模型 系统准入 审查/local_evidence.md>))

P4A 已证明两 ONNX 在 **100 个固定 val 来源、211 个累计样本位置**上的 PyTorch–ORT parity，通过不等于新包的 provider 行为通过。正式 stable200 则为各类按 filename 排序取前20的另一集合；manifest 对它的声明或已有 val 预测诊断不能替代 provider 执行。预处理需保持项目的 RGB、直接 bilinear resize224、/255、ImageNet normalization、NCHW float32 与 logits/c0…c9 语义；架构名称不能代替实际合同。([RN parity](/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/ml/outputs/runs/p4a_20261021/parity_RN-HPO42.json)、[MN parity](/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/ml/outputs/runs/p4a_20261021/parity_MN-HPO42.json)、[runtime 合同审查](</Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/docs/fyp2/ml/research_notes/FYP2 模型 系统准入 审查/runtime_compatibility.md>))

## 额外 fine-tuning 应由目标域问题驱动

两视觉模型已从 ImageNet 预训练权重进行任务训练与 bounded HPO；当前训练实现优化全部 `model.parameters()`，不能描述为尚未 fine-tune 的现成模型。**目前没有证据证明必须继续 fine-tuning 才能交付 P5。** c9 弱项与潜在视角差异提出诊断问题，却没有证明再训练的收益。WILDS 的跨域研究支持源域表现不能代替目标域观察；本项目据此推论，若未来目标 camera 出现可重复失败，应先区分机位、标签、预处理及数据覆盖问题，再决定数据补充或 fine-tuning 的独立研究方案。它不提供本 FYP 的统一分数门槛，也不授权本轮新训练。([已完成训练与方法学审查](</Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/docs/fyp2/ml/research_notes/FYP2 模型 系统准入 审查/methodology.md>)、[WILDS 原论文](https://proceedings.mlr.press/v139/koh21a.html))

独立 agent 可据以下问题复核结论，问题本身不授权新实验。

| 独立 review 问题 | 主要证据入口 |
|---|---|
| 1. 候选是否始终为冻结 trial/seed42，未由 P4 重选？ | 两份 selection log |
| 2. 包是否保持 ONNX bytes/hash、预处理、logits 与 c0…c9 顺序？ | P4A export/parity、P5 manifest/verification |
| 3. 是否严格区分 P4A100、stable200 元数据及 provider 行为？ | runtime 审查、P5 validation 诊断 |
| 4. RN 优势是否被错误扩大为所有司机、条件或 stable 全面升级？ | P4 clean/driver/stress metrics |
| 5. 是否把低 flip/L1、合成高分或 QC removal 写成正确性证据？ | P4 flags、limitations 与原始统计 |
| 6. package、provider、system integration、Live 的状态是否各有依据？ | 精确系统版本与 P5 verification |
| 7. fine-tuning 是否仍为有目标域依据后再讨论的选项？ | methodology、冻结协议及本报告 |

## 结论

本科原型的合理下一步是让冻结候选接受可追溯的系统比较，而非追求一个脱离使用条件的“足够高准确率”。现有结果已支持这一研究进展；是否替换 stable，应由后续系统轨道在实际兼容路径与目标使用条件下回答。保留这些层次，使报告既能交代已经完成的工作，也能把尚未知的真实 camera 表现转化为清晰的后续问题。
