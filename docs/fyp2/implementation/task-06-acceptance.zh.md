# Task 6 验收报告（中文）

## 1. 任务概要

- **编号与名称**：Task 6 —— 前端展示层：消灭捏造读数
- **实现了什么**：五个视图改为渲染后端产出的 canonical 记录，不再自行重算风险字段；删除前端伪造的 `SystemHealth`；在 localStorage 与 API 两个不可信边界做归一化；补齐 unavailable 的视觉样式；修复五处「编译通过但静默出错」的比较/过滤点；`ConfigurationView` 在权重归零时给出提示。
- **为什么必要**：Task 2 把字段改成可空之后，前端有 34 条类型错误 —— 但更危险的是**类型系统根本抓不到的部分**。`strict` 模式下算术和属性访问会大声报错，而**每一个比较和过滤都能编译通过并静默失败**。此外审计发现前端从不读 `record.DominantEvidence`，五个视图全都自己重算，`LiveMonitor.tsx:45` 还会凭前端的「是否过期」判断**伪造** `SystemHealth = "UNAVAILABLE"`。
- **行为变化**：无评估窗口在 UI 上显示为明确的 unavailable 状态（灰色虚线样式），不再长得像普通低风险；显示的 `SystemHealth` 等于记录自身的值；「可用 / 过期 / 无评估」成为三个独立显示态。

## 2. 实现证据

- **Commits**：`8236244`（主实现，37 个文件）+ `1edb923`（修复轮 1，仅测试）
- **主要文件**：新增纯函数模块 `views/riskDistribution.ts`、`views/liveMonitorModel.ts`、`views/explanationModel.ts`、`components/trendSeries.ts`、`utils/alertOverlay.ts`、`utils/display.ts`；修改五个视图、`AlertBanner`、`TrendChart`、`Pill`、`ScoreGauge`、`styles.css`、`persistence.ts`、`api/client.ts`、`utils/export.ts`、`App.tsx`
- **关键决定**：
  - **把五个静默失败点抽成纯函数**再测试。没有 DOM 测试环境（vitest 跑在 node，无 jsdom），所以这是唯一能让它们被自动化覆盖的办法。
  - `riskTrends.ts` 与 `RiskTrends.tsx` 在 macOS 大小写不敏感文件系统上冲突（TS1149），故纯函数放在 `riskDistribution.ts`。评审认可。
  - 边界归一化的判定式选 `RiskScore !== null && SystemHealth !== "UNAVAILABLE"`。另外两种直觉写法分别会**清空全部历史**（`!assessment_available`）或**把历史上的捏造行判为可用**（`=== false`），评审用一次性探针验证了两者朝相反方向失败。
  - `App.tsx:66` 改为 `AlertSeverity: record.RiskLevel === null ? null : fsm.severity`（经 `utils/alertOverlay.ts:25`）—— 这一处 tsc **不会**提醒。

## 3. 测试结果

| 命令 | 结果 |
|---|---|
| `./node_modules/.bin/vitest run --no-cache` | **394 passed / 0 failed**（15 文件；基线 276/1） |
| `./node_modules/.bin/tsc --noEmit` | **exit 0，0 errors**（基线 34） |
| `pytest backend/tests -q` | 504 / 0（未触碰后端） |
| `./node_modules/.bin/eslint .` | exit 0 |
| `vite build` | ✓ |

注：本机 `npx` 会被 `rtk` 包装器改写，全部门禁改为直接调用 `./node_modules/.bin/*`。

**核心用例**：UT-PERS-MIGRATE-01（历史 localStorage 双向归一化）、UT-EXPORT-01（无评估单元格为空、JSON 保留 `dominant_evidence` 键）、UT-DIST-01（25 窗口四桶计数恰和为 25）、UT-TREND-01（null 点不被渲染成 `0.0 / 100`），以及一条 grep 断言确保 `SystemHealth === "UNAVAILABLE"` 不再出现在 `LiveMonitor.tsx`/`AlertBanner.tsx`。

**五个静默失败点**全部由评审**从当前源码重新推导**并逐一变异验证 —— 不是采信实现者的转述。实现者自报 M1–M17 共 17 个变异全部被杀死；评审另做 7 个自己的变异。

**修复轮 1**：评审发现 `riskDistribution.ts` 两处可用性守卫**没有测试防守**（删掉后仍 390/390 全绿）。补了一条自相矛盾记录的测试（`assessment_available: false` 且 `RiskLevel: "High"`）。复审独立复现：两个变异现在各使**恰好一条**测试变红；生产逻辑 blob hash 在修复前后都是 `a6421a42`，逐字节未改。

**存在但未执行的测试**：**没有任何 DOM / 组件渲染测试**。见第 4 节。

## 4. 问题与风险

- **失败测试**：无。
- **预期的临时兼容性错误**：**已全部清零**（tsc 34 → 0，vitest 1 失败 → 0）。
- **非预期回归**：无。评审确认没有改数据（`preparedSessionInput.ts` 与 `ai/prototype-data/` 零 diff）、没有削弱测试（全仓库仅 5 行测试被删，每行都被更强的断言替代）。
- **⚠️ 前端目前只被证明到「纯函数层」，没有被证明为 UI**：
  - 仓库里**没有任何 DOM / 渲染测试**。所有 JSX 条件分支（`LiveMonitor.tsx:87-122` 的三态、`AlertBanner` 的三个 return、`ExplanationView.tsx:259` 的分支）只经实现者手工浏览器验证。
  - Recharts 对 null 点的渲染行为（`filterNull={false}` + `connectNulls={false}` 真的画出断口）是**假设**，没有被观测。
  - CSS 是 grep 验证的 —— 规则和 class 字符串存在，但没有自动化确认 unavailable 窗口在屏幕上**看起来**确实不同。
  - **Live 模式从未对着真实后端跑过**，API 边界只被 stub 的 fetch 覆盖。
- **遗留 Minor**：
  1. 前后端 CSV 在 unavailable 表示之外仍有既有分歧（`vision_dominant` vs `Vision-dominant`、列名大小写、`40` vs `50.0`）。**不影响可追溯性** —— 两份导出是两个不同制品：live 走后端 `/export`，replay 走前端 `utils/export.ts`，没有任何记录会被两者同时导出。
  2. `vitest.config.ts:9` 的 include 仍只有 `*.test.ts`：将来新建的 `.test.tsx` 会被**静默跳过且不报错**。
  3. `ExplanationView` 对回放记录用的是**当前配置**权重（回放记录没有 `provenance.fusion_config`），所以配置改动后贡献度拆分会被**抑制并说明原因**，而不是给出错误数字。

## 5. 验收结论

**CONDITIONAL PASS**

理由：全部 Step 满足，tsc 与 vitest 的临时错误全部清零，五个静默失败点被独立重新推导并变异验证，唯一的 Important 已在一轮修复内关闭并经复审确认。判 CONDITIONAL 而非 PASS 的原因只有一个，但它很重要：**前端被证明的是「类型正确 + 纯函数逻辑正确」，不是「UI 渲染正确」**。没有 DOM 测试、Live 模式没有对真实后端跑过，这两件事属于 Task 10 的范围，在那之前不能声称 UI 已被验证。

## 6. 下一任务就绪度

- 本批的停止条件是 Task 6 之后停止，**不开始 Task 7**。
- Task 7 开工前**必须先处理**两项（详见总结报告）：
  1. **F2**：`inference.py:14-28` 的「EVERY key」说法与 watermark 豁免冲突 —— 按现有指引去做 Task 7 会静默杀死乱序守卫。
  2. **F4**：`ROUND_HALF_UP` 必须写回计划与 `global-constraints.md`，否则 Task 7–10 的 brief 不携带舍入模式。
