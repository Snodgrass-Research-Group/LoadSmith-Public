"""Migration spec for SRMV (see scripts/migrate_data.py docstring).

Auto-discovered by migrate_data.py: this module must export REGION (str)
and SPEC (dict). Added per region so regions never edit shared
files.

Verified against the raw files (2026-07-10): .mat variables AR/LO/MO, all
(8760,), no NaNs. Bus xlsx numeric matrix is 3123x31 — exactly the MATLAB
smoothing bound 1:3123, resolving flag F1 for SRMV (whether SPP's identical
bound is a copy-paste stays open until SPP migrates). CIR block: the MATLAB
reads rows 1:6 cols 28:30 (an SRVC 6-state copy-paste) but only rows 1:3
are non-NaN, so cir_rows = (1, 3). NREL folders hold the original
EnergyPlus exports (header row + Date/Time column) -> nrel_parse =
"skip_sum", 17 CSVs per city, TMY2 weather file present in each.

⚠ Louisiana CIR anomaly (real data, used verbatim by the MATLAB): the
'Total % C/I/R' row for LA sums to 0.9025, not 1.0 — hence the
cir_expected_sums entry below (the migration otherwise validates every CIR
row against 1.0 ± 2%). The raw bus share columns for LA sum to the same
0.9025 fractions (F3 convention #2 holds), so share renormalization (C4)
is unaffected. See loadsmith/regions/srmv.py and
docs/conversion_manual/regions/SRMV.md for the downstream consequences.
"""

REGION = "SRMV"

SPEC = {
    "bus_xlsx": "SRMV bus data.xlsx",
    "states": ["AR", "LO", "MO"],
    "state_loads": {
        "AR": {"mat": "Arkansas.mat", "var": "AR"},
        "LO": {"mat": "Louisiana.mat", "var": "LO"},
        "MO": {"mat": "Missouri.mat", "var": "MO"},
    },
    "state_code_col": 5,
    "state_codes": {1, 2, 3},
    "share_cols": (24, 25, 26),
    "cir_rows": (1, 3),
    "cir_cols": (28, 30),
    "expected_bus_count": 3123,
    "nrel_cities": {
        "Little_Rock": "AR", "New_Orleans": "LO", "Kansas_City": "MO",
    },
    "nrel_parse": "skip_sum",      # csvread(f,1,1), row-sum remaining cols
    # LA's raw CIR row genuinely sums to 0.9025 (see module docstring);
    # validate it against that known value instead of 1.0.
    "cir_expected_sums": {"LO": 0.9025},
}
