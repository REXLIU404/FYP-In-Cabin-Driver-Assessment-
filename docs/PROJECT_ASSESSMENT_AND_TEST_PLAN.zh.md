# 驾驶员风险评估系统：现状、模型实验与实施计划

> 历史快照：本文保留初始审计/旧 prototype 的状态与规划。2026-10-05 已接通实时 camera、已训练模型、后端与 UI；telemetry 仍为 prepared replay。当前完成情况见 [IMPLEMENTATION_PROGRESS.zh.md](IMPLEMENTATION_PROGRESS.zh.md)，启动与边界见 [LIVE_RUNTIME_GUIDE.zh.md](LIVE_RUNTIME_GUIDE.zh.md)。其他模型对比已按用户要求暂停。

日期：2026-09-28。范围：当前 `dev_cc` 工作区、引用任务「评估正面视角和30帧」、本地真实模型与数据。本文的“已完成”只指有代码或本次运行证据的事项；后续方案与建议验收值不代表已部署或已达标。

## 1. 结论与当前进度

项目已经完成可演示的前端、风险融合逻辑、基础后端及两条模型的离线 baseline。当前主要缺口是把真实输入、已训练模型、后端状态与 dashboard 接成同一条可验证链路。优先接入现有 MobileNetV3-Large ONNX；EfficientNet-B0 作为对照候选，不能仅凭模型名称判断它更准确或更适合 edge。

“EfficientNet 80”暂按 EfficientNet-B0 解读。最终 edge device 尚未指定，因此本次性能数据属于本机 macOS ARM CPU；不代表 Raspberry Pi、Jetson 或手机上的性能。未采集摄像头、未进行实际驾驶实验。

| 模块 | 核实后的状态 | 还缺什么 |
|---|---|---|
| React/Vite 五视图、session log、导出 | 已实现，32 项现有测试通过，生产构建通过 | 后端数据源、连接/重试/过期状态、真实模型来源显示 |
| 摄像头 | `getUserMedia` 的 640×480 preview | frameRate 设置、抽帧、时间戳、模型输入；目前摄像头画面不参与风险计算 |
| TS late fusion | 已实现，0–100 分数、默认 0.5/0.5、EMA、持续告警 FSM | 与 Python 行为一致的跨语言序列测试；避免前后端重复平滑 |
| FastAPI + SQLite | session/window CRUD、latest、status、JSON/CSV 导出 | 真实输入入口、真实 provider、队列、可靠缓存/编号、完整时间状态 |
| 视觉训练 | MobileNetV3-Large 真正训练过；本地 `.pt` 与 `.onnx` 可加载 | 正面数据验证、弱类改善、模型 manifest、生产接入 |
| Telemetry 训练 | XGBoost 真正训练过；本地 JSON booster 可加载 | 原始 8 特征接入、特征顺序/单位检查、真实 telemetry 外部验证 |
| 联合实时系统 | 未完成；UI 和 API 仍使用 prepared/mock 概率 | 真正的 camera → model → fusion → DB → UI E2E |
| 正面与 edge 验证 | 未完成 | 标注正面视频、指定设备、端到端时延/掉帧/热稳定性测试 |

旧 [CLAUDE.md](../CLAUDE.md) 与 [DEVELOPMENT_SCHEDULE.md](DEVELOPMENT_SCHEDULE.md) 的“模型未训练”描述已落后于现有产物，不能继续当成当前事实。[ml/README.md](../ml/README.md) 更接近实际状态。无需用不可靠的百分比描述项目完成度；上表区分了离线模型完成和在线集成完成。

## 2. 为什么现在的 inference 没有使用训练模型

当前两条独立链路：

```text
Frontend: prepared CSV/预设视觉概率 → TS EMA/fusion/FSM → localStorage → UI
Camera:   getUserMedia → video preview

Backend:  客户端传入概率 → MockAIProvider 原样返回 → Python fusion → SQLite/cache

Offline:  State Farm → MobileNetV3-Large → .pt/.onnx
          synthetic telemetry → XGBoost → .json
          ↑ 两组权重尚未连接到上面的 runtime
```

直接证据：

- [frontend/src/App.tsx](../frontend/src/App.tsx) 第 62–79 行每次取 `PREPARED_SESSION_WINDOWS` 并本地融合；没有 API 请求。
- [useCameraPreview.ts](../frontend/src/hooks/useCameraPreview.ts) 只启动 video stream，没有 frame 推理。
- [preparedSessionInput.ts](../frontend/src/data/preparedSessionInput.ts) 第 272 行 `latency_ms = 38 + window_id * 4` 是演示值，不是推理计时。
- [backend/app/inference.py](../backend/app/inference.py) 第 19 行固定调用 `mock_ai.infer(w)`；[mock_ai.py](../backend/app/providers/mock_ai.py) 只回传输入。
- [schemas.py](../backend/app/schemas.py) 的 `WindowInput` 要求概率，不接图片；`operation_mode` 只有 `PREPARED_SESSION_RUNTIME`。
- [status.py](../backend/app/routers/status.py) 明确固定 `models_loaded = False`。

因此，替换 provider 不是唯一改动：必须同时增加输入协议、模型预处理与类别映射、状态管理、frontend API 数据源、可核对的模型 provenance。

## 3. 本次已实际执行的测试

原始证据集中在 [evidence/2026-09-28](evidence/2026-09-28)。下面的准确率是重新加载现有权重后运行得到的，不只是抄旧报告。

| 测试 | 结果 | 证据/边界 |
|---|---|---|
| Frontend Vitest | 4 文件、32/32 通过 | [frontend-test.log](evidence/2026-09-28/frontend-test.log)；无浏览器 camera/API E2E |
| TypeScript + Vite build | 通过 | [frontend-build.log](evidence/2026-09-28/frontend-build.log)；JS 598.15 kB、gzip 170.34 kB，有大 chunk 提示 |
| ESLint | 失败，2 个旧 `prefer-const` 错误 | [frontend-lint.log](evidence/2026-09-28/frontend-lint.log)；`ai/src/alertFsm.test.ts:31–32` |
| 原后端 smoke + 新审计探针 | 3 passed、10 xfailed | [backend-tests.log](evidence/2026-09-28/backend-tests.log)；xfail 是待修缺口，不是通过 |
| 移除 xfail 掩盖后重跑 | 2 passed、10 failed | [backend-regressions-unmasked.log](evidence/2026-09-28/backend-regressions-unmasked.log)；均有断言证据 |
| 视觉完整 test：3,657 张 | accuracy **89.8824%**，macro-F1 **87.4641%** | [vision-benchmark.json](evidence/2026-09-28/vision-benchmark.json)；State Farm 视角 |
| 128 张 PyTorch/ONNX 对照 | argmax 分歧 **0**；最大概率差约 **3.76e-6** | 是样本对照，不是对所有可能输入的等价证明 |
| Driver-grouped split | train/val/test 为 18/4/4 名司机；三组司机 ID 无交集 | 15,899/2,868/3,657 张；不等于证明不存在所有类型的泄漏 |
| Telemetry 完整 test：4,500 条 | accuracy **99.9333%**，macro-F1 **99.9333%** | [telemetry-benchmark.json](evidence/2026-09-28/telemetry-benchmark.json)；合成/规则数据，不能称真实驾驶准确率 |

### 3.1 比整体 accuracy 更重要的结果

当前视觉模型的 `c9 talking_to_passenger` recall 为 **27.33%**，F1 为 **39.72%**；311 张中仅 85 张被判对，72 张被判为 c0，另有大量被判为 c7/c8。`c8 hair_makeup` F1 为 **79.79%**。应优先分析这些失败图和视野覆盖，而不是只继续追整体 accuracy。

融合使用的是 `P_distraction = 1 - P(c0)`，因此另测二分类指标。在预先固定的 0.5 阈值下，当前 ONNX 的 distraction recall 为 **97.21%**，safe false-positive rate 为 **9.05%**，Brier score 为 **0.02905**。这是静态图片指标；9.05% 不能换算成“每小时误报”。10 类 argmax 是否为 c0 与 `P(c0) < 0.5` 是不同判定，不能混用二者的混淆矩阵。

Telemetry 新发现：直接用 `Booster.predict` 的默认所有树，与训练时 `XGBClassifier` 的 best iteration 行为可能不同。本次两者 accuracy 恰好相同，但个别类别概率最大相差 **0.07924**；概率会进入 late fusion，不能忽略。接入时使用已核对的 `iteration_range=(0, 91)`，或保持与训练时一致的 classifier 包装器。`best_iteration=90` 是从零计数。

### 3.2 模型对照实验与性能

本次增加了两类不同目的的实验：

1. Batch=1、FP32、CPU、同一运行时的架构前向延迟对照。未训练的候选权重只用于计算成本，不用于准确率。
2. 完整 driver-grouped 划分上的 ImageNet 冻结骨干 + logistic 分类头对照：MobileNetV3-Large 和 EfficientNet-B0 使用相同 RGB 224×224 预处理、train-only 标准化、相同 C 搜索空间，在 validation macro-F1 上选择 C，最后评估 test。它检验迁移特征，不是完整 CNN 微调的胜负结论。

详细结果见本节后续实验表以及 JSON 证据。5 epoch 已微调 MobileNet 与冻结 B0 的成绩只能用于理解各自训练阶段，不能宣称架构优劣。未来架构选择应采用相同 split、训练预算、调参预算和至少 3 个 seed。

## 4. 如何提高视觉准确率

### 4.1 第一优先：数据与观测范围

- 收集与最终安装位置相同的正面数据：相机高度、距离、焦距、日夜光照、眼镜、遮挡、方向盘与手部可见性。正面仅露脸时，不能可靠区分所有需要手部/中控/手机线索的 State Farm 类别。
- 以 driver/session/vehicle 分组拆分；同一视频相邻帧不得分进 train 和 test。先固定 test，再采集和使用 train/validation 做修改。
- 建议首轮覆盖 12–20 名参与者、每类多个独立动作片段、至少两种光照；这是采集计划，不是已有数据。按安全的模拟/静止场景采集，不要求实际驾驶中做分心动作。
- 保留 10 类用于已有结果比较，同时报告 safe/distraction 二分类。如果正面缺少必要线索，应通过明确的标签方案调整任务，不要靠高置信输出掩盖不可观测类别。
- 使用合适的驾驶员上半身 ROI，并对 full-frame 与 ROI 做独立 ablation。避免裁掉手机、手、方向盘；不要默认人脸 crop 更好。

### 4.2 第二优先：训练与误差分析

- 冻结现有 baseline checkpoint 与 split manifest，先复现，再逐项修改。
- MobileNetV3-Large、Small、EfficientNet-B0 使用显式架构 registry。现有 notebook 只认识 `small`，其他字符串走 Large 分支；直接设置 `VISION_ARCH=efficientnet_b0` **不会得到 B0**。
- 对 c0/c9、c7/c8/c9 看真实失败图、每司机混淆矩阵与难例占比；在训练集做难例采样，避免按 test 图定制增强。
- 尝试 backbone/head 分组学习率、较小 backbone LR、延长到约 15–30 epoch、early stopping 以 validation macro-F1 为主；训练 loss 已接近零，不应简单加 epoch 后宣称必然更好。
- 可试轻度光照/色彩/模糊/遮挡增强、label smoothing；强 crop、CutMix 等需检查是否破坏动作线索。继续禁止无标签重映射的水平翻转，左右手类别有含义。
- 正面迁移采用 source + frontal-train 混合训练或先冻结后解冻；不要把 source test 的高分当作 frontal validation。
- 模型输出 softmax 后才计算 `1 - P(c0)`。在 validation 上做 temperature scaling/阈值选择；报告 calibration、分心召回、safe FPR、c9 recall，不只报 accuracy。
- 可在教师模型验证有效后尝试 Small 蒸馏。蒸馏和量化都是待做实验，不能预先写“无损提高”。

### 4.3 实验矩阵与选择规则

| 实验 | 只改变什么 | 必须固定 | 主要验收 |
|---|---|---|---|
| E0 当前 baseline | 无，复现已有模型 | 原预处理、split、类别顺序 | 已复现；ONNX 对照通过 |
| E1 架构对比 | Large / Small / B0 | driver split、预算、seed 集、分辨率 | val macro-F1、c9 recall；锁定后一次 test |
| E2 正面适配 | 增加 frontal-train / fine-tuning | 独立 frontal-val/test | frontal macro-F1、safe FPR、按司机分层 |
| E3 输入区域 | full-frame / 上半身 ROI | 模型与训练预算 | 弱类召回与遮挡鲁棒性 |
| E4 时间处理 | 无平滑 / EMA / 时间窗均值 | 同一连续标注视频 | 事件漏检、误报/小时、检测延迟、跳变次数 |
| E5 部署优化 | FP32 / FP16 / calibrated INT8 | 同一权重与锁定评估集 | accuracy 与 calibration 变化、目标设备 p95 时延 |

建议作为项目目标（不是已通过门槛）：source macro-F1 不低于当前 0.8746；c9 recall 明显改善并给出司机级不确定性；frontal distraction recall ≥0.95 且 safe FPR ≤0.05。若目标不满足，报告实际 trade-off 并调整数据/范围，不能在 test 上反复调阈值。只有 4 个 source test drivers，泛化结论应保持克制；新增正面 holdout 更重要。

## 5. 30 FPS、30 帧与实时 pipeline

它们是三个不同设置：camera capture FPS、模型 infer FPS、aggregation window。当前 `deltaT=2` 是 replay tick，不是相机帧率。

- Camera 可以请求 ideal 30 FPS，并读取实际 track settings；实际设备不一定输出 30 FPS。
- 建议先保留 30 FPS 预览，模型以约 10–15 FPS 起步，在目标设备测量后再决定。队列只保留最新待处理帧（容量 1），忙时丢弃旧帧，防止排队造成“画面实时、结果几秒前”。
- 30 个预测在 30 inference FPS 下约 1 秒；在 10 inference FPS 下约 3 秒。所以推荐用时间戳定义 0.5–1 秒滑动窗口，而不是固定等到 30 次推理。
- 窗口每 100–200 ms 更新，并记录 sample count/覆盖时间/最新 capture age；低样本数或过期应明确 degraded。
- 均值/EMA 会带来延迟，并可能吞掉短动作。原前端的 High 持续 2 秒才 HIGH_ALERT、Low 持续 10 秒才恢复，必须算入总检测延迟；不要再把 1 秒窗口 + EMA + 2 秒 FSM 无限制叠加。
- 时间处理只能降低噪声，不能证明正面视角准确，也不能修复相机遮挡或缺少手部信息。

建议目标链路：

```text
Camera 30 FPS preview
  → capture timestamp + latest-frame slot
  → RGB/resize/normalize → warmed ONNX session → 10 logits → softmax
  → time-window aggregation → P_distraction + vision freshness + model hash

Raw telemetry + source timestamp
  → 8 ordered features → loaded XGBoost → 3 probabilities → 1-P(Safe)

两支证据 → server-side freshness/EMA/FSM/late fusion
          → SQLite 异步/批量记录 + latest result
          → dashboard polling 或 SSE → 五视图和导出
```

先实现本机 Python worker + ONNXRuntime CPU 与浏览器 UI。Jetson 的 TensorRT/FP16、手机的 CoreML/NNAPI、ARM CPU 的 INT8 作为设备确定后的分支实验；不在尚未指定设备时锁死工具链。ONNX Runtime 的 [mobile 部署文档](https://onnxruntime.ai/docs/tutorials/mobile/) 列出了硬件执行后端；是否更快需实测。

## 6. 后端优化及真实模型接入方案

保留 FastAPI、SQLAlchemy、SQLite、React 与两支 decision-level late fusion。现阶段没有证据支持为了“实时”更换数据库或引入 Redis。

| 优先级 | 具体工作 | 对应验证 |
|---|---|---|
| P0 | 注册显式 `mock` / `trained` provider；启动时加载一次，warmup；模型失败要显示 unavailable，不静默伪装成 mock | 换权重 hash 会改变来源；缺文件/错 shape/错类别时明确失败 |
| P0 | 新建 real frame + raw telemetry 输入协议；与 replay 概率端点分开，限制图片大小/尺寸，拒绝损坏输入 | 固定图片得固定预测；空图片、NaN、无效特征返回稳定错误 |
| P0 | manifest 记录 SHA256、架构、输入 NCHW/RGB/224、归一化、类别顺序、安全类索引、ONNX opset/runtime、训练数据版本 | notebook 与 service 在同一图片上概率误差 <1e-4；输出来自具体版本 |
| P0 | `c0 normal_driving` 到 UI `safe_driving` 做显式映射；XGBoost 固定 8 特征顺序及 best iteration | c0 的概率正确进入 `1-P(c0)`；重排输入仍按特征名校验 |
| P0 | 后端成为 live 模式 EMA/FSM 唯一执行者；session 隔离、restart/reset、并发顺序；缺失证据时不当作 safe | 同一时间序列 TS/Python 输出对齐；High <2s 不升级；新 session 不继承旧状态 |
| P0 | flag/delete 后失效 latest cache；删除最后窗口返回 404 | 本次 3 项 cache 回归探针转绿 |
| P0 | 每 session 原子分配单调序号、DB `(session_id, window_id)` UNIQUE、幂等 frame/window key、冲突重试 | 2 并发已复现 `[1,1]`；修复后唯一、重试不重复落库；删除最高编号后不复用 |
| P0 | 使用可解析 UTC 时间与每支 capture/arrival 时间，服务端计算 stale；验证概率有限/范围、latency 非负、权重和与阈值顺序 | 旧 timestamp 不再 FULL；非法输入拒绝；configured freshness 确实生效 |
| P1 | 推理 worker 与请求/UI 解耦，latest-frame backpressure；CPU pool 线程数可调 | 慢推理时 queue 不增长，drop count 和 input age 可见 |
| P1 | SQLite 单 writer、短事务、WAL/busy timeout 经并发测试后启用；按聚合窗口写入，不每帧同步写入 | 长时间稳定、写失败不阻塞模型；状态与已提交记录一致 |
| P1 | session/window 列表分页；SQL count/聚合替代 `len(s.records)`；stream export 避免全量 `.all()` | 大 session 内存与响应时间有界；导出数量正确 |
| P1 | 模型加载/就绪、每支 provenance、真实分段延迟、帧丢弃数、stale age、session state 指标 | dashboard 和导出可定位 replay/model/数据断流，status 不再硬编码 |
| P1 | frontend API adapter、明确模式、错误/断线/重连/初始空状态；服务端结果直接渲染 | live 模式关闭 prepared fallback；没有后端结果时显示 waiting/unavailable |
| P2 | UI 图表延迟加载、历史数据分页/抽样，修复 lint；固定测试依赖版本与 SQL migration | bundle/长 session 渲染改善；CI 全绿 |

若以后跨机器或多人访问，才增加对应认证、session ownership、明确 CORS origin 和限流；本机单用户实验不需要为尚不存在的部署引入大型平台。

量化：对 CNN 优先评估 representative calibration 的 static INT8/QDQ，校准数据来自 train/calibration 子集，不使用最终 test；保留 FP32 对照，并测弱类/calibration 变化。量化会引入精度变化，速度也依赖硬件算子支持，参考 [ONNX Runtime quantization](https://onnxruntime.ai/docs/performance/model-optimizations/quantization.html)。不应直接把动态量化一键结果当作 edge 最优解。

## 7. 分阶段计划与完成标准

以下是单开发者、数据和设备可用时的约 6 周工作块，可按实际学期调整；不是保证工期。

| 阶段 | 时间估算 | 交付 | 完成标准 |
|---|---|---|---|
| A 基线冻结与协议 | 1–2 天 | 本次审计、split/model manifest、类别/预处理契约 | 保存原始 checkpoint；测试能重复；明确 mock 与 trained 模式 |
| B 后端可靠性 | 2–4 天 | cache/编号/时间验证修复、EMA/FSM 状态服务、回归测试 | 本次 10 个预期失败变为真正通过；额外并发/重启/多 session 测试通过 |
| C 真实模型垂直接入 | 3–5 天 | MobileNet ONNX + XGBoost provider、真实输入端点、frontend API adapter | 固定图和 telemetry 经真实模型到 UI/DB/export 的值一致；模型缺失不回退成伪结果 |
| D 正面数据与模型对照 | 1–2 周，可与 B/C 并行采集 | frontal 分组标注集；Large/Small/B0 公平微调报告 | val 选型、test 锁定；报告每类/每司机指标与 calibration |
| E 时间与设备优化 | 3–5 天 | 时间窗/EMA ablation、FP32/FP16/INT8 和后端线程对照 | 在实际设备测 30 FPS capture、有效 infer FPS、p95 age、事件延迟、温度/功耗 |
| F 集成与论文证据 | 3–5 天 | 30–60 分钟连续运行、断流/恢复/E2E 记录、报告更新 | raw log、可重跑命令、模型版本、失败场景齐全；未通过目标明确披露 |

依赖关系：A → B/C → F；正面数据决定 D 能否完成；设备到位决定 E 能否完成。不要等待 B0 训练结束才接现有 ONNX，先证明真实 baseline 在完整系统中工作。

## 8. 测试验收矩阵

| ID | 范围/输入 | 方法与建议目标 | 当前 |
|---|---|---|---|
| T01 | 已训模型 + source holdout | 全 3,657 张，记录 hash/预处理/全部类指标 | 已完成 |
| T02 | PyTorch vs ONNX | 多类真实图概率误差 <1e-4、argmax 一致；扩展到全部类覆盖样本 | 128 张已完成，未宣称全域等价 |
| T03 | B0 vs MobileNet | 完整 split 的冻结骨干 pilot；正式对比再用同预算微调/3 seed | pilot 见实验结果；完整微调待做 |
| T04 | 后端故障回归 | cache、并发重复、非法 timestamp、旧证据、FSM、EMA、值域 | 已复现 10 项失败，待修 |
| T05 | 真实数据 E2E | 同一 frame ID 和模型 hash 可追溯至 UI/DB/export；禁用 replay fallback | 待实现 |
| T06 | 连续正面标注视频 | driver-disjoint；事件 precision/recall、误报/小时、切换率、time-to-detect | 缺正面标注数据 |
| T07 | 摄像头/队列/网络故障 | camera unplug、模糊/黑屏、慢 worker、乱序/重复帧、断网重连 | 待 live 接入；缺失不能显示 safe |
| T08 | 目标 edge 稳态 | 30–60 分钟，warmup 独立；固定 batch=1，p50/p95/p99，FPS、drops、RSS、功耗/温度 | 设备未指定；本机 forward timing 仅作参考 |
| T09 | 实时目标 | 若要求每帧推理 30 FPS，整个串行预算 ≤33.3ms；若 10 FPS 推理，输入 age p95 建议 <200ms，UI freshness 建议 <500ms | 建议值；aggregation/FSM 延迟另列，不能算进“零延迟” |
| T10 | 量化正确性 | 与 FP32 同数据比较；初始可设 macro-F1 降幅 ≤1 个百分点且 weak class/校准无显著恶化 | 待目标设备验证 |
| T11 | 长 session 持久化 | 并发、重启、删除、分页、导出；数据库事务与 cache 一致 | 当前只有 CRUD smoke 和缺陷探针 |

设备测试必须记录：硬件型号/内存、OS、运行时及 execution provider、线程、输入分辨率、权重 hash、精度、warmup、测量次数、供电/散热模式。端到端 latency 从 capture timestamp 开始；另报 decode/preprocess/queue/model/fusion/network/render 各段。`1000 / forward_ms` 只能称 model-only throughput 估算。

## 9. 可复现命令与新增文件

从项目根目录执行。现有 `.venv` 已有依赖，本次未修改依赖清单；新实验不覆盖原 notebook、权重或原 metrics。输出文件若已存在，脚本会拒绝覆盖，请换名。

```bash
npm test
npm run build
npm run linc
PYTHONPATH=backend .venv/bin/python -m pytest backend/tests -q -rx
# 下条应返回失败：直接呈现尚未修复的缺口
PYTHONPATH=backend .venv/bin/python -m pytest backend/tests/test_audit_regressions.py --runxfail -q

.venv/bin/python ml/experiments/vision_benchmark.py --output /tmp/vision-recheck.json
.venv/bin/python ml/experiments/telemetry_benchmark.py --output /tmp/telemetry-recheck.json
OPENBLAS_NUM_THREADS=2 OMP_NUM_THREADS=2 VECLIB_MAXIMUM_THREADS=2 \
  .venv/bin/python ml/experiments/linear_probe.py --output /tmp/linear-probe-recheck.json
```

默认数据路径来自现有 README 的 sibling repo；可用 `--data-root` 指定其他位置。冻结骨干实验还需要官方 EfficientNet-B0 ImageNet 权重和既有 MobileNet ImageNet 权重，脚本参数可指定路径；脚本检查官方 SHA256 前缀。B0 本次从 [PyTorch 官方下载地址](https://download.pytorch.org/models/efficientnet_b0_rwightman-7f5810bc.pth) 获取；大文件、feature cache 和线性头保存在 git-ignored `ml/experiments/cache/`。

新增：[vision_benchmark.py](../ml/experiments/vision_benchmark.py)、[telemetry_benchmark.py](../ml/experiments/telemetry_benchmark.py)、[linear_probe.py](../ml/experiments/linear_probe.py)、[后端审计探针](../backend/tests/test_audit_regressions.py) 和本次证据目录。这里交付的是分析、实验工具、实测证据和实施计划；**尚未将 production frontend/backend 切到真实模型**，也未声称已达到正面实时 edge 部署。
