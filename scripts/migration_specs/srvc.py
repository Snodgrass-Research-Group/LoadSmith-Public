"""Migration spec for SRVC (see scripts/migrate_data.py docstring).

Auto-discovered by migrate_data.py: this module must export REGION (str)
and SPEC (dict). Added per region so regions never edit shared
files.
"""

REGION = "SRVC"

SPEC = {
    "bus_xlsx": "SRVC bus data.xlsx",
    "states": ["DL", "DC", "MY", "NC", "VG", "WV"],
    "state_loads": {
        "DL": {"mat": "Delaware.mat", "var": "DL"},
        "DC": {"mat": "DistrictofColumbia.mat", "var": "DC"},
        "MY": {"mat": "Maryland.mat", "var": "MY"},
        "NC": {"mat": "NorthCarolina.mat", "var": "NC"},
        "VG": {"mat": "Virginia.mat", "var": "VG"},
        "WV": {"mat": "WestVirginia.mat", "var": "WV"},
    },
    "state_code_col": 5,
    "state_codes": {1, 2, 3, 4, 5, 6},
    "share_cols": (24, 25, 26),
    "cir_rows": (1, 6),
    "cir_cols": (28, 30),
    "expected_bus_count": 6340,
    "nrel_cities": {
        "Wilmington": "DL", "DC": "DC", "Baltimore": "MY",
        "Charlotte": "NC", "Richmond": "VG", "Charleston": "WV",
    },
    "nrel_parse": "skip_sum",      # csvread(f,1,1), row-sum remaining cols
}
