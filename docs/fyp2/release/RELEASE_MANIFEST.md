# FYP2 Live-System — Release Manifest（Task 1 基线冻结）

> 本文件由 Task 1（`fyp2/live-system` 分支）产出，用来把「源码 / 模型 / 数据 split / 依赖」钉死，作为后续 Task 2–10 的对照基线。
> 第 7 节是 `python3 scripts/freeze_manifest.py` 的**原样输出**；任何时候重跑该脚本即可复核（脚本在模型哈希不符时退出码为 1）。
> 模型二进制**不入库**，只记 SHA-256（B05 的解法）。

## 1. 工作环境

| 项 | 值 |
|---|---|
| 工作树 | `/Users/liu/Desktop/FYP2-Live-System`（`git worktree`，由控制者在派发前创建） |
| 分支 | `fyp2/live-system` |
| 基线 commit | `845b43a`（= `dev_cc` HEAD） |
| 主仓库 | `/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1` —— **只读**，Task 1 未对其做任何写入 |
| 模型 checkpoint | 三个文件以符号链接接入 `ml/outputs/`，指向主仓库，只读 |
| `.venv` / `node_modules` | 符号链接到主仓库，已列入 `.git/info/exclude` |
| 数据根目录（split CSV） | `/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment-`（**末尾无 `1`**，兄弟仓库；也可用环境变量 `FYP_DATA_ROOT` 覆盖）。本工作树与主仓库均**没有** `eda_outputs/` |
| 开发数据库 | **不存在**（全树无 `.db` / `.sqlite` / `.sqlite3`），因此没有可备份的库；Task 4 的迁移只能对一次性副本演练 |

> 第 7 节 manifest 是在 Task 1 的 commit **之前**生成的，所以其中「Working tree: dirty」列出的恰好是 Task 1 的改动集（已 `git add`，尚未 commit），HEAD 仍是基线 `845b43a`。

## 2. 基线门禁（Task 1 改动之后、commit 之前实跑）

环境：`export TMPDIR=$(mktemp -d); export PYTHONDONTWRITEBYTECODE=1`（`backend/tests/test_api.py` 会在收集阶段销毁固定位置的临时库，所以必须隔离 `TMPDIR`）。

| 门禁 | 命令 | 结果 | 退出码 |
|---|---|---|---|
| pytest | `cd backend && PYTHONPATH=. ../.venv/bin/python -m pytest tests -q -p no:cacheprovider` | **28 passed**, 1 warning | 0 |
| vitest | `npx vitest run` | **32 passed**（4 个文件） | 0 |
| tsc | `npx tsc --noEmit` | 无输出（无错误） | 0 |
| eslint（整仓） | `npx eslint .` | 无输出（无问题） | 0 |
| eslint（源码） | `npx eslint ai frontend` | 无输出（无问题） | 0 |

pytest 原始输出：

```
............................                                             [100%]
=============================== warnings summary ===============================
../../FYP-In-Cabin-Driver-Assessment--1/.venv/lib/python3.13/site-packages/fastapi/testclient.py:1
  /Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/.venv/lib/python3.13/site-packages/fastapi/testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
28 passed, 1 warning in 5.15s
```

vitest 原始输出：

```
 RUN  v2.1.9 /Users/liu/Desktop/FYP2-Live-System

 ✓ ai/src/alertFsm.test.ts (7 tests) 2ms
 ✓ frontend/src/utils/persistence.test.ts (3 tests) 2ms
 ✓ ai/src/riskLogic.test.ts (16 tests) 3ms
 ✓ frontend/src/data/preparedSessionInput.test.ts (6 tests) 2ms

 Test Files  4 passed (4)
      Tests  32 passed (32)
   Start at  13:11:10
   Duration  285ms (transform 105ms, setup 0ms, collect 160ms, tests 9ms, environment 0ms, prepare 301ms)
```

`pytest` 的 1 个 warning 是 `fastapi.testclient` 对 `httpx` 的弃用提示（第三方，非本项目代码），不影响结果。

## 3. `AGENTS.md` 处置

- `AGENTS.md` 在基线 `845b43a` 中**是被跟踪文件**，内容仅为 1 字节 `;`。
- 用户已明确决定：**删除，不恢复**（主仓库 `dev_cc` 工作区里已是未提交的删除）。本分支用 `git rm AGENTS.md` 做了同样的删除并纳入 Task 1 的 commit。
- 注意：这个删除**只存在于 `fyp2/live-system` 分支**；`dev_cc` 在用户自己提交其删除之前仍然跟踪该文件。
- 历史内容仍可取回：`git show 0113b61:AGENTS.md`（647 行 / 20,275 字节）。本阶段不恢复、不归档。
- 本分支不 push。

## 4. 悬挂引用处理与已知陈旧项登记

已改（`CLAUDE.md`）：

| 位置 | 原文 | 现文 |
|---|---|---|
| 小节标题 | `## Scope guardrails (from AGENTS.md — keep the project on-route)` | `## Scope guardrails (keep the project on-route)`（小节内容未动） |
| `Source of truth & docs` | `` `AGENTS.md` contains the applicable project instructions.`` | `This file (`CLAUDE.md`) contains the applicable project instructions.`（句子其余部分未动） |

按用户「文档暂不整改」的决定**保持原样、仅登记**的陈旧引用：

| 文件:行 | 性质 |
|---|---|
| `PROJECT_MEMORY.md:518` | 目录树仍列出 `AGENTS.md` |
| `docs/FYP2_CLAUDE_DEVELOPMENT_HANDBOOK.zh.md:17` | 「`AGENTS.md` 的原有用户修改必须保留」 |
| `docs/IMPLEMENTATION_PROGRESS.zh.md:98` | 「用户原有的 `AGENTS.md` 修改保留」 |
| `ml/experiments/README.md:81` | 「…user changes to `AGENTS.md` were edited by this assessment」 |

另有若干**历史证据文件**按时点记录了 `AGENTS.md`（`docs/evidence/2026-10-09/verification-manifest.json:2`、`docs/fyp2/evidence/audit_commands.md:67`、`docs/fyp2/evidence/repository_discovery.json:471`、`docs/fyp2/evidence/source_inventory.json:6,14`）。它们是审计时点快照，**不应修改**。

## 5. Lint 门禁修复

`eslint.config.js` 的 `ignores`：`["dist", "node_modules", ".venv"]` → `["dist", "node_modules", ".venv", ".claude", ".superpowers"]`。

- 动机：在主仓库里存在 `.claude/worktrees/…` 时，`eslint .` 会走进陈旧副本报 `prefer-const`（来源：旧的 `alertFsm.test.ts`）。`.superpowers/` 是本流程的工作文件目录，一并排除，避免日后放入 `.ts` 草稿引发同类误报。
- 验证：`npx eslint .` 退出 0（见第 2 节）。**诚实说明**：本工作树里 `.claude/` 与 `.superpowers/` 都不含任何 `.ts/.tsx/.js` 文件，用旧配置在此处跑 `eslint .` 同样退出 0，所以「修复前报错」在本工作树**无法复现**；该条目是针对主仓库场景的防御性修复，修复本身已验证不引入新问题。

## 6. 依赖声明

- `backend/requirements.txt`：顶部新增注释——`trained.py` 在 `TrainedProvider.__init__` 中 import `PIL` / `numpy` / `onnxruntime` / `xgboost`，因此 **live 运行时必须安装 `pip install -r requirements-inference.txt`**（它通过 `-r requirements.txt` 包含核心依赖）。本文件的依赖列表本身未改。
- `backend/requirements-inference.txt`：新增 `playwright>=1.60`（`.venv` 中实装 1.60.0；Task 10 的浏览器端到端验证要用）。
- `backend/requirements.lock.txt`：`.venv/bin/pip freeze` 的快照（143 个 pin）。**这是整个共享 `.venv` 的完整快照**，包含 ML 工具链（`torch`、`torchvision`、`scikit-learn`、`jupyterlab` 等）；后端 / live 运行时实际只需要 `requirements-inference.txt` 的依赖闭包。文件头部 4 行注释已说明这一点。
- 脚本会校验「声明的下界是否被实装版本满足」以及「lock 是否与 live `.venv` 一致」（见第 7.4 小节）。

## 7. Freeze manifest（`python3 scripts/freeze_manifest.py` 的输出，仅标题层级下移）

**脚本输出**（`## n.` 小节标题改为 `### 7.n`，其余原样）

Generated (UTC): `2026-10-12T05:11:46Z`  
Generator: `scripts/freeze_manifest.py` (python `3.13.9`)  
Repository root: `/Users/liu/Desktop/FYP2-Live-System`

### 7.1 Source (git)

| Item | Value |
|---|---|
| HEAD | `845b43a086e296d96835bf82e4ef8366c636e105` |
| Branch | `fyp2/live-system` |
| HEAD commit | 2026-10-10T17:28:18+08:00  docs(audit): FYP2 repository audit package and its nine deliverables |
| Working tree | dirty |
| Uncommitted entries | 10 |

Uncommitted entries (`git status --porcelain`):

```
D  AGENTS.md
M  CLAUDE.md
M  backend/requirements-inference.txt
A  backend/requirements.lock.txt
M  backend/requirements.txt
A  docs/fyp2/implementation/task-01.md
A  docs/fyp2/release/RELEASE_MANIFEST.md
A  docs/plans/2026-10-12-fyp2-live-system-completion.md
M  eslint.config.js
A  scripts/freeze_manifest.py
```

### 7.2 Model checkpoints (`ml/outputs/`, git-ignored, hash-only)

| File | SHA-256 (recomputed) | Bytes | Frozen baseline (SHA-256 / bytes) | Status |
|---|---|---|---|---|
| `ml/outputs/vision/mobilenetv3_large_vision.onnx` | `b3a42e8dd4553355b1fd7d9e7fe3d28e318decb894e76eb029489b7ff2e90bcf` | 16849378 | `b3a42e8dd4553355b1fd7d9e7fe3d28e318decb894e76eb029489b7ff2e90bcf` / 16849378 | MATCH, git-ignored |
| `ml/outputs/vision/mobilenetv3_large_vision.pt` | `196ca7b151d84e0c4a8eac87128da9dd8f22c894984a991ef611536bb523e7c7` | 17066477 | `196ca7b151d84e0c4a8eac87128da9dd8f22c894984a991ef611536bb523e7c7` / 17066477 | MATCH, git-ignored |
| `ml/outputs/telemetry/xgb_telemetry.json` | `9802cb06ca98f0c1befaf851fa7668cfec70e005cf8bb3884e49d7d45d7aec07` | 629723 | `9802cb06ca98f0c1befaf851fa7668cfec70e005cf8bb3884e49d7d45d7aec07` / 629723 | MATCH, git-ignored |

Symlink targets (read-only, owned by the main repository):

- `ml/outputs/vision/mobilenetv3_large_vision.onnx` -> `/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/ml/outputs/vision/mobilenetv3_large_vision.onnx`
- `ml/outputs/vision/mobilenetv3_large_vision.pt` -> `/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/ml/outputs/vision/mobilenetv3_large_vision.pt`
- `ml/outputs/telemetry/xgb_telemetry.json` -> `/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/ml/outputs/telemetry/xgb_telemetry.json`

No additional checkpoint-like files (`.joblib`, `.onnx`, `.pkl`, `.pt`, `.pth`, `.safetensors`, `.ubj`) under `ml/outputs/`.

**Models unchanged vs frozen baseline: YES**

### 7.3 Data splits (`eda_outputs/processed/**/*.csv`)

Data root: `/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment-` (not part of this repository; read-only).

| File (relative to `eda_outputs/processed/`) | SHA-256 | Bytes | Data rows |
|---|---|---|---|
| `telemetry/telemetry_clean.csv` | `5361962af47b7d06b36e8e43567aaa003cb33596c699a9ddafef93ba2ddc4820` | 5338910 | 30000 |
| `telemetry/telemetry_feature_order.csv` | `abce565234a3892d4c121e0bd97335500ac9b46e2a1477692615d79ce5541ae0` | 106 | 8 |
| `telemetry/telemetry_model_ready.csv` | `202308a8e5caa00ce0812d1c2eda1e39f27e519750f4adc8e1967d056f717050` | 4714973 | 30000 |
| `telemetry/telemetry_raw_snapshot.csv` | `5361962af47b7d06b36e8e43567aaa003cb33596c699a9ddafef93ba2ddc4820` | 5338910 | 30000 |
| `telemetry/telemetry_test.csv` | `3bc3d47680a87359e1470fd8ffaf5ff330dc4419b37cc645e5736d51a91c96de` | 707415 | 4500 |
| `telemetry/telemetry_train.csv` | `97dd20ee9c0832ba33455e5c31088f9b4abb65c198bf988699a959d545d1e5b5` | 3300372 | 21000 |
| `telemetry/telemetry_val.csv` | `1b02792df846b5af138bae59e4f4ccfa8fa421fbb4fd6d42fad88d57722774f1` | 707412 | 4500 |
| `vision/vision_metadata_clean.csv` | `2982a621507e222bab80e136bb06427d03105f4da31f497430d5c4040316d056` | 4155890 | 22424 |
| `vision/vision_metadata_raw.csv` | `bbc826cdb6090b201addba6d50766f8ae2fc615bd25f033183af37b86c425fd2` | 3550416 | 22424 |
| `vision/vision_metadata_with_split.csv` | `b4f8e90dec769bb419eaa490aea869668bed6484089cebe4d545c7667baa8ea4` | 4281047 | 22424 |

10 CSV files. Row counts exclude the header record.

### 7.4 Python environment (`.venv`, actually installed)

| Item | Value |
|---|---|
| Interpreter | `.venv/bin/python` -> `/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/.venv/bin/python` |
| Python | `3.13.3` |
| Host platform | `macOS-26.6.2-arm64-arm-64bit-Mach-O` |
| Installed distributions | 144 |

Declared requirements vs installed versions:

| Declared | Declared in | Installed | Spec check |
|---|---|---|---|
| `fastapi>=0.110` | `requirements.txt` | `0.136.3` | ok |
| `uvicorn[standard]>=0.29` | `requirements.txt` | `0.48.0` | ok |
| `SQLAlchemy>=2.0` | `requirements.txt` | `2.0.50` | ok |
| `pydantic>=2.6` | `requirements.txt` | `2.13.4` | ok |
| `pydantic-settings>=2.2` | `requirements.txt` | `2.14.1` | ok |
| `pytest>=8.0` | `requirements.txt` | `9.0.3` | ok |
| `httpx>=0.27` | `requirements.txt` | `0.28.1` | ok |
| `numpy>=1.26` | `requirements-inference.txt` | `2.4.6` | ok |
| `Pillow>=10.0` | `requirements-inference.txt` | `12.2.0` | ok |
| `onnxruntime>=1.17` | `requirements-inference.txt` | `1.26.0` | ok |
| `xgboost>=2.0` | `requirements-inference.txt` | `3.2.0` | ok |
| `playwright>=1.60` | `requirements-inference.txt` | `1.60.0` | ok |

`backend/requirements.lock.txt`: 143 pins, sha256 `a0fa1c76ca7706736f51c03491ce9c3f4f9a3f69c261dbf91fa9e9218e164f2c`.
Lock vs live `.venv`: IN SYNC.

### 7.5 Node toolchain

| Item | Value |
|---|---|
| node | `v24.1.0` |
| npm | `11.4.2` |
| package-lock.json sha256 | `f6fa92fd6f2e9f1cd22a97f827fdb364b9a1afb169afd1e3842b9284c9fec19b` |

Declared (`package.json`) vs installed (`node_modules`):

| Package | Group | Declared | Installed |
|---|---|---|---|
| `lucide-react` | dependencies | `^0.468.0` | `0.468.0` |
| `react` | dependencies | `^18.3.1` | `18.3.1` |
| `react-dom` | dependencies | `^18.3.1` | `18.3.1` |
| `recharts` | dependencies | `^2.13.3` | `2.15.4` |
| `@eslint/js` | devDependencies | `^9.17.0` | `9.39.4` |
| `@types/react` | devDependencies | `^18.3.18` | `18.3.28` |
| `@types/react-dom` | devDependencies | `^18.3.5` | `18.3.7` |
| `@vitejs/plugin-react` | devDependencies | `^4.3.4` | `4.7.0` |
| `eslint` | devDependencies | `^9.17.0` | `9.39.4` |
| `eslint-plugin-react-hooks` | devDependencies | `^5.1.0` | `5.2.0` |
| `eslint-plugin-react-refresh` | devDependencies | `^0.4.16` | `0.4.26` |
| `globals` | devDependencies | `^15.14.0` | `15.15.0` |
| `prettier` | devDependencies | `^3.4.2` | `3.8.3` |
| `typescript` | devDependencies | `^5.7.2` | `5.9.3` |
| `typescript-eslint` | devDependencies | `^8.18.2` | `8.59.1` |
| `vite` | devDependencies | `^6.0.5` | `6.4.2` |
| `vitest` | devDependencies | `^2.1.9` | `2.1.9` |

### 7.6 Development database

No `.db` / `.sqlite` / `.sqlite3` file exists anywhere in the working tree (`.git`, `node_modules`, `.venv`, `dist` excluded). There is no development database to back up; later schema migrations must be exercised on a throw-away copy.

### 7.7 Dependency / config files

| File | SHA-256 | Bytes |
|---|---|---|
| `backend/requirements.txt` | `5dd8966c3a136e3d4b5bf5141d3524dcd300a149b493cedf5994b066638eaa2e` | 490 |
| `backend/requirements-inference.txt` | `0af6e32adf918e6fb427abcd36a13c868dce3678eb1b2d54d6688af67aaf0522` | 151 |
| `backend/requirements.lock.txt` | `a0fa1c76ca7706736f51c03491ce9c3f4f9a3f69c261dbf91fa9e9218e164f2c` | 2977 |
| `package.json` | `0ab677fe2705de9ed47bf97c16776567973e7c19e5b1563ceb8b745012fc887a` | 1081 |
| `package-lock.json` | `f6fa92fd6f2e9f1cd22a97f827fdb364b9a1afb169afd1e3842b9284c9fec19b` | 171363 |
| `eslint.config.js` | `427dea849b2bd321fb55e96bf889a3f3c08fd365b1343280cf43d673046e8bec` | 788 |
| `tsconfig.json` | `50d1f40b9207c81ce7a02cf2605b0b6eaacf36f0acac743342c140fe3d37d4c2` | 564 |
| `vite.config.ts` | `1fa310cf929927e48702d2245c9fa1635b07e14b3fc3b4335028f9322f0bb770` | 321 |
| `vitest.config.ts` | `c361d732b7c9b5de1b0dd68729ad6b922eb2990917b9bf47245b2065bd974fcd` | 340 |

## 8. 复现方式

```bash
cd /Users/liu/Desktop/FYP2-Live-System
python3 scripts/freeze_manifest.py            # 无参数；Markdown 输出到 stdout
echo $?                                       # 0 = 三个模型哈希均与冻结基线一致；1 = 有缺失或不符
FYP_DATA_ROOT=/path/to/data python3 scripts/freeze_manifest.py   # 数据根目录不在默认位置时
```

Task 10 的最终门禁应重新运行该脚本并断言：第 7.2 小节「Models unchanged vs frozen baseline: YES」、退出码 0。
