# Reclamation Evidence Ledger

> **Notice (2026-10-09):** The screening results here did not hold up under pre-registered testing, and the well reports are not evidence of recovery at any well. See [NEGATIVE-RESULT-2026-10-09.md](NEGATIVE-RESULT-2026-10-09.md).

**This pipeline screens Alberta's orphan well sites from orbit. It compares Sentinel-2 imagery month for month and stamps every claim with its tier, provenance, uncertainty, and limits.**

[![CI](https://github.com/FetchDoge/reclamation-evidence-ledger/actions/workflows/ci.yml/badge.svg)](https://github.com/FetchDoge/reclamation-evidence-ledger/actions/workflows/ci.yml) [![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE) [![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](requirements.txt) [![Release](https://img.shields.io/github/v/release/FetchDoge/reclamation-evidence-ledger)](https://github.com/FetchDoge/reclamation-evidence-ledger/releases) [![Contributor Covenant](https://img.shields.io/badge/Contributor%20Covenant-2.1-4baaaa.svg)](CODE_OF_CONDUCT.md) [![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md) [![Discussions](https://img.shields.io/badge/Discussions-Join-blueviolet.svg)](https://github.com/FetchDoge/reclamation-evidence-ledger/discussions)

An independent, low-cost satellite screen. It uses free Sentinel-2 imagery and an automated Python pipeline, and it asks one question per site: *did vegetation (NDVI) in the ~1 km² square around the site visibly change compared with its own earlier growing seasons?*

> **Screening only.** Outputs prioritize sites for a closer look. They are not legal proof, not a reclamation certification or compliance verdict, and not a methane, soil, contamination or subsurface measurement. The analysis square is mostly land *around* the pad, so a change describes that square, not the pad. No packet has been human-reviewed yet; each says so.

**[Live evidence dashboard](https://marsojuji-cmyk.github.io/reclamation-evidence-ledger/)** · 99-site pilot · Alberta, Canada

> **Re-scoring in progress (Oct 2026): site-level calls are withheld pending a surrounding-land baseline.** Every site is published as *detected – screening only*. No-well control points still produced 3/100 "identified" under the current rule (Seedling Lab, 2026-10-08), so no site-level "identified" call is published until a pad-vs-surrounding-land baseline exists.

The dashboard (`docs/index.html`) renders from the packets themselves with `python ops/render_dashboard.py`. It shows the audit story, the 99-site findings register, per-site dossiers with NDVI time series, the method, and the ongoing self-audit. It computes every packet-derived number (sites, published tiers, deltas, CIs, render stamp) at render time. The figures in Plates I and V (the 2026-09-27 verification traces and the BACI probe notes) are typed from those audit notes, and the dashboard labels them that way.

## Where this stands (2026-10-16) and what's next

- **Locations:** 21,340 of 22,057 OWA inventory sites now have a verified AER ST37 surface-hole location; 717 are refused as "location unverified" ([details](ops/results/geolocation-verification-2026-10-16.md)). The old DLS geocoder was a median ~2.7 km off.
- **Control (no-well) placebo:** the CI-gated rule flagged 3 of 98 no-well points as `identified` (3.1%, 95% upper bound 8.6%; pass line <= 5%, committed before the run). The earlier rule flagged 13 of 98 and failed. This reran points I had already seen, so it is a regression check, not independent confirmation, and does not show the screen detects reclamation. See [`placebo/`](placebo/) and [STAGE0-2026-10-16.md](STAGE0-2026-10-16.md).
- **Next:** [NEXT-STEPS.md](NEXT-STEPS.md). In short, a fresh pre-registered control run, a pad-vs-ring test at 10 m, and three buyer interviews; if the control passes and the interviews are positive, build it, and if either fails, stop.

## What it guarantees

- **A tier is earned, not assumed.** The screen rule (`ci-gated-v2`) allows `identified` only when |median matched-month NDVI delta| ≥ 0.08 **and** a bootstrap 95% CI (≥ 4 matched months) **and** a CI that excludes zero. **While the publication hold is active (since 2026-10-10) the published tier is `detected – screening only` for every site**; the screen result is kept in each packet as `claim.screen_tier_internal` for internal tracking, and the schema rejects a published `identified` while the hold is on.
- **Nothing is silently overwritten.** Re-assessing a site archives the previous packet under `packets/history/<site>/<date>.json` and carries its revision log forward.
- **No attribution, ever.** The packet schema allows only `detected` or `identified` claim tiers. `attributed` is not a valid value, so the pipeline cannot name a responsible party (`schemas/evidence-packet.schema.json`).
- **Month-matched or nothing.** The assessment compares each calendar month only with itself. With fewer than 2 matched months it refuses to assess (`ledger/change.py` raises).
- **No interval without data.** It reports a bootstrap 95% CI on the median delta only with at least 4 matched months. Otherwise the interval is `None`, never guessed (`MIN_MATCHED_MONTHS_FOR_CI`).
- **Evidence is checkable.** Every chip is recorded with its SHA-256, its scene ID and the source COG URL it was read from, and every transform is logged in the packet. Chips themselves are not committed (they are re-derivable with `ledger.imagery fetch`). Each packet names the OWA inventory file it used by URL, date and SHA-256 (packets built before 2026-10 say that this was not recorded and carry a re-check against the 2026-10-01 file instead).
- **No claimed review without a record.** `provenance.review` is an empty log until a human review is actually recorded.
- **Every published packet honors the contract.** CI validates every `packets/*.json` against the schema on each push to main. A packet that fails never ships.

## Quickstart

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 1. Build the site registry — downloads the current OWA monthly inventory automatically
#    and writes data/sites.owa_provenance.json (file URL, date, SHA-256).
#    The OWA file carries no coordinates: sites are geocoded from their
#    Dominion Land Survey names to LSD centroids. COORDINATE ACCURACY
#    WITHDRAWN 2026-10-09: the published diagnosis (NEGATIVE-RESULT-2026-10-09.md)
#    measured a median error of 2,658 m on 20,000 wells. Do not screen on these
#    positions until dls_to_latlon is verified against ground truth.
python -m ledger.sites --out data/sites.parquet

# 2. Fetch imagery chips for pilot sites (STAC query + windowed band download,
#    500 m buffer crops, per-site manifest with URLs, checksums, rejections)
python -m ledger.imagery fetch --sites pilots/pilot-01.txt \
    --start 2023-05-01 --end 2026-08-31 --out data/chips --max-scenes 10
# Re-running fetch for a site only downloads dates it doesn't already have
# (incremental backfill — safe to repeat for clouded-out years).

# 3. Assess chips -> schema-validated evidence packet (SCL cloud mask, NDVI/NDMI/
#    bare-soil/SAVI/MSAVI per scene, month-matched baseline diff with bootstrap
#    95% CI on the median delta, claim tier)
python -m ledger.change assess --site "01-06-018-26W4 (100)" \
    --chips data/chips/01-06-018-26W4__100_ \
    --baseline-start 2023 --baseline-end 2024 --assessment 2025-2026 \
    --out packets/

# 4. Render the static ledger site
python -m ledger.render --packets packets/ --out out/ledger/

# 5. Recurring run (the entry point ops/ca.reclamation-ledger.plist calls):
#    refresh the OWA inventory + fetch new scenes + re-assess all pilot sites
#    (--force) + re-render. No-ops outside the growing season (May-Sep).
python -m ledger.pipeline run-monthly --sites pilots/pilot-02.txt

# TLS verification is on. Only on a network whose TLS-intercepting proxy GDAL
# cannot verify, opt in with LEDGER_TRUST_EGRESS_PROXY_TLS=1 (packets record it).
```

## How it fails

| Condition | Behavior |
|---|---|
| Fewer than 2 month-matched baseline/current months | `ledger.change` raises and writes no packet for that site, never a guess |
| Fewer than 4 matched months | The median delta is reported without a confidence interval, and the site cannot be `identified` |
| \|Δ\| ≥ 0.08 but the 95% CI includes zero | Tier stays `detected`: "change beyond threshold, not supported" |
| Cloud or shadow over the site (SCL mask) | Scene rejected and the rejection recorded in the per-site manifest |
| Recurring run outside May–Sep | No-op: winter snow makes comparisons meaningless |
| Packet violates the schema | CI fails and the packet does not ship |

## Evidence

- **99 evidence packets** are committed in `packets/`, all published as `detected – screening only`. CI validates all of them against schema v1.3.0 (`validate.yml`).
- **Re-tiered 2026-10.** Under the first rule, which ignored the CI, 28 packets were published as `identified`. 18 of those had no CI (6) or a CI that includes zero (12). Then, on 2026-10-10, all site-level calls were withheld pending a surrounding-land baseline. The full before/after diff is public: [`docs/retier-2026-10.md`](docs/retier-2026-10.md).
- **Why the hold:** the CI resamples months within the same two baseline and two current years, the baseline includes the 2023 drought, 80 of 99 deltas are positive, and the rule still fired at 3 of 100 no-well control points. The signal is likely partly regional until a pad-vs-surrounding-ring baseline is built (milestone M3).
- **Radiometric lineage** is audited for all 273 scenes the packets cite (`ledger/data/radiometric_lineage.json`, 2026-10-08, 0 anomalies).
- **Operator names are not published** on the dashboard, packet pages or result files. A tier describes vegetation in a square around a DLS centroid; it is not a finding about any operator.
- **Status 2026-10-09:** these packets' screening claims did not hold under pre-registered testing — the published diagnosis measured a median geocoding error of 2,658 m and found 0 of 99 analysis squares contain their well. They are retained as the published record, not as evidence of recovery. See [NEGATIVE-RESULT-2026-10-09.md](NEGATIVE-RESULT-2026-10-09.md).
- **Tests:** CI runs ruff lint and format checks, `pytest tests/` and schema validation. `test_pipeline_rerun_deterministic` uses downloaded chips under `data/chips/` when present (gitignored, reproducible via `ledger.imagery fetch`) and otherwise a self-contained synthetic fixture.
- **The caught mistake is documented below.** The first method reported all 27 pilot sites recovering, and the audit traced that to seasonal sampling bias.

## The story in 60 seconds

Alberta has tens of thousands of orphan oil and gas well sites whose
operators are gone, leaving cleanup to the Orphan Well Association. This
project adds an independent, checkable screen of whether vegetation around
those sites visibly changes, and publishes what it measures with its limits.

Its most important output is a caught mistake, not a green dashboard. The first version of the change-detection method
compared seasonal vegetation medians and reported that **all 27 pilot sites
were recovering**. A full audit found the flaw: baseline scenes were sampled
in May/June while current scenes were sampled in July. Summer is greener than
spring — the method was measuring the calendar, not reclamation. The
assessment was rebuilt around **month-matched median-of-deltas** (each
calendar month compared only to itself, ≥2 matched months required, honest
refusal otherwise). Under the corrected method, most sites show no
change beyond the threshold. (No site in the 99-site pilot fell below the
2-matched-month minimum, so no refusals were published.)

The second caught mistake came in October 2026: the tier rule ignored the
confidence interval, so 28 sites were called `identified` although 18 had no
CI or a CI including zero. A no-well control test then showed even the
corrected rule fires at 3 of 100 points with no well, so every site-level
call is now withheld until a surrounding-land baseline exists. All 99 packets
were re-tiered and the diff published.

That arc — build, audit, catch the error, fix it, say so publicly — is the
point. A screen that can't catch its own errors can't be trusted.

## What it does

1. **Registry** — downloads the Orphan Well Association's monthly inventory,
   records its URL, file date and SHA-256, and derives coordinates from
   Dominion Land Survey names to LSD centroids (the 2026-10-01 file geocodes
   to 22,057 sites). The file itself is not committed. (Coordinate accuracy
   withdrawn 2026-10-09: NEGATIVE-RESULT-2026-10-09.md measured a median
   error of 2,658 m.)
2. **Imagery** — queries the Sentinel-2 STAC catalog and downloads windowed
   red/NIR/SWIR/blue/SCL chips (500 m buffers) with per-scene checksums,
   cloud/shadow rejection, and incremental backfill.
3. **Assessment** — per-scene NDVI/NDMI/bare-soil indices, SCL cloud masking,
   month-matched baseline-vs-current comparison, schema-validated evidence
   packet per site with claim tier (`detected` / `identified` only, CI-gated —
   attribution is excluded by design).
4. **Ledger** — renders a static, publish-anywhere website: site map, trend
   per site, methodology, and a limitations page.

## Doctrine

Borrowed from imagery interpretation tradecraft:

- **Detection ≠ identification ≠ attribution.** The pipeline may report that
  a delta was measured (detected) and that NDVI in the analysis square moved
  beyond the threshold with a 95% CI that excludes zero (identified, a
  screening hypothesis; currently withheld from publication). It does not say the pad is reclaimed, and it never
  names a responsible party (attributed) — attribution requires human review
  and ground truth.
- **Keep the raw evidence.** Every chip is stored untouched with a checksum.
  Every transform is logged. Nothing is a black box.
- **Change over time beats single frames.** Baselines are built from prior
  growing seasons; each new observation is a diff against the baseline.
- **Screen, don't accuse.** Outputs prioritize sites for ground inspection.
  They are not compliance verdicts.

## Known limits

- Sentinel-2's 10 m pixels cannot resolve wellheads or prove contamination,
  legal compliance, causation, or methane emissions. This is not a methane
  detection system.
- The 500 m buffer is a ~1 km² square, mostly land around the pad. In 4 of 5
  hand-checked pilot sites no pad was visible at 10 m.
- The bootstrap CI measures within-season consistency over matched months,
  not year-to-year variability; regional weather moves every site together.
- Compare growing season to growing season only (May–Sep). Alberta snow
  (Nov–Mar) makes winter comparisons meaningless; drought years mimic
  non-recovery.
- Every public claim carries its claim tier and provenance. No exceptions.

## Layout

```
ledger/          pipeline modules (sites → imagery → indices → change → packet → render)
schemas/         JSON schema for evidence packets (the contract everything honors)
pilots/          pilot site lists (start small: 20–30 sites, one county)
data/            raw inputs (chips/ gitignored; reproducible via fetch, not stored)
packets/         evidence packets (generated; each is self-describing)
docs/            published ledger site snapshot (GitHub Pages serves this)
ops/             launchd plist for the recurring run
```

## Recurring run

The pipeline runs monthly during growing season (May–Sep), refreshes the OWA inventory each run and re-assesses sites with new scenes. It is macOS-only (launchd). To install the launchd agent configured for your checkout path:

```bash
# 1. Install plist configured for this checkout into ~/Library/LaunchAgents/
python -m ledger.pipeline install-plist

# 2. Load the daemon
launchctl load ~/Library/LaunchAgents/ca.reclamation-ledger.plist
```

To preview the populated plist XML without installing:
```bash
python -m ledger.pipeline generate-plist
```

On Linux, an equivalent cron line is
`0 2 15 5-9 * cd /path/to/reclamation-evidence-ledger && .venv/bin/python -m ledger.pipeline run-monthly`.

## Data sources

| Source | What | Access | Cost |
|---|---|---|---|
| OWA site inventory | orphan site list, closure stage (no coordinates in file) | orphanwell.ca (monthly) | free |
| DLS geocoding | LSD-centroid coords derived from OWA site names (accuracy withdrawn 2026-10-09 — see NEGATIVE-RESULT-2026-10-09.md) | built-in (`ledger/sites.py`) | free |
| Sentinel-2 L2A | 10 m multispectral imagery, ~5-day revisit | AWS `s3://sentinel-cogs/` / Copernicus Data Space | free |
| Landsat | deep archive back to 1972 (optional baseline) — **not yet implemented; no packet uses it** | USGS EarthExplorer | free |

Copernicus data requires attribution — see the site footer.

## Status

v0.3.1 ([releases](https://github.com/FetchDoge/reclamation-evidence-ledger/releases)), with a 99-site pilot published and re-tiered (M1 "Honest Ledger", 2026-10). Outputs prioritize sites for ground inspection. They screen; they never certify, and they are not compliance verdicts or legal proof.

## Contributing & Community

We welcome contributions, methodological audits, and data validation! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for local setup, testing guidelines, and PR workflow, and [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) for community standards.

- Join discussions: [GitHub Discussions](https://github.com/FetchDoge/reclamation-evidence-ledger/discussions)
- Report bugs: [Issue Tracker](https://github.com/FetchDoge/reclamation-evidence-ledger/issues)
- Security reports: [SECURITY.md](SECURITY.md)

## Citation

If you use this project, pipeline methodology, or the published evidence packets in research or reports, please cite it:

```bibtex
@software{richards2026reclamation,
  author = {Richards, Marcus},
  title = {Reclamation Evidence Ledger: Satellite Watchdog for Alberta Orphan Well Reclamation},
  year = {2026},
  url = {https://github.com/FetchDoge/reclamation-evidence-ledger},
  version = {0.4.0}
}
```

See [CITATION.cff](CITATION.cff) for complete metadata.

Built by Marcus Richards, directing AI coding agents.

## License

MIT. See [LICENSE](LICENSE). Copernicus Sentinel data requires attribution; see the site footer.
