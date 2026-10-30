# Stage 5 自审表（2026-10-30）

依据：计划 §8（Phase 5）与用户清单 `11_SYSTEM_INTEGRATION_STAGE_PLAN_AND_AUDIT.md` 的 Stage 5 表。模型选择由用户在 U-5 决定，本表不替用户决定。

| 审计点 | 证据 | 结果 |
|---|---|---|
| 回滚可执行且被验证（演练日志 exit 0） | `docs/evidence/2026-10-30/stage5-rollback-drill/`：`drill.log`、`drill.json`、两份 uvicorn 日志；README 启动命令、8001 端口、临时库；候选在役 → 新进程 `DRA_ACTIVE_VISION` 不设 → stable，hash = 冻结值 `b3a42e8d…`，各做一次正常 `/infer`（201、有评估、provenance 指向对应模型）；`ml/outputs` 下 94 个文件前后哈希一致；11/11 PASS，exit 0 | 待审计 |
| 决策记录引用 Stage 2/3 的当日证据 | `docs/fyp2/task10a/release_decision.md` §2：Stage 2 `docs/evidence/2026-10-29/comparison-official-bf76ddf/`（三个模型同日运行）、Stage 3 `docs/evidence/2026-10-30/stage3-raw/`（同日交替运行）；文中每个路径都可打开 | 待审计 |
| 版本化配置与回滚步骤，不覆盖稳定产物 | `release_decision.md` §4：唯一开关 `DRA_ACTIVE_VISION`（默认 stable）、启动与核对命令、回滚步骤；候选在 `ml/outputs/candidates/` 自己的包目录，稳定产物路径不变 | 待审计 |
| 不自动启用 ResNet18（计划 §8 Step 3） | 代码默认值 `active_vision = "stable"`（`backend/app/config.py`）未改；决策记录状态为「待用户决定」 | 待审计 |
| 报告措辞与决策一致 | `release_decision.md` §5 给出 6.2.3 结论段与 Table 23 的两套措辞（按用户选择择一）；DOCX 由用户修改 | 待用户决定后核对 |
