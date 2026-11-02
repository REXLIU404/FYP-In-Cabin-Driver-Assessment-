# Task 10A 阶段门复审：Stage 3（Runtime Evaluation）与 Stage 5（Release Decision）

审计人：独立只读审计子代理。日期 2026-10-30，我的命令在 06:47Z–07:00Z 之间运行。
对象：`fyp2/live-system` @ `f5fb90f`（范围 `1cd5660~1..f5fb90f`：`1cd5660`、`637a0ff`、`f15f539`、`a46f80d`、`f5fb90f`）。

缩写：
- `INTEG=/Users/liu/Desktop/FYP2-Live-System-Integration`
- `LIVE=/Users/liu/Desktop/FYP2-Live-System`（现为另一会话的 `fyp2/dmd-adaptation` 工作树）
- `ML=/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1`
- `SP2=/private/tmp/claude-501/-Users-liu-Desktop-FYP-In-Cabin-Driver-Assessment--1--claude-worktrees-exciting-keller-fdf913/e713c74d-2981-4f3f-bccb-7aa94bfb77b4/scratchpad/r2`（我的全部输出都在这里）

只读声明：
- 三个工作树都没有编辑、暂存、提交或清理。`git status --porcelain` 前后逐字相同：INTEG 0 行，LIVE 10 行（另一会话的文件），ML 1 行。
- 测试和演练都在全新克隆中进行：`SP2/clone`、`SP2/mut`、`SP2/drillclone`、`SP2/envprobe/repo`，均检出 `f5fb90f`。用 `LIVE/.venv` 只读运行，设 `PYTHONDONTWRITEBYTECODE=1`。
- 没有访问 8000 端口。对 `driver_risk.db*` 只用 stat 看了 mtime（10-29），没有打开。
- DOCX 先复制到 SP2 再读，原件 sha `ea1778c1…` 不变。
- scratchpad 根目录里有更早会话留下的文件（如 `release_decision.revised.md`）。我没有使用其中任何文件，脚本都在 `SP2` 里重新写。
- 用户在对话中的决定我看不到。下文的 FUD-1/4/5、U-5、Table 23 都**按实现方的记录**处理。harness 转述的唯一用户原话是「是的，也接受」，与「接受」一致，但我无法确定它对应哪几项。

## 1. Verdict table

### Stage 3

| 审计点 | 实现方声明 | 本人核查（打开的文件 / 我运行的命令及 exit code） | 结果 |
|---|---|---|---|
| S3-a 延迟 JSON 当日生成，MN 与 RN 都有 | 10-30 stable/RN 交替各 3 轮，每轮 600 窗口 | **B1** `python3 -I -B SP2/b1_recompute.py SP2/clone/docs/evidence/2026-10-30/stage3-raw` **exit 0**：<br>• 6/6 的 `generated_utc` 都是 10-30（05:38–05:44Z）<br>• 每轮 600 窗口 + 20 预热，`short_run=false`<br>• `vision_model`：stable `b3a42e8d…`，RN `5e226722…`<br>• 采集时间 05:37:25Z–05:44:21Z，晚于 `1cd5660` 的提交时间 05:37:06Z<br>• `runs.log` 记录 commit `1cd5660`，6 次 exit 0<br>• 克隆中的文件与 INTEG 工作区一致（`diff -r` 无差异） | PASS |
| S3-b RN 场景下 p95 是实测值 | RN p95 45/44/43 ms | B1 从原始窗口复算，RN p95 为 45/44/43，计算方式是逐窗口 `renderedAtMs-capturedAtMs`，没有外推 | PASS |
| S3-c（R-1）六轮可由原始样本复算 | sha 绑定，复算与汇总相等 | B1 用我自己的代码，不导入仓库代码：<br>• 6/6 的 sha256 等于 `raw_timings.sha256`<br>• `capture_to_render` 的 n/min/median/p95/max 全部相等：stable 27/31/127、28/31/63、28/31/58；RN 42/45/125、41/44/63、41/43/75<br>• capture_to_send、network、render 三段也相等；每行 c2r−三段之和 = 0<br>• `windowId` 为 21..620；采集间隔 ≥100 ms 且单调；`attemptIndex` 都是 1<br>• 线性插值 p95（仅作参考）：31/45/31/44/31/43.05<br>• 服务端分段只有汇总值，原始文件里没有 | PASS |
| S3-d 测试先红后绿，且加强后有效 | 29 passed；加强后的测试能抓到恒定时长变异 | **B2** 克隆 `f5fb90f`，运行 `pytest tests/test_perf_scripts.py`：**exit 0，29 passed**。<br>**B3** RED：同一测试放到 `e07ef42:scripts/perf01.py` 上，**exit 1**（`KeyError: 'raw_timings'`）。<br>**M1** 在 `SP2/mut` 中让原始文件写成恒定 30 ms：<br>• 加强后的测试 **exit 1**（median 30≠50，min 30≠20）<br>• 同一变异放到 `637a0ff` 的旧测试上 **exit 0**。这说明旧测试确实太弱，加强是有效的<br>**M2** 原始文件保留预热窗口：**exit 1**。<br>变异文件已还原 | PASS |
| S3-e 全量测试当日重跑 | f15f539 全新克隆门禁 pytest 1360 / 0 skipped / 8 deselected，vitest 1061 | 打开 `INTEG/docs/evidence/2026-10-30/stage5-coldstart-f15f539/`：生成于 10-30 06:33:47Z，build/pytest/vitest/tsc/eslint 五个门禁都是 EXIT CODE 0，日志写明「no model-dependent test was skipped」。<br>`git diff --stat f15f539 f5fb90f` 只有 docs。<br>**B6** 在 `SP2/drillclone`（`f5fb90f`，模型只读链接）运行 `DRA_REQUIRE_MODELS=1 pytest tests -m 'not e2e'`：**exit 0，1310 passed，58 deselected**，没有跳过模型相关测试。<br>e2e 和前端门禁我没有重跑；自 `e07ef42` 以来非文档改动只有 `scripts/perf01.py` 和它的测试 | PASS |
| S3-f 健康 | 0 控制台错误；全部 exit 0 | B1：6/6 `console_errors=[]`，`attempts_other_than_1=0`。<br>10-30 perf01 的服务器日志无法恢复，README 已说明。<br>我重跑的演练中两份 uvicorn 日志 error/traceback 为 0 行。<br>DB 权威性/幂等测试包含在 B6 中，全部通过 | PASS |
| S3-g 日志完整性（RN） | 10-29 perf02 210/210 | 打开 `docs/evidence/2026-10-29/perf-stage3/{stable,rn}/perf02.json`：<br>• D1/D2 都是 210/210，completeness 1.0<br>• stable 入库 209，另有 1 个 `input_validation` 故障<br>• `active_vision` 字段正确 | PASS |
| S3-h 用户决定的记录一致性（FUD-1/FUD-5） | 记录在 `stage3_audit_table.md` §7 | 已提交的文档之间一致：`stage3_audit_table.md` §6–7、`stage5_audit_table.md` 补充节。<br>但 BOARD（git 忽略）最后一条 14:33 仍写「FUD-1/FUD-5 待用户回答」，之后没有新条目（N-3） | PASS（附 N-3） |

### Stage 5

| 审计点 | 实现方声明 | 本人核查 | 结果 |
|---|---|---|---|
| S5-a 回滚可执行且被验证（演练日志 exit 0） | 11/11 PASS | 运行前确认 8001 空闲（lsof exit 1）。<br>**B5** 在 `SP2/drillclone` 中，把 `ml/outputs` 和 `.venv` 只读链接到 LIVE，运行未修改的 `drill.py SP2/drill_out`：**exit 0，RESULT PASS（11/11）**，HEAD `f5fb90f`。<br>• 候选在役：`VisionCandidateONNX+XGBoost`，`5e226722…`<br>• 新进程不设变量：`MobileNetV3ONNX+XGBoost`，`b3a42e8d…`<br>• 遥测两次都是 `9802cb06…`<br>• `/infer` 都返回 201；RiskScore/P_distraction 与原始演练逐位相同（85.0/0.7100527882575989；99.5/0.9999986290931702）<br>我自己对 LIVE `ml/outputs` 下 94 个文件计算 sha+mtime：演练前、演练后、B6 之后三次完全一致。结束时 8001 空闲。<br>`drill.py` 自 `637a0ff` 起没有改动。原始演练时间 05:45:44Z，在 `1cd5660` 上 | PASS |
| S5-b 决策记录引用 Stage 2/3 证据，路径可打开 | 每个路径都可打开 | 脚本逐个检查 `release_decision.md` 中反引号里的路径：<br>• 所有 `docs/...` 证据路径在 INTEG 和 LIVE 都存在；ML 绝对路径存在<br>• 3 个 git 忽略的模型路径只在 LIVE 存在，INTEG（现在承载 `fyp2/live-system`）中不存在：`ml/outputs/candidates/index.json`、`…/p5_resnet18_search004_seed42_20261023/`、`ml/outputs/vision/mobilenetv3_large_vision.onnx`（N-2） | PASS（附 N-2） |
| S5-c 决策记录数字与来源一致（包括新加的 90/3226、63/3226、129/150） | 见 §1/§2 | **B7** `ML/.../p4b_20261022/evaluation_metrics.json`（sha `4f1c517a…`）：<br>• stable：Acc 0.8988 / MF1 0.8746 / LL 0.5745<br>• RN：0.9016 / 0.8892 / 0.4509<br>• MN-HPO：0.8731 / 0.8677<br>• c0 召回 0.9211/0.8329，c9 召回 0.2733/0.4920；n=3657，c0=431，分心帧 3226<br>• stable 二分类错误 3657×(1−0.96473)=129.000，误报 0.090487×431=39.0，所以漏报 **90**（2.79%）；RN 错误 150，误报 87，漏报 63<br>**B8** 候选包 RN `predictions_test_clean.csv`（sha `6f7e8946…`，与 ML 包中副本一致）逐行计数：<br>• 3657 行，全部是 clean，4 名驾驶员 p012/p026/p035/p050<br>• 误报（P_d≥0.5）87，漏报（P_d<0.5）**63**，0.5 处没有平局<br>• 二分类准确率 0.95898，c0/c9 召回 0.8329/0.4920<br>stable 的 90 无法逐行计数：p4b 没有 stable 的逐行文件，我也不重跑模型（红线）。但这一推导在算术上精确，§2 也注明是推出的。另注：按阈值计算的 90 与按 argmax 得到的 93（混淆矩阵第 0 列）是不同口径，记录用的是阈值口径，正确。<br>**其他数字：**<br>• E1：10.45/3.80，48.32/56.99；18 个条件中 RN 更低 8 个、stable 更低 9 个、持平 1 个，符合「互有胜负」<br>• runtime p95 7.2472/25.4215；模型大小 16.07/42.65 MiB<br>• Stage 2：从 `comparison_results.json`（sha `6db717f1…`）复算得 0.91 / 5 / 12<br>• Stage 1 行与 `official_stable200_behavior.json` 一致：stable 用 parity100（n=100，最大误差 1.78e-7），stable200 按每类众数规则，`NO_STABLE200_REFERENCE`；RN stable200 误差 1.48e-6 ≤ 1e-4，argmax 一致 1.0<br>• 正面摄像头：README 第 20 行「5 times in about 5,170 frames」<br>• DOCX 副本中 Table 16/17/18/20 与以上一致；长会话 8,867 个窗口一致<br>小问题：`stage1_audit_table.md` 本身不含 VERIFIED_PASS（N-4） | PASS（附 N-4） |
| S5-d 两个选项呈现是否公平 | 已对称化 | 现在两边对称：<br>• 误报和漏报两侧都列出，并给出合计 129/150<br>• 小样本告诫明确同时适用于 A 的 c0 差异和 B 的整体提升<br>• B 的优点列完整（F1、log loss、漏报、c9）<br>• 写明「选择 B 也是有依据的选择」；更看重误报一侧被标为「判断，不是测量结论」<br>剩余措辞小问题见 N-5，不构成不公平 | PASS（附 N-5） |
| S5-e 版本化配置与回滚，不覆盖稳定产物 | 唯一开关 `DRA_ACTIVE_VISION` | `git show f5fb90f:backend/app/config.py`：`active_vision="stable"`，`env_file=".env"`。<br>**B9** 探测：在仓库根目录 cwd 下读的是根目录的 `.env`，在 `backend/` 下读的是 `backend/.env`；两个 `.env` 去掉后为 `stable`。INTEG 与 LIVE 的根目录和 `backend/` 下都没有 `.env`。§4 的说法正确。<br>模型 sha 都是冻结值（B5）。<br>附注 N-2：§4 的命令需要仓库根目录下有 `.venv` 和 `ml/outputs`，INTEG 两者都没有 | PASS（附 N-2） |
| S5-f 不自动启用 ResNet18，默认值与 U-5 = A 一致 | 默认 stable，不需改配置 | config 默认值是 stable；B5 中不设变量启动得到 stable；`backend/app` 在范围内没有任何 diff | PASS |
| S5-g 决定记录的一致性（U-5 = A、Table 23 用 10-30、FUD-4） | release_decision §3/§5 | 以下记录一致：`release_decision.md` 状态行与 §3/§5，`stage5_audit_table.md` 处理节与补充节，BOARD 14:33 条目。<br>签字栏空着，属于用户。<br>不一致之处：BOARD 任务表中 U-5 仍是 TODO、CL-3 仍是 DOING；`stage5_audit_table.md` 主表各行仍写「待审计」，ResNet18 行仍写「待用户决定」（N-3） | PASS（附 N-3） |
| S5-h 报告措辞与决策一致 | §5 给出 A 段落 | DOCX 副本 sha `ea1778c1…`，mtime 10-29，未改动；6.2.3 仍写 undecided，§5 的引文与原句逐字一致。§5 中 A 的段落与 §3 的理由一致，并保留了「RN 是 validation 选出的候选」。<br>DOCX 由用户修改，不阻断。<br>Table 23 的修改说明不够精确（N-1） | PASS（记录侧，附 N-1） |

### 上一轮审计发现 O-1..O-9

| 发现 | 我的核查 | 状态 |
|---|---|---|
| O-1 R-1 原措辞（复算 10-29 历史六次）做不到 | 替代方案（10-30 重测并保存原始时序）由 B1 独立复算，6/6 一致。用户接受替代关闭（FUD-1）记录在 `stage3_audit_table.md` §7（`f5fb90f`），按实现方记录 | ACCEPTED-BY-USER |
| O-2 两个选项呈现不对称 | 见 S5-d：漏报一侧与合计已补上，数字核对一致（B7/B8），告诫对两边同样适用 | CLOSED（剩余措辞见 N-5） |
| O-3 `.env` 写错了文件 | B9 探测证实修订后的说法正确 | CLOSED |
| O-4 措辞不精确 | 逐项核对：<br>• 5,170 帧：README 第 20 行<br>• Stage 1 行：与 stable200 JSON 一致<br>• Stage 3 行：注明服务端分段只有汇总<br>• HPO MN 0.8731/0.8677：与 JSON 和 Table 16 一致<br>• §1 与 §5 列出的需改章节一致<br>• 「概率更可信」已改为「按 log loss 概率估计更好」 | CLOSED |
| O-5 证据归档缺口 | 已补归档：GREEN 日志（06:32:15Z，`637a0ff` + 工作区）、RED 日志（06:32:24Z）、`recompute_raw.py` + `recompute.log`（exit 0）；我的 B2/B3/B1 复现了这些结果。<br>残余：10-30 perf01 的服务器日志无法恢复，已在 README 说明。FUD-7 的记录方式是「用户未提出异议」 | CLOSED（残余为默示接受） |
| O-6 提交落在 `fyp2/dmd-adaptation` | 按用户 FUD-4 处理：<br>• `fyp2/live-system` 的 reflog 显示 14:31 +0800「Reset to 637a0ff」<br>• `merge-base --is-ancestor e26e32a 637a0ff` exit 0，等价于快进，没有丢失提交<br>• 快进带来的 9 个提交（`f28b10a..637a0ff`）都是本会话的，没有 DMD 提交<br>• `dmd-adaptation` 仍在 `637a0ff`；之后的提交都在 INTEG 的 `fyp2/live-system` 上 | CLOSED（按用户 FUD-4 执行） |
| O-7 测试数据恒定，断言偏弱 | M1 恒定时长变异：新测试 exit 1，旧测试 exit 0；M2 保留预热：exit 1 | CLOSED |
| O-8 `drill.py` 文档说明不准确 | 演练 README 已加更正说明；`git diff 637a0ff f5fb90f -- drill.py` 为空，脚本保持原样 | CLOSED |
| O-9 Stage 5 在 Stage 3 VERIFIED_PASS 之前开始 | 用户确认（FUD-5）记录在 `stage3_audit_table.md` §7 与 `stage5_audit_table.md`；BOARD 13:36 写的是「用户要求开始 Stage 5」 | ACCEPTED-BY-USER |

## 2. Red-line checklist

- **PASS — 没有训练、HPO、导出或 benchmark。** 范围内的非文档改动只有 `scripts/perf01.py` 和 `backend/tests/test_perf_scripts.py`，`ml/` 没有改动。10-30 perf01 是 Stage 3 计划内的测量套件重跑，走的是 FUD-1 的路径。我的重跑只做推理。
- **PASS — RF/LR 运行时从不加载。** `git grep` 在 `f5fb90f` 的 `backend/app` 和 perf 脚本中搜索 RandomForest、LogisticRegression、joblib、sklearn、RF-/LR-HPO，没有任何命中。
- **PASS — XGB 加载路径与行为不变。** `git diff 2745348 f5fb90f -- backend/app/providers/trained.py` 只有 vision 侧的改动；唯一含「XGBoost」的改动行是候选 provider 的名称字符串。`trained.py` 自 Stage 1 审计过的 `00b0e5d` 起没有变化（exit 0）。演练两次启动的遥测都是 `9802cb06…`。
- **PASS — 没有替换 SQLite。** `database_url` 默认值是 sqlite；范围内 `backend/app ai frontend ml` 没有 diff；演练使用临时 SQLite。
- **PASS — 没有 silent fallback。** 应用代码没有改动。演练中 provenance 写的是实际加载的模型，provider 名称随模型不同。
- **PASS — fusion/EMA/FSM 与概率解释不变。** 快进范围 `e26e32a..637a0ff` 中 `ai/` 和 `backend/app` 都没有 diff。
- **PASS — 没有覆盖模型。** 94 个文件的 sha+mtime 前后一致。冻结 sha 全部吻合：`b3a42e8d`、`5e226722`、`9ee60abb`、`9802cb06`；`evaluation_metrics.json` 为 `4f1c517a…`。
- **PASS — 没有提交模型产物。** `git ls-tree -r f5fb90f` 中没有 .onnx/.pt/.pkl、`xgb_telemetry.json`、`ml/outputs/candidates` 或 `demo/bundles`。
- **PASS — 没有 push。** `origin/fyp2/live-system` 仍在 `b58fcc6`，最后一次「update by push」是 2026-10-22。包含 `1cd5660` 的只有本地分支 `refs/heads/fyp2/dmd-adaptation` 和 `fyp2/live-system`。我只查了本地远端跟踪引用，没有查询远端服务器。
- **PASS — 只用同日证据。** 10-30 的证据都是 10-30 生成：perf01 05:38–05:44Z，演练 05:45Z，补归档日志 06:32Z，全新克隆门禁 06:33Z。引用的旧证据都标了日期。我的命令在 10-30 06:47–07:00Z 运行。
- **PASS — 默认模型仍是 stable，与 U-5 = A 一致。** `backend/app/config.py` 中 `active_vision="stable"`。
- **PASS — 没碰 8000 端口和真实 DB，保留无关状态。** 演练用 8001 和临时库；三个工作树的状态前后一致。
- **PASS — 提交位于 `fyp2/live-system`。** 这是 FUD-4 之后的状态。

## 3. Scope-creep findings

1. **范围内提交没有代码扩张。** `f15f539` 只加强了测试（O-7）并修订文档。`a46f80d` 和 `f5fb90f` 只有证据和文档。
2. **快进带来了非 Task 10A 的前端改动。** `e26e32a..637a0ff` 有 21 个非文档文件属于 UI 修正（`ead8895`、`37e7229`、`9255c83`，例如 AlertBanner、LiveMonitor、dataMode），不属于 Stage 3/5。它们不触及 `ai/` 和 `backend/app`；各自有全新克隆门禁，`f15f539` 的门禁也覆盖了它们。本次阶段门没有审计这些改动（FUD-8 按默认处理），这里只作标记。
3. **决策记录带有推荐（A）。** 计划 §14 允许给出发布建议，不算越权。

## 4. FOR_USER_DECISION items

- **FUD-R2-1（Table 23 其余行）：** §5 写的是「日志完整性……沿用各自的证据（10-29 perf02：210/210）」，但 DOCX 中的 Table 23 现在用的是 10-22 的「D1/D2 211/211」和「Persisted 210 + 1 fault」。10-29 对应的数字是 210/210 和入库 209 + 1。请用户决定这两行保留 10-22 还是改为 10-29，并决定 Server total 一行是否同时写入 10-30 的 p95（19.65/19.83/19.83 ms）。之后让实现方据此澄清 §5。
- **FUD-R2-2（演示与回滚在哪里运行）：** FUD-4 之后，`fyp2/live-system` 所在的 INTEG 没有模型文件，也没有 `.venv`。有模型的 LIVE 现在是另一会话的 dmd 工作树。需要用户决定演示后端从哪个工作区运行，例如把模型只读链接进 INTEG（我的重跑就是这样做的），以及 §4 是否要写明根目录。
- **FUD-R2-3：** FUD-3、FUD-7、FUD-8 记录为「用户未提出异议」，属于默示接受。是否需要明示确认，以及是否要求对上述 UI 提交另做阶段门审计，由用户决定。
- **FUD-R2-4：** `release_decision.md` §3 的书面签字，以及 DOCX 6.2.3 末两句和 Table 23 的修改，都由用户完成。
- **FUD-R2-5：** 签字前是否要求实现方先修 N-3、N-4、N-5 这几处文书问题。

## 5. Final verdicts

**Stage 3：VERIFIED_PASS**
- 我独立复算了 6/6 的 sha 绑定与分位数（B1 exit 0），三段之和残差为 0。
- 测试 RED（exit 1）到 GREEN（exit 0，29 passed）复现成功；加强后的测试能抓到恒定时长变异（exit 1），而旧测试抓不到（exit 0）。
- f15f539 全新克隆门禁五项都是 exit 0；我在 `f5fb90f` 上非 e2e 回归 1310 passed（exit 0）。健康与日志完整性 PASS，没有违反红线。
- 前提：O-1 以用户接受 FUD-1 关闭，这一点**只依据实现方的记录**，我看不到对话。

**Stage 5（Steps 1–3 加上已记录的决定）：VERIFIED_PASS**
- Step 1：回滚演练我从 `f5fb90f` 克隆重跑，exit 0，11/11，结果与原始演练逐位相同，模型树不变。
- Step 2：决策记录字段齐全，所有数字都与来源一致（包括 90/3226、63/3226、129/150），证据路径都能打开，两个选项已呈现公平，O-2/O-3/O-4 已关闭。
- Step 3：没有自动启用 ResNet18；默认值 stable 与已记录的 U-5 = A 一致。
- 签字和 DOCX 修改属于用户，不阻断。

**Open findings（均不阻断）：**
- N-1：§5 的 Table 23 说明不够精确：日志完整性来源（10-22 211/211 还是 10-29 210/210）、Persisted 行和 Server total p95 都没有写清楚（见 FUD-R2-1）。
- N-2：§4 的启动命令和三个模型路径依赖仓库根目录下有 `.venv` 和 `ml/outputs`。现在 `fyp2/live-system` 的工作树 INTEG 两者都没有，只有 LIVE 有（见 FUD-R2-2）。
- N-3：记录不同步：
  - BOARD 任务表中 U-5 仍是 TODO、CL-3 仍是 DOING，也没有记录 FUD-1/FUD-5 答复的条目；
  - `stage5_audit_table.md` 主表各行仍写「待审计」「待用户决定」。
- N-4：§2 引用 `stage1_audit_table.md` 时注明「Codex VERIFIED_PASS」，但该文件本身没有这一判定；判定在 git 忽略的 `LIVE/.superpowers/collab/codex/stage1_audit.md` 第 290 行。
- N-5：措辞小问题：
  - 「ResNet18 少漏几个分心帧」实际是 27 帧（90 到 63），说少了；
  - A 的优点里写「报告……不必改写」，但按 §5，选 A 仍要改 6.2.3 末两句和 Table 23；
  - 「服务端视觉中位数约 9.6 ms」实际三轮为 9.58–9.79 ms。
- O-5 残余：10-30 perf01 的服务器日志不可恢复，已说明，属于默示接受。

本审计没有进入下一阶段，没有修改计划，也没有选择或更改模型。

**本人证据（SP2）：**
- `b1_recompute.py` / `b1_recompute.out`（B1）
- `b2_focused_f5fb90f.log`（B2）
- `b3_RED_e07ef42.log`、`b3_mut_M1_newtest.log`、`b3_mut_M1_oldtest.log`、`b3_mut_M2_newtest.log`（B3/M1/M2）
- `b5_drill_stdout.log`、`drill_out/`（B5）
- `b4_treehash.py`、`b4_models_before.txt`、`b4_models_after.txt`、`b4_models_after_pytest.txt`
- `b6_pytest_non_e2e_f5fb90f.log`（B6）
- `envprobe/`（B9）
- `FYP2.r2copy.docx`、`docx/`
- `*_status_before.txt` / `*_status_after.txt`