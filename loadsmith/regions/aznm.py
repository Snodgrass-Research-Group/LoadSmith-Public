"""AZNM region config — Arizona, Colorado, Nevada, New Mexico, Utah.

Provenance: AZNM/MakeLoadProfiles_AZNM.m (752 lines, canonical; analyzed
2026-07-10). Full extraction notes:
docs/conversion_manual/regions/AZNM.md.

Archetype: **NREL** — per-day NNLS fit against the same day's slice of the
frozen full-year NREL aggregates; NYSEG load line commented out, day-type
calendar dead. Residual policy proportional (CIR-weighted), like SPP/SRVC;
no `; +` typo (B3). Unlike SPP, the fit/distribution blocks are internally
consistent — no cross-state variable bugs (the "%Do Tennessee Fit" header
over the New Mexico block is cosmetic only, B11).

Quirk: the MATLAB reads the CIR block as ``Atmp(1:6,28:30)`` (6 rows) but
the region has 5 states; row 6 is all-NaN padding and is never used.
Bus xlsx: 4,536 rows, matching the (no-op, B1) smoothing loop 1:4536.
"""

from __future__ import annotations

from loadsmith.config import (
    BasisKind,
    BusTableSpec,
    NRELBasisSpec,
    RegionConfig,
    StateConfig,
)

# Frozen NREL aggregate groups (building indices 1..17, divisor), extracted
# VERBATIM — including divisor oddities (harmless after demean+normalize,
# cf. B7): CO#7 three members/2, NM#8 and UT#8 singleton/2, and CO#9/NV#9
# pairs without the usual /2. AZ's grouping is structurally unique among
# all NREL-archetype states (e.g. [3 4 11], [7 9], [1 6] clusters).
NREL = {
    "AZ": NRELBasisSpec(
        city_folder="NREL_Profiles/Phoenix",
        groups={
            1: ((12, 13, 14), 3), 2: ((3, 4, 11), 3), 3: ((8, 10), 2),
            4: ((7, 9), 2), 5: ((2,), 1), 6: ((5,), 1),
            7: ((1, 6), 2), 8: ((15,), 1), 9: ((16,), 1), 10: ((17,), 1),
        },
        fit_groups=(10, 2, 5),
    ),
    "CO": NRELBasisSpec(
        city_folder="NREL_Profiles/Boulder",
        groups={
            1: ((13, 14, 15), 3), 2: ((4, 5, 12), 3), 3: ((8,), 1),
            4: ((10,), 1), 5: ((3,), 1), 6: ((6,), 1),
            7: ((1, 9, 11), 2),                # ⚠ 3 members /2 (verbatim)
            8: ((16,), 1),
            9: ((2, 7), 1),                    # ⚠ pair WITHOUT /2 (verbatim)
            10: ((17,), 1),
        },
        fit_groups=(10, 4, 9),
    ),
    "NV": NRELBasisSpec(
        city_folder="NREL_Profiles/Las_Vegas",
        groups={
            1: ((12,), 1), 2: ((4, 5, 13, 14, 15), 5), 3: ((8,), 1),
            4: ((10,), 1), 5: ((1, 9, 11), 3), 6: ((3,), 1),
            7: ((6,), 1), 8: ((16,), 1),
            9: ((2, 7), 1),                    # ⚠ pair WITHOUT /2 (verbatim)
            10: ((17,), 1),
        },
        fit_groups=(10, 3, 9),
    ),
    "NM": NRELBasisSpec(
        city_folder="NREL_Profiles/Albuquerque",
        groups={
            1: ((2,), 1), 2: ((7,), 1), 3: ((8,), 1), 4: ((10,), 1),
            5: ((1, 9, 11), 3), 6: ((4, 5, 12, 13, 14, 15), 6),
            7: ((3,), 1),
            8: ((6,), 2),                      # ⚠ singleton /2 (B7-style)
            9: ((16,), 1), 10: ((17,), 1),
        },
        fit_groups=(10, 1, 4),
    ),
    "UT": NRELBasisSpec(
        # ⚠ folder contains Boulder (5B) building CSVs + Salt Lake City TMY
        city_folder="NREL_Profiles/Salt_Lake_City",
        groups={  # identical to NM's grouping in the MATLAB
            1: ((2,), 1), 2: ((7,), 1), 3: ((8,), 1), 4: ((10,), 1),
            5: ((1, 9, 11), 3), 6: ((4, 5, 12, 13, 14, 15), 6),
            7: ((3,), 1),
            8: ((6,), 2),                      # ⚠ singleton /2 (B7-style)
            9: ((16,), 1), 10: ((17,), 1),
        },
        fit_groups=(10, 1, 4),
    ),
}

AZNM = RegionConfig(
    name="AZNM",
    matlab_source="AZNM/MakeLoadProfiles_AZNM.m",
    states=(
        StateConfig(name="Arizona", abbrev="AZ", bus_state_code=1,
                    basis=BasisKind.NREL, nrel=NREL["AZ"],
                    residual="proportional"),
        StateConfig(name="Colorado", abbrev="CO", bus_state_code=2,
                    basis=BasisKind.NREL, nrel=NREL["CO"],
                    residual="proportional"),
        StateConfig(name="Nevada", abbrev="NV", bus_state_code=3,
                    basis=BasisKind.NREL, nrel=NREL["NV"],
                    residual="proportional"),
        StateConfig(name="NewMexico", abbrev="NM", bus_state_code=4,
                    basis=BasisKind.NREL, nrel=NREL["NM"],
                    residual="proportional"),
        StateConfig(name="Utah", abbrev="UT", bus_state_code=5,
                    basis=BasisKind.NREL, nrel=NREL["UT"],
                    residual="proportional"),
    ),
    bus_table=BusTableSpec(
        bus_number_col=1,
        state_code_col=5,
        share_cols=(24, 25, 26),
        cir_rows_cols=((1, 5), (28, 30)),   # MATLAB read 1:6; row 6 NaN pad
    ),
    expected_bus_count=4536,
    calendar_year=2015,
    notes="NREL archetype; calendar dead. Residual proportional (CIR-"
          "weighted) per the MATLAB; no cross-state bugs. Q was written "
          "by MATLAB (with bug B2); LoadSmith writes Q per D3.",
)
