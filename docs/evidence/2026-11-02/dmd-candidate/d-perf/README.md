# D. 性能：stable 与 DMD 候选各 3 轮（perf01，2026-11-02）

**问题**：在同一台机器、同一套前端循环下，DMD 候选的端到端与服务端视觉耗时与 stable 相差多少？

**性质**：描述性测量。不是目标硬件基准，不选模型。

## 命令

六轮交替执行（每轮 600 个测量窗口，预热 20 个）：

```bash
for round in 1 2 3; do
  for model in stable dmd; do
    # stable -> --active-vision stable; dmd -> --active-vision dmd_adapted_mobilenet_v3_20261029
    .venv/bin/python scripts/perf01.py --windows 600 --warmup 20 \
      --active-vision <model> --out docs/evidence/2026-11-02/dmd-candidate/d-perf/<model>-r${round}
  done
done
```

原始命令、时间、负载与退出码在 `runs.log`；独立复算在 `recompute.log` / `recompute.json`。

## 结果

| 轮次 | 模型 | capture→render p50 / p95 / max (ms) | Server total p50 / p95 (ms) | Server vision p50 / p95 (ms) | 速率 |
|---|---|---|---|---|---|
| stable-r1 | stable | 27 / 45 / 127 | 16.42 / 23.53 | 8.645 / 12.56 | 9.84 Hz |
| dmd-r1 | DMD | 27 / 30 / 186 | 17.26 / 18.84 | 9.23 / 9.99 | 9.83 Hz |
| stable-r2 | stable | 27 / 36 / 136 | 16.57 / 20.37 | 8.88 / 10.87 | 9.82 Hz |
| dmd-r2 | DMD | 28 / 36 / 104 | 17.44 / 20.42 | 9.345 / 10.83 | 9.83 Hz |
| stable-r3 | stable | 28 / 35 / 149 | 17.62 / 20.10 | 9.41 / 11.00 | 9.83 Hz |
| dmd-r3 | DMD | 28 / 39 / 124 | 17.23 / 21.60 | 9.095 / 11.85 | 9.83 Hz |

六轮全部：

- `windows_measured = 600`，`short_run = false`，`console_errors = []`，`attempts_other_than_1 = 0`；
- `target_1s`（capture→render p95 ≤ 1000 ms）全部 `met = true`，余量很大；
- 每轮 `perf01_timings.json` 的 sha256 与 `perf01.json.raw_timings.sha256` 一致，
  独立复算的 p50/p95/max 与摘要逐项相等（6/6，见 `recompute.log`）。

### 读数注意

- 运行期间 `load average` 约 3.9–5.1（8 核），高于 2026-10-30 stage3-raw 的 2.3–4.1。
  因此这些**绝对毫秒数不要与 stage3 的 31 ms 直接比较**；本轮 stable 与 DMD 交替运行，
  比较应在同一天的这六轮内部进行。
- 两模型的 capture→render p95 在 30–45 ms 之间交替，没有稳定的方向性差异；
  Server vision 中位数 stable 8.645–9.41 ms，DMD 9.095–9.345 ms，差距在轮间波动范围内。
- 范围：一台开发机（Apple M2）、Chromium 假摄像头、冻结模型；不是目标硬件或真实摄像头。
- 这些数字不能证明真实摄像头/真实浏览器负载下的延迟，也不能单独作为切换模型的理由。

## 文件

| 文件 | 内容 |
|---|---|
| `stable-r1..r3/`、`dmd-r1..r3/` | 每轮 `perf01.json` + `perf01_timings.json`（600 行原始计时） |
| `runs.log` | 命令顺序、load before/after、PERF-01 摘要与 exit code |
| `recompute.log` / `recompute.json` | `scripts/dmd_candidate_perf_archive.py` 的独立复算 |
| `tests-RED.log` / `tests-GREEN.log` | 先失败、后通过的归档校验测试 |
