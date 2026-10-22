# W5 系统测试验收报告（中文）：会话生命周期、冷启动、Task 10A schema 交接、E3 网格；G-W5-A 提前关闭

## 1. 任务概要

- **来源**：
  - 用户 10-22 用 `/superpowers:executing-plans` 要求「继续 live system 的 task，完成 system test」；
  - 主计划 Task 1–10 已完成，剩下的系统测试来自冲刺计划 v3 的 W5 / W6 Track A，写成执行计划 `docs/plans/2026-10-22-w5-w6-system-tests.md`（S1–S10）；
  - 用户同日要求以后按覆盖矩阵增补节测试，由此新增 S10。
- **本报告覆盖 W5 部分**：S1–S5，加上 S10。W6 部分（S6–S9）另写报告。

| 项 | 实现了什么 | 为什么必要 |
|---|---|---|
| S1 | Inspector 与 Explanation 的选中窗口**默认跟随最新**；点选后固定；切换会话（新建或加载）后恢复为跟随最新 | 原来运行中一直默认选中窗口 1，加载旧会话时也不是最新窗口。冲刺计划要求「加载已保存会话时默认选中最新窗口」 |
| S2 | **ST-SESSION-01**：用真实浏览器走完整个生命周期，依次是开始、暂停、恢复、新会话、加载已保存会话、加载后再开始、点选固定，对三个会话分别做五方对账 | G-W5-A 的会话生命周期检查项 |
| S3 | **ST-COLDSTART-01**：`scripts/coldstart_check.sh` 依次完成全新克隆、用锁文件建虚拟环境、`npm ci`、链接模型、全量门禁、从干净副本启动服务。README 增加「从零启动」一节。本工作树的 `.venv` 改为本地虚拟环境 | G-W5-A 的「从全新 checkout 干净启动」。原来 `.venv` 是指向主仓库的符号链接，Codex 的环境一变，系统轨道就可能受影响 |
| S4 | Task 10A 候选模型包的 **runtime manifest**：JSON Schema、校验器、命令行工具、交接文档，以及用这个格式描述的稳定模型示例 | 冲刺计划 W5：把 manifest schema 交给 Track B |
| S5 | G-W5-A 证据归档 | 硬性门禁 |
| S10 | **E3 新鲜度 3×3 网格**：视觉和遥测各取 fresh / missing / expired 组合；expired 的分数与 missing 逐字节相同，并保留过期原因 | 覆盖矩阵增补节（2026-10-22），用户要求以后按它测试 |

## 2. 实现证据

| 项 | 提交 | 主要文件 |
|---|---|---|
| S1 | `62f13fb` | `frontend/src/utils/selection.ts`（新）、`App.tsx` |
| S2 | `59f91a7`，评审后补充 `183d38f` | `backend/tests/test_live_session_lifecycle.py`（新） |
| S3 | `fd2a8a5`、`527f12d`，评审后修复 `258e380` | `scripts/coldstart_check.sh`（新）、`README.md`、`docs/evidence/2026-10-22/coldstart/` 与 `coldstart-final/` |
| S4 | `095424f`，评审后修复 `0530b1a` | `backend/app/runtime_manifest.schema.json`、`backend/app/runtime_manifest.py`、`scripts/validate_runtime_manifest.py`、`docs/fyp2/handoff/`（均为新文件） |
| S5 | `6491dd7` | `docs/evidence/2026-10-22/w5-gate/` |
| S10 | `12a0f98` | `backend/tests/test_e3_freshness_grid.py`（新） |

产品代码只改了 S1 的选中逻辑。S4 新增的校验模块目前不被运行时加载，要到 Task 10A 改造 provider 时才接入。

## 3. 测试结果

**G-W5-A 门禁**（`5040e9d`，`run_gates.py` 加 `DRA_REQUIRE_MODELS=1`，在本工作树新的本地虚拟环境里运行）：

| 门禁 | 结果 |
|---|---|
| build | 通过 |
| pytest | **1021 passed，0 skipped**，1 deselected（ST-LONG-01 默认不跑，单独运行过） |
| vitest | 922 passed |
| tsc / eslint | 0 / 0 |
| 模型哈希 | 三个都 MATCH |

**冷启动**（`fd2a8a5` 的全新克隆）：

| 步骤 | 耗时 / 结果 |
|---|---|
| 克隆 | 0 s |
| 建虚拟环境 | 3 s |
| pip 安装锁文件 | 82 s |
| `npm ci` | 3 s |
| 全量门禁 | 268 s：pytest 987 / 0 skipped，vitest 922，全部通过 |
| 启动服务检查 | 3 s：健康检查 200，模型哈希正确，仪表盘 200 |

**变异检验**（都在隔离副本中进行，每项都有明确变红的测试）：

| 项 | 变异 | 变红 |
|---|---|---|
| S2 | 选中项固定为窗口 1 | 2 条 |
| S2 | 加载后点 Start 仍往旧会话写 | 运行停止，8 条全红 |
| S2 | 恢复时遥测游标从 0 重新开始 | 服务端返回 409，8 条全红 |
| S2 | 点选的窗口不固定 | `test_07` |
| S2（评审后补充） | 删掉 App.tsx 中「切换会话时清除固定」的代码 | `test_05`、`test_09` |
| S4 | 去掉 6 条跨字段规则中的任意一条（路径不得逃出包、类别下标顺序、safe 类、输出宽度、符号链接逃逸、哈希） | 每条各有测试变红 |
| S10 | 过期判断不生效 | 10 条 |
| S10 | 过期仍参与计分 | 10 条 |

**新增测试数**：
- vitest：+4（`selection.test.ts`）；
- pytest：+9（ST-SESSION-01，其中 1 条是评审后补的）、+24（manifest，其中 6 条是评审后补的）、+2（`long` 标记）、+14（E3 网格），另有 ST-LONG-01 1 条，默认不跑。
- 最终代码在全新克隆上：pytest 1028 / 0 skipped，vitest 922（`docs/evidence/2026-10-22/coldstart-final/`）。

## 4. 问题与风险

- **裁定：选中窗口跟随最新的范围。** 冲刺计划只写了「加载会话时选中最新窗口」，我把它扩展到运行中也默认跟随最新，用户点选后固定。代价：如果你更喜欢运行中停在窗口 1，只需改初始值。
- **裁定：恢复后第一个 seq 的断言是「大于暂停前的最大值，且不超过它加 2」，不是恰好加 1。** 原因是游标可能在最后一个请求和点击 Pause 之间前进了一格。真正的错误，也就是复用旧 seq，已经由变异证明能被抓到。
- **裁定：冷启动安装锁文件，其中包含 torch。** 有一条测试要拿后端预处理与训练 notebook 的 torch 变换逐像素对比。代价是多装约 1 GB 的训练依赖。
- **已知待决（Task 10A 开工时决定）**：本工作树里的稳定模型文件都是指向主仓库的符号链接，manifest 的「不得逃出包目录」规则会**正确地**拒绝它；指向真实目录时校验通过。交接文档已写明这一点。
- **E3 网格只覆盖 E3 中与新鲜度有关的部分。** 完整的 E2–E5 runner 依赖导师对 D06（构造场景）的决定，不在本轮范围内。
- **应用回退事件**：10-22 下午，应用把本会话的若干文件撤回或删除，全部已从 git 恢复。详见 TELEMETRY-CONTRIBUTIONS 验收报告第 4 节。
- **独立评审之后的修复**：
  - 冷启动脚本会留下没关掉的 uvicorn。已改为在子 shell 里 exec，并在退出时停止；最终代码上重跑后，确认没有残留；
  - 「切换会话后清除固定」原来没有测试守护，现已补上；
  - manifest 校验器原来没有落实交接文档写明的几条规则：provenance 里不得有指标、`run_id` 必须等于包目录名、目录路径要报错而不是崩溃、坏 JSON 要给出提示。现已全部落实；
  - W5 证据 README 里 dirty 的说明不全，已补上未跟踪的 PERF 脚本这一原因。

## 5. 验收结论

**PASS**

理由：
- G-W5-A 的所有检查项都有对应的测试和证据，详见 `docs/evidence/2026-10-22/w5-gate/README.md`；
- 门禁全部通过，0 skipped；
- 冷启动在全新克隆上通过；
- 变异检验都按预期变红。

G-W5-A 原定 11-06 关闭，提前到 10-22。

## 6. 下一任务就绪度

- **W6**（另写报告）：ST-LONG-01、PERF-01、PERF-02、G-W6-A。
- **最后**：整分支独立评审 → 修复 → 在最终代码上跑 G-W6-A 门禁。
- **推送 `fyp2/live-system`**：需要你的同意。
- **Constructed scenario**：回放会话在 `fyp2/constructed-scenario` 上开发，起点是 `bb947f0`，已经确认可用。
