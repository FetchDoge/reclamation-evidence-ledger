# Pre-registration: placebo (no-well) false-positive gate, v1

Written and committed 2026-10-16 (America/Edmonton) BEFORE `ledger/placebo.py` was run.
The harness refuses to run unless this file's SHA-256 matches `PREREG-placebo-2026-10-16.sha256`.
Screens, never certifies. A pass here is a precondition for publishing any tier above
`detected`; it is not evidence that any well site has recovered.

## Disclosure (read first)
The method under test (`ledger.change.assess`, thresholds +/-0.08 NDVI, month-matched
median-of-deltas) is byte-identical in its tiering logic to the code Seedling Lab tested on
2026-10-08 (Stage 0a), which flagged 15/100 no-well points "identified" (pre-set KILL line >= 11).
This run is therefore a **reproduction and regression test of a known failing result**, and
the 5% line below is the bar that any *replacement* method must clear before it may publish
tiers. We expect this run to FAIL. A harness that cannot fail would be worthless; one that is
expected to fail today and must pass tomorrow is the point.

## Question
How often does the screen assign the tier `identified` (either direction) to a point where
there is no well, using the same pipeline, same years, same thresholds as for real sites?

## Units
- N = 100 no-well placebo points `NULL-001`..`NULL-100`, drawn by Seedling Lab
  (`/workspace/seedling-ledger/run/stage0a/matched_points.csv`, seed 20261002, matched to the
  pilot sites on township, land-cover group and natural subregion).
- Eligibility (re-verified by the harness, not trusted): nearest AER ST37 surface hole >= 600 m.
  Ineligible points are dropped and reported. If fewer than 80 eligible points remain the run is INCOMPLETE.
- Imagery: the Sentinel-2 L2A chips Seedling Lab already fetched for those points
  (2023-05..2026-08, up to 20 scenes each). The harness records the SHA-256 of each point's
  `manifest.json` and of every chip listed in it; no new imagery is selected after seeing results.

## Method under test (frozen)
`ledger.change.assess` with baseline years 2023-2024, assessment years 2025-2026, `Config`
defaults (recover delta +0.08, stall delta -0.08), bootstrap seed 20260927. No parameter may be
changed after this file is committed; a changed method needs a new pre-registration file.

## Primary outcome and pass line
- Primary: share of eligible placebo points with `claim.tier == "identified"` (recovering or stalled).
- **PASS: flagged / eligible <= 5%** (i.e. <= 5 of 100). Anything above is **FAIL**.
- Points that refuse (<2 matched months) count as not flagged and stay in the denominator.
- INCOMPLETE if < 80 eligible points, or if more than 10 points have neither a result nor a documented refusal.
- The harness also reports the exact 95% Wilson upper bound on the flag rate, for context only.

## Secondary outcomes (reported, cannot rescue a FAIL)
1. Share flagged under the audit rule: |delta| >= 0.08 AND a CI exists AND the CI excludes 0.
2. Share of placebo deltas that are positive (a regional-weather signature if far above 50%).
3. Median and 5/95th percentiles of the placebo deltas.

## Consequences (binding)
- If FAIL: the pipeline version may not publish any tier above `detected` (measurement only) or
  `not_assessable`; "identified" stays withheld.
- If PASS: tiers above `detected` still also require verified geolocation (`ledger.geolocate`),
  a resolved pad footprint, and the guard-pad detection check (separate pre-registration, not yet written).
- Results are stored under `placebo/runs/<date>/` with SHA-256 of inputs and outputs.
