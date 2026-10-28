"""External data locations (large files that live OUTSIDE this repo).

The user keeps multi-hundred-MB reference outputs and consumer code in other
folders (decision D15). Each path is set by an environment variable; the
defaults are sibling folders of this clone.

| What | Env var | Contains |
|------|---------|----------|
| UW-Madison Synthetic Load | LOADSMITH_UW_LOAD_DIR | per-region folders with the reference P_Load_/Q_Load_<R>.csv (NATIONAL bus numbers in col 1), raw MATLAB inputs, 'Entire US Load Data from Steve, Modified.xlsx' (the regional->national bus map), and EI/WECC bus-mapping folders |
| KCL-KVL Compliant Grid Generator | LOADSMITH_KCLKVL_DIR | READ-ONLY (decision D12) downstream consumer: calls MakeLoadProfiles_<R>() expecting [P_Load, Q_Load], strips column 1 when it is bus numbers |

The national bus map source workbook (hook H1, RESOLVED):
sheet 'Entire US Load Data from Steve' — col A 'Final National Bus Num'
(the numbering used by the published WISPO-POP SyntheticElectricNetworkModels;
verified: Florida model buses 27810+ == FRCC block), col C 'Regional Bus Num',
col D bus type (Gen/Load), col F state, col G region, col H region number.
Migrated once to data/shared/national_bus_map.parquet.
"""

from __future__ import annotations

import os
from pathlib import Path

_PARENT = Path(__file__).resolve().parents[2]   # the folder holding this clone
_UW_DEFAULT = _PARENT / "UW-Madison Synthetic Load"
_KCLKVL_DEFAULT = (_PARENT / "Synthetic-Grid-Generator"
                   / "KCL-KVL Compliant Grid Generator")


def uw_load_dir() -> Path:
    """UW-Madison Synthetic Load folder (raw data + reference outputs)."""
    return Path(os.environ.get("LOADSMITH_UW_LOAD_DIR", _UW_DEFAULT))


def kclkvl_dir() -> Path:
    """KCL-KVL Compliant Grid Generator folder — NEVER write here (D12)."""
    return Path(os.environ.get("LOADSMITH_KCLKVL_DIR", _KCLKVL_DEFAULT))


def national_bus_map_xlsx() -> Path:
    """The regional->national bus number mapping workbook (hook H1)."""
    return uw_load_dir() / "Entire US Load Data from Steve, Modified.xlsx"


def reference_dir(region: str | None = None) -> Path:
    """Reference P/Q CSVs live inside the UW folder's region subfolders.

    An in-repo override (validation/reference_outputs/<REGION>/) is checked
    first by the Validator so small excerpts can be committed for CI.
    """
    base = uw_load_dir()
    return base / region if region else base
