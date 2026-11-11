# Stage 5 自审表（2026-10-30）

依据：计划 §8（Phase 5）与用户清单 `11_SYSTEM_INTEGRATION_STAGE_PLAN_AND_AUDIT.md` 的 Stage 5 表。模型选择由用户在 U-5 决定，本表不替用户决定。

| 审计点 | 证据 | 结果 |
|---|---|---|
| 回滚可执行且被验证（演练日志 exit 0） | `docs/evidence/2026-10-30/stage5-rollback-drill/`：`drill.log`、`drill.json`、两份 uvicorn 日志；README 启动命令、8001 端口、临时库；候选在役 → 新进程 `DRA_ACTIVE_VISION` 不设 → stable，hash = 冻结值 `b3a42e8d…`，各做一次正常 `/infer`（201、有评估、provenance 指向对应模型）；`ml/outputs` 下 94 个文件前后哈希一致；11/11 PASS，exit 0 | 复审 VERIFIED_PASS（2026-10-30） |
| 决策记录引用 Stage 2/3 的当日证据 | `docs/fyp2/task10a/release_decision.md` §2：Stage 2 `docs/evidence/2026-10-29/comparison-official-bf76ddf/`（三个模型同日运行）、Stage 3 `docs/evidence/2026-10-30/stage3-raw/`（同日交替运行）；文中每个路径都可打开 | 复审 VERIFIED_PASS（2026-10-30） |
| 版本化配置与回滚步骤，不覆盖稳定产物 | `release_decision.md` §4：唯一开关 `DRA_ACTIVE_VISION`（默认 stable）、启动与核对命令、回滚步骤；候选在 `ml/outputs/candidates/` 自己的包目录，稳定产物路径不变 | 复审 VERIFIED_PASS（2026-10-30） |
| 不自动启用 ResNet18（计划 §8 Step 3） | 代码默认值 `active_vision = "stable"`（`backend/app/config.py`）未改；决策记录现为「已决定：A」，默认值本来就是 stable，未改配置 | 复审 VERIFIED_PASS（2026-10-30） |
| 报告措辞与决策一致 | `release_decision.md` §5 给出 6.2.3 结论段与 Table 23 的两套措辞（按用户选择择一）；DOCX 由用户修改 | 用户已决定 A；DOCX 6.2.3 与 Table 23 由用户按 `release_decision.md` §5 修改 |

## 独立审计结果与处理（2026-10-30）

Stage 5 判 **PARTIAL**：回滚演练审计者重跑 11/11、exit 0；决策记录的路径与数字全部核对一致；未自动启用 ResNet18。问题与处理：

- O-2（两个选项呈现不对称）→ 已改：补上「分心帧被漏判为安全」一侧（stable 2.79% 对 ResNet18 1.95%）与二分类合计错误（129 对 150）；4 名驾驶员的小样本告诫对两边同样适用；ResNet18 的优点一栏补全。
- O-3（`.env` 位置写错）→ 已改：设置读取启动时当前目录的 `.env`，按文档命令即仓库根目录。
- O-4（措辞不精确）→ 已改：正面摄像头改为原文表述；Stage 1 行分开 stable 与候选的检查口径；Stage 3 行注明服务端分段只有汇总；HPO MN 的数字写进正文；§1 与 §5 的需改章节一致；「概率更可信」改为「按 log loss 概率估计更好」。
- O-8（演练脚本的说明）→ 在演练 README 说明，脚本保持运行时原样。
- 用户决定（2026-10-30，对话中）：**A，保留 stable MobileNetV3-Large**；Table 23 改用 10-30 同日数字。记录在 `release_decision.md` §3、§5；书面签字待用户补签。
- 「报告措辞与决策一致」：§5 给出选 A 的 6.2.3 结论段与 Table 23 的具体数字，DOCX 由用户修改后核对。

## 用户决定补充（2026-10-30）

- FUD-5：确认 Stage 5 是用户授权开始的（对话中「start the stage 5, select the final model」）。
- FUD-4：用户选择把 `fyp2/live-system` 快进到 `637a0ff`；之后的提交在独立工作区 `/Users/liu/Desktop/FYP2-Live-System-Integration`。
- f15f539 的全新克隆门禁：`docs/evidence/2026-10-30/stage5-coldstart-f15f539/`，PASS（pytest 1360 / 0 skipped / 8 deselected，vitest 1061）。

## 复审结果（2026-10-30）

新鲜只读子代理复审：**Stage 5 VERIFIED_PASS**（同时 Stage 3 VERIFIED_PASS）。报告原文：`docs/fyp2/task10a/stage3_stage5_reaudit.md`。审计者自己重跑：回滚演练 11/11、exit 0；决策记录中每个数字与来源一致（含 90/3226、63/3226、129/150，RN 的漏判数由 `predictions_test_clean.csv` 逐行计数）；两个选项的呈现已对称。复审留下的 Minor（N-1 Table 23 说明、N-2 新工作区缺模型链接、N-3 记录不同步、N-4 Stage 1 判定的引用位置、N-5 措辞）已在本次提交中修正。
