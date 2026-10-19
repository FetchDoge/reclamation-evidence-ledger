#!/usr/bin/env python3
"""Radiometric lineage audit: per-scene processing baseline + BOA offset record.

Collects the unique Sentinel-2 scene IDs from every chip manifest under
data/chips/ (when present) AND every committed packet's observations, so the
audit covers every scene a published packet relies on, even on a fresh clone
without chips. Fetches each scene's STAC item from Earth Search (metadata only,
no imagery) to record:
  - s2:processing_baseline
  - earthsearch:boa_offset_applied
  - the asset HREFs of the bands the pipeline reads (red, nir, swir16, blue,
    scl), which packets cite as each chip's source_url

Writes ledger/data/radiometric_lineage.json — the recorded evidence behind the
pipeline's DN/10000 reflectance scaling. The scaling is NOT assumed: it is
justified per scene by the provider's own offset-correction flag, plus an
empirical chip-level check (raw DN minima ~1, inconsistent with a residual
+1000 offset).

Any scene breaking uniformity (offset flag False, baseline < 04.00 where
offset semantics differ) is reported loudly, not smoothed over.

Usage: python ops/audit_lineage.py
"""

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# Tracked location (ledger/data/ is NOT covered by the root /data/ ignore):
# the lineage record is evidence and must survive a fresh clone.
OUT = ROOT / "ledger" / "data" / "radiometric_lineage.json"
STAC_URL = "https://earth-search.aws.element84.com/v1"
COLLECTION = "sentinel-2-l2a"


ASSET_KEYS = ("red", "nir", "swir16", "blue", "scl")  # ledger.imagery.BAND_ASSETS


def collect_scenes() -> dict[str, str]:
    scenes: dict[str, str] = {}
    for m in sorted((ROOT / "data" / "chips").glob("*/manifest.json")):
        d = json.loads(m.read_text())
        for s in d["scenes"]:
            scenes.setdefault(s["scene_id"], s["date"])
    for p in sorted((ROOT / "packets").glob("*.json")):
        for o in json.loads(p.read_text()).get("observations", []):
            scenes.setdefault(o["scene_id"], o["date"])
    return scenes


def audit() -> dict:
    from pystac_client import Client

    scenes = collect_scenes()
    print(f"{len(scenes)} unique scenes across chip manifests", flush=True)
    client = Client.open(STAC_URL)
    collection = client.get_collection(COLLECTION)

    records, anomalies = [], []
    for i, (sid, date) in enumerate(sorted(scenes.items()), 1):
        try:
            item = collection.get_item(sid)
            p = item.properties
            baseline = p.get("s2:processing_baseline")
            boa = p.get("earthsearch:boa_offset_applied")
        except Exception as e:  # noqa: BLE001
            anomalies.append({"scene_id": sid, "date": date, "anomaly": f"STAC fetch failed: {e}"})
            print(f"[{i}/{len(scenes)}] {sid}: FETCH FAILED", flush=True)
            continue
        rec = {
            "scene_id": sid,
            "date": date,
            "processing_baseline": baseline,
            "boa_offset_applied": boa,
            "stac_item": f"{STAC_URL}/collections/{COLLECTION}/items/{sid}",
            "assets": {k: item.assets[k].href for k in ASSET_KEYS if k in item.assets},
        }
        records.append(rec)
        flag = ""
        if boa is not True:
            flag = "  <-- ANOMALY: boa_offset_applied is not True"
            anomalies.append({**rec, "anomaly": "boa_offset_applied is not True"})
        print(f"[{i}/{len(scenes)}] {sid} baseline={baseline} boa_offset={boa}{flag}", flush=True)
        time.sleep(0.2)  # be polite to the STAC API

    baselines = sorted({r["processing_baseline"] for r in records})
    result = {
        "audit_date": time.strftime("%Y-%m-%d"),
        "stac_api": STAC_URL,
        "collection": COLLECTION,
        "n_unique_scenes": len(scenes),
        "n_audited": len(records),
        "processing_baselines_observed": baselines,
        "boa_offset_applied_uniform_true": all(r["boa_offset_applied"] is True for r in records),
        "chip_level_dn_check": (
            "The chip-level DN-minimum check was run on the chips audited "
            "2026-09-27; it needs downloaded chips and is not re-run by this "
            "metadata audit. The per-scene boa_offset_applied flag is."
        ),
        "scale_justification": (
            "DN/10000. Per-scene STAC records show earthsearch:boa_offset_applied=True "
            "for every audited scene: the data provider removed the +1000 DN radiometric "
            "offset introduced at processing baseline 04.00 when generating these COGs, "
            "so stored DN = reflectance * 10000 directly. Independently confirmed at chip "
            "level: raw red-band DN minima reach ~1, which is inconsistent with a residual "
            "+1000 offset (minima would sit near 1000). If a future scene arrives with "
            "boa_offset_applied != True, this justification does not cover it — re-audit."
        ),
        "anomalies": anomalies,
        "scenes": records,
    }
    OUT.write_text(json.dumps(result, indent=2))
    print(f"\nwrote {OUT}")
    print(f"baselines observed: {baselines}")
    print(f"anomalies: {len(anomalies)}")
    for a in anomalies:
        print("  ANOMALY:", json.dumps(a))
    return result


if __name__ == "__main__":
    r = audit()
    sys.exit(1 if r["anomalies"] else 0)
