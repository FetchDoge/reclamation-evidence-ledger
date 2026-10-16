"""Automated validation memo and triage register generator.

Transforms a collection of schema-validated evidence packets into a client
deliverable: a ranked site register, methodology packet, and written validation
memo for screening pilots and portfolio triage.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path


def _triage_recommendation(delta: float | None, tier: str, confidence: str) -> str:
    if tier == "not_assessable":
        return "Not assessable: the screen makes no claim (see packet reasons). Not a finding about the site."
    if delta is None:
        return "Refused: Insufficient matched months (<2). Defer until next season."
    if delta <= -0.05:
        return "Walk First: Negative vegetation trend. Priority field inspection."
    if delta >= 0.08 and tier == "identified":
        return "Candidate: Positive recovery signal identified across seasons."
    return "Monitor: Within neutral envelope (|delta| < 0.08). Regular orbital watch."


def build_validation_memo(packets: list[dict], title: str = "Screening Validation Memo") -> str:
    """Build a formal Markdown validation memo from a list of packet dicts."""
    total_sites = len(packets)
    detected_count = sum(1 for p in packets if p.get("claim", {}).get("tier") == "detected")
    identified_count = sum(1 for p in packets if p.get("claim", {}).get("tier") == "identified")
    refused_count = sum(
        1 for p in packets if p.get("assessment_detail", {}).get("delta_vs_baseline") is None
    )
    not_assessable_count = sum(
        1 for p in packets if p.get("claim", {}).get("tier") == "not_assessable"
    )

    # Sort packets: lowest delta first (regressed sites at the top of the walk register)
    def sort_key(p: dict):
        d = p.get("assessment_detail", {}).get("delta_vs_baseline")
        return d if d is not None else 999.0

    sorted_packets = sorted(packets, key=sort_key)

    lines = [
        f"# {title}",
        "",
        "**Reclamation Evidence** · Calgary, Alberta · `contact@marcusrichards.dev`  ",
        f"**Date:** {datetime.now(UTC).strftime('%Y-%m-%d')} | **Protocol:** Month-Matched Median-of-Deltas (Sentinel-2 L2A)  ",
        "",
        "---",
        "",
        "## Executive Screening Summary",
        "",
        f"- **Total Sites Screened:** {total_sites}",
        f"- **Published tier `detected`:** {detected_count} (screening only; an NDVI "
        "difference vs baseline was measured, not a finding of recovery)",
        f"- **Published tier `identified`:** {identified_count} (withheld while "
        "`claim.publication_hold` is active)",
        "- **Status 2026-10-09:** screening results did not hold up under "
        "pre-registered testing (NEGATIVE-RESULT-2026-10-09.md); not evidence "
        "of recovery at any well.",
        f"- **Not assessable:** {not_assessable_count} (the screen declines to make a claim; "
        "a normal result, not a finding about the site)",
        f"- **Honest Refusals:** {refused_count} (Fewer than 2 matched calendar months; no claim made)",
        "",
        "> [!IMPORTANT]",
        "> **Notice of Stated Limits**: This screening memo establishes triage priority for ground personnel.",
        "> It does NOT certify environmental compliance, does NOT prove contamination absence,",
        "> and does NOT substitute for field inspection by qualified environmental professionals.",
        "> Attribution of responsibility is strictly excluded by design.",
        "",
        "---",
        "",
        "## Ranked Screening Register",
        "",
        "Sites are ranked by vegetation delta. Sites exhibiting stalled or negative trajectories appear first",
        "so field inspection resources can be dispatched where physical verification is most urgent.",
        "",
        "| Rank | Site ID | Name | Stage | Delta (NDVI) | 95% CI | Tier | Conf | Triage Recommendation |",
        "| :--- | :--- | :--- | :--- | :---: | :---: | :---: | :---: | :--- |",
    ]

    for rank, p in enumerate(sorted_packets, 1):
        site = p.get("site", {})
        claim = p.get("claim", {})
        det = p.get("assessment_detail", {})

        site_id = site.get("site_id", "Unknown")
        name = site.get("name", "Unknown")
        stage = site.get("owa_stage", "—")
        delta = det.get("delta_vs_baseline")
        tier = claim.get("tier", "—")
        conf = claim.get("confidence", "—")

        delta_str = (
            f"{delta:+.3f}"
            if delta is not None
            else ("n/a" if tier == "not_assessable" else "REFUSED")
        )
        ci = det.get("delta_ci95")
        if ci and len(ci) == 2:
            ci_str = f"[{ci[0]:+.2f}, {ci[1]:+.2f}]"
        else:
            ci_str = "Not estimated"

        action = _triage_recommendation(delta, tier, conf)
        lines.append(
            f"| {rank} | `{site_id}` | {name} | {stage} | {delta_str} | {ci_str} | {tier} | {conf} | {action} |"
        )

    lines.extend(
        [
            "",
            "---",
            "",
            "## Methodology & Provenance",
            "",
            "1. **Month-Matched Sampling:** To eliminate seasonal phenology artifacts (summer is greener than spring),",
            "   every observation is compared strictly against baseline scenes from the exact same calendar month.",
            "   A minimum of 2 matched months is required to report an assessment; otherwise the site is honestly refused.",
            "2. **Uncertainty Quantification:** For sites with at least 4 matched months, a 95% bootstrap confidence interval",
            "   is calculated on the median delta. If fewer than 4 matched months exist, the interval is omitted rather",
            "   than reported deceptively.",
            "3. **Claim Tiers:**",
            "   - **Detected:** Statistically significant vegetation index delta vs baseline.",
            "   - **Identified:** Delta >= +0.08 sustained across multiple observations without crossing zero.",
            "   - **Attributed:** Never emitted by automated systems; requires qualified human ground truth.",
            "",
            "---",
            "",
            "## Limits & Caveats",
            "",
            "- **Spatial Resolution:** Sentinel-2 multispectral resolution is 10 m per pixel. It cannot resolve wellheads, piping, or point-source leaks.",
            "- **Atmospheric & Snow Rejection:** Winter scenes (November–March) are excluded. Alberta snow cover obscures ground conditions.",
            "- **Drought & Regional Variation:** Regional moisture anomalies affect baseline comparisons; ground confirmation is essential.",
            "",
            "---",
            "© 2026 Marcus Richards · Calgary, Alberta · contact@marcusrichards.dev",
        ]
    )

    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate validation memo from evidence packets.")
    ap.add_argument("--packets", default="packets", help="directory containing packet JSON files")
    ap.add_argument("--out", default=None, help="output markdown file (default: stdout)")
    ap.add_argument("--title", default="Screening Pilot Validation Memo", help="title for the memo")
    args = ap.parse_args()

    packets_dir = Path(args.packets)
    files = sorted(packets_dir.glob("*.json"))
    if not files:
        raise SystemExit(f"no packets found in {packets_dir}")

    packets = [json.loads(f.read_text()) for f in files]
    memo = build_validation_memo(packets, title=args.title)

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(memo, encoding="utf-8")
        print(f"wrote validation memo for {len(packets)} sites to {out_path}")
    else:
        sys.stdout.write(memo)


if __name__ == "__main__":
    main()
