# Pre-registration: placebo (no-well) gate for the CI-gated tier rule `ci-gated-v2`, v2

Written and committed 2026-10-16 (America/Edmonton) BEFORE the harness was run against this rule.
The harness refuses to run unless this file's SHA-256 matches `PREREG-placebo-ci-gated-v2-2026-10-16.sha256`.
Supersedes nothing: the v1 pre-registration (`PREREG-placebo-2026-10-16.md`) tested the pre-#33 rule
and stays on record (13/98 flagged, FAIL). Screens, never certifies.

## Disclosure (read first)
- Rule under test: `ledger.change.assign_tier`, `TIER_RULE = "ci-gated-v2"` (from PR #33): `identified` only if
  |median matched-month NDVI delta| >= 0.08 AND a bootstrap 95% CI exists (>= 4 matched months) AND the CI excludes zero.
- **We already know roughly what to expect.** The v1 run's secondary count, "audit rule" (the same condition),
  was 3 of 98 on these same chips, and Seedling Lab's Stage 0a reported 3/100. So this run will most likely
  PASS the 5% line (3/98 = 3.1%) *on data already seen*. It is a regression check of the rule as merged,
  **not** an independent confirmation and **not** a fresh draw of placebo points.
- A pass is necessary, not sufficient. Separate findings stand: the square-level screen still flagged 6/100 matched-control
  nulls and 0/10 known new pads (Seedling Lab v2a, RE-SCOPE), and 10 m pixels cannot resolve many pads. A pass here
  does not show that any site recovered or that the screen detects reclamation.

## Question
How often does the CI-gated rule assign `identified` (either direction) at a point with no well, using the same pipeline,
years and thresholds as for real sites?

## Units (identical to v1, unchanged)
N = 100 no-well points `NULL-001..100` (`/workspace/seedling-ledger/run/stage0a/matched_points.csv`, seed 20261002),
Sentinel-2 L2A chips already fetched, hashes re-verified by the harness. Eligibility re-verified against the current AER ST37:
nearest surface hole >= 600 m; ineligible points are dropped and reported. INCOMPLETE if < 80 eligible.

## Method under test (frozen)
`ledger.change.assess` as of the merge of PR #33 into this branch (tier rule `ci-gated-v2`), baseline 2023-2024 vs 2025-2026,
`Config` defaults, bootstrap seed 20260927. No parameter may change after this commit; a changed method needs a new file.

## Primary outcome and pass line
- Primary: share of eligible placebo points with tier `identified` as returned by `assess()`.
- **PASS: flagged / eligible <= 5%** (at most 5 of 100). Otherwise **FAIL**. Refusals (<2 matched months) count as not flagged and stay in the denominator.
- Reported for context: exact 95% Wilson upper bound (with ~98 points and 3 flagged it is ~8.6%, so a pass cannot exclude a true rate above 5%).

## Secondary (reported, cannot rescue a FAIL)
Share of positive placebo deltas; median and 5/95th percentile of placebo deltas; count flagged by `|delta|>=0.08` alone (the v1 rule, for comparison).

## Consequences (binding)
- FAIL: `identified` stays withheld, as today.
- PASS: only removes this one blocker. `identified` still needs verified geolocation, a resolved pad footprint, a pad-vs-ring test
  and guard-pad detection (not yet pre-registered), and the publication hold from PR #33 stays on until Marcus lifts it.
