# Whole System 实施进度与下一步

更新：2026-10-09。测试分别在 2026-09-28、10-05、10-09 执行，以下按证据注明日期。

## 当前结论

**已接通可运行的本机系统：实时 camera → 已训练 MobileNetV3；prepared telemetry 原始特征 → 已训练 XGBoost；后端融合/告警/SQLite → React 五视图/历史/导出。**

只有 camera 是现场实时输入。Telemetry 按预先准备的场景循环回放，没有连接真实车辆传感器，也不与 camera 中的动作构成同一真实驾驶事件。界面、API provenance 和导出都明确标注 `prepared_replay`。

用户要求的优先级已执行：先完成现有模型的 whole system，暂停其他模型下载/使用和对比。没有把 EfficientNet 接入系统，也没有声称提高了视觉模型的离线准确率。已有权重接通与准确率提升是不同事项。

## 已完成清单

| 部分 | 已实现/验证 |
|---|---|
| 项目核查 | 读取引用任务「评估正面视角和30帧」；确认旧 camera 仅 preview、UI/后端用 prepared/mock 概率的问题 |
| 真实模型服务 | 复用 ONNXRuntime CPU session 与 XGBoost booster；RGB/224×224/ImageNet 预处理、类别/特征顺序、best_iteration、模型 SHA256 核对 |
| 输入 API | `/infer` 接图片、时间戳和原始 8 特征，服务端计算概率；live/replay 会话隔离；缺权重/依赖返回 503，不悄悄回退 mock |
| 后端融合 | session 独立配置、vision EMA、freshness-aware late fusion、持续告警 FSM；断流清理连续状态；前端不重复处理 live 结果 |
| 状态与数据库 | 原子单调窗口编号、唯一约束、request ID 去重/冲突检测、乱序拒绝；DB authoritative latest；flag/delete 一致；状态跨进程重启恢复 |
| 数据库性能/迁移 | WAL、busy timeout、短写事务、模型运算不占写锁、SQL count、分页、流式导出；additive migration 保留旧记录 |
| 前端实时控制 | camera 采帧、一次一个请求、超时/退避、Start/Pause/New Session、模型检查、历史加载、标记与导出 |
| 五视图 | Live Monitor、Signal Inspector、Risk Trends、Explanation、Configuration 接通后端结果；保留独立 Prepared replay demo |
| 诚实状态显示 | camera/telemetry 来源、模型 hash、处理/请求耗时、实际请求完成速率；camera missing、结果 stale、故障和空状态显示 |
| 回归修复 | 修复新状态刷新打断旧 demo 定时器的问题；图表采用会话阈值；缺失分支不显示为正常的 0% 输入 |
| 交付文档 | 根 README、backend README、当前启动指南与本进度表；旧文档增加历史快照提示，CLAUDE.md 更新运行事实 |

## 测试记录

### 工程与集成

| 检查 | 结果 | 证据 |
|---|---|---|
| Backend pytest（10-09） | **28 passed**；无 xfail/skip | [runtime-backend-tests.log](evidence/2026-10-09/runtime-backend-tests.log) |
| Frontend Vitest（10-05） | **32 passed**，4 个测试文件 | [runtime-frontend-tests.log](evidence/2026-10-05/runtime-frontend-tests.log) |
| TypeScript + Vite build（10-05） | 通过 | [runtime-frontend-build.log](evidence/2026-10-05/runtime-frontend-build.log) |
| ESLint（10-05） | 通过 | [runtime-frontend-lint.log](evidence/2026-10-05/runtime-frontend-lint.log) |
| 浏览器真实模型链路（10-05） | 模拟 camera → 实际权重 → DB → UI；切换视图后 camera 推理继续 | [browser-live-check.log](evidence/2026-10-05/browser-live-check.log)、[运行截图](../output/playwright/live-runtime.png) |
| 浏览器五视图/flag/下载（10-05） | 通过；下载 JSON/CSV 各 169 条记录，首条 flag 保留 | [browser-views-exports-check.log](evidence/2026-10-05/browser-views-exports-check.log) |
| 暂停/恢复/新会话/camera 停止/历史（10-05） | 通过；恢复到 window 170，新会话从 1 开始；camera 停止后 vision missing、DEGRADED | [browser-session-check.log](evidence/2026-10-05/browser-session-check.log) |
| 故障恢复/独立 demo（10-05） | 注入 503 后显示错误、不回退 demo；恢复后仍是真实 provider；修复后 demo 连续到达至少 2 个窗口 | [browser-errors-check.log](evidence/2026-10-05/browser-errors-check.log) |
| 最新 HTTP/导出链路（10-09） | 实际 HTTP 服务执行固定 JPEG + prepared 特征，JSON 与 CSV 中完整特征/概率一致 | [http-runtime-check.json](evidence/2026-10-09/http-runtime-check.json) |

28 项后端测试覆盖：CRUD/flag/latest/delete、并发编号、概率/时间边界、EMA/FSM、坏图片、缺失/过期/乱序输入、真实模型/API/DB/导出一致、请求幂等与冲突、缺权重/依赖、旧库迁移、模型 readiness 与历史记录区分，以及两个 session 在真正进程重启后的状态隔离/恢复。预处理对照使用非均匀图像并与 torchvision 比较。

浏览器测试使用 Chrome 模拟摄像头，**没有测试你的物理 camera 权限、真实人像识别准确率或 edge 硬件**。故障注入产生的 503 console 项是预期测试事件。`browser-errors-before-replay-fix.log` 记录了旧 demo 定时器回归的失败；最终结果以修复后的日志为准。

当前还有两个不阻断运行的工程提示：主 JS bundle 约 611 kB（gzip 175 kB）的构建提示；测试工具 httpx 的弃用提示。不是业务测试失败。

### 原模型复测（09-28，权重未改动）

| 项目 | 测量结果 | 边界 |
|---|---|---|
| MobileNetV3-Large，3,657 张完整 test | accuracy **89.8824%**；macro-F1 **87.4641%** | State Farm 源视角，不是正面 camera 准确率 |
| 10 类覆盖的 128 张 PyTorch/ONNX 对照 | argmax 分歧 **0**；最大概率差约 **4.17e-6** | 样本对照，不是所有输入的形式证明 |
| c9 talking_to_passenger | recall **27.33%**、F1 **39.72%** | 优先排查的弱类 |
| XGBoost，4,500 条 test | accuracy **99.9333%** | 合成数据，不能代表真实车辆传感器表现 |
| 1,000 张 validation 鲁棒性探针 | 原始 accuracy 90.3%；暗化 87.2%；模糊 88.7% | 不是正面数据实验 |

源结果：[vision-stratified-parity.json](evidence/2026-09-28/vision-stratified-parity.json)、[telemetry-benchmark.json](evidence/2026-09-28/telemetry-benchmark.json)、[robustness-probe.json](evidence/2026-09-28/robustness-probe.json)。

EfficientNet-B0 官方权重在用户调整优先级**之前**下载过，probe 已中断，没有完成对比或集成；不将不完整实验作为优劣结论。不会继续此项，除非用户恢复该方向。

## 现在如何运行

从项目根目录：

```bash
npm run build
.venv/bin/python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

打开 http://127.0.0.1:8000 → Live trained models → Start Monitoring → 允许 camera。已有依赖与本地模型即可运行，服务不会下载新模型。详细安装、开发启动、配置、数据保存路径与故障处理见 [LIVE_RUNTIME_GUIDE.zh.md](LIVE_RUNTIME_GUIDE.zh.md)。

默认 camera 请求 30 FPS，推理目标 10 FPS（可调 1–30）；页面分别显示流配置帧率和最近请求完成速率。浏览器截图为模拟 camera 报告 20 FPS、推理约 10 FPS；这不是物理 camera 30 FPS 或 edge 性能达标证明。当前没有 30 帧投票，使用的是 EMA 与时间持续告警。

## 后面要做什么

| 顺序 | 下一步 | 验收方式/需要的输入 |
|---|---|---|
| 1 | 用你的实际 camera 做桌面验收 | 允许权限；检查正常姿势/动作、Stop/Start、断开重连、5–10 分钟连续运行；记录 FPS、延迟和错误。正常桌面操作即可，无需实际驾驶 |
| 2 | 建立正面视角标注集 | 多人、不同光照/距离、10 类；按司机分组划分；独立 test 不参与调参 |
| 3 | 改善现有 MobileNet 弱类 | 审查 c9/c8 错误样本、统一机位/预处理、补代表性数据，再用 validation 比较采样/增强/微调方案 |
| 4 | 验证准确率和稳定性 | macro-F1、各类 recall、混淆矩阵、safe 误报率；视频按事件评估告警延迟/误报次数。EMA 不能补救视角缺失 |
| 5 | 指定 edge 设备后实测 | 固定硬件/电源/分辨率/模型；测 capture→显示的 p50/p95、丢帧、吞吐、内存/温度与持续运行。先建立 FP32 baseline，再决定量化 |
| 6 | 可选后续工程优化 | 图表按需加载、历史分页浏览、真实 feature attribution、模型 manifest/版本流程；按实际测量优先级实施 |
| 暂缓 | EfficientNet 等其他模型 | 用户恢复模型对比后，在同一 split/预处理/训练预算下比较精度与端到端成本 |

这些后续项不等于当前功能仍使用 mock。当前软件链路已经接通；未完成的是物理设备与目标数据域的实测、精度迭代和可选扩展。尚未实现人脸/驾驶员存在检测；整帧分类器对非驾驶画面也会给出类别概率。Live feature contribution 没有伪造 SHAP，当前显示 unavailable。

## 代码与计划入口

- [初始审计和精度/edge 计划](PROJECT_ASSESSMENT_AND_TEST_PLAN.zh.md)：保留修复前证据，不应当作今天的系统状态。
- [真实 provider](../backend/app/providers/trained.py)、[输入与存储 API](../backend/app/routers/windows.py)、[后端融合](../backend/app/inference.py)。
- [前端实时控制](../frontend/src/hooks/useLiveSession.ts)、[摄像头采集](../frontend/src/hooks/useCameraPreview.ts)、[主界面](../frontend/src/App.tsx)。

没有提交 git commit。用户原有的 `AGENTS.md` 修改保留；训练 notebook、原始数据和训练权重没有被覆盖。测试使用独立临时数据库。
