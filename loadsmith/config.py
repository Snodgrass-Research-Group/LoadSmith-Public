"""Region configuration schema — the declarative heart of LoadSmith.

Every difference between the 13 MATLAB main scripts that is *data* (states,
city folders, frozen cluster groups, spreadsheet column maps, fit-basis
indices, policies) lives in a :class:`RegionConfig` instance under
``loadsmith/regions/``. Everything that is *behavior* lives in the stage
modules, keyed by the small enums here.

Conversion contract: a region is "converted" when its ``RegionConfig`` is
complete and the pipeline passes validation for it
(docs/conversion_manual/VALIDATION_MATRIX.md).

Design decisions: D7 (frozen cluster groups as config), C4 (shares
renormalized at ingestion), C5 (one config module per region).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Literal

# --------------------------------------------------------------------------- #
# Enums / policies
# --------------------------------------------------------------------------- #


class BasisKind(Enum):
    """Where a state's daily fit basis comes from (algorithms/03)."""

    NYSEG = "nyseg"          # 36 day-type profiles, calendar-selected
    NREL = "nrel"            # frozen aggregate groups, same-day year slice
    UTILITY = "utility"      # 365x24 utility class profiles (CAISO, RFCW)


class Role(Enum):
    """Semantic role of a basis column / class index (order: C, I, R)."""

    COMMERCIAL = 0
    INDUSTRIAL = 1
    RESIDENTIAL = 2


ResidualPolicy = Literal["residential", "proportional", "drop"]
# residential  : residual added wholly to the residential class (most regions)
# proportional : residual split by CIR fractions (SRVC; FRCC "AE" variant)
# drop         : residual discarded (FRCC MATLAB-faithful mode, bug B3)

SmoothingPolicy = Literal["qp", "none"]
# qp   : day-boundary QP on state class profiles (algorithms/05, C2)
# none : skip (matches MATLAB reference outputs -- smoothing was a no-op, B1)


# Reactive-power power-factor ranges, uniform per bus per class (decision D3;
# deliberately NEWER/HIGHER than the MATLAB ranges -- a design decision).
PF_RANGES: dict[Role, tuple[float, float]] = {
    Role.COMMERCIAL: (0.98, 0.99),
    Role.INDUSTRIAL: (0.99, 1.00),
    Role.RESIDENTIAL: (0.95, 0.98),
}

DEFAULT_SEED = 20260708  # reproducible PF draws (D3); recorded in run metadata


# --------------------------------------------------------------------------- #
# Per-state configuration
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class NRELBasisSpec:
    """Frozen NREL aggregation for one state (NREL archetype only).

    ``groups`` maps aggregate-group number (1..10) to (member building
    indices 1..17, divisor). Extracted VERBATIM from the MATLAB
    ``profiles_aggregate_XX`` blocks -- including oddities like singleton/2
    (B7), which are harmless because basis columns are demeaned+normalized.

    ``fit_groups`` are the 3 group numbers used as basis columns, in
    (residential, com/ind, com/ind) order as in MATLAB.
    """

    city_folder: str                                  # e.g. "NREL_Profiles/Baltimore"
    groups: dict[int, tuple[tuple[int, ...], float]]
    fit_groups: tuple[int, int, int]                  # e.g. (10, 2, 6)


@dataclass(frozen=True)
class UtilityBasisSpec:
    """365x24 utility class profiles for one state (CAISO / RFCW).

    ``sources`` maps Role -> parquet source key (see HOOKS.md section 3),
    e.g. CAISO: {COMMERCIAL: "a1", INDUSTRIAL: "a10", RESIDENTIAL: "e1"}.
    """

    sources: dict[Role, str]


@dataclass(frozen=True)
class StateConfig:
    """One state's inputs within a region."""

    name: str                       # "Florida"
    abbrev: str                     # "FL"
    bus_state_code: int             # value in the bus table's state-code column
    basis: BasisKind
    nrel: NRELBasisSpec | None = None
    utility: UtilityBasisSpec | None = None
    residual: ResidualPolicy = "residential"
    # MISO-only: states fit as a combined series then de-combined per class
    # (algorithms/04). States sharing a combine_group are summed for the fit.
    combine_group: str | None = None


# --------------------------------------------------------------------------- #
# Region configuration
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class BusTableSpec:
    """Column map for '<REGION> bus data.xlsx' (NUMERIC-matrix indices, 1-based
    as in the MATLAB xlsread result -- migration re-derives real columns).

    Note: share columns are renormalized at migration so each state's class
    column sums to 1.0 (C4) -- this neutralizes the two MATLAB distribution
    conventions (flag F3).
    """

    bus_number_col: int = 1
    state_code_col: int = 5          # CAISO: 6
    share_cols: tuple[int, int, int] = (24, 25, 26)   # C, I, R; CAISO: (26, 27, 28)
    cir_rows_cols: tuple[tuple[int, int], tuple[int, int]] | None = None
    # ((first_row, last_row), (first_col, last_col)) of the state CIR block,
    # e.g. FRCC ((1, 3), (27, 29)); None = CIR hard-coded (CAISO)


@dataclass(frozen=True)
class RegionConfig:
    """Everything LoadSmith needs to run one region."""

    name: str                        # "FRCC"
    matlab_source: str               # canonical .m file (provenance)
    states: tuple[StateConfig, ...]
    bus_table: BusTableSpec
    expected_bus_count: int | None = None   # MATLAB hard-coded count; verify only
    cir_hardcoded: dict[str, tuple[float, float, float]] = field(default_factory=dict)
    # state abbrev -> (C, I, R); only CAISO uses this
    calendar_year: int = 2015        # F4: hand-coded MATLAB calendar == 2015
    notes: str = ""                  # quirks; long-form in docs/…/regions/<R>.md
