"""Stage 3 — per-day fit-basis construction (three source families).

Produces, for each day, ``Base`` = (24, 1+k) with column 0 all-ones (trend)
and k class-shape columns each demeaned THEN L2-normalized (MATLAB order).
Spec: docs/conversion_manual/algorithms/03_basis_construction.md.

Roles are mapped BY NAME, never by column position — this is what fixes the
CAISO (res = col 4) and RFCW (com/ind/res order, misnamed vars) pitfalls.

Index conventions (MATLAB provenance — all config-facing indices 1-BASED):

* ``day``          : 1..365 (calendar day of the profile year)
* ``day_type``     : 1..36  (stage-2 calendar bucket, NYSEG archetype only)
* NYSEG slices     : 1..9   (class dimension of profiles_aggregate)
* NREL buildings   : 1..17  (17th = TMY-derived "residential" series)
* NREL groups      : 1..10  (frozen aggregate groups, decision D7)

Conversion to 0-based happens exactly once, inside this module, at each
``[... - 1]`` marked below. Nothing 0-based ever leaves this module's API.
"""

from __future__ import annotations

from typing import Protocol

import numpy as np

from loadsmith.config import NRELBasisSpec, Role, UtilityBasisSpec  # noqa: F401
# UtilityBasisSpec re-exported for callers that resolve parquet sources into
# the ``profiles_by_role`` dict consumed by UtilityBasis (HOOKS.md section 3).

#: Norm threshold below which a demeaned column is left as zeros instead of
#: being normalized. MATLAB would divide by ~0 and produce NaN/Inf here; we
#: choose all-zeros so the NNLS fit (stage 4) simply ignores the column.
_ZERO_NORM_TOL = 1e-12

HOURS_PER_DAY = 24
DAYS_PER_YEAR = 365


def _check_day(day: int) -> None:
    """Validate a 1-based calendar day (MATLAB convention, 1..365)."""
    if not 1 <= day <= DAYS_PER_YEAR:
        raise ValueError(f"day must be in 1..{DAYS_PER_YEAR} (1-based), got {day}")


def normalize_columns(base: np.ndarray) -> np.ndarray:
    """Demean + L2-normalize every column except column 0 (the trend).

    MATLAB order matters: each column is demeaned FIRST, then divided by the
    norm of the *demeaned* vector (``tmp = x - mean(x); tmp / norm(tmp)``).
    Column 0 (the all-ones trend column) is returned untouched.

    Zero-variance guard: if the demeaned column's norm is below
    ``_ZERO_NORM_TOL`` the column is set to exact zeros. MATLAB would produce
    NaN (0/0); we choose zeros so downstream NNLS simply ignores the column.

    Returns a NEW array; the input is never mutated.
    """
    out = np.array(base, dtype=float, copy=True)
    if out.ndim != 2:
        raise ValueError(f"expected a 2-D basis matrix, got ndim={out.ndim}")
    for j in range(1, out.shape[1]):
        v = out[:, j] - out[:, j].mean()
        n = float(np.linalg.norm(v))
        if n < _ZERO_NORM_TOL:
            out[:, j] = 0.0
        else:
            out[:, j] = v / n
    return out


class BasisSource(Protocol):
    """A per-day basis provider; one instance per (region, state)."""

    #: semantic role of each non-trend basis column, e.g. (RESIDENTIAL, CI, CI)
    roles: tuple[Role, ...]

    def day_basis(self, day: int, day_type: int) -> np.ndarray:
        """(24, 1+k) normalized basis for 1-based ``day`` (1..365)."""
        ...


class NYSEGBasis:
    """NYSEG archetype: profiles_aggregate slices (2, 3, 5), day-type indexed.

    Slice 2 = residential shape; slices 3 and 5 = commercial/industrial.
    Used by: MISO, NYISO, NEISO, FRCC (output-driving fit).

    ``roles`` is (RESIDENTIAL, COMMERCIAL, INDUSTRIAL) — but note the caveat:
    stage-4 fitting treats every non-RESIDENTIAL column as one joint
    commercial/industrial pool, so only the *position of Role.RESIDENTIAL*
    is semantically load-bearing. The COMMERCIAL/INDUSTRIAL labels on the
    remaining columns are nominal.
    """

    def __init__(self, profiles: np.ndarray, slices: tuple[int, ...] = (2, 3, 5)) -> None:
        """``profiles``: (24, 36, 9) hour x day-type x class array (stage 1).

        ``slices`` are 1-BASED class indices into the third dimension
        (MATLAB provenance); the default (2, 3, 5) is the production choice
        for every NYSEG-archetype region.
        """
        profiles = np.asarray(profiles, dtype=float)
        if profiles.ndim != 3 or profiles.shape[0] != HOURS_PER_DAY:
            raise ValueError(
                f"profiles must be (24, n_day_types, n_classes), got {profiles.shape}"
            )
        if not slices:
            raise ValueError("slices must be non-empty")
        for s in slices:
            if not 1 <= s <= profiles.shape[2]:
                raise ValueError(
                    f"slice {s} out of range 1..{profiles.shape[2]} (1-based)"
                )
        self._profiles = profiles
        self._slices = tuple(int(s) for s in slices)
        # First slice is residential; remaining columns are the joint C/I pool
        # (labels cycle COMMERCIAL, INDUSTRIAL — nominal, see class docstring).
        ci_cycle = (Role.COMMERCIAL, Role.INDUSTRIAL)
        self.roles: tuple[Role, ...] = (Role.RESIDENTIAL,) + tuple(
            ci_cycle[i % 2] for i in range(len(self._slices) - 1)
        )

    def day_basis(self, day: int, day_type: int) -> np.ndarray:
        """(24, 1+k) basis for the given 1-based ``day_type`` (1..36).

        ``day`` is validated but otherwise UNUSED — the NYSEG archetype is
        indexed purely by day-type (the stage-2 calendar maps day -> day_type
        upstream). It is kept in the signature for the BasisSource protocol.
        """
        _check_day(day)
        n_day_types = self._profiles.shape[1]
        if not 1 <= day_type <= n_day_types:
            raise ValueError(
                f"day_type must be in 1..{n_day_types} (1-based), got {day_type}"
            )
        base = np.ones((HOURS_PER_DAY, 1 + len(self._slices)))
        for j, s in enumerate(self._slices, start=1):
            # 1-based -> 0-based: day_type and slice both MATLAB-indexed.
            base[:, j] = self._profiles[:, day_type - 1, s - 1]
        return normalize_columns(base)


class NRELAggregateBasis:
    """NREL archetype: frozen aggregate groups, same-day slice of the 8760
    aggregate profiles (calendar NOT used — dead code in MATLAB).

    Used by: AZNM, NWPP, SPP, SRMV, SRTV, SRVC, RFCE.

    ``roles`` is (RESIDENTIAL, COMMERCIAL, INDUSTRIAL): ``spec.fit_groups``
    is in (residential, com/ind, com/ind) order per the MATLAB scripts. As
    with NYSEG, only the RESIDENTIAL position is load-bearing in stage 4;
    the two C/I labels are nominal.
    """

    def __init__(self, city_profiles: np.ndarray, spec: NRELBasisSpec) -> None:
        """``city_profiles``: (8760, 17) hourly building profiles for one city
        (16 DOE reference buildings + TMY series x1000 as column 17).
        """
        self._agg = self.aggregate(city_profiles, spec)
        n_groups = self._agg.shape[1]
        for g in spec.fit_groups:
            if not 1 <= g <= n_groups or g not in spec.groups:
                raise ValueError(
                    f"fit_group {g} not among the defined aggregate groups "
                    f"{sorted(spec.groups)} (1-based)"
                )
        self._fit_groups = tuple(int(g) for g in spec.fit_groups)
        self.roles: tuple[Role, ...] = (
            Role.RESIDENTIAL,
            Role.COMMERCIAL,
            Role.INDUSTRIAL,
        )

    @staticmethod
    def aggregate(city_profiles: np.ndarray, spec: NRELBasisSpec) -> np.ndarray:
        """(8760, 10) frozen aggregate group profiles from (8760, 17) input.

        Group column g (1-based) = sum of member building columns (1-based
        indices from ``spec.groups``) divided by the group's divisor. The
        divisor is preserved VERBATIM from MATLAB — including oddities like
        singleton/2 (B7), which are harmless because basis columns are
        demeaned + normalized afterwards.
        """
        cp = np.asarray(city_profiles, dtype=float)
        if cp.ndim != 2 or cp.shape[0] != DAYS_PER_YEAR * HOURS_PER_DAY:
            raise ValueError(
                f"city_profiles must be (8760, n_buildings), got {cp.shape}"
            )
        if not spec.groups:
            raise ValueError("spec.groups is empty")
        n_groups = max(spec.groups)
        out = np.zeros((cp.shape[0], n_groups))
        for g, (members, divisor) in spec.groups.items():
            if not 1 <= g <= n_groups:
                raise ValueError(f"group number {g} out of range 1..{n_groups}")
            idx = np.asarray(members, dtype=int) - 1  # 1-based -> 0-based
            if idx.size == 0 or idx.min() < 0 or idx.max() >= cp.shape[1]:
                raise ValueError(
                    f"group {g} members {members} out of range "
                    f"1..{cp.shape[1]} (1-based)"
                )
            out[:, g - 1] = cp[:, idx].sum(axis=1) / float(divisor)
        return out

    def day_basis(self, day: int, day_type: int) -> np.ndarray:
        """(24, 4) basis = the day's own 24-h window of the aggregates.

        ``day_type`` is IGNORED — the stage-2 calendar is dead code in every
        NREL-archetype MATLAB script; the parameter exists only to satisfy
        the BasisSource protocol. Rows (day-1)*24 .. day*24 (1-based day).
        """
        _check_day(day)
        rows = slice((day - 1) * HOURS_PER_DAY, day * HOURS_PER_DAY)
        base = np.ones((HOURS_PER_DAY, 1 + len(self._fit_groups)))
        for j, g in enumerate(self._fit_groups, start=1):
            base[:, j] = self._agg[rows, g - 1]  # 1-based group -> 0-based col
        return normalize_columns(base)


#: Fixed, insertion-independent column order for UtilityBasis — follows the
#: Role enum declaration order (COMMERCIAL, INDUSTRIAL, RESIDENTIAL). This
#: matches the CAISO/RFCW MATLAB layout where residential is the LAST basis
#: column (col 4 with the trend); stage 4 maps columns by ``roles``, never
#: by position, so the order is a documentation contract, not a fit input.
_UTILITY_ROLE_ORDER: tuple[Role, ...] = (
    Role.COMMERCIAL,
    Role.INDUSTRIAL,
    Role.RESIDENTIAL,
)


class UtilityBasis:
    """Utility archetype: (365, 24) class profiles indexed by calendar day.

    Used by: CAISO (PG&E a1/a10/e1), RFCW (Ohio Power Co. com/ind/res).
    """

    def __init__(self, profiles_by_role: dict[Role, np.ndarray]) -> None:
        """``profiles_by_role``: Role -> (365, 24) day x hour class profile.

        Column order in ``day_basis`` is FIXED by ``_UTILITY_ROLE_ORDER``
        (COMMERCIAL, INDUSTRIAL, RESIDENTIAL), independent of dict insertion
        order; ``roles`` reports the same order restricted to roles present.
        """
        if not profiles_by_role:
            raise ValueError("profiles_by_role must be non-empty")
        cleaned: dict[Role, np.ndarray] = {}
        for role, arr in profiles_by_role.items():
            a = np.asarray(arr, dtype=float)
            if a.shape != (DAYS_PER_YEAR, HOURS_PER_DAY):
                raise ValueError(
                    f"{role}: expected ({DAYS_PER_YEAR}, {HOURS_PER_DAY}) "
                    f"profile, got {a.shape}"
                )
            cleaned[role] = a
        self._profiles = cleaned
        self.roles: tuple[Role, ...] = tuple(
            r for r in _UTILITY_ROLE_ORDER if r in cleaned
        )

    def day_basis(self, day: int, day_type: int) -> np.ndarray:
        """(24, 1+len(roles)) basis for the 1-based calendar ``day``.

        ``day_type`` is IGNORED — utility profiles are indexed by calendar
        day directly (protocol-compatibility parameter only).
        """
        _check_day(day)
        base = np.ones((HOURS_PER_DAY, 1 + len(self.roles)))
        for j, role in enumerate(self.roles, start=1):
            base[:, j] = self._profiles[role][day - 1, :]  # 1-based -> 0-based
        return normalize_columns(base)
