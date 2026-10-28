"""SRMV region config — AR, LA, MO (NREL archetype).

Provenance: SRMV/MakeLoadProfiles_SRMV.m (511 lines, canonical).
Full extraction notes: docs/conversion_manual/regions/SRMV.md.

Archetype: NREL production basis — per-day fit against the same day's 24-h
slice of the state's frozen aggregate profiles (NYSEG load line commented
out; day-type calendar block present but DEAD). Residual policy is
**proportional** (CIR-weighted) for every state — MATLAB adds
``XX_CIR(k)*XX_resid`` to each class; no ``; +`` typos (B3-clean), and every
state uses its OWN CIR throughout (no B6-style cross-state bug).

⚠ Louisiana CIR anomaly: the bus workbook's 'Total % C/I/R' row for LA sums
to **0.9025**, not 1.0 (AR and MO sum to 1.0000). The MATLAB uses it
verbatim, so LA class loads deliver only ~90.25% of the fitted trend +
residual energy (the shape terms are unscaled) — an energy leak analogous
to B12 but in the FIT stage. LoadSmith renormalizes CIR to sum to 1
(fitting.py), conserving energy; LA buses therefore run ~10% higher than
the 2024 reference. tests/test_wave4_south.py quantifies both variants.

Verbatim group oddities (harmless per B7): MO#5 = [1 11]/2 — omits building
9, unlike every other state's [1 9 11] cluster; MO#9 = [2 7] summed with NO
divisor. Cosmetic MATLAB typo at the MO block: ``profiles_aggregate_ =
zeros(...)`` initializes a stray variable (assignments auto-grow the real
profiles_aggregate_MO) — not ported.

CIR block: MATLAB reads ``Atmp(1:6,28:30)`` (SRVC copy-paste); only rows
1:3 exist/are used (rows 4:6 NaN); the migration reads rows 1:3.

Distribution: shares (cols 24:26) divided by the state CIR — the CORRECT
convention (B12/F3), numerically identical to LoadSmith's renormalized
shares. Q computed AND written (Q_Load_SRMV.csv) with unseeded rand + bug
B2; smoothing loop 1:3123 was a no-op (B1). F1 RESOLVED for SRMV: the bus
table has exactly 3,123 rows, so the 3123 bound was correct here — whether
SPP's identical bound is a copy-paste stays open until SPP migrates.
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
    "AR": NRELBasisSpec(
        city_folder="NREL_Profiles/Little_Rock",
        groups={
            1: ((8,), 1), 2: ((10,), 1), 3: ((13, 14, 15), 3),
            4: ((4, 5, 12), 3), 5: ((1, 9, 11), 3), 6: ((3,), 1),
            7: ((6,), 1), 8: ((16,), 1), 9: ((2, 7), 2), 10: ((17,), 1),
        },
        fit_groups=(10, 1, 6),
    ),
    "LO": NRELBasisSpec(
        city_folder="NREL_Profiles/New_Orleans",
        groups={
            1: ((8,), 1), 2: ((10,), 1), 3: ((4, 5, 13, 14, 15), 5),
            4: ((12,), 1), 5: ((1, 9, 11), 3), 6: ((3,), 1),
            7: ((6,), 1), 8: ((2, 7), 2), 9: ((16,), 1), 10: ((17,), 1),
        },
        fit_groups=(10, 6, 8),
    ),
    "MO": NRELBasisSpec(
        city_folder="NREL_Profiles/Kansas_City",
        groups={
            1: ((13, 14, 15), 3), 2: ((4, 5, 12), 3), 3: ((8,), 1),
            4: ((10,), 1),
            5: ((1, 11), 2),     # ⚠ omits building 9 (elsewhere [1 9 11])
            6: ((3,), 1), 7: ((6,), 1), 8: ((16,), 1),
            9: ((2, 7), 1),      # ⚠ summed, NO mean divisor (verbatim)
            10: ((17,), 1),
        },
        fit_groups=(10, 6, 9),
    ),
}


def _state(name: str, abbrev: str, code: int) -> StateConfig:
    return StateConfig(
        name=name, abbrev=abbrev, bus_state_code=code,
        basis=BasisKind.NREL, nrel=_NREL[abbrev],
        residual="proportional",   # MATLAB: XX_CIR(k)*XX_resid on every class
    )


SRMV = RegionConfig(
    name="SRMV",
    matlab_source="SRMV/MakeLoadProfiles_SRMV.m",
    states=(
        _state("Arkansas", "AR", 1),
        _state("Louisiana", "LO", 2),   # MATLAB variable LO (not LA)
        _state("Missouri", "MO", 3),
    ),
    bus_table=BusTableSpec(
        bus_number_col=1,
        state_code_col=5,
        share_cols=(24, 25, 26),
        cir_rows_cols=((1, 3), (28, 30)),   # MATLAB reads rows 1:6 (SRVC
                                            # copy-paste); only 1:3 are real
    ),
    expected_bus_count=3123,   # smoothing/LoadDist bound 1:3123 == actual rows
    calendar_year=2015,
    notes="NREL production basis; residual proportional (CIR-weighted); "
          "each state uses its own CIR (no B6 analogue). ⚠ LA raw CIR sums "
          "to 0.9025 — LoadSmith renormalizes (energy-conserving), so LA "
          "runs ~10% above the MATLAB reference. Verbatim group oddities: "
          "MO#5 [1 11]/2 omits bldg 9, MO#9 [2 7] no divisor (B7-harmless). "
          "Q written in MATLAB (unseeded, B2); LoadSmith Q per D3.",
)
