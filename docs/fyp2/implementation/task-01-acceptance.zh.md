# Task 1 验收报告（中文）

## 1. 任务概要

- **编号与名称**：Task 1 —— 冻结基线、清理 AGENTS.md 引用、确认工作目录
- **实现了什么**：建立隔离开发工作树并冻结可复现基线。产出 `scripts/freeze_manifest.py`（重新计算模型/数据/依赖指纹）与 `docs/fyp2/release/RELEASE_MANIFEST.md`；删除 `AGENTS.md`；修正 `CLAUDE.md` 中指向该文件的两处悬挂引用；修掉 `eslint.config.js` 的扫描范围缺陷；补齐 Python 依赖声明并生成锁文件。
- **为什么必要**：审计 B05 指出整个 FYP2 运行时当时只以未提交状态存在，模型文件被 git-ignored，无法构成可复现交付。没有基线指纹，后续任何一个 task 都无法证明「模型没被动过」。此外 `eslint .` 会走进嵌套工作树去 lint 陈旧副本并误报，使 lint 门禁失效。
- **行为变化**：无应用行为变化。本任务不触碰 `backend/app/`、`ai/src/`、`frontend/src/` 任何一行。

## 2. 实现证据

- **Commit**：`6553a46` on `fyp2/live-system`（未 push）
- **文件**：删除 `AGENTS.md`；修改 `CLAUDE.md`、`eslint.config.js`、`backend/requirements.txt`、`backend/requirements-inference.txt`；新增 `scripts/freeze_manifest.py`、`backend/requirements.lock.txt`、`docs/fyp2/release/RELEASE_MANIFEST.md`、`docs/plans/2026-10-12-...md`、`docs/fyp2/implementation/task-01.md`
- **关键决定**：
  - 工作树 `/Users/liu/Desktop/FYP2-Live-System`，分支 `fyp2/live-system`，自 `dev_cc@845b43a` 新建；主仓库降为只读。
  - 三个模型 checkpoint 以**符号链接**接入，只读；manifest 独立重算哈希并与基线比对，不是硬编码回显（评审已用伪造仓库做反向验证：哈希不符时 exit 1）。
  - `AGENTS.md` 仅在本分支删除；`dev_cc` 仍跟踪它，等用户自行提交删除。
  - 全仓库无 `.db`/`.sqlite`，**没有开发数据库需要备份**，manifest 如实记录而非虚构备份。

## 3. 测试结果

| 命令 | 结果 |
|---|---|
| `cd backend && PYTHONPATH=. ../.venv/bin/python -m pytest tests -q` | **28 passed** |
| `npx vitest run` | **32 passed**（4 文件） |
| `npx tsc --noEmit` | exit 0，无错误 |
| `npx eslint .` | exit 0 |
| `./.venv/bin/python scripts/freeze_manifest.py` | exit 0，三个模型哈希与基线相符 |

**PASS 60 / FAIL 0 / SKIP 0**（pytest 28 + vitest 32）。模型未跳过 —— 符号链接使 `requires_models` 生效。

**验证核心需求的用例**：`freeze_manifest.py` 的独立重算即核心验收；评审另建伪造仓库注入「哈希不符」与「文件缺失」两种故障，脚本均 exit 1，证明它是真实闸门。

**存在但未执行的测试**：无。

## 4. 问题与风险

- **失败测试**：无。
- **预期的临时兼容性错误**：无（Task 1 不改契约）。
- **非预期回归**：无。
- **遗留 Minor（4 项，已入 ledger 延后处理）**：
  1. `RELEASE_MANIFEST.md:14` 称未写主仓库，但 vitest 经符号链接写了 `node_modules/.vite/vitest/results.json`。**后续一律用 `npx vitest run --no-cache`**。
  2. `freeze_manifest.py` 的 `eda_outputs` 解析：坏的 `FYP_DATA_ROOT` 会静默回退到 sibling repo；NOT FOUND 仍 exit 0；未嵌入 split 基线哈希。
  3. `freeze_manifest.py` 错误处理：git 报错文本会进 HEAD 单元格；未捕获异常与模型不符同为 exit 1。
  4. `requirements.lock.txt` 是共享 `.venv` 的 143 条全量 pin（真实依赖闭包仅 39 个，其余为 torch/jupyterlab 等 ML 工具）。Task 10 若要声称 clean-install 验证，需先改为闭包锁。
- **对后续任务的风险**：低。唯一需要传递的是 `--no-cache` 这条操作约定。

## 5. 验收结论

**PASS**

理由：7 个 Step 全部满足，独立评审逐条核实并自行重跑了全部门禁（未采信实现者的转述）。4 个 Minor 均不影响本任务目标，也不阻塞下游。模型三个 SHA256 与审计基线逐一相符，无应用逻辑改动。

## 6. 下一任务就绪度

- **可以开始 Task 2**。
- **已满足的依赖**：隔离工作树可用；基线四道门禁全绿且有记录；模型基线哈希已锁定；R1/R2 计划与 SDD 上下文已随分支落地。
- **须先解决**：无。
