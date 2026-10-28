"""Run settings — the switches that decide what parts of the pipeline run.

Settings live in a TOML file (default: ``loadsmith.toml`` at the repo/working
directory root — TOML because Python >= 3.11 reads it with the stdlib
``tomllib``; no YAML dependency needed, per the evergreen policy). Every
switch can still be overridden per call: precedence is

    explicit run() keyword  >  [regions.<NAME>] override  >  [run] table  >  built-in default

Built-in defaults (used when no file exists) are the dataclass defaults
below, so ``LoadSmith().run("FRCC")`` works with no file at all.

The switches:

===============  ======================================================
formats          list of "csv"/"parquet"; empty list = in-memory only
smoothing        "none" (default; MATLAB outputs were never smoothed, B1)
                 | "qp" (EXPERIMENTAL midnight-convexity smoothing)
residual         "" = per-state region-config default | "residential"
                 | "proportional" | "drop" (legacy B3 behavior)
shares           "renormalized" (energy-conserving) | "raw" (legacy B12)
peak_scaling     "none": bus loads exactly conserve the fitted state
                 energies. | "kclkvl": rescale P and Q by one global
                 factor so the region's coincident system PEAK equals
                 the sum of the bus table's per-state peak loads
                 (col 16) — the KCL-KVL function variants' `loadscaling`
                 step, present in the published 2024 reference outputs
                 (FRCC factor ~0.8814). (H5, decision D16)
csv_header       true | false (false reproduces MATLAB csvwrite)
validate         run structural validation after each region
seed             RNG seed for per-bus power factors (D3)
store            parquet data store path
output_dir       where outputs/<REGION>/ folders are written
===============  ======================================================
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field, fields, replace
from pathlib import Path

DEFAULT_SETTINGS_FILE = "loadsmith.toml"

_VALID = {
    "smoothing": {"none", "qp"},
    "shares": {"renormalized", "raw"},
    "peak_scaling": {"none", "kclkvl"},
    "residual": {"", "residential", "proportional", "drop"},
}


@dataclass(frozen=True)
class Settings:
    """Resolved run switches (module docstring explains each)."""

    formats: tuple[str, ...] = ("csv", "parquet")
    smoothing: str = "none"
    residual: str = ""            # "" -> per-state region-config default
    shares: str = "renormalized"
    peak_scaling: str = "none"
    csv_header: bool = True
    validate: bool = True
    seed: int = 20260708
    store: str = "data"
    output_dir: str = "outputs"
    #: raw [regions.<NAME>] tables for per-region overrides
    region_overrides: dict[str, dict] = field(default_factory=dict)

    def for_region(self, region: str) -> Settings:
        """Apply this region's ``[regions.<NAME>]`` override table, if any."""
        override = self.region_overrides.get(region.upper())
        if not override:
            return self
        known = {f.name for f in fields(Settings)} - {"region_overrides"}
        unknown = set(override) - known
        if unknown:
            raise ValueError(
                f"[regions.{region}] has unknown settings: {sorted(unknown)}")
        clean = dict(override)
        if "formats" in clean:
            clean["formats"] = tuple(clean["formats"])
        return replace(self, **clean)

    def __post_init__(self) -> None:
        for name, allowed in _VALID.items():
            value = getattr(self, name)
            if value not in allowed:
                raise ValueError(
                    f"settings.{name} must be one of {sorted(allowed)}, "
                    f"got {value!r}")
        bad = set(self.formats) - {"csv", "parquet"}
        if bad:
            raise ValueError(f"settings.formats has unknown entries: {sorted(bad)}")


def load_settings(path: str | Path | None = None) -> Settings:
    """Load ``loadsmith.toml``; missing file -> built-in defaults.

    ``path=None`` looks for :data:`DEFAULT_SETTINGS_FILE` in the current
    working directory. An explicitly-given path that doesn't exist raises
    (a silently ignored typo would be worse).
    """
    if path is None:
        candidate = Path(DEFAULT_SETTINGS_FILE)
        if not candidate.exists():
            return Settings()
    else:
        candidate = Path(path)
        if not candidate.exists():
            raise FileNotFoundError(f"settings file not found: {candidate}")

    with open(candidate, "rb") as f:
        raw = tomllib.load(f)

    run = raw.get("run", {})
    known = {f.name for f in fields(Settings)} - {"region_overrides"}
    unknown = set(run) - known
    if unknown:
        raise ValueError(f"[run] has unknown settings: {sorted(unknown)} "
                         f"(known: {sorted(known)})")
    if "formats" in run:
        run["formats"] = tuple(run["formats"])
    overrides = {
        name.upper(): table for name, table in raw.get("regions", {}).items()
    }
    return Settings(**run, region_overrides=overrides)
