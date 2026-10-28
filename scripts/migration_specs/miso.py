"""Migration spec for MISO (see scripts/migrate_data.py docstring).

Auto-discovered by migrate_data.py: this module must export REGION (str)
and SPEC (dict). Added per region so regions never edit shared
files.
"""

REGION = "MISO"

SPEC = {
    "bus_xlsx": "MISO bus data.xlsx",
    "states": ["IL", "IA", "MN", "WI"],
    "state_loads": {
        abbr: {"mat": "RawStateLoadProfiles.mat", "var": abbr}
        for abbr in ("IL", "IA", "MN", "WI")
    },
    "state_code_col": 5,
    "state_codes": {1, 2, 3, 4},
    "share_cols": (24, 25, 26),
    "cir_rows": (1, 4),
    "cir_cols": (28, 30),
    "expected_bus_count": 6672,    # MATLAB ambiguity B5: loops 1:6671 vs 1:6672
    "nrel_cities": {},
    "nrel_parse": None,
}
