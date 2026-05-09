# 系统解释文稿

## 1. 系统目标

本系统是一个 in-cabin driver risk assessment prototype，目标是在监控过程中把驾驶员视觉状态和车辆遥测状态结合起来，输出一个可解释的风险判断。系统关注的不是单一模型结果，而是多模态风险评估流程。

## 2. 输入来源

当前 prototype 使用 `prepared_sessions/session_001` 作为 Prepared Session Dataset。这个 folder 提供一组已经准备好的 visual frames、telemetry records、timestamps 和 missing/stale cases。

它不是随机模拟输出，而是用于复现一段固定的 monitoring session，让系统可以按 window 顺序读取输入，稳定验证 runtime pipeline。

## 3. Runtime Pipeline

系统运行流程是：

```text
Prepared session folder
-> Input Source Adapter
-> Monitoring window construction
-> Prototype inference contract
-> Late fusion
-> RiskScore / RiskLevel
-> Dashboard + Session Log
```

在 FYP1 前端 MVP 中，`Input Source Adapter` 会读取 `telemetry.csv`，按 timestamp 构建 monitoring windows。后续 FYP2 接入后端时，这一层可以替换成真实 FastAPI / WebSocket input source，而 dashboard contract 不需要大改。

## 4. Risk Fusion Logic

每个 window 会生成两个 branch-level probability：

- `P_distraction`：视觉分支估计驾驶员分心概率。
- `P_telemetry_anomaly`：遥测分支估计车辆行为异常概率。

系统使用 weighted late fusion：

```text
RiskScore = weighted(P_distraction, P_telemetry_anomaly) x 100
```

然后根据 threshold 映射为 `Low`、`Medium` 或 `High`，同时生成 `SystemHealth`、`AlertSeverity` 和 evidence type。

## 5. Evidence Interpretation

`Enable Evidence Interpretation` 控制导出内容是否包含解释字段。

启用时，JSON / CSV 会包含：

```json
{
  "window_id": 96,
  "risk_score": 11.7,
  "risk_level": "Low",
  "p_distraction": 0.11,
  "p_telemetry_anomaly": 0.12,
  "dominant_evidence": "combined",
  "top_visual_class": "normal_driving",
  "top_telemetry_cue": "speed",
  "latency_ms": 42
}
```

关闭时，只导出最小风险记录：

```json
{
  "window_id": 96,
  "risk_score": 11.7,
  "risk_level": "Low"
}
```

这个设计的意义是：系统既可以输出完整的可解释 session log，也可以输出简洁的 risk-only result，适合不同评估场景。

## 6. Demo 讲法

展示时可以这样解释：

“这个 prototype 使用 prepared session dataset 来模拟一段监控过程。系统每隔 delta t 自动构建一个 monitoring window，然后计算视觉分心概率和遥测异常概率。两个分支结果进入 late fusion，生成 RiskScore 和 RiskLevel。Dashboard 展示实时状态，Signal Inspector 用于回看历史窗口，Risk Trends 用于观察整段 session 的风险变化。Configuration 只保留 runtime 参数和导出选项，不强调 demo mode 或 uploaded video，因为当前系统没有视频上传推理功能。”
