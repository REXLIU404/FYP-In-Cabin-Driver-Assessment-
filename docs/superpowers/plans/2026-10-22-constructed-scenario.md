# Constructed scenario 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增一个「Constructed scenario」模式：State Farm test split 的图片，配上 Driver_Behavior test 集的遥测行，按剧本以真实节奏（5 fps / 2 s）送进现有的 Live 管线，在答辩时演示真实模型、R10、告警、存储、五个视图与导出。

**Architecture:**
- 后端：新增运行模式 `CONSTRUCTED_SCENARIO_RUNTIME`，内部按 Live 类处理（同一条 R10 路径），来源标签由服务端按会话模式写入；另加一个只读的情景包接口。
- 离线：一个生成脚本按剧本从数据目录挑图、挑遥测行，生成被 git 忽略的情景包。
- 前端：一个纯函数的「播放时钟」同时充当遥测源和帧来源，接入现有的 Live 循环，循环逻辑不改；界面用「Constructed scenario」替换旧的「Prepared replay」选项。

**Tech Stack:** FastAPI + Pydantic + SQLite（pytest）；TypeScript + React（vitest，node 环境，`react-dom/server` 静态渲染）；Playwright（端到端）；Python 标准库写生成脚本。

**Spec:** `docs/superpowers/specs/2026-10-22-constructed-scenario-design.md`（2026-10-22 用户确认，第 11 节为修订记录）

**工作副本：** `/Users/liu/Desktop/FYP2-Constructed-Scenario`，分支 `fyp2/constructed-scenario`（从 `fyp2/live-system` 的 `bb947f0` 分出）。所有命令都在这个目录里运行。

## Global Constraints

- 运行模式取值 `"CONSTRUCTED_SCENARIO_RUNTIME"`；Live 仍是 `"LIVE_MODEL_RUNTIME"`；旧回放仍是 `"PREPARED_SESSION_RUNTIME"`。
- 「是否 Live 类模式」只有一个判断：后端 `is_live_like(mode)`，前端 `isLiveLike(mode)`。
- 本模式的 provenance：`vision_source = "dataset_replay"`、`telemetry_source = "dataset_replay"`（该分支缺失时为 `"missing"`），由服务端按会话模式写入。请求 schema 的 `telemetry_source` 取值范围**不**增加 `dataset_replay`。Live 仍是 `camera_frame` / `prepared_replay`。
- `captured_at_source` 新增 `"replay_clock"`，只在本模式下接受。
- 请求可选块 `replay = {scenario_id, segment_index, frame_file, vision_label, telemetry_label, telemetry_row}`：字段都可为空；`segment_index` 从 0 开始；存入 `provenance.replay`；**不参与任何计算**；值为空时**不进入** request hash。
- 非本模式的会话带 `replay` 或 `replay_clock`：422，类别 `input_validation`，在 `windows._infer` 里检查。
- Live 会话的 409 文本 `Create a live model session first` 与 `Input does not match session operation mode` 一字不改。
- 帧周期 200 ms（5 fps），遥测周期 2000 ms；每段时长必须同时是两者的整数倍。
- 只用 test split；所用司机不得出现在 train / val；只按标签挑选，生成脚本不导入任何模型代码；`demo/bundles/` 被 git 忽略，图片永不入库。
- 剧本 `viva_v1`：7 段，20 / 16 / 16 / 26 / 16 / 16 / 26 s，共 136 s、680 帧、68 行遥测（分段表见 spec 第 3 节，逐字照搬）。
- 界面文字：下拉框两项 `Live camera (trained models)` 与 `Constructed scenario`；播放器标签 `CONSTRUCTED SCENARIO · not live`；顶栏标签 `CONSTRUCTED SCENARIO`；本模式**不显示**模式说明句；剧本结束显示 `Scenario finished`。
- 每次打开页面从 Live 开始（`loadConfig` 不变）。剧本结束即停止，不循环。
- Live 循环（`ai/src/liveLoop.ts` 的循环逻辑）不改，只扩展类型与 `buildLivePayload`。
- 报告与答辩引用的结果只来自 Live。本模式的测试和运行报告是工程检查。
- `backend/tests/e2e_support.py` 与 Tasks1-10 会话共享：修改前先用 SendMessage 通知 `local_51808963-6280-4a75-a5a4-1354fa430268`。
- 合并回 `fyp2/live-system` 之前：先与 Tasks1-10 确认，再在合并后的树上运行 `DRA_REQUIRE_MODELS=1 python3 scripts/run_gates.py`，全绿才快进合并（见 Task 10）。
- 命令（不用 `npx`）：
  - pytest：`cd backend && PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. ../.venv/bin/python -m pytest tests/<file> -q -p no:cacheprovider`
  - vitest：`./node_modules/.bin/vitest run <file>`
  - `./node_modules/.bin/tsc --noEmit`、`./node_modules/.bin/eslint .`
  - 全量门禁：`DRA_REQUIRE_MODELS=1 python3 scripts/run_gates.py`
- 测试期望值写成字面量，不从实现里导入文本、类别名或头名（沿用仓库惯例）。

## Review Focus

1. **暂停超过 3 s 再继续**：继续后的第一个窗口，两路都必须是 fresh（采集时间以恢复时刻为基准）。→ Task 5 单测 `test_ages_stay_below_one_period_after_a_long_pause`，Task 8 端到端暂停 4 s 的步骤。
2. **后端出错停下、再点 Retry**：同一会话，剧本从停下的位置继续，冻结的请求原样重发；停止期间播放位置不前进。→ Task 6 `test_a_stopped_loop_freezes_playback_and_retry_continues_it`。
3. **重复的 resume**（循环在丢掉迟到帧后会对正在运行的遥测源再调一次 resume）：必须是空操作，不得开新 seq。→ Task 5 `test_resume_while_running_is_a_no_op`。
4. **从 Live 切到本模式再开始**：必须新建一个 `CONSTRUCTED_SCENARIO_RUNTIME` 会话，不得沿用 Live 会话。→ Task 6 `test_switching_mode_creates_a_session_of_the_new_mode`。
5. **采集时间永不超前墙钟**（服务端拒绝超前 5 s 的时间戳，422 会停掉会话）。→ Task 5 `test_acquisition_times_never_run_ahead_of_now`。

## 执行顺序（2026-10-23 补充）

Tasks1-10 还在改与本计划重叠的产品文件，所以：
- **Task 3**（剧本定义与生成脚本）只新增文件、改 `.gitignore`，与它的改动没有交集，可以在同步之前先做。
- **Task 1、2、4–9** 等 Step 0 的同步完成之后再做，避免在它改动之前写的代码到合并时冲突。
- 其余规则不变。

---

### Task 1：后端——新模式走同一条 Live / R10 路径（含本地环境）

**Files:**
- Modify: `backend/app/schemas.py`（`OperationMode` 字面量；常量与 `is_live_like`）
- Modify: `backend/app/inference.py`（`run_inference` 中 `live = ...` 一行与相关注释、`ValueError` 文本）
- Modify: `backend/app/routers/windows.py`（`_infer` 的模式检查与写入模式、`_persist_window` 中的 Live 判断）
- Modify: `backend/app/routers/status.py`（两处 `== "LIVE_MODEL_RUNTIME"`）
- Modify: `backend/tests/test_r10_fsm.py`、`backend/tests/test_r10_observations.py`（只做参数化，断言不变）
- Create: `backend/tests/test_constructed_mode.py`

**Interfaces:**
- Produces（`backend/app/schemas.py`）：`LIVE_MODE = "LIVE_MODEL_RUNTIME"`、`CONSTRUCTED_MODE = "CONSTRUCTED_SCENARIO_RUNTIME"`、`def is_live_like(mode: str) -> bool`。`inference.py` 从 schemas 导入并继续导出 `LIVE_MODE`（现有调用方不变）。
- Produces：`/infer` 用**会话自己的模式**调用 `_persist_window(..., mode=<session mode>)`，记录的 `operation_mode` 就是会话模式。

- [ ] **Step 0：同步起点**（**用户同意后**才做）：2026-10-23 Tasks1-10 通知暂停同步——它按用户要求继续改 `fyp2/live-system`（合并 `dev_cc`；修 App.tsx / SignalInspector.tsx / inference.py / liveLoop.ts / client.ts / e2e_support.py / conftest.py；做一轮 UI 易用性审查，可能改 LiveMonitor.tsx、各视图与 styles.css）。**不合并 `447cd2a`**；等它发来新的稳定提交号（全量门禁已通过），再在本工作副本 `git merge --no-edit <该提交>`，有冲突就停下报告。基线以合并后的实测为准。
  - **Tasks1-10 已告知的接口变化**（2026-10-23；后续任务以同步后的实际代码为准，不要照搬本计划写作时的旧形状）：
    - `App.tsx` 新增 `SelectionBar`，删去传给 `ConfigurationView` 的 `onStart` / `onPause` / `onRestart`；
    - `LiveMonitor.tsx` 新增 `stopped` prop；
    - `ai/src/liveLoop.ts` 的 `LiveLoopApi.infer` 增加可选的第 5 个参数 `onServerTiming`；
    - `frontend/src/api/client.ts` 的 `request` 增加 `onOk` 回调；
    - `backend/tests/e2e_support.py`：`drop_images` 写法改变；`LATEST_PANEL_JS` 的概率改为读卡片 `strong` 的 `title`，格式 `P = 0.50`。
- [ ] **Step 1：准备本工作副本的环境**（参照 `scripts/coldstart_check.sh`，就地进行）
  - `python3 -m venv .venv && .venv/bin/pip install -r backend/requirements.lock.txt`
  - `npm ci`
  - 模型只读链接：`mkdir -p ml/outputs/vision ml/outputs/telemetry`，把 `mobilenetv3_large_vision.onnx`、`mobilenetv3_large_vision.pt`、`xgb_telemetry.json` 链接到 `/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1/ml/outputs/` 下的同名文件（与 `FYP2-Live-System` 相同）
  - 运行 `DRA_REQUIRE_MODELS=1 python3 scripts/run_gates.py --out <scratch>`。期望：全绿，作为基线计数（预计与 Tasks1-10 的 pytest 1028 / vitest 922 一致，以实测为准）。

- [ ] **Step 2：写失败的测试** `backend/tests/test_constructed_mode.py`
  - `test_is_live_like`：`is_live_like("LIVE_MODEL_RUNTIME") is True`，`is_live_like("CONSTRUCTED_SCENARIO_RUNTIME") is True`，`is_live_like("PREPARED_SESSION_RUNTIME") is False`，`is_live_like("NO_SUCH_MODE") is False`。
  - `test_a_constructed_session_is_created_and_echoed`：`POST /api/sessions` 带 `operation_mode: "CONSTRUCTED_SCENARIO_RUNTIME"` → 201，响应与 `GET /api/sessions/{id}` 都回显该模式。
  - `test_infer_on_a_constructed_session_stores_records_under_that_mode`：用 `test_r10_observations.py` 的 `ProbStub` 方式替换 provider，发一条 `/infer` → 201，记录与 `GET /windows` 中的 `operation_mode == "CONSTRUCTED_SCENARIO_RUNTIME"`。
  - `test_a_replay_session_still_gets_the_unchanged_409`：`PREPARED_SESSION_RUNTIME` 会话调 `/infer` → 409，`detail == "Create a live model session first"`。
  - `test_status_reports_models_for_a_constructed_session`：`GET /api/sessions/{id}/system-status` 中 `models_loaded` 与 `ai_provider` 与同样设置下的 Live 会话相同。

- [ ] **Step 3：运行，确认失败**（新模式会被 schema 拒绝成 422）。

- [ ] **Step 4：实现**
  - `OperationMode` 加入新值；`is_live_like(mode) -> bool` 判断是否属于 `{LIVE_MODE, CONSTRUCTED_MODE}`。
  - `inference.run_inference`：`live = is_live_like(operation_mode)`；`ValueError` 文本改为「a Live-like mode needs the observation verdicts of the request」；更新提到「LIVE_MODEL_RUNTIME only」的注释。
  - `windows._infer`：在 `db.rollback()` **之前**取 `mode = sess.operation_mode`；检查改为 `if not is_live_like(mode)`，409 文本不变；`_persist_window(..., mode=mode, ...)`。`_persist_window` 内 `if mode == inference.LIVE_MODE:` 改为 `if is_live_like(mode):`。`_infer` 的签名保持 `(db, session_id, payload)`（`test_backend_marker.py` 依赖）。
  - `status.py` 两处改为 `is_live_like(...)`。

- [ ] **Step 5：参数化现有 R10 测试**
  - `test_r10_observations.py`：`Driver` 与 `drive` fixture 加 `mode` 参数，`drive` fixture 用 `params=["LIVE_MODEL_RUNTIME", "CONSTRUCTED_SCENARIO_RUNTIME"]`。
  - `test_r10_fsm.py`：直接调用 `run_inference(..., operation_mode="LIVE_MODEL_RUNTIME", ...)` 的测试改用 fixture `live_mode`，同样两个取值。
  - 断言一律不改。只按模式区分的测试（例如检查 PREPARED 行为的）保持原样。

- [ ] **Step 6：运行**新文件与两个 R10 文件全部通过；全量 pytest 通过，计数增加 = 新文件条数 + 被参数化的条数（报告里逐项写明）。

- [ ] **Step 7：变异**（隔离副本）：`is_live_like` 对新模式返回 False → 新文件与参数化后的 R10 测试变红；`_infer` 写回 `mode=LIVE_MODE` → `test_infer_on_a_constructed_session_stores_records_under_that_mode` 变红（409）。

- [ ] **Step 8：提交** `feat(backend): CONSTRUCTED_SCENARIO_RUNTIME runs the Live/R10 path; one is_live_like check; R10 tests for both modes`

---

### Task 2：后端——来源标签、`replay` 块与 `replay_clock`

**Files:**
- Modify: `backend/app/schemas.py`（`ReplayInfo`、`LiveInput.replay`、`captured_at_source` 字面量、hash 可选字段）
- Modify: `backend/app/routers/windows.py`（`_infer`：模式限制 422、provenance 覆盖）
- Create: `backend/tests/test_constructed_labels.py`

**Interfaces:**
- Consumes：Task 1 的 `CONSTRUCTED_MODE`、`is_live_like`。
- Produces（`schemas.py`）：
  ```python
  class ReplayInfo(BaseModel):  # extra="forbid"，与 VisionFrame 同一写法
      scenario_id: str           # 1..100，^[A-Za-z0-9_-]+$
      segment_index: int         # ge=0
      frame_file: Optional[str] = None      # ^[A-Za-z0-9._-]+$，max 200
      vision_label: Optional[str] = None    # max 64
      telemetry_label: Optional[Literal["Safe", "Aggressive", "Distracted"]] = None
      telemetry_row: Optional[int] = None   # ge=0
  ```
  `LiveInput.replay: Optional[ReplayInfo] = None`；`captured_at_source` 字面量加 `"replay_clock"`；`"replay"` 加入值为 None 时不进 hash 的字段集合（把 `R10_OPTIONAL_FIELDS` 扩成 `HASH_OPTIONAL_FIELDS` 或另设一个元组，`canonical_body` 两者都处理）。
- Produces（provenance）：本模式下 `vision_source`、`telemetry_source` 如 Global Constraints；`provenance.replay = payload.replay.model_dump()`（为空时为 `None`）。

- [ ] **Step 1：写失败的测试** `backend/tests/test_constructed_labels.py`
  - `test_the_server_writes_dataset_replay_whatever_the_client_claims`：本模式会话，请求带图像与遥测、`telemetry_source: "prepared_replay"`；记录 `provenance.vision_source == "dataset_replay"`、`provenance.telemetry_source == "dataset_replay"`。使用真实 `TrainedProvider` + 假权重的路径（`test_fault_events.py` 的 `live` fixture 方式），证明覆盖胜过 `trained.py` 的 `camera_frame`。
  - `test_an_absent_branch_is_labelled_missing`：无图像 → `vision_source == "missing"`；无遥测 → `telemetry_source == "missing"`。
  - `test_live_sessions_still_say_camera_frame_and_prepared_replay`。
  - `test_the_replay_block_is_kept_in_provenance`：`provenance.replay` 与发送的块逐字段相等。
  - `test_truth_labels_never_change_the_scores`：两个本模式会话，输入完全相同、`replay` 标签不同（例如 `vision_label` 互换、`telemetry_label` 不同）；两边记录除 `provenance.replay`、`request_id`、`session_id`、时间戳类字段外逐字段相等。
  - `test_a_replay_block_on_a_live_session_is_422` 与 `test_replay_clock_on_a_live_session_is_422`：422，`GET /api/faults` 中类别 `input_validation`。
  - `test_an_absent_replay_block_keeps_the_request_hash`：`LiveInput(...).canonical_body()` 不含键 `"replay"`；`test_r10_observations.py` 的 `LEGACY_BODIES` 字面量 hash 测试保持通过。
  - `test_the_same_request_id_with_another_replay_block_is_409`：detail 为现有的 `request_id already used for different input`。
  - `test_the_request_schema_does_not_accept_dataset_replay`：`telemetry_source: "dataset_replay"` → 422（schema）。
  - `test_both_exports_show_dataset_replay`：JSON 与 CSV 导出的 `vision_source` / `telemetry_source` 列为 `dataset_replay`；CSV 的 `provenance` 单元格含 `replay`。

- [ ] **Step 2：运行，确认失败。**

- [ ] **Step 3：实现**
  - schemas 如 Interfaces。
  - `windows._infer`：取得 `mode` 后、计算 digest 之前：`if mode != CONSTRUCTED_MODE and (payload.replay is not None or payload.captured_at_source == "replay_clock"): raise FaultHTTPException(422, "replay data is accepted only in a constructed scenario session", error_category=faults.CATEGORY_INPUT_VALIDATION, origin=faults.ORIGIN_REQUEST_VALIDATION)`。
  - 现有那一行 provenance 组装之后：`if mode == CONSTRUCTED_MODE:` 覆盖两个来源标签并写入 `replay`。`trained.py` 不改。

- [ ] **Step 4：运行**新文件、`test_r10_observations.py`、`test_r10b_payload_contract.py`、`test_backend_marker.py`、`test_retry_contract.py` 全部通过；全量 pytest 通过。

- [ ] **Step 5：变异**：服务端改用客户端的 `telemetry_source` → 第一条测试变红；`replay` 的某字段参与融合（例如 `vision_label == "safe_driving"` 时把 P_distraction 置 0）→ `test_truth_labels_never_change_the_scores` 变红；`"replay"` 不在 hash 可选字段里 → `LEGACY_BODIES` 与 `test_an_absent_replay_block_keeps_the_request_hash` 变红。

- [ ] **Step 6：提交** `feat(backend): constructed scenario labels - server-authoritative dataset_replay, replay block in provenance (never in fusion), replay_clock`

> **合并点 M1**：Task 1–2 完成后，按 Task 10 的规则合并一次。

---

### Task 3：剧本定义与情景包生成脚本

**Files:**
- Create: `demo/scenarios/viva_v1.json`、`demo/scenarios/e2e_short.json`
- Create: `scripts/build_dataset_replay.py`
- Modify: `.gitignore`（加 `demo/bundles/`）
- Create: `backend/tests/test_build_dataset_replay.py`

**Interfaces:**
- 剧本文件格式：
  ```json
  {"scenario_id": "viva_v1", "seed": 20261022, "frame_period_ms": 200, "telemetry_period_ms": 2000,
   "segments": [{"title": "Baseline", "duration_s": 20, "driver_id": "p050", "vision_class": "c0", "telemetry_label": "Safe"}, ...]}
  ```
  `viva_v1` 的 7 段逐字照搬 spec 第 3 节分段表（司机、类别、遥测类别、时长）；`title` 用该表「展示内容」一列的英文（Baseline / Vision only / Both / Recovery / Telemetry only / Both / Recovery）。`e2e_short`：3 段 × 4 s（c0 + Safe、c1 + Safe、c4 + Distracted，司机 p026）。
- 类别名映射（脚本内写死，测试钉住）：`c0 safe_driving, c1 texting_right, c2 talking_phone_right, c3 texting_left, c4 talking_phone_left, c5 operating_radio, c6 drinking, c7 reaching_behind, c8 hair_makeup, c9 talking_to_passenger`。
- 命令行：`python3 scripts/build_dataset_replay.py <scenario_id> [--out demo/bundles] [--data-root PATH]`；不给 `--data-root` 时用 `freeze_manifest.resolve_data_root()`（同目录导入）。
- 输出 `demo/bundles/<scenario_id>/manifest.json` 与 `frames/NNNN_<原文件名>`：
  ```json
  {"schema": "constructed-scenario/1", "scenario_id": "...", "scenario_sha256": "...", "generated_at": "<ISO UTC>",
   "frame_period_ms": 200, "telemetry_period_ms": 2000, "duration_ms": 136000,
   "sources": {"split": "test", "vision_metadata_sha256": "...", "telemetry_csv_sha256": "..."},
   "segments": [{"index": 0, "title": "...", "start_ms": 0, "duration_ms": 20000, "driver_id": "p050",
                 "vision_class": "c0", "vision_label": "safe_driving", "telemetry_label": "Safe",
                 "first_frame": 0, "frame_count": 100, "frame_cycles": 0, "first_telemetry": 0, "telemetry_count": 10}],
   "frames": [{"n": 0, "file": "0000_img_1234.jpg", "source_file": "img_1234.jpg", "driver_id": "p050",
               "class_id": "c0", "vision_label": "safe_driving", "segment_index": 0, "sha256": "..."}],
   "telemetry": [{"n": 0, "row": 1234, "label": "Safe", "segment_index": 0,
                  "features": {"speed_kmph": 0.0, "accel_x": 0.0, "accel_y": 0.0, "brake_pressure": 0.0,
                               "steering_angle": 0.0, "throttle": 0.0, "lane_deviation": 0.0, "headway_distance": 0.0}}]}
  ```
- 挑选规则：
  - 帧：该司机该类别的 test 图片按 `filename` 排序取前 `duration_ms / 200` 张，不够时按序循环，记录 `frame_cycles`。
  - 遥测：`telemetry_test.csv` 中 `behavior_label` 等于该类别的行（行号从 0 计），用 `random.Random(seed * 1000 + segment_index)` 不放回抽 `duration_ms / 2000` 行，按抽中顺序排列。

- [ ] **Step 1：写失败的测试** `backend/tests/test_build_dataset_replay.py`。在 `tmp_path` 里造一个小数据集：元数据 CSV 带 train / val / test、两位 test 司机、每类几张 16×16 的 JPEG；`telemetry_test.csv` 每类 5 行。
  - `test_the_same_seed_builds_the_same_bundle`：两次生成，manifest 除 `generated_at` 外逐字节相同，帧文件 SHA256 相同。
  - `test_frames_are_chosen_by_label_and_filename_order`。
  - `test_frames_cycle_when_a_driver_has_too_few_and_it_is_recorded`。
  - `test_it_refuses_a_split_other_than_test`（剧本里的司机只在 train 中）与 `test_it_refuses_a_driver_seen_in_training`（同一司机同时出现在 test 与 train）。
  - `test_durations_must_be_multiples_of_both_periods`（例如 15 s → 报错）。
  - `test_manifest_hashes_match_the_copied_files`。
  - `test_the_builder_imports_no_model_code`：在子进程里导入脚本后，`onnxruntime`、`xgboost`、`torch` 都不在 `sys.modules`。
  - `test_the_class_name_mapping`：上面 10 个名字逐一对应。
  - `test_viva_v1_is_the_table_of_the_spec`：读 `demo/scenarios/viva_v1.json`，7 段的（时长、司机、类别、遥测类别）与 spec 表逐字相等，合计 136 s。
  - `test_bundles_are_git_ignored`：`git check-ignore -q demo/bundles/x/manifest.json` 返回 0。

- [ ] **Step 2：运行，确认失败。** **Step 3：实现。** **Step 4：运行通过。**

- [ ] **Step 5：用真实数据生成一次**：`python3 scripts/build_dataset_replay.py viva_v1` 与 `e2e_short`。核对 `viva_v1` 共 680 帧、68 行遥测，第 7 段 `frame_cycles` 记录了循环 7 帧。`git status` 中看不到 `demo/bundles/`。

- [ ] **Step 6：变异**：改用 train split → 拒绝测试变红；挑帧时打乱顺序 → 同种子测试变红。

- [ ] **Step 7：提交**（不含 `demo/bundles/`）`feat(demo): constructed scenario definitions and the bundle builder (test split only, label-based, git-ignored output)`

---

### Task 4：后端——只读情景包接口

**Files:**
- Modify: `backend/app/config.py`（`scenario_root`）
- Create: `backend/app/routers/scenarios.py`
- Modify: `backend/app/main.py`（导入并注册，位置在静态挂载之前）
- Create: `backend/tests/test_scenarios_api.py`

**Interfaces:**
- `Settings.scenario_root: Path = <repo>/demo/bundles`（`DRA_SCENARIO_ROOT`）。路由**每次请求时**读取 `settings.scenario_root`。
- `router = APIRouter(prefix="/api/scenarios")`：
  - `GET /api/scenarios` → `[{"id", "segments", "duration_ms", "generated_at", "status": "ok" | "invalid", "error": str | null}]`，按 id 排序；根目录不存在时 `[]`。
  - `GET /api/scenarios/{scenario_id}/manifest` → manifest JSON。
  - `GET /api/scenarios/{scenario_id}/frames/{file}` → `image/jpeg`。只允许 manifest 中列出的 `file`；`{file}` 用普通路径参数，不用 `:path`。
- 完整性检查（列表接口）：manifest 能解析且 `schema == "constructed-scenario/1"`；每个 `frames[].file` 存在；SHA256 与 manifest 一致。不符时 `status: "invalid"`，`error` 写明第一处原因（例如 `frame 0003_img_9.jpg is missing`、`frame 0003_img_9.jpg does not match its sha256`）。

- [ ] **Step 1：写失败的测试** `backend/tests/test_scenarios_api.py`（用 Task 3 的生成函数在 `tmp_path` 造包；`monkeypatch.setattr(settings, "scenario_root", tmp_path)`）
  - `test_no_root_lists_nothing`；`test_a_good_bundle_is_listed_ok`（id、segments、duration_ms 字面量）
  - `test_a_missing_frame_makes_the_bundle_invalid_with_its_reason`；`test_a_changed_frame_makes_the_bundle_invalid_with_its_reason`
  - `test_the_manifest_is_served`；`test_an_unknown_scenario_is_404`
  - `test_a_listed_frame_is_served_as_jpeg`；`test_a_file_not_in_the_manifest_is_404`
  - `test_path_traversal_is_404`：请求 `frames/..%2Fmanifest.json`、`frames/%2E%2E%2F...` 等，均为 404，且响应体不是 manifest
  - `test_scenario_answers_carry_the_backend_marker`：三个接口的 200 与 404 都带 `x-dra-backend: 1`

- [ ] **Step 2–4：失败 → 实现 → 通过。** 全量 pytest 通过。

- [ ] **Step 5：变异**：去掉「只允许 manifest 中的文件」→ 穿越或越权测试变红；跳过 SHA256 检查 → `changed_frame` 测试变红。

- [ ] **Step 6：提交** `feat(backend): read-only /api/scenarios (list with integrity status, manifest, whitelisted frames)`

> **合并点 M2**：Task 3–4 完成后合并一次。

---

### Task 5：前端纯逻辑——模式判断、播放时钟、请求组装

**Files:**
- Modify: `ai/src/types.ts`（`OperationMode` 加新值）
- Create: `ai/src/operationMode.ts`（`isLiveLike`）
- Create: `ai/src/scenarioTimeline.ts`、`ai/src/scenarioTimeline.test.ts`
- Modify: `ai/src/liveLoop.ts`（只改类型与 `buildLivePayload`）
- Modify: `ai/src/liveLoop.test.ts` 或新建 `ai/src/scenarioPayload.test.ts`
- Create: `backend/tests/fixtures/constructed_payload_shapes.json`、`backend/tests/test_constructed_payload_contract.py`

**Interfaces:**
- `export function isLiveLike(mode: OperationMode): boolean`。
- `liveLoop.ts`：
  - `CapturedAtSource` 加 `"replay_clock"`；
  - `LiveFrame.replay?: { scenario_id: string; segment_index: number; frame_file: string; vision_label: string }`；
  - `TelemetryReading.replay?: { scenario_id: string; segment_index: number; telemetry_row: number; telemetry_label: "Safe" | "Aggressive" | "Distracted" }`；
  - `export interface ReplayBlock { scenario_id: string; segment_index: number; frame_file?: string; vision_label?: string; telemetry_row?: number; telemetry_label?: "Safe" | "Aggressive" | "Distracted" }`，`LivePayload.replay?: ReplayBlock`（字段与后端 `ReplayInfo` 一一对应）。
  - `buildLivePayload`：帧或遥测带 `replay` 时组装 `payload.replay`，`scenario_id` / `segment_index` 取自帧（没有帧时取自遥测）；帧字段只在有帧时带，遥测字段只在有遥测时带；两边都没有时省略整个键。
- `scenarioTimeline.ts`：
  - `ScenarioManifest`、`ScenarioSegment`、`ScenarioFrame`、`ScenarioTelemetryRow` 类型，镜像 Task 3 的 manifest。
  - `export interface PlaybackSnapshot { positionMs: number; segmentIndex: number; frameN: number; finished: boolean; running: boolean }`
  - ```ts
    export function createScenarioPlayback(
      manifest: ScenarioManifest,
      frameImage: (n: number) => string | null,  // 预加载好的 data URL
      now: () => number,
    ): { telemetry: TelemetrySource; captureFrame(): LiveFrame | null; snapshot(): PlaybackSnapshot }
    ```
  - 规则（决定性的部分，必须照做）：
    - 播放位置 `pos` 只在 running 时随墙钟增加，并封顶在 `duration_ms - 1`；`finished = pos >= duration_ms - 1`。
    - `reset(t)`：pos = 0，`base = t`，`posAtBase = 0`，`epoch = t`，seq = 0，running。
    - `pause(t)`：把 pos 推进到 t 后冻结（running 时才生效，幂等）。
    - `resume(t)`：**已在 running 时是空操作**；否则 `base = t`、`posAtBase = pos`，seq + 1（立即开始一个新观测）。
    - 帧：`n = floor(pos / frame_period_ms)`；`vision_frame = { epoch, index: n }`；`captured_at = base + max(0, n * frame_period_ms - posAtBase)`；`captured_at_source = "replay_clock"`；`image_base64 = frameImage(n)`，为 null 时 `captureFrame` 返回 null。
    - 遥测：`k = floor(pos / telemetry_period_ms)`，行取 `manifest.telemetry[k]`（**按位置，不按 seq**）；seq 在 k 增加时 + 1；`acquiredAtMs = base + max(0, k * telemetry_period_ms - posAtBase)`。
    - 段号由位置决定，帧和遥测在同一时刻永远落在同一段。

- [ ] **Step 1：写失败的测试** `ai/src/scenarioTimeline.test.ts`（造一个 2 段 × 4 s 的小 manifest，注入可控的 `now`）
  - `segments, frames and telemetry rows follow the position`：t = 0、199、200、3999、4000 ms 的段号、帧号、遥测行号用字面量断言。
  - `segment boundaries coincide for frames and telemetry`。
  - `a paused playback does not move`。
  - `test_ages_stay_below_one_period_after_a_long_pause`：暂停 10 s 再 resume，紧接着读取的帧年龄 < 200 ms、遥测年龄 < 2000 ms。
  - `test_resume_while_running_is_a_no_op`：running 时 resume，seq 不变。
  - `resume opens a new telemetry observation (seq + 1) on the row of the current position`。
  - `frame identity only grows and the epoch changes only on reset`。
  - `test_acquisition_times_never_run_ahead_of_now`：随机取 200 个时刻（固定种子），`captured_at` 与 `acquiredAtMs` 都 ≤ now。
  - `the scenario finishes at its duration and then keeps returning the last frame`。
  - `a missing image yields no frame`。
- [ ] 同时写 `buildLivePayload` 的测试：Live 请求没有 `replay` 键；本模式请求带完整 `replay`；没有帧时只带遥测字段；没有遥测时只带帧字段。
- [ ] 跨语言契约：`constructed_payload_shapes.json` 收录上面三种请求形状（字面量 JSON）；`test_constructed_payload_contract.py` 在本模式会话上逐一 POST 得到 201，在 Live 会话上得到 422。

- [ ] **Step 2–4：失败 → 实现 → 通过。** vitest、tsc、eslint 全部通过。

- [ ] **Step 5：变异**：暂停时位置仍随墙钟前进 → `a paused playback does not move` 变红；采集时间改用整次运行的基准 → 长暂停测试变红；遥测行改按 seq 取 → resume 测试变红；resume 在 running 时也开新 seq → no-op 测试变红；循环时帧号回到 0 → identity 测试变红。

- [ ] **Step 6：提交** `feat(ai): scenario playback clock (frame + telemetry source on one position) and the replay block in buildLivePayload`

---

### Task 6：前端接线——API、情景 hook、可切换的遥测源

**Files:**
- Modify: `frontend/src/api/client.ts`（`create` 用 `config.operationMode`；新增情景接口）
- Create: `frontend/src/data/switchableTelemetry.ts`（+ 测试）
- Create: `frontend/src/hooks/useScenarioReplay.ts`
- Create: `frontend/src/data/scenarioPreload.ts`（+ 测试）
- Modify: `frontend/src/hooks/useLiveSession.ts`（遥测源改为可切换；`refreshSessions` 按当前模式过滤）
- Modify: `frontend/src/hooks/useCameraPreview.ts`（只在 `CaptureMiss` 加一个取值）与显示 capture miss 文字的位置

**Interfaces:**
- `api.create` 的 `operation_mode` 取 `config.operationMode`，`description` 按模式给出：Live 原文不变；本模式 `"Constructed scenario: State Farm test frames + Driver_Behavior test rows through trained models"`。
- `api.scenarios(): Promise<ScenarioListItem[]>`、`api.scenarioManifest(id): Promise<ScenarioManifest>`、`api.scenarioFrameUrl(id, file): string`。
- `createSwitchableTelemetry(current: () => TelemetrySource): TelemetrySource`：每次调用都转发给 `current()` 当时返回的源。
- `preloadFrames(manifest, fetchFrame: (file: string) => Promise<Blob>, onProgress: (done: number, total: number) => void): Promise<string[]>`：返回按 `n` 排列的 data URL；任何一帧失败都 reject，并带上文件名。
- `useScenarioReplay(api)` 返回 `{ scenarios, selectedId, select(id), status: "idle" | "loading" | "ready" | "invalid", progress, error, playback: ReturnType<typeof createScenarioPlayback> | null }`。
- `useLiveSession(config, captureFrame, telemetry?: () => TelemetrySource)`：不给第三个参数时行为与现在完全相同。注意 `captureFrame` 的类型是 `() => CaptureResult`（`useCameraPreview.ts`），不是 `LiveFrame | null`。
- `scenarioCapture(playback): () => CaptureResult`（放在 `useScenarioReplay.ts`）：有帧时 `{ frame, reason: null }`，没有帧时 `{ frame: null, reason: "scenario_frame_unavailable" }`。`CaptureMiss` 联合类型新增这个取值（现有取值都是摄像头相关的），提示文字放在显示 capture miss 的现有位置（`RuntimeNotices` / App 的提示行），文字为 `No scenario frame is available (a preloaded image is missing)`，并加一条静态渲染测试。

- [ ] **Step 1：写失败的测试**
  - `switchableTelemetry.test.ts`：切换前后的 reset / pause / resume / read 分别落到对应的源。
  - `scenarioPreload.test.ts`：顺序、进度回调次数、一帧失败时整体 reject 且消息含文件名。
  - `client.test.ts` 增加：本模式下 `create` 的请求体 `operation_mode == "CONSTRUCTED_SCENARIO_RUNTIME"`；Live 下请求体与现在逐字节相同。
  - 在 `liveLoop.test.ts` 用假 API 驱动循环：
    - `test_switching_mode_creates_a_session_of_the_new_mode`：先 Live 开始、暂停，再把 config 切到本模式开始，第二次 `create` 的模式是新模式。
    - `test_a_stopped_loop_freezes_playback_and_retry_continues_it`：用 `createScenarioPlayback` 作遥测源；让 infer 连续失败直到停止，推进假时钟 10 s，点 Retry；冻结的请求逐字节相同，之后的第一个新请求的段号、帧号与停止时相同。

- [ ] **Step 2–4：失败 → 实现 → 通过。** 全部前端门禁通过。

- [ ] **Step 5：变异**：`create` 写死 Live → client 测试与模式切换测试变红；可切换源缓存第一次的源 → 切换测试变红。

- [ ] **Step 6：提交** `feat(frontend): scenario API, preload and switchable telemetry source; sessions are created in the selected mode`

---

### Task 7：界面

**Files:**
- Modify: `frontend/src/utils/dataMode.ts`、`frontend/src/utils/dataMode.test.ts`
- Create: `frontend/src/components/ScenarioPlayer.tsx`
- Create: `frontend/src/views/scenarioPlayerModel.ts`（+ 测试）
- Create: `frontend/src/components/scenarioPlayerRender.test.ts`
- Modify: `frontend/src/App.tsx`、`frontend/src/views/LiveMonitor.tsx`、`frontend/src/views/SignalInspector.tsx`、`frontend/src/styles.css`
- Modify: `README.md`（第 42 行附近）与 `prototype-tests/README.md`（第 68 行附近）：Live 选项改名后的文字；`prototype-tests/live_e2e.md` 中提到该选项的地方一并核对

**Interfaces:**
- `DATA_MODE_OPTIONS` 只剩两项（Global Constraints 中的文字）；`DATA_MODE_NOTE` 新模式的值为 `""`，App 只在非空时渲染 `<p>`。旧模式的选项不再列出（代码与测试保留）。
- `buildScenarioPlayerModel(manifest, snapshot, latest: RiskUpdate | undefined)` → `{ badge, caption, truth: string, model: string | null, segments: { title: string; state: "done" | "current" | "todo" }[], elapsed: string, finished: boolean }`：
  - `caption` 例如 `Segment 2/7 · Vision only · texting_right · driver p026 · State Farm test split`；
  - `model` 取 `latest.visual_top_classes` 中概率最高的一项，格式 `texting_right 0.97`（两位小数，half-up），没有记录时为 null；
  - `elapsed` 格式 `0:34 / 2:16`。
- App：
  - `const isLiveLikeMode = isLiveLike(config.operationMode)`，`const isScenario = config.operationMode === "CONSTRUCTED_SCENARIO_RUNTIME"`。原来的 `isLive` 分支改用 `isLiveLikeMode`，只有摄像头相关部分仍然只限 Live。
  - 本模式：显示剧本下拉框（`aria-label="Scenario"`）与加载进度；`status !== "ready"` 时 Start Monitoring 不可点，并显示 `invalid` 的原因或生成命令 `python3 scripts/build_dataset_replay.py viva_v1`；`start()` 不碰摄像头；把 `scenarioCapture(playback)` 与 `() => playback.telemetry` 传给 `useLiveSession`（Live 模式仍传 `camera.captureFrame`，不传第三个参数）。
  - 顶栏在本模式显示 `CONSTRUCTED SCENARIO`。
  - **不能破坏的既有行为**（ST-SESSION-01 等浏览器测试依赖）：Live 模式下已保存会话下拉框的 `aria-label="Saved live sessions"` 不变；「选中窗口默认跟随最新，除非用户钉住某个窗口」（`frontend/src/utils/selection.ts`）不变；每次打开页面从 Live 开始。
  - `snapshot.finished` 时调用 `live.pause()`，并显示 `Scenario finished (136 s, 7 segments)`（数字取自 manifest）。
- `LiveMonitor`：本模式渲染 `ScenarioPlayer` 代替 `CameraPreview`；Vehicle Signals 标题在本模式为 `Scenario telemetry`，并显示当前遥测的真实类别。
- `SignalInspector`：所选窗口有 `provenance.replay` 时，显示 `Truth` 一组（vision_label、telemetry_label、frame_file、segment）。

- [ ] **Step 1：写失败的测试**
  - `dataMode.test.ts`：两项的值与文字字面量；新模式说明为空。
  - `scenarioPlayerModel.test.ts`：caption、truth / model、elapsed、段状态、finished 的字面量。
  - `scenarioPlayerRender.test.ts`（静态渲染）：标签文字 `CONSTRUCTED SCENARIO · not live` 一定出现；没有 Start / Stop Camera 按钮；进度条有 7 个块且当前块带 current 类名。
  - LiveMonitor 静态渲染：本模式标题为 `Scenario telemetry` 且没有 `<video>`；Live 模式与现在相同。
- [ ] **Step 2–4：失败 → 实现 → 通过。** 全部前端门禁与 build 通过。
- [ ] **Step 5：变异**：删掉播放器标签 → 渲染测试变红；本模式仍渲染说明句 → dataMode 测试变红。
- [ ] **Step 6：提交** `feat(ui): Constructed scenario replaces Prepared replay in the mode selector - player, truth vs model, progress, finished state`

> **合并点 M3**：Task 5–7 完成后合并一次。

---

### Task 8：端到端（工程检查，不写入报告结果）

**Files:**
- Modify: `backend/tests/e2e_support.py`（`start_server` 加可选参数 `extra_env: dict[str, str] | None = None`，默认行为不变）——**修改前先 SendMessage 通知 Tasks1-10**
- Create: `backend/tests/test_constructed_scenario_e2e.py`

**Interfaces:**
- 模块级 fixture：在 `tmp_path_factory` 下用 Task 3 的脚本生成 `e2e_short` 情景包；用 `start_server(..., extra_env={"DRA_SCENARIO_ROOT": <dir>})` 起一个独立的服务端。
- 跳过条件：模型文件缺失时用 `requires_models`（原因文本与 `conftest.MODELS_SKIP_REASON` 完全一致）；数据目录不可用时显式跳过，原因 `State Farm data root not available`。

- [ ] **Step 1：写测试**（浏览器真实点击）
  - `test_the_mode_is_offered_and_the_scenario_loads`：下拉框选 `Constructed scenario`，剧本下拉框列出 `e2e_short`，加载完成后 Start 可点；页面上没有说明句。
  - `test_a_full_run`：开始播放直到 `Scenario finished`。断言：
    - 标签 `CONSTRUCTED SCENARIO · not live` 可见；
    - 每条记录 `operation_mode == "CONSTRUCTED_SCENARIO_RUNTIME"`，有图像时 `provenance.vision_source == "dataset_replay"`；
    - `provenance.replay.segment_index` 依次经过 0、1、2，界面显示的 Truth 与 manifest 一致；
    - 播放结束后循环停止；
    - 五方逐窗口对账（复用 `LiveRun`、`assert_reconciled`、`assert_ui_shows_latest`）。
  - `test_a_long_pause_does_not_expire_the_evidence`：播放中暂停 4 s 再继续，继续后的第一个窗口 `modality_freshness == {"vision": "fresh", "telemetry": "fresh"}`。
  - `test_live_is_still_the_default_on_reload`：重新加载页面后，下拉框是 Live。
- [ ] **Step 2：运行通过**；全量 pytest（含浏览器测试）通过。
- [ ] **Step 3：提交** `test(e2e): constructed scenario end to end on a short scenario (engineering check)`

---

### Task 9：生成 viva_v1、内部运行报告与使用说明

**Files:**
- Create: `backend/tests/test_constructed_scenario_rehearsal.py`（标记为 `long`，默认不收集，与 ST-LONG-01 相同的做法）
- Modify: `README.md`（如何生成情景包、如何选择这个模式）、`prototype-tests/live_e2e.md`（标注本模式是演示手段）

- [ ] **Step 1：** 用 `long` 标记的测试在浏览器里把 `viva_v1` 完整跑一遍（136 s）。按段写出：帧数、「真实 vs 模型」命中率、RiskLevel 计数、AlertSeverity 的变化序列。输出到环境变量 `DRA_E2E_EVIDENCE_DIR` 指定的目录。只断言结构：7 段都出现、剧本结束后停止、无故障；不断言命中率。
- [ ] **Step 2：** 运行一次，把输出存到 `docs/evidence/<日期>/constructed-scenario-rehearsal/`，并附 README，第一行写明「内部彩排记录，不是评估结果，报告与答辩不引用」。
- [ ] **Step 3：** 文档更新。**Step 4：** 提交 `docs(demo): constructed scenario rehearsal record (internal) and how to run the demo`

> **合并点 M4**：Task 8–9 完成后合并一次。

---

### Task 10：合并回 `fyp2/live-system`（每个合并点执行一次）

- [ ] **Step 1：** 用 SendMessage 告诉 Tasks1-10 会话（`local_51808963-6280-4a75-a5a4-1354fa430268`）要合并的提交范围，**等它回复确认**之后才继续，期间不拉取。
- [ ] **Step 2：** 在本工作副本 `git merge --no-edit fyp2/live-system`（把对方的新提交合进来）。有冲突时停下，报告给用户。
- [ ] **Step 3：** 在合并后的树上运行 `DRA_REQUIRE_MODELS=1 python3 scripts/run_gates.py --out <scratch>`。全绿才继续；不绿就修，修完重跑。
- [ ] **Step 4：** 快进 `fyp2/live-system`：`git -C /Users/liu/Desktop/FYP2-Live-System merge --ff-only fyp2/constructed-scenario`。前提是那个工作树干净；不干净时停下，问 Tasks1-10。
- [ ] **Step 5：** 通知 Tasks1-10 合并完成，告知新的提交号。推送与否由用户决定。
