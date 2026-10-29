# R29 导航验收 — 2026-10-29

DS-3 / 用户决定：在 ≤900 px 隐藏品牌文字（`.brand-copy`），并把一行导航的滚动条从
`scrollbar-width: none` 改为 `thin`。本目录是修复后真实 Chromium 的测量与截图。

## 方法

- `npm run build` 后把 `dist/` 用一次性 `http.server` 挂在 127.0.0.1 的随机空闲端口（不碰 8000）；
- Playwright Chromium（`.venv`），viewport 高度 900，逐个宽度 `goto` 后读取
  `.nav-list` 的 `scrollWidth` / `clientWidth`、`scrollbar-width` 计算值、`.brand-copy` 的
  `display`，以及页面 `documentElement.scrollWidth` 与 `innerWidth`；
- 每个宽度截图 `nav-<width>.png`；原始数字 `nav-measurements.json`。

## 测量结果（修复后）

| viewport | nav scrollWidth | nav clientWidth | 是否放得下 | scrollbar-width | brand-copy | 页面是否横向溢出 |
|---|---:|---:|---|---|---|---|
| 390 px | 684 | 326 | 否（可滚动） | thin | none | 否（390 = 390） |
| 700 px | 684 | 636 | 否（差 48 px，可滚动） | thin | none | 否（700 = 700） |
| 800 px | 736 | 736 | **是** | thin | none | 否（800 = 800） |
| 1280 px | 203 | 203 | 是（侧栏布局） | auto | block | 否（1280 = 1280） |

- 690–900 px 的裁切问题在 800 px 已消除（六个视图按钮全部可见，见 `nav-800.png`）。
- 700 px 仍有约 48 px 溢出：导航可以横向滚动，细滚动条不再被隐藏（macOS 覆盖式滚动条
  只在滚动时绘出；`scrollbar-width` 计算值为 `thin`，见 JSON）。
- 390 px 窄屏可滚动，右缘露出下一个按钮，提示还有内容（见 `nav-390.png`）。
- 1280 px 回到常驻侧栏，品牌文字正常显示，不受影响。

## 复现

构建后用任意静态服务器把 `dist/` 挂在随机端口，在 Chromium 里设 390/700/800/1280 宽度，
读取上面四项数字并截图即可；本次命令与时间见提交信息与状态板。
