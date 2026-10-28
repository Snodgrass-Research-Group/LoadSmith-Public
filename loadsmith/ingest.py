"""Stage 1 (runtime half) — read the migrated parquet store.

The one-time migration (``scripts/migrate_data.py``) is the ONLY code that
parses Excel/.mat/.csv raw files (decision D8). This module reads the clean
parquet store (schema: HOOKS.md §3) and returns numpy/pandas objects per the
inter-stage contracts (HOOKS.md §2).

Spec: docs/conversion_manual/algorithms/01_ingestion_migration.md.
Implemented for the shared inputs and all regions, including utility profiles.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


class ParquetStore:
    """Typed reader over ``data/`` (shared + per-region parquet files).

    Results are cached per file; instantiate a fresh store after re-running
    the migration in the same process.
    """

    def __init__(self, root: str | Path = "data") -> None:
        self.root = Path(root)
        self._cache: dict[Path, pd.DataFrame] = {}

    # ---- internals ------------------------------------------------------ #

    def _read(self, relpath: str) -> pd.DataFrame:
        path = self.root / relpath
        if path not in self._cache:
            if not path.exists():
                raise FileNotFoundError(
                    f"{path} not found — run scripts/migrate_data.py first "
                    "(one-time migration, decision D8)")
            self._cache[path] = pd.read_parquet(path)
        return self._cache[path]

    @staticmethod
    def _region_dir(region: str) -> str:
        return region.strip().lower()

    # ---- shared ----------------------------------------------------------- #

    def nyseg_profiles(self) -> np.ndarray:
        """NYSEG ``profiles_aggregate`` as (24, 36, 9): hour x day-type x class.

        Source: NYSEGloadprofiles2016.mat (static input, no producer script),
        stored long-format in data/shared/nyseg_profiles.parquet.
        """
        df = self._read("shared/nyseg_profiles.parquet")
        arr = np.full((24, 36, 9), np.nan)
        arr[df["hour"].to_numpy() - 1,
            df["day_type"].to_numpy() - 1,
            df["class"].to_numpy() - 1] = df["value"].to_numpy(float)
        if np.isnan(arr).any():
            raise ValueError("nyseg_profiles.parquet does not cover the full "
                             "(24, 36, 9) grid")
        return arr

    def national_bus_map(self, region: str | None = None) -> pd.DataFrame:
        """Regional -> national bus number mapping (hook H1, RESOLVED).

        Columns: region, regional_bus_num, national_bus_num (the 'Final
        National Bus Num' used by the published WISPO-POP models), bus_type
        ('Gen'/'Load'), state, region_num. Filtered to ``region`` if given.
        """
        df = self._read("shared/national_bus_map.parquet")
        if region is not None:
            df = df[df["region"] == region.strip().upper()].reset_index(drop=True)
        return df.copy()

    # ---- per region -------------------------------------------------------- #

    def state_load(self, region: str, state_abbrev: str) -> np.ndarray:
        """State hourly demand, shape (8760,), MW, validated at migration."""
        df = self._read(f"{self._region_dir(region)}/state_loads.parquet")
        abbrev = state_abbrev.strip().upper()
        sub = df[df["state"] == abbrev]
        if sub.empty:
            raise KeyError(
                f"state {state_abbrev!r} not in {region} store "
                f"(available: {sorted(df['state'].unique())})")
        series = (sub.sort_values("hour")["load_mw"]
                  .to_numpy(dtype=np.float64))
        if series.shape != (8760,):
            raise ValueError(f"{region}/{abbrev}: store holds {series.shape}, "
                             "expected (8760,)")
        return series

    def bus_table(self, region: str) -> pd.DataFrame:
        """Bus table: bus_number (= national numbering, as in the MATLAB bus
        xlsx column 1), national_bus_num (verified against the shared map),
        regional_bus_num, state_code, share_c/i/r (RENORMALIZED to sum to 1.0
        per state per class — C4/F3), raw_share_* originals, and
        state_peak_mw (xlsx col 16 'State Peak Load' — the per-state values
        whose sum is the KCL-KVL loadscaling peak target, D16/H5)."""
        return self._read(f"{self._region_dir(region)}/bus_table.parquet").copy()

    def cir_fractions(self, region: str) -> pd.DataFrame:
        """State C/I/R fractions: columns state, frac_c, frac_i, frac_r."""
        return self._read(f"{self._region_dir(region)}/cir_fractions.parquet").copy()

    def nrel_profiles(self, region: str, city_folder: str) -> np.ndarray:
        """(8760, 17) building profiles for one city, TMY column (index 17)
        already x1000-scaled, columns ordered by the canonical building index
        (regions/FRCC.md legend), NOT by directory order.

        ``city_folder`` accepts either the bare folder name ("Miami_Intl_AP")
        or the config form ("NREL_Profiles/Miami_Intl_AP").
        """
        city = city_folder.replace("\\", "/").rstrip("/").split("/")[-1]
        df = self._read(f"{self._region_dir(region)}/nrel_profiles.parquet")
        sub = df[df["city"] == city]
        if sub.empty:
            raise KeyError(
                f"city folder {city!r} not in {region} store "
                f"(available: {sorted(df['city'].unique())})")
        arr = np.full((8760, 17), np.nan)
        arr[sub["hour"].to_numpy() - 1,
            sub["building_idx"].to_numpy() - 1] = sub["value"].to_numpy(float)
        if np.isnan(arr).any():
            raise ValueError(f"{region}/{city}: store does not cover the full "
                             "(8760, 17) grid")
        return arr

    def utility_profiles(self, region: str, source_key: str) -> np.ndarray:
        """(365, 24) day-by-hour class profile (e.g. 'a1', 'opc_com').

        Source keys per HOOKS.md §3 (long-format utility_profiles.parquet,
        written by migrate_data._migrate_utility). Used by the utility
        archetype (CAISO/RFCW) and the mixed NWPP region (OR/WA fit against
        PG&E year-2000 a1/a10/e1 profiles).
        """
        df = self._read(f"{self._region_dir(region)}/utility_profiles.parquet")
        sub = df[df["source"] == source_key]
        if sub.empty:
            raise KeyError(
                f"utility source {source_key!r} not in {region} store "
                f"(available: {sorted(df['source'].unique())})")
        arr = np.full((365, 24), np.nan)
        arr[sub["day"].to_numpy() - 1,
            sub["hour"].to_numpy() - 1] = sub["value"].to_numpy(float)
        if np.isnan(arr).any():
            raise ValueError(f"{region}/{source_key}: store does not cover "
                             "the full (365, 24) grid")
        return arr
