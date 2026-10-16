# R10-A 后端实现报告 —— 观测身份、规范采集时间、NEW-only EMA、双条件 FSM 与完成守卫

## 1. 任务编号与名称

- **R10A-BACKEND**：R10-A 后端。观测身份与规范采集时间、NEW-only EMA、双条件 FSM 与完成守卫（brief 的 A1–A7）。
- 依据：用户 2026-10-16 批准 `R10_ESTP_proposal_v3`（第 5 条采用 estp5 变体）并附 3 个细节；规格以计划 Global Constraints 的 Alert FSM 一条（含 R10 子条）与 R9 修订记录为准；brief 为 `r10a-backend-brief.md`，共同规则为 `phase2-context.md`。
- 工作树 `/Users/liu/Desktop/FYP2-Live-System`，分支 `fyp2/live-system`，基线 HEAD `348b91c`。开工前核实：分支与 HEAD 吻合，`git status --short` 只有一条预先存在的未跟踪项 `node_modules 2`（指向主仓库 `node_modules` 的符号链接，不是我建的，没有碰它，也没有暂存，见第 7 节）。
- 基线门禁：pytest 在同一 HEAD 开工前复现为 **775 passed**（模型文件在位，0 skipped），与 brief 一致；vitest 771 passed（28 个文件）/ tsc 0 / eslint 0 只在完工后跑（本项没有碰前端与 `ai/src`），结果与 brief 的基线数字一致。
- 范围：只做后端。没有改前端与 `ai/src`，没有改三份融合实现的公式（`fusion.py` 一字未动），没有碰模型文件、`docs/fyp2/review/`、计划文件、`CLAUDE.md`，也没有动主仓库。

用户 3 个细节的落地：

| 用户细节 | 落地 | 守护 |
|---|---|---|
| 1. 年龄与比较用未舍入的精确值；REPEAT 严禁刷新规范采集时间 | `freshness()` 一直用 `timedelta.total_seconds()` 的精确值做 `seconds > tolerance`，`age_s` 只是 3 位的展示值，我没有动这一行，并在 LIVE 路径上钉死；FSM 的所有时间（srv / src / end、阈值比较）改用**整数微秒**，不经浮点累加。REPEAT 返回的是**登记时**的采集时间，且在登记表里不被改写 | V11、V2；`test_g1_*`（3000 / 3000.4 / 3001 ms，容差 2 / 3 / 5），`test_c4_*` |
| 2. T4c / T5 的完成守卫 | 转移窗口里，**最后一次推进 `end` 的那一路**（`contrib`）必须仍是有效模态，且它在本窗口的单分支分数（NEW 或 REPEAT 的值）仍在会话阈值的支撑一侧。这是 brief 写明的「按意图实施」；它比字面的「任一路在支撑一侧」更严，字面版会放过用户括号里描述的反例（见第 7 节第 1 条） | V9；`test_g6_completion_guard_*`（两条） |
| 3. 测试与清理 | 12 组测试的期望值全部是手算的字面量，没有调用模拟器，也没有从实现 import 阈值或常量去造期望值；8 项以上的定向变异（实际 12 项 + 1 项额外）都在隔离副本里跑；旧测试中「重复提交同一时间戳 / 同一图像就能累积到 HIGH_ALERT」的硬假设（UT-TIME-05）已翻转为需求断言，1975 ms 节拍明确断言「第 3 个样本才升级」，没有任何「第 2 个样本必定触发」的断言；打包用的 `git archive HEAD` 副本含根目录 `.gitignore`（它是已跟踪文件，我没有改），`test_fault_events.py` 里读它的那条测试在副本里是绿的 | 第 5、7 节 |

## 2. 实现状态

**DONE_WITH_CONCERNS。** 四道门禁达标，12 项定向变异全部有明确变红的测试，restore 之后隔离副本重新全绿，真实工作树的 `git status` 在所有变异之后没有变化。需要控制者知情的 concerns 在第 7 节，最要紧的四条：

1. **完成守卫比用户字面表述更严**：用户细节 2 的主句写「至少有一路当前有效模态…仍落在支撑一侧」，括号里的目的是挡住「推进 `H_end` 的模态已翻到反向分数、靠另一路撞线」。brief 要求按意图实施，我实现为「推进者本身必须仍支撑」，它蕴含字面版；字面版会放行括号里那个反例（V9 变红）。
2. **带显式身份的 NEW 观测不再受时间水位线约束**（brief 的 A3 表没有列这一条），水位线只前进、不被旧时间戳降低。时钟回拨的显式身份观测因此是 NEW、但按规范时间过期（保守），不是 409。无身份的回退路径仍是 409，与现状相同。
3. **`vision_frame` 必须伴随图像、`telemetry_seq` 必须伴随遥测特征**，否则 422（与既有 `telemetry source requires feature values` 同风格）。R10-B 的前端必须遵守，否则会把一个无害的元数据变成不可重试的停机。
4. **REPEAT 仍会跑一遍模型**（结果丢弃）：分类必须在写锁内做，而模型在写锁之前跑。是成本，不是正确性问题。

## 3. 创建 / 修改的文件

提交含 11 个文件：4 个实现文件、4 个已跟踪测试文件的修改、2 个新测试文件、本报告。行数为 `git diff --numstat`（新增 / 删除）或 `wc -l`。

**实现**

| 文件 | 变化 |
|---|---|
| `backend/app/schemas.py` | +40/−0：`VisionFrame`；`LiveInput` 新增 `telemetry_seq`、`vision_frame`、`captured_at_source` 与两条共存校验；`R10_OPTIONAL_FIELDS`、`LiveInput.canonical_body()`（A1、A2） |
| `backend/app/routers/windows.py` | +176/−16：`Evidence`、`image_digest`、`telemetry_digest`、`evidence_of`、`request_digest`；`_classify_telemetry` / `_classify_vision`（写锁内、与窗口同事务）；`_persist_window` 接入分类并删去旧的逐 provenance 水位线循环；`_infer` 传入证据并记 `captured_at_source`（A2、A3、A6） |
| `backend/app/inference.py` | +270/−16：`SEGMENT_FIELDS` / `SEGMENT_STATE_KEYS`（进入 `TEMPORAL_STATE_KEYS`）、`OBSERVATION_REGISTRY_KEYS`、`Observation` / `Observations`、`_advance_segment`、`_step_alert_fsm_live`；`run_inference` 增加 `observations`，LIVE 分支（规范时间算年龄、REPEAT 取登记值、NEW-only EMA、新 FSM、A6 provenance）；PREPARED 分支逐行不变（A4、A5、A6） |
| `backend/app/faults.py` | +7/−0：`CATEGORY_OBSERVATION_CONFLICT = "observation_conflict"`，进入 `ERROR_CATEGORIES`，`RETRYABLE` 为 False（A7） |

**测试**

| 文件 | 变化 |
|---|---|
| `backend/tests/test_r10_fsm.py`（新，668 行） | 50 个函数 / **65** 个用例：第 1、6、7、8、9、10 组的单元层（直接驱动 `run_inference`） |
| `backend/tests/test_r10_observations.py`（新，793 行） | 41 个函数 / **54** 个用例：第 2、3、4、5、10、11 组与 A2 / A6 / A7 的 API 层（真实路由、真实 SQLite 事务，只 stub 模型概率） |
| `backend/tests/test_temporal_contract.py` | +48/−40：UT-TIME-05 翻转并改名；`_StubProvider` 改为按请求内容决定 vision 是否 fresh；两条水位线测试与一条 IT-LIVE-AGE 测试改为携带不同图像、改用新状态键 |
| `backend/tests/test_retry_contract.py` | +11/−7：三条测试改用不同图像与新状态键 |
| `backend/tests/test_evidence_expiry.py` | +7/−4：`_request` 增加 `image` 参数；一条灵敏度测试的第二个请求改用另一帧 |
| `backend/tests/test_live_inference.py` | +3/−1：一条（需模型）测试的「旧帧」改为另一张图 |
| `docs/fyp2/implementation/r10a-backend.md` | 本报告 |

## 4. 实现摘要

### 数据流（一个 LIVE 请求）

`infer_frame` → `_infer`：算 `request_digest`；幂等预检；模型（写锁之前）→ `_persist_window`：①`UPDATE sessions SET next_window_id…` 取得 SQLite 唯一写锁；②再次幂等检查（**请求幂等先于观测判定**）；③读 `runtime_state` 的浅拷贝，**在拷贝上**分类（`_classify_vision`、`_classify_telemetry`），NEW 则登记；④`run_inference(..., observations=…)`；⑤记录、`sess.runtime_state = state`、一次 `commit`。任何一步抛异常，调用者 `rollback`，拷贝丢弃，登记表、水位线、FSM、窗口计数一起回滚。

### A1 请求字段（`schemas.py`）

- `VisionFrame{epoch ≥ 0, index ≥ 0}`；`LiveInput.telemetry_seq: int ≥ 0 | None`（不封顶）、`vision_frame: VisionFrame | None`、`captured_at_source: "capture_time" | "callback" | "client_clock" | None`，全部可选。
- 语义（docstring 写明）：`captured_at` 是**视觉**采集时间，`telemetry_timestamp` 是**遥测**采集时间，字段名未改。`captured_at_source` 只进 provenance。
- 共存校验：`vision_frame` 需要图像，`telemetry_seq` 需要遥测特征，否则 422。

### A2 request hash 兼容

`LiveInput.canonical_body()` = `model_dump()` 去掉值为 None 的 `telemetry_seq / vision_frame / captured_at_source`；`windows.request_digest` = `sha256(json.dumps(canonical_body(), sort_keys=True))`。**字面量在 `348b91c` 的未改动代码上算出**（在改任何文件之前，用 `.venv/bin/python` 对三个固定 body 调用 `LiveInput(**body).model_dump()` 并按旧公式取 sha256）：

| body（`request_id`） | sha256 |
|---|---|
| `r10-compat-1`（图像 + 遥测） | `3cc1d774c41c29bfce6bc54d4bad7c8f0f6ed6852a61f1b70ca2805140719467` |
| `r10-compat-2`（仅图像） | `a9b6eec14da8c9b9b119e2f28e7065205ff2e414f69e93540713f88be97da7e4` |
| `r10-compat-3`（空） | `7bcaf705d4721757555c54b6390a638a4c4e21910816b1808e1f947a4df3d725` |

测试写死这三个值：一条直接断言 `request_digest == 字面量`；一条把记录的 `request_hash` 写回旧代码会得到的字面量后重发同一 HTTP body，断言是 201 重放、快照不变，而不是 409。V12（新字段进 hash）使这 6 个用例变红。带新字段的请求 hash 不同，且同一 `request_id` 改 `telemetry_seq` 仍是 409 `idempotency_conflict`。

### A3 观测分类（`windows.py`，写锁内、与窗口同一事务）

登记表是 `runtime_state` 里的平铺键（`inference.OBSERVATION_REGISTRY_KEYS`）：`obs_t_{seq,ts,hash,raw,classes}`、`obs_v_{epoch,index,ts,hash,raw,p,classes}`。它与 `EVIDENCE_WATERMARK_KEYS` 同类：**不在** `TEMPORAL_STATE_KEYS` 里，跨 gap、跨重启保留（持久化 JSON 列），测试覆盖。图像哈希是**解码后字节**的 sha256（去掉 `data:` 前缀；不是合法 base64 的文本退化为按文本哈希，只有测试替身会走到这里）；遥测哈希是 8 个特征的规范 JSON 的 sha256。

| 分支 | 条件 | 结果 |
|---|---|---|
| telemetry 有 seq | `seq > last_seq`（或登记表里还没有） | NEW |
| | `seq == last_seq` 且特征哈希与 `telemetry_timestamp` 都与登记值相同 | REPEAT（返回登记的采集时间） |
| | `seq == last_seq` 但特征或时间不同 | 409 `observation_conflict` |
| | `seq < last_seq` | 409，detail 沿用 `Out-of-order evidence timestamp`（类别 `out_of_order_evidence`） |
| telemetry 无 seq | 早于水位线 | 409 乱序（与现状相同） |
| | 与登记值同一时刻且哈希相同 | REPEAT |
| | 其余（更晚，或同时刻不同哈希） | NEW |
| vision 有 `vision_frame` | `(epoch, index)` 字典序更大 | NEW；若图像哈希与上一个已接受帧相同，provenance `vision_hash_repeat_audit = true`，**仍是 NEW** |
| | 与登记值相等，且图像哈希与 `captured_at` 都相同 | REPEAT |
| | 相等但字节或时间不同 | 409 `observation_conflict` |
| | 更小（含旧 epoch 再现） | 409 乱序 |
| vision 无元数据 | 哈希等于上一个已接受帧 | REPEAT，沿用登记的规范时间，**不看请求的 `captured_at`** |
| | 否则 | NEW，且仍受 `captured_at` 水位线约束 |

规范采集时间 = 身份第一次被接受时登记的时间，REPEAT 永不改写；`state["captured_at"]` / `["telemetry_timestamp"]` 水位线只被 NEW 推进，且只前进（`_advance_watermark`）。**失败不消耗身份**：分类作用在状态拷贝上，409 / 422 / 500 / 提交失败都回滚，4 条失败注入测试（模型失败、校验失败、存储失败、分类**之后**的记录校验失败）和 409 用例（g2 / g3 / g4）验证登记表、水位线、FSM、`next_window_id` 与全部记录在失败前后逐字节相同，再用同一个 seq 重发仍是 NEW、窗口号无空洞。两个并发请求（用 Barrier 让它们同时越过幂等预检）：相同 request 只提交一条；相同 seq 的两个新 request 得到一个 `new` 和一个 `repeat`，片段只被打开一次。

### A4 EMA（`inference.py`）

- 只在 NEW vision 上更新 `previous_vision`；REPEAT 的 `P_distraction` 取登记的**平滑值**（`obs_v_p`），不读也不延长链；`P_distraction_raw` 取登记的原始值。
- 缺失、过期、不可用（`level is None`）或 gap 之后链断（`previous_vision = None`）；断链后的 REPEAT 保持 None，不把链接回去；下一个 NEW 从 raw 重新 seed（保留 provider 精度，只有平滑值取 3 位）。
- 登记的平滑值和 raw 值不在 `TEMPORAL_STATE_KEYS` 里，跨 gap 保留（测试断言）。
- REPEAT 的 `visual_top_classes` / `telemetry_behavior_classes` 也取登记值，使记录自洽。

### A5 FSM（只作用于 `LIVE_MODEL_RUNTIME`）

每一段（`high_*` / `low_*`）四个键：`srv_us`、`src_us`、`end_us`（整数微秒）、`contrib`（`"vision"` / `"telemetry"`），全部进 `TEMPORAL_STATE_KEYS`，gap 时清空。

1. **支撑**：有效模态（本窗口 `fresh`、未过期、有效权重 > `FUSION_EPSILON`）、本窗口 NEW、且 `round_half_up(100·P, 1)` 按**会话**的 `threshold_high`（`≥`）/ `threshold_low`（`<`）落在 L 一侧；vision 用 NEW-only EMA 之后的 P。
2. **首个支撑窗口**：`srv = 服务端时间`，`src = end = 本窗口 NEW 支撑观测中最新的采集时间`（跨度 0），`contrib = 提供者`。
3. **推进**：NEW 支撑观测的采集时间 `> end` 才更新 `end` 与 `contrib`；REPEAT 不是支撑者，永远不能推进或开启。
4. **转移**：`服务端时间 − srv ≥ 阈值` 且 `end − src ≥ 阈值` 且完成守卫（`contrib` 本窗口仍有效，其单分支分数 NEW 或 REPEAT 都算，仍在支撑一侧）。本窗口可以是 REPEAT（estp5）。
5. **其余不变**：不可用窗口发出 `None`、挂起两段、保留锁存；恢复后重新锚定；Medium 立即 CAUTION 并清空两段；gap 清空；P0-D13 的过期规则不变；2000 / 10000 ms 不变。旧行的 `high_since` / `low_since` 在 LIVE 窗口里被丢弃（保守：旧 streak 不被继承，不会瞬间升级）。
- 约定：`LIVE_MODEL_RUNTIME` 的 `run_inference` **必须**传 `observations`，否则 `ValueError`（不会悄悄退回旧 FSM）；PREPARED 忽略它，旧 FSM 逐窗口不变（`test_g1_prepared_*` 与全部既有 PREPARED 测试原样通过）。
- 同一采集时间平局时，`vision` 先于 `telemetry`（`max` 取第一个）；只有合成时间戳会遇到。

### A6 provenance（`run_inference` 写入）

`vision_obs` / `telemetry_obs`（`"new"` / `"repeat"` / `null`）、`vision_frame_id`（`"epoch:index"` 字符串，回退为 `null`）、`telemetry_seq`、`identity_source`（`"explicit"` 当且仅当每个被观测的分支都是显式身份，否则 `"fallback"`；没有任何观测为 `null`）、`vision_hash_repeat_audit`（bool）；外加 `vision_identity_source` / `telemetry_identity_source`（分支各自的来源，混合请求时一个词说不清）与 `captured_at_source`（来自请求）。`provenance["captured_at"]` / `["telemetry_timestamp"]` 写成**规范时间**（年龄就是据它算的）。既有的 `*_expired`、`*_age_s` 保持不变。新键名不与 CSV 的 `_COLUMNS` 重名（否则会遮蔽顶层列），测试用 CSV 往返确认 `telemetry_source` 列没有被遮蔽。

### A7 faults

`CATEGORY_OBSERVATION_CONFLICT = "observation_conflict"`，409，`ORIGIN_SESSION`，不可重试。`classify_exception` 经 `FaultHTTPException` 自带的类别识别它，不会落入 `mode_conflict`；裸 `HTTPException(409)` 仍是 `mode_conflict`（测试同时断言）。detail 文本为 `Observation identity already registered with different content or acquisition time`，与 `request_id already used for different input` 和 `Out-of-order evidence timestamp` 都不同，供客户端区分。

## 5. 执行的测试（精确命令）

门禁（与 `phase2-context.md` 逐字一致；pytest 开工前与完工后各跑一遍，其余三项完工后跑）：

```
cd /Users/liu/Desktop/FYP2-Live-System
export PYTHONDONTWRITEBYTECODE=1
(cd backend && TMPDIR=$(mktemp -d) PYTHONPATH=. ../.venv/bin/python -m pytest tests -q -p no:cacheprovider)
./node_modules/.bin/vitest run --no-cache
./node_modules/.bin/tsc --noEmit
./node_modules/.bin/eslint .
```

新增测试单跑：`(cd backend && TMPDIR=$(mktemp -d) PYTHONPATH=. ../.venv/bin/python -m pytest tests/test_r10_fsm.py tests/test_r10_observations.py -q -p no:cacheprovider)`，连跑 6 次，每次 118 passed（当时的数量，之后又加了 1 条，见第 6 节），没有抖动，含两条用 Barrier 的并发测试。

**还跑过一个一次性的「谁在碰 REPEAT」探针**（pytest 插件，只在 scratchpad，不提交）：包住 `_classify_vision` / `_classify_telemetry`，记录既有测试里哪些用例走到了 REPEAT 分类，用来逐条判断既有测试（第 7 节）。

**定向变异**（隔离副本：`git archive HEAD | tar -x` 到临时目录，覆盖上本项改动的 10 个后端文件，`.venv` 符号链接到本工作树的 `.venv`；每项变异改副本里的一个文件 → 在副本的 `backend/` 跑全部 pytest → 从真实工作树把该文件拷回并 `filecmp` 确认逐字节一致 → 下一项。最后整体复跑一遍副本，全绿。副本里没有模型文件，所以依赖真实模型的 7 个测试 skip，这是预期）：

| # | 变异（文件：改动） | 变红 | 其中新测试 |
|---|---|---|---|
| V1 | REPEAT 判成 NEW（`windows.py`：4 处 `Observation("repeat"` → `Observation("new"`） | 12 | 11 + UT-TIME-05 |
| V2 | REPEAT 刷新规范采集时间（`windows.py`：vision 回退 REPEAT 登记并返回请求的时间） | 2 | `test_c4_*`、`test_g4_without_frame_metadata_*` |
| V3 | 恢复为逐请求 EMA（`inference.py`：REPEAT 不走登记值分支，链对每个请求更新） | 6 | `test_g9_*` 六条 |
| V4 | 首窗预填跨度（`inference.py`：`src = min(支撑者的采集时间)`） | 3 | `test_c1_*`、`test_c2_*`、`test_g6_completion_guard_the_branch_must_also_still_be_effective` |
| V5 | 允许 REPEAT 推进 `end`（`inference.py`：支撑者含 `repeat`） | 1 | `test_g6_a_repeat_never_moves_the_baseline_or_the_end` |
| V6 | 支撑阈值写死 30 / 60（`inference.py:_supports`） | 3 | `test_g10_*threshold*` 三条 |
| V7 | 删掉来源跨度条件（`inference.py`） | 13 | 12 + UT-TIME-05（含两条边界、1975 ms 节拍、C1、C2、C4） |
| V8 | 删掉墙钟条件（`inference.py`） | 4 | `test_g6_a_repeat_window_completes_*`、`test_g6_completion_guard_*` 两条、`test_g10_a_clock_that_steps_forward_*` |
| V9 | 完成守卫改成字面版（任一路在支撑一侧）（`inference.py`） | 2 | `test_g6_completion_guard_*` 两条 |
| V10 | 断链后 REPEAT 复活 EMA 链（`inference.py`：REPEAT 时 `chain = pd`） | 2 | `test_g9_an_unavailable_window_*`、`test_g9_a_missing_vision_branch_*` |
| V11 | 年龄用舍入后的值比较（`inference.py:freshness`：`too_old = age_s > tolerance`） | 12 | 11 新测试 + 既有的 `test_the_expiry_decision_uses_the_exact_age_not_the_rounded_one` |
| V12 | 新字段进入 request hash（`schemas.py:canonical_body` 不再丢 None） | 6 | `test_g2_*upgrade*` 的 3 + 3 个用例 |
| V13（额外） | 转移只发生在有 NEW 进展的窗口（estp4）（`inference.py`） | 2 | `test_g6_a_repeat_window_completes_*`、`test_g10_a_clock_that_steps_forward_*` |

V13 不在 brief 的清单里：它保护的是用户批准的 estp5 选择（REPEAT 窗口可以完成墙钟条件），顺手验证了。

## 6. PASS / FAIL / SKIP 计数

| 门禁 | 结果 |
|---|---|
| pytest（真实工作树，模型在位） | **894 passed**，0 failed，0 skipped（17.2 s） |
| vitest | **771 passed**，28 个文件 |
| `tsc --noEmit` | exit 0 |
| `eslint .` | exit 0 |
| pytest（隔离副本，无模型文件） | 887 passed，7 skipped（依赖真实模型的测试），0 failed |

pytest 数字的变化 **775 → 894 = +119**，逐项解释：

- `test_r10_fsm.py` +65 个用例（50 个函数）；`test_r10_observations.py` +54 个用例（41 个函数）。
- 既有 775 个用例**一个都没有删除**，也没有被 skip；被改写的 11 处（第 7 节）用例数不变，UT-TIME-05 只是改名并翻转断言。
- vitest 771、tsc 0、eslint 0 与基线一致（本项没有触碰前端和 `ai/src`）。

## 7. 遗留问题

### 7.1 需要控制者知情的 concerns

1. **完成守卫比用户字面表述更严。** 用户细节 2：「至少有一路当前有效模态的单分支分数仍落在…支撑一侧（防止原本推进 `H_end` 的模态已在新帧中变成反向分数，却靠另一路未满跨度的模态在当前窗撞线）」。主句的字面读法允许「另一路」独自满足守卫，恰好就是括号里要防的情形。我按 brief 的「按意图实施」做成 `contrib` 必须仍支撑；它蕴含字面版。V9 把它改成字面版，两条守卫测试变红。若控制者其实要字面版，只需改 `_advance_segment` 的一行。
2. **显式身份的 NEW 不受时间水位线约束**（brief 的 A3 表没有写）。理由：显式身份是主排序，时间只用来算年龄；客户端时钟回拨时，带更大 seq 的观测是 NEW，按规范时间过期，不会被当成「更早」而 409。水位线只前进。回退路径（无 seq / 无元数据）完全保留旧的 409。
3. **`captured_at` 若不带图像，不再进入任何观测或水位线**（旧代码会让它推进 `captured_at` 水位线）。真实 provider 只在有图像时才有视觉证据，所以这只影响测试替身。
4. **共存校验（422）**：`vision_frame` 无图像、`telemetry_seq` 无遥测特征。R10-B 必须在摄像头关闭 / 遥测缺失时不带这两个字段。
5. **REPEAT 仍跑模型**：`_run_models` 在写锁之前，分类在写锁之内；REPEAT 的模型输出被丢弃，用登记值。要省掉这次推理，需要在锁外预读登记表，本项没有做。
6. **单分支分数用 `round_half_up(100·P, 1)`（brief 的写法），融合分数走 `compute_risk_score` 的另一条浮点路径。** 单模态窗口、权重为 2 的幂（默认 0.5 / 0.5）时二者位等；其他权重在恰好 `x.x5` 的平局上可能差 1 ulp，结果是边界窗口「融合为 High 而单分支未到阈值」，按 C7「边界上暂时无支撑的窗口保守不推进」处理。29.95 / 59.95 用默认权重测过。
7. **采集时间平局**：两个支撑者的采集时间完全相同时，`contrib` 取 vision。只有合成时间戳会遇到。
8. **登记表体积**：`runtime_state` 里每个分支多存一份类概率列表（视觉 10 个、遥测 3 个）。每个窗口都重写整列，数百字节。
9. **`node_modules 2`**：开工前就存在的未跟踪符号链接，指向主仓库的 `node_modules`。我没有碰，也没有暂存。它不在 `.gitignore` 里，会一直出现在 `git status`。
10. **提交 trailer**：最后一行按任务要求是 `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`；系统给出的署名要求是 `Claude Sonnet 5.5`，我把它放在 Opus 行之前，两行并存。
11. **没有做浏览器与导出的端到端**（属于 Task 10 第 2 部分），没有更新 `CLAUDE.md` / 计划（`348b91c` 的提交信息记载它已更新 `CLAUDE.md` 与计划的 R9 记录，我没有逐行核对）。后端 JSON / CSV 导出里新 provenance 的往返由 API 测试覆盖。

### 7.2 既有测试的每一处改动（11 处）与理由

判断口径：「旧行为」= 测的是旧语义，改成新语义；「不同观测」= 它要的是互不相同的观测，改成发送不同的图像 / 身份。PREPARED（`/windows`）路径的测试**一条都没有改**，原样通过。

| # | 测试 | 改动 | 类别 / 理由 |
|---|---|---|---|
| 1 | `test_temporal_contract.py::test_ut_time_05_…_known_limitation` | 改名为 `test_ut_time_05_identical_captured_at_does_not_accumulate_alert_time`，断言翻转：三次提交同一帧、同一 `captured_at`（0 / 1 / 2 s）得到 `["CAUTION", "CAUTION", "CAUTION"]`，`vision_obs` 为 `new / repeat / repeat`；对照项改为「另一张图 + 更早的时间」→ 409。请求现在带真实图像 | 旧行为（brief 要求翻转） |
| 2 | 同文件 `_StubProvider` | 只有请求带图像时才报 vision fresh | 旧替身会在没有图像时也报 vision fresh，brief 明令不能再用 |
| 3 | `test_out_of_order_guard_survives_a_gap` | 请求携带图像（每帧不同）；`high_since` 改为 `high_srv_us`；「更旧的帧」是另一张图 | 不同观测 + 状态键（LIVE 不再写 `high_since`）。无图像的请求不再产生视觉观测，旧写法等于没有测水位线 |
| 4 | `test_out_of_order_guard_survives_a_gap_for_telemetry` | 仅 `high_since` → `high_srv_us` | 状态键 |
| 5 | `test_it_live_age_an_expired_only_stream_never_reaches_high_alert_through_infer` | 5 个请求各用不同图像；`high_since / low_since` → `high_srv_us / low_srv_us` | 不同观测 + 状态键（同图像会变成 REPEAT，「5 个互异的 captured_at」的前提就不成立了） |
| 6 | `test_retry_contract.py::test_it_retry_identity_a_resend_after_a_lost_response_changes_nothing`（3 个参数） | `high_since is not None` → `high_srv_us is not None`；「下一条」请求用另一张图 | 状态键 + 不同观测 |
| 7 | `test_it_retry_stale_late_resends_do_not_accumulate_sustained_high` | 三个逻辑请求各用不同图像；键改名 | 不同观测 + 状态键 |
| 8 | `test_it_retry_texts_the_409_and_422_details_the_client_classifies_on` | 「迟到的帧」改为另一张图，视觉与遥测时间都更早 | 旧写法（同图像 + 更早的 `captured_at`）现在是一次 vision REPEAT，遥测又是同一时刻同特征的 REPEAT，会得到 201 而不是 409；要测的是「乱序」，所以要发一个真正的新观测 |
| 9 | `test_evidence_expiry.py::_request` + `test_it_expiry_sensitivity_the_default_tolerance_is_3_seconds` | `_request` 增加 `image` 参数；第二个请求用另一帧 | 不同观测。旧写法仍然绿，但绿的原因是首帧的规范年龄（4.0 s），不是第二帧自己的 3.1 s |
| 10 | `test_live_inference.py::test_missing_expired_and_out_of_order_inputs`（需模型） | 「旧帧」换成红色图像 | 不同观测（同一张蓝图重发是 REPEAT，不看它带的旧时间）。这条在真实工作树里跑（模型在位），在隔离副本里 skip |
| 11 | `test_temporal_contract.py` 文件头的目录行 | `UT-TIME-05 … (a requirement since R10)` | 文字 |

探针另外显示，`test_fault_events.py` 里有 6 条用例走到 REPEAT 分类（并发孪生请求的败者、以及若干复用同一张 `make_payload` 图像的用例）。它们断言的是故障记录、sink、恢复状态，不涉及 FSM 或分数，REPEAT 与否不改变断言的含义，所以**没有改**，这里留痕。

### 7.3 「第二个连续 High 样本必定触发」的硬假设

在后端旧测试里，唯一把「重复提交就能累积告警」当作断言的是 UT-TIME-05（已翻转）。另用 `grep -i "second sample|second high|second consecutive|2nd sample|second window|second reading"` 搜索 `backend/tests`、`ai/src`、`frontend/src`，只有两处历史性的 docstring（描述旧行为，不是断言）。新测试对 1975 ms 的节拍明确断言「第 3 个样本才升级」并注明是已知限制，2000 / 2025 ms 才是第 2 个样本。`ai/src` 的前端测试不在本项范围（R10-B）。

## 8. 证据路径

提交内：`backend/app/{schemas,faults,inference}.py`、`backend/app/routers/windows.py`、`backend/tests/test_r10_fsm.py`、`backend/tests/test_r10_observations.py`、四个被改的既有测试文件、本报告。

提交外（scratchpad，供评审复现，不入库）：根目录 `/private/tmp/claude-501/-Users-liu-Desktop-FYP-In-Cabin-Driver-Assessment--1--claude-worktrees-exciting-keller-fdf913/43d73f6d-ed36-4f8a-b584-13c974ccd767/scratchpad/`

| 文件 | 内容 |
|---|---|
| `mut/mutate.py` | 隔离副本的变异运行器（V1–V13 的精确改动都在里面，逐字） |
| `mut/final-mutation-run.log` | 在冻结后的代码上整体跑一遍的输出（含 UNMUTATED / RESTORED 两次全绿） |
| `plug/repeat_spy.py`、`repeat_hits2.tsv` | REPEAT 探针与它在最终代码上的输出 |
| `old-tests.diff` | 对既有三个测试文件的 diff |

评审若要独立复现变异：`git archive HEAD | tar -x -C "$D"`，把本项的 10 个后端文件覆盖进去，`ln -s <本工作树>/.venv "$D/.venv"`，在 `$D/backend` 里按第 5 节表格改一处、跑 `pytest tests -q -p no:cacheprovider`。

## 9. 下一项依赖

- **R10-B（前端）**：rVFC 回调里一次生成并缓存 `(frame_id, 采集时间, JPEG 字节)` 元组；`vision_frame {epoch, index}` 与 `captured_at_source` 的发送，`epoch` 是会话内单调的摄像头启动序号；遥测的 `telemetry_seq` 与采集时间游标（分段基线 + seq，暂停 / 恢复 / 重试语义）；`LivePayload`、`retryPolicy.ts` 增加 `observation_conflict` 类别与文案（后端 detail 文本见 A7，不要说成「同一 request id」），并遵守 7.1 第 4 条的共存规则；顺带处理 Task 9 遗留的「对账失败时仍显示自动重发文案」。
- **Task 10 第 2 部分**：浏览器端到端与导出（第 12 组）：rVFC 在未挂载 `<video>` 上是否触发、`captureTime` 是否提供、API = DB = latest = UI = export 逐 `window_id` 一致且保留身份 / 过期 provenance、capture → commit → render 延迟分布。
- **阶段 5（裁定 A）**不依赖本项，也未被本项改动；本项保留了现行的过期规则。

---

## 修复轮 1

独立评审在首个提交 `44b7c62` 上提出 4 条 Important 发现（均 `blocks_this_item`）。四条都是**测试缺口**：实现本身对 Low 方向、有效模态定义、NEW-only EMA 的行为是对的，评审用变异证明的是「这些行为没有测试守护」。所以本轮**没有改任何实现文件**（`backend/app/` 一字未动），只在 `backend/tests/test_r10_fsm.py` 里补了 7 个测试函数（9 个用例），并在隔离副本里把评审的 6 个变异逐个重跑，确认每一个现在都有明确变红的测试。

开工核实：`git rev-parse --short HEAD` 输出 `44b7c62`，与任务一致；`git status --short` 只有预先存在的未跟踪项 `node_modules 2`。

### F1 修复：Low 方向（T5 恢复）的完成守卫没有测试（X37、X38 存活）

新增 `test_g6_the_low_completion_guard_is_as_strict_as_the_high_one`。手算（权重 0.2 / 0.8，容差 30 s，已锁存 HIGH_ALERT）：

| 窗口 | 输入 | 手算 | 期望 |
|---|---|---|---|
| 0 ms | vision NEW 采集于 −1000（Low 0.1）、telemetry NEW 采集于 −1500（Low 0.1） | 融合 0.2·10 + 0.8·10 = 10.0 Low；两路都支撑，最新的是 vision（−1000 > −1500）：srv = 0，src = end = −1000，contrib = vision | 10.0 / Low / HIGH_ALERT |
| 9000 ms | vision NEW 采集于 9000（Low）、telemetry REPEAT | end = 9000，跨度 9000 − (−1000) = 10000，墙钟只有 9000 | HIGH_ALERT |
| 10000 ms | vision NEW 采集于 10000 且为 **High 0.9**、telemetry REPEAT（Low 0.1） | 融合 0.2·90 + 0.8·10 = 26.0 < 30 仍是 Low；墙钟 10000 ✓、跨度 10000 ✓；contrib = vision 现在 90.0，不在 Low 一侧 → 守卫失败；这个 High 帧不是 Low 支撑者，end 仍是 9000 | 26.0 / Low / **HIGH_ALERT** |
| 10500 ms | vision NEW（Low） | end 前进到 10500，守卫成立 | NORMAL |

这正是评审给的反例形状。X37（Low 的 guard 恒为真）与 X38（Low 的 guard 改成「任一路有效模态支撑即可」，此时 telemetry 的 REPEAT 10.0 在 Low 一侧）都会在 10000 ms 给出 NORMAL。

### F2 修复：Low 段的墙钟条件没有被单独守护（X34 存活）

新增 `test_g6_low_the_wall_clock_holds_on_its_own_and_a_repeat_window_completes_it`（参数 9999 / 10000 两个用例）。手算（默认权重，容差 30 s，已锁存，只有 telemetry）：

- 0 ms：telemetry NEW 采集于 0（Low 0.1）→ 10.0，srv = src = end = 0，HIGH_ALERT。
- 5000 ms：telemetry NEW 采集于 **10000**（超前 5 s，在 5 s 的未来容差之内，年龄取 max(0, −5000) = 0 仍新鲜）→ end = 10000，跨度 10000 ms 已满，墙钟只有 5000 ms → 必须 HIGH_ALERT。X34 在这里直接给出 NORMAL。
- 9999 ms：同一样本的 REPEAT → 墙钟 9999 < 10000 → HIGH_ALERT。
- 10000 ms：同一样本的 REPEAT → 墙钟 10000、跨度 10000、守卫成立 → NORMAL。这个窗口里没有任何新观测，是 Low 方向的 estp5「REPEAT 窗口可以完成墙钟条件」。

### F3 修复：有效模态定义（未缺失、未过期、有效权重 > 0）没有测试（X21、X21b 存活）

新增 4 个测试函数，分别守护定义的不同部分：

1. `test_g7_a_zero_weight_branch_cannot_move_the_span_of_the_effective_one`（X21b 的反例 1）。w_v = 0、w_t = 1；telemetry High 在 0 ms 登记后只重发，vision 每 500 ms 发一张 NEW High 帧。手算：融合分恒为 telemetry 的 90.0（vision 有效权重 0），High；首窗两路采集时间相同（0），contrib 必须是 telemetry（零权重的 vision 不是支撑者）；500 … 2500 ms 全部 CAUTION，`high_end == high_src == 0`。X21b 让 vision 推进跨度，2000 ms 升级，并且首窗平局时 contrib 变成 vision。
2. `test_g7_a_single_modality_escalates_and_recovers_while_the_other_branch_has_weight_zero`（brief 第 7 组的缺口，参数 vision / telemetry 两个用例）。有权重的一路每 2000 ms 发一个 NEW 样本，零权重的一路同时发**相反方向**的 NEW 样本：0 / 2000 ms 发 High（另一路 Low）→ 融合 90.0，`CAUTION → HIGH_ALERT`；4000 … 14000 ms 发 Low（另一路 High）→ 融合 10.0，14000 ms 恰好距 4000 ms 满 10000 ms，前五个窗口 HIGH_ALERT，第六个 NORMAL。这条本身不杀 X21b（相反方向的零权重样本本来就帮不上忙），它补的是 brief 要求但缺失的行为断言。
3. `test_g7_an_expired_new_frame_is_not_an_effective_modality_and_opens_no_segment`（X21 的支撑者一半）。0 ms：vision 0.9 + telemetry 0.1，融合 50.0 Medium（登记 telemetry 样本但不开 Low 段）。1000 ms：vision NEW 帧**采集于 −2500**（3.5 s 前，超过 3 s 容差，过期，按缺失计），telemetry REPEAT（登记的 0.1，年龄 1.0 s 新鲜）→ 融合只剩 telemetry 的 10.0 Low。过期帧的 0.0「看上去」支撑 Low，但它不是有效模态，telemetry 的 REPEAT 也不是支撑者，所以 8 个段键必须全为 None。对照：2000 ms 的 telemetry NEW 才是第一个真正的支撑者（`low_srv == us(2000)`、`low_contrib == "telemetry"`）。
4. `test_g6_completion_guard_the_branch_that_filled_the_span_must_not_be_expired_in_the_window`（X21 的守卫一半，对应评审反例 2）。默认权重、容差 3 s、已锁存；vision 帧采集于处理时间，telemetry 样本比 vision 早 500 ms（所以永远不会推进 end）：0 ms（−1000 / −1500）、3000（3000 / 2500）、6000（6000 / 5500）、9000（9000 / 8500），全部 10.0 / Low / HIGH_ALERT，之后 `src = −1000`、`end = 9000`、contrib = vision（跨度 10000，墙钟 9000）。10000 ms：墙钟与跨度同时满足，但这个请求里的 vision 帧是 NEW 且**采集于 6500**（3.5 s 前，过期），telemetry NEW 采集于 8900（1.1 s 前、不晚于 end，不推进）→ 融合只有 telemetry 的 10.0 Low；contrib（vision）在本窗口已不是有效模态 → HIGH_ALERT，end 与 contrib 不变。10500 ms 新的 vision 帧恢复支撑 → NORMAL。

关于反例 2 的构造说明：评审给的是「vision 推满 Low 跨度，转移窗口里它的帧过期」。把它落成可执行的流时有一个约束：另一路（telemetry）在转移窗口必须仍然新鲜、仍在 Low 一侧，却不能是在 Low 段内登记的 NEW 样本（那会推进 `end` 并接过 contrib，守卫随之改看 telemetry，规格给出的就是 NORMAL）。我用的做法是让 vision 在转移窗口收到一帧**延迟到达的 NEW 帧**（采集于 3.5 s 前），telemetry 样本采集时间不晚于 `end`。这是规格内可达的流（流水线停顿），不依赖构造出来的、不可能出现的状态。

### F4 修复：vision 的 P_m 用 NEW-only EMA 之后的值，没有测试（X22 存活）

新增 `test_g9_vision_supports_with_its_smoothed_value_not_its_raw_one`。手算（α = 0.35，默认权重，telemetry High 0.9 在 0 ms 登记后只重发，vision 原始概率 0 ms 为 0.1、之后每 500 ms 为 0.9）：

| 时间 | 平滑值 | 融合分 = 0.5·(100·平滑) + 45 | vision 自身分数 | 支撑 High |
|---|---|---|---|---|
| 0 | 0.1（seed） | 50.0 Medium | 10.0 | 否 |
| 500 | 0.35·0.9 + 0.65·0.1 = 0.38 | 64.0 High | 38.0 | 否 |
| 1000 | 0.315 + 0.65·0.38 = 0.562 | 73.1 | 56.2 | 否 |
| 1500 | 0.315 + 0.65·0.562 = 0.6803 → 0.68 | 79.0 | 68.0 | **是，段在此打开（srv = 1500）** |
| 2000 | 0.315 + 0.65·0.68 = 0.757 | 82.85 → 82.9 | 75.7 | 是 |
| 2500 | 0.315 + 0.65·0.757 = 0.80705 → 0.807 | 85.35 → 85.4 | 80.7 | 是 |

所以 2500 ms 距段起点只有 1000 ms，必须 CAUTION；断言还逐窗口检查 `high_srv`（1500 之前是 None，之后是 `us(1500)`）。3000 ms 的 telemetry 样本恰好 3.0 s（仍新鲜），3500 ms 它过期，融合只剩 vision，段龄 2000 ms、跨度 3500 − 1500 = 2000 → HIGH_ALERT。X22（支撑判定改用原始 0.9）在 500 ms 就开段，2500 ms 升级。

### 本轮的命令与输出

门禁（精确命令，与 `phase2-context.md` 一致）：

```
cd /Users/liu/Desktop/FYP2-Live-System
export PYTHONDONTWRITEBYTECODE=1
(cd backend && TMPDIR=$(mktemp -d) PYTHONPATH=. ../.venv/bin/python -m pytest tests -q -p no:cacheprovider)
  -> 903 passed, 1 warning in 17.52s
./node_modules/.bin/vitest run --no-cache
  -> Test Files  28 passed (28) / Tests  771 passed (771)
./node_modules/.bin/tsc --noEmit
  -> exit 0
./node_modules/.bin/eslint .
  -> exit 0
```

pytest 数字的变化 **894 → 903 = +9**：`test_r10_fsm.py` 新增 7 个函数、9 个用例（F1 1 个、F2 2 个〔参数化〕、F3 的 4 个函数共 5 个〔其中单模态那条参数化为 2〕、F4 1 个）。既有 894 个用例一个都没有删、没有改、没有 skip。vitest 771 / tsc 0 / eslint 0 与上一轮一致（本轮没有碰前端与 `ai/src`）。`tests/test_r10_fsm.py` 单独 74 passed（原 65），与 `test_r10_observations.py` 合并 128 passed（原 119）。

### 变异验证（隔离副本）

方法与首轮相同：`git archive HEAD | tar -x` 到临时目录（`/var/folders/0k/dtzqmkm53vqgg530vd7h3fmr0000gn/T/r10fix1-mut-_o71efqn`），把真实工作树里改动过的后端文件（这一轮只有 `tests/test_r10_fsm.py`）叠上去，`.venv` 符号链接到本工作树的 `.venv`；每项变异改副本里的 `backend/app/inference.py` 一处 → 在副本的 `backend/` 里跑**全部** pytest → 从真实工作树把该文件拷回并 `filecmp` 逐字节确认一致 → 下一项。真实工作树不做任何变异（`git status` 在所有变异之后只有 `test_r10_fsm.py` 与预先存在的 `node_modules 2`）。副本里没有模型文件，依赖真实模型的 7 个测试 skip，这是预期。运行器：scratchpad 下的 `mut/mutate_fix1.py`，完整输出 `mut/fix1-mutation-run.log`（不入库）。

- 未变异的副本：`896 passed, 7 skipped, 1 warning`（= 真实工作树的 903 − 7 个需要模型的测试）。
- 还原后的副本：`896 passed, 7 skipped, 1 warning`。

| # | 变异（`inference.py` 的改动） | 副本结果 | 变红的测试 |
|---|---|---|---|
| X37（F1） | 只对 High 做守卫：`guard = level == "Low" or (…)` | 2 failed, 894 passed | `test_g6_the_low_completion_guard_is_as_strict_as_the_high_one`、`test_g6_completion_guard_the_branch_that_filled_the_span_must_not_be_expired_in_the_window` |
| X38（F1） | Low 的守卫改成字面版「任一路有效模态支撑即可」 | 2 failed, 894 passed | 同 X37 的两条 |
| X34（F2） | Low 段去掉墙钟条件（High 保留） | 4 failed, 892 passed | `test_g6_low_the_wall_clock_holds_on_its_own_and_a_repeat_window_completes_it[9999-HIGH_ALERT]`、`[10000-NORMAL]`，另外 F1、F3-4 的两条 Low 守卫测试也变红 |
| X21b（F3） | 有效模态 = 新鲜（忽略权重） | 1 failed, 895 passed | `test_g7_a_zero_weight_branch_cannot_move_the_span_of_the_effective_one` |
| X21（F3） | 有效模态 = 请求带了观测（缺失、过期、权重都不看） | 3 failed, 893 passed | `test_g6_completion_guard_the_branch_that_filled_the_span_must_not_be_expired_in_the_window`、`test_g7_a_zero_weight_branch_cannot_move_the_span_of_the_effective_one`、`test_g7_an_expired_new_frame_is_not_an_effective_modality_and_opens_no_segment` |
| X22（F4） | vision 的支撑判定用原始概率 | 1 failed, 895 passed | `test_g9_vision_supports_with_its_smoothed_value_not_its_raw_one` |
| X21g（额外） | 只有完成守卫忽略「有效」 | 1 failed, 895 passed | `test_g6_completion_guard_the_branch_that_filled_the_span_must_not_be_expired_in_the_window` |
| X21s（额外） | 只有支撑者判定忽略「有效」 | 2 failed, 894 passed | `test_g7_a_zero_weight_branch_cannot_move_the_span_of_the_effective_one`、`test_g7_an_expired_new_frame_is_not_an_effective_modality_and_opens_no_segment` |
| X39（额外） | Low 段只在带 NEW 支撑者的窗口完成（estp4 用于 Low） | 1 failed, 895 passed | `…wall_clock_holds_on_its_own_and_a_repeat_window_completes_it[10000-NORMAL]` |
| X40（额外） | 两个方向的守卫都删掉 | 4 failed, 892 passed | 既有的两条 High 守卫测试 + 本轮的两条 Low 守卫测试 |

评审的 6 个变异（X37、X38、X34、X21b、X21、X22）现在每一个都有明确变红的测试；X21 / X21g / X21s 把「有效」的两处使用（支撑者、完成守卫）分开各有一条守护；首轮 V1–V13 未重跑（实现没有改动，首轮的结果仍然成立）。

### 遗留与说明

1. **没有改实现**：4 条发现都是测试缺口，行为本来就对。若控制者另有期望（例如 Low 方向的守卫要与 High 不同），那是规格问题，不是本轮范围。
2. **F3 反例 2 的构造与评审给出的不完全相同**（见上文说明）；我没有看到评审的探针，只按其描述重建，并用 X21 / X21g 证明该测试确实守护守卫那一半。
3. 变异 X21b 只在 High 方向被杀（零权重 vision 推进 High 跨度）。零权重一路在 Low 方向的同类情形（零权重的 Low 帧推进 Low 跨度）没有单独的测试；两个方向共用 `_Signal.effective` 与 `_supports`，同一行变异在 High 方向已红。
4. 首轮报告第 3 节的文件行数、第 5 节的测试计数、第 6 节的 894 现在应读作：`test_r10_fsm.py` 813 行 / 57 个函数 / 74 个用例；pytest 总数 903。首轮其余内容不变。
