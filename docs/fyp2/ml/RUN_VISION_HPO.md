# 用户终端运行视觉 probe / bounded HPO

当前 **S2 已批准**：遥测已运行，两个视觉模型的真实MPS probe已完成并核验；用户已明确批准正式视觉预算。监督器修复、测试、预算文件分别提交（见规范进度报告），search由用户终端运行。所有命令在主 ML 仓库、`fyp2/ml-training` 上执行；不要进入 Claude worktree 或 Live-System 文件夹。使用现有 `.venv`，不安装/升级包。

先接上电源，保持屏幕打开，不要合盖。`caffeinate -dims` 避免运行期间自动休眠；不能代替接电源。系统轨道做性能测量时，不同时运行 probe/search。MPS 不可用时脚本拒绝运行，不回退 CPU。

```bash
cd /Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1
git branch --show-current
```

继续使用同一个 run_id：`p3_vision_20261018`。不删除旧 attempt、不换 run_id 绕过累计预算。只在一个终端窗口运行同一 run；新启动器持有 `.run.lock`，第二个启动器会报告 `ALREADY_RUNNING` 并退出，不停止第一个 worker。不要删除 lock 文件；进程退出后操作系统自动释放锁。

## 当前 run：运行正式 search

```bash
caffeinate -dims ./.venv/bin/python -B ml/experiments/run_vision_hpo.py search --run-id p3_vision_20261018
```

两份缓存的完整 SHA-256 已与原 `weights_manifest.json` 核对，不必再次 fetch。原 `fetch-weights` 仅允许下载官方 ResNet18 ImageNet V1 的 `resnet18-f37072fd.pth`（约45 MB），MobileNetV3-Large ImageNet V2 必须已经缓存；此处不新增下载授权。既存文件与 manifest 不一致即拒绝。

已完成的probe使用完整冻结 train=15899、val=2868，每模型 seed42、lr8e-4、wd1e-4、batch64、1epoch及完整val。MobileNet train+val206.259663833 s、ResNet187.059520584 s；累计482.473836584 s包含原保留的78.098847875 s。旧中断与成功attempt均保留，**不要重新执行probe**；probe不计正式HPO、不用于选型。实际执行的旧监督器源码已按原SHA精确存入该run的`source_snapshot/`，不把本次新监督器冒充旧probe源码。

两个模型都完成后，`budget_proposal.json` 分模型计算：

`(实测一轮训练时间 + 完整val时间) × 8 epochs × 8 logical trials × 1.15`

这是时间估计，不是批准的预算；早停可能缩短实际运行，初始化/重载、资源波动可能增加耗时。内存报告包含 OS peak RSS，以及同步 batch 后采样到的 MPS allocated/driver 最大值；后者可能漏掉 batch 内瞬时峰值。

probe已有`PROBE_COMPLETE`与`VISION_STATUS probe COMPLETED`证据，S2的具体数字已获批，当前进入用户运行search步骤。

## 中断、续跑与状态

用 `Ctrl+C` 停止，看到 `INTERRUPTED` 后再执行**相同命令、相同 run_id**。已完成 trial 先核验必需文件及 manifest SHA，再跳过；缺失/损坏立即停止，不自动重训。被中断的逻辑 trial 新建 attempt 从头训练，旧 attempt 和耗时保留；同一 trial 的累计时间以及模型/阶段总时间均不重置。中断后的多个 physical attempts 是本次第5节明确允许的重跑，分别留痕；不会新增网格配置或超过8个正式逻辑 trial。非中断的 implementation failure 不会自动重跑。

父进程异常退出后，下次启动核查旧 worker 的父进程；父控制器仍在运行时报告 `ALREADY_RUNNING`，不会停止它。只有确认原控制器不再运行的孤儿 worker 才按原恢复规则处理；必要时按提示等旧 worker 退出后再执行相同命令。SIGINT/SIGTERM记为`INTERRUPTED`，普通实现错误仍为`IMPLEMENTATION_FAILED`；预算终态重复启动不增加空转账单、不重置预算。新预算隔离规则见下文。

本次旧版本把 worker 的 `-15` 误记为 `IMPLEMENTATION_FAILED`。专用的**非训练**恢复命令如下（本次修复已执行，勿重复执行）：

```bash
./.venv/bin/python -B ml/experiments/run_vision_hpo.py recover-interrupted --run-id p3_vision_20261018
```

该入口仅接受旧 probe 的 SIGTERM 证据：核查原提交源码/hash，要求除控制器外的环境、数据、预训练、trainer、protocol/预算均未变化且尚有剩余预算、无存活 worker；普通错误、耗尽预算或其他配置漂移均拒绝。`recovery_001/` 保存原 state/config、原控制器源码与 hash manifest；原 attempt/config/log 不变，已耗时不变，只把可验证的中断改为 `INTERRUPTED` 并指向新控制器 context。恢复本身不创建新训练 attempt。不得手工改 ledger、删 attempt 或清空预算。

```bash
./.venv/bin/python -B ml/experiments/run_vision_hpo.py status --run-id p3_vision_20261018
```

status 不训练、不下载、不要求 MPS。

## 已批准的 S2 预算与 clean commit 门禁

`ml/configs/approved_vision_budget.json`已按用户批准写入并独立提交：`per_trial=2400 s`、MobileNet `17100 s`、ResNet `15300 s`、`total=32400 s`。不扩额；grid、batch64、MPS、CPU两线程、workers0保持不变。估计约8小时02分、阶段硬限9小时，早停可缩短；这不是完成全部trial的保证。

启动前必须无暂存或tracked修改，执行源码、protocol和预算逐字节等于`HEAD`。只允许用户要求保留的`09_INDEPENDENT_AUDIT_REVIEW.md`未跟踪报告，以及当前run自己的未跟踪输出；其他dirty拒绝。原始Git状态仍如实保存，`tracked_worktree_clean=true`与`execution_commit`明确表明执行来自已提交源码，不伪造完全空的`git status`。首次search context单独记录最终提交，不改写probe旧context。

```bash
caffeinate -dims ./.venv/bin/python -B ml/experiments/run_vision_hpo.py search --run-id p3_vision_20261018
```

search按已提交网格顺序，每模型6组seed42；第一组计作P2，其余P3。按val macro-F1、1e-4并列规则、log-loss、复杂度、trial号选配置，再用43/44确认。冻结模型始终是选中配置的seed42产物，确认结果不重选。最多8epochs、patience2、cosine T_max8；增强和224×224无裁剪预处理保持冻结契约。所有保存checkpoint都是原始logits模型；不导出/部署候选包。

`per_trial`或`per_model`触顶：当前attempt保留`TIME_BUDGET_EXCEEDED`，该模型剩余trial记`NOT_RUN_BUDGET`，继续下一个模型；已完成的trial不作废。`total`触顶才停止全部。模型预算不完整时最终状态为`PARTIAL`，总预算耗尽为`NOT_RUN_BUDGET`；二者都不算完整搜索通过。模型封停状态、原截断原因和累计耗时保留，若另一模型被Ctrl+C中断，同命令续跑只续仍允许的模型。

超时trial即使留下checkpoint或高分metrics也不进入选型。部分结果仍写`selection_log.json`及`search_state.json`中的`excluded_trials`：列出model/trial/role/seed、截断scope、attempt、实际timeout或未启动。无完成search的模型写`NOT_SELECTED`；有完成search但确认不足则列missing seeds，不冒称三seed完成。

完成后贴回`SEARCH_COMPLETE`或`SEARCH_PARTIAL`、`BUDGET_EXCLUDED_TRIALS`和`VISION_STATUS search`；Codex在S3核验并将被截断trial列入规范报告。P4最终test/E1和P5打包另需授权。

## 结果解释边界

- MobileNetV3用ImageNet V2，ResNet18用ImageNet V1，不能把全部差异归因于架构。
- MPS固定seed不保证逐位复现；43/44只量化观察到的波动。
- test split过去已多次评估；本次仅按开工要求做过CSV字节hash，训练/选型不读取test CSV或test图像。
- 遥测是合成数据、近似线性可分；高分不证明真实世界泛化、实际安全改善或事故风险降低。
