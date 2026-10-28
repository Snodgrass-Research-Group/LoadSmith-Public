"""FRCC region config (PILOT) — Florida, Georgia, South Carolina.

Provenance: FRCC/MakeLoadProfiles_FRCC_NEW.m (canonical, original analysis).
Full extraction notes: docs/conversion_manual/regions/FRCC.md.

Archetype: the OUTPUT-driving fit is NYSEG-basis (profiles_aggregate slices
2/3/5, day-type calendar). The NREL clustering/aggregation in the MATLAB
script feeds a comparison-only fit (bug/finding B4); its frozen groups are
preserved below (COMPARISON_NREL) for reference and for the optional
analysis tools, but the production pipeline does not use them.

MATLAB-faithful validation notes: residual policy in the MATLAB is
effectively "drop" (the `; +` typo, bug B3); LoadSmith default here is
"residential" (the evident intent, matching MISO/NYISO/RFCW). Use
residual="drop" when regressing against the old P_Load_FRCC.csv.
"""

from __future__ import annotations

from loadsmith.config import (
    BasisKind,
    BusTableSpec,
    NRELBasisSpec,
    RegionConfig,
    StateConfig,
)

# Frozen NREL aggregate groups (building indices 1..17, divisor) — comparison
# only for FRCC (B4). ⚠ preserved verbatim, incl. FL#9 singleton/2 and the
# suspected SC#4 typo (12 vs 13) — see regions/FRCC.md.
COMPARISON_NREL = {
    "FL": NRELBasisSpec(
        city_folder="NREL_Profiles/Miami_Intl_AP",
        groups={
            1: ((5,), 1), 2: ((4, 10, 13, 14, 15), 5), 3: ((8,), 1),
            4: ((12,), 1), 5: ((1, 9, 11), 3), 6: ((16,), 1),
            7: ((2, 7), 2), 8: ((6,), 1), 9: ((3,), 2), 10: ((17,), 1),
        },
        fit_groups=(10, 2, 7),
    ),
    "GA": NRELBasisSpec(
        city_folder="NREL_Profiles/Atlanta_AP",
        groups={
            1: ((12,), 1), 2: ((4, 5, 13, 14, 15), 5), 3: ((8,), 1),
            4: ((10,), 1), 5: ((1, 9, 11), 3), 6: ((3,), 1),
            7: ((6,), 1), 8: ((16,), 1), 9: ((2, 7), 2), 10: ((17,), 1),
        },
        fit_groups=(10, 2, 7),
    ),
    "SC": NRELBasisSpec(
        # ⚠ folder contains Atlanta building CSVs + Charleston TMY only
        city_folder="NREL_Profiles/Charleston",
        groups={
            1: ((8,), 1), 2: ((10,), 1), 3: ((12,), 1),
            4: ((4, 5, 12, 14, 15), 5),  # ⚠ 12 likely a typo for 13 (verbatim)
            5: ((1, 9), 2), 6: ((3,), 1), 7: ((6,), 1),
            8: ((16,), 1), 9: ((2, 7), 2), 10: ((17,), 1),
        },
        fit_groups=(10, 2, 7),
    ),
}

FRCC = RegionConfig(
    name="FRCC",
    matlab_source="FRCC/MakeLoadProfiles_FRCC_NEW.m",
    states=(
        StateConfig(name="Florida", abbrev="FL", bus_state_code=1,
                    basis=BasisKind.NYSEG),
        StateConfig(name="Georgia", abbrev="GA", bus_state_code=2,
                    basis=BasisKind.NYSEG,
                    # D18: with "residential" GA's residential class dips to
                    # -467 MW for one hour; "proportional" keeps all classes
                    # strictly positive. MATLAB-faithful comparisons pass
                    # residual="residential" explicitly (test_regression.py).
                    residual="proportional"),
        StateConfig(name="SouthCarolina", abbrev="SC", bus_state_code=3,
                    basis=BasisKind.NYSEG),
    ),
    bus_table=BusTableSpec(
        bus_number_col=1,
        state_code_col=5,
        share_cols=(24, 25, 26),
        cir_rows_cols=((1, 3), (27, 29)),   # FL/GA/SC x C/I/R (NB: 27:29,
                                            # not 28:30 as in most regions)
    ),
    expected_bus_count=7224,
    calendar_year=2015,
    notes="Pilot region. NREL sections comparison-only (B4); residual "
          "policy 'drop' reproduces MATLAB (B3). Q was commented out in "
          "MATLAB; LoadSmith writes Q per D3.",
)
