"""Migration spec for CAISO (see scripts/migrate_data.py docstring).

Verified against the raw files (2026-07-10): the bus workbook
'California bus tracts with load apportionemnts.xlsx' (sic) does NOT use
the standard '<REGION> bus data.xlsx' layout — it carries the national-map
column order: col 1 Final National Bus Num, col 2 Initial Nat Bus Num,
col 3 REGIONAL bus num (hence regional_col=3), col 6 state code (all 1),
col 17 total_el_demand (the MATLAB LoadDist column), col 18 State Peak
Load (hence state_peak_col=18), share cols 26:28. Numeric matrix is
8034 x 32 — F2 RESOLVED: the MATLAB smoothing bound 1:8034 was exact.

CIR is HARD-CODED in the MATLAB (CA_CIR = [0.455 0.197 0.348], "from EIA
data") — no CIR block in the workbook -> cir_hardcoded.

Utility basis: PG&E year-2000 rate-class profiles (same files as NWPP's
OR/WA basis but CAISO's own copies): a1 = small commercial, a10 =
medium/industrial, e1 = residential. csvread(f,1) semantics; e1-2000.csv
is headerless so its first DATA day is dropped (day-shift quirk, same as
NWPP — faithful to MATLAB).
"""

REGION = "CAISO"

SPEC = {
    "bus_xlsx": "California bus tracts with load apportionemnts.xlsx",
    "states": ["CA"],
    "state_loads": {
        "CA": {"mat": "California.mat", "var": "CA", "xls": "CA_Houly_Load.xls"},
    },
    "state_code_col": 6,
    "state_codes": {1},
    "share_cols": (26, 27, 28),
    "regional_col": 3,          # col 2 is 'Initial Nat Bus Num' in this layout
    "state_peak_col": 18,
    "cir_hardcoded": {"CA": (0.455, 0.197, 0.348)},
    "expected_bus_count": 8034,
    "nrel_cities": {},
    "nrel_parse": None,
    "utility_profiles": {
        "a1": "a1-2000.csv",    # PG&E A-1  small commercial
        "a10": "a10-2000.csv",  # PG&E A-10 medium/industrial
        "e1": "e1-2000.csv",    # PG&E E-1  residential (headerless: day 1 dropped)
    },
}
