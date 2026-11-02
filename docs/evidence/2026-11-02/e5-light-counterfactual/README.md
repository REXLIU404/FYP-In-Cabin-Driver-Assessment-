# E5 (light): single-branch counterfactuals on the viva_compact scenario (2026-11-02)

Status: **PASS** (validity).

- The result is descriptive only (`DESCRIPTIVE_ONLY`).
- This is a **constructed evaluation scenario** (D06). It is not real multimodal data and not
  evidence of real-world risk-prediction accuracy.

## Provenance

| Item | Value |
|---|---|
| Protocol | `docs/fyp2/e2e5/protocol.json` §`e5_light`, committed in `66641a7` before any run. The runner gate passed. |
| Runner | `scripts/fusion_eval.py e5`, at HEAD `9d4ace8`. The only dirty path was the untracked E2 evidence, written by the E2 run just before this one. |
| Run history | Same as E2: dry runs after the protocol commit, a first run at `9295f91`, and the official re-run at `9d4ace8`. Per-window outputs were identical in every run (checked). |
| Pipeline | The real `/infer` (TestClient, temporary SQLite, injected clock), with the session in `CONSTRUCTED_SCENARIO_RUNTIME`. Fusion, the vision EMA (α 0.35, NEW observations only) and the Live AlertSeverity FSM are the product code. Weights 0.5/0.5, thresholds 30/60. |
| Models | The same stable vision and telemetry models as E2. The vision id and both sha256 values are checked on every window. |
| Timeline | Follows `ai/src/scenarioTimeline.ts` at the product default of 10 windows/s: 600 windows over 60 s per variant. Frames change every 200 ms and telemetry rows every 2 s. |

## Variants

| Variant | What changes |
|---|---|
| `FUSED` | nothing: `viva_compact` as declared |
| `VISION_HELD_SAFE` | every segment's vision is c0, so only telemetry varies |
| `TELEMETRY_HELD_SAFE` | every segment's telemetry is Safe, so only vision varies |

All three are built by `build_dataset_replay.build_bundle` with the same seed. The runner
checked the inputs (`unchanged_segment_identity` in `results.json`):

- every segment whose labels were unchanged has byte-identical frames and rows;
- in each changed segment, only the held branch differs.

## Results (declared metrics, FUSED)

| # | Segment (V / T) | Reference | Agreeing windows | RiskScore mean / max / last | Highest alert |
|---|---|---|---|---|---|
| 1 | Baseline (c0 / Safe) | REF_LOW | 100/100 | 0.0 / 0.0 / 0.0 | NORMAL |
| 2 | Telemetry only (c0 / Aggressive) | REF_ELEVATED | 40/40 | 50.0 / 50.0 / 50.0 | CAUTION |
| 3 | Telemetry wavers (c0 / Safe) | REF_LOW | 40/40 | 0.0 / 0.0 / 0.0 | CAUTION |
| 4 | Telemetry only (c0 / Aggressive) | REF_ELEVATED | 40/40 | 50.0 / 50.0 / 50.0 | CAUTION |
| 5 | Vision only (c1 / Safe) | REF_ELEVATED | 96/100 (lag 400 ms) | 47.5 / 50.0 / 49.8 | CAUTION |
| 6 | Both (c4 / Distracted) | REF_HIGH | 100/100 | 93.1 / 99.0 / 98.4 | HIGH_ALERT |
| 7 | Recovery (c0 / Safe) | REF_LOW | 178/180 (lag 200 ms) | 1.1 / 31.5 / 0.1 | CAUTION |

**Branch contributions in "Both".** These are computed per window as FUSED minus the variant
with that branch held safe:

- vision adds a median of 43.7 points (31.6–49.0);
- telemetry adds a median of 49.9 points (49.6–50.0).

The two contributions add up to the fused score to within 0.4 points; the gap is the held
branch's small residual probability plus rounding. With one branch held safe, "Both" stays
Medium/CAUTION:

- telemetry alone: 50.0;
- vision alone: median 43.85, max 49.1.

Neither held variant reaches High or HIGH_ALERT anywhere in the 60 s.

## Additional descriptive statistics (NOT pre-declared)

**Alert at segment end.** NORMAL, then CAUTION for segments 2–5, HIGH_ALERT for 6 and
NORMAL for 7.

**FSM timings.**

- **HIGH_ALERT** starts 2.0 s into "Both". This is the 2 s High-sustain rule.
- **Recovery** reaches NORMAL 10.4 s into the segment in FUSED and TELEMETRY_HELD_SAFE, and
  10.0 s in VISION_HELD_SAFE. The Live (R10) FSM opens a Low run only on a NEW observation
  whose own branch score is below 30. The run must then hold for 10 s on the server clock and
  across the NEW-observation span.
  - In FUSED the fused score is Low from 42.2 s.
  - Vision's own smoothed score was still 41.0 at 42.2 s. It first fell below 30 on the NEW
    frame at 42.4 s (26.7).
  - So the 10 s count started at 42.4 s, and NORMAL came at 52.4 s.
- **"Telemetry wavers"** lasts 4 s, too short to clear CAUTION.
- **Leaving HIGH_ALERT:** the first Recovery window is CAUTION, at score 31.5 (Medium).

**Smoothing.**

- Only vision is EMA-smoothed (`backend/app/inference.py`). Telemetry moves the score at its
  first new row.
- The c0 → c1 change into "Vision only" needed 400 ms (4 windows, 3 NEW frames) to cross into
  Medium. This describes that one transition, not a general constant.

**Saturation.**

- Telemetry is near-saturated throughout: P_telemetry is at least 0.999 when non-safe and at
  most 0.0089 when Safe.
- The c0 and c1 frames are near-saturated too.
- The c4 frames in "Both" are not: 20 of 50 NEW c4 frames have a raw P_distraction in
  (0.05, 0.95), with a minimum of 0.179. That minimum is the same p050 c4 image the model
  misses in E2 pair S5-08. This is why the vision contribution there has a median of 43.7,
  not about 50, and why FUSED dips to 81.6.

## What it shows

- **Single-branch vs both.** Under 0.5/0.5, each branch alone gives a Medium score and CAUTION
  in this scenario; only "Both" reaches High and HIGH_ALERT.
  - With w = 0.5 and the High threshold at 60, a single branch contributes at most 50.
    The single-branch result is therefore guaranteed **by the configuration**. It is not an
    empirical property.
  - What the run does measure is how far the fused score sits from the thresholds, and the
    EMA and FSM timings.
- **Attenuation (the declared counter-example).** One strong branch is diluted to about half:
  - "Vision only": P_distraction mean 0.949, fused score about 50 (Medium);
  - "Telemetry only": P_telemetry about 0.9999, fused score rounding to 50.0.

## What this does not show

- It is one scenario with one test driver (p050), 60 s long, and descriptive only.
- **The base scenario was authored for this storyline before the protocol.** `viva_compact`
  is the viva demo, committed in `1e05cba`. It was designed to show every risk situation once,
  with Recovery long enough for the 10 s NORMAL latch. The FUSED storyline was designed in,
  not measured blind.
- The labels are dataset labels arranged into a story, not a recorded trip. Agreement is with
  the declared policy, not ground-truth severity.
- **This is a held-safe single-branch ablation.** It is not the coverage matrix's E5-A (vision
  corrupted, telemetry clean) or E5-B (vision clean, telemetry stressed). Those paths are still
  `PLANNED_ONLY` (`docs/fyp2/03_EVALUATION_COVERAGE_MATRIX.md`).

## Files

- `results.json` holds provenance, gate, identity, the three scenarios and their segments, the
  input identity check, and the per-segment summary for every variant:
  - agreement, lag, levels and dominant evidence;
  - alert first, last and max;
  - first HIGH_ALERT and first NORMAL;
  - mean branch probabilities;
  - the branch contributions.
- `e5_windows.csv`: 1,800 windows (3 variants × 600). This is the table view for the figure.
- `e5_timeline.png`.

To reproduce, run `.venv/bin/python scripts/fusion_eval.py e5`. Bundles are rebuilt in a
temporary directory; no images are written to the repo.
