# Task 10A Stage 3（Runtime Evaluation）：实现方自审表

- **实现方**：Claude（CL-3，集成会话）。**日期**：2026-10-29。
- **代码提交**：`fe5c41d`。perf01/perf02 加 `--active-vision`，启动后核对 `/api/models` 报告的视觉模型；不一致就中止，不会把结果标错。改动只在 4 个文件：`scripts/perf01.py`、`scripts/perf02.py`、`backend/tests/e2e_support.py`、`backend/tests/test_perf_scripts.py`。没有改 `backend/app/`，默认视觉模型仍是 stable。
- **证据**：`docs/evidence/2026-10-29/perf-stage3/`（总览见 `README.md`），`docs/evidence/2026-10-29/stage3-gate/`。
- **规格措辞更正（C-6 / U-2）**：规格写「延迟 JSON 与 perf02 同构」；在本仓库，延迟由 `perf01.py`（capture→render）测量，日志完整性由 `perf02.py`（D1/D2）测量。所以延迟 JSON 与 `docs/evidence/2026-10-22/perf/perf01.json` 同构，完整性 JSON 与 `perf02.json` 同构，两者只多了 `active_vision` 与模型身份字段。

## 1. 规格 Stage 3 的审计点

| 审计点 | 证据 | 结果 |
|---|---|---|
| 延迟 JSON 当日生成，含 MN 与 RN 两条 | `perf-stage3/{stable,rn,stable-r2,rn-r2,stable-r3,rn-r3}/perf01.json`，`generated_utc` 都是 2026-10-29；每个文件的 `vision_model` 都写明 model_id 与 sha256：stable `b3a42e8d…`，RN `5e226722…`。字段与 10-22 的 perf01.json 相同，只多 `active_vision`、`vision_model` | 满足 |
| RN 场景下 p95 有实测值 | RN capture→render p95 三轮实测 **123 / 75 / 77 ms**（中位数 61 / 50 / 50）；同一时段 stable p95 92 / 56 / 46（中位数 41 / 27 / 28）。没有使用外推值。全部满足 p95 < 1 s | 满足（见下方负载说明） |
| 全量测试当日重跑 | `stage3-gate/`，`fe5c41d`：GREEN，pytest **1355 passed / 0 skipped / 8 deselected**（`DRA_REQUIRE_MODELS=1`），vitest **1022**，build、tsc、eslint 都 exit 0；附 `freeze_manifest.txt`。唯一的 pytest warning 是已有的 Starlette/httpx 弃用提示，与 `runner-fix-gate` 相同 | 满足 |
| 健康检查 | 每次运行的 uvicorn 日志都已归档（`<run>/server-perf0N/`），服务以 `log_level="warning"` 运行，**10 个日志全部 0 字节**；控制台错误数都是 0。DB 权威性与幂等测试在 pytest 全量中通过 | 满足 |

## 2. 计划 Phase 3 的其他要求

| 要求 | 证据 | 结果 |
|---|---|---|
| 日志完整性（RN 在役） | `rn/perf02.json`：D1 210/210，D2 210/210，入库 209，1 个 `input_validation` 故障，0 重复；perf02 在重启前后都核对过模型身份（`vision_models` 两条一致）。stable 对照 `stable/perf02.json` 结果相同 | 满足。分母 210 而基线 211，原因说明见 README §2 |
| 两个模型分别运行，使用临时库 | 每次运行都是新的临时目录和临时 SQLite，服务在随机空闲端口（`e2e_support.start_server`）；没有碰 8000 端口与 `driver_risk.db*` | 满足 |
| 引用参考数字时注明出处 | 10-22 系统基线 `docs/evidence/2026-10-22/perf/perf01.json`：stable 中位数 28、p95 39。纯模型推理按 p4b `runtime_benchmark/*_round*.json` 计算：RN-HPO42 p95 25.42 ms，MN-HPO42（MN 候选）p95 7.25 ms，范围只是 ORT session.run | 满足 |

## 3. 需要说明的情况

1. **机器负载高**：本日 load average 在 10 到 56 之间（8 核），主要是 iCloud 同步与桌面应用。所以本日 stable 的 p95（46–92 ms）比 10-22 的 39 ms 高。MN 与 RN 的比较按**同一轮**看：RN 的中位数每轮比 stable 高 20–23 ms，与纯模型推理的差值（约 18 ms，再加上负载）一致。**报告 Table 23 目前引用的是 10-22 的 stable 数字**；如果 Stage 5 决定启用 RN，Table 23 是否要换成 RN 的数字、在什么负载条件下重测，需要用户决定（FUD-S3-1）。
2. **作废的运行**：第一次的第 2/3 轮因为一个后台任务被重复启动，出现了两套 perf01 并发运行。这些结果已经删除，没有用于任何结论；现在的 r2/r3 是之后单独重跑的，`load_log.txt` 记录了每次运行前后的负载和对应的服务器目录。第 1 轮（stable、rn 的 perf01/perf02）在并发发生之前已经结束，不受影响。
3. **范围**：本阶段没有训练、HPO、导出或基准测试；没有改 XGB 路径，也没有改默认模型；候选包与 demo bundles 都没有提交；没有 push。

## 4. 待用户决定

- **FUD-S3-1**：如果 RN 成为在役模型，报告 Table 23 的端到端数字要不要换成 RN 的实测值（需要在安静的机器上重测），还是保留 stable 的数字并注明在役模型？

## 5. R-1 关闭（2026-10-30，针对 CX-A3 的 PARTIAL）

| 审计点 | 证据 | 结果 |
|---|---|---|
| 分位数可由原始样本独立复算（R-1） | `1cd5660`：perf01 另写 `perf01_timings.json`（预热后的被测窗口），并在 `perf01.json` 中记录其 sha256 与分位数规则；先红后绿的测试 `test_perf01_writes_the_measured_windows_raw_timings_and_they_reproduce_the_quantiles` | 待审计 |
| 同日 MN 与 RN 实测（安静机器） | `docs/evidence/2026-10-30/stage3-raw/`：stable / RN 交替各 3 轮，每轮 600 窗口、约 9.78 Hz；capture→render p95：stable 31 / 31 / 31 ms，RN 45 / 44 / 43 ms；服务端视觉中位数 stable 约 9.6 ms，RN 约 26.6 ms；load 2.3–4.1；全部 exit 0、0 个控制台错误 | 待审计 |
| 原始文件与汇总一致 | 实现者自查：六份 `perf01_timings.json` 的 sha256 都等于 `raw_timings.sha256`，复算结果与 `stages.capture_to_render_ms` 完全相同 | 待审计（审计者独立复算） |
| 当日全量门禁 | `docs/evidence/2026-10-30/review-followups-coldstart-9255c83/`（全新克隆，pytest 1359 / 0 skipped / 8 deselected、vitest 1061）；`1cd5660` 只改了 `scripts/perf01.py` 与其测试（`test_perf_scripts.py` 29 passed） | 待审计 |

说明：10-29 的六次运行保留原样（只有汇总，标为历史）；Stage 5 的决定引用 10-30 的这六次。FUD-S3-3（已删除的作废运行）不影响 10-30 的结果。

## 6. 独立审计结果与处理（2026-10-30）

审计报告：`docs/fyp2/task10a/stage3_r1_stage5_audit.md`（新鲜只读子代理的原文）。Stage 3 判 **PARTIAL**：技术核查全部通过（6/6 复算一致、RED/GREEN 复现、非 e2e 回归 1310 passed），未给 VERIFIED_PASS 的原因只有两条：

- O-1：R-1 原措辞（复算 10-29 历史六次）做不到，改为 10-30 重测是否算关闭，需用户接受（FUD-1）。
- O-5：日志归档缺口 → 已补：`stage3-raw/focused-test-GREEN.log`、`focused-test-RED-e07ef42.log`、`recompute_raw.py` + `recompute.log`；perf01 服务器日志无法恢复，已在 README 说明。
- O-7：测试数据过于恒定 → 已加强（逐窗口时长不同、预热窗口时长在范围外），变异「原始文件写成恒定时长」使其变红。
- O-6：提交曾落在 `fyp2/dmd-adaptation`（另一会话 10-29 19:29 切换了共用工作区）→ 用户选择快进：`fyp2/live-system` 已快进到 `637a0ff`，之后在独立工作区 `/Users/liu/Desktop/FYP2-Live-System-Integration` 提交。

## 7. 用户决定（2026-10-30，对话中）

- **FUD-1：接受。** 10-29 历史六次的原始样本已不存在，R-1 以 10-30 的同日重测关闭（stable / RN 交替各 3 轮，原始时序与 sha256 绑定，审计者已独立复算一致）。10-29 的汇总文件保留为历史记录，不再作为 Stage 3 / Stage 5 的依据。
- **FUD-5：确认。** 在 Stage 3 获得 VERIFIED_PASS 之前开始 Stage 5，是用户的指令（「start the stage 5, select the final model」）。
- 实现方提出的默认处理，用户未提出异议：FUD-3（10-29 已删除的作废运行）按实现方说明处理，不影响 10-30 的数字；FUD-7 日志已补归档（不可恢复的 perf01 服务器日志已说明）；FUD-8 之后的 UI 提交已各自复审并通过全新克隆门禁，不另行审查。
