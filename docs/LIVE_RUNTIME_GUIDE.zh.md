# 实时模型系统：启动、操作与边界

更新：2026-10-09。当前交付是本机运行的研究原型：**实时 camera + prepared telemetry + 实际训练权重 + 后端融合/存储 + React dashboard**。

## 1. 输入与推理

```text
Browser getUserMedia → 最新 JPEG 帧 → MobileNetV3-Large ONNX → 1-P(c0)
Prepared CSV → 每 2 秒切换一行原始 8 特征 → XGBoost → 1-P(Safe)
                          ↓
               Backend EMA → freshness-aware late fusion → alert FSM
                          ↓
                  SQLite → dashboard / JSON / CSV
```

- **只有 camera 是真实现场输入。** Telemetry 是预先准备的场景数据，循环回放；不是车辆传感器，也不与实际驾驶动作同步。
- Telemetry 运行时重新计算 XGBoost 概率，不使用 CSV 中的 `p_safe/p_aggressive/p_distracted` 来冒充推理。`telemetry_source=prepared_replay` 会写入每条输出与导出。
- Live 模式的 telemetry 时间戳表示本次回放提交时间，不是原始车辆采集时间；输入缺失行保持 missing。旧 demo 的 stale 场景标签属于 demo，不能把 live 回放的新时间戳解释为真实传感器新鲜度。
- 图片在请求内进行推理，不存储图片/视频；数据库保留概率、8 特征、时间、模型 SHA256、来源、融合参数和告警结果。
- Vision EMA 和告警 FSM 在后端执行一次。High 连续至少 2 秒升级 HIGH_ALERT；Low 连续至少 10 秒恢复 NORMAL；Medium 为 CAUTION。断流超过 freshness tolerance 会清除连续状态。

## 2. 启动

从项目根目录运行。现有 `.venv` 和 `node_modules` 已在本机用于测试；无需下载其他模型。

首次安装依赖（已有环境可跳过）：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements-inference.txt
npm ci
```

服务需要以下**已有训练产物**，不会自动下载替代模型：

```text
ml/outputs/vision/mobilenetv3_large_vision.onnx
ml/outputs/vision/metrics.json
ml/outputs/telemetry/xgb_telemetry.json
ml/outputs/telemetry/metrics.json
```

训练所用 PyTorch 不在在线服务依赖中；`.pt` 仅用于离线评估/训练。`metrics.json` 用于核对类别、特征顺序和 XGBoost best_iteration。

开发时打开两个终端：

```bash
# 终端 1：API，默认创建根目录 driver_risk.db
.venv/bin/python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

```bash
# 终端 2：Vite；/api 自动代理到 127.0.0.1:8000
npm run dev
```

打开终端显示的 Vite URL（通常 http://127.0.0.1:5173）。浏览器允许 camera 权限；camera 需要 localhost 或 HTTPS 安全上下文。

单服务演示：

```bash
npm run build
.venv/bin/python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

打开 http://127.0.0.1:8000；FastAPI 在 API 路由之后提供 `dist/`。先 build，再启动服务器。`npm run preview` 只预览静态页面，不是完整的单服务运行命令。

API 文档：http://127.0.0.1:8000/docs。`GET /api/health` 检查进程；`GET /api/models` 实际加载/检查本地模型，成功返回模型版本，失败返回 503。

环境变量（可在根目录 `.env` 配置，不必覆盖已有文件）：

| 变量 | 默认/用途 |
|---|---|
| `DRA_DATABASE_URL` | `sqlite:///./driver_risk.db`；路径相对于启动目录 |
| `DRA_MODEL_ROOT` | 仓库 `ml/outputs`；可指向已有模型副本 |
| `DRA_INFERENCE_THREADS` | `2`；ORT / XGBoost CPU 线程数 |
| `DRA_CORS_ORIGINS` | JSON 数组；默认 localhost/127.0.0.1:5173 |
| `VITE_API_BASE_URL` | 可选构建时配置；默认同源 `/api` |

当前部署面向本机单用户研究演示，使用单 Uvicorn worker。未实现公网账户、权限、TLS 网关或车载控制；无需为了本机演示更换 SQLite。

## 3. 页面操作

1. Data mode 选择 **Live trained models**，点击 **Start Monitoring**。首次会启动 camera、检查模型并创建 session。已有浏览器配置若保留 demo 模式，需要手动切换。
2. 页面显示 `Vision: camera → trained MobileNetV3`、`Telemetry: prepared raw features → trained XGBoost`，可展开模型 SHA256。
3. Camera 请求 640×480、30 FPS；显示的是浏览器 track 报告的流帧率。推理默认目标 10 FPS，可调 1–30；实际完成速率是最近最多 20 次请求的均值，不保证达到目标。摄像头采集、推理频率和 EMA 是三个不同概念；当前没有“30 帧投票”。
4. 每次最多一个推理请求，只抓最新画面，不积压旧帧。Request round trip 是浏览器采帧/编码/请求往返；Server processing 包括模型与融合等提交前处理，不包括 DB commit 和 UI 渲染。
5. **Pause** 停止推理；预览仍可继续。**Stop Camera** 关闭 camera。Camera 停止而 telemetry 继续时显示 DEGRADED/vision missing，评估仅来自 prepared telemetry。暂停/断网后超过 3 秒默认容差，当前评估显示 unavailable，历史仍可查看。
6. **Start Monitoring** 可恢复本次 session，并同步可能在暂停时已提交的最后记录。**New Session** 新建 session，不删除已有历史。修改配置也会在下次开始时创建新 session。
7. **Refresh saved sessions** → 选择历史 session → Signal Inspector 标记/取消标记。加载的历史用于查看；再次 Start 会新建采集 session。
8. Configuration 的 JSON/CSV 导出来自后端，包含全部记录。页面仅保留最近 500 条，session 下拉默认最近 100 个；更早记录可通过分页 API 或整段导出读取。
9. **Prepared replay (legacy, test-only)** 保留旧的本地回放，使用预设概率/本地融合/localStorage，只用于回归测试与向后兼容（D03：系统只保留 Live Monitoring 作为正式运行模式）。它与 Live 模式有明确标识；重新打开页面时总是回到 Live；模型故障不会自动切到回放。

错误提示：模型文件/依赖缺失为 503；无效图像/特征为 422；乱序帧或请求 ID 内容冲突为 409。网络错误退避重试，新请求抓取最新帧。404/409/422/503 暂停采集并显示错误，需要修复原因后 Start。

## 4. 数据、复现与后续

- SQLite 自动进行 additive migration，保留旧 session/window；旧窗口若存在重复编号，启动会报错要求人工核对，不会删除记录“修复”。
- Session 保存自己的融合配置和 EMA/FSM 状态，编号单调增加；重启或删除单条记录不会重用编号。重复相同 request ID/输入返回原记录，冲突返回 409。
- 测试：[IMPLEMENTATION_PROGRESS.zh.md](IMPLEMENTATION_PROGRESS.zh.md) 与 [浏览器/前端证据](evidence/2026-10-05)、[最终后端/HTTP 证据](evidence/2026-10-09)。浏览器使用模拟 camera，模型与数据库真实运行。
- 下一步是实际 camera/权限验收、带标签正面视频评估与指定 edge device 的时延/掉帧/持续运行测试。State Farm 测试集 accuracy 不能代表正面实拍准确率。
- Vision 当前是整帧分类器，没有额外人脸/驾驶员存在检测；空座位/非驾驶场景仍可能给出类别概率。真实特征 SHAP 尚未接入，Live 的 feature-contribution 项显示 unavailable；不使用 demo 的人工贡献值冒充解释。
- EfficientNet 等对比按用户要求暂停；精度改善方案保留在 [初始分析与实验计划](PROJECT_ASSESSMENT_AND_TEST_PLAN.zh.md)。
