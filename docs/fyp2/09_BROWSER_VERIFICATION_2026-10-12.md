# 浏览器实机验证与 `hair_makeup` 问题诊断

日期：2026-10-12，Asia/Kuala_Lumpur。本文补充原始 00–08 审计，保留其 2026-10-10 快照及原结论，避免把后来取得的证据写成当时已经完成。

## 结论

**真实电脑摄像头的推理链路已验证跑通；当前电脑画面的动作识别没有通过实用性验证。** 用户报告不停变换动作但结果仍为 `hair_makeup`。本次诊断观察到 394 个不同的 JPEG 指纹，394 次 HTTP 201、394 条对应数据库记录，视觉原始输出的最高类别全部为 `hair_makeup`。这不是重复发送同一张图片，也不是前端把新类别简单显示成旧类别：服务端原始类别概率与保存结果一致。

同一个部署 provider 对原数据集 test 的 30 张图片（每类按元数据顺序选前 3 张）给出了全部 10 类输出，25 张与标注一致。这个小样本只用于排除“模型对所有输入始终固定输出 c8”的假设，**25/30 不是正式准确率报告，也不能代表正面摄像头表现**。

证据支持优先调查目标场景泛化：训练机位与桌面正面画面、背景、身体/手部覆盖范围、光照不同。尚未做带逐动作真值的控制实验，不能确定唯一根因。RGB、224×224、ImageNet mean/std 与训练验证预处理一致，运行模型 hash 与已有源数据评估产物一致；本轮未发现这些配置不一致。

## 审计与写入范围

| 项目 | 本次范围 |
|---|---|
| 实际运行代码 | `/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1` |
| 分支/验证时 HEAD | `dev_cc` / `845b43a086e296d96835bf82e4ef8366c636e105` |
| 文档工作区 | `/Users/liu/.codex/worktrees/d39a/FYP-In-Cabin-Driver-Assessment--1`，HEAD `ae55041`；应用代码仍是旧版 |
| 浏览器 | Chrome，`http://127.0.0.1:8008/`，真实摄像头权限由用户明确批准 |
| 数据库 | 隔离验证库 `/tmp/fyp2-browser-oct10/validation.db`，非项目默认数据库 |
| 输入 | 真实电脑 camera；telemetry 是 `prepared_replay` 原始特征，经真实 XGBoost 推理 |
| 改动 | 新文档、日志、数值诊断脚本；没有改应用或训练代码，没有训练/下载模型 |

对 10-10 指纹清单中的 59 个应用及训练源码文件逐一复核，内容未变。主仓库期间另有 `AGENTS.md` 删除、`CLAUDE.md`、`eslint.config.js` 和 `docs/plans/` 的并行改动；这些不属于本次工作，不纳入本次文档提交。完整源证据见 [verification_manifest.json](evidence/2026-10-12-browser/verification_manifest.json)。

## 浏览器与数据库证据

主会话：`S8d4e616a597b4dd5973d31a9ad417049`，约 82 秒，811 条保存记录。开始/停止摄像头、暂停、恢复、历史加载、五视图、标记和下载实际通过 UI 执行。主会话没有画面指纹观察器，因此“每张画面都不同”的直接证据只来自下面的独立诊断会话。

| 检查 | 观察/结果 | 证据 |
|---|---|---|
| 真实 camera 运行 | 浏览器报告 stream 配置 30.0 FPS；请求完成速率约 9.7–10.0 FPS，目标 10；图像源/模型来源明确 | [01-live.txt](evidence/2026-10-12-browser/01-live.txt) |
| backend → UI → DB | 主会话 811 条；645 条含 camera 图像；585 FULL、226 DEGRADED | [verification_manifest.json](evidence/2026-10-12-browser/verification_manifest.json) |
| Stop Camera | vision missing、telemetry 可用时 DEGRADED，视觉分支显示无输入 | [03-camera-stopped.txt](evidence/2026-10-12-browser/03-camera-stopped.txt)、[截图](evidence/2026-10-12-browser/03-camera-stopped.jpg) |
| Start Camera 恢复 | 两分支 fresh，恢复 FULL；没有回退 demo provider | [04-camera-recovered.txt](evidence/2026-10-12-browser/04-camera-recovered.txt) |
| 暂停与历史 | 暂停时可存在最后一个在途提交；810 后最终保存 811；重开服务/新浏览器 tab 能加载 811 | [05-session-reloaded.txt](evidence/2026-10-12-browser/05-session-reloaded.txt) |
| 五视图 | Live Monitor、Signal Inspector、Risk Trends、Explanation、Configuration 均渲染对应会话 | 本目录 01–10 AX 文本/截图 |
| 标记 | Inspector 选 Window 753，Flag 后显示 Unflag；DB、JSON、CSV 均保留 true | [10-window753-flagged.jpg](evidence/2026-10-12-browser/10-window753-flagged.jpg)、[selected_window_753.json](evidence/2026-10-12-browser/selected_window_753.json) |
| 浏览器下载 | JSON 与 CSV 各 811 条；界面历史最多 500 条不影响全量导出 | [verification_manifest.json](evidence/2026-10-12-browser/verification_manifest.json) |
| 导出一致性 | JSON 全字段等于 DB payload 加最新 flagged；CSV 所有导出字段逐条等于 JSON；811 条独立手算融合公式一致 | [verify_saved_evidence.py](evidence/2026-10-12-browser/verify_saved_evidence.py) |

本轮下载原文件留在本机 Downloads；仓库保存下载 SHA256、校验脚本及两条数值样本，不复制全部下载记录。校验脚本使用明确的只读 SQLite 连接。摄像头已关闭，页面保留暂停后的历史记录。

## 画面更新与类别恒定诊断

诊断会话：`S05a3faf1461640c2855f6830a7282f2d`。

- 观察时间：2026-10-12 09:40:18–09:40:57 UTC（当地 17:40），约 40 秒。
- 394 次 camera 请求，394 个不同的图像 SHA256，输入均为 640×480；RGB 均值有变化。
- 全部 HTTP 201；request ID、window ID、规范化后 capture timestamp、10 类概率及 raw distraction 与数据库逐条一致。
- 最高视觉类别：`hair_makeup` 394/394。最后一条 `hair_makeup` 约 0.98、`talking_to_passenger` 约 0.02；页面可以显示这种概率变化，但最高类别仍不变。
- `P_distraction_raw` 范围约 0.999742–1.0。它是 `1−P(safe_driving)`，不是 `P(hair_makeup)`。
- 主会话的 645 条 camera 记录中，642 条最高类为 hair_makeup，3 条 reaching_behind；与用户报告一致，但没有逐动作真值，不能计算摄像头准确率。

使用 `/tmp` 的临时 ASGI 观察器导入原应用，对请求/响应做只读观察并原样传递。只写图像 hash、分辨率、RGB 统计、请求标识和概率，**未保存摄像头图片/视频**。保存的截图均为无摄像头画面的 Inspector/配置/趋势等页面。诊断结束后已停止观察器，恢复原 `app.main:app` 服务；未来运行不会继续写画面指纹。

证据：[frame_hash_summary.json](evidence/2026-10-12-browser/frame_hash_summary.json)、[frame_hash_trace.jsonl](evidence/2026-10-12-browser/frame_hash_trace.jsonl)、[camera_diagnostic_wrapper.py](evidence/2026-10-12-browser/camera_diagnostic_wrapper.py)、[13-diagnostic-inspector.jpg](evidence/2026-10-12-browser/13-diagnostic-inspector.jpg)。临时脚本中的本机绝对路径仅用于复现本次检查，不属于生产运行入口。

源场景对照：[source_class_probe.py](evidence/2026-10-12-browser/source_class_probe.py)、[source_class_probe.json](evidence/2026-10-12-browser/source_class_probe.json)。历史全 test/ONNX 对照保存在主仓库 `docs/evidence/2026-09-28/vision-stratified-parity.json`；这里不把历史 89.88% 重述为本轮实机准确率。

## 自动检查更新

2026-10-10 在主仓库运行，使用隔离临时目录/数据库，未改源码：

| 检查 | 结果 |
|---|---|
| backend pytest | 28 passed；有 httpx 弃用提示 |
| frontend/shared Vitest | 32 passed |
| 标准 `npm run build` | 通过；主 JS bundle 约 611 kB，存在大小提示 |
| `npm run linc` | 当时失败：扫描到嵌套 Claude 工作树的两个 prefer-const 错误 |
| `npm run linc -- --ignore-pattern '.claude/**'` | 主项目源码检查通过；保留原失败日志，不修改另一工作树 |

证据目录：[2026-10-10-browser](evidence/2026-10-10-browser/)。其后应用源码未变，未重复整套回归。新增数值诊断/导出校验均已实际运行通过。当前并行 lint 配置变动不由本次验证声称已验收。

新增文档链接、Python 语法和 JSON 数据已校验；Git whitespace 检查覆盖新增文档/脚本/JSON。原始 AX 文本及工具日志保留采集时的尾部空格/空行，未为满足格式检查而重写证据内容。

## 原审计缺口的状态变化

| 原项 | 本次更新 | 仍未完成 |
|---|---|---|
| B04 浏览器链路 | 新增真实电脑 camera、五视图、flag、DB/export 手工验证证据 | 可重复自动 E2E suite、正式 UAT/长时间验收 |
| B05 交付冻结 | 主仓库 runtime 已由其他任务分八个 commit 保存于 dev_cc，当前 HEAD 845b43a | Git ignored 模型产物的受控分发、无本地依赖的 clean-clone 演示 |
| B01/B02 unavailable/零有效权重 | 仍有原数据契约问题；本轮未改代码 | nullable/availability 契约以及全消费者验收 |
| B03 故障与恢复 | camera stop/recover、进程重开历史读取有新证据 | 持久 fault 表、DB 不可用/网络异常/模型异常的完整注入与恢复 |
| B06–B10 模型/评估/性能/UAT | 本轮仅增加诊断，不能视为这些评估全部完成 | 五模型/HPO、E1–E5 规范实验、capture→render p95、日志分母、真实 UAT |
| 新实机识别问题 | 实际 camera 画面持续被 c8 支配，技术链路与识别质量必须分开签署 | 标注正面动作验证、误报率/每类 recall/混淆矩阵及原因确认 |

因此不能把“完整可运行原型”升级成“识别可靠、Week 7 全部验收完成”。当前也未测物理 edge 设备。摄像头配置 30 FPS 不等于 30 FPS 模型推理，界面 round trip 不等于 capture→render p95；本次 40/82 秒检查不是 5–10 分钟稳定性测试。

## 后续建议（未执行）

1. 保持原模型和融合参数，建立短的逐动作标注对照：正常姿势、喝水、打电话、整理头发等；记录 camera 机位/距离/光照、手部可见性和时间段，先验证是否有可区分输入。
2. 对照目标机位与源图片的 framing；分别控制机位/背景/距离，报告结果。不要只靠移动融合阈值把视觉误判隐藏起来。
3. 用正面独立标注集评估原模型，按人划分；记录 safe 误报率、macro-F1、每类 recall、混淆矩阵、置信度分布。没有标注就不报 camera accuracy。
4. 在重新授权模型开发后再决定数据补充/微调；不恢复 EfficientNet 等暂停实验。本轮只完成诊断与文档。

操作与全部参数中文说明见 [10_SYSTEM_PARAMETERS_EXPLAINED.zh.md](10_SYSTEM_PARAMETERS_EXPLAINED.zh.md)。
