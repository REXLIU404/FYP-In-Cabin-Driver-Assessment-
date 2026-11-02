# Task 10A：预检、容差与 Stage-2 协议（来自 Codex CX-0）

| 文件 | 内容 | 状态 |
|---|---|---|
| `preflight_report.md` | Phase 0 依赖预检：两份 manifest 用系统 CLI 校验通过、200 张 stable200 图片可读、成员哈希 `601dc3ed…`、provider 相对 `2745348` 无改动，附当日命令输出 | **GO**（只针对依赖，不代表 Stage-1 验收） |
| `tolerance_predeclaration.md` | Stage-1 三个模型的参照与容差：每个有参照的集合要求 `max_abs_prob_delta ≤ 1e-4` 且 argmax 一致率 = 1.0；另外单独评估 `per_class_mode_equals_label` | 用户批准（FUD-01），已生效 |
| `tolerance_predeclaration.preapproval_20261026.md` | 批准前的版本，保留作对照 | 历史 |
| `comparison_protocol.json` | Stage-2 对比协议，从 Codex 的 `comparison_protocol.approved.json` 原样发布，sha256 `b63050221c467ac7ed1ced0ae5e4af95ca734a7ba15fe4d7af94c948074c988f` | 用户批准（FUD-02–05）；**runner 要等用户的 Stage-1 审计通过后才能运行** |
| `comparison_protocol.draft.json` | 交给用户审阅时的草案，与批准版在方法上一字不差 | 历史 |
| `approval_record.json` | 用户批准的记录：2026-10-26，用户在 Codex 会话里回复「都批准」，FUD-01–06 全部批准 | — |

上游计划：`docs/plans/2026-10-25-task-10a-candidate-integration.md`。改正与分工：`docs/plans/2026-10-26-task-10a-analysis-and-collaboration.zh.md`。
