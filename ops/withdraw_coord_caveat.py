#!/usr/bin/env python3
"""Replace the withdrawn '~±300 m' coordinate caveat in committed packets.

The old caveat said site coordinates were DLS LSD centroids accurate to
~±300 m and that the 500 m buffer absorbed the error. That claim was
withdrawn on 2026-10-09 (NEGATIVE-RESULT-2026-10-09.md). This script swaps
that one caveat for ledger.change.COORDINATE_CAVEAT and appends a revision
entry. Nothing else in the packet changes; tiers and measurements are
untouched. Idempotent: packets without the old caveat are skipped.

Usage:
    python ops/withdraw_coord_caveat.py --date 2026-10-10
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

import jsonschema

from ledger.change import COORDINATE_CAVEAT
from ledger.packet import SCHEMA

ROOT = Path(__file__).resolve().parent.parent
OLD_PREFIX = "Site coordinates are DLS LSD centroids (~±300 m"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--packets", default=str(ROOT / "packets"))
    ap.add_argument("--date", required=True, help="revision date (YYYY-MM-DD)")
    args = ap.parse_args()
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=ROOT, check=True
    ).stdout.strip()

    changed = 0
    for p in sorted(Path(args.packets).glob("*.json")):
        packet = json.loads(p.read_text())
        caveats = packet["claim"]["caveats"]
        hits = [i for i, c in enumerate(caveats) if c.startswith(OLD_PREFIX)]
        if not hits:
            continue
        for i in hits:
            caveats[i] = COORDINATE_CAVEAT
        packet["provenance"].setdefault("revisions", []).append(
            {
                "date": args.date,
                "tool": "ops/withdraw_coord_caveat.py",
                "code_commit": commit,
                "change": "coordinate caveat replaced: the former DLS-centroid accuracy "
                "claim ('absorbed by the 500 m buffer') was withdrawn 2026-10-09 "
                "(NEGATIVE-RESULT-2026-10-09.md); tier and measurements unchanged",
            }
        )
        jsonschema.validate(packet, SCHEMA)
        p.write_text(json.dumps(packet, indent=2))
        changed += 1
    print(f"updated {changed} packets")


if __name__ == "__main__":
    main()
