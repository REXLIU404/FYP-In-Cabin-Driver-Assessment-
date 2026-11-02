内部彩排记录，不是评估结果，报告与答辩 不引用。

# Constructed scenario rehearsal — viva_v1（内部工程记录）

`viva_v1-rehearsal.json` 是 `backend/tests/test_constructed_scenario_rehearsal.py`（`-m long`）把
viva_v1 在浏览器里完整播放一次后写出的**工程检查记录**。它验证演示模式的机制：7 段都出现、
剧本结束后自动停止、零故障。里面的命中率、RiskLevel 计数、AlertSeverity 序列都是**如实记录**，
**不是评估结果**：报告结果只来自 Live 运行（设计文档 D06）。

## 本次运行

- 命令：`DRA_REQUIRE_MODELS=1 DRA_E2E_EVIDENCE_DIR=<本目录> .venv/bin/python -m pytest backend/tests/test_constructed_scenario_rehearsal.py -m long -q`
- 结果：1 passed（149 s）；7 段全部出现、每段 distinct frames 与 manifest 帧数一致；剧本结束后停止、无 stop panel；fault_events = 0；无 console / page 错误。
- 会话：`S4892a94caeee4a84b3da95083cb22872`（临时数据库，运行即弃）。
- 窗口数：收到 1341，服务端 total 1341（一致）。
- 模型：默认 stable MobileNetV3 / XGBoost（本工作区链接的三个稳定模型文件）。

## 文件

- `viva_v1-rehearsal.json` — 测试写入的逐段报告（窗口数、distinct frames、各模态「真实 vs 模型」一致率、RiskLevel 计数、AlertSeverity 变化序列）。所有数字由存储记录与 bundle manifest 计算，未编造。
