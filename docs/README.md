# 文档索引

更新：2026-10-13。按「现在该看哪份」分类。标为**历史快照**的文件保留原样，不再更新；它们被审计包按路径和哈希引用，所以不移动、不改名。

## 现行（以这些为准）

| 文件 | 用途 |
|---|---|
| `docs/plans/2026-10-12-fyp2-live-system-completion.md` | 系统轨道的权威实施计划（Task 1–10、10A；修订 R1–R4） |
| `.planning/system-track/task_plan.md` | 系统轨道 roadmap：阶段、顺序、状态、待决事项 |
| `docs/fyp2/implementation/` | 每个 task 的技术报告（`task-NN.md`）与中文验收报告（`task-NN-acceptance.zh.md`）；`TASK_1_TO_6_SUMMARY.md` 是 `564d0b1` 时刻的快照 |
| `docs/fyp2/release/RELEASE_MANIFEST.md` | 基线冻结清单（模型哈希、split 哈希、依赖版本） |
| `docs/fyp2/review/` | 给 Codex 的提示词，以及 Codex 的独立审阅报告 |
| `docs/LIVE_RUNTIME_GUIDE.zh.md` | 启动与操作说明（内容停在 2026-10-09，Task 9 / 10 时更新） |
| `docs/explanation-implementation-guide.zh.md` | 解释模块的设计说明（注意审阅 R14：`DominantEvidence` 语义待定） |
| `backend/README.md` | 后端运行与测试 |
| `README.md`、`CLAUDE.md`、`PROJECT_MEMORY.md` | 项目入口、Claude 工作约定、设计记忆 |

## 审计包（冻结证据，不修改）

| 文件 | 说明 |
|---|---|
| `docs/fyp2/00`–`08_*.md`、`audit_manifest.json` | 首轮审计（2026-10-09/10）；其中的系统实现状态已过期，以 Codex 独立审阅为准 |
| `docs/fyp2/evidence/` | 首轮审计的原始日志与诊断 |
| `docs/fyp2/{task_plan,findings,progress}.md` | 首轮审计员的工作笔记，不是系统轨道的计划 |

## 报告证据

| 文件 | 说明 |
|---|---|
| `docs/evidence/<date>/` | 按日期归档的门禁、浏览器与实验证据（Chapter 5） |
| `docs/evidence/README.md` | Chapter 5 证据索引 |

## 历史快照（已被取代，仅供追溯）

| 文件 | 被什么取代 |
|---|---|
| `docs/DEVELOPMENT_SCHEDULE.md` | 实施计划 + roadmap |
| `docs/IMPLEMENTATION_PROGRESS.zh.md` | roadmap 的 progress |
| `docs/CLAUDE_HANDOFF_PROMPT.zh.md`、`docs/FYP2_CLAUDE_DEVELOPMENT_HANDBOOK.zh.md` | 实施计划 + roadmap |
| `docs/PROJECT_ASSESSMENT_AND_TEST_PLAN.zh.md` | 审计 03 / 04 与 Codex 独立审阅（E1–E5 命名以审计为准） |

## 待用户确认是否删除

`Changelog.md`、`backend/COMPLETION_PLAN.md`、`docs/prototype-summary.md`、`docs/system-explanation-script.zh.md`、`docs/figma-wireframe-fit-analysis.md`：没有任何文档引用它们，内容已被取代。确认前保留。
