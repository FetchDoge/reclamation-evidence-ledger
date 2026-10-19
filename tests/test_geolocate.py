"""Verified-geolocation gate, not_assessable tier and placebo harness."""

import copy
import json
import subprocess
import sys
from pathlib import Path

import jsonschema
import pandas as pd
import pytest

from ledger import placebo
from ledger.geolocate import Candidate, location_gate, resolve_site

ROOT = Path(__file__).resolve().parent.parent
SCHEMA = json.loads((ROOT / "schemas" / "evidence-packet.schema.json").read_text())


def _st37(rows):
    df = pd.DataFrame(
        rows,
        columns=[
            "licence",
            "Well_Licence_Number",
            "Licence_Status",
            "SH_Actual_Latitude",
            "SH_Actual_Longitude",
            "Licence_Surface_Location_Label",
        ],
    )
    return df.set_index("licence")


ST = _st37(
    [
        ["0260210", "0260210", "RecCertified", 50.70, -113.60, "01-01-002-19W4/0"],
        ["0000099", "0000099", "Abandoned", 51.00, -114.00, "05-05-020-27W4/0"],
    ]
)


def test_verified_when_licence_joins_and_label_agrees():
    loc = resolve_site("01-01-002-19W4 (Facility)", "260210", "Well & Access Road", ST)
    assert loc.verified and loc.source.startswith("AER ST37")
    assert loc.latitude == pytest.approx(50.70)
    assert loc.legacy_offset_m is not None and loc.legacy_offset_m > 300  # the DLS defect
    assert location_gate(loc) == (True, [])


def test_unverified_when_no_licence_or_not_in_st37():
    for lic in ("", "9999999"):
        loc = resolve_site("01-01-002-19W4 (100)", lic, "Well & Access Road", ST)
        assert not loc.verified
        ok, reasons = location_gate(loc)
        assert not ok and reasons[0] == "location_unverified"


def test_label_disagreement_refuses():
    loc = resolve_site("09-09-009-09W4 (100)", "0000099", "Well & Access Road", ST)
    assert not loc.verified
    assert "st37_label_disagrees_with_owa_site_name" in loc.flags


def test_non_well_component_refuses():
    loc = resolve_site("01-01-002-19W4 (100)", "260210", "Pipeline", ST)
    assert not loc.verified and any(f.startswith("component_not_a_well") for f in loc.flags)


def test_disagreeing_extra_source_flags_and_refuses():
    far = Candidate("hand-digitized pad", "test", 50.75, -113.60, 20.0, True)
    loc = resolve_site("01-01-002-19W4 (100)", "260210", "Well & Access Road", ST, [far])
    assert not loc.verified and any(f.startswith("sources_disagree") for f in loc.flags)
    near = Candidate("hand-digitized pad", "test", 50.7002, -113.6001, 20.0, True)
    assert resolve_site("01-01-002-19W4 (100)", "260210", "Well & Access Road", ST, [near]).verified


def test_gate_without_record_is_not_ok():
    assert location_gate(None)[0] is False


def _na_packet(status="unverified"):
    return {
        "packet_id": "T_2025-2026_growing_seasons",
        "schema_version": "1.4.0",
        "site": {
            "site_id": "T",
            "latitude": 50.0,
            "longitude": -113.0,
            "owa_stage": "reclamation",
            "location": {"status": status, "source": "s", "method": "m"},
        },
        "assessment_date": "2026-10-16",
        "claim": {
            "tier": "not_assessable",
            "statement": "not assessable",
            "rationale": "r",
            "not_assessable_reasons": ["location_unverified"],
        },
        "observations": [],
        "transforms": [],
        "provenance": {
            "sources": [],
            "generated_at": "x",
            "generated_by": "y",
            "review": {"status": "not_reviewed", "log": []},
            "owa_inventory_file": {
                "url": None,
                "file_name": None,
                "file_date": "2026-10-01",
                "sha256": None,
                "retrieved_at": None,
            },
        },
    }


def test_schema_accepts_not_assessable():
    jsonschema.validate(_na_packet(), SCHEMA)


def test_schema_forbids_tier_above_not_assessable_for_unverified_location():
    p = _na_packet()
    p["claim"]["tier"] = "identified"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(p, SCHEMA)
    p["claim"]["tier"] = "detected"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(p, SCHEMA)


def test_schema_verified_location_may_carry_detected_and_not_assessable_needs_reasons():
    p = _na_packet("verified")
    p["claim"]["tier"] = "detected"
    p["claim"].pop("not_assessable_reasons")
    with pytest.raises(
        jsonschema.ValidationError
    ):  # screen claims need direction/rule/internal tier
        jsonschema.validate(p, SCHEMA)
    p["claim"].update(
        direction="none",
        tier_rule="r",
        screen_tier_internal={
            "tier": "detected",
            "direction": "none",
            "statement": "s",
            "rule": "r",
        },
    )
    jsonschema.validate(p, SCHEMA)
    q = _na_packet("verified")
    q["claim"].pop("not_assessable_reasons")
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(q, SCHEMA)


def test_schema_v14_requires_location():
    p = copy.deepcopy(_na_packet())
    del p["site"]["location"]
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(p, SCHEMA)


def test_cli_without_geolocation_record_writes_not_assessable_packet(tmp_path):
    from tests.test_ledger import _make_synthetic_chips_and_registry

    chips, reg = _make_synthetic_chips_and_registry(tmp_path / "fx", site_id="SYNTH-SITE-02")
    out = tmp_path / "out"
    r = subprocess.run(
        [
            sys.executable,
            "-m",
            "ledger.change",
            "assess",
            "--site",
            "SYNTH-SITE-02",
            "--chips",
            str(chips),
            "--registry",
            str(reg),
            "--geolocation",
            str(tmp_path / "does-not-exist.parquet"),
            "--out",
            str(out),
        ],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        timeout=300,
    )
    assert r.returncode == 0, r.stderr[-500:]
    pkt = json.loads(next(out.glob("*.json")).read_text())
    assert pkt["claim"]["tier"] == "not_assessable"
    assert pkt["site"]["location"]["status"] == "unverified"
    jsonschema.validate(pkt, SCHEMA)


def test_cli_chips_at_wrong_place_are_not_assessable(tmp_path):
    from tests.test_ledger import _make_synthetic_chips_and_registry

    chips, reg = _make_synthetic_chips_and_registry(tmp_path / "fx", site_id="SYNTH-SITE-03")
    geo = pd.read_parquet(reg.parent / "geolocation.parquet")
    geo["latitude"] = 51.05  # ~5.5 km from where the chips were fetched
    geo.to_parquet(reg.parent / "geolocation.parquet")
    out = tmp_path / "out"
    r = subprocess.run(
        [
            sys.executable,
            "-m",
            "ledger.change",
            "assess",
            "--site",
            "SYNTH-SITE-03",
            "--chips",
            str(chips),
            "--registry",
            str(reg),
            "--geolocation",
            str(reg.parent / "geolocation.parquet"),
            "--out",
            str(out),
        ],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        timeout=300,
    )
    assert r.returncode == 0, r.stderr[-500:]
    pkt = json.loads(next(out.glob("*.json")).read_text())
    assert pkt["claim"]["tier"] == "not_assessable"
    assert pkt["claim"]["not_assessable_reasons"][0].startswith("chips_not_at_verified_location")


# --- placebo harness -----------------------------------------------------------
def test_wilson_upper_known_value():
    assert placebo.wilson_upper(5, 100) == pytest.approx(0.1117, abs=1e-3)
    assert placebo.wilson_upper(0, 0) != placebo.wilson_upper(0, 0)  # nan


def test_prereg_hash_is_enforced(tmp_path):
    f = tmp_path / "PREREG-x.md"
    f.write_text("line pass <= 5%")
    f.with_suffix(".sha256").write_text(placebo.sha256_file(f) + "\n")
    assert placebo.verify_prereg(f) == placebo.sha256_file(f)
    f.write_text("line pass <= 50%")
    with pytest.raises(SystemExit):
        placebo.verify_prereg(f)


def test_committed_prereg_matches_its_hash_and_pass_line():
    f = ROOT / "placebo" / "PREREG-placebo-2026-10-16.md"
    placebo.verify_prereg(f)
    assert placebo.PASS_MAX_SHARE == 0.05 and "<= 5%" in f.read_text()


def test_gate_exit_codes(tmp_path):
    base = {"n_identified": 13, "n_eligible": 98, "pass_line_max_share_identified": 0.05}
    for verdict, code in (("FAIL", 1), ("INCOMPLETE", 1), ("PASS", 0)):
        s = tmp_path / f"{verdict}.json"
        s.write_text(json.dumps({**base, "verdict": verdict}))
        ns = type("N", (), {"summary": str(s)})()
        assert placebo.gate(ns) == code


def test_schema_rejects_nonempty_log_marked_not_reviewed():
    p = _na_packet()
    p["provenance"]["review"] = {
        "status": "not_reviewed",
        "log": [{"reviewer": "r", "date": "2026-10-16", "scope": "s", "outcome": "o"}],
    }
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(p, SCHEMA)
    p["provenance"]["review"]["status"] = "reviewed"
    jsonschema.validate(p, SCHEMA)


def test_resolve_registry_prefers_the_well_component(tmp_path):
    from ledger.geolocate import resolve_registry

    owa = pd.DataFrame(
        [
            {
                "Site Name": "01-01-002-19W4 (100)",
                "License Number": "9999999",
                "Component Type": "Pipeline",
                "Licensee": "X",
                "Responsible Department": "d",
                "Current Project Type": "t",
            },
            {
                "Site Name": "01-01-002-19W4 (100)",
                "License Number": "260210",
                "Component Type": "Well & Access Road",
                "Licensee": "X",
                "Responsible Department": "d",
                "Current Project Type": "t",
            },
        ]
    )
    path = tmp_path / "owa.xlsx"
    owa.to_excel(path, index=False)
    out = resolve_registry(path, ST, ["01-01-002-19W4 (100)"])
    assert len(out) == 1
    assert out.iloc[0]["status"] == "verified"
    assert out.iloc[0]["licence"] == "0260210"


def test_placebo_run_refuses_to_overwrite_existing_run(tmp_path):
    from types import SimpleNamespace

    out = tmp_path / "run"
    out.mkdir()
    (out / "summary.json").write_text("{}\n")
    args = SimpleNamespace(
        out=str(out),
        prereg="unused",
        points="unused",
        chips_root="unused",
        st37="unused",
        overwrite=False,
    )
    with pytest.raises(SystemExit, match="refusing to overwrite"):
        placebo.run(args)
