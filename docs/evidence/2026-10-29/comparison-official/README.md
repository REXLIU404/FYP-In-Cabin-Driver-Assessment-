# Stage 2 官方运行（集成后，`c0c6d43`）

命令：`.venv/bin/python scripts/compare_vision_models.py --out docs/evidence/2026-10-29/comparison-official`，exit 0，用时 23 s。协议门禁四项都通过，有效性检查 PASS。

- 同日 `docs/evidence/2026-10-29/comparison/` 下是实现方（DeepSeek）在 `94c6d14` 上的运行；与本次官方运行逐窗口逐字段比较，差异为 0。
- 这是协议意义上的「构造的评估场景」，结果只做描述，不选胜者，也不改变默认模型。自审表：`docs/fyp2/task10a/stage2_audit_table.md`。

> **已被取代（2026-10-29）**：本目录是修复前的 runner 在 `c0c6d43` 上的运行，没有做运行后的协议哈希复算（A2 审计的 F-1）。现行的官方运行是 `../comparison-official-bf76ddf/`。两次运行的结果逐字段相同。
