"""Command-line interface (stdlib argparse only — evergreen policy).

Commands::

    loadsmith run <REGION> [--settings FILE] [--formats csv,parquet|none]
                           [--peak-scaling none|kclkvl] [--smoothing none|qp]
                           [--shares renormalized|raw] [--residual ...]
                           [--seed N] [--no-header]
    loadsmith run --all    [same options; regions run sequentially]
    loadsmith migrate [--region REGION]

Unspecified options resolve from ``loadsmith.toml`` (loadsmith/settings.py).
Implemented.
"""

from __future__ import annotations

import argparse
import json
import sys


def _add_run_options(p: argparse.ArgumentParser) -> None:
    p.add_argument("--settings", help="settings TOML (default: ./loadsmith.toml)")
    p.add_argument("--formats", help="'csv,parquet' | 'csv' | 'parquet' | 'none'")
    p.add_argument("--smoothing", choices=["none", "qp"])
    p.add_argument("--shares", choices=["renormalized", "raw"])
    p.add_argument("--peak-scaling", choices=["none", "kclkvl"], dest="peak_scaling")
    p.add_argument("--residual", choices=["residential", "proportional", "drop"])
    p.add_argument("--seed", type=int)
    p.add_argument("--no-header", action="store_true",
                   help="omit the CSV header row (MATLAB csvwrite layout)")
    p.add_argument("--no-validate", action="store_true")


def main(argv: list[str] | None = None) -> int:
    """Entry point for the ``loadsmith`` console script (see module docstring).

    Parses ``run``/``migrate`` subcommands, resolves unspecified options from
    ``loadsmith.toml``, and returns a process exit code: ``0`` on success, ``1``
    if any region fails structural validation.
    """
    parser = argparse.ArgumentParser(
        prog="loadsmith",
        description="Synthesize hourly bus-level P/Q load profiles "
                    "for EPIGRIDS regions.")
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="run the pipeline for a region")
    p_run.add_argument("region", nargs="?", help="e.g. FRCC")
    p_run.add_argument("--all", action="store_true", help="run every region")
    _add_run_options(p_run)

    p_mig = sub.add_parser("migrate", help="one-time raw-data -> parquet migration")
    p_mig.add_argument("--region")
    p_mig.add_argument("--data-dir", default="data")

    args = parser.parse_args(argv)

    if args.command == "migrate":
        sys.path.insert(0, "scripts")
        import migrate_data

        return migrate_data.main(
            (["--region", args.region] if args.region else [])
            + ["--data-dir", args.data_dir])

    # command == "run"
    from loadsmith.core import LoadSmith

    if not args.all and not args.region:
        parser.error("give a REGION or --all")

    kwargs: dict = {}
    if args.formats is not None:
        kwargs["formats"] = () if args.formats.lower() == "none" else tuple(
            s.strip() for s in args.formats.split(",") if s.strip())
    for name in ("smoothing", "shares", "peak_scaling", "residual"):
        if getattr(args, name) is not None:
            kwargs[name] = getattr(args, name)
    if args.no_header:
        kwargs["write_csv_header"] = False
    if args.no_validate:
        kwargs["validate"] = False

    smith = LoadSmith(seed=args.seed, settings=args.settings)
    regions = None
    if args.all:
        from loadsmith.regions import REGISTRY
        regions = sorted(REGISTRY)
    else:
        regions = [args.region]

    exit_code = 0
    for region in regions:
        result = smith.run(region, **kwargs)
        report = result.validation_report
        ok = report.get("ok", True) if report else True
        status = "OK" if ok else "STRUCTURAL-FAIL"
        scale = result.metadata.get("peak_scale_factor", 1.0)
        print(f"{region}: {status}  buses={len(result.national_bus_numbers)}  "
              f"peak_scaling={result.metadata['peak_scaling']} "
              f"(factor {scale:.6f})  files={list(result.written_files)}")
        if report and not ok:
            failed = {k: v for k, v in report["checks"].items()
                      if v["ok"] is False}
            print(json.dumps(failed, indent=2, default=str))
            exit_code = 1
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
