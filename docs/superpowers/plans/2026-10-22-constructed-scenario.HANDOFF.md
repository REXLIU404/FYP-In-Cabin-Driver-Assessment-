# Constructed scenario — 交接文件（2026-10-26 周末，DeepSeek → Claude）

工作区 `/Users/liu/Desktop/FYP2-Constructed-Scenario`，分支 `fyp2/constructed-scenario`，未 push。
起点 911c1a4（合并自 fyp2/live-system 94c6d14）。本文件与账本 `.superpowers/sdd/2026-10-22-constructed-scenario/progress.md`（git 忽略）配套。

## 每个 Task 的状态（全部完成，无进行中 / 未开始）

| Task | 状态 | 提交 |
|---|---|---|
| Task 3 剧本与生成脚本 | 完成 | 14f1b4e |
| Task 1 后端模式接线（R10/Live 类） | 完成 | c233780 |
| Task 2 label 覆盖 + replay provenance | 完成 | ee2a16a |
| Task 4 scenarios API（白名单 + sha256） | 完成 | 46c4f2a |
| 合并点 1 | 完成 | cb4f65b（merge fyp2/live-system 00b0e5d）+ cb04c10（门禁证据） |
| Task 5 播放时钟 + payload 契约 | 完成 | 176caec |
| Task 6 客户端与循环接线（含 liveLoop 模式切换） | 完成 | baa073c |
| Task 7 界面（下拉、ScenarioPlayer、玩家模型） | 完成 | e28eae0 |
| Task 8 端到端（e2e_short） | 完成 | 9ead12b（产品修复）+ d4308c2（测试） |
| Task 9 viva_v1 彩排、long 标记、报告与文档 | 完成 | 7f32371（Task 8 测试竞态修复）+ 5c0461a |
| 合并点 2（RP-2） | 完成 | 无新 merge 提交（origin/fyp2/live-system 已在 00b0e5d 之内）+ 634107e（门禁证据） |
| 模式名用户决定 | 完成 | 0066e01（Constructed demo scenario） |

## 下一步（Claude）

1. 把 `fyp2/constructed-scenario`（最新 tip **0066e01**，本分支未 push）合并进 `fyp2/live-system`。
2. 模式名已由用户决定为 **Constructed demo scenario**，改名已在 0066e01 完成（常量 + 会话描述 +
   两处测试字面量 + README），无需再做。

## 全部 Ruling（详情见账本；共 17 条）

1. Task 1：A6 CSV telemetry_source 断言按会话模式分支（Task 2 服务端覆盖与 Task 1 断言冲突）。
2. Task 4：白名单变异哨兵改为「磁盘上存在但不在 manifest 中的文件」（%2F 穿越在路由层即 404）。
3. Task 2：replay 存储用 model_dump(exclude_none=True)（与「逐字保留」语义一致）。
4. Task 5：LiveMonitor mode prop 与 DATA_MODE_NOTE 的类型先行放宽（Task 7 不动）。
5. Task 6：liveLoop 模式切换测试用 realApi + fetch stub（rig 假 api 绕开 client.ts）。
6. Task 6：useScenarioReplay() 不带 api 参数（与仓库 hooks 风格一致）。
7. Task 6：refreshSessions 过滤用 isLiveLike（规则 E 唯一判断；PREPARED 行为不变）。
8. Task 6：两个源码守卫测试随 Task 6 更新形状，守卫本意不变。
9. Task 7：useScenarioReplay() 增加返回值 manifest（App 组装玩家模型需要）。
10. Task 7：计划合并点 M3 取消，只设 RP-1 / RP-2 两处（用户执行指令）。
11. Task 8：scenarioTimeline.resume() 推进 epoch（否则暂停-继续必 409 observation_conflict）。
12. Task 8：App 场景结束 effect 只依赖 live.pause + finished 标志（否则 React maximum update depth 白屏）。
13. Task 8：五方对账容忍自动停止的 in-flight 竞态窗口（服务器至多多一个窗口）。
14. Task 8：e2e_short 第三段是 c4=talking_phone_left，测试期望按 manifest 修正（原期望笔误）。
15. Task 8：start_server 的 extra_env 签名 extra_env: dict[str, str] | None = None（覆盖规则 D，状态板已写一行，Task 10A Phase 3 复用）。
16. Task 9：test_a_full_run UI 面板断言容忍 pause 边界丢弃竞态（strip.Window ∈ {n, n-1}）。
17. Task 9：status.py 的 trained scope 文本保持不变（API 载荷有、UI 不渲染；未来若渲染需按模式改）。

## BLOCKED 项

无。全程没有需要停下等用户的事项；模式名一项按「先按原名实现 + 单常量」处理，见下。

## 最近门禁

- 合并点 2 门禁（在本分支合并了最新 fyp2/live-system 之后）：`DRA_REQUIRE_MODELS=1 python3 scripts/run_gates.py --out docs/evidence/2026-10-26/constructed-scenario-m2-gate/` → GREEN：pytest 1308 passed / 0 skipped / 8 deselected，vitest 1022 passed，build/tsc/eslint PASS。证据同目录（SUMMARY.md）。
- Task 9 彩排：`docs/evidence/2026-10-26/constructed-scenario-rehearsal/`（README 首行「内部彩排记录，不是评估结果，报告与答辩 不引用」；viva_v1 一次完整播放：1341 窗口 / 7 段 / 零故障，逐段一致率、RiskLevel、AlertSeverity 序列为如实记录）。
- 基线门禁（911c1a4）：pytest 1115 / 0 skipped / 7 deselected，vitest 972。

## 待用户决定

无。**界面模式名已决定（2026-10-26，用户）：`Constructed demo scenario`**，实现于 0066e01
（`CONSTRUCTED_MODE_LABEL` 常量、会话描述前缀、`dataMode.test.ts` / `client.test.ts` /
`test_constructed_scenario_e2e.py` 期望字面量、README 演示节）。

## 已知问题

1. 构造会话的 `/api/models` 也返回 trained.info["scope"]（"Frontal-camera inference is experimental..."）：
   UI 不渲染（Ruling 17）。未来若前端渲染 scope，需按模式改写。
2. 场景自动停止后 3 s，Live Monitor 面板变 "Latest result is stale"（与 Live Pause 一致，设计内行为）。
   elapsed 显示 0:11/0:12（pos 封顶 duration_ms-1 的 mmss 表现）。
3. 每个帧被发送两次（tick 100 ms vs frame 200 ms → NEW + REPEAT），REPEAT 也分配新 window_id（服务器 R10
   协议）→ 窗口数 ≈ 2× 帧数。彩排报告里同时记录了 windows 与 distinct_frames，勿混淆。
4. 彩排中 distracted 段的「真实 vs 模型」一致率为 0（稳定 MobileNetV3 不输出 c1/c4/c7 类别）——模型事实，
   仅记录不断言；任何命中率/RiskLevel 数字都不是评估结果（规则 F / D06）。
5. 测试与运行一律临时数据库；不碰 8000 端口（有用户 10-22 启动的开发后端，PID 41104）与 driver_risk.db*。
6. `demo/bundles/` 被 git 忽略，图片永不入库；生成脚本不导入模型代码。
7. 合并时注意：origin/fyp2/live-system 目前停在 b58fcc6（CL-2 的 00b0e5d 尚未 push 到远程），本分支已包含
   00b0e5d（RP-1 时并入）。Claude 若在 live-system 上有新提交，先 merge 进本分支、跑门禁，再合回。
