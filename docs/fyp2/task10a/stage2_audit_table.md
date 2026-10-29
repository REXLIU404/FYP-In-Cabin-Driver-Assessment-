# Task 10A Stage 2（Paired System Comparison）：实现方自审表

- **实现方**：DeepSeek 写 runner（DS-2，`6df94ef`）；Claude 负责集成（合并 `dd7b9d5`，修复一条 e2e 测试 `fbc9593`；按 A2 审计修 runner `bf76ddf`）和官方运行。
- **现行官方运行**：`docs/evidence/2026-10-29/comparison-official-bf76ddf/`（`bf76ddf`）。`comparison-official/` 已被取代。
- **日期**：2026-10-29。
- **协议**：`docs/fyp2/task10a/comparison_protocol.json`，sha256 `b63050221c46…`。用户已批准（FUD-02 至 FUD-05，`approval_record.json`）。

## 1. 规格 Stage 2 的审计点

| 审计点 | 证据 | 结果 |
|---|---|---|
| 协议文件存在，且早于 runner 运行；内容含输入哈希 | `comparison-official-bf76ddf/comparison_results.json` 中的 `protocol_gate.checks` 四项都为 true（approval_status、protocol_status、sha_match、mtime_before_run）；`protocol_mtime_ns < run_start_epoch_ns`；运行后协议哈希没有变（`protocol_after_run.unchanged = true`）；协议的 `input_set` 含成员哈希 | 满足 |
| 输入集哈希可以复算 | `recomputed_membership_sha256 = 601dc3ed…`，与协议一致；另外复算了 `recomputed_source_ids_sha256` 与 `recomputed_image_bytes_manifest_sha256`（200 张原始 JPEG 逐张核对） | 满足 |
| 两次运行之间状态隔离 | 每个模型一个独立子进程，各用新建的临时 SQLite（见 `worker_spec_*.json`），注入合成时钟。**确定性复核**：DeepSeek 在 `94c6d14` 上的运行（`docs/evidence/2026-10-29/comparison/`）与集成后在 `c0c6d43` 上的官方运行，3 个模型 × 200 个窗口逐字段比较，RiskScore、RiskLevel、DominantEvidence、AlertSeverity、argmax、概率等的**差异为 0** | 满足 |
| 结果与 P4 的已知事实一致（c9 是弱类） | 同一组 stable200 的 c9 图片，三个模型的 argmax 分布各不相同：stable `{0:6, 7:4, 9:10}`、RN `{0:3, 9:17}`、MN 候选 `{0:3, 7:7, 9:10}`；`identical_results = false` | 满足 |

## 2. 描述性结果

不评胜负，不设单一分数门槛，也不切换默认模型。

| 对比 | argmax 一致率 | RiskLevel 不同的窗口 | AlertSeverity 不同的窗口 | DominantEvidence 不同的窗口 |
|---|---|---|---|---|
| RN − stable | 0.91 | 5 | 12 | 5 |
| MN 候选 − stable | 0.90 | 6 | 13 | 6 |

各模型的 RiskLevel：stable 为 Low 27 / Medium 173；RN 为 Low 24 / Medium 176；MN 候选为 Low 23 / Medium 177。

## 3. 限制（来自协议与 D06，结果文件中逐条记录）

- 这是**构造的评估场景**：10 个类别各 20 张，依次排成块。类别块边界上的迁移由这个顺序和 EMA 的延续造成，不是真实的停留时间。
- 遥测固定用一行（FUD-04，Safe 行），所以两个分支里只有视觉在变化；遥测的非安全概率接近 0，融合权重各 0.5，RiskScore 最高约 50。**因此这个场景从设计上就到不了 High，也测不到 HIGH_ALERT。** 它不能用来说明多模态的一般收益。
- argmax 一致率是模型之间的一致程度，不是准确率；它也不说明哪个模型更安全。

## 4. 偏离与修正

- runner 由 DeepSeek 在 `94c6d14` 上开发并试跑；官方运行在集成后的 `c0c6d43` 上重做，两次结果完全一致。
- 合并后的第一次门禁（`dd7b9d5`）有 1 条 e2e 测试失败，单独运行 3/3 通过。原因是测试统计的是「服务器已应答」的请求，暂停前已在途的请求可能在快照之后才得到应答。已改为在途请求落地之后，统计页面「发出」的请求（`fbc9593`）。修复后门禁全绿：pytest 1341 / 0 skipped，vitest 1022（`docs/evidence/2026-10-29/merge-ds2-gate/`）。红灯那次保留在 `merge-ds2-gate-RED-dd7b9d5-flaky/`。

## 5. A2 独立审计（第一轮：PARTIAL）及处理

审计员的结论是 PARTIAL：Stage 2 的四个审计点它都独立重跑并通过，自己的运行与已提交的运行逐字段相同；没过的原因是一条。

| 发现 | 处理 |
|---|---|
| F-1：协议要求运行后重新计算协议哈希，runner 声称做了，实际没做 | 已修复（`bf76ddf`）：`post_run_protocol_check`，结果字段为 `protocol_after_run`；先写测试、看到它失败，再修复；重做官方运行。实现方 README 已加更正说明 |
| F-2：输入只在父进程核验一次 | 已修复：每个模型运行前重新核验，结果记在 `pre_run_input_verification` |
| F-3：没有记录父命令 | 已修复：`parent_command` |
| F-4：子进程继承了其他 `DRA_*` 变量 | 已修复：`worker_env` 先清掉所有 `DRA_*` |
| F-5：`mean_abs_prob_delta` 实际是「逐窗口最大绝对差」的均值 | 不改字段名，以免改动结果的格式；报告引用时按真实含义写 |
| FUD-A：U-1 只有推断出的放行记录 | 用户 2026-10-29 明确回复「通过」 |
| FUD-B：固定的 Safe 遥测行让场景到不了 High，也测不到 HIGH_ALERT | 用户 2026-10-29 决定：按现状接受；报告只用几句话说明这个限制 |
| FUD-C：报告不能写成 RN 的 c9 弱点已经消失（P4 中 RN pooled c9 F1 为 0.6059） | 报告措辞规则 |
