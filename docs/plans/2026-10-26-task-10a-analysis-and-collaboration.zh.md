# Task 10A 计划分析与三方协作方案（Claude / Codex / DeepSeek）

- **日期**：2026-10-26。
- **分析对象**：`docs/plans/2026-10-25-task-10a-candidate-integration.md`，下文称「计划」。
- **分析依据**：
  - 规格 `/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/docs/fyp2/11_SYSTEM_INTEGRATION_STAGE_PLAN_AND_AUDIT.md`，下文称「规格」，在 ML 工作区里，**未提交**；
  - Live System 代码，`276f059`。代码与 `2745348` 相同，`276f059` 只多了文档；
  - ML 工作区里的 P4/P5 产物，同样**未提交**。
- **核对方式**：本节所有事实都由 Claude 在 2026-10-26 亲自运行命令确认，证据写在每条后面。

---

## 1. 结论

**可以执行，但计划有 6 处必须先改**，否则执行时会出错或得出错误结论。下面的 C-1 到 C-6 已作为裁定写进本文，执行者按改正后的写法做。

另有 6 处建议改，见 C-7 到 C-12；还有 3 项要用户决定，见第 3 节。

**已核实的事实**：

| 事实 | 证据 |
|---|---|
| 两个候选包都在，ONNX 的 sha256 与计划一致：RN `5e226722…`，MN 候选 `9ee60abb…` | 在 `…/p5_candidates_20261023/<包>/model.onnx` 上运行 `shasum -a 256` |
| 两份 `runtime_manifest.json` 用系统自带的校验器检查都是 **valid，exit 0**（含包内模型文件检查） | 把校验器和 schema 复制到临时目录，运行 `scripts/validate_runtime_manifest.py <manifest> --package-dir <包>` |
| stable200 的 200 张图片**都能找到**，划分全是 `val` | 位置是 `/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment-/state-farm-distracted-driver-detection/imgs/train/<class_id>/<filename>`。注意 data root 是**单横线**目录，不是 `--1` |
| 候选包按 `runtime_aliases` 覆盖 `training_labels` 生成的标签，与稳定模型的标签列表**完全一致**，c0 为 `safe_driving` | `class_metadata.json` 与 `ml/outputs/vision/metrics.json` |
| manifest 自带预声明的冒烟规则：`contract_smoke_set.rule = per_class_mode_equals_label`，`n = 200`，哈希 `601dc3ed…` | 包内 `runtime_manifest.json` |
| `onnx 1.21.0` 已装，也在锁文件里 | `.venv/bin/python -c "import onnx"`；`backend/requirements.lock.txt:80` |
| provider 第一次被请求时才构建（`get_provider()` 单例），`settings` 在进程启动时读取环境变量 | `backend/app/providers/trained.py:190-200`，`config.py:13`（`env_prefix="DRA_"`） |

## 2. 必须改正的地方（裁定）

| # | 计划位置 | 问题 | 改为（裁定） |
|---|---|---|---|
| **C-1** | Task 1.1–1.3 的测试代码与命令 | 测试写的是 `from backend.app.config import …`，并用 `PYTHONPATH=backend … pytest backend/tests/…` 运行。仓库约定是在 `backend/` 目录下以 `PYTHONPATH=.` 运行，导入写 `from app.…`（门禁 `scripts/run_gates.py:14`）。按计划的写法，在门禁里会 ImportError；就算在仓库根目录跑通了，进程里也会同时存在 `app.*` 和 `backend.app.*` 两套模块，monkeypatch 只改到其中一个 `settings` | 测试一律写 `from app.config import settings` 这种形式。命令一律是 `cd backend && PYTHONPATH=. ../.venv/bin/python -m pytest tests/test_vision_candidates.py -q -p no:cacheprovider` |
| **C-2** | Task 1.2 的加载器约定与合成测试包 | 计划假设 `class_metadata.json` 里有 `{"class_names": {"c0": …}}`。**真实格式**是这些键：`class_to_idx`、`classes`、`training_labels{c0..c9}`、`runtime_aliases{"c0": "safe_driving"}`、`safe_class`、`meaning`。按计划写的加载器读不了真实的候选包 | `labels = [runtime_aliases.get(c, training_labels[c]) for c in classes]`，并断言等于稳定模型的标签列表（运行时契约）。合成测试包必须使用真实格式 |
| **C-3** | Task 1.4（稳定模型那一项） | 计划要拿稳定 MobileNetV3 去和「它的 stable200 已存预测」比较，但**这种预测在两个工作区里都不存在**。stable200 的已存预测只有两个候选包里有，而且是 **PyTorch** 的 val 预测，不是 ONNX 的 | 稳定模型改用 `ml/outputs/runs/p4a_20261021/parity_MN-STABLE.json` 中的 `result.validation_predictions`（100 个 val 来源，带 logits）作为参照。候选模型同时对照 stable200 的已存预测和各自的 `parity_*-HPO42.json`。三个模型都要评估 manifest 自带的 `per_class_mode_equals_label` 规则。规格 Stage-1 的审计点要求「与 parity 缓存对比的断言」，这样正好满足 |
| **C-4** | Task 1.2、1.3 中「找不到 index.json 就 skip」的真实包测试 | 门禁要求 0 skipped，冷启动也不会复制候选包。所以这些测试在门禁里要么显示为 skipped，破坏 0 skipped；要么用了模型跳过的原因，被 `DRA_REQUIRE_MODELS=1` 判为失败 | 与 `long` 的做法一致：新加 `candidates` 标记，**默认 deselect**，只有 `-m candidates` 时才运行。Stage-1 证据里单独跑一次 `-m candidates`，并设 `DRA_REQUIRE_CANDIDATES=1`，让缺包直接失败。合成包测试不打这个标记，永远运行；`onnx` 直接 import，不要 `importorskip` |
| **C-5** | 「前端保持不变」 | 前端有两处写死了模型名：`frontend/src/App.tsx:292` 显示「MobileNetV3: \<sha\>」，`frontend/src/utils/dataMode.ts:24` 写着「trained MobileNetV3」。候选模型启用后，界面会把 ResNet18 的哈希标成 MobileNetV3，这是误导 | 最小改动：两处都改为读 `/api/models` 返回的 `vision.architecture` / `model_id`，并加一条 vitest。Task 1.3 的范围里加上这两个文件 |
| **C-6** | Phase 3 Step 1；规格 Stage 3 第 1 条 | 计划和规格都写「延迟用 perf02 模式」。在本仓库，**延迟是 `scripts/perf01.py`（capture → render）**；perf02 测的是日志完整性（D1/D2）。另外两个脚本都通过 `e2e_support.start_server` 起服务，目前没有办法把 `DRA_ACTIVE_VISION` 传进去 | 延迟用 perf01，日志完整性用 perf02。`start_server` 加参数 `extra_env: dict[str, str] \| None = None`，默认行为不变，签名与回放分支的计划一致（已通知回放会话）。规格里的措辞问题见 U-2 |

## 3. 建议改进的地方，以及要用户决定的事

**建议**（执行者直接照做，记为裁定）：

| # | 内容 |
|---|---|
| C-7 | 测试数已过时：门禁计数是 **pytest 1046 / 0 skipped / 1 deselected，vitest 954**（`276f059`），不是 1028 / 922。XGB 未改动的对比基准 `git diff 2745348 -- backend/app/providers/trained.py` 仍然有效，因为 `276f059` 没有改代码 |
| C-8 | 计划的风险一节要求每个窗口都带上模型 id **和 sha256**，但 Task 1.3 只加了 `vision_model_id`。再加一个 `vision_model_sha256`，成本很低，历史记录也就能自我说明 |
| C-9 | Stage-2 协议补充预声明（D06）：200 帧是 10 个类别、每类 20 张的连续块，属于**构造的评估场景**，要写明：<br>• 时间基准：例如每 0.1 s 一个窗口，注入时钟；<br>• 观测身份：帧的 epoch / index 与遥测 seq 逐个递增；<br>• 遥测配对：建议所有窗口用同一条固定的遥测行，这样唯一的变量是视觉模型；<br>• 结论口径：FSM 在类别块边界上的迁移是场景造成的，只做描述。<br>runner 通过 TestClient 走 `/infer`，这样 R10 的规则也在测试范围内。每个模型一个子进程，各用自己的 `DRA_DATABASE_URL` 临时库 |
| C-10 | `verify_stable200.py` 的 data root 用参数传入，不写死；运行前先按规则重新计算成员哈希，必须等于 `601dc3ed…`，否则退出 |
| C-11 | 与回放分支（`fyp2/constructed-scenario`）重叠的文件：`App.tsx`、`dataMode.ts`（C-5 要改），`e2e_support.py`（C-6 要改）。合并顺序由 Claude 协调。回放分支最终合回时，需要先合并最新的 `fyp2/live-system`，不能再 fast-forward |
| C-12 | 计划的 D1 规定「不 push」。这适用于 Task 10A 的开发过程；推送到 `dev_cc` 只在用户要求时做 |

**要用户决定**：

| # | 问题 | Claude 的建议 |
|---|---|---|
| U-1 | stable200 / parity 对比的容差：计划给稳定模型的容差是 1e-5、候选是 1e-4。但参照是 PyTorch 输出，provider 走的是自己的 JPEG 解码和缩放路径，不是 P4A 测的「同一个张量」。1e-5 可能因为良性的预处理差异而误判失败 | 三个模型统一用 **概率最大绝对差 ≤ 1e-4、argmax 一致率 = 1.0**。依据：P4A 实测概率误差最大 4.85e-6，再加上解码路径的余量。由 Codex 在 CX-0 里起草，必须在任何对比运行**之前**由你批准 |
| U-2 | 规格 Stage 3 写着「延迟 JSON 与 perf02 同构」 | 改为与 perf01 同构，见 C-6。规格由你维护，请你确认这一处更正 |
| U-3 | Stage-2 的输入集：规格的未决问题 1 | 计划选了 stable200，我同意。P4A 的 100 来源 / 211 位置集作为附录 |

---

## 4. 三方协作方案

### 4.1 分工原则

1. **一个文件只有一个负责人。** provider、推理与配置的核心代码（`trained.py`、`inference.py`、`config.py`）只由 Claude 改。
2. **实现者不审计自己的工作。** 按用户的长期偏好「Claude 写，Codex 审」，Codex 主要负责独立审计和 ML 事实核查。Codex 起草了 Stage-2 协议，所以 Stage-2 改由全新的 Claude 子代理审计。
3. **DeepSeek 做边界清楚的独立模块。** 例如评审修复和两个 runner 脚本。它在自己的 worktree 和短分支上工作，由 Claude 审阅后合并。
4. **集成者唯一。** 只有 Claude 向 `fyp2/live-system` 提交或合并。每次合并前都在合并后的代码上跑一次全量门禁：`DRA_REQUIRE_MODELS=1 python3 scripts/run_gates.py`。
5. **用户的关卡不跳过。** Stage-1 审计（U-1）和 Stage-5 发布决定（U-5）都由用户做。

### 4.2 各 lane 与依赖

```
现在并行：  DS-0 评审修复        CX-0 预检 + 容差 / 协议草案        CL-1 Task 1.1–1.3
               │                       │                                │
               └────── Claude 合并 ────┴───────────┬────────────────────┘
                                                   ▼
                                    DS-1 stable200 runner（用 CX-0 批准后的容差）
                                                   ▼
                                    CL-2 Stage-1 证据 → CX-A1 Codex 审计 → U-1 用户审计（停）
                                                   ▼
                                    用户批准协议 → DS-2 对比 runner → CL-3 运行 Stage 2 → A2 审计（停）
                                                   ▼
                                    CL-3 Phase 3 延迟与完整性 → CX-A3 审计 → Stage 4 说明 → 回滚演练 → U-5 用户决定
```

**之后可以接着做的并行项**（Task 10A 之外）：
- E2 / E5 runner：D06 已有决定。适合 Codex 起草评估设计，DeepSeek 实现。
- 回放会话继续做 Constructed scenario。

### 4.3 git 布局

| 谁 | 工作区 | 分支 | 来源 |
|---|---|---|---|
| Claude | `/Users/liu/Desktop/FYP2-Live-System` | `fyp2/live-system`（集成分支） | — |
| DeepSeek | `/Users/liu/Desktop/FYP2-DeepSeek`（**已建好**，`.venv`、`node_modules` 和三个模型都已链接） | `fyp2/ds-review-fixes`，从 `fyp2/live-system` 的最新提交切出（见状态板上的「当前基线」）；之后的 lane 由 Claude 从最新基线另切新分支 | Claude 建 |
| Codex | 只读访问 Live System（读的是 `fyp2/live-system` 的当前代码）；它自己的 ML 工作区（`fyp2/ml-training`）不动 | **不建分支**：CX-0 和各次审计都不改代码 | 报告写到 `/Users/liu/Desktop/FYP2-Live-System/.superpowers/collab/codex/`，被 git 忽略，由 Claude 提交进 `docs/fyp2/task10a/`。以后如果让 Codex 写代码（例如 E2 / E5），再由 Claude 另建 `FYP2-Codex` 工作区和 `fyp2/cx-*` 分支 |
| 回放会话 | `/Users/liu/Desktop/FYP2-Constructed-Scenario` | `fyp2/constructed-scenario` | 基线 `276f059` |

### 4.4 同步协议

**状态板**：`/Users/liu/Desktop/FYP2-Live-System/.superpowers/collab/BOARD.md`，被 git 忽略，所有 agent 用绝对路径读写。

- 开工时：读状态板，把自己的 lane 改为 DOING，在消息记录里追加一行。
- 完成时：
  1. 在自己的分支上提交；
  2. 跑本 lane 规定的门禁；
  3. 把状态改为 READY，填上「最新提交」和「门禁 / 证据」；
  4. 追加一行消息。
- 受阻时：状态改为 BLOCKED，在消息里写清缺少的具体依赖，然后停下。
- 合并：由 Claude 完成。Claude 读状态板，审阅 diff，在合并后的代码上跑全量门禁，全绿后合并，然后更新「当前基线」，并把相关 lane 改为 MERGED。
- **你在中间转话。** Codex 与 DeepSeek 不能直接给 Claude 发消息，所以：
  - 某个 agent 说完成了，你就对 Claude 说「同步」，Claude 会读状态板并合并；
  - 某个 lane 被阻塞，你把它的消息原样贴给 Claude。
- **从不 push，除非你明确要求。**
- 每个 agent 都**不碰** 8000 端口、`backend/driver_risk.db*`、ML 工作区，以及其他 lane 负责的文件。

### 4.5 你的操作步骤

1. 把 §5.1 的 prompt 发给 **DeepSeek**，工作目录设为 `/Users/liu/Desktop/FYP2-DeepSeek`。
2. 把 §5.2 的 prompt 发给 **Codex**。
3. 对 **Claude** 说「开始 CL-1」。Claude 会按本文改正后的计划执行 Task 1.1–1.3。
4. 任何一方报告完成后，对 Claude 说「同步」。
5. Codex 交来容差与协议草案后，由你批准（U-1 / U-3），把结论告诉 Claude，Claude 写进状态板。
6. Claude 合并 CL-1 后，会通知你把 §5.3 的 prompt 发给 DeepSeek（DS-1）。
7. Claude 准备好 Stage-1 证据后，把 §5.4 的审计 prompt 发给 Codex。Codex 给出 `VERIFIED_PASS` 后，由你完成 Stage-1 审计。
8. 之后按 4.2 的顺序推进：协议批准 → §5.5 发给 DeepSeek → …… → Stage-5 由你决定。

---

## 5. Prompt（原样复制）

### 5.1 DeepSeek：DS-0 评审验证与修复（现在就可以开始）

```text
你是本项目的实现者之一，工作目录是 /Users/liu/Desktop/FYP2-DeepSeek（git worktree，分支 fyp2/ds-review-fixes，从 fyp2/live-system 的最新提交切出；先运行 git log -1，与状态板上的「当前基线」核对是否一致）。项目是 FYP 原型「In-Cabin Multi-Modal Driver Risk Assessment」：FastAPI + SQLite 后端（backend/app），React 前端（frontend/src），共享的风险逻辑在 ai/src。

先读：
1) ./CLAUDE.md（项目规则：分层、RiskScore 0–100、AlertSeverity FSM、范围红线）；
2) 协作规则与状态板 /Users/liu/Desktop/FYP2-Live-System/.superpowers/collab/BOARD.md；把 DS-0 改为 DOING，在消息记录里追加一行；
3) 待处理清单 /Users/liu/Desktop/FYP2-Live-System/.superpowers/collab/review-2745348/findings.md：独立评审对提交 87d8668..2745348（UI 易用性审查 + 暂缓 Minor 修复）给出的 31 条（R1–R31），尚未全部验证。可以用 git -C . log -3 --format=%B 看提交说明。

任务：
A. 逐条独立复现。用一个测试或一段具体的代码路径（带 file:line）证明它成立，判为 REAL / NOT_REAL / DUPLICATE。疑似重复：R9≈R20、R7≈R10≈R28、R11≈R27、R12≈R19。
B. 修复：
   - REAL 的 Important 必须修。
       - R9/R20：Prepared replay 的 appendReplay 每个 tick 都调用 setSelectedWindowId，导致选择栏一直显示 pinned。修法：删掉那一行，因为 null 本来就表示跟随最新。App 有 hooks，无法静态渲染，可以沿用 frontend/src/components/runtimeNotices.test.ts 里 `import appSource from "../App.tsx?raw"` 的做法，写一条检查源码的测试。
       - R12/R19：告警提示里的时长只描述了挂钟 FSM；Live 后端的 R10 FSM 还要求「服务器时间 AND 新观测的源时间跨度」。措辞要对两种 FSM 都成立，例如「…stays High for 2 s (Live: 2 s of server time and of new observations)」。这只是 frontend/src/utils/display.ts 里的显示文字，测试期望写成字面量。
   - REAL 的 Minor：修复不超过约 20 行、并且明确成立的（主要是补测试和改措辞，例如 R21 的「in every view」改成具体的三个视图）；其余写明理由，记为 deferred。
   - 每个行为修复都先写测试，亲眼看它失败，再修复。
C. 门禁：DRA_REQUIRE_MODELS=1 .venv/bin/python scripts/run_gates.py --out docs/evidence/<今天日期>/ds-review-fixes。必须全绿，0 skipped。写出 pytest 与 vitest 的计数（基线是 1046 / 954）。
D. 报告：docs/fyp2/implementation/review-2745348-fixes.zh.md（中文）。内容包括：
   - R1–R31 每一条：判定、证据、修复提交或 deferred 的理由；
   - 每个修复对应测试「修复前红、修复后绿」的输出摘录；
   - 门禁结果。
E. 在本分支上提交，可以分多个提交，信息用英文。不要 push，不要 merge，不要改 fyp2/live-system。完成后把状态板 DS-0 改为 READY，写上最新提交和门禁结果，追加一行消息。

红线：
- 只改与这 31 条相关的文件；
- 不碰 8000 端口与任何 driver_risk.db*；
- 不改 /Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1（ML 工作区）；
- 不改融合公式、FSM、EMA、R10 的观测逻辑；
- 浏览器端到端测试会自己起服务、用临时库和空闲端口，可以运行；
- 遇到无法判断的事，写进报告的「需要用户决定」一节，不要自己猜。
```

### 5.2 Codex：CX-0 预检与预声明草案（现在就可以开始）

```text
你是本项目 ML 轨道的负责人（P0–P5 由你完成），这次担任系统轨道 Task 10A 的「ML 事实核查与预声明」角色。全程只读：不修改、暂存或提交任何一个工作区里被 git 跟踪的文件，也不清理任何东西。只能在 /Users/liu/Desktop/FYP2-Live-System/.superpowers/collab/codex/ 下写文件（被 git 忽略，Claude 会把它们提交进 docs/fyp2/task10a/）。

先读：
1) 计划 /Users/liu/Desktop/FYP2-Live-System/docs/plans/2026-10-25-task-10a-candidate-integration.md；
2) 分析与改正 /Users/liu/Desktop/FYP2-Live-System/docs/plans/2026-10-26-task-10a-analysis-and-collaboration.zh.md 的第 1–3 节。C-1 到 C-12 优先于计划原文；
3) 规格 /Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/docs/fyp2/11_SYSTEM_INTEGRATION_STAGE_PLAN_AND_AUDIT.md；
4) 状态板 /Users/liu/Desktop/FYP2-Live-System/.superpowers/collab/BOARD.md：把 CX-0 改为 DOING，并在消息记录里追加一行。

产出：
(1) preflight_report.md，即计划的 Phase 0 Step 1–6：
   - 用当日命令输出复核以下各项，每项附命令、exit code 和关键行：
     - Live System 的 HEAD 与 dirty 列表；
     - 两个包的文件与 sha256；
     - 用系统 CLI 校验两份 manifest：先把 backend/app/runtime_manifest.py、runtime_manifest.schema.json、scripts/validate_runtime_manifest.py 原样复制到 /tmp 下的目录（保持目录结构），再用 --package-dir 运行；
     - stable200 的 200 张图片能否找到：data root 是 /Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment-/state-farm-distracted-driver-detection/imgs/train/<class_id>/<filename>；
     - 按规则重新计算成员哈希，应为 601dc3ed…；
     - git diff 2745348 -- backend/app/providers/trained.py 应为空。
   - 给出结论 GO 或 BLOCKED。
(2) tolerance_predeclaration.md：三个模型的验证方案。
   - 稳定 MobileNetV3：参照 p4a_20261021/parity_MN-STABLE.json 的 result.validation_predictions（100 个来源，带 logits）；
   - RN 与 MN 候选：参照各自包里的 validation/stable200_saved_predictions.csv（这是 PyTorch 预测），以及 parity_RN-HPO42.json / parity_MN-HPO42.json；
   - 三个模型都评估 manifest 的 per_class_mode_equals_label 规则。
   - 写清楚：
     - 每个模型的比较量：概率最大绝对差、argmax 一致率；
     - 建议的容差，以及用 P4A 实测数字做的理由；
     - 参照是 PyTorch 输出，而 provider 走自己的 JPEG 解码与 bilinear 缩放路径，这会带来哪些差异，为什么容差能覆盖它们；
     - 先读 Live System 的 backend/app/providers/trained.py 中的 preprocess，对比 ML 侧的验证变换，指出任何可能导致较大差异的不同之处。
   - 容差本身标为 FOR_USER_DECISION，由用户批准后才生效。
(3) comparison_protocol.draft.json：Stage-2 协议草案。
   - 计划 Phase 2 Step 1 列出的每一项都要有，并加上分析文档 C-9 的预声明。这是 D06 意义上的「构造的评估场景」，要写清：
     - 时间基准与窗口间隔；
     - 观测身份；
     - 遥测配对（建议所有窗口用同一条固定遥测行）；
     - 隔离方式（每个模型一个子进程，使用临时 SQLite）；
     - 比较量；
     - 判定口径：只做描述，没有单一分数门槛，替换与否由用户决定。
   - 标为 DRAFT，用户批准之后 runner 才能运行。
(4) 完成后把状态板 CX-0 改为 READY，在消息里列出三个文件的路径，以及所有 FOR_USER_DECISION 项。

红线（来自规格 0.5 与计划第 1 节）：
- 不新增训练、HPO、导出或 benchmark；
- 不改动冻结的 ML 证据；
- 不碰 8000 端口与 driver_risk.db*；
- 不编造任何数字。缺少什么就写 BLOCKED，并写出缺少的确切路径。
```

### 5.3 DeepSeek：DS-1 stable200 runner（等 Claude 通知：CL-1 已合并、容差已批准）

```text
工作目录 /Users/liu/Desktop/FYP2-DeepSeek，分支 fyp2/ds-stable200。Claude 会从最新基线把它切好；你先运行 git log -1，与状态板上的「当前基线」核对是否一致。先读 ./CLAUDE.md、状态板，以及分析文档 docs/plans/2026-10-26-task-10a-analysis-and-collaboration.zh.md 的 C-1、C-3、C-10，再读计划 Task 1.4。容差以 .superpowers/collab/codex/tolerance_predeclaration.md 里**用户已批准**的版本为准，状态板上会注明。

实现 scripts/verify_stable200.py：
- 对每个模型（stable_mobilenet_v3_large、resnet18_search004_seed42、mobilenet_v3_large_search006_seed42）各起一个子进程，用环境变量 DRA_ACTIVE_VISION=<id> 选择模型（stable 为默认），走真实的 provider 路径：TrainedProvider.preprocess(base64 后的原始 JPEG) → provider.vision.run → softmax 一次 → 10 个概率。
- 按已批准的方案与对应参照比较（C-3），同时评估 manifest 的 per_class_mode_equals_label 规则。
- data root 用参数传入。运行前重新计算成员哈希，不一致就退出（C-10）。
- 容差写在脚本的 docstring 里，也写进输出。
- 每个模型输出一个 JSON，再合并为 official_stable200_behavior.json，字段按计划 Task 1.4。
- 失败时如实记录 pass:false 和差异最大的样本，绝不放宽容差。
同时写单元测试（cd backend && PYTHONPATH=. ../.venv/bin/python -m pytest tests/<你的文件> -q），不依赖真实候选包的部分要始终能运行。依赖真实包的测试打 candidates 标记（C-4）。
运行一次：输出写到 docs/evidence/<今天日期>/stable200/。证据 README 要写清三者的区别：ML 侧已存预测的诊断（历史）、P4A parity（历史）、本次 provider 的新鲜 forward（新）。
跑全量门禁（同 DS-0 的命令），提交，不 push。状态板 DS-1 改为 READY。红线与 DS-0 相同。
```

### 5.4 Codex：阶段审计（CX-A1 / CX-A3，等 Claude 通知后使用）

```text
使用计划 §15 的「Reusable auditor subagent prompt」全文。你就是那个独立的、只读的审计者。由 Claude 把以下占位符填好后交给你：N、STAGE-NAME、PHASE-SECTION、EVIDENCE-DIR、COMMITS，以及自审表。
补充规则：
- 测试命令按分析文档 C-1：cd backend && PYTHONPATH=. ../.venv/bin/python -m pytest …；
- 门禁基线按 C-7；
- 真实候选包的测试用 -m candidates 加 DRA_REQUIRE_CANDIDATES=1 运行（C-4）；
- 审计报告写到 /Users/liu/Desktop/FYP2-Live-System/.superpowers/collab/codex/stage<N>_audit.md，最后一行写结论：VERIFIED_PASS / PARTIAL / BLOCKED / FAILED；
- 状态板对应的 lane 改为 READY。
```

### 5.5 DeepSeek：DS-2 对比 runner（等 U-1 通过、协议批准后使用）

```text
工作目录 /Users/liu/Desktop/FYP2-DeepSeek，分支 fyp2/ds-compare。Claude 会切好，你先核对基线。先读 ./CLAUDE.md、状态板、分析文档的 C-1、C-9，以及计划 Phase 2；协议用 docs/fyp2/task10a/comparison_protocol.json，即用户批准后由 Claude 提交的版本，你只读、不改。
实现 scripts/compare_vision_models.py：
- 每个模型一个子进程，设置 DRA_ACTIVE_VISION 和独立的 DRA_DATABASE_URL（临时 SQLite）；
- 用 FastAPI TestClient 按协议的时间基准、观测身份与遥测配对逐帧调用 /infer，走完整的 R10 / EMA / FSM 管线；
- 把每个窗口的 RiskScore、RiskLevel、DominantEvidence、AlertSeverity、argmax、概率导出，合并为 comparison_results.json；
- 结果里记录协议文件的 sha256，以及输入哈希的重算值。
- 先确认协议文件的 mtime 早于运行时间。如果两个模型的结果完全相同，说明 runner 有问题，先查清楚。
写单元测试（合成模型或 stub provider），跑全量门禁，提交，不 push，状态板 DS-2 改为 READY。只描述结果，不挑胜者，不切换默认模型。
```

---

## 6. Claude 在 CL-1 里会做什么

按计划 Task 1.1–1.3 并加入改正 C-1、C-2、C-4、C-5、C-7、C-8，每一步先写测试、亲眼看它失败。完成后会有：

- 候选包复制到 `ml/outputs/candidates/` 并加上 index；
- `DRA_ACTIVE_VISION` 开关（默认 stable）；
- `app/vision_candidates.py`；
- provider 接线，窗口多两个字段 `vision_model_id`、`vision_model_sha256`；
- 前端模型名从 `/api/models` 读取；
- `candidates` 标记。

**XGB 与遥测相关的每一行都保持不变**，用 `git diff 2745348 -- backend/app/providers/trained.py` 证明。
