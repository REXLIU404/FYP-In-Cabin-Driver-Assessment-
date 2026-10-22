# Constructed scenario 设计文档（演示用的数据集图片回放）

- 日期：2026-10-22
- 分支 / 工作副本：`fyp2/dataset-replay`，`/Users/liu/Desktop/FYP2-Live-System-backups`（从 `fyp2/live-system` 的 `84a1891` 分出）
- 状态：设计四节已逐节经用户确认，本文件待用户审阅

## 1. 背景与目的

**为什么要做**

正面摄像头下，视觉分支实际上不可用。

| 证据 | 结果 |
|---|---|
| 2026-10-12 | 394 帧全部被判为 c8 |
| 2026-10-22，用户开发库 7 个会话 | 约 5,170 帧以 `hair_makeup` / `talking_to_passenger` / `reaching_behind` 为主，`safe_driving` 只出现 5 次，P_distraction 中位数 1.000 |

同一条实时路径在 State Farm test split（3,657 张）上的准确率是 0.8983，离线结果是 0.8988，10 类都会被预测到。所以管线没有问题，原因是**视角差异（domain shift）**：模型在侧面、副驾驶视角上训练，不能迁移到正面摄像头。证据见 `docs/evidence/2026-10-22/vision-runtime-path/`。

**这次要做什么**

用户 2026-10-13 决定：如果「把摄像头放到训练视角」（B）不成功，就以带严格标注的数据集图片回放作为兜底。2026-10-22 用户确认用途是 **A：演示**，即 B 已判定失败或来不及。

目标是做一个 **Constructed scenario** 模式：

- 把 State Farm **test split** 的图片当作「摄像头画面」，按剧本播放；
- 遥测按同一剧本，从 `Driver_Behavior` 的 test 集配对；
- 两路都走**真实的**实时管线：真实模型、R10、告警状态机、SQLite、五个视图和导出。

答辩时可以完整演示系统，并直观展示晚期融合的作用。

**成功标准**

1. 选择该模式后，能看到图片流；
2. 视觉概率随动作类别变化；
3. 风险等级与告警按剧本变化；
4. 全程看得出这是构造情景，不是实时监测。

## 2. 范围与非目标

- **不改动 `fyp2/live-system`**：全部工作在 `fyp2/dataset-replay` 上完成。
- **不是评估结果**：本模式的测试和演示运行报告只是工程检查，用来保证演示能跑通。**FYP 报告与答辩引用的结果只来自 Live 系统。** 本模式在报告中只作为演示手段出现，并与「正面摄像头视角差异」这条限制一起说明。
- 不训练、不调参模型，模型文件保持冻结。
- 不修复正面摄像头的视角问题，Live 模式保持现状。
- 旧的 legacy 预算概率回放只从下拉框中移除，代码与它的回归测试保留。

## 3. 剧本 `viva_v1`

**挑选规则**

- **每段的构成**：一位司机、一个视觉类别、一个遥测类别，加一个时长。时长是 2 s 的整数倍，保证两路的段落边界对齐。
- **视觉**：取该司机该类别 test 图片，按文件名排序，以 5 fps（每 200 ms 一帧）播放。文件名是随机编号，没有真实的时间顺序，所以这是「同一人同一动作的图片序列」，不是真视频。如果图片少于所需帧数，就按文件名顺序循环使用，清单记录循环了几次。
- **遥测**：从 `telemetry_test.csv` 中该类别的行里，用固定种子挑选，每 2 s 一行。
- **只按标签挑选，不按模型结果挑选。** 模型在 test 上的准确率约 0.90，演示中出现的误判是真实表现，不做筛选。

**分段**

| # | 时长 | 帧数 | 视觉类别 | 司机（可用帧） | 遥测类别 | 遥测行 | 展示内容 | 预期 |
|---|---|---|---|---|---|---|---|---|
| 1 | 20 s | 100 | c0 `safe_driving` | p050（123） | Safe | 10 | 基线 | Low → NORMAL |
| 2 | 16 s | 80 | c1 `texting_right` | p026（129） | Safe | 8 | **只有视觉异常** | 约 50 → Medium、CAUTION，Vision-dominant |
| 3 | 16 s | 80 | c4 `talking_phone_left` | p035（89） | Distracted | 8 | **两路都异常** | 约 100 → High → 2 s 后 HIGH_ALERT |
| 4 | 26 s | 130 | c0 `safe_driving` | p026（130） | Safe | 13 | 恢复 | Low 持续 10 s → NORMAL |
| 5 | 16 s | 80 | c0 `safe_driving` | p012（84） | Aggressive | 8 | **只有遥测异常** | 约 50 → Medium、CAUTION，Telemetry-dominant |
| 6 | 16 s | 80 | c7 `reaching_behind` | p035（87） | Distracted | 8 | 两路都异常 | HIGH_ALERT |
| 7 | 26 s | 130 | c0 `safe_driving` | p050（123，循环 7 帧） | Safe | 13 | 再次恢复 | NORMAL |

合计 136 s、680 帧、68 行遥测。4 位司机（p012、p026、p035、p050）都不在训练集中。第 7 段和第 1 段用的是同一位司机的同一组图片。

**「预期」一列**是按模型的典型输出估算的：视觉异常时 P_d ≈ 1，安全时 P_d 较低；遥测各类别的预测都很确定。实际结果以运行记录为准。

**剧本的核心论点**：只有一路异常时，融合分数大约 50，只到 CAUTION；两路同时异常时才会到 HIGH_ALERT。

**可选、默认不加**：一段「摄像头被挡住、只剩遥测」，用来展示数据过期与缺失的处理。

## 4. 架构与数据流

**数据流**

1. 生成脚本按剧本生成情景包；
2. 后端只读地提供情景包；
3. 前端的帧来源和遥测来源接入**现有的、未修改的** `ai/src/liveLoop.ts`；
4. `POST /infer` → 真实的 MobileNetV3 与 XGBoost → R10 与告警状态机 → SQLite → 五个视图与导出。

### 4.1 运行模式与标注

- **新增 `OperationMode = "CONSTRUCTED_SCENARIO_RUNTIME"`**，前后端同步：`ai/src/types.ts`、`backend/app/schemas.py`。
  - 每条记录的 `operation_mode` 都会写明是这个模式。
  - 内部按 Live 类处理：观测身份、规范采集时间、NEW-only EMA、双条件告警，调用真实模型。
  - 现在判断 `== "LIVE_MODEL_RUNTIME"` 的地方，改成判断「是否属于 Live 类模式」（`LIVE_LIKE_MODES`）。
- **来源标签由服务端按会话模式写入，不采用客户端的说法**：
  - `provenance.vision_source = "dataset_replay"`，不再在 `trained.py` 里写死成 `camera_frame`；
  - `provenance.telemetry_source = "dataset_replay"`；
  - `captured_at_source` 新增取值 `"replay_clock"`，只在本模式下接受。
- **真实标签块 `replay`**：请求可以附带
  ```json
  {"scenario_id", "segment_index", "frame_file", "vision_label", "telemetry_label", "telemetry_row"}
  ```
  - 只在本模式下接受，其他模式发送会返回 422；
  - 存入 `provenance.replay`，**不参与任何计算**；
  - 它是请求体的一部分，因此进入 request hash。
- **模式不能混用**：会话模式与请求不符时返回 409，沿用 `conflict_mode`。

### 4.2 情景包

- **剧本定义** `demo/scenarios/viva_v1.json` 提交进 git，内容是第 3 节的分段表、种子、fps（5）、遥测周期（2000 ms）。
- **生成脚本** `scripts/build_dataset_replay.py <scenario>`：
  - 从数据目录（`FYP_DATA_ROOT`，默认与 `freeze_manifest.py` 相同）读取 `vision_metadata_with_split.csv` 和 `telemetry_test.csv`；
  - **拒绝 test 以外的 split**，并核对所用司机不在 train / val 中；
  - 把图片复制到 `demo/bundles/<scenario>/frames/`，按 `NNNN_<原文件名>` 命名；
  - 写出 `manifest.json`，内容包括：剧本内容及其 SHA256、两个 CSV 的 SHA256、每帧的文件名 / 司机 / 类别 / SHA256 / 所属段、每行遥测的行号 / 8 个特征 / 类别、循环次数；
  - 同一种子必须得到完全相同的结果；
  - 脚本不导入任何模型代码。
- `demo/bundles/` 加入 `.gitignore`，**图片永不进入 git**。整个目录可以直接拷到答辩用的电脑上。

### 4.3 后端接口（只读）

- `GET /api/scenarios`：列出本机已有的情景包，每项包括 id、段数、时长、生成时间；
- `GET /api/scenarios/{id}/manifest`；
- `GET /api/scenarios/{id}/frames/{file}`：只允许清单里列出的文件名，防止路径穿越。
- 根目录取 `DRA_SCENARIO_ROOT`，默认 `<repo>/demo/bundles`。
  - 根目录不存在时，列表接口返回空列表；
  - 未知 id，或清单中没有的文件名，返回 404。

### 4.4 前端

- **`ai/src/scenarioTimeline.ts`（纯函数）**：给定有效播放时间，算出段号、全局帧序号、遥测序号和行号；判断剧本是否结束；处理暂停与恢复。
- **帧来源** `createScenarioFrameSource(manifest, images, clock)`，返回 `LiveFrame`：
  - 图片用预加载好的**原始 JPEG** data URL，不重新编码；
  - `vision_frame = {epoch: 本次运行开始的毫秒数, index: 全局帧序号}`，序号只增不减；
  - **`captured_at` 按分段基准计算**：每次开始或恢复时，以当时的墙钟为本分段的基准时间，加上本分段内的有效播放时间。这样帧的年龄只取决于播放节奏，暂停再继续也不会因为采集时间落后墙钟而被判为过期（裁定 A，3 s）；
  - `captured_at_source = "replay_clock"`。
- **遥测来源** `createScenarioTelemetrySource(manifest)`，实现现有的 `TelemetrySource` 接口：
  - 每 2 s 一个 seq，seq 只增不减；
  - **送哪一行由播放位置决定**（当前段，以及段内第几个 2 s），seq 只用作观测身份；
  - 采集时间与帧一样，按分段基准计算；
  - 暂停与恢复沿用现有游标的规则：恢复时立即开始一个新观测，即新的 seq，内容是当前播放位置对应的那一行。
- **同步方式**：两个来源由同一个有效播放时钟驱动，暂停时一起冻结，恢复后从原位置继续。剧本的段落边界由播放位置决定，所以无论中途暂停多少次，两路始终处在同一段。
- **`buildLivePayload`**：只在本模式下附带 `replay` 块，由帧的元数据和遥测行的元数据组成；遵守现有的字段省略规则。
- **hook `useScenarioReplay`**：负责取清单、预加载图片并显示进度，然后组装上面两个来源，交给现有的 Live 循环。

## 5. 界面

- **「Data mode」下拉框**只有两项：「Live camera (trained models)」和「**Constructed scenario**」。旧的 legacy 回放不再列出。每次打开页面仍从 Live 开始。
- **模式说明**：本模式**不显示**说明句。
- **剧本下拉框**（仅本模式显示）：列出本机的情景包。没有情景包时，显示一行提示和生成命令，Start Monitoring 不可点。预加载期间显示进度，完成后才能开始。
- **回放播放器** `ScenarioPlayer`：放在摄像头预览的位置，尺寸相同。
  - 左上角常驻 **CONSTRUCTED SCENARIO · not live**。
  - 画面下方显示当前段的说明，例如「Segment 2/7 · 只有视觉异常：texting_right · 司机 p026 · State Farm test split」。
  - **真实与模型对照**：「Truth: texting_right · Model: texting_right 0.97」。模型结果取自最新的记录，组件只负责显示。
  - **进度条**：7 个色块，当前段高亮，显示「已播放 / 总时长」。
  - 本模式没有 Start / Stop Camera 按钮，播放由顶部原有的 Start Monitoring / Pause 控制。
- **剧本结束后停止**：会话停在「Scenario finished（136 s，7 段）」，按 New Session 可以重新播放。一个会话 = 一次完整剧本。
- **「Vehicle Signals」**面板在本模式下标题改为「Scenario telemetry」，并显示当前遥测的真实类别。
- 五个视图的顶栏都带 **CONSTRUCTED SCENARIO** 标签；Signal Inspector 显示所选窗口的 `provenance.replay`。导出不需要改动。
- **分层不变**：计时逻辑放在 `ai/src`，取图与预加载放在 hook，组件只负责显示。

## 6. 错误处理

1. **情景包缺失或损坏**（清单哈希不符、缺少图片）：剧本下拉框显示原因，不能开始。
2. **预加载**：开始前加载全部约 680 张图片（约 25 MB）。万一某帧拿不到，就按「这一帧没有画面」处理（`captureFrame` 返回 null），如实记为视觉缺失，不伪造。
3. **后端出错**：沿用 D02 的重试和停止面板。停止期间播放时钟冻结，点 Retry 后从原位置继续，仍是同一个会话。
4. **模式混用**：服务端返回 409 / 422，见 4.1。
5. **数据卫生**：生成脚本只用 test split 并做司机核对；`.gitignore` 守住 `demo/bundles/`。

## 7. 测试（只作工程检查，不写入报告结果）

1. **vitest**：`scenarioTimeline` 的段号、帧序号、遥测序号和行号；段落边界两路对齐；暂停时冻结；**暂停再继续后，帧与遥测的年龄仍小于各自的周期**；身份只增不减；剧本结束的判断；两个来源的接口行为；只在本模式附带 `replay` 块；播放器的静态渲染（标签、对照、进度）。
2. **pytest（生成脚本）**：用几张假图组成的小数据集验证：同一种子生成结果完全相同；只按标签挑选；拒绝 train / val；清单哈希正确；不导入模型代码。
3. **pytest（后端）**：
   - 新模式可用；
   - 来源标签由服务端写入；
   - **改动真实标签，分数逐字节不变**；
   - `replay_clock` 只在本模式下接受；
   - 模式混用会被拒绝；
   - 情景包接口防路径穿越，没有情景包时返回 404；
   - 响应带 `X-DRA-Backend` 标识。
4. **端到端（Playwright，真实模型）**：用缩短的测试剧本（3 段 × 4 s）跑完整链路，检查：
   - 标签可见；
   - 每条记录都是新模式、来源为 `dataset_replay`；
   - 段落按时推进，剧本结束后停止；
   - 界面显示的真实标签与清单一致；
   - 五方逐窗口对账。

   本机没有数据目录或情景包时显式跳过。
5. **演示运行报告**（内部彩排用）：在后台把 `viva_v1` 完整跑一遍，按段输出「真实 vs 模型」的命中率，以及 RiskLevel 和告警的时间线。**不作为报告或答辩引用的结果。**
6. **变异**（在隔离副本中，每项都必须有测试变红）：
   - 真实标签进入了融合计算；
   - 服务端采用客户端声明的来源；
   - 循环时身份被重置；
   - 暂停时画面仍在前进；
   - 采集时间改用整次运行的基准：暂停再继续后，帧和遥测都被判为过期；
   - 遥测行改按 seq 取，不按播放位置：暂停恢复后两路错段；
   - 生成脚本使用了 train 数据；
   - 播放器上的标签消失。
7. **现有门禁保持全绿**。需要修改的既有测试只有下拉框选项那一条（`dataMode.test.ts`）。

## 8. 标注与诚实性约束（落实 2026-10-13 的条件）

| 条件 | 落实方式 |
|---|---|
| 到处标注、绝不称为实时监测 | `operation_mode = CONSTRUCTED_SCENARIO_RUNTIME`；provenance 来源为 `dataset_replay`；界面常驻 **CONSTRUCTED SCENARIO · not live**；导出带上述字段；报告只作为演示手段描述 |
| 按司机、类别编排，不随机 | 第 3 节的剧本 |
| 循环帧序号递增，避免被判为重复 | 4.4：`index` 和 `seq` 只增不减 |
| 遥测配对写明是构造的 | 模式名本身就是 Constructed scenario；清单记录配对 |
| 图片不进公开仓库 | `demo/bundles/` 被 git 忽略，测试守护 |
| test split 只用于评估与演示，不调参 | 生成脚本拒绝其他 split；本模式不产生任何训练或调参数据 |

## 9. 工作副本、环境与 ML 同步

- **工作副本**：`/Users/liu/Desktop/FYP2-Live-System-backups`，分支 `fyp2/dataset-replay`。`fyp2/live-system` 保持不变。
- **本地环境**（实施计划的第一步）：
  - `node_modules`：从 `FYP2-Live-System` 用 ditto 复制一份本地副本，不用符号链接，以免 vite 写到别的工作树；
  - `.venv`：沿用与系统轨道相同的做法；
  - 模型文件：以只读链接接入 `ml/outputs/`。
- **ML 同步**：ML 轨道（`fyp2/ml-training`）有新的冻结模型或 manifest 时，把相应提交合并进本分支，模型文件按同样方式链接。情景包与模型无关，换模型后不需要重新生成。

## 10. 未决与可选

- 「摄像头被挡住」段：默认不加。
- 循环播放：默认不循环，剧本结束后停止。
- 本分支将来是否合回 `fyp2/live-system` / `main`：由用户之后决定，本设计不预设。
