"""NWPP region config — Idaho, Montana, Oregon, Washington, Wyoming.

Provenance: NWPP/MakeLoadProfiles_NWPP.m (524-line script; canonical). The
KCL-KVL "Master Load Data" copy is the SAME code wrapped as a function
(csvwrite commented out) — functionally identical, and unlike FRCC/RFCE it
has NO loadscaling step, so the published P_Load_NWPP.csv carries no global
peak-pinning factor. Full extraction notes:
docs/conversion_manual/regions/NWPP.md.

MIXED archetype (unique among the 13 regions):

* ID / MT / WY — NREL frozen aggregate groups (cities Boise / Billings /
  Cheyenne), same-day year slice. ID and MT share IDENTICAL group tables;
  WY has its own. Building CSVs are borrowed climates (Boise folder holds
  BOULDER CO buildings; Billings AND Cheyenne hold HELENA MT buildings) —
  only the TMY series (building 17) is city-specific.
* OR / WA — PG&E year-2000 utility class profiles a1/a10/e1 (the CSVs in
  the region folder are ACTIVELY used by the canonical fit, not dead code).
  Quirk: e1-2000.csv is headerless, so MATLAB's ``csvread(f,1)`` drops its
  first data day — the migrated "e1" source is day-shifted by one,
  faithfully.

MATLAB bug found here (LoadSmith fixes it; see regions/NWPP.md): the WY
fit adds ``ID_Res_top`` — Idaho's day-365 residential shape, a stale
leftover — to every WY day instead of ``WY_Res_top`` (copy-paste, same
family as B6). Production LoadSmith uses WY's own residential column;
MATLAB-faithful comparison must replicate the stale term.

Residual policy: the MATLAB adds every state's fit residual to the
residential class (no ``; +`` typo anywhere). Production keeps that for
ID/MT/OR/WA but uses ``proportional`` for WY (user decision D18,
2026-07-11): under ``residential`` WY's small residential class goes
negative on 138 hours (min -302 MW). Faithful comparisons override to
``residential`` explicitly.
Q was computed AND written (Q_Load_NWPP.csv) with the B2 qf bug.
"""

from __future__ import annotations

from loadsmith.config import (
    BasisKind,
    BusTableSpec,
    NRELBasisSpec,
    RegionConfig,
    Role,
    StateConfig,
    UtilityBasisSpec,
)

# Frozen NREL aggregate groups (building indices 1..17, divisor) — verbatim
# from the profiles_aggregate_XX blocks. ID and MT are IDENTICAL tables.
_GROUPS_ID_MT = {
    1: ((8,), 1), 2: ((10,), 1), 3: ((13, 14, 15), 3), 4: ((1, 9, 11), 3),
    5: ((3,), 1), 6: ((6,), 1), 7: ((4, 5, 12), 3), 8: ((2, 7), 2),
    9: ((16,), 1), 10: ((17,), 1),
}

_GROUPS_WY = {
    1: ((11,), 1), 2: ((13, 14, 15), 3), 3: ((1, 9), 2), 4: ((3,), 1),
    5: ((6,), 1), 6: ((4, 5, 12), 3), 7: ((8, 10), 2), 8: ((2, 7), 2),
    9: ((16,), 1), 10: ((17,), 1),
}

# PG&E year-2000 class profiles (utility basis for OR and WA).
_PGE = UtilityBasisSpec(sources={
    Role.COMMERCIAL: "a1",
    Role.INDUSTRIAL: "a10",
    Role.RESIDENTIAL: "e1",
})

NWPP = RegionConfig(
    name="NWPP",
    matlab_source="NWPP/MakeLoadProfiles_NWPP.m",
    states=(
        StateConfig(name="Idaho", abbrev="ID", bus_state_code=1,
                    basis=BasisKind.NREL,
                    nrel=NRELBasisSpec(
                        city_folder="NREL_Profiles/Boise",
                        groups=_GROUPS_ID_MT,
                        fit_groups=(10, 2, 5),
                    )),
        StateConfig(name="Montana", abbrev="MT", bus_state_code=2,
                    basis=BasisKind.NREL,
                    nrel=NRELBasisSpec(
                        city_folder="NREL_Profiles/Billings",
                        groups=_GROUPS_ID_MT,
                        fit_groups=(10, 2, 5),
                    )),
        StateConfig(name="Oregon", abbrev="OR", bus_state_code=3,
                    basis=BasisKind.UTILITY, utility=_PGE),
        StateConfig(name="Washington", abbrev="WA", bus_state_code=4,
                    basis=BasisKind.UTILITY, utility=_PGE),
        StateConfig(name="Wyoming", abbrev="WY", bus_state_code=5,
                    basis=BasisKind.NREL,
                    nrel=NRELBasisSpec(
                        city_folder="NREL_Profiles/Cheyenne",
                        groups=_GROUPS_WY,
                        fit_groups=(10, 4, 6),
                    ),
                    # D18: with "residential" (the MATLAB behavior) WY's
                    # residential class goes negative on 138 h (min -302 MW,
                    # -7% of state peak) — the class is too small for the
                    # residual spikes. "proportional" keeps every class
                    # strictly positive. MATLAB-faithful comparisons pass
                    # residual="residential" explicitly.
                    residual="proportional"),
    ),
    bus_table=BusTableSpec(
        bus_number_col=1,
        state_code_col=5,
        share_cols=(24, 25, 26),
        cir_rows_cols=((1, 5), (28, 30)),   # MATLAB reads 1:6 but row 6 is NaN
    ),
    expected_bus_count=2977,
    calendar_year=2015,
    notes="Mixed archetype: ID/MT/WY NREL groups, OR/WA PG&E utility basis "
          "(a1/a10/e1; e1 headerless -> day-shifted, faithful). MATLAB WY "
          "bug: ID_Res_top (Idaho day-365 residential shape) added to every "
          "WY day instead of WY_Res_top — fixed in LoadSmith. Script "
          "csvwrites its own P+Q with ÷CIR distribution and no loadscaling.",
)
