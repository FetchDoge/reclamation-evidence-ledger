"""Imagery fetch: Sentinel-2 L2A chips per site via STAC.

Usage:
    python -m ledger.imagery fetch --sites pilots/pilot-01.txt \
        --start 2023-05-01 --end 2026-08-31 --out data/chips

For each pilot site: query the STAC API for Sentinel-2 L2A scenes intersecting
a 500 m buffer, growing-season only, cloud cover < 40% (pre-filter; the SCL
band does the honest masking later). For a bounded subset of scenes (evenly
spaced across the date range), download bands B04 (red), B08 (NIR),
B11 (SWIR), B02 (blue) and SCL via windowed rasterio reads over HTTP from the
STAC asset HREFs, crop to a 500 m buffer around the site centroid, and store
as GeoTIFFs. A per-site manifest records every source URL, the scene ID, the
SHA-256 of each written chip, the clear-pixel fraction, and any rejections.

Raw chips are evidence: never modified after download. Checksums are recorded
at write time.

TLS note: TLS verification is on by default. Some sandboxed networks
terminate TLS at an egress proxy whose CA GDAL's bundled OpenSSL does not
trust. Only there should an operator set LEDGER_TRUST_EGRESS_PROXY_TLS=1,
which sets GDAL_HTTP_UNSAFESSL so windowed reads work; packets built that way
carry a caveat saying so. No credentials or private data transit this path.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import time
from datetime import UTC, date, datetime
from pathlib import Path

import numpy as np
import rasterio
from pyproj import Transformer
from pystac_client import Client
from rasterio import Env
from rasterio.enums import Resampling
from rasterio.transform import from_bounds as transform_from_bounds
from rasterio.windows import bounds as window_bounds
from rasterio.windows import from_bounds

from .config import DEFAULT, Config
from .packet import sha256_file

# STAC asset keys (earth-search sentinel-2-l2a uses common band names).
BAND_ASSETS = {
    "red": "red",  # B04, 10 m
    "nir": "nir",  # B08, 10 m
    "swir": "swir16",  # B11, 20 m
    "blue": "blue",  # B02, 10 m
    "scl": "scl",  # scene classification, 20 m
}
SCALED_BANDS = {"red", "nir", "swir", "blue"}  # DN = reflectance * 10000

if DEFAULT.trust_egress_proxy_tls:
    os.environ.setdefault("GDAL_HTTP_UNSAFESSL", "YES")
os.environ.setdefault("GDAL_DISABLE_READDIR_ON_OPEN", "EMPTY_DIR")


def safe_site_id(site_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", site_id)


def query_scenes(lon: float, lat: float, start: date, end: date, cfg: Config = DEFAULT):
    """Return STAC items for the AOI. No downloading here — query is cheap."""
    client = Client.open(cfg.stac_url)
    # buffer is applied by the caller in metres; here we use a small bbox
    # (~0.01 deg ≈ 1.1 km) and crop precisely after download.
    bbox = [lon - 0.005, lat - 0.005, lon + 0.005, lat + 0.005]
    search = client.search(
        collections=[cfg.collection],
        bbox=bbox,
        datetime=f"{start.isoformat()}/{end.isoformat()}",
        query={"eo:cloud_cover": {"lt": 40}},
    )
    return list(search.items())


def growing_season_windows(year: int, cfg: Config = DEFAULT):
    months = cfg.growing_months
    return (date(year, min(months), 1), date(year, max(months), 28))


def select_scenes(items, max_scenes: int, growing_months):
    """Evenly spaced scenes across the date range, growing season only.

    Deduplicates to one scene per calendar date (keeps lowest cloud cover),
    then picks evenly spaced indices so the selection covers the full span.
    """
    dated = [i for i in items if i.datetime is not None and i.datetime.month in growing_months]
    by_date: dict[str, object] = {}
    for it in dated:
        d = it.datetime.date().isoformat()
        cur = by_date.get(d)
        cc = it.properties.get("eo:cloud_cover", 100)
        if cur is None or cc < cur.properties.get("eo:cloud_cover", 100):
            by_date[d] = it
    uniq = sorted(by_date.values(), key=lambda i: i.datetime)
    if len(uniq) <= max_scenes:
        return uniq
    idx = [round(j * (len(uniq) - 1) / (max_scenes - 1)) for j in range(max_scenes)]
    return [uniq[i] for i in sorted(set(idx))]


def read_chip(
    asset_href: str,
    lon: float,
    lat: float,
    buffer_m: float,
    out_hw: tuple[int, int] | None,
    resampling: Resampling,
):
    """Windowed read of one band over HTTP; returns (array, crs, transform, profile)."""
    with rasterio.open(asset_href) as ds:
        tr = Transformer.from_crs("EPSG:4326", ds.crs, always_xy=True)
        x, y = tr.transform(lon, lat)
        win = from_bounds(x - buffer_m, y - buffer_m, x + buffer_m, y + buffer_m, ds.transform)
        h = int(win.height) if out_hw is None else out_hw[0]
        w = int(win.width) if out_hw is None else out_hw[1]
        arr = ds.read(1, window=win, out_shape=(h, w), resampling=resampling)
        wb = window_bounds(win, ds.transform)  # west, south, east, north
        chip_transform = transform_from_bounds(wb[0], wb[1], wb[2], wb[3], w, h)
        return arr, ds.crs, chip_transform, (h, w)


def fetch_site_chips(
    site_id: str,
    lon: float,
    lat: float,
    start: date,
    end: date,
    out_dir: Path,
    max_scenes: int,
    cfg: Config = DEFAULT,
) -> dict:
    """Download chips for one site. Returns the site manifest dict."""
    site_dir = out_dir / safe_site_id(site_id)
    site_dir.mkdir(parents=True, exist_ok=True)

    # Incremental mode: never re-download a date we already have chips for.
    prior = None
    prior_path = site_dir / "manifest.json"
    if prior_path.exists():
        try:
            prior = json.loads(prior_path.read_text())
        except json.JSONDecodeError:
            prior = None
    have_dates = {s["date"] for s in (prior["scenes"] if prior else [])}

    items = query_scenes(lon, lat, start, end, cfg)
    scenes = [
        s
        for s in select_scenes(items, max_scenes, cfg.growing_months)
        if s.datetime.date().isoformat() not in have_dates
    ]

    manifest = {
        "site_id": site_id,
        "site_dir": safe_site_id(site_id),
        "longitude": lon,
        "latitude": lat,
        "query": {
            "stac_url": cfg.stac_url,
            "collection": cfg.collection,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "cloud_cover_lt": 40,
            "growing_months": list(cfg.growing_months),
            "candidates_found": len(items),
            "scenes_selected": len(scenes),
            "buffer_m": cfg.aoi_buffer_m,
        },
        "scenes": [],
        "rejections": [],
        "fetched_at": datetime.now(UTC).isoformat(),
    }

    with Env():
        for n, item in enumerate(scenes):
            scene_date = item.datetime.date().isoformat()
            missing = [b for b, a in BAND_ASSETS.items() if a not in item.assets]
            if missing:
                manifest["rejections"].append(
                    {
                        "scene_id": item.id,
                        "date": scene_date,
                        "reason": f"missing assets: {missing}",
                    }
                )
                continue
            try:
                chips = {}
                hw = None
                ref_crs = ref_tform = None
                for band, asset_key in BAND_ASSETS.items():
                    href = item.assets[asset_key].href
                    rs = Resampling.nearest if band == "scl" else Resampling.bilinear
                    arr, crs, tform, hw = read_chip(href, lon, lat, cfg.aoi_buffer_m, hw, rs)
                    if ref_crs is None:  # pin every chip to the red band's grid
                        ref_crs, ref_tform = crs, tform
                    chips[band] = arr
                    time.sleep(0.15)  # polite: breathe between band reads
                if chips["red"].size == 0 or not np.any(chips["red"] > 0):
                    raise ValueError("empty chip (AOI outside scene footprint?)")

                # SCL honesty check before writing anything.
                scl = chips["scl"].astype(np.int16)
                valid = scl != 0
                masked = np.isin(scl, list(cfg.scl_mask_values))
                clear = valid & ~masked
                clear_frac = float(clear.mean()) if clear.size else 0.0
                snow_frac = (
                    float(((scl == cfg.scl_snow_value) & valid).mean()) if clear.size else 0.0
                )

                if snow_frac > 0.5:
                    manifest["rejections"].append(
                        {
                            "scene_id": item.id,
                            "date": scene_date,
                            "reason": f"snow-covered scene (snow fraction {snow_frac:.0%})",
                        }
                    )
                    continue
                if clear_frac < cfg.min_clear_fraction:
                    manifest["rejections"].append(
                        {
                            "scene_id": item.id,
                            "date": scene_date,
                            "reason": (
                                f"cloud/shadow: clear fraction {clear_frac:.0%} "
                                f"< {cfg.min_clear_fraction:.0%}"
                            ),
                        }
                    )
                    continue

                scene_files = []
                stamp = item.datetime.strftime("%Y%m%d")
                for band, arr in chips.items():
                    fname = f"{stamp}_{band}.tif"
                    fpath = site_dir / fname
                    profile = {
                        "driver": "GTiff",
                        "height": hw[0],
                        "width": hw[1],
                        "count": 1,
                        "dtype": arr.dtype,
                        "crs": ref_crs,
                        "transform": ref_tform,
                        "compress": "deflate",
                        "tiled": True,
                    }
                    with rasterio.open(fpath, "w", **profile) as dst:
                        dst.write(arr, 1)
                    scene_files.append(
                        {
                            "band": band,
                            "asset_key": BAND_ASSETS[band],
                            "path": str(fpath),
                            "source_url": item.assets[BAND_ASSETS[band]].href,
                            "sha256": sha256_file(fpath),
                            "shape": [hw[0], hw[1]],
                            "scale_note": "DN = reflectance * 10000"
                            if band in SCALED_BANDS
                            else "SCL class codes",
                        }
                    )
                manifest["scenes"].append(
                    {
                        "scene_id": item.id,
                        "datetime": item.datetime.isoformat(),
                        "date": scene_date,
                        "cloud_cover": item.properties.get("eo:cloud_cover"),
                        "clear_pixel_fraction": round(clear_frac, 4),
                        "snow_pixel_fraction": round(snow_frac, 4),
                        "chips": scene_files,
                    }
                )
                print(f"    {scene_date} {item.id}: kept (clear {clear_frac:.0%})")
            except Exception as e:  # noqa: BLE001 — record, don't crash the run
                manifest["rejections"].append(
                    {
                        "scene_id": item.id,
                        "date": scene_date,
                        "reason": f"download/read failed: {type(e).__name__}: {e}",
                    }
                )
                print(f"    {scene_date} {item.id}: FAILED {type(e).__name__}: {e}")
            if n < len(scenes) - 1:
                time.sleep(1.0)  # polite: breathe between scenes

    manifest["new_scenes_kept"] = len(manifest["scenes"])
    manifest["new_scenes_rejected"] = len(manifest["rejections"])
    (site_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    if prior:
        # merge with the earlier run's manifest (incremental backfill)
        manifest["scenes"] = prior["scenes"] + manifest["scenes"]
        manifest["rejections"] = prior.get("rejections", []) + manifest["rejections"]
        manifest["query"]["candidates_found"] += prior["query"].get("candidates_found", 0)
        manifest["query"]["scenes_selected"] += prior["query"].get("scenes_selected", 0)
        (site_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
        print(f"    (merged with prior run: {len(prior['scenes'])} scenes kept earlier)")
    return manifest


def main() -> None:
    import pandas as pd

    ap = argparse.ArgumentParser(description="Fetch Sentinel-2 chips for pilot sites.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    f = sub.add_parser("fetch", help="query STAC and download windowed band chips")
    f.add_argument(
        "--sites", required=True, help="text file, one site_id per line (as in the registry)"
    )
    f.add_argument("--registry", default="data/sites.parquet")
    f.add_argument(
        "--geolocation",
        default=None,
        help="output of `ledger.geolocate resolve`: fetch at VERIFIED coordinates only; "
        "sites without a verified location are skipped (they stay not_assessable)",
    )
    f.add_argument("--start", default="2023-05-01")
    f.add_argument("--end", default="2026-08-31")
    f.add_argument("--out", default="data/chips")
    f.add_argument(
        "--max-scenes",
        type=int,
        default=10,
        help="max scenes per site, evenly spaced across the range",
    )
    args = ap.parse_args()

    wanted = [
        line.strip()
        for line in Path(args.sites).read_text().splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    sites = pd.read_parquet(args.registry)
    sites = sites[sites.site_id.isin(wanted)].copy()
    missing = set(wanted) - set(sites.site_id)
    if missing:
        print(f"WARNING: {len(missing)} site_ids not in registry: {sorted(missing)[:5]}")
    if args.geolocation:
        geo = pd.read_parquet(args.geolocation)
        ok = geo[geo.status == "verified"].set_index("site_id")
        skipped = sorted(set(sites.site_id) - set(ok.index))
        if skipped:
            print(f"SKIP {len(skipped)} sites without a verified location, e.g. {skipped[:3]}")
        sites = sites[sites.site_id.isin(ok.index)].copy()
        sites["latitude"] = sites.site_id.map(ok["latitude"])
        sites["longitude"] = sites.site_id.map(ok["longitude"])
    print(
        f"fetching chips for {len(sites)} sites "
        f"({args.start}..{args.end}, max {args.max_scenes}/site)"
    )

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)

    for _, row in sites.iterrows():
        print(f"  {row.site_id} ({row.longitude:.4f}, {row.latitude:.4f})")
        m = fetch_site_chips(
            str(row.site_id),
            float(row.longitude),
            float(row.latitude),
            start,
            end,
            out_dir,
            args.max_scenes,
        )
        kept = m.get("new_scenes_kept", len(m["scenes"]))
        rej = m.get("new_scenes_rejected", len(m["rejections"]))
        print(
            f"    -> {kept} scenes kept, {rej} rejected; "
            f"manifest: {out_dir / safe_site_id(str(row.site_id)) / 'manifest.json'}"
        )


if __name__ == "__main__":
    main()
