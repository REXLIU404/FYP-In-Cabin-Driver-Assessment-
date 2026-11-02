# DMD 候选在役资格证据：总索引（2026-11-02）

本目录回答：`dmd_adapted_mobilenet_v3_20261029` 是否具备作为系统在役视觉模型的证据基础。
**没有切换在役模型**；所有结果均为描述性，最终由用户决定。

- 先行协议：`docs/fyp2/dmd-candidate/protocol.json`（commit `a198a15`）
- 系统级补充协议：`docs/fyp2/dmd-candidate/e2e5_dmd_protocol.json`（commit `4b8506f`）
- 事实汇总：`docs/fyp2/dmd-candidate/decision_facts.md`
- 阈值语义：`docs/fyp2/dmd-candidate/threshold_note.md`
- 摄像头清单（用户执行）：`docs/fyp2/dmd-candidate/camera_check_checklist.md`

## 项目状态

| 项 | 状态 | 证据 | 一句话结果 |
|---|---|---|---|
| A. State Farm + DMD 重算 | `PASS_WITH_WARNINGS` | `a-source-domain/` | State Farm acc 0.8988→0.8091；DMD acc 0.2777→0.7171；c8/c9 大幅退化 |
| B. 运行时兼容性 | `PASS` | `b-runtime-compat/` | manifest valid；200 图 max Δp 1.192e-06，argmax 1.0 |
| C. 阈值语义 | 文档 | `docs/fyp2/dmd-candidate/threshold_note.md` | 运行时用连续 P_distraction；0.5 列 FPR 0.2074，0.7038 列不在路径上 |
| D. 性能 | `PASS`（归档校验 6/6） | `d-perf/` | p95 30–45 ms 交替，Server vision 中位数约 8.6–9.4 ms |
| E. 系统级 E2/E5（DMD） | `PASS`（E2、E5） | `e-system-level/` | E2 59/60 vs 59/60；E5 纯 c0 段 DMD Pd 0.0641，score 略高 |
| F. 实时摄像头 | `NOT_RUN`（用户执行） | `f-camera-check/` | 脚本与清单已准备；没有打开摄像头 |
| 门禁 | `GREEN` | `docs/evidence/2026-11-02/dmd-candidate-gates/` | 5/5 PASS；pytest 1438 passed, 12 skipped（DMD torch，单独 12 passed）, 11 deselected；ml/tests 302 passed |

## 核心数字（本数据集上）

| | stable | DMD 候选 |
|---|---|---|
| State Farm test accuracy | 0.8988 | 0.8091 |
| State Farm test macro-F1 | 0.8746 | 0.7266 |
| State Farm c0→分心（0.5） | 0.0905 | 0.0487 |
| State Farm c8 recall | 0.8321 | 0.0679 |
| State Farm c9 recall | 0.2733 | 0.0643 |
| DMD test accuracy | 0.2777 | 0.7171 |
| DMD test macro-F1 | 0.3105 | 0.5065 |
| DMD test FPR @0.5（运行时等价列） | 0.8157 | 0.2074 |
| DMD test c0 recall | 0.1951 | 0.8863 |
| DMD test c8 recall | 0.8154 | 0.0154 |
| DMD test c9 recall | 0.5167 | 0.0000 |
| capture→render p95 (3 轮) | 45 / 36 / 35 ms | 30 / 36 / 39 ms |
| Server vision median (3 轮) | 8.645 / 8.88 / 9.41 ms | 9.23 / 9.345 / 9.095 ms |

## 必须先读的事实

1. **输入与模型身份**：`a-source-domain/identity_check.json` 显示 State Farm 冻结清单
   （`098001f1…`）、DMD manifest（`527f714b…`）与两个 ONNX 的 sha256 都与协议一致。
2. **阈值**：运行时直接融合 `P_distraction = 1 − P(safe_driving)`，没有 0.7038 阈值。
   DMD 测试集上对应运行时的是 **0.5 列，FPR 0.2074**；0.0891 属于历史离线列。
3. **c8/c9**：两个数据集上都大幅退化（State Farm c8 0.8321→0.0679、c9 0.2733→0.0643；
   DMD c8 0.8154→0.0154、c9 0.5167→0.0000）。macro-F1 的整体变化不能替代逐类报告。
4. **State Farm 交叉核对**：stable 重算与 p4b 的 accuracy/macro-F1/混淆矩阵一致；log loss 差
   5.815e-9，超过协议写下的 1e-9，因此 A 项记 `PASS_WITH_WARNINGS`，没有隐藏。
5. **性能**：六轮交替；机器负载高于 2026-10-30 stage3，绝对毫秒数不要跨日比较；
   两模型没有稳定的方向性差异。
6. **E2/E5**：构造场景，不是准确率测试；stable 的 2026-11-02 结果未重跑、未覆盖。
7. **摄像头**：F 未运行；不要把它当作已有结果。

## 用户还需要亲自做的事

按 `docs/fyp2/dmd-candidate/camera_check_checklist.md`：

1. 启动 stable 后端 → 运行 `scripts/camera_ab_check.py --label stable` → 正常坐姿/拿手机/喝水各 60 秒；
2. 用 `DRA_ACTIVE_VISION=dmd_adapted_mobilenet_v3_20261029` 重启后端 → 运行 `--label dmd` → 同样三个动作；
3. 运行 `--compare` 生成 `comparison.json`，把 `stable.json`、`dmd.json`、`comparison.json`
   放进 `f-camera-check/`。

## 复现命令

```bash
# A
.venv/bin/python scripts/dmd_candidate_eval.py --out docs/evidence/2026-11-02/dmd-candidate/a-source-domain
# B
.venv/bin/python scripts/dmd_candidate_runtime_check.py --out docs/evidence/2026-11-02/dmd-candidate/b-runtime-compat
# D（六轮）
for round in 1 2 3; do
  for model in stable dmd; do
    .venv/bin/python scripts/perf01.py --windows 600 --warmup 20 --active-vision <stable|dmd_adapted_mobilenet_v3_20261029> \
      --out docs/evidence/2026-11-02/dmd-candidate/d-perf/<model>-r${round}
  done
done
.venv/bin/python scripts/dmd_candidate_perf_archive.py --root docs/evidence/2026-11-02/dmd-candidate/d-perf
# E
.venv/bin/python scripts/fusion_eval.py e2 --protocol docs/fyp2/dmd-candidate/e2e5_dmd_protocol.json \
  --out docs/evidence/2026-11-02/dmd-candidate/e-system-level/e2-dmd
.venv/bin/python scripts/fusion_eval.py e5 --protocol docs/fyp2/dmd-candidate/e2e5_dmd_protocol.json \
  --out docs/evidence/2026-11-02/dmd-candidate/e-system-level/e5-dmd
# F（用户本人）
.venv/bin/python scripts/camera_ab_check.py --label stable --out docs/evidence/2026-11-02/dmd-candidate/f-camera-check/stable.json
```

## 门禁结果（2026-11-02）

`DRA_REQUIRE_MODELS=1 python3 scripts/run_gates.py --out docs/evidence/2026-11-02/dmd-candidate-gates`

- build / pytest / vitest / tsc / eslint **全部 PASS**（`dmd-candidate-gates/SUMMARY.md`）；
- pytest：**1438 passed, 12 skipped, 11 deselected**；没有模型缺失导致的 skip
  （`DRA_REQUIRE_MODELS=1: no model-dependent test was skipped.`）；
- 12 skipped 是 `DRA_DMD_TORCH=1` 门控的 DMD torch 测试，单独跑 **12 passed**
  （`dmd-candidate-gates/dmd-torch-tests.log`）；
- `ml/tests`：**302 passed**（`dmd-candidate-gates/ml-tests.log`）；
- 11 deselected 是 `long` / `candidates` 标记；真实候选包的 runtime 检查在 B 项用
  `-m candidates` 单独跑过（`b-runtime-compat/tests-candidates-GREEN.log`）；
- 门禁运行时的 dirty entries 是未跟踪的报告/计划/证据文档，不是代码改动；详见
  `dmd-candidate-gates/GATES_NOTE.md`。

## 约束核对

- 未修改 `DRA_ACTIVE_VISION` 默认值、`config.py` 默认值、`release_decision.md` 或报告 docx；
- 候选包 `evaluation_metrics.json` 仍为 `{}`，未原地修改；
- 未提交模型权重、DMD 帧、State Farm 图片或 constructed bundle；
- 未 push、未合并到其他分支、未占用 8000 端口、未写 `backend/driver_risk.db*`；
- 未改写已提交的 `docs/fyp2/e2e5/protocol.json` 或 `docs/fyp2/dmd-candidate/protocol.json`。
