# Codex 审阅任务：FYP2 Live-Only System，Tasks 1–6 与实施计划

你是独立审阅者兼决策者。Claude 负责实现，你负责审阅，并对未决事项做出裁定。
用中文写结论；代码标识符、文件路径、字段名、测试 ID 保持原文。

## 0. 你在哪里，以及为什么不需要切换分支

你的项目文件夹是 `/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1`。**本任务不要切换分支，也不要 checkout 任何东西。**

要审阅的代码在分支 `fyp2/live-system` 上，但这个分支正被 Claude 的另一个文件夹（`/Users/liu/Desktop/FYP2-Live-System`）占用，git 不允许在你的项目里检出它。你也不需要检出：所有 commit 都在同一个 `.git` 里，直接按 SHA 读即可。

- **审阅范围固定为 `845b43a..564d0b1`**，即 Tasks 1–6 的 8 个 commit。Claude 之后会继续往这个分支提交，按 SHA 读就不会受影响。
- 读文件：`git show 564d0b1:<path>`
- 看改动：`git diff 845b43a 564d0b1 -- <path>`、`git log --oneline 845b43a..564d0b1`

**不要直接读工作区里的源码文件。** 你的工作区停在 `dev_cc` 或别的分支上，内容不是 Tasks 1–6 之后的代码。

## 1. 硬性规则

- **只读。** 唯一允许新建的文件是你的审阅报告：项目根目录下的 `CODEX_REVIEW_TASKS_1_6.md`，见第 7 节。它已在 git 排除列表里，不会被提交。
- 不要修改任何已有文件；不要 commit、push、merge、rebase、reset、stash、checkout、switch；不要 `git worktree add`。
- **不要写入 `/Users/liu/Desktop/FYP2-Live-System` 里的任何东西。** 那是 Claude 正在工作的文件夹。
- **不要写 `ml/outputs/` 下的任何文件。** Claude 的开发文件夹通过符号链接实时使用这里的三个模型文件。
- 不要训练、调参或修改模型。ML 训练是另一个独立任务。

## 2. 门禁复现（建议做）

Claude 报告的结果是：pytest 504/0、vitest 394/0、tsc 0。请独立复现，不要采信。

因为不能 checkout，请把 `564d0b1` **导出到一个临时目录**再跑。这只是一份文件快照，不是工作树，git 里不会留下任何登记：

```bash
R=/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1
T=$(mktemp -d)
git -C "$R" archive 564d0b1 | tar -x -C "$T"
# 模型、虚拟环境、node_modules 被 git 忽略，不在快照里；以符号链接接入，只读
for f in vision/mobilenetv3_large_vision.onnx vision/mobilenetv3_large_vision.pt telemetry/xgb_telemetry.json; do
  ln -sfn "$R/ml/outputs/$f" "$T/ml/outputs/$f"; done
ln -sfn "$R/.venv" "$T/.venv"; ln -sfn "$R/node_modules" "$T/node_modules"
cd "$T"
export TMPDIR=$(mktemp -d)      # backend/tests/test_api.py 会在收集阶段销毁一个固定路径的临时库
(cd backend && PYTHONPATH=. ../.venv/bin/python -m pytest tests -q -p no:cacheprovider)
./node_modules/.bin/vitest run --no-cache     # 必须带 --no-cache，否则会经符号链接写入主仓库
./node_modules/.bin/tsc --noEmit
./node_modules/.bin/eslint .
```

本机的 `npx` 会被一个 `rtk` 包装器改写，请直接调用 `./node_modules/.bin/` 下的二进制。
如果你的沙箱不允许写临时目录，跳过这一节，并在报告里写明「未复现」。

## 3. 阅读顺序

1. `git show 564d0b1:docs/fyp2/implementation/TASK_1_TO_6_SUMMARY.md` —— 总结，末尾有「不应对外陈述的说法」清单
2. `git show 564d0b1:docs/plans/2026-10-12-fyp2-live-system-completion.md` —— R1/R2 修订后的 10 任务计划
3. **SDD ledger**：`/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/.superpowers/sdd/2026-10-12-fyp2-live-system-completion/progress.md`。记录了全部裁定（搜索 `Ruling`）、延后的 Minor、任务间的移交项。它是项目里一个被 git 忽略的文件，内容是与 `564d0b1` 同一时刻的快照，不随分支切换而变化，直接读它
4. `git show 564d0b1:docs/fyp2/implementation/task-0N.md`（技术报告）与 `task-0N-acceptance.zh.md`（验收报告），N = 1..6
5. 规格来源：`docs/fyp2/00`–`08` 审计文档

## 4. 需要你做出的决定

对每一项给出：**决定**（接受 / 推翻 / 修改）、**理由**、**证据**（file:line）、**把握程度**（高 / 中 / 低）。

### D-A 逐条裁定 Claude 代为做出的决定

至少覆盖以下 7 条。ledger 里其余的 `Ruling` 也请过一遍。

1. 三份融合实现统一为 `ROUND_HALF_UP`（score 保留 1 位、EMA 保留 3 位）。代价：相对旧 Python 改变 17.0% 的分数，相对旧 TS 改变 13.0%，556 个网格点的 RiskLevel 发生改变。
2. EMA 以 Python 语义为准：首帧不 round；stale/missing 之后重新 seed、不做 EMA。直接后果：回放窗口 W16、W18 由 Medium 变为 High。
3. Alert FSM 在无评估窗口期间**挂起**而不是冻结，挂起条件绑定 `level is None`；恢复时把 `high_since` / `low_since` 重新锚定到当前时刻。
4. 不变式比原计划更严：`assessment_available` 为 true 时，四个风险字段必须全部非 null。
5. 迁移把历史上 `system_health='UNAVAILABLE'` 行里的 `0 / Low / NORMAL` 置为 null。**这是不可逆的历史数据改写。**
6. 不引入 jsdom / `@testing-library`，组件渲染断言推迟到 Task 10 用 Playwright 做。
7. Task 4 由控制者代为提交（实现 agent 写完代码后被速率限制终止）。

### D-B 给 F1–F6 排优先级

总结第 6 节列出的六项发现，逐项判定：**Task 7 开工前必须修 / Week 7 签收前必须修 / 作为已知限制接受**。
Claude 的提议是：F2、F4 作为 Task 7 的前置条件，F1 作为写报告的前置条件。请确认或推翻。

### D-C D13：过期证据可以无限累积告警时长

现在就实现 Maximum Evidence Age / Stale-Only Alert Guard，还是保留为已知限制，到 System Freeze 前再决定？
如果主张现在实现，请给出具体的年龄上限和理由。注意：这条路径在 Live 主运行时不可达，只能经回放路径或直接 POST `/windows` 触发。

### D-D 两份 CSV 导出

前端回放导出和后端 Live 导出目前是两个不同的制品，只在 6 个契约单元格上编码一致，表头、列集合、列顺序都不同。
应该统一，还是保持为两个独立制品？

### D-E Tasks 7–10 的计划是否仍然成立

结合 Tasks 1–6 的发现，计划是否需要调整顺序、补充前置条件，或修改 DoD？

### D-F 合并时机

`fyp2/live-system` 现在就合入 `dev_cc`（只含 Tasks 1–6），还是等 Task 10 完成、通过整分支评审之后再合？

## 5. 独立审阅

不要只回答上面的问题。请做一次你自己的审阅，重点放在 Claude 的审阅流程**可能漏掉**的地方：

- 跨层契约是否真的一致：`ai/src/`、`backend/app/fusion.py`、`ai/reference/risk_logic.py`、`backend/app/inference.py` + `schemas.py`、`frontend/src/`
- 迁移在某种真实数据形态下是否可能丢数据
- 有没有测试被削弱，或者期望值被改成迁就实现
- 时序状态在重启、gap、会话切换时是否会泄漏（`runtime_state` 是持久化的 JSON 列）

每条发现标注 Critical / Important / Minor，并给出 file:line 和具体的失败场景。

## 6. 与 ML 任务的关系

同一个项目里还会有一个 ML 训练任务，它会把工作区切到 `fyp2/ml-training` 分支。
只要你始终按 SHA 读 git 对象，这就不影响你：ledger 快照和你的报告都是被忽略的文件，不随分支切换而变化或消失。

## 7. 输出

把完整报告写到项目根目录的这一个文件（只新建这一个文件）：

`/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/CODEX_REVIEW_TASKS_1_6.md`

结构：
1. 总体结论（一段）
2. D-A 至 D-F 的逐项决定（表格）
3. 独立审阅发现，按严重度排序
4. 你复现的门禁数字与命令；没复现就写没复现
5. 你无法验证的事项
