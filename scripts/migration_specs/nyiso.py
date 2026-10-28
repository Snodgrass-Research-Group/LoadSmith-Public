"""Migration spec for NYISO (see scripts/migrate_data.py docstring).

Auto-discovered by migrate_data.py: this module must export REGION (str)
and SPEC (dict). Added per region so regions never edit shared
files.

Raw-file notes (verified 2026-07-09): NewYork.xls is a clean 365x24 hourly
workbook; NewYork.mat (var 'NY') was produced from it by xls2rawMat_NYISO.m
— both are listed so migration cross-checks them.
"""

REGION = "NYISO"

SPEC = {
    "bus_xlsx": "NYISO bus data.xlsx",
    "states": ["NY"],
    "state_loads": {
        "NY": {"xls": "NewYork.xls", "mat": "NewYork.mat", "var": "NY"},
    },
    "state_code_col": 5,
    "state_codes": {1},
    "share_cols": (24, 25, 26),
    "cir_rows": (1, 1),
    "cir_cols": (27, 29),          # NB: 27:29 like FRCC, not 28:30
    "expected_bus_count": 4880,
    "nrel_cities": {},             # pure NYSEG archetype — no NREL sections
    "nrel_parse": None,
}
