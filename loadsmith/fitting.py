"""Stage 4 — daily NNLS decomposition into C/I/R class loads.

Per day: ``alpha = nnls(Base, y)``; split trend by CIR shares, com/ind shape
energy C:I, residential shape (+ residual, per policy) to residential.
Spec: docs/conversion_manual/algorithms/04_daily_fit.md.
Replaces the inline lsqnonneg blocks of every MATLAB main.

Fixes carried here: B3 (FRCC residual no-op -> policy switch),
B6 (SRVC WV uses MD's CIR -> correct state), MISO IA+MN combined fit.

Column-role convention (see basis.py): the position of ``Role.RESIDENTIAL``
in ``basis.roles`` is the only load-bearing label — every OTHER non-trend
column belongs to the joint commercial/industrial pool, whatever its nominal
COMMERCIAL/INDUSTRIAL tag says.

Implementation status: IMPLEMENTED.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.optimize import nnls

from loadsmith.basis import DAYS_PER_YEAR, HOURS_PER_DAY, BasisSource
from loadsmith.config import ResidualPolicy, Role

HOURS_PER_YEAR = DAYS_PER_YEAR * HOURS_PER_DAY  # 8760

_POLICIES = ("residential", "proportional", "drop")


@dataclass
class FitResult:
    """State-level decomposition (HOOKS.md contract 'ClassLoads')."""

    class_loads: np.ndarray  # (8760, 3) [C, I, R] MW
    alphas: np.ndarray       # (365, 1+k) NNLS coefficients per day
    residuals: np.ndarray    # (8760,) y - fit (diagnostics / plotting)

    def total(self) -> np.ndarray:
        """(8760,) sum over classes; == state load unless residual='drop'."""
        return self.class_loads.sum(axis=1)


def _validate_inputs(
    load: np.ndarray,
    day_types: np.ndarray,
    cir: tuple[float, float, float],
    residual: str,
) -> tuple[np.ndarray, np.ndarray, tuple[float, float, float]]:
    """Common shape/value checks; returns cleaned (load, day_types, cir)."""
    load = np.asarray(load, dtype=float)
    if load.shape != (HOURS_PER_YEAR,):
        raise ValueError(f"load must have shape ({HOURS_PER_YEAR},), got {load.shape}")
    day_types = np.asarray(day_types)
    if day_types.shape != (DAYS_PER_YEAR,):
        raise ValueError(
            f"day_types must have shape ({DAYS_PER_YEAR},), got {day_types.shape}"
        )
    cir_t = tuple(float(x) for x in cir)
    if len(cir_t) != 3:
        raise ValueError(f"cir must be a (C, I, R) triple, got length {len(cir_t)}")
    if any(x < 0 for x in cir_t):
        raise ValueError(f"cir fractions must be non-negative, got {cir_t}")
    c, i, r = cir_t
    if c + i == 0.0:
        raise ValueError(
            "cir has C + I == 0: the commercial/industrial shape energy is "
            "split C:I, which is undefined when both fractions are zero"
        )
    # Renormalize to sum exactly 1 (C4 spirit: shares renormalized at the
    # boundary). The raw xlsx CIR rows sum only ~1 (FRCC FL: 0.9958); using
    # them verbatim would scale the trend term by C+I+R and silently leak
    # trend energy, breaking the 04-doc validation invariant
    # (load_C + load_I + load_R == y for energy-conserving policies).
    s = c + i + r
    cir_t = (c / s, i / s, r / s)
    if residual not in _POLICIES:
        raise ValueError(f"residual must be one of {_POLICIES}, got {residual!r}")
    return load, day_types, cir_t  # type: ignore[return-value]


def fit_state(
    load: np.ndarray,                      # (8760,) state demand
    basis: BasisSource,
    day_types: np.ndarray,                 # (365,) from profile_calendar
    cir: tuple[float, float, float],       # state (C, I, R) fractions
    *,
    residual: ResidualPolicy = "residential",
) -> FitResult:
    """365 independent 24-point NNLS fits + class split (algorithms/04).

    Per day d (1-based): ``alpha = nnls(Base, y)`` with
    ``Base = basis.day_basis(d, day_types[d-1])`` (24, 1+k). Components:

    * Trend  = ``Base[:,0] * alpha[0]``      -> split by CIR shares
    * Res    = residential column * its alpha -> residential
    * CI     = all remaining shape columns    -> split C : I

    Residual policy: ``"residential"`` adds ``y - fit`` wholly to the
    residential class (energy-conserving, most regions); ``"proportional"``
    splits it by CIR (SRVC; FRCC "AE" variant — also energy-conserving);
    ``"drop"`` discards it (MATLAB FRCC bug B3 — class sums == fit != y).

    ``cir`` is renormalized to sum exactly 1 (raw xlsx rows sum only ~1),
    so for the two energy-conserving policies ``class_loads.sum(axis=1)``
    equals ``load`` to float tolerance — the stage-4 validation invariant.
    """
    load, day_types, cir = _validate_inputs(load, day_types, cir, residual)
    if Role.RESIDENTIAL not in basis.roles:
        raise ValueError(
            f"basis.roles {basis.roles} has no Role.RESIDENTIAL column — "
            "stage 4 cannot locate the residential shape"
        )
    c_frac, i_frac, r_frac = cir
    ci_total = c_frac + i_frac

    # Column bookkeeping: col 0 = trend; res_col = the residential shape;
    # every other column joins the joint C/I pool regardless of nominal label.
    n_cols = 1 + len(basis.roles)
    res_col = 1 + basis.roles.index(Role.RESIDENTIAL)
    ci_cols = [j for j in range(1, n_cols) if j != res_col]

    class_loads = np.empty((HOURS_PER_YEAR, 3))
    alphas = np.empty((DAYS_PER_YEAR, n_cols))
    residuals = np.empty(HOURS_PER_YEAR)

    for d in range(1, DAYS_PER_YEAR + 1):
        rows = slice((d - 1) * HOURS_PER_DAY, d * HOURS_PER_DAY)
        y = load[rows]
        base = basis.day_basis(d, int(day_types[d - 1]))
        if base.shape != (HOURS_PER_DAY, n_cols):
            raise ValueError(
                f"day {d}: basis returned {base.shape}, expected "
                f"({HOURS_PER_DAY}, {n_cols})"
            )
        alpha, _ = nnls(base, y)
        fit = base @ alpha
        resid = y - fit

        trend = base[:, 0] * alpha[0]
        res = base[:, res_col] * alpha[res_col]
        ci = base[:, ci_cols] @ alpha[ci_cols]

        load_c = trend * c_frac + ci * (c_frac / ci_total)
        load_i = trend * i_frac + ci * (i_frac / ci_total)
        load_r = trend * r_frac + res
        if residual == "residential":
            load_r = load_r + resid
        elif residual == "proportional":
            load_c = load_c + c_frac * resid
            load_i = load_i + i_frac * resid
            load_r = load_r + r_frac * resid
        # "drop": residual discarded (B3) — class sums == fit, not y.

        class_loads[rows, 0] = load_c
        class_loads[rows, 1] = load_i
        class_loads[rows, 2] = load_r
        alphas[d - 1, :] = alpha
        residuals[rows] = resid

    return FitResult(class_loads=class_loads, alphas=alphas, residuals=residuals)


def fit_combined_states(
    loads: dict[str, np.ndarray],
    cirs: dict[str, tuple[float, float, float]],
    basis: BasisSource,
    day_types: np.ndarray,
    *,
    residual: ResidualPolicy = "residential",
) -> dict[str, FitResult]:
    """MISO IA+MN quirk: fit the summed series once, then de-combine per class.

    Exactly two states. The combined series is ``load_a + load_b`` with an
    energy-weighted CIR: ``cir[c] = (cir_a[c]*E_a + cir_b[c]*E_b) / (E_a+E_b)``
    where ``E = load.sum()``. After a single :func:`fit_state`, each class
    column is split by ``scale_a[c] = cir_a[c]*E_a / (cir_a[c]*E_a +
    cir_b[c]*E_b)`` (regions/MISO.md) and state b takes the exact remainder,
    so ``a + b == combined`` per class by construction. If a class's weight
    denominator is zero (both states have a 0 fraction), the split falls back
    to the plain energy share ``E_a / (E_a + E_b)`` — MATLAB would emit NaN.

    Diagnostics choice: the NNLS solve happens once on the combined series,
    so per-state alphas/residuals do not exist. Each state receives a copy of
    the COMBINED alphas and the combined residuals scaled by
    ``E_state / E_total`` (the two states' residuals then sum back to the
    combined residuals). These are diagnostic conventions only — class loads
    are the contractual output.
    """
    if len(loads) != 2:
        raise ValueError(f"fit_combined_states takes exactly 2 states, got {len(loads)}")
    if set(loads) != set(cirs):
        raise ValueError(
            f"loads/cirs state keys differ: {sorted(loads)} vs {sorted(cirs)}"
        )
    key_a, key_b = loads.keys()
    load_a = np.asarray(loads[key_a], dtype=float)
    load_b = np.asarray(loads[key_b], dtype=float)
    for key, arr in ((key_a, load_a), (key_b, load_b)):
        if arr.shape != (HOURS_PER_YEAR,):
            raise ValueError(
                f"{key}: load must have shape ({HOURS_PER_YEAR},), got {arr.shape}"
            )
    cir_a = tuple(float(x) for x in cirs[key_a])
    cir_b = tuple(float(x) for x in cirs[key_b])
    for key, cir in ((key_a, cir_a), (key_b, cir_b)):
        if len(cir) != 3 or any(x < 0 for x in cir):
            raise ValueError(f"{key}: cir must be 3 non-negative fractions, got {cir}")

    e_a = float(load_a.sum())
    e_b = float(load_b.sum())
    e_total = e_a + e_b
    if e_total <= 0:
        raise ValueError("combined annual energy is not positive — cannot weight CIR")

    combined = load_a + load_b
    combined_cir = tuple(
        (cir_a[c] * e_a + cir_b[c] * e_b) / e_total for c in range(3)
    )
    combined_result = fit_state(
        combined, basis, day_types, combined_cir, residual=residual
    )

    # Per-class de-combination weights for state a (state b = 1 - scale).
    scale_a = np.empty(3)
    for c in range(3):
        denom = cir_a[c] * e_a + cir_b[c] * e_b
        scale_a[c] = (cir_a[c] * e_a / denom) if denom > 0 else e_a / e_total

    class_a = combined_result.class_loads * scale_a  # broadcast over columns
    class_b = combined_result.class_loads - class_a  # exact remainder

    return {
        key_a: FitResult(
            class_loads=class_a,
            alphas=combined_result.alphas.copy(),
            residuals=combined_result.residuals * (e_a / e_total),
        ),
        key_b: FitResult(
            class_loads=class_b,
            alphas=combined_result.alphas.copy(),
            residuals=combined_result.residuals * (e_b / e_total),
        ),
    }
