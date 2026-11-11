# Task 10A Stage 4（Target Camera Validation）：演示路径说明

- **日期**：2026-10-29。**作者**：Claude（集成会话）。**性质**：说明文件，不是实验。按规格 Stage 4 与 10-25 机位裁定，本阶段不做新实验。

## 1. 演示走哪条路径（4-C）

答辩演示的主路径是 **Constructed demo scenario**（数据集帧回放），不是笔记本的正面摄像头。

- 模式：`CONSTRUCTED_SCENARIO_RUNTIME`。后端用 `schemas.is_live_like` 判断这个模式，走的是与 Live 相同的 R10 / EMA / FSM 管线（`backend/app/schemas.py:23-34`，`backend/app/inference.py:334`）。所以回放帧经过的是完整的 RiskUpdate 链路，不是另一套逻辑。
- 情景包：`viva_v1`，680 帧、68 行遥测、7 段、136 s，由 `scripts/build_dataset_replay.py` 生成，目录被 git 忽略。
- 界面标签：`CONSTRUCTED SCENARIO · not live`，Data mode 下拉项为 `Constructed demo scenario`，与 `Live camera (trained models)` 明确区分。
- 会话可追溯：合并后的浏览器验收（`cde7ab1`）跑完一整个情景会话，共 1321 个窗口，在 Risk Trends 与 Signal Inspector 中可见，控制台无报错。证据：`docs/evidence/2026-10-29/constructed-scenario-merge-gate/ACCEPTANCE.md`（同目录有当日门禁日志：pytest 1308 / vitest 1022 / build / tsc / eslint）。

## 2. 侧面机位（4-B）

只由用户自己非正式观察。没有标签，也没有被试划分，所以**不是评估证据**，不进入第 6 章，答辩时可以口头提及。正面视角识别受限仍然是已测量的局限，证据见 `docs/evidence/2026-10-22/vision-runtime-path/README.md`。

## 3. 报告口径检查（没有把回放数字当作评估结果）

2026-10-29 只读检查了报告草稿 `~/Desktop/FYP/FYP2.docx`（修改时间 2026-10-29 15:47）的第 6 章（6.1–6.7）：

- 第 6 章所有段落都不含 `viva_v1`，也没有出现回放会话的命中率或 RiskLevel 数字。
- 6.6 节（Table 23）的端到端数字来自 Live 证据 `docs/evidence/2026-10-22/perf/`：capture→render 中位数 28 ms、p95 39 ms；D1/D2 211/211。
- 6.7 节写明：*Constructed demo scenarios are demonstration material and are not counted as evaluation outcomes here.*
- 检索方法：对第 6 章逐段检索 `constructed|replay|scenario|viva_v1|demo|dataset frame`，只有 6.7 的上面那句命中。
- 注意区分：D06 的 constructed evaluation pairs（E2，2026-10-23 用户决定）是**预先声明的构造评估情景**，和这里的 Constructed demo scenario 演示回放不是同一个东西。当前草稿还没有 E2 结果，6.7 节写的是 E2/E5 报告尚未完成。本检查只针对演示回放。

**结论**：演示走回放路径；第 6 章没有把回放数字当作评估结果。以后修改第 6 章时，这条规则继续适用。

> 2026-10-29 晚补记（只追加）：上文「界面标签」一条记录的是当时的界面。按用户要求，播放器标识已改为 `CONSTRUCTED SCENARIO`（不再带 `· not live`，提交 e26e32a）；顶栏标识与 Data mode 选项不变。演示路径的其他内容不受影响。
