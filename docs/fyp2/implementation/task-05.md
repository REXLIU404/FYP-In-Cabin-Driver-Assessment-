# Task 5 实现报告 —— 时序路径：unavailable 期间的 FSM 与 EMA

## 1. Task ID and name

- **Task 5**：时序路径 —— 一个没有评估结果的窗口，对 EMA 与 Alert FSM 意味着什么
- 工作树 `/Users/liu/Desktop/FYP2-Live-System`，分支 `fyp2/live-system`，基线 HEAD `64d67b9`
- 范围外、零改动：`frontend/src/`（Task 6）、`backend/app/schemas.py`（Task 4，已定稿）、故障事件（Task 7）、`ml/outputs/`。

## 2. Implementation status

**DONE_WITH_CONCERNS。** 控制者给定的五条 carry-forward 与全部「额外陷阱」均已落实并有测试钉住；**停止条件未触发**：`ROUND_HALF_UP` 之后 `test_restart.py:44`（钉死 `.312`）与 `test_audit_regressions.py:139` 仍然是绿的，两处期望值**没有改动**。concerns 见第 7 节，其中 #1（`App.tsx` 现在会静默给 unavailable 记录盖上非空 `AlertSeverity`）和 #2（回放演示数据有 11/25 个窗口的数值变了）需要 Task 6 / 报告撰写者知情。

| 项 | 状态 |
|---|---|
| 零权重 FSM 泄漏（已确认的 bug） | 修复；`test_zero_weight_unavailable_window_reports_unavailable_health_and_keeps_the_latch` 钉住 |
| ROUND_HALF_UP 全线对齐（Python x2 + TS） | 完成；1,900,120 个随机用例 + 1,002,001 格全网格上 Python 与 TS **零差异** |
| EMA 跨语言分歧（首帧不 round；stale/missing/unavailable 之后重新 seed） | TS 对齐到 Python；`UT-EMA-PARITY-01` 两个半边 |
| `inference.py` 显式传 `assessment_available` | 完成；自相矛盾的 producer 在写路径上响亮失败 |
| `build_explanation` 传入 statuses 与权重 | 完成；unavailable 解释能点名原因 |
| `UT-TIME-01` … `UT-TIME-06`、`UT-EMA-PARITY-01`、零权重 FSM 测试 | 全部完成 |

## 3. Files created or modified

| 文件 | 动作 | 说明 |
|---|---|---|
| `backend/app/inference.py` | 修改（重写） | 命名常量 `ALERT_SUSTAIN_MS=2000` / `ALERT_RECOVER_MS=10000`、`TEMPORAL_STATE_KEYS`、`_step_alert_fsm`；一次性算分母；显式 `assessment_available`；scratch-copy 事务式更新 state |
| `backend/app/fusion.py` | 修改（仅舍入） | 新增 `round_half_up`；`compute_risk_score` 改用它；docstring |
| `ai/reference/risk_logic.py` | 修改（舍入 + `ema()` 注释） | 同款 `round_half_up`；`ema()` 加 seed / 重新初始化约定注释（见第 4 节「偏离」） |
| `ai/src/alertFsm.ts` | 修改 | `updateAlertState` 的 `level` 放宽为 `RiskLevel \| null`，null 时挂起计时器；`AlertFsmState.severity` 仍非空 |
| `ai/src/riskLogic.ts` | 修改（EMA + 舍入） | 导出 `roundHalfUp`（精确的十进制串算法）；`round1/round3` 改用它；EMA 条件与首帧；遥测概率不再 round3 |
| `ai/fixtures/fusion_vectors.json` | 修改 | 追加 4 行平局：`F-R1`（84.25）、`F-R2`（29.95，跨 Low/Medium 边界）、`F-R3`（29.95，不等分支）、`F-R4`（22.25） |
| `ai/fixtures/ema_parity_vectors.json` | **新建** | `UT-EMA-PARITY-01` 的共享 oracle：9 个序列；期望值用精确 `Decimal` 算术独立推出，不 import 任何实现 |
| `ai/src/alertFsm.test.ts` | 修改 | 去掉 `ALERT_*_MS` 的 import，改硬编码 2000 / 10000；加 `UT-TIME-01`、`UT-TIME-04` 与 null 级别用例（7 -> 16 项） |
| `ai/src/emaParity.test.ts` | **新建** | `UT-EMA-PARITY-01` 的 TypeScript 半边（10 项） |
| `ai/src/fusionVectors.test.ts` | 修改 | 行数钉 21 -> 25；新增舍入模式 describe；prettier 已格式化 |
| `backend/tests/test_temporal_contract.py` | **新建** | 65 项：`UT-TIME-01..06`、零权重、state 卫生、写路径、HTTP 端到端、`UT-EMA-PARITY-01` Python 半边 |
| `backend/tests/test_fusion_vectors.py` | 修改 | 行数钉 21 -> 25；平局行与 `round_half_up` 困难用例；一处过期注释 |
| `docs/fyp2/implementation/task-05.md` | 新建 | 本报告 |

## 4. Implementation summary

**零权重 FSM 泄漏（最高优先级）。** 旧代码在 `:40` 调 `map_system_health(vstatus, tstatus)` 时没传权重，于是 `w=1.0/0.0` 且 vision missing、telemetry fresh 时 score 与 level 是 `None`、health 却是 `DEGRADED`；FSM 以 `health == "UNAVAILABLE"` 为键，落入 Low 分支，10 秒后把已激活的 `HIGH_ALERT` 悄悄降成 `NORMAL`。现在 health 带着配置权重算，`available = denominator > FUSION_EPSILON` 一次得出，并作为 `assessment_available` 显式传给 `RiskUpdate`；FSM 以 `level is None` 为键，**从不**看 health 字符串。任何一个 producer 函数与分母不一致，都会被 `RiskUpdate` 的 `after` 校验器当场拒绝（5 个猴子补丁用例加 1 个 HTTP 写路径用例钉住）。

**FSM 记忆与发射值分离。** 发射值（unavailable 时为 `None`）只存在于返回的记录上；FSM 记忆是 `state["last_severity"]`，**永远非空**。旧名 `severity` 只作为读取回退保留（升级前写入的持久化行仍能读到锁存），写入时会被 `pop` 掉。

**挂起而不是冻结。** unavailable 窗口：记 `unavailable_since`（仅首次）、清掉 `high_since/low_since`、返回 `None`、不碰 `last_severity`。恢复后的第一个可用窗口：弹出 `unavailable_since` 并把两个计时器重锚到当前窗口。挂起逻辑**没有**搭在 gap 分支上（`last_processed_ms` 对每个窗口都更新，60 秒无证据在 gap 逻辑看来是连续处理）。

**state 键卫生。** `TEMPORAL_STATE_KEYS` 列出全部 7 个键（含新键 `last_severity`、`unavailable_since`，以及旧名 `severity`）；gap 重置遍历它。有两个测试：一个用「gap 后接 blackout」的构造证明两个 severity 键都被清掉（blackout 不写它们，所以残留即泄漏）；一个跑完所有分支后断言 state 的键集合 ⊆ `TEMPORAL_STATE_KEYS`。state 还做了 JSON 往返测试，因为 `runtime_state` 是持久化 JSON 列。

**EMA 链。** `previous_vision` 现在是 `pd if vstatus == "fresh" and level is not None else None`，切断了「unavailable 但 vision fresh」（`w_v=0, w_t=1`、telemetry missing）继续累积 EMA 链的路径。

**事务式 state。** 所有时序记账先在 `scratch = dict(state)` 上进行，`RiskUpdate` 校验通过后才 `state.clear(); state.update(scratch)`。producer 出错抛异常时，时序记忆原样保留（有测试）。

**ROUND_HALF_UP。** Python 两份用 `Decimal(str(x)).quantize(..., ROUND_HALF_UP)`。**TS 不能用指数平移**（`Number("27.849999999999998e1")` 直接落在平局 278.5 上）：我先试过这个朴素实现，在 1,900,120 个用例里有 1,992 处与 Python 不一致；最终实现直接对 `String(value)` 的十进制数字串做 `BigInt` 精确运算，最后只做一次精确的字符串转 `Number`。这条路径零差异。**语义要点：舍入对象是 `repr`，不是精确二进制值**，所以 29.95（二进制略小于平局）现在是 30.0 -> Medium，旧的 Python `round` 与 TS `toFixed` 都给 29.9 -> Low。

**EMA 对齐（TS -> Python）。** 首帧发原始精度（去掉 `round3`）；条件改为「上一条记录 `assessment_available` 且其 vision 为 fresh，且当前 vision 为 fresh」。未改任何 Python 的 seed 行为。

**`alertFsm.ts`。** `level: RiskLevel | null`；null 返回 `{ severity: prev.severity, highSince: null, lowSince: null }`。可空性只在发射边界出现。

**与 brief 的偏离 / 额外发现（均已处理，需要知情）**

1. **brief 的前提「UT-TIME-04 现在会升级」没有复现。** 按字面序列（High@0 -> 双 missing@1000 -> High@2000），旧代码也**不会**升级：旧的 `health == "UNAVAILABLE"` 分支会把严重度强置 `NORMAL` 并清计时器。所以该序列的实际缺陷是**锁存被丢掉**（HIGH_ALERT -> NORMAL），不是误升级。我保留了 `UT-TIME-04` 作为回归守卫，并做了变异验证：把「挂起」改成「冻结」（保留 `high_since`、不在恢复时重锚）后，4 条 `UT-TIME-04` 用例全部变红。针对旧缺陷的有效红测试是零权重那条与「blackout 不清锁存」那组（第 5 节命令 4 的 19 条失败）。
2. **第三处跨语言分歧：遥测概率的 round3。** TS 在融合前把 `P_telemetry_anomaly` 舍入到 3 位，Python 不舍入；`pT = 0.1237`、`pD = 0.5`、权重 0.6/0.4 时后端得 34.9、TS 得 35.0。这会改变 `RiskScore`，比 `P_distraction` 分歧更实质。按同一裁定（Python 为准）把 TS 的该 `round3` 去掉；加入 oracle 用例 `telemetry-probability-is-not-rounded`（修复前红）。回放数据的遥测值本来就是 3 位，对回放是 no-op。
3. **时钟毫秒精度：调查后没有改。** 我最初怀疑 `now.timestamp() * 1000` 经两次二进制浮点会把精确的 2000 ms 变成 1999.9998，并为此改过 `_epoch_ms`；但对 200 万个随机（含微秒）基准时刻 x 3 个跨度（2000 / 3000 / 10000 ms，共 600 万次比较）的实测一次都没有复现，于是**撤回了该改动**，保留原表达式。`test_ut_time_01_whole_millisecond_boundaries_are_exact` 作为 1999 / 2000 ms 精确边界的回归守卫保留（对 109 个基准时刻扫描），它在新旧两种写法下都通过。
4. **`ai/reference/risk_logic.py` 的 `ema()` 首帧也改成不 round。** brief 说「只加注释」；但注释若声明「首帧以 provider 精度发射」而代码仍 `round(current, 3)`，规格就在自相矛盾。该文件零 importer，不受 `.312` 钉子约束，故改为与后端一致。其 `build_risk_update` 展示字段仍保留 3 位舍入（改用 half-up），属于规格文件的展示用途，见第 7 节 #6。
5. **`severity` 键改名为 `last_severity`**（带旧键回退读取），而不是并存两个等值键 —— 两个必须保持相等的键，正是会被某次重置漏掉一个的结构。

## 5. Tests executed (exact commands)

均在 `/Users/liu/Desktop/FYP2-Live-System` 下执行。

```bash
# 1. 基线（改动前）
cd backend && export TMPDIR=$(mktemp -d) && PYTHONPATH=. ../.venv/bin/python -m pytest tests -q
#   -> 367 passed, 1 warning in 5.44s
npx vitest run --no-cache            # -> Tests 1 failed | 219 passed (220)
npx tsc --noEmit | grep -c "error TS"  # -> 35

# 2. 最终门禁（改动后）
cd backend && export TMPDIR=$(mktemp -d) && PYTHONPATH=. ../.venv/bin/python -m pytest tests -q
#   -> 504 passed, 1 warning in 4.69s
./node_modules/.bin/vitest run --no-cache
#   -> Test Files 1 failed | 6 passed (7); Tests 1 failed | 276 passed (277)
npx tsc --noEmit | grep -c "error TS"                    # -> 34
npx tsc --noEmit | grep "error TS" | grep -vc "^frontend/"   # -> 0
./node_modules/.bin/eslint ai frontend; echo $?          # -> 0
./node_modules/.bin/prettier --check ai/src/riskLogic.ts ai/src/alertFsm.ts ai/src/alertFsm.test.ts \
    ai/src/emaParity.test.ts ai/src/fusionVectors.test.ts ai/fixtures/*.json   # -> All matched files use Prettier code style!

# 3. 停止条件的两个钉子测试
cd backend && PYTHONPATH=. ../.venv/bin/python -m pytest tests/test_restart.py tests/test_audit_regressions.py -v
#   -> 13 passed;  test_worker_restart_preserves_independent_session_state PASSED  (.312, 未改)
#                  test_second_window_uses_vision_ema PASSED

# 4. 红测试验证：新测试对「旧」inference.py
cp backend/app/inference.py <scratch>/inference.new.py && git show HEAD:backend/app/inference.py > backend/app/inference.py
cd backend && PYTHONPATH=. ../.venv/bin/python -m pytest tests/test_temporal_contract.py -q
#   -> 19 failed, 46 passed   (随后已把新文件复制回来，git diff 确认 119+/31-)

# 5. 变异验证：把「挂起」改成「冻结」
#   删除不可用分支清 high_since/low_since 的一行，以及恢复时的重锚
cd backend && PYTHONPATH=. ../.venv/bin/python -m pytest tests/test_temporal_contract.py -q -k "ut_time_04 or blackout"
#   -> 4 failed (全部是 UT-TIME-04 的 4 条), 3 passed;  已还原

# 6. 跨语言舍入暴力对拍（脚本在 scratchpad，未入库）
.venv/bin/python <scratch>/gen.py      # 1,900,120 用例：随机分数 / 字面平局 / 指数记法 / EMA 输出
node <scratch>/check.mjs               # -> { n: 1900120, bad: 0 }   (朴素指数平移版本：bad: 1992)
.venv/bin/python <scratch>/grid.py && node <scratch>/grid.mjs
#   -> 1002001 格 (pD,pT 步长 0.001, 权重 0.5/0.5): 新 Python 与新 TS 差异 0；
#      旧 Python round() 与新规则不同 170,228 格 (17.0%)；旧 TS toFixed 与新规则不同 130,174 格 (13.0%)

# 7. 回放影响（临时文件，已删除）：旧 riskLogic.ts vs 新，跑 PREPARED_SESSION_WINDOWS
#   -> 25 个窗口中 11 个不同（7, 9, 16, 18-25）
```

## 6. PASS / FAIL / SKIP counts

| 门禁 | 基线 | 现在 | 说明 |
|---|---|---|---|
| pytest | 367 passed / 0 failed | **504 passed / 0 failed / 0 skipped** | +137 = `test_temporal_contract.py` 65 + `test_fusion_vectors.py` 72（4 个新行 x (2 端口 x 4 项 + 1 项 reference) = 36，平局断言 8，层级 2，困难用例 26） |
| vitest | 219 passed / 1 failed | **276 passed / 1 failed** | +57 = `alertFsm` +9、`emaParity` +10、`fusionVectors` +38。唯一失败仍是 `frontend/src/data/preparedSessionInput.test.ts:31`（Task 6 的：回放里含 `null` 级别） |
| tsc | 35 errors，全在 `frontend/` | **34 errors，全在 `frontend/`，`ai/` 为 0** | 少的一个是 `App.tsx(62,7)`：`updateAlertState` 现在接受 `RiskLevel \| null`。**这不是修好了，见第 7 节 #1** |
| eslint | — | 0 | 直接调用二进制；`npx eslint` 在此环境被 RTK 包装器拦截（`could not determine executable to run`），与本 task 无关 |

## 7. Remaining issues

1. **（Task 6 必须处理）`App.tsx` 的 tsc 错误消失了，但问题还在。** `App.tsx:60-66` 把 `fsm.severity` 盖到每一条回放记录：`replayLog.append({ ...record, AlertSeverity: fsm.severity })`。现在 `updateAlertState` 接受 `null`，tsc 不再拦这一行，但对 unavailable 记录（`RiskLevel === null`）它会写入非空的 `AlertSeverity`，违反「unavailable 时四字段同时为 null」的契约。Task 6 需要改成 `AlertSeverity: record.RiskLevel === null ? null : fsm.severity`。tsc 的 34 里不再有任何提示会提醒这一点。
2. **回放演示数据的数值变了。** 25 个窗口中有 11 个不同（窗口 7、9 仅因舍入模式：30.9 -> 31、68 -> 68.1；窗口 16 与 18–25 因 stale/missing 之后重新 seed：例如窗口 16 的 `RiskLevel` Medium -> High、窗口 18 的 Medium -> High 且 `DominantEvidence` Telemetry-dominant -> Combined evidence）。这是裁定方向的直接后果，不是 bug；但任何引用回放具体 RiskScore 的报告文字或截图需要刷新。
3. **舍入变化的幅度比「4%」大。** 4% 是旧 Python 与旧 TS **互相**的分歧。新规则「对 `repr` 做 half-up」把所有十进制平局统一向上，而旧的两个实现按二进制噪声随机地向上或向下；因此相对旧 Python 变了 17.0%，相对旧 TS 变了 13.0%（权重 0.5/0.5、0.001 步长网格）。唯一会改变 `RiskLevel` 的是恰好落在 29.95 / 59.95 这类阈值平局上的输入（29.95 现在是 Medium）。
4. **长时间 blackout 不会让 HIGH_ALERT 失效。** 这是 brief 的设计（挂起而不是清除）：一分钟甚至更久的无证据窗口之后，锁存仍在，恢复后要连续 10 秒 Low 才解除。只有处理间隔 > 容差的 gap（例如 worker 重启）才会清空。如果希望「超过某个时长的无证据期自动解除锁存」，需要新的策略，不在本 task 内。
5. **`missing` 遥测在 TS 侧没有被置 0。** Python 对 `tstatus == "missing"` 发射 `P_telemetry_anomaly = 0.0`，TS 发射传入值。只影响发射字段，不影响分数或等级（权重为 0），回放数据本来就给 0，且不属于「EMA + 舍入」范围，所以没有动。
6. **`ai/reference/risk_logic.py:build_risk_update` 的展示字段仍把 P 值舍入到 3 位**（已改 half-up），而后端首帧发 provider 精度。分数与等级用的是未舍入值，两边一致；只是这个无 importer 的规格函数的两个展示字段与后端的首帧精度不同。
7. **D13 仍是已知限制**，不是本 task 的修复项。`UT-TIME-05`（相同 `captured_at` 通过严格 `<`）与 `UT-TIME-06`（stale-only 流累积到 HIGH_ALERT；对 1 分钟 / 1 小时 / 30 天前的帧参数化）断言的是**当前**行为，名字含 `known_limitation`，docstring 写明「不是期望行为、系统没有最大证据年龄」。另有源码守卫 `test_ut_time_06_source_guard_the_trained_provider_never_emits_stale`：`trained.py` 若开始输出 `stale`，该守卫变红，提示 D13 不再是仅回放可达。本报告与任何对外陈述都**不能**声称系统已完整处理过期证据。
8. 预先存在、未触碰：`ai/src/evidence.ts` 与 `ai/src/riskLogic.test.ts` 在 HEAD 就不符合 prettier。

## 8. Evidence paths

- 实现：`backend/app/inference.py`、`backend/app/fusion.py`、`ai/reference/risk_logic.py`、`ai/src/alertFsm.ts`、`ai/src/riskLogic.ts`
- 新测试与 oracle：`backend/tests/test_temporal_contract.py`、`ai/src/emaParity.test.ts`、`ai/fixtures/ema_parity_vectors.json`
- 修改的测试 / 夹具：`ai/src/alertFsm.test.ts`、`ai/src/fusionVectors.test.ts`、`backend/tests/test_fusion_vectors.py`、`ai/fixtures/fusion_vectors.json`
- 停止条件钉子：`backend/tests/test_restart.py:44`、`backend/tests/test_audit_regressions.py:139`（未改动，仍绿）
- D13 留证（Task 10 归档用）：`backend/tests/test_temporal_contract.py::test_ut_time_05_identical_captured_at_is_accepted_and_accumulates_alert_time_known_limitation`、`::test_ut_time_06_stale_only_stream_still_reaches_high_alert_known_limitation_d13[1-minute|1-hour|30-days]`
  - 取证命令：`cd backend && PYTHONPATH=. ../.venv/bin/python -m pytest tests/test_temporal_contract.py -k known_limitation -v`
- 对拍脚本（未入库）：`/private/tmp/claude-501/scratch/{gen.py,check.mjs,grid.py,grid.mjs,gen_ema.py}`

## 9. Next task dependencies

- **Task 6（前端）**：读第 7 节 #1。`updateAlertState` 现在接受 `null`；`App.tsx:66` 必须在 `RiskLevel === null` 时发 `AlertSeverity: null`。`ai/src/riskLogic.ts` 现在导出 `roundHalfUp`，前端若要显示与后端一致的舍入请用它而不是 `toFixed`。`preparedSessionInput.test.ts:31` 的失败（回放里有 `null` 级别）仍待 Task 6 处理。
- **Task 7（故障事件）**：`inference.py` 的 state 现在是 `scratch` 事务式更新；若故障事件需要读 FSM 记忆，读 `state["last_severity"]`，**不要**读已退役的 `state["severity"]`。`TEMPORAL_STATE_KEYS` 是权威键清单，新增任何 state 键必须同时加进去。
- **Task 10（最终门禁）**：归档第 8 节的 D13 取证命令输出；重新计算三个模型 checkpoint 哈希（本 task 未触碰 `ml/outputs/`）。
