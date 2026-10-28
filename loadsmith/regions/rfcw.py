"""RFCW region config — Indiana, Michigan, Ohio.

Provenance: RFCW/MakeLoadProfiles_RFCW.m (443 lines).
Full extraction: docs/conversion_manual/regions/RFCW.md.

Archetype: **utility** — Ohio Power Company (OPC) 2016 class profiles
(365x24 com/ind/res) are the fit basis for ALL THREE states, indexed by
calendar day. NYSEG and Columbus Southern fits exist in the MATLAB as
comparison-only dead ends (the latter with bug B10).

⚠ SEMANTICS WARNING (regions/RFCW.md): the MATLAB reuses the NYSEG-archetype
split formulas on a com/ind/res-ordered basis, so its "Res_top" slot
actually receives the COMMERCIAL shape and the com/ind pool gets ind+res.
LoadSmith maps roles BY NAME (the evident intent — residential shape to the
residential class). Which behavior the UW reference embodies is settled
empirically in regions/RFCW.md (validation); if the reference
matches the mismapped variant, the MATLAB-faithful comparison must swap
roles accordingly (see tests/test_wave4_utility.py).

Residual: all three states add the daily residual to the residential class
correctly (no B3 typo) -> "residential".
"""

from __future__ import annotations

from loadsmith.config import (
    BasisKind,
    BusTableSpec,
    RegionConfig,
    Role,
    StateConfig,
    UtilityBasisSpec,
)

_OPC = UtilityBasisSpec(sources={
    Role.COMMERCIAL: "opc_com",
    Role.INDUSTRIAL: "opc_ind",
    Role.RESIDENTIAL: "opc_res",
})

RFCW = RegionConfig(
    name="RFCW",
    matlab_source="RFCW/MakeLoadProfiles_RFCW.m",
    states=(
        StateConfig(name="Indiana", abbrev="IN", bus_state_code=1,
                    basis=BasisKind.UTILITY, utility=_OPC),
        StateConfig(name="Michigan", abbrev="MI", bus_state_code=2,
                    basis=BasisKind.UTILITY, utility=_OPC),
        StateConfig(name="Ohio", abbrev="OH", bus_state_code=3,
                    basis=BasisKind.UTILITY, utility=_OPC),
    ),
    bus_table=BusTableSpec(
        bus_number_col=1,
        state_code_col=5,
        share_cols=(24, 25, 26),
        cir_rows_cols=((1, 3), (28, 30)),
    ),
    expected_bus_count=7217,
    calendar_year=2015,   # NB: OPC data is 2016YTD — F4 note in RFCW.md
    notes="OPC utility basis for all states; ÷CIR distribution in MATLAB "
          "(F3 convention #2, energy-correct); Q written in MATLAB (B2 bug). "
          "Role mapping by name fixes the MATLAB column-order mismatch — "
          "validation verdict in regions/RFCW.md.",
)
