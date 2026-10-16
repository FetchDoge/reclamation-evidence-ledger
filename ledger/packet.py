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
        "schema_version": "1.2.0",
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
            "generated_by": "reclamation-ledger pipeline (human-reviewed before publish)",
        },
    }


def packet_filename(packet_id: str) -> str:
    """Filesystem-safe packet filename. Site_ids can contain '/' (e.g.
    "102/10-16"); it must never become a path separator."""
    return re.sub(r"[\\/]", "_", packet_id) + ".json"


def write_packet(packet: dict, out_dir: str | Path) -> Path:
    jsonschema.validate(packet, SCHEMA)
    out = Path(out_dir) / packet_filename(packet["packet_id"])
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
