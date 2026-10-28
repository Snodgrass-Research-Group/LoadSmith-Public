"""Tests — daily NNLS fit & C/I/R class split (fitting.py).

Synthetic tests build tiny stub BasisSources (no repo data needed); the last
test drives the real FRCC FL series through the NYSEG basis and skips
cleanly when the parquet store has not been built.
Spec under test: docs/conversion_manual/algorithms/04_daily_fit.md.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from loadsmith.basis import NYSEGBasis, normalize_columns
from loadsmith.config import Role
from loadsmith.fitting import fit_combined_states, fit_state
from loadsmith.profile_calendar import day_type_calendar

DATA_DIR = Path(__file__).resolve().parents[1] / "data"

needs_store = pytest.mark.skipif(
    not (DATA_DIR / "shared" / "nyseg_profiles.parquet").exists()
    or not (DATA_DIR / "frcc" / "state_loads.parquet").exists(),
    reason="parquet store not built — run scripts/migrate_data.py first",
)

DAYS, HOURS = 365, 24


# --------------------------------------------------------------------------- #
# Synthetic fixtures
# --------------------------------------------------------------------------- #


class StubBasis:
    """Minimal BasisSource: one fixed (24, 1+k) basis, every day, any type."""

    def __init__(self, base: np.ndarray, roles: tuple[Role, ...]) -> None:
        self._base = np.asarray(base, dtype=float)
        self.roles = roles

    def day_basis(self, day: int, day_type: int) -> np.ndarray:
        return self._base.copy()


def _make_base(k: int = 3, seed: int = 0) -> np.ndarray:
    """(24, 1+k) well-conditioned basis: trend + k distinct normalized shapes."""
    rng = np.random.default_rng(seed)
    h = np.arange(HOURS)
    shapes = [
        np.sin(2 * np.pi * (j + 1) * h / HOURS + j) + 0.05 * rng.random(HOURS)
        for j in range(k)
    ]
    return normalize_columns(np.column_stack([np.ones(HOURS), *shapes]))


def _tile_year(day_block: np.ndarray) -> np.ndarray:
    """(8760,) load with the same 24-hour block every day."""
    return np.tile(np.asarray(day_block, dtype=float), DAYS)


def _orthogonal_to(base: np.ndarray, seed: int = 7) -> np.ndarray:
    """A (24,) vector orthogonal to every column of ``base`` (exact residual):
    adding it to y leaves the least-squares alphas unchanged."""
    rng = np.random.default_rng(seed)
    v = rng.standard_normal(HOURS)
    q, _ = np.linalg.qr(base)
    v = v - q @ (q.T @ v)
    return v


RES_FIRST_ROLES = (Role.RESIDENTIAL, Role.COMMERCIAL, Role.INDUSTRIAL)
RES_LAST_ROLES = (Role.COMMERCIAL, Role.INDUSTRIAL, Role.RESIDENTIAL)
ONES_CAL = np.ones(DAYS, dtype=int)


# --------------------------------------------------------------------------- #
# 1. Exact recovery on a synthetic basis
# --------------------------------------------------------------------------- #


class TestExactRecovery:
    def test_nnls_recovers_alphas_and_split(self):
        base = _make_base(k=3, seed=0)
        basis = StubBasis(base, RES_FIRST_ROLES)
        rng = np.random.default_rng(42)
        # Strictly positive daily alphas -> the LS optimum is interior, so
        # NNLS must return it exactly. Trend alpha scaled up to mimic MW.
        alpha_true = rng.uniform(0.5, 2.0, size=(DAYS, 4))
        alpha_true[:, 0] *= 100.0
        load = np.concatenate([base @ alpha_true[d] for d in range(DAYS)])
        cir = (0.3, 0.2, 0.5)

        result = fit_state(load, basis, ONES_CAL, cir, residual="residential")

        np.testing.assert_allclose(result.alphas, alpha_true, atol=1e-8)
        np.testing.assert_allclose(result.residuals, 0.0, atol=1e-8)
        np.testing.assert_allclose(result.total(), load, rtol=1e-12, atol=1e-9)

        # Hand-computed split for day 1 (roles: residential is column 1).
        a = alpha_true[0]
        trend = base[:, 0] * a[0]
        res = base[:, 1] * a[1]
        ci = base[:, 2:] @ a[2:]
        c_frac, i_frac, r_frac = cir
        day1 = result.class_loads[:HOURS]
        np.testing.assert_allclose(
            day1[:, 0], trend * c_frac + ci * c_frac / (c_frac + i_frac), atol=1e-8
        )
        np.testing.assert_allclose(
            day1[:, 1], trend * i_frac + ci * i_frac / (c_frac + i_frac), atol=1e-8
        )
        np.testing.assert_allclose(day1[:, 2], trend * r_frac + res, atol=1e-8)

    def test_residential_role_mapped_by_name_not_position(self):
        # Residential LAST (utility-archetype layout): the R class must take
        # column 3's shape, and columns 1-2 must land in the C/I pool.
        base = _make_base(k=3, seed=1)
        basis = StubBasis(base, RES_LAST_ROLES)
        a = np.array([50.0, 2.0, 3.0, 4.0])
        load = _tile_year(base @ a)
        cir = (0.4, 0.1, 0.5)

        result = fit_state(load, basis, ONES_CAL, cir, residual="residential")

        trend = base[:, 0] * a[0]
        res = base[:, 3] * a[3]           # residential = LAST column
        ci = base[:, 1:3] @ a[1:3]        # joint pool = the other two
        day1 = result.class_loads[:HOURS]
        np.testing.assert_allclose(day1[:, 2], trend * 0.5 + res, atol=1e-8)
        np.testing.assert_allclose(day1[:, 0], trend * 0.4 + ci * 0.8, atol=1e-8)
        np.testing.assert_allclose(day1[:, 1], trend * 0.1 + ci * 0.2, atol=1e-8)


# --------------------------------------------------------------------------- #
# 2. Residual policies
# --------------------------------------------------------------------------- #


@pytest.fixture(scope="module")
def residual_case():
    """Same fit with a known, exactly-orthogonal residual v injected each day:
    the alphas (hence fit) are identical across policies; only where v goes
    differs."""
    base = _make_base(k=3, seed=2)
    basis = StubBasis(base, RES_FIRST_ROLES)
    a = np.array([80.0, 1.5, 2.5, 1.0])
    v = _orthogonal_to(base)
    assert np.linalg.norm(v) > 0.1  # residual actually nonzero
    load = _tile_year(base @ a + v)
    cir = (0.25, 0.35, 0.40)
    results = {
        pol: fit_state(load, basis, ONES_CAL, cir, residual=pol)
        for pol in ("residential", "proportional", "drop")
    }
    return load, _tile_year(v), cir, results


class TestResidualPolicies:
    def test_residuals_identical_across_policies(self, residual_case):
        _, v_year, _, results = residual_case
        for pol, res in results.items():
            np.testing.assert_allclose(res.residuals, v_year, atol=1e-8, err_msg=pol)

    def test_residential_policy_puts_all_residual_in_r(self, residual_case):
        _, v_year, _, results = residual_case
        delta = results["residential"].class_loads - results["drop"].class_loads
        np.testing.assert_allclose(delta[:, 2], v_year, atol=1e-8)
        np.testing.assert_allclose(delta[:, 0], 0.0, atol=1e-10)
        np.testing.assert_allclose(delta[:, 1], 0.0, atol=1e-10)

    def test_proportional_policy_splits_residual_by_cir(self, residual_case):
        _, v_year, cir, results = residual_case
        delta = results["proportional"].class_loads - results["drop"].class_loads
        for col, frac in enumerate(cir):
            np.testing.assert_allclose(delta[:, col], frac * v_year, atol=1e-8)

    def test_drop_policy_loses_the_residual(self, residual_case):
        load, v_year, _, results = residual_case
        total = results["drop"].total()
        np.testing.assert_allclose(total, load - v_year, atol=1e-8)  # == fit
        assert not np.allclose(total, load)  # B3: classes don't sum to load


# --------------------------------------------------------------------------- #
# 3. Energy conservation on random data (through the real NYSEG basis)
# --------------------------------------------------------------------------- #


class TestEnergyConservation:
    @pytest.mark.parametrize("policy", ["residential", "proportional"])
    def test_class_sums_equal_load(self, policy):
        rng = np.random.default_rng(20260709)
        basis = NYSEGBasis(rng.random((24, 36, 9)) + 0.5, slices=(2, 3, 5))
        day_types = rng.integers(1, 37, size=DAYS)
        load = 100.0 + 50.0 * rng.random(DAYS * HOURS)
        # Deliberately un-normalized CIR (sums to 0.98): fit_state renormalizes.
        cir = (0.30, 0.18, 0.50)

        result = fit_state(load, basis, day_types, cir, residual=policy)

        np.testing.assert_allclose(result.total(), load, rtol=1e-9)
        assert (result.alphas >= 0).all()
        assert result.class_loads.shape == (DAYS * HOURS, 3)
        assert result.alphas.shape == (DAYS, 4)


# --------------------------------------------------------------------------- #
# 4. Validation errors
# --------------------------------------------------------------------------- #


class TestValidation:
    def setup_method(self):
        self.basis = StubBasis(_make_base(), RES_FIRST_ROLES)
        self.load = _tile_year(np.full(HOURS, 100.0))

    def test_c_plus_i_zero_raises(self):
        with pytest.raises(ValueError, match=r"C \+ I == 0"):
            fit_state(self.load, self.basis, ONES_CAL, (0.0, 0.0, 1.0))

    def test_wrong_load_shape_raises(self):
        with pytest.raises(ValueError, match=r"load must have shape \(8760,\)"):
            fit_state(self.load[:-1], self.basis, ONES_CAL, (0.3, 0.2, 0.5))
        with pytest.raises(ValueError, match="load"):
            fit_state(self.load.reshape(365, 24), self.basis, ONES_CAL,
                      (0.3, 0.2, 0.5))

    def test_wrong_day_types_shape_raises(self):
        with pytest.raises(ValueError, match=r"day_types must have shape \(365,\)"):
            fit_state(self.load, self.basis, np.ones(366, dtype=int),
                      (0.3, 0.2, 0.5))

    def test_bad_cir_raises(self):
        with pytest.raises(ValueError, match="triple"):
            fit_state(self.load, self.basis, ONES_CAL, (0.5, 0.5))
        with pytest.raises(ValueError, match="non-negative"):
            fit_state(self.load, self.basis, ONES_CAL, (0.6, -0.1, 0.5))

    def test_bad_policy_raises(self):
        with pytest.raises(ValueError, match="residual must be one of"):
            fit_state(self.load, self.basis, ONES_CAL, (0.3, 0.2, 0.5),
                      residual="keep")

    def test_basis_without_residential_role_raises(self):
        basis = StubBasis(_make_base(k=2), (Role.COMMERCIAL, Role.INDUSTRIAL))
        with pytest.raises(ValueError, match="RESIDENTIAL"):
            fit_state(self.load, basis, ONES_CAL, (0.3, 0.2, 0.5))


# --------------------------------------------------------------------------- #
# 5. Combined-state fit (MISO IA+MN quirk)
# --------------------------------------------------------------------------- #


CIR_A = (0.30, 0.20, 0.50)
CIR_B = (0.40, 0.40, 0.20)


@pytest.fixture(scope="module")
def combined_case():
    base = _make_base(k=3, seed=3)
    basis = StubBasis(base, RES_FIRST_ROLES)
    rng = np.random.default_rng(11)
    load_a = 200.0 + 80.0 * rng.random(DAYS * HOURS)
    load_b = 120.0 + 40.0 * rng.random(DAYS * HOURS)
    results = fit_combined_states(
        {"IA": load_a, "MN": load_b},
        {"IA": CIR_A, "MN": CIR_B},
        basis, ONES_CAL, residual="residential",
    )
    # Reference: fit the combined series directly with hand-computed
    # energy-weighted CIR.
    e_a, e_b = load_a.sum(), load_b.sum()
    cir_comb = tuple(
        (CIR_A[c] * e_a + CIR_B[c] * e_b) / (e_a + e_b) for c in range(3)
    )
    combined = fit_state(load_a + load_b, basis, ONES_CAL, cir_comb,
                         residual="residential")
    return load_a, load_b, results, combined, (e_a, e_b)


class TestCombinedStates:
    def test_states_sum_to_combined_exactly(self, combined_case):
        _, _, results, combined, _ = combined_case
        np.testing.assert_array_equal(
            results["IA"].class_loads + results["MN"].class_loads,
            combined.class_loads,
        )

    def test_scale_formula_matches_hand_computation(self, combined_case):
        _, _, results, combined, (e_a, e_b) = combined_case
        for c in range(3):
            scale_c = CIR_A[c] * e_a / (CIR_A[c] * e_a + CIR_B[c] * e_b)
            np.testing.assert_allclose(
                results["IA"].class_loads[:, c],
                combined.class_loads[:, c] * scale_c,
                rtol=1e-12,
            )

    def test_energy_conservation_across_the_pair(self, combined_case):
        load_a, load_b, results, _, _ = combined_case
        # Policy 'residential' conserves energy at the COMBINED level; the
        # per-class split then distributes it between the two states.
        np.testing.assert_allclose(
            results["IA"].total() + results["MN"].total(),
            load_a + load_b, rtol=1e-9,
        )

    def test_diagnostics_convention(self, combined_case):
        load_a, load_b, results, combined, (e_a, e_b) = combined_case
        # Alphas: combined coefficients duplicated to both states.
        np.testing.assert_array_equal(results["IA"].alphas, combined.alphas)
        np.testing.assert_array_equal(results["MN"].alphas, combined.alphas)
        # Residuals: combined residuals scaled by each state's energy share.
        np.testing.assert_allclose(
            results["IA"].residuals,
            combined.residuals * (e_a / (e_a + e_b)), rtol=1e-12,
        )
        np.testing.assert_allclose(
            results["IA"].residuals + results["MN"].residuals,
            combined.residuals, rtol=1e-9, atol=1e-12,
        )

    def test_drop_policy_pair_sums_to_combined_fit(self):
        base = _make_base(k=3, seed=4)
        basis = StubBasis(base, RES_FIRST_ROLES)
        v = _orthogonal_to(base, seed=9)
        a = np.array([60.0, 2.0, 1.0, 3.0])
        load_a = _tile_year(base @ a + v)          # residual v every day
        load_b = _tile_year(0.5 * (base @ a))      # exact fit component
        results = fit_combined_states(
            {"IA": load_a, "MN": load_b},
            {"IA": CIR_A, "MN": CIR_B},
            basis, ONES_CAL, residual="drop",
        )
        pair_total = results["IA"].total() + results["MN"].total()
        combined_load = load_a + load_b
        np.testing.assert_allclose(
            pair_total, combined_load - _tile_year(v), atol=1e-8)  # == fit
        assert not np.allclose(pair_total, combined_load)          # residual lost

    def test_wrong_state_count_or_keys_raise(self):
        basis = StubBasis(_make_base(), RES_FIRST_ROLES)
        load = _tile_year(np.full(HOURS, 100.0))
        with pytest.raises(ValueError, match="exactly 2 states"):
            fit_combined_states({"IA": load}, {"IA": CIR_A},
                                basis, ONES_CAL)
        with pytest.raises(ValueError, match="exactly 2 states"):
            fit_combined_states(
                {"IA": load, "MN": load, "WI": load},
                {k: CIR_A for k in ("IA", "MN", "WI")}, basis, ONES_CAL)
        with pytest.raises(ValueError, match="keys differ"):
            fit_combined_states({"IA": load, "MN": load},
                                {"IA": CIR_A, "WI": CIR_B},
                                basis, ONES_CAL)


# --------------------------------------------------------------------------- #
# 6. Real-data smoke test: FRCC Florida through the NYSEG basis
# --------------------------------------------------------------------------- #


@needs_store
def test_frcc_florida_real_fit():
    from loadsmith.ingest import ParquetStore

    store = ParquetStore(DATA_DIR)
    load = store.state_load("FRCC", "FL")
    basis = NYSEGBasis(store.nyseg_profiles(), slices=(2, 3, 5))
    day_types = day_type_calendar(2015)
    cir_df = store.cir_fractions("FRCC")
    row = cir_df[cir_df["state"] == "FL"].iloc[0]
    cir = (float(row["frac_c"]), float(row["frac_i"]), float(row["frac_r"]))

    result = fit_state(load, basis, day_types, cir, residual="residential")

    # Energy conservation (raw FL CIR sums to ~0.9958; fit_state renormalizes).
    np.testing.assert_allclose(result.total(), load, rtol=1e-9)
    assert (result.alphas >= 0).all()
    # All three classes carry real energy (not wildly unbalanced).
    annual_energy = result.class_loads.sum(axis=0)
    assert (annual_energy > 0).all()
    # Fit quality: the NYSEG day-type shapes describe Florida reasonably.
    rel = np.abs(result.residuals) / load
    median_rel, p95_rel = np.median(rel), np.percentile(rel, 95)
    print(f"\nFRCC FL fit quality: median |resid|/load = {median_rel:.4f}, "
          f"95th pct = {p95_rel:.4f}, class energy shares = "
          f"{annual_energy / annual_energy.sum()}")
    assert median_rel < 0.15
