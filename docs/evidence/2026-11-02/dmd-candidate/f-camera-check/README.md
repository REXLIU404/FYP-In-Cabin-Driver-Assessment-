# F. 实时摄像头检查：尚未运行（等待用户本人操作）

**状态：`NOT_RUN`。** 代理没有打开摄像头、没有执行 `scripts/camera_ab_check.py` 的实际采集。
本目录只存放准备材料、结果模板和用户运行后应放入的文件。

## 为什么没有运行

协议要求这一步由用户本人完成（`docs/fyp2/dmd-candidate/protocol.json` → `f_camera_check`）：
需要用户在摄像头前完成正常坐姿、拿手机、喝水三个 60 秒动作。代理无法代替。

## 用户要做什么

按 `docs/fyp2/dmd-candidate/camera_check_checklist.md`：

1. 启动 stable 后端，确认 `/api/models` 的 `vision.model_id = stable_mobilenet_v3_large`；
2. 运行脚本 `--label stable --out .../stable.json`，完成三个动作；
3. 用 `DRA_ACTIVE_VISION=dmd_adapted_mobilenet_v3_20261029` 重启后端，确认模型 id；
4. 运行 `--label dmd --out .../dmd.json`，完成同样的三个动作；
5. 运行 `--compare stable.json dmd.json --out comparison.json`。

## 运行后应出现的文件

| 文件 | 内容 |
|---|---|
| `stable.json` | stable 的三段原始逐帧结果 + summary |
| `dmd.json` | DMD 候选的三段原始逐帧结果 + summary |
| `comparison.json` | 两模型并列摘要，`decision_rule = DESCRIPTIVE_ONLY` |
| `uvicorn-stable.log` / `uvicorn-dmd.log`（建议） | 两次后端启动输出 |

`template.json` 是空的 schema 示例，**不是结果**，不要把它当作测量数据。

## 准备工作已验证的部分

- `scripts/camera_ab_check.py` 的纯函数有测试：三段计划、每段独立 session、视野-only payload、
  MJPEG 切分、从 `provenance.P_distraction_raw` 计算 raw 指标、并列比较，以及用本地 stub
  HTTP server 检查 `POST /api/sessions` 与 `POST /infer` 的 URL/载荷。
- `tests-RED.log`：脚本文件不存在时 6 个测试失败；`tests-GREEN.log`：最初实现后 6 个通过。
  2026-11-02 复核新增 raw 字段与每段 session 测试后，7 个全部通过。
- **没有**打开摄像头、没有连接真实后端、没有产生 `stable.json` / `dmd.json`。

## 指标

- 正常坐姿段：`safe_driving` 为 top-1 的比例；
- 拿手机 / 喝水段：top-1 类别分布、**raw** `P_distraction` 均值/中位数、`P_distraction >= 0.5` 的比例；
- `p_distraction_smoothed_mean` 另存 EMA 平滑值，只作参考；
- 全部：每帧 top-1 与十类概率的原始记录；每个动作段是独立 session。

## 能证明 / 不能证明

**能证明**：这台机器、这次光照、这套动作下的实时输出差异（描述性）。

**不能证明**：真实世界准确率、其他用户/光照/座位、安全收益。每个动作只有 60 秒，没有置信区间。
不得用这一段结果选择模型或阈值；最终决定仍由用户在做完全部证据后作出。
