"""One-time raw-data migration: MATLAB-era inputs -> clean parquet store.

THE ONLY code allowed to parse Excel (.xls via xlrd, .xlsx via openpyxl),
.mat (scipy.io), and raw CSVs (decision D8). Everything downstream reads
data/ parquet via loadsmith.ingest.ParquetStore.

Scope: shared inputs (NYSEG profiles, national bus map) + regions
FRCC, MISO, SRVC, plus the utility-archetype regions CAISO and RFCW
(utility_profiles.parquet, HOOKS.md section 3).

Verified raw-file layouts (2026-07-09):

* ``<REGION> bus data.xlsx`` sheet 1 is NOT a bare numeric matrix: it has a
  text header row (dropped by MATLAB ``xlsread``) and its **column 1 is
  'Final National Bus Num'** — the bus tables already carry national bus
  numbers. Column 2 = 'Regional Bus Num' (gen+load regional numbering; FRCC
  load buses start at regional 217 -> national 28026 as in the reference
  P_Load_FRCC.csv). Column 5 = 'state' code; cols 24:26 = 'Bus % C/I/R';
  the state CIR block is 'Total C/I/R' (FRCC, cols 27:29) or a text 'State'
  col 27 + 'Total % C/I/R' cols 28:30 (MISO/SRVC). All rows are Load buses.
* FRCC state workbooks: 365 rows x (1 date text col + 24 hour cols); the
  numeric matrix is 365x24, flattened day-major (``reshape(X.',1,[])``).
  ⚠ Florida.xls cell (day 72, hour 3) is EMPTY -> NaN, and Florida.mat
  carries the same NaN; migration fills it by linear interpolation and
  records the repair (the 2024 reference P CSV is finite there).
* NREL CSVs, two different layouts (hence per-region parse modes):
  - FRCC folders: headerless pure-numeric CSVs, first column = precomputed
    row total of the remaining columns; MATLAB ``csvread(f)`` + column 1.
  - SRVC folders: original NREL EnergyPlus exports with a header row and a
    'Date/Time' first column; MATLAB ``csvread(f,1,1)`` + row-sum.
  TMY weather file (name contains 'TMY') scaled x1000, stored as building
  index 17; buildings 1..16 ordered by the canonical RefBldg list
  (docs/conversion_manual/regions/FRCC.md), matched by filename, never by
  directory order.

Raw sources are looked up in the repo region folders first, then the same
subpath under the external UW-Madison folder (loadsmith.locations).

Usage (once per machine, or after raw-data changes)::

    python scripts/migrate_data.py [--region FRCC] [--data-dir data]

Requires: pip install loadsmith[migrate]
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import scipy.io as sio

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from loadsmith import locations  # noqa: E402

# --------------------------------------------------------------------------- #
# Region specifications (verified against the raw files, see module docstring)
# --------------------------------------------------------------------------- #

# Canonical NREL building list, indices 1..16 (17 = TMY weather series x1000).
# docs/conversion_manual/regions/FRCC.md "Building-type index legend".
NREL_BUILDINGS: tuple[str, ...] = (
    "FullServiceRestaurant", "Hospital", "LargeHotel", "LargeOffice",
    "MediumOffice", "MidriseApartment", "OutPatient", "PrimarySchool",
    "QuickServiceRestaurant", "SecondarySchool", "SmallHotel", "SmallOffice",
    "Stand-aloneRetail", "StripMall", "SuperMarket", "Warehouse",
)

LOADSMITH_REGIONS = {
    "AZNM", "CAISO", "FRCC", "MISO", "NEISO", "NWPP", "NYISO",
    "RFCE", "RFCW", "SPP", "SRMV", "SRTV", "SRVC",
}

def _load_region_specs() -> dict[str, dict]:
    """Auto-discover per-region migration specs (scripts/migration_specs/).

    Each module there exports REGION (str) and SPEC (dict). One file per
    region so regions never conflict on this file.
    """
    import importlib.util

    specs: dict[str, dict] = {}
    for path in sorted((Path(__file__).parent / "migration_specs").glob("*.py")):
        if path.name.startswith("_"):
            continue
        spec = importlib.util.spec_from_file_location(f"migspec_{path.stem}", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        specs[mod.REGION] = mod.SPEC
    return specs


REGION_SPECS: dict[str, dict] = _load_region_specs()


# --------------------------------------------------------------------------- #
# Provenance / parquet helpers
# --------------------------------------------------------------------------- #


def _json_default(o):
    """Make numpy scalars JSON-serializable in migration reports."""
    if isinstance(o, np.generic):
        return o.item()
    raise TypeError(f"Object of type {type(o).__name__} is not JSON serializable")


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


#: Folder names a recorded source path is cut back to, so provenance never
#: carries a machine-specific prefix.
_PATH_ANCHORS = ("EPIGRIDS-Time-Series-Load-Code", "UW-Madison Synthetic Load",
                 "Synthetic-Grid-Generator")


def portable_path(path: str | Path) -> str:
    """``path`` from its last anchor folder on, with forward slashes; else
    relative to the repository, else the bare file name."""
    parts = Path(str(path).replace("\\", "/")).parts
    for i in range(len(parts) - 1, -1, -1):
        if parts[i] in _PATH_ANCHORS:
            return "/".join(parts[i:])
    try:
        return Path(path).resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return parts[-1] if parts else str(path)


def _provenance(path: Path) -> dict:
    st = path.stat()
    return {
        "path": portable_path(path),
        "sha256": _sha256(path),
        "mtime": _dt.datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds"),
    }


def _write_parquet(df: pd.DataFrame, path: Path, sources: list[dict],
                   extra: dict | None = None) -> None:
    """Write ``df`` with loadsmith provenance stamped into the schema metadata."""
    path.parent.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pandas(df, preserve_index=False)
    meta = dict(table.schema.metadata or {})
    meta[b"loadsmith_migration"] = json.dumps({
        "sources": sources,
        "migration_date": _dt.datetime.now().isoformat(timespec="seconds"),
        **(extra or {}),
    }).encode()
    pq.write_table(table.replace_schema_metadata(meta), path)


def _find_raw(region: str, relpath: str) -> Path:
    """Raw input: repo region folder first, else same subpath in the UW folder."""
    repo = REPO_ROOT / region / relpath
    if repo.exists():
        return repo
    external = locations.uw_load_dir() / region / relpath
    if external.exists():
        return external
    raise FileNotFoundError(
        f"{region}/{relpath} not found in repo ({repo}) or UW folder ({external})"
    )


# --------------------------------------------------------------------------- #
# MATLAB xlsread emulation
# --------------------------------------------------------------------------- #


def _xlsread_numeric(path: Path, sheet: int = 0) -> pd.DataFrame:
    """Emulate ``xlsread``'s numeric matrix: coerce to numeric, trim the
    bounding box of leading/trailing all-NaN rows and columns. The returned
    frame is reindexed 0..n-1 so MATLAB 1-based index k = ``.iloc[k-1]``."""
    engine = "openpyxl" if path.suffix.lower() == ".xlsx" else None
    raw = pd.read_excel(path, sheet_name=sheet, header=None, engine=engine)
    num = raw.apply(pd.to_numeric, errors="coerce")
    row_any = num.notna().any(axis=1).to_numpy()
    col_any = num.notna().any(axis=0).to_numpy()
    if not row_any.any():
        raise ValueError(f"{path}: no numeric cells")
    r0, r1 = np.argmax(row_any), len(row_any) - np.argmax(row_any[::-1])
    c0, c1 = np.argmax(col_any), len(col_any) - np.argmax(col_any[::-1])
    sub = num.iloc[r0:r1, c0:c1]
    sub.index = range(sub.shape[0])
    sub.columns = range(sub.shape[1])
    return sub


def _flatten_state_xls(path: Path) -> np.ndarray:
    """365x24 hourly workbook -> (8760,) day-major, as reshape(X.',1,[])."""
    num = _xlsread_numeric(path)
    if num.shape != (365, 24):
        raise ValueError(f"{path}: numeric matrix is {num.shape}, expected (365, 24)")
    return num.to_numpy(dtype=float).reshape(-1)  # C order == day-major


def _fill_nan_linear(series: np.ndarray) -> tuple[np.ndarray, list[int]]:
    """Fill NaNs by linear interpolation over the hour index; return filled
    copy + 0-based indices that were filled."""
    nan_idx = np.flatnonzero(np.isnan(series))
    if nan_idx.size == 0:
        return series, []
    out = series.copy()
    ok = np.flatnonzero(~np.isnan(series))
    out[nan_idx] = np.interp(nan_idx, ok, series[ok])
    return out, nan_idx.tolist()


# --------------------------------------------------------------------------- #
# Shared migration
# --------------------------------------------------------------------------- #


def migrate_shared(data_dir: str = "data") -> dict:
    """Migrate cross-region inputs (NYSEG profiles + national bus map)."""
    out_dir = Path(data_dir) / "shared"
    out_dir.mkdir(parents=True, exist_ok=True)
    report: dict = {"scope": "shared", "checks": {}}

    # ---- NYSEG profiles_aggregate (24 x 36 x 9) ------------------------- #
    nyseg_path = _find_raw("FRCC", "NYSEGloadprofiles2016.mat")
    mat = sio.loadmat(str(nyseg_path))
    arr = np.asarray(mat["profiles_aggregate"], dtype=float)
    if arr.shape != (24, 36, 9):
        raise ValueError(f"profiles_aggregate shape {arr.shape} != (24, 36, 9)")
    if not np.isfinite(arr).all():
        raise ValueError("profiles_aggregate contains non-finite values")
    hour, day_type, cls = np.meshgrid(
        np.arange(1, 25), np.arange(1, 37), np.arange(1, 10), indexing="ij"
    )
    nyseg_df = pd.DataFrame({
        "hour": hour.ravel().astype(np.int16),
        "day_type": day_type.ravel().astype(np.int16),
        "class": cls.ravel().astype(np.int16),
        "value": arr.ravel(),
    })
    src = _provenance(nyseg_path)
    _write_parquet(nyseg_df, out_dir / "nyseg_profiles.parquet", [src],
                   {"mat_variable": "profiles_aggregate", "shape": [24, 36, 9]})
    report["nyseg"] = {"rows": len(nyseg_df), "shape": [24, 36, 9], "source": src}

    # ---- National bus map (hook H1) -------------------------------------- #
    map_xlsx = locations.national_bus_map_xlsx()
    print(f"  reading national bus map (slow, ~1 min): {map_xlsx}")
    raw = pd.read_excel(
        map_xlsx, sheet_name="Entire US Load Data from Steve",
        engine="openpyxl",
        usecols=["Final National Bus Num", "Regional Bus Num", "Bus type",
                 "state", "Region", "Region Num"],
    )
    bus_map = raw.rename(columns={
        "Final National Bus Num": "national_bus_num",
        "Regional Bus Num": "regional_bus_num",
        "Bus type": "bus_type",
        "state": "state",
        "Region": "region",
        "Region Num": "region_num",
    })
    bus_map = bus_map[["region", "regional_bus_num", "national_bus_num",
                       "bus_type", "state", "region_num"]]
    bus_map["national_bus_num"] = bus_map["national_bus_num"].astype(np.int64)
    bus_map["regional_bus_num"] = bus_map["regional_bus_num"].astype(np.int64)
    bus_map["region_num"] = bus_map["region_num"].astype(np.int64)
    bus_map["region"] = bus_map["region"].astype(str)
    bus_map["bus_type"] = bus_map["bus_type"].astype(str)

    checks = report["checks"]
    checks["map_rows"] = {"actual": len(bus_map), "expected": 75432,
                          "pass": len(bus_map) == 75432}
    regions_found = set(bus_map["region"].unique())
    checks["all_13_regions"] = {
        "found": sorted(regions_found),
        "extra_non_loadsmith_regions": sorted(regions_found - LOADSMITH_REGIONS),
        "pass": LOADSMITH_REGIONS <= regions_found,
    }
    frcc = bus_map[bus_map["region"] == "FRCC"]
    frcc_ok = (
        len(frcc) == 7440
        and frcc["regional_bus_num"].min() == 1
        and frcc["regional_bus_num"].max() == 7440
        and frcc["national_bus_num"].min() == 27810
        and frcc["national_bus_num"].max() == 35249
        and (frcc["national_bus_num"] == frcc["regional_bus_num"] + 27809).all()
    )
    checks["frcc_block"] = {
        "rows": len(frcc),
        "regional_range": [int(frcc["regional_bus_num"].min()),
                           int(frcc["regional_bus_num"].max())],
        "national_range": [int(frcc["national_bus_num"].min()),
                           int(frcc["national_bus_num"].max())],
        "national_equals_regional_plus_27809": bool(
            (frcc["national_bus_num"] == frcc["regional_bus_num"] + 27809).all()),
        "pass": bool(frcc_ok),
    }
    failed = [k for k, v in checks.items() if not v.get("pass", True)]
    if failed:
        raise ValueError(f"national bus map validation failed: {failed}: {checks}")

    src = _provenance(map_xlsx)
    _write_parquet(bus_map, out_dir / "national_bus_map.parquet", [src],
                   {"sheet": "Entire US Load Data from Steve"})
    report["national_bus_map"] = {"rows": len(bus_map), "source": src}

    with open(out_dir / "migration_report.json", "w") as f:
        json.dump(report, f, indent=2, default=_json_default)
    return report


# --------------------------------------------------------------------------- #
# Per-region migration
# --------------------------------------------------------------------------- #


def _migrate_state_loads(region: str, spec: dict, out_dir: Path, report: dict) -> None:
    frames = []
    sources: list[dict] = []
    info: dict = {}
    seen_mats: dict[str, dict] = {}
    for abbrev in spec["states"]:
        entry = spec["state_loads"][abbrev]
        state_info: dict = {}

        mat_path = _find_raw(region, entry["mat"])
        if entry["mat"] not in seen_mats:
            seen_mats[entry["mat"]] = _provenance(mat_path)
            sources.append(seen_mats[entry["mat"]])
        mat_series = np.asarray(
            sio.loadmat(str(mat_path))[entry["var"]], dtype=float).ravel()
        if mat_series.size != 8760:
            raise ValueError(f"{region}/{abbrev}: .mat series len {mat_series.size}")
        state_info["mat_variable"] = entry["var"]

        if "xls" in entry:  # raw source preferred; cross-check against .mat
            xls_path = _find_raw(region, entry["xls"])
            sources.append(_provenance(xls_path))
            series = _flatten_state_xls(xls_path)
            both = ~np.isnan(series) & ~np.isnan(mat_series)
            state_info["cross_check"] = {
                "vs": entry["mat"],
                "nan_positions_match": bool(
                    np.array_equal(np.isnan(series), np.isnan(mat_series))),
                "max_abs_diff": float(np.max(np.abs(series[both] - mat_series[both]))),
                "allclose": bool(np.allclose(series[both], mat_series[both])),
            }
            if not state_info["cross_check"]["allclose"]:
                raise ValueError(f"{region}/{abbrev}: xls vs mat mismatch")
        else:
            series = mat_series

        series, filled = _fill_nan_linear(series)
        if filled:
            state_info["nan_hours_filled_linear"] = {
                "hours_1based": [i + 1 for i in filled],
                "fill_values": [float(series[i]) for i in filled],
            }
        if not np.isfinite(series).all():
            raise ValueError(f"{region}/{abbrev}: non-finite load after fill")
        if not (series > 0).all():
            raise ValueError(f"{region}/{abbrev}: non-positive load values")

        frames.append(pd.DataFrame({
            "state": abbrev,
            "hour": np.arange(1, 8761, dtype=np.int32),
            "load_mw": series,
        }))
        info[abbrev] = state_info

    df = pd.concat(frames, ignore_index=True)
    _write_parquet(df, out_dir / "state_loads.parquet", sources,
                   {"states": spec["states"]})
    report["state_loads"] = {"rows": len(df), "per_state": info}


def _migrate_bus_table(region: str, spec: dict, out_dir: Path, report: dict,
                       bus_map: pd.DataFrame) -> None:
    xlsx_path = _find_raw(region, spec["bus_xlsx"])
    src = _provenance(xlsx_path)
    num = _xlsread_numeric(xlsx_path)
    anchors: dict = {}
    report["bus_table"] = {"source": src, "anchors": anchors}

    def col(k: int) -> pd.Series:  # 1-based numeric-matrix column
        return num.iloc[:, k - 1]

    # --- anchor: column 1 = integer bus numbers -------------------------- #
    c1 = col(1)
    anchors["col1_integer_bus_numbers"] = {
        "pass": bool(c1.notna().all() and (c1 == c1.round()).all()),
        "min": int(c1.min()), "max": int(c1.max()),
        "note": "header 'Final National Bus Num' — bus table col 1 is the "
                "NATIONAL bus number, not the regional one (regional is col 2)",
    }

    # --- anchor: state codes --------------------------------------------- #
    c5 = col(spec["state_code_col"])
    codes_found = set(int(v) for v in c5.dropna().unique())
    anchors["state_codes"] = {
        "expected": sorted(spec["state_codes"]), "found": sorted(codes_found),
        "pass": codes_found == spec["state_codes"] and c5.notna().all(),
    }

    # --- anchor: share cols in [0, 1] ------------------------------------ #
    sc = spec["share_cols"]
    shares = num.iloc[:, [sc[0] - 1, sc[1] - 1, sc[2] - 1]].to_numpy(float)
    anchors["share_cols_in_0_1"] = {
        "cols": list(sc),
        "min": float(np.nanmin(shares)), "max": float(np.nanmax(shares)),
        "pass": bool(np.isfinite(shares).all()
                     and shares.min() >= 0.0 and shares.max() <= 1.0),
    }

    # --- anchor: row count ------------------------------------------------ #
    anchors["bus_row_count"] = {
        "expected_approx": spec["expected_bus_count"], "actual": int(num.shape[0]),
        "pass": abs(num.shape[0] - spec["expected_bus_count"]) <= 1,
    }

    bus_number = c1.astype(np.int64)
    # Regional bus number: col 2 in the standard '<REGION> bus data.xlsx'
    # layout; CAISO's tracts workbook carries the national-map column order
    # (col 2 = Initial Nat Bus Num, col 3 = Regional) -> spec override.
    regional = col(spec.get("regional_col", 2)).astype(np.int64)
    state_code = c5.astype(np.int32)

    # 'State Peak Load' (MW), one value per state repeated on every bus row
    # (col 16 standard; col 18 in CAISO's layout). The KCL-KVL function
    # variants compute their loadscaling target as sum(unique(col)) == the
    # sum of state peak loads (hook H5).
    state_peak = col(spec.get("state_peak_col", 16)).astype(float)

    df = pd.DataFrame({
        "bus_number": bus_number.to_numpy(),
        "regional_bus_num": regional.to_numpy(),   # documented extension
        "state_code": state_code.to_numpy(),
        "raw_share_c": shares[:, 0],
        "raw_share_i": shares[:, 1],
        "raw_share_r": shares[:, 2],
        "state_peak_mw": state_peak.to_numpy(),
    })
    per_state_peaks = df.groupby("state_code")["state_peak_mw"].nunique()
    anchors["state_peak_col16"] = {
        "pass": bool((per_state_peaks == 1).all()),
        "unique_values_per_state": per_state_peaks.to_dict(),
        "region_peak_target_mw": float(
            df.groupby("state_code")["state_peak_mw"].first().sum()),
    }

    # --- F3: which share convention does the raw file use? ---------------- #
    cir_df = _extract_cir(spec, num)
    f3: dict = {}
    for i, abbrev in enumerate(spec["states"]):
        code = i + 1
        sums = df.loc[df["state_code"] == code,
                      ["raw_share_c", "raw_share_i", "raw_share_r"]].sum()
        cir_row = cir_df.iloc[i][["frac_c", "frac_i", "frac_r"]].to_numpy(float)
        raw_sums = sums.to_numpy(float)
        f3[abbrev] = {
            "raw_col_sums_cir": [float(s) for s in raw_sums],
            "state_cir_fracs": [float(v) for v in cir_row],
            "sums_to_one": bool(np.allclose(raw_sums, 1.0, atol=0.02)),
            "sums_to_cir_fraction": bool(np.allclose(raw_sums, cir_row, atol=0.02)),
        }
    verdicts = {(v["sums_to_one"], v["sums_to_cir_fraction"]) for v in f3.values()}
    convention = ("sums_to_1_per_class" if verdicts == {(True, False)}
                  else "sums_to_cir_fraction" if verdicts == {(False, True)}
                  else "mixed_or_other")
    report["f3_share_convention"] = {"per_state": f3, "verdict": convention}

    # --- renormalize (C4): each state's class column sums to 1.0 ---------- #
    for rc, nc in [("raw_share_c", "share_c"), ("raw_share_i", "share_i"),
                   ("raw_share_r", "share_r")]:
        totals = df.groupby("state_code")[rc].transform("sum")
        if (totals <= 0).any():
            raise ValueError(f"{region}: zero column total for {rc}")
        df[nc] = df[rc] / totals

    # --- join national bus map -------------------------------------------- #
    region_map = bus_map[bus_map["region"] == region]
    join_report: dict = {}
    for filt, label in ((region_map[region_map["bus_type"] == "Load"], "bus_type=Load"),
                        (region_map, "unfiltered")):
        merged = df.merge(
            filt[["regional_bus_num", "national_bus_num", "bus_type"]],
            on="regional_bus_num", how="left", validate="one_to_one",
        )
        n_matched = int(merged["national_bus_num"].notna().sum())
        ok = n_matched == len(df)
        join_report[label] = {"matched": n_matched, "of": len(df), "pass": ok}
        if ok:
            join_report["used_filter"] = label
            agree = (merged["national_bus_num"].astype(np.int64)
                     == merged["bus_number"]).all()
            join_report["national_equals_bus_table_col1"] = bool(agree)
            if not agree:
                raise ValueError(f"{region}: joined national != bus table col 1")
            df["national_bus_num"] = merged["national_bus_num"].astype(np.int64)
            break
    else:
        raise ValueError(f"{region}: bus map join failed both ways: {join_report}")
    # gen+load numbering evidence: do any Gen-typed regional numbers appear?
    gens = region_map[region_map["bus_type"] == "Gen"]["regional_bus_num"]
    join_report["gen_plus_load_numbering"] = {
        "region_map_gen_buses": int(len(gens)),
        "bus_table_regional_min": int(df["regional_bus_num"].min()),
        "note": "regional numbering covers gen+load; bus table holds only "
                "the Load rows",
    }
    report["bus_table"]["map_join"] = join_report

    df = df[["bus_number", "national_bus_num", "regional_bus_num", "state_code",
             "share_c", "share_i", "share_r",
             "raw_share_c", "raw_share_i", "raw_share_r", "state_peak_mw"]]
    _write_parquet(df, out_dir / "bus_table.parquet", [src], {
        "column_semantics": {
            "bus_number": "bus xlsx numeric col 1 = Final National Bus Num "
                          "(MATLAB BusNums)",
            "regional_bus_num": "bus xlsx numeric col 2 (gen+load regional "
                                "numbering)",
            "share_*": "renormalized: sums to 1.0 per state per class (C4/F3)",
            "state_peak_mw": "bus xlsx numeric col 16 'State Peak Load', one "
                             "value per state; sum over states = the KCL-KVL "
                             "loadscaling peak target (H5)",
        },
        "f3_convention": convention,
    })
    report["bus_table"]["rows"] = len(df)

    # --- CIR fractions ------------------------------------------------------ #
    cir_checks = []
    for i, abbrev in enumerate(spec["states"]):
        row = cir_df.iloc[i][["frac_c", "frac_i", "frac_r"]].to_numpy(float)
        # Optional spec override for raw workbooks whose CIR row genuinely
        # does NOT sum to 1 (known case: SRMV Louisiana = 0.9025 — see
        # scripts/migration_specs/srmv.py). Default stays the strict 1.0.
        expected_sum = spec.get("cir_expected_sums", {}).get(abbrev, 1.0)
        cir_checks.append({
            "state": abbrev, "fracs": [float(v) for v in row],
            "sum": float(row.sum()),
            "expected_sum": expected_sum,
            "nonnegative": bool((row >= 0).all()),
            "sums_to_1_within_2pct": bool(abs(row.sum() - expected_sum) <= 0.02),
        })
    bad = [c for c in cir_checks if not (c["nonnegative"] and c["sums_to_1_within_2pct"])]
    if bad:
        raise ValueError(f"{region}: CIR rows invalid: {bad}")
    report["cir_fractions"] = {"rows": len(cir_df), "per_state": cir_checks}
    cir_origin = (
        "hard-coded in MATLAB (CA_CIR, 'from EIA data')"
        if "cir_hardcoded" in spec else
        f"numeric rows {spec['cir_rows'][0]}:{spec['cir_rows'][1]}, "
        f"cols {spec['cir_cols'][0]}:{spec['cir_cols'][1]}")
    _write_parquet(cir_df, out_dir / "cir_fractions.parquet", [src], {
        "block": cir_origin,
    })


def _extract_cir(spec: dict, num: pd.DataFrame) -> pd.DataFrame:
    if "cir_hardcoded" in spec:
        # CAISO: the MATLAB hard-codes CA_CIR = [0.455 0.197 0.348] ("from
        # EIA data") instead of reading it from the bus workbook.
        rows = [(s, *spec["cir_hardcoded"][s]) for s in spec["states"]]
        return pd.DataFrame(rows, columns=["state", "frac_c", "frac_i", "frac_r"])
    r0, r1 = spec["cir_rows"]
    c0, c1 = spec["cir_cols"]
    block = num.iloc[r0 - 1:r1, c0 - 1:c1].to_numpy(float)
    if np.isnan(block).any():
        raise ValueError(
            f"CIR block rows {r0}:{r1} cols {c0}:{c1} contains NaN — layout changed?")
    return pd.DataFrame({
        "state": spec["states"],
        "frac_c": block[:, 0],
        "frac_i": block[:, 1],
        "frac_r": block[:, 2],
    })


# --------------------------------------------------------------------------- #
# NREL profiles
# --------------------------------------------------------------------------- #


def _parse_nrel_csv(path: Path, mode: str) -> np.ndarray:
    """One NREL CSV -> (8760,) series, reproducing the region's MATLAB read.

    mode='col1'    : FRCC — headerless numeric CSV whose column 1 is a
                     precomputed row total; csvread(f) then column 1.
    mode='skip_sum': SRVC — original NREL export (header row + Date/Time
                     column); csvread(f,1,1) then row-sum the data columns.
    """
    if mode == "col1":
        df = pd.read_csv(path, header=None)
        series = pd.to_numeric(df.iloc[:, 0], errors="raise").to_numpy(float)
    elif mode == "skip_sum":
        df = pd.read_csv(path, skiprows=1, header=None)
        series = (df.iloc[:, 1:]
                  .apply(pd.to_numeric, errors="raise")
                  .to_numpy(float).sum(axis=1))
        if series.shape == (8759,) and path.name.startswith("aRefBldg"):
            # SRTV/Birmingham 'aRefBldg…' has NO header row and NO Date/Time
            # column, so MATLAB's csvread(f,1,1) drops its first DATA hour and
            # its first DATA column (Electricity:Facility); the preallocated
            # zeros(8760,1) buffer leaves hour 8760 = 0. The skiprows/iloc
            # above already reproduce the row/col drop — pad the final zero.
            series = np.append(series, 0.0)
    else:
        raise ValueError(f"unknown NREL parse mode {mode!r}")
    if series.shape != (8760,):
        raise ValueError(f"{path}: parsed {series.shape}, expected (8760,)")
    if not np.isfinite(series).all():
        raise ValueError(f"{path}: non-finite values")
    return series


def _migrate_nrel(region: str, spec: dict, out_dir: Path, report: dict) -> None:
    if not spec["nrel_cities"]:
        return
    frames = []
    sources: list[dict] = []
    nrel_report: dict = {"parse_mode": spec["nrel_parse"], "cities": {}}
    for city, state in spec["nrel_cities"].items():
        folder = _find_raw(region, f"NREL_Profiles/{city}")
        files = sorted(p.name for p in folder.glob("*.csv"))
        if len(files) != 17:
            raise ValueError(f"{region}/{city}: {len(files)} CSVs, expected 17")
        tmy = [f for f in files if "TMY" in f.upper()]
        if len(tmy) != 1:
            raise ValueError(f"{region}/{city}: expected exactly 1 TMY file, got {tmy}")
        tmy_file = tmy[0]

        # buildings 1..16 by canonical name (never directory order)
        by_index: dict[int, str] = {}
        others = [f for f in files if f != tmy_file]
        for f in others:
            # SRTV/Birmingham holds a stray 'aRefBldgFullServiceRestaurant…'
            # (leading 'a', present in the repo AND UW archives) — strip the
            # prefix for name matching only; the stored building is still
            # canonical index 1. ⚠ The prefix changes MATLAB's dir() order
            # for Alabama — see docs/conversion_manual/regions/SRTV.md.
            stem = f[1:] if f.startswith("aRefBldg") else f
            hits = [i + 1 for i, b in enumerate(NREL_BUILDINGS)
                    if stem.startswith(f"RefBldg{b}New")]
            if len(hits) != 1:
                raise ValueError(f"{region}/{city}: {f} matched buildings {hits}")
            if hits[0] in by_index:
                raise ValueError(f"{region}/{city}: duplicate building idx {hits[0]}")
            by_index[hits[0]] = f
        if sorted(by_index) != list(range(1, 17)):
            raise ValueError(f"{region}/{city}: missing buildings "
                             f"{set(range(1, 17)) - set(by_index)}")
        by_index[17] = tmy_file

        mat = np.empty((8760, 17))
        for idx in range(1, 18):
            fpath = folder / by_index[idx]
            series = _parse_nrel_csv(fpath, spec["nrel_parse"])
            if idx == 17:
                series = series * 1000.0
            mat[:, idx - 1] = series
            sources.append(_provenance(fpath))

        hour = np.tile(np.arange(1, 8761, dtype=np.int32), 17)
        bidx = np.repeat(np.arange(1, 18, dtype=np.int16), 8760)
        frames.append(pd.DataFrame({
            "state": state, "city": city,
            "building_idx": bidx, "hour": hour,
            "value": mat.T.reshape(-1),  # building-major to match bidx/hour
        }))
        nrel_report["cities"][city] = {
            "state": state, "n_files": len(files), "tmy_file": tmy_file,
            "building_files": {str(i): by_index[i] for i in range(1, 18)},
        }

    df = pd.concat(frames, ignore_index=True)
    _write_parquet(df, out_dir / "nrel_profiles.parquet", sources, {
        "parse_mode": spec["nrel_parse"],
        "tmy_scaling": "x1000 applied (building_idx 17)",
    })
    nrel_report["rows"] = len(df)
    report["nrel_profiles"] = nrel_report


# --------------------------------------------------------------------------- #
# Utility class profiles (utility archetype: CAISO/RFCW; mixed: NWPP OR/WA)
# --------------------------------------------------------------------------- #


def _migrate_utility(region: str, spec: dict, out_dir: Path, report: dict) -> None:
    """(365, 24) day-by-hour class profiles -> utility_profiles.parquet.

    ``spec["utility_profiles"]`` maps a source key (HOOKS.md §3: "a1",
    "a10", "e1", "opc_com", ...) to a CSV relpath in the region folder.
    Reproduces MATLAB ``csvread(file, 1)``: the first LINE is skipped
    unconditionally. ⚠ NWPP quirk: a1/a10-2000.csv have a header line +
    366 data rows (leap year 2000) but e1-2000.csv has NO header, so the
    skip drops its first DATA day — faithful to the MATLAB read (the res
    basis is day-shifted by one). MATLAB then indexes rows 1:365 and
    columns 1:24; rows/columns beyond that are dropped here too (recorded).
    """
    frames = []
    sources: list[dict] = []
    util_report: dict = {"sources": {}}
    for key, entry in spec["utility_profiles"].items():
        if isinstance(entry, dict):
            # xls-slice mode (RFCW OPC workbooks): MATLAB xlsread numeric
            # matrix sliced 1-based-inclusive, e.g. rows (3, 367) cols
            # (5, 28) -> (365, 24). Verified: values finite and in per-unit
            # class-profile range.
            relpath = entry["xls"]
            path = _find_raw(region, relpath)
            sources.append(_provenance(path))
            num = _xlsread_numeric(path).to_numpy(float)
            r0, r1 = entry["rows"]
            c0, c1 = entry["cols"]
            mat = num[r0 - 1:r1, c0 - 1:c1]
            skipped = f"xls slice rows {r0}:{r1} cols {c0}:{c1}"
            if mat.shape != (365, 24):
                raise ValueError(
                    f"{region}/{relpath}: slice gave {mat.shape}, need (365, 24)")
        else:
            relpath = entry
            path = _find_raw(region, relpath)
            sources.append(_provenance(path))
            with open(path, "rb") as f:
                first = f.readline().decode("utf-8-sig", "replace").split(",", 1)[0]
            try:
                float(first)
                skipped = "data_row"   # e1-2000.csv: headerless, day 1 dropped
            except ValueError:
                skipped = "header_row"  # a1/a10-2000.csv
            df = pd.read_csv(path, skiprows=1, header=None)
            num = df.apply(pd.to_numeric, errors="raise").to_numpy(float)
            if num.shape[0] < 365 or num.shape[1] < 24:
                raise ValueError(
                    f"{region}/{relpath}: parsed {num.shape}, need >= (365, 24)")
            mat = num[:365, :24]
        if not np.isfinite(mat).all():
            raise ValueError(f"{region}/{relpath}: non-finite values")
        day = np.repeat(np.arange(1, 366, dtype=np.int16), 24)
        hour = np.tile(np.arange(1, 25, dtype=np.int16), 365)
        frames.append(pd.DataFrame({
            "source": key, "day": day, "hour": hour, "value": mat.reshape(-1),
        }))
        util_report["sources"][key] = {
            "file": relpath,
            "first_line_skipped": skipped,
            "rows_parsed": int(num.shape[0]),
            "rows_beyond_365_dropped": int(num.shape[0] - 365),
            "cols_parsed": int(num.shape[1]),
            "value_range": [float(mat.min()), float(mat.max())],
        }

    df = pd.concat(frames, ignore_index=True)
    _write_parquet(df, out_dir / "utility_profiles.parquet", sources, {
        "read_rule": "csvread(f,1) emulation: first line skipped, rows 1:365, "
                     "cols 1:24 (see per-source first_line_skipped)",
    })
    util_report["rows"] = len(df)
    report["utility_profiles"] = util_report


# --------------------------------------------------------------------------- #
# Region driver / CLI
# --------------------------------------------------------------------------- #


def migrate_region(region: str, data_dir: str = "data") -> dict:
    """Migrate one region's inputs; return its migration report dict."""
    region = region.upper()
    if region not in REGION_SPECS:
        raise ValueError(f"region {region!r} not supported "
                         f"(available: {sorted(REGION_SPECS)})")
    spec = REGION_SPECS[region]
    out_dir = Path(data_dir) / region.lower()
    out_dir.mkdir(parents=True, exist_ok=True)
    report: dict = {"scope": region}

    map_path = Path(data_dir) / "shared" / "national_bus_map.parquet"
    if not map_path.exists():
        raise FileNotFoundError(
            f"{map_path} missing — run shared migration first (no --region, "
            "or run once without arguments)")
    bus_map = pq.read_table(map_path).to_pandas()

    _migrate_state_loads(region, spec, out_dir, report)
    _migrate_bus_table(region, spec, out_dir, report, bus_map)
    _migrate_nrel(region, spec, out_dir, report)
    if spec.get("utility_profiles"):
        _migrate_utility(region, spec, out_dir, report)

    with open(out_dir / "migration_report.json", "w") as f:
        json.dump(report, f, indent=2, default=_json_default)
    return report


def main(argv: list[str] | None = None) -> int:
    """CLI entry point for the one-time raw-data -> parquet migration.

    With ``--region`` migrates a single region (building the shared national
    bus map first if it is missing); otherwise migrates the shared inputs plus
    the default wave-1a regions. Returns ``0`` on success.
    """
    parser = argparse.ArgumentParser(
        description="One-time raw-data migration to the parquet store "
                    "(HOOKS.md section 3)")
    parser.add_argument("--region", help="single region (default: shared + "
                        "FRCC, MISO, SRVC)")
    parser.add_argument("--data-dir", default="data")
    args = parser.parse_args(argv)

    t0 = time.perf_counter()
    if args.region:
        # region-only rerun still needs the shared map; build it if absent
        map_path = Path(args.data_dir) / "shared" / "national_bus_map.parquet"
        if not map_path.exists():
            print("== shared (required by region migration) ==")
            migrate_shared(args.data_dir)
        print(f"== {args.region.upper()} ==")
        migrate_region(args.region, args.data_dir)
    else:
        print("== shared ==")
        migrate_shared(args.data_dir)
        for region in REGION_SPECS:
            print(f"== {region} ==")
            migrate_region(region, args.data_dir)
    print(f"done in {time.perf_counter() - t0:.1f}s -> {args.data_dir}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
