# Changelog

## Unreleased: M1 "Honest Ledger" (2026-10-08, hold added 2026-10-10)

- feat: publication hold (2026-10-10). Every site is published as "detected – screening only"; site-level "identified" is withheld pending a surrounding-land baseline because no-well control points still produced 3/100 "identified" under the current rule (Seedling Lab, 2026-10-08). The CI-gated screen result stays in each packet as `claim.screen_tier_internal`. Schema 1.3.0 (`claim.publication_hold`, `claim.screen_tier_internal`; a published `identified` is rejected while a hold is active). Published identified: v1 28 -> 0.
- feat: re-assessment archives the previous packet to `packets/history/<site>/<date>.json` and carries its revisions forward instead of overwriting.
- fix: operator (licensee) names removed from the dashboard, packet pages, README and `ops/pilot02-results.csv`; they remain only in the pilot selection inputs.
- feat: "Re-scoring in progress" banner on the dashboard, packet pages and README.
- fix: tier rule `ci-gated-v2`. `identified` now needs |median delta| >= 0.08 AND a 95% CI (>= 4 matched months) that excludes zero. Neutral wording ("NDVI higher/lower than baseline in the analysis square") replaces "vegetation recovering" / "stalled or regressing".
- fix: all 99 packets re-tiered offline from their stored observations under the CI rule: identified 28 -> 10 (2026-10-08, before the hold), detected 71 -> 89 (6 lacked a CI, 12 had a CI including zero). Public diff in `docs/retier-2026-10.md` / `.csv`.
- feat: packet schema 1.2.0 (claim.direction, claim.tier_rule, chip scene_id/source_url, provenance.review, owa_inventory_file, owa_recheck, lineage_audit, revisions).
- fix: removed the unrecorded "human-reviewed before publish" stamp; packets carry an empty review log instead.
- feat: OWA inventory URL, file date and SHA-256 recorded per run (hardcoded 2026-09-01 removed); run-monthly refreshes the inventory first.
- chore: radiometric lineage audit re-run over all 273 scenes the packets cite (was 62); 0 anomalies.
- fix: TLS verification on by default; GDAL_HTTP_UNSAFESSL is opt-in via LEDGER_TRUST_EGRESS_PROXY_TLS=1.
- feat: run-monthly re-assesses with --force and period-named packets; assess_all no longer hardcodes .venv or years.
- ci: pytest runs in CI; the chip-dependent determinism test skips without data.
- fix: two provisional footprints (16-14-018-26W4, 07-30-018-26W4) re-projected from the wrong UTM zone (were 6 degrees east).
- docs: README and dashboard drop "is the land healing?", "watchdog", the false refusals line and the hand-typed 21,892; Landsat marked not implemented; colophon link fixed to marsojuji-cmyk; screening-only disclaimer added.

## Unreleased: 360° engineering audit (2026-10-10, merged from main)

- 360° engineering audit (AUDIT-2026-10-10.md): P0/P1 findings fixed, P2 parked with reasons
- fix: withdraw the published-false ±300 m geocoding accuracy claim everywhere it appeared (sites.py docstrings, registry `geo_method`, packet caveats, rendered HTML, README); all now reference NEGATIVE-RESULT-2026-10-09.md
- feat: `tests/test_geocode.py` — grid-geometry pins (LSD/township/range steps, boustrophedon parity) + xfail work-order test for ground-truth verification of `dls_to_latlon`
- feat: `pyproject.toml` — `reclamation-ledger` is now pip-installable with console entry points for all 7 CLIs; removed every `sys.path` import hack
- fix: `ops/assess_all.py` uses `sys.executable` instead of a hardcoded `.venv` python; packet period is a `--period` flag instead of a hardcoded string
- fix: deduplicate `sha256_file` (single home: `ledger.packet`)
- ci: ruff lint + format check on every push; fixed 43 findings, formatted 19 files
- fix: `test_observation_count_definitions` reads period years from each packet's own transform instead of hardcoding 2023-2026
- docs: README test count 11 → 17; Evidence section carries the 2026-10-09 negative-result status inline

## v0.4.0 (2026-10-09)

- feat: enhance community standards, automated testing, and client portal (#28)

## v0.3.1 (2026-10-05)

- fix: grant lint-title job pull-requests read permission (#14)

## v0.3.0 (2026-09-29)

- feat: interactive evidence dashboard generated from packets
- feat: dashboard is single-file, dependency-free (`ops/render_dashboard.py` → `docs/index.html`): self-audit story, 99-site findings register with delta histogram and filters, per-site dossiers (NDVI time series with month-matched observations ringed, delta + bootstrap CI, claim, caveats, provenance), method plate, BACI self-audit plate, colophon. Replaces the static snapshot index; per-site packet pages retained as the deep-dive layer.
- docs: README now reflects the 99-site / 13-licensee pilot and the dashboard.
- fix: bump CI to Python 3.12 for rasterio 1.5 support (#8)

## v0.2.0 (2026-09-28)

- feat: pilot-02 evidence — 72 new packets, tier/identified results, Pages snapshot
- feat: pilot-02 expansion selection + tooling (99 sites, 13 licensees)

## v0.1.0 (2026-09-27)

- feat: provisional hand-digitized footprints for 5 pilot sites
- feat: radiometric lineage audit recorded as evidence
- fix: degenerate bootstrap CI refused; claim labels made exact; determinism tripwires
- fix: actually ignore data/ (trailing comments broke gitignore patterns)
