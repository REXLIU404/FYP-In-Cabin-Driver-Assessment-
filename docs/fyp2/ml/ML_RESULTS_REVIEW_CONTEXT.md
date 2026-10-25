# 给独立分析 agent 的 ML 结果 context（结果2026-10-19；选型分析更新2026-10-20）

用途：分析已经保存的五模型正式 validation/HPO 结果，核对结论与证据，并审阅下一阶段 E1 方法。本文是用户明确要求的分析 context；唯一进度报告仍是 `docs/fyp2/ml/ML_TRACK_PROGRESS.md`。本文不授予训练、下载、额外 HPO、held-out test/E1、部署、提交或 push 权限。

## 任务与边界

项目：In-Cabin Multimodal Driver Monitoring & Risk Assessment。ML 工作区 `/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1`，分支 `fyp2/ml-training`；正式视觉 search 执行 commit `335da4e3de203836c045452f84cc291bcd352a26`，执行记录为 tracked clean。本 context 生成时，S3 核验/P3 E1 准备为后续未提交改动；不得把当前 dirty state 倒推成原训练 dirty。

只读理解权威文件，按用户指示从当前仓库读取：

```bash
git show fyp2/live-system:docs/fyp2/review/CODEX_ML_TRACK_PROMPT.md
git show fyp2/live-system:docs/fyp2/review/CODEX_ML_TRACK_ADDENDUM_R4.md
```

较新的已批准执行细则：`.claude/worktrees/intelligent-chebyshev-836ed9/research/CODEX_ML_P2_P3_PROMPT.md`。优先级为用户当前批准范围 > 最新 P2/P3 执行细则 > R4 > 原 prompt > 旧准备计划/审计/sprint 参考。R4 限定 ML 仅 E1；E2–E5、backend/frontend/fusion/EMA/Alert FSM 属于系统轨道。不要进入 `/Users/liu/Desktop/FYP2-Live-System`。`docs/fyp2/09_INDEPENDENT_AUDIT_REVIEW.md` 为受保护 untracked 原报告，不修改、不删除、不暂存或提交。

P0 冻结；P1 三 comparator smoke；P2 comparator 首个完整配置；P3 五模型 bounded HPO/confirmation 与 E1 generator 准备；P4 冻结后一次 clean test 与正式 E1；P5 R4§3 候选包。每阶段停止等待批准。P2 首网格已计入 P3，不另加全量训练。

## 已得到的结果

全部下表为 **validation**，按模态比较。Vision 10 类 c0–c9，train15899/val2868，18/4 名 driver 不相交；telemetry 3 类 `Safe/Aggressive/Distracted`，train21000/val4500，合成数据，固定8特征。所有选型和 early stopping 用 validation，冻结模型均为 seed42；43/44 只作确认，不重新择优 seed。

| 模型 | 选中 trial / 配置 | seed42 accuracy | seed42 macro-F1 | 选中配置确认 mean ± std(ddof=0) |
|---|---|---:|---:|---:|
| MobileNetV3-Large | search_006；lr .0008 / wd .001；best epoch6 | .9229428173 | .9162198680 | .8936628163 ± .0159504608 |
| ResNet18 | search_004；lr .0003 / wd .001；best epoch3 | .9421199442 | .9406150485 | .9247975522 ± .0271136326 |
| XGBoost | xgboost_02；depth3 / lr .03 / subsample1；400 trees | .9988888889 | .9988888884 | .9988888884 ± 0 |
| Random Forest | random_forest_06；400 trees / depth24 / min_samples_leaf2 | .9988888889 | .9988888884 | .9988888884 ± 0 |
| Logistic Regression | logistic_regression_06；C1000 / lbfgs；train-only imputer+scaler | .9968888889 | .9968885811 | .9968885811 ± 0 |

Vision seed scores：MobileNet `[.9162198680081481,.8824860851282594,.8822824958402411]`；ResNet `[.9406150484662007,.9471390721342718,.8866385360192561]`。LR seed43 是确定性重复，不独立，44 按预注册规则跳过；XGB/RF 三次 macro-F1 相等也不等于所有概率逐位相等。选中 seed42 log-loss 依次为 `.306039094925/.186423733830/.004925716203/.008043999630/.008746305336`。

视觉6组配置/模型 + seed43/44确认，共16实际训练、81 epochs，全部成功。预算 `per_trial2400 / MobileNet17100 / ResNet15300 / total32400 s`，实际 `8244.061593375 / 7041.178746042 / total15288.353217291 s`，excluded=[]。遥测25次实际 fit（XGB10/RF8/LR7），合计41次正式 fit/训练。P1 smoke 和 probe 不计入正式 HPO，也不是性能对照。剩余时间不是追加实验授权。

旧部署 baseline 为 MobileNetV3-Large 与 XGBoost，始终保留。存储的旧 validation macro-F1 分别为 `.8906507716026614` / `.9984444432338747`，仅 `STORED_NOT_RERUN`。P1 的 ResNet random-init smoke、单 epoch probe、旧 baseline 和本次正式 HPO 不得混合排名。两种视觉 ImageNet recipe 是 MobileNet V2 / ResNet V1。

## 建议分析的核心问题

1. 现有 val 中 ResNet seed42 高约2.44个百分点、三seed均值高约3.11个百分点，但波动也较大，尤其 seed44。三点 std 不是 CI/显著性证明；同 val 被用于选配置/epoch，再报告该 val 有选择乐观性。不要改选最高 seed43，也不追加确认训练。
2. 类级并非全面占优：MobileNet c9 F1 `.669767442` vs ResNet `.877637131`；c0 则 `.866556837` vs `.840531561`。查看原报告支持数、recall 与 confusion，分析失败类别，不把 macro-F1 变成真实驾驶风险改善。
3. MobileNet checkpoint17052801 bytes，ResNet44803787 bytes，约2.63倍。这是保存文件大小，不是 ONNX 大小、部署 RAM 或实测推理时延；当前没有匹配部署环境的 latency/吞吐证据。预训练 recipe 不同，差异不能全归架构。
4. 合成 telemetry 上 XGB/RF 接近天花板且 LR 也很高。可以说此数据任务较容易，不能宣称真实驾驶99.9%准确率或安全收益；零std不证明自然域稳定。RF/LR 仅 benchmark，不进入候选包。
5. 当前没有本轮 held-out test 或正式 E1。旧 test 曾多次评估（R27），不能称从未见过；现有审计未发现直接用 test 选参的代码。R26 上游 EDA 全量 median 与本流水线 train-only imputer provenance 有区别，但原始8特征无NaN，不能声称旧 .9993 被污染。
6. P4 须按冻结模型身份去重、明确适用 baseline 对照；固定 shared IDs/变换/mask，独立 recognizability QC 后才能把变换样本纳入 F1；无效标签仍保留 flip/distribution。Vision 按 driver/clip cluster，4个test司机限制推断；telemetry D2 是 label-conditioned stress，非自然 domain shift。DMD 仍 BLOCKED。

## 用户补充：请明确分析应该选什么 model

用户要求其他agent同时分析“刚刚的训练/HPO结果，应选什么model”，而不只核对证据或讨论E1准备。请基于上表和原始保存产物给出明确建议，并区分三个问题：

1. **Validation层面的优先模型**：vision在MobileNetV3-Large/ResNet18之间、telemetry在XGB/RF/LR之间分别推荐谁？写明依据和代价，不能只抄最高单次分数；同时列出被保留的比较模型。冻结的每架构配置和seed42保持不变，建议不等于修改selection log。
2. **后续候选评估**：哪些是值得继续检验的候选，尚缺哪些test/E1、兼容性和目标硬件运行证据？按现有预注册的val目标提出建议；不要事后用c0指标、文件大小或未取得的test表现另造排名规则。P4是冻结后的评估，不能再拿test/E1调参或择优seed。
3. **当前Live System使用谁**：明确旧部署MobileNet+XGB与本次tuned模型的身份差异；如建议暂留旧部署，应给证据/阶段原因。R4规定RF/LR只benchmark。模型推荐不等于批准替换部署或生成候选包。

期望输出一张表：`modality / 推荐架构与trial / 主要证据 / 不确定性与权衡 / 当前部署建议`，再回答ResNet的较大seed波动与c0弱项是否改变建议、XGB/RF近似并列应如何解释。结论请区分validation观察和最终部署决定。刚完成的190/300条生成器检查没有model forward或新性能分数，不能用于声称某模型更robust。其他agent应独立检查原始指标后表达判断，可以不同意本context中的解释，但须提供依据。

## 已完成的独立模型选择分析（2026-10-20）

已由`vision_model_choice_review`与`telemetry_model_choice_review`分别只读审阅两种模态；主agent复核原选中trial的metrics/class reports、selection logs及数值差异。以下是**现有validation证据下的建议**，未修改任何冻结配置/seed、原始选型日志或模型文件，也没有运行新实验。

| 模态 / 模型 | 建议与冻结身份 | 主要依据 | 权衡 / 当前部署建议 |
|---|---|---|---|
| Vision / ResNet18 | **下一阶段优先评估的视觉候选**；`search_004` / seed42 / best epoch3 | seed42 macro-F1 .940615，比MobileNet高2.4395个百分点；三seed均值 .924798，高3.1135个百分点；log-loss .186424更低 | std .027114较大，c0召回较弱，checkpoint较大；尚无正式test/E1、兼容性/目标硬件时延证据，不自动部署 |
| Vision / MobileNetV3-Large | **保留既定配对比较模型**；`search_006` / seed42 / best epoch6 | seed42 macro-F1 .916220、确认均值 .893663；c0 recall .900685高于ResNet .866438；checkpoint17.05MB vs44.80MB | 不能由文件大小推断时延；c9较弱。旧部署MobileNet baseline继续保留，与本次tuned checkpoint分开 |
| Telemetry / XGBoost | **遥测架构首选 / 后续离线评估优先对象**；`xgboost_02` / seed42 | 与RF accuracy同为 .998888889，各错5/4500条；log-loss .004925716低于RF .008044000 | 与RF macro-F1只差约4.94e-13，视为实质持平，不宣称分类或统计显著胜出。继续使用旧部署XGB，不替换为本次joblib benchmark产物 |
| Telemetry / Random Forest | 保留对照；`random_forest_06` / seed42 | macro-F1与XGB实质持平，提供另一类树模型比较 | 按R4只benchmark，不进入候选包；与XGB不一定错同样的记录或拥有相同概率 |
| Telemetry / Logistic Regression | 保留简单对照；`logistic_regression_06` / seed42 | macro-F1 .996888581，错14/4500条；说明合成任务用线性分类器也接近满分 | 较XGB约低.2000个百分点；seed43确定性重复不独立。按R4只benchmark，不进入候选包 |

**视觉判断：**独立审阅支持优先ResNet，不支持“全面优于MobileNet”。c9 F1从 .669767提高至 .877637、recall从 .564706提高至 .815686；c0 F1从 .866557降至 .840532、recall从 .900685降至 .866438（support292，少正确识别10张c0图像）。这是分类层面的权衡，不是Live告警率测量。它不构成事后重写macro-F1主目标或挑seed43的理由。三seed std不是置信区间，确认均值也不取代被冻结的seed42 checkpoint。两模型仍须保留在已批准比较设计中。

**遥测判断：**优先XGB是基于近似并列的分类表现、更低的validation log-loss及既有架构范围，不是声称其准确率超过RF。合成数据、共享validation选型及零std限制真实域结论；更低log-loss不能单独证明概率校准。RF/LR的benchmark角色不是新加的性能门槛。所有本轮遥测trial当前均记录`benchmark_only=true`；tuned XGB的`checkpoint.joblib`也不等于已部署的`ml/outputs/telemetry/xgb_telemetry.json`，本次建议不改变导出/部署权限。

**当前可执行结论：**研究评估优先关注 **ResNet18 + XGBoost**；Live System继续保留 **旧MobileNetV3-Large + 旧XGBoost**。两位独立审阅均未建议丢弃其他比较模型或追加训练。P4/P5依旧等待单独批准，未来test/E1只能评估已冻结模型，不能反过来调参/择优seed。其他agent可在这份完整context上继续质疑和复核上述建议。

支持上述数值的原始文件为vision根`selection_log.json`与两个选中trial的`class_report.json`，telemetry根`selection_log.json`与`xgboost_02`、`random_forest_06`、`logistic_regression_06`的`validation_metrics.json`；完整相对路径见下表，精确汇总见`verification/validation_metrics.json`。

## 原始证据入口

所有相对路径均以 ML 仓库根为起点。优先核验下列文件，再作结论，不仅阅读本 context。

| 路径 | 内容 |
|---|---|
| `ml/outputs/runs/p3_vision_20261018/verification/validation_metrics.json` | 五模型精确指标、选型配置、checkpoint路径/bytes/SHA、旧baseline来源 |
| `ml/outputs/runs/p3_vision_20261018/search_state.json`、`selection_log.json`、`search_config.json` | 完成attempt、预算/选型/执行commit与源码来源 |
| `ml/outputs/runs/p3_vision_20261018/search/<model>/<trial>/attempt_01/` | checkpoint、config、sample_manifest、保存val logits/probabilities、class_report/confusion、epoch/timing logs、manifest |
| `ml/outputs/runs/p3_telemetry_20261018/` | 遥测25实际fit、selection/trials、每trial保存val结果、train_statistics和执行源码snapshot |
| `ml/outputs/runs/p3_vision_20261018/verification/artifacts/verification.log` | 5276断言、0失败；176视觉+250遥测产物hash，16 PT finite/head/metadata；仅CPU weights_only读取，无forward |
| `ml/outputs/runs/p3_vision_20261018/verification/predictions/execution.log` | 2249断言、0失败；45888条保存val预测及96输入hash；class/order/metrics独立复算 |
| `ml/outputs/runs/p3_vision_20261018/verification/protocol/verification.log` | 557/557；grid/81epochs/选型/预算/clean commit核验 |
| `ml/outputs/runs/e1_preparation_20261019_record_missingness/` | 最新P3准备：10 val图像→190变体、30 val遥测→300变体，记录级5/10/20%实际2/3/6条各缺1特征，参数/IDs/hash/mask、0fit/0forward、QC未判定；3761产物checks，不是正式E1性能 |
| `ml/configs/e1_preparation.json` | 固定强度与准备示例；D3记录级缺失率方案已由用户指定为proposed，整体P4协议仍待冻结；方向/物理边界/裁切细节/QC尚待决定 |
| `docs/fyp2/ml/ML_TRACK_PROGRESS.md` | 唯一规范进度，最新章节优先于保留的历史快照 |

核验脚本与日志同目录，可先读脚本。预测审计初版32个误报来自 validator 对原metadata索引的误解，原日志保留、修正后通过，没有改训练输出。全部核验断言数不等于重训次数。历史 probe/遥测源码须使用其保存 snapshot，而非假定当前HEAD就是当时源码。

## 当前停止点与期望输出

用户已批准 S3 后下一步，本轮仅推进 P3 E1 generator/QC接口准备：初稿42项测试RED→GREEN；用户明确D3记录级语义后另先复现4项失败，再修复至44项新增测试通过、完整 ML suite176 passed（21.25s），3761产物checks；只使用 synthetic/validation。生成器与共享预处理/掩码验证有实际证据；独立人工QC、正式协议freeze、held-out执行仍未完成。P3软件准备可以通过，整体正式E1准备仍 `PARTIAL / APPROVAL_PENDING`，P4/P5没有执行授权。

**用户最新D3决定：**5%/10%/20%是受影响**记录**的比例，每条受影响记录随机mask恰好8特征中的1个；seed42、XGB/RF/LR共享同一mask、train-only median。按source-ID seeded hash排序取嵌套prefix，整数人数用`floor(N*rate+0.5)`，特征按source-ID seed42抽取并跨severity固定。4500条synthetic fixture的实际计数恰225/450/900；30条val为2/3/6，首档实际6.6667%，已记录requested/realized而非伪称恰5%。参数仍为**proposed**，整体P4协议freeze前不正式执行。

最初`e1_preparation_20261019/`采用逐特征独立缺失，仅是已被取代的准备草案；`superseded_protocol.json`与`source_snapshot/`保留旧代码/配置/日志。请使用`record_missingness` run分析当前实现，不能把旧D3结果混入新方案。用户明确要求本轮完成P3准备后停止，禁止held-out读取、正式E1或进入P4。

请按 Implementation / Testing / Evidence / Reproducibility 分析：哪些结论成立、哪些表述过强、证据缺口及 P4 方法应如何冻结。建议针对已有证据和下一阶段协议；不要自动运行训练/test/E1、改选模型/seed、扩预算或改部署文件。用中文回复，区分“validation观察”“方法建议”“已验证结果”“仍待批准”。
