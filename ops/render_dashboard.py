#!/usr/bin/env python3
"""Render the Reclamation Evidence Ledger dashboard.

Reads packets/*.json and emits a single-file,
dependency-free, publish-anywhere dashboard at docs/index.html, plus
site/ledger-data.js: the same published payload for the client portal
(site/ledger.js reads it; nothing in site/ hardcodes packet data).

Every packet-derived number (sites, licensees, tiers, deltas, CIs) is
computed from the packets at render time. The Plate I verification traces and
Plate V BACI-probe figures are typed into the template from the 2026-09-27
audit notes, and the page labels them so. Re-run after any assess/render cycle:

    python ops/render_dashboard.py
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent.parent
PACKETS = sorted(ROOT.glob("packets/*.json"))
OUT = ROOT / "docs" / "index.html"
SITE_DATA = ROOT / "site" / "ledger-data.js"
PAGES_URL = "https://marsojuji-cmyk.github.io/reclamation-evidence-ledger/"

BASE_YEARS = (2023, 2024)
CUR_YEARS = (2025, 2026)


def period_years(packet: dict) -> tuple[list[int], list[int]]:
    for t in packet.get("transforms", []):
        if t.get("step") == "baseline_assessment":
            p = t.get("parameters", {})
            return (
                list(p.get("baseline_years", []) or list(BASE_YEARS)),
                list(p.get("assessment_years", []) or list(CUR_YEARS)),
            )
    return (list(BASE_YEARS), list(CUR_YEARS))


def build_site(packet: dict, packet_file: Path) -> dict:
    """Public dashboard row. Only the PUBLISHED claim is used; the internal
    screen tier (claim.screen_tier_internal) and licensee names are never
    placed in the page."""
    site = packet["site"]
    claim = packet["claim"]
    det = packet["assessment_detail"]
    base_yrs, cur_yrs = period_years(packet)
    matched = set(det.get("matched_months", []))
    obs = []
    for o in packet.get("observations", []):
        ndvi = o.get("ndvi_mean")
        if ndvi is None:
            continue
        d = o["date"]
        yr, mo = int(d[:4]), int(d[5:7])
        obs.append(
            [
                d,
                round(float(ndvi), 4),
                round(float(o.get("clear_pixel_fraction") or 0), 3),
                1 if yr in base_yrs else 0,
                1 if mo in matched else 0,
            ]
        )
    obs.sort(key=lambda r: r[0])
    sid = site["site_id"]
    return {
        "id": sid,
        "tier": claim["tier"],
        "conf": claim["confidence"],
        "stmt": claim["statement"],
        "rat": claim["rationale"],
        "cav": claim["caveats"],
        "delta": det.get("delta_vs_baseline"),
        "ci": det.get("delta_ci95"),
        "mm": sorted(matched),
        "nobs": len(obs),
        "nchips": len(packet.get("chips", [])),
        "bmed": packet.get("baseline", {}).get("ndvi_median"),
        "cmed": det.get("ndvi_median"),
        "page": quote(packet_file.stem + ".html"),
        "lat": round(site.get("latitude") or 0, 5),
        "lon": round(site.get("longitude") or 0, 5),
        "obs": obs,
    }


def main() -> None:
    sites = []
    for f in PACKETS:
        packet = json.loads(f.read_text())
        sites.append(build_site(packet, f))
    sites.sort(key=lambda s: s["id"].lower())

    tiers = {}
    confs = {}
    n_noci = 0
    for s in sites:
        tiers[s["tier"]] = tiers.get(s["tier"], 0) + 1
        confs[s["conf"]] = confs.get(s["conf"], 0) + 1
        if s["ci"] is None:
            n_noci += 1
    hi_ident = sum(1 for s in sites if s["tier"] == "identified" and s["conf"] == "high")
    first = json.loads(PACKETS[0].read_text())
    schema_v = first.get("schema_version", "?")
    hold = first.get("claim", {}).get("publication_hold") or {}

    agg = {
        "n_sites": len(sites),
        "tiers": tiers,
        "confs": confs,
        "n_noci": n_noci,
        "hi_ident": hi_ident,
        "schema": schema_v,
        "generated": dt.datetime.now(dt.UTC).strftime("%Y-%m-%d %H:%M UTC"),
        "hold": {k: hold.get(k) for k in ("active", "since", "reason")},
    }
    data = {"sites": sites, "agg": agg}
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    payload = payload.replace("</", "<\\/")  # keep </script> out of the JSON

    tpl = (ROOT / "ops" / "dashboard_template.html").read_text()
    html = tpl.replace("%%LEDGER_JSON%%", payload)
    html = html.replace("%%GENERATED%%", agg["generated"])
    html = html.replace("%%SCHEMA%%", str(schema_v))
    html = html.replace("%%N_SITES%%", str(agg["n_sites"]))
    html = html.replace("%%N_IDENT%%", str(tiers.get("identified", 0)))
    html = html.replace("%%N_DETECT%%", str(tiers.get("detected", 0)))
    html = html.replace("%%N_HI%%", str(hi_ident))
    html = html.replace("%%N_NOCI%%", str(n_noci))
    OUT.write_text(html)

    # Client portal data: the same published payload as the dashboard.
    portal = {"sites": sites, "agg": agg, "pages_url": PAGES_URL}
    SITE_DATA.write_text(
        "/* Generated by ops/render_dashboard.py from packets/*.json -- do not edit.\n"
        "   Published claims only: no licensee names, no internal screen tier. */\n"
        "window.RECLAMATION_LEDGER_DATA = "
        + json.dumps(portal, ensure_ascii=False, separators=(",", ":"))
        + ";\n"
    )
    print(f"wrote {SITE_DATA} ({len(sites)} sites)")
    print(f"wrote {OUT} ({OUT.stat().st_size / 1024:.0f} KB, {len(sites)} sites)")


if __name__ == "__main__":
    main()
