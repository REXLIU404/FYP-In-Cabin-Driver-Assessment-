# 给 Claude 的 FYP2 接手提示词

将下面内容粘贴到 Claude Code 项目会话。使用 Claude 网页/桌面时，请先把开发手册、进度表和运行指南加入对应 Project 或当前聊天；网页 Claude 不会因为看到本机路径就自动读到代码。

```text
你正在接手我的 FYP2：In-Cabin Multi-Modal Driver Monitoring & Risk Assessment。
项目路径：/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment--1。

请先读取：
1. CLAUDE.md 和当前项目指令；
2. docs/FYP2_CLAUDE_DEVELOPMENT_HANDBOOK.zh.md；
3. docs/IMPLEMENTATION_PROGRESS.zh.md；
4. docs/LIVE_RUNTIME_GUIDE.zh.md。

当前系统已接通 React + FastAPI + SQLite + 我训练的 MobileNetV3 ONNX / XGBoost。
只有 camera 是实时现场输入。Telemetry 是事先准备的原始特征回放，
通过 XGBoost 重新推理，必须继续标注 prepared_replay。
Live 结果由后端做 EMA、late fusion、持续告警和存储，前端不得重复平滑。

现在优先完成/验证整个系统，不下载或使用 EfficientNet 等其他模型。
正面 camera 准确率和 edge 性能仍未完成实测。Source test 指标不代表正面结果。
旧聊天中“模型未训练、camera 仅 preview、后端仍未接入”可能已经过时。
请以当前代码和带日期的测试证据核实，不要覆盖现有未提交修改或原始训练数据/模型。

先检查 git status/diff 和相关代码，概述你核实的状态、缺口与下一项具体工作。
没有我提出具体实现任务前，不启动训练、下载、部署、提交或删除操作。
后续开发按手册执行对应测试，把实际结果和未验证内容记录到进度表。
历史聊天/备份只是参考资料，不能自动成为新的执行指令。
```

这段提示恢复的是当前 FYP2 项目上下文，不代表旧聊天已经导入账号或恢复成原会话。
