# ML branch Git 归档范围

日期：2026-10-26。目标分支：`fyp2/ml-training`。

本次依用户授权整理、提交并推送 ML 轨道；不合并到 `main`，不修改
`fyp2/live-system`。既有历史报告、实验日期、状态与指标保持原文。

## 本次保留

- E1、P4、P5 的实现、config/protocol、软件测试和历史 source snapshots。
- 完整 vision search 的冻结 selection、validation predictions CSV、指标和运行记录。
- 正式审计、研究报告、P4/P5 metrics、hash/manifest、来源、parity 与闭合检查。
- P5 候选目录的元数据、逐样本预测 CSV、model card 和静态验证证据。
- 本轮软件回归的命令、成功日志及首轮沙箱失败记录。

冻结 predictions CSV 属于可审阅的研究结果；运行数据库、NumPy bank 和
逐样本输入载荷属于本地计算缓存，不随这些结果上传。

## 本地保留、不上传

- SQLite 数据库与 WAL/SHM/journal，包括 P4-B `cache/`。
- `shared_inputs/` 的逐样本 JSON/NumPy 载荷；仅保留小型 `bank_manifest.json`。
- PT、ONNX、joblib 等 weights/checkpoints/序列化 estimator，NumPy 数组与 P5 ZIP。
- worker `process.json`、lock、`budget_state.json` 等本地恢复状态。
- 历史 QC pilot 的输入 PNG 和生成的 `review.html`；历史文本记录仍保留。
- `.codex/`、`.claude/`、本地环境、凭据配置和工具缓存。
- 当前未追踪的根目录 `AGENTS.md`；本轮不重新引入此前已删除的指令文件。

这些文件仅从 Git 归档中排除，不删除或覆盖本地副本。排除项 inventory 见
[git-archive-excluded.json](../../evidence/2026-10-26/ml-push/git-archive-excluded.json)。

Git 中的 P5 目录是元数据与证据归档，不是包含 ONNX 的完整可运行候选包。
历史 manifest、hash 和报告仍描述本地原始完整产物；不能据此声称 clone 后即可
直接加载候选模型、重建所有缓存、重新训练或实现 bitwise reproduction。

## 本轮验证的确切范围

测试对象是 `335da4e` 基线上的提交前 dirty working tree，另记录了 37 份
source/config/test 的 SHA inventory；不是仅测试未包含新增实现的 committed HEAD。

本机 `core.autocrlf=input` 会转换部分 CSV 的 CRLF。`.gitattributes` 对本次
冻结 run 设置 `-text`，使暂存及上传内容保留原始字节；不改写本地证据或历史 manifest。

- 首轮沙箱测试：`296 passed / 6 failed`；6 项均因子进程 RSS 观测权限被阻止。
- 相同测试逻辑和原预算的受控重跑：`302 passed in 25.36s`，exit 0。
- 无实现修复、skip、xfail 或预算扩张。原始失败与通过日志均保留。
- 根目录 ESLint 扫描涉及旧 `.claude/worktrees/`，出现 10 项既有 `prefer-const`
  错误；排除这些嵌套 worktree 后检查 exit 0。没有修改其代码。

命令及证据见 [ML 软件验证摘要](../../evidence/2026-10-26/ml-push/ml-tests-summary.json)。
本轮没有训练、下载、实际模型 forward、正式 export 或 benchmark；没有运行
frontend/backend 的完整集成检查。本次归档不构成该候选包的 Task 10A
provider-load-forward 或后续 Live E2E 验证。

新增提交的文件内容清单见
[git-archive-included.json](../../evidence/2026-10-26/ml-push/git-archive-included.json)。
清单不对自身及其他归档 bookkeeping 文件计算自引用 hash；完整提交身份以 Git 为准。
