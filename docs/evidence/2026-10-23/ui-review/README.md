# UI 易用性审查截图（2026-10-23）

对五个视图做的易用性审查（用户要求「review the UI, make sure is user friendly」）。截图来自真实的仪表盘：一次性的 uvicorn 与数据库、Chromium 假摄像头、冻结模型，与端到端测试用的是同一套环境。

| 目录 | 内容 | 采集脚本 |
|---|---|---|
| `before/` | 修改前，提交 `87d8668` | `capture_before.py` |
| `after/` | 修改后，提交 `2745348`（界面改动在 `6886a2e`） | `capture_after.py` |

复现方法：在仓库根目录运行 `.venv/bin/python docs/evidence/2026-10-23/ui-review/capture_after.py <输出目录>`。

## 修改前发现的问题与对应截图

| 问题 | 修改前 | 修改后 |
|---|---|---|
| 状态标签没有名字（High / HIGH_ALERT / DEGRADED 并排，不知道哪个是哪个） | `before/01-live-monitor.png` | `after/01-live-monitor.png` |
| 统计列表里的标签被 CSS 拉成整行灰条，颜色也失效 | `before/06-camera-stopped.png`（Runtime State） | `after/01-live-monitor.png` |
| 会话 ID 折成三行 | `before/01-live-monitor.png` | `after/01-live-monitor.png` |
| 同一个数显示两次（100% 与 1.00） | `before/06-camera-stopped.png` | `after/01-live-monitor.png` |
| 点选窗口之后，看不出是「固定」还是「跟随最新」，也无法回到跟随最新（暂缓 minor M1） | `before/02-signal-inspector.png` | `after/02-inspector-following.png`、`after/03-inspector-pinned.png` |
| 视觉类别按类别编号排列、名字被截断 | `before/02-signal-inspector.png` | `after/03-inspector-pinned.png` |
| Risk Trends 的窗口表没有上限，页面约 5,600 px 高 | `before/03-risk-trends.png` | `after/04-risk-trends.png` |
| 分布图只标出一半类别 | `before/04-explanation.png` | `after/05-explanation.png` |
| Configuration 重复了顶栏的开始 / 暂停 / 重启按钮 | `before/05-configuration.png` | `after/06-configuration.png` |
| 摄像头运行时，半透明的禁用按钮「Start Camera」叠在画面上 | `before/09-stop-panel.png` | `after/10-stop-panel.png` |
| 故障停止时徽标写「Monitoring paused」，过期提示重复三次 | `before/09-stop-panel.png` | `after/10-stop-panel.png` |
| 手机宽度下，约 280 px 高的侧栏一直盖住屏幕上部 | `before/07-mobile-live-monitor.png`、`before/08-mobile-inspector.png` | `after/08-mobile-top.png`、`after/09-mobile-scrolled.png` |

截图本身不判定通过与否。对应的自动化检查是 `frontend/src/views/usability.test.ts`、`frontend/src/utils/selection.test.ts`、`frontend/src/utils/display.test.ts`，以及 `backend/tests/test_live_session_lifecycle.py` 的 test_05 与 test_07b。
