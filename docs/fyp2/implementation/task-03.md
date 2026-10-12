# Task 3 实现报告 —— Python 侧契约同步（两份移植）

## 1. Task ID and name

- **Task 3**：Python 侧契约同步 —— `backend/app/fusion.py` 与 `ai/reference/risk_logic.py` 对齐 Task 2 已提交的 TypeScript 契约
- 工作树 `/Users/liu/Desktop/FYP2-Live-System`，分支 `fyp2/live-system`，基线 HEAD `b6cbf01`
- 范围：`backend/app/fusion.py`、`ai/reference/risk_logic.py`、新建 `backend/tests/test_fusion_vectors.py`。`backend/app/inference.py`、`backend/app/schemas.py`、`frontend/`、`ai/src/`、`ml/outputs/` 零改动。

## 2. Implementation status

**DONE_WITH_CONCERNS。** 两份 Python 移植与 TS 契约逐函数对齐，新增的 294 项测试全绿；但全量 pytest 有 **1 条失败**，且它**无法在本 task 的范围内修复**（第 7 节第 1 条）。vitest / tsc 数字与基线完全一致（219 通过 / 1 失败；35 条错误），没有漂移。

| Step | 内容 | 状态 |
|---|---|---|
| 1 | 写读同一份夹具的测试 | 完成 |
| 2 | 确认红 | 完成（旧代码 `F-U1` 得 `0.0`、`F-Z1`/`F-Z2` 得 `DEGRADED`，见第 5 节） |
| 3 | 改 `fusion.py` | 完成 |
| 4 | 同步 `ai/reference/risk_logic.py` | 完成，含 `__main__` worked example |
| 5 | 跑测试 | 完成；`test_api.py:83` 已复核仍为 `DEGRADED`；另有 1 条非本 task 可修的失败 |
| 6 | 单次本地 commit | 完成，SHA 见控制者收到的返回值 |

## 3. Files created or modified

| 文件 | 动作 | 说明 |
|---|---|---|
| `backend/app/fusion.py` | 修改（重写） | 见第 4 节 |
| `ai/reference/risk_logic.py` | 修改（重写） | 逐函数同步；`RiskUpdate` 增 `assessment_available`；`__main__` 增 unavailable 示例 |
| `backend/tests/test_fusion_vectors.py` | 新建 | 294 项：读 `ai/fixtures/fusion_vectors.json`，对**两份**移植断言；含 epsilon 边界、None 陷阱、解释文案、死代码守卫 |
| `docs/fyp2/implementation/task-03.md` | 新建 | 本报告 |

## 4. Implementation summary

**`fusion.py`**

- `FUSION_EPSILON = 1e-9`；判零一律 `total <= FUSION_EPSILON`，不用 `== 0`。
- `effective_weights(w_v, w_t, vision_status, telemetry_status) -> (eff_v, eff_t, total)` 是**唯一**的分母来源，`compute_risk_score` 与 `map_system_health` 都读它，不再各算各的。Task 5 的 `inference.py` 直接消费它。
- `compute_risk_score -> float | None`：分母 `<= epsilon` 返回 `None`；否则先 `/total * 100` 再 `round(..., 1)`（与 TS 同序）。
- `map_risk_level(score: float | None, ...) -> str | None`：**第一行**判 `None`。Python 对 `None < 30` 抛 `TypeError`，与 TS 的静默 `true` 方向相反，所以 pytest 全绿本身不能证明 TS 侧没问题。
- `map_system_health(vision_status, telemetry_status, weight_vision=0.5, weight_telemetry=0.5)`：分母 `<= epsilon` -> `UNAVAILABLE`；否则任一支非 `fresh` -> `DEGRADED`；否则 `FULL`。FULL/DEGRADED 只看 freshness，不看权重（`F-Z3`）。
- `determine_dominant_evidence(...) -> str | None`：**第一个分支**是 `risk_score is None or system_health == "UNAVAILABLE"` -> `None`，镜像 TS `determineEvidenceType`。原先 `system_health != "FULL" -> "Partial evidence"` 恰好挡住了对 `None` 的比较，所以旧代码不会崩，而是**静默给无证据窗口编造 "Partial evidence"**。
- `build_explanation(dominant, level, vision_status=None, telemetry_status=None, weight_vision=None, weight_telemetry=None)`：新增**前置** unavailable 分支（`dominant is None or level is None`）。文案 `No risk assessment is available because <cause>, so the effective fusion denominator is zero and there is no evidence to fuse.`，**不含任何 level 词**；`<cause>` 由新函数 `describe_unavailable_cause` 产生（`both the vision and telemetry inputs are missing` / `the vision input is missing and the telemetry branch has zero fusion weight` / ...，镜像 TS）。`level.lower()` 不再会对 `None` 抛 `AttributeError`。兜底 `"below the low-risk threshold"` 现在**只**对 `"Low observed risk"` 命中；无法识别的 dominant 值返回中性文案，不再被说成低风险。
- `map_alert_severity(level) -> str | None`：加 `None` 守卫；docstring 顶部写明「**未被调用，不要接线**，FSM 在 `inference.py`」。**没有删除，没有接线。** 测试里有一条静态扫描断言 `backend/app` 下除 `fusion.py` 外没有任何文件提到它。

**`ai/reference/risk_logic.py`**

逐函数照搬上述改动。`build_risk_update` 原先 `map_system_health(v, t)` 的位置参数调用已改为 `map_system_health(v, t, w_vision=w_v, w_telemetry=w_t)`（关键字参数，防止静默错位）。`RiskUpdate` 数据类增 `assessment_available: bool`，`RiskScore / RiskLevel / DominantEvidence` 改为可空。`__main__` 增第三个示例（两路 missing），实际输出：

```
Unavailable example (vision AND telemetry missing, w 0.5/0.5):
  -> assessment_available = False
  -> RiskScore       = None (None, never 0)
  -> RiskLevel       = None
  -> DominantEvidence= None
  -> SystemHealth    = UNAVAILABLE
```

该模块没有 `build_explanation` / `map_alert_severity`（原本就没有），未新增。该模块**零 importer**，所以我让 `test_fusion_vectors.py` 通过 `importlib` 加载它，与 `fusion.py` 一起对同一份 JSON 做参数化测试——以后它漂移会红。

**`test_fusion_vectors.py`**

- 夹具路径由 `Path(__file__).resolve().parents[2] / "ai" / "fixtures" / "fusion_vectors.json"` 解析（相对仓库根）。形状守卫：顶层是数组、21 行、id 唯一、字段集固定、`available` 与四字段 null 性一致。
- 对 `{backend_fusion, reference_risk_logic} x 21 行` 断言 `score / level / health / dominant`（168 项），另对参考实现的 `build_risk_update` 端到端断言 21 项。阈值 30 / 60 与 gap 0.15 是文件内硬编码字面量，**不从实现 import 任何期望值**。
- **epsilon 边界（夹具不覆盖）**：8 个用例 x 2 份移植 x 5 个断言 = 80 项。权重和为 1（落在 `RuntimeConfig` 的 `1e-6` 容差内，用 `abs(wv+wt-1) <= 1e-6` 断言），小分母由缺失的那一支贡献 0 得到：分母 `1e-10 -> unavailable`、`1e-9 -> unavailable`（恰在边界）、`1.1e-9 -> available`，vision 侧与 telemetry 侧镜像各一组；再加两个 stale 用例（`2.2e-9 * 0.45 ~ 9.9e-10` 不可用；`2.3e-9 * 0.45 ~ 1.035e-9` 可用）。边界字面量硬编码，不 import `FUSION_EPSILON`。
- **`determine_dominant_evidence` 调用一律用关键字参数**（`low=`、`gap=`）。注意：Python 版签名仍是 `(p_distraction, p_telemetry_anomaly, risk_score, system_health, low, gap)`——它接收**已算好的** `system_health`，而不是像 TS 那样接收两个 status 再加权重，所以 Python 侧**不需要**追加 `weightVision/weightTelemetry`。保持这个签名也是为了不破坏尚未改动的 `inference.py:41` 的调用（`determine_dominant_evidence(pd, pt, score, health, low=...)`）。

## 5. Tests executed (exact commands)

所有 pytest 命令前先 `export TMPDIR=$(mktemp -d)`（`test_api.py` 会销毁固定临时库）。

```bash
# 基线（改动前）
cd backend && PYTHONPATH=. ../.venv/bin/python -m pytest tests -q          # 28 passed
cd .. && npx vitest run --no-cache                                          # 1 failed | 219 passed (220)
npx tsc --noEmit | grep -c "error TS"                                       # 35
npx tsc --noEmit | grep "error TS" | grep -v "^frontend/" | wc -l           # 0

# RED：把两份移植还原成 HEAD 版本再跑新测试（之后已恢复，cmp 逐字节核对）
cd backend && PYTHONPATH=. ../.venv/bin/python -m pytest tests/test_fusion_vectors.py -q
#   -> 190 failed, 104 passed
#   -> 首个失败 TestFusionVector::test_compute_risk_score[F-U1-backend_fusion]: assert 0.0 == None
#   旧代码实测: F-U1 score 0.0 / level Low；F-Z1、F-Z2 score 0.0 / health DEGRADED / level Low

# 变异测试：把 `total <= FUSION_EPSILON` 改成 `total == 0`（两份移植），再跑
PYTHONPATH=. ../.venv/bin/python -m pytest tests/test_fusion_vectors.py -q
#   -> 30 failed, 264 passed；30 条失败全部在 TestEpsilonBoundary（非 Epsilon 的失败数 = 0）
#   -> `-k "not Epsilon"`: 214 passed —— 即 21 行夹具在 `== 0` 实现下全绿，证明夹具确实不覆盖边界，epsilon 测试有牙

# GREEN（最终状态）
cd backend && PYTHONPATH=. ../.venv/bin/python -m pytest tests/test_fusion_vectors.py -q   # 294 passed in 0.23s
cd backend && PYTHONPATH=. ../.venv/bin/python -m pytest tests -q                          # 1 failed, 321 passed
cd backend && PYTHONPATH=. ../.venv/bin/python -m pytest tests/test_api.py -v              # test_full_crud_and_fusion PASSED
python3 ai/reference/risk_logic.py                                                         # 三个示例均正常打印
cd .. && npx vitest run --no-cache                                                         # Test Files 1 failed | 5 passed (6); Tests 1 failed | 219 passed (220)
npx tsc --noEmit | grep -c "error TS"                                                      # 35 (frontend 之外 0)
```

## 6. PASS / FAIL / SKIP counts

| 套件 | 通过 | 失败 | 跳过 | 备注 |
|---|---|---|---|---|
| `pytest tests/test_fusion_vectors.py` | **294** | 0 | 0 | 本 task 新增 |
| `pytest tests`（全量） | **321** | **1** | 0 | 基线 28 通过 + 新增 294 = 322；1 条失败见第 7 节 |
| `pytest tests/test_api.py` | 1 | 0 | 0 | `:83` `latest_system_health == "DEGRADED"` **复核仍为真** |
| `vitest run --no-cache` | **219** | **1** | 0 | **与基线完全一致**；唯一失败仍是 `preparedSessionInput.test.ts:31`（Task 6） |
| `tsc --noEmit` | —— | **35** 条错误 | —— | **与基线完全一致**；`frontend/` 之外 0 条 |

`test_fusion_vectors.py` 的 294 项构成：形状守卫 3 + 夹具向量 168（2 份移植 x 21 行 x 4 函数）+ 参考实现 `build_risk_update` 21 + 取整顺序 `F-T5` 2 + epsilon 边界 80 + None 陷阱 10 + 解释文案 7 + 死代码守卫 3。

`test_api.py:83` 的复核：该用例权重 `0.5/0.5`，仅 telemetry 一侧 missing，分母 `0.5 != 0`，health 仍为 `DEGRADED`，`DominantEvidence` 仍为 `"Partial evidence"`——**实测通过，未移动**。

## 7. Remaining issues

1. **全量 pytest 有 1 条失败，本 task 范围内无法修复：`tests/test_live_inference.py::test_missing_expired_and_out_of_order_inputs`。** 该用例向 `/infer` POST 一个空窗口（两路 missing）。`fusion.compute_risk_score` 现在正确返回 `None`，但未改动的 `backend/app/inference.py:62` 把 `RiskScore=None / RiskLevel=None / DominantEvidence=None` 传给仍然非空的 `schemas.RiskUpdate`，抛 `pydantic ValidationError: 3 validation errors for RiskUpdate`（`RiskScore` / `RiskLevel` / `DominantEvidence`）。这条失败**本身就是契约变更的正确症状**（旧行为是捏造的 `0.0/Low`），修复属于 **Task 4**（`schemas.py` 四字段改 `Optional`；Task 4 brief 已列出 `test_live_inference.py:98-100`）与 **Task 5**（`inference.py` 对 `AlertSeverity`/FSM 的处理）。我没有改这两个文件，也没有削弱/跳过该测试——这是 Task 3 与 Task 4 之间已知的接缝，在 Task 4 提交前全量 pytest 不可能全绿。
2. **既有的跨语言取整分歧（不是本 task 引入，未修，建议控制者决定归属）。** `compute_risk_score` 用 Python `round(x, 1)`（银行家取整，作用于精确二进制值），TS 用 `Number(x.toFixed(1))`（精确平局取较大者，即 half-up）。当 `score*100` 恰为 `k.x25 / k.x75`（可精确表示的平局）时两边差 0.1。实测：`pD=0.916, pT=0.769, 0.5/0.5, fresh/fresh` 的原始值恰为 `84.25`，**真实 TS `computeRiskScore` 返回 `84.3`，Python 返回 `84.2`**。对 3 位小数输入随机抽样 400000 次，约 **0.4%（1501 次）** 出现分歧。这 21 行夹具不含此类平局，所以不会红。它**不会改变 RiskLevel**（平局值只可能是 `x.25/x.75`，不会跨越 30 / 60 阈值），只造成显示分数差 0.1。同一问题也存在于 EMA 的 `round(..., 3)` vs `round3`（Task 5 的 `UT-EMA-PARITY-01` 可能撞到）。修法很小（两份移植里用 `Decimal(x).quantize(Decimal("0.1"), ROUND_HALF_UP)` 复刻 `toFixed`），但这改变既有语义、超出本 task 简报，所以只记录不改。
3. `build_explanation` 的非 unavailable 分支文案仍是 Python 原有的较短版本（不含 `P_distraction` 百分比），与 TS 的长文案不同。契约只钉死 unavailable 分支，且 Python 版签名里没有 `pD/pT`，所以未改。
4. `inference.py` 目前调用 `fusion.build_explanation(dominant, level)`（两参），unavailable 时会得到 generic 原因（`no input branch carries usable evidence ...`）。Task 5 应改为传入 `vstatus, tstatus, config.weight_vision, config.weight_telemetry`，才能点名具体是哪一支缺失 / 零权重。

## 8. Evidence paths

- `backend/app/fusion.py`
- `ai/reference/risk_logic.py`
- `backend/tests/test_fusion_vectors.py`
- `ai/fixtures/fusion_vectors.json`（只读，TS 与 Python 共用的 oracle）
- 对照的 TS 权威实现：`ai/src/riskLogic.ts`、`ai/src/availability.ts`、`ai/src/evidence.ts`、`ai/src/fusionVectors.test.ts`
- 本报告：`docs/fyp2/implementation/task-03.md`

## 9. Next task dependencies

- **Task 4**（`schemas.py` 等）：必须把 `RiskUpdate` 的 `RiskScore / RiskLevel / DominantEvidence / AlertSeverity` 改 `Optional` 并加 `assessment_available`，才能让第 7 节第 1 条失败转绿。Task 4 消费的 `fusion` 签名现已就绪：`compute_risk_score -> float | None`、`map_risk_level(None) -> None`、`map_system_health(v, t, wv, wt)`、`determine_dominant_evidence(...) -> str | None`、`build_explanation(None, None, ...)`。
- **Task 5**（`inference.py`）：
  - 用 `fusion.effective_weights(...)` 一次性算 `(eff_v, eff_t, total)`；health 调用改传权重 `fusion.map_system_health(vstatus, tstatus, config.weight_vision, config.weight_telemetry)`（当前 `inference.py:40` 只传两个 status，零权重配置下会与 score 自相矛盾）。
  - `determine_dominant_evidence` 保持 `(pd, pt, score, health, low=...)` 的调用形状即可；`build_explanation` 补传 status 与权重。
  - **不要**接线 `fusion.map_alert_severity`——它会绕过 2 秒 sustain；`test_fusion_vectors.py::TestMapAlertSeverityIsDeadCode::test_nothing_in_the_backend_calls_it` 会在有人接线时变红。
- **Task 5 的 EMA 对齐 / 第 7 节第 2 条**：取整分歧需要在 Task 5 之前或之中由控制者裁定（同一个 `toFixed` vs `round` 问题会影响 `UT-EMA-PARITY-01`）。
- **Task 6**：`frontend/src/data/preparedSessionInput.test.ts:31` 的唯一 vitest 失败仍待其处理。
