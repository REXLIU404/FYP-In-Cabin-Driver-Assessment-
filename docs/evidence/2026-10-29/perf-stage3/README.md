# Task 10A Stage 3：运行时延迟与日志完整性（2026-10-29）

- **代码**：`fe5c41d`（perf01/perf02 加 `--active-vision`；服务启动后读 `/api/models`，核对加载的视觉模型与要求的一致，不一致就中止；perf02 在重启后再核对一次）。
- **命令**：`DRA_REQUIRE_MODELS=1 .venv/bin/python scripts/perf01.py --active-vision <stable|resnet18_search004_seed42> --out docs/evidence/2026-10-29/perf-stage3/<run>`，perf02 同理。服务在随机空闲端口，用临时 SQLite；没有碰 8000 端口与 `driver_risk.db*`。
- **模型身份**：stable = `stable_mobilenet_v3_large`，sha256 `b3a42e8d…`；RN = `resnet18_search004_seed42`，sha256 `5e226722…`，source `candidate:p5_resnet18_search004_seed42_20261023`。每个 JSON 里都有 `active_vision` 与 `vision_model(s)`。
- **服务器日志**：每次运行的 uvicorn 日志都归档在 `<run>/server-perf0N/`。服务以 `log_level="warning"` 运行（`backend/tests/e2e_server_main.py:35`），**全部 0 字节**，即没有 warning 或 error。perf02 的 `fault_events.log` 各有 1 行，是阶段 4 故意注入的 422。

## 1. 延迟（perf01，capture→render，每次 600 个窗口，预热 20 个）

单位 ms。三轮按 stable → RN 交替，同一时间只有一个运行。

| 运行 | 模型 | 中位数 | p95 | 最大 | 服务器 total 中位数 / p95 | 服务器 vision 中位数 / p95 | 速率 Hz | 结束 UTC |
|---|---|---|---|---|---|---|---|---|
| `stable` | stable_mobilenet_v3_large | 41 | 92 | 433 | 23.72 / 48.25 | 12.41 / 23.94 | 9.43 | 09:19:12 |
| `rn` | resnet18_search004_seed42 | 61 | 123 | 408 | 46.705 / 88.89 | 37.17 / 71.59 | 9.15 | 09:21:23 |
| `stable-r2` | stable_mobilenet_v3_large | 27 | 56 | 225 | 16.745 / 29.6 | 9.02 / 15.13 | 9.75 | 09:30:32 |
| `rn-r2` | resnet18_search004_seed42 | 50 | 75 | 221 | 38.375 / 56.69 | 30.835 / 45.31 | 9.71 | 09:31:49 |
| `stable-r3` | stable_mobilenet_v3_large | 28 | 46 | 187 | 16.565 / 24.89 | 8.9 / 13.44 | 9.67 | 09:33:08 |
| `rn-r3` | resnet18_search004_seed42 | 50 | 77 | 254 | 38.4 / 55.63 | 31.1 / 45.15 | 9.75 | 09:34:25 |

- **RN 的 capture→render p95 是实测值**（三轮分别 123、75、77 ms），不是从模型单独推理的 25.4 ms 推算出来的。
- 所有运行都满足 p95 < 1 s 的开发原型目标（`target_1s.met = true`），控制台无报错。
- **机器负载**：本日 8 核机器的 load average 在 10 到 56 之间，主要来自 iCloud 同步与桌面应用，见 `load_log.txt`（第 2、3 轮；第 1 轮开始前约 31）。所以绝对数字比 10-22 的安静基线高：10-22 的 stable 是中位数 28、p95 39，见 `docs/evidence/2026-10-22/perf/perf01.json`。p95 受负载影响最大。比较 MN 和 RN 时，看同一轮的中位数更可靠：每一轮 RN 都比 stable 高约 20–23 ms，服务器 vision 阶段也高约 22–25 ms。这与 p4b 纯模型推理的差值一致：RN-HPO42 中位数 25.12 / p95 25.42 ms，MN-HPO42 中位数 6.95 / p95 7.25 ms，按 `ml/outputs/runs/p4b_20261022/runtime_benchmark/*_round*.json` 的 600 个样本计算，范围是 `CPU_ORT_SESSION_RUN_ONLY_NOT_CAPTURE_TO_RENDER`。注意 MN-HPO42 是 MN 候选，不是 stable。
- **作废的运行**：第一次的第 2/3 轮因为后台任务重复启动，两套 perf01 并发运行、互相干扰，结果已删除，没有用于任何结论。现在的 `*-r2`、`*-r3` 是之后的干净重跑。

## 2. 日志完整性（perf02，D1/D2）

| 运行 | 模型 | D1 | D2 | 入库窗口 | 故障 | 重复 request_id | 各阶段结束时的窗口数 |
|---|---|---|---|---|---|---|---|
| `stable` | stable_mobilenet_v3_large（重启前后一致：True） | 210/210 | 210/210 | 209 | {'input_validation': 1} | 0 | {'1_normal': 100, '2_transport_burst': 150, '3_backend_restart': 200} |
| `rn` | resnet18_search004_seed42（重启前后一致：True） | 210/210 | 210/210 | 209 | {'input_validation': 1} | 0 | {'1_normal': 100, '2_transport_burst': 150, '3_backend_restart': 201} |

- 与 10-22 基线形状相同：D1/D2 完整性 1.0，1 个 `input_validation` 故障，0 重复。
- 分母是 210，而基线是 211。perf02 每个阶段的结束条件是「≥ N 个窗口」（`scripts/perf02.py:68-89`），之后还有阶段 4 的 422。脚本没有固定逻辑请求的总数，它随阶段结束的时机与阶段之间的时序变化（这是从脚本结构推断的，没有逐条追踪是哪一个请求造成了差别），所以分母不是固定目标。审计看的是完整性比例、故障数与重复数，而不是 211 这个数字。
