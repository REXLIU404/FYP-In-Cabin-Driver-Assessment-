# Task 10A 阶段门审计：Stage 3（R-1 关闭）与 Stage 5（Steps 1–3）

审计人：独立只读审计子代理。日期：2026-10-30。我的命令在 05:50Z 到 06:04Z 之间运行。
审计对象：`/Users/liu/Desktop/FYP2-Live-System` 的 `637a0ff`（父提交 `1cd5660`，再往上是 `e07ef42`）。
缩写：`LIVE=/Users/liu/Desktop/FYP2-Live-System`；`ML=/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1`；`SP=/private/tmp/claude-501/-Users-liu-Desktop-FYP-In-Cabin-Driver-Assessment--1--claude-worktrees-exciting-keller-fdf913/e713c74d-2981-4f3f-bccb-7aa94bfb77b4/scratchpad`（我的全部输出都在这里）。

只读声明：
- 两个工作树都没有被编辑、暂存、提交或清理。
- 测试都在全新克隆 `SP/clone637`、`SP/cloneRED` 中运行（检出 `637a0ff`）。用原 `.venv` 只读运行，加 `-B`/`PYTHONDONTWRITEBYTECODE=1`。stable 模型以只读符号链接接入。
- 回滚演练按任务规定，从 LIVE 根目录运行，输出到 `SP/drill_rerun`。运行前确认 8001 端口空闲，使用临时库。我没有访问 8000 端口，也没有访问任何 `driver_risk.db*`。
- LIVE 的 `git status --porcelain --untracked-files=all` 运行前后逐字相同。另一会话的未提交文件原样保留。
- ML 工作树没有已跟踪或已暂存的 diff。
- DOCX 先复制到 SP 再读取。原件 sha256 `ea1778c1…` 不变。

## 1. Verdict table

| 审计点 | 实现方声明 | 本人核查（打开的文件 / 我重跑的命令及 exit code） | 结果 |
|---|---|---|---|
| S3-a 延迟 JSON 当日生成，MN 与 RN 都有 | 10-30 stable/RN 交替各 3 轮，每轮 600 窗口 | 逐一打开 `LIVE/docs/evidence/2026-10-30/stage3-raw/*/perf01.json`。**A1** `python3 -I -B SP/recompute_perf01.py LIVE` **exit 0**：<br>• 6/6 的 `generated_utc` 是 2026-10-30<br>• 每轮 600 测量窗口 + 20 预热，`short_run=false`<br>• `vision_model` 由 `/api/models` 报告：stable `b3a42e8d…`，RN `5e226722…`<br>• 工作树文件与 `637a0ff` 中的 blob 一致<br>• 时间线：最早 capture 05:37:25Z，晚于 `1cd5660` 的提交时间 05:37:06Z；与 `runs.log` 的起止时间吻合 | PASS |
| S3-b RN 场景下 p95 是实测值 | RN p95 45/44/43 ms | A1：RN 的 p95 从原始窗口复算，得到 45/44/43 ms。代码路径是每窗口 `renderedAtMs-capturedAtMs`，没有外推 | PASS |
| S3-c（R-1）10-30 六轮的分位数可由原始样本复算，sha256 绑定 | 六份 `perf01_timings.json` 的 sha 都等于 `raw_timings.sha256`，复算与汇总完全相同 | A1 用我独立实现的分位规则（不导入仓库代码），6/6 sha 绑定一致。`capture_to_render_ms` 的 n/min/median/p95/max 完全相等：<br>• stable 27/31/127、28/31/63、28/31/58<br>• RN 42/45/125、41/44/63、41/43/75<br>`capture_to_send`、network、render 三段与 `achieved_rate_hz` 也完全相等。<br>线性插值 p95 作参考：31/45/31/44/31/43.05。<br>**A1b** 内部一致性：每行 c2r = 三段之和，残差 0；采集间隔 ≥100 ms，单调递增。<br>注：`server_timing_ms`（服务端视觉中位数 9.6/26.6 ms）只有汇总值，原始文件不含这一字段，无法复算 | PASS |
| S3-c'（R-1 原文）10-29 历史六次 p50/p95 从原始样本复算 | 10-29 文件保留为历史，只有汇总；Stage 5 改引 10-30 | 10-29 文件仍然没有逐窗口时序，原措辞要求的复算依然无法完成。实现方的做法是用 10-30 新测量**替代**历史复算，没有复算历史六次。替代能否算作关闭，交用户裁定（FUD-1） | BLOCKED（原措辞） |
| S3-d perf01 原始时序测试先红后绿 | `test_perf01_writes_the_measured_windows_raw_timings…` RED→GREEN；29 passed | **A2** 在克隆 `637a0ff` 中运行 `pytest tests/test_perf_scripts.py`：**exit 0，29 passed**。<br>**A3** 把同一测试放到改动前的 `e07ef42:scripts/perf01.py` 上：**exit 1**（`KeyError: 'raw_timings'`），RED 成立。<br>缺口：实现方的 RED/GREEN 与 29 passed 都没有归档日志（O-5）。<br>该测试的合成数据恒为 30 ms，分位数断言偏弱；窗口 ID 21..620 的断言仍然锁定了被测窗口集合（O-7） | PASS |
| S3-e 全量测试当日重跑 | 9255c83 全新克隆门禁 pytest 1359/0 skipped/8 deselected，vitest 1061；`1cd5660` 只改了 perf01 | 打开 `LIVE/docs/evidence/2026-10-30/review-followups-coldstart-9255c83/` 的 SUMMARY 与 02/03 日志：生成于 2026-10-30T04:41Z，五个门禁都是 exit 0。<br>`git diff --stat 9255c83 637a0ff`（不含 docs）只有 `scripts/perf01.py` 和 `backend/tests/test_perf_scripts.py`；全仓只有 `test_perf_scripts.py` 引用 perf01。<br>**A4** 在克隆 `637a0ff` 中运行 `pytest tests -m 'not e2e'`：**exit 0，1310 passed，58 deselected**。<br>e2e 的 58 项和前端门禁没有在 `637a0ff` 上重跑；前端与 e2e 相关代码自 9255c83 以来无变化 | PASS |
| S3-f 健康 | 0 控制台错误，全部 exit 0 | A1：6/6 `console_errors=[]`，`attempts_other_than_1=0`；`runs.log` 中 6/6 exit 0。<br>10-30 的 perf01 服务器日志写在临时目录，没有归档（O-5）。<br>10-29 的 10 份服务器日志为 0 字节，已由 CX-A3 核过。<br>A5 演练的两份 uvicorn 日志中 error/traceback 为 0 行 | PASS |
| S3-g 日志完整性（RN） | 10-29 perf02 210/210 | 打开 `LIVE/docs/evidence/2026-10-29/perf-stage3/{stable,rn}/perf02.json`：D1/D2 都是 210/210，completeness 1.0。CX-A3 曾独立重跑得到 211/211。10-30 没有重跑这一项，R-1 也不要求 | PASS |
| S3-h 负载与对比方式 | 安静机器，load 2.3–4.1，交替运行 | `runs.log` 中 1 分钟 load 为 2.30–4.06，stable/RN 交替。这只是描述性记录，没有进程归因 | PASS |
| S5-a 回滚可执行且被验证（演练日志 exit 0） | 11/11 PASS，exit 0；94 个文件哈希不变 | 读了 `drill.py`、README、`drill.log`、`drill.json` 和两份 uvicorn 日志，原始演练时间为 2026-10-30T05:45Z，HEAD `1cd5660`。<br>**A5** 本人重跑 `drill.py SP/drill_rerun`：**exit 0，RESULT PASS（11/11）**，HEAD `637a0ff`，端口 8001，每次启动用新的临时 SQLite，并剥离 `DRA_*`。<br>• 候选在役：`VisionCandidateONNX+XGBoost`，`5e226722…`<br>• 新进程不设变量：`MobileNetV3ONNX+XGBoost`，`b3a42e8d…`<br>• 遥测两次都是 `9802cb06…`<br>• `/infer` 都返回 201，RiskScore 与 P_distraction 和原始演练逐位相同（85.0/0.710053，99.5/0.9999986）<br>• `ml/outputs` 下 94 个文件前后一致；结束时 8001 空闲 | PASS |
| S5-b 决策记录引用 Stage 2/3 证据，路径可打开 | §2 每个路径都可打开 | 逐个检查 §2/§4 引用的 12 个路径，全部存在。<br>Stage 2 用 10-29 的 `comparison-official-bf76ddf`，三个模型同日运行。<br>Stage 3 用 10-30 的 `stage3-raw`；日志完整性用 10-29 perf02。日期都标注清楚 | PASS |
| S5-c 决策记录数字与来源一致 | 见 release_decision §1/§2 | **A6** 从 `ML/ml/outputs/runs/p4b_20261022/evaluation_metrics.json` 的混淆矩阵复算（行 = 真类，c0 support 431，n=3657）：<br>• stable：Acc 0.8988、Macro-F1 0.8746、log loss 0.574、c0 召回 0.9211、c9 召回 0.2733<br>• RN：0.9016、0.8892、0.451、0.8329、0.4920<br>• `distraction_diagnostic`：stable 0.9647 / 0.0905（=39/431）；RN 0.9590 / 0.2019（=87/431）<br>**A7** 用 RN 的 `predictions_test_clean.csv` 逐行复算：87/431、二分类准确率 0.95898、c9 召回 0.4920，与 JSON 一致。<br>**A8** 从 `comparison_results.json`（sha `6db717f1…`）的 200 个窗口复算：RN 与 stable 的 argmax 一致率 0.91，RiskLevel 不同 5，AlertSeverity 不同 12。<br>**A9** `runtime_benchmark` 原始样本：MN-HPO42 p95 7.2472 ms，RN 25.4214 ms。<br>E1：brightness_down:2 为 RN 10.45% / stable 3.80%；motion_blur:2 为 48.32% / 56.99%。<br>模型大小 16.07 / 42.65 MiB。<br>DOCX 6.2.3 原句与 §5 的引文一致。<br>以上全部相符；措辞上的小问题见 O-4 | PASS |
| S5-d 两个选项是否公平，是否夸大 | 推荐 A，并列出 A/B 两方的优缺点 | 优点：<br>• 两个选项都有优点、代价，以及「两者都没有证明的」：正面摄像头准确率、目标硬件、融合后的风险准确率<br>• 没有把 Macro-F1 等同于更安全；签字栏空着<br>问题：<br>• **遗漏对 B 有利的对称证据。** 理由 1 以「安全/分心」二分类为最贴近风险的口径，但只列出误报一侧（9.0% 对 20.2%），没有列出漏报一侧。同一 0.5 阈值下，分心帧被判为安全的比例是 stable 90/3226 = **2.79%**、RN 63/3226 = **1.95%**。RN 的 63 来自逐行复算；stable 的 90 由 Acc 与 FP proxy 推得：129 个错误减 39 个误报<br>• **小样本告诫只用在 B 的优势上。**「测试集只有 4 名驾驶员」只用来淡化 B 的增益，没有用在 A 所依赖的 c0 召回差上<br>• 「产生误报」「概率更可信」是推断性表述，有离线诊断的免责说明，但仍偏强（O-2/O-4） | FAIL（需修订） |
| S5-e 版本化配置与回滚步骤，不覆盖稳定产物 | §4 只有一个开关 `DRA_ACTIVE_VISION`；稳定产物不变 | 用 `git show 637a0ff:backend/app/config.py` 确认 `active_vision: str = "stable"`。模型 sha 当场复算：stable ONNX、XGB 和两个候选都等于冻结值。<br>**A11** 探测：`Settings` 读取的是**相对 cwd** 的 `.env`。按文档里的启动命令（在仓库根目录、带 `--app-dir backend`）读的是 `<repo>/.env`，不是 §4 写的 `backend/.env`；两个文件目前都不存在（O-3） | PASS（附 O-3） |
| S5-f 不自动启用 ResNet18 | 默认 stable；状态「待用户决定」 | config 默认值是 stable；A5 中不设变量启动得到 stable；`release_decision.md` 状态为「待用户决定（U-5）」，签字栏空着 | PASS |
| S5-g 报告措辞与决策一致 | 用户决定后再核对 | 要等 U-5 决定后才能核对。DOCX 未改动（sha `ea1778c1…` 与 CX-A3 记录的一致），6.2.3 仍写着 undecided | BLOCKED（依赖 U-5） |

## 2. Red-line checklist

- **PASS — 没有训练、HPO、导出或模型 benchmark。** 本阶段只改了 `scripts/perf01.py` 和它的测试，其余都是文档和证据。10-30 的运行属于计划内已有的系统 perf01 套件；演练只做推理。ML 的 runtime_benchmark 我只复算了原始样本，没有重跑。
- **PASS — RF/LR 运行时从不加载。** `backend/app` 和 perf01 中没有 RF/LR/joblib 引用；provider 只加载 ONNX 和 `xgb.Booster`。
- **PASS — XGB 加载路径与行为不变。** `git diff 2745348 637a0ff -- backend/app/providers/trained.py` 的改动都在 vision 侧，遥测块与 XGB 相关行没有变；本阶段没有改这个文件。两次演练启动的遥测都是 `9802cb06…`。
- **PASS — 没有替换 SQLite。** `git diff e07ef42 637a0ff -- backend/app ai frontend` exit 0（无差异）。演练使用临时 SQLite。
- **PASS — 没有 silent fallback。** 失败路径未改动。演练中 provenance 的 `vision_model_id`/sha 是实际加载的模型，候选在役时 provider 名为 `VisionCandidateONNX+XGBoost`。
- **PASS — fusion/EMA/FSM 与概率解释不变。** 本阶段没有改应用代码。演练 provenance 中 `fusion_config` 为 0.5/0.5、0.35、3.0、30/60。
- **PASS — 没有覆盖模型。** 我复算的 sha 全部等于冻结值；演练前后 94 个文件一致（原始和我的重跑都是）。`evaluation_metrics.json` 的 mtime 仍是 10-22，sha `4f1c517a…` 与 `ML/docs/evidence/2026-10-26/ml-push/git-archive-included.json` 的记录一致。
- **PASS — 没有提交模型产物。** `git ls-files ml/outputs/candidates demo/bundles` 为空；两个提交只包含 docs、scripts 和 tests。
- **PASS — 没有 push。** 没有任何远端跟踪分支包含 `1cd5660`；`fyp2/dmd-adaptation` 没有 upstream；`origin/fyp2/live-system` 的最后一次 push 是 10-22。
- **PASS（附注）— 只用同日证据。** 10-30 的证据日期、mtime 和日志时间戳都是 2026-10-30；引用的 10-29、10-26、10-22 证据都标了日期，没有冒充重跑。附注：实现方「29 passed」、RED 和自查复算都没有归档日志（O-5），已由我的 A1–A3 补证。
- **PASS — 用户裁定前没有切换默认模型。** `backend/app/config.py` 中 `active_vision` 的默认值仍是 `"stable"`。
- **PASS — 保留无关状态，没碰 8000 端口和真实 DB。** 工作区状态前后一致；演练剥离 `DRA_*`，使用临时库和 8001 端口。
- **PASS（附注）— 任务范围内的提交。** 但提交位于 `fyp2/dmd-adaptation`，不在 `fyp2/live-system` 上。reflog 显示 2026-10-29 19:29:23 从 live-system 切到 dmd-adaptation，BOARD 上没有记录；`fyp2/live-system` 仍停在 `e26e32a`。用户清单接受「live-system 或其新分支」，但计划 §1 第 6 条和 D1 写的是 live-system。是否接受交用户（FUD-4）。

## 3. Scope-creep findings

1. **没有代码层面的范围扩张。** `1cd5660` 是针对 R-1 的增量修复，只改两个文件，符合 §15 的「新提交修复审计发现」。`637a0ff` 只有证据、自审表和决策记录。`drill.py` 放在证据目录里，仅作为证据脚本。
2. **门禁顺序偏离。** §15 规定前一阶段 VERIFIED_PASS 之后才能开始下一阶段，但 Stage 5 的 Steps 1–3 在 Stage 3 复审之前就做了。BOARD 2026-10-30 13:36 的条目由实现方自写，称「用户要求开始 Stage 5」，我无法核实（FUD-5）。
3. **提交落在另一工作流的分支上。** 分支名 `fyp2/dmd-adaptation` 对应另一会话的 DMD 工作（工作区里有其未提交的计划和规格文件），Task 10A 的提交与它混在一起，可追溯性下降（FUD-4）。
4. **决策记录带有推荐（A）。** 计划 §14 允许给出发布建议，不算越权；但见 S5-d 的公平性问题。§5 的报告措辞只是草稿，DOCX 没有改动。

## 4. FOR_USER_DECISION items

- **FUD-1（R-1 如何关闭）：** 原措辞是「历史六次分位数从原始样本复算」，这一点仍然做不到。实现方改为 10-30 重新测量六次，并保存可复算的原始时序；我已独立复算，结果完全一致。是否接受这种替代关闭，由用户裁定。CX-A3 的 FUD-S3-2 把这条路径附了「另行授权」的条件，这次授权有没有给出，我无法核实。
- **FUD-2（FUD-S3-1，Table 23）：** 三种选择：保留 10-22 的 stable 数字、换成 10-30 的 stable 数字（p95 31 ms），或在选 B 时换成 10-30 的 RN 数字（p95 43–45 ms），并注明开发机和 fake camera。
- **FUD-3（FUD-S3-3）：** 10-29 已删除的作废并发运行没有可审阅的记录，是否接受实现方的说明。这不影响 10-30 的数字。
- **FUD-4（分支归属）：** 是否接受 `1cd5660`/`637a0ff`（以及 `f28b10a..e07ef42`）位于 `fyp2/dmd-adaptation`，以及要不要让 `fyp2/live-system` 跟进。我不做这个决定。
- **FUD-5（门禁顺序）：** 请确认是否确实授权在 Stage 3 VERIFIED_PASS 之前开始 Stage 5。
- **FUD-6（U-5，模型选择）：** 由用户在 A 与 B 之间裁定。建议签字前先让实现方按 O-2、O-3、O-4 修订 `release_decision.md`（补上漏报一侧的证据，对两个选项对称地给出小样本告诫）；是否要求修订，也由用户决定。
- **FUD-7：** 是否要求补归档 `1cd5660` 的 RED/GREEN 日志和 10-30 perf01 的服务器日志，还是接受本审计的重跑（A1–A4）作为补证。
- **FUD-8（FUD-S3-4）：** 后续 UI 提交另有全新克隆门禁（9255c83），不在本次审计范围内，是否另行审查由用户决定。

## 5. Final verdicts

**Stage 3：PARTIAL**
- 技术核查全部通过：10-30 六轮 perf01 的 sha256 绑定和分位数复算 6/6 完全一致，原始数据内部一致；perf01 测试 RED（exit 1）到 GREEN（exit 0，29 passed）已复现；9255c83 同日全量门禁日志已打开，我在 `637a0ff` 上非 e2e 回归 1310 passed（exit 0）；健康与日志完整性 PASS；红线没有违规。
- 只因两件事不能给 VERIFIED_PASS：
  1. R-1 原措辞（历史六次复算）仍是 BLOCKED，以 10-30 新测量替代需要用户接受（FUD-1）；
  2. 证据归档有缺口（O-5）。
- 如果用户接受替代关闭，我没有发现其他阻断性技术缺陷。

**Stage 5（Steps 1–3；决定本身属于用户）：PARTIAL**
- Step 1 回滚演练：我重跑 exit 0，11/11，PASS。
- Step 3 没有自动启用 ResNet18：PASS。
- Step 2 决策记录：字段齐全，所有路径都能打开，所有数字都与来源一致；但两个选项的呈现不够对称（S5-d FAIL：遗漏分心漏判率 2.79% 对 1.95%，小样本告诫只施于 B），另有 `.env` 说明不准确（O-3）和若干措辞不精确（O-4），需要修订后再交用户签字。
- 「报告措辞一致」要等 U-5 决定（BLOCKED）。

**Open findings：**
- O-1：R-1 原措辞仍未满足，替代关闭待用户接受。
- O-2：`release_decision.md` 对两个选项的呈现不对称（漏报率、小样本告诫）。
- O-3：§4 的 `.env` 限制写错了文件。`Settings` 读相对 cwd 的 `.env`，按文档命令应是仓库根目录的 `.env`。
- O-4：措辞不精确。
  - 「约 5,170 帧几乎全判 c8/c9」：实际 c8+c9 为 4701/5174 ≈ 90.9%，另有 c7 约 4.5%。
  - Stage 1 行对 stable 的描述：|Δp| 实际来自 parity100（100 个样本），stable200 用的是 per-class mode 规则（`NO_STABLE200_REFERENCE`）。
  - 「原始时序可复算」一行里的服务端视觉中位数只有汇总值。
  - 「HPO MN 不如 stable（下表）」：表中没有这组数据。
  - §1 与 §5 列出的需改章节不一致；「概率更可信」偏强。
- O-5：证据归档缺口：`1cd5660` 的 29 passed/RED 没有日志；实现方的复算没有日志；10-30 perf01 没有服务器日志。
- O-6：提交在 `fyp2/dmd-adaptation` 上，不在 `fyp2/live-system` 上。
- O-7：新测试用恒定 30 ms 的计时数据，分位数断言偏弱。
- O-8：`drill.py` 文档说 provider 会因 hash 不符而拒绝加载，对 stable 路径不准确：provider 只计算 stable 的 sha，比对冻结值的是演练脚本本身。
- O-9：Stage 5 在 Stage 3 VERIFIED_PASS 之前开始。

本审计没有进入下一阶段，没有修改计划，也没有选择模型。

**本人证据（SP）：**
- `recompute_perf01.py`、`recompute_perf01.out`（A1）
- `focused_637.log`（A2）、`focused_RED.log`（A3）、`pytest_non_e2e_637.log`（A4）
- `drill_rerun/`（A5）
- `clone637/`、`cloneRED/`、`envprobe/`（A11）、`FYP2.copy.docx`