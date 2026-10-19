"""Placebo (no-well) harness: how often does the screen flag land with no well?

This is the calibration gate for every claim tier. It runs the SAME tiering
code (`ledger.change.assess`) on matched no-well points and reports the share
tagged "identified", against a pass line pre-registered in a committed file
(placebo/PREREG-placebo-*.md) before the run. The harness refuses to run if the
pre-registration's SHA-256 does not match the committed hash file.

It deliberately does not write evidence packets: placebo points are not sites,
and nothing here may ever be published as a claim about land.

    python -m ledger.placebo run \
        --prereg placebo/PREREG-placebo-2026-10-16.md \
        --points /workspace/seedling-ledger/run/stage0a/matched_points.csv \
        --chips-root /workspace/seedling-ledger/run/stage0a/chips \
        --st37 /workspace/seedling-ledger/run/ref/ST_37_Excel.zip \
        --out placebo/runs/2026-10-16
    python -m ledger.placebo gate --summary placebo/runs/2026-10-16/summary.json

`gate` exits non-zero unless the latest run PASSED, so CI or a release script
can block any tier above "detected".
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from .change import TIER_RULE, _monthly_medians, _scene_means, assess
from .geolocate import load_st37

PASS_MAX_SHARE = 0.05  # must equal the committed pre-registration
MIN_ELIGIBLE = 80
MAX_NO_RESULT_UNDOCUMENTED = 10
MIN_WELL_DISTANCE_M = 600.0
BASELINE_YEARS = [2023, 2024]
CURRENT_YEARS = [2025, 2026]


def sha256_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_prereg(prereg: Path) -> str:
    """Return the SHA-256 of the pre-registration, or raise if it was altered."""
    want_file = prereg.with_suffix(".sha256")
    if not want_file.exists():
        raise SystemExit(f"missing committed hash file {want_file}")
    want = want_file.read_text().split()[0].strip()
    got = sha256_file(prereg)
    if got != want:
        raise SystemExit(f"pre-registration altered: sha256 {got} != committed {want}")
    return got


def wilson_upper(k: int, n: int, z: float = 1.96) -> float:
    if n == 0:
        return float("nan")
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    w = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (c + w) / d


def nearest_well_m(lat: float, lon: float, wells_lat: np.ndarray, wells_lon: np.ndarray) -> float:
    """Planar nearest-neighbour distance (equirectangular, fine at <=few km)."""
    k = 111_320.0
    dy = (wells_lat - lat) * k
    dx = (wells_lon - lon) * k * math.cos(math.radians(lat))
    return float(np.sqrt(dx * dx + dy * dy).min())


def audit_rule(delta: float, ci: list | None) -> bool:
    return abs(delta) >= 0.08 and ci is not None and (ci[0] > 0 or ci[1] < 0)


def evaluate_point(chips_dir: Path) -> dict:
    """Run the production tiering on one point's chips. Never raises on data."""
    try:
        scenes, manifest = _scene_means(chips_dir)
    except Exception as e:  # noqa: BLE001
        return {"result": "no_scenes", "note": f"{type(e).__name__}: {e}"}
    if not scenes:
        return {"result": "no_scenes", "note": "no usable scenes"}
    base = _monthly_medians(scenes, BASELINE_YEARS)
    cur = _monthly_medians(scenes, CURRENT_YEARS)
    try:
        a = assess(chips_dir.name, base, cur, "2025-2026 growing seasons")
    except ValueError as e:
        return {"result": "refused", "note": str(e), "n_scenes": len(scenes)}
    return {
        "result": "assessed",
        "tier": a.tier,
        "direction": a.direction,
        "statement": a.statement,
        "delta": a.delta,
        "ci_lo": a.delta_ci95[0] if a.delta_ci95 else None,
        "ci_hi": a.delta_ci95[1] if a.delta_ci95 else None,
        "matched_months": len(a.matched_months),
        "n_scenes": len(scenes),
        "audit_rule_flag": audit_rule(a.delta, a.delta_ci95),
        "delta_only_flag": abs(a.delta) >= 0.08,
        "manifest_lat": manifest.get("latitude"),
        "manifest_lon": manifest.get("longitude"),
    }


def run(args) -> dict:
    out = Path(args.out)
    run_files = [out / n for n in ("results.csv", "summary.json", "SHA256SUMS.json")]
    if not getattr(args, "overwrite", False) and any(p.exists() for p in run_files):
        raise SystemExit(
            f"refusing to overwrite existing placebo run in {out}: "
            + ", ".join(p.name for p in run_files if p.exists())
            + " (pass --overwrite to replace it)"
        )
    prereg = Path(args.prereg)
    prereg_sha = verify_prereg(prereg)
    pts = pd.read_csv(args.points)
    pts = pts[pts["status"] == "matched"] if "status" in pts else pts
    st = load_st37(args.st37)
    st = st.dropna(subset=["SH_Actual_Latitude", "SH_Actual_Longitude"])
    wl, wo = st["SH_Actual_Latitude"].to_numpy(), st["SH_Actual_Longitude"].to_numpy()

    rows = []
    for r in pts.itertuples():
        chips = Path(args.chips_root) / r.null_id
        d = nearest_well_m(r.null_lat, r.null_lon, wl, wo)
        row = {
            "null_id": r.null_id,
            "lat": r.null_lat,
            "lon": r.null_lon,
            "nearest_st37_well_m": round(d, 1),
            "eligible": d >= MIN_WELL_DISTANCE_M,
        }
        mf = chips / "manifest.json"
        row["manifest_sha256"] = sha256_file(mf) if mf.exists() else None
        if mf.exists():
            row["chips_hash_all_ok"] = _chips_ok(mf, chips)
        if row["eligible"]:
            row.update(evaluate_point(chips))
        else:
            row["result"] = "ineligible_well_within_600m"
        rows.append(row)
    df = pd.DataFrame(rows)

    elig = df[df.eligible]
    n = len(elig)
    assessed = elig[elig.result == "assessed"]
    flagged = int((assessed.tier == "identified").sum())
    refused = int((elig.result == "refused").sum())
    undocumented = int(elig.result.isin(["no_scenes"]).sum())
    if n < MIN_ELIGIBLE or undocumented > MAX_NO_RESULT_UNDOCUMENTED:
        verdict = "INCOMPLETE"
    elif flagged / n <= PASS_MAX_SHARE:
        verdict = "PASS"
    else:
        verdict = "FAIL"
    deltas = assessed.delta.astype(float)
    ident_dirs = (
        assessed.loc[assessed.tier == "identified", "direction"]
        if len(assessed) and "direction" in assessed
        else pd.Series(dtype=object)
    )
    summary = {
        "prereg_file": str(prereg),
        "prereg_sha256": prereg_sha,
        "st37_file": str(args.st37),
        "st37_sha256": sha256_file(args.st37),
        "pass_line_max_share_identified": PASS_MAX_SHARE,
        "n_points": int(len(df)),
        "n_eligible": int(n),
        "n_ineligible": int(len(df) - n),
        "n_assessed": int(len(assessed)),
        "n_refused": refused,
        "n_no_scenes": undocumented,
        "n_identified": flagged,
        "n_identified_increase": int((ident_dirs == "increase").sum()),
        "n_identified_decrease": int((ident_dirs == "decrease").sum()),
        "share_identified": flagged / n if n else None,
        "wilson95_upper": wilson_upper(flagged, n),
        "verdict": verdict,
        "secondary": {
            "n_audit_rule_flag": int(assessed.audit_rule_flag.sum()),
            "n_delta_only_flag": int(assessed.delta_only_flag.sum()),
            "share_positive_delta": float((deltas > 0).mean()) if len(deltas) else None,
            "delta_median": float(deltas.median()) if len(deltas) else None,
            "delta_p05": float(deltas.quantile(0.05)) if len(deltas) else None,
            "delta_p95": float(deltas.quantile(0.95)) if len(deltas) else None,
        },
        "all_chip_hashes_verified": bool(
            df.get("chips_hash_all_ok", pd.Series([True])).fillna(False).all()
        ),
        "tier_rule": TIER_RULE,
        "method": "ledger.change.assess, baseline 2023-2024 vs 2025-2026, thresholds +/-0.08",
    }
    out.mkdir(parents=True, exist_ok=True)
    df.to_csv(out / "results.csv", index=False)
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    manifest = {p.name: sha256_file(p) for p in (out / "results.csv", out / "summary.json")}
    manifest["prereg"] = prereg_sha
    manifest["points_csv"] = sha256_file(args.points)
    manifest["st37"] = sha256_file(args.st37)
    (out / "SHA256SUMS.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(summary, indent=2))
    return summary


def _chips_ok(manifest_path: Path, chips_dir: Path) -> bool:
    """Re-hash every chip named in the manifest (file located by name in chips_dir)."""
    m = json.loads(manifest_path.read_text())
    for sc in m.get("scenes", []):
        for c in sc.get("chips", []):
            f = chips_dir / Path(c["path"]).name
            if not f.exists() or sha256_file(f) != c.get("sha256"):
                return False
    return True


def gate(args) -> int:
    s = json.loads(Path(args.summary).read_text())
    ok = s["verdict"] == "PASS"
    print(
        f"placebo verdict {s['verdict']}: {s['n_identified']}/{s['n_eligible']} "
        f"'identified' (line <= {s['pass_line_max_share_identified']:.0%}). "
        + (
            "Tiers above 'detected' may be considered."
            if ok
            else "Tiers above 'detected' stay WITHHELD."
        )
    )
    return 0 if ok else 1


def main() -> None:
    ap = argparse.ArgumentParser(description="Placebo calibration harness.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--prereg", required=True)
    r.add_argument("--points", required=True, help="CSV with null_id,null_lat,null_lon[,status]")
    r.add_argument("--chips-root", required=True, help="dir with one chips folder per null_id")
    r.add_argument("--st37", required=True)
    r.add_argument("--out", required=True)
    r.add_argument(
        "--overwrite",
        action="store_true",
        help="replace the results of an existing run in --out (default: refuse)",
    )
    g = sub.add_parser("gate")
    g.add_argument("--summary", required=True)
    args = ap.parse_args()
    if args.cmd == "run":
        run(args)
    else:
        sys.exit(gate(args))


if __name__ == "__main__":
    main()
