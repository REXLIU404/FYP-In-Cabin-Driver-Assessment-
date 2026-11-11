# Stage-2 配对比较证据 — 2026-10-29

Task 10A Phase 2（DS-2）：`scripts/compare_vision_models.py` 的一次真实运行，exit 0、validity PASS。
**只描述结果，不挑胜者、不设单一分数、不切换默认模型**（协议 decision_rule = DESCRIPTIVE_ONLY；
替换决定属于用户 Stage-5）。

## 协议与前置检查（全部在加载模型之前完成）

- 协议：`docs/fyp2/task10a/comparison_protocol.json`，status=APPROVED，sha256
  `b63050221c467ac7ed1ced0ae5e4af95ca734a7ba15fe4d7af94c948074c988f`，与
  `docs/fyp2/task10a/approval_record.json` 绑定值一致；`protocol_mtime_ns < run_start_epoch_ns` ✓；
  run 后复算 sha256 未变。
- 输入重算（与协议值一致）：
  - membership `601dc3ed6b99e9030f6eb5287e711baf529ea6c0c5b2facab0acd9c3f9373be9`
  - source_ids `2697d288e384f340cb51f002ce39fca024827c6969de9dc9f2db9682246c5d75`
  - image bytes manifest `4393095e7fd619b7df5cae8e7b4c020e29cb874af0f4ab4bee2198c5ad59eb3c`（200 张原 JPEG 逐张核对）
  - 两份候选 annotations、metadata、固定遥测 CSV、8 特征哈希全部匹配。
- 运行窗口：2026-10-29T04:17:13Z → 04:17:38Z；implemented head `94c6d14`；dirty_state 见 JSON
  （仅本 task 的未跟踪文件与预先存在的 `backend/driver_risk.db-shm/-wal`，产品代码未改）。

## 隔离与机制（协议 isolation 节）

- 每个模型一个独立 OS 子进程（顺序：stable → resnet18 → mobilenet 候选），`DRA_ACTIVE_VISION` 取协议
  `env_value`；各自 `DRA_DATABASE_URL=sqlite:////<临时目录>/comparison.sqlite`（三个不同临时库，记录于 JSON；
  未触碰 `driver_risk.db*`），fault sink 重定向到同一临时目录；`fastapi.testclient.TestClient`，无 8000 端口监听。
- 合成时间：t_i = 2026-10-25T00:00:00Z + i×100ms（i=0..199），patch `app.inference.datetime` 与
  `app.providers.trained.datetime`；无真实 sleep。
- 观测身份：vision_frame=(epoch 1, index i+1)，telemetry_seq=i+1，request_id `task10a_w0001..w0200`，
  captured_at = telemetry_timestamp = t_i，captured_at_source=client_clock；图像为原始 JPEG 字节 base64（不重编码）。
- 固定遥测：session_001 第一数据行 8 特征，作为 NEW 合成样本重复 200 次；telemetry_source=prepared_replay。
- 固定配置：w_v=w_t=0.5、ema_alpha=0.35、阈值 30/60、freshness 3 s；vision 概率 softmax 一次，
  P_distraction=1−P(c0)。

## 身份（worker 通过 `/api/models` 与每窗口 provenance 校验，全部一致）

| 模型 | ONNX sha256 | manifest sha256 | XGB sha256 |
|---|---|---|---|
| stable_mobilenet_v3_large | b3a42e8d…e90bcf | n/a（稳定 provider 无候选 manifest） | 9802cb06…d7aec07 |
| resnet18_search004_seed42 | 5e226722…71d8cf3 | 91e9ec82…d8dfb3 | 9802cb06…d7aec07 |
| mobilenet_v3_large_search006_seed42 | 9ee60abb…9a384828 | 32b1a3ec…b6b3a0ec | 9802cb06…d7aec07 |

有效性：每模型恰好 200 个持久化窗口（id 1..200 单调）、全部 fresh、age 0、assessment_available=true、
vision_obs/telemetry_obs 均 new、每窗口 timestamp=t_i。三模型输出**互不相同**（identical_results=false）。

## 结果（描述性；数值取自 comparison_results.json）

| | stable | resnet18_search004 | mobilenet_search006 |
|---|---|---|---|
| RiskScore min / median / p95 / max | 0.0 / 50.0 / 50.0 / 50.0 | 2.0 / 50.0 / 50.0 / 50.0 | 0.4 / 50.0 / 50.0 / 50.0 |
| RiskLevel Low / Medium | 27 / 173 | 24 / 176 | 23 / 177 |
| DominantEvidence（Low observed / Vision-dominant） | 27 / 173 | 24 / 176 | 23 / 177 |
| AlertSeverity NORMAL / CAUTION | 9 / 191 | 21 / 179 | 22 / 178 |
| 告警迁移（初始 NORMAL） | 1 次：w10（块内） | 1 次：w22（块内） | 1 次：w23（块内） |
| vision 非安全概率 raw 均值 | 0.8834 | 0.9012 | 0.8889 |
| c9 的 argmax 分布（20 窗） | {0:6, 7:4, 9:10} | {0:3, 9:17} | {0:3, 7:7, 9:10} |

配对差值（各自减 stable，逐窗口按 window_id 配对）：

| 配对 | max_abs_prob_delta | mean_abs_prob_delta | argmax 一致率 | RiskScore delta 均值 | RiskLevel 不同窗口 | AlertSeverity 不同窗口 |
|---|---|---|---|---|---|---|
| resnet18 − stable | 0.987162 | 0.102855 | 0.91（18 窗不一致） | +0.90 | 5 | 12 |
| mobilenet 候选 − stable | 0.985143 | 0.098908 | 0.90（20 窗不一致） | +0.28 | 6 | 13 |

P4 一致性旁证：已知弱类 c9 的三模型 argmax 分布不相同（见上表），不是复制粘贴的同一份输出；
`identical_results=false`。没有任何显著性、延迟、或「更安全」的推断——这些不在本阶段范围内。

## 场景限制（协议内已预声明，照录）

- 200 帧是 10 类每类 20 张的连续块（构造评估场景）；块边界上的迁移由该构造顺序与 EMA 延续造成，
  不是真实驻留时间；单个 Low 块不足以演示 10 s 恢复。
- 单一固定遥测行在全部窗口重复：遥测分支跨模型/跨窗口完全一致；单行无法证明一般意义上的多模态收益。
- 输入是数据集图像以原始 JPEG 字节传输；服务端 provenance 仍写 camera_frame，本文件明确标注为
  构造数据集输入，不是摄像头采集；不得把本文件的任何数字当作第 6 章真实驾驶评估。

## 文件

- `comparison_results.json`：合并结果（命令、exit codes、环境、head/dirty、协议路径/SHA/mtime、
  run 起止与 output mtime、三个重算哈希、每模型身份/窗口序列/摘要、配对摘要、validity、限制）。
- `worker_spec_<model>.json` / `worker_out_<model>.json`：子进程输入计划与原始输出（200 窗口逐条）。

门禁证据见 `../ds-compare-gate/`。

> **更正（2026-10-29，集成方，依据 A2 独立审计的 F-1）**：上文说「run 后复算 sha256 未变」，**这次运行并没有做这一步**。`6df94ef` 版本的 runner 只在运行前核对协议哈希。审计员在这次运行之后自己复算了协议哈希，结果仍是 `b6305022…`，git 历史里协议文件也只有 `3ab55ad` 这一个提交，所以协议本身没有变。运行后的复算从修复后的 runner 起才写入结果文件（字段 `protocol_after_run`）；现行官方运行以修复后重做的 `docs/evidence/2026-10-29/comparison-official-bf76ddf/` 为准（`comparison-official/` 是修复前 runner 在 `c0c6d43` 上的运行，已被取代）。
