"""SRTV region config — AL, KY, MS, TN (NREL archetype).

Provenance: SRTV/MakeLoadProfiles_SRTV.m (657 lines, canonical).
Full extraction notes: docs/conversion_manual/regions/SRTV.md.

Archetype: NREL production basis — per-day fit against the same day's 24-h
slice of the state's frozen aggregate profiles (NYSEG load line commented
out; day-type calendar block present but DEAD). Residual policy is
**proportional** (CIR-weighted) for every state — MATLAB adds
``XX_CIR(k)*XX_resid`` to each class; no ``; +`` typos (B3-clean), and every
state uses its OWN CIR throughout (no B6-style cross-state bug).

Verbatim group oddities (all harmless per B7 — basis columns are demeaned +
normalized): KY#7 = [1 9 11]/2 (three members divided by 2), KY#9 & MS#9 =
[2 7] summed with NO divisor, TN#8 = singleton [6]/2.

⚠ AL/Birmingham dir-order quirk: the stray
headerless ``aRefBldg…`` file sorts LAST under the ASCII enumeration the
reference generator's ``dir()`` used, so the AL groups here are the
canonical-index PERMUTATION of the script's literals (p<=15 -> p+1,
16 -> TMY, 17 -> the shifted aRefBldg restaurant, which is AL's actual
"residential" fit basis). See the AL spec comment and
docs/conversion_manual/regions/SRTV.md.

CIR block: MATLAB reads ``Atmp(1:6,28:30)`` — a copy-paste of SRVC's
6-state read — but only rows 1:4 exist/are used (rows 5:6 are NaN); the
migration reads rows 1:4.

Distribution: shares (cols 24:26) divided by the state CIR — the CORRECT
convention (B12/F3; raw columns sum to the CIR fraction), numerically
identical to LoadSmith's renormalized shares. Q computed AND written
(Q_Load_SRTV.csv) with unseeded rand + bug B2; smoothing loop 1:4451 was a
no-op (B1). Kentucky.mat hours 1587 & 7298 and Tennessee.mat hour 699 are
NaN in the raw data — interpolated at migration; reference comparisons
deviate on those days.
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
# VERBATIM from the profiles_aggregate_XX blocks (D7) — incl. the oddities
# flagged in the module docstring.
_NREL = {
    "AL": NRELBasisSpec(
        city_folder="NREL_Profiles/Birmingham",
        # ⚠ Birmingham's FullServiceRestaurant CSV is a stray headerless
        # 'aRefBldg…' file that sorts LAST in ASCII/case-sensitive order.
        # The reference generator's dir() enumerated it that way (verified
        # empirically: median 6.3e-06 vs 2.9e-02 for the canonical reading),
        # so the script's literal indices [p] mean: p<=15 -> canonical p+1,
        # 16 -> TMY (UNSCALED — the x1000 hit position 17 instead), and
        # 17 -> the aRefBldg restaurant (headerless, so csvread(f,1,1)
        # dropped its first hour + its Electricity:Facility column; stored
        # faithfully at canonical index 1). The groups below are the
        # PERMUTED (canonical-index) equivalents of the MATLAB literals —
        # note they land exactly on the author's usual semantic patterns
        # (retail trio, office trio, schools, hospital pair …). The x1000
        # mismatches sit in single-member groups (9, 10), where per-day
        # demean+normalization makes constant scales irrelevant.
        groups={
            1: ((13, 14, 15), 3),   # MATLAB [12 13 14]: retail trio
            2: ((4, 5, 12), 3),     # MATLAB [3 4 11]:   office trio
            3: ((9, 11), 2),        # MATLAB [8 10]
            4: ((8, 10), 2),        # MATLAB [7 9]:      school pair
            5: ((3,), 1),           # MATLAB [2]:        LargeHotel
            6: ((6,), 1),           # MATLAB [5]:        MidriseApartment
            7: ((2, 7), 2),         # MATLAB [1 6]:      hospital pair
            8: ((16,), 1),          # MATLAB [15]:       Warehouse
            9: ((17,), 1),          # MATLAB [16]:       TMY (unscaled there)
            10: ((1,), 1),          # MATLAB [17]:       SHIFTED aRefBldg
        },
        fit_groups=(10, 5, 7),      # res = shifted restaurant(!), com, ind
    ),
    "KY": NRELBasisSpec(
        city_folder="NREL_Profiles/Louisville",
        groups={
            1: ((13, 14, 15), 3), 2: ((4, 5, 12), 3), 3: ((8,), 1),
            4: ((10,), 1), 5: ((3,), 1), 6: ((6,), 1),
            7: ((1, 9, 11), 2),  # ⚠ B7-family: 3 members divided by 2
            8: ((16,), 1),
            9: ((2, 7), 1),      # ⚠ summed, NO mean divisor (verbatim)
            10: ((17,), 1),
        },
        fit_groups=(10, 5, 9),
    ),
    "MS": NRELBasisSpec(
        city_folder="NREL_Profiles/Jackson",
        groups={
            1: ((12,), 1), 2: ((4, 5, 13, 14, 15), 5), 3: ((8,), 1),
            4: ((10,), 1), 5: ((1, 9, 11), 3), 6: ((3,), 1),
            7: ((6,), 1), 8: ((16,), 1),
            9: ((2, 7), 1),      # ⚠ summed, NO mean divisor (verbatim)
            10: ((17,), 1),
        },
        fit_groups=(10, 5, 6),
    ),
    "TN": NRELBasisSpec(
        city_folder="NREL_Profiles/Nashville",
        groups={
            1: ((2,), 1), 2: ((7,), 1), 3: ((8,), 1), 4: ((10,), 1),
            5: ((1, 9, 11), 3), 6: ((4, 5, 12, 13, 14, 15), 6),
            7: ((3,), 1),
            8: ((6,), 2),        # ⚠ B7: singleton divided by 2 (verbatim)
            9: ((16,), 1), 10: ((17,), 1),
        },
        fit_groups=(10, 1, 7),
    ),
}


def _state(name: str, abbrev: str, code: int) -> StateConfig:
    return StateConfig(
        name=name, abbrev=abbrev, bus_state_code=code,
        basis=BasisKind.NREL, nrel=_NREL[abbrev],
        residual="proportional",   # MATLAB: XX_CIR(k)*XX_resid on every class
    )


SRTV = RegionConfig(
    name="SRTV",
    matlab_source="SRTV/MakeLoadProfiles_SRTV.m",
    states=(
        _state("Alabama", "AL", 1),
        _state("Kentucky", "KY", 2),
        _state("Mississippi", "MS", 3),
        _state("Tennessee", "TN", 4),
    ),
    bus_table=BusTableSpec(
        bus_number_col=1,
        state_code_col=5,
        share_cols=(24, 25, 26),
        cir_rows_cols=((1, 4), (28, 30)),   # MATLAB reads rows 1:6 (SRVC
                                            # copy-paste); only 1:4 are real
    ),
    expected_bus_count=4451,   # smoothing/LoadDist bound 1:4451 == actual rows
    calendar_year=2015,
    notes="NREL production basis; residual proportional (CIR-weighted); "
          "each state uses its own CIR (no B6 analogue). Verbatim group "
          "oddities: KY#7 [1 9 11]/2, KY#9 & MS#9 [2 7] no divisor, TN#8 "
          "[6]/2 (all B7-harmless). KY hours 1587/7298 and TN hour 699 NaN "
          "-> interpolated at migration. Q written in MATLAB (unseeded, "
          "B2); LoadSmith Q per D3.",
)
