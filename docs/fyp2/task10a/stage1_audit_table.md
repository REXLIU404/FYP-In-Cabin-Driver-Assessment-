# Task 10A Stage 1（Candidate Provider Integration）：实现方自审表

- 实现方：Claude（CL-1、CL-2）与 DeepSeek（DS-1）。
- 日期：2026-10-26。
- 提交范围：`2745348..HEAD`（`fyp2/live-system`）。

Stage-1 的提交：

| 提交 | 内容 |
|---|---|
| `871d309` | Task 1.1 配置开关 |
| `09b4b8d` | Task 1.2 加载器 |
| `4ca3c69` | Task 1.3 provider 接线、前端模型名 |
| `90b5e2e` | 假 provider 补上 `model_id` |
| `777cd05` | 合并 DS-1：Task 1.4 stable200 验证 |
| `5edd868` | 合并 DS-0：评审修复，不属于 10A，但在基线里 |

依据：
- 规格 `/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/docs/fyp2/11_SYSTEM_INTEGRATION_STAGE_PLAN_AND_AUDIT.md` 的 Stage 1；
- 计划 `docs/plans/2026-10-25-task-10a-candidate-integration.md` 的 §4 与 §9；
- 改正 `docs/plans/2026-10-26-task-10a-analysis-and-collaboration.zh.md` 的 C-1 至 C-12。

证据目录：`docs/evidence/2026-10-26/task10a-stage1/`，下文简写为 `S1/`，全部为当日运行。

## 1. 规格 Stage 1 审计点

| 审计点 | 实现方的说法 | 证据（当日） | exit |
|---|---|---|---|
| provider 代码已改，并在 `2745348` 之后提交到 live-system | 上表各提交都在 `fyp2/live-system` 上，没有推送 | `git log --oneline 2745348..HEAD` | — |
| 两份 manifest 通过系统 CLI 校验 | 针对**复制后的**真实包运行 `scripts/validate_runtime_manifest.py <manifest> --package-dir <包>`，结果为 `valid` | `S1/manifest-cli-p5_resnet18_search004_seed42_20261023.log`、`S1/manifest-cli-p5_mobilenet_v3_large_search006_seed42_20261023.log` | 0 / 0 |
| 实际 forward 已发生，并与 parity 缓存对比 | ① 三个模型的 provider 新鲜 forward：与 P4A parity 缓存（100 个来源，历史 ORT logits）比较，概率最大差 1.54e-7 至 1.78e-7，argmax 100/100；两个候选与 stable200 的 PyTorch 预测比较，1.48e-6 / 6.87e-6，argmax 200/200。容差为批准的 1e-4（FUD-01）。② 加载器与 provider 的 warm-up 都断言输出为 (1, 10) 且有限。③ 真实包测试 6 条通过。 | `docs/evidence/2026-10-26/stable200/official_stable200_behavior.json`（overall PASS）；`S1/pytest-m-candidates.log`（6 passed） | 0 |
| hash 校验确实在运行（红 / 绿） | 绿：被篡改的包被拒绝，报 `model.sha256 mismatch`，而且不会回退到稳定模型。红：在隔离副本里去掉 sha256 比较，同样两条测试失败 | `S1/tamper-green.log`（7 passed）；`S1/tamper-red-sha-check-removed.log`（2 failed） | 0 / 1 |
| 默认仍是 MN-STABLE | 配置默认值 `active_vision = "stable"`（有测试钉住）；默认启动后 `/api/models` 的 vision 为 `stable_mobilenet_v3_large`、`mobilenetv3_large_vision.onnx`，sha256 `b3a42e8d…`，`source = stable` | `S1/startup-default.json` 与 `.uvicorn.log`（空闲端口、临时库、停止后无残留进程） | — |
| XGB 未被改动 | `git diff 2745348 -- backend/app/providers/trained.py` 共 39 行改动，全部在视觉一侧，涉及遥测或 XGB 的为 0 行（`candidate_name` 这个字符串除外） | `S1/trained_py_diff_vs_2745348.diff`；`S1/SUMMARY.json` 中的 `telemetry_or_xgb_lines: []` | — |

## 2. 规格 Stage 1 交付物

| 交付物 | 实现 | 测试 |
|---|---|---|
| 1. manifest 驱动加载：manifest → 模型路径、SHA256、输入 / logits 契约 | `backend/app/vision_candidates.py`，复用 `validate_package`，并加上 c0..c9、safe_class、preprocess、标签与 warm-up 的检查 | `backend/tests/test_vision_candidates.py`（10 条合成包测试，始终运行） |
| 2. Active 模型开关（默认 stable），切换有版本记录 | `DRA_ACTIVE_VISION`；`/api/models` 返回 `model_id` / `run_id` / `source`；每个窗口记录 `vision_model_id` 与 `vision_model_sha256`；界面显示实际模型名 | `test_the_stable_default_is_unchanged_and_says_so`、`test_live_inference`（`vision_model_id`）、`frontend/src/utils/modelInfo.test.ts` |
| 3. XGB 路径原样保留 | 见上面的 diff | 全量门禁 |
| 4. 加载失败时明确报错，不回退 | hash 不符、schema 不符、类别顺序不符、标签缺 `safe_driving`、warm-up 失败都会抛出 `ModelUnavailable`，进而返回 503；测试里稳定 ONNX 根本不存在 | `test_a_refused_candidate_raises_and_never_falls_back` 等 |
| 5. 测试：hash、c0–c9、forward 与 parity 一致、切换后重复加载 | 见上；切换与回滚由 `test_switching_to_a_candidate_and_back_in_fresh_processes`（`-m candidates`）覆盖，另有两次真实启动的记录 | `S1/pytest-m-candidates.log`、`S1/startup-*.json` |

## 3. 计划的 Gate A–D（本阶段涉及的部分）

| Gate | 状态 | 证据 |
|---|---|---|
| A（产物与 provider） | 满足 | 上面第 1 节 |
| B（stable200） | 满足：三个模型都 PASS | `docs/evidence/2026-10-26/stable200/` |
| C（集成回归） | 满足：在 `777cd05` 上全量门禁全绿，pytest 1115 / 0 skipped / 7 deselected，vitest 972，build、tsc、eslint 都通过 | `docs/evidence/2026-10-26/merge-ds1-gate/` |
| D（失败处理） | 本阶段的部分已满足（篡改、schema、类别顺序、warm-up、无回退）；回滚演练在 Stage 5 | 同上 |

## 4. 偏离计划之处（均记为裁定）

- C-1：测试从 `app.*` 导入，在 `backend/` 下运行。
- C-2：标签由 `training_labels` 加 `runtime_aliases` 生成。
- C-3：稳定模型的参照是 P4A parity。
- C-4：真实包测试打 `candidates` 标记，默认不运行。
- C-5：界面上的模型名从 `/api/models` 读取。
- C-8：provenance 里本来就有 `vision_model_sha256`。
- 计划 Step 3 要求的 provenance 断言放在 `test_live_inference`，没有放在 `test_r10b_payload_contract`，因为后者用的是桩 provider。
- 候选模式下 provider 名为 `VisionCandidateONNX+XGBoost`。
- 证据事故：13:08 另一个会话删掉并覆盖了一个门禁目录。已在 `ba018bb` / `44b93d7` 纠正：干净重跑全绿，标错的目录已移除。

## 5. 未做 / 不声称

- 没有声称候选模型在实时摄像头下更可靠，Stage 1 不涉及。
- 没有做 Stage 2 对比；没有切换默认模型；没有推送。
