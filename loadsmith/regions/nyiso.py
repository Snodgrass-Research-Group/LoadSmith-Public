"""NYISO region config — New York (single state).

Provenance: NYISO/MakeLoadProfiles_NYISO.m (180 lines; no in-repo _NEW
variant → decision D1 backport applies).
Full extraction notes: docs/conversion_manual/regions/NYISO.md.

Archetype: NYSEG, single state. Extraction facts verified against the
MATLAB source (2026-07-09):

* CIR block: bus xlsx numeric row 1, cols **27:29** (NOT 28:30 — same
  columns as FRCC); row sums 0.9988 (renormalized at fit time, C4).
* Residual correctly added to the residential class (no B3 typo).
* Distribution has bug **B9**: all three share columns multiply
  ``NY_load_total`` — the class decomposition is discarded and every bus is
  proportional to one series. LoadSmith implements per-class (D1).
* The KCL-KVL Master Load Data folder holds a ``MakeLoadProfiles_NYISO_NEW.m``
  (SLG 2020-12-17, not in this repo) that fixes B9 per-class with RAW shares
  (B12 unfixed) and actively writes P_Load_NYISO.csv — wave-4 provenance
  analysis shows the UW reference CSV matches THAT variant, not the rank-1
  B9 output (see regions/NYISO.md and tests/test_wave4_nyseg.py).
* Only NYSEG-family script that WRITES Q (random PFs, bug B2; superseded by
  D3 ranges). BusNums written as CSV column 1.
"""

from __future__ import annotations

from loadsmith.config import BasisKind, BusTableSpec, RegionConfig, StateConfig

NYISO = RegionConfig(
    name="NYISO",
    matlab_source="NYISO/MakeLoadProfiles_NYISO.m",
    states=(
        StateConfig(name="NewYork", abbrev="NY", bus_state_code=1,
                    basis=BasisKind.NYSEG),
    ),
    bus_table=BusTableSpec(
        bus_number_col=1,
        state_code_col=5,
        share_cols=(24, 25, 26),
        cir_rows_cols=((1, 1), (27, 29)),   # NY x C/I/R (27:29, like FRCC)
    ),
    expected_bus_count=4880,
    calendar_year=2015,
    notes="D1 backport: per-class distribution replaces the B9 total "
          "broadcast. Reference P CSV matches the KCL-KVL _NEW variant "
          "(per-class, raw shares); reference Q is the old B9 broadcast.",
)
