"""SRVC region config — DE, DC, MD, NC, VA, WV (NREL archetype).

Provenance: SRVC/MakeLoadProfiles_SRVC.m (933 lines, canonical).
Full extraction notes: docs/conversion_manual/regions/SRVC.md.

Archetype: the NREL basis IS the production path — each day is fit against
the same day's 24-h slice of the state's frozen NREL aggregate profiles
(NYSEG load line commented out; the day-type calendar block is present but
DEAD). Residual policy is **proportional** (CIR-weighted across all three
classes) for every state — MATLAB adds ``XX_CIR(k)*XX_resid`` to each class,
with no ``; +`` typos (unlike FRCC's B3).

Bug B6 (FIXED here): the MATLAB WV residential class uses Maryland's CIR in
the trend term — line 792: ``WV_load(:,3) = WV_Trend*MY_CIR(3) + WV_Res_top
+ WV_CIR(3)*WV_resid``. Only that ONE term is wrong (the C/I columns, the
C:I split, and the residual all use WV's own CIR). LoadSmith uses WV's own
CIR everywhere — the fix — so WV buses deviate from the 2024 reference by
``WV_Trend * (MY_CIR(3) - WV_CIR(3)) ≈ WV_Trend * 0.0952`` in the
residential class. tests/test_wave4_south.py quantifies both variants.

B7 (kept verbatim): groups DE#9 and VA#9 divide the singleton [16] by 2 —
harmless, basis columns are demeaned + normalized before the fit.

Distribution: the MATLAB divides bus share cols 24:26 by the state CIR
(the CORRECT convention per B12/F3 — raw columns sum to the CIR fraction),
which is numerically identical to LoadSmith's renormalized shares. Q was
computed AND written (Q_Load_SRVC.csv) with unseeded rand and bug B2;
LoadSmith writes Q per D3. Smoothing loop 1:6340 was a no-op (B1).
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
# VERBATIM from the profiles_aggregate_XX blocks (D7). ⚠ includes the B7
# singleton/2 oddities in DE#9 and VA#9.
_NREL = {
    "DL": NRELBasisSpec(
        city_folder="NREL_Profiles/Wilmington",
        groups={
            1: ((11,), 1), 2: ((1, 9), 2), 3: ((13, 14, 15), 3),
            4: ((4, 5, 12), 3), 5: ((8, 10), 2), 6: ((3,), 1),
            7: ((6,), 1), 8: ((2, 7), 2),
            9: ((16,), 2),  # ⚠ B7: singleton divided by 2 (verbatim)
            10: ((17,), 1),
        },
        fit_groups=(10, 5, 6),
    ),
    "DC": NRELBasisSpec(
        # ⚠ the "DC" folder's TMY file is Sterling / Washington-Dulles (VA)
        city_folder="NREL_Profiles/DC",
        groups={
            1: ((2,), 1), 2: ((7,), 1), 3: ((13, 14, 15), 3),
            4: ((4, 5, 12), 3), 5: ((1, 9, 11), 3), 6: ((8, 10), 2),
            7: ((3,), 1), 8: ((6,), 1), 9: ((16,), 1), 10: ((17,), 1),
        },
        fit_groups=(10, 6, 7),
    ),
    "MY": NRELBasisSpec(
        city_folder="NREL_Profiles/Baltimore",
        groups={
            1: ((8,), 1), 2: ((10,), 1), 3: ((13, 14, 15), 3),
            4: ((4, 5, 12), 3), 5: ((1, 9, 11), 3), 6: ((3,), 1),
            7: ((6,), 1), 8: ((2, 7), 2), 9: ((16,), 1), 10: ((17,), 1),
        },
        fit_groups=(10, 2, 6),
    ),
    "NC": NRELBasisSpec(
        # ⚠ folder holds Atlanta (3A) building CSVs + Charlotte TMY
        city_folder="NREL_Profiles/Charlotte",
        groups={
            1: ((12,), 1), 2: ((4, 5, 13, 14, 15), 5), 3: ((8,), 1),
            4: ((10,), 1), 5: ((1, 9, 11), 3), 6: ((3,), 1),
            7: ((6,), 1), 8: ((16,), 1), 9: ((2, 7), 2), 10: ((17,), 1),
        },
        fit_groups=(10, 4, 6),
    ),
    "VG": NRELBasisSpec(
        # MATLAB aggregate variable is profiles_aggregate_VA (state var VG)
        city_folder="NREL_Profiles/Richmond",
        groups={
            1: ((2,), 1), 2: ((7,), 1), 3: ((12,), 1),
            4: ((4, 5, 13, 14, 15), 5), 5: ((1, 9, 11), 3),
            6: ((8, 10), 2), 7: ((3,), 1), 8: ((6,), 1),
            9: ((16,), 2),  # ⚠ B7: singleton divided by 2 (verbatim)
            10: ((17,), 1),
        },
        fit_groups=(10, 2, 6),
    ),
    "WV": NRELBasisSpec(
        city_folder="NREL_Profiles/Charleston",
        groups={
            1: ((12,), 1), 2: ((4, 5), 2), 3: ((13, 14, 15), 3),
            4: ((1, 9, 11), 3), 5: ((3,), 1), 6: ((6,), 1),
            7: ((8, 10), 2), 8: ((2, 7), 2), 9: ((16,), 1), 10: ((17,), 1),
        },
        fit_groups=(10, 2, 5),
    ),
}


def _state(name: str, abbrev: str, code: int) -> StateConfig:
    return StateConfig(
        name=name, abbrev=abbrev, bus_state_code=code,
        basis=BasisKind.NREL, nrel=_NREL[abbrev],
        residual="proportional",   # MATLAB: XX_CIR(k)*XX_resid on every class
    )


SRVC = RegionConfig(
    name="SRVC",
    matlab_source="SRVC/MakeLoadProfiles_SRVC.m",
    states=(
        _state("Delaware", "DL", 1),
        _state("DistrictOfColumbia", "DC", 2),
        _state("Maryland", "MY", 3),
        _state("NorthCarolina", "NC", 4),
        _state("Virginia", "VG", 5),
        _state("WestVirginia", "WV", 6),
    ),
    bus_table=BusTableSpec(
        bus_number_col=1,
        state_code_col=5,
        share_cols=(24, 25, 26),
        cir_rows_cols=((1, 6), (28, 30)),   # 'Total % C/I/R' block (col 27 =
                                            # text 'State' label column)
    ),
    expected_bus_count=6340,
    calendar_year=2015,
    notes="NREL production basis; residual proportional (CIR-weighted). "
          "B6 WV/MD CIR bug FIXED (WV uses its own CIR). B7 singleton/2 in "
          "DE#9 & VA#9 kept verbatim. NorthCarolina.mat hour 17 NaN "
          "interpolated at migration. Q written in MATLAB (unseeded, B2); "
          "LoadSmith Q per D3.",
)
