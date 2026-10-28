"""SPP region config — Kansas, Nebraska, North Dakota, Oklahoma, South
Dakota, Texas (panhandle/SPP share).

Provenance: SPP/MakeLoadProfiles_SPP.m (897 lines, canonical; analyzed
2026-07-10). Full extraction notes:
docs/conversion_manual/regions/SPP.md.

Archetype: **NREL** — per-day NNLS fit against the same day's slice of the
frozen full-year NREL aggregates; the NYSEG load line is commented out and
the day-type calendar block is dead. Residual policy is proportional
(CIR-weighted across all three classes), like SRVC — no `; +` typo (B3)
anywhere in this script.

Three MATLAB copy-paste bugs are FIXED here (production = evident intent);
each has a faithful-mode counterpart for validation against the 2018
P_Load_SPP.csv (see regions/SPP.md and tests/test_wave4_west1.py):

* ND's fit used ``profiles_aggregate_OK`` (Oklahoma City basis) instead of
  its own Fargo aggregates — the comment "use profiles 5 and 6 ... in
  North Dakota" shows the intent. Faithful spec: ND_MATLAB_FAITHFUL_NREL.
* OK's industrial class reused the stale ``ND_CI_top`` 24-h vector (ND's
  day-365 com/ind fit component) for every day of the year.
* KS's bus distribution used share column 24 (commercial) for the
  industrial term as well (col 25 never read for KS P).

The bus xlsx has 8,025 rows; the MATLAB smoothing/LoadDist bound 1:3123
was a copy-paste from SRMV (flag F1 — resolved; moot because of B1).
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
# VERBATIM from the profiles_aggregate_XX blocks — including divisor
# oddities (harmless after demean+normalize, cf. B7): KS#4 singleton/3,
# KS#9 singleton/2, TX#5 three members/2, and OK#9/SD#8/TX#8 pairs
# without the usual /2.
NREL = {
    "KS": NRELBasisSpec(
        city_folder="NREL_Profiles/Wichita",   # Baltimore 4A building donors
        groups={
            1: ((2,), 1), 2: ((7,), 1), 3: ((8,), 1),
            4: ((10,), 3),                     # ⚠ singleton /3 (verbatim)
            5: ((1, 9, 11), 3), 6: ((4, 5, 12, 13, 14, 15), 6),
            7: ((3,), 1), 8: ((6,), 1),
            9: ((16,), 2),                     # ⚠ singleton /2 (B7-style)
            10: ((17,), 1),
        },
        fit_groups=(10, 1, 7),
    ),
    "NB": NRELBasisSpec(
        city_folder="NREL_Profiles/Omaha",     # Chicago-O'Hare 5A donors
        groups={
            1: ((11,), 1), 2: ((1, 9), 2), 3: ((13, 14, 15), 3),
            4: ((4, 5, 12), 3), 5: ((8, 10), 2), 6: ((3,), 1),
            7: ((6,), 1), 8: ((2, 7), 2), 9: ((16,), 1), 10: ((17,), 1),
        },
        fit_groups=(10, 5, 6),
    ),
    "ND": NRELBasisSpec(
        city_folder="NREL_Profiles/Fargo",     # Duluth 7A donors
        groups={
            1: ((11,), 1), 2: ((13, 14, 15), 3), 3: ((4, 5, 12), 3),
            4: ((1, 9), 2), 5: ((8, 10), 2), 6: ((3,), 1),
            7: ((6,), 1), 8: ((2, 7), 2), 9: ((16,), 1), 10: ((17,), 1),
        },
        fit_groups=(10, 5, 6),
    ),
    "OK": NRELBasisSpec(
        city_folder="NREL_Profiles/Oklahoma_City",  # Atlanta 3A donors
        groups={
            1: ((13, 14, 15), 3), 2: ((4, 5, 12), 3), 3: ((8,), 1),
            4: ((10,), 1), 5: ((1, 9, 11), 3), 6: ((3,), 1),
            7: ((6,), 1), 8: ((16,), 1),
            9: ((2, 7), 1),                    # ⚠ pair WITHOUT /2 (verbatim)
            10: ((17,), 1),
        },
        fit_groups=(10, 6, 9),
    ),
    "SD": NRELBasisSpec(
        city_folder="NREL_Profiles/Sioux_Falls",    # Minneapolis 6A donors
        groups={
            1: ((4, 5, 12), 3), 2: ((13, 14, 15), 3), 3: ((11,), 1),
            4: ((1, 9), 2), 5: ((8, 10), 2), 6: ((3,), 1),
            7: ((6,), 1),
            8: ((2, 7), 1),                    # ⚠ pair WITHOUT /2 (verbatim)
            9: ((16,), 1), 10: ((17,), 1),
        },
        fit_groups=(10, 1, 6),
    ),
    "TX": NRELBasisSpec(
        city_folder="NREL_Profiles/Houston",
        groups={
            1: ((8,), 1), 2: ((10,), 1), 3: ((12,), 1),
            4: ((4, 5, 13, 14, 15), 5),
            5: ((1, 9, 11), 2),                # ⚠ 3 members /2 (verbatim)
            6: ((3,), 1), 7: ((6,), 1),
            8: ((2, 7), 1),                    # ⚠ pair WITHOUT /2 (verbatim)
            9: ((16,), 1), 10: ((17,), 1),
        },
        fit_groups=(10, 6, 8),
    ),
}

# MATLAB-faithful ND basis: the script's ND fit block sliced
# profiles_aggregate_OK (already computed at that point), so the ND class
# loads in the 2018 reference are built from Oklahoma City aggregates with
# groups [10 5 6]. Validation-only — the production config above uses ND's
# own Fargo aggregates (the evident intent).
ND_MATLAB_FAITHFUL_NREL = NRELBasisSpec(
    city_folder=NREL["OK"].city_folder,
    groups=NREL["OK"].groups,
    fit_groups=(10, 5, 6),
)

SPP = RegionConfig(
    name="SPP",
    matlab_source="SPP/MakeLoadProfiles_SPP.m",
    states=(
        StateConfig(name="Kansas", abbrev="KS", bus_state_code=1,
                    basis=BasisKind.NREL, nrel=NREL["KS"],
                    residual="proportional"),
        StateConfig(name="Nebraska", abbrev="NB", bus_state_code=2,
                    basis=BasisKind.NREL, nrel=NREL["NB"],
                    residual="proportional"),
        StateConfig(name="NorthDakota", abbrev="ND", bus_state_code=3,
                    basis=BasisKind.NREL, nrel=NREL["ND"],
                    residual="proportional"),
        StateConfig(name="Oklahoma", abbrev="OK", bus_state_code=4,
                    basis=BasisKind.NREL, nrel=NREL["OK"],
                    residual="proportional"),
        StateConfig(name="SouthDakota", abbrev="SD", bus_state_code=5,
                    basis=BasisKind.NREL, nrel=NREL["SD"],
                    residual="proportional"),
        StateConfig(name="Texas", abbrev="TX", bus_state_code=6,
                    basis=BasisKind.NREL, nrel=NREL["TX"],
                    residual="proportional"),
    ),
    bus_table=BusTableSpec(
        bus_number_col=1,
        state_code_col=5,
        share_cols=(24, 25, 26),
        cir_rows_cols=((1, 6), (28, 30)),
    ),
    expected_bus_count=8025,        # actual xlsx rows; MATLAB 3123 wrong (F1)
    calendar_year=2015,
    notes="NREL archetype; calendar dead. Residual proportional (CIR-"
          "weighted) per the MATLAB. Fixed vs MATLAB: ND fit basis (used "
          "OK's aggregates), OK industrial (stale ND_CI_top), KS "
          "distribution (col 24 reused for industrial). Q was written by "
          "MATLAB (with bug B2); LoadSmith writes Q per D3. 'ERCOT "
          "Backcasted Load Profiles 2016.xls' is dead (Texas.mat <- "
          "TX_Hourly_Load.xls).",
)
