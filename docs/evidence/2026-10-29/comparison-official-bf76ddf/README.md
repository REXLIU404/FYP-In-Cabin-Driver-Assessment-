# Stage 2 官方运行（修复后的 runner，`bf76ddf`）：现行版本

命令：`.venv/bin/python scripts/compare_vision_models.py --out docs/evidence/2026-10-29/comparison-official-bf76ddf`，exit 0。运行时工作树干净，只有用户的 `AGENTS.md` 与开发库的两个文件未跟踪。

- **协议**：运行前的协议门禁 4/4 通过；运行后重新计算的协议哈希没有变（`protocol_after_run.unchanged = true`，`b6305022…`）。
- **输入复核**：每个模型运行前都重新核验输入（`models.*.pre_run_input_verification.ok = true` × 3）；结果中记录了 `parent_command`；子进程不继承任何其他 `DRA_*` 变量。
- **有效性**：PASS。
- **确定性**：与实现方在 `94c6d14` 上的运行（`../comparison/`）、以及修复前的官方运行（`../comparison-official/`，在 `c0c6d43` 上）逐窗口逐字段比较，差异为 0。

这次重跑修复了 A2 独立审计的 F-1 至 F-4，取代 `../comparison-official/`。
