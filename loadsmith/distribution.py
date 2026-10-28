"""Stage 6 — bus distribution and reactive power.

P[b,t] = sum_c share[b,c] * class_load[t,c]  (per-class everywhere — D1;
shares renormalized at ingestion so each state's class column sums to 1,
which conserves energy and neutralizes the two MATLAB conventions, F3).

Q[b,t] = sum_c sqrt(1-pf²)/pf [b,c] * share[b,c] * class_load[t,c] with
per-bus power factors ~ U(PF_RANGES[role]) from a seeded generator (D3 —
NEW ranges: C 0.98-0.99, I 0.99-1.00, R 0.95-0.98; fixes MATLAB bug B2 and
NYISO's total-broadcast bug B9).

Spec: docs/conversion_manual/algorithms/06_distribution_reactive.md.
Implemented.
"""

from __future__ import annotations

import numpy as np

from loadsmith.config import PF_RANGES, Role

HOURS_PER_YEAR = 8760
N_CLASSES = 3  # C, I, R (Role order)


def draw_power_factors(n_bus: int, seed: int, region: str) -> np.ndarray:
    """(n_bus, 3) per-bus power factors, one column per Role (C, I, R).

    Deterministic for a given (seed, region) and independent across regions:
    the generator is seeded with a ``numpy.random.SeedSequence`` whose
    entropy is ``seed`` followed by the region name's UPPERCASE byte values
    (``np.random.default_rng([seed, *region.upper().encode()])``). The draw
    order is FIXED and part of the reproducibility contract (D3): one
    ``uniform(lo, hi, n_bus)`` call per class, in Role order
    COMMERCIAL -> INDUSTRIAL -> RESIDENTIAL, with (lo, hi) = PF_RANGES[role].
    """
    if n_bus < 1:
        raise ValueError(f"n_bus must be >= 1, got {n_bus}")
    if not region or not region.strip():
        raise ValueError("region must be a non-empty string")
    rng = np.random.default_rng([seed, *region.upper().encode()])
    pf = np.empty((n_bus, N_CLASSES), dtype=np.float64)
    for role in (Role.COMMERCIAL, Role.INDUSTRIAL, Role.RESIDENTIAL):
        lo, hi = PF_RANGES[role]
        pf[:, role.value] = rng.uniform(lo, hi, n_bus)
    return pf


def _check_class_loads_and_shares(
    class_loads: np.ndarray, shares: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """Validate the HOOKS §2 contract shapes; return float64 arrays."""
    class_loads = np.asarray(class_loads, dtype=np.float64)
    shares = np.asarray(shares, dtype=np.float64)
    if class_loads.ndim != 2 or class_loads.shape != (HOURS_PER_YEAR, N_CLASSES):
        raise ValueError(
            f"class_loads must have shape ({HOURS_PER_YEAR}, {N_CLASSES}) "
            f"[hour x C/I/R]; got {class_loads.shape}")
    if shares.ndim != 2 or shares.shape[1] != N_CLASSES:
        raise ValueError(
            f"shares must have shape (n_bus, {N_CLASSES}) [bus x C/I/R]; "
            f"got {shares.shape}")
    if np.any(shares < 0.0):
        raise ValueError(
            "bus shares must be non-negative (renormalized C4 shares)")
    return class_loads, shares


def distribute(
    class_loads: np.ndarray,   # (8760, 3) state C/I/R loads
    shares: np.ndarray,        # (n_bus, 3) renormalized per-class bus shares
) -> np.ndarray:
    """(n_bus, 8760) real power: one BLAS matmul (shares @ class_loads.T).

    With shares renormalized so each class column sums to 1 over a state's
    buses (C4), state energy is conserved exactly:
    ``P.sum(axis=0) == class_loads.sum(axis=1)``.
    """
    class_loads, shares = _check_class_loads_and_shares(class_loads, shares)
    return shares @ class_loads.T


def reactive_power(
    class_loads: np.ndarray,
    shares: np.ndarray,
    power_factors: np.ndarray,  # (n_bus, 3)
) -> np.ndarray:
    """(n_bus, 8760) reactive power via qf = sqrt(1-pf²)/pf per class.

    Each class's qf uses ITS OWN power factor column — this fixes MATLAB
    bug B2, where the industrial/residential qf were divided by the
    COMMERCIAL pf. Computed as one matmul: Q = (qf * shares) @ class_loads.T.
    """
    class_loads, shares = _check_class_loads_and_shares(class_loads, shares)
    pf = np.asarray(power_factors, dtype=np.float64)
    if pf.shape != shares.shape:
        raise ValueError(
            f"power_factors must have shape {shares.shape} "
            f"(matching shares); got {pf.shape}")
    if np.any(pf <= 0.0) or np.any(pf > 1.0):
        raise ValueError("power factors must lie in (0, 1]")
    qf = np.sqrt(1.0 - pf * pf) / pf
    return (qf * shares) @ class_loads.T
