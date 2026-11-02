# 阶段 1 · 第 4 项（P1-4）技术报告：经 API 的 near-epsilon 权重测试 IT-EPS（Codex R05）

- 分支 `fyp2/live-system`，工作树 `/Users/liu/Desktop/FYP2-Live-System`，开工 HEAD `0b7a0ec`（与简报要求一致，工作树干净）。
- 日期 2026-10-13。角色：实现者。未派发子 agent。

## 1. 任务编号与名称

P1-4-IT-EPS：在 `backend/tests/test_unavailable_contract.py` 新增一组经公共 API、穿过生产者（`backend/app/inference.py:129` 的 `available = denominator > fusion.FUSION_EPSILON`）的 near-epsilon 权重测试（Codex R05）。融合层的 epsilon 边界已由 `test_fusion_vectors.py` 钉住；本项补的是「经 HTTP、穿过生产者」那一层。

## 2. 实现状态

| 简报条目 | 状态 |
|---|---|
| 方向一（`weight_vision = ε`，视觉 fresh、遥测 missing）：ε = 1e-10、1e-9 不可用；ε = 1.1e-9 可用 | 完成 |
| 方向二（镜像：`weight_telemetry = ε`，视觉 missing、遥测 fresh）：同上三档 | 完成 |
| 先断言会话创建返回 201 | 完成（`new_session` 内部断言 201；窗口提交由 `post_window` 断言 201） |
| 不可用档：`assessment_available is False`；四个字段全为 `None`；`SystemHealth == "UNAVAILABLE"` | 完成 |
| 可用档：`DEGRADED`、`RiskScore == 80.0`、`RiskLevel == "High"`、`AlertSeverity == "CAUTION"`、`DominantEvidence == "Partial evidence"` | 完成 |
| 所有期望值为测试里的字面量；每个用例独立会话 | 完成 |
| 验收 M1（`>` 改 `>=`）→ ε = 1e-9 用例变红 | 完成：两个方向的 1e-9 用例均变红（第 5.3 节） |
| 验收 M2（改 `> 0`）→ ε = 1e-10 用例变红 | 完成：两个方向的 1e-10 用例均变红（第 5.3 节） |
| 对照：未加新测试时跑 M1，旧套件全绿 | 完成：512 passed / 7 skipped / 0 failed；同时对 M2 也做了对照（第 5.2 节） |
| 四项门禁 0 失败；解释 pytest 数字变化 | 完成：519 → 525（第 6 节） |

## 3. 创建 / 修改的文件

提交内包含 2 个文件：

| 文件 | 性质 |
|---|---|
| `backend/tests/test_unavailable_contract.py` | 修改：+75 / −0。在 `test_partial_evidence_with_positive_denominator_stays_available` 与 `_jpeg_b64` 之间新增 `IT-EPS` 小节 |
| `docs/fyp2/implementation/phase1-04-iteps.md` | 新建：本报告 |

未触碰：`backend/app/`（没有改任何实现，所有变异只在隔离副本里做）、`docs/fyp2/review/`、`ml/outputs/`、主仓库、计划文档（登记工作留给控制者）。

## 4. 实现摘要

### 4.1 事实依据（我自己核对过源码）

- `backend/app/inference.py:128-129`：`_, _, denominator = fusion.effective_weights(weight_v, weight_t, vstatus, tstatus)`，随后 `available = denominator > fusion.FUSION_EPSILON`。
- `backend/app/fusion.py:25`：`FUSION_EPSILON = 1e-9`。`compute_risk_score`（`:89`）与 `map_system_health`（`:125`）都用 `total <= FUSION_EPSILON` 判不可用，即融合层的边界是 `<=`。生产者若把自己的判定改成 `>=` 或 `> 0`，就会与融合层在 `(1e-10 .. 1e-9]` 内互相矛盾：`available=True` 而 `RiskScore is None`。
- `backend/app/schemas.py:99-105`（`RuntimeConfig.coherent`）：只要求两个权重之和与 1 的偏差 `<= 1e-6`，所以 `(ε, 1−ε)` 都是合法配置，可以经 `POST /api/sessions` 的 `config` 字段进入。
- 矛盾记录会被 `RiskUpdate` 的 `after` validator 拒绝（错误信息：`an available assessment must carry RiskScore, RiskLevel, DominantEvidence and AlertSeverity`）。`backend/app` 里没有注册任何 `exception_handler`，所以在生产里它是一个 500；在 `TestClient` 里（默认 `raise_server_exceptions=True`）它表现为这个 `ValidationError` 被直接抛进测试，而不是一个 500 响应（第 5.3 节如实记录）。

### 4.2 新增测试

文件内新增小节 `IT-EPS`，共：

- `EPS_CASES`：一个字典，描述两个镜像方向，每个方向给出权重构造、「唯一 fresh 分支承载微小权重」的窗口参数、期望的 `modality_freshness`：
  - `vision-tiny`：`w_v = ε`、`w_t = 1−ε`，窗口 `v="fresh"`、`t="missing"`、`pd=0.8`、`pt=0.2`；
  - `telemetry-tiny`：`w_v = 1−ε`、`w_t = ε`，窗口 `v="missing"`、`t="fresh"`、`pd=0.2`、`pt=0.8`。
  这样有效分母恰好等于那个微小权重 ε。
- `_eps_run(client, direction, eps, label)`：每次调用创建**独立会话** `eps-{direction}-{label}`（`new_session` 断言 201），提交一个窗口（`post_window` 断言 201），并额外断言两件事，防止测试「空过」：
  - `body["provenance"]["fusion_config"][<微小权重键>] == eps`：证明微小权重确实经 API 进入了生产者，而不是被默认的 0.5/0.5 悄悄替换；
  - `body["modality_freshness"]` 等于预期：证明窗口的 fresh / missing 配置到位。
- `test_effective_weight_at_or_below_epsilon_is_unavailable_not_a_server_error`：参数化为 `eps ∈ {1e-10, 1e-9}` × 两个方向 = 4 个用例。断言 `assessment_available is False`，`RiskScore`、`RiskLevel`、`DominantEvidence`、`AlertSeverity` 全为 `None`，`SystemHealth == "UNAVAILABLE"`，并调用已有的 `assert_unavailable` 做三向恒等式检查；再读回 `/risk/latest` 与 `/windows`，证明落库的记录与响应完全一致（`ε = 1e-9` 用例钉住边界是 `<=`）。
- `test_effective_weight_just_above_epsilon_is_an_available_degraded_assessment`：`ε = 1.1e-9` × 两个方向 = 2 个用例。断言 `assessment_available is True`、`SystemHealth == "DEGRADED"`、`RiskScore == 80.0`、`RiskLevel == "High"`、`AlertSeverity == "CAUTION"`（首个 High 窗口，尚未持续满 2 s）、`DominantEvidence == "Partial evidence"`，`assert_identity`，并读回 `/risk/latest`。

期望值（`80.0`、`"High"`、`"CAUTION"`、`"Partial evidence"`、`"DEGRADED"`、`"UNAVAILABLE"`、`1e-10` / `1e-9` / `1.1e-9`）全部是测试里的字面量；没有 import 任何实现常量（包括 `FUSION_EPSILON`）来构造期望。权重 `1 − ε` 是配置输入，不是期望值。

与简报相比我多加的只有测试内部的防空过断言（上述 provenance / freshness 两条）与读回断言；没有新增 fixture、helper 文件或实现改动。

## 5. 执行的测试（精确命令）

### 5.1 新测试单独运行（真实工作树）

```
cd /Users/liu/Desktop/FYP2-Live-System
export PYTHONDONTWRITEBYTECODE=1
(cd backend && TMPDIR=$(mktemp -d) PYTHONPATH=. ../.venv/bin/python -m pytest tests/test_unavailable_contract.py -q -p no:cacheprovider -k "epsilon" -v)
```
结果：`6 passed, 32 deselected, 1 warning`。

### 5.2 对照实验：新测试不存在时，M1 与 M2 都让旧套件全绿（证明「此前无防线」）

隔离副本：`D=$(mktemp -d) && git -C /Users/liu/Desktop/FYP2-Live-System archive HEAD | tar -x -C "$D" && ln -s .../.venv "$D/.venv"`（本次 `D=/var/folders/0k/dtzqmkm53vqgg530vd7h3fmr0000gn/T/tmp.cXz13wcfxS`）。`git archive HEAD` 取的是已提交内容，因此副本里**没有**我的新测试。

| 变异（只改副本 `backend/app/inference.py:129`） | 命令（在 `$D/backend`） | 结果 |
|---|---|---|
| M1：`denominator >= fusion.FUSION_EPSILON` | `TMPDIR=$(mktemp -d) PYTHONPATH=. ../.venv/bin/python -m pytest tests -q -p no:cacheprovider` | **512 passed, 7 skipped, 0 failed**（全绿，变异存活） |
| M2：`denominator > 0` | 同上 | **512 passed, 7 skipped, 0 failed**（全绿，变异存活） |

512 + 7 = 519，恰好等于开工基线 519；7 个 skip 是副本里没有模型文件所致（预期）。

### 5.3 验收变异：新测试加入后，变异必须变红

做法：把新的 `test_unavailable_contract.py` 拷进同一隔离副本，每次先把被变异的文件还原成 `HEAD` 版本，再只施加一个变异，运行
`TMPDIR=$(mktemp -d) PYTHONPATH=. ../.venv/bin/python -m pytest tests/test_unavailable_contract.py -q -p no:cacheprovider -k epsilon`

| 变异 | 结果 | 变红的用例 |
|---|---|---|
| **M1**：`inference.py:129` `>` → `>=` | `2 failed, 4 passed` | `…at_or_below_epsilon…[1e-9-vision-tiny]`、`…[1e-9-telemetry-tiny]`（两个 1e-10 用例保持绿，因为 `1e-10 >= 1e-9` 为假——这正是 M1 只在恰好等于 ε 时才有症状的原因） |
| **M2**：`inference.py:129` 改为 `denominator > 0` | `4 failed, 2 passed` | `…at_or_below_epsilon…` 的 `[1e-10-vision-tiny]`、`[1e-10-telemetry-tiny]`、`[1e-9-vision-tiny]`、`[1e-9-telemetry-tiny]`（两个 1.1e-9 的「可用」用例保持绿） |
| 追加 M3：`fusion.py:25` `FUSION_EPSILON = 1e-8` | `2 failed, 4 passed` | `…just_above_epsilon…[vision-tiny]`、`[telemetry-tiny]`（证明「可用」那一侧同样被守住） |
| 追加 M4：`fusion.py:25` `FUSION_EPSILON = 1e-10` | `2 failed, 4 passed` | `…at_or_below_epsilon…[1e-9-vision-tiny]`、`[1e-9-telemetry-tiny]` |

M1 / M2 的失败形态（如实记录）：错误是 `pydantic_core._pydantic_core.ValidationError: 1 validation error for RiskUpdate … an available assessment must carry RiskScore, RiskLevel, DominantEvidence and AlertSeverity`，即生产者产出了「`assessment_available=True` 而 `RiskScore is None`」的矛盾记录，被 schema 的 `after` validator 拒绝。因为 `TestClient` 默认重新抛出服务端异常，测试看到的是这个异常，而不是简报所说的「返回 500 而非 201」的状态码；两者是同一个故障的两种表现（真实服务里这条请求会得到 500），测试在两种表现下都会变红。我没有为此改 `TestClient` 的配置。

还原核对：变异结束后把副本里的 `inference.py`、`fusion.py` 重新用 `git show HEAD:…` 覆盖并 `diff` 对比，均与 `HEAD` 一致（`copy restored`），再跑 `-k epsilon` 得 `6 passed`。真实工作树从未被变异：`git status --short` 在提交前只显示 `M backend/tests/test_unavailable_contract.py`（`backend/app`、`ml`、`docs/fyp2/review` 路径无任何改动）。

没有在变异状态下跑完整套件加新测试；变异下我只跑了 `test_unavailable_contract.py -k epsilon`，因此「其余测试在变异下的表现」只有 5.2 的旧套件对照可作证据。

### 5.4 四项门禁（真实工作树，提交前）

```
cd /Users/liu/Desktop/FYP2-Live-System
export PYTHONDONTWRITEBYTECODE=1
(cd backend && TMPDIR=$(mktemp -d) PYTHONPATH=. ../.venv/bin/python -m pytest tests -q -p no:cacheprovider)
./node_modules/.bin/vitest run --no-cache
./node_modules/.bin/tsc --noEmit
./node_modules/.bin/eslint .
```

## 6. PASS / FAIL / SKIP 计数

| 门禁 | 结果 |
|---|---|
| pytest（真实工作树，有模型文件） | **525 passed, 0 failed, 0 skipped**，1 个 `StarletteDeprecationWarning`（既有，与本项无关） |
| vitest | **397 passed / 0 failed**（15 个测试文件） |
| `tsc --noEmit` | 退出码 0 |
| `eslint .` | 退出码 0 |

pytest 数字变化：基线 519 → 525，**+6**，全部来自本项新增的测试：`test_effective_weight_at_or_below_epsilon_is_unavailable_not_a_server_error` 参数化 4 个（2 个 ε × 2 个方向）+ `test_effective_weight_just_above_epsilon_is_an_available_degraded_assessment` 参数化 2 个（2 个方向）。没有删除、替换或修改任何既有测试；vitest 与上一项持平（397），因为本项不涉及前端。

## 7. 遗留问题

1. **失败形态与简报措辞略有差异**：简报写「返回 500 而非 201」，在本仓库的 `TestClient` 设置下实际表现为 `ValidationError` 被抛进测试（5.3 节）。结论不变（测试变红），仅提示评审复现时不要期待看到字面的 `500 != 201` 断言信息。如果将来希望失败信息更友好，可以考虑在 `app.main` 注册一个把此类生产者矛盾映射为明确 500 的异常处理器，或在测试里用 `TestClient(app, raise_server_exceptions=False)`；这超出了本项范围，我没有做。
2. **边界的数值前提**：`ε = 1e-9` 用例依赖有效分母恰好等于浮点字面量 `1e-9`（`1e-9 * 1.0 + (1−1e-9) * 0.0`）并与 `FUSION_EPSILON` 的同一字面量比较。当前实现下这是精确的（M1 实测可区分）。若将来 `freshness_weight("fresh")` 不再恰好为 1.0，或分母的构造方式改变，这条边界用例需要重新审视。
3. 本项没有触碰阶段 5 的裁定 A（D13），现行代码仍有 0.45 stale 档，按指令不在本阶段实施。
4. 隔离副本 `/var/folders/0k/dtzqmkm53vqgg530vd7h3fmr0000gn/T/tmp.cXz13wcfxS` 按规则保留未删除。

## 8. 证据路径

- 测试：`/Users/liu/Desktop/FYP2-Live-System/backend/tests/test_unavailable_contract.py`（`IT-EPS` 小节，约第 232–306 行）
- 被守护的实现行：`/Users/liu/Desktop/FYP2-Live-System/backend/app/inference.py:129`；融合层边界：`backend/app/fusion.py:25,89,125`
- 变异 / 对照用的隔离副本：`/var/folders/0k/dtzqmkm53vqgg530vd7h3fmr0000gn/T/tmp.cXz13wcfxS`（最终状态为已还原）
- 本报告：`/Users/liu/Desktop/FYP2-Live-System/docs/fyp2/implementation/phase1-04-iteps.md`

## 9. 下一项依赖

- 本项不依赖也不阻塞后续项：只新增测试，没有改动任何实现、契约或 fixture。
- 对评审者：请在自己的隔离副本里独立复现 M1（预期 `2 failed, 4 passed`）与 M2（预期 `4 failed, 2 passed`）以及 5.2 的对照（预期 `512 passed, 7 skipped`）。
- 阶段 5 实施裁定 A 时若修改 `inference.py` 的可用性判定或 freshness 权重，这组测试仍应保持绿；如果 `freshness_weight` 的取值改变导致分母不再等于微小权重本身，需同步调整本组用例的窗口构造（见遗留问题 2）。
