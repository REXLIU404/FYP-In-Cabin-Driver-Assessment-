# 进度日志

## 会话：2026-10-13（Claude，系统轨道）

### 已完成
- Tasks 1–6：`845b43a..564d0b1`（8 个 commit），验收报告见 `docs/fyp2/implementation/`
- F2：`ef2417d`（watermark 豁免 + 两条测试），验收 PASS（`3eeb1a7`）
- 记录 Codex 提示词：`54e0a60`
- R3：模型替换决定 + Task 10A 写入计划：`0822cac`
- 清理过期工作树与分支（Codex 旧工作树 3 个、分支 2 个）；保留 `exciting-keller-fdf913`（「Tasks1-6+7」会话正在使用）
- 读完 Codex 独立审阅，核实 R08（Live 可达 stale）属实
- 建立本 roadmap（`.planning/system-track/`）

### 门禁（最近一次，F2 之后，作者自报）

| 命令 | 结果 |
|---|---|
| pytest | 506 passed / 0 failed |
| vitest | 394 / 0 |
| tsc | 0 |

注：Codex 只独立复现了 tsc = 0；506 / 394 被标为 UNRESOLVED（R02），Task 10 要补原始日志。

### 分支状态
- `fyp2/live-system`：本地领先 `origin/fyp2/live-system`（远端停在 `564d0b1`），未 push
- `dev_cc`：本地领先 origin 2 个 commit（`23dec98`、`efb3ea6`），未 push
- `main`：未改动
- `fyp2/ml-training`：Codex 使用中，尚无新 commit

### 待用户回答
1. ~~E2–E5 归属~~ —— 已定：系统轨道（2026-10-13）
2. 文档删除 / 归档清单（见 findings.md）
3. 阶段 5 的三项政策（之后逐个问）

## 会话：2026-10-13（Claude，系统轨道，接手会话）

- 接手交接；核实 HEAD `86f12ca`、远端停在 `564d0b1`
- 独立核实 R08 属实（`inference.py:107-108` 按 `captured_at` / `telemetry_timestamp` 重判 freshness）
- 用户确认 E2–E5 归系统轨道，并下令开工阶段 1
- 发现计划第 510 行（Task 5 的 UT-TIME-06 规格）与第 755 行（Task 9 可达性表）仍写着 stale「不可达」，R4 未覆盖，并入 R08 更正项
- P1-1 F4 完成：`f289d66`、`9632812`（修复轮补 TS EMA 舍入测试），验收 PASS `9db6e2a`
- 用户批准删除 5 份零引用旧文档：`2000ffb`
- P1-2 R08 完成：`c7391b5`，评审 clean；IT-LIVE-AGE 共 9 个用例经 `/infer`，替换了编码错误前提的 source guard
- 门禁：pytest 518 / vitest 397 / tsc 0 / eslint 0
