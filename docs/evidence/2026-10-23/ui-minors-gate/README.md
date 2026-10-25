# 界面审查与暂缓 Minor 修复：门禁证据

- **门禁提交**：`2745348`（`fyp2/live-system`）。界面改动在 `6886a2e`，Minor 修复在 `2745348`。
- **命令**：`DRA_REQUIRE_MODELS=1 .venv/bin/python scripts/run_gates.py --out docs/evidence/2026-10-23/ui-minors-gate`，在已提交的代码上运行。
- **结果**：全绿。

| 门禁 | 结果 |
|---|---|
| build | PASS |
| pytest | **1046 passed / 0 skipped / 1 deselected**（ST-LONG-01，只在 `-m long` 时运行） |
| vitest | 954 passed |
| tsc | 0 |
| eslint | 0 |

- **「working tree dirty（4 entries）」**：这 4 项是 `AGENTS.md`、`backend/driver_risk.db-shm`、`backend/driver_risk.db-wal` 和本证据目录 `docs/evidence/2026-10-23/`。门禁不读取其中任何一项。
- **`freeze_manifest.txt`**：三个冻结模型的哈希都是 MATCH。
- **截图**：`docs/evidence/2026-10-23/ui-review/`。
- **验收报告**：`docs/fyp2/implementation/ui-review-minors-acceptance.zh.md`。
