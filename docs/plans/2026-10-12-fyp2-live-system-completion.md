# FYP2 Live-Only System Completion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 FYP2 系统做完整 —— 修复 unavailable / zero-effective-weight 数据契约，把 Live Monitoring 确立为唯一主运行时，实现有界重试与可观测故障恢复，并用可复现的端到端回归证明它。

**Architecture:** 单一权威链路 `摄像头帧 + prepared raw telemetry → POST /sessions/{id}/infer → MobileNetV3 ONNX + XGBoost → freshness/EMA/late fusion/Alert FSM → SQLite → React 五视图`。融合契约的唯一真相在 `ai/src/`（TypeScript），`backend/app/fusion.py` 与 `ai/reference/risk_logic.py` 是它的两份移植，三者由一份**共享数值夹具**锁定。前端只渲染后端返回的 canonical 记录，不再自行重算。

**Tech Stack:** TypeScript / React 18 / Vite 6 / Vitest 2；Python 3.13 / FastAPI / SQLAlchemy 2 / SQLite / pytest；ONNX Runtime + XGBoost（模型冻结不动）；Playwright 1.60（已在 `.venv`，无需新增 npm 依赖）。

**Spec:** `docs/fyp2/00_AUDIT_EXECUTIVE_SUMMARY.md` 的 B01–B05，`docs/fyp2/02_TEST_CASE_INVENTORY_AND_CRITIQUE.md` 的最小补测包，`docs/fyp2/06_WEEK7_CRITICAL_PATH_AND_ACTION_PLAN.md` 的工作包 A01–A05 与 Week 7 签收清单，`docs/fyp2/08_OPEN_DECISIONS_FOR_SUPERVISOR.md` 的 D01/D02/D11。执行者必须同时阅读本计划与上述文档。

---

## Global Constraints

本节的每一条都隐含在每个 task 的要求里。数值一律逐字取自 spec / 已验证的源码。

- **RiskScore 量纲 0–100**，阈值 `low=30` / `high=60`（`score < 30` Low，`30 ≤ score < 60` Medium，`score ≥ 60` High）。**先 round 到 1 位小数，再映射等级** —— 顺序不可换。
- **舍入规则：统一为 ROUND_HALF_UP（阶段 1 F4 写回）**。RiskScore 保留 **1 位**小数，EMA 平滑值保留 **3 位**小数。
  - **实现位置（已存在）**：Python 在 `backend/app/fusion.py` 与 `ai/reference/risk_logic.py` 中的 `round_half_up(value, places)`，做法是 `Decimal(str(value)).quantize(..., rounding=ROUND_HALF_UP)`；TypeScript 在 `ai/src/riskLogic.ts` 导出的 `roundHalfUp(value, places)`。两种语言（Python、TypeScript）、三份实现逐值一致。
  - **禁止**：在 score、概率、EMA 值上使用 Python 内置 `round()`（banker's rounding），或 JS 的 `toFixed` / `Math.round(v*100)`。前端显示 score、概率、EMA 值一律用 `roundHalfUp`。后续任何 task（含 Task 7–10 的实现与测试）不得重新引入这些写法，否则跨语言分歧回归。
  - **这是有意的数值改变（Codex 审阅 R30 确认），不是 bug**：相对旧 Python 实现改变了约 17.0% 的分数网格，相对旧 TS 实现约 13.0%，有 556 个网格点的 RiskLevel 改变（1,001×1,001 网格）。
  - **来源**：Task 5 的控制者裁定（SDD ledger），Codex 审阅 R30 确认，阶段 1 F4 写回本计划与 SDD `global-constraints.md`。Task 5 小节及其 SDD brief 中「不要顺手整理 EMA 的舍入」一句是旧指示，已被本条取代，以本条为准。
- **freshness 权重**：`fresh=1.0`、`stale=0.45`、`missing=0.0`；容差 3 秒，`age > 3` 才是 stale（3.000s 仍 fresh，严格 `>`）。
- **有效分母** `denominator = w_v·fw(vision_status) + w_t·fw(telemetry_status)`。`RuntimeConfig` 允许权重和偏离 1 达 `1e-6`，因此判零必须用**声明过的 epsilon**（`FUSION_EPSILON = 1e-9`），不能写 `== 0`。
- **EMA** `alpha=0.35`，仅在 vision 为 `fresh` 且存在 previous 值时应用。**seed 约定 = seed-on-first-sample**（首帧 raw 直接作为 previous）；`0.2 → 1.0` 的第二个平滑值是 `0.48`（seed-at-0 会得 `0.3955`）。**R1 已对三份实现逐一核实，发现两处真实分歧，Task 5 必须消除**：

  | 维度 | `backend/app/inference.py:34-36` | `ai/src/riskLogic.ts:158-164` | `ai/reference/risk_logic.py:90-94` |
  |---|---|---|---|
  | seed 约定 | seed-on-first-sample ✅ | seed-on-first-sample ✅ | seed-on-first-sample ✅ |
  | **首帧是否 round3** | ❌ **不 round**（round 只在 EMA 分支内） | ✅ 两个分支都 round | ✅ 两个分支都 round |
  | **stale/missing 之后的重新初始化** | `previous_vision` 被置 `None`（`:57`）→ 下一个 fresh 窗口**重新 seed，不做 EMA** | `previousRecord` 恒存在，只看当前窗口是否 fresh → 下一个 fresh 窗口**会拿 stale 窗口的值做 EMA** | n/a（无状态函数） |
  | restart 之后 | `runtime_state` 是持久化 JSON 列，EMA 链跨重启存活；但 `:31` 的 gap 分支在间隔 > 3s 时清空（实际重启必然 > 3s，所以等价于重新 seed） | localStorage 日志恒存在 → 跨重载继续 EMA | n/a |

  两处分歧都会让同一串输入在前后端算出不同的 `P_distraction`。**R1 裁定：以 Python 后端的语义为准**（后端是 canonical 产出方），即：首帧**不** round（保持 provider 原始精度），stale/missing 之后**重新 seed 不做 EMA**。TS 侧改为匹配。注意 `test_audit_regressions.py:139` 与 `test_restart.py:44`（钉死 `.312`）依赖现有 Python 行为，裁定方向正是「不动 Python」，这两个测试应保持绿。
- **Alert FSM 三态** `NORMAL / CAUTION / HIGH_ALERT`：High 持续 `>= 2000ms` 升 HIGH_ALERT（1900ms 仍 CAUTION），Low 持续 `>= 10000ms` 回 NORMAL（9900ms 保持原 severity），Medium 立即 CAUTION 且清空 High streak。测试中 **2000 / 10000 必须硬编码**，不得从实现 import 常量。
- `P_telemetry_anomaly` 是保留的历史字段名 = `1 − P(Safe)`，**不是**无监督异常检测。不得改名。
- **遥测 8 特征固定顺序**：`speed_kmph, accel_x, accel_y, brake_pressure, steering_angle, throttle, lane_deviation, headway_distance`。
- 只做 **decision-level late fusion**。权重是透明设计参数，不是学习出来的安全权重；`RiskLevel` 是派生的运行等级，不是事故严重度标签。
- 数据库只用 **SQLite**。不得引入 Flask-SocketIO / APScheduler / Hydra / OmegaConf。
- **本阶段不做任何模型工作**：不训练、不调参、不加 ResNet18 / RF / LR、不跑 E1–E5。这些属于并行的 ML 开发轨道。**R3 补充**：Task 10A 同样**不训练、不调参**，它只对 ML 轨道交付的冻结候选模型包做兼容性检查与离线影子评估。遥测的部署模型固定为 XGBoost；Random Forest 与 Logistic Regression **只用于 benchmark，运行时永不加载**。
- **模型 checkpoint 必须原封不动（R1 新增，硬约束）**：`ml/outputs/vision/mobilenetv3_large_vision.onnx`（SHA256 `b3a42e8d…`）、`mobilenetv3_large_vision.pt`（`196ca7b1…`）、`ml/outputs/telemetry/xgb_telemetry.json`（`9802cb06…`）**只读**。任何 task 都不得覆写、移动、重新导出或重新量化它们。Task 1 的 manifest 记录基线哈希；Task 10 的最终门禁必须重新计算并断言三个哈希未变。模型文件保持 git-ignored —— 只记哈希，不入库。**R3 补充**：Task 10A 引入的版本化发布同样受此约束 —— 任何候选模型都以**新的版本目录**发布，绝不覆盖、移动或改写这三个稳定产物；Task 10A 的门禁同样要断言三个基线哈希未变。
- **后端产出 canonical RiskUpdate（R1 新增，硬约束）**：`RiskScore` / `RiskLevel` / `DominantEvidence` / `AlertSeverity` / `SystemHealth` / `assessment_available` 的**唯一**产出方是后端 `inference.run_inference()`。前端**只渲染**该记录，不得自行重算风险评估。当前违规点：五个视图全都用 `getEvidenceType()` 重算 `DominantEvidence`，`ExplanationView` 还用 `computeRiskContributions()` 重算贡献度，`LiveMonitor.tsx:45` 更是凭前端的 `stale` 标志伪造 `SystemHealth = "UNAVAILABLE"`。Task 6 必须全部改为读记录字段；`ai/src` 的纯函数保留给保留的 replay 路径与单元测试使用。
- **D13（证据最大可用年龄 / stale-only 告警累积）不在本阶段修复，但必须作为「已知限制」显式追踪 —— R1 强化。**

  机理：`inference.py:13-18` 对任何提供了时间戳的分支永远只返回 `stale`、不会变 `missing`，所以任意旧的证据会一直以 0.45 权重参与融合、持续累积 sustained-High，最终触发 `HIGH_ALERT`。D01 修好之后这个洞会**看起来像已经解决**。

  ~~**R1 新发现，显著改变风险画像**：Live 主运行时**目前根本到不了 stale**。`trained.py:122-123` 只会输出 `fresh`（有输入）或 `missing`（无输入），而前端对两路都打 `new Date()` 当时间戳 —— 所以 Live 路径里 `age` 恒为 ~0。**D13 只能经由保留的 replay 路径或直接 POST `/windows` 触发，不是主运行时的在役缺陷。**~~

  **R4 更正（Codex 独立审阅 R08 判 INCORRECT，已核实）**：上一段是错的。`run_inference` 用 `provenance.captured_at` / `telemetry_timestamp` **重新判定** freshness（`backend/app/inference.py:107-108`），不依赖 provider 给的 `fresh`。`backend/tests/test_live_inference.py:114-117` 本身就断言：旧 `captured_at` 经 `POST /infer` 得到 `stale` 与 `DEGRADED`。正常浏览器操作下 age 接近 0，但网络或处理延迟超过 3 秒、客户端时钟偏差、或任何直接调用 `/infer` 的客户端都能让 Live 出现 stale。**因此 D13 在 Live 主运行时可达**，其优先级由「System Freeze 前再决定」提升为待用户裁定的政策项（见 R4 记录）。

  **本阶段的义务（不是修复，是留证）**：
  1. Task 5 必须新增 `UT-TIME-06 (stale-only stream)`：用注入时钟喂一串**只有 stale 证据**、分数持续在 High 区间的窗口，断言并记录**当前**行为（即会累积到 `HIGH_ALERT`）。该测试是行为快照，不是期望行为 —— 测试名与注释必须写明这是已知限制的留证。
  2. Task 10 的证据归档必须包含该测试输出。
  3. 报告与任何对外陈述**不得声称系统已完整处理过期证据**。
  4. 在 System Freeze 前再决定是否实现 Maximum Evidence Age 或 Stale-Only Alert Guard；该决定不属于本 10 个 task。
- **不删除任何现有功能**。prepared-probability replay 保留给回归测试与向后兼容，只降级、不移除。
- 三份融合实现必须同步：`ai/src/riskLogic.ts` + `ai/src/evidence.ts`（权威）、`backend/app/fusion.py`、`ai/reference/risk_logic.py`（报告引用的语言无关规范）。**它现在有测试守护**（阶段 1 P1-2 更正，此前写作「零 importer，不会有任何测试因它漂移而失败」）：`backend/tests/test_fusion_vectors.py` 经 importlib 加载它，`backend/tests/test_temporal_contract.py` 再从前者 import 它；把它的 `round_half_up` 改成内置 `round`，会让 pytest 失败（Codex 审阅在 `e326449` 实测 25 个；F4 追加舍入用例之后，P1-2 在 `9db6e2a` 的干净归档上复测为 27 个）。
- **门禁命令（精确形式，阶段 1 F4 更新）**：在 `/Users/liu/Desktop/FYP2-Live-System` 下依次运行
  ```
  export PYTHONDONTWRITEBYTECODE=1
  (cd backend && TMPDIR=$(mktemp -d) PYTHONPATH=. ../.venv/bin/python -m pytest tests -q -p no:cacheprovider)
  ./node_modules/.bin/vitest run --no-cache
  ./node_modules/.bin/tsc --noEmit
  ./node_modules/.bin/eslint .
  ```
  原因：本机 `rtk` 包装器会改写 `npx`，所以一律直接调用 `./node_modules/.bin/*`；vitest 加 `--no-cache`，避免它经 `node_modules` 符号链接写入只读的主仓库。后端测试一律用一次性 `TMPDIR`，不得碰真实数据库。**`npm test` 不做类型检查**，`tsc` 必须单独跑。

### 已拍板的契约（不得再议）

```
RiskUpdate 新增 assessment_available: bool（必填）
RiskScore / RiskLevel / DominantEvidence / AlertSeverity → 可为 null
SystemHealth 保持必填且非空

不变式：
  assessment_available === (RiskScore !== null) === (SystemHealth !== "UNAVAILABLE")
  且 assessment_available === false 时，上述四个字段同时为 null

SystemHealth 规则：
  denominator <= FUSION_EPSILON          → "UNAVAILABLE"
  否则 vision_status 或 telemetry_status 任一 != "fresh" → "DEGRADED"
  否则                                    → "FULL"
```

**显式钉死的边界**：零权重但该分支非 fresh 时（如 `w_t=0` 且 telemetry missing、vision fresh），`denominator = w_v = 1.0 ≠ 0`，所以结果 **available**，health 为 **DEGRADED**，dominant 为 **"Partial evidence"**（即 FULL/DEGRADED 边界只看 freshness 状态，不看权重）。这就是夹具 `F-Z3`。

`P_distraction` / `P_telemetry_anomaly` **不**变成可空：缺失分支仍被替换成 `0.0`（`inference.py:34,37`）。诚实的原始值在 `provenance.P_distraction_raw` / `P_telemetry_raw`。这是 B01 在下一层的残留，本阶段用 `modality_freshness` + 导出列消化，不改这两个字段的类型。

### 失败策略（D02 —— R1 修订，已消除 Task 7/8 矛盾）

**预算定义（R1 澄清）：`MAX_ATTEMPTS_PER_REQUEST = 3`，指一个逻辑请求最多 3 次投递 —— 1 次首发 + 最多 2 次自动重试。**原名 `MAX_ATTEMPTS_PER_REQUEST` 歧义（3 次失败还是 3 次重试？），改名并以「总投递次数」为准。第 3 次仍失败即进入 stopped 态，不再自动重试。

**退避表（R1 修订）**：只有两次退避会真正发生。

| 事件 | 退避 | 说明 |
|---|---|---|
| 第 1 次投递失败 → 第 2 次 | `2000 ms` | `1000 · 2^1` |
| 第 2 次投递失败 → 第 3 次 | `4000 ms` | `1000 · 2^2` |
| 第 3 次投递失败 | —— | 停止，不再排定时器 |

原文写的 `min(1000 · 2^n, 10000)` 上限 **10000 ms 在 3 次投递下永远达不到**（最大 4000 ms），属于死代码。保留公式但在实现里注明上限仅为防御性保护；测试只断言 2000 / 4000 两个值，**不得断言 8000** —— `backoffMs(3)` 永远不会被调用。

**错误分类（R1 修订 —— 原 Task 7 把 503 当可重试，与 Global Constraints 的「503 不可重试」直接冲突；按用户裁定如下解决）**：

| 情形 | HTTP | 可重试 | category | 处理 |
|---|---|---|---|---|
| 非法输入（坏 base64、越界概率、schema 不符） | 400 / 422 | ❌ | `input` | 立即停止，要求用户修正输入 |
| 会话不存在 | 404 | ❌ | `not_found` | 立即停止；重试将新建会话（UI 必须说明） |
| request_id hash 冲突 | 409 | ❌ | `conflict_hash` | 立即停止 —— 同 id 不同内容是程序错误 |
| 证据时间戳乱序 | 409 | ❌ | `conflict_stale_frame` | 立即停止；**与上一行区分**，UI 文案不同 |
| **模型文件缺失 / 无法加载** | **503** | **❌** | `models_unavailable` | **立即停止**，要求用户修复部署配置。重试无意义 —— 文件不会自己出现 |
| **模型执行期异常**（前向推理抛错） | **500** | **✅** | `model_runtime` | 有限重试。后端必须用**不同的状态码**把它与「模型缺失」分开，否则客户端无法区分 |
| 存储失败（commit 失败、DB 锁） | 500 | ✅ | `storage` | 有限重试 |
| 网络断开 / fetch rejection | —— | ✅ | `transport` | 有限重试 |
| 请求超时（10s tick / 15s client） | —— | ✅ | `timeout` | 有限重试 |
| 用户 pause / unmount 导致的 abort | —— | —— | `aborted` | **不计数**，不是失败 |

**由此产生的后端要求（Task 7 必须实现）**：`trained.py` 现在把「模型文件缺失」和「模型执行期异常」都归到 `ModelUnavailable → 503`。R1 要求拆开：缺失/加载失败保持 503 + `models_unavailable`；**执行期异常改为 500 + `model_runtime`**。`ST-RECOVER-01` 的三次可重试失败必须用 `model_runtime`(500) 或 `transport` 注入，**不能再用 503**。

- 停止后进入可见的 stopped 态 + 手动 Retry；成功后计数器清零。
- 每次失败写一条持久 fault event（request_id、时间戳、category、attempt_index ∈ {1,2,3}、recovery status）。
- 重试不得产生重复 risk 记录 —— 见下方「重试身份」。

### 重试身份（R1 强化，D02 第 9 项）

一个**逻辑请求**在其全部重试中必须保持**逐字节相同**的 payload：同一个 `request_id`、同一个 `image_base64`、同一个 `captured_at`、同一组 `telemetry_features`、同一个 `telemetry_timestamp`。

理由是服务端的两道门：幂等键是 `request_hash = sha256(json.dumps(payload, sort_keys=True))`（`windows.py:95`），同 id 不同 hash → 409；而 `runtime_state` 保存每分支单调时间戳，更早的时间戳 → 409（`windows.py:51-58`）。所以「只保住 request_id、重新采帧」会把每次重试都变成 409，而 409 不可重试 —— 直接停机。

实现上：整个 `LivePayload` 在**首次投递前**构造一次并存入 ref，重试原样重发；只有在该逻辑请求成功、或预算耗尽进入 stopped 态之后，才允许构造下一个 payload。

### CSV / JSON unavailable 表示（R1 统一 —— 前后端必须一致）

| 字段 | CSV（后端 `export.py` 与前端 `utils/export.ts` 一致） | JSON |
|---|---|---|
| `RiskScore` | 空单元格 | `null` |
| `RiskLevel` | 空单元格 | `null` |
| `DominantEvidence` | 空单元格 | `null` |
| `AlertSeverity` | 空单元格 | `null` |
| `assessment_available` | `false` | `false` |
| `SystemHealth` | `UNAVAILABLE` | `"UNAVAILABLE"` |

原计划里后端写空单元格、前端写字面量 `unavailable`，两者会对同一个窗口给出不同的 CSV —— R1 统一为**全部空单元格**。空单元格本身有歧义（也可能是缺字段），消歧义由同一行的 `assessment_available=false` 与 `SystemHealth=UNAVAILABLE` 承担，这两列**必须始终有值**。布尔一律小写 `true` / `false`，两端一致。

---

## Review Focus

spec 没有明说、但没有任何 task 的测试会自然覆盖、且最可能在真实使用中咬人的五类输入。每一条都已指派给拥有该代码的 task，并在那里以该 task 的步骤风格补了测试。

1. **改契约之前就已落盘的历史记录。** SQLite `inference_records.payload` 和浏览器 localStorage 里的记录都没有 `assessment_available` 键。所有读路径都用 `RiskUpdate(**rec.payload)` 重建对象（`windows.py:19`、`risk.py:24`、`export.py:36`），所以一个无默认值的必填字段会让每条历史记录读取时 500 —— 而 `export.py` 是流式的，客户端会在已发出 200 之后收到被截断的坏 JSON。更坏的是历史上 health 为 `UNAVAILABLE` 的行里存着 `0 / "Low" / "NORMAL"`，正好违反新不变式。→ Task 4（SQLite，before-validator + 迁移双保险）、Task 6（localStorage 读时归一化）。
2. **权重和的 1e-6 容差让「零分母」不是精确零。** `schemas.py:101` 接受 `abs(w_v + w_t - 1) <= 1e-6`，所以 `(5e-7, 0.999999)` 是合法配置；vision fresh + telemetry missing 时分母是 `5e-7`，不是 0，整个 D01 不变式被一个舍入容差绕过。→ Task 2 / Task 3（`FUSION_EPSILON` 作为契约参数）。
3. **客户端时钟快于服务端 5 秒以上会让 Live 直接死掉。** `captured_at` 与 `telemetry_timestamp` 都来自浏览器时钟，`normalize_timestamp` 对超前 >5s 的时间戳抛错 → 422 → 按 D02 属不可重试 → 监控立刻停止，且报错文案是不透明的 "Inference request failed"。→ Task 8（专门的 error category 与文案）。
4. **重试时的时间戳与幂等键。** 服务端用 `request_hash = sha256(payload)` 做幂等（`windows.py:95`），同 id 不同 hash 直接 409；同时 `runtime_state` 保存每分支单调时间戳，更早的时间戳也 409（`windows.py:51-58`）。而当前每个 tick 都重新 `crypto.randomUUID()`、重新 `captureFrame()`、重新打 `new Date()` 时间戳 —— 所以「保留 request_id」的天真改法会把每次重试都变成 409。相等（而非更早）的时间戳则能通过，可以无限累积告警时长。→ Task 8（冻结整个 payload）、Task 5（相等时间戳的累积断言）。
5. **写 fault 这件事本身失败时。** SQLite 单写者：在失败事务尚未 rollback 时用第二个连接写 fault，会阻塞到 `busy_timeout=15000` 然后报 "database is locked"；而 fault sink 如果绑在模块级 `SessionLocal` 上，测试里会写进开发者的真实数据库。→ Task 7（先 rollback 再写、绑 `db.get_bind()`、文件 sink 兜底、断言原始异常原样抛出）。

---

## File Structure

### 新建

| 文件 | 职责 |
|---|---|
| `ai/src/availability.ts` | 共享纯函数：有效分母、可用性判定、三态显示状态、不变式断言。**唯一**的 unavailable 判定来源 |
| `ai/fixtures/fusion_vectors.json` | 21 行跨语言数值夹具，Python 与 TypeScript 两套测试都读它 |
| `ai/src/liveLoop.ts` | 从 React 抽出的纯采集循环驱动（注入 api / captureFrame / clock），使 D02 可在 node 环境下测 |
| `frontend/src/api/retryPolicy.ts` | `MAX_ATTEMPTS_PER_REQUEST`、`classifyFailure`、`backoffMs` —— 纯函数，可测 |
| `backend/app/faults.py` | `record_fault` / `mark_recovered` / `open_fault_count` + 独立文件 sink |
| `backend/app/routers/faults.py` | `GET /api/faults`、`GET /api/sessions/{id}/faults`、`POST /api/faults`（**不**以 session 存在为前提） |
| `backend/tests/conftest.py` | 统一 tmp DB fixture，终结 `test_api.py` 的固定路径与收集顺序耦合 |
| `backend/tests/test_unavailable_contract.py` | UT-FUS-03 / UT-FUS-ZERO-WEIGHT / EX-NULL-01 / ST-STATUS-01 |
| `backend/tests/test_fusion_vectors.py` | 21 行夹具的 Python 侧断言 |
| `backend/tests/test_temporal_contract.py` | UT-TIME-01/02/03 + unavailable 期间 FSM 暂停 |
| `backend/tests/test_fault_events.py` | ST-FAIL-01/02/03、ST-RECOVER-01 |
| `backend/tests/test_live_e2e.py` | Playwright 驱动的完整 Live 端到端（零 npm 依赖） |
| `ai/src/availability.test.ts` `ai/src/fusionVectors.test.ts` `frontend/src/api/retryPolicy.test.ts` `ai/src/liveLoop.test.ts` `frontend/src/utils/export.test.ts` | 对应单测 |
| `docs/fyp2/release/RELEASE_MANIFEST.md` + `scripts/freeze_manifest.py` | 源码 / 模型 / split / 依赖的 SHA256 清单（B05） |
| `prototype-tests/live_e2e.md` | 取代 replay checklist 的 Live 端到端人工验收单 |

### 修改（按层）

- **契约核心**：`ai/src/types.ts`、`ai/src/riskLogic.ts`、`ai/src/evidence.ts`、`ai/src/alertFsm.ts`、`ai/reference/risk_logic.py`、`backend/app/fusion.py`、`backend/app/inference.py`、`backend/app/schemas.py`
- **持久化与接口**：`backend/app/models.py`、`db.py`、`cache.py`、`main.py`、`routers/{windows,risk,status,export}.py`、`backend/requirements.txt`
- **前端展示**：`frontend/src/utils/{format,export,persistence}.ts`、`components/{Pill,ScoreGauge,AlertBanner,TrendChart}.tsx`、`views/{LiveMonitor,SignalInspector,RiskTrends,ExplanationView,ConfigurationView}.tsx`、`styles.css`
- **前端采集**：`frontend/src/api/client.ts`、`hooks/useLiveSession.ts`、`hooks/useCameraPreview.ts`、`App.tsx`、`data/preparedSessionInput.ts`
- **测试与配置**：`vitest.config.ts`、`eslint.config.js`、`ai/src/riskLogic.test.ts`、`ai/src/alertFsm.test.ts`、`frontend/src/data/preparedSessionInput.test.ts`、`backend/tests/test_{api,live_inference,migration,audit_regressions}.py`
- **文档**：`AGENTS.md`（恢复）、`CLAUDE.md`、`README.md`、`frontend/README.md`、`prototype-tests/README.md`

---

## 已验证的跨语言数值夹具

这 21 行由一个独立 agent 用精确有理数（`fractions.Fraction`）**从公式重算**，不引用任何实现或现有测试，结论 **CONFIRMED，零分歧**。它们是 `ai/fixtures/fusion_vectors.json` 的全部内容。

| id | pD | pT | w_v | w_t | vision | telemetry | available | score | level | health | dominant |
|---|---|---|---|---|---|---|---|---|---|---|---|
| F-W1 | .1 | .9 | .5 | .5 | fresh | fresh | true | 50 | Medium | FULL | Telemetry-dominant |
| F-W2 | .1 | .9 | .6 | .4 | fresh | fresh | true | 42 | Medium | FULL | Telemetry-dominant |
| F-W3 | .1 | .9 | .4 | .6 | fresh | fresh | true | 58 | Medium | FULL | Telemetry-dominant |
| F-W4 | .1 | .9 | .7 | .3 | fresh | fresh | true | 34 | Medium | FULL | Telemetry-dominant |
| F-W5 | .1 | .9 | .3 | .7 | fresh | fresh | true | 66 | High | FULL | Telemetry-dominant |
| F-S1 | .1 | .9 | .5 | .5 | stale | fresh | true | 65.2 | High | DEGRADED | Partial evidence |
| F-S2 | .1 | .9 | .5 | .5 | fresh | stale | true | 34.8 | Medium | DEGRADED | Partial evidence |
| F-S3 | .1 | .9 | .5 | .5 | stale | stale | true | 50 | Medium | DEGRADED | Partial evidence |
| F-M1 | .1 | .9 | .5 | .5 | missing | fresh | true | 90 | High | DEGRADED | Partial evidence |
| F-M2 | .1 | .9 | .5 | .5 | fresh | missing | true | 10 | Low | DEGRADED | Partial evidence |
| F-M3 | .1 | .9 | .5 | .5 | stale | missing | true | 10 | Low | DEGRADED | Partial evidence |
| F-M4 | .1 | .9 | .5 | .5 | missing | stale | true | 90 | High | DEGRADED | Partial evidence |
| F-U1 | .1 | .9 | .5 | .5 | missing | missing | **false** | null | null | UNAVAILABLE | null |
| F-Z1 | .1 | .9 | 1.0 | 0.0 | missing | fresh | **false** | null | null | UNAVAILABLE | null |
| F-Z2 | .1 | .9 | 0.0 | 1.0 | fresh | missing | **false** | null | null | UNAVAILABLE | null |
| F-Z3 | .1 | .9 | 1.0 | 0.0 | fresh | missing | true | 10 | Low | DEGRADED | Partial evidence |
| F-T1 | .299 | .299 | .5 | .5 | fresh | fresh | true | 29.9 | Low | FULL | Low observed risk |
| F-T2 | .3 | .3 | .5 | .5 | fresh | fresh | true | 30 | Medium | FULL | Combined evidence |
| F-T3 | .599 | .599 | .5 | .5 | fresh | fresh | true | 59.9 | Medium | FULL | Combined evidence |
| F-T4 | .6 | .6 | .5 | .5 | fresh | fresh | true | 60 | High | FULL | Combined evidence |
| F-T5 | .29951 | .29951 | .5 | .5 | fresh | fresh | true | 30 | Medium | FULL | Combined evidence |

复算附带的三条警告，必须写进实现：

1. **审计文档里的 `/1.45` 写法不通用。** `(0.45·0.1 + 0.9)/1.45` 只在 `w_v = w_t = 0.5` 时等价于 `eff_v/eff_t` 形式，因为相等权重被约掉了。在 `(0.6, 0.4)` 下 vision-stale 的真实有效占比是 `0.6·0.45/(0.6·0.45+0.4) = 0.40298507`，不是 `0.3103448`。实现与任何新夹具一律用 `eff_v / eff_t` 分母。
2. **没有任何一行落在舍入半点上。** 21 行分别用 `ROUND_HALF_UP`、`ROUND_HALF_EVEN`、Python `round()`、JS `Number(x.toFixed(1))` 四种路径跑过，结果全部一致，所以两套测试不会因 banker's rounding 分歧。往夹具里加新行时必须重做这项检查。
3. **`F-T5` 是「先 round 再映射」的唯一守卫。** 精确值 `29.951` 在 round 前 `< 30`；只有先 round 成 `30.0` 才得到 Medium。若实现改成对未舍入的 score 映射等级，这一行会变成 Low / "Low observed risk"。

---

## Task 1：冻结基线、清理 AGENTS.md 引用、确认工作目录

**Files:**
- Create: `scripts/freeze_manifest.py`、`docs/fyp2/release/RELEASE_MANIFEST.md`、`backend/requirements.lock.txt`
- Modify: `CLAUDE.md`（清理 AGENTS.md 悬挂引用）、`eslint.config.js`、`backend/requirements.txt`、`backend/requirements-inference.txt`
- Delete: `AGENTS.md` —— **用户已删除，只需在授权后把该删除纳入 commit，不要恢复**

**Interfaces:**
- Produces：一个从 `dev_cc` HEAD 切出的干净工作树，所有后续 task 在其中执行；一份把源码 / 模型 / split / 依赖钉死的 manifest。

**前置事实：** `dev_cc` 已是 `845b43a`，工作区干净，8 个 commit 已在 `origin/dev_cc`。当前会话所在的工作树 `claude/audit-files-dev-plan-ed0c73` 停在 `17c4b41`，**不含任何 live 运行时代码**，不能在其中实现。

- [ ] **Step 1：确认工作目录（R2 —— 用户裁定改用隔离工作树）**

R1 曾裁定「直接在主仓库 dev_cc 开发」。**用户于 2026-10-12 推翻该裁定**，理由是另一个工作树将并行用于 ML 开发，必须隔离。控制者已在派发前完成以下准备，实现 agent 只需**核实**，不要重做：

| 项 | 值 |
|---|---|
| 工作树 | `/Users/liu/Desktop/FYP2-Live-System` |
| 分支 | `fyp2/live-system`（从 `dev_cc` @ `845b43a` 新建） |
| 主仓库 | `/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1` @ `dev_cc` —— **只读，禁止任何写入** |
| 模型 | 三个 checkpoint 以**符号链接**接入 `ml/outputs/`，指向主仓库，只读 |
| `.venv` / `node_modules` | 符号链接到主仓库，已加入 `.git/info/exclude` |
| 已验证基线 | pytest 28 passed / vitest 32 passed / `tsc` clean / `eslint ai frontend` clean |
| 模型 SHA256 基线 | onnx `b3a42e8d…`、pt `196ca7b1…`、xgb `9802cb06…` —— 与审计记录逐一相符 |
| 开发数据库 | **不存在**（全仓库无 `.db`/`.sqlite` 文件），故无需备份；Task 4 只能对一次性副本做迁移 |

```bash
cd /Users/liu/Desktop/FYP2-Live-System
git rev-parse --short HEAD && git branch --show-current   # 期望 845b43a / fyp2/live-system
```

**禁止**：reset / clean / merge / cherry-pick / push；禁止写主仓库；禁止触碰 `~/.codex/worktrees/` 下三个陈旧工作树。
每个 task 末尾允许**一次本地 commit**，仅限 `fyp2/live-system` 分支。

- [ ] **Step 2：`AGENTS.md` 已被用户删除 —— 只需清理悬挂引用**

用户已于 2026-10-12 删除 `AGENTS.md`（`git status` 显示 ` D AGENTS.md`，未提交）。**不要恢复它。** 此前关于「可能是误删」的分析到此结束：这是用户的明确决定。

历史内容仍可取回（`git show 0113b61:AGENTS.md`，647 行 / 20,275 字节），但本阶段不恢复、不归档。

**必须做的只有一件事**：清理指向它的悬挂引用，否则文档会指向一个不存在的文件。
- `CLAUDE.md:122` 写着「`AGENTS.md` contains the applicable project instructions」—— 必须删除或改写。
- `CLAUDE.md:107` 的小节标题是「Scope guardrails (from AGENTS.md — keep the project on-route)」—— 该节内容已内联在 CLAUDE.md 自身（:109-119），改标题去掉来源引用即可，**内容不要动**。
- `PROJECT_MEMORY.md:518` 的目录树列出了 `AGENTS.md` —— 按「文档暂不整改」的决定**保持原样**，仅在本计划里登记为已知陈旧项。
- `docs/FYP2_CLAUDE_DEVELOPMENT_HANDBOOK.zh.md:17`、`docs/IMPLEMENTATION_PROGRESS.zh.md:98`、`ml/experiments/README.md:81` 提到「保留用户对 AGENTS.md 的修改」—— 同样保持原样，登记即可。

提交删除本身需要用户授权（见 Step 7）。

- [ ] **Step 3：修掉会误报的 lint 门禁**

`eslint.config.js` 的 `ignores` 只有 `["dist", "node_modules", ".venv"]`，于是 `eslint .` 会走进 `.claude/worktrees/…` 去 lint 陈旧副本并报错。加入 `".claude"`。

验证：`./node_modules/.bin/eslint .` 退出 0（修复前在存在工作树时报 2 个 `prefer-const`，来源是工作树里的旧 `alertFsm.test.ts`）。

- [ ] **Step 4：写 freeze manifest 脚本**

`scripts/freeze_manifest.py`，无参数运行，输出 Markdown 到 stdout：git HEAD 与 dirty 状态；`ml/outputs/` 下模型文件（git-ignored）的 SHA256 与字节数；`eda_outputs/processed/**/*.csv` split 文件的 SHA256 与行数；`.venv` 实际安装版本（非 requirements 下界）；node/npm 版本。模型二进制**不入库**，只记哈希 —— 这是 B05 的解法。

- [ ] **Step 5：补齐 Python 依赖声明**

`backend/requirements.txt` 没有声明 `numpy`、`Pillow`、`onnxruntime`、`xgboost`，而 `backend/app/providers/trained.py:27-30` 四个都 import。它们目前只在 `requirements-inference.txt`。加一句注释指明 live 运行时必须装 `-r requirements-inference.txt`，并生成 `backend/requirements.lock.txt`（`.venv/bin/pip freeze`）。Playwright 1.60.0 也在 `.venv` 里但任何 requirements 文件都没写，Task 10 要用，一并补进 `requirements-inference.txt`。

- [ ] **Step 6：跑基线并记录**

```bash
export TMPDIR=$(mktemp -d); export PYTHONDONTWRITEBYTECODE=1
cd backend && PYTHONPATH=. ../.venv/bin/python -m pytest tests -q -p no:cacheprovider
cd .. && ./node_modules/.bin/vitest run --no-cache && ./node_modules/.bin/tsc --noEmit && ./node_modules/.bin/eslint .
```

期望：pytest 28 passed、vitest 32 passed、tsc 无错、eslint 退出 0。把输出与 manifest 一并写入 `docs/fyp2/release/RELEASE_MANIFEST.md`。

- [ ] **Step 7：Commit（不 push）**

```bash
git add AGENTS.md CLAUDE.md eslint.config.js scripts/freeze_manifest.py docs/fyp2/release backend/requirements.txt backend/requirements.lock.txt backend/requirements-inference.txt
git commit -m "chore: restore AGENTS.md, freeze release manifest, fix lint scope"
```

用户已明确指示 **AGENTS.md 不 push**。本 task 及之后所有 task 一律只 commit，不 push，直到用户另行指示。

---

## Task 2：`ai/src` 契约核心 —— 可空 RiskScore 与分母驱动的 health

**Files:**
- Create: `ai/src/availability.ts`、`ai/src/availability.test.ts`、`ai/fixtures/fusion_vectors.json`、`ai/src/fusionVectors.test.ts`
- Modify: `ai/src/types.ts:55-99`、`ai/src/riskLogic.ts:41-59,87-105,107-124,128-147,149-216`、`ai/src/evidence.ts:13-50,55-64,77-115`、`ai/src/riskLogic.test.ts:29-41`

**Interfaces:**
- Produces（后续 task 依赖这些精确签名）：
  ```ts
  export const FUSION_EPSILON = 1e-9;
  export const effectiveFusionDenominator(
    weightVision: number, weightTelemetry: number,
    visionStatus: FreshnessStatus, telemetryStatus: FreshnessStatus,
  ): { effVision: number; effTelemetry: number; denominator: number };
  export const isAssessmentAvailable(record: RiskUpdate): boolean;
  export const assertAvailabilityInvariant(record: RiskUpdate): void;   // 违反则 throw
  export const getDisplayState(record: RiskUpdate, opts: { stale: boolean }):
    "available" | "stale" | "unavailable";

  computeRiskScore(...): number | null
  mapRiskLevel(score: number | null, low?, high?): RiskLevel | null
  mapSystemHealth(visionStatus, telemetryStatus, weightVision = 0.5, weightTelemetry = 0.5): SystemHealth
  determineDominantEvidence(...): DominantEvidence | null
  ```
  `mapSystemHealth` 的两个权重参数**必须有 0.5/0.5 默认值** —— `riskLogic.test.ts:36,38,40` 三处是两参调用，给默认值它们才继续编译且期望值仍然正确。

- [ ] **Step 1：写夹具与失败测试**

把上表 21 行逐字写入 `ai/fixtures/fusion_vectors.json`（字段 `id, pd, pt, wv, wt, vision, telemetry, expect{available,score,level,health,dominant}`）。`ai/src/fusionVectors.test.ts` 读该文件，对每行断言 `computeRiskScore` / `mapRiskLevel` / `mapSystemHealth` / `determineDominantEvidence` 的输出。**期望值只能来自 JSON，不得从实现 import 任何常量。**

同时在 `ai/src/availability.test.ts` 写 `UT-AVAIL-01`：9 种 freshness 组合 × 权重 `(0.5,0.5)` / `(1.0,0.0)` / `(0.0,1.0)` 共 27 种，断言 `isAssessmentAvailable(r) === (r.RiskScore !== null) === (r.SystemHealth !== "UNAVAILABLE")`。

- [ ] **Step 2：确认测试失败**

Run: `./node_modules/.bin/vitest run --no-cache ai/src/fusionVectors.test.ts ai/src/availability.test.ts`
Expected: FAIL —— `availability.ts` 不存在；`F-U1` 现在返回 `0` 而非 `null`；`F-Z1`/`F-Z2` 现在返回 `DEGRADED` 而非 `UNAVAILABLE`。

- [ ] **Step 3：实现 `ai/src/availability.ts` 与 `ai/src/types.ts`**

`types.ts` 的 `RiskUpdate` 增加 `assessment_available: boolean`，四个字段加 `| null`。`frontend/src/types.ts` 只是 re-export，无需改动，可空性会自动传播到所有视图。

- [ ] **Step 4：改 `riskLogic.ts` 与 `evidence.ts`**

`computeRiskScore` 把 `if (total === 0) return 0`（:53）改成 `if (total <= FUSION_EPSILON) return null`。`mapRiskLevel` 在比较之前先处理 null。`mapSystemHealth` 按分母规则重写。`buildRiskUpdate` 同时产出 `assessment_available` 与四个 null。`buildExplanation` 增加 unavailable 分支，文案要点名是哪一侧缺失或零权重，**且不得提及任何 level**。

`evidence.ts:31` 是 `if (riskScore < thresholdLow) return "Low observed risk"` —— **JS 里 `null < 30` 为 `true`**，所以可用性判断必须排在所有关系运算之前，否则一个无证据窗口会被报成「低风险」这种捏造的安全读数。`getMatchedEvidenceRule` 的兜底分支（:112-115）要加一条显式的「有效融合分母为 0」规则，不能继续说「one modality is stale or missing」。

- [ ] **Step 5：更新既有断言**

`ai/src/riskLogic.test.ts:29-31` 的 `both modalities missing -> 0` 改为 `toBeNull()`，并补 `(1.0, 0.0)` + vision missing、`(0.0, 1.0)` + telemetry missing 两例。`:34-41` 的 `mapSystemHealth` 块补零分母用例。

- [ ] **Step 6：跑测试与类型检查**

Run: `./node_modules/.bin/vitest run --no-cache && ./node_modules/.bin/tsc --noEmit`
Expected: 夹具与 availability 全绿。**`tsc` 预期会报大量错误** —— 那是 Task 6 的工作面，此刻把错误清单记进 `findings` 供 Task 6 使用，不要在本 task 修视图。

- [ ] **Step 7：Commit**

```bash
git add ai/src ai/fixtures && git commit -m "feat(ai): nullable risk contract with denominator-driven availability"
```

---

## Task 3：Python 侧契约同步（两份移植）

**Files:**
- Modify: `backend/app/fusion.py:12-95`、`ai/reference/risk_logic.py:27-118`
- Create: `backend/tests/test_fusion_vectors.py`

**Interfaces:**
- Consumes: `ai/fixtures/fusion_vectors.json`（Task 2）
- Produces:
  ```python
  FUSION_EPSILON = 1e-9
  def effective_weights(w_v, w_t, vision_status, telemetry_status) -> tuple[float, float, float]
  def compute_risk_score(...) -> float | None
  def map_risk_level(score: float | None, low=None, high=None) -> str | None
  def map_system_health(vision_status, telemetry_status, weight_vision=0.5, weight_telemetry=0.5) -> str
  def determine_dominant_evidence(...) -> str | None
  ```

- [ ] **Step 1：写读同一份夹具的失败测试**

`backend/tests/test_fusion_vectors.py` 读 `ai/fixtures/fusion_vectors.json`（相对仓库根定位），对 21 行做与 TS 侧**字面相同**的断言。这是跨语言 oracle：两边期望值都来自同一个 JSON，谁漂移谁红。

- [ ] **Step 2：确认失败**

Run: `cd backend && PYTHONPATH=. ../.venv/bin/python -m pytest tests/test_fusion_vectors.py -q`
Expected: FAIL —— `F-U1` 返回 `0.0`、`F-Z1`/`F-Z2` 返回 `DEGRADED`。

- [ ] **Step 3：改 `fusion.py`**

抽出 `effective_weights`，让 score、health、provenance 读**同一个**分母，而不是各算各的。`compute_risk_score` 在 `total <= FUSION_EPSILON` 时返回 `None`。

`map_risk_level` 必须先判 None 再比较 —— Python 对 `None < 30` 抛 TypeError，这和 TS 的静默 `true` 正好是**相反方向的失败**，所以 pytest 全绿完全不能说明 TS 侧没问题。

`determine_dominant_evidence` 要把 unavailable 判断放在**第一个**分支。注意现状是：`:70` 的 `if system_health != "FULL": return "Partial evidence"` 恰好挡住了对 None score 的比较，所以这个 bug **不会崩**，它只是安静地给无证据窗口编造出 "Partial evidence"。

`build_explanation` 的兜底 `return "The current window is below the low-risk threshold."`（:95）会对 `dominant=None` 命中 —— 这条文案会进 Explanation 视图和 CSV 的 `explanation` 列，等于 B01 换成英文句子继续存活。必须加前置 unavailable 分支。`level.lower()`（:86）对 None 会抛 AttributeError。

`map_alert_severity`（:79-82）**全仓库零调用方**，是死代码，且它把 High 直接映射成 HIGH_ALERT、绕过 2 秒 sustain，对 None 还会 KeyError。它就躺在要改的 `build_explanation` 正上方 —— 顺手把它接上去就会静默删掉 2 秒门槛。本 task 的处理：加 None 守卫 + 在 docstring 顶部写明「未被调用；不要接线，FSM 在 inference.py」，不删除（本阶段不删功能）。

- [ ] **Step 4：同步 `ai/reference/risk_logic.py`**

逐函数照搬相同改动，包括 `:109` 对 `map_system_health` 的位置参数调用。~~这个模块 **零 importer、零测试覆盖**，却被文档声明为报告引用的语言无关规范 —— 不同步它，报告里的 Eq.1/Eq.2 叙述就和实现分叉，而且不会有任何测试报错。~~ **（阶段 1 更正：Task 3 之后它已被 `test_fusion_vectors.py` 经 importlib 加载并有测试守护，见 Global Constraints。）**更新 `__main__` 的 worked example（:120-138）使其打印新的 unavailable 情形。

- [ ] **Step 5：跑测试**

Run: `cd backend && PYTHONPATH=. ../.venv/bin/python -m pytest tests -q`
Expected: `test_fusion_vectors.py` 全绿；`test_api.py:83` 断言 `latest_system_health == "DEGRADED"` 需复核（该用例权重为 0.5/0.5 且仅一侧 missing，分母非零，结论不变，应仍绿）。

- [ ] **Step 6：Commit**

---

## Task 4：后端 schema、迁移与导出

**Files:**
- Modify: `backend/app/schemas.py:134-186`、`models.py:39-61`、`db.py:30-53`、`cache.py:1-16`、`routers/windows.py:64-69`、`routers/risk.py:6`、`routers/status.py:42-54`、`routers/export.py:14-19,31-55`
- Create: `backend/tests/test_unavailable_contract.py`、`backend/tests/conftest.py`
- Modify: `backend/tests/test_migration.py:10-14`、`test_live_inference.py:98-100`

**Interfaces:**
- Consumes: Task 3 的 `fusion` 签名
- Produces: `RiskUpdate.assessment_available`；`inference_records.assessment_available` 列；导出里的 `assessment_available` 列

- [ ] **Step 1：建统一的 pytest fixture**

目前**没有 `conftest.py` 也没有 pytest 配置**。`test_api.py:5-17` 在 import 期把 `DRA_DATABASE_URL` 指向 `tempfile.gettempdir()` 下的固定路径并 `drop_all`，于是任何在它之前被收集、且 import 了 `app.config` 的新测试模块，会静默改写整轮测试的数据库。`test_live_inference.py:11` 的 `from test_audit_regressions import api` 也只是靠 pytest 把测试目录塞进 `sys.path` 才成立。

新建 `backend/tests/conftest.py`，提供 tmp_path 作用域的 `api` fixture（override `get_db`、跳过 lifespan、teardown 清 `cache` 模块全局量），所有新测试只用它。

- [ ] **Step 2：写失败测试**

`test_unavailable_contract.py`：
- `UT-FUS-03`：两路 missing 的窗口返回 201，且 `assessment_available is False`、四字段 `is None`、`SystemHealth == "UNAVAILABLE"`，并在同一个响应体上断言三元恒等式。
- `UT-FUS-ZERO-WEIGHT`：会话配置 `weight_vision=1.0, weight_telemetry=0.0`，vision missing + telemetry fresh（`P_telemetry_anomaly=0.9`）→ unavailable。镜像用例同理。对照组：`0.5/0.5` + vision stale + telemetry fresh、`0.1/0.9` → 仍 available，`RiskScore == 65.2`，`DEGRADED`。注意 `RuntimeConfig` 本来就接受 `(1.0, 0.0)`，这条路径**今天就能从公开 API 走到**，而唯一的权重测试（`test_live_inference.py:117-118`）只测了非法的 `0.9/0.9 → 422`。
- `EX-NULL-01`：JSON 导出里 `records[1]["RiskScore"] is None`、`records[1]["assessment_available"] is False`（用 `is False`，不是真值判断）；CSV 里表头含 `assessment_available`，该行 `RiskScore` 是**空字符串**而非 `"0"`，且两行的布尔大小写约定一致。
- `ST-STATUS-01`：新建会话 `latest_window_id is None` 且 `latest_assessment_available is None`；写入一个 unavailable 窗口后 `latest_window_id == 1`、`latest_assessment_available is False`、`latest_alert_severity is None` —— 证明「还没有记录」和「记录本身无评估」可区分。

`test_migration.py` 扩展 legacy fixture（现为 1 行）到 3 行：正常行、捏造的 unavailable 行（`risk_score=0.0, risk_level='Low', alert_severity='NORMAL', system_health='UNAVAILABLE'`）、以及现有的 `{"proof":"keep this"}` 纯 payload 行。

- [ ] **Step 3：确认失败**

Run: `cd backend && PYTHONPATH=. ../.venv/bin/python -m pytest tests/test_unavailable_contract.py tests/test_migration.py -q`

- [ ] **Step 4：改 schema**

`RiskUpdate` 四字段改 `Optional`，`assessment_available: bool` 放在 `timestamp` 之后、`P_distraction` 之前（让它在任何数值之前被读到）。

**两道防线，都要**：
1. `model_validator(mode="before")`：当 payload 里没有 `assessment_available` 键时，由 `RiskScore is not None and SystemHealth != "UNAVAILABLE"` 推导，并把捏造的 `0/Low/NORMAL` 归一化为 None。这保证历史行**读取不 500**。
2. `model_validator(mode="after")`：强制三元恒等式与四字段同时为 null。因为有了第 1 道防线，第 2 道不会被历史数据绊倒。

`SystemStatusOut` 增加 `latest_assessment_available: Optional[bool]`、`latest_risk_score: Optional[float]`，以及 Task 7 要用的 `open_fault_events: int = 0`。

**不要**改 `SessionCreate.operation_mode` 的默认值。D03 保留 replay，而 `test_audit_regressions.py:41`、`test_restart.py:18`、`test_api.py:49` 都是不带 mode 建会话后 POST `/windows`。Live 默认值已由客户端携带（`frontend/src/api/client.ts:68`）。

- [ ] **Step 5：改模型与迁移**

`models.py` 只需加 `assessment_available = Column(Boolean, nullable=False, default=True, server_default="1")` —— `risk_score` / `risk_level` / `dominant_evidence` / `alert_severity` 四列**本来就可空**（SQLAlchemy `Column(...)` 默认 `nullable=True`），`test_migration.py:12` 的 legacy DDL 也没有 NOT NULL，所以 D01 不需要任何列可空性迁移。

`db.py` 的 `additions` 字典加入新列。payload JSON 回填必须带守卫：

```sql
UPDATE inference_records SET payload = json_set(payload,'$.assessment_available', json('true'))
WHERE payload IS NOT NULL AND json_valid(payload)
  AND json_extract(payload,'$.assessment_available') IS NULL
  AND json_extract(payload,'$.RiskScore') IS NOT NULL
```

守卫是强制的：`json_set()` 作用在 NULL 或非法 JSON 上返回 NULL，会**抹掉整行** —— `test_migration.py:14` 插入的正是这样一行。另外必须用 `json('true')` 而不是 `1`，否则 `export.py:36` 直接 dump payload 时迁移行导出 `"assessment_available": 1`，而新行导出 `true`。

对 `system_health='UNAVAILABLE'` 的历史行，把列与 payload 里的四个值都置 null、`assessment_available` 置 `json('false')`。

- [ ] **Step 6：改导出与状态**

`export.py` 的 `_COLUMNS` **追加**（不是插入）`"assessment_available"`，顺带追加 `P_distraction_raw` / `P_telemetry_raw` —— 这两个诚实值目前存在 `provenance` 里却没有 CSV 列。CSV 分支显式把布尔规范成 `"true"/"false"`、把 None 映成 `""`，不要依赖 `DictWriter` 的隐式行为。注意 `:48` 允许任何同名 provenance 键覆盖顶层值，所以 **`assessment_available` 绝不能放进 provenance**。防注入守卫（`:53`）只检查 `str`，None 会原样通过，没问题。

`status.py` 增加新字段，并给 `:49` 的 provenance 读取加 `latest.payload or {}` 守卫（手工 legacy 行可能 payload 为 NULL）。

`cache.py` 无结构改动，但把 `windows.py:141` 的 delete 收紧成「只在删除的就是缓存中那条时才清空」，对齐 `:128-130` 已有的写法。`risk.py:6` 删掉已无用的 `cache` import，并确认 404（没有记录）与 200 + `assessment_available=false`（有记录但无评估）两种语义保持区分。

- [ ] **Step 7：跑全套 + 类型检查，Commit**

Run: `pytest tests -q` → 期望全绿，含新用例。`test_live_inference.py:98-100` 原本只断言 `SystemHealth == "UNAVAILABLE"`，替换为完整契约断言。

---

## Task 5：时序路径 —— unavailable 期间的 FSM 与 EMA

**Files:**
- Modify: `backend/app/inference.py:13-73`、`ai/src/alertFsm.ts:37-65`
- Create: `backend/tests/test_temporal_contract.py`
- Modify: `ai/src/alertFsm.test.ts`

**Interfaces:**
- Consumes: Task 3 的 `effective_weights`、Task 4 的 schema
- Produces: `inference.py` 的 state 字典新键 `last_severity`、`unavailable_since`

- [ ] **Step 1：写失败测试（硬编码 2000 / 10000）**

`test_temporal_contract.py`，全部用注入的假时钟，**不得 import 实现里的阈值常量**：
- `UT-TIME-01`：High@0 → CAUTION；High@1900 → CAUTION；High@2000 → HIGH_ALERT；High@2100 → HIGH_ALERT。随后 Low@2100 起算，Low@12000（9.9s）仍 HIGH_ALERT，Low@12100（10.0s）→ NORMAL。打断序列：High@0 → Medium@1000（CAUTION，streak 清空）→ High@1500 → High@3400（1.9s，CAUTION）→ High@3500（2.0s，HIGH_ALERT）。
- `UT-TIME-02`：age 2.999 fresh、3.000 fresh、3.001 stale；gap > 3s 重置 EMA 与 streak；同一时刻的不同 UTC 偏移写法等价。
- `UT-TIME-03`：`alpha=0.35`，raw `0.2 → 1.0` 的第二个平滑值 `0.48`（**断言 seed-on-first-sample 约定**；seed-at-0 会得 `0.3955`）。
- **`UT-TIME-04`（新，关键）**：High@0 → unavailable@1000 → High@2000。断言**不**升级为 HIGH_ALERT —— unavailable 区间不得计入 2 秒 sustain。
- **`UT-TIME-05`（Review Focus #4）**：连续三个窗口携带**完全相同**的 `captured_at`。`windows.py:55` 用的是严格 `<`，相等时间戳能通过，于是重复的旧证据可以累积告警时长。断言当前行为并记录为已知限制（完整的 D13 策略不在本阶段范围）。
- **`UT-TIME-06`（R1 新增 —— D13 留证，非期望行为）**：用注入时钟喂一串**只有 stale 证据**、分数持续落在 High 区间的窗口，断言当前行为 —— sustained-High 计时会照常累积并最终升到 `HIGH_ALERT`。测试名必须含 `known_limitation`，docstring 必须写明：这是 D13 的行为快照，不是期望行为，系统**尚未**实现最大证据年龄。~~注意该路径在 Live 主运行时不可达（`trained.py` 只输出 fresh/missing），测试需直接驱动 `run_inference` 或走 `/windows`。~~
  **R4 更正（Codex R08）**：该路径在 Live 主运行时**可达**。`run_inference` 用 `provenance.captured_at` / `telemetry_timestamp` **重新判定** freshness（`backend/app/inference.py:107-108`），不依赖 provider 报告的 `fresh`；证据时间戳距服务端处理时刻超过 3 s 即为 `stale`（严格 `>`），与 `trained.py` 输出什么无关。`UT-TIME-06` 本身仍直接驱动 `run_inference`；Live 路径的对应测试是阶段 1 的 `IT-LIVE-AGE`（`backend/tests/test_temporal_contract.py`，经 `POST /api/sessions/{sid}/infer`，provider 用 stub，不依赖模型权重）。
- **`UT-EMA-PARITY-01`（R1 新增）**：同一串输入分别跑 Python `run_inference` 与 TS `buildRiskUpdate`，断言 `P_distraction` 逐窗口相等。至少覆盖三种情形：首帧（Python 不 round / TS round3 的分歧点）、stale 之后的第一个 fresh 窗口（Python 重新 seed / TS 继续 EMA 的分歧点）、以及连续 fresh 序列。以 Python 语义为准。

- [ ] **Step 2：确认失败** — `UT-TIME-04` 预期 FAIL（现在会升级）。

- [ ] **Step 3：改 `inference.py`**

把 `(eff_v, eff_t, denominator)` 算一次，score/level/health/dominant 全部由它派生 —— 现在 health 在 `:40` 独立从状态推导，这正是 score=0 与 health=DEGRADED 能自相矛盾的原因。

**unavailable 时的 FSM，三条都要做到：**
- (a) payload 里 `AlertSeverity` 发 `None`；
- (b) **绝不把 None 写进 `state['severity']`** —— `:42` 会读回它、`:48` 靠 `severity == "HIGH_ALERT"` 维持锁存，写入 None 会让一次证据中断就静默把 HIGH_ALERT 降级，且任何地方都不会报错。用单独的 `last_severity` 键保存最后一个非空值；
- (c) 计时器**挂起而非冻结**：记 `unavailable_since`，恢复后把 `high_since` / `low_since` 重锚到当前时刻。

**不能把挂起逻辑搭在现有 gap 分支上**：`:31` 比较的 `last_processed_ms` 在 `:58` 对**每个**窗口（含 unavailable）都更新，所以一段 60 秒的无证据窗口在 gap 逻辑看来是「持续处理中」。

**新加的「时序记忆」键（streak、锁存、EMA 链）都必须进 `:32` 的 pop 元组**（现为 `inference.TEMPORAL_STATE_KEYS`），否则它会越过 gap 重置、并且因为 `runtime_state` 是持久化 JSON 列（`models.py:28`）而越过 worker 重启活下来 —— 症状是几小时后恢复的会话带着陈旧的 HIGH_ALERT 锁存，而没有任何测试失败。**反过来，`inference.EVIDENCE_WATERMARK_KEYS`（`captured_at`、`telemetry_timestamp`，乱序守卫的 watermark）绝不能加入该元组**：它们必须跨 gap、跨重启保留，否则一次暂停之后更旧的证据会被重新接受（`test_out_of_order_guard_survives_a_gap` 守住这一点）。

`:57` 的 `previous_vision=pd if vstatus == "fresh" else None` 会在「unavailable 但 vision fresh」（`w_v=0, w_t=1`、telemetry missing）时继续累积 EMA 链 —— 要一并切断。

把硬编码的 `2000`（:48）和 `10000`（:55）提成具名常量。

**不要顺手「整理」EMA 的舍入**：`:34-36` 只在 EMA 分支里 `round(...,3)`，所以首帧与 stale-vision 帧发的是全精度浮点。`test_audit_regressions.py:139` 与 `test_restart.py:44`（钉死 `.312`）依赖现状。要改就单独做并同步 `ai/src/riskLogic.ts:164`，不要混在本 task 里。

- [ ] **Step 3b：消除 EMA 的两处跨语言分歧（R1 新增）**

以 Python 为准，改 TS：
1. `ai/src/riskLogic.ts:158-164` 的非 EMA 分支去掉 `round3`，与 `inference.py:34` 对齐（首帧发原始精度）；
2. 同处的条件由「`previousRecord` 存在且当前 fresh」改为「**上一条记录的 vision 也是 fresh**，且当前 fresh」，与 `inference.py:57` 把 `previous_vision` 在非 fresh 时置 `None` 的语义对齐。

`ai/reference/risk_logic.py:90-94` 的 `ema()` 同步加注释说明 seed 与重新初始化约定。**不要改 Python** —— `test_audit_regressions.py:139` 与 `test_restart.py:44`（钉死 `.312`）依赖现状，裁定方向就是保持它。

- [ ] **Step 4：改 `ai/src/alertFsm.ts`**

`updateAlertState` 的 `level` 参数放宽为 `RiskLevel | null`，null 时挂起计时器并保持 `severity` 不变（内部状态仍非空，可空性只出现在 `RiskUpdate` 边界）。`alertFsm.test.ts` 把 import 来的 `ALERT_SUSTAIN_MS` / `ALERT_RECOVER_MS` 换成硬编码 2000 / 10000 —— 否则改常量时期望值会跟着实现一起漂移，审计 EX-TS-19/21 就是指这个。

- [ ] **Step 5：跑测试，Commit**

---

## Task 6：前端展示层 —— 消灭捏造读数

**Files:**
- Modify: `frontend/src/utils/format.ts:5-6`、`utils/export.ts:17-23,47-51,53-68,104-132`、`utils/persistence.ts:17-25,32-33`、`api/client.ts:40`
- Modify: `components/Pill.tsx:8-22`、`ScoreGauge.tsx:3-49`、`AlertBanner.tsx:11-45`、`TrendChart.tsx:26-37,66-72`、`styles.css:268-277,512-534`
- Modify: `views/LiveMonitor.tsx:36-45,87-126,145-171`、`SignalInspector.tsx:23-24,72-92`、`RiskTrends.tsx:17-23,74-104`、`ExplanationView.tsx:27-33,100-127,140-182,226-272`、`ConfigurationView.tsx:31-37,100-126`
- Create: `frontend/src/utils/export.test.ts`、`frontend/src/components/trendChart.test.ts`、`frontend/src/views/riskTrends.test.ts`
- Modify: `frontend/src/utils/persistence.test.ts`、`data/preparedSessionInput.test.ts:29-32`

**Interfaces:** Consumes Task 2 的 `ai/src/availability.ts`

**本 task 最重要的事实：`tsc` 抓不全。** strict 模式会在算术、索引、prop 处大声报错（`formatRiskScore` 的 6 个调用点、`ScoreGauge.score`、所有 `Pill` 的 label/tone、`evidence.ts:46`、`export.ts:57`、`App.tsx:62`），但每一个**比较和过滤**都编译通过且静默失败：`RiskTrends.tsx:22` 的 `record.RiskLevel === label`、`:79` 的 `=== "High"`、`AlertBanner.tsx:27` 的 `=== "NORMAL"`、`TrendChart.tsx:28` 已经可空的三元、以及 `App.tsx:66` 把 `AlertSeverity: fsm.severity` spread 覆盖掉 null。**把 `./node_modules/.bin/tsc --noEmit` 当完成信号的计划会把这五个全部放过去。**

- [ ] **Step 1：写失败测试（纯函数优先）**

先把可测逻辑从组件里抽出来，再测：`TrendChart.tsx:26-37` 的 series builder、`RiskTrends.tsx:19-23` 的 `distribution()`。
- `UT-PERS-MIGRATE-01`：`loadSessionLog` 读到没有 `assessment_available` 的历史记录时，`RiskScore: 42.0 / SystemHealth: "DEGRADED"` 的行归一化为 `available === true`；`RiskScore: 0 / RiskLevel: "Low" / AlertSeverity: "NORMAL" / SystemHealth: "UNAVAILABLE"` 的行归一化为 `available === false` 且四字段变 `null`。
- `UT-EXPORT-01`：2 条记录（1 可用 1 不可用）的 CSV 表头含 `assessment_available`；不可用行的 `risk_score` / `risk_level` / `dominant_evidence` / `alert_severity` 全部是**空单元格**（R1 统一：前后端一致用空单元格，不用字面量 `unavailable`），**绝不能是 `0`**；同一行的 `assessment_available` 为 `false`、`SystemHealth` 为 `UNAVAILABLE` —— 这两列承担消歧义，必须始终有值；JSON 导出里不可用记录**仍包含** `dominant_evidence` 键（现在 `dominantEvidenceLabel[null]` 是 `undefined`，`JSON.stringify` 会把这个键整个删掉，两条记录形状不同）。
- `UT-DIST-01`：`distribution()` 在 25 窗口的 prepared replay 上返回 `{Low, Medium, High, Unavailable}` 且 `Unavailable === 1`（窗口 17），四个计数和恰为 25；现在三个计数能凑够 25 只是因为窗口 17 被错当成 Low。
- `UT-TREND-01`：series builder 当且仅当 `assessment_available === false` 时把 risk 点置 null；tooltip formatter 对 null 点返回 unavailable 标记，而不是 `Number(null) === 0` 导出的 `"0.0 / 100"`。

- [ ] **Step 2：确认失败**

- [ ] **Step 3：归一化两个边界**

`persistence.ts` 的 `readJson` 与 `api/client.ts:40` 都是无校验的 `as T` 强转。两处用同一个归一化函数：`assessment_available ?? (RiskScore != null && SystemHealth !== "UNAVAILABLE")`。

**判定式的选择决定了失败模式**：`!record.assessment_available` 会把所有历史记录标成 UNAVAILABLE（UI 里整段历史消失）；`record.assessment_available === false` 会把它们全标成可用（对一般 replay 记录正确，但对历史上存成 `0/Low/NORMAL/UNAVAILABLE` 的窗口 17 错误）。只有从 `RiskScore` 与 `SystemHealth` 推导才是对的。

- [ ] **Step 4：改组件与视图**

- `format.ts:5` 的 `formatRiskScore` 放宽为 `number | null` 并返回统一的 unavailable 文案，6 个调用点因此得到一致字符串，而不是各自发明占位符。
- `Pill.tsx` 增加 `"unavailable"` tone，`styles.css` 增加 `.pill--unavailable`。现在 `styles.css:512-534` 只为 Low/Medium/High 系列定义了 tone，`alert-banner--` 规则（:268-277）也只有 CAUTION 与 HIGH_ALERT —— null 插进模板字符串会得到 `.pill--null`，匹配不到任何规则，**于是一个不可用窗口会长得和普通低风险窗口一模一样，而且没有任何报错**。
- `LiveMonitor.tsx:45` 的 `const health = stale ? "UNAVAILABLE" : latest.SystemHealth` **捏造 SystemHealth**，`:37-44` 同样把 `modality_freshness` 改写成 "stale"。这两处必须删掉：显示的 SystemHealth 必须等于记录自己的值。`stale` 是关于记录**年龄**的前端判断（由 1Hz 的 `setNow` 驱动、依赖客户端与服务端时钟一致），`assessment_available` 是记录**自身**的属性 —— 这是 available / stale / unavailable **三个**显示态，不是两个，而现在的代码在两个文件里把它们塌缩成一个分支。统一改用 `getDisplayState()`。
- `ExplanationView.tsx` 是最糟的一个：完全没有 unavailable 处理，会在一条不可用记录上同时渲染 AlertStatus pill 和写着 UNAVAILABLE 的 SystemHealth pill，并打印 `"Visual Distraction 0 + Telemetry Non-Safe 0 = RiskScore 0.0 / 100"` 这个捏造的等式（:255-271）。它经由 `App.tsx:365` 的 `selectedRecord`（不是 `latest`）进入，所以用户在 Signal Inspector 里选中一个不可用窗口再切过来就能看到 —— **五个视图都要处理，不只是 live 瓦片**。
- `RiskTrends.tsx:19-23` 的 `distribution()` 增加 Unavailable 桶。
- `ConfigurationView.tsx` 的两个 range input `min="0"`，用户能从 UI 直接设出 `(1.00, 0.00)` 把系统推进零分母状态且毫无提示。任一权重归零时加一条行内说明。

- [ ] **Step 5：堵住「前端重算」这个洞（IT-UI-01 的核心）**

grep 证实：**没有任何视图读 `record.DominantEvidence`**。全前端只有 `utils/export.ts:57` 和 `preparedSessionInput.test.ts:35` 读它；`LiveMonitor:36`、`SignalInspector:23`、`RiskTrends:95`、`ExplanationView:116/123` 全都用 `getEvidenceType(record, thresholdLow)` **重新算**。所以把 canonical 字段改成可空，在任何视图里都不会报错，视图会继续显示一个重算出来的非空标签，而存储的记录说 null —— 这正是 IT-UI-01 要抓的「no frontend refusion」违规。`ExplanationView:100-107` 的 `computeRiskContributions` 同理。

本步：把这些调用点全部改为读 `record.DominantEvidence`，仅在该字段缺失（历史记录）时回落到重算，并在 `ai/src/availability.test.ts` 里加一条 grep 断言，确保 `LiveMonitor.tsx` 与 `AlertBanner.tsx` 中不再出现字符串 `SystemHealth === "UNAVAILABLE"`。

- [ ] **Step 6：更新会破的既有断言**

`preparedSessionInput.test.ts:29-32` 是整个 32 项 TS 套件里**唯一**被 D01 硬破坏的断言：prepared 窗口 17（`telemetry.csv` 第 18 行，vision 与 telemetry 都 unavailable）是唯一的两路缺失窗口，所以 `new Set(records.map(r => r.RiskLevel))` 从 3 元集变成 4 元集（含 `null`）。该文件另外四条覆盖断言靠运气存活：`"Partial evidence"` 仍由窗口 14/15/16 产生，SystemHealth 三态仍齐全，尾部 Low 长度 6（≥5），最长连续 High 为 4（≥2）。**说「replay 覆盖套件会崩」是夸大，说「什么都不会崩」是漏报。**

- [ ] **Step 7：跑三道门禁，Commit**

Run: `./node_modules/.bin/vitest run --no-cache && ./node_modules/.bin/tsc --noEmit && ./node_modules/.bin/eslint .` —— 三者全绿才算完成。

---

## Task 7：fault_events —— 可观测且能活过会话删除

**Files:**
- Create: `backend/app/faults.py`、`backend/app/routers/faults.py`、`backend/tests/test_fault_events.py`
- Modify: `backend/app/models.py`（新表）、`db.py`、`main.py:26-48`、`routers/windows.py:42-108`、`schemas.py`

**Interfaces:**
- Produces:
  ```python
  record_fault(db, *, session_id, request_id, retry_index, origin,
               error_category, http_status, retryable, detail) -> None
  mark_recovered(db, session_id, request_id) -> None
  open_fault_count(db, session_id) -> int
  ```
  `error_category` ∈ `input_validation | mode_conflict | not_found | idempotency_conflict | model_unavailable | model_runtime | storage | transport_timeout | unknown`；`recovery_status` ∈ `open | recovered | exhausted`。

- [ ] **Step 1：写失败测试**

- `ST-FAIL-02`：live 会话上 POST `/infer` 带 `image_base64="not-base64"` → 422；`total_windows` 仍为 0、`/risk/latest` 仍 404；`GET /api/faults?session_id=…` 恰好一行，`error_category == "input_validation"`、`http_status == 422`、`retryable is False`、`request_id` 等于提交值、`recovery_status == "open"`。重复同一请求不产生第二行。把 `model_root` 指向空目录后 POST → 503，恰好一行 `model_unavailable`、`retryable is True`。
- `ST-FAIL-03`：monkeypatch 请求 Session 的 `commit` 在第一次 `/infer` 抛 `OperationalError`。响应是 5xx 且 detail 仍指向存储失败（不是 fault logger 的错）；`total_windows` 仍 0；没有对应的 `InferenceRecord`；独立文件 sink（测试里重定向到 `tmp_path`）里有一行 `storage` + 该 request_id。**第二个子用例**：把 fault session 的 `commit` 也 patch 成抛错，断言原始 `OperationalError` 原样向上传播 —— fault logger 绝不掩盖原因。
- `ST-RECOVER-01`（**R1 修订：不再用 503**）：1 次成功 → 3 次可重试失败 → 恢复 → 第 4 次请求。**注入方式必须是 `model_runtime`（HTTP 500）或 `transport`，不能是 503** —— 503 在 R1 的分类里是不可重试的「模型文件缺失」，用它注入会和客户端策略自相矛盾（这正是 R1 要消除的 Task 7/8 冲突）。断言三行 fault 的 `attempt_index` 为 1/2/3，第 4 次提交后 `recovery_status` 转 `recovered` 且 `recovered_by_request_id` 指向成功请求；`/system-status` 的 `open_fault_events` 恢复前 3、恢复后 0；**总共只有 2 条 `InferenceRecord`**（失败不落记录、重试不产生重复）。**任何断言都不得把 3 次上界当成服务端策略** —— 上界属于客户端，由 Task 8 断言，后端只记录它被告知的 `attempt_index`。
- `ST-FAIL-04`（**R1 新增**）：拆分 `trained.py` 的两类失败。模型文件缺失 → 503 + `models_unavailable`；provider 前向推理抛异常 → **500 + `model_runtime`**。断言两者 HTTP 码不同、category 不同，且各自只产生一行 fault。没有这个拆分，客户端无法区分「重试没用」和「值得重试」。
- `ST-FAIL-01`：产生两行 fault 后 `DELETE /api/sessions/{sid}` → 204，`GET /api/sessions/{sid}` → 404，但 `GET /api/faults?session_id={sid}` **仍返回两行**且 `occurred_at` 不变；该会话的 `inference_records` 计数为 0。

- [ ] **Step 2：确认失败**

- [ ] **Step 3：建表（三个陷阱）**

1. **`session_id` 必须是普通的、带索引的可空 String，不能有 ForeignKey。** `models.py:34` 的 `cascade="all, delete-orphan"` + `:45` 的 `ondelete="CASCADE"` + `db.py:24` 的 `PRAGMA foreign_keys=ON` 合起来，会让 fault 行随会话一起消失 —— 正好与 D02 要求相反。可空是因为「session not found」这类 fault 带的 id 从来就不存在。
2. **`fault_events` 必须用显式 `CREATE TABLE IF NOT EXISTS`**，不能靠 `Base.metadata.create_all`。`db.py:44` 的 `inspect(conn).get_columns(table)` 对不存在的表抛 `NoSuchTableError`；现在能跑通只是因为 `main.py:14` 先 import 了 `app.models`，而 `test_migration.py:8` 只 import `app.db`，建表与否取决于 pytest 收集顺序。
3. 唯一索引 `uq_fault_session_request_retry ON fault_events(session_id, request_id, retry_index)` 用 `CREATE UNIQUE INDEX IF NOT EXISTS`（SQLite 的 `ALTER TABLE` 不能加 UNIQUE），照抄 `db.py:52-53` 的幂等写法。

`occurred_at` 用 ISO 字符串，与 `InferenceRecord.timestamp`（`models.py:50`）保持一致，不要用 `DateTime`。

- [ ] **Step 4：写 `faults.py`（独立性是重点）**

`record_fault` 必须在**自己的事务**里、用绑定到请求 engine 的 session 跑：`sessionmaker(bind=db.get_bind())()`，**不是**模块级 `SessionLocal`。模块级 engine 指向 `sqlite:///./driver_risk.db`（`config.py:15`），而 `test_audit_regressions.py:25-37` 只 override 了 `get_db`、刻意跳过 lifespan —— 用全局 engine 的 logger 会在测试运行时写进开发者的真实数据库，直接违反 IT-DB-01 的「no production DB access」。

任何异常都吞掉并写进独立 sink（`logging` → `backend/logs/fault_events.log`），保证数据库坏掉时事件不丢、原始异常不被掩盖。暴露 `get_fault_sink` 依赖供测试 override。

**写入时机**：必须在 `db.rollback()` **之后**。SQLite 只允许一个写者，失败事务还握着写锁时第二个连接写入会阻塞到 `busy_timeout=15000`（`db.py:26`）然后报 "database is locked"。

另外注意：`test_audit_regressions.py:25-37` 直接用 `create_engine` 建 engine，所以 `db.py:21-27` 的 `@event.listens_for(engine, "connect")` 对它**不生效** —— 没有 WAL、没有 busy_timeout、没有 foreign_keys。故障注入测试可能瞬间撞上 "database is locked"，而生产环境会扛过去。新 conftest 的 fixture 要复用同一个 pragma 钩子。

- [ ] **Step 5：接线**

`windows.py:_save_window` 把 `IntegrityError` 单独捕获并转 409（或改为读回既有记录）：唯一索引上的并发重复现在会冒成 500，而客户端的不可重试清单里没有 500，于是会对一个重复请求发起重试风暴。成功路径在 `db.commit()` 之后、`cache.set_latest` 之前调 `mark_recovered`。

`infer_frame` 在 404 / 409（两种成因）/ 422 / 503 各路径记录 fault。

`main.py` 注册 `faults` 路由，并添加目前**完全不存在**的异常处理器：`RequestValidationError`（这是 `/infer` 上 422 的**唯一**可观测位置 —— FastAPI 在 `infer_frame` 运行前就拒了 `LiveInput`，所以 `request_id` 要从 `exc.body` 里挖）、`HTTPException`、`Exception`，各自委托给 `record_fault` 后原样抛回。

**连续失败计数器不能放进 `SessionMeta.runtime_state`** —— 它在 risk 事务内写入（`windows.py:72`），而需要递增它的恰恰是会被 rollback 掉的失败路径。

- [ ] **Step 6：跑测试，Commit**

---

## Task 8：有界重试、冻结 payload、可见停止态

**Files:**
- Create: `frontend/src/api/retryPolicy.ts` + `.test.ts`、`ai/src/liveLoop.ts` + `ai/src/liveLoop.test.ts`
- Modify: `frontend/src/api/client.ts:9-45,62-104`、`hooks/useLiveSession.ts`、`hooks/useCameraPreview.ts:66-71,82-104`、`App.tsx:97-116,156-186,278-293`

**Interfaces:**
```ts
// R1: 改名并以「总投递次数」为准 —— 1 次首发 + 最多 2 次自动重试
export const MAX_ATTEMPTS_PER_REQUEST = 3;
export type FaultCategory =
  | "input" | "not_found" | "conflict_hash" | "conflict_stale_frame"
  | "models_unavailable" | "model_runtime" | "storage"
  | "timeout" | "transport" | "aborted";
export function classifyFailure(err: unknown):
  { category: FaultCategory; status?: number; retryable: boolean; counted: boolean };
// 只会被 attemptIndex 1 和 2 调用；3 次投递用完即停，没有第三次退避
export function backoffMs(attemptIndex: 1 | 2): number;   // 2000 / 4000
```

**为什么要抽成纯模块**：`vitest.config.ts` 是 `environment: "node"`，没有 jsdom、没有 `@testing-library`，而且 include glob 只有 `*.test.ts` —— 新建的 `*.test.tsx` 会被**静默跳过且退出 0**。把策略与循环抽出 React 是零新依赖的路线；Task 10 再决定要不要引入 jsdom。

- [ ] **Step 1：写失败测试**

- `retryPolicy.test.ts`（**R1 修订**）：`MAX_ATTEMPTS_PER_REQUEST === 3`；**不可重试**：400/422 → `input`、404 → `not_found`、409 → `conflict_hash` 或 `conflict_stale_frame`（由响应 detail 区分）、**503 → `models_unavailable`**，四者 `retryable: false`；**可重试**：**500 → `model_runtime` 或 `storage`**、502/504 → `storage`、超时 DOMException → `timeout`、fetch 的 TypeError → `transport`，`retryable: true`；pause 引发的 AbortError → `category: "aborted"`、`counted: false`。`backoffMs(1) === 2000`、`backoffMs(2) === 4000`，并断言**不存在**第三次退避（类型上 `backoffMs` 只接受 1 | 2）。
- `liveLoop.test.ts`（假定时器 + mock api）：`infer` 持续 reject TypeError 时**恰好 3 次**尝试（不是 4 次），之后不再排任何定时器、`running === false`、fault 为 `{category:"transport", stopped:true, retryCount:3}` 且 requestId 非空。随后 `retry()` 恰好再发一次；成功后 fault 清空、计数归零、循环按配置间隔恢复。
- **冻结 payload（Review Focus #4）**：一次被 10 秒超时中断的尝试在重试时，第二次 `infer` 收到的 payload 与第一次**深度相等** —— 同一个 `request_id`、同一个 `image_base64`、同一个 `captured_at`、同一组 `telemetry_features`、同一个 `telemetry_timestamp`。断言 mock 记录到 2 次调用但只有 1 个不同的 request_id。pause 引发的 abort 断言**不**递增计数器。
- 单次 `ApiError(422)` 立刻停止（恰好 1 次尝试）；`ApiError(503)` 同理；setup 阶段 `api.models` 返回 503 时在建会话之前就停（`api.create` 未被调用），进入同样的 stopped 态，而不是现在那样只留下一行文字、`running` 悄悄变 false。
- `retry()` 恢复**同一个会话**：`api.create` 未被调用，reconcile 路径（`api.session → api.latest → api.windows`）恰好跑一次，被中断尝试期间服务端已提交的窗口只出现一次。反之 `ApiError(404)` 之后，停止态要说明重试将新建会话，`retry()` 调一次 `api.create`。

- [ ] **Step 2：确认失败**

- [ ] **Step 3：实现 `retryPolicy.ts` 与 `liveLoop.ts`**

把 `useLiveSession.ts:187-194` 的内联数组和 `:204-206` 的内联表达式搬进 `retryPolicy.ts`。**补上 400** —— 现在的清单 `[404, 409, 422, 503]` 缺它。

**409 是重载的**：`windows.py:28` 为 request hash 冲突抛它，`windows.py:56` 为乱序证据时间戳抛它。按现状，一个迟到的帧会**永久停掉**会话。两种成因要分开归类。

- [ ] **Step 4：冻结请求身份**

当前 `crypto.randomUUID()`（`:153`）、`captureFrame()`（`:144`）、`new Date().toISOString()`（`:157`）全在 try 内部求值，所以每次重试都是新 id、新帧、新时间戳 —— D02 的「重试不得产生重复 risk 记录」在今天根本不成立：10 秒超时在服务端已提交之后触发，重试带着新 UUID 又写一条。而 `setHistory` 按 `window_id` 去重（`:165`），**在 UI 里把重复藏了起来**，SQLite 里却在累积。

但「只保住 UUID」是不够的：服务端幂等键是 `request_hash = sha256(payload)`，同 id 不同 hash 直接 409，而 409 按 D02 不可重试 —— 天真的修法会让每次重试都停机。**整个 payload 必须冻结在一个 ref 里**，重试时逐字节原样重发。

- [ ] **Step 5：区分超时与暂停**

`client.ts:19-23` 把调用方 signal 和内部 15 秒超时接到**同一个** AbortController，tick 又自带 10 秒 controller（`:142`），于是两者在 catch 点无法区分。现在能分清纯属偶然：`pause` 先递增 `runId`（`:28`），靠 `!current()` 守卫（`:181`）挡掉。任何停止先递增 runId 的重构都会立刻把用户暂停算成连续失败并触发 3 次停机。加一个由超时闭包捕获的 `timedOut` 标志，抛出独立的 TimeoutError。

顺带：`api.sessions/session/latest/windows/flag`（`:88-101`）**不接受 AbortSignal**，可以在停止后最多 15 秒才 resolve 并覆写已停止的状态。补上 signal。

- [ ] **Step 6：状态与 UI**

`failures` 现在是 `start` 闭包里的 `let`（`:136`），UI 看不到、fast-refresh 会悄悄清零、也无法持久化。提升为 `useRef` + 一个独立的 `fault` state。**停止态必须是独立且不会被自动清除的 state**：现在 `setError` 被 refreshSessions / loadSession / setup / tick / flag / export 六处写、被成功的 tick 无条件清空（`:178`），所以一次成功 tick 能抹掉导出错误，一次 flag 失败能覆盖停止态。

`App.tsx` 增加可见的停止面板：类别、request id、`n of 3`、以及重试是恢复同一会话还是新建会话；Retry 按钮接 `live.retry()`（**不是** `start(true)`，那会重启会话；也不能走 `updateConfig`，那会改 `configKey` 强制新建会话）。

**时钟偏移（Review Focus #3）**：`captured_at` 与 `telemetry_timestamp` 都来自浏览器时钟，超前服务端 5 秒以上会被 `normalize_timestamp` 拒成 422 → 不可重试 → 立刻停机。给它一个专门的 category 和一句能看懂的文案，而不是 "Inference request failed"。

`useCameraPreview.ts:82-104` 的 `captureFrame` 在 `readyState<2`、`videoWidth` 为 0、track 非 live 时返回 null，而 `useLiveSession` 只是发 `image_base64:null` —— 一个悄悄死掉的摄像头和一次故意的 vision-missing 完全一样。返回原因码。track 的 `ended` 监听（`:66-71`）只把 status 设成 "error"，从不通知 `useLiveSession`，于是监控会一直发 null 帧；把它暴露出来作为 fault 事件。

- [ ] **Step 7：跑测试，Commit**

---

## Task 9：Live-only 范围落地（D03）

**Files:**
- Modify: `frontend/src/App.tsx:37-39,50-69,191-210,240-244`、`data/preparedSessionInput.ts`、`utils/persistence.ts:90-94`、`hooks/useLiveSession.ts:145-149`
- Modify: `README.md`、`frontend/README.md`、`prototype-tests/README.md`、`docs/fyp2/06_WEEK7_CRITICAL_PATH_AND_ACTION_PLAN.md`（加一条范围说明，不改原文结论）

**不删除任何东西。** 本 task 只做降级、澄清与可确定性。

- [ ] **Step 1：把 prepared raw telemetry 和 prepared probability 分开**

`frontend/src/data/preparedSessionInput.ts` **不是** replay 路径 —— `useLiveSession.ts:3` import 的 `PREPARED_SESSION_WINDOWS` 只被读 `.telemetry_features`（`:146-149`），这是**保留的 prepared raw telemetry**，属于 Live 运行时。

新增 `PREPARED_RAW_TELEMETRY: { timestamp, telemetry_features, telemetry_age_s }[]` 供 Live 路径 import，把带 `P_distraction` / `P_telemetry_anomaly` / `visual_top_classes` 等 replay 专用字段的 `PREPARED_SESSION_WINDOWS` 留给保留的 replay。不做这个拆分，Live 路径就仍在 import 一个 prepared-**probability** 对象，Live-only 的说法在报告里站不住。

- [ ] **Step 2：让 Live 可复现**

prepared telemetry 游标是 `Math.floor((Date.now() - startedAt.current) / 2000) % 25`，而 `startedAt.current` 只在新建会话时设置（`:108`）。后果：pause/resume 或重试会让游标跳跃，没有任何一次 Live 运行是可复现的，Week 7 的端到端测试也无法断言哪条遥测记录到了后端。改成可注入的单调游标（每提交一个窗口推进一次）。

**R1 更正 —— 原文关于「34 秒内自然到达 UNAVAILABLE」的说法是错的。** 实测核实如下。

`telemetry.csv` 共 25 行数据（26 行含表头），其中：第 **14** 行 `telemetry_available=0`；第 **15** 行 `vision_available=0`（原计划遗漏）；第 **17** 行两者皆 0。

但 Live 路径**只读** `.telemetry_features`（`useLiveSession.ts:149`），`vision_available` 这一列在 Live 模式下**完全不被消费** —— vision 是否存在只取决于 `captureFrame()` 是否返回帧。后端 `trained.py:122-123` 则是二值判断：`image_base64 is not None → "fresh"`，否则 `"missing"`；telemetry 同理。

| 状态 | Live 主运行时可达？ | 触发条件 |
|---|---|---|
| telemetry `missing` | ✅ 可达 | 游标落在 CSV 第 14 或 17 行（`telemetry_features === null`） |
| vision `missing` | ⚠️ 仅靠摄像头 | `captureFrame()` 返回 null（摄像头关闭 / 未就绪）。CSV 第 15 行**不起作用** |
| 两路皆 `missing`（UNAVAILABLE） | ⚠️ 需同时满足 | 摄像头关闭 **且** 游标在第 14 / 17 行 |
| 任一路 `stale` | ~~❌ **不可达**~~ ✅ **可达**（**R4 更正**，Codex R08） | ~~两路时间戳都打 `new Date()`，且 `trained.py` 只输出 fresh/missing~~ `captured_at` / `telemetry_timestamp` 距服务端处理时刻超过 3 s：网络或处理延迟、客户端时钟偏差、或任何直接调用 `/infer` 的客户端。`inference.py:107-108` 按时间戳重新判定，不依赖 provider 报告的状态 |

**因此 `ST-FAIL-01` 的 UNAVAILABLE 场景需要显式关闭摄像头，不是「自然到达」**；~~而「age to stale」这一步在 Live 里**没有任何机制**，只能走保留的 replay 路径或直接 POST `/windows`。~~ Task 10 的端到端脚本必须显式 stop camera，并在断言里说明这一点。~~这同时解释了为什么 D13 不是主运行时的在役缺陷。~~

**R4 更正（Codex R08）**：划掉的两句是错的。「age to stale」在 Live 里**有**触发条件：`captured_at` / `telemetry_timestamp` 距服务端处理时刻超过 3 s，即可经 `POST /infer` 得到 `stale` 与 `DEGRADED`（`backend/app/inference.py:107-108`；`backend/tests/test_live_inference.py:114-117` 本身就断言这一点；阶段 1 的 `IT-LIVE-AGE` 在不依赖模型权重的情况下复现了 2.999 / 3.000 / 3.001 s 边界与 30 天旧帧）。因此 `ST-FAIL-01` 的 stale 步骤可以用旧 `captured_at` 经 `/infer` 构造，**D13 在 Live 主运行时可达**，是在役缺陷而不是仅限 replay 的限制。UNAVAILABLE 仍需显式关闭摄像头这一点不受影响。

- [ ] **Step 3：不要让回访用户悄悄启动到 replay**

`DEFAULT_CONFIG.operationMode` 已经是 `LIVE_MODEL_RUNTIME`（`ai/src/riskLogic.ts:14`），但 `persistence.loadConfig`（`utils/persistence.ts:90-94`）会原样恢复之前保存的 `PREPARED_SESSION_RUNTIME`。把 `App.tsx:191-210` 的 "Data mode" 选项改名为 legacy/test-only 并加门槛，`:240-244` 的说明文字同步改写。

- [ ] **Step 4：replay 调用点的 D01 兼容**

「保留 replay」不等于「不用动它」。`App.tsx:60-64` 把 `record.RiskLevel` 直接喂给 `updateAlertState`，`:66` 再用 `AlertSeverity: fsm.severity` spread 回去 —— 后者会**静默覆盖掉 null 并破坏 D01 不变式，且没有任何类型错误**。prepared 窗口 17 今天算出 0 → "Low"，正在**推进** 10 秒恢复计时器；RiskLevel 变 null 之后这一 tick 必须按 Task 5 的规则挂起计时器。

- [ ] **Step 5：改 Week 7 验收口径**

`prototype-tests/README.md` 的五视图清单是对着 replay 写的，而 Week 7 验收正靠它。重写为 Live 端到端：后端启动且 `/api/models` 报告模型已加载 → Start Monitoring → 至少 N 个来自 `/sessions/{id}/infer` 的 201 且记录 request_id → 五个视图读的都是后端记录 → flag 经 PATCH 持久化 → JSON/CSV 导出覆盖整个会话（不是 UI 的 500 条窗口）→ pause/retry/restart 行为符合策略 → 注入的传输故障在 3 次重试后停止并能手动恢复。

在 `docs/fyp2/06` 末尾追加一节说明：`ST-REPLAY-01` 在本阶段由 Live 端到端取代，原文结论保留不动。

- [ ] **Step 6：Commit**

---

## Task 10：测试基础设施与可复现的 Live 端到端

**Files:**
- Modify: `vitest.config.ts`、`package.json`（scripts）
- Create: `backend/tests/test_live_e2e.py`、`prototype-tests/live_e2e.md`
- Create: `docs/evidence/<date>/live-e2e/`（运行产物）

- [ ] **Step 1：补上类型检查门禁**

vitest **不做类型检查**，而仓库里没有任何 script 或 CI 步骤跑 `tsc`。加 `"typecheck": "tsc --noEmit"` 并在 `"test"` 里串起来，否则套件会在一个编译不过的应用上报绿。

`vitest.config.ts` 的 include glob 只有 `*.test.ts`：新建的 `*.test.tsx` 会被静默跳过且退出 0。要么把 glob 扩成 `*.test.{ts,tsx}` 并加 jsdom + `@testing-library/react`，要么明确记录「组件级渲染断言不在本阶段范围，由 Task 6 抽出的纯函数 + Playwright 端到端覆盖」。**计划在此明确选后者**：零新增 npm 依赖，IT-UI-01 的渲染部分由 Playwright 断言。

- [ ] **Step 2：Live 端到端（零 npm 依赖）**

启用它的关键事实容易被忽略：`backend/app/main.py:66-68` 在 `dist/` 存在时把它挂成 StaticFiles，所以**一个 uvicorn 进程同时提供 `/api` 和构建好的 UI，同源**，不需要 Vite dev server、不需要代理、不触发 CORS（`config.py:30` 本来也只允许 `:5173`）。Playwright 1.60.0 已在 `.venv`，Chromium 已安装，`playwright.sync_api` 能直接从普通 pytest 测试驱动浏览器（未安装 `pytest-playwright` 插件，也不需要）。

仍需补齐：把 playwright 写进 requirements（Task 1 已做）；setup 里跑 `npm run build` 或断言 `dist/` 存在（`dist` 是 git-ignored）；uvicorn 绑到空闲端口并用 tmp_path 作 `DRA_DATABASE_URL`；复用 `output/playwright/runtime.config.json` 里记录过的启动参数（`--use-fake-device-for-media-stream`、`--use-fake-ui-for-media-stream`、`permissions: ["camera"]`）。

**不要断言数值分数**：`--use-fake-device-for-media-stream` 产生动态合成图案，每一 tick 的 JPEG 都不同，`P_distraction` 不可复现。确定性杠杆在遥测侧。断言**契约**：operation_mode、`provenance.vision_source` / `telemetry_source`、10 类 / 3 类的类别数、D01 不变式、以及 **UI 显示值 == `GET /risk/latest` == 导出行**（这就是 IT-UI-01 的 oracle）。

- [ ] **Step 3：把 `requires_models` 的静默跳过变成显式**

`test_live_inference.py:14` 在 `ml/outputs/vision/mobilenetv3_large_vision.onnx` 缺失时跳过，而模型是 git-ignored（B05）。干净检出上五个最重的 live 测试全部 SKIP 而 pytest 仍退出 0 —— 一次**什么都没证明的绿**。新的 D01 / D02 测试必须写成不依赖权重（monkeypatch provider），并在汇总里显式打印跳过数量。

- [ ] **Step 4：跑完整门禁并归档证据**

```bash
cd /Users/liu/Desktop/FYP2-Live-System
export PYTHONDONTWRITEBYTECODE=1
npm run build
(cd backend && TMPDIR=$(mktemp -d) PYTHONPATH=. ../.venv/bin/python -m pytest tests -q -p no:cacheprovider)
./node_modules/.bin/vitest run --no-cache
./node_modules/.bin/tsc --noEmit
./node_modules/.bin/eslint .
```

把四份输出、端到端截图、导出的 JSON/CSV、以及 Task 1 的 manifest 一并写进 `docs/evidence/<date>/live-e2e/`。**不要**写进 `output/`（已 git-ignored 并按用户要求删除）。

**R3 边界**：Task 10 只做 Live 端到端，始终针对**稳定模型**运行，不包含任何候选模型或离线影子评估（那属于 Task 10A）。Task 10 的 Live E2E 同时是 Task 10A provider 改造的**回归基线**。

- [ ] **Step 5：Commit**

---

## Task 10A：模型替换与集成验证（系统侧离线影子评估）—— R3 新增

> 本节记录 2026-10-13 用户拍板的决定及其影响。**这里只立范围、决定、前置条件与 DoD**；具体接口与步骤在 Task 10A 开工时再细化成可执行的 brief，届时不再重新讨论下面「已拍板的决定」。

**目的（用户裁定 B）**：为报告提供一套**可辩护、有文档**的模型替换流程，重点是**影子评估与对比证据**。线上可能一直保留现有 MobileNetV3，**正式替换那一步未必执行**。因此 Task 10A 的 DoD 必须在**不执行替换**的情况下也能完成。

### 已拍板的决定（不得再议）

1. **方案 = 系统侧离线影子评估**（三个候选方案中的方案 1）。否决「后端实时双模型影子推理」（推理延迟翻倍、要改 schema、要动刚稳定的 Live 管线，且本项目没有真正的生产环境）与「评估全部放在 ML 分支」（会产生第四份融合实现，且走不到运行时的预处理路径）。
2. **只有视觉模型是替换候选**。遥测的部署模型固定为 **XGBoost**；**RF 与 LR 只做 benchmark**，运行时永不加载。
3. **视觉 provider 使用独立的 runtime manifest**，执行严格的校验：预处理、类别映射、输入/输出契约、路径、哈希。provider 不再写死模型名称、架构名或文件名。
4. **`runtime_manifest.json` 与 `evaluation_metrics.json` 分离**。runtime manifest 只描述加载、预处理、输入/输出契约、类别映射与产物完整性；评估指标（如 `macro_f1`）只作为实验证据，**不是**加载的前提条件，provider 不得读取它。
5. **离线评估器复用现有的 `TrainedProvider`、融合逻辑、EMA 与 Alert FSM**，不在 ML 轨道重复实现。
6. **分工**：Codex（ML 轨道）交付**冻结的候选模型包**与评估产物；系统轨道负责兼容性检查，以及「稳定 vs 候选」的对比评估。
7. **Task 10（Live E2E）与离线影子评估分开**。
8. **基于构造场景的融合结果，不得作为现实世界多模态风险预测准确率来陈述。**
9. **版本化模型发布 + 受控回滚**，不覆盖现有稳定产物。
10. 全部在本机运行，不接 CI；线上模型在用户明确批准之前**绝不替换**。

### 决定带来的影响

**对系统代码**：

- 需要去掉的硬编码：`backend/app/providers/trained.py:24`（provider 名）、`:34-35`（文件名）、`:64`、`:67`（架构名）；`backend/app/routers/status.py:52`（provider 名回退值）。
- `scripts/freeze_manifest.py:50-62` 的 `MODEL_BASELINE` 是稳定基线的路径与哈希记录，**应保留**，它正是「预期的冻结产物」的来源之一。但发布清单冻结需要能额外记录版本化发布的模型。
- 现在 `trained.py:36-37` 从 `metrics.json` 读类别与特征顺序，即评估文件兼任了运行时契约。分离后，provider 只读 runtime manifest，并要有测试钉住「provider 不读评估文件」。
- **稳定基线也需要一份 runtime manifest**（以新文件补写，不改动模型产物），这样稳定模型与候选模型走**同一条**加载路径，不留两套代码。
- provider 改造会触及 Live 推理路径，所以必须以 Task 10 的 Live E2E 作为回归基线。这也是 Task 10A 排在 Task 10 之后的原因。
- `DRA_MODEL_ROOT` 是进程级设置（`config.py`，`env_prefix="DRA_"`）。离线评估器应在**独立进程内**直接调用 provider，**不起服务器、不写开发数据库**。这是「隔离的本地 A/B 评估」，**不是**生产环境的并行影子部署。
- 每条记录已带 `vision_model_sha256` / `telemetry_model_sha256`（provenance 与 CSV 导出），可据此区分每条记录由哪个模型产出，包括跨越一次模型切换的会话。

**对模型契约（ML 轨道导出候选之前就必须知道）**：

- **元数据校验 ≠ 模型行为校验**。现有加载检查（`trained.py:38` 类别码、`:50` 输入形状、`:60` 预热输出形状）只核对元数据「声称」的内容。如果导出的模型类别索引顺序不同，元数据照样写 `c0…c9`，加载会成功，`P_distraction = 1 − P(c0)` 却会悄悄算错。因此必须：
  - 保留并校验训练时的 `class_to_idx`（现有 `.pt` 中存有 `classes` 与 `idx_to_name`，见 `ml/vision/train_vision.ipynb` cell 20）；
  - 用一份**冻结、带标注的契约冒烟数据集**做行为检查（例如每个类别的预测众数必须等于该类别）；
  - 冒烟数据集**不得取自最终 held-out test set**，test set 也不得反复用于选型或调试；数据本身不入公开仓库，只记录样本 ID 与文件哈希。
- **预处理契约必须声明，不支持的一律拒绝加载**。运行时目前只实现一套预处理（`trained.py:87-92`）：RGB → 直接缩放到 224×224（PIL `BILINEAR`，**不裁剪**）→ `/255` → ImageNet mean/std → NCHW float32。现有 MobileNetV3 的验证变换 `Resize((224,224))` + `Normalize(ImageNet)`（notebook cell 9）与之一致。**ResNet18 常见的 `Resize(256)` + `CenterCrop(224)` 属于不同的预处理，会被拒绝加载**；ML 轨道若希望候选能进入影子评估，必须用与运行时相同的验证变换。
- **输出语义必须声明**。运行时对 ONNX 输出做 softmax（`trained.py:106-107`）。如果候选模型导出的是概率而不是 logits，形状检查拦不住，结果会被二次 softmax 压平。manifest 必须声明输出是 logits。
- 训练 notebook 默认写线上路径（`ml/telemetry/train_telemetry.ipynb:466`、`ml/vision/train_vision.ipynb:827`、`:850`），候选必须输出到 `ml/outputs/runs/<run_id>/`（已写入 ML 轨道 prompt）。

**对产物完整性**：

- 校验 `model_path`：拒绝任何逃逸出候选包根目录的路径，包括路径遍历与基于符号链接的逃逸。
- **与现有开发环境的冲突需要调和**：本工作树里三个稳定模型文件本身就是指向主仓库的符号链接。containment 规则必须保住「候选包不能逃逸」的安全意图，同时不误伤稳定配置。具体规则在开工时确定，见下方「开工时须确定」。
- 对照**预期的冻结产物**校验 SHA-256。区分两件事：manifest 内自报的哈希只能发现意外损坏；与经批准的发布清单比对才能发现被替换。
- 「产物完整性校验」与「不同架构之间的行为对比」是两件不同的事，报告中分开陈述。

**对评估与对外陈述**：

- 证据严格分四层：
  1. 分支级单模态模型评估；
  2. 构造场景下的融合评估；
  3. 运行时鲁棒性评估；
  4. Live / replay 端到端集成测试（由 Task 10 承担）。
- 视觉模型替换后必须重新检查：概率校准（ECE、Brier）、RiskScore 分布、Low/Medium/High 分布、融合权重敏感性、阈值敏感性、Alert FSM 行为。基线与候选必须使用**同一组、固定的**成对输入。
- **模型准确率提升 ≠ 融合风险评估必然改善。** 没有同步的多模态风险真值，只能陈述「分类表现、校准、分数稳定性、运行时行为发生了哪些变化」，**不能**声称新模型的 RiskScore 更准确。构造场景只能证明运行一致性、敏感性与实现正确性。

**对部署与回滚**（仅当用户批准替换时才执行；不执行替换时，用临时目录演练一次切换与回滚，全程不触碰稳定产物）：

- 完整闭环：明确的审批关卡 → 稳定产物备份 → 候选晋级 → 晋级后回归测试 → 基线复核 → 发布清单冻结 → 回滚验证。
- **不预设需要替换的文件数量**。如果候选需要不同的预处理，那就不是换文件，而是改代码，必须另立任务。

### 前置条件

- Task 10 完成（Live E2E 作为 provider 改造的回归基线）。
- ML 轨道交付至少一个**冻结的候选模型包**及其评估产物（含带样本 ID 的 test 预测）。没有候选时，可以先完成 manifest 化的 provider 与评估器，并用**稳定模型对自身**跑通全流程作为自检。

### 开工时须确定（记录在此，不在本阶段决定）

1. runtime manifest 放在哪里：`ml/` 归 ML 轨道的文件范围，`backend/` 归系统轨道，需避免两条分支修改同一文件。
2. 符号链接 / containment 规则如何与现有的稳定模型符号链接共存。
3. 遥测是否也改用 runtime manifest，以统一加载路径（遥测不做替换）。
4. 构造场景的配对规则：需固定随机种子、冻结，且基线与候选完全相同。
5. 契约冒烟数据集的来源 split、规模与判定阈值。

- [ ] **Step 1–N**：开工时由 brief 细化。
- [ ] **Commit**：每个完成项一个本地 commit，规则同其他 task。

---

## Self-Review

**1. Spec coverage.** A01（unavailable 契约）→ Task 2/3/4/5；A02（冻结与可复现包）→ Task 1；A03（跨语言公式/EMA/FSM/freshness 独立测试）→ Task 2/3/5 + 共享夹具；A04（可观测错误事件与故障恢复）→ Task 7/8；A05（可复现端到端）→ Task 9/10。B01→Task 2/3/4；B02→Task 2/3；B03→Task 7；B04→Task 10；B05→Task 1。D01→Task 2–6；D02→Task 7/8；D11（replay 架构）→ Task 9。**未覆盖且已声明**：D03（五模型 HPO）、D04–D10、D12、E1–E5、PERF-01/02、UAT-01..05 —— 均为用户确认的 P1，不在本阶段。D13 显式声明不在范围。**R3**：模型替换与集成验证由新增的 Task 10A 承担（不含训练与调参，这些仍属 ML 轨道）。

**2. 类型一致性。** `assessment_available` / `FUSION_EPSILON` / `effectiveFusionDenominator` / `effective_weights` / `record_fault` / `MAX_ATTEMPTS_PER_REQUEST` / `classifyFailure` 在各 task 的 Interfaces 块中签名一致。`mapSystemHealth` 的权重参数在两种语言里都带 0.5/0.5 默认值，以保持既有两参调用点可编译。

**3. 比例。** 本计划约 600 行，对应约 700 行密集 spec 加五份影响面清单，未逐行转写实现代码 —— 代码块只出现在 SQL 迁移守卫、签名、命令这三类「签名与测试无法确定」的地方。

**4. 已知的计划内未决项**（执行时必须显式记录决定，不要默默选一个）：
- unavailable 窗口仍会占用 window_id 并产生一行记录（`windows.py:36-38` 在融合之前就原子自增）。Week 7 的「accepted request counts reconcile」要求计划说明 no-assessment 窗口算不算 accepted request。
- `RuntimeConfig` 是 `extra="forbid"` 且按会话持久化（`models.py:29`），新增字段会让旧会话用**新默认值**回放，而不是它们被创建时的语义。Task 5 提取 `alert_sustain_ms` 常量时会碰到这个。
- `StatusBadge.tsx` 是 `Pill.tsx` 的未使用副本，`MetricTile.tsx` 同样未被引用。只加宽 `Pill` 的 tone 会留下静默漂移。本阶段禁止删除，需记为已知死代码。

---

## R1 修订记录（2026-10-12）

| # | 问题 | 裁定 |
|---|---|---|
| 1 | worktree / 分支冲突 | `dev_cc` 已在主仓库检出，`git worktree add … dev_cc` 必失败。**直接在主仓库 `dev_cc` 开发**，不建工作树、不建分支 |
| 2 | AGENTS.md | 用户已删除。**不恢复**，只清理 `CLAUDE.md:107/122` 的悬挂引用；其余文档按「暂不整改」保持原样 |
| 3 | 503 可重试性在 Task 7/8 自相矛盾 | 拆分：模型缺失/加载失败 = 503 **不可重试**；模型执行期异常 = **500 可重试**。`ST-RECOVER-01` 改用 500 注入，新增 `ST-FAIL-04` 验证拆分 |
| 4 | `MAX_TRANSIENT_FAILURES` 语义含糊 | 改名 `MAX_ATTEMPTS_PER_REQUEST = 3`，定义为**每个逻辑请求最多 3 次投递**（1 首发 + 2 重试） |
| 5 | 退避表不自洽 | 只发生两次退避：2000 / 4000 ms。10000 ms 上限在 3 次投递下不可达，`backoffMs` 类型收紧为 `1 | 2` |
| 6 | 前后端 CSV 空值不一致 | 统一为**空单元格**（原前端写字面量 `unavailable`）。消歧义由 `assessment_available=false` + `SystemHealth=UNAVAILABLE` 承担，布尔一律小写 |
| 7 | EMA seed 约定未核实 | 已核实三份实现，**发现两处真实分歧**（首帧是否 round3；stale 后是否重新 seed）。裁定以 Python 为准，Task 5 Step 3b 改 TS |
| 8 | prepared 行能否真触发 missing | **原说法错误**。CSV 的 `vision_available` 在 Live 模式下根本不被消费；UNAVAILABLE 需显式关摄像头；~~`stale` 在 Live 完全不可达~~（**R4 更正**：可达，见 Global Constraints 的 D13 段） |
| 9 | 重试幂等 | 新增「重试身份」小节：整个 payload 在首投前冻结，重试逐字节重发 |
| 10 | D13 | 不修复，但作为已知限制追踪：新增 `UT-TIME-06` 行为快照测试 + 证据归档 + 禁止对外声称已解决 |
| 11 | canonical RiskUpdate | 列为硬约束。当前违规点（五视图重算 `DominantEvidence`、`LiveMonitor.tsx:45` 伪造 `SystemHealth`）由 Task 6 修 |
| 12 | 模型 checkpoint | 列为硬约束，三个文件只读。Task 1 记基线哈希，Task 10 重算并断言未变 |

## R3 决策记录（2026-10-13）：模型替换与集成验证

| # | 问题 | 裁定 |
|---|---|---|
| 1 | 模型替换流程的目的 | **B**：为报告提供可辩护、有文档的替换流程，重点是影子评估与对比证据；正式替换未必执行 |
| 2 | 替换范围 | 只有视觉模型是候选；遥测部署固定为 XGBoost；RF / LR 只做 benchmark |
| 3 | 整体方案 | **系统侧离线影子评估**，复用 `TrainedProvider`、融合、EMA、Alert FSM；否决后端实时双模型影子推理，也否决把评估全部放在 ML 分支 |
| 4 | 元数据 | `runtime_manifest.json` 与 `evaluation_metrics.json` 分离；provider 不读评估文件，不写死模型名 |
| 5 | 视觉 provider 校验 | 预处理、类别映射、输入/输出、路径、哈希全部严格校验；不支持的预处理拒绝加载 |
| 6 | 分工 | Codex 交付冻结的候选模型包与评估产物；系统轨道做兼容性检查与「稳定 vs 候选」评估 |
| 7 | 计划结构 | Task 10 只做 Live E2E；新增 **Task 10A**（模型替换与集成验证），排在 Task 10 之后 |
| 8 | 对外陈述 | 构造场景下的融合结果不得作为现实世界多模态风险准确率陈述 |
| 9 | 发布与回滚 | 版本化发布 + 受控回滚，不覆盖现有稳定产物 |

## R4 修订记录（2026-10-13）：Codex 独立审阅之后

来源：`docs/fyp2/review/CODEX_INDEPENDENT_AUDIT_REVIEW_2026-10-13.md`（下称「审阅」，编号 R01–R32）。阶段化的执行顺序见 `.planning/system-track/task_plan.md`。

**结论**：Tasks 1–6 的修复被确认成立（R04、R05、R11、R12、R13），**不需要重做**。计划需要一处事实更正、若干补测，以及三个新的待决政策项。

| # | 审阅编号 | 问题 | 处理 |
|---|---|---|---|
| 1 | R08 | 「Live 到不了 stale」是错的 | 已在 Global Constraints、R1 #8、风险表更正。**已完成（P1-2，`c7391b5`）**：`TASK_1_TO_6_SUMMARY.md` 加勘误；`UT-TIME-06` 的 docstring 与 source-string guard 改为完整 pipeline 的可反证测试（UT/IT-LIVE-AGE：经 `/infer` 的 2.999 / 3 / 3.001 s 边界与 30 天旧帧） |
| 2 | R30 | F4、F1 | 「等 Codex 审阅」的前提已解除。**F4 已完成**（`f289d66`、`9632812`：ROUND_HALF_UP 写回 Global Constraints 与 SDD `global-constraints.md`）；**F1 仍在本批待做**（`missing_cases.csv` W16/17/19） |
| 3 | R13 | 只有 `captured_at` 有 HTTP gap 测试 | **已完成（P1-3，`d83782d`）**：`test_out_of_order_guard_survives_a_gap_for_telemetry`，与 `captured_at` 版逐步对称 |
| 4 | R05 | 缺 near-epsilon 的 API 级变异防线 | 审阅修复批次补 IT-EPS：权重 1e-10 / 1e-9 / 1.1e-9，另一路 missing，双向 |
| 5 | R16 | 失败恢复的必测场景 | Task 7 / 8 的 DoD 追加，见 DoD 表 |
| 6 | R02、R17、R31 | 门禁原始日志、逐 ID 对账、NULL 导出 | Task 10 的 DoD 追加，见 DoD 表 |
| 7 | R09 | D13 最大证据年龄 / stale-only 守卫 | **待用户裁定**。审阅定为 P0 / P1，但明确不替需求发明阈值 |
| 8 | R10 | 相等时间戳 + 新 UUID 的重复证据能推进告警 | **待用户裁定**：重复证据是否算持续的新观察 |
| 9 | R14 | `DominantEvidence` 不接收权重，可能与加权贡献相反 | **待用户裁定**：定义为 raw strength 还是 weighted contribution。改语义需动三份实现与共享夹具，并修正报告与 UI 文案 |
| 10 | R16 | `MAX_ATTEMPTS_PER_REQUEST = 3` 被质疑为任意值 | 保留。这是用户裁定的 D02 Option 1，文档按「明确需求」陈述 |
| 11 | — | E2–E5（融合 / 时序层评估）由谁负责 | **建议系统轨道**，待用户确认。ML 分支停在 `efb3ea6`，那里是 Tasks 1–6 之前的旧融合代码；复用系统代码也与 R3 决定一致 |

**审阅没有逐项回答提示词中的 D-A…D-F。** 从 R30、R31、R17 能间接读出：ROUND_HALF_UP、迁移改写历史行（需披露）、不引入 jsdom，这三项未被推翻。其余 Ruling 视为未被质疑。

## 执行顺序与依赖

```
Task 1  冻结基线 / 工作目录 / lint / manifest
   │
   ├─► Task 2  ai/src 契约核心（+ 夹具 JSON）        ← 所有契约改动的源头
   │      │
   │      ├─► Task 3  Python 两份移植同步            （消费夹具）
   │      │      │
   │      │      ├─► Task 4  后端 schema / 迁移 / 导出
   │      │      │      │
   │      │      │      ├─► Task 5  时序路径（FSM / EMA 对齐）
   │      │      │      └─► Task 7  fault_events       （需要 Task 4 的 conftest）
   │      │      │                      │
   │      │      │                      └─► Task 8  前端有界重试   （需要 Task 7 的错误分类）
   │      │      └─────────────────────────────┐
   │      └─► Task 6  前端展示层                │   （需要 Task 2 的 availability.ts）
   │                      │                     │
   │                      └──────┬──────────────┘
   │                             ▼
   │                        Task 9  Live-only 范围   （需要 6 和 8 都落地）
   │                             │
   └─────────────────────────────┴─► Task 10  测试基础设施 + 端到端
                                          │
                                          └─► Task 10A  模型替换与集成验证（R3）
                                                        （另需 ML 轨道交付冻结候选模型包；
                                                          无候选时可先用稳定模型自检）
```

**R4 插入**：Task 7 开工前先完成「审阅修复批次」（F4、R08 更正与测试、F1、`telemetry_timestamp` 对称测试、IT-EPS）。R4 的三个待决政策项（R09、R10、R14）裁定后，各自作为独立 task 插入，位置在开工时确定。

**串行约束**：2 → 3 → 4 是硬串行（契约先立、再移植、再落库）。**可并行**：Task 6 只依赖 Task 2，可与 3/4/5 并行；但按 SDD 规则实现 agent 不并行派发，顺序按上图深度优先即可。

**批量机会**：Task 1 的 Step 3（eslint ignores 加一项）与 Step 5（requirements 补四行）是同形小改，与 Step 2 的 CLAUDE.md 两处引用清理合并为一次派发。

## Definition of Done（Task 1–10 与 10A）

每个 task 的 DoD = 下表全部满足 + 该 task 的全部 `- [ ]` 步骤勾完 + task review 通过（spec ✅ 且 quality approved）。

| Task | Definition of Done |
|---|---|
| **1** | `pwd`/`branch`/`HEAD` 三连核实输出已记入 ledger；`CLAUDE.md` 不再引用 AGENTS.md；`./node_modules/.bin/eslint .` 退出 0（存在工作树时也是）；`scripts/freeze_manifest.py` 可运行且输出含三个模型 SHA256 + split 哈希 + 实装依赖版本；`backend/requirements.lock.txt` 存在；四道基线门禁（pytest 28 / vitest 32 / tsc clean / eslint clean）复现并写入 `docs/fyp2/release/RELEASE_MANIFEST.md` |
| **2** | `ai/fixtures/fusion_vectors.json` 含且仅含 21 行；`ai/src/fusionVectors.test.ts` 与 `availability.test.ts` 全绿；`computeRiskScore` 两路缺失返回 `null`；`(1.0,0.0)+vision missing` 返回 `UNAVAILABLE`；`./node_modules/.bin/vitest run --no-cache` 绿（`tsc` 此刻**允许**报错，错误清单记入 ledger 移交 Task 6） |
| **3** | `backend/tests/test_fusion_vectors.py` 读**同一份** JSON 且全绿；`fusion.py` 与 `ai/reference/risk_logic.py` 两份都改且语义一致；`map_alert_severity` 加 None 守卫 + 「勿接线」注释；`pytest tests -q` 全绿（28 + 新增） |
| **4** | `conftest.py` 提供 tmp DB fixture 且新测试全部使用它；`RiskUpdate` 前置 + 后置两个 validator 都在；历史行读取不 500（`test_migration.py` 三行 fixture 验证）；`json('true')` 而非 `1`；CSV 表头含 `assessment_available`；`UT-FUS-03` / `UT-FUS-ZERO-WEIGHT` / `EX-NULL-01` / `ST-STATUS-01` 全绿 |
| **5** | `UT-TIME-01..06` 全绿（`06` 是 D13 行为快照，断言当前行为）；`UT-EMA-PARITY-01` 绿；unavailable 不写 `None` 进 `state['severity']`；新增 state 键全部进 gap-reset 元组；`test_audit_regressions.py:139` 与 `test_restart.py:44` **仍绿**（证明没误动 Python EMA） |
| **6** | `./node_modules/.bin/tsc --noEmit` **清零**；五个视图与 `ExplanationView` 都有 unavailable 分支；`LiveMonitor.tsx:45` 伪造 `SystemHealth` 已删除；视图读 `record.DominantEvidence` 而非重算；grep 断言 `SystemHealth === "UNAVAILABLE"` 不再出现在 `LiveMonitor.tsx`/`AlertBanner.tsx`；`.pill--unavailable` 样式存在；`preparedSessionInput.test.ts:31` 更新为 4 元集并绿 |
| **7** | `fault_events` 表无 FK、有唯一索引、用显式 `CREATE TABLE IF NOT EXISTS`；`record_fault` 绑 `db.get_bind()` 且在 `rollback()` 之后调用；DB 故障时文件 sink 有记录且原始异常原样抛出；`ST-FAIL-01/02/03/04` + `ST-RECOVER-01` 全绿；会话删除后 fault 仍可查。**R4 追加（审阅 R16）**：原生 ORT 运行期异常、单分支失败、DB commit 失败各有分类与测试；**每个 eligible 请求都有成功或失败的持久 outcome**，并为 logging ≥ 99% 写明两个分母（成功预测的持久化率、全部 outcome 的记录率），不得用 stored / stored 自证 |
| **8** | `retryPolicy.ts` 与 `liveLoop.ts` 为纯模块、node 环境可测；3 次投递后停止且不再排定时器；重试 payload 深度相等（同 request_id + 同帧 + 同时间戳）；pause-abort 不计数；`retry()` 不新建会话；时钟偏移有专属 category 与文案；UI 有可见 stopped 面板 + 手动 Retry。**R4 追加（审阅 IT-RETRY-IDENTITY）**：commit 之后 response 丢失、再以同 UUID 同 payload 重发 → DB 恰好一行、时序状态只推进一次；同 UUID 改 payload → 409 |
| **9** | `PREPARED_RAW_TELEMETRY` 导出存在且 Live 路径改用它；游标单调可注入、同一输入序列可复现；`loadConfig` 不会把用户静默带回 replay；replay 调用点在 `RiskLevel` 为 null 时不破坏不变式；`prototype-tests/README.md` 改为 Live 端到端清单 |
| **10** | `npm run typecheck` 存在并接入 `npm test`；`test_live_e2e.py` 在单 uvicorn + 静态 `dist/` 上跑通，断言 UI 值 == `/risk/latest` == 导出行；显式 stop camera 以触达 UNAVAILABLE；`requires_models` 跳过数显式打印；四道门禁全绿；三个模型 SHA256 与 Task 1 基线**逐一相等**；证据归档到 `docs/evidence/<date>/live-e2e/`。**R4 追加（审阅 R02、R17、R31）**：对账从 6 个单元格扩为**逐 ID 全行**（API 保存 = DB = latest = 同窗口 UI = 导出行）；门禁原始日志带 version / env / argv / exit / skips；capture → 预处理 → 模型 → commit → 网络 → render 分段计时（`windows.py:62` 的计时早于 commit，前端 `requestMs` 不含 render，所以目前未证明 ≤ 1 s）；`freeze_manifest.py` 在 `FYP_DATA_ROOT` 错误时不得静默回退；导出遇 NULL / 畸形 payload 有测试与守卫 |
| **10A** | provider 只经 runtime manifest 加载，代码中不再写死模型名、架构名或文件名，且有测试证明 provider 不读评估文件；稳定基线有自己的 runtime manifest，与候选走同一加载路径；预处理不支持、输出语义不符、类别映射或契约冒烟检查失败、路径逃逸、哈希不符时**一律拒绝加载**，每种情况各有测试；离线评估器复用 `TrainedProvider` / 融合 / EMA / Alert FSM，不起服务器、不写开发数据库，输出四层分开的对比报告，包含 ECE、Brier、RiskScore 与 L/M/H 分布、权重与阈值敏感性、FSM 行为；报告不含「RiskScore 更准确」一类表述；版本化发布与回滚流程已文档化，并在临时目录演练过一次（不触碰稳定产物）；Task 10 的 Live E2E 仍全绿；三个基线 SHA256 不变。**不要求执行正式替换** |

## 剩余技术风险

| 风险 | 影响 | 缓解 |
|---|---|---|
| **D13 过期证据可无限累积告警** | **高（R4 更正：Live 主运行时可达）** —— 旧 `captured_at` 经 `/infer` 即为 stale，且永不变 missing | `UT-TIME-06` 留证；最大证据年龄 / stale-only 守卫的政策**待用户裁定**（R4）；裁定前报告列为已知限制 |
| ~~**Live 永远到不了 `stale`**~~ | **R4：该风险的前提不成立**（Codex R08）。stale 在 Live 可达，所以 `ST-FAIL-01` 的 stale 步骤可以用旧 `captured_at` 经 `/infer` 构造 | 阶段 1 用完整 pipeline 测试（UT/IT-LIVE-AGE）替换 source-string guard |
| **`tsc` 抓不到静默比较** | 高 —— 五处 `=== "High"` / `=== "NORMAL"` 之类编译通过但语义错 | Task 6 用 grep 断言 + 抽纯函数单测补网 |
| **无 DOM 测试环境** | 中 —— 组件渲染断言只能靠 Playwright | 已决定不引入 jsdom；IT-UI-01 的渲染部分由 Task 10 承担 |
| **`requires_models` 静默跳过** | 中 —— 干净检出上五个最重的 live 测试 SKIP 而 pytest 退 0 | Task 10 显式打印跳过数；新测试不依赖权重 |
| **历史数据迁移改写用户数据** | 中 —— 把历史 `UNAVAILABLE` 行的四个值置 null 是不可逆的数据改写 | 迁移前备份 DB 文件；`test_migration.py` 三行 fixture 守护；**执行前需用户确认** |
| **`RuntimeConfig` 是 `extra="forbid"` 且按会话持久化** | 低中 —— 加字段会让旧会话用新默认值回放 | Task 5 提常量时避免进 `RuntimeConfig`；若必须进，加迁移说明 |
| **unavailable 窗口仍占 window_id** | 低 —— 影响 Week 7「accepted request counts reconcile」 | 在 DoD 里要求显式声明计数口径 |
| **主仓库直接开发，无隔离** | 中 —— 没有工作树兜底，误操作直接落在 dev_cc | 每 task 独立 commit；禁止 reset/clean；commit 需授权 |
| **候选模型类别顺序错位（R3）** | 高 —— 元数据照样写 `c0…c9`，加载成功，`1 − P(c0)` 静默算错 | Task 10A 加冻结的契约冒烟数据集做行为检查，并要求候选包保留训练时的 `class_to_idx` |
| **候选预处理或输出语义不一致（R3）** | 高 —— 形状检查拦不住，模型照常输出错误概率 | runtime manifest 声明预处理与输出语义，不支持的拒绝加载；**须在 ML 轨道导出候选前告知**（如 ResNet18 的 `CenterCrop`） |
| **符号链接 containment 误伤稳定配置（R3）** | 中 —— 稳定模型在本工作树中本身就是符号链接 | Task 10A 开工时确定兼容规则，并用测试覆盖两种情况 |
| **构造场景结果被过度陈述（R3）** | 中 —— 报告可能把运行一致性写成风险准确率 | 证据分四层；Task 10A 的 DoD 禁止「RiskScore 更准确」一类表述 |

## 建议的第一个编码包

**Task 1 + Task 2 合并为第一个派发包**，理由：

- Task 1 全是配置与脚本，零应用逻辑，风险最低，且它产出的基线哈希是后续一切的锚点；
- Task 2 是整条契约链的源头，**它定下的签名决定了 Task 3–6 的全部接口**，越早冻结越好；
- 两者都不触碰后端运行时，失败回滚代价最小；
- Task 2 的验收是纯数值的（21 行夹具已被独立复算确认），review 的判据客观，不依赖主观判断。

派发建议：Task 1 用便宜模型（机械改动 + 脚本），Task 2 用标准模型（跨文件契约设计）。两者之间插一次 task review，不要合并评审 —— Task 2 的接口一旦评审放过就会被下游六个 task 消费。
