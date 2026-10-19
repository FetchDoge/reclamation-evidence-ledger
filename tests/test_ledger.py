"""Tripwire tests for the Reclamation Evidence Ledger.

Each test guards a hard-won correction. If one fails, something regressed
toward a previously fixed bug — read the test name, read the linked rule,
fix the cause, not the test.

Run: .venv/bin/python -m pytest tests/ -q
"""

import json
import re
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

from ledger.change import MIN_MATCHED_MONTHS_FOR_CI, assess  # noqa: E402

SCHEMA = json.loads((ROOT / "schemas" / "evidence-packet.schema.json").read_text())
PACKETS = sorted((ROOT / "packets").glob("*.json"))


def _packet_period_years(packet: dict) -> tuple[set[int], set[int]]:
    """Baseline/assessment years from the packet's own baseline_assessment
    transform — never hardcoded, so the test survives new periods."""
    for t in packet.get("transforms", []):
        if t.get("step") == "baseline_assessment":
            p = t.get("parameters", {})
            return set(p.get("baseline_years", [])), set(p.get("assessment_years", []))
    raise AssertionError("packet has no baseline_assessment transform")


def _synth(months, base_vals, cur_vals):
    """Synthetic month -> [scene means] inputs for assess()."""
    b = {m: [v] * 3 for m, v in zip(months, base_vals, strict=True)}
    c = {m: [v] * 3 for m, v in zip(months, cur_vals, strict=True)}
    return b, c


# --- Item 1: the degenerate-CI guard ---------------------------------------


def test_ci_omitted_below_threshold_unit():
    """assess() must not emit delta_ci95 with <4 matched months."""
    b, c = _synth([5, 6], [0.30, 0.32], [0.40, 0.42])
    a = assess("TEST", b, c, "test period")
    assert a.delta_ci95 is None
    assert a.matched_months == [5, 6]
    assert "not estimated" in a.rationale


def test_ci_present_at_threshold_unit():
    b, c = _synth([5, 6, 7, 8], [0.30] * 4, [0.40] * 4)
    a = assess("TEST", b, c, "test period")
    assert a.delta_ci95 is not None and len(a.delta_ci95) == 2
    assert "95% CI" in a.rationale


def test_no_packet_carries_ci_below_threshold():
    """No packet on disk may carry delta_ci95 with <4 matched months."""
    bad = []
    for p in PACKETS:
        d = json.loads(p.read_text())
        det = d["assessment_detail"]
        if len(det["matched_months"]) < MIN_MATCHED_MONTHS_FOR_CI and "delta_ci95" in det:
            bad.append(p.name)
    assert not bad, f"packets with degenerate CI: {bad}"


def test_caveat_does_not_claim_wide_interval():
    """The old lie ('few matched months means a wide interval') must be gone."""
    for p in PACKETS:
        d = json.loads(p.read_text())
        for cav in d["claim"]["caveats"]:
            assert "wide interval" not in cav.lower(), f"{p.name}: {cav}"


# --- Item 3: observation-count labels mean one thing -------------------------


def test_observation_count_definitions():
    """n_scene_observations == recomputed count of scene means in matched
    months with usable NDVI — separately for each period. One label, one
    definition, everywhere."""
    for p in PACKETS:
        d = json.loads(p.read_text())
        base_years, cur_years = _packet_period_years(d)
        matched = set(d["assessment_detail"]["matched_months"])
        obs = d["observations"]
        n_base = sum(
            1
            for o in obs
            if int(o["date"][:4]) in base_years
            and int(o["date"][5:7]) in matched
            and o["ndvi_mean"] is not None
        )
        n_cur = sum(
            1
            for o in obs
            if int(o["date"][:4]) in cur_years
            and int(o["date"][5:7]) in matched
            and o["ndvi_mean"] is not None
        )
        assert d["baseline"]["n_scene_observations"] == n_base, p.name
        assert d["assessment_detail"]["n_scene_observations"] == n_cur, p.name


def test_delta_is_median_of_deltas():
    """delta_vs_baseline is the median of per-month deltas, and must NOT
    equal the difference of the displayed medians in the asymmetric case."""
    # asymmetric monthly deltas: median of deltas (0.075) != diff of medians (0.10)
    b, c = _synth([5, 6, 7, 8], [0.20, 0.30, 0.40, 0.50], [0.25, 0.35, 0.55, 0.60])
    a = assess("TEST", b, c, "test period")
    assert a.delta == pytest.approx(0.075)
    assert (a.current_ndvi - a.baseline_ndvi) == pytest.approx(0.10)
    assert (a.current_ndvi - a.baseline_ndvi) != pytest.approx(a.delta)
    assert "median matched-month" in a.rationale.lower()


def test_delta_std_is_spread_of_deltas():
    """delta_std must be the std of matched-month deltas (not baseline var)."""
    import numpy as np

    b, c = _synth([5, 6, 7, 8], [0.20, 0.30, 0.40, 0.50], [0.30, 0.42, 0.48, 0.55])
    a = assess("TEST", b, c, "test period")
    deltas = [0.10, 0.12, 0.08, 0.05]
    assert a.delta_std == pytest.approx(float(np.std(deltas)), abs=1e-3)


# --- Tier rule ci-gated-v2: identified needs |delta| >= 0.08 AND a CI that
# excludes zero. v1 ignored the CI and called 28/99 sites "identified".

from ledger.change import STATEMENTS, assign_tier  # noqa: E402


def test_identified_requires_ci_excluding_zero():
    assert assign_tier(0.12, [0.05, 0.20])[0] == "identified"
    assert assign_tier(-0.12, [-0.20, -0.05])[0] == "identified"


def test_large_delta_without_ci_is_detected():
    tier, direction, key = assign_tier(0.20, None)
    assert (tier, direction, key) == ("detected", "increase", "no_ci")


def test_large_delta_with_ci_straddling_zero_is_detected():
    assert assign_tier(0.10, [-0.01, 0.20])[:2] == ("detected", "increase")
    assert assign_tier(-0.10, [-0.20, 0.0])[:2] == ("detected", "decrease")


def test_small_delta_is_detected_even_with_tight_ci():
    assert assign_tier(0.05, [0.04, 0.06]) == ("detected", "none", "none")


def test_unit_assess_two_months_never_identified():
    b, c = _synth([5, 6], [0.30, 0.30], [0.50, 0.50])
    a = assess("TEST", b, c, "test period")
    assert a.tier == "detected" and a.direction == "increase"


def test_statements_do_not_overclaim():
    """No tier wording may say reclamation, recovery, healing or stalling:
    the screen describes NDVI in an analysis square, nothing more."""
    banned = ("reclam", "recover", "heal", "stalled", "regress", "certif")
    for text in STATEMENTS.values():
        assert not any(w in text.lower() for w in banned), text


# --- Item 5: determinism ------------------------------------------------------


def test_assess_deterministic_unit():
    b, c = _synth([5, 6, 7, 8], [0.30, 0.31, 0.29, 0.33], [0.40, 0.41, 0.39, 0.43])
    a1 = asdict(assess("TEST", b, c, "test period"))
    a2 = asdict(assess("TEST", b, c, "test period"))
    assert a1 == a2


def _normalize(packet: dict) -> dict:
    """Strip run timestamps so two runs of identical inputs compare equal."""
    p = json.loads(json.dumps(packet))
    p["assessment_date"] = "STAMP"
    p["provenance"]["generated_at"] = "STAMP"
    for t in p["transforms"]:
        t["at"] = "STAMP"
    for s in p["provenance"]["sources"]:
        s["accessed"] = "STAMP"
    return p


_DET_SITE = "07-30-018-26W4 (100)"


def _det_inputs_present() -> bool:
    from ledger.imagery import safe_site_id
    from ledger.sites import provenance_path

    reg = ROOT / "data" / "sites.parquet"
    return (
        (ROOT / "data" / "chips" / safe_site_id(_DET_SITE) / "manifest.json").exists()
        and reg.exists()
        and provenance_path(reg).exists()
    )


def _make_synthetic_chips_and_registry(base_dir: Path, site_id: str = "SYNTH-SITE-01"):
    """Create a minimal, valid set of GeoTIFF chips, manifest, and registry parquet for testing."""
    import numpy as np
    import pandas as pd
    import rasterio
    from rasterio.transform import from_bounds

    chips_dir = base_dir / "chips"
    chips_dir.mkdir(parents=True, exist_ok=True)

    dates = [
        "2023-05-15",
        "2023-06-15",
        "2024-05-15",
        "2024-06-15",
        "2025-05-15",
        "2025-06-15",
        "2026-05-15",
        "2026-06-15",
    ]
    scenes = []
    tform = from_bounds(0, 0, 100, 100, 4, 4)
    profile = {
        "driver": "GTiff",
        "height": 4,
        "width": 4,
        "count": 1,
        "dtype": "uint16",
        "crs": "EPSG:3857",
        "transform": tform,
    }

    for d in dates:
        stamp = d.replace("-", "")
        chip_meta = []
        for band in ("red", "nir", "swir", "blue", "scl"):
            fpath = chips_dir / f"{stamp}_{band}.tif"
            val = 4 if band == "scl" else (2000 if band == "nir" else 1000)
            arr = np.full((4, 4), val, dtype=np.uint16)
            with rasterio.open(fpath, "w", **profile) as dst:
                dst.write(arr, 1)
            chip_meta.append(
                {"band": band, "path": str(fpath), "sha256": "0" * 64, "shape": [4, 4]}
            )
        scenes.append({"date": d, "scene_id": f"S2_{stamp}", "chips": chip_meta})

    manifest = {
        "scenes": scenes,
        "query": {"synthetic": True},
        "rejections": [],
        "latitude": 51.0,
        "longitude": -114.0,
    }
    (chips_dir / "manifest.json").write_text(json.dumps(manifest))

    reg_df = pd.DataFrame(
        [
            {
                "site_id": site_id,
                "name": "Synthetic Test Site",
                "latitude": 51.0,
                "longitude": -114.0,
                "owa_stage": "reclamation",
                "geo_method": "synthetic centroid",
            }
        ]
    )
    reg_path = base_dir / "sites.parquet"
    reg_df.to_parquet(reg_path)
    from ledger.sites import provenance_path

    provenance_path(reg_path).write_text(
        json.dumps(
            {
                "url": "https://example.invalid/synthetic.xlsx",
                "file_name": "synthetic.xlsx",
                "file_date": "2026-10-01",
                "sha256": "0" * 64,
                "retrieved_at": "2026-10-01T00:00:00+00:00",
            }
        )
    )
    pd.DataFrame(
        [
            {
                "site_id": site_id,
                "status": "verified",
                "latitude": 51.0,
                "longitude": -114.0,
                "source": "synthetic verified source",
                "method": "test fixture",
                "uncertainty_m": 100.0,
                "flags": "",
            }
        ]
    ).to_parquet(base_dir / "geolocation.parquet")
    return chips_dir, reg_path


def test_pipeline_rerun_deterministic(tmp_path):
    """Two CLI runs on the same chips must produce byte-identical packets
    apart from run timestamps. Uses the gitignored local pilot chips when
    present, otherwise a self-contained synthetic fixture."""
    from ledger.imagery import safe_site_id

    site = _DET_SITE
    if _det_inputs_present():
        chips_path = ROOT / "data" / "chips" / safe_site_id(site)
        registry_path = ROOT / "data" / "sites.parquet"
    else:
        site = "SYNTH-SITE-01"
        chips_path, registry_path = _make_synthetic_chips_and_registry(
            tmp_path / "fixtures", site_id=site
        )

    outs = []
    for i in (1, 2):
        out = tmp_path / f"run{i}"
        r = subprocess.run(
            [
                sys.executable,
                "-m",
                "ledger.change",
                "assess",
                "--site",
                site,
                "--chips",
                str(chips_path),
                "--registry",
                str(registry_path),
                "--geolocation",
                str(registry_path.parent / "geolocation.parquet"),
                "--baseline-start",
                "2023",
                "--baseline-end",
                "2024",
                "--assessment",
                "2025-2026",
                "--out",
                str(out),
            ],
            capture_output=True,
            text=True,
            cwd=str(ROOT),
            timeout=600,
        )
        assert r.returncode == 0, r.stderr[-500:]
        outs.append(next(out.glob("*.json")))
    p1 = _normalize(json.loads(outs[0].read_text()))
    p2 = _normalize(json.loads(outs[1].read_text()))
    assert p1 == p2


# --- schema contract ----------------------------------------------------------


def test_packets_validate_against_schema():
    import jsonschema

    bad = []
    for p in PACKETS:
        try:
            jsonschema.validate(json.loads(p.read_text()), SCHEMA)
        except Exception as e:  # noqa: BLE001
            bad.append((p.name, str(e)[:150]))
    assert not bad, bad


def test_schema_version_pinned():
    from ledger.packet import SCHEMA_VERSION

    assert SCHEMA_VERSION in SCHEMA["properties"]["schema_version"]["enum"]
    # The committed (published) packets are the M1 publication-hold record, 1.3.0.
    want = "1.3.0"
    assert want in SCHEMA["properties"]["schema_version"]["enum"]
    for p in PACKETS:
        d = json.loads(p.read_text())
        assert d["schema_version"] == want, p.name


# --- M1 Honest Ledger invariants over the committed packets -------------------


def test_internal_screen_tier_meets_ci_rule():
    """The CI-gated result is kept internally in every packet."""
    n_internal = 0
    for p in PACKETS:
        d = json.loads(p.read_text())
        det, internal = d["assessment_detail"], d["claim"]["screen_tier_internal"]
        tier, direction, _ = assign_tier(det["delta_vs_baseline"], det.get("delta_ci95"))
        assert (internal["tier"], internal["direction"]) == (tier, direction), p.name
        n_internal += tier == "identified"
    assert n_internal == 10


def test_publication_hold_publishes_detected_only():
    """Decision 2026-10-10: no site-level 'identified' is published until a
    surrounding-land baseline exists."""
    from ledger.change import PUBLICATION_HOLD

    assert PUBLICATION_HOLD["active"]
    for p in PACKETS:
        claim = json.loads(p.read_text())["claim"]
        assert claim["tier"] == "detected", p.name
        assert claim["statement"] == "detected – screening only", p.name
        assert claim["publication_hold"]["active"] is True, p.name
        assert "3/100" in claim["publication_hold"]["reason"], p.name


def test_schema_rejects_identified_under_hold():
    import copy

    import jsonschema

    d = copy.deepcopy(json.loads(PACKETS[0].read_text()))
    d["claim"]["tier"] = "identified"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(d, SCHEMA)


def test_published_claim_unit():
    from ledger.change import published_claim

    b, c = _synth([5, 6, 7, 8], [0.30] * 4, [0.40, 0.42, 0.41, 0.39])
    a = assess("TEST", b, c, "test period")
    assert a.tier == "identified"
    claim = published_claim(a, ["cav"])
    assert claim["tier"] == "detected"
    assert claim["screen_tier_internal"]["tier"] == "identified"
    assert claim["caveats"][-1] == "cav"


def test_rewrite_archives_previous_packet(tmp_path):
    """A re-assessment must archive the old packet and carry its revisions."""
    from ledger.packet import packet_filename, write_packet

    first = json.loads(PACKETS[0].read_text())
    write_packet(json.loads(json.dumps(first)), tmp_path)
    second = json.loads(json.dumps(first))
    second["assessment_date"] = "2027-06-15"
    out = write_packet(second, tmp_path)
    assert out.name == packet_filename(first["packet_id"])
    site_dir = tmp_path / "history" / re.sub(r"[\\/]", "_", first["site"]["site_id"])
    archived = site_dir / f"{first['assessment_date']}.json"
    assert archived.exists()
    assert json.loads(archived.read_text()) == first
    revs = json.loads(out.read_text())["provenance"]["revisions"]
    assert revs[:-1] == first["provenance"].get("revisions", [])
    assert revs[-1]["archived_packet"] == archived.relative_to(tmp_path).as_posix()
    # a third write never overwrites history
    write_packet(json.loads(json.dumps(second)), tmp_path)
    assert (site_dir / "2027-06-15.json").exists() and archived.exists()


def test_no_licensee_names_in_public_pages():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "select_pilot02", ROOT / "ops" / "select_pilot02.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    LICENSEES = mod.LICENSEES
    names = [n.lower() for n in LICENSEES] + ["lexin"]
    public = [
        ROOT / "README.md",
        ROOT / "ops" / "pilot02-results.csv",
        *sorted((ROOT / "docs").glob("*.html")),
        *sorted((ROOT / "docs").glob("*.md")),
        *sorted((ROOT / "docs").glob("*.csv")),
        *PACKETS,
    ]
    for f in public:
        text = f.read_text().lower()
        hit = [n for n in names if n in text]
        assert not hit, (f.name, hit)


def test_no_packet_claims_unrecorded_human_review():
    for p in PACKETS:
        d = json.loads(p.read_text())
        assert "review" not in d["provenance"]["generated_by"].replace(
            "no human review recorded", ""
        ), p.name
        assert "human-reviewed" not in json.dumps(d["claim"]), p.name
        rv = d["provenance"]["review"]
        assert rv["status"] == ("reviewed" if rv["log"] else "not_reviewed"), p.name


def test_every_chip_cites_its_source():
    for p in PACKETS:
        d = json.loads(p.read_text())
        for c in d["chips"]:
            assert c.get("source_url", "").startswith("https://"), (p.name, c["path"])
            assert c.get("scene_id"), (p.name, c["path"])


def test_lineage_audit_covers_every_cited_scene():
    lin = json.loads((ROOT / "ledger" / "data" / "radiometric_lineage.json").read_text())
    audited = {s["scene_id"] for s in lin["scenes"]}
    assert not lin["anomalies"]
    for p in PACKETS:
        d = json.loads(p.read_text())
        missing = {o["scene_id"] for o in d["observations"]} - audited
        assert not missing, (p.name, sorted(missing))


def test_owa_provenance_recorded():
    for p in PACKETS:
        prov = json.loads(p.read_text())["provenance"]
        f = prov["owa_inventory_file"]
        assert f["sha256"] or f.get("note"), p.name  # recorded, or says why not
        if "owa_recheck" in prov:
            assert len(prov["owa_recheck"]["sha256"]) == 64, p.name


def test_tls_verification_on_by_default(monkeypatch):
    from ledger.config import Config

    monkeypatch.delenv("LEDGER_TRUST_EGRESS_PROXY_TLS", raising=False)
    assert Config().trust_egress_proxy_tls is False
    monkeypatch.setenv("LEDGER_TRUST_EGRESS_PROXY_TLS", "1")
    assert Config().trust_egress_proxy_tls is True


def test_owa_file_date_parsed_from_filename():
    from ledger.sites import owa_file_date

    url = "https://cdn.example/x_Reporting%20-%20Full%20Inventory%20-%202026-10-01%2013.41.42.xlsx"
    assert owa_file_date(url) == "2026-10-01"
    assert owa_file_date("owa_inventory_latest.xlsx") is None


def test_footprints_sit_at_their_sites():
    """Guards the UTM-zone bug: two polygons were once 6 degrees east."""
    import math

    g = json.loads(
        (ROOT / "ledger" / "data" / "footprints" / "pilot5_provisional.geojson").read_text()
    )
    sites = {}
    for p in PACKETS:
        s = json.loads(p.read_text())["site"]
        sites[s["site_id"]] = (s["latitude"], s["longitude"])
    for f in g["features"]:
        lat0, lon0 = sites[f["properties"]["site_id"]]
        ring = f["geometry"]["coordinates"][0][:-1]
        lon = sum(c[0] for c in ring) / len(ring)
        lat = sum(c[1] for c in ring) / len(ring)
        dx = (lon - lon0) * 111_320 * math.cos(math.radians(lat0))
        dy = (lat - lat0) * 110_574
        assert math.hypot(dx, dy) < 1000, f["properties"]["site_id"]


# --- launchd plist generation -------------------------------------------------


def test_generate_plist_valid():
    import plistlib

    from ledger.pipeline import generate_plist

    xml_text = generate_plist(ROOT, Path(sys.executable))
    data = plistlib.loads(xml_text.encode("utf-8"))

    assert data["Label"] == "ca.reclamation-ledger"
    args = data["ProgramArguments"]
    assert args[0] == "/bin/bash"
    assert args[1] == "-lc"
    assert f"cd {ROOT}" in args[2]
    assert str(Path(sys.executable)) in args[2]
    assert "ledger.pipeline run-monthly" in args[2]

    intervals = data["StartCalendarInterval"]
    assert len(intervals) == 5
    months = [item["Month"] for item in intervals]
    assert months == [5, 6, 7, 8, 9]


# --- coordinate caveat (±300 m claim withdrawn 2026-10-09) --------------------


def test_no_packet_or_page_claims_withdrawn_coordinate_accuracy():
    from ledger.change import COORDINATE_CAVEAT

    for p in PACKETS:
        d = json.loads(p.read_text())
        assert COORDINATE_CAVEAT in d["claim"]["caveats"], p.name
    public = [
        *PACKETS,
        *sorted((ROOT / "docs").glob("*.html")),
        ROOT / "ops" / "dashboard_template.html",
    ]
    for f in public:
        text = f.read_text()
        for bad in ("\u00b1300", "±300", "&plusmn;300", "+/-300 m;"):
            assert bad not in text, (f.name, bad)


def test_hold_banner_does_not_call_not_assessable_sites_detected():
    from ledger.render import _banner

    na = {"claim": {"tier": "not_assessable"}}
    banner = _banner(na)
    assert "not assessable" in banner
    assert 'Every site is published as "detected' not in banner
    general = _banner()
    assert 'Every assessable site is published as "detected' in general
