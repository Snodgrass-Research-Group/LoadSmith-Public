"""Migration spec for SPP (see scripts/migrate_data.py docstring).

Auto-discovered by migrate_data.py: this module must export REGION (str)
and SPEC (dict). Added per region so regions never edit shared
files.

Raw-layout notes (verified 2026-07-10):

* State workbooks are clean 365x24 numeric matrices matching their .mat
  series exactly (max |diff| = 0) — both are listed so migration
  cross-checks them (xls preferred, .mat verified against it).
* ``ERCOT Backcasted Load Profiles 2016.xls`` in the SPP folder is DEAD:
  the canonical script loads Texas.mat, which xls2rawMat_SPP.m builds from
  TX_Hourly_Load.xls (byte-identical to the .mat). The ERCOT workbook is a
  22568x96 15-minute backcast — not a pipeline input; do not migrate.
* All six NREL city folders hold 17 EnergyPlus-export CSVs (header row +
  Date/Time column) -> parse mode "skip_sum" (csvread(f,1,1) + row-sum).
  Building CSVs are climate-zone donors, not local: Wichita=Baltimore 4A,
  Omaha=Chicago-O'Hare 5A, Fargo=Duluth 7A, Oklahoma_City=Atlanta 3A,
  Sioux_Falls=Minneapolis 6A; only Houston is its own city. TMY files ARE
  local (Wichita/Omaha/Fargo/OKC/Sioux Falls/Houston).
* Bus xlsx has 8,025 numeric rows — NOT the 3,123 hard-coded in the MATLAB
  smoothing/LoadDist loops (copy-paste from SRMV; flag F1 resolved). The
  CIR block is rows 1:6, cols 28:30 and matches the per-state share-column
  sums (F3 convention #2, same as every region checked so far).
"""

REGION = "SPP"

SPEC = {
    "bus_xlsx": "SPP bus data.xlsx",
    # state order == CIR block row order == state_code order
    "states": ["KS", "NB", "ND", "OK", "SD", "TX"],
    "state_loads": {  # abbrev -> dict(xls=..., mat=..., var=...)
        "KS": {"xls": "KAN_Houly_Load.xls", "mat": "Kansas.mat", "var": "KS"},
        "NB": {"xls": "NEB_Houly_Load.xls", "mat": "Nebraska.mat", "var": "NB"},
        "ND": {"xls": "ND_Houly_Load.xls", "mat": "NorthDakota.mat", "var": "ND"},
        "OK": {"xls": "OK_Houly_Load.xls", "mat": "Oklahoma.mat", "var": "OK"},
        "SD": {"xls": "SD_Houly_Load.xls", "mat": "SouthDakota.mat", "var": "SD"},
        "TX": {"xls": "TX_Hourly_Load.xls", "mat": "Texas.mat", "var": "TX"},
    },
    "state_code_col": 5,
    "state_codes": {1, 2, 3, 4, 5, 6},
    "share_cols": (24, 25, 26),
    "cir_rows": (1, 6),
    "cir_cols": (28, 30),
    "expected_bus_count": 8025,    # actual xlsx rows; MATLAB's 3123 was wrong (F1)
    "nrel_cities": {  # city folder -> state abbrev
        "Wichita": "KS", "Omaha": "NB", "Fargo": "ND",
        "Oklahoma_City": "OK", "Sioux_Falls": "SD", "Houston": "TX",
    },
    "nrel_parse": "skip_sum",      # csvread(f,1,1), row-sum remaining cols
}
