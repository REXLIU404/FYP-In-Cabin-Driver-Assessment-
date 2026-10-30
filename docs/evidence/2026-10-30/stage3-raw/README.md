# Stage 3 R-1 closure: same-day perf01 with raw per-window timings (2026-10-30)

Why: the Stage-3 audit (CX-A3, `.superpowers/collab/codex/stage3_audit.md`, finding R-1) could not recompute the
2026-10-29 p50/p95, because `perf01.json` kept only the summary. Commit `1cd5660` makes perf01 also write
`perf01_timings.json` (the measured windows after the 20-window warm-up) and bind it in `perf01.json`
(`raw_timings.sha256`, `quantile_rule`). These six runs were made with that code, at `1cd5660`, all on the
same day, alternating stable / RN to spread machine drift evenly. The machine was quiet (load 2.3-4.1 on
8 cores, recorded before and after each run in `runs.log`).

| Run | Vision model (from `/api/models`) | Windows | Rate | capture->render median / p95 / max (ms) | Server total median (ms) | Server vision median (ms) |
|---|---|---|---|---|---|---|
| stable-r1 | stable_mobilenet_v3_large `b3a42e8d...` | 600 | 9.78 Hz | 27 / 31 / 127 | 17.70 | 9.58 |
| RN-r1 | resnet18_search004_seed42 `5e226722...` | 600 | 9.78 Hz | 42 / 45 / 125 | 33.04 | 26.61 |
| stable-r2 | stable | 600 | 9.79 Hz | 28 / 31 / 63 | 18.11 | 9.69 |
| RN-r2 | RN | 600 | 9.79 Hz | 41 / 44 / 63 | 33.15 | 26.56 |
| stable-r3 | stable | 600 | 9.77 Hz | 28 / 31 / 58 | 18.21 | 9.79 |
| RN-r3 | RN | 600 | 9.79 Hz | 41 / 43 / 75 | 33.12 | 26.58 |

- Every run: `short_run` false, 0 console errors, exit 0; the p95 target (<= 1 s) is met by both models with a wide margin.
- Recomputation check (implementer's): for all six, `sha256(perf01_timings.json)` equals `raw_timings.sha256`, and
  `summarise(renderedAtMs - capturedAtMs)` over the file equals `stages.capture_to_render_ms` exactly. The auditor
  reruns this independently.
- Scope: one development machine (Apple M2), Chromium fake camera, prepared telemetry, frozen models; not target
  hardware or a real camera. These runs supersede the 2026-10-29 Stage-3 numbers for the release decision; the
  10-29 files are kept as they were (historical, summary-only).
