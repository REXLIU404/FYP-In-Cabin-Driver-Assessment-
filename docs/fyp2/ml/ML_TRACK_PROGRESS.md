# FYP2 ML 轨道进度（唯一规范进度报告）

## 2026-10-18 最新执行记录：S1 交付与 Week 3 验收

本节覆盖下方2026-10-15的历史审批状态；旧日志与历史结论原样保留。用户明确要求执行 `.claude/worktrees/intelligent-chebyshev-836ed9/research/CODEX_ML_P2_P3_PROMPT.md`，并要求核验 Week 3。授权为遥测CPU P2/P3、视觉脚本/测试/说明以及C1–C6本地提交；代理不得执行视觉训练、下载、P4或P5。视觉search具体预算需probe后另批。

第1节开工检查：cwd/root正确，branch=`fyp2/ml-training`，初始HEAD=`efb3ea6`。58项status逐路径比对全部吻合：7删除、1 ignore修改、09报告、5个P0文件、44个P1文件；`unexpected=[]`、`missing=[]`、暂存区为空，另一个只读agent独立核对通过。P0八项保护SHA-256 **8/8一致**。其中test CSV仅按开工要求做字节hash，未解析、选型或预测；训练阶段不重新打开test。两份原权威说明均从当前仓库git show完整读取，未访问Live-System工作区。

已完成提交：C1=`a8e5da7`（仅ignore），C2=`bb3e6cd`（P0五文件原样），C3=`644a930`（P1四十四文件原样），C4=`48b7980`（用户决定的七删除），C5=`07d3390`（仅预注册config）。每次核精确暂存路径、无模型二进制/符号链接/单文件>5MB；09报告从未暂存。C3保留历史RED日志中的pytest尾空格，不清洗原始证据。C1首次自动审批误判非空工作树/授权后拒绝；补充任务明确授权及58项匹配证据，同一动作重试获准。未绕过审批，未push/merge/reset/stash或切分支。

预注册已提交，状态`PREREGISTERED`：原五模型grid/search_trials/max_total_runs/epoch上限逐项比较未变。各模型首个网格seed42为P2并计入P3预算；选型仅val，macro-F1差`<1e-4`比log-loss、复杂度和trial号；冻结seed42，确认43/44不重选。遥测每trial300s/合计2700s/线程2；视觉probe每模型1200s/合计2400s，不计HPO/不选型。此前100/190分钟P2提案被本次明确授权替代。未创建`approved_vision_budget.json`。

### 真实执行与结果

本次 run_id=`p3_telemetry_20261018`，训练时 HEAD=`07d3390`，branch=`fyp2/ml-training`；训练源码当时尚未提交，完整dirty snapshot和源码SHA均写入run/worker config。当前交付提交为任务规定C6（提交号以最终git log为准）。没有额外正式模型重跑。

关键实际命令：

```bash
./.venv/bin/python -B -m pytest -q ml/tests/test_comparator_pipeline.py -p no:cacheprovider
./.venv/bin/python -B -m pytest -q ml/tests/test_hpo_protocol.py -p no:cacheprovider
./.venv/bin/python -B -m pytest -q ml/tests/test_telemetry_hpo.py -p no:cacheprovider
./.venv/bin/python -B ml/experiments/run_telemetry_hpo.py --run-id p3_telemetry_20261018 --data-root /Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment-
./.venv/bin/python -B ml/outputs/runs/p3_telemetry_20261018/verification/verify_artifacts.py
./.venv/bin/python -B ml/outputs/runs/p3_telemetry_20261018/software_verification/verify_week3.py
./.venv/bin/python -B -m pytest -q ml/tests -p no:cacheprovider
./.venv/bin/python -B ml/experiments/run_vision_hpo.py status --run-id p3_vision_20261018
```

遥测完整train=21000、val=4500，固定8特征/3类，CPU两线程。外层真实墙钟 **68.61661075 s / 2700 s**，最慢trial **4.898389542 s / 300 s**。26个计划记录中，实际 **25 fits = XGB10 + RF8 + LR7**；24条`COMPLETED`、1条`DETERMINISTIC_DUPLICATE`、1条`SKIPPED_DETERMINISTIC_DUPLICATE`。没有失败、超时、中断、NOT_RUN_BUDGET或额外训练；LR seed43概率与选中seed42完全相同，因此按批准规则不运行44。重复运行消耗实际fit数，明确不算独立证据。

| 模型 | 冻结seed42 trial / 配置 | Val accuracy | Val macro-F1 | Val log-loss | 确认macro-F1 mean / std(ddof=0) | 实际fit / 最大RSS |
|---|---|---:|---:|---:|---|---|
| XGBoost | `xgboost_02`：depth3、lr.03、subsample1、实际用400棵树 | 0.998888889 | 0.998888888395 | 0.004925716203 | 42/43/44：0.998888888395 / 0 | 10 / 216776704 bytes |
| Random Forest | `random_forest_06`：400棵树、depth24、min_leaf2 | 0.998888889 | 0.998888888395 | 0.008043999630 | 42/43/44：0.998888888395 / 0 | 8 / 215252992 bytes |
| Logistic Regression | `logistic_regression_06`：C1000、lbfgs、max_iter1000（实际16迭代） | 0.996888889 | 0.996888581119 | 0.008746305336 | 42/43：0.996888581119 / 0；43非独立重复，44未跑 | 7 / 193019904 bytes |

以上仅val结果。std=0只描述本次所列seed的macro-F1，不能证明概率逐位相同或真实世界稳定性。RF/LR checkpoint仅用于benchmark，未创建候选包或部署。没有引用test指标作本轮对照。

独立agent执行保存产物核验：**4987 checks / 0 failures / 2.648646 s**，包括250条artifact记录的exists/bytes/SHA、25个checkpoint的独立重载val预测、train-only median/LR mean/var/scale、val IDs/顺序/标签、CSV/npy、class order、全部metrics/class reports、选型重算及资源/次数上限。RF并行求和的独立重载最大差`1.1102230246251565e-16`，满足原`atol=rtol=1e-12`合同；没有把allclose说成bitwise equal。验证没有任何fit，没有打开test。核验原始输出和可重跑脚本位于`ml/outputs/runs/p3_telemetry_20261018/verification/`。

### 软件验证、审查修复与源码身份

完整ML软件套件 **103 passed / 16.46 s**（P1原36项 + protocol19项 + telemetry23项 + vision orchestration17项 + vision worker8项）。没有把它称为全仓库CI、Live E2E或真实MPS训练验证。视觉指定六项门禁通过fake设备/合成文件测试：无预算拒绝、无MPS拒绝、跳过已完成、保留INTERRUPTED、不覆盖完成目录、墙钟停止；另覆盖篡改产物和启动调度开销。

两名实现agent中途遇到usage limit，主代理接手其测试；交付依据是后续实际测试/产物，不是agent完成声明。独立代码审查指出两项Important，均已单次修复并验证：

1. 遥测双层独立process group在相同终止宽限下可能留下忽略TERM的worker。纯heartbeat假进程回归先失败，再改为coordinator/worker共享外层group、内层只终止worker、外层最终清理整个group；回归及103项suite通过。实际25次训练远低于截止，没有发生该故障。**修复在训练后，不重fit**。
2. 视觉resume原先只信COMPLETED状态。删除/篡改合成checkpoint的两项回归先失败，修后跳过前逐文件核必需产物及SHA；损坏即停、不自动重训。回归及完整suite通过。

另一个训练前修复保留内层TIME_BUDGET_EXCEEDED，防止外层非零exit把它误标IMPLEMENTATION_FAILED；视觉调度/写config开销也有RED→GREEN回归，不能追加在trial预算之外。原始RED/GREEN日志都在`software_verification/`，不清洗捕获输出。最初runner RED包含14 failed / 21 missing-module fixture errors；这些不是模型fit失败。后续边界回归均实际失败后修复。

监督器修复导致`source_current_match=false`；**这不是训练产物哈希失败**。训练前实际执行的5份源码/config已在修复前逐字节保存到`source_snapshot/<原仓库相对路径>`，与原config SHA全部吻合，独立核验`source_snapshot_match=true`。原config/log/source_hashes均未改写；不能把修复后的监督器冒充实际生成这25个模型的代码。其余训练方法/参数未变。

### Week 3 是否完成：VERIFIED_PASS（ML milestone 已提前完成）

- **Implementation PASS**：三种comparator的P1 reusable trainer/loader、预处理/保存重载，以及预算监督器已存在；原P1四份执行源码SHA当前均未变。
- **Testing PASS**：本次重新运行原P1 suite，**36 passed / 7.60 s**；已有三个真实首轮smoke均为PASS，没有追加smoke。ResNet18 train200/val100、每类20/10、1epoch；RF/LR train300/val90、每类100/30、各1fit。重新检查sample_manifest确认分层数量与ID唯一。
- **Evidence PASS**：重新验证32条保存产物记录的存在/bytes/SHA和三模型保存预测的accuracy/macro-F1/log-loss；训练/validation/reload原始日志、模型二进制、class order与输出维度仍一致。证据为`software_verification/week3-verification.log`和原P1 run；历史85项核验未冒称本次重跑。
- **Reproducibility PASS（原P1限定范围）**：seed42、源ID/配置/软件版本/统计/哈希和原save/reload证据可追溯；本次没有独立P1数值重训或新增forward。ResNet18仍是获批random-init smoke，**不用于正式性能比较**。

本结论只验收Week3的ML comparator scripts + smoke，不能代替系统轨道Week3、完整视觉训练、五模型比较、E1、UAT或安全效果验收。

### 最新阶段状态、限制与停止点

| 阶段 | 当前四维验收 / 实际证据 | Verdict / 下一依赖 |
|---|---|---|
| P0 / W2准备 | 数据/模型/契约冻结已验证；网格/seed/tie协议已预注册，遥测预算获批；完整视觉预算故意留S2 | 技术准备PASS；总体仍PARTIAL，视觉数字预算APPROVAL_PENDING |
| P1 / W3 | implementation、testing、evidence、限定reproducibility均PASS，36项当前测试+真实smoke+保存产物复核 | **VERIFIED_PASS**，已提前完成 |
| P2 | 遥测首网格全量fit已完成；ResNet18用户终端正式fit尚未运行 | **PARTIAL**，等待用户fetch-weights/probe与S2预算 |
| P3 | 遥测三模型HPO/确认/冻结/独立核验PASS；视觉CLI与103项软件验证PASS；真实视觉search未运行，E1 generator未实现 | **PARTIAL**，不能称五模型HPO完成 |
| P4 | 最终test/E1均未运行 | **NOT_STARTED / 未授权** |
| P5 | 候选包/部署均未执行 | **NOT_STARTED / 未授权** |

视觉交付：`ml/experiments/run_vision_hpo.py`、`ml/vision/train_hpo.py`、fake-device tests及唯一新增的必需说明`docs/fyp2/ml/RUN_VISION_HPO.md`。实际只执行status，输出`NOT_STARTED p3_vision_20261018`；没有创建该run目录，没有下载权重，没有运行probe/search。真实MPS训练路径为**IMPLEMENTED_UNVERIFIED**，需要用户终端probe验证。`approved_vision_budget.json`不存在。

本次说明明确允许中断后同一逻辑trial从头重跑，因此视觉可能有多个physical attempts；每个attempt保留且累加预算，不增加网格或正式逻辑trial上限。这是最新第5节对中断重跑的明确授权，不能外推为失败自动重跑或额外HPO。第1节test CSV hash完整性核验与第4节训练禁读test分开执行，未声称字节hash等于“完全没有接触文件”。

R26披露继续有效：外部EDA曾在split前算median；本次每个trial仅train fit imputer/scaler，不修改源CSV；保留8特征没有NaN，不据此声称旧基线被污染。R27：test曾被多次评估，本轮未解析或推理test，也未用于选型。Telemetry为合成数据，近似线性可分，高val分数不证明真实泛化或事故风险改善。MobileNetV3 V2与ResNet18 V1配方差异、MPS固定seed不保证逐位复现必须保留披露。E2–E5/融合/前后端/Live runtime均未修改或执行；DMD仍blocked，不是新增W3 gate。

**停止在S1**：C6提交本次代码/小证据后等待用户在终端执行`RUN_VISION_HPO.md`中的fetch-weights/probe命令并贴回`WEIGHTS_READY`、`PROBE_COMPLETE`、`VISION_STATUS probe`行。S2先核验probe再请求批准具体per_trial/per_model/total秒数；S3用户完成search后再核验。绝不自动开始视觉训练、P4或P5。W5/W7主里程碑不变。

## 以下为 2026-10-15 的历史过程记录（审批状态以本页开头为准）

更新日期：2026-10-15；时区：Asia/Kuala_Lumpur。当前 run_id：`p1_comparators_20261015`；P0 历史 run_id：`w2_preparation_20261015`。

## 最新验收复核：四维标准、Week 2 与 P2 待审批方案

复核日期：2026-10-15。**Week 2 ML 总体验收仍为 PARTIAL；数据/模型冻结及技术准备已验证，正式预算/协议审批尚未闭合。P1 原八项 smoke 验收继续为 VERIFIED_PASS。P2 没有开始。** 本轮只读取规格、代码、日志、模型产物和资源信息，仅修改本规范报告；没有新 classifier fit、模型 forward、smoke、权重下载或 HPO，也没有改写旧 run evidence。

权威规格完整重读于当前仓库的 `git show fyp2/live-system:docs/fyp2/review/...`，并以不可变 commit `50bddefe4286949c3a6ea16b1baf15a42ca3f6f7` 复核内容：Prompt SHA256=`53c53b82777d6376189a3e6e208d18977dc0047fa4359538c103f01d8c509b48`；R4 SHA256=`5a46fec48facec1fb8f92fea4446956089f6d3c2573fefe53296d59865dc55ff`。与 P0/P1 保存的内容一致；历史 `cbe573...` 是当时的真实快照，不改写它。没有进入 Live-System 文件夹或切换 branch/worktree。

### 四维判定规则与规格冲突裁定

- **Implementation**：本阶段功能、隔离和门禁确实存在且符合批准范围；规划文字或空配置不能代替实现。
- **Testing**：本阶段应执行的验证实际执行并记录结果；以各阶段范围界定测试，不把旧系统 CI、E2–E5 或未来 final test 当作本阶段 gate。
- **Evidence**：source IDs、配置/seed、软件/源码/模型/split hashes、命令、日志、实际时间和输出可核对。只能对有证据的范围声明通过。
- **Reproducibility**：输入及抽样可重建、recipe/环境/命令/计数可追溯、序列化可验证并能复算已保存结果。它与“独立重新训练后数值完全相同”分开记录；后者当前 NOT_RUN，不假称已证明。

四维标准是用户本次批准的验收框架；P0–P5 编号及边界来自本会话的安排，并非 R4 原有编号。阶段总 verdict 同时考虑四维与审批条件：准备产物可以已经通过技术验证，但预算审批未完成时总 verdict 仍 PARTIAL / APPROVAL_PENDING。不能通过本次复核自动授权下一阶段。

需要明确的冲突/边界：

1. R4 把原 Prompt 的 E1–E5 收窄为 **E1 only**，优先级不变。E2–E5、fusion/EMA/FSM、前后端和 Live runtime 不加入任何 ML 阶段验收。
2. Prompt 的“每次运行有 test predictions”须同时服从“选型冻结后 final test 一次”：P0–P3 标 **NOT_YET_DUE**，P4 生成，P5 引用；不得为了凑文件在 P1/P2/P3 提前跑 test。
3. P1 用户授权明确允许缺预训练时 random-init smoke、batch16、RF20/depth6、LR max_iter200；这些例外**只适用于 P1**。P2 不能把它们继承为正式比较 recipe，正式参数回到审计04/R4 的有限空间。
4. 不追加“成功 P1 再训练一次才能通过 reproducibility”的硬 gate：这与成功后不得追加 smoke 的预算授权冲突。当前 P1 通过范围是已记录运行、独立抽样/统计重建与 serialization/reload；若以后要求独立数值重训，必须另行批准范围和预算。
5. 不新增 comparator 必须胜过 baseline、E1 必须改善、校准、DMD 解锁、全新 external holdout、目标 camera/edge 实测、MPS 必须可用或 UAT/全系统 CI 等硬 gate。继承 F1 targets 可在最终结果报告达成/未达；R4 未规定“每个 comparator 达标才算完成合法训练”。
6. P4 须在执行前冻结模型清单，包含 untouched baseline 对照；若 selected MobileNet/XGB 与线上版本不同，提前列明原 baseline 的配对预测范围，按 checkpoint identity 去重。不能到 P5 临时追加 held-out inference；既有 test 曝光继续披露。
7. P5 完整执行 R4 §3，另保留原 Prompt 要求的 model card。`runtime_manifest.json` 与 `evaluation_metrics.json` 分开，不把评估指标当 loader 前提；最终 Task10A schema/系统行为检查的归属与 ML 验包区分，不在旧 ML branch 冒充系统轨道验收。

### P0–P5 最终四维验收矩阵

表中列出阶段标准及现有状态；未来标准不是执行授权。

| 阶段 / 保留边界 | Implementation | Testing | Evidence | Reproducibility | 当前总 verdict / 审批 |
|---|---|---|---|---|---|
| **P0：安全、冻结、HPO 准备** | split/model/class/feature/preprocess、隔离输出与 ignore、五模型 finite-grid 草案具备；技术项 PASS | 司机 disjoint、hash/schema/缺失重复、路径与 train-only 方法核验；历史75项 PASS，当前8项保护hash复核匹配 | P0 config/evidence、环境/数据 provenance、真实审批缺口齐全；PASS | 准备命令、源码/版本/seed、source ID规则可追溯；冻结条件 PASS，无模型训练要求 | **PARTIAL**：正式 HPO wall caps、seed/tie/资源方案尚待冻结审批；不把 P2 权重实际下载追加为 W2 hard gate |
| **P1：三个 comparator pipeline + 批准 smoke** | ResNet18/RF/telemetry LR、train/val-only、train-fit、安全保存/reload和门禁；PASS | 批准样本/steps/fits/time内通过原八项；36 tests、三个真实首轮 smoke；PASS | 原始 logs/config/IDs/trials/timings/predictions、二进制存在/hash、实际结果；PASS | 本次独立抽样/统计/预测结果复算与保存/reload记录一致；**PASS（限定范围）**；独立重训数值复现 NOT_RUN | **VERIFIED_PASS**；已批准且完成，仅 pipeline smoke，不是正式比较 |
| **P2：三个 comparator 完整单配置训练** | 先实现获批 full mode；固定正式权重/recipe、全量 train/val、合法预处理；当前 NOT_STARTED | epoch/fit/wall门禁、val macro-F1/类报告、finite/shape/order、保存检查；不访问 test/E1；NOT_STARTED | 每模型 formal config、trial ledger归属、val predictions/报告、checkpoint/hash、train-only统计、实际资源；NOT_STARTED | source IDs/hash、预训练hash、seed/设备/线程/命令固定，不新增重复训练；NOT_STARTED | **APPROVAL_PENDING**，不得启动 |
| **P3：五模型 bounded HPO + E1 generator 准备** | 五个指定模型均参与；有限搜索/confirmation/selection；确定性 generators/QC protocol；NOT_STARTED | val macro-F1跨trial排名；XGB内部early-stop指标另列；budget/test隔离；generator用toy/validation软件测试验证参数/字节/计数；NOT_STARTED | actual trials及未完成状态、val类报告、selection freeze、train-only stats、generator版本/参数；NOT_STARTED | 共用冻结split；确认seeds/tie policy；LR随机性条件判断；生成输入可重建；NOT_STARTED | **NOT_STARTED**，须独立批准；正式 held-out E1 留P4；预算内安全停止不等于完整grid coverage通过 |
| **P4：冻结后的 final clean test + E1** | 冻结模型清单一次 final clean test；E1-V6×3、E1-T4500×10=45k；NOT_STARTED | 共用source IDs/seed42/逐字节输入与masks、recognizability QC、train-only统计、driver/clip cluster；test/E1不重新选参；NOT_STARTED | 带ID的clean/stress预测、logits/prob语义、类报告/confusion、paired变化、QC/排除、45k/mask计数与原始timing；NOT_STARTED | held-out manifest/generator/params/hash/方法冻结，已保存结果可复算，无额外final forward要求；NOT_STARTED | **NOT_STARTED**，须独立批准；标签失效限制和不利结果均照实报告 |
| **P5：candidate package + evidence freeze** | R4§3完整自包含包、独立两份JSON、真实mapping/预处理/logits/I/O/路径/hash/run/commit与model card；NOT_STARTED | 按Task10A最终schema验包，float32动态NCHW224、input/logits、无内置softmax、路径/hash与标注行为证据分工；NOT_STARTED | val/selection/带ID test predictions、metrics/model card、文件hash与来源齐全；NOT_STARTED | 包内artifact独立可核，禁止symlink/外部文件依赖；PT weights_only；RF/LR pickle/joblib绝不进候选包；NOT_STARTED | **NOT_STARTED**，须独立批准；不自动部署或替换稳定baseline |

### P1 本次实际证据复核（不是依据 planning 文档的 PASS 标签）

两项独立只读子审查分别核对权威标准和 P1 evidence。本次确认：32个 worker artifact 的 existence/bytes/SHA256、四份执行源码hash、测试源码hash、五份软件日志hash、四项线上模型/受保护review hash全部匹配；P0八项保护hash也重新核对一致。冻结 telemetry_test CSV仅做字节hash完整性检查，没有解析、预测或选型。

从源 train/val CSV 和 vision membership 的 train/val 行，以 seed42 独立重建三模型 source_row/ID/label/driver/path/顺序，全部匹配；300张选中的 train/val 图片仅读字节核hash，一致。RF/LR median与LR mean/scale从train300重算一致；保存 validation CSV 的概率单纯形、argmax、confusion、accuracy/macro-F1/logloss，以及vision logits→softmax重算匹配。PT只用weights_only读取：head `[10,512]`、122个state tensors均finite。没有新fit/forward，没有加载joblib，没有重跑现有会覆盖旧evidence的校验脚本。

| 模型 | 实际run证据 | 当前二进制（bytes / SHA256） | 结论 |
|---|---|---|---|
| ResNet18 | 200train/100val、10类分层、epoch1、13train+7val+1reload；CPU2；21.757676s/600s；reload差0 | 44803723 / `a0e82bdb55266554a821b4cf8142d2e049be7d21c71ec2afa81f32265bae9640` | 原八项 PASS；random-init 非正式比较 |
| RF | 300/90、三类分层、fit1、20trees/depth6/n_jobs2；1.541931s/120s；reload差1.11e-16 | 51274 / `3e8ef64f91446ac5a4978653008da75f04753753dc6a91b62ba3f5900691175c` | 原八项 PASS；benchmark-only artifact |
| LR | 同RF source顺序、fit1、lbfgs/max_iter200、n_iter16；1.464323s/120s；reload差0 | 2449 / `0b5b3af85033a678770d4c57526a32fc7e6c47690a91edd58df01db652c475d1` | 原八项 PASS；benchmark-only artifact |

组合26.110907s/1200s、attempts3、rerun0；原始绿色日志36 passed/6.66s、保存产物核验85 passed仍可核对。本次没有冒称重新执行36/85套验证或重新训练。Hash一致不能证明未来重新生成二进制必然逐字节一致；reload只证明serialization的一致性，vision原reload覆盖16张同批。该限制不被藏在 VERIFIED_PASS 标签里。

### P2 资源先决条件：实际确认与未测范围

2026-10-15 17:45–17:47（Asia/Kuala_Lumpur）使用既有 `.venv/bin/python -B` 做只读probe：

| 项目 | 当前证据 | P2 方案 / 限制 |
|---|---|---|
| CPU / 内存 | 原生sysctl确认 **Apple M2、8 physical/logical CPU cores、25769803776 bytes = 24 GiB统一内存** | 建议顺序单进程；CPU计算threads≤2、torch interop1、DataLoader workers0；不与系统轨道性能计时并发 |
| GPU | 原生上下文 `mps_built=true, mps_available=true`；CUDA false。当前受限上下文 `mps_available=false` | MPS作为推荐正式ResNet设备，需在允许GPU的执行上下文启动；不能把当前sandbox的false解释为机器没有GPU；本轮未测MPS训练性能 |
| 磁盘 | 工作区文件系统free=339732922368 bytes，约316.4 GiB（时点值） | 建议新run预留1 GiB输出空间；不复制外部原始数据；这是资源规划建议，不是新增R4验收阈值 |
| ResNet18 预训练 | 本地 `~/.cache/torch/hub/checkpoints/` 无 ResNet18文件；P1 `.pt` 是random-init训练结果，不能充作ImageNet预训练 | 建议声明 `torchvision.models.ResNet18_Weights.IMAGENET1K_V1`；现有库给出官方URL `https://download.pytorch.org/models/resnet18-f37072fd.pth`，metadata `_file_size=44.661`（约45MB）；尚未下载/没有实际完整SHA256 |
| 实际内存需求 | P1 batch16峰值约978.6 MiB；full batch64峰值未测 | 建议调度预留约8 GiB统一内存，但**不是已实测值或新增硬gate**；OOM须停止报告，不自动降低batch或扩预算 |
| 环境/契约 | 继续现有venv，无新包需求；CPU路径P1已实际工作 | 正式ResNet train/eval均保持224×224、RGB/ImageNet norm；不用V1的默认Resize256/CenterCrop transforms；P2 batch64沿用审计04，而不是P1特例batch16 |

原生sysctl/MPS probe是批准的只读硬件核验，不是训练许可。本轮只核对库内weight recipe/URL metadata，没有发出下载请求。正式下载须用户批准后验证文件、完整SHA256与安全加载；仅凭文件名prefix不能冒称已经冻结了真实预训练文件。

### P2 待批准的精确训练配置与墙钟预算（尚未执行）

每模型一个**预先固定**配置，seed42，无配置搜索，无full-data重跑，无test/E1。ResNet只在获批正式权重到位后训练；不再用weights=None作为formal comparator。RF/LR各fit1，imputer/scaler只fit完整train，不用P0全量外部EDA median作为训练参数。ResNet ImageNet V1 与既有 MobileNet V2 的上游预训练不同，正式比较须披露，不能将差异全部归因于architecture。

| 模型 | 正式train / validation | 预登记参数，均在审计04空间内 | 推荐MPS方案wall上限 | CPU备选wall上限 |
|---|---|---|---|---|
| ResNet18 | 15899 / 2868，batch64 | IMAGENET1K_V1→10-class fc；AdamW LR8e-4/wd1e-4；cosine；≤8epochs，val macro-F1 patience2；同既有合法augmentation | **5400s = 90min** | **10800s = 180min**，CPU2 |
| RF | 21000 / 4500 | n_estimators200、max_depth12、min_samples_leaf2、n_jobs2；fit1 | **300s = 5min**，CPU2 | **300s = 5min** |
| LR | 21000 / 4500 | C1、lbfgs、max_iter1000；train-only median+StandardScaler；fit1 | **300s = 5min**，CPU2 | **300s = 5min** |
| P2 combined | 三个顺序运行、startup/load/train/val/save/reload均计时 | 原生MPS方案和CPU方案是两个待选预算，不自动互换或重试 | **6000s = 100min** | **11400s = 190min** |

ResNet由数量推导的上限为train每epoch249 steps、最多1992 train steps；每epoch45 validation steps，8epochs最多360，另一次saved-checkpoint reload检查最多1 batch。这是现有样本/batch/epoch限制的计数推导，不是新增训练量。预训练下载/校验在训练启动前单独审批，不混入上述训练预算；所有模型运行各自进入新run_id，phase结束即停止。

预算数字是**本次建议的待审批硬上限**，不是R4已规定的小时数，不改动R4 trial/epoch ceiling，也不是“保证完成8epoch”的时长承诺。P1 raw CPU step timing的线性参考约19.3min/full epoch、8epochs约154min，但不含所有decode/load开销，batch64与MPS未实测，不能作为P2 benchmark。MPS不可用、OOM或TIME_BUDGET_EXCEEDED时停止并记录PARTIAL/失败，不自动切CPU再训练一次或扩大时间。

### P2 是否计入 HPO：建议计入，同一ledger不重复运行

**建议并请求用户批准：P2三个formal runs各计入对应模型初始finite-grid的1个seed42 trial，`counts_toward_hpo=true`。** P2只执行预登记单配置；P3复用其checkpoint/完整val结果/日志，补余下配置，不再重复该trial。P1的3个smoke仍永远不计HPO。

若P2三项成功：ResNet/RF/LR各用掉初始6trial中的1个，P3各余5个；MobileNet仍6、XGB仍8。总初始预算仍32（P2用3+P3余29），总formal runs仍在40–42 ceiling内，不变成43–45。各模型total ceiling仍为MobileNet8、ResNet8、XGB10、RF8、LR≤8（LR额外2仅在实际随机性成立时）。开始过的formal训练/fit也记录为attempt并占上限；中途超时/失败不自动补跑，未完成grid coverage照实PARTIAL，修复重跑须另批且不能越过既有总cap。

为补齐准备协议，建议在正式执行前冻结：XGB/RF confirmation seeds43/44；选型按**未舍入val macro-F1**最大，完全并列则按预登记grid_order/trial_id决定，不用test、事后延迟或弱类test表现破并列；confirmation只报告稳定性，不额外搜索/挑最佳seed。当前这些是proposed，机器配置仍保留`launch_authorized=false`和未批准wall caps，不在本轮改配置或启动任务。

### 尚未闭合的验收/审批事项与 Week 2 最终判定

- **W2正式HPO准备审批未闭合**：trial ceiling/grid已明确，但五模型正式wall-time/资源分配、seed/tie规则和协议freeze尚未获批。P2这一份建议不是完整P3执行预算；批准P2不自动批准P3，W2缺口不会用P1成功来掩盖。
- **P2 READY条件**：批准所选MPS/CPU方案、正式weight recipe与必要下载/本地权重授权，以及P2计入HPO的口径。权重文件就绪和batch64实测资源属于P2运行条件，不倒推成旧W2新硬验收要求。
- **性能门槛**：本次不发明正式P2最小macro-F1/per-class recall、必须优于baseline或target-device latency值；如用户要将它们变硬gate，需明确阈值/口径和R4关系。训练及证据完整可PASS，目标达成状况另列PASS/NOT_MET。
- **P3/P4未来方法决策**：E1-V held-out数量/QC流程与统计protocol，E1-T D3 drift方向/missing rates、physical bounds及标签有效性处理须在对应phase冻结；不得把审计示例5/10/20%静默变成R4硬规定。当前未决不授权提前test/E1，也不要求今天执行实验。
- **P5外部契约**：按系统轨道最终Task10A schema冻结验包；本轮不推断其系统实现/影子评估是否完成。DMD继续BLOCKED，与W2/P1通过分开，不作为新增W2 gate。

**因此：Week 2 ML的冻结与技术准备已经完成并有证据；Week 2 ML完整验收仍 PARTIAL / APPROVAL_PENDING。Week 3的comparator trainer+smoke已提前通过。系统轨道Week 2整体状态不在本次ML审查范围。** 当前仅请求用户批准正式资源/预算方案与下一阶段；未启动P2/P3。

## P1 完成结论与审批状态

**P1：VERIFIED_PASS。** 已实现三个 comparator 的可复用 smoke training pipelines；完整 ML 软件契约测试 **36 passed**，保存产物的独立核验 **85 passed / 0 failed**，三个真实 smoke 的首次 attempt 全部通过，**rerun=0**。组合实际执行 **26.1109 秒 / 1200 秒上限**。P1 结果是 pipeline checks，不是正式模型性能比较。已停止，**P2 / P3 均未授权**。

用户已明确批准 **P1 ONLY**，随后确认 audit package 的七项 tracked deletions 是本人操作并要求继续。保留这些删除与 P0 未提交产物；没有恢复/暂存/提交它们。新的代码与所有 P1 evidence/model artifacts 都在 ML-owned paths；未修改应用、源 CSV、共享环境或线上基线。

### 批准预算与实际运行

全部分层采样 seed42。ResNet18 train 每类20、val每类10；RF/LR train每类100、val每类30，两个 telemetry 模型使用相同 source IDs 和顺序。只访问 train/val 的样本；vision 的既有 membership CSV 包含 test split 行，但在数据加载器返回/采样/类别处理之前过滤掉，不打开 test 图像；不打开 telemetry_test.csv，不用 held-out 数据训练/选型。

| 模型 | 批准样本 train / val | 实际 epochs / fits / steps | 完整子进程 wall-time / 上限 | 结果 |
|---|---|---|---|---|
| ResNet18 | 200 / 100，batch16 | 1 epoch；13 train steps；7 validation + 1 reload = 8 validation steps（train cap16 / val cap8） | **21.7577s / 600s** | VERIFIED_PASS；CPU torch threads2、interop1、workers0 |
| Random Forest | 300 / 90 | **1 fit**；20 trees、depth6、min_leaf2、n_jobs2 | **1.5419s / 120s** | VERIFIED_PASS；train-only median Pipeline；native OpenMP threads2 |
| Logistic Regression | 300 / 90 | **1 fit**；lbfgs、max_iter200、C1；实际 n_iter=16 | **1.4643s / 120s** | VERIFIED_PASS；train-only median + StandardScaler Pipeline；native OpenMP threads2 |

子进程时间包括启动、imports、data loading、训练、validation、保存与重载。组合时间包括 active orchestration overhead。单位测试与存储产物核验不拟合分类器，也不做模型 forward；不计为额外 smoke、HPO 或正式训练。每模型只有 attempt_01，未用 rerun 权限、未扩大样本/epoch/time。

当前本地缺 ResNet18 预训练缓存，按用户授权采用 `weights=None`。配置/checkpoint/metrics 明确标记 `RANDOM_INITIALIZATION_SMOKE_ONLY`、`NOT_VALID_FOR_FORMAL_MODEL_COMPARISON`、`formal_comparison_valid=false`。没有自动下载权重。

### 实际资源、数值与保存/重载

| 模型 | peak RSS | CPU user / system seconds | validation diagnostic accuracy / macro-F1 | loss 与 reload |
|---|---|---|---|---|
| ResNet18 | 1026162688 bytes（约978.6 MiB） | 27.3476 / 2.8219 | .100000 / .018182 | train CE=2.548873、val CE=2.908995，均有限；reload 16 张同批 logits max difference=0 |
| RF | 178372608 bytes（约170.1 MiB） | .088224 / .046210 | .966667 / .966657 | val log_loss=.132143；reload 概率 max difference=1.11e-16 |
| LR | 178012160 bytes（约169.8 MiB） | .067487 / .035506 | .988889 / .988886 | val log_loss=.046117；reload 概率 max difference=0；无 convergence warning |

CPU user/system 是 `train_smoke` 入口（完成 imports 后）至保存结果的差值，peak RSS 是 worker 整个进程的峰值；不是目标硬件性能 benchmark。上述 accuracy/macro-F1 仅用于确认 validation 预测管道工作，**不得排名/引用为正式五模型比较结果**。Telemetry 仍是 synthetic source；这些数字不证明真实世界泛化、camera reliability、融合效果或事故风险改善。

ResNet18 验证概率 `[100,10]`、原始 logits `[100,10]`；RF/LR 概率各 `[90,3]`；全部概率与 loss 有限、概率行和有效、输出类别顺序正确。RGB→PIL bilinear 直接224×224→/255→ImageNet Normalize、c0…c9 mapping 沿用冻结契约；无 center crop / horizontal flip。RF/LR feature order 为既有八特征，labels 为 Safe/Aggressive/Distracted。Imputer/scaler 只 fit 当前 smoke train300；validation 没有重新 fit。`.pt` 所有 load 均 `weights_only=True`；RF/LR joblib 只保存/重载本次自生成 benchmark Pipeline，不进入 candidate package。

### 软件验证与独立审查

Superpowers TDD 记录：31 个共享契约用例先因未实施而失败→通过；CLI/path 边界新增后 3 failed/31 passed→通过；HPO入口拒绝用例 1 failed/34 passed→通过。最终 36 个用例覆盖：预算扩张拒绝、十类/三类分层、train-only median/scaler 与极端 validation 值、固定预处理/概率契约、train/val-only loaders、路径越界/symlink/重复 run 拒绝、native hang 安全终止、仅 genuine fix 后允许一次 rerun、global budget gate。

独立只读 reviewer 在 smoke 前发现 **1 项 Important**：Popen 启动开销可能追加在 wait 的完整 timeout 之外，且超过硬限但 exit0 可能被误判 PASS。无模型子进程复现（0.2s startup delay / 0.1s budget）后新增失败回归测试；修正为同一 absolute deadline 的 remaining wait，正常退出 elapsed 达上限也记 TIME_BUDGET_EXCEEDED。修复后的完整 suite **36 passed（6.66s）**。这是训练前的软件修复，**不占任何模型 rerun**；无其他 Important finding。

独立 reviewer 自行跑过当时的35个 ML tests（35 passed / 6.76s），未训练或读取 held-out data。仅执行 ML-owned software tests，未执行旧系统 branch 的 backend/frontend/fusion 验收或 E2–E5，不能称全仓库 CI / Live System acceptance 通过。

### 本轮文件与证据

可复用实现：

- `ml/experiments/comparator_common.py`：冻结数据加载、分层采样、train-only Pipeline、契约验证、安全输出目录、deadline/rerun 门禁、日志/版本/hash helpers。
- `ml/vision/train_resnet18.py`：P1-only 训练/validation/weights_only reload，禁止 full-dataset CLI；不调用 pretrained download。
- `ml/telemetry/train_comparator.py`：RF/LR one-fit smoke + benchmark Pipeline save/reload，禁止 full-dataset CLI。
- `ml/experiments/run_p1_smoke.py`：模型子进程顺序执行，600/120/120s 与 combined1200s 硬上限；不自动重跑；超时记 TIME_BUDGET_EXCEEDED 并停止。
- `ml/tests/test_comparator_pipeline.py`：36项无分类器拟合的 ML unit/contract tests。

本轮唯一 run directory：`ml/outputs/runs/p1_comparators_20261015/`。根 `config.json` 保存用户范围/budgets、seed配置、Git HEAD/dirty snapshot、源码和权威规格哈希；根 `artifact_manifest.json` 保存三次 attempt 的命令/exit/wall-time/artifact hashes/实际状态及保护哈希前后结果。

每模型 `resnet18|random_forest|logistic_regression/attempt_01/` 包含 `config.json`、`sample_manifest.csv`、`predictions_validation.csv`（注明概率，vision另含 logits）、`validation_metrics.json`、`class_report.json`、`selection_log.json`、`trials.csv`（record_kind=PIPELINE_SMOKE，counts_toward_hpo=false）、`timing_samples.csv`、`execution.log` 和 git-ignored checkpoint。RF/LR 另有 `train_statistics.json`。没有 test predictions、formal selection、ONNX candidate export 或 runtime_manifest；P1 不是 candidate package 交付阶段。

`verification/` 保留 RED / GREEN 原始 test logs、`validation_metrics.json`（软件验证/审查记录及源码哈希）、`verify_smoke_artifacts.py` 和其 `artifact_manifest.json`（85项读取已保存产物的核验）。核验不 load 模型、不 fit、不 forward，不额外占 validation steps。

### 实际执行命令

```bash
# 先核 Git / 保护模型并读两份 authority；保留用户确认的7项删除
pwd
git rev-parse --show-toplevel
git branch --show-current
git rev-parse --short HEAD
git status --short --untracked-files=all
git diff --cached --name-only
git show fyp2/live-system:docs/fyp2/review/CODEX_ML_TRACK_PROMPT.md
git show fyp2/live-system:docs/fyp2/review/CODEX_ML_TRACK_ADDENDUM_R4.md

# ML TDD；各轮日志归档在本轮 verification/
./.venv/bin/python -B -m pytest ml/tests -q --tb=short -p no:cacheprovider
./.venv/bin/python -B -m pytest ml/tests/test_comparator_pipeline.py::test_process_startup_cannot_hide_exceeded_wall_budget -q --tb=short -p no:cacheprovider
./.venv/bin/python -B -m pytest ml/tests -q -p no:cacheprovider

# 唯一真实 smoke 调用：exit0，3 primary attempts 全部通过
./.venv/bin/python -B ml/experiments/run_p1_smoke.py --run-id p1_comparators_20261015 --data-root /Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment-

# 仅保存产物验证：exit0，85 checks passed，0 fits/forwards
./.venv/bin/python -B ml/outputs/runs/p1_comparators_20261015/verification/verify_smoke_artifacts.py
git diff --check
```

fast-context 优先调用仍因 Windsurf API Key 缺失失败，随后精确本地读取；没有因此扩大工作范围。实际 worker argv 和 environment deadline 由 supervisor 日志/manifest 记录。验证源码/源 CSV 哈希和线上三模型/受保护 review 哈希均保持一致；共享 `.venv` 没有 install/upgrade。

### P1 acceptance verdict

八项全部 **VERIFIED_PASS**：loading/preprocessing、预算内训练/fit、validation prediction、shape/class order、finite loss/probabilities、train-only 防泄漏、artifact save/reload、source IDs/seed/config/runtime/results 日志。证据分别来自 36 tests、各 worker metrics/sample/predictions/config、supervisor manifest 和独立 85项 artifact checks。判定仅针对批准的 smoke 管道，正式 model comparison/HPO/E1 与候选兼容性仍未完成。

下一阶段 **P2：完整 comparator training**，当前 `APPROVAL_PENDING`。须另获用户明确授权；声明正式 ResNet18 预训练 recipe（可考虑 torchvision IMAGENET1K_V1）和本地已验证权重/下载授权；确认每模型及组合 wall-time/设备资源安排；启用独立的 full-training mode 并先验证其预算门禁。正式参数固定在 R4/审计04有限空间内，训练计入获批上限，不因 P1 的低/高 diagnostic 指标选参。P3 HPO、final test/E1 和 candidate package 不自动授权。

## P0 历史结论与审批状态（已交付）

本轮完成 **P0：训练前安全检查、已有工作复核、数据/基线/契约冻结及 bounded HPO 草案准备**。准备验证命令退出码 0，**75 项检查通过、0 失败**；证据见 [preparation_evidence.json](../../../ml/outputs/runs/w2_preparation_20261015/preparation_evidence.json)。

**Week 2 ML preparation：PARTIAL，尚未通过完整 sprint acceptance。** 数据/模型冻结与准备验证为 `VERIFIED_PASS`；HPO trial 上限已按审计 04 写入草案，但墙钟上限没有获批，训练设备和 ResNet18 预训练 recipe/权重仍待确定。不能将配置存在当作 HPO 已执行。

P0 当时分类器训练 = 0；HPO trials = 0；test 模型预测 = 0；E1 执行 = 0。P1 已按新增授权完成，上方为最新结果；正式 HPO wall-time / P2 授权仍未闭合。

## 权威来源、冲突裁定与阶段边界

已在当前仓库完整读取：

```bash
git show fyp2/live-system:docs/fyp2/review/CODEX_ML_TRACK_PROMPT.md
git show fyp2/live-system:docs/fyp2/review/CODEX_ML_TRACK_ADDENDUM_R4.md
```

读取的 branch snapshot：`cbe573f25191999b22c027fcde06e2a524cb01c4`；两份文件的内容 SHA-256 记录在本轮证据的 `authorities`。没有进入或读取 `/Users/liu/Desktop/FYP2-Live-System` 的文件。

- 用户本轮请求 > R4 > 原 ML Track Prompt > 旧审计/Week 2 计划/附带 sprint plan。
- 用户明确允许唯一未跟踪的独立审阅文件，因此原 Prompt 的“status 必须为空”按此例外执行。
- 原 Prompt 的 E1–E5 被 R4 收窄为 **E1-V / E1-T**。E2–E5、融合、EMA/FSM 和应用开发归系统轨道。
- 旧“no training”和暂停其他架构研究的说明不覆盖本轮指定的 ML 开发授权；当前不训练是本轮阶段边界，不是沿用旧禁令。
- 两份权威文件列出优先级，但没有命名/编号的 implementation phases。本报告以用户的“Start now”、Week 2 冻结要求和逐阶段审批建立下表；这是明确披露的执行划分，不声称其编号来自 R4。

| 阶段 | 工作与先决条件 | 当前状态 |
|---|---|---|
| P0，本轮 | Git 安全、复用核验、split/model/contract 冻结、输出隔离与 HPO 草案 | 技术验证 `VERIFIED_PASS`；W2 总体验收 `PARTIAL` |
| P1，已完成 | ResNet18 / RF / telemetry LR 训练脚本、train-only Pipeline、可追溯日志、仅 train/val 的小规模 smoke；先获用户阶段授权并固定 smoke 上限 | `VERIFIED_PASS`；36 tests + 3真实 smoke + 85 artifact checks |
| P2，下一阶段 | 三个 comparator 的完整训练与初始 validation 选型；所有正式训练计入获批 bounded 上限，不额外增加未授权 full-size runs | `APPROVAL_PENDING`，实际训练 `NOT_STARTED` |
| P3 | 五模型 bounded HPO、confirmation/selection logs；准备确定性 E1 generators；完整预算/资源安排须先冻结 | `NOT_STARTED` |
| P4 | 冻结 validation 选型后，每个冻结模型一次最终 clean test；执行配对 E1、标签 QC、按 driver/clip 聚类的统计和证据生成 | `NOT_STARTED` |
| P5 | 严格按 R4 §3 打包候选并冻结 ML 证据；依赖系统轨道 Task 10A 最终 manifest schema | `NOT_STARTED` |

R26 train-only 统计与 R27 test 曝光披露提前到训练前完成，属于方法学先决条件。任何下一阶段都需用户明确授权。P0 仅完成准备；P1 已实现并验证三个 comparator 的 smoke 路径，R4 的完整模型训练/比较项仍未完成。

## Git 与工作区保护

实际执行 `pwd`、`git rev-parse --show-toplevel`、`git branch --show-current`、`git rev-parse --short HEAD`、`git status --short`、`git worktree list`。

- cwd / top-level：`/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1`。
- 当前分支：`fyp2/ml-training`；HEAD：`efb3ea6`，`chore: remove AGENTS.md`。
- 开工 status 仅有 `?? docs/fyp2/09_INDEPENDENT_AUDIT_REVIEW.md`，没有其他异常改动。
- 此报告 SHA-256 前后均为 `0731ebfbe8c49ef08452a23688a6fce26a13f9c3497d53ec898da91d9866daf0`。未改写、删除或暂存它。
- 未执行 stage、commit、push、merge、cherry-pick、reset、clean 或 branch/worktree switch；新产物保持未提交。`ml/.gitignore` 已修复，但“首个 commit 先修它”的约束仍适用于将来的首个获准 commit。
- 本轮只是阶段暂停，ML 轨道尚未结束，保留当前训练分支；Prompt 的轨道结束后返回 `dev_cc` 尚未执行。
- 没有修改 `backend/`、`frontend/`、`ai/src/`、`ai/reference/`、共享 `.venv` 或外部数据目录。准备脚本只提取并验证当前 provider 的独立 preprocessing 方法，不 import backend、不运行融合/EMA/FSM。

## 已有工作复用与真实验证

| 项目 | 处理与证据 | 状态 / 限制 |
|---|---|---|
| Vision membership manifest | 复用外部 `vision_metadata_with_split.csv`，不另造等价 CSV；重新核对哈希、路径、类别、司机与数量 | `REUSED_AND_VERIFIED`；15899/2868/3657，18/4/4 drivers，所有司机交集 0，重复路径/缺失路径 0；没有做 pixel/near-duplicate 审计 |
| Telemetry splits | 复用 train/val/test CSV 与旧 `data_artifact_audit.json`；重核全部哈希、列顺序、标签、NaN、有限值及完全相同行 | `REUSED_AND_VERIFIED`；21000/4500/4500，每个 split 三类平衡；缺失、重复及跨 split 完整行交集均 0；不能据此证明生成机制独立 |
| 基线 checkpoint / inventory | 重核三个受保护模型的 SHA-256；已有模型/图表/metrics inventory 写入本轮证据 | `REUSED_AND_VERIFIED`；没有另复制或重新导出线上基线 |
| Vision class order | `.pt` 通过 `torch.load(..., weights_only=True)` 读取；checkpoint、CSV 与 metrics 的标签映射相符 | `REUSED_AND_VERIFIED`；真实 `class_to_idx={c0:0,…,c9:9}`；训练 c0 名为 `normal_driving`，运行时显示 alias 为 `safe_driving`，不改数据标签 |
| Telemetry feature/class order | CSV、notebook 与 metrics 的固定八特征及 `Safe/Aggressive/Distracted` 顺序一致 | `REUSED_AND_VERIFIED`；排除 `phone_usage/reaction_time`；没有原始稳定 source_record_id |
| Preprocessing | 复用 notebook 的 RGB→PIL bilinear 直接 224×224→ToTensor→ImageNet Normalize；对当前 provider 做固定 seed 42 合成 PNG 验证 | `REUSED_AND_VERIFIED`；NCHW float32 `[1,3,224,224]` 逐字节相同，max difference = 0；不裁剪；只验证此合成输入，不代替真实标注行为检查 |
| ONNX contract | `onnx.checker.check_model`；input/logits、动态 batch、float32、10 类输出和无 Softmax/LogSoftmax 节点 | `VERIFIED_PASS`；未做本轮 test 推理或候选行为验收 |
| R26 train-only 准备 | `SimpleImputer` 与 LR `StandardScaler` 仅 fit train；记录 median/mean/SD/class means 与 train 哈希；toy train=[0,2]，不同 heldout 值中的 NaN 均填 1 | `VERIFIED_PASS`，仅统计/方法核验；后续正式 trainer 的 Pipeline 尚未实现 |
| HPO 草案 | 复用审计 04 搜索空间，新增机器可读 `ml/configs/bounded_hpo.json` | `PARTIAL / APPROVAL_PENDING`；不能启动 costly runs |
| 日志约定 | 复用 Prompt / 审计 04 所列 config、trials、validation、selection、checkpoint、test IDs 与 timing；配置列明路径与语义 | 规范已整理；实际 classifier runner `NOT_STARTED` |

Telemetry ID 规则固定为 `telemetry-v1:<split CSV SHA256>:<split>:<zero-based data row>`；vision 为 `vision-v1:<class_id>/<filename>`。它们绑定现有不可变 split，不修改源 CSV，也不冒充恢复了原始生成记录/人物 ID。E1 的实际 held-out ID manifest、变换/共享 masks 尚未生成。

所有数据/线上模型预期哈希都在本轮 `config.json`；验证前后保持一致。统计、软件版本、实际 source fingerprints 和详细检查输出见 `preparation_evidence.json`，不再创建重叠说明文件。

## HPO 上限与执行门槛

| 模型 | 搜索空间（复用审计 04） | 最大正式预算 |
|---|---|---|
| MobileNetV3-Large | LR `{1e-4,3e-4,8e-4}` × wd `{1e-4,1e-3}`；固定现有合法 augmentation / 224² / batch64 | seed42 六 trials + selected seeds43/44；≤8 runs，≤8 epochs/run，patience2，val macro-F1 |
| ResNet18 | 同 LR×wd 与 augmentation / resolution / batch；上游 recipe 待声明 | 同六+二、≤8 runs，≤8 epochs/run，patience2；不使用默认 256→CenterCrop |
| XGBoost | depth `{3,6}` × LR `{.03,.1}` × subsample `{.8,1}`；colsample=.9/lambda=1 | 八+二 confirmation，≤10 runs；≤400 trees，val mlogloss early-stop30，跨 trial 仍以 val macro-F1 排名 |
| RF | trees `{200,400}` × depth `{None,12,24}`；min_leaf2、n_jobs2 | 六+二 selected-config seeds，≤8 runs |
| Telemetry LR | C `{.01,.1,1,10,100,1000}`，lbfgs、max_iter1000；train-only imputer/scaler | 六 trials；仅有随机性时另做二次 reproducibility checks，≤8；确定性重复不算独立证据 |

合计初始搜索为 **32 trials**；confirmation 后总上限为 **40–42 runs**，不是本轮运行数。有限 trial 上限不等于墙钟预算已批准。当前 per-trial / per-model / total wall-time 均为 `null`，`launch_authorized=false`；没有发明小时数或扩充搜索空间。

后续正式训练前还应固定：ResNet18 recipe/权重哈希、XGB/RF confirmation seed 编号、val 并列时确定性规则、设备/线程和共享机器的资源窗口。这些是在实现阶段冻结的配置决策，不以 test 表现作决定。

## 实验方法与候选包约束

- 原始 `Driver_Behavior.csv` 八保留特征也已核验无 NaN。外部 EDA 的全量 median→split 与其 train-only 文档不符；后续自己的 Pipeline 必须 train-only fit，但**没有证据证明既有 .9993 被该差异污染**。
- test split 已被多次评估，不称“从未见过”。在已检查 notebook 中，vision epoch 使用 val accuracy、XGB 使用 val early stopping；没有发现直接 test 选参的代码。新 HPO 改用 val macro-F1。此结论限已检查代码，不能证明人员从未受 test 信息影响。
- E1-V 固定 held-out IDs + seed42；六类×三强度及 clean；两模型共用逐字节相同输入；保存方向、位置、crop 参数；独立 recognizability QC；统计按 driver/clip cluster。Gaussian≠motion，grayscale≠IR。
- E1-T 4500×(1+9)=45000 source variants，共享生成集/masks，D0 `synthetic=true, perturbed=false`；D2 是 label-conditioned stress。未来 physical bounds、D3 missing rates/方向和标签有效性规则仍需冻结；没有把合成 telemetry 指标推广为真实世界泛化。
- DMD access/license、动作区间、人物分组和映射没有获证，保持 `BLOCKED`；不下载或用其他数据代替。
- P5 必须完整遵循 R4 §3：自包含 `ml/outputs/runs/<run_id>/` package、无 symlink/目录外引用；`runtime_manifest.json` 只含加载字段（文件名/哈希、I/O、预处理、logits 语义、真实 class_to_idx、标签名、架构、来源 run_id/commit）；`evaluation_metrics.json` 独立；保留 validation、selection log 和带 ID 且注明 logits/probabilities 的 test predictions。ONNX `input` / `logits`、float32 `[N,3,224,224]`、动态 batch、原始 logits；`.pt` weights_only；RF/LR pickle/joblib 仅 benchmark、不进入 candidate package。
- Task 10A 最终 manifest schema 未确定，不能把当前草案称为系统可加载候选。本轮没有用简化 package 代替 R4，也没有自动部署模型。

## 环境、文件与执行记录

实际使用 `./.venv/bin/python`，没有安装/升级包。Python 3.13.3；torch 2.12.0、torchvision 0.27.0、scikit-learn 1.9.0、xgboost 3.2.0、onnx 1.21.0、onnxruntime 1.26.0、pandas 3.0.3、numpy 2.4.6、Pillow 12.2.0。

当前受限执行上下文 `mps_built=true, mps_available=false, cuda_available=false`；不能继承旧“GPU 已可用”结论，也不能据此断言整台机器没有 Apple GPU。本地只找到 MobileNetV3-Large V2 的预训练缓存，未找到 ResNet18 权重；没有下载权重。完整训练前应确认可执行设备和资源预算。

本轮新增/修改：

| 文件 | 用途 |
|---|---|
| `ml/.gitignore` | 忽略 runs 下模型序列化/feature caches；JSON 默认忽略，显式保留 config、manifest、metrics、selection 等规范证据名；CSV/log/脚本可保留 |
| `ml/configs/bounded_hpo.json` | 五模型有限 HPO 草案及运行产物规范；launch=false |
| `ml/outputs/runs/w2_preparation_20261015/config.json` | P0 范围、预期哈希、seed、复用来源和改动前 ignore 实测 |
| `ml/outputs/runs/w2_preparation_20261015/verify_preparation.py` | 可重跑的准备验证，不训练分类器/预测/导出 |
| `ml/outputs/runs/w2_preparation_20261015/preparation_evidence.json` | 本轮机器可读实际结果、统计、versions、hashes、git dirty snapshot |
| `docs/fyp2/ml/ML_TRACK_PROGRESS.md` | 唯一规范进度/阶段/审批报告 |

关键命令与实际结果：

1. 六项 Git 安全命令：exit 0，branch/HEAD/唯一例外如上。
2. 两次 `git show`：exit 0，两份权威文件完整可读。
3. `shasum -a 256`：三模型、vision metadata、telemetry test 和受保护审阅报告均匹配；随后验证脚本进一步核 train/val。
4. fast-context 优先调用：失败，`Windsurf API Key not found`；按本地 `rg`/JSON notebook source 检查继续，不读取巨大嵌入输出作为代码。
5. `git check-ignore --no-index`：改动前 runs 下 XGB JSON、RF joblib、LR pkl 未忽略；改后 16 个模型/证据路径检查全部通过，不需要创建或暂存探针文件。
6. 首次准备验证：exit 0，71 checks；补充司机数/source-ID 唯一性、数据↔checkpoint 名称映射和 HPO run caps 后最终重跑：**exit 0，75 checks**。两次都没有分类器训练或 test 推理；最终证据为最新快照。
7. 交付核验：`git diff --check`、JSON/Python syntax、所有新增文本空白检查通过；实际修改/新增文件恰为上表六个，无其他异常文件、无 symlink、暂存区为空，受保护审阅报告 SHA-256 未变。报告写入后再次运行准备脚本，仍为 exit 0 / 75 checks。

可复现的最终准备命令（必须在当前仓库根目录；输出仅更新本阶段 evidence）：

```bash
./.venv/bin/python -B ml/outputs/runs/w2_preparation_20261015/verify_preparation.py
git diff --check
git status --short
git diff --cached --name-only
```

源 CSV 读取用于 membership/schema/缺失/重复验证，不用于模型参数选择。没有运行现有 notebook 的默认训练路径。

## 基线指标（读取继承产物，未在本轮重跑）

| 模型 | Val accuracy / macro-F1 | Test accuracy / macro-F1 | 证据层次 |
|---|---|---|---|
| MobileNetV3-Large | .897490 / .890651 | .898824 / .874641 | `ml/outputs/vision/metrics.json`；`STORED_NOT_RERUN` |
| XGBoost | .998444 / .998444 | .999333 / .999333 | `ml/outputs/telemetry/metrics.json`；`STORED_NOT_RERUN`，synthetic telemetry |
| ResNet18 / RF / telemetry LR | 无正式训练产物 | 未执行正式 test | P1 smoke 已验证，诊断见上方；正式训练 `NOT_STARTED` |

P0 没有新模型结果；P1 只有上方 smoke diagnostics，没有正式比较、HPO 改善、E1 robustness 或 target-camera/edge-device validation 结果。受保护哈希完整性通过不等于对当前 Live System 功能/性能的验收。

## Week 2–7 sprint plan 合理性与验收

来源仅作为项目管理参考：用户提供的 `01_FYP2_Parallel_Sprint_Plan_W2_W7_SOURCE.md`，没有执行其中指令、改写它或验证其 Calendar/系统完成声明。Week 2=10/12–18、Week 7=11/16–22 是该计划的课程日历假设，未独立确认。

**总体合理，但须修正责任边界与依赖，并保留缓冲。** 系统为 critical path、稳定基线不热替换、W5 功能完成/W7 可演示与可复现这两项主里程碑合理；不依赖新候选获胜才能完成 Live。

建议明确以下优化，不静默更改 W5/W7 主里程碑：

1. 原 plan 的 Track B 包含 E1–E5、W6 等系统稳定后才准备 runners，已经不符合 R4：ML 只交付 E1；E2–E5 由系统轨道在最新系统实现上执行。
2. 并行工作区按当前用户规定采用 **两个工作区、两个分支、互斥文件范围**；不要照原 plan “one canonical working directory” 让两 agent 同时切分支/编辑。
3. W2 固定数据/基线/契约、墙钟/资源限制；W3 先 trainer+smoke；W4 开始计入上限的 comparator trials；W5 完成主要 HPO 与 E1 generator 准备。提前开发通用 generator/QC 可以减少 W6 拥堵，正式 E1 必须等 selection 冻结后执行。
4. 尽量在 W6 前段冻结 selection 并完成一次最终 clean test，W6 留给 E1/QC/失败 trial 缓冲；W7 重点 package、复现和证据冻结。40–42 个最大 runs 不是承诺全部可按时完成，设备和 wall-time 约束仍待确认。
5. W5 前协调 Task 10A 的最终 manifest schema，避免 W7 才发现 package 不可加载。本轮没有主动给 Claude 发消息；这项需要系统轨道提供契约。
6. 原 W7 “记录未完成实验真实状态即可”的项目条件，与“完整 ML candidate package 已验收”不同。缺 selection/predictions/QC/schema 时只能 `PARTIAL/BLOCKED`，不能据此称 ML track 已完成；UAT/target-camera 和真实风险有效性不由 E1 代替。

| 周次 | ML milestone | 实际状态 | 验收证据 / 缺口 |
|---|---|---|---|
| W2 | dataset/model freeze + bounded HPO preparation | **PARTIAL / APPROVAL_PENDING** | 冻结/75 checks和当前保护hash复核通过；五模型正式wall-time及协议freeze审批未闭合。硬件已核实；权重实际下载属于P2条件，不追加为旧W2 hard gate |
| W3 | comparator trainers + smoke | **VERIFIED_PASS** | P1 提前完成；36 tests / 三模型首次 smoke / 85 artifact checks；正式训练尚未开始 |
| W4 | comparator training + initial tuning | **NOT_STARTED** | 没有 ResNet18/RF/LR 完整 checkpoint 或新 val 指标 |
| W5 | five-model bounded HPO + generators | **NOT_STARTED** | 仅 W2 草案，不是 trials/selection 或 generator 的完成证据 |
| W6 | final model evaluation + E1 evidence | **NOT_STARTED** | 无配对扰动/QC/45k/shared-mask/cluster 结果 |
| W7 | candidate package + evidence freeze | **NOT_STARTED** | 无候选；依赖 Task 10A schema、冻结模型及完整证据 |

以上只评 ML track，不替 Claude 系统轨道签署 sprint acceptance。

## 最新下一阶段与停止状态

P1 已完成且本次实际产物复核继续支持原八项通过；最新四维矩阵及MPS/CPU两个预算方案在报告开头。当前请求 **P2** 的明确授权，并确认正式ResNet预训练下载/本地权重、所选资源/墙钟方案及三个P2 runs计入HPO ceiling。正式五模型HPO的其他wall-time尚未批准，P2授权不自动授权P3。P0/P1产物和源码均未提交；本轮没有启动任何训练、HPO、final held-out prediction、E1或candidate packaging，仅更新本规范报告，没有新增duplicate文档。
