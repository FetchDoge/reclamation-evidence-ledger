"""Evidence packet builder: assessment + provenance -> schema-valid JSON.

A packet is the unit of publication. It contains everything a skeptical
reader needs to check the claim: the raw chips (by reference + checksum),
every transform in order, the observation series, the claim with its tier
and caveats, and the provenance of every source.

Usage:
    python -m ledger.packet build --site SITE_ID --assessment assessments/SITE_ID.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path

import jsonschema

SCHEMA = json.loads(
    Path(__file__)
    .resolve()
    .parent.parent.joinpath("schemas/evidence-packet.schema.json")
    .read_text()
)
SCHEMA_VERSION = "1.4.0"  # see schema_version enum: 1.4.0 adds location gate + not_assessable

# No packet may claim a human review that is not on record. The pipeline is
# automated; a review is recorded only by appending an entry (reviewer, date,
# scope, outcome) to provenance.review.log, and status changes with it.
GENERATED_BY = "reclamation-ledger pipeline (automated; no human review recorded)"


def empty_review() -> dict:
    return {"status": "not_reviewed", "log": []}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def build_packet(
    site: dict,
    assessment: dict,
    observations: list[dict],
    chips: list[dict],
    transforms: list[dict],
    sources: list[dict],
) -> dict:
    packet_id = f"{site['site_id']}_{assessment['period'].replace(' ', '_')}"
    return {
        "packet_id": packet_id,
        "schema_version": SCHEMA_VERSION,
        "site": site,
        "assessment_date": datetime.now(UTC).date().isoformat(),
        "claim": {
            "tier": assessment["tier"],
            "statement": assessment["statement"],
            "rationale": assessment["rationale"],
            "confidence": assessment["confidence"],
            "caveats": assessment["caveats"],
            **(
                {"not_assessable_reasons": assessment["not_assessable_reasons"]}
                if assessment.get("not_assessable_reasons")
                else {}
            ),
        },
        "observations": observations,
        "transforms": [{**t, "at": t.get("at", datetime.now(UTC).isoformat())} for t in transforms],
        "chips": chips,
        "provenance": {
            "sources": sources,
            "generated_at": datetime.now(UTC).isoformat(),
            "generated_by": GENERATED_BY,
            "review": empty_review(),
        },
    }


def packet_filename(packet_id: str) -> str:
    """Filesystem-safe packet filename. Site_ids can contain '/' (e.g.
    "102/10-16"); it must never become a path separator."""
    return re.sub(r"[\\/]", "_", packet_id) + ".json"


def archive_previous(existing: Path, out_dir: Path) -> Path:
    """Copy an existing packet to <out_dir>/history/<site>/<assessment_date>.json
    (suffixing _2, _3... if that name is taken). Never overwrites history."""
    old = json.loads(existing.read_text())
    site = re.sub(r"[\\/]", "_", old["site"]["site_id"])
    hdir = out_dir / "history" / site
    hdir.mkdir(parents=True, exist_ok=True)
    stem = old.get("assessment_date", "undated")
    dest, n = hdir / f"{stem}.json", 1
    while dest.exists():
        n += 1
        dest = hdir / f"{stem}_{n}.json"
    dest.write_text(existing.read_text())
    return dest


def write_packet(packet: dict, out_dir: str | Path, preserve_history: bool = True) -> Path:
    """Validate and write a packet. If a packet with the same id already
    exists it is archived under history/ first, and its revisions list is
    carried into the new packet with an entry pointing at the archive, so a
    re-assessment never silently overwrites a published packet."""
    jsonschema.validate(packet, SCHEMA)  # fail before touching anything on disk
    out_dir = Path(out_dir)
    out = out_dir / packet_filename(packet["packet_id"])
    if preserve_history and out.exists():
        old = json.loads(out.read_text())
        archived = archive_previous(out, out_dir)
        revs = list(old.get("provenance", {}).get("revisions", []))
        revs.append(
            {
                "date": packet["assessment_date"],
                "change": "re-assessed; previous packet archived",
                "archived_packet": archived.relative_to(out_dir).as_posix(),
                "previous_assessment_date": old.get("assessment_date"),
                "previous_tier": old.get("claim", {}).get("tier"),
                "previous_statement": old.get("claim", {}).get("statement"),
                "new_tier": packet["claim"]["tier"],
                "new_statement": packet["claim"]["statement"],
            }
        )
        packet["provenance"]["revisions"] = revs
    jsonschema.validate(packet, SCHEMA)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(packet, indent=2))
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Build a validated evidence packet.")
    ap.add_argument(
        "--spec",
        required=True,
        help="JSON file with site/assessment/observations/chips/transforms/sources",
    )
    ap.add_argument("--out", default="packets")
    args = ap.parse_args()

    spec = json.loads(Path(args.spec).read_text())
    packet = build_packet(
        site=spec["site"],
        assessment=spec["assessment"],
        observations=spec["observations"],
        chips=spec.get("chips", []),
        transforms=spec.get("transforms", []),
        sources=spec["sources"],
    )
    path = write_packet(packet, args.out)
    print(f"validated against schema v{packet['schema_version']}: {path}")


if __name__ == "__main__":
    main()
