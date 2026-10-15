# Reclamation Evidence Ledger

> **Notice (2026-10-09):** The screening results here did not hold up under pre-registered testing, and the well reports are not evidence of recovery at any well. See [NEGATIVE-RESULT-2026-10-09.md](NEGATIVE-RESULT-2026-10-09.md).

**This pipeline watches Alberta's orphan-well reclamation from orbit. It compares Sentinel-2 imagery month for month and stamps every claim with provenance, uncertainty, and limits.**

[![CI](https://github.com/FetchDoge/reclamation-evidence-ledger/actions/workflows/ci.yml/badge.svg)](https://github.com/FetchDoge/reclamation-evidence-ledger/actions/workflows/ci.yml) [![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE) [![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](requirements.txt) [![Release](https://img.shields.io/github/v/release/FetchDoge/reclamation-evidence-ledger)](https://github.com/FetchDoge/reclamation-evidence-ledger/releases) [![Contributor Covenant](https://img.shields.io/badge/Contributor%20Covenant-2.1-4baaaa.svg)](CODE_OF_CONDUCT.md) [![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md) [![Discussions](https://img.shields.io/badge/Discussions-Join-blueviolet.svg)](https://github.com/FetchDoge/reclamation-evidence-ledger/discussions)

An independent satellite watchdog. It uses free Sentinel-2 imagery and a fully automated Python pipeline, and it answers one question per site on a schedule: *is the land healing?*

**[Live evidence dashboard](https://FetchDoge.github.io/reclamation-evidence-ledger/)** · 99-site pilot · 13 licensees · Alberta, Canada

The dashboard (`docs/index.html`) renders from the packets themselves with `python ops/render_dashboard.py`. It shows the audit story, the 99-site findings register, per-site dossiers with NDVI time series, the method, and the ongoing self-audit. It computes every packet-derived number (sites, licensees, findings, render stamp) at render time. The one fixed figure is the registry-size counter (21,892), taken from the 2026-09-01 OWA inventory.

## What it guarantees

- **No attribution, ever.** The packet schema allows only `detected` or `identified` claim tiers. `attributed` is not a valid value, so the pipeline cannot name a responsible party (`schemas/evidence-packet.schema.json`).
- **Month-matched or nothing.** The assessment compares each calendar month only with itself. With fewer than 2 matched months it refuses to assess (`ledger/change.py` raises).
- **No interval without data.** It reports a bootstrap 95% CI on the median delta only with at least 4 matched months. Otherwise the interval is `None`, never guessed (`MIN_MATCHED_MONTHS_FOR_CI`).
- **Raw evidence is kept.** Every chip is stored untouched with a per-scene SHA-256 checksum, and every transform is logged in the packet.
- **Every published packet honors the contract.** CI validates every `packets/*.json` against the schema on each push to main. A packet that fails never ships.

## Quickstart

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 1. Build the site registry — downloads the current OWA monthly inventory automatically.
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
#    fetch new scenes + assess all pilot sites + re-render. No-ops outside
#    the growing season (May-Sep).
python -m ledger.pipeline run-monthly --sites pilots/pilot-01.txt
```

## How it fails

| Condition | Behavior |
|---|---|
| Fewer than 2 month-matched baseline/current months | `ledger.change` raises and writes no packet for that site, never a guess |
| Fewer than 4 matched months | The median delta is reported without a confidence interval |
| Cloud or shadow over the site (SCL mask) | Scene rejected and the rejection recorded in the per-site manifest |
| Recurring run outside May–Sep | No-op: winter snow makes comparisons meaningless |
| Packet violates the schema | CI fails and the packet does not ship |

## Evidence

- **99 evidence packets** are committed in `packets/`: 71 `detected` and 28 `identified`. CI validates all of them against schema v1.1.0 (`validate.yml`, passing on main). **Status 2026-10-09:** these packets' screening claims did not hold under pre-registered testing — the published diagnosis measured a median geocoding error of 2,658 m and found 0 of 99 analysis squares contain their well. They are retained as the published record, not as evidence of recovery. See [NEGATIVE-RESULT-2026-10-09.md](NEGATIVE-RESULT-2026-10-09.md).
- **13 licensees** across the 99 pilot sites (`ops/pilot02-results.csv`).
- **Tests:** `pytest tests/` gives 17 of 17 passing locally (all tests pass out of the box using self-contained fixtures for pipeline determinism, falling back to local `data/chips/` if present). CI runs lint, format check, tests, and schema validation.
- **The caught mistake is documented below.** The first method reported all 27 pilot sites recovering, and the audit traced that to seasonal sampling bias.

## The story in 60 seconds

Alberta has tens of thousands of orphan oil and gas wells — sites whose
operators walked away, leaving cleanup to the public purse. Nobody was
watching whether reclaimed land actually recovers. This project watches from
orbit and publishes exactly what it sees.

Its most important output is a caught mistake, not a green dashboard. The first version of the change-detection method
compared seasonal vegetation medians and reported that **all 27 pilot sites
were recovering**. A full audit found the flaw: baseline scenes were sampled
in May/June while current scenes were sampled in July. Summer is greener than
spring — the method was measuring the calendar, not reclamation. The
assessment was rebuilt around **month-matched median-of-deltas** (each
calendar month compared only to itself, ≥2 matched months required, honest
refusal otherwise). Under the corrected method, most sites show no
significant change, and several honestly report insufficient evidence.

That arc — build, audit, catch the bias, fix it, say so publicly — is the
point. A watchdog that can't catch its own errors can't be trusted to watch
anyone else.

## What it does

1. **Registry** — downloads the Orphan Well Association's monthly inventory
   (21,892 geocoded sites in the 2026-09-01 file used for the pilot; that file is not committed. The 2026-10-01 file geocodes to 22,057 sites, re-run 2026-10-07) and derives coordinates from Dominion Land Survey
   names to LSD centroids. (Coordinate accuracy withdrawn 2026-10-09:
   NEGATIVE-RESULT-2026-10-09.md measured a median error of 2,658 m.)
2. **Imagery** — queries the Sentinel-2 STAC catalog and downloads windowed
   red/NIR/SWIR/blue/SCL chips (500 m buffers) with per-scene checksums,
   cloud/shadow rejection, and incremental backfill.
3. **Assessment** — per-scene NDVI/NDMI/bare-soil indices, SCL cloud masking,
   month-matched baseline-vs-current comparison, schema-validated evidence
   packet per site with claim tier (`detected` / `identified` only —
   attribution is excluded by design).
4. **Ledger** — renders a static, publish-anywhere website: site map, trend
   per site, methodology, and a limitations page.

## Doctrine

Borrowed from imagery interpretation tradecraft:

- **Detection ≠ identification ≠ attribution.** The pipeline may report that
  vegetation changed (detected) and that the change is consistent with
  reclamation (identified). It never names a responsible party (attributed) —
  attribution requires human review and ground truth.
- **Keep the raw evidence.** Every chip is stored untouched with a checksum.
  Every transform is logged. Nothing is a black box.
- **Change over time beats single frames.** Baselines are built from prior
  growing seasons; each new observation is a diff against the baseline.
- **Screen, don't accuse.** Outputs prioritize sites for ground inspection.
  They are not compliance verdicts.

## Known limits

- Sentinel-2's 10 m pixels cannot resolve wellheads or prove contamination,
  legal compliance, causation, or methane emissions.
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

The pipeline runs monthly during growing season (May–Sep) to ingest new scenes and refresh assessments. To install the launchd daemon automatically configured for your checkout path:

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

## Data sources

| Source | What | Access | Cost |
|---|---|---|---|
| OWA site inventory | orphan site list, closure stage (no coordinates in file) | orphanwell.ca (monthly) | free |
| DLS geocoding | LSD-centroid coords derived from OWA site names (accuracy withdrawn 2026-10-09 — see NEGATIVE-RESULT-2026-10-09.md) | built-in (`ledger/sites.py`) | free |
| Sentinel-2 L2A | 10 m multispectral imagery, ~5-day revisit | AWS `s3://sentinel-cogs/` / Copernicus Data Space | free |
| Landsat | deep archive back to 1972 (optional baseline) | USGS EarthExplorer | free |

Copernicus data requires attribution — see the site footer.

## Status

v0.3.1 ([releases](https://github.com/FetchDoge/reclamation-evidence-ledger/releases)), with a 99-site pilot published. Outputs prioritize sites for ground inspection. They are not compliance verdicts.

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

## License

MIT. See [LICENSE](LICENSE). Copernicus Sentinel data requires attribution; see the site footer.
