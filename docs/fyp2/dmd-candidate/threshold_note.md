# 阈值语义：运行时没有 0.7038 这个阈值（事实说明）

日期：2026-11-02。性质：事实记录，不选择模型、不改代码。

## 运行时实际消费什么

1. 视觉 provider 对 logits 做一次 softmax，直接计算
   `P_distraction = 1 − P(c0)`：
   `backend/app/providers/trained.py:157`（`pd = float(1 - probs[0])`），
   `backend/app/providers/trained.py:187` 写入 `WindowInput`。
2. 推理层把它作为 `P_distraction` 传给融合：
   `backend/app/inference.py:393`、`backend/app/inference.py:479`。
3. 融合层把 `P_distraction` 作为连续概率使用，权重默认 0.5/0.5：
   `backend/app/fusion.py`（`compute_risk_score`）。阈值 30/60 作用在 0–100 的
   **RiskScore** 上（`backend/app/config.py:22-23`），不是视觉概率阈值。

在 `backend/`、`frontend/`、`ai/`、`scripts/` 的非测试代码中检索 `0.7037` / `0.703772`：
**没有命中**。该值只存在于 2026-10-29 的 DMD 证据与本次新增的测试/证据中。

## 0.7038 是什么

`docs/evidence/2026-10-29/dmd-adaptation/selected_threshold.json`：
在 DMD 验证受试者 `gB_10` 上按 FPR ≤ 0.10 选出的二分类阈值。
它用于 2026-10-29 的离线评估表，**没有进入运行时**。

## 因此，与运行时对应的列是 0.5

本次 DMD 测试集（1354 帧）上的重算结果：

| DMD 候选 | 阈值 | recall | FPR | precision |
|---|---|---|---|---|
| 运行时输入的离线二分类诊断 | **0.5** | 0.7881 | **0.2074** | 0.8041 |
| 历史离线列（运行时不用） | 0.7037721940337633 | 0.6344 | 0.0891 | 0.8849 |

- 描述运行时输入时使用 **0.5 列：FPR 0.2074**。
- **不能**把 **0.0891** 说成部署误报率：运行时没有应用这个阈值。
- 0.5 也只是把连续概率二值化的离线诊断约定；运行时本身不做这个二值化。
- 0.7038 是在 `gB_10` 上选的，不是 test；在 test 上它也不保证 10% 的误报预算
  （见 `docs/fyp2/dmd_adaptation_section_draft.md` 的 5.x.4）。

## 相关文件

- 协议：`docs/fyp2/dmd-candidate/protocol.json` → `c_threshold_semantics`
- 重算证据：`docs/evidence/2026-11-02/dmd-candidate/a-source-domain/`
  （`dmd_test/binary_diagnostics.csv` 同时列出两列，`operative = true` 标在 0.5 行）
- 历史：`docs/evidence/2026-10-29/dmd-adaptation/selected_threshold.json`
