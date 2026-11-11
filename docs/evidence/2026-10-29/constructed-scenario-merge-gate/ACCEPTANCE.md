# Constructed demo scenario：合并后的门禁与验收（2026-10-29）

- **合并**：`cde7ab1` 把 `fyp2/constructed-scenario`（tip `8084131`，DeepSeek 的 RP-0 至 RP-H）合并进 `fyp2/live-system`，没有冲突。合并前已核对：`liveLoop.ts` 只增加了类型定义和 `buildLivePayload` 里的 `replay` 组装，循环逻辑没有改；`inference.py` 只把 Live 判断改为 `is_live_like`，语义不变；diff 中没有 `demo/bundles` 和图片文件。
- **门禁**（本目录，`cde7ab1`，运行期间工作树里没有其他运行）：GREEN。pytest 1308 passed / 0 skipped / 8 deselected，vitest 1022，build、tsc、eslint 均通过。与分支基线一致。
- **情景包**：`python3 scripts/build_dataset_replay.py viva_v1 --out demo/bundles` 生成 680 帧、68 行遥测、7 段、136000 ms。目录被 git 忽略。
- **验收**：`npm run build` 之后，uvicorn 用临时库在 8100 端口启动；8000 端口上当时没有进程。用浏览器逐项检查：

| 项 | 结果 |
|---|---|
| Data mode 下拉正好两项：`Live camera (trained models)` / `Constructed demo scenario` | 通过 |
| Scenario 下拉列出 `viva_v1 · 136 s · 7 segments` | 通过 |
| Start Monitoring 之后，LIVE MONITOR 区域是图片流（Scenario Player），标签为 `CONSTRUCTED SCENARIO · not live`，显示 Truth 与 Model | 通过 |
| 约 136 s 后自动停止，显示 `Scenario finished`，Start Monitoring 可以再次点击 | 通过（1321 个窗口；帧数的约 2 倍，因为每帧有 NEW 与 REPEAT 两次，这是设计行为） |
| Risk Trends 与 Signal Inspector 显示这个会话；控制台无报错 | 通过 |

- **观察（不是缺陷）**：选好场景后，页面会先预加载 680 帧。预加载期间 Start Monitoring 是禁用的（`App.tsx:255`），状态栏显示 `Loading frames n/680…`，所以在这几秒内点击没有效果。
- 本模式的任何命中率或 RiskLevel 数字都不是评估结果，不进入报告；报告只引用 Live 的数字。
