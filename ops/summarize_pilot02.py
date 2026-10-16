#!/usr/bin/env python3
"""Summarize pilot-02 assessment results for the run report.

Reads packets/*.json (schema v1.3.0), joins licensee from the registry,
prints tier x confidence distribution, licensee breakdown, refusal count,
and per-licensee delta stats to the console (internal use only). The CSV it
writes, ops/pilot02-results.csv, carries NO licensee names: the repo is
public and licensee names are not published.
"""

import glob
import json
from collections import Counter

import pandas as pd

ROOT = "."
packets = sorted(glob.glob("packets/*.json"))
reg = pd.read_parquet("data/sites.parquet").set_index("site_id")

tiers = Counter()
conf_by_tier = Counter()
refusals = []
rows = []
for path in packets:
    p = json.load(open(path))
    claim = p.get("claim", {})
    tier, conf = claim.get("tier"), claim.get("confidence")
    det = p.get("assessment_detail", {}) or {}
    delta = det.get("delta_vs_baseline")
    site_id = p.get("site", {}).get("site_id") or p.get("packet_id", "")
    tiers[tier] += 1
    conf_by_tier[(tier, conf)] += 1
    if delta is None:
        refusals.append(site_id)
    lic = reg.loc[site_id, "licensee"] if site_id in reg.index else "?"
    rows.append(
        {"site_id": site_id, "licensee": lic, "tier": tier, "confidence": conf, "delta": delta}
    )

df = pd.DataFrame(rows)
print(f"packets: {len(packets)}")
print("\n== tier distribution ==")
for t, n in tiers.most_common():
    print(f"  {t}: {n}")
print("\n== tier x confidence ==")
for (t, c), n in sorted(conf_by_tier.items(), key=lambda x: (str(x[0][0]), str(x[0][1]))):
    print(f"  {t} / {c}: {n}")
print(f"\n== honest refusals (no delta): {len(refusals)} ==")
for s in refusals:
    print("  ", s)
print("\n== licensee breakdown ==")
print(
    df.groupby("licensee")
    .agg(
        sites=("site_id", "count"),
        detected=("tier", lambda s: (s == "detected").sum()),
        identified=("tier", lambda s: (s == "identified").sum()),
        refused=("delta", lambda s: s.isna().sum()),
        median_delta=("delta", "median"),
    )
    .round(3)
    .to_string()
)
df.drop(columns=["licensee"]).to_csv("ops/pilot02-results.csv", index=False)
print("\nwrote ops/pilot02-results.csv")
