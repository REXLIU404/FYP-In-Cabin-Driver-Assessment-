# 解释模块实现指南（Vision + Telemetry）

本文档说明本项目在没有文字模型的情况下，如何实现可解释性（explanation）。当前系统的模型输入不是自然语言，而是两个结构化分支：

- 视觉分支：MobileNetV3 或未来视觉模型输出 `P_distraction` 和 `visual_top_classes`。
- 车辆遥测分支：XGBoost 或未来表格模型基于 vehicle-dynamics features 输出 `P(Safe)`、`P(Aggressive)`、`P(Distracted)`。为保持 dashboard contract 稳定，系统继续使用字段名 `P_telemetry_anomaly`，但当前定义为 `1 - P(Safe)`。

因此，解释模块不需要 LLM 或文本分类器。它应该基于模型已经产生的数值证据，生成可审计、可复现的说明。

## 1. 前端 MVP 当前实现方式

前端现在使用 `ai/prototype-data/prepared_sessions/session_001` 中的 prepared monitoring session 作为输入源。系统按 window 顺序读取 prepared frames 与 telemetry records，并在前端 MVP 中用 deterministic prototype inference 生成与后续后端一致的结构化输出。每个窗口包含：

- `P_distraction`：驾驶员分心概率，范围 0-1。
- `P_telemetry_anomaly`：telemetry non-safe behaviour probability，范围 0-1，计算为 `1 - P(Safe)`。
- `visual_top_classes`：视觉分类概率，例如 `safe_driving`、`texting_right`、`phone_right`、`operating_radio`、`drinking`、`reaching_behind`、`talking_to_passenger`。
- `telemetry_features`：`speed_kmph`、`accel_x`、`accel_y`、`brake_pressure`、`steering_angle`、`throttle`、`lane_deviation`、`headway_distance`。
- `modality_freshness`：视觉和遥测分支是 `fresh`、`stale` 还是 `missing`。
- `RiskScore`：融合后的风险分数，前端展示为 0-100。
- `latency_ms`：当前窗口推理或模拟推理延迟。

`ai/src/riskLogic.ts` 仍保留 `buildExplanation()` 作为 session log 兼容字段。当前 UI 的 Explanation 页面优先使用结构化字段和 rule-based badges，不依赖大段自然语言文本。`DominantEvidence` 判断当前风险主要来自哪个分支：

- `Vision-dominant`：视觉分心概率明显高于遥测异常概率。
- `Telemetry-dominant`：遥测异常概率明显高于视觉分心概率。
- `Combined evidence`：两个分支都对风险有贡献。
- `Partial evidence`：其中一个分支缺失，只能基于部分证据判断。
- `Low observed risk`：两个分支概率都低。

## 2. 为什么不能用“word explanation”思路

如果模型是 NLP 模型，解释可能来自关键词、高亮 token 或文本 attention。但本系统不是文字输入：

- 视觉模型处理的是图像帧。
- 遥测模型处理的是数值表格特征。
- 融合层处理的是两个分支的概率输出。

所以解释应回答的是“哪个模态推动了风险”和“哪些结构化证据支持这个判断”，而不是解释某个单词。

## 3. 推荐的 FYP2 解释数据结构

后端 AI 层可以返回一个结构化 `explanation` 对象，而不是只返回一段字符串：

```json
{
  "text": "Vision-dominant: texting_right probability is high and telemetry non-safe behaviour probability is moderate.",
  "dominant_evidence": "Vision-dominant",
  "risk_score": 72.4,
  "vision": {
    "p_distraction": 0.81,
    "top_classes": [
      { "label": "texting_right", "probability": 0.54 },
      { "label": "phone_right", "probability": 0.22 }
    ]
  },
  "telemetry": {
    "p_telemetry_anomaly": 0.28,
    "current_behaviour": "Safe",
    "behaviour_score": 0.72,
    "telemetry_feature_contributions": []
  },
  "freshness": {
    "vision": "fresh",
    "telemetry": "fresh"
  },
  "latency_ms": 47
}
```

后端模型可以保留完整 class probability vector 用于计算 `P_telemetry_anomaly`，但解释 payload 和 Evidence Card 优先展示当前 top behaviour 和 score。

## 4. 视觉分支解释怎么做

MVP 阶段使用 `visual_top_classes` 作为解释证据。FYP2 接入真实 MobileNetV3 后，建议保留同样的数据字段：

1. 取 softmax 输出中概率最高的 3-5 个类别。
2. 使用 `P_distraction = 1 - P(safe_driving)`，或等价地累加所有非 `safe_driving` 类别概率，作为分心风险概率。
3. 如果 `texting_right`、`phone_right`、`operating_radio`、`drinking`、`reaching_behind`、`talking_to_passenger` 等类别概率高，就在解释文本中说明视觉分支推动风险。
4. 可选增强：使用 Grad-CAM 生成热力图，帮助说明视觉模型关注的图像区域。

注意：Grad-CAM 是可选项，不应成为 MVP 的必需功能。当前 dashboard 只需要 top class probabilities 就能解释视觉分支的主要证据。

## 5. 遥测分支解释怎么做

MVP 阶段使用 prepared behaviour probabilities 来模拟 telemetry model 输出。FYP2 接入真实 XGBoost 后，建议改为以下方式：

1. 用 XGBoost 输出 `P(Safe)`、`P(Aggressive)`、`P(Distracted)`。
2. 使用 `P_telemetry_anomaly = 1 - P(Safe)` 作为 telemetry branch 的 non-safe behaviour risk。
3. 前端 Telemetry Evidence Card 显示当前 predicted behaviour、behaviour score、`P_telemetry_anomaly`，以及可选的 SHAP / feature contribution signals。
4. Feature contribution 不等同于模型预测出的 behaviour；它只解释哪些输入特征推动了当前 behaviour 或 non-safe score。
5. 不在 Evidence Card 里展示手工定义的 high-speed / hard-brake cue，因为这些不是模型直接识别出的行为类别。
6. 如果后续需要解释输入特征贡献，再额外使用 SHAP TreeExplainer；当前 MVP 可以用 prepared attribution fixture 占位。

因此当前 Telemetry Evidence Card 可以分成两层：

- Model output：当前是什么 telemetry behaviour，以及这个 behaviour 的 probability score。
- Model attribution：哪些 telemetry input features 对当前输出贡献最大。

后期可选的 SHAP result signals 可以来自 8 个 telemetry 输入特征，但它们应作为“为什么模型倾向于这个 behaviour”的 attribution，而不是当前 behaviour 本身：

| SHAP signal | 解释含义 |
|---|---|
| `speed_kmph` | 当前速度特征对 non-safe / selected behaviour probability 的正负贡献 |
| `accel_x` | 纵向加速度对 selected behaviour probability 的贡献 |
| `accel_y` | 横向加速度对 selected behaviour probability 的贡献 |
| `brake_pressure` | 制动压力对 selected behaviour probability 的贡献 |
| `steering_angle` | 方向盘角度对 selected behaviour probability 的贡献 |
| `throttle` | 油门输入对 selected behaviour probability 的贡献 |
| `lane_deviation` | 车道偏移对 selected behaviour probability 的贡献 |
| `headway_distance` | 跟车距离对 selected behaviour probability 的贡献 |

例如后期 payload 可以是：

```json
{
  "predicted_behaviour": "Aggressive",
  "behaviour_score": 0.72,
  "p_telemetry_anomaly": 0.82,
  "telemetry_feature_contributions": [
    { "feature": "brake_pressure", "contribution": 0.18 },
    { "feature": "throttle", "contribution": 0.14 },
    { "feature": "headway_distance", "contribution": 0.09 }
  ]
}
```

这里的 `telemetry_feature_contributions` 只说明 feature 对模型输出的贡献方向和强度，不应被写成固定规则，例如“速度高所以一定 aggressive”。

## 6. 融合层解释怎么做

融合层解释应基于配置权重和分支概率：

```text
vision_contribution = P_distraction * weight_vision * 100
telemetry_contribution = P_telemetry_anomaly * weight_telemetry * 100
RiskScore = normalized_sum(vision_contribution, telemetry_contribution)
```

如果两个分支都 fresh，解释可以比较两个 contribution。  
如果某个分支 stale 或 missing，解释必须说明当前风险是 partial evidence，并降低系统健康状态为 `DEGRADED` 或 `UNAVAILABLE`。

## 7. Combined Evidence 页面展示建议

Explanation 页面不要依赖大段自然语言解释，建议改为可审计的结构化解释：

- 顶部 `Dominant Evidence` 卡：显示 `COMBINED EVIDENCE`、Vision 分数、Telemetry 分数、`RiskScore`、`RiskLevel`、`AlertStatus` 和 freshness。
- 中间两张 evidence cards：分别显示 `P_distraction`、primary distraction cue、vision freshness、vision contribution，以及 telemetry predicted behaviour、behaviour score、`P_telemetry_anomaly`、feature contribution、telemetry freshness、telemetry contribution。
- 下方 `Contribution Breakdown`：用 stacked bar 展示 `Vision contribution + Telemetry contribution = RiskScore / 100`。
- 右侧 `Evidence Mapping Rule`：用 rule badges 展示 `Vision-dominant`、`Telemetry-dominant`、`Combined`、`Partial`、`Low observed risk`。

Combined evidence 的核心规则是：两个模态都 active，并且 `|P_distraction - P_telemetry_anomaly| < 0.15`。这种解释是 rule-based，不需要假装模型能生成完整自然语言理由。

## 8. 实施步骤

1. 保持当前 `RiskUpdate` 合约，先用字符串 `explanation` 支撑 MVP 演示。
2. 在 FYP2 后端新增 `explanation_payload`，包含 visual、telemetry、freshness、latency。
3. 视觉模型接入后，把 MobileNetV3 softmax top classes 写入 `visual_top_classes`。
4. 遥测模型接入后，可选把 XGBoost SHAP top features 写入 `telemetry_feature_contributions`；Evidence Card 同时展示当前 behaviour/score 和 top feature contributions。
5. 前端 Explanation 页面优先读取结构化 payload；如果没有，就回退到当前字符串 explanation。
6. 保持 RiskScore 展示为 0-100，概率字段仍保留 0-1，避免混淆模型概率和最终风险分数。
