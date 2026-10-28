"""Migration spec for AZNM (see scripts/migrate_data.py docstring).

Auto-discovered by migrate_data.py: this module must export REGION (str)
and SPEC (dict). Added per region so regions never edit shared
files.

Raw-layout notes (verified 2026-07-10):

* State workbooks are clean 365x24 numeric matrices matching their .mat
  series exactly (max |diff| = 0) — both listed for the migration
  cross-check.
* All five NREL city folders hold 17 EnergyPlus-export CSVs -> "skip_sum".
  Salt_Lake_City contains BOULDER (5B) building CSVs + the Salt Lake City
  TMY (same donor-city pattern as SRVC "Charleston"). Las_Vegas building
  files use a "New2004_7.1_5.0_3B" name variant (no "_v1.3") — still
  matched by the RefBldg<Name>New prefix rule.
* Bus xlsx has 4,536 numeric rows, matching the MATLAB smoothing loop
  1:4536. The MATLAB reads the CIR block as rows 1:6 x cols 28:30 but the
  region has only 5 states — row 6 is all-NaN padding (harmless copy-paste
  from a 6-state region); the spec reads rows 1:5. CIR values match the
  per-state share-column sums (F3 convention #2).
"""

REGION = "AZNM"

SPEC = {
    "bus_xlsx": "AZNM bus data.xlsx",
    # state order == CIR block row order == state_code order
    "states": ["AZ", "CO", "NV", "NM", "UT"],
    "state_loads": {  # abbrev -> dict(xls=..., mat=..., var=...)
        "AZ": {"xls": "AZ_Hourly_Load.xls", "mat": "Arizona.mat", "var": "AZ"},
        "CO": {"xls": "CO_Hourly_Load.xls", "mat": "Colorado.mat", "var": "CO"},
        "NV": {"xls": "NV_Hourly_Load.xls", "mat": "Nevada.mat", "var": "NV"},
        "NM": {"xls": "NM_Hourly_Load.xls", "mat": "NewMexico.mat", "var": "NM"},
        "UT": {"xls": "UT_Hourly_Load.xls", "mat": "Utah.mat", "var": "UT"},
    },
    "state_code_col": 5,
    "state_codes": {1, 2, 3, 4, 5},
    "share_cols": (24, 25, 26),
    "cir_rows": (1, 5),            # MATLAB reads 1:6; row 6 is NaN padding
    "cir_cols": (28, 30),
    "expected_bus_count": 4536,    # matches the MATLAB loop bound 1:4536
    "nrel_cities": {  # city folder -> state abbrev
        "Phoenix": "AZ", "Boulder": "CO", "Las_Vegas": "NV",
        "Albuquerque": "NM", "Salt_Lake_City": "UT",
    },
    "nrel_parse": "skip_sum",      # csvread(f,1,1), row-sum remaining cols
}
