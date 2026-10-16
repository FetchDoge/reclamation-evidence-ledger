"""Change assessment: baseline diffs and claim-tier assignment.

The core interpretive rule, from imagery tradecraft:

    detection    — something changed vs the baseline (a measured delta)
    identified   — the change is consistent with a reclamation signal
                   across multiple observations (a hypothesis)
    attributed   — a named party is responsible (NEVER emitted by code;
                   requires human review and ground truth)
    not_assessable — the screen declines to make a claim (unverified
                   location, too few matched months, ...). First-class result,
                   never a failure and never counted against a site.

The pipeline's job ends at "identified", and only with caveats attached.
"""

from __future__ import annotations

from dataclasses import dataclass

from .config import DEFAULT, Config

# Bootstrap CIs over matched-month deltas are degenerate below this many
# matched months (with n=2 the resampled-median distribution has only 3
# distinct values: the interval looks precise and means almost nothing).
# Below the threshold we report NO interval rather than a misleading one.
MIN_MATCHED_MONTHS_FOR_CI = 4


@dataclass
class Assessment:
    site_id: str
    period: str  # e.g. "2026 growing season"
    baseline_ndvi: float  # median of per-month baseline medians (context only)
    delta_std: float  # std dev of the matched-month DELTAS — NOT baseline
    # variation. Named for what it is: spread of the
    # month-for-month differences the delta summarizes.
    current_ndvi: float  # median of per-month current medians (context only)
    delta: float
    delta_ci95: list | None  # [lo, hi]: bootstrap 95% CI on the median
    # matched-month delta (1000 resamples, fixed
    # seed); None when len(matched_months) < 4 —
    # an interval there would be degenerate, not wide
    n_baseline_obs: int
    n_current_obs: int
    matched_months: list  # calendar months compared month-for-month
    tier: str  # "detected" | "identified" (not_assessable is decided in cmd_assess)
    statement: str
    rationale: str
    caveats: list
    confidence: str  # "low" | "medium" | "high" (evidence-volume heuristic)


def assess(
    site_id: str,
    baseline_monthly: dict[int, list[float]],
    current_monthly: dict[int, list[float]],
    period: str,
    cfg: Config = DEFAULT,
) -> Assessment:
    """Month-matched baseline diff.

    baseline_monthly / current_monthly map calendar month -> list of scene
    NDVI means for that month. Deltas are computed per matched month and the
    median of those deltas is the signal, so a baseline sampled in May/June
    is never compared against a current period sampled in July. This is the
    fix for phenology bias: greenness follows the calendar, not the project.
    """
    import numpy as np

    matched = sorted(set(baseline_monthly) & set(current_monthly))
    if len(matched) < 2:
        raise ValueError(
            f"{site_id}: need >=2 month-matched baseline/current months, got {matched}"
        )
    month_deltas = []
    n_base = n_cur = 0
    for m in matched:
        b = float(np.median(baseline_monthly[m]))
        c = float(np.median(current_monthly[m]))
        month_deltas.append(c - b)
        n_base += len(baseline_monthly[m])
        n_cur += len(current_monthly[m])

    base = float(np.median([float(np.median(baseline_monthly[m])) for m in matched]))
    current = float(np.median([float(np.median(current_monthly[m])) for m in matched]))
    delta = float(np.median(month_deltas))
    std = float(np.std(month_deltas)) if len(month_deltas) > 2 else 0.0

    # Real uncertainty: bootstrap 95% CI on the median matched-month delta.
    # 1000 resamples over the matched-month deltas, fixed seed so packets are
    # reproducible. With few matched months this interval is DEGENERATE, not
    # wide: at n=2 the resampled-median distribution has only 3 distinct
    # values, so the interval looks precise and means almost nothing. Below
    # MIN_MATCHED_MONTHS_FOR_CI we refuse to report one — a missing interval
    # is the honest statement of how much we know.
    if len(matched) >= MIN_MATCHED_MONTHS_FOR_CI:
        rng = np.random.default_rng(20260927)
        d = np.asarray(month_deltas, dtype=float)
        boots = [float(np.median(rng.choice(d, size=d.size, replace=True))) for _ in range(1000)]
        ci_lo, ci_hi = float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))
        ci = [round(ci_lo, 4), round(ci_hi, 4)]
        ci_txt = f"95% CI [{ci_lo:+.3f}, {ci_hi:+.3f}]"
        ci_caveat = f"Uncertainty is a bootstrap 95% CI over {len(matched)} matched-month deltas."
    else:
        ci = None
        ci_txt = (
            f"interval not estimated (only {len(matched)} matched months; "
            f"a bootstrap CI needs >= {MIN_MATCHED_MONTHS_FOR_CI})"
        )
        ci_caveat = (
            f"No uncertainty interval is reported: {len(matched)} "
            f"matched months is below the {MIN_MATCHED_MONTHS_FOR_CI} "
            "needed for a non-degenerate bootstrap CI. The delta "
            "below is a point estimate only."
        )

    caveats = [
        "10 m pixels cannot resolve wellheads; this is a vegetation screen, not a compliance verdict.",
        "Drought years depress NDVI independent of reclamation progress.",
        "Baseline and current periods are compared month-for-month "
        f"(matched months: {matched}) to avoid seasonal sampling bias.",
        ci_caveat,
    ]

    if delta >= cfg.ndvi_recover_delta:
        tier, statement = "identified", "vegetation recovering"
        rationale = (
            f"Median matched-month NDVI delta {delta:+.2f} (median of "
            f"{len(matched)} matched-month deltas; baseline median "
            f"{base:.2f}, current median {current:.2f}; {ci_txt})."
        )
    elif delta <= cfg.ndvi_stall_delta:
        tier, statement = "identified", "vegetation stalled or regressing"
        rationale = (
            f"Median matched-month NDVI delta {delta:+.2f} (median of "
            f"{len(matched)} matched-month deltas; baseline median "
            f"{base:.2f}, current median {current:.2f}; {ci_txt})."
        )
    else:
        tier, statement = "detected", "no significant change vs baseline"
        rationale = (
            f"Median matched-month delta {delta:+.2f} is within the noise band "
            f"(±{max(cfg.ndvi_recover_delta, abs(cfg.ndvi_stall_delta)):.2f}; "
            f"baseline median {base:.2f}, current median {current:.2f}; {ci_txt})."
        )
    # The delta is the median of per-month deltas, NOT the difference of the
    # two displayed medians (median of differences != difference of medians).
    # The rationale states all three numbers so the relationship is exact by
    # construction: nothing is implied to subtract.

    # Confidence scales with evidence volume, never with enthusiasm.
    n = n_base + n_cur
    confidence = "high" if n >= 24 else "medium" if n >= 12 else "low"

    return Assessment(
        site_id=site_id,
        period=period,
        baseline_ndvi=round(base, 4),
        delta_std=round(std, 4),
        current_ndvi=round(current, 4),
        delta=round(delta, 4),
        delta_ci95=ci,
        n_baseline_obs=n_base,
        n_current_obs=n_cur,
        matched_months=matched,
        tier=tier,
        statement=statement,
        rationale=rationale,
        caveats=caveats,
        confidence=confidence,
    )


# ---------------------------------------------------------------------------
# CLI: assess chips on disk and build a schema-validated evidence packet.
#
#     python -m ledger.change assess --site <site_id> \
#         --chips data/chips/<safe_id> \
#         --baseline-start 2023 --baseline-end 2024 --assessment 2025-2026
# ---------------------------------------------------------------------------

OWA_INVENTORY_URL = "https://www.orphanwell.ca/inventory/site-specific-inventory"
OWA_INVENTORY_MONTH = "2026-09-01"  # file month of the inventory used; recheck live
EARTH_SEARCH_URL = "https://earth-search.aws.element84.com/v1"
COPERNICUS_URL = "https://sentiwiki.copernicus.eu/"


def _parse_years(spec: str) -> list[int]:
    spec = spec.strip()
    if "," in spec:
        return sorted({int(y) for y in spec.split(",") if y.strip()})
    if "-" in spec:
        a, b = spec.split("-", 1)
        return list(range(int(a), int(b) + 1))
    return [int(spec)]


def _scene_means(chips_dir, cfg: Config = DEFAULT):
    """Per-scene index means from chip GeoTIFFs. Returns (scenes, manifest)."""
    import json

    import numpy as np
    import rasterio

    from . import indices

    manifest = json.loads((chips_dir / "manifest.json").read_text())
    scene_by_stamp = {s["date"].replace("-", ""): s for s in manifest["scenes"]}
    out = []
    for f in sorted(chips_dir.glob("*_red.tif")):
        stamp = f.name.split("_")[0]
        sc = scene_by_stamp.get(stamp)
        if sc is None:
            continue
        bands = {}
        for band in ("red", "nir", "swir", "blue", "scl"):
            p = chips_dir / f"{stamp}_{band}.tif"
            with rasterio.open(p) as ds:
                bands[band] = ds.read(1)
        refl = {b: bands[b].astype(float) / 10000.0 for b in ("red", "nir", "swir", "blue")}
        scl = bands["scl"].astype(np.int16)
        clear = (scl != 0) & ~np.isin(scl, list(cfg.scl_mask_values))
        clear &= bands["red"] > 0  # nodata guard
        out.append(
            {
                "date": sc["date"],
                "scene_id": sc["scene_id"],
                "ndvi_mean": indices.mean_or_nan(indices.ndvi(refl["nir"], refl["red"], clear)),
                "ndmi_mean": indices.mean_or_nan(indices.ndmi(refl["nir"], refl["swir"], clear)),
                "bare_soil_mean": indices.mean_or_nan(
                    indices.bare_soil_index(
                        refl["swir"], refl["red"], refl["nir"], refl["blue"], clear
                    )
                ),
                "savi_mean": indices.mean_or_nan(indices.savi(refl["nir"], refl["red"], clear)),
                "msavi_mean": indices.mean_or_nan(indices.msavi(refl["nir"], refl["red"], clear)),
                "clear_pixel_fraction": round(indices.clear_fraction(clear), 4),
            }
        )
    return out, manifest


def _monthly_medians(scenes: list[dict], years: list[int]) -> dict[int, list[float]]:
    """Scene NDVI means grouped by calendar month (month-matched comparison)."""
    out: dict[int, list[float]] = {}
    for s in scenes:
        y, m = int(s["date"][:4]), int(s["date"][5:7])
        if y in years and s["ndvi_mean"] is not None:
            out.setdefault(m, []).append(s["ndvi_mean"])
    return out


def _location_block(loc: dict) -> dict:
    return {
        "status": loc["status"],
        "source": loc["source"],
        "method": loc["method"],
        "uncertainty_m": loc["uncertainty_m"],
        "flags": list(loc.get("flags") or []),
    }


def _write_not_assessable(args, r, loc, reasons, period):
    """Write a schema-valid packet whose tier is not_assessable (first-class result)."""
    from datetime import date as date_cls

    from .packet import build_packet, write_packet

    if loc is None:
        loc = {
            "status": "unverified",
            "source": "none",
            "method": "location unverified: no geolocation record for this site",
            "uncertainty_m": None,
            "flags": [],
            "latitude": float(r["latitude"]),
            "longitude": float(r["longitude"]),
        }
    unverified = loc["status"] != "verified"
    site_block = {
        "site_id": str(r["site_id"]),
        "name": str(r["name"]),
        "latitude": float(loc["latitude"] if loc["latitude"] is not None else r["latitude"]),
        "longitude": float(loc["longitude"] if loc["longitude"] is not None else r["longitude"]),
        "owa_stage": str(r["owa_stage"]),
        "owa_inventory_date": OWA_INVENTORY_MONTH,
        "location": _location_block(loc),
    }
    statement = "not assessable"
    rationale = (
        "The screen declines to make a claim for this site. Reasons: "
        + "; ".join(reasons)
        + ". This is a statement about what the screen can support, not about the "
        "condition of the land."
    )
    caveats = [
        "Not assessable is a normal, first-class result of this screen; it is not a finding about the site or its licensee.",
        "This screen never certifies reclamation and is not a compliance determination.",
    ]
    if unverified:
        caveats.append(
            "Published coordinates are the legacy approximation (median error ~2.7 km, "
            "NEGATIVE-RESULT-2026-10-09.md); they do not locate the well. No imagery "
            "from this location may be read as evidence about the site."
        )
    packet = build_packet(
        site=site_block,
        assessment={
            "tier": "not_assessable",
            "statement": statement,
            "rationale": rationale,
            "confidence": "low",
            "period": period,
            "caveats": caveats,
            "not_assessable_reasons": reasons,
        },
        observations=[],
        chips=[],
        transforms=[
            {
                "step": "location_gate",
                "tool": "ledger.geolocate.location_gate",
                "parameters": {
                    "status": loc["status"],
                    "source": loc["source"],
                    "flags": list(loc.get("flags") or []),
                    "reasons": reasons,
                },
            }
        ],
        sources=[
            {
                "name": "OWA site-specific inventory (Excel)",
                "url": OWA_INVENTORY_URL,
                "accessed": date_cls.today().isoformat(),
                "license_note": "public data",
            }
        ],
    )
    out = write_packet(packet, args.out)
    print(f"{args.site}: NOT_ASSESSABLE — {'; '.join(reasons)}")
    print(f"  packet: {out}")
    return out


def cmd_assess(args):
    from datetime import date as date_cls
    from pathlib import Path

    import pandas as pd

    from .geolocate import haversine_m, load_location, location_gate
    from .packet import build_packet, write_packet

    chips_dir = Path(args.chips)

    baseline_years = list(range(args.baseline_start, args.baseline_end + 1))
    current_years = _parse_years(args.assessment)
    period = (
        f"{min(current_years)}-{max(current_years)} growing seasons"
        if len(current_years) > 1
        else f"{current_years[0]} growing season"
    )

    registry = pd.read_parquet(args.registry)
    row = registry[registry.site_id == args.site]
    if len(row) == 0:
        raise SystemExit(f"site {args.site} not found in {args.registry}")
    r = row.iloc[0]

    # --- Location gate (ledger.geolocate): nothing above not_assessable unless
    # the site's coordinates were verified AND the chips were fetched there.
    geo_path = Path(args.geolocation)
    loc = load_location(geo_path, args.site) if geo_path.exists() else None
    loc_ok, na_reasons = location_gate(loc)
    scenes, manifest = [], None
    if chips_dir.is_dir():
        try:
            scenes, manifest = _scene_means(chips_dir)
        except Exception:  # noqa: BLE001 - no usable chips is itself a reason
            scenes, manifest = [], None
    if loc_ok and manifest is not None:
        mlat, mlon = manifest.get("latitude"), manifest.get("longitude")
        if mlat is None or mlon is None:
            loc_ok = False
            na_reasons = ["chips_location_unrecorded_in_manifest"]
        else:
            off = haversine_m(loc["latitude"], loc["longitude"], float(mlat), float(mlon))
            if off > 50.0:
                loc_ok = False
                na_reasons = [f"chips_not_at_verified_location:{off:.0f}m_from_verified_point"]
    a = None
    if loc_ok:
        if not scenes:
            raise SystemExit(f"no usable scenes in {chips_dir}")
        base_monthly = _monthly_medians(scenes, baseline_years)
        cur_monthly = _monthly_medians(scenes, current_years)
        try:
            a = assess(args.site, base_monthly, cur_monthly, period)
        except ValueError as e:
            na_reasons = [f"insufficient_matched_months: {e}"]
    if a is None:
        return _write_not_assessable(args, r, loc, na_reasons, period)

    observations = [
        {
            "date": s["date"],
            "scene_id": s["scene_id"],
            "ndvi_mean": s["ndvi_mean"],
            "ndmi_mean": s["ndmi_mean"],
            "bare_soil_mean": s["bare_soil_mean"],
            "savi_mean": s["savi_mean"],
            "msavi_mean": s["msavi_mean"],
            "clear_pixel_fraction": s["clear_pixel_fraction"],
        }
        for s in scenes
    ]
    chips = []
    for sc in manifest["scenes"]:
        for c in sc["chips"]:
            chips.append(
                {"date": sc["date"], "path": c["path"], "sha256": c["sha256"], "bands": [c["band"]]}
            )

    transforms = [
        {"step": "stac_scene_query", "tool": "pystac-client", "parameters": manifest["query"]},
        {
            "step": "chip_download_windowed",
            "tool": "rasterio windowed read over HTTPS (/vsicurl)",
            "parameters": {
                "buffer_m": 500.0,
                "bands": ["B04", "B08", "B11", "B02", "SCL"],
                "resampling": {"10m": "bilinear", "SCL": "nearest"},
                "reference_grid": "red band (10 m)",
                "note": "chips stored as written; DN = reflectance*10000",
            },
        },
        {
            "step": "cloud_mask",
            "tool": "Sentinel-2 SCL classification",
            "parameters": {
                "masked_classes": list(DEFAULT.scl_mask_values),
                "min_clear_fraction": DEFAULT.min_clear_fraction,
                "rejected_scenes": manifest["rejections"],
            },
        },
        {
            "step": "index_computation",
            "tool": "ledger.indices (numpy)",
            "parameters": {
                "ndvi": "(nir-red)/(nir+red)",
                "ndmi": "(nir-swir)/(nir+swir)",
                "bare_soil": "((swir+red)-(nir+blue))/((swir+red)+(nir+blue))",
                "savi": "((nir-red)*(1+L))/(nir+red+L), L=0.5 "
                "(soil-adjusted; supporting evidence only)",
                "msavi": "(2*nir+1-sqrt((2*nir+1)^2-8*(nir-red)))/2 "
                "(self-adjusting; supporting evidence only)",
                "primary_signal": "ndvi",
                "scale": "DN/10000",
                "scale_justification": "ledger/data/radiometric_lineage.json: "
                "per-scene STAC audit (processing baseline + "
                "earthsearch:boa_offset_applied per scene); the data "
                "provider removed the PB>=04.00 +1000 DN offset when "
                "generating these COGs, confirmed by chip-level DN "
                "minima ~1. Not assumed — recorded.",
                "mask": "clear pixels only",
            },
        },
        {
            "step": "baseline_assessment",
            "tool": "ledger.change.assess",
            "parameters": {
                "baseline_years": baseline_years,
                "assessment_years": current_years,
                "seasonal_aggregation": "month-matched median deltas "
                "(each calendar month compared only to itself)",
                "recover_delta": DEFAULT.ndvi_recover_delta,
                "stall_delta": DEFAULT.ndvi_stall_delta,
            },
        },
        {
            "step": "packet_build",
            "tool": "ledger.packet.build_packet",
            "parameters": {"schema_version": "1.2.0"},
        },
    ]
    sources = [
        {
            "name": "OWA site-specific inventory (Excel)",
            "url": OWA_INVENTORY_URL,
            "accessed": date_cls.today().isoformat(),
            "license_note": "public data; inventory file month 2026-09-01, recheck live",
        },
        {
            "name": "Element 84 Earth Search STAC (Sentinel-2 L2A)",
            "url": EARTH_SEARCH_URL,
            "accessed": date_cls.today().isoformat(),
        },
        {
            "name": "Copernicus Sentinel-2 (ESA)",
            "url": COPERNICUS_URL,
            "accessed": date_cls.today().isoformat(),
            "license_note": "Contains modified Copernicus Sentinel data.",
        },
    ]
    caveats = list(a.caveats) + [
        f"Site coordinates: {loc['source']} ({loc['method']}); nominal uncertainty "
        f"{loc['uncertainty_m']:.0f} m. This pins the licensed surface hole, not the "
        "visible pad footprint.",
        "Sentinel-2's 10 m pixels cannot resolve individual wellheads.",
        "Chip download used GDAL_HTTP_UNSAFESSL on a TLS-intercepting egress "
        "proxy; payload integrity rests on S3-hosted COGs, not TLS pinning.",
    ]

    packet = build_packet(
        site={
            "site_id": str(r["site_id"]),
            "name": str(r["name"]),
            "latitude": float(loc["latitude"]),
            "longitude": float(loc["longitude"]),
            "owa_stage": str(r["owa_stage"]),
            "owa_inventory_date": OWA_INVENTORY_MONTH,
            "location": _location_block(loc),
        },
        assessment={
            "tier": a.tier,
            "statement": a.statement,
            "rationale": a.rationale,
            "confidence": a.confidence,
            "period": period,
            "caveats": caveats,
        },
        observations=observations,
        chips=chips,
        transforms=transforms,
        sources=sources,
    )
    packet["claim"]["caveats"] = caveats
    packet["baseline"] = {
        "period": f"{baseline_years[0]}-{baseline_years[-1]}",
        "ndvi_median": a.baseline_ndvi,
        "n_scene_observations": a.n_baseline_obs,
    }
    packet["assessment_detail"] = {
        "period": period,
        "ndvi_median": a.current_ndvi,
        "n_scene_observations": a.n_current_obs,
        "delta_vs_baseline": a.delta,
        "delta_std": a.delta_std,
        # Median of per-month deltas != difference of the displayed medians.
        # Stated here so no reader has to discover it by subtraction.
        "delta_method_note": (
            "delta_vs_baseline is the median of per-month "
            "(current-median minus baseline-median) deltas over matched "
            "months; it is not the difference of baseline.ndvi_median and "
            "assessment_detail.ndvi_median."
        ),
        "matched_months": a.matched_months,
    }
    if a.delta_ci95 is not None:
        # Omitted (not null) below MIN_MATCHED_MONTHS_FOR_CI matched months:
        # the schema keeps the field optional so absence is the honest signal.
        packet["assessment_detail"]["delta_ci95"] = a.delta_ci95

    out = write_packet(packet, args.out)
    print(
        f"{args.site}: {a.tier.upper()} — {a.statement} "
        f"(delta {a.delta:+.3f} = median of {len(a.matched_months)} matched-month deltas; "
        f"baseline median {a.baseline_ndvi:.3f}, current median {a.current_ndvi:.3f}, "
        f"confidence {a.confidence})"
    )
    print(f"  packet: {out}")
    return out


def main() -> None:
    import argparse

    ap = argparse.ArgumentParser(description="Change assessment and packet builder.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("assess", help="assess chips and build an evidence packet")
    a.add_argument("--site", required=True, help="site_id as in the registry")
    a.add_argument("--chips", required=True, help="data/chips/<safe site dir>")
    a.add_argument("--registry", default="data/sites.parquet")
    a.add_argument(
        "--geolocation",
        default="data/geolocation.parquet",
        help="output of `python -m ledger.geolocate resolve`; without a verified "
        "record the site is not_assessable",
    )
    a.add_argument("--baseline-start", type=int, default=2023)
    a.add_argument("--baseline-end", type=int, default=2024)
    a.add_argument(
        "--assessment", default="2025-2026", help="'2025-2026' range or '2025,2026' list"
    )
    a.add_argument("--out", default="packets")
    args = ap.parse_args()
    if args.cmd == "assess":
        cmd_assess(args)


if __name__ == "__main__":
    main()
