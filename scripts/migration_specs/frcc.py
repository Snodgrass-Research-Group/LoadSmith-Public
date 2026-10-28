"""Migration spec for FRCC (see scripts/migrate_data.py docstring).

Auto-discovered by migrate_data.py: this module must export REGION (str)
and SPEC (dict). Added per region so regions never edit shared
files.
"""

REGION = "FRCC"

SPEC = {
    "bus_xlsx": "FRCC bus data.xlsx",
    # state order == CIR block row order == state_code order
    "states": ["FL", "GA", "SC"],
    "state_loads": {  # abbrev -> dict(xls=..., mat=..., var=...)
        "FL": {"xls": "Florida.xls", "mat": "Florida.mat", "var": "FL"},
        "GA": {"xls": "GA_Hourly_Load.xls", "mat": "Georgia.mat", "var": "GA"},
        "SC": {"xls": "SC_Houly_Load.xls", "mat": "SouthCarolina.mat", "var": "SC"},
    },
    "state_code_col": 5,
    "state_codes": {1, 2, 3},
    "share_cols": (24, 25, 26),
    "cir_rows": (1, 3),
    "cir_cols": (27, 29),          # NB: 27:29, not 28:30 (other regions)
    "expected_bus_count": 7224,
    "nrel_cities": {  # city folder -> state abbrev
        "Miami_Intl_AP": "FL", "Atlanta_AP": "GA", "Charleston": "SC",
    },
    "nrel_parse": "col1",          # csvread(f), take column 1
}
