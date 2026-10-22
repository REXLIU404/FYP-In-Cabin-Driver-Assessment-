# W5 / W6 系统测试执行计划（系统轨道，`fyp2/live-system`）

> 执行方式：superpowers:executing-plans（用户 2026-10-22 指定，内联执行，最后一次整分支评审）。
> 账本：`.superpowers/sdd/2026-10-12-fyp2-live-system-completion/progress.md`（与主计划共用）。

**Spec**：
- 冲刺计划 v3（`/Users/liu/Desktop/01_FYP2_Parallel_Sprint_Plan_W2_W7_v3.zh.md`）的 W5 / W6 Track A 行、§6 的 G-W5-A / G-W6-A；
- 主计划 `docs/plans/2026-10-12-fyp2-live-system-completion.md` 的 Global Constraints 与 Task 10A。

**目标**：关闭 G-W5-A（硬性）与 G-W6-A，E2–E5 runner 除外。

## Global Constraints

- 不改融合、FSM、EMA、阈值和模型文件；不碰 `docs/fyp2/review/`、主仓库、用户 8000 端口上的后端与开发库。
- 每项都用 TDD：先写失败的测试，看着它变红，再写实现。每项一个提交，提交信息末尾带 Opus 署名行。
- 门禁：`DRA_REQUIRE_MODELS=1 python3 scripts/run_gates.py`，五道全部通过且 0 skipped。
- 新文件一律用 shell 写入（10-22 应用回退事件的教训）。
- 端到端测试用空闲端口、tmp 数据库和 Chromium 假摄像头，沿用 `e2e_support.py`。
- **只陈述实测结果**。PERF 只记录、如实报告是否达标，不得放宽目标去凑结果。

## Review Focus

1. **加载旧会话后点 Start**：必须新建会话，不得往只读的旧会话里写。
2. **暂停后恢复**：同一会话，`window_id` 连续；遥测开一个新分段，seq 加 1，不得复用旧 seq 导致 409。
3. **用户选中一个窗口后**：新窗口到达时，选中项不得被「跟随最新」覆盖；切换会话后恢复为跟随最新。
4. **冷启动**：不得依赖主仓库的 `.venv`、`node_modules` 或开发库；模型文件缺失时显式跳过，`DRA_REQUIRE_MODELS=1` 下必须失败。
5. **长会话**：超过 500 个窗口后，导出仍完整、`window_id` 连续，页面只保留 500 个。

---

### S1：选中窗口默认跟随最新

- **改动**：`frontend/src/App.tsx` 的选中逻辑抽成纯函数 `selectRecord(history, selectedWindowId: number | null)`（新文件 `frontend/src/utils/selection.ts`）。
  - `null` 表示跟随最新；用户点了某个窗口就固定在那个窗口；会话 id 变化（新建、恢复到另一个、加载）时重置为 `null`。
  - replay 路径保持现状。
- **测试**（vitest）：
  1. `null` 时返回最新；
  2. 指定的窗口在 history 里就返回它；
  3. 指定的窗口已不在 history（被 500 条上限挤出）时返回最新；
  4. 空 history 返回 `undefined`。
- App 的重置行为由 S2 的端到端测试守护。

### S2：ST-SESSION-01（真实浏览器）

新文件 `backend/tests/test_live_session_lifecycle.py`，带 `e2e` 标记与 `requires_models`，使用会话级共享的 `e2e_server`：

1. **Start**：会话 A 收到 ≥ 5 个窗口，Inspector 默认选中最新窗口（S1）。
2. **Pause，再 Start（恢复）**：
   - 仍是会话 A，没有新的 `POST /api/sessions`；
   - `window_id` 接着之前的继续，没有间断；
   - 恢复后第一个带遥测的请求，`telemetry_seq` 等于暂停前的最大值加 1；
   - 没有任何 409 或故障记录。
3. **New Session**：建立会话 B，`window_id` 从 1 开始，会话 A 的行数不再增加。
4. **Refresh saved sessions，选择会话 A**：
   - 界面显示 A 的记录，不再请求 `/infer`；
   - 选中项默认是 A 的最新窗口；
   - Explanation 与 Inspector 显示同一个窗口。
5. **加载 A 之后点 Start**：建立新会话 C，A 和 B 的行数都不变。
6. **在 Inspector 中点选某个窗口**：新窗口持续到达时，选中项保持不变。
7. **每个会话**都做五方对账（`assert_reconciled`）；全程没有控制台错误，也没有故障记录。

### S3：ST-COLDSTART-01（从全新 checkout 干净启动）

新文件 `scripts/coldstart_check.sh`，在 tmp 目录完成以下步骤，每步计时：
1. `git clone` 本地仓库并检出指定提交；
2. `python3 -m venv` 加 `pip install -r backend/requirements.txt`，以及 Playwright 浏览器检查；
3. `npm ci`；
4. 三个模型以只读符号链接接入。模型不进 git，需要另行提供，这一点写进 README；
5. 跑 `run_gates.py`，`DRA_REQUIRE_MODELS=1`；
6. 在空闲端口用 tmp 数据库启动 uvicorn，检查 `/api/health` 和 `/api/models` 的哈希。

另外：
- 输出写进 `docs/evidence/<date>/coldstart/`；
- README 增加「从零启动」一节；
- 把本工作树的 `.venv` 从指向主仓库的符号链接，换成本地虚拟环境。原链接改名保留，不删除。

### S4：Task 10A 候选模型包 manifest schema 交接（给 ML 轨道）

新文件：
- `docs/fyp2/handoff/task-10a-runtime-manifest.md`：说明文档；
- `backend/app/runtime_manifest_schema.json`：JSON Schema；
- `scripts/validate_runtime_manifest.py`：校验脚本，附 pytest。

**schema 字段**按主计划 Task 10A 的要求：
- 模型路径（相对候选包根目录，禁止逃逸）、SHA-256；
- 架构名；
- 输入形状 `[1,3,224,224]`、float32、NCHW；
- 预处理：只接受 `rgb_resize_224_bilinear_no_crop_div255_imagenet`；
- 输出为 `logits`；
- 类别顺序与 `class_to_idx`，safe 类的下标；
- 契约冒烟集的来源 split 与样本 ID 清单的哈希；
- 不得包含评估指标。

**测试**：
- 稳定模型的示例 manifest 能通过校验；
- 以下情况都会被拒绝：预处理不同、输出为 probabilities、路径逃逸（`../`）、缺少哈希、带评估指标、类别重复。

**本项不做**：provider 改造与离线评估器（W6 拓展项，以 G-W5 通过为前提）。

### S5：G-W5-A 证据归档

`docs/evidence/<date>/w5-gate/`，内容包括：
- `run_gates.py` 的输出；
- `freeze_manifest.txt`；
- `README.md`：把 G-W5-A 每一项对应到测试与报告，涉及会话生命周期、冷启动、五视图、latest / flag / 完整导出、无未关闭的 P0。

### S6：ST-LONG-01（长会话）

- 新文件 `backend/tests/test_live_long_session.py`，带 `long` 标记，**默认门禁不运行**，需显式 `-m long`。
- **运行方式**：Live 加假摄像头，连续运行 ≥ 15 分钟（约 9,000 个窗口）。
- **断言**：
  - `window_id` 连续，数据库、`GET /windows`、导出 JSON 和 CSV 的窗口数一致；
  - 抽样窗口全行对账；
  - 页面保留 500 个；
  - 没有故障记录，也没有停止面板。
- **记录、不设门槛**：前 1,000 个与后 1,000 个窗口的往返耗时 p50 / p95、浏览器 JS 堆大小、数据库文件大小。
- 证据写进 `docs/evidence/<date>/perf/long-session/`。

### S7：PERF-01 与新鲜度阈值敏感性

- `scripts/perf01.py` 用 Playwright 驱动 Live，运行 ≥ 600 个窗口。
- **采集**：
  - 前端计时缓冲：截帧到发送、网络加服务端、渲染；
  - `Server-Timing`：预处理、视觉、遥测、融合、提交。
- **输出**：capture → render 的 p50 / p95 与原目标对照，原目标的含义（最坏值还是 p95）见审计 D07，未经用户确认不得改写。
- **2 / 3 / 5 s 敏感性**：用实测的证据年龄分布，计算在三个阈值下各自会过期的窗口比例。必须注明：遥测年龄 0–2000 ms 是回放分段造成的，不是传感器年龄。
- 证据写进 `docs/evidence/<date>/perf/`。

### S8：PERF-02（日志完整性，两个分母）

`scripts/perf02.py` 统计以下几个数：
- 客户端发出的请求数（tap 计数）；
- 服务端接受的请求数（201）；
- 数据库行数；
- 故障记录数；
- 不可用窗口数（按 CNT 的默认口径：算作已接收，outcome 记为 `unavailable`）。

再算两个分母下的完整性：
- **分母 1**：已接受的请求中，有数据库记录的比例；
- **分母 2**：符合条件的请求中，有成功记录或故障记录的比例。

运行时注入一段传输故障与一次后端重启，复用 FIX-BACKEND-REACH 的方法，然后核对完整性。

### S9：G-W6-A 证据归档

`docs/evidence/<date>/perf/README.md`，把 G-W6-A 的每一项对应到 S6–S8。E2–E5 runner **不在本计划内**，如实标为未完成：配对规则依赖审计 D06 的导师决定。
