# P5 候选模型包与系统准入审查

审查日期：2026-10-23。ML 工作区为 `/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1`，分支 `fyp2/ml-training`，HEAD `335da4e3de203836c045452f84cc291bcd352a26`；已有 P4 代码与证据仍有未提交文件。本审查没有训练、导出、forward、held-out 重测、额外 benchmark、服务启动或部署。

Live 源码仅通过上述仓库的 Git 对象读取：`git show 2745348f3d4587e14c1d4a7e53a2bfc4d72225d5:<path>`（审查时本地 `fyp2/live-system`）。没有进入或读取 physical `/Users/liu/Desktop/FYP2-Live-System`。下文 `LIVE:<path>` 均指该精确 Git 对象，**不是当前 ML 工作区里的同名旧文件**。每条 LIVE 引用链接到实际保存这些 Git 对象的[当前仓库](</Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1>)，并写明对象内路径，避免把旧 backend 当作当前实现。正式约束已完整读取 `LIVE:docs/fyp2/review/CODEX_ML_TRACK_PROMPT.md` 与 `LIVE:docs/fyp2/review/CODEX_ML_TRACK_ADDENDUM_R4.md`。

## 1. P5 的实际 manifest schema 与可交付范围是什么？

### Takeaway

已有正式 **vision manifest v1**，可以按其打包 RN-HPO42 和 MN-HPO42 的已有 ONNX；格式与文件哈希验收可独立完成。当前 schema 没有 telemetry research-candidate 导入合同，XGB-HPO42 留作研究证据；RF/LR 不进入任何候选包。

### Cited Findings

- 最终已交接的文件名为 `backend/app/runtime_manifest.schema.json`（带点，**不是**计划草稿中的 `runtime_manifest_schema.json`）、跨字段 checker `backend/app/runtime_manifest.py`、CLI `scripts/validate_runtime_manifest.py` 和示例 `docs/fyp2/handoff/examples/stable-mobilenetv3.runtime_manifest.json`。交接明确说“这一步只交 schema”，后续 provider 与离线评估器另属 Task 10A。— [LIVE 2745348：docs/fyp2/handoff/task-10a-runtime-manifest.md；backend/app/runtime_manifest.schema.json](</Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1>)
- schema 的完整 required 顶层集合为 `manifest_version, kind, run_id, architecture, model, input, preprocess, output, classes, class_to_idx, safe_class, contract_smoke_set`，可选 `provenance`；拒绝其他顶层键。`manifest_version=1`，`kind="vision_classifier"`，`run_id` 匹配 `[A-Za-z0-9_.-]{1,100}`，且 package 校验时必须与真实包目录名相同。`architecture` 是长度 1–100 的字符串，不限为 MobileNet。— [LIVE 2745348：backend/app/runtime_manifest.schema.json；runtime_manifest.py](</Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1>)
- `model={path,format:"onnx",sha256}`；SHA256 必须 64 位小写十六进制。`path` 必须相对包目录，不含 `..`、反斜线或绝对路径，文件必须存在、为普通文件、解析后的路径仍在包内，实际文件哈希必须相符。checker 会拒绝 symlink 逃逸；R4 的交付约束更严格，包目录内不得有符号链接。不要利用 checker 对包内 symlink 的宽松部分绕过 R4。— [LIVE 2745348：backend/app/runtime_manifest.py；docs/fyp2/review/CODEX_ML_TRACK_ADDENDUM_R4.md §3](</Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1>)
- `input` 必须为 `{shape:[1,3,224,224],dtype:"float32",layout:"NCHW",color:"RGB"}`；`preprocess` 只接受 `rgb_resize_224_bilinear_no_crop_div255_imagenet`；`output={kind:"logits",shape:[1,K]}`，K 与 classes 数一致。P5 使用完整 c0…c9、`class_to_idx={c0:0,…,c9:9}`、`safe_class="c0"`、K=10。schema 本身允许不少于 2 个符合 c0…c9 的不同类别码，不能据此缩减本项目的 10 类合同。— [LIVE 2745348：backend/app/runtime_manifest.schema.json；runtime_manifest.py；docs/fyp2/review/CODEX_ML_TRACK_ADDENDUM_R4.md §3](</Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1>)
- 正式 v1 schema 没有 `input.name`、`output.name`、`labels`、`label_names` 或独立 `source_commit` 顶层键；给 input/output 添加 name 会触发 `additionalProperties:false`。ONNX graph 的 `input` / `logits` 名称和动态 N 由 R4、P4A export/graph/parity 证据承载；来源 run/commit 等可写入无指标的 `provenance`。不要为迎合旧自然语言说明而发明 schema 字段。— [LIVE 2745348：backend/app/runtime_manifest.schema.json；docs/fyp2/review/CODEX_ML_TRACK_ADDENDUM_R4.md §3](</Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1>)
- `evaluation_metrics.json` 与 runtime manifest 分开。manifest 的 provenance 任意深度键名按完整词拆分后如含 `f1, accuracy, acc, precision, recall, auc, ece, brier, nll, loss, metric, metrics, score, mae, mse, rmse` 则拒绝。加载所需元数据不以指标高低为前提。— [LIVE 2745348：backend/app/runtime_manifest.py；docs/fyp2/handoff/task-10a-runtime-manifest.md](</Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1>)
- `contract_smoke_set={split,selection,n,sample_ids_sha256,rule}`；split 只能 train/val，rule 固定 `per_class_mode_equals_label`。正式 stable 示例是 **val、各类按 filename 排序取前 20、共 200**，`sample_ids_sha256=601dc3ed6b99e9030f6eb5287e711baf529ea6c0c5b2facab0acd9c3f9373be9`；交接建议候选沿用同一份。checker 仅校验这些元数据，未执行该行为规则。— [LIVE 2745348：docs/fyp2/handoff/examples/stable-mobilenetv3.runtime_manifest.json；docs/fyp2/handoff/task-10a-runtime-manifest.md；backend/app/runtime_manifest.py](</Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1>)
- P4A100 是另一套 val bank：每类 10 张，按 `SHA256(42|runtime-val|source_id)` 排序，ordered-source-ID hash `0b38faf42d6820831a569d835054c093cd1f4dacaecd1bf1d4f6d64c8371ac37`，bank-file hash `7a40f0c3ae4d7cdb73b2f00dadda4c641c2ea759e55cc2e76e0b071c900dfdfc`。不能把它称为 stable200 已运行的 golden set。— [P4A validation_manifest.json](</Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/ml/outputs/runs/p4a_20261021/validation/validation_manifest.json>)
- RF/LR 的 `.joblib/.pkl` 只用于 benchmark，不进入任何候选包；只有视觉是替换候选，遥测固定 XGBoost，遥测是否走 manifest 仍是 Task 10A 开工待决项。— [LIVE 2745348：docs/fyp2/review/CODEX_ML_TRACK_ADDENDUM_R4.md §3；docs/fyp2/handoff/task-10a-runtime-manifest.md](</Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1>)

### Inferences

- 推荐 P5 只复制两份现有 ONNX 到各自自成一体的包目录，写正式 v1 runtime manifest、独立 evaluation_metrics/model card/证据索引。**schema+package/hash PASS 可以成立；provider-load / behavioral-contract / live-integration 必须分别标 NOT_RUN 或 BLOCKED**。依据是上面的 schema 与交接边界，而非新增部署门槛。
- manifest 可引用正式 stable200 的 selection/hash，并明确行为未执行。可从已有 full-val 预测派生相同 200 的补充诊断，但必须标为 saved-validation-prediction diagnostic；它不能代替 ONNX/provider 对 stable200 的行为验收。P4A100 的 ONNX parity 单独引用，不混写。
- RN 来源 `[...]/p4a_20261021/runtime_benchmark/resnet18_search004_seed42/model.onnx`，SHA256 `5e226722e0712824c78aa0976afa6fa5b8dc6100b147a7f523a09048171d8cf3`；MN 来源 `[...]/p4a_20261021/runtime_benchmark/mobilenet_v3_large_search006_seed42/model.onnx`，SHA256 `9ee60abb78007773cc625af80c313049c1970f63c1f041bed9f5b2539a384828`。其中 `[...]` 为 `/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/ml/outputs/runs`。直接复制并重新核对哈希，不重新导出。— [RN export metadata](</Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/ml/outputs/runs/p4a_20261021/export_RN-HPO42.json>)；[MN export metadata](</Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/ml/outputs/runs/p4a_20261021/export_MN-HPO42.json>)
- 只读可用的 P3 full-val 材料分别位于 `/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/ml/outputs/runs/p3_vision_20261018/search/resnet18/search_004/attempt_01/` 与 `.../search/mobilenet_v3_large/search_006/attempt_01/` 的 `predictions_validation.csv`、`probabilities_validation.npy`、`selection_log.json`。已有预测可支持派生诊断；不需要也不授权新 forward。— [RN full-val predictions](</Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/ml/outputs/runs/p3_vision_20261018/search/resnet18/search_004/attempt_01/predictions_validation.csv>)；[MN full-val predictions](</Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/ml/outputs/runs/p3_vision_20261018/search/mobilenet_v3_large/search_006/attempt_01/predictions_validation.csv>)

### Gaps

- 本审查不执行新包校验，也不预告新包 PASS；包作者需对最终目录运行冻结版本 checker。正式命令为 `.venv/bin/python scripts/validate_runtime_manifest.py <package>/runtime_manifest.json --package-dir <package>`。当前 ML 分支没有该 CLI 时，可将 **2745348 的原始** `runtime_manifest.py` 与 `.schema.json` 复制到 `/tmp` 隔离目录，调用原样 `validate_package`；记录该过程是静态 schema/file/hash 检查，不是 backend 模型加载。— [LIVE 2745348：scripts/validate_runtime_manifest.py；backend/tests/test_runtime_manifest.py](</Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1>)
- stable200 的 sample-ID 哈希重建应先与正式示例相符；若命名或排序规则解释无法复现，需披露差异，不能发明 PASS。已有 P4A100 不能填补这一缺口。— [LIVE 2745348：docs/fyp2/handoff/task-10a-runtime-manifest.md](</Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1>)

## 2. 当前 strict loader 何时接受 RN/MN？XGB-HPO 是否有候选导入契约？

### Takeaway

在所审查的 Live `2745348`，strict manifest loader **尚未接线**。两份 vision 包可以交给 later Task 10A，不能报告当前系统已经接受 RN/MN；XGB-HPO42 没有正式 research-candidate manifest/importer，不应伪装成受支持的系统候选包。

### Cited Findings

- 当前 `TrainedProvider.__init__` 使用 `settings.model_root` 加固定路径 `vision/mobilenetv3_large_vision.onnx`、`telemetry/xgb_telemetry.json`，同时读取 `vision/metrics.json` 与 `telemetry/metrics.json`。它不导入 `runtime_manifest`，不调用 validate_manifest/validate_package。provider 名和 vision architecture 仍写为 MobileNetV3。— [LIVE 2745348：backend/app/providers/trained.py](</Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1>)
- 当前 vision 检查 metadata `classes==c0…c9`、float32 tensor 与后三维 `[3,224,224]`、零输入 warmup 输出 `(1,10)` 有限值；实际预处理 RGB→直接 PIL bilinear resize(224,224)→/255→ImageNet mean/std→NCHW contiguous float32，推理后外部 softmax，`P_distraction=1-probs[0]`。这不等于能证明输出是 logits 或类别标签语义正确。— [LIVE 2745348：backend/app/providers/trained.py；docs/plans/2026-10-12-fyp2-live-system-completion.md Task 10A](</Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1>)
- 当前 XGBoost 检查固定 classes `Safe/Aggressive/Distracted`、8-feature order 与 schema、Booster feature_names、一致的 best_iteration；按 `iteration_range=(0,best_iteration+1)` 预测，另用同组树 `pred_contribs` 取 Safe margin 的负贡献。当前模型根配置只是 `DRA_MODEL_ROOT` 指向一个含 vision/telemetry 固定子目录和旧 metrics 的根，**不是候选包导入接口**。— [LIVE 2745348：backend/app/providers/trained.py；backend/app/config.py](</Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1>)
- 当前 `.planning/system-track/task_plan.md:87,97-98` 明列 Task 10A provider 改造与离线评估器未完成；`docs/fyp2/implementation/w6-system-tests-acceptance.zh.md:104` 也列为 W6 拓展项。schema/checker 测试位于 `backend/tests/test_runtime_manifest.py`，模块说明明确“不加载模型”；checker 的 package hash 测试使用 `b"onnx bytes"`，证明其范围是结构/路径/哈希。— [LIVE 2745348：.planning/system-track/task_plan.md；docs/fyp2/implementation/w6-system-tests-acceptance.zh.md；backend/tests/test_runtime_manifest.py](</Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1>)
- Task 10A 计划要求：稳定与候选同一 manifest 加载路径；不读评估文件；拒绝不支持预处理、输出语义、类别映射/契约冒烟失败、路径逃逸与哈希不符；隔离进程离线复用 provider 与系统逻辑，不起服务器、不写开发数据库；后续对比及版本/回滚演练另行完成。不要求执行正式替换。— [LIVE 2745348：docs/plans/2026-10-12-fyp2-live-system-completion.md Task 10A 与 DoD 10A](</Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1>)
- 交接仍列稳定包目录名与 run_id 不一致、稳定模型 symlink containment、runtime manifest 最终位置，以及遥测是否也走 manifest 为待决事项。— [LIVE 2745348：docs/fyp2/handoff/task-10a-runtime-manifest.md「已知的待决事项」](</Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1>)

### Inferences

- RN/MN 的 system admission 当前为 **BLOCKED_BY_TASK10A_IMPLEMENTATION**，并非候选模型已经证明不兼容。未来何时接受取决于系统轨道完成上述已批准的 Task 10A，并对实际包执行验证；本次不新建 backend contract 或 importer。
- 即使把 RN ONNX 改名并放入旧固定目录可能穿过部分 shape checks，也不构成正式准入：provider 会继续报告 MobileNet 架构、读取旧 metrics，且未履行 manifest/golden 合同。P5 不尝试这种绕行。
- XGB-HPO42 可保留冻结身份、8-feature/class/iteration/imputer provenance 和离线评估材料供研究报告；没有正式 telemetry manifest 合同前，不创建一个看似可导入的 package 或宣称 compatibility PASS。RF/LR 始终 benchmark-only。

### Gaps

- 当前未实现 provider manifest 加载、稳定与候选同路径、provider 不读 evaluation 文件的运行测试、stable200 真正的 provider 行为检查，以及候选 Live E2E 回归；这些是 later system Task 10A 的工作，不是 P5 静态包验收的新增 hard gate。— [LIVE 2745348：.planning/system-track/task_plan.md；主计划 DoD 10A](</Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1>)
- 未执行系统离线影子评估、正式替换、发布、回滚或摄像头验证。本次结论仅针对代码与现有证据。

## 3. 已有运行证据足以支持哪一层结论？

### Takeaway

已有 ONNX export、val-only parity 和 CPU session.run benchmark 足以支持 **FYP 受控离线候选交付**。它们不足以支持候选已被系统加载、Live end-to-end validated、特定真实相机视角可靠或车辆部署结论；这些边界来自现有运行范围与项目计划，不添加事故安全或部署 hard gate。

### Cited Findings

- P4A 已有 export metadata：RN-HPO42 与 MN-HPO42 的 graph 输入名 `input`、输出名 `logits`，float32 `['N',3,224,224]` 与 `['N',10]`，输出 raw_logits；opset17、`dynamo=false`、`external_data=false`。旧 export metadata 标 `candidate_package=false, deployment_eligible=false, scope=benchmark/evaluation-only`，不能把旧记录改写为当时已部署候选；P5 是对同一字节产物的新交付包装。— [RN export](</Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/ml/outputs/runs/p4a_20261021/export_RN-HPO42.json>)；[MN export](</Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/ml/outputs/runs/p4a_20261021/export_MN-HPO42.json>)
- P4A parity 两候选均 PASS；比较 211 个累计样本位置，覆盖 N=1/2/4/9/32，`atol=rtol=1e-4` 且 argmax_equal。RN max absolute logit error `1.9073486328125e-05`、max probability error `2.302238954254854e-06`；MN 分别 `4.100799560546875e-05`、`6.364584130613693e-06`。211 不是 211 个独立 val ID；其输入来自上述固定100 bank 的单张与重复分批计划。— [RN parity](</Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/ml/outputs/runs/p4a_20261021/parity_RN-HPO42.json>)；[MN parity](</Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/ml/outputs/runs/p4a_20261021/parity_MN-HPO42.json>)；[parity 实现](</Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/ml/experiments/p4_preflight.py:108>)
- parity 是逐元素 `abs(actual-reference) <= 1e-4 + 1e-4*abs(reference)` 加 argmax 一致；max_relative_error 可在接近零的 logits 上大于 1e-4，不能单凭这个汇总量推翻 PASS。PyTorch 官方教程同样要求对同输入的 PyTorch/ORT 输出做数值比较，而非只看 graph 能否打开。— [本地 parity check](</Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/ml/experiments/p4_preflight.py:108>)；[PyTorch 官方 ONNX 导出教程](https://docs.pytorch.org/tutorials/beginner/onnx/export_simple_model_to_onnx_tutorial.html)
- P4A graph checker 要求动态 batch；P4A export 用 dynamic_axes，parity 观察到多个 N 已执行。manifest `[1,...]` 表达运行时单窗调用形状，graph `N` 表达导出支持的 batch 维；两者不矛盾。P5 只记录现有 evidence，不重新导出。— [P4A graph/export 实现](</Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/ml/experiments/p4_preflight.py:149>)；[P4A export metadata](</Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/ml/outputs/runs/p4a_20261021/export_RN-HPO42.json>)；[LIVE 2745348 schema](</Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1>)
- P4B runtime 的精确 scope 为 `CPU_ORT_SESSION_RUN_ONLY_NOT_CAPTURE_TO_RENDER`。每个候选 6 轮、每轮50 warmup、100单张 latency calls、另100 throughput calls；CPUExecutionProvider、intra-op=2、inter-op=1、ORT_SEQUENTIAL、ORT_ENABLE_ALL，spinning关闭。load time 单独记录，预处理不在单次 timer 内。— [runtime worker/session 配置](</Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/ml/experiments/run_p4.py:397>)；[P4B evaluation_metrics.json runtime](</Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/ml/outputs/runs/p4b_20261022/evaluation_metrics.json>)

| 已有 runtime 字段 | RN-HPO42 | MN-HPO42 |
|---|---:|---:|
| pooled p50 ms | 25.120188 | 6.9475415 |
| pooled p95 ms | 25.4214503 | 7.2472 |
| 每轮 p95 范围 ms | 25.29761635–26.12586455 | 7.21374825–7.56844935 |
| pooled calls/s | 39.7130078830 | 141.9534388074 |
| ONNX bytes | 44,717,068 | 16,849,370 |
| checkpoint bytes | 44,803,787 | 17,052,801 |

表中数字均来自 [P4B evaluation_metrics.json / runtime](</Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/ml/outputs/runs/p4b_20261022/evaluation_metrics.json>)。RSS 在源记录中明确为观察采样，可能漏瞬时峰值；RSS delta 不等于模型独占内存，macOS ru_maxrss 是整个 worker lifetime。

- ONNX Runtime 官方说明线程池任务分配可导致平台上的 latency variance；本项目已有原始 latency samples、p95 与轮间范围，适合报告已测主机/config 的 steady-state 行为，不能把单个均值外推为所有平台性能。这里不建议也不执行调参或新 benchmark。— [ONNX Runtime 官方 performance troubleshooting](https://onnxruntime.ai/docs/performance/tune-performance/troubleshooting.html)；[本地 runtime 记录](</Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/ml/outputs/runs/p4b_20261022/evaluation_metrics.json>)
- Torchvision 的 ResNet18 ImageNet pretrained 默认 transforms 是 resize256+centercrop224；这与本项目直接224 resize的合同不同。P5 必须声明实际使用的自定义验证/runtime预处理，不能从架构名推断默认预处理。— [Torchvision 官方 ResNet18 文档](https://docs.pytorch.org/vision/stable/models/generated/torchvision.models.resnet18.html)；[本地 P4A preprocess](</Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/ml/experiments/p4_preflight.py:89>)
- MobileNetV3 原论文针对 mobile-phone CPUs 的硬件感知搜索，提供的是其论文任务/硬件实验；本项目 CPU ORT 的更快测量是独立本地证据，论文不能替代真实相机或本项目端到端时延验证。— [Searching for MobileNetV3 原论文](https://arxiv.org/abs/1905.02244)；[本地 P4B runtime](</Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/ml/outputs/runs/p4b_20261022/evaluation_metrics.json>)
- P4B clean 源数据 RN macro-F1 `0.8892363766947888`、MN-HPO `0.8676544859032846`、MN-STABLE `0.8746408408872671`。同文件明确仅4名 test drivers、历史 test 已多次曝光、DMD BLOCKED、offline benchmark 不证明 live performance；corruption label validity 未验证，不计算 source-label corruption F1，不应写为 human-validated robustness。ResNet/XGB validation priorities 已冻结，不再次选型或调参。— [P4B evaluation_metrics.json / models 与 limitations](</Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/ml/outputs/runs/p4b_20261022/evaluation_metrics.json>)
- 当前 provider 的 info 直接写明 frontal-camera inference experimental，source metrics 不验证 frontal reliability。真实目标相机的机位、视角、光照、裁剪/压缩路径没有由上述 dataset/runtime 实验验证。— [LIVE 2745348：backend/app/providers/trained.py info.scope](</Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1>)

### Inferences

- **层1 / artifact**：已有字节身份、logits、class mapping、动态N与数值parity，可支持生成可审查的 vision 包；最终包检查由打包步骤实测。
- **层2 / controlled runtime**：已有warm CPU ORT session.run比较支持“MN更快、RN也可作为本机受控候选”的工程描述；RN保持 validation-frozen preferred candidate，MN保留较快候选，稳定基线不动。benchmark不负责重新选型。
- **层3 / system admission**：当前 BLOCKED_BY_TASK10A_IMPLEMENTATION；将来在系统轨道按既定计划执行 stable/candidate同路径和行为检查，才能判断系统接纳，不能从包静态PASS跳过。
- **层4 / Live end-to-end与target viewpoint**：本轮 NOT_RUN / NOT_VALIDATED。不能把源数据accuracy、ONNX parity、prepared telemetry、constructed scenario、CPU微基准或稳定系统已有E2E混为候选模型Live验证。
- 后续可在获授权的系统 Task10A 做隔离离线成对评估，再做目标相机视角诊断与必要的系统回归。此处只是建议后续工作，不执行，也不将它们加入 P5 包结构验收的硬门槛。

### Gaps

- 本轮没有候选摄像头capture→编码/网络→provider→fusion/EMA/FSM→SQLite commit→UI render测试；没有真实目标相机视角的标注验证。现有记录不能证明任一路径的候选 Live end-to-end指标或真实场景可靠性。
- source dataset 与目标viewpoint/domain之间差异不能靠输入shape、ImageNet normalization或architecture声称消除；现有证据只覆盖已记录的数据与测量边界。该限制不是否定FYP受控候选交付，也不是要求本次训练或采集新数据。
