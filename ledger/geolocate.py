"""Verified pad geolocation: the gate in front of every claim tier.

Why this exists: the DLS-centroid geocoder in ``ledger.sites`` was measured
2026-10-09 to be a median ~2.4-2.7 km from the real wells, so the first 99
packets measured land that does not contain the well
(NEGATIVE-RESULT-2026-10-09.md). The OWA inventory ships NO coordinates.

What actually exists (checked 2026-10-16, see ops/results/geolocation-audit-*):
  * AER ST37 "List of Wells in Alberta" (free, monthly; Excel/Shapefile/GDB)
    carries licensee-reported surface-hole latitude/longitude per well
    licence, plus a licence surface-location label. The OWA inventory carries
    the licence number, so the two join on it.
  * The OWA inventory itself: licence number + DLS site name, no coordinates.
  * The DLS LSD centroid (legacy): kept ONLY as a recorded, withdrawn fallback.
  * Optional extra sources (e.g. a hand-digitized pad, ABMI Human Footprint
    polygons if their licence allows) can be passed as CSV to cross-check.

Rules (enforced here, and re-enforced in ledger.change and the schema):
  * A site is "verified" only when an authoritative coordinate was joined by
    licence number AND its surface-location label agrees with the OWA site
    name at section/township/range level AND no other source disagrees.
  * Otherwise the site is "unverified" and the pipeline may emit nothing
    above the "not_assessable" tier.
  * The DLS centroid never verifies a site.

    python -m ledger.geolocate resolve --owa OWA.xlsx --st37 ST_37_Excel.zip \
        --sites pilots/pilot-02.txt --out data/geolocation.parquet
    python -m ledger.geolocate audit --geolocation data/geolocation.parquet --out-dir ops/results
"""

from __future__ import annotations

import argparse
import io
import json
import math
import re
import urllib.request
import zipfile
from dataclasses import asdict, dataclass, field
from pathlib import Path

import pandas as pd

from .sites import dls_to_latlon, load_owa, parse_dls, read_owa_raw

ST37_URL = "https://www.aer.ca/prd/documents/sts/st37/ST_37_Excel.zip"
ST37_PAGE = "https://www.aer.ca/data-and-performance-reports/statistical-reports/st37"

# Configured, not measured: nominal 1-sigma-ish bound on "surface-hole point vs
# pad", chosen as a conservative round-up of the largest point-to-footprint-centre
# offset seen in the 2026-10-08 pad diagnosis (87 m, 40 well points vs ABMI HFI).
ST37_NOMINAL_UNCERTAINTY_M = 100.0
# Legacy DLS centroid: median error measured at 2,658 m over 20,000 wells.
DLS_LEGACY_UNCERTAINTY_M = 2700.0
# Two sources that should agree must be within this distance or the site is
# flagged and left unverified.
DISAGREE_M = 250.0

ALBERTA_BOUNDS = (49.0, 60.0, -120.0, -110.0)  # lat_min, lat_max, lon_min, lon_max

SOURCE_ST37 = "AER ST37 surface hole (licence join)"
SOURCE_DLS = "DLS LSD centroid (legacy, withdrawn)"

_LABEL_RE = re.compile(r"^(\d{1,2})-(\d{1,2})-(\d{1,3})-(\d{1,2})W([456])\b")


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371008.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = (
        math.sin((p2 - p1) / 2) ** 2
        + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    )
    return 2 * r * math.asin(math.sqrt(a))


def norm_licence(x: object) -> str:
    s = re.sub(r"\D", "", str(x or ""))
    return s.zfill(7) if s else ""


@dataclass
class Candidate:
    source: str
    method: str
    latitude: float
    longitude: float
    uncertainty_m: float
    authoritative: bool


@dataclass
class Location:
    site_id: str
    status: str  # "verified" | "unverified"
    latitude: float | None
    longitude: float | None
    source: str
    method: str
    uncertainty_m: float | None
    flags: list[str] = field(default_factory=list)
    candidates: list[dict] = field(default_factory=list)
    legacy_latitude: float | None = None
    legacy_longitude: float | None = None
    legacy_offset_m: float | None = None

    @property
    def verified(self) -> bool:
        return self.status == "verified"

    def as_site_block(self) -> dict:
        """The ``site.location`` object stored in packets."""
        return {
            "status": self.status,
            "source": self.source,
            "method": self.method,
            "uncertainty_m": self.uncertainty_m,
            "flags": list(self.flags),
        }


# ---------------------------------------------------------------- ST37 ----
def download_st37(dest: str | Path, url: str = ST37_URL) -> Path:
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=300) as r, open(dest, "wb") as f:
        f.write(r.read())
    return dest


_ST37_COLS = [
    "Well_Licence_Number",
    "Licence_Status",
    "SH_Actual_Latitude",
    "SH_Actual_Longitude",
    "Licence_Surface_Location_Label",
]


def load_st37(path: str | Path) -> pd.DataFrame:
    """Load ST37 surface holes from the AER zip, ST37_SH.xlsx, a parquet or a csv.

    Returns one row per normalized licence number with the columns in _ST37_COLS.
    """
    p = Path(path)
    if p.suffix == ".parquet":
        df = pd.read_parquet(p)
    elif p.suffix == ".csv":
        df = pd.read_csv(p, dtype=str)
    elif p.suffix == ".zip":
        with zipfile.ZipFile(p) as z:
            name = next(n for n in z.namelist() if n.endswith("ST37_SH.xlsx"))
            df = pd.read_excel(io.BytesIO(z.read(name)), dtype=str)
    else:
        df = pd.read_excel(p, dtype=str)
    missing = [c for c in _ST37_COLS if c not in df.columns]
    if missing:
        raise ValueError(f"ST37 file lacks expected columns {missing}")
    df = df[_ST37_COLS].copy()
    df["licence"] = df["Well_Licence_Number"].map(norm_licence)
    df["SH_Actual_Latitude"] = pd.to_numeric(df["SH_Actual_Latitude"], errors="coerce")
    df["SH_Actual_Longitude"] = pd.to_numeric(df["SH_Actual_Longitude"], errors="coerce")
    return df.drop_duplicates("licence").set_index("licence")


# ------------------------------------------------------------ resolving ----
def _label_key(label: object) -> tuple[int, int, int, str, int] | None:
    m = _LABEL_RE.match(str(label or "").strip())
    if not m:
        return None
    lsd, sec, twp, rng, mer = int(m[1]), int(m[2]), int(m[3]), int(m[4]), m[5]
    return (sec, twp, rng, mer, lsd)


def _in_alberta(lat: float, lon: float) -> bool:
    return (
        ALBERTA_BOUNDS[0] <= lat <= ALBERTA_BOUNDS[1]
        and ALBERTA_BOUNDS[2] <= lon <= ALBERTA_BOUNDS[3]
    )


def resolve_site(
    site_id: str,
    licence: object,
    component_type: object,
    st37: pd.DataFrame,
    extras: list[Candidate] | None = None,
    disagree_m: float = DISAGREE_M,
) -> Location:
    """Pin one OWA site, or refuse it. Never raises for data problems."""
    flags: list[str] = []
    cands: list[Candidate] = []
    dls = parse_dls(site_id)

    legacy = None
    if dls is not None:
        la, lo = dls_to_latlon(*dls)
        legacy = Candidate(
            SOURCE_DLS,
            "LSD centroid, road allowances ignored",
            la,
            lo,
            DLS_LEGACY_UNCERTAINTY_M,
            authoritative=False,
        )
        cands.append(legacy)
    else:
        flags.append("site_name_not_dls_parsable")

    st_cand = None
    lic = norm_licence(licence)
    comp = str(component_type or "")
    if not lic:
        flags.append("no_licence_number")
    elif "well" not in comp.lower():
        flags.append(f"component_not_a_well:{comp or 'blank'}")
    elif lic not in st37.index:
        flags.append("licence_not_in_st37")
    else:
        row = st37.loc[lic]
        lat, lon = row["SH_Actual_Latitude"], row["SH_Actual_Longitude"]
        if pd.isna(lat) or pd.isna(lon) or not _in_alberta(float(lat), float(lon)):
            flags.append("st37_coordinate_missing_or_outside_alberta")
        else:
            key_st, key_site = (
                _label_key(row["Licence_Surface_Location_Label"]),
                ((dls[1], dls[2], dls[3], dls[4], dls[0]) if dls else None),
            )
            if key_st is None or key_site is None:
                flags.append("st37_label_not_comparable")
            elif key_st[:4] != key_site[:4]:
                flags.append("st37_label_disagrees_with_owa_site_name")
            else:
                if key_st[4] != key_site[4]:
                    flags.append("st37_lsd_differs_same_section")
                st_cand = Candidate(
                    SOURCE_ST37,
                    "OWA licence number -> ST37 SH_Actual lat/lon; "
                    "label matches OWA site name at section/township/range",
                    float(lat),
                    float(lon),
                    ST37_NOMINAL_UNCERTAINTY_M,
                    True,
                )
                cands.append(st_cand)

    for e in extras or []:
        cands.append(e)

    auth = [c for c in cands if c.authoritative]
    best = min(auth, key=lambda c: c.uncertainty_m) if auth else None
    if best is not None:
        for c in auth:
            if c is not best and haversine_m(
                best.latitude, best.longitude, c.latitude, c.longitude
            ) > max(disagree_m, best.uncertainty_m + c.uncertainty_m):
                flags.append(f"sources_disagree:{best.source}|{c.source}")

    off = None
    if best is not None and legacy is not None:
        off = haversine_m(best.latitude, best.longitude, legacy.latitude, legacy.longitude)

    if best is None or any(f.startswith("sources_disagree") for f in flags):
        return Location(
            site_id=site_id,
            status="unverified",
            latitude=legacy.latitude if legacy else None,
            longitude=legacy.longitude if legacy else None,
            source=legacy.source if legacy else "none",
            method="location unverified: no authoritative coordinate could be pinned"
            if best is None
            else "location unverified: authoritative sources disagree",
            uncertainty_m=legacy.uncertainty_m if legacy else None,
            flags=flags,
            candidates=[asdict(c) for c in cands],
            legacy_latitude=legacy.latitude if legacy else None,
            legacy_longitude=legacy.longitude if legacy else None,
            legacy_offset_m=None,
        )
    return Location(
        site_id=site_id,
        status="verified",
        latitude=best.latitude,
        longitude=best.longitude,
        source=best.source,
        method=best.method,
        uncertainty_m=best.uncertainty_m,
        flags=flags,
        candidates=[asdict(c) for c in cands],
        legacy_latitude=legacy.latitude if legacy else None,
        legacy_longitude=legacy.longitude if legacy else None,
        legacy_offset_m=off,
    )


def load_extras(path: str | Path) -> dict[str, list[Candidate]]:
    """CSV with site_id, latitude, longitude, source, uncertainty_m (+ optional method)."""
    df = pd.read_csv(path)
    out: dict[str, list[Candidate]] = {}
    for r in df.itertuples():
        out.setdefault(str(r.site_id), []).append(
            Candidate(
                str(r.source),
                str(getattr(r, "method", "extra source csv")),
                float(r.latitude),
                float(r.longitude),
                float(r.uncertainty_m),
                True,
            )
        )
    return out


def _site_components(owa_path: str | Path) -> dict[str, list[tuple[str, str]]]:
    """site name -> [(licence, component_type), ...] in workbook order.

    load_owa() collapses each site to its FIRST component row, so a site
    whose first row is a facility or pipeline would be resolved against the
    wrong component. The resolver needs every component row to find the
    well. Returns {} if the raw workbook cannot be read (callers then fall
    back to the collapsed registry row)."""
    try:
        raw = read_owa_raw(owa_path)
    except Exception:  # noqa: BLE001 - fallback is the registry row
        return {}
    if "Site Name" not in raw:
        return {}
    lics = raw["License Number"].astype(str) if "License Number" in raw else [""] * len(raw)
    comps = raw["Component Type"].astype(str) if "Component Type" in raw else [""] * len(raw)
    out: dict[str, list[tuple[str, str]]] = {}
    for name, lic, comp in zip(raw["Site Name"], lics, comps, strict=True):
        if pd.isna(name):
            continue
        out.setdefault(str(name), []).append((lic, comp))
    return out


def resolve_registry(
    owa_path: str | Path,
    st37: pd.DataFrame,
    site_ids: list[str] | None = None,
    extras: dict[str, list[Candidate]] | None = None,
) -> pd.DataFrame:
    reg = load_owa(owa_path)
    if site_ids is not None:
        reg = reg[reg.site_id.isin(site_ids)]
    components = _site_components(owa_path)
    rows = []
    for r in reg.itertuples():
        licence, comp = r.license_number, r.component_type
        for cand_lic, cand_comp in components.get(r.site_id, []):
            if "well" in str(cand_comp).lower():
                licence, comp = cand_lic, cand_comp
                break
        loc = resolve_site(r.site_id, licence, comp, st37, (extras or {}).get(r.site_id))
        d = asdict(loc)
        d["flags"] = ";".join(loc.flags)
        d["candidates"] = json.dumps(loc.candidates)
        d["licence"] = norm_licence(licence)
        rows.append(d)
    return pd.DataFrame(rows)


# ----------------------------------------------------------------- gate ----
def location_gate(loc: dict | Location | None) -> tuple[bool, list[str]]:
    """(ok_to_assess, reasons). None / unverified => not ok. Used by change.py."""
    if loc is None:
        return False, ["location_unverified:no_geolocation_record"]
    status = loc.status if isinstance(loc, Location) else loc.get("status")
    if status != "verified":
        flags = loc.flags if isinstance(loc, Location) else loc.get("flags") or []
        if isinstance(flags, str):
            flags = [f for f in flags.split(";") if f]
        return False, ["location_unverified"] + list(flags)
    return True, []


def load_location(geolocation_path: str | Path, site_id: str) -> dict | None:
    df = (
        pd.read_parquet(geolocation_path)
        if str(geolocation_path).endswith(".parquet")
        else pd.read_csv(geolocation_path)
    )
    row = df[df.site_id == site_id]
    if row.empty:
        return None
    r = row.iloc[0]
    flags = [f for f in str(r["flags"] or "").split(";") if f and f != "nan"]
    unc = r["uncertainty_m"]
    return {
        "site_id": site_id,
        "status": str(r["status"]),
        "latitude": None if pd.isna(r["latitude"]) else float(r["latitude"]),
        "longitude": None if pd.isna(r["longitude"]) else float(r["longitude"]),
        "source": str(r["source"]),
        "method": str(r["method"]),
        "uncertainty_m": None if pd.isna(unc) else float(unc),
        "flags": flags,
    }


# ---------------------------------------------------------------- audit ----
def audit(geo: pd.DataFrame, half_square_m: float = 500.0) -> dict:
    v = geo[geo.status == "verified"].copy()
    off = v["legacy_offset_m"].dropna()

    # legacy analysis square: +/-500 m around the DLS centroid (planar approx.)
    def in_square(r) -> bool:
        dy = (r.latitude - r.legacy_latitude) * 111_320.0
        dx = (r.longitude - r.legacy_longitude) * 111_320.0 * math.cos(math.radians(r.latitude))
        return abs(dx) <= half_square_m and abs(dy) <= half_square_m

    inside = int(sum(in_square(r) for r in v.itertuples())) if len(v) else 0
    flags: dict[str, int] = {}
    for f in geo["flags"].fillna(""):
        for x in str(f).split(";"):
            if x:
                k = x.split(":")[0]
                flags[k] = flags.get(k, 0) + 1
    q = (lambda p: float(off.quantile(p))) if len(off) else (lambda p: None)
    return {
        "n_sites": int(len(geo)),
        "n_verified": int(len(v)),
        "n_unverified": int((geo.status != "verified").sum()),
        "legacy_offset_m": {
            "n": int(len(off)),
            "min": float(off.min()) if len(off) else None,
            "p05": q(0.05),
            "median": q(0.5),
            "p95": q(0.95),
            "max": float(off.max()) if len(off) else None,
            "within_300m": int((off <= 300).sum()),
            "within_500m": int((off <= 500).sum()),
        },
        "verified_sites_whose_legacy_500m_square_contains_the_well": inside,
        "flag_counts": flags,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Verified pad geolocation.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("resolve", help="resolve sites against ST37; refuse the unverifiable")
    r.add_argument("--owa", required=True)
    r.add_argument("--st37", required=False, help="ST37 zip/xlsx/parquet/csv (omit to download)")
    r.add_argument("--sites", help="text file of site ids (lines starting # ignored); default all")
    r.add_argument("--extra", help="CSV of extra candidate sources for cross-checking")
    r.add_argument("--out", required=True)
    a = sub.add_parser("audit", help="measure legacy geocode error against verified coordinates")
    a.add_argument("--geolocation", required=True)
    a.add_argument("--out-dir", default="ops/results")
    a.add_argument("--label", default="2026-10-16")
    args = ap.parse_args()

    if args.cmd == "resolve":
        st_path = args.st37 or download_st37(Path("data") / "ST_37_Excel.zip")
        st37 = load_st37(st_path)
        ids = None
        if args.sites:
            ids = [
                ln.strip()
                for ln in Path(args.sites).read_text().splitlines()
                if ln.strip() and not ln.startswith("#")
            ]
        extras = load_extras(args.extra) if args.extra else None
        geo = resolve_registry(args.owa, st37, ids, extras)
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        geo.to_parquet(args.out) if args.out.endswith(".parquet") else geo.to_csv(
            args.out, index=False
        )
        print(
            f"{len(geo)} sites: {(geo.status == 'verified').sum()} verified, "
            f"{(geo.status != 'verified').sum()} location unverified -> {args.out}"
        )
    else:
        geo = (
            pd.read_parquet(args.geolocation)
            if args.geolocation.endswith(".parquet")
            else pd.read_csv(args.geolocation)
        )
        res = audit(geo)
        out = Path(args.out_dir)
        out.mkdir(parents=True, exist_ok=True)
        (out / f"geolocation-audit-{args.label}.json").write_text(json.dumps(res, indent=2))
        print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
