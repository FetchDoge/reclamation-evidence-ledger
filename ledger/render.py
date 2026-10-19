"""Static ledger renderer: packets -> publishable HTML.

No server, no database, no JavaScript framework. The ledger is a set of
static pages: an index table plus one page per packet. Anything a reader
needs is in the HTML; the JSON packets sit alongside for verification.

Usage:
    python -m ledger.render --packets packets/ --out docs/
    python ops/render_dashboard.py   # then overwrite docs/index.html
"""

from __future__ import annotations

import argparse
import html
import json
import re
from pathlib import Path

ATTRIBUTION = (
    "Imagery: Copernicus Sentinel-2 (ESA), via AWS Open Data. "
    "Contains modified Copernicus Sentinel data."
)

PAGE_TMPL = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} — Reclamation Evidence Ledger</title>
<style>
body{{font-family:system-ui,sans-serif;max-width:70ch;margin:2rem auto;padding:0 1rem;line-height:1.5}}
.tier{{display:inline-block;padding:.2rem .6rem;border-radius:4px;font-weight:600}}
.detected{{background:#fff3cd}} .identified{{background:#d1ecf1}} .not_assessable{{background:#e2e3e5;border:1px dashed #6c757d}}
table{{border-collapse:collapse;width:100%}} th,td{{border:1px solid #ccc;padding:.4rem;text-align:left}}
.hold{{border:3px solid #222;padding:.6rem 1rem;margin:0 0 1rem;font-weight:600}}
.caveat{{background:#f8f9fa;border-left:4px solid #999;padding:.5rem 1rem;margin:.5rem 0}}
footer{{margin-top:3rem;font-size:.85rem;color:#555;border-top:1px solid #ccc;padding-top:1rem}}
code{{background:#f4f4f4;padding:.1rem .3rem}}
</style></head>
<body>
{banner}
<h1>Reclamation Evidence Ledger</h1>
{body}
<footer><p>{attribution}</p>
<p>Screening only: these packets prioritize ground inspection. They are not
legal proof, reclamation certifications or compliance verdicts, they do not
measure methane, soil, contamination or subsurface conditions, and they name
no responsible party. A tier describes NDVI in a ~1 km² square around a DLS
centroid, mostly land around the pad, not the pad itself.</p></footer>
</body></html>"""


def _esc(v) -> str:
    return html.escape(str(v))


def _banner(packet: dict | None = None) -> str:
    from .change import PUBLICATION_HOLD

    if not PUBLICATION_HOLD.get("active"):
        return ""
    if packet is not None and packet.get("claim", {}).get("tier") == "not_assessable":
        lead = 'This site is published as "not assessable" — the screen makes no claim for it. '
    else:
        lead = 'Every assessable site is published as "detected – screening only". '
    return (
        '<div class="hold" role="status">Re-scoring in progress (Oct 2026): '
        "site-level calls are withheld pending a surrounding-land baseline. "
        f"{lead}"
        f"{_esc(PUBLICATION_HOLD['reason'])}</div>"
    )


def render_packet(packet: dict, chart_file: str | None = None) -> str:
    c = packet["claim"]
    obs_rows = "".join(
        f"<tr><td>{_esc(o['date'])}</td><td><code>{_esc(o['scene_id'])}</code></td>"
        f"<td>{o.get('ndvi_mean') if o.get('ndvi_mean') is not None else '—'}</td>"
        f"<td>{o.get('ndmi_mean') if o.get('ndmi_mean') is not None else '—'}</td>"
        f"<td>{o['clear_pixel_fraction']:.0%}</td></tr>"
        for o in packet["observations"]
    )
    caveats = "".join(f'<div class="caveat">{_esc(x)}</div>' for x in c["caveats"])
    transforms = "".join(
        f"<li><b>{_esc(t['step'])}</b> — {_esc(t['tool'])} "
        f"<code>{_esc(json.dumps(t['parameters']))}</code></li>"
        for t in packet["transforms"]
    )
    srcs = "".join(
        f"<li>{_esc(s['name'])} — <a href='{_esc(s['url'])}'>{_esc(s['url'])}</a> "
        f"(accessed {_esc(s['accessed'])})</li>"
        for s in packet["provenance"]["sources"]
    )
    s = packet["site"]
    prov = packet["provenance"]
    review = prov.get("review") or {}
    review_txt = (
        "no human review recorded"
        if not review.get("log")
        else f"{len(review['log'])} review(s) recorded"
    )
    owa = prov.get("owa_inventory_file") or {}
    owa_txt = (
        f"OWA file {_esc(owa.get('file_date'))}, sha256 <code>{_esc(owa.get('sha256'))}</code>"
        if owa.get("sha256")
        else _esc(owa.get("note", "OWA inventory file not recorded"))
    )
    recheck = prov.get("owa_recheck")
    if recheck:
        owa_txt += (
            f"<br>Re-checked against OWA file {_esc(recheck.get('file_date'))} "
            f"(sha256 <code>{_esc(recheck.get('sha256'))}</code>) on "
            f"{_esc(recheck.get('checked_on'))}: site "
            f"{'found' if recheck.get('site_found') else 'NOT found'}, stage "
            f"{_esc(recheck.get('owa_stage'))}"
        )
    n_src = sum(1 for ch in packet.get("chips", []) if ch.get("source_url"))
    # Date and change only: while the publication hold is active, pages do
    # not restate intermediate (internal) tiers. The packet JSON keeps them.
    revisions = "".join(
        f"<li>{_esc(r.get('date'))}: {_esc(r.get('change'))}"
        + (
            f" (previous packet archived at <code>{_esc(r['archived_packet'])}</code>)"
            if r.get("archived_packet")
            else ""
        )
        + "</li>"
        for r in prov.get("revisions", [])
    )
    revisions_html = f"<h3>Revisions</h3><ul>{revisions}</ul>" if revisions else ""
    loc = s.get("location")
    loc_html = (
        f"<p class='caveat'>Location: <b>{_esc(loc['status'])}</b> — {_esc(loc['source'])}"
        f"{'; ±' + _esc(round(loc['uncertainty_m'])) + ' m nominal' if loc.get('uncertainty_m') else ''}."
        f" {_esc(loc['method'])}</p>"
        if loc
        else "<p class='caveat'>Location provenance: not recorded (legacy packet; see "
        "NEGATIVE-RESULT-2026-10-09.md).</p>"
    )
    na = c.get("not_assessable_reasons") or []
    na_html = (
        "<p class='caveat'><b>Why no claim is made:</b> "
        + _esc("; ".join(na))
        + ". Not assessable is a normal result of this screen, not a finding about the site.</p>"
        if na
        else ""
    )
    chart_html = (
        f'<h3>NDVI time series</h3><p><img src="assets/{_esc(chart_file)}" '
        f'alt="per-scene NDVI time series" style="max-width:100%"></p>'
        if chart_file and packet["observations"]
        else ""
    )
    return PAGE_TMPL.format(
        title=_esc(packet["packet_id"]),
        attribution=ATTRIBUTION,
        banner=_banner(packet),
        body=f"""
<h2>Site {_esc(s["site_id"])}</h2>
<p>{_esc(s.get("name", ""))} — {_esc(s["latitude"])}, {_esc(s["longitude"])}<br>
OWA stage: <b>{_esc(s["owa_stage"])}</b> (inventory {_esc(s.get("owa_inventory_date", ""))})</p>
{loc_html}
<h3>Claim <span class="tier {c["tier"]}">{_esc(c["tier"]).replace("_", " ").upper()}</span></h3>
<p><b>{_esc(c["statement"])}</b> — {_esc(c["rationale"])}<br>
Confidence: {_esc(c.get("confidence", "n/a"))}
· Review: {review_txt}</p>
{na_html}
{chart_html}
{caveats}
<h3>Observations</h3>
<table><tr><th>Date</th><th>Scene</th><th>NDVI</th><th>NDMI</th><th>Clear</th></tr>
{obs_rows}</table>
<h3>Transforms (the argument against the result)</h3>
<ol>{transforms}</ol>
<h3>Sources</h3>
<ul>{srcs}</ul>
<p>{owa_txt}</p>
<p>{n_src} of {len(packet.get("chips", []))} chips cite their source COG URL and
SHA-256 in the packet JSON.</p>
{revisions_html}
<p><a href="index.html">← ledger index</a></p>
""",
    )


def _marker_color(claim: dict) -> str:
    """Colour only published identified results; everything else is grey.
    (While the publication hold is active nothing is identified.)"""
    if claim.get("tier") != "identified":
        return "grey"
    return {"increase": "#1f6fb2", "decrease": "#b25f1f"}.get(claim.get("direction"), "grey")


def render_index_map(packets: list[dict], pages: list[str]) -> str:
    """Leaflet map of all sites, markers colored by outcome."""
    pts = []
    for packet, page in zip(packets, pages, strict=True):
        s = packet["site"]
        pts.append(
            {
                "lat": s["latitude"],
                "lon": s["longitude"],
                "site_id": packet["packet_id"],
                "page": page,
                "tier": packet["claim"]["tier"],
                "statement": packet["claim"]["statement"],
                "confidence": packet["claim"].get("confidence", "n/a"),
                "color": _marker_color(packet["claim"]),
            }
        )
    data_js = json.dumps(pts)
    return f"""
<h2>Site map</h2>
<div id="map" style="height:420px;max-width:100%"></div>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
const pts = {data_js};
const map = L.map('map').setView([50.7, -113.6], 9);
L.tileLayer('https://tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png',
  {{attribution: '&copy; OpenStreetMap contributors'}}).addTo(map);
const bounds = [];
for (const p of pts) {{
  const m = L.circleMarker([p.lat, p.lon], {{
    radius: 7, color: p.color, fillColor: p.color, fillOpacity: 0.7, weight: 2
  }}).addTo(map);
  const div = document.createElement('div');
  const a = document.createElement('a'); a.href = p.page; a.textContent = p.site_id;
  div.appendChild(a);
  const info = document.createElement('div');
  info.textContent = p.tier + ' — ' + p.statement + ' (' + p.confidence + ' confidence)';
  div.appendChild(info);
  m.bindPopup(div);
  bounds.push([p.lat, p.lon]);
}}
if (bounds.length) map.fitBounds(bounds, {{padding: [20, 20]}});
</script>
<p><span style="color:#1f6fb2">●</span> identified: NDVI higher than baseline
<span style="color:#b25f1f">●</span> identified: NDVI lower than baseline
<span style="color:grey">●</span> detected (no CI-supported change).
Coordinates are DLS-derived (accuracy withdrawn 2026-10-09 — see NEGATIVE-RESULT-2026-10-09.md).
Markers show screening areas, not wellheads.</p>
"""


def main() -> None:
    ap = argparse.ArgumentParser(description="Render the static ledger site.")
    ap.add_argument("--packets", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    from .charts import render_site_chart

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    assets = out / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    packets = sorted(Path(args.packets).glob("*.json"))

    rows, pages, objs = [], [], []
    for p in packets:
        packet = json.loads(p.read_text())
        # packet_ids can contain '/' (site names like "102/10-16"); filenames must not.
        stem = re.sub(r"[\\/]", "_", packet["packet_id"])
        page = stem + ".html"
        chart = stem + ".png"
        try:
            render_site_chart(packet, assets / chart)
        except Exception as e:  # a missing chart must never break the ledger
            print(f"  chart failed for {packet['packet_id']}: {e}")
            chart = None
        (out / page).write_text(render_packet(packet, chart))
        c = packet["claim"]
        rows.append(
            f"<tr><td><a href='{page}'>{_esc(packet['packet_id'])}</a></td>"
            f"<td><span class='tier {c['tier']}'>{_esc(c['tier'].replace('_', ' '))}</span></td>"
            f"<td>{_esc(c['statement'])}</td><td>{_esc(c.get('confidence', 'n/a'))}</td></tr>"
        )
        pages.append(page)
        objs.append(packet)

    index = PAGE_TMPL.format(
        title="Index",
        attribution=ATTRIBUTION,
        banner=_banner(),
        body=f"<h2>{len(packets)} evidence packets</h2>"
        + render_index_map(objs, pages)
        + "<table><tr><th>Packet</th><th>Tier</th><th>Finding</th><th>Confidence</th></tr>"
        + "".join(rows)
        + "</table>",
    )
    (out / "index.html").write_text(index)
    print(f"rendered {len(packets)} packets -> {out}")


if __name__ == "__main__":
    main()
