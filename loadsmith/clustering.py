"""Optional analysis tool — building-profile clustering (NOT in the pipeline).

Re-implements the exploratory analysis whose results were frozen into the
per-region aggregate groups (decision D7): per city, demean/normalize each
building profile per day, correlation matrix R = (Y'Y)[:16,:16], then
agglomerative clustering (MATLAB clusterdata(R, 9) ~= single-linkage
euclidean on rows of R, cut at 9 clusters).

Use when onboarding a NEW region/city to propose aggregation groups; a human
still reviews and freezes them into config (that's what happened in MATLAB).

Spec: docs/conversion_manual/algorithms/03_basis_construction.md §B.
"""

from __future__ import annotations

import numpy as np
from scipy.cluster.hierarchy import fcluster, linkage

#: Same zero-variance guard as basis.normalize_columns: a day slice whose
#: demeaned norm is below this is left as zeros (MATLAB would produce NaN).
_ZERO_NORM_TOL = 1e-12

_HOURS = 24
_DAYS = 365
_BUILDINGS = 17  # 16 DOE reference buildings + TMY series (column 17)


def building_correlation_matrix(city_profiles: np.ndarray) -> np.ndarray:
    """(16, 16) correlation of per-day-normalized building profiles.

    ``city_profiles``: (8760, 17) hourly profiles, one column per building
    (columns 1..17 in MATLAB terms; the 17th/TMY column participates in the
    normalization but is EXCLUDED from the returned matrix, as in MATLAB).

    For every building column and every one of the 365 days, the 24-hour
    slice is demeaned then L2-normalized (zero-norm slices left as zeros —
    same guard as basis.normalize_columns). The stacked result Y (8760, 17)
    gives R = Y.T @ Y; each entry is a sum of 365 per-day cosine
    similarities, so the diagonal is exactly 365 for non-degenerate columns.
    """
    cp = np.asarray(city_profiles, dtype=float)
    if cp.shape != (_DAYS * _HOURS, _BUILDINGS):
        raise ValueError(
            f"city_profiles must be ({_DAYS * _HOURS}, {_BUILDINGS}), got {cp.shape}"
        )
    # (8760, 17) -> (365, 24, 17): [day, hour, building]
    days = cp.reshape(_DAYS, _HOURS, _BUILDINGS)
    demeaned = days - days.mean(axis=1, keepdims=True)
    norms = np.linalg.norm(demeaned, axis=1, keepdims=True)  # (365, 1, 17)
    safe = np.where(norms < _ZERO_NORM_TOL, 1.0, norms)
    y = np.where(norms < _ZERO_NORM_TOL, 0.0, demeaned / safe)
    y = y.reshape(_DAYS * _HOURS, _BUILDINGS)
    r = y.T @ y
    return r[:16, :16]  # drop the 17th (TMY) row/column, as in MATLAB


def propose_clusters(corr: np.ndarray, n_clusters: int = 9) -> np.ndarray:
    """Cluster labels (1..n) per building, mimicking clusterdata(R, 9).

    MATLAB ``clusterdata(R, 9)`` with an integer cutoff >= 2 is agglomerative
    single-linkage clustering with euclidean distance on the ROWS of R, cut
    at MaxClust = 9. Equivalent here: ``linkage(corr, method="single",
    metric="euclidean")`` (rows of ``corr`` are the observations) +
    ``fcluster(criterion="maxclust")``.

    Returns int labels in 1..``n_clusters``, shape (corr.shape[0],) — i.e.
    (16,) for the standard building correlation matrix. Analysis only:
    results informed but do not equal the hand-tuned frozen groups.
    """
    corr = np.asarray(corr, dtype=float)
    if corr.ndim != 2:
        raise ValueError(f"corr must be a 2-D matrix, got ndim={corr.ndim}")
    z = linkage(corr, method="single", metric="euclidean")
    labels = fcluster(z, t=n_clusters, criterion="maxclust")
    return labels.astype(int)
