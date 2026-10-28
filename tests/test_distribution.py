"""Distribution & reactive-power tests.

Covers: (1) power-factor matrix shape/ranges/determinism/column order (D3);
(2) distribute() hand example + exact energy conservation (C4 invariant);
(3) reactive_power() one-hot exactness, non-negativity, max-qf envelope;
(4) B2 regression guard (each class's qf uses its OWN pf, never the
commercial one); (5) real-data smoke through the FRCC parquet store.
"""

from pathlib import Path

import numpy as np
import pytest

from loadsmith.config import DEFAULT_SEED, PF_RANGES, Role
from loadsmith.distribution import (
    HOURS_PER_YEAR,
    distribute,
    draw_power_factors,
    reactive_power,
)

DATA_ROOT = Path(__file__).resolve().parents[1] / "data"

requires_data = pytest.mark.skipif(
    not (DATA_ROOT / "frcc" / "bus_table.parquet").exists(),
    reason="parquet data store not migrated (data/frcc missing)",
)


def make_class_loads(seed=0):
    """Synthetic positive (8760, 3) state class loads."""
    rng = np.random.default_rng(seed)
    return rng.uniform(50.0, 500.0, size=(HOURS_PER_YEAR, 3))


def make_shares(n_bus, seed=1):
    """(n_bus, 3) nonneg shares with each class column summing to 1.0 (C4)."""
    rng = np.random.default_rng(seed)
    raw = rng.uniform(0.0, 1.0, size=(n_bus, 3))
    return raw / raw.sum(axis=0)


# ---------------------------------------------------------------------------
# 1. Power-factor matrix (D3)
# ---------------------------------------------------------------------------


def test_pf_shape_dtype_and_ranges():
    pf = draw_power_factors(500, DEFAULT_SEED, "FRCC")
    assert pf.shape == (500, 3)
    assert pf.dtype == np.float64
    for role in Role:
        lo, hi = PF_RANGES[role]
        col = pf[:, role.value]
        assert np.all(col >= lo), f"{role} below {lo}"
        assert np.all(col <= hi), f"{role} above {hi}"


def test_pf_column_order_is_c_i_r():
    # The D3 ranges are disjoint (R 0.95-0.98 < C 0.98-0.99 < I 0.99-1.00),
    # so band membership uniquely identifies each column's class: if the
    # column order were anything but C, I, R, at least one column would
    # leave its band (probability of every draw landing on the shared
    # endpoint is zero).
    pf = draw_power_factors(1000, DEFAULT_SEED, "FRCC")
    c, i, r = pf[:, 0], pf[:, 1], pf[:, 2]
    assert np.all((c >= 0.98) & (c <= 0.99))
    assert np.all((i >= 0.99) & (i <= 1.00))
    assert np.all((r >= 0.95) & (r <= 0.98))
    # Order also shows in the means (0.985 / 0.995 / 0.965).
    assert r.mean() < c.mean() < i.mean()


def test_pf_deterministic_for_seed_region():
    a = draw_power_factors(200, 123, "FRCC")
    b = draw_power_factors(200, 123, "FRCC")
    np.testing.assert_array_equal(a, b)
    # Region is folded in uppercase, so case does not change the stream.
    np.testing.assert_array_equal(a, draw_power_factors(200, 123, "frcc"))


def test_pf_varies_with_region_and_seed():
    base = draw_power_factors(200, 123, "FRCC")
    assert not np.array_equal(base, draw_power_factors(200, 123, "MISO"))
    assert not np.array_equal(base, draw_power_factors(200, 123, "SRVC"))
    assert not np.array_equal(base, draw_power_factors(200, 124, "FRCC"))


def test_pf_bad_args():
    with pytest.raises(ValueError):
        draw_power_factors(0, DEFAULT_SEED, "FRCC")
    with pytest.raises(ValueError):
        draw_power_factors(10, DEFAULT_SEED, "")
    with pytest.raises(ValueError):
        draw_power_factors(10, DEFAULT_SEED, "   ")


# ---------------------------------------------------------------------------
# 2. distribute()
# ---------------------------------------------------------------------------


def test_distribute_hand_example():
    shares = np.array([[0.5, 0.2, 0.3],
                       [0.5, 0.8, 0.7]])
    class_loads = make_class_loads(1)
    class_loads[0] = [100.0, 50.0, 200.0]   # hand-checkable first hour
    p = distribute(class_loads, shares)
    assert p.shape == (2, HOURS_PER_YEAR)
    assert p.dtype == np.float64
    # bus 0, hour 0: 0.5*100 + 0.2*50 + 0.3*200 = 120
    assert p[0, 0] == pytest.approx(120.0, rel=1e-14)
    # bus 1, hour 0: 0.5*100 + 0.8*50 + 0.7*200 = 230
    assert p[1, 0] == pytest.approx(230.0, rel=1e-14)
    # Whole-matrix cross-check against an explicit per-class outer-product sum.
    ref = np.zeros((2, HOURS_PER_YEAR))
    for c in range(3):
        ref += np.outer(shares[:, c], class_loads[:, c])
    np.testing.assert_allclose(p, ref, rtol=1e-13)


def test_distribute_energy_conservation():
    # With each shares column summing to 1.0 (the C4 renormalization),
    # bus-summed power equals the state class total at every hour.
    shares = make_shares(40)
    class_loads = make_class_loads(2)
    p = distribute(class_loads, shares)
    np.testing.assert_allclose(
        p.sum(axis=0), class_loads.sum(axis=1), rtol=1e-12)


def test_distribute_validation():
    loads = make_class_loads()
    with pytest.raises(ValueError):
        distribute(loads[:100], np.ones((2, 3)))        # not 8760 hours
    with pytest.raises(ValueError):
        distribute(loads[:, :2], np.ones((2, 3)))       # not 3 classes
    with pytest.raises(ValueError):
        distribute(loads, np.ones((2, 4)))              # shares not 3 columns
    with pytest.raises(ValueError):
        distribute(loads, np.ones(3))                   # shares not 2-D
    bad = np.full((2, 3), 0.5)
    bad[0, 1] = -0.01
    with pytest.raises(ValueError):
        distribute(loads, bad)                          # negative share


# ---------------------------------------------------------------------------
# 3. reactive_power()
# ---------------------------------------------------------------------------


def test_reactive_one_hot_shares_exact():
    # Bus b carries 100% of class b: Q[b] must equal qf(pf[b,b]) * L[:,b]
    # exactly (the matmul only adds exact zeros to the single product).
    class_loads = make_class_loads(3)
    shares = np.eye(3)
    pf = np.array([[0.980, 0.995, 0.960],
                   [0.985, 0.990, 0.950],
                   [0.990, 1.000, 0.970]])
    q = reactive_power(class_loads, shares, pf)
    assert q.shape == (3, HOURS_PER_YEAR)
    for b in range(3):
        qf = np.sqrt(1.0 - pf[b, b] ** 2) / pf[b, b]
        np.testing.assert_array_equal(q[b], qf * class_loads[:, b])


def test_reactive_nonneg_and_max_qf_envelope():
    class_loads = make_class_loads(4)
    shares = make_shares(60, seed=11)
    pf = draw_power_factors(60, DEFAULT_SEED, "SRVC")
    q = reactive_power(class_loads, shares, pf)
    p = distribute(class_loads, shares)
    assert np.all(q >= 0.0)
    # Residential pf floor 0.95 gives the largest possible qf across all
    # D3 ranges, so Q <= P * max_qf everywhere.
    max_qf = np.sqrt(1.0 - 0.95 ** 2) / 0.95
    assert np.all(q <= p * max_qf * (1.0 + 1e-12))


def test_reactive_unity_pf_gives_zero_q():
    class_loads = make_class_loads(6)
    shares = make_shares(5, seed=12)
    q = reactive_power(class_loads, shares, np.ones((5, 3)))
    np.testing.assert_array_equal(q, 0.0)


def test_reactive_validation():
    class_loads = make_class_loads()
    shares = make_shares(4)
    with pytest.raises(ValueError):
        reactive_power(class_loads, shares, np.ones((3, 3)))     # n_bus mismatch
    with pytest.raises(ValueError):
        reactive_power(class_loads, shares, np.full((4, 3), 1.01))  # pf > 1
    with pytest.raises(ValueError):
        reactive_power(class_loads, shares, np.zeros((4, 3)))    # pf = 0
    with pytest.raises(ValueError):
        reactive_power(class_loads, shares, np.full((4, 3), -0.9))  # pf < 0


# ---------------------------------------------------------------------------
# 4. B2 regression guard: each class's qf uses ITS OWN pf
# ---------------------------------------------------------------------------


def test_b2_each_class_uses_own_pf():
    class_loads = make_class_loads(5)
    rng = np.random.default_rng(21)
    shares = rng.uniform(0.1, 1.0, size=(8, 3))
    # Commercial pf near unity (qf ~ 0.03); industrial/residential far lower,
    # so dividing by the WRONG (commercial) pf changes Q dramatically.
    pf = np.column_stack([
        np.full(8, 0.9995),
        rng.uniform(0.55, 0.65, 8),
        rng.uniform(0.35, 0.45, 8),
    ])
    q = reactive_power(class_loads, shares, pf)

    # Reference: explicit per-class loop, each class dividing by ITS OWN pf.
    q_ref = np.zeros_like(q)
    for c in range(3):
        qf_c = np.sqrt(1.0 - pf[:, c] ** 2) / pf[:, c]
        q_ref += np.outer(qf_c * shares[:, c], class_loads[:, c])
    np.testing.assert_allclose(q, q_ref, rtol=1e-12)

    # MATLAB bug B2: industrial/residential qf divided by the COMMERCIAL pf.
    # The fixed implementation must NOT reproduce it.
    q_bug = np.zeros_like(q)
    for c in range(3):
        qf_bug = np.sqrt(1.0 - pf[:, c] ** 2) / pf[:, 0]
        q_bug += np.outer(qf_bug * shares[:, c], class_loads[:, c])
    assert not np.allclose(q, q_bug, rtol=1e-3)


# ---------------------------------------------------------------------------
# 5. Real-data smoke: FRCC parquet store
# ---------------------------------------------------------------------------


@requires_data
def test_frcc_shares_renormalized_and_conserving():
    from loadsmith.ingest import ParquetStore

    store = ParquetStore(DATA_ROOT)
    bus = store.bus_table("FRCC")
    share_cols = ["share_c", "share_i", "share_r"]

    # C4 invariant: renormalized share columns sum to 1.0 per state.
    for code, group in bus.groupby("state_code"):
        np.testing.assert_allclose(
            group[share_cols].sum().to_numpy(), 1.0, rtol=1e-9,
            err_msg=f"state_code {code} shares do not sum to 1")

    # Distribute a synthetic year through the FL-state subset (the largest
    # state_code group) and verify hourly energy conservation.
    fl_code = bus["state_code"].value_counts().idxmax()
    subset = bus[bus["state_code"] == fl_code]
    shares = subset[share_cols].to_numpy(dtype=np.float64)
    class_loads = make_class_loads(99)
    p = distribute(class_loads, shares)
    assert p.shape == (len(subset), HOURS_PER_YEAR)
    assert np.all(p >= 0.0)
    np.testing.assert_allclose(
        p.sum(axis=0), class_loads.sum(axis=1), rtol=1e-9)
