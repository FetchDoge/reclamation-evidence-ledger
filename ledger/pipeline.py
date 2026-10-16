"""Monthly pipeline: fetch new scenes, assess all pilot sites, render the ledger.

This is the entry point the launchd plist calls:

    python -m ledger.pipeline run-monthly --sites pilots/pilot-02.txt

It chains the stages that already exist as CLIs:
  0. ledger.sites            (downloads the current OWA inventory and writes
     the registry plus <registry>.owa_provenance.json: file URL, date,
     SHA-256; skip with --skip-owa-refresh)
  1. ledger.imagery fetch   (incremental; skips dates already on disk)
  2. per-site ledger.change assess  (via ops/assess_all.py --force, so sites
     with new scenes are re-assessed; failures are recorded, not fatal)
  3. ledger.render           (rebuilds the static site from packets/)

Growing-season discipline lives in config.growing_months; months outside it
are never fetched or assessed. Nothing is published here — the operator
reviews out/ledger/ before any upload.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VENV_PY = sys.executable


def _run(*argv: str) -> None:
    print(f"$ {' '.join(argv)}", flush=True)
    r = subprocess.run(argv, cwd=str(ROOT))
    if r.returncode != 0:
        raise SystemExit(f"pipeline step failed ({r.returncode}): {' '.join(argv[1:3])}")


def cmd_run_monthly(args) -> None:
    today = date.today()
    # Growing season only; outside it there is nothing honest to add.
    from .config import DEFAULT

    if today.month not in DEFAULT.growing_months:
        print(
            f"{today.isoformat()}: outside growing season "
            f"{sorted(DEFAULT.growing_months)} — nothing to do."
        )
        return

    season_start = date(today.year, 5, 1)
    if not args.skip_owa_refresh:
        _run(VENV_PY, "-m", "ledger.sites", "--out", args.registry)
    _run(
        VENV_PY,
        "-m",
        "ledger.imagery",
        "fetch",
        "--sites",
        args.sites,
        "--registry",
        args.registry,
        "--start",
        season_start.isoformat(),
        "--end",
        today.isoformat(),
        "--out",
        args.chips,
        "--max-scenes",
        str(args.max_scenes),
    )
    assess = [
        VENV_PY,
        str(ROOT / "ops" / "assess_all.py"),
        "--sites",
        args.sites,
        "--registry",
        args.registry,
        "--chips",
        args.chips,
        "--packets",
        args.packets,
        "--baseline-start",
        str(args.baseline_start),
        "--baseline-end",
        str(args.baseline_end),
        "--assessment",
        args.assessment,
    ]
    if not args.no_force:
        assess.append("--force")
    _run(*assess)
    _run(VENV_PY, "-m", "ledger.render", "--packets", args.packets, "--out", args.out)
    print("monthly run complete: review out/ledger/ before publishing.")


def generate_plist(repo_root: Path, python_bin: Path | None = None) -> str:
    """Generate launchd plist XML pinned to the specified checkout and python."""
    import plistlib

    from .config import DEFAULT

    root = Path(repo_root).resolve()
    if python_bin is not None:
        py = Path(python_bin)
        if not py.is_absolute():
            py = root / py
    else:
        if (root / ".venv" / "bin" / "python").exists():
            py = root / ".venv" / "bin" / "python"
        else:
            py = Path(sys.executable)

    cmd = f"cd {root} && {py} -m ledger.pipeline run-monthly"

    calendar_intervals = [
        {"Month": m, "Day": 15, "Hour": 2, "Minute": 0} for m in sorted(DEFAULT.growing_months)
    ]

    plist_data = {
        "Label": "ca.reclamation-ledger",
        "ProgramArguments": ["/bin/bash", "-lc", cmd],
        "StartCalendarInterval": calendar_intervals,
        "StandardOutPath": "/tmp/reclamation-ledger.log",
        "StandardErrorPath": "/tmp/reclamation-ledger.err",
    }
    return plistlib.dumps(plist_data).decode("utf-8")


def cmd_generate_plist(args) -> None:
    xml_text = generate_plist(ROOT, Path(args.python or sys.executable))
    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(xml_text, encoding="utf-8")
        print(f"wrote launchd plist to {out_path}")
    else:
        sys.stdout.write(xml_text)


def cmd_install_plist(args) -> None:
    target_dir = Path.home() / "Library" / "LaunchAgents"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / "ca.reclamation-ledger.plist"

    xml_text = generate_plist(ROOT, Path(args.python or sys.executable))
    target.write_text(xml_text, encoding="utf-8")
    print(f"Installed launchd agent to {target}")

    if args.load:
        r = subprocess.run(["launchctl", "load", str(target)])
        if r.returncode == 0:
            print(f"Loaded {target} via launchctl")
        else:
            print(f"launchctl load returned {r.returncode}")
    else:
        print(f"To load now, run: launchctl load {target}")


def cmd_uninstall_plist(args) -> None:
    target = Path.home() / "Library" / "LaunchAgents" / "ca.reclamation-ledger.plist"
    if args.unload:
        subprocess.run(["launchctl", "unload", str(target)], check=False)
    if target.exists():
        target.unlink()
        print(f"Removed {target}")
    else:
        print(f"{target} does not exist")


def main() -> None:
    ap = argparse.ArgumentParser(description="Reclamation Evidence Ledger pipeline.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run-monthly", help="fetch + assess + render for pilot sites")
    r.add_argument("--sites", default="pilots/pilot-02.txt")
    r.add_argument("--registry", default="data/sites.parquet")
    r.add_argument("--chips", default="data/chips")
    r.add_argument("--packets", default="packets")
    r.add_argument("--out", default="out/ledger")
    r.add_argument("--max-scenes", type=int, default=10)
    r.add_argument("--baseline-start", type=int, default=2023)
    r.add_argument("--baseline-end", type=int, default=2024)
    r.add_argument(
        "--assessment",
        default="2025-2026",
        help="assessment years; packets are named by this period",
    )
    r.add_argument(
        "--skip-owa-refresh",
        action="store_true",
        help="reuse the existing registry instead of downloading the current OWA inventory",
    )
    r.add_argument(
        "--no-force",
        action="store_true",
        help="skip sites that already have a packet for the period",
    )

    gp = sub.add_parser("generate-plist", help="generate launchd plist XML for current checkout")
    gp.add_argument(
        "--python", default=None, help="python binary path to use (defaults to sys.executable)"
    )
    gp.add_argument("--out", default=None, help="output path for plist file (defaults to stdout)")

    ip = sub.add_parser("install-plist", help="install launchd plist into ~/Library/LaunchAgents")
    ip.add_argument("--python", default=None, help="python binary path to use")
    ip.add_argument(
        "--load", action="store_true", help="immediately run launchctl load after install"
    )

    up = sub.add_parser("uninstall-plist", help="remove launchd plist from ~/Library/LaunchAgents")
    up.add_argument(
        "--unload", action="store_true", help="run launchctl unload before removing file"
    )

    args = ap.parse_args()
    if args.cmd == "run-monthly":
        cmd_run_monthly(args)
    elif args.cmd == "generate-plist":
        cmd_generate_plist(args)
    elif args.cmd == "install-plist":
        cmd_install_plist(args)
    elif args.cmd == "uninstall-plist":
        cmd_uninstall_plist(args)


if __name__ == "__main__":
    main()
