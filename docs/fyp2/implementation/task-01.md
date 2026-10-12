# Task 1 实现报告 —— 冻结基线、清理 AGENTS.md 引用、确认工作目录

## 1. Task ID and name

- **Task 1**：冻结基线、清理 `AGENTS.md` 悬挂引用、确认工作目录
- 计划：`docs/plans/2026-10-12-fyp2-live-system-completion.md`（本 task 的 commit 一并带入该文件）
- 工作树 `/Users/liu/Desktop/FYP2-Live-System`，分支 `fyp2/live-system`，基线 HEAD `845b43a`
- 本 task **不触碰任何应用逻辑**（`ai/`、`backend/app/`、`frontend/` 零改动）

## 2. Implementation status

**DONE**（另有几条需要控制者知晓的说明，见第 7 节）。

| Step | 内容 | 状态 |
|---|---|---|
| 1 | 核实工作目录（控制者已建好，本 task 只重跑核实命令） | 完成，输出与期望一致 |
| 2 | `AGENTS.md` 删除 + `CLAUDE.md` 悬挂引用清理 | 完成 |
| 3 | `eslint.config.js` 的 `ignores` 修复 | 完成，`npx eslint .` 退出 0 |
| 4 | `scripts/freeze_manifest.py` | 完成，无参数可运行，三个模型哈希独立重算并与基线一致 |
| 5 | Python 依赖声明（注释 + playwright + lock） | 完成 |
| 6 | 跑基线并写入 `docs/fyp2/release/RELEASE_MANIFEST.md` | 完成 |
| 7 | 一次本地 commit（不 push） | 完成，SHA 见控制者收到的返回值 |

## 3. Files created or modified

| 文件 | 动作 | 说明 |
|---|---|---|
| `AGENTS.md` | **删除**（`git rm`） | 见下方「AGENTS.md 处置」 |
| `CLAUDE.md` | 修改（2 处） | 小节标题去掉 `from AGENTS.md`；`Source of truth & docs` 首句改为 ``This file (`CLAUDE.md`) contains the applicable project instructions.`` |
| `eslint.config.js` | 修改（1 行） | `ignores` → `["dist", "node_modules", ".venv", ".claude", ".superpowers"]` |
| `scripts/freeze_manifest.py` | 新建 | 无参数、纯标准库；Markdown 输出到 stdout |
| `docs/fyp2/release/RELEASE_MANIFEST.md` | 新建 | 基线门禁输出 + manifest 嵌入 + 登记项 |
| `backend/requirements.txt` | 修改（仅在顶部加 6 行注释） | 指明 live 运行时必须 `pip install -r requirements-inference.txt` |
| `backend/requirements-inference.txt` | 修改（+2 行） | 加 `playwright>=1.60`（`.venv` 实装 1.60.0） |
| `backend/requirements.lock.txt` | 新建 | `.venv/bin/pip freeze` 快照，143 个 pin + 4 行头部注释 |
| `docs/plans/2026-10-12-fyp2-live-system-completion.md` | 新增入库（原为 untracked） | 按控制者决定随分支走 |
| `docs/fyp2/implementation/task-01.md` | 新建 | 本报告 |

**AGENTS.md 处置（请控制者原样转告用户）**

- `AGENTS.md` 在基线 `845b43a` **是被跟踪文件**，内容仅 1 字节 `;`（`od -c` 确认）。
- 我已按用户的明确决定在 **`fyp2/live-system` 分支上** `git rm AGENTS.md`，并纳入本次 commit。
- **`dev_cc` 仍然跟踪该文件**，直到用户自己提交其在主仓库工作区里的未提交删除。本分支的删除与之互不依赖。
- 历史内容仍可取回：`git show 0113b61:AGENTS.md`。

**未触碰（按用户「文档暂不整改」的决定）**：`PROJECT_MEMORY.md:518`、`docs/FYP2_CLAUDE_DEVELOPMENT_HANDBOOK.zh.md:17`、`docs/IMPLEMENTATION_PROGRESS.zh.md:98`、`ml/experiments/README.md:81` 仍提到 `AGENTS.md`。已登记在 `RELEASE_MANIFEST.md` 第 4 节；另外用 `git grep` 找到 4 处历史证据文件里的时点记录（`docs/evidence/2026-10-09/verification-manifest.json:2`、`docs/fyp2/evidence/audit_commands.md:67`、`docs/fyp2/evidence/repository_discovery.json:471`、`docs/fyp2/evidence/source_inventory.json:6,14`），它们是审计快照，不应改，也一并登记。

## 4. Implementation summary

**Step 1 核实。** 重跑 brief 的两条命令：`git rev-parse --short HEAD` → `845b43a`；`git branch --show-current` → `fyp2/live-system`。另外确认：三个模型文件是符号链接（指向主仓库）并被 git-ignore（`git status --ignored` 显示 `!!`）；`.venv`、`node_modules`、`.superpowers` 同样被忽略。没有创建任何 worktree / 分支。

**Step 2。** 只做了控制者指定的两处 `CLAUDE.md` 编辑（用带 `assert count == 1` 的脚本做精确替换，确认两个原文各恰好出现一次），之后 `CLAUDE.md` 中不再有 `AGENTS` 字样。

**Step 3。** `ignores` 加入 `.claude` 与 `.superpowers`（后者是控制者指定的第 5 个条目）。

**Step 4。** `scripts/freeze_manifest.py`，七个部分：
1. git HEAD、分支、HEAD commit、dirty 状态及逐条未提交项；
2. 三个模型：**独立重算** SHA-256 与字节数，对照脚本内嵌的冻结基线，逐行给出 `MATCH / MISMATCH / MISSING`，附 git-ignored 状态、符号链接目标，并扫描 `ml/outputs/` 下是否有基线之外的 checkpoint 类文件；
3. 数据 split：`eda_outputs/processed/**/*.csv` 的 SHA-256、字节数、数据行数（用 `csv.reader` 数记录，不会被引号内换行误数）；
4. `.venv` 实装版本：在 `.venv/bin/python -I` 里用 `importlib.metadata` 取实装版本，与 `requirements*.txt` 声明的下界做 `packaging` 规范校验，并核对 `requirements.lock.txt` 与 live `.venv` 是否一致（结果 `IN SYNC`）；
5. node / npm 版本、`package-lock.json` 哈希、`package.json` 声明 vs `node_modules` 实装；
6. 全树扫描 `.db/.sqlite/.sqlite3`（结果：无）；
7. 依赖/配置文件哈希。

退出码：三个模型全部 `MATCH` 时为 0，否则 1 —— Task 10 可以直接把它当「模型未变」门禁用。脚本只读，不写仓库、不写数据根目录、不写模型文件。

**一个事实需要说明**：brief 里写的 `eda_outputs/processed/**/*.csv` **在本工作树和主仓库里都不存在**。实际位置是兄弟仓库 `~/Desktop/FYP-In-Cabin-Driver-Assessment-`（末尾无 `1`），这也是 `ml/README.md` 记载的约定（环境变量 `FYP_DATA_ROOT` 可覆盖）。脚本按 `FYP_DATA_ROOT` → 仓库根 → 该兄弟仓库的顺序解析，找不到时输出明确的 NOT FOUND 而不是崩溃。本次找到并记录了 10 个 CSV（telemetry 30000 行，train/val/test = 21000/4500/4500；vision 元数据 22424 行）。

**Step 5。** `requirements.txt` 只加注释，不改依赖列表（brief 要求的是注释）；`playwright>=1.60` 用下界风格，与文件中其他条目一致，精确版本由 lock 固定。已读 `backend/app/providers/trained.py` 核实 `TrainedProvider.__init__` 里确实 import `PIL / numpy / onnxruntime / xgboost`。

**Step 6。** 基线门禁在全部文件改动完成之后才实跑；其原始输出写入 `RELEASE_MANIFEST.md` 第 2 节。第 7 节嵌入的 manifest 是在 commit 前生成的（HEAD 为基线 `845b43a`，working tree 的 10 条 dirty 项恰好是 Task 1 的改动集），仅把标题层级下移一级以便嵌套，其余原样。

## 5. Tests executed (exact commands)

```bash
# Step 1 核实
cd /Users/liu/Desktop/FYP2-Live-System
git rev-parse --short HEAD && git branch --show-current
#   845b43a
#   fyp2/live-system

# 基线门禁（在所有改动完成之后）
export TMPDIR=$(mktemp -d) PYTHONDONTWRITEBYTECODE=1
cd backend && PYTHONPATH=. ../.venv/bin/python -m pytest tests -q -p no:cacheprovider
#   ............................                                             [100%]
#   28 passed, 1 warning in 5.15s            (exit 0)
cd .. && npx vitest run
#   Test Files  4 passed (4)
#        Tests  32 passed (32)               (exit 0)
npx tsc --noEmit                              # 无输出, exit 0
npx eslint .                                  # 无输出, exit 0
npx eslint ai frontend                        # 无输出, exit 0

# manifest 脚本
python3 scripts/freeze_manifest.py            # exit 0；三个模型均 MATCH；"Models unchanged vs frozen baseline: YES"
python3 -m py_compile scripts/freeze_manifest.py   # 通过（随后清掉了 __pycache__）
```

vitest 逐文件：`ai/src/alertFsm.test.ts` 7、`ai/src/riskLogic.test.ts` 16、`frontend/src/utils/persistence.test.ts` 3、`frontend/src/data/preparedSessionInput.test.ts` 6 = 32。

pytest 的 1 个 warning：`fastapi.testclient` 对 `httpx` 的第三方弃用提示（`StarletteDeprecationWarning`），非本项目代码。

三个模型哈希（脚本独立重算，与控制者给的基线逐字比对）：

| 文件 | SHA-256 | 字节 | 结果 |
|---|---|---|---|
| `ml/outputs/vision/mobilenetv3_large_vision.onnx` | `b3a42e8dd4553355b1fd7d9e7fe3d28e318decb894e76eb029489b7ff2e90bcf` | 16849378 | MATCH |
| `ml/outputs/vision/mobilenetv3_large_vision.pt` | `196ca7b151d84e0c4a8eac87128da9dd8f22c894984a991ef611536bb523e7c7` | 17066477 | MATCH |
| `ml/outputs/telemetry/xgb_telemetry.json` | `9802cb06ca98f0c1befaf851fa7668cfec70e005cf8bb3884e49d7d45d7aec07` | 629723 | MATCH |

## 6. PASS / FAIL / SKIP counts

| 套件 | PASS | FAIL | SKIP |
|---|---|---|---|
| pytest（`backend/tests`） | 28 | 0 | 0 |
| vitest | 32 | 0 | 0 |
| `tsc --noEmit` | 0 错误 | — | — |
| `eslint .` | 0 问题 | — | — |
| `eslint ai frontend` | 0 问题 | — | — |
| freeze_manifest 模型哈希 | 3 / 3 MATCH | 0 | 0 |

合计测试用例：**60 passed / 0 failed / 0 skipped**，与控制者预期（28 / 32 / clean / clean）一致。

## 7. Remaining issues

1. **修复前的 lint 误报在本工作树无法复现。** `.claude/` 与 `.superpowers/` 在此处都不含 `.ts/.tsx/.js`，所以用基线 `eslint.config.js`（`git show HEAD:eslint.config.js` 的临时副本，已删除）跑 `eslint .` 同样退出 0。该修复针对主仓库存在 `.claude/worktrees/…` 的场景，属防御性修复；没有「先红后绿」的证据，已在 `RELEASE_MANIFEST.md` 第 5 节如实写明。
2. **`requirements.lock.txt` 是整个共享 `.venv` 的快照**（143 个 pin，含 `torch`、`torchvision`、`scikit-learn`、`jupyterlab` 等 ML 工具链），不是后端闭包的最小锁。我按 brief 字面要求用 `pip freeze` 生成，并在文件头加了 4 行注释说明这一点。若以后要「仅后端」的锁，需另行决定（不属于本 task）。
3. **vitest 写了一个 git-ignored 缓存文件到主仓库**：`node_modules` 是指向主仓库的符号链接，vitest 把结果缓存写到 `node_modules/.vite/vitest/results.json`（我用 `find -newer` 确认它比我创建的脚本更新）。这是 gitignore 范围内的测试缓存，不是源码或模型；除此之外我没有对主仓库做任何写入（`.venv` 只读，`pytest` 加了 `-p no:cacheprovider`，`PYTHONDONTWRITEBYTECODE=1`）。若要求严格零写入，需后续给 vitest 配 `cacheDir`，不在本 task 范围。
4. **数据 split 不在本仓库**，而在兄弟仓库 `~/Desktop/FYP-In-Cabin-Driver-Assessment-`。manifest 记录了该路径与哈希，换机器时必须保证该目录存在或设置 `FYP_DATA_ROOT`，否则 7.3 小节为 NOT FOUND（脚本不会因此失败，退出码只取决于模型哈希）。
5. **`AGENTS.md` 的删除只在 `fyp2/live-system` 上**（见第 3 节）；`dev_cc` 仍跟踪它，直到用户提交自己的删除。
6. 已登记但未处理的陈旧 `AGENTS.md` 引用共 4 处文档 + 4 处历史证据文件（见 `RELEASE_MANIFEST.md` 第 4 节），按用户决定本阶段不整改。
7. **commit 的 Co-Authored-By 行**：控制者指令要求 `Claude Opus 5`，而本会话的 harness 归属提示要求 `Claude Sonnet 5.5`（实际执行本 task 的模型）。我采用了与实际执行模型一致的 `Sonnet 5.5`。如需改成 `Opus 5`，控制者可对该 commit 做一次 `git commit --amend`。
8. 脚本里的冻结基线哈希是内嵌常量。若以后有意重新训练并更新 checkpoint，必须同步改 `MODEL_BASELINE`，否则门禁会（正确地）报 MISMATCH。

## 8. Evidence paths

- `/Users/liu/Desktop/FYP2-Live-System/docs/fyp2/release/RELEASE_MANIFEST.md` —— 基线门禁原始输出 + manifest 输出 + AGENTS.md / 陈旧引用登记
- `/Users/liu/Desktop/FYP2-Live-System/scripts/freeze_manifest.py` —— 可重复运行的 manifest / 模型哈希门禁
- `/Users/liu/Desktop/FYP2-Live-System/backend/requirements.lock.txt`、`requirements.txt`、`requirements-inference.txt`
- `/Users/liu/Desktop/FYP2-Live-System/eslint.config.js`、`/Users/liu/Desktop/FYP2-Live-System/CLAUDE.md`
- 门禁原始输出副本（会话 scratchpad，非入库）：`/private/tmp/claude-501/-Users-liu-Desktop-FYP-In-Cabin-Driver-Assessment--1--claude-worktrees-audit-files-dev-plan-ed0c73/be4350f1-4e5a-4bf1-9aeb-63516764da7e/scratchpad/gates/`
- Commit：commit 不可能包含自己的 SHA；用 `git log -1 fyp2/live-system` 查询。

## 9. Next task dependencies

- **所有后续 task 都在本工作树 / 本分支上执行**，以本 commit 作为起点。
- **Task 10 最终门禁**：重跑 `python3 scripts/freeze_manifest.py`，断言退出码 0 且「Models unchanged vs frozen baseline: YES」。
- **Task 4（迁移）**：开发数据库不存在，只能对一次性副本演练迁移，不得「重建库来修迁移错误」。
- **Task 10（Playwright E2E）**：`playwright>=1.60` 已声明；浏览器二进制是否已安装未在本 task 验证。
- **后续 task 的 pytest 一律先 `export TMPDIR=$(mktemp -d)`**（`test_api.py` 在收集阶段会销毁固定位置的临时库）。
- **门禁命令**：`npm test` 不做类型检查，`npx tsc --noEmit` 必须单独跑；`npx eslint .` 现在可作为整仓 lint 门禁。
- 任何后续 task 不得覆写 / 移动 / 重新导出 `ml/outputs/` 下的三个 checkpoint（它们是指向主仓库的只读符号链接）。
