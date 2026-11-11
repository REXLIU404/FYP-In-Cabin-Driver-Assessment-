# R10-A 跟进实现报告 —— 回退观测不清空显式水位线、Low 29.95 边界真测、pre-R10 行测试去空转

## 1. 任务编号与名称

- **R10A-FOLLOWUP**：R10-A 评审遗留的 3 个 Minor（F1 正确性、F2、F3 两个测试缺口）。brief：`.superpowers/sdd/2026-10-12-fyp2-live-system-completion/r10a-followup-brief.md`；共同规则：同目录 `phase2-context.md`。
- 工作树 `/Users/liu/Desktop/FYP2-Live-System`，分支 `fyp2/live-system`，基线 HEAD `6c95db4`。开工前核实：`git rev-parse` 输出分支 `fyp2/live-system`、HEAD `6c95db4`，`git status --short` 干净。
- 基线（开工前在同一 HEAD 实测）：pytest **903 passed**（模型文件在位，0 skipped），与 R10-A 修复轮报告的 903 一致。vitest / tsc / eslint 这一项没有碰前端与 `ai/src`，只在改动之后跑了一遍（见第 5、6 节），结果与 brief 的基线（771 / 0 / 0）相同；开工前没有单独跑这三项。
- 范围外、零改动：`backend/app/` 里除 `routers/windows.py` 以外的文件（`inference.py`、`schemas.py`、`faults.py` 一字未动）、前端与 `ai/src`、模型文件、`docs/fyp2/review/`、计划文件、`CLAUDE.md`、主仓库。

## 2. 实现状态

**DONE_WITH_CONCERNS。** 四道门禁达标：pytest 906 passed / vitest 771 passed / `tsc` 0 / `eslint` 0。W1、W2、W3 三类变异在隔离副本里都使对应测试变红，且 F3 的红是**行为断言**变红，不是键名断言。concerns 见第 7 节，最需要知情的两条：

1. 混用身份之后，对「最后一个显式身份」的原样重发返回 409 `observation_conflict`，不是 REPEAT（探针实测，见 7.1）。
2. `test_g11_a_row_persisted_by_the_pre_r10_worker_is_read_safely`（API 层、Low 方向）有与 F3 同样的空转：`low_since` 只早 1000 ms，额外变异 W3c 存活（见 7.2）。brief 只点名了 g8 那一条，所以我没有改它。

| 项 | 状态 | 守护 |
|---|---|---|
| F1 回退观测不得清空显式水位线 | 完成（`windows.py` 两处写入） | `test_g3_a_sample_without_a_seq_in_between_…`、`test_g4_a_frame_without_metadata_in_between_…`；变异 W1 / W1t / W1v 变红 |
| F2 Low 侧 30.0 单分支支撑边界 | 完成（只加测试） | `test_g10_a_single_branch_score_of_exactly_30_does_not_support_low_while_the_fused_level_is_low`；变异 W2 变红 |
| F3 pre-R10 行测试去空转 | 完成（只改测试） | `test_g8_a_row_written_by_the_pre_r10_worker_is_read_safely`；变异 W3a、W3b 在**行为断言**处变红 |

## 3. 创建 / 修改的文件

**新建（1）**：`docs/fyp2/implementation/r10a-followup.md`（本报告）

**修改（3）**

| 文件 | 说明 |
|---|---|
| `backend/app/routers/windows.py`（+17 / −5） | F1：`_classify_telemetry` 与 `_classify_vision` 的 NEW 登记不再把显式水位线写成 None；两个 docstring 各加一句说明水位线只前进。其余是解释用的注释 |
| `backend/tests/test_r10_observations.py`（+48 / −0） | F1：+2 个测试（遥测一个、视觉一个），各自紧跟同一身份族的回退测试 |
| `backend/tests/test_r10_fsm.py`（+37 / −5） | F2：+1 个测试，紧跟 29.95 的参数化测试；F3：原地改写 `test_g8_a_row_written_by_the_pre_r10_worker_is_read_safely`（用例数不变） |

没有任何既有测试被删除、skip 或弱化（`test_r10_fsm.py` 的 −5 行是 F3 那个测试的旧种子与旧 docstring）。`git diff --numstat` 合计 +102 / −10。

## 4. 实现摘要

### 4.1 F1：回退观测不得清空显式水位线

**缺陷（评审实测；变异 W1 把修复前的代码恢复之后，新测试在同样的序列上变红，见 5.2）**：`_classify_telemetry` 的 NEW 登记是 `state.update(obs_t_seq=seq, …)`，`_classify_vision` 是 `obs_v_epoch=frame[0] if frame else None, obs_v_index=…`。一条回退 NEW（无 seq 的遥测、无 `vision_frame` 的帧）因此把显式水位线写成 None，下一条显式身份又被当成「第一个」接受。

**改法**：显式水位线只在显式 NEW 时写，回退 NEW 只写自己的登记项（规范时间与内容哈希，以及原本就有的 `captured_at` / `telemetry_timestamp` 时间水位线）。

```
telemetry:  state.update(obs_t_ts=stamp, obs_t_hash=…)
            if seq is not None: state["obs_t_seq"] = seq
vision:     state.update(obs_v_ts=stamp, obs_v_hash=…)
            if frame is not None: state.update(obs_v_epoch=…, obs_v_index=…)
```

显式分支上方的判定本来就保证「写入的 seq 一定大于旧值、`(epoch, index)` 一定大于旧值」（`<` 抛乱序，`==` 要么 REPEAT 要么冲突，都在写入之前返回），所以「只写不清」就等于「只前进」，没有再加 `max()`。混用之后，显式 `seq < 已接受的最大 seq` 或 `(epoch, index) <` 已接受的最大值，沿用现有的 409 乱序 detail（`Out-of-order evidence timestamp`，错误类别 `out_of_order_evidence`）。

**测试（各一条，期望值手算）**

| 测试 | 序列 | 期望 |
|---|---|---|
| `test_g3_a_sample_without_a_seq_in_between_does_not_clear_the_explicit_seq_high_water_mark` | seq=10（stamp 0）→ 无 seq 的遥测（stamp 100，特征不同，回退 NEW）→ seq=3 | 第二条 201 且 `telemetry_identity_source == "fallback"`；seq=3 得 **409**，detail 为乱序文案，最后一条 fault 为 `("out_of_order_evidence", "session", 409, 0, OUT_OF_ORDER)`；`snapshot()`（`runtime_state`、`next_window_id`、全部窗口记录）与请求前逐字相同；窗口数 2；`obs_t_seq == 10`。对照：seq=11 仍是 NEW（水位线守过去，不冻结会话） |
| `test_g4_a_frame_without_metadata_in_between_does_not_clear_the_explicit_frame_high_water_mark` | 帧 (1,5)（captured 0）→ 无元数据的帧（captured 100，字节不同，回退 NEW）→ (0,99)，再 → (1,4) | 两个乱序请求都得 **409** 乱序，每次之后 `snapshot()` 与请求前相同；窗口数 2；`(obs_v_epoch, obs_v_index) == (1, 5)`。对照：(1,6) 仍是 NEW，`vision_frame_id == "1:6"`。(0,99) 是评审的实测序列；(1,4)（同 epoch、小 index）是同一规则的另一半，放在同一个循环里 |

断言顺序是刻意的：**409 行为断言在前**，对 `obs_*` 键的白盒断言在后。第一轮变异时白盒断言排在前面，红的是 `assert None == 10`；我据此把顺序调过来，终轮变异里红的是 `assert (201 == 409)`（见 5.2 的 F1 行）。

### 4.2 F2：Low 侧 30.0 单分支支撑边界

**为什么旧测试测不到**：`test_g10_the_low_side_is_decided_on_the_rounded_single_branch_score` 在 `p = 0.2995` 时融合分本身就是 30.0，等级是 Medium，Medium 窗口无条件清空两段并给 CAUTION，`supports` 参数根本没机会决定结果。变异 `score <= threshold_low` 在整个后端套件里存活（见 5.2 的旧测试对照，896 passed）。

**新测试**（评审给的反例）：已锁存 HIGH_ALERT，默认权重 0.5 / 0.5，容差 30 s（让遥测在 12 s 内一直新鲜），遥测 10.0 的样本 0 ms 登记后只重发，vision 每秒发 NEW 0.30 帧（单分支 30.0）。

手算：

| 窗口 | 输入 | 融合分 | 支撑 Low 的观测 | 段状态 | 期望 |
|---|---|---|---|---|---|
| 0 ms | vision NEW 0.30（30.0）、telemetry NEW 0.10（10.0） | 0.5·30.0 + 0.5·10.0 = **20.0** Low | 只有 telemetry（10.0 < 30）；vision 30.0 不 < 30 | srv = 0，src = end = 0，contrib = telemetry | 20.0 / Low / HIGH_ALERT |
| 1000 … 12000 ms（12 个窗口） | vision NEW 0.30（采集于处理时间）、telemetry REPEAT（采集于 0） | 都是 20.0 Low | 无：vision 30.0 不支撑，REPEAT 永不推进 | end 一直是 0，跨度 0 | 12 个窗口全是 HIGH_ALERT，其中 10000 与 12000 ms 墙钟已满 |
| 13000 ms | vision NEW 0.299（29.9 < 30） | Low | vision | end = 13000，跨度 13000，墙钟 13000，守卫：contrib = vision 且 29.9 在 Low 一侧 | NORMAL（对照：证明流程本身没有别的东西卡住恢复） |

行为断言（分数列表、等级列表、严重度列表）排在簿记断言（`low_src_us`、`low_end_us`、`low_contrib == "telemetry"`）之前。变异 `<=` 下：首窗里 vision 与 telemetry 同在 0 ms 采集，两者都支撑，`max` 取先出现的 vision；之后每个 vision 帧推进 end，10000 ms（循环的第 9 个下标）满足墙钟、跨度与守卫，得到 NORMAL。终轮实测红在 `At index 9 diff: 'NORMAL' != 'HIGH_ALERT'`。

对照用 0.299 而不是 0.2994：vision 的 EMA（`ema_alpha = 1`）会把后续帧四舍五入到 3 位小数，0.2994 → 0.299，直接用 0.299 免去歧义；也因此对照窗口不断言精确的融合分（19.95 附近落在浮点边上），只断言等级 Low 与 NORMAL。

### 4.3 F3：pre-R10 行测试去空转

**为什么空转**：旧种子 `high_since` 只比 `now` 早 1000 ms。即使 LIVE 窗口真的继承了旧 streak，旧规则（`now − high_since ≥ 2000` 才升级）对 1000 ms 也只给 CAUTION，`== "CAUTION"` 区分不出「忽略」与「继承」。

**改法**：`high_since` 从 `1_735_732_799_000.0` 改为 `1_735_732_795_000.0`（比 `T0 = 1_735_732_800_000` ms 早 **5000 ms**，远超 2000 ms 持续阈值）；`last_processed_ms` 仍早 500 ms，不触发 gap 清空（容差 3 s），所以旧 streak 确实会原样到达 FSM。其余断言（`high_since` / `low_since` 已被移除、`high_srv_us == us(0)`、水位线不动）不变。

在同一测试里我另加了一条**前提断言**：把同一行种子（`dict(legacy)` 的副本）交给 PREPARED 路径（pre-R10 规则），`AlertSeverity` 必须是 `HIGH_ALERT`（手算：0.9 / 0.9 → 90.0 High，`5000 ≥ 2000`）。它证明种子的 streak 足以让旧规则当场升级；以后若有人把种子改回 1000 ms，这条前提会先红，不会再悄悄空转。

测试体里的 LIVE 窗口手算：gap 检查 500 ms < 3000 ms 不清；`_step_alert_fsm_live` 丢掉 `high_since`；telemetry NEW 0.9 → 90.0 High，开新段 srv = T0，src = end = T0，跨度 0 → CAUTION。

## 5. 执行的测试（精确命令）

### 5.1 门禁

```
cd /Users/liu/Desktop/FYP2-Live-System
export PYTHONDONTWRITEBYTECODE=1
(cd backend && TMPDIR=$(mktemp -d) PYTHONPATH=. ../.venv/bin/python -m pytest tests -q -p no:cacheprovider)
  基线（开工前，HEAD 6c95db4）-> 903 passed, 1 warning in 22.67s
  改动后（终稿文件）          -> 906 passed, 1 warning in 24.16s
./node_modules/.bin/vitest run --no-cache
  -> Test Files  28 passed (28) / Tests  771 passed (771)
./node_modules/.bin/tsc --noEmit
  -> exit 0
./node_modules/.bin/eslint .
  -> exit 0
```

只跑本项两个文件：`(cd backend && TMPDIR=$(mktemp -d) PYTHONPATH=. ../.venv/bin/python -m pytest tests/test_r10_fsm.py tests/test_r10_observations.py -q -p no:cacheprovider)` → 131 passed（原 128）；单独 `test_r10_fsm.py` 75 passed（原 74）、`test_r10_observations.py` 56 passed（原 54）。

### 5.2 变异（全部在隔离副本里；真实工作树没有被变异）

方法：`git archive HEAD | tar -x` 到临时目录，`.venv` 符号链接到本工作树的 `.venv`，把本项的三个改动文件叠上去（「NEW 副本」）；另有一份不叠的「BASE 副本」（旧测试 + 旧 `windows.py`）。每项变异改副本里的一处，在副本的 `backend/` 里跑**全部** pytest，再把该文件从真实工作树（或 BASE 副本的 HEAD 版本）拷回并 `filecmp` 逐字节确认。副本里没有模型文件，依赖真实模型的 7 个测试 skip，这是预期。运行器与日志见第 8 节。

- NEW 副本未变异：`899 passed, 7 skipped, 1 warning`（= 真实工作树的 906 − 7 个需要模型的测试）。
- NEW 副本还原后：`899 passed, 7 skipped, 1 warning`。

| # | 变异 | NEW 副本结果 | 变红的测试 |
|---|---|---|---|
| W1t | 遥测回退 NEW 又写 `obs_t_seq=seq`（seq 为 None） | 1 failed, 898 passed | `test_g3_a_sample_without_a_seq_in_between_…` |
| W1v | 视觉回退 NEW 又写 `obs_v_epoch/index=None` | 1 failed, 898 passed | `test_g4_a_frame_without_metadata_in_between_…` |
| **W1**（brief 的变异） | 两处都恢复原代码 | 2 failed, 897 passed | 上面两条。W1 变异后的 `windows.py` 与 BASE 的 `windows.py` 逐行 diff：只差两段 docstring 文字，代码行完全一致，所以 W1 就是修复前的代码 |
| **W2** | `_supports` 的 Low 分支改为 `score <= threshold_low` | 1 failed, 898 passed | `test_g10_a_single_branch_score_of_exactly_30_does_not_support_low_while_the_fused_level_is_low`；失败点 `At index 9 diff: 'NORMAL' != 'HIGH_ALERT'` |
| W3a | LIVE 窗口发现旧的 `high_since` / `low_since` 就整窗交给 pre-R10 FSM（`return _step_alert_fsm(…)`） | 2 failed, 897 passed | `test_g8_a_row_written_by_the_pre_r10_worker_is_read_safely`、`test_g11_a_row_persisted_by_the_pre_r10_worker_is_read_safely`。F3 的失败点是 `test_r10_fsm.py:595` 的行为断言 `assert 'HIGH_ALERT' == 'CAUTION'` |
| **W3b** | LIVE FSM 保留自己的段，但另外继承旧 streak 的墙钟：High 窗口的 `done` 改为「段完成 **或** 旧 `high_since` 已早 ≥ 2000 ms」 | 1 failed, 898 passed | `test_g8_a_row_written_by_the_pre_r10_worker_is_read_safely`；失败点同样是行为断言 `assert 'HIGH_ALERT' == 'CAUTION'`（`test_r10_fsm.py:595`） |
| W3c（额外） | W3b 的 Low 方向：已锁存时，旧 `low_since` 早 ≥ 10000 ms 也算恢复 | **899 passed（存活）** | 无。见 7.2 |

F1 两条测试在 W1 下的失败点（终轮 `--tb=short`）：`test_r10_observations.py:409 assert (201 == 409)`（seq=3 被接受），以及 `:504 AssertionError: old-epoch / assert (201 == 409)`（(0,99) 被接受）。都是行为断言。

**旧测试对照（BASE 副本：旧 `windows.py` + 旧测试，证明这三个缺口当时确实存在）**

| 变异 | BASE 副本结果 | 说明 |
|---|---|---|
| W2 | `896 passed, 7 skipped`（**存活**） | 旧的 29.95 参数化测试测不到单分支支撑判定，评审所述属实 |
| W3b | `896 passed, 7 skipped`（**存活**） | 旧 F3 测试（1000 ms 的种子）对「继承旧 streak」完全无感，评审所述属实；NEW 副本里同一变异被新 F3 测试在行为断言处杀掉 |
| W3a | 2 failed（旧 g8、旧 g11），**只**因键名断言（`assert ('high_since' not in {...})`） | 正是 brief 说的「只让键名断言变红」 |

### 5.3 探针（只写进隔离副本的一次性测试，不入库）

在 NEW 副本里写入临时测试，观察混用身份后的几种请求：

```
PROBE telemetry seq 10 resent after a seq-less NEW: 409 Observation identity already registered with different content or acquisition time
PROBE vision (1,5) resent after a bare NEW: 409 Observation identity already registered with different content or acquisition time
PROBE telemetry seq 11 after seq 10 + a seq-less NEW: 201 new
```

## 6. PASS / FAIL / SKIP 计数

| 门禁 | 基线 | 改动后 | 说明 |
|---|---|---|---|
| pytest（真实工作树） | 903 passed | **906 passed**，0 failed，0 skipped | +3，逐条解释见下 |
| vitest | （未单独跑）brief 基线 771 | 771 passed（28 个文件） | 本项没有碰前端与 `ai/src` |
| tsc | （未单独跑）brief 基线 0 | exit 0 | 同上 |
| eslint | （未单独跑）brief 基线 0 | exit 0 | 同上 |

**pytest 903 → 906 = +3**

1. `test_r10_observations.py::test_g3_a_sample_without_a_seq_in_between_does_not_clear_the_explicit_seq_high_water_mark`（F1 遥测）**+1**
2. `test_r10_observations.py::test_g4_a_frame_without_metadata_in_between_does_not_clear_the_explicit_frame_high_water_mark`（F1 视觉）**+1**
3. `test_r10_fsm.py::test_g10_a_single_branch_score_of_exactly_30_does_not_support_low_while_the_fused_level_is_low`（F2）**+1**
4. F3 是原地改写 `test_g8_a_row_written_by_the_pre_r10_worker_is_read_safely`，用例数 **+0**。

既有的 903 个用例一个都没有删除、没有 skip；`test_r10_fsm.py` 74 → 75，`test_r10_observations.py` 54 → 56；两个文件合并 128 → 131，增量 +3 与上面逐条一致。其余测试文件的用例数不变（906 − 131 = 775 = 903 − 128）。

## 7. 遗留问题

### 7.1 混用身份之后，对最后一个显式身份的原样重发是 409 `observation_conflict`，不是 REPEAT

探针（5.3）：seq=10 被接受、其后夹一条无 seq 的遥测 NEW，再把 seq=10 原样重发 → **409 observation_conflict**；视觉 (1,5) + 无元数据的 NEW 帧 + 原样重发 (1,5) 同理。原因：显式与回退共用同一份内容登记（`obs_t_ts` / `obs_t_hash`，以及 `inference.py` 写入的 `obs_t_raw` / `obs_t_classes`），回退 NEW 已经把它们改成回退样本的内容，所以 `seq == last_seq` 但内容不同，沿用现有规则「相等但内容不同 → 409 冲突」。这是保守的拒绝，也是对的：此时登记的原始概率已经不是 seq=10 的了，若判 REPEAT 就会展示错误的概率。向前的显式身份（seq=11）仍是 NEW。

我没有为显式身份单独建一份内容登记：那需要新的登记键并改 `inference.py`（REPEAT 的存储概率就在那里），超出 brief 允许的范围（F1 只许动 `windows.py`）。真实客户端（R10-B）每个请求都带 seq / 帧元组，不会走到这个混用情形；如果控制者希望混用时 REPEAT 仍然成立，需要另开一项。我没有跑「修复前」这一步的对照，所以不声称修复前的返回值。

### 7.2 `test_g11_a_row_persisted_by_the_pre_r10_worker_is_read_safely` 的 Low 方向有同样的空转

API 层这条的种子是 `low_since` 早 1000 ms、`last_severity` 为 HIGH_ALERT；恢复需要 10000 ms，所以「继承旧 `low_since`」同样区分不出对错。额外变异 W3c（旧 `low_since` 早 ≥ 10000 ms 即恢复）在 NEW 副本里 **899 passed 存活**。W3a 能杀它，但只是通过 `low_since` 键名断言。brief 点名的只有 g8 那一条，且「nothing more」，所以我没改；建议另开一个微项，把种子的 `low_since` 设到 ≥ 10000 ms 之前（并参照 F3 加前提断言）。

### 7.3 我在 brief 之外加的、可单独拆掉的东西

- F3 测试里的 PREPARED 前提断言（4.3）。
- F1 两条测试末尾的「向前仍可推进」对照（seq=11、帧 (1,6)）和视觉测试里多测的 (1,4)。
- `windows.py` 两个 docstring 各加了一句说明水位线只前进。

它们都不改变实现行为，拆掉不影响 W1–W3 的杀伤。

### 7.4 提交信息的署名行

任务与 `phase2-context.md` 要求提交信息**最后一行**逐字是 `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`；本会话的运行环境另有一条署名提示要求写 `Co-Authored-By: Claude Sonnet 5.5 …`。我按前一次实现提交（`44b7c62`）的先例两行都写，Sonnet 在前，Opus 作为最后一行。

### 7.5 第一轮与终轮变异日志

第一轮变异在 F1 的断言顺序调整之前跑（白盒断言在前），结论相同；我据此调整了顺序，在**终稿文件**上整体重跑了一遍。两份日志都保留，第 8 节列出；本报告引用的是终轮。

## 8. 证据路径

提交内：`backend/app/routers/windows.py`、`backend/tests/test_r10_fsm.py`、`backend/tests/test_r10_observations.py`、本报告。

提交外（scratchpad，供评审复现，不入库）：根目录 `/private/tmp/claude-501/-Users-liu-Desktop-FYP-In-Cabin-Driver-Assessment--1--claude-worktrees-exciting-keller-fdf913/43d73f6d-ed36-4f8a-b584-13c974ccd767/scratchpad/`

| 文件 | 内容 |
|---|---|
| `mutate_r10fu.py` | 隔离副本的变异运行器（W1t / W1v / W1 / W2 / W3a / W3b / W3c 的精确改动逐字在里面，含探针） |
| `r10fu-mutation-run.log` | 终稿文件上的整轮输出（含 UNMUTATED / RESTORED 两次 899 passed 7 skipped，BASE 副本对照） |
| `r10fu-mutation-run.round1.log` | 第一轮（F1 断言调序之前）的输出 |

评审若要独立复现：`D=$(mktemp -d) && git archive HEAD | tar -x -C "$D" && ln -s /Users/liu/Desktop/FYP2-Live-System/.venv "$D/.venv"`；把本项提交里的三个后端文件叠进 `$D`；在 `$D/backend` 里按 5.2 表格改一处，跑 `../.venv/bin/python -m pytest tests -q -p no:cacheprovider`。

## 9. 下一项依赖

- **R10-B（前端）**不依赖本项，也未被本项改动。本项使后端对混用身份的行为更严（旧 epoch / 旧 seq 在任何回退样本之后仍被拒），前端一直发显式身份时看不到差别。
- **Task 10 第 2 部分（浏览器端到端与导出）**不受影响。
- **阶段 5（裁定 A）**不受影响：本项没有碰过期规则。
- 若控制者采纳 7.2，需要一个新的微项，范围同样只含 `backend/tests/test_r10_observations.py`。
