# 实时摄像头 A/B 检查：用户操作清单

本检查**必须由用户本人**在摄像头前完成；代理没有运行它，也不会替用户执行。
目的：在**同一套动作、同一台机器、同一段光照**下，描述 stable 与 DMD 候选的实时摄像头输出差异。
它不证明真实世界准确率，也不证明安全收益。

## 0. 准备

1. 关闭所有会占用摄像头的应用（Zoom、Teams、Photo Booth、浏览器会议页等）。
2. 第一次运行前，给终端/IDE 摄像头权限（系统设置 → 隐私与安全性 → 摄像头）。
3. 确认 `ffmpeg` 可用：
   ```bash
   ffmpeg -version
   ffmpeg -f avfoundation -list_devices true -i ""
   ```
   记下摄像头的视频设备编号（通常是 `0`）。如果编号不是 `0`，下面加 `--device <编号>`。
4. 确认后端依赖和模型都在（仓库根目录执行）：
   ```bash
   ls ml/outputs/vision/mobilenetv3_large_vision.onnx \
      ml/outputs/candidates/dmd_adapted_mobilenet_v3_20261029/model.onnx
   ```
5. 准备一个安静、光线稳定的位置；两次运行之间不要改变座位、摄像头角度、光照和穿着。

## 1. 运行 stable

终端 1（仓库根目录）：

```bash
.venv/bin/python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

另开终端 2，先确认在役模型：

```bash
curl -s http://127.0.0.1:8000/api/models
```

`vision.model_id` 应为 `stable_mobilenet_v3_large`，`vision.sha256` 应为 `b3a42e8d…`。

然后运行（脚本会提示你做三个动作）：

```bash
.venv/bin/python scripts/camera_ab_check.py \
  --label stable --base-url http://127.0.0.1:8000 \
  --out docs/evidence/2026-11-02/dmd-candidate/f-camera-check/stable.json
```

三个 60 秒动作（每个动作开始前按 Enter）：

1. **正常坐姿**：双手放在方向盘/桌面，目视前方，不拿手机、不喝水。
2. **拿手机**：拿起手机并低头看屏幕，保持这个动作；不要遮挡整张脸。
3. **喝水**：拿起杯子/水瓶做出喝水动作，保持这个动作。

脚本会为**每个动作新建一个 session**（记录在结果的 `session_ids`）；动作之间的 EMA 和融合状态
不会延续，因此每段都从该段第一帧开始统计，不采用“丢弃开头过渡窗口”的做法。每个动作仍要尽量
连续，不要在 60 秒内切换动作。结束后终端会打印每段的 `safe_driving` top-1 比例、
**raw P_distraction** 中位数和 `>=0.5` 比例。

## 2. 运行 DMD 候选

停掉终端 1 的 uvicorn（Ctrl-C），用候选模型重新启动：

```bash
DRA_ACTIVE_VISION=dmd_adapted_mobilenet_v3_20261029 \
  .venv/bin/python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

再次核对：

```bash
curl -s http://127.0.0.1:8000/api/models
```

`vision.model_id` 应为 `dmd_adapted_mobilenet_v3_20261029`，`vision.sha256` 应为 `01f1d6a3…`。
如果不一致，脚本会拒绝运行，不会把两次结果标错模型。

重复同一套三个动作：

```bash
.venv/bin/python scripts/camera_ab_check.py \
  --label dmd --base-url http://127.0.0.1:8000 \
  --out docs/evidence/2026-11-02/dmd-candidate/f-camera-check/dmd.json
```

## 3. 生成并列对比

```bash
.venv/bin/python scripts/camera_ab_check.py \
  --compare docs/evidence/2026-11-02/dmd-candidate/f-camera-check/stable.json \
            docs/evidence/2026-11-02/dmd-candidate/f-camera-check/dmd.json \
  --out docs/evidence/2026-11-02/dmd-candidate/f-camera-check/comparison.json
```

## 4. 导出什么

请把以下文件交给代理/放进证据目录：

| 文件 | 内容 |
|---|---|
| `f-camera-check/stable.json` | stable 的三段原始逐帧结果 + 每段 summary |
| `f-camera-check/dmd.json` | DMD 候选的三段原始逐帧结果 + 每段 summary |
| `f-camera-check/comparison.json` | 两模型的并列摘要（脚本生成） |
| uvicorn 日志（可选） | 两次启动的终端输出；如果出现 503/500，请保留 |

脚本每完成一段就写一次文件；中断也会保留 partial 结果，`status` 会标为 `PARTIAL`/`INTERRUPTED`。

## 5. 指标怎么算（脚本已自动计算）

对一段的 N 个成功窗口（HTTP 201）：

- `safe_driving_top1_rate = count(top-1 == safe_driving) / N`（主要看正常坐姿段）；
- `p_distraction_mean = mean(provenance.P_distraction_raw)`，
  `p_distraction_median = median(provenance.P_distraction_raw)`；
- `p_distraction_ge_0_5_rate = count(provenance.P_distraction_raw >= 0.5) / N`；
- `p_distraction_smoothed_mean`：顶层 `P_distraction` 的均值（经过 EMA α=0.35 并保留 3 位小数），
  只作参考，不用于上面三项；
- `p_distraction_basis`：固定为 `provenance.P_distraction_raw`，说明指标来自模型原始输出；
- `top1_counts`：该段 top-1 类别计数。

比较时只看同一段、同一动作的并列数字。**不设胜者**，不根据这三个 60 秒片段挑模型或阈值。

## 6. 能证明 / 不能证明

**能证明**：在这台机器、这次光照、这套动作下，两个模型对实时摄像头的描述性输出。

**不能证明**：总体准确率、其他用户/光照/座位、真实风险或安全收益；60 秒/动作没有置信区间。

## 7. 常见问题

| 现象 | 处理 |
|---|---|
| `backend unreachable` | 后端没启动、端口不对，或 `--base-url` 写错 |
| `camera produced 0 frames` | 摄像头被占用/无权限；先跑 `ffmpeg -f avfoundation -list_devices true -i ""` 检查设备号 |
| `backend loaded 'stable...' expected 'dmd...'` | 用错 `DRA_ACTIVE_VISION`；重启后端并核对 `/api/models` |
| 403/404 on `/api/models` | 后端工作目录不是仓库根目录（需要能读到 `ml/outputs`） |
| 画面全黑/过曝 | 调整光照后重跑；不要只截取一部分 |
