# FYP2 系统集成五阶段计划与完成审计清单

创建日期：2026-10-25。用途：供你逐项检查系统轨道（Codex/Claude）是否完成各阶段任务。**本文件只列验收标准和证据位置，不预判完成状态**——每项"已完成"必须由你在对应证据路径里找到当日新鲜输出确认。

## 0. 冻结参照（所有阶段共用）

| 参照物 | 值 | 位置 |
|---|---|---|
| 系统轨道基线 commit | `fyp2/live-system@2745348f3d4587e14c1d4a7e53a2bfc4d72225d5` | git |
| ML 轨道来源 commit | `fyp2/ml-training@335da4e3de203836c045452f84cc291bcd352a26`（工作树仍 dirty） | git |
| RN 候选包 | `p5_resnet18_search004_seed42_20261023.zip`，SHA `9fb9551f49aeb3582dfc7cb76c9050b7690a8856621944eb363fecd73ea35029` | `ml/outputs/runs/p5_candidates_20261023/` |
| MN 候选包 | `p5_mobilenet_v3_large_search006_seed42_20261023.zip`，SHA `ae887dabe3588969576ecfb54fead41d0f03bd02267028a8a80f73311811ae13` | 同上 |
| RN ONNX SHA | `5e226722e0712824c78aa0976afa6fa5b8dc6100b147a7f523a09048171d8cf3` | 包内 manifest |
| MN ONNX SHA | `9ee60abb78007773cc625af80c313049c1970f63c1f041bed9f5b2539a384828` | 包内 manifest |
| manifest 契约 v1 | `[1,3,224,224]` float32 NCHW/RGB、直接 bilinear resize224/ImageNet 归一化、`[1,10]` logits、c0–c9 顺序、c0=safe | `backend/app/runtime_manifest.py` + `.schema.json`（live-system） |
| Parity 参照 | 两份 ONNX 在 100 个 val 来源、211 个样本位置 PyTorch–ORT 一致 | `ml/outputs/runs/p4a_20261021/parity_RN-HPO42.json`、`parity_MN-HPO42.json` |
| P4 结果 | clean test 表、E1 表、runtime 表 | `ml/outputs/runs/p4b_20261022/evaluation_metrics.json` |
| 遥测 | 部署固定 XGB-STABLE（R3）；`xgboost_02` 仅研究记录，无候选 importer | `backend/app/providers/trained.py` |
| 机位裁定（10-25） | 演示以 C（数据集回放）为主；B（侧面机位）仅用户闲暇非正式测试，不作评估证据 | 本会话裁定 |

## 0.5 全局红线（违反任何一条即该阶段不算完成）

- 不新增训练/HPO/导出/benchmark；不按 Test 重新选 trial/seed。
- RF/LR 运行时永不加载；XGB 加载路径与行为不变。
- 不替换 SQLite；不做 prepared-probabilities fallback（加载失败必须报错）。
- 每个"完成"声明必须附带当日命令输出（exit code + 关键行），旧日志不能冒充新重跑。

---

## Stage 1：Candidate Provider Integration

**目标**：`TrainedProvider` 能读两份 vision manifest，校验 hash、输入预处理、类别顺序，并实际 forward。

### 交付物

1. manifest 驱动的加载：manifest 路径 → 模型文件路径、SHA256 校验、input/logits 契约、iteration_range。
2. Active 模型配置开关：默认 `mobilenet_v3_large`（STABLE），可切换 `resnet18 search_004/seed42`；切换有版本记录（R3：版本化发布、不覆盖稳定产物）。
3. XGB 路径原样保留。
4. 加载失败路径：hash 不符、schema 不符、类别顺序不符 → 明确报错，无 mock fallback。
5. 测试用例：hash 不符拒绝、c0–c9 顺序断言、forward 输出与 parity 参照一致、开关切换后重复加载正常。

### 验收标准（审计点）

| 审计点 | 怎么查 |
|---|---|
| provider 代码已改且提交在 live-system 或其新分支 | `git log fyp2/live-system` 或新分支上，时间晚于 2745348 |
| 两份 manifest 通过系统 CLI 校验 | `scripts/validate_runtime_manifest.py` 输出 `valid / exit0`（针对实际两份 manifest） |
| 实际 forward 已发生 | 测试里出现 ORT session run + 与 parity 缓存对比的断言，且当日输出 0 failed |
| hash 校验真在跑 | 测试含"篡改 hash → 拒绝加载"的 red/green 证据 |
| 默认仍是 MN-STABLE | 配置默认值 + 一次默认启动日志显示加载 `mobilenetv3_large_vision.onnx` |
| XGB 未被改动 | `git diff 2745348 -- backend/app/providers/trained.py` 中 XGB 相关行无变化 |

**完成状态：待审计。** 截至 2745348，`TrainedProvider` 仍硬编码 MN 路径、不消费 manifest（`BLOCKED_BY_TASK10A_IMPLEMENTATION`）。

---

## Stage 2：Paired System Comparison

**目标**：固定回放输入下，RN 候选与 Stable MN 逐帧对照，其余模块（fusion/EMA/FSM/DB）配置不变。

### 前置：先写死对比协议（D06 要求预声明）

协议必须预先记录并含以下条目，缺一不可：

- 回放输入集身份：推荐直接用 stable200（各类按 filename 排序取前 20）或 P4A 的 100 来源/211 位置集；**无论选哪个，必须记录输入集 hash 与构成规则**。
- fusion 配置固定（w_v/w_t 默认 0.5/0.5、freshness 策略不变）。
- 对比量清单：RiskScore 分布、RiskLevel 序列、DominantEvidence、alert 状态迁移（FSM）、逐类 argmax。
- 判定口径：**不设单一分数门槛**；差异逐项描述，替换与否由用户（Stage 5）拍板并记录理由。

### 交付物

1. 对比 runner：同一输入流分别喂两模型，其余管线相同；两次运行之间 EMA/FSM/DB 状态隔离（确定性）。
2. 协议记录文件（含输入 hash、配置、对比量）。
3. 结果 JSON：两模型逐帧/逐窗口对照表。

### 验收标准（审计点）

| 审计点 | 怎么查 |
|---|---|
| 协议文件存在且早于 runner 运行 | 文件时间戳 + 内容含输入 hash |
| 输入集 hash 可复算 | 用协议记录的规则重算，得到同一 hash |
| 两次运行状态隔离 | runner 代码有状态重置，或结果注明逐窗口独立计算 |
| 结果与 P4 已知事实一致 | 例如 c9 是弱类（RN pooled c9 F1 0.6059、p050 c9 F1=0）应在对照中体现，而不是消失 |

**完成状态：待审计。** 目前 `official_stable200_behavior=NOT_RUN`——如果 Stage 2 采用 stable200 作为输入集，stable 基准行为必须在本阶段内一并产出。

---

## Stage 3：Runtime Evaluation

**目标**：capture-to-render latency、系统健康、fusion 正确性、EMA/FSM、日志完整性，在候选接入后复测。

### 交付物

1. 延迟测量（MN 与 RN 各一份）：沿用 perf 套件（`docs/evidence/2026-10-22/perf/perf02.json` 模式）。已知参照：MN model-only p95 7.2ms；系统 capture→render p95 39ms（MN 在役时）；RN model-only p95 25.4ms → 预计 capture→render 约 57ms，**必须实测而非外推**。
2. 系统健康与回归：backend pytest 全绿（基线 1028 passed）、前端 vitest 全绿、`npm run build` + `npx tsc --noEmit` exit0。
3. fusion/EMA/FSM 正确性：现有回归测试集通过，不因切换 active 模型而改变语义。
4. 日志完整性：同 perf02 的逐条日志核对（基线 211/211）。

### 验收标准（审计点）

| 审计点 | 怎么查 |
|---|---|
| 延迟 JSON 当日生成，含 MN 与 RN 两条 | 文件名带日期，字段与 perf02 同构 |
| RN 场景下 p95 有实测值 | 不允许出现"预计/外推"代替测量 |
| 全量测试当日重跑 | 新日志文件，exit code 0 |
| 健康检查 | 无新 error 级日志；DB 权威性/幂等测试通过 |

**完成状态：待审计。**

---

## Stage 4：Target Camera Validation

**目标**：确认目标使用场景下的视觉行为。**按 10-25 机位裁定分两条线。**

### 4-C（主演示路径：数据集回放）

- 不做新实验。已具备的证据：State Farm test 3,657 帧 clean test 0.8988；三路径（ONNX/provider/HTTP）逐张一致；browser 式重编码仅损 0.0005。
- 交付：演示会话正常运行（回放帧 → RiskUpdate 全链路），会话记录可追溯。
- 报告口径：演示回放产生的任何命中率/RiskLevel 数字**不进报告第 6 章**。

### 4-B（用户闲暇非正式测试：侧面机位）

- 仅用户自行观察；无标签、无被试划分 → **不是评估证据**，不进报告第 6 章，答辩可口头提及。
- 正面视角（笔记本摄像头）识别仍为 measured limitation（证据：`docs/evidence/2026-10-22/vision-runtime-path/README.md`，~5,170 帧 safe_driving 仅 5 次）。

### 验收标准（审计点）

| 审计点 | 怎么查 |
|---|---|
| 演示走回放路径而非正面摄像头 | 会话记录/演示脚本 |
| 报告草稿中未出现回放数字当评估结果 | 检查第 6 章数字出处是否全部指向 Live/ML 证据 |

---

## Stage 5：Release Decision（由你裁定）

**目标**：根据 Stage 1–3 证据选择 Active Model，保留 Stable Rollback，记录版本与理由。

### 交付物

1. 决策记录文件：选谁、为什么、引用的证据文件、日期、签字（你的裁定）。
2. 版本化配置：active 模型标识 + 回滚配置（切回 MN-STABLE 的开关/步骤），不覆盖稳定产物（R3）。
3. 回滚演练：至少一次"切回 MN-STABLE → hash 校验 → 正常 forward"的实测记录。

### 验收标准（审计点）

| 审计点 | 怎么查 |
|---|---|
| 决策记录引用 Stage 2/3 的当日证据 | 文件内的证据路径可打开 |
| 回滚可执行且被验证 | 回滚演练日志（exit0） |
| 报告措辞与决策一致 | 6.2 结论段与决策记录一致：RN 是 validation 选出的候选，Active 状态按本记录 |

---

## 附：逐阶段"检查 Claude 是否完成"速查表

| 阶段 | 一句话检查 | 关键证据文件名 |
|---|---|---|
| 1 | provider 里找得到 manifest 读取与 hash 校验，且默认模型仍是 MN | 新提交 diff、manifest 校验日志、forward 对比测试日志 |
| 2 | 有一份协议文件（含输入 hash）+ 一份对照结果 JSON | 协议记录、comparison 结果 |
| 3 | 有当日 RN 延迟实测 JSON + 全量测试 exit0 | perf JSON（日期）、pytest/vitest 日志 |
| 4 | 演示回放正常；报告里没有回放数字冒充评估 | 会话记录、报告草稿 |
| 5 | 你的决策记录 + 回滚演练日志 | 决策文件、rollback 日志 |

## 未决问题（供你与 Codex 确认）

1. Stage 2 回放输入集选 stable200 还是 P4A 100/211 集？（谁定，就要谁在协议里写 hash）
2. Stage 1 的代码分支策略：直接在 `fyp2/live-system` 续做，还是新分支？（本清单两种都接受，但要求 commit 可追溯）
3. `official_stable200_behavior`（现为 NOT_RUN）由 Stage 1 还是 Stage 2 补做？
