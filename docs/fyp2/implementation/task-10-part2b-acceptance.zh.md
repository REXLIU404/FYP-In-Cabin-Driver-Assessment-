# Task 10 第 2b 部分验收报告（中文）：单分支系统测试、默认摄像头对账、G-W4-A 证据归档

## 1. 任务概要

- **编号与名称**：Task 10 第 2b 部分，Task 10 的最后一部分。
- **实现了什么**：新文件 `backend/tests/test_live_single_branch.py`，四个单分支系统测试类，共 18 条，全部在真实浏览器、真实模型、真实后端上运行。

  - **ST-BRANCH-T-SMOKE（只有遥测，冒烟）**：
    - 开始监测后点 Stop Camera；
    - 之后每个窗口的分数 = `round_half_up(100 × P_t, 1)`；
    - P_t 与冻结 fixture 中该回放行的值完全相等。fixture 与 XGBoost 的哈希 `9802cb06` 绑定，测试先比对哈希。

  - **ST-BRANCH-T-CONTINUITY（只有遥测，整轮）**：
    - **视觉从第一个请求起就没有**：浏览器拒绝摄像头权限，`getUserMedia` 失败，循环按 R5 继续只发遥测，没有拦截任何请求。
    - **运行长度**：跑完一整轮 25 行再回绕，约 56 s，超过 510 个窗口。
    - **断言内容**：
      - 窗口不缺、不重、不停，序号不跳；
      - 第 13、16 行的窗口为 UNAVAILABLE，下一行恢复；
      - **R10 告警序列**按字面量逐窗口核对；
      - 页面只保留最新 500 个窗口，两种导出都覆盖整个会话（控制者新增）。

  - **ST-BRANCH-V（只有视觉）**：
    - 用 Playwright 改写请求，去掉遥测，**连同 `telemetry_seq` 一起去掉**，否则会触发 422；
    - 用 5 fps 假摄像头，让 REPEAT 出现，并在中途 Stop / Start Camera 一次；
    - 端到端检验 NEW-only EMA：REPEAT 不推进平滑链，重启后的第一帧重新播种。

  - **ST-BRANCH-ZERO（反向）**：
    - 在配置页把视觉权重设为 1.00、遥测权重设为 0.00；
    - 所有没有图像的窗口一律 UNAVAILABLE，绝不出现 `100 × P_t`。这正是 Tasks 2–4 修过的零有效权重边界。

  - **2a 转入**：在默认 20 fps 摄像头的 E3 运行末尾加了五方对账。此时每帧都是 NEW，正好覆盖了 2a 没测到的情形。

  - **G-W4-A 证据**：归档在 `docs/evidence/2026-10-20/live-e2e/`。另新建 `prototype-tests/live_e2e.md`，把人工验收清单逐条对应到自动化测试，并写明哪些仍需人工完成。

- **为什么必要**：
  - 单分支运行是系统本来就要支持的降级路径（R5）。
  - G-W4-A 要求单分支行为正确，并且有归档证据。
  - 计划 DoD 第 10 行的 R5 追加部分，就是这四个测试。

## 2. 实现证据

- **Commit**：
  - `ae1c197`：测试、fixture、`live_e2e.md`、报告；
  - `c2191c0`：第一次证据归档；
  - `87bdc3f`：控制者修正；
  - `eb000bc`：在最终代码上重新生成 G-W4-A 门禁日志。
- **两次派发**：第一次派发的实现者在会话限额处中断，没有提交。草稿完整备份在 SDD 目录 `task-10-part2b-partial-run1/`。第二次派发时，实现者逐条核对草稿后接着完成。评审确认，对 2a 文件的改动与备份补丁逐行相同。
- **文件**：
  - 新增：`test_live_single_branch.py`、`fixtures/telemetry_pt_by_row.json`，以及生成脚本 `fixtures/make_telemetry_pt_fixture.py`。脚本只读模型，带 `--check --cross-check-provider` 模式，用来核对 fixture 与产品推理逐位一致；
  - 修改：`e2e_support.py`（挪入 2a 的辅助代码、给 E3 加对账、加证据输出）、`test_live_e2e.py`、`conftest.py`；
  - 新增 `prototype-tests/live_e2e.md`。
- **产品代码一行没改。**
- **告警序列的独立推导**：控制者先用冻结模型离线算出每行的分数，手推出告警序列表，写进 brief；实现者和评审又各自独立推导了一遍，三方一致：

  | seq | 告警状态 | 原因 |
  |---|---|---|
  | 0 | NORMAL | 第 0 行是 Low |
  | 1 | 全部 CAUTION | High 段从这里开始 |
  | 2 | 若干 CAUTION 之后转为 HIGH_ALERT，至少一个 HIGH_ALERT | 来源跨度恰为 2000 ms |
  | 3 起 | 一直 HIGH_ALERT | 第 21–25 行的 Low 段跨度只有 8000 ms，小于恢复所需的 10000 ms，锁存不解除 |
  | 13、16 | null | 窗口不可用，锁存保留 |

  实现者还用真实的 `run_inference` 扫了 96 种循环节奏，在 62 种里，seq 2 的第一个窗口就已是 HIGH_ALERT。所以测试同时允许「seq 2 里没有 CAUTION」和「有 CAUTION」两种情况，不写死。

## 3. 测试结果

| 门禁 | 结果（`87bdc3f`，`run_gates.py` + `DRA_REQUIRE_MODELS=1`，日志在 `docs/evidence/2026-10-20/live-e2e/`） |
|---|---|
| build | 通过 |
| pytest | **952 passed / 0 failed / 0 skipped**（934 → 952，新增 18 条全部是单分支测试：3 + 6 + 5 + 4） |
| vitest | 870 passed，29 个文件（未改前端） |
| tsc / eslint | 0 / 0 |
| 模型 SHA256 | `freeze_manifest.txt` 中三个都 MATCH |

**耗时**：
- 新文件单独运行约 90 s，其中 T-CONTINUITY 约 56 s；
- 全量 pytest 从 2a 的约 61 s 增加到约 134 s。

**变异检验**：brief 要求的 B-M1 到 B-M10，实现者和评审都在隔离副本里跑过，每项都有明确变红的测试：

| # | 变异 | 变红的测试 |
|---|---|---|
| B-M1 | 分母用 `w_v + w_t`，不用有效权重 | T-SMOKE：「RiskScore 33.8 ≠ 67.7」 |
| B-M2 | P_t 取错类别 | T-SMOKE：fixture 不等 |
| B-M3 | 不可用窗口沿用上一次的 severity | 字面写法被产品的 D01 校验器拦下（HTTP 500），所以另加 B-M3b（锁存丢失），只让 T-CONTINUITY 的告警断言变红 |
| B-M4 | 两个连续 High 窗口就升级 | 只有 T-CONTINUITY：「seq 1 出现 HIGH_ALERT」 |
| B-M5 | 游标行号用 `seq % 24` | T-CONTINUITY：反查的行号与 seq 不一致 |
| B-M6 | EMA 在 REPEAT 上也推进 | 只有 V |
| B-M7 | 不可用窗口之后不重新播种 | 只有 V |
| B-M8 | 零有效权重时仍然打分 | 只有 ZERO |
| B-M9 | DominantEvidence 先判 Low、后判 Partial | T-CONTINUITY 等 |
| B-M10 | 导出 CSV 删掉 `request_id` 列 | E3 的对账 |

此外：
- 实现者另加一项变异：篡改 fixture 记录的哈希，测试会提示「fixture 与模型不匹配」；
- 评审另加 B-M10b，删掉另一列，也变红。

**控制者修正**（`87bdc3f`）：评审有两条被标为阻塞本项的 Minor，工作流不会自动修，由控制者处理。另外修了一条不阻塞的。

| # | 问题 | 修正 | 验证（隔离副本） |
|---|---|---|---|
| C1 | ZERO 只检查停止之后的无图窗口，而 brief 写的是「任何窗口」 | 范围扩到会话中所有无图窗口，包括启动阶段 not_ready 的窗口；有图窗口由 test_03 的 `== 100·P_d` 精确约束 | 评审的探针显示目前这类启动窗口为 0 个，这是字面覆盖上的补全 |
| C2 | 人工清单第 3、6 步要求「超过 500 个窗口」，但没有断言，也没列为人工 | T-CONTINUITY 一直跑到超过 510 个窗口；新增 test_06：Signal Inspector 正好列出最新的 500 个窗口，两种导出覆盖 1..N | 页面保留条数改成 400：test_06 变红；导出截断到 500：test_05 与 test_06 变红 |
| C3 | 导出缺列时，对账辅助函数抛 `KeyError`，信息不可读 | 改为报告可读的「缺列」差异 | CSV 删掉 `request_id`：E3 变红，信息是「column 'request_id' is missing from the export」 |

C2 的第一个版本是控制者自己写错的：不可用窗口的按钮带一个「Unavailable」标记，导致文字比对失败。改为只比较窗口编号后通过。

修正之后，在 `87bdc3f` 上**重新生成了 G-W4-A 的门禁日志与 freeze manifest**，所以归档对应的是最终代码。第一次归档（在 `ae1c197` 上，pytest 951）保留在 git 历史里。

**存在但未执行的测试**：无。

## 4. 问题与风险

- **失败测试**：无。**非预期回归**：无。**产品缺陷**：本项没有发现。
- **已知限制**（写在测试 docstring 与报告中）：
  - **告警序列依赖算术采集时间**。测试先断言前提：相邻 seq 的时间戳恰好相差 2000 ms。真实传感器的时间戳有抖动时，告警可能晚一个样本（K2）。这个测试不声称能覆盖那种情况。
  - **EMA 的「处理间隔超过有效期就断链」规则，这次没有在线上触发**（`gap_resets = 0`）。在线上证明的只有「不可用窗口之后重新播种」。间隔断链有后端单元测试覆盖；要在端到端里触发，需要暂停后恢复并带新帧，不在本次范围内。
  - **R14 再次出现**：ZERO 在停止之前是双分支窗口，此时 `DominantEvidence` 不看权重，可能把一个权重为 0 的分支标为主导，实测出现过「Low observed risk」。测试有意不断言这些窗口的 DominantEvidence。这个问题等你对 R14 作出裁定。
- **e2e 的代价**：
  - 全量 pytest 现在约 134 s；
  - 需要 npm、Playwright Chromium 和三个模型文件。缺模型时显式跳过，`DRA_REQUIRE_MODELS=1` 时判失败；缺 npm 或浏览器时是硬失败。
- **测的是假摄像头**：没有测真实摄像头、真实光照与人脸、目标硬件上的性能。`live_e2e.md` 的「仍需人工」一节逐条列出了这些。PERF-01 是单独的工作。
- **文档同步**：`prototype-tests/README.md` 中「脚本化端到端尚不存在」的旧说法、证据总索引中 G-W4-A「待做」一行，都已更新。SDD 上下文文件里「裁定 A 未实施」的过时说法也已改正（该文件被 git 忽略）。
- **外观问题**：实现者提交的提交信息里多了一行 Sonnet 署名，与以前的提交情况相同。

## 5. 验收结论

**PASS**

理由：
- 四个单分支系统测试与 2a 转入的对账全部落实。
- 10 项 brief 变异与附加变异全部变红。
- 告警序列由三方独立推导，结果一致。
- 两条阻塞性的 Minor 由控制者修正，并用变异证明有测试守护。
- 在最终代码上重新生成的 G-W4-A 门禁全部通过，0 跳过，模型哈希不变。

**Task 10 全部完成，G-W4-A 关闭。** 按计划这一周原定在 10-30 关闭，提前完成。

## 6. 下一任务就绪度

- **按你的决定**：Task 10 完成后，把 `fyp2/live-system` 推送到远端，不动 `main`。
- **接下来是 W5**：
  - 会话生命周期 ST-SESSION-01；
  - 干净冷启动 ST-COLDSTART-01，包括把 `.venv` 符号链接换成本工作树自己的环境；
  - 导出完善（latest / flag / full），以及选中窗口的修正；
  - Task 10A 的 manifest 交接。
- **W6**：PERF-01 / PERF-02（含遥测年龄 0–2000 ms 的说明、2 / 3 / 5 s 敏感性）、E2–E5 runner、ST-LONG-01。
- **待你裁定**：R14，即 `DominantEvidence` 按原始强度还是按加权贡献判定。
