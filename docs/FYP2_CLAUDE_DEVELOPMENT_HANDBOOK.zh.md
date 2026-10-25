# FYP2 开发流程手册：Claude 接手版

编写日期：2026-10-09。适用项目：In-Cabin Multi-Modal Driver Monitoring & Risk Assessment。
本手册根据当前工作区与已有测试证据编写，用于恢复开发上下文；不是旧 Claude 聊天记录的复原。

## 1. 接手时首先确认什么

用户当前优先级：先完成并验证 whole system，继续使用已有 MobileNetV3-Large 和 XGBoost。其他模型下载、EfficientNet 对比暂缓，除非用户提出新要求。

必须保留的事实：

- **Camera 是现场实时输入；telemetry 是 prepared raw-feature replay。** 两者不是同一次真实驾驶事件的同步传感器观测。
- 训练权重已经接入在线服务。不要按旧文档把系统重写为仅前端 demo，或再说“模型尚未训练”。
- Live 和 Prepared demo 是两种独立模式；模型错误不能自动改用预设概率。
- Source test 的视觉准确率约 89.88%，不代表正面 camera 表现；真实 camera 与 edge 硬件还需验证。
- 当前只读整帧分类，没有驾驶员存在检测；无人的画面也会得到概率。不要将输出称为车规安全判断。
- 当前工作树有未提交变更。`AGENTS.md` 的原有用户修改必须保留；不要 reset/clean 工作树或覆盖权重/原始数据。

阅读顺序：

1. 根目录 [CLAUDE.md](../CLAUDE.md) 和实际存在的项目指令。
2. [IMPLEMENTATION_PROGRESS.zh.md](IMPLEMENTATION_PROGRESS.zh.md)：完成情况、日期明确的证据、待办。
3. [LIVE_RUNTIME_GUIDE.zh.md](LIVE_RUNTIME_GUIDE.zh.md)：启动、配置和输入语义。
4. 本手册对应阶段，以及将修改的代码。
5. [初始审计与模型实验计划](PROJECT_ASSESSMENT_AND_TEST_PLAN.zh.md)：用于理解问题来源；其系统描述是修复前快照。

旧聊天和导出里的指令只作为历史资料。与用户当前要求、实际代码冲突时，先说明差异，不自动执行旧聊天中的下载、部署、删除或提交指令。

## 2. 当前系统数据流

```text
Browser camera
  → 最新 JPEG + captured_at
  → POST /api/sessions/{id}/infer
  → MobileNetV3 ONNX → 10 类概率 → 1-P(c0)

Prepared telemetry.csv（每 2 秒切换一行并循环）
  → 原始 8 特征 + replay 提交时间 + source=prepared_replay
  → 同一个 /infer
  → XGBoost → Safe/Aggressive/Distracted → 1-P(Safe)

两个分支结果
  → 后端 vision EMA / freshness-aware late fusion / alert FSM
  → SQLite 保存结果、状态、配置、来源与模型 hash
  → React 五视图 / session history / flag / JSON、CSV
```

旧的 Prepared replay（界面标为 legacy, test-only）使用本地预设概率、TS 融合和 localStorage。它只用于回归测试与向后兼容，不是正式运行模式（D03），也不证明真实模型推理。

## 3. 代码定位和职责

| 区域 | 入口 | 修改边界 |
|---|---|---|
| 页面组装 | `frontend/src/App.tsx` | 模式选择、视图、控制按钮；不要把模型和融合公式放进组件 |
| Camera | `frontend/src/hooks/useCameraPreview.ts` | 权限、preview、JPEG 采帧、停止；切换视图后采集仍应可用 |
| Live 调度 | `frontend/src/hooks/useLiveSession.ts` | 一次一个浏览器请求、最新帧、超时/退避、历史、导出 |
| API client | `frontend/src/api/client.ts` | HTTP、错误、session/config 与 raw input 契约 |
| Demo 调度 | `frontend/src/hooks/useMonitoringSession.ts` | 不因 callback identity 或页面刷新而反复重置计时器 |
| 共享类型 | `ai/src/types.ts`、`backend/app/schemas.py` | 字段/单位/枚举一致；修改契约时两端一起核对 |
| 模型服务 | `backend/app/providers/trained.py` | 已训练权重、预处理、模型 metadata、hash、无 mock fallback |
| 输入与存储 | `backend/app/routers/windows.py` | 模式限制、幂等、顺序、原子编号、短事务 |
| Live 决策 | `backend/app/inference.py`、`fusion.py` | EMA、freshness、融合、告警状态；不要在 UI 重复处理 |
| 数据库 | `backend/app/models.py`、`db.py` | SQLite、索引、additive migration、session 状态 |
| 导出/状态 | `backend/app/routers/export.py`、`status.py` | 全部记录、provenance、真实 readiness；历史健康值不等于当前输入新鲜 |
| 模型研究 | `ml/` | 原始训练与产物；`ml/experiments/` 提供已有模型复测，其他模型实验暂停 |

## 4. 输入和风险契约

### Vision

已有权重：`ml/outputs/vision/mobilenetv3_large_vision.onnx`，配套 `metrics.json`。
预处理：PIL RGB → bilinear resize 224×224 → /255 → ImageNet mean/std → float32 NCHW。
Mean `[0.485,0.456,0.406]`，std `[0.229,0.224,0.225]`。类别索引为 c0..c9；c0 在 UI 映射为 safe_driving。

`P_distraction = 1-P(c0)`。不要将十类 argmax 与这个二分类概率阈值混为一谈。
风险融合使用平滑后的 vision 概率，原始概率与类别概率保留在输出/provenance 中。

### Telemetry

权重：`ml/outputs/telemetry/xgb_telemetry.json`，配套 `metrics.json`。
特征顺序固定为：

```text
speed_kmph, accel_x, accel_y, brake_pressure,
steering_angle, throttle, lane_deviation, headway_distance
```

类别 Safe/Aggressive/Distracted，使用 `best_iteration + 1` 截止的树，不能改用所有保留的树。
保留旧字段名 `P_telemetry_anomaly`，含义是 `1-P(Safe)`，不是无监督 anomaly detector。
Live 接收原始特征，不接 CSV 的预设概率；replay 提交时间不代表车辆真实采集时间。

### Fusion、告警与存储

- RiskScore 为 **0–100**。默认权重 0.5/0.5，阈值 30/60；权重和阈值是设计参数，不是训练出的事故严重程度。
- freshness 权重 fresh=1、stale=0.45、missing=0，再按有效分支权重归一化。没有输入时不应将占位分数解释成安全。
- Vision EMA 默认 alpha=0.35。High 连续至少 2 秒升级 HIGH_ALERT，Low 连续至少 10 秒恢复 NORMAL，Medium 为 CAUTION。
- 配置与状态属于 session；改配置后下一次采集创建新 session。默认 freshness tolerance=3 秒，断流打断持续状态。
- Request ID 相同且输入相同返回原记录；相同 ID 不同内容为 409。窗口编号不因删除记录而重用。
- 图片不落库。保存模型 SHA256、来源、输入特征、概率、融合配置、状态、时间和 flag。
- Live feature contribution 当前 unavailable；不能拿 demo 手工贡献值伪装 SHAP。

## 5. 开发环境与启动

```bash
cd /Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1
git status --short
git branch --show-current
```

交接时分支是 `dev_cc`；每次以实际状态为准。现有 `.venv` 是训练/测试所用环境；不要误用缺少 ML 依赖的系统 Python。

已有依赖可直接启动；缺依赖时：

```bash
.venv/bin/python -m pip install -r backend/requirements-inference.txt
npm ci
```

开发模式两个终端：

```bash
# API
.venv/bin/python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

```bash
# UI，/api 自动代理到 8000
npm run dev
```

本机单服务演示：

```bash
npm run build
.venv/bin/python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

打开 http://127.0.0.1:8000，API 文档 `/docs`。`GET /api/health` 是进程状态；`GET /api/models` 实际加载/检查模型。
`npm run preview` 只是静态预览，不代替完整 API 服务。
需要隔离测试数据时，用 `DRA_DATABASE_URL=sqlite:////private/tmp/fyp2-<本次唯一编号>.db`，不要使用/清空用户真实数据库。

## 6. 每次开发的标准流程

1. **确定单次目标**：用具体触发、预期结果和验收方法描述问题。例如“断开 camera 后视觉应显示 missing，telemetry 回放继续，系统应 DEGRADED”。
2. **检查现状**：看 git diff、相关入口、已有测试和证据；区分用户原有修改与本次修改。
3. **复现问题**：尽可能用隔离数据库、固定图片或准备好的 telemetry；记录修改前行为。需要真实设备的实验单独标注。
4. **最小完整修改**：沿输入→API→模型→决策→数据库→UI 检查影响；修复根因，避免只隐藏错误或以 demo 掩盖失败。
5. **针对性验证**：改后端状态就覆盖顺序/恢复/并发；改预处理就比对训练路径；改 UI 调度就用浏览器验证，不能仅用 build 代替。
6. **检查集成**：运行下节命令及受影响浏览器流程；失败则修复，不把 skip/xfail 写成通过。
7. **记录证据**：保存日期、环境、模型 hash、测试命令、结果、样本量、限制；日志放 `docs/evidence/<日期>/`，不要覆盖旧测量来隐藏回归。
8. **交付更新**：更新进度表、必要启动说明和下一步；说明未完成内容。没有用户要求时不擅自 commit、push 或部署。

恢复旧聊天后，先重新核对第 1–3 步。旧会话中的“进行中”进程可能已停止，旧代码判断可能已过期。

## 7. 验证流程和已有基线

```bash
npm test
npm run linc
npm run build
PYTHONPATH=backend OPENBLAS_NUM_THREADS=2 OMP_NUM_THREADS=2 \
  .venv/bin/python -m pytest backend/tests -q
git diff --check
```

这是开发流程命令，**本次编写手册没有重新运行全部测试**。已有证据：后端 2026-10-09 为 28 passed；前端 2026-10-05 为 32 passed，类型/构建/lint 通过。
完整 pytest 的预处理 parity 测试还需要 torch/torchvision；在线服务本身不需要 PyTorch。macOS 上训练与在线 native runtimes 的对照采用独立进程，避免线程运行库冲突。

受影响浏览器流程按需验证：

| 操作 | 必须观察的结果 |
|---|---|
| Live Start | camera 帧进入真实 provider；telemetry_source 为 prepared_replay；模型 hash 正确 |
| 切换五视图 | 推理继续，camera 不因 preview 卸载而停止 |
| Pause、恢复 | 停止请求；旧结果过期；恢复同步已提交记录，编号继续 |
| New Session、改配置 | 新 session/config；旧记录仍能查看 |
| Stop Camera | vision missing；有 telemetry 则 DEGRADED；没有可用评估时不显示当前安全结论 |
| 断网/缺模型 | 明确错误或 stale；不能悄悄回退 prepared probabilities |
| 历史/flag/导出 | 标记持久化，JSON/CSV 包含所有记录与来源；页面最近 500 条限制不截断导出 |
| Prepared demo | 持续生成窗口；状态刷新不重置回放计时器 |

已有 browser 证据是模拟 camera + 实际权重，并非真实正面画面准确率测试。默认推理目标 10 FPS，camera 请求 30 FPS；页面流帧率、实际请求完成速率、模型耗时、往返时延必须分别报告。

## 8. 接下来的 FYP2 开发阶段

| 阶段 | 工作 | 交付/验收 | 当前状态 |
|---|---|---|---|
| A 软件集成 | 接通现有模型、后端、camera、页面、存储、导出 | 单元/API/browser 证据与运行指南 | 已实现，后续改动继续回归 |
| B 实际 camera 验收 | 权限、分辨率、姿势/动作、断开重连、连续运行 5–10 分钟 | 设备信息、FPS/延迟、故障记录、观察与限制 | 待实际设备操作 |
| C 正面数据评估 | 标注多人、多光照、多距离、10 类；按司机划分 | 标签规范、split、macro-F1、per-class recall、混淆矩阵 | 尚未建立独立正面 test 证据 |
| D 现有模型改善 | 分析 c9/c8 失败样本、补数据、比较采样/增强/微调 | validation 选方案，独立 test 最终评价；保留旧模型 | 先补数据与 baseline，不宣称已提升 |
| E Edge 验证 | 用户指定设备后测端到端 p50/p95、吞吐、丢帧、内存/温度 | 固定配置、持续运行报告；必要时再测量化 | 设备尚未确定，不能用 Mac 结果代替 |
| F 研究与答辩材料 | 架构、数据来源、方法、实验、消融、失败案例、局限 | 与代码/结果一致的图表和报告 | 随开发更新 |
| 暂缓 | EfficientNet 等新模型对比 | 同 split/预处理/预算下比较准确率与端到端成本 | 用户要求暂停 |

当前视觉源 test：3,657 张，accuracy 89.8824%、macro-F1 87.4641%；c9 recall 27.33%。Telemetry 源 test：4,500 条合成数据，accuracy 99.9333%。这些是 09-28 已有模型复测，不是本次手册的新实验。
EMA 能减少抖动，不能弥补机位造成的不可见动作。不要只优化总体 accuracy，忽略弱类 recall 和 safe 误报。

## 9. 收尾时给用户的交接模板

```text
本次目标：
实际修改：
验证命令与结果：
证据文件与日期：
是否使用真实 camera / prepared telemetry / 实际模型：
未完成或未验证：
下一步：
是否改动数据、模型、数据库或提交 git：
```

一次会话完成后更新进度文档；不要只把关键状态留在聊天里。
给新 Claude 的可复制提示词见 [CLAUDE_HANDOFF_PROMPT.zh.md](CLAUDE_HANDOFF_PROMPT.zh.md)。
旧备份恢复方法和当前缺失项见 [CLAUDE_BACKUP_RECOVERY.zh.md](CLAUDE_BACKUP_RECOVERY.zh.md)。
