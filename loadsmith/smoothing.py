"""Stage 5 — day-boundary smoothing (replaces smoothprofile.m + quadprog).

For each consecutive-day pair of the (n_hours, k) class-load matrix, solve a
2k-variable QP adding quadratic corrections to hours 20-24 of the first day
and hours 1-5 of the second day so that the second derivative across midnight
is non-negative (convex) while minimally changing total load. The sweep is
sequential (day pair d, d+1 uses corrections already applied for d-1, d), so
the operation is order-dependent — this replicates the MATLAB loop exactly.
Spec: docs/conversion_manual/algorithms/05_smoothing.md.

IMPORTANT HISTORY (bug B1): MATLAB called smoothprofile with 1x8760 row
vectors, tripping the size guard — smoothing NEVER RAN, so all MATLAB
reference outputs are unsmoothed. Use smoothing="none" for regression
comparisons. Applying the QP to the 3 state class profiles BEFORE bus
distribution (decision C2) realizes the function's design intent and makes
every bus profile (a nonneg combination) inherit midnight convexity.

QP (per boundary, k load classes, x has length 2k):

    min  0.5 * x^T H x      H = blkdiag(ones(k,k), ones(k,k))
                            (objective = 0.5 * [(sum of first k x)^2 +
                             (sum of last k x)^2] — squared net change in
                             TOTAL load on each side of midnight)
    s.t. A x <= b           A = (2 - 9/16) * I_{2k} with the two
                            antidiagonal blocks set to -I_k;
                            b = the two centered second-difference
                            estimates around midnight, per class.

The constraints mean: after the correction, the two second-difference
estimates become b1_c - (2 - 9/16) x_c + x_{c+k} >= 0 and
b2_c - (2 - 9/16) x_{c+k} + x_c >= 0, i.e. non-negative curvature across
midnight for every class.

CANONICAL BEHAVIOR NOTE: H has rank 2, so the QP minimizer may be
non-unique (any x with the same per-side sums gives the same objective).
Because the MATLAB code never actually executed (bug B1), there is no
legacy behavior to match; we DEFINE the canonical solution to be the
MINIMUM-NORM optimum, selected by regularizing H_reg = H + 1e-9 * I
(strictly convex, unique minimizer, negligibly perturbed objective).

Solver (decision C3, no new dependencies): exhaustive active-set
enumeration. With 2k = 6 variables and 6 inequality constraints there are
only 64 candidate active sets; for each subset S we solve the
equality-constrained KKT system

    [ H_reg  A_S^T ] [x]   [ 0  ]
    [ A_S    0     ] [l] = [ b_S]

and accept the candidate iff it is primal feasible (A x <= b) and dual
feasible (l >= 0); the accepted candidate with the lowest regularized
objective is the (unique) global optimum. A is nonsingular (eigenvalues
2 - 9/16 -+ 1 = 7/16 and 39/16), so every row subset A_S has full row rank
and every KKT system is well-posed. scipy is used only as a cross-check in
the tests (SLSQP), never at runtime.

Fast path: if b >= 0 the boundary is already convex and x = 0 is optimal —
the vast majority of boundaries in real data.
"""

from __future__ import annotations

import numpy as np

# Quadratic correction shape: z[h] = X_c * RAMP[h]/16 over the 5 boundary hours
RAMP_OUT = np.array([0.0, 1.0, 4.0, 9.0, 16.0]) / 16.0   # day-1 hours 20..24
RAMP_IN = RAMP_OUT[::-1].copy()                           # day-2 hours 1..5

# Diagonal coefficient of the constraint matrix A (see module docstring).
_CURV = 2.0 - 9.0 / 16.0

# Tikhonov weight selecting the minimum-norm optimum of the singular QP.
_REG = 1e-9


def _qp_matrices(k: int) -> tuple[np.ndarray, np.ndarray]:
    """Return (H, A) for k load classes (2k-variable QP)."""
    n = 2 * k
    H = np.zeros((n, n))
    H[:k, :k] = 1.0
    H[k:, k:] = 1.0
    A = _CURV * np.eye(n)
    A[:k, k:] -= np.eye(k)
    A[k:, :k] -= np.eye(k)
    return H, A


def solve_boundary_qp(b: np.ndarray) -> np.ndarray:
    """Solve min 0.5 x^T H x  s.t.  A x <= b for one midnight boundary.

    H = blkdiag(ones(k,k), ones(k,k))  (minimize squared net total-load change
    on each side of midnight); A = (2 - 9/16) I_{2k} with A[i, i+k] =
    A[i+k, i] = -1; b = the two centered second-difference estimates per
    class (length 2k, k=3 in the primary pipeline).

    Returns the minimum-norm optimizer x (2k,); see the module docstring for
    the regularization convention and the active-set enumeration solver.
    Fast path: b >= 0 -> zeros.
    """
    b = np.asarray(b, dtype=np.float64).ravel()
    if b.size == 0 or b.size % 2 != 0:
        raise ValueError(f"b must have even positive length 2k, got {b.size}")
    k = b.size // 2
    n = 2 * k
    if np.all(b >= 0.0):
        return np.zeros(n)

    H, A = _qp_matrices(k)
    H_reg = H + _REG * np.eye(n)
    # Absolute tolerances scaled to the data magnitude so large-MW second
    # differences do not trip false infeasibility on machine-epsilon residuals.
    scale = max(1.0, float(np.abs(b).max()))
    primal_tol = 1e-12 * scale
    dual_tol = 1e-12 * scale

    best_x: np.ndarray | None = None
    best_obj = np.inf
    for mask in range(1, 1 << n):  # empty active set covered by the fast path
        active = [i for i in range(n) if (mask >> i) & 1]
        m = len(active)
        A_s = A[active]
        kkt = np.zeros((n + m, n + m))
        kkt[:n, :n] = H_reg
        kkt[:n, n:] = A_s.T
        kkt[n:, :n] = A_s
        rhs = np.zeros(n + m)
        rhs[n:] = b[active]
        try:
            sol = np.linalg.solve(kkt, rhs)
        except np.linalg.LinAlgError:  # pragma: no cover — A_S full rank by construction
            continue
        x = sol[:n]
        lam = sol[n:]
        if np.any(A @ x > b + primal_tol):  # primal feasibility
            continue
        if np.any(lam < -dual_tol):  # dual feasibility
            continue
        obj = 0.5 * (x @ H_reg @ x)
        if obj < best_obj:
            best_obj = obj
            best_x = x

    if best_x is None:  # pragma: no cover — the QP is always feasible
        raise RuntimeError(f"no feasible KKT candidate found for b={b!r}")
    # Sanity check demanded by the spec: corrected curvature non-negative.
    assert np.all(b - A @ best_x >= -1e-9), "QP solution violates convexity constraints"
    return best_x


def smooth_class_loads(class_loads: np.ndarray) -> np.ndarray:
    """Return a smoothed float64 copy of an (n_hours, k) class-load matrix.

    Sweeps the Ndays-1 midnight boundaries sequentially (each 48-hour window
    uses values already corrected by the previous boundary, matching the
    MATLAB loop). Boundaries whose two second-difference estimates are
    already >= 0 are skipped (x = 0 optimal). Hours beyond the last full
    24-hour day are left untouched; if n_hours < 48 the copy is returned
    unmodified (MATLAB guard). The input array is never mutated.
    """
    arr = np.asarray(class_loads)
    if arr.ndim != 2:
        raise ValueError(f"class_loads must be 2-D (n_hours, k), got shape {arr.shape}")
    n_hours, k = arr.shape
    if k < 1:
        raise ValueError("class_loads must have at least one class column")

    out = arr.astype(np.float64, copy=True)  # always a fresh copy
    if n_hours < 48:
        return out

    ndays = n_hours // 24
    for day in range(1, ndays):  # MATLAB day = 1 .. Ndays-1
        a1 = (day - 1) * 24  # 48-row window is out[a1 : a1 + 48]
        w = out[a1:a1 + 48]
        # Second-difference estimates across midnight (MATLAB ptmp(23..26)).
        b1 = w[24] - 2.0 * w[23] + w[22]
        b2 = w[25] - 2.0 * w[24] + w[23]
        b = np.concatenate([b1, b2])
        if np.all(b >= 0.0):
            continue  # already convex at this boundary
        x = solve_boundary_qp(b)
        # Window rows 19..23 = day-d hours 20..24; rows 24..28 = day-(d+1) hours 1..5.
        out[a1 + 19:a1 + 24] += np.outer(RAMP_OUT, x[:k])
        out[a1 + 24:a1 + 29] += np.outer(RAMP_IN, x[k:])
    return out
