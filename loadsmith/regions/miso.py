"""MISO region config — Illinois, Iowa, Minnesota, Wisconsin.

Provenance: MISO/MakeLoadProfiles_MISO_NEW.m (496 lines; the reference
implementation of the NYSEG archetype). A byte-identical stray copy lives at
NYISO/MakeLoadProfiles_MISO_NEW.m (orphan).
Full extraction notes: docs/conversion_manual/regions/MISO.md.

Extraction facts verified against the MATLAB source (2026-07-09):

* CIR block: bus xlsx numeric rows 1:4, cols 28:30 (IL/IA/MN/WI).
* **Combined IA+MN fit** (unique quirk): ``IAMN = IA + MN`` fitted once with
  the energy-weighted CIR, then de-combined per class c with
  ``scale_c = IA_CIR[c]*E_IA / (IA_CIR[c]*E_IA + MN_CIR[c]*E_MN)`` and
  ``MN = IAMN - IA`` — expressed here as ``combine_group="IAMN"`` on both
  states (loadsmith.fitting.fit_combined_states).
* Residual added to the residential class CORRECTLY for IL, WI and the
  combined IAMN fit (the ``; +`` B3 typo does NOT occur in MISO; the
  residual-proportional alternatives are commented out).
* Distribution multiplies the RAW share columns (B12 energy deficit — MISO
  under-delivers Σ_c CIR_c·L_c); a ÷CIR line exists for MN only but is
  assigned to a dead ``P_MN`` variable. LoadSmith uses renormalized shares.
* Bus table has exactly 6,671 rows (B5 resolved: the ``1:6671`` smoothing
  loop was right, the commented 6672 wrong).
* **B8**: no ``BusNums`` — ``P_Load_MISO.csv`` has NO bus-number column.
  Q commented out.
"""

from __future__ import annotations

from loadsmith.config import BasisKind, BusTableSpec, RegionConfig, StateConfig

MISO = RegionConfig(
    name="MISO",
    matlab_source="MISO/MakeLoadProfiles_MISO_NEW.m",
    states=(
        StateConfig(name="Illinois", abbrev="IL", bus_state_code=1,
                    basis=BasisKind.NYSEG),
        StateConfig(name="Iowa", abbrev="IA", bus_state_code=2,
                    basis=BasisKind.NYSEG, combine_group="IAMN"),
        StateConfig(name="Minnesota", abbrev="MN", bus_state_code=3,
                    basis=BasisKind.NYSEG, combine_group="IAMN"),
        StateConfig(name="Wisconsin", abbrev="WI", bus_state_code=4,
                    basis=BasisKind.NYSEG),
    ),
    bus_table=BusTableSpec(
        bus_number_col=1,
        state_code_col=5,
        share_cols=(24, 25, 26),
        cir_rows_cols=((1, 4), (28, 30)),   # IL/IA/MN/WI x C/I/R
    ),
    expected_bus_count=6671,   # actual xlsx row count (B5 resolved)
    calendar_year=2015,
    notes="IA+MN fitted combined then de-combined per class (combine_group). "
          "No B3 residual typo. Q commented out in MATLAB; LoadSmith writes "
          "Q per D3. Legacy CSV lacks the bus-number column (B8). The UW "
          "reference P/Q are the OLD total-broadcast script's output; the "
          "stray NYISO/P_Load_MISO_NEW.csv is the _NEW per-class output "
          "(see regions/MISO.md).",
)
