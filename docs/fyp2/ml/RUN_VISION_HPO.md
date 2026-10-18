# 用户终端运行视觉 probe / bounded HPO

当前交付停在 **S1**：遥测已运行，视觉仅实现和软件验证。Codex 没有下载权重或运行视觉训练。所有命令在主 ML 仓库、`fyp2/ml-training` 上执行；不要进入 Claude worktree 或 Live-System 文件夹。使用现有 `.venv`，不安装/升级包。

先接上电源，保持屏幕打开，不要合盖。`caffeinate -dims` 避免运行期间自动休眠；不能代替接电源。系统轨道做性能测量时，不同时运行 probe/search。MPS 不可用时脚本拒绝运行，不回退 CPU。

```bash
cd /Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1
git branch --show-current
```

本次使用同一个新 run_id：`p3_vision_20261018`。如果已有同名、属于其他实验的目录，先向 Codex 说明，不删除或覆盖目录。

## 现在可执行：fetch-weights，再 probe

```bash
caffeinate -dims ./.venv/bin/python -B ml/experiments/run_vision_hpo.py fetch-weights --run-id p3_vision_20261018
caffeinate -dims ./.venv/bin/python -B ml/experiments/run_vision_hpo.py probe --run-id p3_vision_20261018
```

`fetch-weights` 仅允许下载官方 ResNet18 ImageNet V1 的 `resnet18-f37072fd.pth`（约45 MB）到默认 torch 缓存，启用 hash 校验。MobileNetV3-Large ImageNet V2 必须已经缓存；缺失或损坏会停止，不会下载它。两文件完整 SHA-256 写入新 run 的 `weights_manifest.json`。既存文件与 manifest 不一致即拒绝。

probe 使用完整冻结 train=15899、val=2868，每模型 seed42、lr8e-4、wd1e-4、batch64，训练1个epoch及一次完整val。每模型硬限20分钟、合计40分钟；目前没有真实 MPS probe 耗时，不给虚构的完成时间。达到上限就停止，记录 `NOT_RUN_BUDGET`，不要换新 run_id 绕过预算。probe 不计正式 HPO，不用于选型。

两个模型都完成后，`budget_proposal.json` 分模型计算：

`(实测一轮训练时间 + 完整val时间) × 8 epochs × 8 logical trials × 1.15`

这是时间估计，不是批准的预算；早停可能缩短实际运行，初始化/重载、资源波动可能增加耗时。内存报告包含 OS peak RSS，以及同步 batch 后采样到的 MPS allocated/driver 最大值；后者可能漏掉 batch 内瞬时峰值。

完成后贴回终端的 **`WEIGHTS_READY`、`PROBE_COMPLETE`、`VISION_STATUS probe`** 行；失败时贴回最后一个错误和状态行。Codex 会读取保存产物独立核验，给出具体预算建议并停在 S2 等待批准。

## 中断、续跑与状态

用 `Ctrl+C` 停止，看到 `INTERRUPTED` 后再执行**相同命令、相同 run_id**。已完成 trial 先核验必需文件及 manifest SHA，再跳过；缺失/损坏立即停止，不自动重训。被中断的逻辑 trial 新建 attempt 从头训练，旧 attempt 和耗时保留；同一 trial 的累计时间以及模型/阶段总时间均不重置。中断后的多个 physical attempts 是本次第5节明确允许的重跑，分别留痕；不会新增网格配置或超过8个正式逻辑 trial。非中断的 implementation failure 不会自动重跑。

父进程异常退出后，下次启动先处理仍在运行的旧 worker，并记录 `INTERRUPTED`；必要时按提示等旧 worker 退出后再执行相同命令。不得手工改 ledger、删 attempt 或清空预算。

```bash
./.venv/bin/python -B ml/experiments/run_vision_hpo.py status --run-id p3_vision_20261018
```

status 不训练、不下载、不要求 MPS。

## 只有 S2 批准具体预算后才能 search

当前**不存在** `ml/configs/approved_vision_budget.json`。不要自行创建或把 proposal 改为 approved。必须先在本对话批准 `per_trial`、两个模型的 `per_model`、`total` 的具体秒数，由 Codex 写入并提交 `launch_authorized=true` 的预算文件。之后才执行：

```bash
caffeinate -dims ./.venv/bin/python -B ml/experiments/run_vision_hpo.py search --run-id p3_vision_20261018
```

search 按已提交网格顺序，每模型6组seed42；第一组计作P2，其余P3。按val macro-F1、1e-4并列规则、log-loss、复杂度、trial号选配置，再用43/44确认。冻结模型始终是选中配置的seed42产物，确认结果不重选。最多8epochs、patience2、cosine T_max8；增强和224×224无裁剪预处理保持冻结契约。所有保存 checkpoint 都是原始logits模型；不导出/部署候选包。

完成后贴回 `SEARCH_COMPLETE` 和 `VISION_STATUS search`；Codex 在 S3 核验，P4最终test/E1和P5打包另需授权。

## 结果解释边界

- MobileNetV3用ImageNet V2，ResNet18用ImageNet V1，不能把全部差异归因于架构。
- MPS固定seed不保证逐位复现；43/44只量化观察到的波动。
- test split过去已多次评估；本次仅按开工要求做过CSV字节hash，训练/选型不读取test CSV或test图像。
- 遥测是合成数据、近似线性可分；高分不证明真实世界泛化、实际安全改善或事故风险降低。
