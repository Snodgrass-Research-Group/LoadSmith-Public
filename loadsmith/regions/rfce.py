"""RFCE region config — New Jersey, Pennsylvania.

Provenance: RFCE/MakeLoadProfiles_RFCE.m (407 lines; canonical algorithm).
⚠ TWO variants exist (wave-4d correction — an earlier note wrongly called
them byte-identical): the REPO copy is a plain script (absolute macOS
paths, ACTIVE csvwrite, NO loadscaling); the KCL-KVL "Master Load Data"
copy is a FUNCTION taking LoadPath with `ispc` paths, csvwrite commented
out, and a KCL-KVL loadscaling step appended. The published
P_Load_RFCE.csv was made by the KCL-KVL variant (verified empirically —
see the loadscaling note below). Full extraction notes:
docs/conversion_manual/regions/RFCE.md.

Archetype: NREL — per-day fit against the same day's slice of the frozen
full-year NREL aggregates (cities Newark / Philadelphia; both folders hold
the BALTIMORE MD building set, only the TMY file is city-specific). The
day-type calendar block is present but DEAD (``profile`` never used), as
in SRVC. Stale "FL, GA, SC" header (B11 family).

Residual policy: **proportional** — the residual is split across all three
classes weighted by CIR fractions (``+ XX_resid*XX_CIR(k)``), like SRVC.
The PN block's ``+ +`` on the residential line is a harmless unary plus,
NOT the FRCC ``; +`` typo — the residual IS added.

MATLAB bug found here (LoadSmith fixes it; see regions/RFCE.md): the PN
COMMERCIAL class uses ``PN_Trend*NJ_CIR(1)`` — New Jersey's commercial
fraction (0.5158) instead of Pennsylvania's (0.3022) in the trend term
(copy-paste, same family as B6/SRVC-WV). This inflates PN class sums by
~21% of the trend energy; MATLAB-faithful comparison must replicate it.

Loadscaling: the KCL-KVL variant ends with a global ``loadscaling =
sum(unique(BusDist(:,16)))/max(sum(P_load))`` applied to BOTH P and Q —
the published P_Load_RFCE.csv carries **0.865687** (peak pinned to
48,489 MW on the BUGGED matrix). ⚠ ``peak_scaling="kclkvl"`` pins the
same 48,489 MW target but on the bug-FIXED matrix, giving a DIFFERENT
factor (0.965592) — the reference's 0.8657 is reproducible only together
with the PN NJ_CIR(1) bug (tests/test_wave4_west2.py).

Q computed with the B2 qf bug (÷pfC everywhere); Q_Load_RFCE.csv exists.
"""

from __future__ import annotations

from loadsmith.config import (
    BasisKind,
    BusTableSpec,
    NRELBasisSpec,
    RegionConfig,
    StateConfig,
)

RFCE = RegionConfig(
    name="RFCE",
    matlab_source="RFCE/MakeLoadProfiles_RFCE.m",
    states=(
        StateConfig(name="NewJersey", abbrev="NJ", bus_state_code=1,
                    basis=BasisKind.NREL,
                    residual="proportional",
                    nrel=NRELBasisSpec(
                        city_folder="NREL_Profiles/Newark",
                        groups={
                            1: ((8,), 1), 2: ((10,), 1), 3: ((13, 14, 15), 3),
                            4: ((4, 5, 12), 3), 5: ((1, 9, 11), 3),
                            6: ((3,), 1), 7: ((6,), 1), 8: ((2, 7), 2),
                            9: ((16,), 1), 10: ((17,), 1),
                        },
                        fit_groups=(10, 2, 6),
                    )),
        StateConfig(name="Pennsylvania", abbrev="PN", bus_state_code=2,
                    basis=BasisKind.NREL,
                    residual="proportional",
                    nrel=NRELBasisSpec(
                        city_folder="NREL_Profiles/Philadelphia",
                        groups={
                            1: ((8,), 1), 2: ((10,), 1), 3: ((13, 14, 15), 3),
                            4: ((4, 5, 12), 3), 5: ((1, 9, 11), 3),
                            6: ((3,), 1), 7: ((6,), 1),
                            8: ((2, 7), 1),   # ⚠ verbatim: NO /2, unlike NJ
                            9: ((16,), 1), 10: ((17,), 1),
                        },
                        fit_groups=(10, 2, 6),
                    )),
    ),
    bus_table=BusTableSpec(
        bus_number_col=1,
        state_code_col=5,
        share_cols=(24, 25, 26),
        cir_rows_cols=((1, 2), (28, 30)),
    ),
    expected_bus_count=5218,
    calendar_year=2015,
    notes="NREL archetype, proportional residual (SRVC-style). MATLAB PN "
          "commercial trend uses NJ_CIR(1) — fixed in LoadSmith. Canonical "
          "function applies KCL-KVL loadscaling (peak target 48,489 MW) to "
          "P and Q; reproduce with peak_scaling='kclkvl'. Dead day-type "
          "calendar; PA group 8 divisor 1 (verbatim, harmless after "
          "normalization, B7 family).",
)
