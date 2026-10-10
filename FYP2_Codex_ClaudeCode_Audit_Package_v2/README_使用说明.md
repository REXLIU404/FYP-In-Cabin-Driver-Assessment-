# 如何把 FYP2 审计交给 Codex 和 Claude Code

**现在要做的是审计，不是让两个 AI 直接大改项目。** 以下文件是基于你的 FYP1 Report、FYP2 Rubric 和讨论中确认的实验设计创建的**规范和 Prompt**；**尚未访问你的真实项目仓库，不能代表项目已经通过测试。**

## 包内文件

| File | 用途 |
|---|---|
| `FYP2_MASTER_REPOSITORY_AUDIT_PROMPT.md` | **主 Prompt**；进入真实 repo 后，给第一个 Agent 完整执行，分析当前模块、测试、E1–E5 合理性、Week 7 风险，写 `docs/fyp2/` |
| `FYP2_EVALUATION_AND_TESTCASE_SPEC.md` | **完整评价定义**；给 Agent 对照的测试协议、可量化标准、禁忌结论和数据有效性检查 |
| `FYP2_CROSS_REVIEW_PROMPT.md` | **第二个 Agent 的独立复核 Prompt**；挑战第一轮的 PASS/VERIFIED 和方法学弱点 |
| `FYP2_DEVELOPMENT_AND_REPORT_MAP.md` | **Week 1–7 开发计划 + Chapter 4–7 Report Mapping**，按学校 Rubric 定义证据 |

## 推荐操作步骤

1. 打开你真实项目 Repo 的 Codex（也可以 Claude Code 先做）。将 `FYP2_EVALUATION_AND_TESTCASE_SPEC.md` 和 `FYP2_DEVELOPMENT_AND_REPORT_MAP.md` 放在 repo 根目录的临时资料区，或直接作为 Agent 上下文上传；然后完整粘贴 `FYP2_MASTER_REPOSITORY_AUDIT_PROMPT.md`。若没有办法写入这些参考文件，请直接在聊天上下文中提供这两份文件内容。
2. 让第一个 Agent **只读分析 + 安全地执行现有轻量测试 + 生成 `docs/fyp2/` 审计文档**。审计期间不要主动让其训练模型、改生产代码或下载大数据。
3. 核对第一轮 `docs/fyp2/00...08...` 输出。凡是 `TEST_PASSED` 必须有实际命令/输出/代码位置；`FYP1_REPORTED` 只是历史数字。
4. 打开第二个 Agent（建议在**独立 worktree** 或第一轮审计完成后顺序进行），让它读取 **同一个 Git commit 及第一轮文件**，完整粘贴 `FYP2_CROSS_REVIEW_PROMPT.md`。第二轮只应输出 `docs/fyp2/09_INDEPENDENT_AUDIT_REVIEW.md`，不可覆盖第一轮。
5. 将 `docs/fyp2/00_AUDIT_EXECUTIVE_SUMMARY.md`, `02_TEST_CASE_INVENTORY_AND_CRITIQUE.md`, `03_EVALUATION_COVERAGE_MATRIX.md`, `06_WEEK7_CRITICAL_PATH_AND_ACTION_PLAN.md`, `09_INDEPENDENT_AUDIT_REVIEW.md` 带回 ChatGPT，我们再把计划改成**基于真实代码证据**的 Week-by-Week Tasks。

## 避免冲突的方式

同一个工作目录让两个 Agent 并行写文档可能互相覆盖或读取半成品。**最简单的做法是 Codex 先审计，再由 Claude Code 复核；或反过来。** 如果一定要并行，请使用不同的 Git worktree 或输出路径。第二轮复核必须明确第一轮的 commit 是否与目前仓库一致。

## 本轮最重要的判断门槛

- 是否能从 **真实训练模型的输入**一路走到 Dashboard 和 SQLite，而非 prepared probabilities？
- E1–E5 所有评价能否被复现？**可测的代码行为**与**需要真实标签的科学结论**有没有混淆？
- 既有 `pytest`/其他测试是否覆盖完整系统、边界和 error handling？有没有真正运行证据？
- Week 7 的最大风险来自模型推理集成、评估方法还是系统可靠性？
- Report Chapter 4–7 哪一项已经有实证，哪一项仍是 PLANNED？

> 你可以对 Agent 额外强调一句：**“Do not implement fixes yet. First produce the evidence-based audit and critique the test design; I will approve the implementation plan afterwards.”**
