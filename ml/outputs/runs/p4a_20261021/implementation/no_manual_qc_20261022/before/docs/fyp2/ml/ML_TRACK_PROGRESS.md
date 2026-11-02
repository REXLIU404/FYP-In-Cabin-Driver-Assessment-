# FYP2 ML 轨道进度（唯一规范进度报告）

## 2026-10-22 P4-A — Implementation and Validation/Synthetic Preflight（run_id 保留 p4a_20261021；技术验证通过，人工 pilot 待完成）

当前用户已原则认可 P4-PROTOCOL-v1，并明确仅批准 P4-A 实现与 validation/synthetic 预检、两份隔离 FP32 ONNX 导出。P4-B held-out / 正式 Test/E1、P5、部署仍未授权。下方 2026-10-20 的“未获导出授权”等描述是历史状态，本节覆盖其权限状态，不改变实验设计。

- 开工：六项 Git 检查通过，`fyp2/ml-training` / `335da4e3de203836c045452f84cc291bcd352a26`；15项既有 dirty 路径与上轮相同。保护基线、09审阅、HPO selection/state 和 P3 generator/profile 原始 hashes 保存在 `ml/outputs/runs/p4a_20261021/startup_snapshot.json`。未暂存、提交、切分支或进入 Live-System。
- 实施任务：① formal runner、独立 P4-B gate、一次 clean cache、预算监督和指标；②按用户修订的单人 R1 盲审 QC、共享生成输入、分阶段 bounds、validation pilot；③两份隔离 ONNX、三身份 parity、CPU throughput 有界预检；④整套 ML 测试和独立 review 后汇总。使用 Superpowers TDD 与隔离子任务，原始 RED/GREEN 证据保留在同一 run 下。
- 接口检查：①与②共享 source ID/condition metadata 和授权 gate；①与③共享 frozen identity/ONNX provenance；②与③只打开 metadata 已证实的 val 图片。禁止用把 test 标为 val 的方式复用 P3；P3 源码和旧准备产物保持原样。实现各组件的 synthetic test 不代表 formal run 已完成。
- Ruling：按用户最小文档政策，本报告兼作实施 ledger，机器日志在 run 目录，不另建 plan/progress 文档；继续当前已核实 ML 分支，不创建工作树、不按 skill 默认提交。代价是交付需要 source snapshot/dirty 记录，不能称干净 commit 复现。
- Ruling：本轮 export/checker/parity 使用 v1 的 600s 阶段上限；额外 validation CPU throughput 预检自行收紧到 600s 上限，非正式 6-round runtime benchmark，不转移/扩大 14400s 正式预算；超时或 parity 失败停止，不改容差、模型、设备或再次导出。
- QC：用户已明确修订 P4-A 为单人 feasibility pilot：`R1 = project developer`，没有 R2、不计算 inter-rater agreement。准备 2 个 validation source ×19 =38 案例，盲审时隐藏原标签和模型输出；记录 VALID/INVALID/UNCERTAIN、选择的行为类别、理由与逐案例实际耗时，锁定后核对原始动作证据。单人偏差、小样本及相关变体局限必须披露；延迟随机重复审阅可选，不设为门禁。未收到 R1 实际判定前，保留率/人工耗时写 PENDING，不影响其他 P4-A 实施/预检。正式 P4-B 的单人 QC 方案随下一次审批明确，不能仍以不存在 R2 阻塞。
- D3 的正式表述为 **combined positive-bias and record-level missingness stress**，同时施加正向偏置与记录级缺失，不解释成 isolated missing-feature 实验。

当前工作是评估准备，不是新增训练。已核对 `ml/vision/train_hpo.py`：两种视觉模型在加载冻结 ImageNet 预训练权重后替换10类分类头，AdamW 优化 `model.parameters()`，没有冻结 backbone，因此 P3 已进行全网络 fine-tuning，并非只有随机初始化或 linear probe。已冻结 RN `search_004/seed42` 与 MN `search_006/seed42`；validation macro-F1 分别为0.9406150484662007和0.9162198680081481，3-seed均值分别为0.9247975522065762和0.8936628163255497。XGB/RF/LR也已有正式训练与bounded HPO。是否额外 fine-tune 是新实验决定，需要单独假设、train/validation方案、预算及用户批准；不能用之后的Test/E1结果继续调参并仍把同一test称作独立确认。本轮不增加HPO或训练，部署旧MN+XGB保持不变。

- 资源：首次可用 RAM 6.33 GiB，按≥8 GiB 门槛暂停模型工作；用户选择“先完成实现，资源不足记录阻塞”。后续自然回升至8.55/8.36 GiB，仍在每次实际启动前复核，不结束系统进程、不降低门槛。`ps`/进程树采样在 sandbox 中被拒绝；小型 synthetic 监督器测试另行受控验证，RSS不可观测时必须 fail closed。
- 实施子任务曾因会话额度中断；已继续原子任务，保留真实中间 RED/失败日志，不把未完成 agent 当作完成证据。

### 已执行的 validation-only 证据（不含正式 Test/E1）

实际执行入口为 `./.venv/bin/python -B ml/experiments/p4_preflight.py run-preflight --run-dir ml/outputs/runs/p4a_20261021`。为观测自己启动的 worker RSS，在受控授权下于 sandbox 外运行同一入口；未变更共享环境、未发起网络下载。启动前自然恢复内存后才执行，每个 worker 启动时可用 RAM 最低 **8.3624 GiB**，磁盘>300 GiB。监督器合计 **11 workers / 60.016934 s**（preflight **42.512368 s**，timing **17.504565 s**；从 invocation 到 summary 文件时间约 **60.037369 s**），低于600+600=1200s内部预检上限。没有重试或再次导出；正式14400s没有启动或扩额。

| Identity | 新 ONNX bytes / SHA256 | validation PyTorch–ORT parity | batch32 CPU吞吐预检 |
|---|---|---|---:|
| MN-HPO42 | 16849370；`9ee60abb78007773cc625af80c313049c1970f63c1f041bed9f5b2539a384828` | PASS；211 sample appearances；max abs `4.100799560546875e-05`；max prob差`6.364584130613693e-06`；全部argmax一致 | 159.6048 images/s |
| RN-HPO42 | 44717068；`5e226722e0712824c78aa0976afa6fa5b8dc6100b147a7f523a09048171d8cf3` | PASS；211 sample appearances；max abs `1.9073486328125e-05`；max prob差`2.302238954254854e-06`；全部argmax一致 | 41.5537 images/s |
| MN-STABLE | 只读现存ONNX，**没有重新导出** | PASS；211 sample appearances；max abs `5.340576171875e-05`；max prob差`4.846009571957133e-06`；全部argmax一致 | 160.5767 images/s |

每身份的211是同100个val来源在100×batch1、32/32/32/4、2、9中的重复出现，不是211个独立样本。三者共享100样本、10类各10的同一tensor bank，hash=`07adb0…42e`（完整值见manifest）。检查均使用原约定`atol=rtol=1e-4`，没有放宽。ONNX checker、FP32 logits、dynamic N、strict weights-only/PT头及真实class顺序通过；两新图是bench/evaluation-only，`candidate_package=false, deployment_eligible=false`。上述吞吐每身份100 warmup +200 measured images，排除完整Live流程；**不是**正式6-round batch1 latency benchmark，不据此改validation候选优先级。最大观测worker RSS **1.52248 GiB**；20ms是采样目标，实际最大片段间隔约100.1ms，不能声称捕获瞬时全部峰值。

`projection.json`按实测100val throughput、1900变体生成耗时以及1.25 margin外推：vision clean167.12s、stress3008.11s、共享生成122.54s；RN stress1980.15s/2400s cap，MN-HPO515.54s/2400s，MN-STABLE512.42s/2400s。加其余未实测阶段按cap预留后总计 **8097.7602s ≈2小时15分**，低于14400s提案。该估计不包含正式cache/QC图片与全量bank写入的实测成本、热/系统负载变化，不能保证整次执行时长；尤其RN模型cap余量约420s，到限仍停，不扩额。

复现记录：`environment_snapshot.json`记录Python3.13.3、torch2.12.0、torchvision0.27.0、onnx1.21.0、ORT1.26.0、numpy2.4.6、Pillow12.2.0、psutil7.2.2及macOS/arm64；这是预检后记录的同一未修改环境。执行过的导出源码保留为`implementation/p4_preflight_executed.py`，SHA=`ffdfa6637bace58c9818ade3b9a84e812a59d2f681543927b10403061301dece`。每worker另记HEAD、dirty、protected前后hash、source hash与线程池。工作树有明确记录的未提交实现，不声称是干净commit运行。

### 单人 QC feasibility pilot

实际命令：`./.venv/bin/python -B -m ml.experiments.p4_qc pilot --metadata /Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment-/eda_outputs/processed/vision/vision_metadata_with_split.csv --metadata-sha256 b4f8e90dec769bb419eaa490aea869668bed6484089cebe4d545c7667baa8ea4 --output ml/outputs/runs/p4a_20261021/qc/validation_pilot`。只打开2个已证实val来源，生成38张匿名PNG及`review.html`、盲审表、受限source key；准备软件耗时 **0.510560708s**，不是人工审阅耗时。与模型预检100来源无重叠，因此本轮实际使用共102个distinct val来源；未打开held-out图片或telemetry test记录。

R1流程为 `review.html → 导出blind JSON → p4_qc lock → reveal → source_review.html或cue CSV → finalize`。逐case包含VALID/INVALID/UNCERTAIN、选择class、理由、elapsed wall seconds（含中断），锁定后才揭示source并确认preserved cue。最终VALID还需blind类别匹配source且cue=True；统计class/driver/family/common-valid支持、实际时间均值/中位/p95，均不调用模型。没有R2、没有inter-rater agreement；延迟随机repeat非必需，本轮未执行。

**当前人工判定0，实际每case耗时、有效保留率和共同集合覆盖仍PENDING。** 38变体仅2个source，完整10类macro-F1不可估计，不代表38个独立参与者。仅给非实测场景：若5/10/20s每case，pilot约3.17/6.33/12.67分钟，最多3800正式case约5.28/10.56/21.11小时；这不是实际人时或新批准预算。原“两人各8h”不再自动转为R1的16h，正式单人时间预算待pilot数据与P4-B审批明确。R1为开发者，存在开发者/单人判断偏差及既往数据熟悉度，须与四test司机/历史test曝光局限同时披露。

页面JavaScript静态语法检查通过（`node --check`），内置浏览器因file URL策略拒绝打开，**未完成浏览器实际渲染/人工操作验证**；没有更换浏览器/代理来绕过。可以由R1本机浏览器手动打开本地文件；软件流程测试不替代人工判断。

### 最终审阅、测试与证据

- 完整 ML suite 最终命令：`set -o pipefail; OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 ./.venv/bin/python -B -m pytest ml/tests -q | tee ml/outputs/runs/p4a_20261021/implementation/full_ml_suite_after_review.log`；实际 **271 passed in 27.63s / exit 0**。修复前完整套件264 passed/26.95s的旧日志保留，修复后focused P4 suite为95 passed/6.21s；不把单元/合成测试称为正式held-out端到端结果。需读取自身测试worker RSS的部分在受控sandbox外执行，未训练或执行正式Test/E1。
- 原 parity JSON 缺直接 ONNX hash 的 P2 已关闭：consumer 使用原始export记录、冻结ONNX SHA及`core/preflight_attestation.json`共同核验；验证三身份都使用已冻结validation bank和原导出源码。未改变已执行导出脚本、重导出或重复模型forward。
- QC PNG/source key 未绑定的 P2 已关闭：`qc/validation_pilot_byte_attestation.json`核验既存38图的文件/像素、2个val原始source、source key和生成源码；lock/reveal/finalize再消费绑定。该sidecar为 **CURRENT_KIT_BYTE_FREEZE / initial_generation_proof=false**，38个历史case缺失的参数仍为UNRECORDED，不重建或冒称当时已记录。JSON文件SHA为`ae9b78cea795e0c50829cffa820d0ccdb7604017a316619d46c350ff441cd1a6`，内部canonical attestation digest为`a61964f46545f2fb6c67b39f5ebb483b13364c67c61466fbc852724a75ce8930`。`p4_qc.py`冻结SHA=`ff04696f5a2abbde841a19a10f7e77bd760bb4b2dde9288ff2b1d94bcb8f01c8`；pilot旧文件未改写。cue理由需非空字符串、PNG/source篡改拒绝、锁定后才揭示均有回归验证。
- 全包独立审阅的 telemetry 汇总 P2 已关闭：`evaluation_metrics.json`将消费已有`telemetry_variants.json`的纯metadata聚合，不增加推理。逐condition/feature报告source/injected/combined缺失的记录与cell数量/比例；四阶段source/pre_mask/observed/imputed分别报告domain/经验status和上下越界count/sum/max，保留UNKNOWN/MISSING与真实分母，不能用imputation掩盖mask前异常。D1–D3仍无有效真值F1。
- 同轮 P3 审批值truthiness已修正为literal `is True`；QC pending文字改为当前run范围。新回归先RED（5 failed/2 passed），修复后7 passed；证据在`core/final_review_fix_red.log`、`core/final_review_fix_green.log`、`core/final_review_fixes.patch`。只读scoped复审确认上述修复PASS，未发现新增P1/P2；该review自身没有运行模型或测试。
- 剩余minor：`p4_qc.py`通用LIMITATIONS仍写2 sources/38 cases，对本轮pilot准确，未来正式QC kit须按scope修订并保留当前pilot的源码/attestation版本；不把此问题解释成当前38案例无效。已执行preflight脚本若保护hash检查在finally失败，结果JSON可能为空，stderr/监督器失败状态仍保留；本轮没有发生，保留执行源码，不为此再次导出/推理。
- 复现限制：实际11worker执行时的`BudgetSupervisor/p4_core.py`没有在后续修复前保存完整源码快照，不能把当前修复版说成当时版本。原始worker预算/RSS/退出日志及精确数值导出脚本仍保留；当前10份最终源码已独立冻结在`source_snapshot_after_review/`，对应`implementation/final_sources_after_review.json`，不覆盖初审snapshot。最终run_p4 SHA=`3b2350b161043a2e3007c99a65ba00695a3793c910986eadb991209575f95ada`。没有重跑实际preflight来掩盖该限制。
- 最终纯artifact核验实际0.860096s：7冻结身份、三组保护hash、exactly2新ONNX、38图attestation、10份源码snapshot、staging为空、正式授权flag=false均PASS，结果在`implementation/artifact_integrity_after_review.json`。此核验仅读取既有val bank/QC字节及hash，模型forward=0、held-out observations=0。修复后仅run_p4及其测试相对初审源码发生变化。四保护原件、3份HPO selection/state、3份P3源码/profile与开工snapshot相同；没有新增HPO/training、修改源CSV、覆盖部署、提交或push。

实现文件：`ml/experiments/{p4_core.py,run_p4.py,p4_data.py,p4_qc.py,p4_preflight.py}`、`ml/configs/p4_protocol.json`及四个`ml/tests/test_p4_*.py`。复用已核验的P3生成器/统计/profile、冻结split/selection/checkpoint、稳定baseline和原实验日志（REUSED_AND_VERIFIED），没有复制第二套训练或fusion实现。仅本规范报告更新；同run下的manifest、机器日志、模型、差异包和快照属于实验原始证据，不是重复进度文档。

### 四维验收与下一阶段门禁

| 维度 | 当前判定 | 实际证据与边界 |
|---|---|---|
| Implementation | VERIFIED_PASS（P4-A技术范围）；人工部分PARTIAL | formal runner、paired共享bank、once-only cache、预算监督、R1盲审/锁定流程、两份隔离导出及三身份parity均已实现并验证；正式QC通用scope文字保留已知minor，正式执行本身未运行 |
| Testing | VERIFIED_PASS（271项软件测试和实际validation预检）；人工/浏览器PARTIAL | 完整日志exit0，实际11worker完成；38案例已有静态JS检查与合成流程测试，但浏览器渲染未验证、R1真实判定为0 |
| Evidence | PARTIAL | ONNX/模型SHA、原始parity/throughput/计时/RSS、validation输入bank、保护hash、测试与review差异证据齐全；实际人工时间、有效保留率及coverage仍PENDING；没有正式Test/E1指标 |
| Reproducibility | PARTIAL（限制已披露） | 精确导出源码、最终10文件snapshot、数据/模型/输入hash、seed42、Git HEAD+dirty、环境版本可定位；没有干净commit复现，初次监督器源码快照缺口不可追补，38历史参数UNRECORDED，不声称逐位重现 |

**P4-A整体：PARTIAL（技术验证通过，人工feasibility交付未完成）；P4-B：APPROVAL_PENDING，尚非无条件READY。** 不新增模型分数门槛，也不以271个测试替代人工QC或正式实验。R1完成pilot后，才可用实际每case耗时、valid/uncertain/invalid与class/family覆盖修订可行性判断；2个pilot来源本来不能证明完整10类覆盖，不据此补抽或伪造结果。

P4-B前须逐项处理：

1. R1在本机打开`ml/outputs/runs/p4a_20261021/qc/validation_pilot/review.html`，完成38案例并导出blind JSON；按lock→reveal→cue checks→finalize取得真实结果。当前等待的是用户人工操作，不需要第二人，也不阻塞已经完成的预检。
2. 明确批准正式单人R1 QC适用范围与人工时间cap；旧两人16人时不能自动沿用。已知formal kit scope文字先做版本化修订，保留当前pilot全部文件及绑定，不重新生成38图来掩盖历史参数缺失。
3. 单独批准P4-B的冻结protocol/source/run binding与**14400s总机器硬上限**；实测外推约8097.76s仅为估计。RN stress约1980.15s/2400s余量较小，到限仍停，不重试/扩额/新HPO。下一次启动重新检测RAM≥8GiB、disk≥20GiB和线程/电源状态，不把之前资源快照当未来保证。
4. 继续保留full clean、QC-conditioned与full-set stability三种结果口径、历史test曝光与仅4名test司机的限制。ResNet/XGB仍是validation优先，MN/RF/LR完整比较；结果不触发重选seed、改阈值、微调或部署。

本轮已停止模型执行。**下一阶段仅在单独授权后为P4-B正式Clean Test/E1/受控runtime；P5与额外fine-tuning均不在当前授权内。** 本节不重新裁定历史Week2/Week3已验证范围，也不因P4-A实现将Week6/Week7、正式评估或候选包标为完成。


## 2026-10-20 P4 Protocol Freeze Review — P4-PROTOCOL-v1（待批准，未执行）

**本节是可供批准的最终协议提案，取代此前pending参数的讨论；尚未获准执行或导出。** 用户已确认ResNet18 `search_004` / seed42为validation优先视觉候选，同时要求MobileNetV3-Large `search_006` / seed42参加完整配对Clean Test与E1；XGB `xgboost_02` / seed42为遥测研究优先，RF/LR保留benchmark，旧部署MobileNet+XGB不变。本轮只做协议审阅和本报告更新，没有实现P4 runner、运行模型、加载checkpoint/反序列化joblib、访问原始held-out观察、生成test ID manifest、执行test/E1/runtime、导出ONNX或提交/push。下面所有数量与预算均为**拟议设计**，不是新实验结果。

### 1. 权威、Git与真实核验

- 本轮以`using-superpowers`进行方案核对，并由三个只读agent分别审查identity、E1/QC、runtime；主agent核对并整合。两份权威文件均从当前repo完整`git show fyp2/live-system:docs/fyp2/review/CODEX_ML_TRACK_PROMPT.md`及`.../CODEX_ML_TRACK_ADDENDUM_R4.md`读取；最新P2/P3执行细则也完整复核。优先级：**用户当前决定/本次review授权 > 已批准P2/P3细则 > R4 > 原prompt > 审计参考**。
- 六项检查仍为cwd/root=`/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1`，branch=`fyp2/ml-training`，HEAD=`335da4e3de203836c045452f84cc291bcd352a26`；dirty全部为已知S3/P3产物、context和本规范报告，另有受保护09。未切branch/worktree，未进入Live-System物理目录；fast-context缺Windsurf key，改用精确读取，未提取凭据。旧prompt的空status/切回dev_cc要求不覆盖用户后续明确的保留已知改动/不切分支要求。
- identity审阅对五个选中目录的checkpoint/config/局部selection/trials/validation metrics做**25/25 exists+bytes+SHA匹配**，最终身份与根selection、summary/state **5/5一致**。局部telemetry selection仍保留训练时`AWAITING_MODEL_SEARCH_COMPLETION`，正式冻结以根`FROZEN_VALIDATION_SELECTION`为准，不能误判为重选。
- vision ledger及正式目录均16 attempts、全部COMPLETED；telemetry ledger26行=24 COMPLETED+1实际LR确定性重复+1未执行skip，目录25个（XGB10/RF8/LR7）。正式运行仍**41**，无extra/missing正式目录，未发现新增HPO或P4 run、正式目录无`predictions_test.csv`。此结论限定核验的ledger/目录，不声称做了全系统进程审计。
- 四项保护hash与P0 **4/4一致**。HPO七份唯一source/config中六份仍等于执行hash；telemetry supervisor有此前已记录的timeout/process-group修复，原执行snapshot **5/5匹配**，不把当前源码冒充原25次fit的版本。
- 为确定bounds报告，仅从SHA匹配的**train CSV 21000条**读取8列计算min/max；无fit、无val/test取值用于边界选择。用普通JSON解析旧XGB的属性确认`best_iteration=90`，没有构造Booster或预测。未重跑历史176tests/3761checks；本轮新增的是只读完整性与协议审查证据。
- 交付前主agent另作只读复核：五checkpoint的实际SHA/bytes **5/5**、四保护hash **4/4**、P3准备源码/profile等 **10/10 source records**不变；正式目录仍16+25、无`p4*` run，`formal_execution_authorized=false`、staging为空；预测/QC计数和机器预算算术通过，`git diff --check`通过。实际命令包括上述六项Git检查、两项`git show`、`git diff --cached --name-only`、`git diff --check`、`df -k .`及`./.venv/bin/python -B`内联JSON/SHA/metadata/train-only min-max程序；torch检查仅`inspect.signature(torch.onnx.export)`与MPS可见性，ORT检查仅provider inventory，无session/forward。

### 2. 冻结模型身份与对照范围

下表五个优化模型全部固定seed42。V=`ml/outputs/runs/p3_vision_20261018/search/`；T=`ml/outputs/runs/p3_telemetry_20261018/`；路径缩写仅为本表可读性，未来机器manifest必须写明完整解析路径。

| Identity / checkpoint | validation选定配置 | bytes | 实际SHA256 |
|---|---|---:|---|
| `MN-HPO42`；V`mobilenet_v3_large/search_006/attempt_01/checkpoint.pt` | lr=.0008, wd=.001, best epoch6；训练8epochs | 17052801 | `bc96e7a230de6391820b1e04e7480087841680ae6cc1b6e73cba42b25eb67295` |
| `RN-HPO42`；V`resnet18/search_004/attempt_01/checkpoint.pt` | lr=.0003, wd=.001, best epoch3；训练5epochs | 44803787 | `008d831c98ea5e4b6c5c821787b3dc9a1dcbc6ca47a74dd1d8f7110eb4ac7d20` |
| `XGB-HPO42`；T`xgboost/xgboost_02/checkpoint.joblib` | depth3, lr=.03, subsample1, 实际400 trees | 1194354 | `a464481d25ecb13f7db8392e039ac74855ad22fd80078154c7a4375a81097836` |
| `RF-HPO42`；T`random_forest/random_forest_06/checkpoint.joblib` | trees400, depth24, min_samples_leaf2 | 6578922 | `cca6d8c7a7832b53c7cc0e6d1777e1c9e37b721612bb58e29df26be875c65aba` |
| `LR-HPO42`；T`logistic_regression/logistic_regression_06/checkpoint.joblib` | C1000, lbfgs；原train-fitted median+scaler | 2449 | `558ac2cbda976822b370f257def52fa1a2dca9bb4cfe0b5e64f29623061c0274` |

审计04明确“Compare untouched baselines too”，R4以该审计为依据。因此本提案另纳入两个**只读stable reference**，不新增架构、不训练，不只引用旧test分数代替当前配对对照：

- `MN-STABLE`：`ml/outputs/vision/mobilenetv3_large_vision.pt` SHA=`196ca7b151d84e0c4a8eac87128da9dd8f22c894984a991ef611536bb523e7c7`；对应现存ONNX SHA=`b3a42e8dd4553355b1fd7d9e7fe3d28e318decb894e76eb029489b7ff2e90bcf`。二者是同一旧训练身份的不同格式，不算两个独立模型，不重新导出旧baseline。
- `XGB-STABLE`：`ml/outputs/telemetry/xgb_telemetry.json` SHA=`9802cb06ca98f0c1befaf851fa7668cfec70e005cf8bb3884e49d7d45d7aec07`；固定`iteration_range=(0,91)`，与保存best_iteration90一致，不能静默使用全部旧trees。
- 保护09 SHA=`0731ebfbe8c49ef08452a23688a6fce26a13f9c3497d53ec898da91d9866daf0`。以上都不写、不移动、不覆盖、不暂存。

核心比较仍是**2个HPO vision+3个HPO telemetry**；stable references单列。身份去重按训练来源、checkpoint SHA、格式映射及树范围联合登记；不同格式SHA不同不自动算新训练身份，同一身份的复制件也不重复推理。43/44 checkpoint不进入P4择优或额外评估。

### 3. 数据、一次clean cache与source-ID provenance

**正式批准后**才允许构造以下manifest、打开held-out图像/CSV或运行forward；本轮只引用P0保存的membership统计和期望SHA：

| 数据 | 固定来源/预期SHA | 计划使用 |
|---|---|---|
| State Farm frozen metadata | `b4f8e90dec769bb419eaa490aea869668bed6484089cebe4d545c7667baa8ea4` | 全部test3657图像，10类；四司机`p012,p026,p035,p050`；不另抽正式预测子集 |
| Telemetry frozen test CSV | `3bc3d47680a87359e1470fd8ffaf5ff330dc4419b37cc645e5736d51a91c96de` | 全部4500 source，3类各1500，合成数据；本轮未重读该CSV |
| Telemetry train CSV | `97dd20ee9c0832ba33455e5c31088f9b4abb65c198bf988699a959d545d1e5b5` | 已验证统计与本轮min/max唯一来源；不重新fit模型/部署预处理 |
| Telemetry val CSV | `1b02792df846b5af138bae59e4f4ccfa8fa421fbb4fd6d42fad88d57722774f1` | 既有选择证据；不混入final held-out结果 |

P4首次打开数据时重新核SHA、membership、train/val/test driver不相交及源8特征finite/无NaN；不符即停止，不能修CSV或自动换split。Vision ID=`vision-v1:<class_id>/<filename>`，记录原metadata行号、driver、原始文件SHA与metadata SHA；telemetry ID=`telemetry-v1:<test_csv_sha>:test:<原CSV零起始数据行号>`，先赋ID再过滤/排序，不重新编号。后者只是版本化位置ID，不是恢复出真实驾驶员/旅程或generator群组。没有可信clip字段，不编造clip ID。

每个`(model_identity,source_id,clean)`只做**本轮一次**完整clean预测，缓存logits/probabilities、原标签、class/feature order、模型/输入hash、runtime和数据版本；E1、QC子集和逐driver统计只引用该clean cache，不再forward。原test历史已曝光，故“一次”只指当前冻结模型的本轮final clean，不是生命周期首次见过。

一次生成/读取shared输入bank，三vision或四telemetry identity逐字节共用，保存输入hash及前后未修改检查。Vision流式batch32，避免保存全部69k张PNG；保留原图hash、生成参数、pixel/tensor SHA，QC subset才保存盲审图片。Telemetry保留同一份45k共享数组/行集及mask，不能为每模型单独抽样。若batch32 OOM不自动改batch/runtime，而是停止并报告协议偏离。

### 4. Clean Test、计数与指标

建议所有vision正式预测统一 **ONNX Runtime CPUExecutionProvider / FP32 / intra-op2 / inter-op1 / sequential / batch32**，两HPO模型先通过下文的val-only导出与parity门禁；stable MN使用已有只读ONNX。这样同一推理实现用于clean/E1，不混用ResNet PyTorch/MPS与MobileNet ORT结果。当前沙箱`mps.is_built=true`但`is_available=false`；不假定历史用户终端MPS可用性等于当前环境。此CPU评估提案不是对既有MPS训练规则的静默fallback，须随本协议获批；不自动启用CoreML。

Telemetry全用CPU2计算线程，依次加载本机已核SHA的可信benchmark pipelines；RF/LR不进入候选包。先共用train median填补，再走各自已冻结pipeline（LR沿用原train-fitted scaler）；无`.fit`。旧XGB也用相同median和8列顺序作离线对照，不能称为修改了部署预处理。非来源明确/哈希不匹配的pickle/joblib不得加载。

| 计划范围 | 共享输入数 | 核心模型预测数 | 含stable reference预测数 |
|---|---:|---:|---:|
| Vision clean（也是E1-V0缓存） | 3657 | 7314（2模型） | 10971（3身份） |
| Vision clean+6×3 E1 | **69483** | **138966** | **208449** |
| Telemetry D0 clean（也是E1缓存） | 4500 | 13500（3模型） | 18000（4身份） |
| Telemetry D0–D3全部 | **45000** | **135000** | **180000** |
| 正式预测总数（clean已包含，不重复相加） | 两种模态分别计算 | **273966** | **388449** |

上表不是独立样本/人的数量。每个source仍保留所有固定变体，即使QC无效，也保留其模型输出用于非真值指标。

Clean主报accuracy、10/3类固定顺序的macro-F1、class precision/recall/F1/support、confusion与log-loss；vision另报c0与c9等全部类，不仅挑弱类。原始logits保持FP32；评分时vision在float64副本上作稳定softmax（温度1），telemetry概率转float64并检查row sum在1±1e-6、范围合法。log-loss固定`eps=np.finfo(float64).eps`，`q=clip(p,eps,1−eps)`后逐行归一化，计算`−mean(log(q[i,y_i]))`；argmax指标使用原logits/概率，不因clip改预测。保存原输出与评分dtype，软件版本固定记录。该P4统一评分口径与历史部分float32评分分开标注，不重算HPO排名、不将不同dtype历史log-loss当新改善证据。

二分类`P_distraction=1−P(c0)`、threshold=.5仅作预声明的附加诊断（包括c0误报代理），与10类argmax区分；不校准、不调threshold，不把它叫实际事故/风险概率或Live告警表现。

### 5. E1-V：变换与rotation/crop几何

全部变换在原图RGB直接bilinear resize224²后执行，再`/255`、ImageNet mean/std、NCHW float32；clean无crop。**有意corruption中的rotation+crop不是把部署eval预处理改为CenterCrop**。同一source/seed42派生同参数，所有模型读取同一生成结果；不horizontal flip，不重标左右类别。

| Family | 冻结提案的3强度 / 细节 |
|---|---|
| brightness_up | 1.2/1.5/1.8；PIL brightness；记录饱和channel计数 |
| brightness_down | .8/.5/.3；不拿历史.35 pilot替代 |
| motion_blur | 真正线性kernel3/7/11，方向从0/45/90/135按source ID+seed固定；edge padding、nearest-even取整；方向约定image x向右/y向下 |
| occlusion | 约5/10/20%面积，黑色方块；side=round(sqrt(area)×224)，位置由同ID/seed锚点确定；保存实际面积与box |
| rotation_then_centered_inscribed_square_resize | 同source跨强度固定正负号，±3/7/12°；PIL bilinear rotate、expand=false、黑fill；见下式 |
| grayscale_blend | .3/.6/1.0；PIL L→RGB与原RGB线性blend；不是IR/NIR |

Rotation冻结**现有P3几何**：先把角度转为radians，`s=floor(224/(cos(abs(theta))+sin(abs(theta))))`，`l=floor((224−s)/2)`，`crop=(l,l,l+s,l+s)`，crop后bilinear回224²；边长213/201/188，裁去约9.6%/19.5%/29.6%的resize方形面积。保存实际angle/crop box/PIL版本，声明旋转、裁切及放大的联合效应，不能称为纯旋转或新相机视角验证。正式实现前用synthetic覆盖mask检查六个角度的离散边缘/fill，不通过就在**held-out打开前**停止修订协议；不能看到test表现后改变crop margin或强度。

### 6. 独立Recognizability QC：完整预测＋预登记评分子集

**明确范围选择，等待批准：**全3657 source全部19变体都预测；人工QC只对事前锁定、最多200个source的子集评分，未审部分不自动设VALID。全量双人QC需要138966个判定，按未实测5秒/判定约193人时，本提案不假装已具备该资源。

QC source选择在P4批准后、任何模型预测/结果查看前完成：每个`driver×原class`层，按`SHA256("42|qc-source|"+source_id)`排序取`min(5,层内数)`，不跨层补抽，不按已有错误或置信度挑图。四driver×10类最多40层、200source；每source clean+18 corruption，共≤3800个case，**两位reviewer共≤7600次判定**。稀疏/缺失层如实记载，不在看过结果后换样本。此source子集不缩减全量配对预测。

流程与oracle：

1. 开始前指定两位实际reviewer，冻结class动作说明和判断表；用val/synthetic例子练习，不依据test模型表现更改QC规则。agent或模型自动打分不能代替这两位独立人工判断。
2. 盲化所有模型身份、预测、概率、排名、source类目录及原标签；以匿名case ID、seed42固定shuffle展示。第一遍只看变体，独立选择`c0…c9 / UNRECOGNIZABLE / AMBIGUOUS`及可见动作依据并锁定；之后才核对source标签/必要原图，记录“原动作证据是否仍保留”。
3. 两人都独立、无歧义识别为同一原标签且动作依据保留，才VALID；明确移除/改变依据记INVALID，其余分歧记UNCERTAIN。没有第三审人自动裁决，也不因某模型猜对而改标签。原始判定/时间/理由/版本都保留，完成后锁定QC再向reviewer展示模型结果。
4. 每family取`clean_VALID ∩ s1_VALID ∩ s2_VALID ∩ s3_VALID`作为**同一共同有效集合**，三强度、clean及所有vision模型都在该集合上报告F1和paired Δ。另报各severity原始valid率、排除原因及driver/class支持数；不要用随强度变化的分母制造改善。
5. 若共同集合为空或缺失某类，完整10类macro-F1记`NOT_ESTIMABLE`并说明覆盖局限；仍可报告有支持的类及描述性结果，不能补抽、换subset或用零支持类别的默认0冒充有效总体比较。这不是要求模型必须达某分的新gate。

正式报告明确区分**full clean test**、**QC-subset conditioned F1**和**full-set无真值一致性分析**。所有full-set/invalid/uncertain/unreviewed case都保留flip rate、`mean ||p_corrupt−p_clean||_1`、逐类平均Δp与预测分布；flip只是对自身clean输出的改变，不是分类错误或安全改善。

### 7. E1-T：D0–D3、方向、bounds、mask及标签政策

8特征固定顺序为`speed_kmph,accel_x,accel_y,brake_pressure,steering_angle,throttle,lane_deviation,headway_distance`。统计复用P0 train-only median/global mean/class mean/SD(ddof0)并与三个HPO pipeline核对，不从test重新估计。

- D0：原4500 source，`synthetic=true, perturbed=false`，保留raw与shared-imputed特征；clean预测缓存一次。
- D1：`x'=x+sigma×train_SD×z_source`，sigma=.1/.3/.5；每source同一8维标准正态draw跨强度复用。
- D2：`x'=x+lambda×(train_global_mean−train_class_y_mean)`，lambda=.25/.5/.75；使用原source标签查train class均值，明确`LABEL_CONDITIONED_STRESS`，不是独立自然domain shift或test选参。
- **D3方向本提案解决为固定`[+1,+1,+1,+1,+1,+1,+1,+1]`**，bias=.25/.5/1×train_SD。方向是事前登记的统一positive sensor-offset stress，不是train-derived风险方向；只有幅度由train决定。不用标签、test结果、均值符号或额外方向搜索，不称所有特征都“更危险”。这采纳P3已验证的固定正向路径，而非增加数据驱动headroom方向规则。
- D3记录级missing率=.05/.1/.2：在固定4500个source ID上按seed42派生hash全局排序，取嵌套prefix恰225/450/900条；每affected source按独立seed42 RNG随机选恰1/8特征，跨强度/模型保持同一feature。保存population ID hash、选择rank、feature index、请求/实际比例、source/injected/combined mask。先确认源无NaN；若出现，停止协议检查，不能把mask已有NaN冒充“新增1格”。原始8列不增删，不引入标签/风险等排除特征。

**Bounds冻结为分层报告，不裁剪、不丢行：** `REPORT_ONLY_NO_CLIP`。speed与headway的逻辑/domain下界0来自其速度/距离语义与既有km/h、m契约，不是设备认证；upper未知。accel/steering符号允许正负，brake/throttle/lane单位与物理上下限缺乏充分契约，记UNKNOWN；不猜0–1、0–100或法定速度上限。以下仅为本轮train21000条新计算的**经验支持区间**，绝不称为physical validity bounds：

| Feature | train min | train max | 已有domain范围 / 未知 |
|---|---:|---:|---|
| speed_kmph | 20.0 | 118.43983141168286 | 下界0；上界UNKNOWN |
| accel_x | -.9496171195275332 | 5.308924454984119 | physical bounds UNKNOWN |
| accel_y | -.4797183579219134 | 1.664604719278922 | physical bounds UNKNOWN |
| brake_pressure | .0031284689143873 | 99.99436534101304 | 单位/physical bounds UNKNOWN |
| steering_angle | -49.10802185530833 | 53.42680553362417 | physical bounds UNKNOWN |
| throttle | 20.001443716829353 | 99.99476210241048 | 单位/physical bounds UNKNOWN |
| lane_deviation | .0000013439689708905078 | 2.3359161325462123 | 单位/符号定义/physical bounds UNKNOWN |
| headway_distance | 5.011333019940173 | 49.99892385921925 | 下界0；上界UNKNOWN |

每feature分别记录source、raw+delta（mask之前）、observed（mask后）和median-imputed final的domain/经验越界flag与幅度；missing处的状态为MISSING/UNKNOWN，不当作通过。保留mask前异常，不能让median填补把原越界证据抹掉。当前generator只检查final、只支持有限双边bounds的接口需要后续有界实现与synthetic测试，本轮不改代码。

**标签政策最终提案：**D0按原合成标签报告F1。D1/D2/D3没有独立数值行为标签有效性oracle，本轮正式E1主报告全部45k行的paired flip、L1概率漂移、逐类Δp/分布、missing与bounds统计，扰动标签统一`LABEL_VALIDITY_UNVERIFIED / f1_eligible=false`；不把“latent行为没变”的假设冒充已验证真值，不以D2 F1下降论证自然泛化。若以后要增加source-label-conditioned F1，须另行明确方法假设，不能看结果后补进本协议有效F1表。此保守处理遵循审计03“标签有效时才F1，否则flip/distribution”，没有缩减45k共享输入或三个benchmark模型。

### 8. 统计、决策优先级与预声明验收

- Vision primary clean为全3657 source的pooled描述性macro-F1；同时报告四driver各自指标、paired model差及leave-one-driver-out范围。QC各family也按相同driver分组。**只有4名test司机**，不将帧/变体当独立人群，不做帧bootstrap/p值或宣称显著优胜；无可靠clip ID不伪造clip聚类。Telemetry按source配对，真实人物/旅程/generator独立群组未知，只解释本合成集。
- 历史test已多次评估的R27限制始终写入；未发现直接用test选参的既有审计结论不等于证明test从未影响开发。两视觉ImageNet recipe不同（MN V2/RN V1），MPS训练非逐位确定，DMD仍BLOCKED。
- **决策顺序事前锁定：**先检查身份/契约/数值有效性及执行证据；然后按冻结设计描述clean/robustness/类级权衡；runtime单独提供工程资源事实。ResNet与XGB的**validation优先**由用户已确定，P4任何结果不触发HPO、重选seed、阈值调整、裁切/方向改变或新加权排名。结果不理想也原样报告，不自动改选MobileNet、seed43或更换test。
- 审计03继承的vision macro-F1≥.80、telemetry≥.85仅作**clean结果目标达成/未达的独立报告**，不倒推为R4新增“比较实验必须通过”gate；corruption不套用该clean阈值。没有新增“必须优于baseline”“E1必须改善”“必须满足1s”等模型性能gate；离线benchmark不代替系统capture→render指标。
- 正式执行验收为四维：Implementation=已批准runner忠实执行；Testing=开test前val/synthetic门禁通过；Evidence=完整IDs/预测/参数/QC/计时/预算/失败日志；Reproducibility=模型/数据/源码/协议SHA、seed、软件/设备和真实Git状态可定位。技术门禁失败记FAILED/BLOCKED；预算截断记PARTIAL/TIME_BUDGET_EXCEEDED；模型分数或鲁棒性差是结果，不能伪装软件失败或删去。
- 后续**工程部署选择**另走系统轨道授权、实际目标环境和影子评估。若需要新工程门槛，须在对应评估前声明；不得用本次test再搜索超参/种子或自动覆盖当前部署。

### 9. 公平non-deployment Runtime Benchmark与ONNX权限

仅比较`MN-HPO42`与`RN-HPO42`，各获得相同输入/重复次数；不测random-weight架构，不把stable baseline与candidate不同格式体积或不同runtime延迟混排。当前只读inventory：Apple M2、8核(4P+4E)、24 GiB；macOS26.6.2 arm64；Python3.13.3、torch2.12.0、torchvision0.27.0、ONNX1.21.0、ORT1.26.0、numpy2.4.6、Pillow12.2.0、psutil7.2.2；onnxscript未安装。ORT列出CoreML/Azure/CPU仅证明provider可见，不证明两模型可加载或加速；本轮没有创建session。

**统一ORT CPU FP32协议**：intra_op2、inter_op1、ORT_SEQUENTIAL、ORT_ENABLE_ALL、关闭intra/inter spinning，单活动worker，不做per-model线程/图优化/provider搜索。线程含义与顺序执行依据[ORT官方线程说明](https://onnxruntime.ai/docs/performance/tune-performance/threading.html)。不和训练、E1或系统性能测量并行；接电保持开盖，记录电源/OS/温度相关可用状态，不改系统电源设置。

- 固定val100个来源（每类10，seed42按ID选择，与正确率/置信度无关），批准后从冻结val metadata选取，原图/预处理张量/顺序hash均记录；不是test、不是新选型集。两模型逐字节使用同一contiguous NCHW float32 bank。
- **6 paired rounds**，预登记3×AB、3×BA，再用seed42shuffle；每模型每round单独新worker，50 warmups、100逐请求latency、100连续batch1 throughput调用。因此每模型**300 warmups+600 latency+600 throughput**，不把warmup混入指标。
- 主timer=`perf_counter_ns()`围绕`session.run`至CPU logits返回，包括Python/ORT调度/输出分配；input dict/张量在timer外准备。排除session load、图像I/O/decode/resize/normalize、softmax、camera/network/fusion/UI。session初始化时间另列，不冒充端到端Live时延。
- 报每round及pooled p50/p95（统一`numpy.percentile(method="linear")`）、6round范围与全部原始时间；throughput=`100 / 完整100次batch1 loop总秒数`，不是1/p95。暂不增加batch8/16或MPS/CoreML实验；正式accuracy batch32的吞吐不可冒充batch1时延。600次调用也不是600名独立受试者。
- 每worker在import和输入bank就绪、session加载前记RSS baseline；另记加载后RSS。父进程每20ms采样RSS、保留实际采样间隔，报告sampled peak、peak−baseline；macOS `ru_maxrss`另列为整个worker生命周期高水位。会漏瞬时峰值、delta不等于精确模型独占内存，CPU RSS不等于MPS/统一内存全部使用量。
- 大小按同格式报实际bytes：当前两PT分别17052801/44803787；将来两份同设置ONNX分别量实际bytes，包含所有sidecar时注明。不得据较小PT推断更快/更低实际RAM。

**兼容门禁（下列数值是本次提案，不是R4原阈值）：**

1. 只读`.pt`用`weights_only=True`/CPU、strict state_dict，正确10类头、eval/inference_mode；构造`weights=None`但必须先完整载入冻结state，不能推理random模型或调用训练入口。核验class_to_idx c0…c9；保留原名`normal_driving`及runtime alias`safe_driving`，不换索引。
2. ONNX checker通过；输入`input` FP32 `[N,3,224,224]`，输出`logits` FP32 `[N,10]`、N动态、finite原始logits，不在输出端Softmax/LogSoftmax。**三vision身份都做parity**：两HPO新图，以及`MN-STABLE`旧PT对既有ONNX（只读、绝不重新导出baseline）。在同100个val张量上，以batch1和32/32/32/4分批，与**同batch**的PyTorch CPU reference比对，所有元素`abs(error) ≤ 1e-4 + 1e-4×abs(reference)`、argmax全部一致，记录max abs/relative/probability差；同bank的前2个及前9个再验证动态batch2与**正式每condition3657条的尾批9**。不增加val来源，不碰test，synthetic shape检查不能代替batch32/尾批数值parity。实际正式流程每condition独立按32分批，不能flatten后静默改变尾批设计。
3. 行为/类别映射由真实训练metadata、state head、保存val ID/类别及对应预测共同核对；不能只靠manifest字符串。上述是实现parity，不要求val100全猜对。任一兼容门禁失败，在test前停止，不放宽容差、挑样本或自动换exporter。

**需要另行明确授权的导出范围：**

- 仅两HPO冻结PT各导出一份benchmark/evaluation-only FP32 ONNX，位于新的`ml/outputs/runs/<approved_p4_run_id>/runtime_benchmark/{mobilenet_v3_large_search006_seed42,resnet18_search004_seed42}/model.onnx`；目录不得已存在，无symlink/覆盖、无外部权重引用。记录`candidate_package=false, deployment_eligible=false`、原PT SHA、ONNX SHA与I/O的`benchmark_manifest.json`。
- 统一现有legacy `dynamo=False`、opset17、`export_params=True`、`keep_initializers_as_inputs=False`、`external_data=False`嵌入权重、dynamic_axes batch、eval模式；constant folding保持相同（当前torch版本始终启用），不量化/FP16、不onnxsim、不自动安装onnxscript、不下载。当前torch API已只读确认支持这些参数，[PyTorch 2.12文档](https://docs.pytorch.org/docs/2.12/onnx.html)区分dynamic_axes与dynamo路径；该legacy路线尚未实测且已属弃用路径，失败就停止，不能宣称一定导出成功或静默切换。
- 本轮不得执行以上导出。未来“批准P4”若没有明确包含两份导出，也不能自行推定导出获批。P5的自包含candidate package、最终`runtime_manifest.json` schema及系统loader验包不在本轮；schema尚未确定不阻止**另获批准的benchmark-only**导出，但阻止宣称系统候选包已合格。R4§3的预处理/logits/I/O/class/hash要求仍遵守，不以benchmark名义导出其他模型。

### 10. 提议执行预算、停机规则与实际阻塞

**以下是新P4请求的硬上限提案，非已批准预算，也非耗时预测。** CPU batch评估没有本轮实测速度，不能把历史MPS val约240–250img/s当CPU预计速度。既有HPO剩余预算不转移到P4，也不授权新增HPO。

| 顺序阶段 | 机器墙钟上限（含本阶段开销） | 限定范围 |
|---|---:|---|
| val-only preflight / 两ONNX导出与checker/parity | 600 s | 只export两HPO各≤120s；三vision身份各checker/parity≤120s（包含stable）；所有开销仍受600s总cap，失败整组停止 |
| 正式ID/共享输入与盲审case准备 | 1200 s | 全量manifest/参数/hash；QC图片仅≤3800，不存69k重复PNG |
| Vision clean cache | 1200 s | 3身份各≤400s，最多10971条clean预测 |
| Vision 18种stress | 7200 s | 3身份各≤2400s；最多197478条stress预测；clean只复用 |
| Telemetry D0及D1–D3 | 1200 s | 4身份各≤300s，共180000条；同一45k输入；无fit |
| 两HPO vision runtime benchmark | 1800 s | 每模型≤900s，12worker各≤90s（初始化计入worker）；6 rounds |
| QC合并、指标与证据完整性核验 | 1200 s | 只聚合已缓存预测/人工判定，不再forward |
| **总机器硬上限** | **14400 s = 4小时** | 串行累计，包含进程启动/失败开销；人工等待暂停累计，不算成机器测量时间 |

CPU计算≤2线程、单活动推理worker、评估batch32/runtime batch1；runtime worker观测RSS到4GiB、评估/生成worker观测RSS到8GiB就停，采样不是内核硬限额且可能漏瞬时峰值。run磁盘输出≤20GiB（不需要dump全部FP32输入张量）；启动前可用磁盘≥20GiB、可用RAM≥8GiB，缺资源就停，不驱逐系统进程。线程限制只作用于独立worker并记录实际thread pools，不改共享环境。当前`df -k .` available319026436KiB仅是review时快照，不保证执行时仍有空间。实现/val-synthetic软件验证需先获授权并完成，不将本表伪装成它们已存在/已通过。

**人工QC提案：两位reviewer合计≤16人时**（每人≤8h，跨天可进行；不是agent自动等待16h）。7600判定×未实测5s≈10.56人时仅供规划，剩余用于说明/盲化/复核；没有承诺该速率。达人工cap仍未双审的case保持UNREVIEWED/UNCERTAIN，QC评分覆盖记PARTIAL，不降低标准、不自动增加source或假判有效。两位实际人选、可用性与该预算尚未落实，这是执行阻塞而非训练阻塞。

任一hash/ID/契约/NaN/finite/parity失败在正式test前停止；正式过程中错误、模型/阶段/总时间或内存/磁盘触顶，安全保存原始失败与已完成ID，`TIME_BUDGET_EXCEEDED/PARTIAL`，不自动重跑、缩样本、删reference、降精度、改batch、换设备或扩预算。若需续跑，另获批准，仅补相同协议/相同身份尚未计算的ID并复用已完成cache，不重算已完成clean，不据已看结果改方案。部分配对只能标实际共同覆盖，不能冒充全量比较成功。

**现状判定与审批边界：**

| 项 | 本轮状态 |
|---|---|
| validation模型优先级/配置/seed与identity | VERIFIED_PASS：用户已决定，五身份SHA与旧baseline保护通过，无新HPO |
| P4-PROTOCOL-v1技术/统计方案 | **READY FOR PROTOCOL APPROVAL**：本节给出完整具体proposal，未执行、未自批准 |
| 正式P4执行器/QC界面与统计合并 | **NOT_READY / IMPLEMENTATION_REQUIRED**：现有generator只准val/synthetic；缺test reader/授权门禁、single-clean cache、双reviewer合并、QC common-valid、半开放/unknown bounds及mask前flags、paired benchmark与预算监督器 |
| 合成/val门禁、导出与parity | **NOT_RUN / APPROVAL_PENDING**：旧176tests/3761checks不验证这些新增P4要求；旧vision_benchmark含random导出且默认all/test，不可直接运行 |
| 人工QC | **APPROVAL_PENDING**：两位reviewer与≤16人时待确认；≤200source的评分范围须明确接受 |
| ONNX benchmark/evaluation导出 | **APPROVAL_PENDING**：需要明确批准两份、固定legacy/opset17路径及600s阶段cap；失败不装包、不换exporter |
| held-out clean/E1/runtime实际执行 | **NOT_STARTED / 未授权**：14400s与资源上限是提议，不是默认准许；正式执行之前必须先通过上述实现/val门禁 |
| P5/部署 | NOT_STARTED：最终schema、候选打包、系统影子评估和替换均另批 |

因此回答“P4是否READY FOR APPROVAL”：**协议可供审批；P4执行尚未就绪，也没有获准。** 等待用户确认本节的baseline reference范围、QC子集/人力、D3正向/unknown-bounds/扰动标签政策、CPU协议、新兼容容差和14400s预算，并明确ONNX权限。随后才可在新授权范围补齐执行器和val/synthetic验证；不得因为协议获批就跳过门禁直接访问test。当前只更新本规范报告，不新增review文档、不提交，不改现有preparation profile的`formal_execution_authorized=false`。

## 2026-10-20 补充：独立agent模型选择分析完成，仍停在P3之后

用户补充要求其他agent分析刚刚的训练/HPO结果并建议选择什么model。本次仅在既有`ML_RESULTS_REVIEW_CONTEXT.md`加入明确的模型选择审阅任务、两位独立agent的已完成结论及证据路径，不新建进度/分析报告。遥测审阅首次因额度未完成，用户要求继续后重试成功；视觉与遥测现在均已完成只读分析。没有启动P4、额外训练/HPO/forward/test/E1、下载、候选导出或部署。

六项Git开工检查仍为正确root、`fyp2/ml-training`、HEAD335da4e；dirty均为此前已知ML产物/报告及受保护09，无新增异常路径。主agent仅读现有原始JSON核对两个vision选中class reports、三telemetry选中metrics/seed/selection，以及五模型汇总；另复算ResNet seed42 macro-F1差2.439518个百分点、确认均值差3.113474个百分点，XGB/RF macro-F1差4.938272e-13。没有打开原始test数据或加载模型。

| 模态 | 独立审阅与主复核建议 | 明确局限 |
|---|---|---|
| Vision | 优先评估ResNet18 `search_004` / seed42；保留MobileNet `search_006` / seed42配对比较 | ResNet val宏F1/均值较高，但std较大、c0 recall较低；不选最高seed43，不改预注册目标。文件大小不证明运行时延 |
| Telemetry | 架构优先XGBoost、离线关注`tuned xgboost_02` / seed42；保留RF/LR对照 | XGB/RF分类实质持平（各错5/4500），XGB log-loss更低；合成高分/零std不等于真实域泛化或显著性。RF/LR仅benchmark，当前tuned XGB joblib也非部署文件 |
| 当前部署 | 继续旧MobileNetV3-Large + 旧XGBoost baseline | 推荐候选不等于替换批准；P4/P5仍未开始 |

证据来源及完整权衡保存在同一份`docs/fyp2/ml/ML_RESULTS_REVIEW_CONTEXT.md`的“已完成的独立模型选择分析”节，原始路径/精确数值可供其他agent继续复核。Implementation/Testing/Evidence/Reproducibility均只在**文档与保存结果核对范围**交付；未重跑176软件tests或3761准备checks，不把历史通过数声称为本轮新执行。原训练/生成器代码、配置、模型、selection及日志不变。本次只修改context和本规范报告，保护hash与暂存区另作最终核对；不commit、不push，继续等待P4协议/预算与执行授权。

## 2026-10-19 最新停止点：P3 E1 generator / QC接口准备与独立分析context

用户在S3结果说明后批准“进入下一步”，并要求提供其他agent分析context。本轮按S3已列出的下一动作，仅补齐P3的E1生成器与QC接口并用synthetic/val验证；**不是P4正式test/E1授权**。没有追加模型训练/HPO、模型加载或forward、权重下载、test图像/telemetry_test CSV读取、候选导出或部署。本节为当前状态，下方S3及更早章节保留为历史证据。

开工六项Git检查确认cwd/root正确，branch=`fyp2/ml-training`、HEAD=`335da4e3de203836c045452f84cc291bcd352a26`，staging为空；既有dirty项仅S3规范报告、受保护09报告和已知正式search/核验产物。fast-context仍缺Windsurf key，使用精确文件读取替代。两份权威说明由当前repo的`git show fyp2/live-system:...`读取，最新P2/P3 prompt仍只允许synthetic/val生成器准备。本轮没有进入Live-System目录、改共享环境/应用/CSV、commit或push；09报告及三个部署基线保护hash前后相同。

### 实现、复用与参数边界

- 新增`ml/experiments/e1_generators.py`：确定性的source ID+seed42 SHA派生随机数；E1-V clean+6×3=19种，包含真正线性motion kernels3/7/11、方向、遮挡box/实际面积、旋转符号和crop几何、grayscale blend参数及pixel SHA。保留RGB/PIL bilinear直接224²预处理，不引入horizontal flip；Gaussian不叫motion，grayscale不叫IR。
- E1-T D0+3×3=10种/source：D1按train SD加噪；D2按train global/class mean作`LABEL_CONDITIONED_STRESS`；D3记录固定方向bias与可复现嵌套missing masks。按用户本轮补充，D3为**5%/10%/20%的记录受影响，每条恰好新增1个缺失特征**，不是8特征各自独立Bernoulli。保留raw/observed/shared-imputed特征、delta、源/注入/合并mask、选中特征索引、population hash、请求/实际缺失率、train hash及source ID。**每个source只生成一份，三模型共用**，LR后续仍使用既有train-fitted scaler。
- `qc_decision()`记录独立reviewer/reason/validity，默认PENDING、f1_eligible=false；无效样本仍保留flip/distribution。接口测试通过不等于实际独立人工QC已完成；本次全部490条validation记录F1 eligibility=0，无任何robustness性能分数。
- `ml/experiments/run_e1_preparation.py`固定仅10张val图像（10类各1）与30条val遥测（3类各10），新run拒绝覆盖。两次应用同一canonical transform，190个输入均finite、float32 `[1,3,224,224]`且逐字节相同。只做生成/预处理，无model forward。
- **REUSED_AND_VERIFIED**：P0 `w2_preparation_20261015/preparation_evidence.json`的train-only median/global mean/SD/class means。只读train21000条重新计算统计并比对，train SHA=`97dd20ee9c0832ba33455e5c31088f9b4abb65c198bf988699a959d545d1e5b5`；与三个选中遥测trial的train hash/feature order/median也一致。没有重新拟合分类器或改写历史统计；数据冻结、class order、source ID命名、预处理、五模型HPO选型/结果和S3审计全部复用。

`ml/configs/e1_preparation.json`记录用户补充决定：D3 **record-level** `.05/.1/.2`、每条随机1/8特征、seed42、三模型shared masks、train-only median，状态`PROPOSED_UNTIL_FULL_P4_PROTOCOL_FREEZE`，**不构成P4执行批准**。实现按seed42+source ID hash对本次输入population排序，取嵌套prefix；人数取`floor(N*rate+0.5)`（明确披露的整数取整实现），特征独立按source ID+seed42选择并跨severity固定。4500 synthetic sources恰为225/450/900条；30 val样本为2/3/6条，实际6.6667%/10%/20%，记录请求和实际比例，不伪称小样本恰5%。原始source缺失与新增缺失分别记录；当前干净8特征无原始NaN。

全正D3漂移方向仍只是准备示例；physical bounds保持UNRESOLVED且不静默clip；`centered_inscribed_square`是可复现的拟议旋转裁切实现，正式几何仍待确认。正式freeze字段继续null，proposal与批准执行分开。生成器在P3主动拒绝train/test observations；P4须在新授权下增加held-out reader，不绕过此门禁。

### 实际命令与验证结果

以下命令均真实执行；最终stdout/stderr日志已复制至`ml/outputs/runs/e1_preparation_20261019_record_missingness/verification/`，命令列表、源码/输入/日志SHA分别见config与artifact manifests。

| 命令 | 日志 / 实际结果 |
|---|---|
| `./.venv/bin/python -B -m pytest -q ml/tests/test_e1_generators.py -p no:cacheprovider` | `generators-red.log`：先**29 failed / .34 s**，确认为缺少生成器；不是训练失败 |
| `./.venv/bin/python -B -m pytest -q ml/tests/test_e1_preparation.py -p no:cacheprovider` | `preparation-red.log`：先**13 failed / 1.43 s**，确认为缺少准备runner的统计/范围门禁 |
| `./.venv/bin/python -B -m pytest -q ml/tests/test_e1_generators.py -k 'd3 or 4500' -p no:cacheprovider` | `record-missingness-red.log`：用户补充后先**4 failed / 27 deselected / 1.45 s**；实际复现旧草案每条可能mask多个特征、受影响记录数不符 |
| `./.venv/bin/python -B -m pytest -q ml/tests/test_e1_generators.py ml/tests/test_e1_preparation.py -p no:cacheprovider` | `e1-green.log`：**44 passed / 2.13 s**；像素oracle、motion非Gaussian、crop/occlusion参数、seed/顺序独立性、train-only/NaN imputation、D2公式、D3记录计数/一条一特征/嵌套mask/小样本取整、bounds不clip、QC、4500 synthetic→45000计数及范围门禁 |
| `./.venv/bin/python -B -m pytest -q ml/tests -p no:cacheprovider` | `suite-green.log`：**176 passed / 21.25 s**；软件测试不替代正式E1 |
| `./.venv/bin/python -B ml/experiments/run_e1_preparation.py --run-id e1_preparation_20261019_record_missingness` | `execution.log`：**E1_PREPARATION_COMPLETE**；10 val图像→190变体、30 val遥测→300变体；runner主体墙钟**2.223334834 s**（不含进入main前import）；CPU threads2，OS峰值RSS**456212480 bytes**，userCPU1.575948/systemCPU.318937 s；0fit/0模型加载/0forward/0held-out observations |
| `./.venv/bin/python -B ml/outputs/runs/e1_preparation_20261019_record_missingness/verification/verify_preparation.py` | `verification.log`：**3761 checks通过**；产物/源码hash、计数/IDs/class balance、共享median、D2独立公式、D3实际2/3/6条与一条一特征/嵌套mask、QC门禁、保护hash及dirty/staging真实性 |

用户补充前的初稿也实际执行过29项GREEN、42项GREEN、174项suite及一次190+300 val准备（1.785324167s、3118checks），保留在`e1_preparation_20261019/`，现有`superseded_protocol.json`明确其D3逐特征语义已被取代；源码/测试/profile在改动前按原SHA存入该run的`source_snapshot/`，旧config/CSV/日志未改写。重现旧版本须使用snapshot，不拿已变动的当前源码去冒充旧hash。**最新接受的准备结果是record_missingness run**。最终suite与val生成检查曾同时运行，以上耗时仅记录执行情况，不是性能benchmark。

45000是**合成单元测试的生成计数**，正式4500条test source未读取；实际val准备仅300条共享遥测变体，不能称正式45k E1已执行。vision split metadata含既有test membership且为验证冻结SHA被读取，但未返回或打开任何test图像；telemetry仅train/val CSV。R26/R27、合成遥测限制、DMD BLOCKED继续适用。

### 文件、证据与独立agent context

代码/测试为`e1_generators.py`、`run_e1_preparation.py`、`test_e1_generators.py`、`test_e1_preparation.py`；准备profile为`ml/configs/e1_preparation.json`。隔离run下的`config.json`、`preparation_checks.json`、`vision_manifest.csv`、`telemetry_variants.csv`、`source_images.json`、`artifact_manifest.json`保存ID、train/val/源码/版本/参数/hash与结果，`verification/`保存RED/GREEN/执行及核验日志。图片变体只在内存生成，未保存190张重复PNG；pixel/tensor hash+源图hash+固定代码/参数可复现，不构成最终E1图像集freeze。

按用户本轮明确要求额外提供 **`docs/fyp2/ml/ML_RESULTS_REVIEW_CONTEXT.md`**：五模型结果、配置、seed波动、证据路径、历史baseline与smoke/probe区别、结论边界、P4待决问题及给独立agent的分析范围；它不是第二份progress/status。没有实际向任何agent发送消息或启动新agent。

本轮准备源码未提交，执行config如实记录HEAD335da4e及dirty state，另保存源码SHA；**不声称准备运行来自clean commit**。这与正式search原始clean335da4e记录分开，未改写任何旧HPO输入/输出。当前未暂存/提交新文件，源CSV和四项保护hash不变。

### 四维验收、sprint与下一阶段

| 范围 | Implementation | Testing | Evidence | Reproducibility | Verdict |
|---|---|---|---|---|---|
| P3 E1生成器/QC接口软件准备 | 完整6×3及D0–D3、记录级一条一特征mask、参数/ID/QC接口与仅val门禁 | 44新增tests与完整176tests；190+300实际val生成；3761产物checks | 独立run日志/manifest/hash/config齐全，无正式指标 | seed/source/population/参数/版本/SHA明确；原始统计复用；未提交状态如实记录 | **VERIFIED_PASS（软件/validation准备范围）** |
| 五模型HPO / S3 | 继承上节冻结选型与41次正式训练/fit | 原16视觉+25遥测与保存审计复用 | 原完整metrics/checkpoints/selection logs复用 | 原执行commit/snapshots/seed不改 | **REUSED_AND_VERIFIED / VERIFIED_PASS** |
| P3整体E1协议准备 | 生成器已补齐；记录级missing方案已proposed，整体drift/bounds/crop/QC与身份/统计协议待冻结 | 独立recognizability QC未执行；正式配对test未创建 | proposal/准备示例明确，无伪造正式E1证据 | 正式freeze待批准 | **PARTIAL / APPROVAL_PENDING**，不倒推为R4新增性能阈值 |
| P4最终clean test / 正式E1 | 未启动；保持一次final test规则 | NOT_RUN | 无本轮test/E1性能 | 依赖冻结协议和新授权 | **NOT_STARTED / 未授权** |
| P5候选包/ML证据冻结 | 未启动 | NOT_RUN | 无新package | 依赖P4及系统最终runtime manifest schema | **NOT_STARTED / 未授权** |

Week2 ML准备、Week3 trainer+真实smoke、Week4 comparator正式训练均保持**VERIFIED_PASS**；Week5的HPO和生成器软件已通过，正式E1准备协议仍**PARTIAL / APPROVAL_PENDING**；Week6正式test/E1与Week7候选包**NOT_STARTED**。这是ML范围，不替系统轨道验收，也不更改Week5/Week7主里程碑。

**本阶段到此停止。** 按用户补充，不进入P4。P4前将D3记录级5/10/20%方案连同漂移方向、physical bounds/out-of-range处理、旋转裁切几何、独立QC protocol、冻结模型/untouched baseline对照身份，以及driver/clip统计口径、设备/墙钟预算整体冻结并批准。held-out ID manifest在P4授权后创建；不把P3禁止test读取解释为允许提前读取观察数据。本轮不发明最小macro-F1、必须优于baseline等新硬门槛。先供其他agent独立分析现有结果，不自动开始正式实验。

## 2026-10-19 最新停止点 S3：五模型正式HPO结果核验与validation比较

用户终端已完成 `caffeinate -dims ./.venv/bin/python -B ml/experiments/run_vision_hpo.py search --run-id p3_vision_20261018`，输出`SEARCH_COMPLETE`、`BUDGET_EXCLUDED_TRIALS []`及`VISION_STATUS search COMPLETED used_seconds 15288.353217291064`。本节取代下方“等待search”的历史状态。S3只核验保存产物、汇总五模型val选型与确认波动，之后停止；**本轮代理没有fit、model forward、下载、重新训练、打开原始test CSV/图像、正式E1或打包/部署**。

本轮Git六项检查：cwd/root正确，branch=`fyp2/ml-training`、HEAD=`335da4e`；开始时仅有受保护09报告与用户刚生成的`search/`、`search_config.json`、`search_state.json`和根selection日志为untracked，均符合当前run。实际训练记录`execution_commit=335da4e3de203836c045452f84cc291bcd352a26`、`tracked_worktree_clean=true`、无staged、首次仅09报告untracked。执行源码4文件、预注册protocol、批准预算与该Git blob及当前字节一致。Prompt/R4再次字节hash核对，仍为`53c53b...9b48` / `5a46fe...5ff`；没有进入Live-System工作区。fast-context因缺Windsurf key失败，改用精确文件读取。

### 实际次数、预算与资源

| 模型 | 搜索/确认、epochs | 本次墙钟 / 批准模型预算 | 最慢trial | 结果 |
|---|---|---:|---:|---|
| MobileNetV3-Large | 6个seed42搜索+43/44确认；8 attempts；43 epochs | 8244.061593375 / 17100 s | 1624.689750667 s < 2400 s | 全部COMPLETED / returncode0 |
| ResNet18 | 同6+2；8 attempts；38 epochs | 7041.178746042 / 15300 s | 1489.546447125 s < 2400 s | 全部COMPLETED / returncode0 |
| 视觉合计 | 16逻辑trial=16实际attempt；81 epochs | **15288.353217291 / 32400 s** | 包含约3.112877874 s监督器开销 | **无失败、中断、超时或NOT_RUN_BUDGET；excluded=[]** |

视觉约 **4小时14分48秒**，使用批准总预算47.1863%；早停使实际epochs少于128上限，不能把剩余预算当作追加trial授权。每模型首网格作为P2且只计一次，probe另账且不计正式HPO。本轮复用遥测25次实际fit（XGB10/RF8/LR7）；加上视觉16次，共41次实际正式fit/训练操作，未超过原各模型上限。LR确定性重复虽消耗fit次数，不作为独立随机性证据。

训练保存的OS峰值RSS最大值：MobileNet1047281664 bytes、ResNet927268864 bytes；同步batch后观测MPS driver最大值4688871424 / 3700080640 bytes。两种口径不相加，采样可能漏瞬时峰值，不用作部署内存硬保证；本轮未另做runtime推理时延benchmark。

### 五模型validation结果：按模态比较，统一冻结seed42

| 模态 / 模型 | 选中trial、配置 / best epoch | Val accuracy | 选中seed42 val macro-F1 | 对选中配置的seed macro-F1 mean ± std(ddof=0) |
|---|---|---:|---:|---|
| Vision / MobileNetV3-Large | `search_006`；lr=.0008、wd=.001；best epoch6（实际8epochs） | .922942817 | **.916219868** | 42/43/44：**.893662816 ± .015950461** |
| Vision / ResNet18 | `search_004`；lr=.0003、wd=.001；best epoch3（实际5epochs） | .942119944 | **.940615048** | 42/43/44：**.924797552 ± .027113633** |
| Telemetry / XGBoost | `xgboost_02`；depth3、lr=.03、subsample1、400 trees | .998888889 | .998888888 | 42/43/44：.998888888 ± 0 |
| Telemetry / Random Forest | `random_forest_06`；400 trees、depth24 | .998888889 | .998888888 | 42/43/44：.998888888 ± 0 |
| Telemetry / Logistic Regression | `logistic_regression_06`；C1000、lbfgs | .996888889 | .996888581 | 42/43：.996888581 ± 0；43确定性重复、44按批准规则跳过 |

selected seed42 log-loss依次为MobileNet .306039094925、ResNet .186423733830、XGB .004925716203、RF .008043999630、LR .008746305336。机器汇总与源报告路径见`ml/outputs/runs/p3_vision_20261018/verification/validation_metrics.json`；各trial逐类报告、confusion、原始logits/probabilities继续复用原文件，不生成重复人类总结。

视觉固定模型为：

- `search/mobilenet_v3_large/search_006/attempt_01/checkpoint.pt`，17052801 bytes；seed42，lr8e-4/wd1e-3、epoch6。
- `search/resnet18/search_004/attempt_01/checkpoint.pt`，44803787 bytes；seed42，lr3e-4/wd1e-3、epoch3。

这些路径均相对于`ml/outputs/runs/p3_vision_20261018/`，完整SHA见机器汇总与原manifest。ResNet seed43的.947139072虽高于seed42，**不得替换被冻结的seed42**。旧MobileNet `.pt/.onnx`与旧XGB权重hash未变，未导出新ONNX或部署。

### 结果解释与类级限制

本次validation中ResNet的选中seed42分数和三seed均值均较高；这是指定完整pipeline在同一val split上的观察，不是最终test或显著性结论。MobileNet三seed为`.916219868/.882486085/.882282496`（范围约3.394个百分点）；ResNet为`.940615048/.947139072/.886638536`（范围约6.050个百分点），ResNet波动更大。三点标准差只描述此次运行，既不是置信区间，也不能把变化全部归因为MPS或证明逐位复现。

类级结果也非全面胜出：选中MobileNet的`c9 talking_to_passenger` F1=.669767442，仍为弱类；ResNet相应F1=.877637131。`c0 normal_driving`则MobileNet .866556837、ResNet .840531561；ResNet的`c8 hair_makeup` F1=.879712747。全部10类支持数/precision/recall/F1与confusion已独立复算，详见原`class_report.json`及预测审计，不能仅凭macro-F1推广为全部行为或真实风险改善。

复用原val基线仅标`STORED_NOT_RERUN`：MobileNet accuracy=.897489540、macro-F1=.890650772；XGB accuracy=.998444444、macro-F1=.998444443。不引用旧test作为本轮对照，不把单次旧基线与HPO选中峰值差异当作无偏改善估计。所有选型/early-stop/确认都使用同一val split，seed42在6组配置中择优具有选择偏差；正式held-out test尚未运行。两种ImageNet预训练仍为MobileNet V2 / ResNet V1，不能把全部差异归因为架构。Telemetry为合成、近线性可分数据，高分与零std不证明真实驾驶泛化、概率逐位一致或安全收益；RF/LR仍仅benchmark。

### S3核验：实际命令、结果与证据

一个主核验与两项独立只读核验，各只在该run的新`verification/`子目录写脚本/日志/机器证据，不改原训练产物：

```bash
./.venv/bin/python -B ml/outputs/runs/p3_vision_20261018/verification/artifacts/verify_artifacts.py
./.venv/bin/python -B ml/outputs/runs/p3_vision_20261018/verification/predictions/verify_predictions.py
./.venv/bin/python -B ml/outputs/runs/p3_vision_20261018/verification/protocol/verify_protocol.py
```

| 核验范围 | 实际结果 / 限制 |
|---|---|
| `artifacts/verification.log` | **5276断言 / 0失败 / 1.510180208 s**；176条视觉产物与250条遥测产物exists/bytes/SHA复核；16个视觉checkpoint仅CPU `weights_only=True`读取，核class/head/recipe/seed/best epoch及全部finite tensors；无模型构造/forward；旧遥测执行源码snapshot hash吻合 |
| `predictions/execution.log` | **2249断言 / 0失败 / .696202500 s**；16attempt、45,888条保存val预测、96输入文件前后SHA不变；同train15899/val2868、18/4名司机无交集、IDs/原metadata索引/顺序一致；float32 NPY/CSV、logits→softmax/argmax、accuracy/macro-F1/log-loss、confusion及全部class report一致；81epochs的batch/sample/timing记录核对 |
| `protocol/verification.log` | **557/557断言通过**；6×2搜索+43/44确认、grid/P2归属、T_max8/patience2、stdout逐epoch、returncode/预算、独立排序/mean/std、Git335da4e clean来源与config/signature匹配。此脚本未另记录墙钟测量，不虚构耗时 |

这些是保存结果的核验断言数，不是新训练次数或全仓库CI。上阶段132软件tests属于已保存证据，本轮没有为改进进度标签而重跑。所有完成worker原记录16样本reload已通过；本轮读取checkpoint不代替独立数值重训或重新forward。

两个核验细节已如实保留：预测验证器初版误把`source_row`当作split局部连续索引，出现32个验证器误报；确认loader保留完整metadata索引后，改验唯一/非负/递增，初次日志保存在`initial_validator.log`，没有改训练数据。另一次Unix start与monotonic elapsed拼接出现−41ms差值，不能据此认定并发；同步监督器源码和顺序日志支持逐trial执行，但没有捕获同一时钟的独立结束时间，局限记入协议审计。

### 四维验收、sprint与停止点

| 范围 | Implementation | Testing | Evidence | Reproducibility | Verdict |
|---|---|---|---|---|---|
| P2三个comparator正式单配置训练 | RF/LR首网格复用；ResNet首网格现已完成并计入HPO | 全量train/val、合法早停、finite/shape/order、原save/reload已执行并核验 | 正式checkpoint/config/预测/ID/metrics完整 | 固定输入/seed/source hashes可追溯；不追加重复fit | **VERIFIED_PASS（formal validation范围）** |
| 五模型bounded HPO子任务 / S3 | 原grid/上限/选型/冻结规则全部执行 | 视觉16成功+遥测25实际fits，确认/独立核验通过，无新截断 | trial/selection/预算与五模型val汇总齐全 | 执行commit或历史snapshot可定位，确认波动披露 | **VERIFIED_PASS（HPO子任务及S3交付）** |
| 整个P3 / Week5 ML milestone | HPO已完成；R4 E1 generator/QC准备仍未齐 | 未验证完整配对扰动/参数/计数/QC流程 | 旧`robustness_probe.py`仅val1000样本、brightness+Gaussian blur、单基线聚合评估，不能代替R4完整vision/telemetry生成器 | 正式生成器freeze/paired manifests尚缺 | **PARTIAL**，不将本次HPO完成冒称P3/Week5全验收 |
| P4最终test/E1；P5包 | 尚未执行 | NOT_RUN | 无新test/E1/candidate证据 | 待新授权及冻结协议 | **NOT_STARTED / 未授权** |

Week2准备及Week3 ML comparator+smoke的原VERIFIED_PASS继续复用；Week4完整comparator训练已有真实正式证据，但不替系统轨道验收，不改W5/W7主里程碑。R27“旧test曾被多次评估”继续披露，后续P4也不能称全新从未见过holdout。

**停在S3。** 下一轮应在既有P3范围内补齐并验证R4 E1 generator/QC准备，仅synthetic/val软件检查，不运行正式held-out E1；之后先明确P4冻结模型清单（包括适用的untouched baseline checkpoint对照、按身份去重）、一次final clean test与E1参数/标签有效性/QC/分组统计，再请求P4执行授权。P5按R4§3完整打包，另行批准，不自动替换线上基线。本轮只更新本规范报告及机器核验证据，不提交、不push，不自动开启下一阶段。

## 2026-10-19 最新交付：S2预算已批准，模型预算隔离修复已提交

用户明确批准 `per_trial=2400 s`、MobileNet `17100 s`、ResNet `15300 s`、`total=32400 s`，要求先修复模型预算互相阻断、TDD及完整ML tests，再分别提交监督器、测试、预算，不push。该批准覆盖正式视觉search的具体数字，**视觉训练仍由用户自己的终端运行**；本轮没有启动probe/search、fit/forward、下载、held-out test、E1或package。

开工Git六项检查：cwd/root正确，branch=`fyp2/ml-training`、初始HEAD=`c6d1f65`；全部dirty项均为此前已记录的监督器/测试/ignore/两份ML文档及该probe run，09审阅报告保持受保护untracked，没有未知改动。fast-context优先调用仍因Windsurf key不可用失败，改用精确文件/函数读取，没有提取凭据。

### 问题、实现与真实验证

旧调度器把任一trial/model超限写成整个search的`NOT_RUN_BUDGET`并break，且terminal early return阻断后续模型。现有修复为：

- `per_trial`或`per_model`触顶只写该模型的`model_budget_stops`和剩余trial的`NOT_RUN_BUDGET`，保留已完成trial并继续下一模型；只有`total`触顶全停。模型封停后另一模型若中断，同run续跑只续允许的模型，账本/旧attempt/原始截断scope不重置。
- 预算检查先于confirmation选型，避免首模型无完成search时阻断另一模型。截断attempt保留`TIME_BUDGET_EXCEEDED`，即使残留checkpoint或高分metrics也不进入选型。无完成search的模型记`NOT_SELECTED / NO_COMPLETED_SEARCH`；确认不足明确列missing seeds。
- 模型级不完整整体为`PARTIAL`，total耗尽为`NOT_RUN_BUDGET`；两者都输出`SEARCH_PARTIAL`、选择日志和`BUDGET_EXCLUDED_TRIALS`。`search_state.json.excluded_trials`逐项保留model/trial/role/seed、scope/reason、attempt和实际截断或未启动状态。所有可生成selection的terminal路径都复核已完成产物，损坏时拒绝发布/自动重训。
- search写文件/启动worker前拒绝staged及tracked修改，且四份执行源码、预注册protocol和预算文件必须逐字节等于`HEAD`。唯一允许的未跟踪例外为受保护09报告及当前run自己的输出；原始Git状态如实记录，另写`tracked_worktree_clean=true`和`execution_commit`，不伪称完全空的git status。新search记录最终已提交HEAD，旧probe context原样保留。

由主代理实现，一名独立只读审查agent复审预算/选型/clean门禁，没有让agent运行训练。审查发现并补回归的三项边界是：后续total停止不能覆盖先前per-trial截断原因；多个余额为负时total判断优先；total终态重新输出selection前也必须验证完成checkpoint。

TDD原始证据位于 `ml/outputs/runs/p3_vision_20261018/s2_budget_verification/`：

| 实际命令 / 日志 | 真实结果 |
|---|---|
| `./.venv/bin/python -B -m pytest -q ml/tests/test_vision_hpo.py -k 'mobilenet_budget_stop or total_budget_stops or other_model_resumes or model_cap_preflight' -p no:cacheprovider` / `model-budget-red.log` | **5 failed / 30 deselected / 1.76 s**；实际断言ResNet未被执行，先复现再修复 |
| 相同命令 / `model-budget-green.log` | **5 passed / 30 deselected / 1.94 s** |
| selection/clean六项RED / `selection-clean-red.log` | **6 failed / 35 deselected / 1.38 s**；新增partial selection、CLI报告和clean-source guard不存在 |
| 独立审查三项边界RED / `review-boundaries-red.log` | **3 failed / 43 deselected / 1.22 s**；先复现再修复 |
| `./.venv/bin/python -B -m pytest -q ml/tests -p no:cacheprovider` / `suite-green.log` | **132 passed / 16.52 s**，其中视觉调度46项；完整ML suite，无新增真实模型训练 |

精确命令、固定16条正式search/confirmation计划、4项保护hash、日志/源码SHA见该目录`config.json`与`artifact_manifest.json`。中间dirty tests的tmp fixture根目录不匹配曾导致3项测试失败，修正fixture后全部通过；不是训练失败。预算JSON在最终132项通过之后才写入，随后只做schema/精确数字/原grid/源hash校验，没有自动扩额或重跑模型。

归档staged检查仅对原始pytest RED日志提示尾部空白、旧status日志提示末尾空行；这些捕获证据保持原字节和hash，不做格式清洗。排除`*.log`后的staged diff空白检查通过，源码/JSON/CSV/文档没有新增空白问题。

### 提交与来源

用户要求的三个独立本地commit已完成：

| commit | 精确范围 |
|---|---|
| `64664e3` | `ml/experiments/run_vision_hpo.py` + `ml/.gitignore`：此前未提交的锁/中断恢复及本次模型预算、partial reporting、clean search修复 |
| `27c8860` | 仅`ml/tests/test_vision_hpo.py`：原有未提交回归及本次新增预算/恢复/选型/clean tests |
| `446c667` | 仅`ml/configs/approved_vision_budget.json`：用户批准的2400/17100/15300/32400秒，MPS/batch64/两线程/workers0不变 |

另将此前未提交的probe/recovery/软件验证小体积证据及本报告/既有运行说明单独归档提交，以清除剩余tracked/非例外dirty。此文档提交本身不改变执行源码或预算；最终运行HEAD以交付时`git log -1`及新search的`execution_commit`为准，不预造尚未执行的search日志。每次提交前核对精确staged路径、无symlink、无模型二进制、无单文件>5MiB；09报告不删除、不修改、不暂存。没有push/reset/merge/rebase/stash或进入Live-System工作区。

probe是在修复前源码`cc711202c31a5e23dc57108bccfcf0ff3c555af1b0ab8bdb583bcb7e8587590f`下执行。本轮已按此前确定的源码变更重建其逐字节快照，**SHA与probe记录完全匹配**，存入该run的`source_snapshot/ml/experiments/run_vision_hpo.py`。没有改写旧config/metrics/账本，不能把新的`64664e3`视为旧probe训练源码。

### 四维验收与下一动作

| 范围 | Implementation | Testing | Evidence | Reproducibility | Verdict |
|---|---|---|---|---|---|
| 本次监督器/测试/预算交付 | 预算按模型隔离、total全停、只用完成trial选型、clean commit门禁 | 关键RED→GREEN，完整132tests通过；真实dirty文档状态也被门禁拒绝且未创建search config/state | 独立3commits、预算JSON、原始日志/manifest/源码快照齐全 | committed源码/config可定位，旧probe来源保留；无新独立数值重训声明 | **VERIFIED_PASS（软件与审批交付）** |
| Week2 ML准备 | 历史冻结/75checks及当前保护hash通过，预注册协议/资源/全部正式预算审批缺口现已闭合 | 真实MPS probe已验证所选资源路径 | 既有P0证据复用、最新protocol/预算已提交 | frozen split/recipe/seed和预算可追溯 | **VERIFIED_PASS（ML准备范围）** |
| Week3 / P1 | 既有comparator pipeline/smoke继续复用 | 原真实smoke和保存复核；本次ML suite仍覆盖P1 tests | 不追加成功smoke | 不把旧random-init smoke算正式比较 | **VERIFIED_PASS（ML milestone）** |
| P2/P3正式视觉search | 数字预算已批准，CLI待用户运行 | **NOT_RUN**；当前run无search config/state、无被截断的真实正式trial | 没有虚构实际截断列表；未来由CLI生成并于S3纳入报告 | 新search将记录最终提交与source hashes | **整体仍PARTIAL；视觉执行待用户终端** |

search保持每模型6个seed42网格+2个selected配置确认seed43/44（总16逻辑运行），首网格计P2；epoch≤8、patience2、T_max8、224²预处理/augmentation不变。probe不计正式trial或正式预算。任何硬限达到均不扩额；真实截断trial在S3按保存账本列出，不能算选型候选、完整grid coverage或确认完成。原P4/P5和E2–E5/系统文件范围均未授权，W5/W7主里程碑不变。

最终交付前只做非训练clean-source preflight：确认已提交文件与HEAD一致、允许例外明确、保护hash不变、无暂存、search尚未开始。接电、保持开盖、一个终端、避免与系统轨道计时并发，然后由用户执行：

```bash
cd /Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1
caffeinate -dims ./.venv/bin/python -B ml/experiments/run_vision_hpo.py search --run-id p3_vision_20261018
```

结束后提供`SEARCH_COMPLETE`或`SEARCH_PARTIAL`、`BUDGET_EXCLUDED_TRIALS`与`VISION_STATUS search`；下一停止点S3只核验保存产物、正式选型/确认波动/截断列表，不自动开始P4或P5。

## 2026-10-19 最新停止点 S2：视觉 probe 完成，正式 search 预算待批准

用户已在自己的终端运行 `caffeinate -dims ./.venv/bin/python -B ml/experiments/run_vision_hpo.py probe --run-id p3_vision_20261018`，提供 `PROBE_COMPLETE` 和 `VISION_STATUS probe COMPLETED used_seconds 482.47383658390027`。本节覆盖下方“等待 probe / INTERRUPTED”的历史快照。当前 branch=`fyp2/ml-training`、HEAD=`c6d1f65`；Git 六项检查仅见本次已授权的修复/报告和该 run 产物，没有新的异常路径，staging 为空。09审阅报告仍未跟踪且哈希未变。本轮代理仅解读并核验保存产物、更新本报告，没有训练、模型加载/forward、权重下载、配置变更或提交。

### 实际 probe 结果与解释

| 模型 / 成功 attempt | 完整训练/验证 | train + val 秒数 | attempt 墙钟秒数 | Val accuracy / macro-F1（仅 probe diagnostics） | 保存/重载 |
|---|---|---:|---:|---|---|
| MobileNetV3-Large / attempt_03 | train15899、val2868；1 epoch；MPS、batch64、threads2、workers0 | 206.259663833 | 210.761519875 | .827405858 / .825530194 | checkpoint17052801 bytes；原重载16样本、logit最大差0 |
| ResNet18 / attempt_01 | 相同样本与设置 | 187.059520584 | 191.677009750 | .909693166 / .908516550 | checkpoint44803787 bytes；原重载16样本、logit最大差0 |

这证明获批全量输入上的单 epoch 训练、完整 validation、有限输出和保存/同批重载已经在用户真实 MPS 环境运行成功，超过了仅有 fake-device tests 的证据范围。它不证明多 epoch 长时稳定、独立重训逐位复现、真实 camera 泛化或 runtime 推理时延。ResNet本轮epoch较快、diagnostic F1较高，不能据此选模型、排除MobileNet、缩减grid或声称优于既有正式baseline；两模型预训练仍分别为ImageNet V2/V1。probe标记 `NON_COMPARATIVE_PROBE`、`formal_comparison_valid=false`、`counts_toward_hpo=false`、`is_p2=false`，selection仍为空。

累计账本482.473836584 s包含原保留78.098847875 s；**本次成功续跑新增404.374988709 s**。MobileNet先前两次 interrupted attempt全部保留。没有超时；不能把482秒当作全部搜索时间，不能把旧中断历史抹除。MPS同步batch后采样的driver峰值约MobileNet4.365 GiB / ResNet2.440 GiB，OS峰值RSS分别706838528 / 959397888 bytes；二者统计口径不同，不相加，也不冒称长时运行的绝对内存上限。

### 本轮只读核验与四维状态

实际使用既有 `.venv/bin/python -B` 的内联Python核验（不另建重复报告）：对两条完成attempt调用 `run_vision_hpo.verify_completed`，**22条 artifact exists/bytes/SHA通过**，包括两份checkpoint；active source SHA/signature、4项受保护hash和context中的冻结metadata/train/val字节hash一致。`sample_manifest.csv`逐行相同，train15899/val2868、ID唯一、train/val司机无交集，validation predictions IDs和顺序一致、10类c0–c9映射正确。保存logits/probabilities均finite、softmax/argmax一致；CSV与`probabilities_validation.npy`一致，重新计算accuracy/macro-F1/log-loss与ledger一致。此核验没有重新加载checkpoint或追加forward；reload结论来自本次真实worker的保存记录。

核验数值口径：第一次从CSV默认float64复算MobileNet log-loss=.737143634909，与原float32评分.736698567867有差异；确认scikit-learn按概率dtype选择裁剪精度后，使用原NPY float32重算，两模型全部指标一致。不是新的训练失败，没有修改原指标或scorer。后续复算应保留现有评分dtype；不能把float64复算值混入当前float32 log-loss并列规则。

当前 `test_images_opened=0`、`test_predictions=0`，无`predictions_test.csv`；未打开test图像或telemetry_test CSV。无`approved_vision_budget.json`，没有正式search或新的HPO计数。软件修复的116项测试仍是下方历史执行证据，本轮未重复声称重跑。

| 范围 | Implementation | Testing | Evidence | Reproducibility | Verdict |
|---|---|---|---|---|---|
| 视觉 probe / S2输入 | 真实MPS单epoch train/val、保存重载已执行 | 两模型各1次成功；输出/IDs/metrics/hash核验通过 | 日志、模型、config、manifest、timing及proposal齐全 | 配方/数据/源码/种子可追溯、原重载通过；MPS独立数值重训未做 | **VERIFIED_PASS（仅probe范围）** |
| 视觉 P2/P3正式训练 | search CLI已实现；原批准grid/8epoch/patience2保持 | **NOT_RUN**；probe不抵扣第一组P2正式trial | 无正式视觉trial/selection freeze | 等待正式运行与确认seed证据 | **APPROVAL_PENDING** |
| 整体进度 | Week3原P1仍VERIFIED_PASS；遥测P2/P3复用既有结果 | 不扩展为五模型HPO/E1全部完成 | 只引用本轮真实产物 | 各阶段门槛不变 | Week2总体仍PARTIAL（正式视觉预算未闭合）；P2/P3 PARTIAL；P4/P5未授权 |

### 正式视觉预算：估计与待审批建议分开

原批准公式 `(train + full val seconds) × 8 epochs × 8 logical trials × 1.15` 已复算一致：

| 模型 | proposal估计（已含15%系数） | 建议模型硬限（尚未批准） |
|---|---:|---:|
| MobileNetV3-Large | 15180.711258114 s ≈ 4小时13分01秒 | **17100 s（4小时45分）** |
| ResNet18 | 13767.580714987 s ≈ 3小时49分28秒 | **15300 s（4小时15分）** |
| 合计 | 28948.291973101 s ≈ 8小时02分28秒 | **32400 s（9小时）** |

另建议 `per_trial=2400 s（40分钟）`，与模型/总限额同时执行；这是本次提交用户考虑的数字，**不是R4规定或已获授权的扩额**。总9小时比已含15%的proposal再多约11.9%，用于长时MPS负载/初始化/保存重载和调度波动；不保证覆盖所有trial。保持MPS、batch64、CPU threads2、workers0，模型与trial顺序执行，接电、开盖，不与系统轨道性能测试并发。单trial不超过8epoch、patience2可能提前结束；达到任一硬限即停，保留已耗预算/attempt并记录NOT_RUN_BUDGET，不自动补跑。probe只计自己的2400s阶段，不计正式HPO trial或正式search账本。

当前未解决事项为：用户是否批准以上每trial、每模型、总秒数及对应MPS资源窗口。批准后才按最新任务§5写入并提交 `approved_vision_budget.json`，给用户终端search命令；不得现在创建授权文件或启动search。正式每模型6组seed42+选中配置43/44共最多8次，首网格计P2；确认不重选。P4 final test/E1、P5 package仍须另批。只更新本规范报告，保留W5/W7里程碑与四维验收边界。

## 2026-10-19 最新执行记录：probe 重复启动与中断恢复修复

本节为最新状态，覆盖下方旧的“视觉 NOT_STARTED / 未下载 / 未执行”快照。Git 开工六项检查：cwd/root=`/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1`、branch=`fyp2/ml-training`、HEAD=`c6d1f65`；原有修改只有本次已记录的 regression tests 与 `p3_vision_20261018/`，09审阅报告仍为受保护 untracked。没有切换分支、访问 Live-System 工作区、暂存、提交或 push。用户已要求修复，但明确保留自己运行 probe；**本轮只修代码、做软件测试和非训练恢复，没有启动 probe/search、下载、fit/forward、P4/P5或读取 held-out test**。

### 实际故障与修复范围

旧 `_recover_running` 没有检查父控制器是否存活：同一 run 第二次启动时，把正在运行的 worker 当作孤儿发出 SIGTERM；`supervise` 又把 `returncode=-15` 标成 `IMPLEMENTATION_FAILED`，之后相同命令不启动新 attempt，却仍增加空转启动计时。这与用户终端的 “Interrupted worker was stopped” 和 attempt_02 的 `-15` 相符。两次 MobileNet attempt 都没有完成 epoch、validation 或 checkpoint，不能推断为模型性能差、权重损坏或已完成 probe。

改动仅在 `ml/experiments/run_vision_hpo.py`、对应 tests、`ml/.gitignore`（忽略运行锁）和本报告/既有运行说明：

- 同 run 的所有写操作持有 OS `flock`；重复启动报告 `ALREADY_RUNNING`，不改账本、不停止已有 worker。锁文件保留原 inode，进程退出后自动释放。
- 兼容旧启动器：确认 worker 的父控制器仍存活时拒绝恢复；真实孤儿才按原规则处理。SIGINT/SIGTERM 记录 `INTERRUPTED`；普通实现错误不自动重跑，超时不扩预算。已停止的 failure/budget 状态再次执行不再增加空转耗时。
- 新增受限 `recover-interrupted` 非训练命令：仅恢复旧 probe 的 `-15` 误分类；原提交源码可按 SHA 重建、除控制器外的 source/recipe/预训练/数据/环境/protocol 不变、无存活 worker 且有剩余预算才允许。原 state/config/控制器源码保存在 `recovery_001/`，原 attempt/config/log 不覆盖；新 source context 单独保存并签名。未改变模型训练 worker、网格、种子、预处理、正式 HPO ceiling 或审批机制。

### 实际执行命令与结果

证据根目录：`ml/outputs/runs/p3_vision_20261018/`，软件证据在其 `software_verification/`；恢复前快照、原源码和审计 manifest 在 `recovery_001/`。

```bash
./.venv/bin/python -B -m pytest -q ml/tests/test_vision_hpo.py -k 'second_launcher or external_sigterm or signal_interruption or live_controller or failed_run_retry or legacy' -p no:cacheprovider
./.venv/bin/python -B -m pytest -q ml/tests/test_vision_hpo.py -p no:cacheprovider
./.venv/bin/python -B -m pytest -q ml/tests -p no:cacheprovider
./.venv/bin/python -B ml/experiments/run_vision_hpo.py recover-interrupted --run-id p3_vision_20261018
./.venv/bin/python -B ml/outputs/runs/p3_vision_20261018/software_verification/verify_recovery.py
./.venv/bin/python -B ml/experiments/run_vision_hpo.py status --run-id p3_vision_20261018
git diff --check
```

先运行 regression，实际 **12 failed / 17 deselected / 1.95 s**（RED），修复后视觉 tests **29 passed / 1.80 s**。增加 CLI 恢复→同配方续跑的合成集成检查后，完整 ML suite **116 passed / 18.62 s**，其中视觉调度30项；日志分别为 `regression-red.log`、`vision-green.log`、`suite-green.log`。这些是 fake worker/临时合成文件/短生命周期软件进程验证，不是实际模型 fit 或 MPS 数值验收。

实际恢复 exit 0，`recovery.log`：`PROBE_RECOVERED INTERRUPTED used_seconds 78.09884787490591 remaining_total_seconds 2321.901152125094 context_file recovery_001/config.json training_started False`。恢复后独立可重跑脚本 **33 checks / 0 failures**（`recovery-verification.log`）：原10个文件 bytes/SHA、4个保护哈希、原 state、审计文件、active source/signature、旧 signal result、零新 attempt/checkpoint、无 search 预算文件、空 staging 均通过。旧原始 execution.status 仍留为失败证据；修正后的 attempt.status 为 `INTERRUPTED` 并保留 `original_status`，没有抹掉历史。

### 当前资源、预算与四维验收

MPS availability 门禁在真实恢复命令中通过，但本轮没有实际 MPS forward 或资源性能测量。MobileNet V2 / ResNet18 V1 缓存已由用户获取，恢复时完整 SHA 与原 manifest 一致（分别 `5c1a416349c4cf298f2a6a5e2600ed0ee55e604713578f5e74e6bc8bcaef7997` / `f37072fd47e89c5e827621c5baffa7500819f7896bbacec160b1a16c560e07ec`）；无需重复 fetch，未变更 `.venv`。

| 项目 | 实际状态 / 预算 |
|---|---|
| MobileNet probe | 2 interrupted attempts；实际 attempt 墙钟合计58.317306792 s；累计1200 s限额剩余约1141.682693208 s |
| ResNet probe | 0 attempts；模型上限1200 s，另受总剩余约束 |
| 阶段总预算 | 原账本已记78.098847875 s，**不退款、不清零**；2400 s总限额剩2321.901152125 s；后续启动开销仍计入 |
| 验证/恢复开销 | RED 1.95 s、视觉GREEN 1.80 s、完整suite 18.62 s，属于软件验证；恢复未新增训练耗时或 attempt，未将原账本改写为“仅fit耗时” |

| 范围 | Implementation | Testing | Evidence | Reproducibility | Verdict |
|---|---|---|---|---|---|
| 本次监督器修复及旧状态恢复 | 锁/中断分类/受限迁移已实现 | 完整116软件tests + 真实恢复33项核验 | RED/GREEN、原快照、源码hash、新context及旧attempt齐全 | 恢复脚本可重跑、配方与预算未变、旧证据保留 | **VERIFIED_PASS（仅软件与状态恢复）** |
| 真实视觉 probe | CLI可续跑；原2 attempts保留 | 没有完整epoch/val/reload结果 | 无 checkpoint、validation metrics 或 proposal | 后续新attempt记录新控制器context；MPS数值复现未验证 | **PARTIAL / INTERRUPTED，等待用户终端续跑** |
| 五模型正式HPO / E1 / package | 遥测既有结果不重跑；视觉search预算文件不存在 | 本轮未执行 | 不新增正式比较或E1证据 | 仍服从各阶段审批 | **P2/P3 PARTIAL；P4/P5 NOT_STARTED / 未授权** |

Week3 的 comparator pipeline + 原批准smoke继续为 `VERIFIED_PASS`（下方实际证据）；这次修复不是追加smoke或验收整条ML轨道。Week2 数据/模型冻结与技术准备通过，总体仍 `PARTIAL / APPROVAL_PENDING`：视觉正式 search 数字预算留待 probe 完成后的 S2 审批。W5/W7 主里程碑未变。

### 下一步与停止状态

本次修复/恢复完成后停止，不代用户启动训练。用户接电、保持开盖，仅在一个终端执行：

```bash
cd /Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1
caffeinate -dims ./.venv/bin/python -B ml/experiments/run_vision_hpo.py probe --run-id p3_vision_20261018
```

不必再 fetch 或 recover；不删除 state/attempt/lock，不更换 run_id。完成后提供 `PROBE_COMPLETE` 和 `VISION_STATUS probe`；若超时或出错，停下并保留状态。接着只核验 probe、提出具体视觉 per-trial/per-model/total预算，在 S2 等用户批准；不自动 search、final test、E1或打包。运行方法已同步到既有 `RUN_VISION_HPO.md`，没有新建重复进度文档。

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
