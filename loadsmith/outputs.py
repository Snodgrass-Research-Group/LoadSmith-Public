"""Stage 7a — output writing (CSV / Parquet / in-memory only).

Output layout (decision D13 — hook H1 RESOLVED): column 1 is the **national
bus number** (the 'Final National Bus Num' from the Steve workbook — the
numbering the published WISPO-POP SyntheticElectricNetworkModels use;
verified against the Florida model, buses 27810+). Then 8760 hourly columns.
This matches the existing nationally-numbered reference CSVs in the
UW-Madison Synthetic Load folder. Regional bus numbers are carried in the
parquet output and RunResult for traceability.

Formats (decision D14): any subset of {"csv", "parquet"} — including NONE,
for callers that consume the arrays in memory via
:class:`loadsmith.core.RunResult` (e.g. feeding the KCL-KVL grid-generator
workflow, whose MATLAB version consumes [P_Load, Q_Load] matrices directly
and strips the bus-number column when present).

CSV compatibility notes:
- ``header=False`` reproduces MATLAB ``csvwrite`` (most reference files have
  no header; the 2024 FRCC P reference has a "bus Num" header row).
- MISO's MATLAB CSV lacked a bus column entirely (B8); LoadSmith always
  writes national bus numbers.

Every run writes/returns run metadata (seed, config hash, policies, version).

Spec: docs/conversion_manual/algorithms/07_outputs_validation.md.
Implemented.
"""

from __future__ import annotations

import json
from collections.abc import Collection
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import numpy as np
import pandas as pd

OutputFormat = Literal["csv", "parquet"]

HOURS_PER_YEAR = 8760


def _as_bus_numbers(arr: np.ndarray, name: str) -> np.ndarray:
    """Validate a 1-D integer bus-number array; return int64."""
    arr = np.asarray(arr)
    if arr.ndim != 1:
        raise ValueError(f"{name} must be 1-D; got shape {arr.shape}")
    if not np.issubdtype(arr.dtype, np.integer):
        raise ValueError(f"{name} must be an integer array; got {arr.dtype}")
    return arr.astype(np.int64, copy=False)


def _json_default(obj):
    """JSON fallback for numpy scalars/arrays, Paths, datetimes."""
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.floating):
        return float(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    return str(obj)


class OutputWriter:
    """Writes region results in the requested formats (possibly none)."""

    def __init__(
        self,
        output_dir: str | Path,
        *,
        formats: Collection[OutputFormat] = ("csv", "parquet"),
        csv_header: bool = True,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.formats = frozenset(formats)
        self.csv_header = csv_header
        unknown = self.formats - {"csv", "parquet"}
        if unknown:
            raise ValueError(f"unknown output formats: {sorted(unknown)}")

    def write_region(
        self,
        region: str,
        national_bus_numbers: np.ndarray,   # (n_bus,) int — output column 1
        regional_bus_numbers: np.ndarray,   # (n_bus,) int — parquet/metadata only
        p_load: np.ndarray,                 # (n_bus, 8760) MW
        q_load: np.ndarray,                 # (n_bus, 8760) Mvar
        run_metadata: dict,
    ) -> dict[str, Path]:
        """Write P/Q in each requested format + run_metadata.json.

        Returns {} when ``formats`` is empty (in-memory-only run) — the
        caller keeps the arrays via RunResult; nothing touches disk (no
        directory creation, no metadata file). Otherwise files land in
        ``output_dir/<REGION>/`` and the returned dict maps
        ``{"p_csv", "q_csv", "p_parquet", "q_parquet", "metadata"}`` (for
        whatever was written) to the paths.
        """
        region = str(region).strip().upper()
        if not region:
            raise ValueError("region must be a non-empty string")
        national = _as_bus_numbers(national_bus_numbers, "national_bus_numbers")
        regional = _as_bus_numbers(regional_bus_numbers, "regional_bus_numbers")
        p = np.asarray(p_load, dtype=np.float64)
        q = np.asarray(q_load, dtype=np.float64)
        if p.ndim != 2 or p.shape[1] != HOURS_PER_YEAR:
            raise ValueError(
                f"p_load must have shape (n_bus, {HOURS_PER_YEAR}); got {p.shape}")
        if q.shape != p.shape:
            raise ValueError(
                f"q_load shape {q.shape} does not match p_load shape {p.shape}")
        n_bus = p.shape[0]
        if national.shape != (n_bus,) or regional.shape != (n_bus,):
            raise ValueError(
                f"bus number arrays must have shape ({n_bus},); got "
                f"national {national.shape}, regional {regional.shape}")

        if not self.formats:
            return {}  # in-memory-only run (D14): nothing touches disk

        region_dir = self.output_dir / region
        region_dir.mkdir(parents=True, exist_ok=True)
        written: dict[str, Path] = {}

        if "csv" in self.formats:
            # pyarrow csv.write_csv instead of pandas to_csv: 5.1x faster at
            # identical shortest-repr float64 precision (benchmark,
            # SRVC-scale 1 GB file: 6.6 s vs 33.9 s; float_format
            # variants save size but no time). Rows end in \n like MATLAB
            # csvwrite (pandas on Windows wrote \r\n).
            import pyarrow as pa
            from pyarrow import csv as pacsv

            write_options = pacsv.WriteOptions(
                include_header=self.csv_header, quoting_style="none")
            for tag, values in (("P", p), ("Q", q)):
                path = region_dir / f"{tag}_Load_{region}.csv"
                table = pa.Table.from_pandas(
                    to_output_frame(national, values), preserve_index=False)
                pacsv.write_csv(table, str(path), write_options)
                written[f"{tag.lower()}_csv"] = path

        if "parquet" in self.formats:
            for tag, values in (("P", p), ("Q", q)):
                path = region_dir / f"{tag}_Load_{region}.parquet"
                frame = to_output_frame(national, values)
                # regional bus number carried for traceability (D13).
                frame.insert(1, "regional_bus_num", regional)
                frame.to_parquet(path, index=False)
                written[f"{tag.lower()}_parquet"] = path

        metadata = dict(run_metadata)
        from loadsmith import __version__  # lazy: avoids circular import

        metadata["loadsmith_version"] = __version__
        metadata["written_at"] = datetime.now(timezone.utc).isoformat()
        metadata["written_files"] = {
            key: path.name for key, path in written.items()}
        meta_path = region_dir / "run_metadata.json"
        meta_path.write_text(
            json.dumps(metadata, indent=2, default=_json_default),
            encoding="utf-8")
        written["metadata"] = meta_path
        return written


def to_output_frame(
    national_bus_numbers: np.ndarray, values: np.ndarray
) -> pd.DataFrame:
    """(n_bus, 8760) -> DataFrame with 'bus Num' + h0001..h8760 columns.

    Shared by the CSV/parquet writers and RunResult.p_frame()/q_frame() so
    every consumer sees the identical layout. 'bus Num' is int64 (the column
    name matches the 2024 FRCC reference CSV header); hourly columns are
    float64, labeled h0001..h8760 (D13).
    """
    bus = _as_bus_numbers(national_bus_numbers, "national_bus_numbers")
    vals = np.asarray(values, dtype=np.float64)
    if vals.ndim != 2:
        raise ValueError(f"values must be 2-D (n_bus, n_hours); got {vals.shape}")
    if vals.shape[0] != bus.shape[0]:
        raise ValueError(
            f"values has {vals.shape[0]} rows but "
            f"{bus.shape[0]} bus numbers were given")
    hour_cols = [f"h{h:04d}" for h in range(1, vals.shape[1] + 1)]
    frame = pd.DataFrame(vals, columns=hour_cols, copy=False)
    frame.insert(0, "bus Num", bus)
    return frame
