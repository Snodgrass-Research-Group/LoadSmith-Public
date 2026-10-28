"""CAISO region config — California (single state).

Provenance: CAISO/MakeLoadProfiles_CAISO_NEW.m (canonical, 207 lines).
Full extraction: docs/conversion_manual/regions/CAISO.md.

Archetype: **utility** — the fit basis is the PG&E year-2000 rate-class
daily profiles (a1 small commercial / a10 medium-industrial / e1
residential), indexed by calendar day. The NYSEG profiles are loaded but
UNUSED in the MATLAB (dead pedigree code). CIR is hard-coded in the MATLAB
([0.455, 0.197, 0.348], "from EIA data") — carried here via cir_hardcoded
AND baked into the migrated cir_fractions.parquet.

MATLAB quirks not carried into production: raw-share distribution (B12);
Q commented out; the e1 headerless-CSV day-shift is faithful in the store
(same quirk as NWPP). Residual policy: residential (the MATLAB adds the
residual to the residential class correctly — no B3 typo).
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

_PGE = UtilityBasisSpec(sources={
    Role.COMMERCIAL: "a1",
    Role.INDUSTRIAL: "a10",
    Role.RESIDENTIAL: "e1",
})

CAISO = RegionConfig(
    name="CAISO",
    matlab_source="CAISO/MakeLoadProfiles_CAISO_NEW.m",
    states=(
        StateConfig(name="California", abbrev="CA", bus_state_code=1,
                    basis=BasisKind.UTILITY, utility=_PGE),
    ),
    bus_table=BusTableSpec(
        bus_number_col=1,
        state_code_col=6,            # tracts workbook layout (regions/CAISO.md)
        share_cols=(26, 27, 28),
        cir_rows_cols=None,          # CIR hard-coded, not in the workbook
    ),
    expected_bus_count=8034,         # F2 RESOLVED: exact row count
    cir_hardcoded={"CA": (0.455, 0.197, 0.348)},
    calendar_year=2015,
    notes="Utility archetype (PG&E a1/a10/e1). Bus workbook uses the "
          "national-map column order (regional col 3, peak col 18 — handled "
          "at migration). Two UW reference P variants exist (2019 _NEW / "
          "2021 plain) — verdicts in regions/CAISO.md.",
)
