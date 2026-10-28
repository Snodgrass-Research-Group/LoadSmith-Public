"""Migration spec for RFCW (see scripts/migrate_data.py docstring).

Verified against the raw files (2026-07-10): standard bus
workbook layout ('RFCW bus data.xlsx': col 1 national, col 2 regional,
col 5 state code IN=1/MI=2/OH=3, shares 24:26, CIR rows 1:3 cols 28:30,
state peak col 16). State loads: Indiana/Michigan/Ohio.mat, vars IN/MI/OH,
(1, 8760) each.

Utility basis: Ohio Power Company (OPC) 2016 class profiles drive ALL
three states' fits (docs/conversion_manual/regions/RFCW.md). MATLAB slices
the xlsread numeric matrix (3:367, 5:28) -> (365, 24); verified finite with
per-unit class-profile ranges (res 0.52-2.9, com 2.3-13.3, ind 19.3-43.9).
The CSP (Columbus Southern) files are comparison-only in the MATLAB
(incl. bug B10: ind_CS mistakenly re-reads CSP_com.xlsx) — NOT migrated.
"""

REGION = "RFCW"

SPEC = {
    "bus_xlsx": "RFCW bus data.xlsx",
    "states": ["IN", "MI", "OH"],
    "state_loads": {
        "IN": {"mat": "Indiana.mat", "var": "IN"},
        "MI": {"mat": "Michigan.mat", "var": "MI"},
        "OH": {"mat": "Ohio.mat", "var": "OH"},
    },
    "state_code_col": 5,
    "state_codes": {1, 2, 3},
    "share_cols": (24, 25, 26),
    "cir_rows": (1, 3),
    "cir_cols": (28, 30),
    "expected_bus_count": 7217,
    "nrel_cities": {},
    "nrel_parse": None,
    "utility_profiles": {
        "opc_res": {"xls": "OhioPowerCompanyClassLoadProfiles2016YTD_2-23-2017.xls",
                    "rows": (3, 367), "cols": (5, 28)},
        "opc_com": {"xls": "OPC_com.xlsx", "rows": (3, 367), "cols": (5, 28)},
        "opc_ind": {"xls": "OPC_ind.xlsx", "rows": (3, 367), "cols": (5, 28)},
    },
}
