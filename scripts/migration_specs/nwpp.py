"""Migration spec for NWPP (see scripts/migrate_data.py docstring).

Auto-discovered by migrate_data.py: this module must export REGION (str)
and SPEC (dict). Added per region so regions never edit shared
files.

Verified against the raw files (2026-07-10): .mat variables ID/MT/OR/WA/WY,
all (8760,), no NaNs; the <XX>_Hourly_Load.xls files are (365, 24) and
match the .mat series bit-exactly (used as cross-checks). Bus xlsx numeric
matrix is 2977x31 (matches the MATLAB smoothing bound 1:2977); the MATLAB
reads CIR rows 1:6 cols 28:30 but row 6 is all-NaN and unused (5 states)
-> cir_rows = (1, 5). NREL folders (Boise/Billings/Cheyenne) hold the
original EnergyPlus exports (header row + Date/Time column) -> nrel_parse
= "skip_sum", 17 CSVs per city, TMY2 file present in each. NOTE the
building CSVs are borrowed climates: Boise folder = BOULDER CO buildings,
Billings AND Cheyenne = HELENA MT buildings; only the TMY file (building
17) is city-specific.

MIXED archetype: OR and WA are fit against PG&E year-2000 class profiles
(a1 = commercial, a10 = industrial, e1 = residential) — ACTIVELY used by
the MATLAB, not dead code -> "utility_profiles" key below. Quirk: a1/a10
have a header line + 366 data rows (leap year 2000); e1-2000.csv has NO
header, so MATLAB csvread(f,1) drops its first DATA day (the residential
basis is day-shifted by one). _migrate_utility reproduces this faithfully.
"""

REGION = "NWPP"

SPEC = {
    "bus_xlsx": "NWPP_bus_data.xlsx",
    "states": ["ID", "MT", "OR", "WA", "WY"],
    "state_loads": {
        "ID": {"mat": "Idaho.mat", "var": "ID", "xls": "ID_Hourly_Load.xls"},
        "MT": {"mat": "Montana.mat", "var": "MT", "xls": "MT_Hourly_Load.xls"},
        "OR": {"mat": "Oregon.mat", "var": "OR", "xls": "OR_Hourly_Load.xls"},
        "WA": {"mat": "Washington.mat", "var": "WA", "xls": "WA_Hourly_Load.xls"},
        "WY": {"mat": "Wyoming.mat", "var": "WY", "xls": "WY_Hourly_Load.xls"},
    },
    "state_code_col": 5,
    "state_codes": {1, 2, 3, 4, 5},
    "share_cols": (24, 25, 26),
    "cir_rows": (1, 5),
    "cir_cols": (28, 30),
    "expected_bus_count": 2977,
    "nrel_cities": {"Boise": "ID", "Billings": "MT", "Cheyenne": "WY"},
    "nrel_parse": "skip_sum",      # csvread(f,1,1), row-sum remaining cols
    "utility_profiles": {          # PG&E 2000 class profiles (OR/WA basis)
        "a1": "a1-2000.csv",       # commercial
        "a10": "a10-2000.csv",     # industrial
        "e1": "e1-2000.csv",       # residential (headerless: day 1 dropped)
    },
}
