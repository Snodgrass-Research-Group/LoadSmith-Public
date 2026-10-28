"""Migration spec for NEISO (see scripts/migrate_data.py docstring).

Auto-discovered by migrate_data.py: this module must export REGION (str)
and SPEC (dict). Added per region so regions never edit shared
files.

Raw-file notes (verified 2026-07-09): each state has a 365x24 hourly xls
(clean, no NaN) AND the .mat produced from it by xls2rawMat_NEISO.m — both
are listed so migration cross-checks them (as FRCC). Note the .mat file
name misspelling "Massachussetts.mat" (sic, from the MATLAB source).
"""

REGION = "NEISO"

SPEC = {
    "bus_xlsx": "NEISO bus data.xlsx",
    # state order == CIR block row order == state_code order (CT=1 .. VT=6)
    "states": ["CT", "ME", "MA", "NH", "RI", "VT"],
    "state_loads": {  # abbrev -> dict(xls=..., mat=..., var=...)
        "CT": {"xls": "CT_Hourly_Load.xls", "mat": "Connecticut.mat", "var": "CT"},
        "ME": {"xls": "ME_Hourly_Load.xls", "mat": "Maine.mat", "var": "ME"},
        "MA": {"xls": "MA_Hourly_Load.xls", "mat": "Massachussetts.mat", "var": "MA"},
        "NH": {"xls": "NH_Hourly_Load.xls", "mat": "NewHampshire.mat", "var": "NH"},
        "RI": {"xls": "RI_Hourly_Load.xls", "mat": "RhodeIsland.mat", "var": "RI"},
        "VT": {"xls": "VT_Hourly_Load.xls", "mat": "Vermont.mat", "var": "VT"},
    },
    "state_code_col": 5,
    "state_codes": {1, 2, 3, 4, 5, 6},
    "share_cols": (24, 25, 26),
    "cir_rows": (1, 6),
    "cir_cols": (28, 30),
    "expected_bus_count": 3370,
    "nrel_cities": {},             # pure NYSEG archetype — no NREL sections
    "nrel_parse": None,
}
