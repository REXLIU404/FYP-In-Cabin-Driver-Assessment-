# FYP2 Independent Audit Review

审查日期：2026-10-13，Asia/Kuala_Lumpur（UTC+8）。角色：independent methodology and software-QA reviewer。范围：verification and criticism；不实施修复，不训练或下载模型。

**结论：首审 00–08 的主要方法学批评成立，但其系统实现状态已经过期，不能直接用来评价最新系统。最新 `fyp2/live-system` 已修复双 missing 和零有效权重造成的虚假低风险；仍不足以签署 Week 7 全系统验收。** 新增的重要发现是：最新总结错误地称 Live 不会出现 stale；DominantEvidence 的“驱动输出”解释可能与加权贡献相反；外部 EDA 的全数据 median 与 train-only 文档不一致。当前模型分支仍缺三个指定 comparator、all-five HPO 和完整 E1/E2/E5 实验产物。

## 1. 版本、授权与证据范围

已阅读提供的 master audit prompt、evaluation/testcase spec、development/report map、cross-review prompt，以及首审 00–08、机器 manifest、原始日志、10-12 浏览器补充报告和最新系统 implementation 文档；从实际源码、测试、notebook、模型与数据指纹核对断言。

| 代号 | 绝对根目录 / 状态 | 用途与比较限制 |
|---|---|---|
| M | `/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1`；`fyp2/ml-training`；HEAD `efb3ea604d584d2c5d1b1684742996e95125a8ec` | 用户明确此分支专供 model 工作。模型与首审文档在这里检查；系统结论不以这里的旧应用实现为准。输出也写在这里。 |
| S | `/Users/liu/Desktop/FYP2-Live-System`；`fyp2/live-system`；HEAD `54e0a60c47320ed48e5687b6180111d123693883`；commit time `2026-10-13T13:11:56+08:00` | 最新系统审查基准。应用与测试对应该 HEAD；唯一既有 dirty 文件为 `docs/plans/2026-10-12-fyp2-live-system-completion.md`，是另一任务的未提交计划。 |
| A | 首审标注 `dev_cc@17c4b41bcfe517c8311b7f6fc2a327f616a916fe` **加未提交内容**；输出 checkout `ae550415237fc1f67bf0de50c643a6d8bd6aca60` | 审计日期 10-10，多数命令实际为 10-09。不能仅凭 commit 比较 dirty 快照；以 source inventory 的 SHA256 为准。 |
| B | 浏览器补充报告的实际运行 `dev_cc@845b43a086e296d96835bf82e4ef8366c636e105` | 10-12 physical-camera 证据；早于 S 的 nullable/temporal 修改，不能替 S 完成当前 E2E。 |
| D | `/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment-` | 原始数据/EDA sibling；本轮仅只读检查 split、特征和生成脚本。 |

本轮按用户补充指令自行读取 S 最新系统，没有 checkout、merge 或把旧系统当最新系统。只读 `git ls-remote --heads origin fyp2/live-system` 核实远端为 `564d0b1c43b3e563390e06606cb02c7e058da3b5`；S 的本地 HEAD 在其后领先 3 commits。默认网络调用曾 DNS 失败，授权的只读网络调用成功。此处“最新”限定为审查时已存在的本地分支，不包含未来提交。

A 的 144 个指纹在 M 上复核：142 相同；仅 `.gitignore` 不同、`AGENTS.md` 已删除；67 个应用/训练/测试源码全部相同。A manifest 的 31 个被哈希产物全部匹配。M 与 S 的 `ml/` diff 为空；这不意味着系统 diff 为空。两个 HEAD 的完整 diff 涉及 125 个文件（包括文档），系统实现已经变化，故旧 28/32 测试日志只能支持 A/M 的历史快照。

遵循用户 AGENTS 指令优先尝试 `fast_context_search`；工具因缺少 Windsurf API Key 失败，改用 `rg`、`nl` 和只读 Python。未读取或修改凭证。两名子审查员分别复核 model 与 S system，均未写文件。

本轮唯一交付文件为本文。未改源码、配置、测试、模型、数据或首审文档；未训练、下载、安装、激活摄像头或迁移真实数据库。pytest fixtures 会创建 SQLite/临时文件（[M/backend/tests/test_api.py:5](/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/backend/tests/test_api.py:5)；[S/backend/tests/conftest.py:30](/Users/liu/Desktop/FYP2-Live-System/backend/tests/conftest.py:30)），因此本次采用不落盘诊断与历史日志追溯，**没有声称独立复跑最新完整 pytest/vitest/build/lint**。

## 2. 独立执行与历史证据追溯

### 2.1 本轮实际执行

以下结果有真实 tool 返回，不是推荐命令或首审转述。Python 使用 M 的 `.venv/bin/python`，`PYTHONDONTWRITEBYTECODE=1`；纯函数加载 S 的 backend，数据库 URL 为 `sqlite:///:memory:`，未初始化数据库。原始 stdout 的关键值与复现代码保存在本文，不另写日志文件。

| Review check | 时间 / 退出码 | 独立结果及边界 |
|---|---|---|
| R-DIAG | stdout UTC `2026-10-13T08:16:25.180851+00:00`；exit 0；30s alarm；tool wall 0.215s | 28 个字面量 oracle 全匹配：6 个 freshness 融合、5 权重、4 风险等级、3 age 边界、10 FSM ticks。另记录 availability、stale-only、weighted explanation、ΔRisk 和 EMA step 反例。只证明指定 core 输入；不是 HTTP/DOM/模型准确率测试。 |
| R-VECTORS | 本轮 2026-10-13；exit 0；tool wall 0.060s；未单独记录精确启动时间 | 用 fixture 输入和独立 Decimal half-up 手算，25 行的 availability、score、level、health 与 expected 一致。未用生产函数生成 expected；dominance 的科学含义另审。跨语言同 fixture 一致本身不证明 risk ground truth。 |
| R-TELEMETRY | stdout UTC `2026-10-13T08:18:33.698731+00:00`；exit 0；30s alarm | 固定 checkpoint、全部 4,500 test rows、best_iteration=90；独立 NumPy confusion/F1：accuracy=.9993333333333333，macro-F1=.999333184740477；confusion `[[1500,0,0],[0,1500,0],[1,2,1497]]`。合成源数据分类结果；不是真实车辆或系统 test。 |
| R-SPLITS | `2026-10-13T08:18:12.563497+00:00` 至 `08:18:12.756823+00:00`；exit 0 | seed42 重构 telemetry 21000/4500/4500 所有特征/标签逐元素相等；vision 15899/2868/3657、18/4/4 drivers 的 partitions 全相等。原始 8 features 的 missing cells=0；global 与 train medians 8/8 不同。 |
| R-TSC | `2026-10-13T08:25:01.347200+00:00` 至 `08:25:03.148096+00:00`；exit 0；stdout/stderr 空 | 从 M 的共享 node_modules 执行 `./node_modules/.bin/tsc --noEmit --incremental false --project /Users/liu/Desktop/FYP2-Live-System/tsconfig.json`。确认 S typecheck；不是 clean install、build 或 browser rendering。 |
| R-BROWSER-ARCHIVE | 本轮只读 JSON/CSV/trace 比对；无新摄像头运行 | 下载原 JSON/CSV 各 811 条，所有导出字段逐条一致、811 融合公式匹配；645 camera 记录中 642 c8、3 reaching_behind；585 FULL、226 DEGRADED；Window753 flagged=true。诊断 trace 有 394 个 unique hashes、394 HTTP201、argmax 均 c8。存档 DB 等价本轮未重新查询（存在 WAL），仍保留为 B 报告的既有验证，不能写成此次独立 DB 实测。 |

环境：Python3.13.3、pandas3.0.3、scikit-learn1.9.0、XGBoost3.2.0、macOS26.6.2 arm64；参数/公式诊断不作为设备性能测量。没有本轮 full vision re-evaluation。

### 2.2 对每类 TEST_PASSED / VERIFIED 的追溯

A manifest 中的 60 个既有 test cases 均与 test symbols、源码和日志核对；按输入与 oracle 家族汇总如下，**CONFIRMED 的是历史执行和限定断言，不是全系统合格**。最新 S 的大批新测试采用重点抽样：nullable contract、25 vectors、temporal boundaries、known limitations、watermark、real-model API 和 UI pure-functions。

| 原 test/status ID | test code / 独立核对范围 | command / actual result / version |
|---|---|---|
| EX-PY-01 | [M/backend/tests/test_api.py:47](/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/backend/tests/test_api.py:47)；prepared .8/.2→50、missing-T .8→80；CRUD/latest/flag/export/delete。手算有效；无真实模型或浏览器 oracle。 | A 的 `python -m pytest backend/tests -vv -p no:cacheprovider --basetemp <fresh-temp>`；[M/docs/fyp2/evidence/PYTEST.log:37](/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/docs/fyp2/evidence/PYTEST.log:37)。 |
| EX-PY-02–13 | [M/backend/tests/test_audit_regressions.py:56](/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/backend/tests/test_audit_regressions.py:56)；12 次实例含输入校验、replay provenance、latest/delete、两线程写入、timestamp、首 High 和 .2→1 EMA。旧 `!=FULL` 断言过弱；EMA 未测总 lag。 | 同 PYTEST；[M/docs/fyp2/evidence/PYTEST.log:38](/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/docs/fyp2/evidence/PYTEST.log:38) 至该组节点输出。 |
| EX-PY-14–24 | [M/backend/tests/test_live_inference.py:42](/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/backend/tests/test_live_inference.py:42)；真实 ONNX/XGB 接线、idempotency、422/503/readiness/restart-state。纯色 JPEG 无动作真值；expected 再调用同 provider，只证明接线。四 ImportError 是 load failure，不是 inference runtime recovery。 | 同 PYTEST；[M/docs/fyp2/evidence/PYTEST.log:50](/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/docs/fyp2/evidence/PYTEST.log:50)。 |
| EX-PY-25–26 | [M/backend/tests/test_live_inference.py:176](/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/backend/tests/test_live_inference.py:176)；硬编码时钟/alpha1 的2s/10s FSM；[M/backend/tests/test_live_inference.py:195](/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/backend/tests/test_live_inference.py:195)，单张随机71×113 PNG 对独立 torchvision transform。 | 同 PYTEST；[M/docs/fyp2/evidence/PYTEST.log:61](/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/docs/fyp2/evidence/PYTEST.log:61)。 |
| EX-PY-27–28 | [M/backend/tests/test_migration.py:7](/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/backend/tests/test_migration.py:7)、[M/backend/tests/test_restart.py:9](/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/backend/tests/test_restart.py:9)；scratch DB migration、真实 Python worker restart。范围明确，不等于断电恢复或真实 DB 已迁移。 | 同 PYTEST；日志最后两个节点及 [M/docs/fyp2/evidence/PYTEST.log:72](/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/docs/fyp2/evidence/PYTEST.log:72)：28 passed、0 skips、exit0；UTC start 10-09 11:45:20.800412。 |
| EX-TS-01–16 | [M/ai/src/riskLogic.test.ts:10](/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/ai/src/riskLogic.test.ts:10)；literal30/60、手算融合/health/evidence helpers。旧 “both missing→0” 是错误验收 oracle；helper raw dominance 不证明 weighted explanation。 | A 的临时 source copy 中 `npm test -- --no-cache`；[M/docs/fyp2/evidence/VITEST.log:34](/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/docs/fyp2/evidence/VITEST.log:34)，16 cases。 |
| EX-TS-17–23 | [M/ai/src/alertFsm.test.ts:10](/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/ai/src/alertFsm.test.ts:10)；7 FSM cases。旧测试引用 production time constants 可共同漂移；“Low5s” 实际仅 Low 的首 tick，不是已持续5秒。 | 同 VITEST；[M/docs/fyp2/evidence/VITEST.log:33](/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/docs/fyp2/evidence/VITEST.log:33)。 |
| EX-TS-24–29 | [M/frontend/src/data/preparedSessionInput.test.ts:25](/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/frontend/src/data/preparedSessionInput.test.ts:25)；6 replay 数据覆盖测试。5 个2s间隔样本首尾只8秒，且该断言不运行 FSM；不是 system test。 | 同 VITEST；[M/docs/fyp2/evidence/VITEST.log:36](/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/docs/fyp2/evidence/VITEST.log:36)。 |
| EX-TS-30–32 | [M/frontend/src/utils/persistence.test.ts:9](/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/frontend/src/utils/persistence.test.ts:9)；3 ID/session helper cases，没有 actual storage roundtrip。 | 同 VITEST；[M/docs/fyp2/evidence/VITEST.log:35](/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/docs/fyp2/evidence/VITEST.log:35)；[M/docs/fyp2/evidence/VITEST.log:39](/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/docs/fyp2/evidence/VITEST.log:39)：32 passed、4 files、exit0；UTC start 10-09 11:45:39.278652。 |
| A DIAGNOSTICS / ML / lint/build | helper source [M/docs/fyp2/evidence/audit_commands.md:93](/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/docs/fyp2/evidence/audit_commands.md:93)、exact commands [M/docs/fyp2/07_EVIDENCE_MANIFEST.md:48](/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/docs/fyp2/07_EVIDENCE_MANIFEST.md:48)、checks.json。模型/数据 hashes 匹配。 | DIAGNOSTICS exit0≠全部正确：23 matches、2 availability failures、1 formula/target distinction。ML full telemetry 本轮再复现；vision20/parity16只 partial。旧 lint 与 runner build exit0，standard build因cache写权限失败；不是 S 的当前 build/lint。 |
| S 506 pytest /394 vitest /tsc0 | [S/docs/fyp2/implementation/task-F2.md:71](/Users/liu/Desktop/FYP2-Live-System/docs/fyp2/implementation/task-F2.md:71) 有命令与嵌入摘要，新测试源码存在；旧 28/32 原始日志不能替新 HEAD 背书。 | 最新 full pytest/vitest **UNRESOLVED（此次独立执行认证）**；没有证据称作者计数虚假。S tsc 本轮确实独立 exit0。 |
| S VERIFIED /约40 mutation checks | [S/docs/fyp2/implementation/TASK_1_TO_6_SUMMARY.md:133](/Users/liu/Desktop/FYP2-Live-System/docs/fyp2/implementation/TASK_1_TO_6_SUMMARY.md:133)；报告还明确承认 surviving mutants、Task6 pure-functions scope 和 UI 未验证。 | 未取得每次 mutation 的独立、不可变 run artifact，亦未复跑；数量/全部效果 **UNRESOLVED**。不能扩张成全系统、真实 camera 或 UAT VERIFIED。 |

完整历史命令、环境、UTC/exit 见 [M/docs/fyp2/evidence/checks.json:1](/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/docs/fyp2/evidence/checks.json:1)。A 已区分 execution pass 与 acceptance validity，不能因存在无效 oracle 就抹掉真实历史通过记录。

## 3. Reviewer matrix

Verdict 严格使用 CONFIRMED / UNSUPPORTED / INCORRECT / UNRESOLVED。CONFIRMED 必须结合“独立证据”列的限定范围；P0=系统验收前优先处理，P1=Week7必要，P2=范围/记录改进。“已修”不再列作当前待修缺陷。

| finding ID | original claim/test ID | first-agent assertion | independent evidence | verdict | exact path:line | scientific impact | correction | priority |
|---|---|---|---|---|---|---|---|---|
| R01 | A EX-PY/TS；07 TEST_PASSED | 历史28+32通过，非E2E | 原命令、节点、退出码、源码和指纹闭环；§2.2全家族追溯 | CONFIRMED | [M/docs/fyp2/02_TEST_CASE_INVENTORY_AND_CRITIQUE.md:10](/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/docs/fyp2/02_TEST_CASE_INVENTORY_AND_CRITIQUE.md:10)；[M/docs/fyp2/evidence/PYTEST.log:72](/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/docs/fyp2/evidence/PYTEST.log:72) | 执行真实性成立；验收范围仍窄 | 保留历史日期/dirty snapshot，不迁移PASS到S | P1 |
| R02 | S Task-F2 gates | 最新506/394通过 | 有作者嵌入输出及新test code，缺此次独立full run；本轮tsc0 | UNRESOLVED | [S/docs/fyp2/implementation/task-F2.md:74](/Users/liu/Desktop/FYP2-Live-System/docs/fyp2/implementation/task-F2.md:74) | 不能认证新HEAD完整门禁，也不能指称结果伪造 | 发布version/env/argv/exit/skips/raw logs；独立重跑时另记录 | P1 |
| R03 | S VERIFIED /mutations | 约40次变异检验 | 有摘要、失败片段和survivor披露；非每次完整版本绑定产物 | UNRESOLVED | [S/docs/fyp2/implementation/TASK_1_TO_6_SUMMARY.md:133](/Users/liu/Desktop/FYP2-Live-System/docs/fyp2/implementation/TASK_1_TO_6_SUMMARY.md:133)；[S/docs/fyp2/implementation/TASK_1_TO_6_SUMMARY.md:142](/Users/liu/Desktop/FYP2-Live-System/docs/fyp2/implementation/TASK_1_TO_6_SUMMARY.md:142) | mutation数量不能作为安全或全系统证明 | 限定assertion scope，保留survivors及raw mutation ledger | P1 |
| R04 | B01/E3-03/EX-TS-08；S Task1–5 | 旧both missing→0/Low/NORMAL；新版本称已修 | R-DIAG四字段null、assessment=false、UNAVAILABLE；新API断言齐全 | CONFIRMED | [S/backend/app/fusion.py:89](/Users/liu/Desktop/FYP2-Live-System/backend/app/fusion.py:89)；[S/backend/app/inference.py:128](/Users/liu/Desktop/FYP2-Live-System/backend/app/inference.py:128)；[S/backend/tests/test_live_inference.py:98](/Users/liu/Desktop/FYP2-Live-System/backend/tests/test_live_inference.py:98) | 旧P0实现状态已过期；M旧实现不代表S | 更新报告，维持API/UI/export全链null回归 | P0已修 |
| R05 | B02/zero effective weights | 新版本按configured denominator判可用 | 双向零权重R-DIAG均null/UNAVAILABLE；共用effective_weights | CONFIRMED | [S/backend/app/fusion.py:58](/Users/liu/Desktop/FYP2-Live-System/backend/app/fusion.py:58)；[S/backend/app/fusion.py:124](/Users/liu/Desktop/FYP2-Live-System/backend/app/fusion.py:124)；[S/backend/tests/test_unavailable_contract.py:189](/Users/liu/Desktop/FYP2-Live-System/backend/tests/test_unavailable_contract.py:189) | no-evidence不再伪造低风险 | 补near-epsilon API mutant防线；不重复列B02未修 | P0已修/P1 |
| R06 | E3-04/05 factor0.45 | stale=.45是factor，非normalized share | (.45×.1+.9)/1.45→65.2；share=.3103448；both stale仍50 | CONFIRMED | [M/docs/fyp2/03_EVALUATION_COVERAGE_MATRIX.md:68](/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/docs/fyp2/03_EVALUATION_COVERAGE_MATRIX.md:68)；[S/backend/app/fusion.py:28](/Users/liu/Desktop/FYP2-Live-System/backend/app/fusion.py:28)；[S/backend/app/fusion.py:91](/Users/liu/Desktop/FYP2-Live-System/backend/app/fusion.py:91) | 两路同stale因子抵消，不能称总风险下降55% | 同时报告factor、effective weights和归一化份额 | P1 |
| R07 | E3 ΔRisk≤.15 | A已拒绝普遍 correctness gate | .1/.9 fresh=.5，Vmissing=.9，Δ=.4；本轮复现 | CONFIRMED | [M/docs/fyp2/03_EVALUATION_COVERAGE_MATRIX.md:74](/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/docs/fyp2/03_EVALUATION_COVERAGE_MATRIX.md:74) | 数学正确与目标未达可同时成立 | 报target attainment比例/分布；保留原目标，不强造PASS | P1 |
| R08 | D13 /Live stale不可达 | S称trained.py fresh/missing所以Live不会stale | 下游按captured_at重判；已有真实模型/infer测试用2000年帧得到stale | INCORRECT | 错：[S/docs/fyp2/implementation/TASK_1_TO_6_SUMMARY.md:186](/Users/liu/Desktop/FYP2-Live-System/docs/fyp2/implementation/TASK_1_TO_6_SUMMARY.md:186)、[S/backend/tests/test_temporal_contract.py:607](/Users/liu/Desktop/FYP2-Live-System/backend/tests/test_temporal_contract.py:607)；反证：[S/backend/app/inference.py:107](/Users/liu/Desktop/FYP2-Live-System/backend/app/inference.py:107)、[S/backend/tests/test_live_inference.py:113](/Users/liu/Desktop/FYP2-Live-System/backend/tests/test_live_inference.py:113) | 错误缩小过期证据问题范围；延迟也可跨3s边界 | 修正文案；用完整pipeline clock/API test替source-string guard | P0 |
| R09 | D13/UT-TIME-06 known limitation | stale永不missing，可持续High | day-old两路.9在0/1/2s为90/DEGRADED，CAUTION→HIGH_ALERT；新test覆盖更老输入 | CONFIRMED | [S/backend/app/inference.py:45](/Users/liu/Desktop/FYP2-Live-System/backend/app/inference.py:45)；[S/backend/tests/test_temporal_contract.py:594](/Users/liu/Desktop/FYP2-Live-System/backend/tests/test_temporal_contract.py:594) | 旧证据可当持续风险；snapshot PASS不等于需求满足 | 明确maximum usable age/stale-only policy，不发明任意expiry阈值 | P0/P1 |
| R10 | UT-TIME-05 equal timestamp | 相等timestamps通过且可累积 | guard为<；新UUID允许同证据；同UUID重试则幂等 | CONFIRMED | [S/backend/app/routers/windows.py:22](/Users/liu/Desktop/FYP2-Live-System/backend/app/routers/windows.py:22)；[S/backend/app/routers/windows.py:53](/Users/liu/Desktop/FYP2-Live-System/backend/app/routers/windows.py:53)；[S/backend/tests/test_temporal_contract.py:494](/Users/liu/Desktop/FYP2-Live-System/backend/tests/test_temporal_contract.py:494) | 重复证据≠持续新观察 | 区分request identity与evidence进度，冻结计时政策 | P1 |
| R11 | 30/60；2s/10s exact boundary | latest边界独立literal覆盖 | R-DIAG 29.9/30/59.9/60、1999/2000ms、Low9999/10000ms匹配 | CONFIRMED | [S/backend/app/fusion.py:95](/Users/liu/Desktop/FYP2-Live-System/backend/app/fusion.py:95)；[S/backend/tests/test_temporal_contract.py:69](/Users/liu/Desktop/FYP2-Live-System/backend/tests/test_temporal_contract.py:69)；[S/backend/tests/test_temporal_contract.py:95](/Users/liu/Desktop/FYP2-Live-System/backend/tests/test_temporal_contract.py:95) | 修正“边界完全未覆盖”的旧描述；非实际总检测延迟 | 保留alpha1隔离FSM，再测EMA+FSM事件响应 | P1 |
| R12 | Task5 unavailable FSM | 不可用挂起计时、内部latch保留 | None输出、high/low streak清空；恢复重新锚定；>3s完全gap另reset | CONFIRMED | [S/backend/app/inference.py:73](/Users/liu/Desktop/FYP2-Live-System/backend/app/inference.py:73)；[S/backend/app/inference.py:81](/Users/liu/Desktop/FYP2-Live-System/backend/app/inference.py:81)；[S/backend/tests/test_temporal_contract.py:193](/Users/liu/Desktop/FYP2-Live-System/backend/tests/test_temporal_contract.py:193) | no-assessment不会赚取Low/High时长；策略差异需披露 | 分开连续不可用与无处理gap，保留恢复测试 | P0已修 |
| R13 | SUMMARY F2 /Task-F2 | watermark豁免和动态守卫已修 | 常量不相交；HTTP gap+older captured_at test存在 | CONFIRMED | [S/backend/app/inference.py:32](/Users/liu/Desktop/FYP2-Live-System/backend/app/inference.py:32)；[S/backend/tests/test_temporal_contract.py:526](/Users/liu/Desktop/FYP2-Live-System/backend/tests/test_temporal_contract.py:526) | SUMMARY旧“F2未修”已过期 | 报最新ef2417d后的状态；补telemetry_timestamp对称HTTP测试 | P1 |
| R14 | DominantEvidence/explanation | Vision-dominant被解释为driving output | pd=.8,pt=.6,w=.3/.7，score66；贡献24/42却Vision-dominant；算法不接收weights | INCORRECT | [S/backend/app/fusion.py:132](/Users/liu/Desktop/FYP2-Live-System/backend/app/fusion.py:132)；[S/backend/app/fusion.py:223](/Users/liu/Desktop/FYP2-Live-System/backend/app/fusion.py:223)；[S/backend/app/inference.py:133](/Users/liu/Desktop/FYP2-Live-System/backend/app/inference.py:133) | 解释可与真正加权贡献相反 | 定义raw strength或weighted contribution；相应修文案/算法/oracle | P1 |
| R15 | E4 EMA effectiveness | A要求平滑和step lag并报 | 同timeline .2→1、T=.4、1s cadence：alpha1 t2 HIGH_ALERT；.35 t5；首次High t0 vs t3 | CONFIRMED | [M/docs/fyp2/03_EVALUATION_COVERAGE_MATRIX.md:80](/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/docs/fyp2/03_EVALUATION_COVERAGE_MATRIX.md:80)；[S/backend/app/inference.py:116](/Users/liu/Desktop/FYP2-Live-System/backend/app/inference.py:116)；[S/backend/tests/test_temporal_contract.py:50](/Users/liu/Desktop/FYP2-Live-System/backend/tests/test_temporal_contract.py:50) | 本反例增加3s；不能把2sFSM称总检测延迟 | 报cadence、多stream smoothing/lag；不外推此单例为实机平均 | P1 |
| R16 | B03/E4 failures/recovery | A指出恢复、maxN、fault logs缺口；S Task7–10未完成 | runtime异常未全分类；503停，其它无界次数backoff；每tick新UUID/frame；仅success records | CONFIRMED | [S/backend/app/providers/trained.py:103](/Users/liu/Desktop/FYP2-Live-System/backend/app/providers/trained.py:103)；[S/frontend/src/hooks/useLiveSession.ts:153](/Users/liu/Desktop/FYP2-Live-System/frontend/src/hooks/useLiveSession.ts:153)；[S/frontend/src/hooks/useLiveSession.ts:180](/Users/liu/Desktop/FYP2-Live-System/frontend/src/hooks/useLiveSession.ts:180)；[S/backend/app/models.py:20](/Users/liu/Desktop/FYP2-Live-System/backend/app/models.py:20) | 成功接线不能证明故障后恢复或≥99%logging | bounded/frozen retry、typed durable fault ledger、commit后timeout对账 | P0 |
| R17 | Task6 VERIFIED/B04 | S明确只pure-functions、无UI当前验收 | vitest=node，仅.test.ts；真实模型API是纯色JPEG+sameprovider oracle | CONFIRMED | [S/vitest.config.ts:8](/Users/liu/Desktop/FYP2-Live-System/vitest.config.ts:8)；[S/backend/tests/test_live_inference.py:17](/Users/liu/Desktop/FYP2-Live-System/backend/tests/test_live_inference.py:17)；[S/docs/fyp2/implementation/TASK_1_TO_6_SUMMARY.md:188](/Users/liu/Desktop/FYP2-Live-System/docs/fyp2/implementation/TASK_1_TO_6_SUMMARY.md:188) | 不能扩张为DOM/system/UAT VERIFIED | 最新browser→API→DB→export逐ID验证null/恢复/五视图 | P0/P1 |
| R18 | B real camera已跑通 | 真实camera，telemetry仍prepared_replay；准确率未验证 | 394 unique frames/201/c8可复数；811 JSON/CSV字段/公式匹配；无动作真值 | CONFIRMED | [M/docs/fyp2/09_BROWSER_VERIFICATION_2026-10-12.md:7](/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/docs/fyp2/09_BROWSER_VERIFICATION_2026-10-12.md:7)；[M/docs/fyp2/09_BROWSER_VERIFICATION_2026-10-12.md:22](/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/docs/fyp2/09_BROWSER_VERIFICATION_2026-10-12.md:22)；[M/docs/fyp2/09_BROWSER_VERIFICATION_2026-10-12.md:54](/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/docs/fyp2/09_BROWSER_VERIFICATION_2026-10-12.md:54) | 旧真实camera证据有效，但不能称当前系统完成或field accuracy | 保留旧版本，做同人/动作/光照/距离配对机位及标注测试 | P0/P1 |
| R19 | E1-V 6×3 | A称pilot不是完整E1 | pilot是val1000/.35brightness/Gaussian radius2；非heldout18conditions；ResNet18缺 | CONFIRMED | [M/docs/fyp2/03_EVALUATION_COVERAGE_MATRIX.md:20](/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/docs/fyp2/03_EVALUATION_COVERAGE_MATRIX.md:20)；[M/ml/experiments/robustness_probe.py:24](/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/ml/experiments/robustness_probe.py:24)；[M/ml/experiments/robustness_probe.py:31](/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/ml/experiments/robustness_probe.py:31) | 不得把Gaussian称motion，grayscale称IR，帧数当独立drivers | 成对clean、共享IDs/seed、driver/clip cluster、label QC | P1 |
| R20 | E1-T D0–D3/45,000 | A称4500×10设计尚未生成；D0 synthetic | 仅现成D0 XGB；无D1–3generator/flags/raw results；计数正确 | CONFIRMED | [M/docs/fyp2/03_EVALUATION_COVERAGE_MATRIX.md:36](/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/docs/fyp2/03_EVALUATION_COVERAGE_MATRIX.md:36)；[M/docs/fyp2/03_EVALUATION_COVERAGE_MATRIX.md:41](/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/docs/fyp2/03_EVALUATION_COVERAGE_MATRIX.md:41) | 三模型复用45k，不是135k独立记录；clean synthetic仍synthetic | 固定source_record_id；D0=true/false flags；统计/masks provenance | P1 |
| R21 | D2 held-out label conditioning | A已指出人工label-conditioned stress | shift由test y选train class mean；train stats本身不足以保证label validity | CONFIRMED | [M/docs/fyp2/03_EVALUATION_COVERAGE_MATRIX.md:38](/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/docs/fyp2/03_EVALUATION_COVERAGE_MATRIX.md:38)；[M/docs/fyp2/03_EVALUATION_COVERAGE_MATRIX.md:43](/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/docs/fyp2/03_EVALUATION_COVERAGE_MATRIX.md:43) | 新x可能改变行为语义，F1不能直接解释真实泛化 | 保留真实y不作选择泄漏指控；叫label-conditioned stress，QC不成立用flip/distribution | P1 |
| R22 | E2 six strata/five weights | A明确constructed/PLANNED，无真实risk oracle | 五权重手算匹配；无真实source pair manifest/full sweep；classification labels≠共同severity | CONFIRMED | [M/docs/fyp2/03_EVALUATION_COVERAGE_MATRIX.md:55](/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/docs/fyp2/03_EVALUATION_COVERAGE_MATRIX.md:55)；[M/docs/fyp2/03_EVALUATION_COVERAGE_MATRIX.md:59](/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/docs/fyp2/03_EVALUATION_COVERAGE_MATRIX.md:59) | formula/score distribution≠risk accuracy | 独立预先定义scenario oracle；报告构造和unique input依赖 | P1 |
| R23 | E5 fusion safety implication | 用人工非同时配对或较小Δscore证明真实safety benefit | 当前无对应paired outcome ground truth；平均会机械缩小单路score波动；高V可被稀释 | UNSUPPORTED | [M/docs/fyp2/03_EVALUATION_COVERAGE_MATRIX.md:94](/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/docs/fyp2/03_EVALUATION_COVERAGE_MATRIX.md:94)；[M/docs/fyp2/03_EVALUATION_COVERAGE_MATRIX.md:97](/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/docs/fyp2/03_EVALUATION_COVERAGE_MATRIX.md:97) | 不能证明事故预防、真实高风险recall或安全优越；A已禁止该推论 | 配对counterfactual+独立high-risk oracle+negative cases；如无真值仅报操作指标 | P1 |
| R24 | M1 five models/all-five tuning | A称ResNet18/RF/telemetryLR缺、HPO未完成 | 当前两branch ml相同；Large/Small配置、fixedXGB+valearlystop、imageLR不是telemetryLR | CONFIRMED | [M/docs/fyp2/04_ML_COMPARISON_AND_TUNING_AUDIT.md:11](/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/docs/fyp2/04_ML_COMPARISON_AND_TUNING_AUDIT.md:11)；[M/ml/vision/train_vision.ipynb:611](/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/ml/vision/train_vision.ipynb:611)；[M/ml/telemetry/train_telemetry.ipynb:258](/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/ml/telemetry/train_telemetry.ipynb:258)；[M/ml/experiments/linear_probe.py:101](/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/ml/experiments/linear_probe.py:101) | 两baseline或Small/B0不能满足指定五模型比较 | bounded val-only trials、统一split/preprocess、选择记录、最终test冻结 | P1 |
| R25 | split seed/provenance未知 | A说generator seed尚未重构 | 本轮seed42 reconstruction逐元素/driver partitions全匹配 | CONFIRMED | [M/docs/fyp2/04_ML_COMPARISON_AND_TUNING_AUDIT.md:26](/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/docs/fyp2/04_ML_COMPARISON_AND_TUNING_AUDIT.md:26)；[D/scripts/run_eda_data_cleaning.py:360](/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment-/scripts/run_eda_data_cleaning.py:360)；[D/scripts/run_eda_data_cleaning.py:1501](/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment-/scripts/run_eda_data_cleaning.py:1501) | 首审未决项可收窄；仍不证明历史训练不可变或生成独立性 | 更新为seed/生成机制已重构；保留历史hash/source-ID/near-dup限制 | P2 |
| R26 | EDA “training-set median” | 外部生成文档称train-only imputation | 脚本先对全30k计算median再split；global/train8/8不同；原8features无NaN | INCORRECT | [D/scripts/run_eda_data_cleaning.py:1446](/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment-/scripts/run_eda_data_cleaning.py:1446)；[D/scripts/run_eda_data_cleaning.py:1501](/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment-/scripts/run_eda_data_cleaning.py:1501)；[D/scripts/run_eda_data_cleaning.py:1830](/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment-/scripts/run_eda_data_cleaning.py:1830) | 潜在未来D3泄漏；**无依据称当前.9993被填补污染** | 三模型共同train-fit imputer；heldout改变不得影响fit；修provenance | P1 |
| R27 | test used for selection? | A称test曝光已发生、未证明test tuning | vision val accuracy选择epoch；XGB eval_set=val earlystop；test报告/重复评估已存在 | UNRESOLVED | [M/ml/vision/train_vision.ipynb:617](/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/ml/vision/train_vision.ipynb:617)；[M/ml/telemetry/train_telemetry.ipynb:258](/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/ml/telemetry/train_telemetry.ipynb:258)；[M/ml/telemetry/train_telemetry.ipynb:330](/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/ml/telemetry/train_telemetry.ipynb:330) | 无直接test选参代码，不能指控已证实leakage；也不能叫pristine封存test | 披露既有test曝光，未来所有HPO只用val；保留selection logs | P1 |
| R28 | calibration/probability | A称未calibrate、非mandatory新gate | 无calibration fit；benchmark Brier是测量；1−P(c0)、1−P(normal)为不同任务分数 | CONFIRMED | [M/docs/fyp2/04_ML_COMPARISON_AND_TUNING_AUDIT.md:40](/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/docs/fyp2/04_ML_COMPARISON_AND_TUNING_AUDIT.md:40)；[M/ml/experiments/vision_benchmark.py:70](/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/ml/experiments/vision_benchmark.py:70)；[S/backend/app/providers/trained.py:103](/Users/liu/Desktop/FYP2-Live-System/backend/app/providers/trained.py:103) | RiskScore不是calibrated accident probability，跨modality尺度可不等价 | 明示局限；如后续calibration用val且freeze，不新增本审 mandatory gate | P2 |
| R29 | DMD M2 | A未找到access/license/mapping，定量BLOCKED | 当前无local labels/interval/person grouping/mapping；实际entitlement无法仓库确认 | UNRESOLVED | [M/docs/fyp2/04_ML_COMPARISON_AND_TUNING_AUDIT.md:58](/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/docs/fyp2/04_ML_COMPARISON_AND_TUNING_AUDIT.md:58) | 不能宣称已获权限、独立frames或10class外部accuracy | 获得明确access后按clip/person分组与兼容subset；无证据时报告blocked | P1/P2 |
| R30 | S F1/F4/rounding contract | expected matrix仍旧、half-up未回写；F2后来已修 | CSV W16/17/19与最新contract不符；summary明示F4延后；half-up数值有意改变 | CONFIRMED | [S/ai/prototype-data/prepared_sessions/session_001/missing_cases.csv:7](/Users/liu/Desktop/FYP2-Live-System/ai/prototype-data/prepared_sessions/session_001/missing_cases.csv:7)；[S/frontend/src/data/preparedSessionInput.ts:87](/Users/liu/Desktop/FYP2-Live-System/frontend/src/data/preparedSessionInput.ts:87)；[S/docs/fyp2/implementation/TASK_1_TO_6_SUMMARY.md:169](/Users/liu/Desktop/FYP2-Live-System/docs/fyp2/implementation/TASK_1_TO_6_SUMMARY.md:169) | fixture表格、图表与演示可能冲突；网格17%不能外推运行分布 | 同步expectedCSV/brief/globalconstraints；保留before-after与EPS集成回归 | P1 |
| R31 | migration“不丢数据”/exports | S说明幂等且历史nullable canonicalization | db对有效对象旧UNAVAILABLE四字段置null；NULL JSON export缺guard；并非真实DB已迁移 | CONFIRMED | [S/backend/app/db.py:71](/Users/liu/Desktop/FYP2-Live-System/backend/app/db.py:71)；[S/backend/app/routers/export.py:51](/Users/liu/Desktop/FYP2-Live-System/backend/app/routers/export.py:51)；[S/docs/fyp2/implementation/TASK_1_TO_6_SUMMARY.md:195](/Users/liu/Desktop/FYP2-Live-System/docs/fyp2/implementation/TASK_1_TO_6_SUMMARY.md:195) | 不删行≠历史payload逐字保持；特殊NULL可能中途stream失败 | 披露不可逆改写，真实迁移另有备份/授权；补malformed/NULL export测试 | P1/P2 |
| R32 | rubric evaluation8 /UAT | A称五类必须分别举证、无真实UAT | 有unit/integration及B旧系统片段；无S完整system/UAT记录；原official marking sheet未找到 | CONFIRMED | [M/docs/fyp2/05_RUBRIC_TRACEABILITY_AND_REPORT_MAP.md:10](/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/docs/fyp2/05_RUBRIC_TRACEABILITY_AND_REPORT_MAP.md:10)；[M/docs/fyp2/05_RUBRIC_TRACEABILITY_AND_REPORT_MAP.md:39](/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/docs/fyp2/05_RUBRIC_TRACEABILITY_AND_REPORT_MAP.md:39) | survey模板不是完成UAT；model benchmark不是system test；不能授分 | 以用户提供rubric映射，真实参与者任务/反馈/结果另列 | P1 |

R23 是对**禁止推论**的判断，并非声称 A 实际作出过该过度主张。A 对 D2、Δ≤.15、45k、calibration、DMD、E1标签、E2/E5安全含义、EMA lag 已有明确批评，相关行属于独立确认，而非“首次发现”。

## 4. E1–E5 方法学结论与五模型完整性

| Requirement | 方法学 verdict | 当前完成度 / 可被证伪的设计 |
|---|---|---|
| E1 Vision6×3 | SOUND_WITH_RESTRICTIONS | brightness+1.2/1.5/1.8、−.8/.5/.3；motion kernels3/7/11；occlusion5/10/20%；rotcrop±3/7/12°；grayscale30/60/100%。同heldout IDs/clean基线、共享变换。遮挡/裁切若移除动作判据，先独立QC，不能强保原标签。样本推断按driver/clip cluster；4个test drivers≠3657独立人。当前未完成。 |
| E1 TelemetryD0–D3 | SOUND_WITH_RESTRICTIONS | D0 synthetic=true/perturbed=false；D1 σ=.1/.3/.5 trainSD；D2 λ=.25/.5/.75、train global/class均值但heldout y选shift；D3 drift .25/.5/1 trainSD和固定masks、train-only median，三模型同一生成集。45k=4500×(1+9)，并非实产物。D2标签失效时不用F1当自然泛化oracle。 |
| E2 | SOUND_WITH_RESTRICTIONS | 六构造strata、五固定weights；手算可验证formula，source pairing/真实severity尚无。score稳定、等级覆盖、raw dominance规则是操作结果。独立co-timed outcome标签缺失时不报risk accuracy/事故预防。 |
| E3 | NEEDS_REDRAFT（无条件Δ gate）；其余SOUND_WITH_RESTRICTIONS | nullable与零权重最新已修；.45归一化解释正确；Δ=.4必须原样报告target未达。所有9freshness组合、async、expiry/repeat政策及UI/export仍要覆盖。不可把known-limitation快照通过当robustness完成。 |
| E4 | SOUND_WITH_RESTRICTIONS；部分需求NEEDS_DECISION | α1隔离FSM与α.35组合分别测；精确2s/10s、3sage、gap、 unavailable挂起已具unit基础。最大可用age、maxN和logging分母需冻结；fault recovery、longsession、capture→render≤1s没有本轮完整结果。 |
| E5 | SOUND_WITH_RESTRICTIONS | 固定paired IDs、只改一路、V-only/T-only/fusion三对照；既报告稳定性也报告高风险稀释和lag。若ground truth仅构造标签，结论限构造scenario；真实fusion safety benefit UNSUPPORTED。 |

五个指定模型是 **MobileNetV3-Large、ResNet18、XGBoost、Random Forest（telemetry）、Logistic Regression（telemetry）**。当前仅前者和XGB有指定baseline产物；Large/Small或EfficientNet/image logistic probe不可替代其余三模型。所有五模型的 bounded HPO 仍为后续开发任务；本轮没有启动实验。

现有 epoch/early-stopping 使用 validation，未发现直接 test-selected 参数代码。既有 test 输出与重复评估必须披露；不能证明研究人员从未受 test 指标影响，也不能据此指控已发生直接泄漏。未来比较须同split、同feature/label order、train-fit transforms、val-only selection、有限trial预算、checkpoint/seed/选择日志和一次冻结后的final evaluation。Vision保留macro-F1/per-class recall/confusion，尤其薄弱类；不能只看accuracy。

DMD不能仅凭视频帧数量称独立验证：需要license/access、action intervals、frame timestamps、clip/person grouping、重复帧检查和compatibility mapping。没有这些资料时，任务保持blocked，不能用人工配对或RGB grayscale替代DMD/IR实证。校准不是新增 mandatory gate，但概率尺度与RiskScore语义限制必须写入报告。

## 5. 用户提供的8-mark system evaluation rubric

未找到独立可认证的官方原始marking sheet，下面只按包内用户提供的类别映射，不授予分数。

| Category | 有效现存证据 | Week7缺口 |
|---|---|---|
| Unit | A literal数学/FSM；S vectors、nullable、fakeclock boundaries；本轮28 core诊断 | EPS producer集成、weighted解释、stale/evidence identity、combined EMA lag；旧不正确oracle更新 |
| Integration | 实模型API接线、CRUD/idempotency/restart/migration；纯色图无行为真值 | timeout-after-commit、runtime模型/DB故障、durable outcomes；S记录逐ID对UI/latest/exports |
| System | B旧版physical-camera/five-view/export记录有效且限定；未执行S当前browser验收 | 当前S完整正常/不可用/恢复、渲染null、全量trace、endurance和性能 |
| UAT | 未发现真实参与者任务结果与反馈 | 真实任务、匿名participant IDs、成功/困难/耗时、原始反馈及分析；模板不算完成，不发明n |
| Error Handling | load503、invalid422、乱序409及部分contract单测 | 有界恢复政策、frozen retry、typed fault日志、去重与状态只推进一次、全链用户可见错误 |

模型benchmark与E1–E5不替代这些类别。日志≥99%必须先定义“所有eligible unique requests（含失败/timeout）”与“成功prediction persistence”的不同分母；不能stored_rows/stored_rows自证100%。当前请求计时结束早于DB commit，frontend requestMs又不含render（[S/backend/app/routers/windows.py:62](/Users/liu/Desktop/FYP2-Live-System/backend/app/routers/windows.py:62)；[S/frontend/src/hooks/useLiveSession.ts:139](/Users/liu/Desktop/FYP2-Live-System/frontend/src/hooks/useLiveSession.ts:139)），故未证明capture→render≤1s。FSM High sustain≥2s属于alert time-to-detect，不能混为处理延迟。

## 6. Week7前 Top10 actual gaps

以下按最新 S 和当前 M 判断；**B01、B02和已修F2不再作为未修缺陷**。这些是整改/补证清单，本次审查未实施。

1. **P0：更正Live stale错误范围并冻结expiry/repeated-evidence政策。** 过去timestamp可进入Live stale；旧输入不会自动missing，相等证据能推进告警。改source-string guard为完整pipeline可反证测试。
2. **P0：完成typed fault handling、bounded frozen-payload retry和持久outcome ledger。** 覆盖模型运行异常、DB故障、网络断连以及commit后response丢失，确保同UUID恰一记录和一次状态推进；maxN按明确需求，不能随意写3。
3. **P0：S当前version的browser→API→DB→export E2E。** null在五视图/图表/历史/JSON/CSV正确，暂停/恢复和latest来源清楚；B旧版存档不能代替S验收。
4. **P0/P1：目标摄像头的带标注可用性验证。** 394不同画面全部c8暴露真实问题；同人/动作/光照/距离配对候选机位，保留真值和混淆结果。不能把其根因判为唯一机位问题或调整阈值掩盖。
5. **P1：版本绑定且可复现的release证据。** 最新full gates/raw logs、clean-install依赖闭包、model/data manifests、启动/readiness/error状态；坏FYP_DATA_ROOT不应静默回退后声称freeze成功。当前共享venv pin不是clean-install证明。
6. **P1：补齐指定五模型比较与all-five bounded HPO。** 仅val选参；test曝光如实披露；不用Small/B0/imageLR顶替指定comparator。
7. **P1：完成E1生成/paired结果并修train-only统计 provenance。** Vision6×3含QC和driver cluster；Telemetry45k含IDs/flags/sharedmasks；global median不得进入未来D3。
8. **P1：E2/E5固定pair manifest、独立oracle和解释语义。** 五weights，同counterfactual与negative dilution例；DominantEvidence明确raw strength还是weighted contribution；没有真实paired真值就不作safety claim。
9. **P1：E4量化EMA lag、故障/长期表现和性能。** 固定timeline不同cadence，同时报平滑与step/event lag；capture→render原始分段计时；logging≥99%独立ledger对账。
10. **P1：真实UAT及最新报告/fixture同步。** official rubric来源待核；实际参与者任务结果；F1 expectedCSV、F4 half-up计划/brief、截图/表格随latestcontract刷新，不声称模板等于UAT。

## 7. 优先补测/修订测试：精确输入与独立oracle

全部是 **PLANNED / NOT_RUN**，不是新增测试文件或执行结果。未定政策明确标“先冻结”，不由 reviewer 发明安全阈值或满意度PASS线。

| Priority / test | 精确输入/操作 | 独立oracle与可反证点 |
|---|---|---|
| P0 UT/IT-LIVE-AGE | 真实provider验timestamp/status；保留其provenance的stub另固定两路raw=.9。新session，captured_at/telemetry_timestamp=now−30days；新UUID在0/1/2s投递；另age2.999/3/3.001s、future和timezone。 | 先确认完整Live会转stale，不能source文本自证不可达。expiry政策冻结后，以需求规定的max_age前/等于/后断言nullable/告警语义；固定stub输出下的90/DEGRADED→HIGH_ALERT是限制记录，不是安全PASS；真实provider不预设raw=.9。 |
| P0 IT-RETRY-IDENTITY | 合法请求commit后丢response，再同UUID/同payload重发；同UUID改payload；另不同UUID/相同captured_at和严格递增captured_at三组。 | DB独立计数：重试恰1row/state一次、内容冲突409；evidence重复不应被假设为持续新观察，按冻结政策断言计时；严格递增新证据按declared FSM推进。 |
| P0 ST-FAIL-RECOVERY | native ORT runtime抛错、单branch失败、DBcommit失败、网络timeout；连续1..N..N+1；保留每次submitted request ledger；恢复后重发frozen input。 | 错误类别/stop-or-degrade/最大N由明确policy给出；每eligible请求有成功或失败持久outcome；没有fake fallback、重复记录/双重EMA；UI可见错误和恢复最新记录，不仅assertHTTP!=200。 |
| P0 ST-LATEST-E2E | S隔离backend/browser/DB；fresh/fresh→Vmissing→bothmissing→fresh；查看五视图、暂停/恢复、flag、reload、全JSON/CSV。 | 事先固定每个request/evidence ID；API saved payload=DB=latest=同window UI数据=对应export；bothmissing四字段null、false、UNAVAILABLE，图表不可绘成0Low；所有行identity对账而非抽6cell。 |
| P1 IT-EPS | 两路weights和为1；可用branch的weight分别1e−10、1e−9、1.1e−9，另一branch missing，概率.8；双向重复。 | literal eps=1e−9；前两组201 unavailable/fournull，第三可用score80；state不被validation失败部分推进。能杀死producer `>`→`>=`/`>0` mutants。 |
| P1 UT-WEIGHTED-EXPLANATION | alpha1/fresh，pd=.9,pt=.6，w=.1/.9；再w=0/1；另pd=.8,pt=.6,w=.3/.7。 | 手算score63/60/66，贡献9/54、0/60、24/42。若label定义为weighted driver，telemetry必须主导；若raw strength，文案不得称vision driving fused output。oracle不调用dominance helper。 |
| P1 UT-TIME-MATRIX | fakeclock High0/1999/2000ms；Low从3000ms开始每1000ms持续tick至12000ms，再12999/13000ms，避免gap reset；Medium中断；另独立gap2999/3000/3001ms；unavailable插入后恢复。 | 硬编码独立要求2s/10s、>3s；alpha1隔离EMA；不可用不计入High/Low持续时长。分别断言watermark保留，captured_at和telemetry_timestamp各一HTTP场景。 |
| P1 E4-EMA-STEP | pd=.2在t−1，t0持续变1，pt=.4，fresh/.5/.5；1s cadence，alpha1与.35；再0.1s cadence固定总时间。 | 独立递推含3dp half-up：.48/.662/.780/.857/.907/.940；score44/53.1/59/62.9/65.4/67；1s组High t0/t3，HIGH_ALERT t2/t5。报total variation/flip及lag，不把平滑降低当单向PASS。 |
| P1 E1-V-GENERATOR | 固定heldout ID manifest，N个clean+上述18变换；seed42、保存kernel方向/occlusion位置/crop；同两模型输入逐byte。 | 输入数N×19，模型prediction两份；driver-disjoint、无ID重采样；独立recognizability QC决定label可用性；macro-F1/recall/confusion基于有效标签，invalid例另报flip；不预设robustness必须改善。 |
| P1 E1-T-IMPUTER/COUNT | unit toy train=[0,2]，heldout=[100,1000,NaN]；再改heldout100/1000；实际4500 source IDs及9stressvariants共享三模型。 | trainmedian=1，NaN填1且heldout变化不影响fit；D0 synthetic=true/perturbed=false；45krows、unique source=4500、同masks/stats；单位/physical bounds/QC独立；不把135kpredictions当独立records。 |
| P1 E2-WEIGHTS | 同pair raw(.1,.9)，fresh，weights(.5,.5),(.6,.4),(.4,.6),(.7,.3),(.3,.7)，另六strata固定source pairs。 | literal scores50/42/58/34/66；formulaerror可PASS。constructed severity只用预先独立policy，不能由融合公式生成再验证自身；risk accuracy没有ground truth时NA。 |
| P1 E3/E5-NEGATIVE | (.1,.9)full/Vmissing；(.9,.1)equal；相同pair只corrupt一路，固定另一输入/weights/time。 | Δ=.4原targetNOT_MET而formula正确；.9高V与.1低T融合50/Medium是稀释反例。high-risk retention须独立severity真值；较小Δscore不能自动PASS safety。 |
| P1 PERF/LOG | 固定计时起止capture→render、预处理/模型/commit/网络/render段；固定声明device/warmups/session duration/故障注入；外部ledger所有eligibleunique requests。 | 依正式需求冻结≤1s的max或p95口径后评价；原始timing分布、drop/skip数；≥99%分别按success persistence与alloutcomes分母。不能只计HTTP时间或stored/stored。 |
| P1 UAT | 实际参与者执行start/stop camera、解释DEGRADED/UNAVAILABLE、找历史/flag、导出、故障恢复；预先同任务脚本与匿名IDs。 | 实际完成/困难/时间/反馈的原始记录和汇总；样本量/满意度阈值预先定义并披露，不发明参与者、不用survey template或developer自检顶替。 |

## 8. Artifact/data指纹与复现附录

本轮R-TELEMETRY/R-SPLITS确认以下SHA256，均与首审baseline相符；hash证明当前内容一致，不证明历史全程封存。

| Artifact | SHA256 |
|---|---|
| M/ml/outputs/vision/mobilenetv3_large_vision.onnx | `b3a42e8dd4553355b1fd7d9e7fe3d28e318decb894e76eb029489b7ff2e90bcf` |
| M/ml/outputs/vision/mobilenetv3_large_vision.pt | `196ca7b151d84e0c4a8eac87128da9dd8f22c894984a991ef611536bb523e7c7` |
| M/ml/outputs/telemetry/xgb_telemetry.json | `9802cb06ca98f0c1befaf851fa7668cfec70e005cf8bb3884e49d7d45d7aec07` |
| D/eda_outputs/processed/vision/vision_metadata_with_split.csv | `b4f8e90dec769bb419eaa490aea869668bed6484089cebe4d545c7667baa8ea4` |
| D/eda_outputs/processed/telemetry/telemetry_train.csv | `97dd20ee9c0832ba33455e5c31088f9b4abb65c198bf988699a959d545d1e5b5` |
| D/eda_outputs/processed/telemetry/telemetry_val.csv | `1b02792df846b5af138bae59e4f4ccfa8fa421fbb4fd6d42fad88d57722774f1` |
| D/eda_outputs/processed/telemetry/telemetry_test.csv | `3bc3d47680a87359e1470fd8ffaf5ff330dc4419b37cc645e5736d51a91c96de` |
| D/scripts/run_eda_data_cleaning.py | `f62aff320ef267dd6abcc3e1c18e4d9895f16889891451348e74496ef57a6505` |

### 8.1 实际执行的R-DIAG命令（cwd=M）

其中expectations为手写字面量；observations仅记录反例，不冒充model/system test。无文件输出。

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/Users/liu/Desktop/FYP2-Live-System/backend DRA_DATABASE_URL=sqlite:///:memory: .venv/bin/python -B - <<'PY'
import json, signal
from datetime import datetime, timezone, timedelta
from app import fusion, inference
from app.schemas import WindowInput, RuntimeConfig
signal.alarm(30)
base=datetime(2026,10,9,10,tzinfo=timezone.utc)
rows=[]
def rec(id,expected,actual):
 rows.append(dict(id=id,expected=expected,actual=actual,match=actual==expected))
for vs,ts,expected in [('fresh','fresh',50),('missing','fresh',90),('fresh','missing',10),('stale','fresh',65.2),('fresh','stale',34.8),('stale','stale',50)]:
 rec('formula-'+vs+'-'+ts,expected,fusion.compute_risk_score(.1,.9,.5,.5,vs,ts))
for wv,wt,expected in [(.5,.5,50),(.6,.4,42),(.4,.6,58),(.7,.3,34),(.3,.7,66)]:
 rec('weights-'+str(wv),expected,fusion.compute_risk_score(.1,.9,wv,wt))
for score,expected in [(29.9,'Low'),(30,'Medium'),(59.9,'Medium'),(60,'High')]:
 rec('level-'+str(score),expected,fusion.map_risk_level(score))
for age,expected in [(2.999,'fresh'),(3,'fresh'),(3.001,'stale')]:
 rec('age-'+str(age),expected,inference.freshness('fresh',(base-timedelta(seconds=age)).isoformat(),base,3))
state={}
for t,p,expected in [(0,1,'CAUTION'),(1.999,1,'CAUTION'),(2,1,'HIGH_ALERT'),(3,0,'HIGH_ALERT'),(5,0,'HIGH_ALERT'),(7,0,'HIGH_ALERT'),(9,0,'HIGH_ALERT'),(11,0,'HIGH_ALERT'),(12.999,0,'HIGH_ALERT'),(13,0,'NORMAL')]:
 r=inference.run_inference('cr',1,WindowInput(P_distraction=p,P_telemetry_anomaly=p),state=state,config=RuntimeConfig(ema_alpha=1),now=base+timedelta(seconds=t))
 rec('fsm-'+str(t),expected,r.AlertSeverity)
obs={}
for name,vs,ts,wv,wt in [('both_missing','missing','missing',.5,.5),('zero_vision','missing','fresh',1,0),('zero_telemetry','fresh','missing',0,1)]:
 r=inference.run_inference('cr',1,WindowInput(P_distraction=.1,P_telemetry_anomaly=.9,vision_status=vs,telemetry_status=ts),config=RuntimeConfig(weight_vision=wv,weight_telemetry=wt),now=base)
 obs[name]={k:getattr(r,k) for k in ['assessment_available','RiskScore','RiskLevel','SystemHealth','AlertSeverity','DominantEvidence']}
state={};seq=[]
for t in [0,1,2]:
 r=inference.run_inference('cr',1,WindowInput(P_distraction=.9,P_telemetry_anomaly=.9,timestamp=(base-timedelta(days=1)).isoformat()),state=state,now=base+timedelta(seconds=t))
 seq.append([t,r.RiskScore,r.SystemHealth,r.AlertSeverity])
obs['repeated_day_old_capture']=seq
obs['weighted_dominant']={'score':fusion.compute_risk_score(.8,.6,.3,.7),'label':fusion.determine_dominant_evidence(.8,.6,66,'FULL'),'vision_points':24,'telemetry_points':42}
obs['delta_missing']=(fusion.compute_risk_score(.1,.9,.5,.5,'missing','fresh')-fusion.compute_risk_score(.1,.9,.5,.5))/100
for alpha in [1,.35]:
 state={};seq=[]
 for t in [-1,0,1,2,3,4,5]:
  p=.2 if t==-1 else 1
  r=inference.run_inference('cr',1,WindowInput(P_distraction=p,P_telemetry_anomaly=.4),state=state,config=RuntimeConfig(ema_alpha=alpha),now=base+timedelta(seconds=t))
  seq.append([t,r.P_distraction,r.RiskScore,r.RiskLevel,r.AlertSeverity])
 obs['step_alpha_'+str(alpha)]=seq
print(json.dumps({'executed_utc':datetime.now(timezone.utc).isoformat(),'matches':sum(x['match'] for x in rows),'cases':rows,'observations':obs},indent=2))
PY
```

关键stdout：matches=28；both_missing、zero_vision、zero_telemetry均 `assessment_available=false`、四risk字段null、health UNAVAILABLE；day-old序列 `[[0,90,DEGRADED,CAUTION],[1,90,DEGRADED,CAUTION],[2,90,DEGRADED,HIGH_ALERT]]`；weighted_dominant=score66/labelVision-dominant/24vs42；delta_missing=.4；step alpha1在t2 HIGH_ALERT、alpha.35在t5 HIGH_ALERT。

### 8.2 实际执行的R-TELEMETRY命令（cwd=M）

独立从gold labels计算confusion/F1，不引用存储metrics作为expected。metrics只用于feature/class order与best_iteration contract。

```bash
PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 .venv/bin/python -B - <<'PY'
import signal, hashlib,json
from pathlib import Path
from datetime import datetime,timezone
import numpy as np, pandas as pd, xgboost as xgb
signal.alarm(30)
root=Path('.');data=Path('/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment-/eda_outputs/processed')
meta=json.loads((root/'ml/outputs/telemetry/metrics.json').read_text())
df=pd.read_csv(data/'telemetry/telemetry_test.csv')
booster=xgb.Booster();booster.load_model(root/'ml/outputs/telemetry/xgb_telemetry.json');booster.set_param({'nthread':2})
assert booster.feature_names==meta['features']
best=int(booster.attr('best_iteration'));assert best==meta['best_iteration']
probs=booster.predict(xgb.DMatrix(df[meta['features']].astype(float)),iteration_range=(0,best+1))
y=df.behavior_label.map({name:i for i,name in enumerate(meta['classes'])}).to_numpy();pred=probs.argmax(1)
cm=np.zeros((3,3),dtype=int);np.add.at(cm,(y,pred),1)
f1=2*np.diag(cm)/(cm.sum(0)+cm.sum(1))
hashes={}
for rel in ['ml/outputs/vision/mobilenetv3_large_vision.onnx','ml/outputs/vision/mobilenetv3_large_vision.pt','ml/outputs/telemetry/xgb_telemetry.json']:
 hashes[rel]=hashlib.sha256((root/rel).read_bytes()).hexdigest()
for rel in ['vision/vision_metadata_with_split.csv','telemetry/telemetry_train.csv','telemetry/telemetry_val.csv','telemetry/telemetry_test.csv']:
 hashes[rel]=hashlib.sha256((data/rel).read_bytes()).hexdigest()
print(json.dumps({'executed_utc':datetime.now(timezone.utc).isoformat(),'xgboost_version':xgb.__version__,'samples':len(df),'best_iteration':best,'probability_sums_valid':bool(np.allclose(probs.sum(1),1,atol=1e-5)),'accuracy':float((y==pred).mean()),'macro_f1':float(f1.mean()),'confusion_matrix':cm.tolist(),'hashes':hashes},indent=2))
PY
```

### 8.3 R-SPLITS的重构定义

只读加载D/`Driver_Behavior.csv`，dropna(behavior_label)、drop_duplicates、reset_index；按`telemetry_feature_order.csv`取八特征。两次`train_test_split`：test_size=.3/seed42/stratify=y，再test_size=.5/seed42/stratify=temp.behavior_label；各split的orderedfeatures+behavior_label与保存CSV逐元素比对，三组均true。Vision排序unique driver IDs后相同.3/.5 seed42划分，对照metadata的driver集合，三组均true。global_median!=train_median计数8，原特征missing cells0。本轮只是重构和诊断，未生成新split文件。

### 8.4 审查交付边界

最终保护性核对以本轮最新M/S快照为基准：M的242个、S的249个既有文件SHA256均不变；首审文件、应用/训练/测试内容未被本审查改写；git status仅新增本文。114个源码链接均存在且行号有效，矩阵32行均具完整9列。完整suite未复跑、当前browser未执行、UAT/E1完整实验未完成的状态均保留。**审查文档完成不等于FYP系统、模型工作或Week7验收完成。**

