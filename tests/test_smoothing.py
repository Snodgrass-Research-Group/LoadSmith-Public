"""Smoothing QP tests.

Covers: (1) x = 0 / no-op when a boundary is already convex; (2) active-set
solution matches scipy SLSQP on random negative-b cases; (3) all midnight
second differences non-negative after smoothing a synthetic year; (4) the
correction minimally changes total energy; (5) input never mutated, float64
output, short-input guard.
"""

import numpy as np
import pytest
from scipy.optimize import minimize

from loadsmith.smoothing import RAMP_IN, RAMP_OUT, smooth_class_loads, solve_boundary_qp

CURV = 2.0 - 9.0 / 16.0


def qp_matrices(k):
    """Independent reconstruction of (H, A) for cross-checking."""
    n = 2 * k
    H = np.zeros((n, n))
    H[:k, :k] = 1.0
    H[k:, k:] = 1.0
    A = CURV * np.eye(n)
    A[:k, k:] -= np.eye(k)
    A[k:, :k] -= np.eye(k)
    return H, A


def solve_with_slsqp(b, k):
    """Reference solution of the same QP via scipy SLSQP (test-only).

    SLSQP is fragile from an infeasible start on this problem, so start at
    the strictly feasible point x0 = A^-1 min(b, 0) (A x0 = min(b, 0) <= b).
    """
    H, A = qp_matrices(k)
    x0 = np.linalg.solve(A, np.minimum(b, 0.0))
    res = minimize(
        lambda x: 0.5 * x @ H @ x,
        x0=x0,
        jac=lambda x: H @ x,
        constraints=[{"type": "ineq", "fun": lambda x: b - A @ x, "jac": lambda x: -A}],
        method="SLSQP",
        options={"maxiter": 1000, "ftol": 1e-12},
    )
    assert res.success, f"SLSQP failed for b={b}: {res.message}"
    return res.x


def make_synthetic_year(seed=42, n_days=365, k=3):
    """Sinusoidal daily load shapes with random per-day jumps at every midnight.

    Shaped like real load (minimum ~4am, peak ~4pm, so the curve is convex
    near midnight); the per-day random amplitude/offset introduces jumps
    whose induced concavity the smoother must fix.
    """
    rng = np.random.default_rng(seed)
    t = np.arange(24)
    scales = np.array([1.0, 0.6, 0.3])[:k]
    days = []
    for _ in range(n_days):
        base = 100.0 - 30.0 * np.cos(2.0 * np.pi * (t - 4) / 24.0)
        offset = rng.uniform(-15.0, 15.0)
        amp = rng.uniform(0.8, 1.2)
        day = np.outer(base * amp + offset, scales)
        days.append(day)
    return np.vstack(days)


def midnight_second_diffs(p, day):
    """The two second-difference estimates at the boundary after `day` full days."""
    h = 24 * day  # first hour (0-based) of day+1; MATLAB ptmp(25)
    b1 = p[h] - 2.0 * p[h - 1] + p[h - 2]
    b2 = p[h + 1] - 2.0 * p[h] + p[h - 1]
    return b1, b2


# ---------------------------------------------------------------------------
# 1. Already-convex boundary -> x = 0 and data unchanged
# ---------------------------------------------------------------------------


def test_convex_b_gives_zero_x():
    b = np.array([0.5, 1.0, 0.0, 2.0, 0.1, 3.0])
    x = solve_boundary_qp(b)
    assert x.shape == (6,)
    np.testing.assert_array_equal(x, np.zeros(6))


def test_convex_data_unchanged():
    # p[h] = (h - 24)^2 per class: second difference = 2 > 0 everywhere.
    h = np.arange(96, dtype=np.float64)
    p = np.outer((h - 24.0) ** 2 + 10.0, [1.0, 0.6, 0.3])
    out = smooth_class_loads(p)
    np.testing.assert_array_equal(out, p)


# ---------------------------------------------------------------------------
# 2. Random negative-b cases vs scipy SLSQP
# ---------------------------------------------------------------------------


def test_matches_slsqp_random_negative_b():
    rng = np.random.default_rng(1234)
    H, A = qp_matrices(3)
    for _ in range(50):
        b = rng.uniform(-5.0, 5.0, size=6)
        if np.all(b >= 0.0):  # force at least one violated constraint
            b[rng.integers(6)] = -rng.uniform(0.1, 5.0)
        x = solve_boundary_qp(b)
        # Our solution satisfies the constraints.
        assert np.all(A @ x <= b + 1e-9), f"constraint violation for b={b}"
        # Objective agrees with the SLSQP reference within 1e-6.
        x_ref = solve_with_slsqp(b, k=3)
        obj = 0.5 * x @ H @ x
        obj_ref = 0.5 * x_ref @ H @ x_ref
        assert obj <= obj_ref + 1e-6, f"suboptimal: {obj} > {obj_ref} for b={b}"
        assert abs(obj - obj_ref) <= 1e-6 * max(1.0, abs(obj_ref)), (
            f"objective mismatch: {obj} vs {obj_ref} for b={b}"
        )


def test_matches_slsqp_general_k():
    # The QP generalizes to any k >= 1 (H = blkdiag(ones(k,k), ones(k,k))).
    rng = np.random.default_rng(99)
    for k in (1, 2, 4):
        H, A = qp_matrices(k)
        for _ in range(10):
            b = rng.uniform(-3.0, 3.0, size=2 * k)
            b[rng.integers(2 * k)] = -rng.uniform(0.1, 3.0)
            x = solve_boundary_qp(b)
            assert np.all(A @ x <= b + 1e-9)
            x_ref = solve_with_slsqp(b, k=k)
            obj = 0.5 * x @ H @ x
            obj_ref = 0.5 * x_ref @ H @ x_ref
            assert abs(obj - obj_ref) <= 1e-6 * max(1.0, abs(obj_ref))


def test_bad_b_length_raises():
    with pytest.raises(ValueError):
        solve_boundary_qp(np.array([1.0, -2.0, 3.0]))  # odd length
    with pytest.raises(ValueError):
        solve_boundary_qp(np.array([]))


# ---------------------------------------------------------------------------
# 3. Synthetic year: every midnight convex after smoothing
# ---------------------------------------------------------------------------


def test_synthetic_year_all_midnights_convex():
    p = make_synthetic_year()
    assert p.shape == (8760, 3)
    # The raw data must actually violate convexity somewhere, or the test is vacuous.
    raw_violations = sum(
        np.any(np.concatenate(midnight_second_diffs(p, d)) < 0.0) for d in range(1, 365)
    )
    assert raw_violations > 50, "synthetic year should have many non-convex midnights"

    out = smooth_class_loads(p)
    assert not np.array_equal(out, p), "smoothing should have changed the data"
    for d in range(1, 365):
        b1, b2 = midnight_second_diffs(out, d)
        assert np.all(b1 >= -1e-8), f"boundary {d}: b1={b1}"
        assert np.all(b2 >= -1e-8), f"boundary {d}: b2={b2}"


# ---------------------------------------------------------------------------
# 4. Energy: total-load change per boundary is small vs correction magnitude
# ---------------------------------------------------------------------------


def test_energy_change_bounded_per_boundary():
    p = make_synthetic_year()
    out = smooth_class_loads(p)
    delta = out - p
    ratios = []
    for d in range(1, 365):
        # Correction band for boundary d: hours 24d-5 .. 24d+4 (10 rows).
        z = delta[24 * d - 5:24 * d + 5]
        z_mag = np.abs(z).sum()
        if z_mag == 0.0:
            continue  # boundary was already convex
        # Net change in total energy attributable to this boundary is the net
        # of its own correction band (neighboring boundaries touch disjoint
        # rows but share the 48-h window, so we scope to the band). The
        # objective minimizes the per-side sums, so |net| <= sum(|z|) always,
        # and is typically << it.
        assert abs(z.sum()) <= z_mag + 1e-9
        ratios.append(abs(z.sum()) / z_mag)
    assert len(ratios) > 50, "expected many corrected boundaries"
    # Typically near 0: when a single aggregate curvature constraint binds
    # (the usual one-sided-jump case), the optimum's ratio is exactly
    # (2 - 9/16 - 1) / (2 - 9/16 + 1) = 7/39 ~ 0.179 — far below the trivial
    # bound of 1 (which would mean the correction only adds or only removes
    # energy). Assert the median stays in that regime.
    assert np.median(ratios) < 0.25, f"median |net z| / sum|z| = {np.median(ratios)}"
    assert np.max(ratios) < 0.5, f"max |net z| / sum|z| = {np.max(ratios)}"


def test_energy_zero_net_change_when_achievable():
    # sum(b1) = 0 and b2 > 0: a zero-net-change correction exists
    # (e.g. x = [-16/23, 8/23, 8/23, 0, 0, 0]), so the optimum objective is ~0
    # and the applied correction changes total energy by ~0.
    b = np.array([-1.0, 0.5, 0.5, 1.0, 1.0, 1.0])
    x = solve_boundary_qp(b)
    H, A = qp_matrices(3)
    assert np.all(A @ x <= b + 1e-9)
    assert 0.5 * x @ H @ x < 1e-8
    # Net total-load change of the applied correction:
    net = RAMP_OUT.sum() * x[:3].sum() + RAMP_IN.sum() * x[3:].sum()
    assert abs(net) < 1e-4
    assert np.abs(x).sum() > 0.1  # a real (nonzero) correction was applied


# ---------------------------------------------------------------------------
# 5. Copy semantics, dtype, short-input guard
# ---------------------------------------------------------------------------


def test_input_not_mutated_and_dtype():
    p = make_synthetic_year(seed=7, n_days=10)
    p_before = p.copy()
    out = smooth_class_loads(p)
    np.testing.assert_array_equal(p, p_before)
    assert out is not p
    assert out.dtype == np.float64
    assert not np.array_equal(out, p)  # this seed produces corrections


def test_integer_input_converted():
    p = np.ones((96, 3), dtype=np.int64) * 100
    out = smooth_class_loads(p)
    assert out.dtype == np.float64
    np.testing.assert_array_equal(out, 100.0)


def test_short_input_returns_unmodified_copy():
    rng = np.random.default_rng(3)
    p = rng.uniform(50.0, 150.0, size=(47, 3))
    out = smooth_class_loads(p)
    np.testing.assert_array_equal(out, p)
    assert out is not p
    out[0, 0] = -999.0  # independent copy: input untouched
    assert p[0, 0] != -999.0


def test_non_2d_raises():
    with pytest.raises(ValueError):
        smooth_class_loads(np.ones(8760))  # the MATLAB bug-B1 shape, now loud
