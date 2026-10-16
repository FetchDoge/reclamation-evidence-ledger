"""Tests for the Reclamation Evidence corporate website."""

import importlib.util
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE_DIR = ROOT / "site"

EXPECTED_PAGES = [
    "index.html",
    "method.html",
    "evidence.html",
    "services.html",
    "about.html",
    "contact.html",
    "order.html",
    "projects.html",
]


def test_site_pages_and_links():
    assert SITE_DIR.is_dir(), "site/ directory must exist"
    for page in EXPECTED_PAGES:
        page_path = SITE_DIR / page
        assert page_path.exists(), f"Missing page: {page}"

    link_pattern = re.compile(r"href=[\"\x27]([^\":]+)[\"\x27]")
    for p in SITE_DIR.glob("*.html"):
        content = p.read_text(encoding="utf-8")
        links = link_pattern.findall(content)
        for link in links:
            if link.startswith("http") or link.startswith("mailto:") or link.startswith("#"):
                continue
            target = SITE_DIR / link
            assert target.exists(), f"Dead link in {p.name}: {link}"


def _portal_data() -> dict:
    text = (SITE_DIR / "ledger-data.js").read_text(encoding="utf-8")
    m = re.search(r"window\.RECLAMATION_LEDGER_DATA = (\{.*\});\s*$", text, re.S)
    assert m, "ledger-data.js must assign window.RECLAMATION_LEDGER_DATA"
    return json.loads(m.group(1))


def test_portal_data_matches_published_packets():
    """site/ledger-data.js is generated from packets/ (ops/render_dashboard.py):
    one row per packet, published claim only."""
    data = _portal_data()
    packets = {}
    for f in sorted((ROOT / "packets").glob("*.json")):
        d = json.loads(f.read_text())
        packets[d["site"]["site_id"]] = d
    assert {s["id"] for s in data["sites"]} == set(packets)
    assert data["agg"]["n_sites"] == len(packets)
    for s in data["sites"]:
        claim = packets[s["id"]]["claim"]
        assert s["tier"] == claim["tier"]
        assert s["stmt"] == claim["statement"]
        assert "lic" not in s
        if claim.get("publication_hold", {}).get("active"):
            assert s["tier"] == "detected"
            assert s["stmt"] == "detected \u2013 screening only"


def test_portal_reads_generated_data_not_hardcoded():
    ledger_js = (SITE_DIR / "ledger.js").read_text(encoding="utf-8")
    assert "window.RECLAMATION_LEDGER_DATA" in ledger_js
    assert '"sites":[' not in ledger_js, "ledger.js must not hardcode packet data"
    for p in SITE_DIR.glob("*.html"):
        html = p.read_text(encoding="utf-8")
        i_data = html.find('<script src="ledger-data.js"></script>')
        i_ledger = html.find('<script src="ledger.js"></script>')
        assert 0 <= i_data < i_ledger, f"{p.name}: load ledger-data.js before ledger.js"


def test_portal_static_counts_match_data():
    """Static fallbacks in data-ledger spans equal the generated counts."""
    agg = _portal_data()["agg"]
    want = {
        "n_sites": agg["n_sites"],
        "n_detected": agg["tiers"].get("detected", 0),
        "n_identified": agg["tiers"].get("identified", 0),
        "n_high": agg["confs"].get("high", 0),
    }
    span = re.compile(r'<span data-ledger="(\w+)">([^<]*)</span>')
    for p in SITE_DIR.glob("*.html"):
        for key, val in span.findall(p.read_text(encoding="utf-8")):
            assert val == str(want[key]), (p.name, key, val)


def test_portal_hold_banner_on_every_page():
    for p in SITE_DIR.glob("*.html"):
        html = p.read_text(encoding="utf-8")
        assert 'id="ledger-hold-banner"' in html, p.name
        assert "RE-SCORING IN PROGRESS" in html, p.name
        assert "NEGATIVE-RESULT-2026-10-09" in html, p.name


def test_portal_has_no_licensee_names_or_withdrawn_accuracy():
    spec = importlib.util.spec_from_file_location(
        "select_pilot02", ROOT / "ops" / "select_pilot02.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    names = [n.lower() for n in mod.LICENSEES] + ["lexin"]
    for p in sorted(SITE_DIR.iterdir()):
        text = p.read_text(encoding="utf-8").lower()
        hit = [n for n in names if n in text]
        assert not hit, (p.name, hit)
        assert "300m" not in text and "300 m" not in text, p.name


def test_site_boundaries_and_limits_displayed():
    for page in ["index.html", "services.html"]:
        html = (SITE_DIR / page).read_text(encoding="utf-8")
        assert "No compliance or reclamation certification" in html
        assert "No contamination status" in html
