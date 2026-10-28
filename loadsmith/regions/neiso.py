"""NEISO region config — Connecticut, Maine, Massachusetts, New Hampshire,
Rhode Island, Vermont.

Provenance: NEISO/MakeLoadProfiles_NEISO_NEW.m (canonical; the plain
MakeLoadProfiles_NEISO.m is the superseded total-broadcast variant — the
boxnote "P_Load_NEISO IS BAD DO NOT USE 10302019" refers to its output:
"Perfect correlation across buses for 8760").
Full extraction notes: docs/conversion_manual/regions/NEISO.md.

Archetype: NYSEG (profiles_aggregate slices 2/3/5, day-type calendar) — the
plain MISO-style per-class script, no NREL sections at all.

Extraction facts verified against the MATLAB source (2026-07-09):

* CIR block: bus xlsx numeric rows 1:6, cols 28:30 (CT/ME/MA/NH/RI/VT);
  rows sum to 1.0000.
* All six states add their daily residual to the residential class CORRECTLY
  (``+ XX_resid;`` after a ``...`` line continuation — the FRCC ``; +`` typo
  (B3) does NOT occur in NEISO). Production and MATLAB-faithful residual
  policy are both "residential".
* Distribution uses the raw share columns (B12 energy deficit); LoadSmith
  uses renormalized shares (C4).
* Q entirely commented out (fit-loop react blocks AND the Q distribution);
  LoadSmith writes Q per D3.
* ``csvwrite('P_Load_NEISO.csv', P_load)`` has NO bus-number column —
  the B8 defect is NOT MISO-only (BusNums never built here either).
"""

from __future__ import annotations

from loadsmith.config import BasisKind, BusTableSpec, RegionConfig, StateConfig

NEISO = RegionConfig(
    name="NEISO",
    matlab_source="NEISO/MakeLoadProfiles_NEISO_NEW.m",
    states=(
        StateConfig(name="Connecticut", abbrev="CT", bus_state_code=1,
                    basis=BasisKind.NYSEG),
        StateConfig(name="Maine", abbrev="ME", bus_state_code=2,
                    basis=BasisKind.NYSEG),
        StateConfig(name="Massachusetts", abbrev="MA", bus_state_code=3,
                    basis=BasisKind.NYSEG),
        StateConfig(name="NewHampshire", abbrev="NH", bus_state_code=4,
                    basis=BasisKind.NYSEG),
        StateConfig(name="RhodeIsland", abbrev="RI", bus_state_code=5,
                    basis=BasisKind.NYSEG),
        StateConfig(name="Vermont", abbrev="VT", bus_state_code=6,
                    basis=BasisKind.NYSEG),
    ),
    bus_table=BusTableSpec(
        bus_number_col=1,
        state_code_col=5,
        share_cols=(24, 25, 26),
        cir_rows_cols=((1, 6), (28, 30)),   # CT/ME/MA/NH/RI/VT x C/I/R
    ),
    expected_bus_count=3370,
    calendar_year=2015,
    notes="No B3 residual typo (all six states conserve energy). Q commented "
          "out in MATLAB; LoadSmith writes Q per D3. Legacy CSV lacks the "
          "bus-number column (B8-style). VALIDATED: the UW reference "
          "P CSV is a regenerated ÷CIR per-class output (NOT the old "
          "total-broadcast file) — matches production mode at scale 1.0000, "
          "median rel diff ~7e-06 per state (regions/NEISO.md).",
)
