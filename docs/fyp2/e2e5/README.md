# E2 and E5 (light): pre-declared protocol

`protocol.json` is the binding, machine-readable declaration. This file states it in short.
Both are committed **before** any E2 or E5 result exists. The runners refuse to start unless
`protocol.json` is committed and unmodified, and they record its sha256 and commit.

## What is measured

- **E2** asks how the late fusion behaves on normal inputs, and how sensitive it is to the
  five fusion weights of report Table 9.
  - 6 strata: vision {safe, distracted} x telemetry {Safe, Aggressive, Distracted}.
  - 10 constructed pairs per stratum, 60 pairs in all; no image and no telemetry row is used
    twice.
  - Each pair runs once per weight setting: 300 single-window runs through the real `/infer`.
- **E5 (light)** asks what each branch adds to the fused result. The `viva_compact`
  scenario runs three times through the real `/infer`, with EMA and the AlertSeverity FSM:
  - as declared;
  - with vision held safe, so only telemetry varies;
  - with telemetry held Safe, so only vision varies.

## Operational reference policy (declared in advance, from source labels only)

| Source labels | Reference | Levels that agree |
|---|---|---|
| neither branch non-safe | REF_LOW | Low |
| exactly one branch non-safe | REF_ELEVATED | Medium or High |
| both branches non-safe | REF_HIGH | High |

The policy reads dataset labels only, never a model output or the fusion formula.
Agreeing with it means agreeing with this declared policy. It is not accuracy against
ground-truth severity.

## Rules

- Descriptive only. No weight is chosen as "best".
- No claim of real-world risk-prediction accuracy.
- Every pair is a **constructed evaluation scenario**, not real multimodal data (D06).
- Disagreements between a branch model and its source label are reported separately, so that
  a model error is not read as a fusion effect.
- The high-vision attenuation counter-examples stay in the results.
