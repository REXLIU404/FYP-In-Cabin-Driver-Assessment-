# E. 系统级 E2 / E5（DMD 候选）与 stable 的并列事实（2026-11-02）

**状态**：DMD 的 E2 与 E5-light 均 `PASS`。**stable 的 2026-11-02 E2/E5 结果保留原样，未重跑、未覆盖。**

## 协议与代码

| 项 | 值 |
|---|---|
| 新协议 | `docs/fyp2/dmd-candidate/e2e5_dmd_protocol.json`，commit `4b8506f`（早于本次运行） |
| 旧协议 | `docs/fyp2/e2e5/protocol.json` 未修改；stable 结果仍由它声明 |
| runner | `scripts/fusion_eval.py`，新增 `--protocol`；协议里的 `fixed_runtime.vision_model_id` 选择模型 |
| 代码 commit | `95bdcc4` + 路径修复 `694819f` |
| DMD 运行 | `DRA_ACTIVE_VISION=dmd_adapted_mobilenet_v3_20261029`，由 runner 注入 worker 环境 |
| stable 证据 | `docs/evidence/2026-11-02/e2-weight-sensitivity/`、`e5-light-counterfactual/`（sha256 见文末） |
| DMD 证据 | `e-system-level/e2-dmd/`、`e-system-level/e5-dmd/` |

两边的运行都通过真实 `POST /infer`、临时 SQLite 和注入时钟；不占 8000 端口，不写
`backend/driver_risk.db*`。DMD 的 `GET /api/models` 身份为 `dmd_adapted_mobilenet_v3_20261029`，
sha256 `01f1d6a3…`；telemetry 仍是 stable XGBoost。

## E2：正常输入融合与权重敏感性（60 对构造输入 × 5 组权重）

来源：`e2-dmd/results.json` 与 stable 的 `e2-weight-sensitivity/results.json`。
协议、种子（`20261102`）、60 对输入、5 组权重完全相同；只有视觉模型不同。

| 权重 | stable 与参考一致 /60 | DMD 与参考一致 /60 | stable L/M/H | DMD L/M/H | stable 衰减例 | DMD 衰减例 | stable R14 | DMD R14 |
|---|---|---|---|---|---|---|---|---|
| 0.5 / 0.5 | 59 | 59 | 10/28/22 | 9/26/25 | 28 | 25 | 0 | 0 |
| 0.6 / 0.4 | 59 | 59 | 10/19/31 | 9/20/31 | 19 | 17 | 1 | 1 |
| 0.4 / 0.6 | 60 | 60 | 10/10/40 | 10/10/40 | 10 | 10 | 0 | 0 |
| 0.7 / 0.3 | 59 | 59 | 10/19/31 | 9/20/31 | 18 | 15 | 2 | 1 |
| 0.3 / 0.7 | 59 | 58 | 11/9/40 | 12/8/40 | 10 | 10 | 0 | 0 |

- 两个模型都通过全部 runner 检查：300 个窗口、公式误差 ≤ 0.05（stable max 0.049518，DMD 0.049992）、
  无阈值舍入造成的 level 不一致、level/dominant oracle 0 不一致、跨权重概率一致、
  `all_fresh` / `all_observations_new` / `all_health_full` 均为 true。
- 分支模型与源标签不一致（60 对，按层）：stable 共 3 次视觉（S2/S3/S5 各 1），DMD 共 2 次视觉
  （S1/S2 各 1）；telemetry 两边都是 0。`model_consistent_pairs` stable 57、DMD 58。
  **这不是准确率**：E2 的 60 对是构造样本，不能从这 3 vs 2 推出模型优劣。
- DMD 在 S1（视觉 safe、遥测 Safe）有 1 次视觉分支不一致，导致该层 1 个窗口的 level 从 Low 变为
  Medium；在 0.5/0.5 下总 level 分布变化为 Low 10→9、Medium 28→26、High 22→25。
- 事后（非预声明）的阈值舍入检查：DMD 在 0.6/0.4 下有 2 对由 1 位小数舍入决定 level
  （S4-01、S4-07）；runner 把它列在 `post_hoc_not_predeclared`，不作为预先声明指标。

## E5-light：`viva_compact` 构造场景的分支反事实

来源：`e5-dmd/results.json` 与 stable 的 `e5-light-counterfactual/results.json`。
场景、种子、段顺序/时长完全相同（`scenarios` 逐项相同）；FUSED 为默认 0.5/0.5。

| 段（参考） | stable FUSED score mean / max | DMD FUSED score mean / max | stable levels | DMD levels | stable 一致 /窗 | DMD 一致 /窗 | stable lag (ms) | DMD lag (ms) | Alert max (stable/DMD) |
|---|---|---|---|---|---|---|---|---|---|
| 0 Baseline (REF_LOW) | 0.0 / 0.0 | 3.228 / 11.0 | Low 100 | Low 100 | 100/100 | 100/100 | 0 | 0 | NORMAL / NORMAL |
| 1 Telemetry only (REF_ELEVATED) | 50.0 / 50.0 | 54.125 / 60.9 | Medium 40 | Medium 38, High 2 | 40/40 | 40/40 | 0 | 0 | CAUTION / CAUTION |
| 2 Telemetry wavers (REF_LOW) | 0.0 / 0.0 | 4.6 / 11.0 | Low 40 | Low 40 | 40/40 | 40/40 | 0 | 0 | CAUTION / CAUTION |
| 3 Telemetry only (REF_ELEVATED) | 50.0 / 50.0 | 54.565 / 60.9 | Medium 40 | Medium 38, High 2 | 40/40 | 40/40 | 0 | 0 | CAUTION / CAUTION |
| 4 Vision only (REF_ELEVATED) | 47.496 / 50.0 | 47.564 / 49.8 | Low 4, Medium 96 | Low 2, Medium 98 | 96/100 | 98/100 | 400 | 200 | CAUTION / CAUTION |
| 5 Both (REF_HIGH) | 93.076 / 99.0 | 99.356 / 99.8 | High 100 | High 100 | 100/100 | 100/100 | 0 | 0 | HIGH_ALERT / HIGH_ALERT |
| 6 Recovery (REF_LOW) | 1.087 / 31.5 | 3.794 / 32.5 | Low 178, Medium 2 | Low 178, Medium 2 | 178/180 | 178/180 | 200 | 200 | CAUTION / CAUTION |

- **DMD 在纯 `c0` 段也有非零 P_distraction**：Baseline 0.0641、Telemetry-only 0.0833 / 0.0916、
  Recovery 0.0752（stable 均约为 0.0）。这是 DMD 候选把部分 State Farm `c0` 帧判为分心的直接结果；
  在 Telemetry-only 段，stable 的 fused score 恰好 50.0，而 DMD 的 score 被抬到 54–60.9，
  其中 2/40 个窗口进入 High。该段参考允许 Medium/High，所以 `agrees` 仍是 40/40。
- Vision-only 段：DMD 的一致窗口 98/100、lag 200 ms；stable 为 96/100、lag 400 ms。
  两边的 Alert max 都是 CAUTION。
- Both 段：两边都是 High 100/100、HIGH_ALERT；DMD 的 score 更高（mean 99.356 vs 93.076）。
- VISION_HELD_SAFE / TELEMETRY_HELD_SAFE 的完整逐段结果在 `e5-dmd/results.json`；
  两模型的分支贡献量级相同（vision 最大贡献约 48.6–50.0，telemetry 约 50.0）。
- 两个模型都 PASS：`unchanged_segment_identity` 全部一致，所有窗口 `assessment_available`。

## 能证明 / 不能证明

**能证明（仅限构造场景）**

- 在 E2 的 60 对构造输入上，两个模型通过同一条真实融合管线；参考一致数、level 分布、
  衰减例与分支不一致已并列记录。
- 在 `viva_compact` 构造场景上，DMD 候选在纯 `c0` 段产生少量非零 P_distraction，
  使 fused score 比 stable 高约 3–5 分；vision-only 段的一致窗口更多、lag 更短；
  Both 段的 score 更高；Alert max 没有变化。
- 这些都是描述性差异，不是准确率或安全收益。

**不能证明**

- 不能证明真实多模态驾驶风险准确率；没有同步风险真值。
- E2 的 60 对是构造样本，不能当作模型准确率；分支不一致 2 vs 3 不构成优劣结论。
- 不能从这些构造场景推断 DMD body 视角或正面摄像头的真实表现；c8/c9 的退化没有在这些段中被充分覆盖。
- 不能选权重或阈值；本协议是 `DESCRIPTIVE_ONLY`，stable 结果未重跑。

## stable 证据未改动（sha256）

| 文件 | sha256 |
|---|---|
| `e2-weight-sensitivity/results.json` | `fda4c80faf8c08b616b696dacf3c65b1229e3dcad3b180018227a05df811c69b` |
| `e5-light-counterfactual/results.json` | `627e8ef49d22740d9f7f3906e9b2e26de1dc1819c8bfaa1e1d9efd1e33e88b74` |
| `e-system-level/e2-dmd/results.json` | `f62b9265d4823339b0806bf0f0f57a69cf91fc01d63a6ad36c2d17dfae984469` |
| `e-system-level/e5-dmd/results.json` | `f19337dbad9df38089894c270f2398a7fd27e74b44ac72ad6d1df4420a1ebd74` |

## 文件

| 文件 | 内容 |
|---|---|
| `e2-dmd/results.json` / `e2_rows.csv` / `pairs.json` | E2 的 DMD 结果、逐窗行、60 对输入 |
| `e5-dmd/results.json` / `e5_windows.csv` | E5 的 DMD 结果、逐窗行 |
| `e2-dmd/figures/`、`e5-dmd/figures/`（如生成） | runner 的图 |
| `tests-GREEN.log` | `backend/tests/test_fusion_eval.py`，31 passed |
