# TELEMETRY-CONTRIBUTIONS 技术报告：Live 模式的遥测特征贡献（TreeSHAP，解释非安全风险）

- 分支 `fyp2/live-system`，工作树 `/Users/liu/Desktop/FYP2-Live-System`，开工 HEAD `84a1891`（与任务要求一致；开工时未跟踪文件只有用户开发库的 `backend/driver_risk.db-shm` / `-wal`，未触碰、未提交）。
- 日期 2026-10-22。角色：实现者。未派发子 agent。
- 本报告关于贡献的统一说法：**TreeSHAP 局部归因，作用于 Safe 类打分（取负号，正号推向不安全），单位为 log-odds，不代表因果，也不是数据集层面的特征重要性。**

## 1. 任务编号与名称

TELEMETRY-CONTRIBUTIONS：Live 模式的遥测特征贡献。`TrainedProvider` 用 XGBoost 自带的 TreeSHAP（`Booster.predict(..., pred_contribs=True)`）算出 `telemetry_feature_contributions`，解释的是参与融合的非安全风险 `P_telemetry_anomaly = 1 − P(Safe)`（用户 2026-10-22 裁定的方案 A）。Explanation 视图 Telemetry Evidence 卡片上长期显示 `unavailable` 的「Feature Contribution」由此有了真实数据。

根因（控制者已查明，我复核过）：`telemetry_feature_contributions` 只有 `MockAIProvider`（legacy replay）会填，值是 FYP1 手写的表 `preparedTelemetryFeatureContributions`；Live 用的 `TrainedProvider` 从未设置过它，一直是默认空列表。

## 2. 实现状态

| 简报条目 | 状态 |
|---|---|
| 1. 后端：`TrainedProvider` 用与概率预测相同的 `iteration_range` 调 `pred_contribs=True`，取 Safe 类（下标 0）一行，每个特征 = −SHAP，bias 不算特征，8 项按模型特征顺序 | 完成（4.1） |
| 1. provenance 增加 `telemetry_contribution_method = "xgboost_treeshap_neg_safe_margin"` 与 `telemetry_contribution_baseline = −(Safe 类 bias)`，Σ 贡献 + baseline = −margin_Safe | 完成（4.1；23 行实测最坏误差 1.9e-6，测试容差 1e-4） |
| 1. 无遥测 / 过期 / 计为缺失的窗口，贡献的规则与 `telemetry_behavior_classes` 一致，先读代码确认并写明 | 完成：规则已读代码确认并逐条测试（4.2）。**注意：简报 C-M4 把「过期窗口仍带贡献」当作错误，但现有代码对 classes 的规则恰恰是过期窗口保留（按「as recorded」），我按简报的明文指令「照着 classes 做」，详见 4.2 与第 7 节** |
| 1. `pred_contribs` 失败归到与遥测推理失败相同的类别（`ModelRuntimeError`，origin 为遥测模型） | 完成（4.1；4 条新增参数化用例） |
| 2. R10：贡献登记进观测注册表（`OBSERVATION_REGISTRY_KEYS`），REPEAT 窗口使用登记时的贡献 | 完成（4.3） |
| 3. 前端：按绝对值显示前 3 个特征、带正负号；带 method 的记录标注「非安全风险 / log-odds / TreeSHAP 局部归因 / 不代表因果」；legacy 记录不显示 | 完成（4.4） |
| 3. 所有提到贡献方向的解释文字，正负号含义与「正号推向不安全」一致 | 完成：全仓搜索后，只有本次新增的标注一处提到方向，没有别的文案要改（4.4） |
| 4. 后端测试（带 `requires_models`）：23 行字面量相等、8 项等式、第 1 行符号字面量、契约、REPEAT | 完成（4.5） |
| 4. 夹具与生成脚本：贡献与 baseline 加进 `telemetry_pt_by_row.json`；脚本自己调 `pred_contribs`；`--check` 也核对贡献；模型哈希不变 | 完成（4.5） |
| 4. vitest：带 method 显示前 3 与标注；legacy 不显示；格式与符号 | 完成（+8） |
| 4. 端到端：五方对账自动覆盖新字段；另在一条 Live e2e 断言卡片显示的前 3 个特征及数值等于记录里绝对值最大的 3 项 | 完成：`test_live_e2e.py::test_06`；并把 ST-BRANCH-T / -V 对贡献的检查加进去（4.5） |
| 4. 性能：写明 `/infer` 增加的耗时 | 完成（4.6） |
| 变异 C-M1 … C-M7，每项在隔离副本里有一条明确变红的测试 | 完成，全部变红，每次还原后副本 `git status` 干净（4.7）。C-M7 并不等价（模型有 121 轮、`best_iteration` = 90），已按原样跑 |

## 3. 创建 / 修改的文件

提交内共 14 个文件（本报告 + 13 个）。

| 文件 | 性质 |
|---|---|
| `backend/app/providers/trained.py` | 修改：常量 `CONTRIBUTION_METHOD`；`infer()` 里在概率预测之后用同一个 `DMatrix`、同一个 `iteration_range` 再调一次 `pred_contribs=True`，取 Safe 行取负；形状 / 有限性校验；provenance 两个键（+27 / −0） |
| `backend/app/inference.py` | 修改（只限 REPEAT 与注册表）：`OBSERVATION_REGISTRY_KEYS` 加 `obs_t_contribs`；NEW 观测登记；REPEAT 使用登记值（+14 / −3，其中大半是注释） |
| `backend/tests/test_telemetry_contributions.py` | 新建：8 个测试（5 个 `requires_models` + 3 个 stub 经真实路由） |
| `backend/tests/fixtures/make_telemetry_pt_fixture.py` | 修改：独立计算贡献与 baseline；生成时自查可加性；`--cross-check-provider` 也比对贡献 / baseline |
| `backend/tests/fixtures/telemetry_pt_by_row.json` | 重新生成：每个有遥测的行多 `feature_contributions`（特征 → 值，模型顺序）与 `contribution_baseline`，无遥测的行为 `null`；模型 SHA-256 `9802cb06…ec07` 不变 |
| `backend/tests/test_fault_events.py` | 修改：替身 `FakeBooster.predict` 接受 `pred_contribs`（否则 Provider 调第二次就会 `TypeError`）；新增 4 条参数化用例（`pred_contribs` 抛错 / NaN / Inf / 形状不对） |
| `backend/tests/test_r10_fsm.py` | 修改：注册表键的字面量元组加 `obs_t_contribs`（1 行） |
| `backend/tests/test_live_e2e.py` | 修改：`test_06` 增加 Explanation 卡片断言 |
| `backend/tests/test_live_single_branch.py` | 修改：`Frozen.contributions(row)`；ST-BRANCH-T 两处核对每个窗口（NEW 与 REPEAT）的贡献等于冻结行，ST-BRANCH-V 核对无遥测窗口的贡献为 `[]` |
| `ai/src/types.ts` | 修改（仅类型）：`RiskUpdate.provenance` 加两个可选字段 `telemetry_contribution_method` / `telemetry_contribution_baseline` |
| `frontend/src/views/ExplanationView.tsx` | 修改：带 method 的记录在贡献列表下显示一行标注（+17） |
| `frontend/src/views/featureContributionRender.test.ts` | 新建：8 个 vitest 用例 |
| `prototype-tests/live_e2e.md` | 修改：第 4 行补一句 Explanation 卡片的验收标准 |
| `docs/fyp2/implementation/telemetry-contributions.md` | 新建：本报告 |

未触碰：融合 / FSM / EMA / 阈值（`fusion.py`、`alertFsm.ts`、`riskLogic.ts`）、三个模型文件、`docs/fyp2/review/`、计划文件、legacy replay 的手写贡献表（`preparedSessionInput.ts`）、主仓库、8000 端口上的开发后端和开发库。

## 4. 实现摘要

### 4.1 后端：`TrainedProvider` 计算贡献

```python
matrix = DMatrix(...)                                   # 与概率预测共用
probs  = predict(matrix, iteration_range=(0, iteration_end))[0]
shap   = predict(matrix, iteration_range=(0, iteration_end), pred_contribs=True)   # (1, 3, 8 + 1)
safe   = shap[0, 0]                                     # 类别 0 = Safe；最后一列是 bias
contributions = [{"feature": name, "contribution": -float(v)} for name, v in zip(features, safe[:-1])]
baseline      = -float(safe[-1])
```

- 两次预测在同一个 `try` 里：任何抛错都归为 `ModelRuntimeError("Telemetry model failed during inference", origin=telemetry_model)`，和概率预测失败是同一个类别（HTTP 500、`model_runtime`、origin `telemetry_model`、可重试）。形状不是 `(1, 3, 9)` 或含非有限数时抛 `ModelRuntimeError("... wrongly shaped feature contributions", origin=telemetry_model)`。整个请求失败，不产生降级窗口（与既有「一个分支失败则整个请求失败」一致）。
- 8 项按模型特征的固定顺序（`speed_kmph … headway_distance`）；排序交给界面。bias 不算特征，单独成 baseline。
- 取负的原因：融合用的是 `1 − P(Safe)`，Safe 类打分往下压的特征才是「推向不安全」的特征；取负后正号 = 推向不安全。
- provenance 只在窗口带有贡献时写 `telemetry_contribution_method` 与 `telemetry_contribution_baseline`；没有遥测的请求不写这两个键（不写一个会被误读为 0 的 `null` baseline）。
- 可加性：Σ 贡献 + baseline = −margin_Safe（`margin_Safe` 为同一批树的 `output_margin`）。
- 数值样例（回放第 1 行，0 起，`window_id` 2，`P_telemetry_anomaly` = 0.6768）：XGBoost 自己的 Safe 类归因是 `headway_distance −4.764`、`brake_pressure +2.296`、`accel_y +0.197`（与简报一致）；记录里是取负后的 `headway_distance +4.764`、`brake_pressure −2.296`、`accel_y −0.197`。

### 4.2 无遥测 / 过期窗口的规则（读了代码，不是推断）

现有 `telemetry_behavior_classes` 的规则（`inference.run_inference` 把 provider 的值原样放进记录，只有 REPEAT 用登记值）：

| 窗口 | `telemetry_behavior_classes` 现状 | 贡献（本项照此） |
|---|---|---|
| 请求没带遥测 | provider 给 `[]` → 记录 `[]`（`test_live_single_branch.py` 已钉死） | `[]`，provenance 无 method / baseline |
| 请求带了遥测但已过期（裁定 A：`P_telemetry_anomaly` 记为 0、`modality_freshness.telemetry = missing`、`telemetry_expired = true`） | **保留**模型当时给的三类概率（「as recorded」；UI 的 Current Behaviour 也照常显示） | **保留**，provenance 的 method / baseline 也在 |
| REPEAT | 登记时的值 | 登记时的值 |

我在改代码之前用 `run_inference` 实跑了一次来确认第二行（过期遥测：`classes 3`、`contribs 1`、`P_t 0.0`），不是只读代码。

这与简报变异表 C-M4 的字面措辞（「无遥测或过期的窗口仍带贡献」是错误）不一致：按现有 classes 规则，过期窗口**应当**保留贡献。简报的明文指令是「与 classes 一致，先读现有代码确认那个规则，再照着做，并在报告里写明」，所以我跟随代码，并让测试在两个方向上都守住「与 classes 一致」：

- `test_a_window_without_telemetry_has_no_contributions_just_as_it_has_no_classes`（真模型）：无遥测 → 两者皆空、无 provenance 键；
- `test_expired_and_telemetry_less_windows_follow_the_rule_the_class_breakdown_has`（stub 经真实路由）：过期窗口两者皆保留，无遥测窗口两者皆空，逐窗口断言 `bool(classes) == bool(contributions)`。

C-M4 因此跑了两个方向（4.7）：(a) 无遥测窗口仍带贡献，(b) 过期窗口丢掉贡献（与 classes 分歧）。两者都有测试变红。如果控制者希望过期窗口把 classes 与贡献**一起**清空，那是一个同时影响两个字段的独立改动，不在本项范围，见第 7 节。

### 4.3 R10：REPEAT 就是它所重复的那个观测

- `OBSERVATION_REGISTRY_KEYS` 增加 `obs_t_contribs`；NEW 遥测观测登记 `[c.model_dump() ...]`（与 `obs_t_classes` 同一处、同一形式；`runtime_state` 是 JSON 列，浮点往返无损）。
- REPEAT 窗口的 `telemetry_feature_contributions` 用登记值，不用本次请求重新推理的结果。同一 seq 的内容逐字节相同，所以重新推理本来也一样；登记的意义是规则一致，并由测试守护（stub 第二次的答案故意不同）。
- 一处超出简报字面的防御：在贡献出现**之前**就登记过的会话，注册表里有 `obs_t_classes` 却没有 `obs_t_contribs`。此时 REPEAT 保留模型对同一字节的回答（等同于登记值），而不是给出空列表却在 provenance 里声称有 method。`stored is None` 与 `stored == []` 区分开（后者是一个真的登记值）。`test_a_repeat_in_a_session_registered_before_...` 守护它。
- 不改的东西：`TEMPORAL_STATE_KEYS`（注册表键不是时间记忆，gap 不清除它），测试 `test_g8_...` 已钉住这一点。

### 4.4 前端

- `ExplanationView.tsx` 仍然 `sort(|contribution| 降序).slice(0, 3)`，格式仍是 `formatSignedContribution`（`+`/`-`、两位小数、half-up 远离 0，与全站同一舍入）。
- 当 `provenance.telemetry_contribution_method === "xgboost_treeshap_neg_safe_margin"` 且有可显示的贡献时，列表下加一行 `<small class="feature-contribution-note">`：

  > Explains Telemetry Non-Safe Risk; + pushes toward unsafe. TreeSHAP local attribution in model-score (log-odds) units; not causal.

  只对已知的 method 名成立；legacy 记录（无 method）以及未知 method 都不显示。样式沿用 `.evidence-metrics small`，没有加 CSS。
- 全仓搜索了 positive / negative / pushes / toward / SHAP / contribution：没有别的文案提到贡献方向，不需要改别的文字。条形图的颜色规则（正 = 蓝、负 = 灰）原样保留，现在正好对应「推向不安全 / 推向安全」。
- 类型：`ai/src/types.ts` 的 `RiskUpdate.provenance` 加了两个可选字段（仅类型）。

### 4.5 测试与夹具

**夹具与生成脚本。** `make_telemetry_pt_fixture.py` 自己调 `Booster.predict(..., pred_contribs=True)`（不经过产品代码路径），取 Safe 行取负；同时自己再取一次 `output_margin=True`，断言 Σ + baseline = −margin_Safe（容差 1e-4），所以一个不满足可加性的夹具写不出来。`--check` 比较的是整个文件文本，贡献与 baseline 因此被核对；`--cross-check-provider` 另外要求产品 Provider 的贡献、顺序和 baseline 与夹具逐位相同。夹具绑定的模型哈希仍是 `9802cb06ca98f0c1befaf851fa7668cfec70e005cf8bb3884e49d7d45d7aec07`（`git diff` 里除了说明文字外，原有字段没有变）。

**后端 `test_telemetry_contributions.py`（新，8 个）。**

| 测试 | 守护什么 |
|---|---|
| `test_the_contributions_equal_the_frozen_literals_on_all_23_telemetry_rows`（`requires_models`） | 23 个有遥测的行：贡献列表（特征名 + 值 + 顺序）与 baseline 与冻结字面量**完全相等**；夹具的模型哈希等于磁盘文件等于测试里的字面量 |
| `test_contributions_plus_baseline_equal_minus_the_safe_margin_on_every_row`（`requires_models`） | 每行 Σ + baseline = −margin_Safe；margin 由测试**自己的** `xgb.Booster` 用 `output_margin=True`、`iteration_range=(0, 91)` 取得；先断言模型是 121 轮、`best_iteration` = 90 |
| `test_the_sign_positive_pushes_toward_unsafe_row_1_as_literals`（`requires_models`） | 第 1 行（0 起，`window_id` 2，P ≈ 0.6768）：`headway_distance` ≈ +4.764、`brake_pressure` ≈ −2.296、`accel_y` ≈ −0.197，绝对值前三位顺序为 headway、brake、accel_y |
| `test_the_contract_eight_features_in_the_models_order_and_the_two_provenance_keys`（`requires_models`） | 8 项、顺序与模型一致、provenance 的 method 为字面量、baseline 为 float、classes 同时存在 |
| `test_a_window_without_telemetry_has_no_contributions_just_as_it_has_no_classes`（`requires_models`） | 无遥测：贡献与 classes 皆空，无 provenance 键 |
| `test_a_repeat_carries_the_contributions_registered_with_the_observation` | stub 经真实路由 + SQLite：REPEAT 带的是登记值（模型第二次的答案不同，且确实又跑了一次）；NEW 样本被登记；再对新样本 REPEAT 取新登记值 |
| `test_a_repeat_in_a_session_registered_before_the_contributions_existed_keeps_the_models_answer` | 注册表里缺 `obs_t_contribs` 的旧会话（4.3） |
| `test_expired_and_telemetry_less_windows_follow_the_rule_the_class_breakdown_has` | 4.2 的规则 |

期望值都是字面量（冻结夹具或测试内字面量），没有从实现 import 常量。

**其它后端测试。** `test_fault_events.py` +4 条（贡献调用失败 / NaN / Inf / 形状错误 → 500、`model_runtime`、origin `telemetry_model`、可重试、无记录）；`test_r10_fsm.py` 注册表键字面量加一项；`test_live_single_branch.py` 的 ST-BRANCH-T（两处）逐窗口核对贡献等于冻结行（NEW 与 REPEAT 窗口都在内）及 `telemetry_contribution_method`，ST-BRANCH-V 核对无遥测窗口贡献为 `[]`；`test_live_e2e.py::test_06` 在 Explanation 视图里读 DOM，断言卡片显示的前 3 个特征及数值（`+4.76` 形式，独立的 half-up 实现 `e2e_support.fixed`）等于该窗口记录里绝对值最大的 3 项，且标注文字逐字相符。2a / 2b 的五方对账（infer 响应 / 数据库行 / `GET /windows` / JSON 导出 / CSV 导出，provenance 逐键）自动覆盖新字段，实跑全绿。

**vitest `featureContributionRender.test.ts`（新，8 个）。** 带 method 的记录：前 3 项及顺序、值与符号（`Headway Distance +4.76` / `Brake Pressure -2.30` / `Lateral Accel -0.20`）、与输入顺序无关、正 / 负条形的样式类、标注逐字、half-up 远离 0（`+1.01` / `-0.13` / `+0.00`）、无贡献时只显示 `unavailable` 且无标注；legacy 记录（无 provenance、`MockAIProvider`）保留表值且不含 `TreeSHAP` / `log-odds`；未知 method 名也不显示标注。

### 4.6 性能

对象：真实 `TrainedProvider` + 冻结模型，只带遥测的请求（23 个回放行轮流），`inference_threads` = 2（默认值）。「有 TreeSHAP」是产品代码；「无 TreeSHAP」是同一个 booster，只是把 `pred_contribs=True` 那次调用换成预先算好的数组（等于改动前的耗时再加一次空方法调用）。两组交替各 5 轮、每轮 600 次，共 3000 次，先预热 300 次。

| | 均值 | 中位数 | p95 |
|---|---|---|---|
| `provider.infer`，有 TreeSHAP | 0.746 ms | 0.589 ms | 0.974 ms |
| `provider.infer`，无 TreeSHAP | 0.221 ms | 0.206 ms | 0.291 ms |
| **增加** | **0.525 ms** | **0.383 ms** | — |

另外在 `nthread` = 1 下单独计时同一个 `DMatrix`：`predict()` 约 0.038 ms，`predict(pred_contribs=True)` 约 0.372 ms（200 次平均）。结论：每个带遥测的 `/infer` 增加约 0.4 ms（中位数）/ 0.5 ms（均值），低于期望的 1 ms；带图像的请求里 MobileNetV3 推理占大头，这个增量不改变量级。3000 次样本里有一次 58 ms 的离群值（出现在「有 TreeSHAP」组，应是系统抖动，没有复现），不影响上述统计量。这是 Provider 层的耗时，不含 HTTP / 融合 / 提交。

### 4.7 变异（实现者；隔离副本）

方法：`git add` 本项文件后用 `git archive $(git write-tree)` 取暂存区的树解到临时目录（含本项全部改动），符号链接 `.venv`、`node_modules`，把三个模型文件以只读符号链接接进副本的 `ml/outputs/`；副本自己 `git init` 提交一次作为基线，每次变异后用备份文件还原并检查副本 `git status --porcelain` 为空。真实工作树没有被变异。脚本：`/private/tmp/claude-501/…/scratchpad/mutate.py`（一次性，不入库）。

结果都是在隔离副本里实测的；「变红的测试」是该变异下失败的全部测试。

**后端（`pytest tests/test_telemetry_contributions.py tests/test_fault_events.py tests/test_r10_fsm.py`，变异前 146 passed）**

| # | 变异 | 变红 |
|---|---|---|
| C-M1 | 不取负号（贡献与 baseline 都用原值） | `test_the_contributions_equal_the_frozen_literals…`、`test_contributions_plus_baseline_equal_minus_the_safe_margin…`、`test_the_sign_positive_pushes_toward_unsafe_row_1…`（3 failed） |
| C-M1b | 贡献取负、baseline 没取负 | 冻结字面量、可加性（2 failed） |
| C-M2 | 用预测类别的 SHAP 而不是 Safe 类（`shap[0, argmax(probs)]`） | 冻结字面量、可加性、第 1 行符号（3 failed） |
| C-M3 | 特征名与数值错位一位（名字轮转） | 冻结字面量、契约（顺序）、第 1 行符号（3 failed） |
| C-M4a | 无遥测窗口仍带贡献（Provider 给 8 个 0.0） | `test_a_window_without_telemetry_has_no_contributions…`（1 failed） |
| C-M4b | 过期窗口丢掉贡献（`inference.py` 里 `tstatus == "missing"` 时给 `[]`，与 classes 分歧） | `test_expired_and_telemetry_less_windows_follow_the_rule_the_class_breakdown_has`（1 failed） |
| C-M5a | REPEAT 的贡献为空列表 | `test_a_repeat_carries_the_contributions_registered…`、`test_a_repeat_in_a_session_registered_before…`（2 failed） |
| C-M5b | REPEAT 用本次重新推理的答案（不用登记值） | `test_a_repeat_carries_the_contributions_registered…`（1 failed） |
| C-M5c | NEW 观测不登记贡献 | 同 C-M5a 的两条（2 failed） |
| C-M5d | `obs_t_contribs` 不在 `OBSERVATION_REGISTRY_KEYS` 里 | `test_g8_every_key_the_live_fsm_writes_is_listed`、`test_g8_the_segment_keys_are_temporal_and_the_registry_keys_are_not`（2 failed） |
| C-M7 | `pred_contribs` 不传 `iteration_range` | 冻结字面量、可加性、第 1 行符号（3 failed）。**不等价**：模型文件有 121 轮，`best_iteration` = 90、`iteration_end` = 91；全部树与前 91 轮的 Safe 行归因最大相差 0.24 – 0.55，所以按原样跑，不需要换同类变异 |
| X1 | `pred_contribs` 形状 / 非有限的错误被归到视觉模型 | `test_fault_events.py` 的 `contribs-nan` / `contribs-inf` / `contribs-shape`（3 failed） |
| X2 | `pred_contribs` 调用挪到 `try` 外面（抛错不再是 `ModelRuntimeError`） | `contribs-raises`（1 failed） |

**前端（`vitest run frontend/src/views/featureContributionRender.test.ts`，变异前 8 passed）**

| # | 变异 | 变红 |
|---|---|---|
| C-M6 | Live 记录上不显示标注（`treeShapContributions = false`） | `says what the numbers mean: non-safe risk, + toward unsafe, TreeSHAP, log-odds, not causal`（1 failed） |
| C-M6b | 标注对所有记录都显示（去掉 method 条件） | `keeps showing the table and carries no TreeSHAP sentence`、`does not claim TreeSHAP for a method name it does not know`（2 failed） |
| C-M6c | 正值不带 `+` 号 | 4 failed（前 3 项带符号、顺序无关、half-up、legacy 表值） |

**端到端（隔离副本里重新 `npm run build`、真 Chromium、真 uvicorn）**

| # | 变异 | 变红 |
|---|---|---|
| E1 | 卡片只显示 2 个特征（`.slice(0, 2)`） | `test_live_e2e.py::TestStLiveE2E01::test_06_the_five_views_open_and_show_what_the_backend_recorded`（1 failed, 11 passed） |
| E2 | REPEAT 的贡献为空列表 | `test_live_single_branch.py::TestStBranchTSmoke::test_02…`、`::TestStBranchTContinuity::test_03…`（2 failed, 7 passed） |
| E3 | 只带视觉的窗口也带贡献 | `test_live_single_branch.py::TestStBranchV::test_02_vision_only_windows_score_the_distraction_probability`（1 failed, 4 passed） |

没有任何一个 e2e 测试能区分 C-M5b（REPEAT 用重新推理的答案）：真模型对同一字节的回答与登记值逐位相同，这正是简报说的「本来也一样」。这一条由 stub 测试守护。

**夹具脚本**：F1 把冻结夹具里某个贡献改一位小数（`4.763640880584717` → `…718`）→ `make_telemetry_pt_fixture.py --check` 退出码 1；F2 Provider 不取负 → `--check --cross-check-provider` 对每个有遥测的行报 `MISMATCH`（只贴前几行）、退出码 1。还原后副本 `git status` 干净；未变异时 `--check --cross-check-provider` 退出码 0（`identical on all 23 telemetry rows`）。

每一次变异后副本都用备份文件还原，并确认副本 `git status --porcelain` 为空（输出里每条都有这一行）。

## 5. 执行的测试（精确命令）

> 第 5–9 节由**控制者**补写：实现者写到这里时撞上会话额度，没有提交。下面的命令和计数都是控制者在 2026-10-22 对这棵树（实现者暂存的改动，加上被应用退回又恢复的 5 个测试辅助文件，见第 7 节）亲自运行的结果。

```bash
cd /Users/liu/Desktop/FYP2-Live-System
DRA_REQUIRE_MODELS=1 PYTHONDONTWRITEBYTECODE=1 python3 scripts/run_gates.py --out <scratch>/contrib-gates
# 变异复现（控制者）：git archive $(git write-tree) 解到隔离副本，.venv / node_modules / 三个模型文件以符号链接接入，
# 每项精确单处替换后跑：
(cd backend && ../.venv/bin/python -m pytest tests/test_telemetry_contributions.py tests/test_fault_events.py tests/test_r10_fsm.py -q -p no:cacheprovider)
./node_modules/.bin/vitest run --no-cache frontend/src/views/featureContributionRender.test.ts
```

## 6. PASS / FAIL / SKIP 计数

| 门禁（控制者，`run_gates.py`，`DRA_REQUIRE_MODELS=1`） | 结果 |
|---|---|
| build | 通过 |
| pytest | **979 passed / 0 failed / 0 skipped**（967 → 979：`test_telemetry_contributions.py` 8 条 + `test_fault_events.py` 新增参数化 4 条） |
| vitest | **918 passed**，30 个文件（910 → 918：`featureContributionRender.test.ts` 8 条） |
| tsc / eslint | 0 / 0 |

控制者复现的 brief 变异（隔离副本，基线 146 passed / vitest 8 passed，每项还原后逐字节相同）：

| # | 结果 |
|---|---|
| C-M1 不取负号 | 3 failed：冻结字面量、可加性、第 1 行符号 |
| C-M2 用预测类别 | 3 failed：同上 |
| C-M3 特征名错位一位 | 3 failed：契约（顺序）、冻结字面量、第 1 行符号 |
| C-M4 无遥测窗口带贡献 | 1 failed：`test_a_window_without_telemetry_has_no_contributions_just_as_it_has_no_classes` |
| C-M5 REPEAT 为空列表 | 2 failed：两条 REPEAT 测试 |
| C-M6 界面不显示标注 | vitest 1 failed：`says what the numbers mean…` |
| C-M7 不传 `iteration_range` | 3 failed：冻结字面量、可加性、第 1 行符号 |

## 7. 遗留问题

1. **过期窗口保留贡献**（与 `telemetry_behavior_classes` 一致，见 4.2）。界面上同一张卡片里，「Current Behaviour」与贡献都按当时记录显示，非安全风险的数值不显示，新鲜度标为 expired，不会误导。若以后要把过期窗口的 classes 与贡献一起清空，那是同时影响两个字段的独立改动。
2. **应用把工作区退回的事件**（2026-10-22 15:12）：本会话用 Edit 改过的 5 个测试辅助文件（`conftest.py`、`e2e_support.py`、`test_model_gate.py`、`test_live_e2e.py`、`test_live_single_branch.py`）的工作区被退回旧版本，另有 5 个已提交的文件被删除。控制者从暂存区 / HEAD 恢复，退回版本存为 SDD 目录 `rewind-1512-backup/` 下的补丁。本项提交的内容与实现者暂存的完全一致，没有混入退回的旧内容。
3. 端到端测试分不出 C-M5b（REPEAT 用重新推理的答案），因为真模型对同一字节的答案与登记值逐位相同。这一条由 stub 测试守护（4.7）。

## 8. 证据路径

- 门禁日志：控制者 scratch 目录 `contrib-gates/`（未归档；G-W4-A 的正式证据仍在 `docs/evidence/2026-10-20/live-e2e/`）。
- 冻结夹具：`backend/tests/fixtures/telemetry_pt_by_row.json`（绑定 `xgb_telemetry.json` 的 `9802cb06…`），生成脚本 `make_telemetry_pt_fixture.py --check --cross-check-provider`。

## 9. 下一项依赖

- 回放分支（`fyp2/dataset-replay`）改 `trained.py` 之前，先合并 `fyp2/live-system`，因为本项也改了 `trained.py` 的 provenance。
- 报告和答辩里关于贡献的说法统一为：TreeSHAP 局部归因，作用于 Safe 类打分，取负号（正号推向不安全），单位为 log-odds，不代表因果，也不是数据集层面的特征重要性。
