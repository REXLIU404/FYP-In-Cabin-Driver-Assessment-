# Errata: figure file paths in README.md

The E-system-level `README.md` (committed in `262846d`) lists the runner figures as
`e2-dmd/figures/` and `e5-dmd/figures/`. The runner actually writes them next to the results:

- `e2-dmd/e2_reference_agreement.png`
- `e2-dmd/e2_scores_by_stratum.png`
- `e5-dmd/e5_timeline.png`

No measurement, number or protocol changed; this note only corrects the file paths.
