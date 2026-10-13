# 任务计划：FYP2 系统开发轨道 Roadmap

本文件是**系统轨道**的持久化路线图（Claude 负责）。ML 轨道（Codex）另有自己的范围，见 `docs/fyp2/review/CODEX_ML_TRACK_PROMPT.md` 与其补充说明。
权威的逐任务实施细节仍以 `docs/plans/2026-10-12-fyp2-live-system-completion.md`（下称「计划」）为准；本文件只管**阶段、顺序、状态和待决事项**。

## 目标

把 Live-only 系统做完整、可复现、可被证据支撑：修完 Codex 独立审阅（`docs/fyp2/review/CODEX_INDEPENDENT_AUDIT_REVIEW_2026-10-13.md`）确认的缺口，完成计划 Task 7–10 与 10A，再为报告准备系统级证据。不训练模型，不宣称超出证据的结论。

## 下一步

**阶段 1 已开工（2026-10-13，用户说「开始」）**，由本会话执行，第一项是 F4。

## 当前阶段

阶段 1（in_progress）

## 工作环境（不得偏离）

| 项 | 值 |
|---|---|
| 系统轨道工作树 | `/Users/liu/Desktop/FYP2-Live-System`，分支 `fyp2/live-system` |
| ML 轨道 | 主仓库 `/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1`，分支 `fyp2/ml-training`（Codex 正在使用，**不得触碰其工作区**） |
| 提交规则 | 只在 `fyp2/live-system` 本地提交，每个完成项一个 commit；**最后统一 push**；`main` 不改，变更先进 `dev_cc` 再经 PR 进 `main` |
| 开发方法 | subagent-driven development：实现 agent → 独立 task reviewer（spec + quality）→ 变异验证 → ledger `Ruling:` |
| SDD 工作区 | `.superpowers/sdd/2026-10-12-fyp2-live-system-completion/`（git-ignored，含 progress.md ledger） |
| 门禁 | `cd backend && TMPDIR=$(mktemp -d) PYTHONPATH=. ../.venv/bin/python -m pytest tests -q`；`./node_modules/.bin/vitest run --no-cache`；`./node_modules/.bin/tsc --noEmit`；`./node_modules/.bin/eslint .`（不用 `npx`，会被 rtk 改写） |
| 模型文件 | 三个基线产物只读，哈希见计划 Global Constraints |
| 数据库 | 不迁移、不改写原始开发数据库；需备份 + 用户明确批准 |
| 汇报 | 中文；Codex 反馈原文展示；一次只问一个问题 |

## 各阶段

### 阶段 0：Tasks 1–6 + F2（已完成）
- [x] Tasks 1–6：commits `845b43a..564d0b1`，Codex 审阅确认 B01/B02/Task 5 FSM 已修（R04、R05、R12）
- [x] F2：`ef2417d`，验收 PASS，Codex 确认（R13）
- [x] R3：模型替换决定写入计划，新增 Task 10A（`0822cac`）
- **状态：** complete

### 阶段 1：审阅修复批次（Task 7 之前）
- [x] **F4**（`f289d66`、`9632812`，验收 PASS `9db6e2a`）：`ROUND_HALF_UP`（score 1 位、EMA 3 位）写回计划 Global Constraints 与 SDD `global-constraints.md`（Codex R30 确认）
- [x] **R08 更正**（`c7391b5`，评审 clean）：「Live 不会出现 stale」的说法是**错的**。`run_inference` 按 `provenance.captured_at` 重判 freshness（`inference.py:107`），`test_live_inference.py:114-118` 本身就断言旧 `captured_at` 经 `/infer` 得到 `stale` / `DEGRADED`。要改：计划第 44 行与 R1 #8、风险表、`TASK_1_TO_6_SUMMARY.md` 加勘误、`test_temporal_contract.py` 中 UT-TIME-06 docstring 与 source-string guard 改为完整 pipeline 的可反证测试（UT/IT-LIVE-AGE：经 `/infer` 的 2.999 / 3 / 3.001 s 边界与 30 天旧帧）
- [x] **R13 补测**（`d83782d`，评审 clean）：`telemetry_timestamp` 的对称 HTTP gap 测试（F2 遗留 minor 4）。变异 M2 下它是 telemetry 水位线唯一的行为防线；两条 gap 测试都依赖 D13 现状（stale-only 仍得 High），阶段 5 落地证据年龄策略时第 1 步会响亮失败，届时改用 fake clock
- [x] **R05 补测**（`2c07d79`，评审 clean）：IT-EPS —— 经 API 的 near-epsilon 权重（1e-10 / 1e-9 / 1.1e-9），杀死 producer 的 `>` → `>=` 与 `> 0` 变异（改动前旧测试集在两种变异下都全绿）
- [x] **P1-6 TS 舍入违规**（`b53f007`，评审 clean）：`asPercent` 与 `formatPercent` 改为先在小数上 half-up 再放大；`round3` 改为 half-up。回放 25 个窗口 + 25 条记录（含解释文本）改动前后逐字节相同（SHA-256 一致），停止条件未触发
- [ ] **F1 / R30**：同步 `missing_cases.csv` W16/17/19 期望值与最新契约
- **状态：** pending

### 阶段 2：Task 7 + Task 8（失败恢复，按计划 + R16 补充）
- [ ] Task 7 `fault_events`：在计划 DoD 之外补 —— 原生 ORT 运行期异常的分类、单分支失败、DB commit 失败；**每个 eligible 请求都有成功或失败的持久 outcome**（为 logging ≥ 99% 定义两个分母）
- [ ] Task 8 有界重试：补 IT-RETRY-IDENTITY —— commit 之后 response 丢失再同 UUID 重发，DB 恰好一行、状态只推进一次；同 UUID 改 payload → 409
- [ ] **重试与新鲜度的交互（2026-10-13 新增，开工 Task 8 前写进计划）**：为保幂等，重试逐字节重发同一 payload，`captured_at` / `telemetry_timestamp` 是首次采集值；退避 2 s + 4 s 后第 3 次投递距采集 ≥ 6 s，第 1 次若因 10 s 超时失败则第 2 次即已超过 3 s 容差。重试成功落库的窗口会被判为 stale / DEGRADED，并按 D13 现状继续累积 sustained-High。需在 Task 8 DoD 中声明并测试，且与阶段 5 的 D13 政策联动
- [ ] **R5（用户批准 2026-10-13）**：摄像头停止后循环继续 —— 帧为 null 照发、不计失败、不停止；全空输入得到 UNAVAILABLE（`liveLoop.test.ts` + API 测试）。见计划 Task 8 与 DoD 8
- [ ] `MAX_ATTEMPTS_PER_REQUEST = 3` 是**用户裁定的策略**（D02 Option 1），在文档中按「明确需求」陈述，回应 Codex「不能随意写 3」
- **状态：** pending

### 阶段 3：Task 9（Live-only 范围落地）
- [ ] 按计划执行
- [ ] **R5**：游标改动保持 Task 8 的循环行为；开工前定游标语义（2 s 节奏 vs 按窗口推进），它决定 ST-BRANCH-T-CONTINUITY 的预期
- [ ] **P1-6 遗留**：趋势图 tooltip（`trendSeries.ts:32` → `formatTrendTooltip`）先 ×100 再 `formatFixed(…, 1)`，二进制噪声会越过平局（0.2855 → 28.5%）。改为先在小数上 half-up 再放大，与 `asPercent` 同一做法，并加平局用例
- **状态：** pending

### 阶段 4：Task 10（Live E2E，按计划 + R02/R17/R31 补充）
- [ ] E2E 对账从「6 个单元格」扩为**逐 ID 全行**：API 保存 = DB = latest = 同窗口 UI = 导出行
- [ ] 门禁原始日志带 version / env / argv / exit / skips，归档 `docs/evidence/<date>/live-e2e/`
- [ ] 分段计时 capture → 预处理 → 模型 → commit → 网络 → render（`windows.py:62` 计时早于 commit；前端 `requestMs` 不含 render）
- [ ] `freeze_manifest.py` 在 `FYP_DATA_ROOT` 错误时不得静默回退
- [ ] R31：导出遇 NULL / 畸形 payload 的测试与守卫（`export.py:51`）
- [ ] **R5 单分支系统测试**：ST-BRANCH-T-SMOKE / T-CONTINUITY / V / ZERO（计划 Task 10 Step 2A）。测试工具内拦截请求，产品代码不改
- **状态：** pending

### 阶段 5：需用户裁定的政策项（裁定后再实现）
- [ ] **R09 / D13：已裁定 A**（2026-10-13，用户本人确认；待实施）：过期证据按 missing 计分，provenance 保留 `{modality}_expired` / `{modality}_age_s`；运行时不再产出 stale，0.45 只留给历史记录；阈值 = `freshness_tolerance_s`，默认 3 s、可配 (0, 30]，只称设计阈值，须用 PERF-01 与 2 / 3 / 5 s 敏感性复核。实施时同步改：IT-LIVE-AGE 3001 ms / 30 天 / D13 快照、两条 gap 测试第 1 步（改 fake clock）、F1 W16（62.5 → 60.0）、Task 8 重试窗口的预期
- [ ] **R10**：相等时间戳、新 UUID 的重复证据是否算「持续新观察」
- [ ] **R14**：`DominantEvidence` 的语义 —— raw strength 还是 weighted contribution。现算法不接收权重，w=.3/.7 时可能标「Vision-dominant」而 telemetry 贡献更大。改语义要动三份实现 + 夹具
- **状态：** pending（等待裁定）

### 阶段 6：Task 10A（模型替换与集成验证，计划 R3）
- [ ] 按计划 Task 10A；前置：Task 10 完成 + Codex 交付冻结候选包（无候选时用稳定模型自检）
- **状态：** pending

### 阶段 7：系统级评估与报告证据（待确认归属）
- [ ] E2 权重 / 构造 strata（固定 pair manifest、独立 oracle）
- [ ] E3 freshness 9 组合、Δ = .4 如实报告 target 未达
- [ ] E4 EMA step lag（alpha 1 vs .35，1 s 与 0.1 s cadence）、FSM、性能与 logging 分母
- [ ] E5 只改一路的配对反事实、稀释反例
- [ ] 目标摄像头的带标注可用性检查（394 帧全为 c8 暴露的问题；需用户本人录制，数据不入公开仓库）
- **状态：** pending（**归属已定：系统轨道负责**，用户 2026-10-13 确认；理由见 findings.md）

### 阶段 8：发布与合并
- [ ] 整分支评审 → `fyp2/live-system` 合入 `dev_cc` → 统一 push → 之后 PR 进 `main`
- [ ] UAT：真实参与者执行（用户主导），系统轨道提供任务脚本与记录表
- **状态：** pending

## 关键问题

1. ~~E2–E5 由谁负责？~~ **已定：系统轨道**（用户 2026-10-13 确认）
2. D13 最大证据年龄的阈值与策略（阶段 5）
3. `DominantEvidence` 语义（阶段 5）
4. 待删 / 归档文档清单（见 findings.md「文档整理」）

## 已做决策

| 决策 | 理由 | 来源 |
|---|---|---|
| 只保留 Live Monitoring 为正式运行模式 | 用户裁定 | 计划 Global Constraints |
| nullable 风险契约 + `assessment_available` | 用户裁定 D01 | 计划 |
| 失败策略：3 次投递后停止 + 手动重试 + fault 表 | 用户裁定 D02 Option 1 | 计划 R1 |
| ROUND_HALF_UP 统一三份实现 | Codex R30 确认为有意的数值改变 | ledger Ruling；阶段 1 写回 |
| 模型替换 = 系统侧离线影子评估，新增 Task 10A | 用户裁定 2026-10-13 | 计划 R3 |
| E2–E5（融合 / 时序层评估）归系统轨道 | ML 分支停在 Tasks 1–6 之前的旧融合代码；复用系统代码与 R3 一致 | 用户 2026-10-13 |
| 下一步从阶段 1 开始，**不是从 Task 4 重做** | Codex 确认 Tasks 1–6 的修复成立（R04/R05/R12/R13） | 本文件 |

## 遇到的错误

| 错误 | 尝试次数 | 解决方案 |
|---|---|---|
| 曾宣称「Live 不会出现 stale」 | 1 | Codex R08 判 INCORRECT，已核实；阶段 1 更正 |
| A–G 防范清单审查的合并步骤因会话额度失败 | 1 | 三个视角的原始结果保存在 workflow journal（`wf_fbb31b26-162`），未复核，未写入计划 |
