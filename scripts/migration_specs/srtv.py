"""Migration spec for SRTV (see scripts/migrate_data.py docstring).

Auto-discovered by migrate_data.py: this module must export REGION (str)
and SPEC (dict). Added per region so regions never edit shared
files.

Verified against the raw files (2026-07-10): .mat variables AL/KY/MS/TN,
all (8760,); Kentucky.mat has NaNs at hours 1587 & 7298 and Tennessee.mat
at hour 699 (1-based) — filled by linear interpolation at migration (the
2024 reference CSVs deviate on those days). Bus xlsx numeric matrix is
4451x31 (matches the MATLAB smoothing bound 1:4451); CIR block: the MATLAB
reads rows 1:6 cols 28:30 (an SRVC 6-state copy-paste) but only rows 1:4
are non-NaN, so cir_rows = (1, 4). NREL folders hold the original
EnergyPlus exports (header row + Date/Time column) -> nrel_parse =
"skip_sum", 17 CSVs per city, TMY2 weather file present in each.
"""

REGION = "SRTV"

SPEC = {
    "bus_xlsx": "SRTV bus data.xlsx",
    "states": ["AL", "KY", "MS", "TN"],
    "state_loads": {
        "AL": {"mat": "Alabama.mat", "var": "AL"},
        "KY": {"mat": "Kentucky.mat", "var": "KY"},
        "MS": {"mat": "Mississippi.mat", "var": "MS"},
        "TN": {"mat": "Tennessee.mat", "var": "TN"},
    },
    "state_code_col": 5,
    "state_codes": {1, 2, 3, 4},
    "share_cols": (24, 25, 26),
    "cir_rows": (1, 4),
    "cir_cols": (28, 30),
    "expected_bus_count": 4451,
    "nrel_cities": {
        "Birmingham": "AL", "Louisville": "KY",
        "Jackson": "MS", "Nashville": "TN",
    },
    "nrel_parse": "skip_sum",      # csvread(f,1,1), row-sum remaining cols
}
