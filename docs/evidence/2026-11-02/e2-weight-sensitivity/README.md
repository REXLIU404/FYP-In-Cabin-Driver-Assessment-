# E2: normal-input fusion behaviour and weight sensitivity (2026-11-02)

Status: **PASS** (validity).

- The result is descriptive only (`DESCRIPTIVE_ONLY`). No weight is chosen as "best", and
  nothing here measures real-world risk-prediction accuracy.
- Every pair is a **constructed evaluation scenario** (D06), not real multimodal data.

## Provenance

| Item | Value |
|---|---|
| Protocol | `docs/fyp2/e2e5/protocol.json`, committed in `66641a7` (2026-11-02T17:03:53+08:00), before any run. The runner's gate checked that it is committed, unmodified and older than the run start (`results.json` → `protocol_gate`). |
| Runner | `scripts/fusion_eval.py e2`, at HEAD `9d4ace8` with a clean tree. |
| Run history | Two dry runs followed the protocol commit: one at 9295f91, then a review-driven fix of the reporting code (9d4ace8). That fix added the post-hoc tie table, the per-window sha256 check and the figure markers. The official run is the 9d4ace8 re-run. Per-window outputs (scores, levels, dominant evidence, probabilities) were identical in every run (checked). |
| Pipeline | the real `POST /api/sessions/{id}/infer` via `fastapi.testclient.TestClient`, with a temporary SQLite, an injected clock and no port-8000 listener. It runs in one worker subprocess with every `DRA_*` variable stripped. |
| Models | vision `stable_mobilenet_v3_large` (sha256 `b3a42e8d…`) and the telemetry XGBoost (sha256 `9802cb06…`). On every window the vision model id and both sha256 values are checked against `GET /api/models`. |
| Inputs | test split only: `eda_outputs/processed/vision/vision_metadata_with_split.csv` and `…/telemetry/telemetry_test.csv` (sha256 in `results.json`). Images are not copied; `pairs.json` lists file names and sha256. |

## Design (as pre-declared)

- **Strata:** 6, vision {safe = c0, distracted = c1–c9} × telemetry {Safe, Aggressive,
  Distracted}.
- **Pairs:** 10 per stratum, drawn with seed `20261102`. No image or row is used twice: 60
  images and 60 rows from 4 test drivers (p012 10, p026 20, p035 14, p050 16).
- **Runs:** every pair under the five Table 9 weight settings. Each (pair, weight) is a new
  session with exactly one window, so no EMA history is involved: 300 windows.
- **Operational reference** (source labels only):

  | Labels | Reference | Agreeing levels |
  |---|---|---|
  | neither branch non-safe | `REF_LOW` | Low |
  | exactly one branch non-safe | `REF_ELEVATED` | Medium or High |
  | both branches non-safe | `REF_HIGH` | High |

## Validity checks (all passed)

| Check | Result |
|---|---|
| Windows | 300 / 300. All have `SystemHealth = FULL`, both branches fresh and both observations `new`. |
| Formula vs an independent exact-arithmetic oracle (`fractions.Fraction`; it does not call `fusion.py`) | max \|error\| 0.0495 score points; every window is within 0.05, the rounding half-step |
| Rounding | 0 mismatches against round-half-up of the exact value (no window is an exact .x5 tie) |
| RiskLevel vs thresholds 30 / 60, and DominantEvidence vs the documented decision tree | 0 mismatches |
| Returned probabilities identical across the 5 weights for each pair | yes |

## Results (declared metrics)

Agreement with the operational reference and level counts (`e2_reference_agreement.png`):

| Weights w_v / w_t | 0.5/0.5 | 0.6/0.4 | 0.4/0.6 | 0.7/0.3 | 0.3/0.7 |
|---|---|---|---|---|---|
| Pairs agreeing (of 60) | 59 | 59 | 60 | 59 | 59 |
| Low / Medium / High | 10 / 28 / 22 | 10 / 19 / 31 | 10 / 10 / 40 | 10 / 19 / 31 | 11 / 9 / 40 |
| Level changes vs 0.5/0.5 | — | 9 (S4 9 up) | 18 (S2 8, S3 9, S5 1; all up) | 11 (S4 10 up; S2 1 down) | 19 (S2 8, S3 9, S5 1 up; S4 1 down) |
| Attenuation cases | 28 | 19 | 10 | 18 | 10 |
| R14 disagreements | 0 | 1 | 0 | 2 | 0 |

Complementarity at 0.5/0.5:

- When both branches are non-safe (S5, S6), 19 of 20 pairs are High.
- When exactly one branch is non-safe (S2–S4), 27 of 30 pairs are Medium and 3 are High.
- The 3 High single-branch pairs are S2-01 (75.6), S2-07 (68.1) and S3-01 (89.1). All three
  are c0 images where the vision model returned a mid-range P_distraction of 0.36–0.78; the
  fusion rule did not cause them.
- With w = 0.5 and the High threshold at 60, one branch alone contributes at most 50. So in
  this configuration only both branches together can reach High, **by construction**. This
  is a property of the configuration, not an empirical finding.

Attenuation (kept, as D06 requires):

- At 0.5/0.5, 28 windows have one branch ≥ 0.8 and the other < 0.2.
  - 27 are single-branch pairs (S2 8, S3 9, S4 10). They fuse to 49.9–53.2, which is Medium,
    so they agree with `REF_ELEVATED`. Even so, a strong single-branch signal is diluted to
    about half.
  - The 28th is S5-08, a `REF_HIGH` pair. The vision model missed a c4 image
    (P_distraction 0.179), so the pair scored 59.0, Medium, and disagrees with the reference.
    This is a branch-model error, not a fusion effect.

The disagreements:

- **S5-08** at 0.5/0.5, 0.6/0.4 and 0.7/0.3: the vision-model miss above, scoring
  59.0, 50.8 and 42.5.
- **S4-05** at 0.3/0.7: P_distraction 0.997 × 0.3 gives 29.9, which is Low against
  `REF_ELEVATED`.
- Three branch-model disagreements with the source label, all on the vision side:
  - S2-01: c0 image, P 0.512;
  - S3-01: c0 image, P 0.783;
  - S5-08: c4 image, P 0.179.

  Telemetry agrees with its label in all 60 pairs.

R14 (DominantEvidence is raw strength):

- There are 0 cases at 0.5/0.5.
- At asymmetric weights there are 3 cases: S3-01 at 0.6/0.4, and S2-01 and S3-01 at 0.7/0.3.
- In each, the label is Telemetry-dominant while the vision branch has the larger weighted
  contribution. For example, at 0.6/0.4: 0.6 × 0.783 > 0.4 × 0.9995.

## Additional analysis (NOT pre-declared; added after the 2026-11-02 review)

**Saturation.** P_telemetry is outside (0.05, 0.95) in 60 of 60 pairs, and P_distraction in
54 of 60.

- So a single-branch score is about 100 × the weight on that branch.
- Medians for S2 and S3 are 50 / 40 / 60 / 30 / 70 across the five settings; for S4 they are
  50 / 60 / 40 / 70 / 30.
- For these cases the weight, much more than the evidence, decides the level.

**Threshold ties (`results.json` → `summary.post_hoc_not_predeclared.threshold_ties`).**

- Table 9's 0.3 and 0.6, times a branch at about 0.9999, land **on** the 30 and 60
  thresholds. The product rounds to 1 dp and maps a score of exactly 30.0 to Medium and 60.0
  to High.
- So for some windows the level is decided by rounding, not by a margin:

| Weights w_v / w_t | 0.5/0.5 | 0.6/0.4 | 0.4/0.6 | 0.7/0.3 | 0.3/0.7 |
|---|---|---|---|---|---|
| Windows with the exact score within 0.1 of a threshold | 0 | 8 | 12 | 12 | 9 |
| Windows whose level rounding decides | 0 | 0 | 11 | 11 | 0 |
| Pairs agreeing, if the unrounded score were mapped | 59 | 59 | 60 | **48** | 59 |
| Level changes vs 0.5/0.5, unrounded | — | 9 | **7** | **22** | 19 |

- The 11 windows are the same pairs at both weights: S2-02/03/04/08/09/10 and
  S3-02/04/05/06/09. Their exact scores are 29.997–29.9996 at 0.7/0.3 and 59.993–59.996 at
  0.4/0.6.
- The declared numbers above are unchanged. Neither "59/60 at 0.7/0.3" nor "18 changes at
  0.4/0.6" should be quoted without this table.

## What this does not show

- It does not measure real-world accuracy. A State Farm image and a `Driver_Behavior` row were
  never recorded together.
- Agreement is with a policy declared in advance, not with ground-truth severity.
- 10 pairs per stratum is a small, descriptive sample, not a powered study.
- Because the branch models are near-saturated, these numbers mostly describe the weights,
  the thresholds and the rounding at the thresholds. They say little about fusion on
  uncertain branch outputs.

## Files

- `results.json`: provenance, gate, identity, environment, checks and summary (including the
  post-hoc block).
- `pairs.json`: the 60 pairs, with the image file and sha256, the telemetry row and features,
  and the reference.
- `e2_rows.csv`: 300 rows, one per (pair, weight), with every per-window check and
  `exact_score`. This is the table view for both figures.
- `e2_scores_by_stratum.png`: a filled dot is a pair that agrees with the reference, a hollow
  ring one that disagrees, and the bar is the median.
- `e2_reference_agreement.png`.

To reproduce, run `.venv/bin/python scripts/fusion_eval.py e2` from the repo root, with the
data root resolvable.
