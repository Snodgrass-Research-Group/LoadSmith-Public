"""Migration spec for RFCE (see scripts/migrate_data.py docstring).

Auto-discovered by migrate_data.py: this module must export REGION (str)
and SPEC (dict). Added per region so regions never edit shared
files.

Verified against the raw files (2026-07-10): .mat variables NJ/PN, both
(8760,); NewJersey.mat has NaNs at hours 1587 & 7298 (1-based; the same
hours as SRTV Kentucky — a shared collection gap) — filled by linear
interpolation at migration. NJ_Hourly_Load.xls / Penn_Hourly_Load.xls are
(365, 24) and match the .mat series bit-exactly (incl. NaN positions) —
used as cross-checks. Bus xlsx numeric matrix is 5218x31 (matches the
MATLAB smoothing bound 1:5218); CIR block rows 1:2 cols 28:30. NREL
folders (Newark/Philadelphia) hold the original EnergyPlus exports
(header row + Date/Time column) -> nrel_parse = "skip_sum"; 17 CSVs per
city (the stray Newark/test.m is not matched by the *.csv glob). NOTE
both cities' building CSVs are the BALTIMORE MD set; only the TMY file
(building 17) is city-specific (Newark / Philadelphia TMY2).
"""

REGION = "RFCE"

SPEC = {
    "bus_xlsx": "RFCE bus data.xlsx",
    "states": ["NJ", "PN"],
    "state_loads": {
        "NJ": {"mat": "NewJersey.mat", "var": "NJ", "xls": "NJ_Hourly_Load.xls"},
        "PN": {"mat": "Pennsylvania.mat", "var": "PN",
               "xls": "Penn_Hourly_Load.xls"},
    },
    "state_code_col": 5,
    "state_codes": {1, 2},
    "share_cols": (24, 25, 26),
    "cir_rows": (1, 2),
    "cir_cols": (28, 30),
    "expected_bus_count": 5218,
    "nrel_cities": {"Newark": "NJ", "Philadelphia": "PN"},
    "nrel_parse": "skip_sum",      # csvread(f,1,1), row-sum remaining cols
}
