"""Tests — basis construction (basis.py) and clustering (clustering.py).

All synthetic data; no repo data files required. Index conventions under
test are 1-based (MATLAB provenance): buildings 1..17, groups 1..10, NYSEG
slices (2, 3, 5), days 1..365.
"""

import numpy as np
import pytest

from loadsmith.basis import (
    NRELAggregateBasis,
    NYSEGBasis,
    UtilityBasis,
    normalize_columns,
)
from loadsmith.clustering import building_correlation_matrix, propose_clusters
from loadsmith.config import NRELBasisSpec, Role


def _dn(v: np.ndarray) -> np.ndarray:
    """Reference demean-then-L2-normalize (the MATLAB order)."""
    v = np.asarray(v, dtype=float)
    v = v - v.mean()
    return v / np.linalg.norm(v)


def _nrel_spec(fit_groups=(10, 9, 6)) -> NRELBasisSpec:
    """Synthetic 10-group spec: groups 1-7 singletons, 8 = [16]/2 (the B7
    singleton-over-2 oddity), 9 = [4 10]/2 (a real mean), 10 = [17]."""
    groups = {g: ((g,), 1.0) for g in range(1, 8)}
    groups[8] = ((16,), 2.0)
    groups[9] = ((4, 10), 2.0)
    groups[10] = ((17,), 1.0)
    return NRELBasisSpec(city_folder="synthetic", groups=groups, fit_groups=fit_groups)


# --------------------------------------------------------------------------- #
# 1. normalize_columns
# --------------------------------------------------------------------------- #


class TestNormalizeColumns:
    def test_basic_contract(self):
        rng = np.random.default_rng(1)
        base = rng.random((24, 4)) * 10 + 5
        snapshot = base.copy()

        out = normalize_columns(base)

        assert out is not base
        np.testing.assert_array_equal(base, snapshot)  # input not mutated
        np.testing.assert_array_equal(out[:, 0], base[:, 0])  # col 0 untouched
        for j in range(1, 4):
            assert abs(out[:, j].mean()) < 1e-12
            assert abs(np.linalg.norm(out[:, j]) - 1.0) < 1e-12
            np.testing.assert_allclose(out[:, j], _dn(base[:, j]))

    def test_demean_before_normalize(self):
        # A column with a big offset: normalizing BEFORE demeaning would give
        # a different (wrong) vector than demeaning first.
        v = np.arange(24, dtype=float) + 1000.0
        base = np.column_stack([np.ones(24), v])
        out = normalize_columns(base)
        np.testing.assert_allclose(out[:, 1], _dn(v))

    def test_zero_and_constant_columns_become_zeros(self):
        base = np.ones((24, 3))
        base[:, 1] = 0.0  # exact zeros
        base[:, 2] = 7.5  # constant -> zeros after demean
        out = normalize_columns(base)
        np.testing.assert_array_equal(out[:, 1], np.zeros(24))
        np.testing.assert_array_equal(out[:, 2], np.zeros(24))
        assert not np.isnan(out).any()  # MATLAB would have NaN here


# --------------------------------------------------------------------------- #
# 2. NYSEGBasis
# --------------------------------------------------------------------------- #


class TestNYSEGBasis:
    def test_slice_selection_and_shape(self):
        rng = np.random.default_rng(2)
        profiles = rng.random((24, 36, 9))  # hour x day-type x class
        b = NYSEGBasis(profiles)

        for day_type in (1, 17, 36):
            base = b.day_basis(day=42, day_type=day_type)
            assert base.shape == (24, 4)
            # cols 1..3 = normalized slices 2, 3, 5 (1-based) of this day-type
            for j, s in enumerate((2, 3, 5), start=1):
                np.testing.assert_allclose(
                    base[:, j], _dn(profiles[:, day_type - 1, s - 1])
                )

    def test_roles(self):
        b = NYSEGBasis(np.random.default_rng(3).random((24, 36, 9)))
        assert b.roles == (Role.RESIDENTIAL, Role.COMMERCIAL, Role.INDUSTRIAL)

    def test_day_type_bounds(self):
        b = NYSEGBasis(np.random.default_rng(4).random((24, 36, 9)))
        with pytest.raises(ValueError):
            b.day_basis(day=1, day_type=0)
        with pytest.raises(ValueError):
            b.day_basis(day=1, day_type=37)

    def test_slice_out_of_range_rejected(self):
        profiles = np.random.default_rng(5).random((24, 36, 9))
        with pytest.raises(ValueError):
            NYSEGBasis(profiles, slices=(2, 3, 10))


# --------------------------------------------------------------------------- #
# 3. NRELAggregateBasis
# --------------------------------------------------------------------------- #


class TestNRELAggregateBasis:
    def test_aggregate_hand_computed(self):
        rng = np.random.default_rng(6)
        cp = rng.random((8760, 17))
        agg = NRELAggregateBasis.aggregate(cp, _nrel_spec())

        assert agg.shape == (8760, 10)
        # group 9 = [4, 10]/2 (1-based buildings) == mean of 0-based cols 3, 9
        np.testing.assert_allclose(agg[:, 8], (cp[:, 3] + cp[:, 9]) / 2.0)
        np.testing.assert_allclose(agg[:, 8], cp[:, [3, 9]].mean(axis=1))
        # group 8 = [16]/2: the B7 singleton-over-2 oddity, preserved verbatim
        np.testing.assert_allclose(agg[:, 7], cp[:, 15] / 2.0)
        # group 10 = [17] (the TMY column)
        np.testing.assert_allclose(agg[:, 9], cp[:, 16])
        # singleton groups 1..7
        for g in range(1, 8):
            np.testing.assert_allclose(agg[:, g - 1], cp[:, g - 1])

    def test_day_basis_window_marker(self):
        rng = np.random.default_rng(7)
        cp = rng.random((8760, 17))
        marker = np.sin(np.linspace(0.0, 3.0, 24)) + 5.0
        day = 100
        cp[(day - 1) * 24 : day * 24, 16] = marker  # building 17 -> group 10

        basis = NRELAggregateBasis(cp, _nrel_spec(fit_groups=(10, 9, 6)))
        base = basis.day_basis(day, day_type=1)
        assert base.shape == (24, 4)
        # fit group 10 (residential) is column 1 and must be the day-100 marker
        np.testing.assert_allclose(base[:, 1], _dn(marker))
        # neighbouring days pick different windows
        for other in (99, 101):
            assert not np.allclose(basis.day_basis(other, 1)[:, 1], _dn(marker))
        # group 9 = mean of buildings 4 and 10, day-100 window
        expected_g9 = (cp[(day - 1) * 24 : day * 24, 3] + cp[(day - 1) * 24 : day * 24, 9]) / 2.0
        np.testing.assert_allclose(base[:, 2], _dn(expected_g9))

    def test_day_type_ignored(self):
        cp = np.random.default_rng(8).random((8760, 17))
        basis = NRELAggregateBasis(cp, _nrel_spec())
        np.testing.assert_array_equal(
            basis.day_basis(50, day_type=1), basis.day_basis(50, day_type=36)
        )

    def test_roles(self):
        cp = np.random.default_rng(9).random((8760, 17))
        basis = NRELAggregateBasis(cp, _nrel_spec())
        assert basis.roles == (Role.RESIDENTIAL, Role.COMMERCIAL, Role.INDUSTRIAL)

    def test_fit_group_must_be_defined(self):
        cp = np.random.default_rng(10).random((8760, 17))
        spec = _nrel_spec(fit_groups=(10, 9, 11))  # group 11 does not exist
        with pytest.raises(ValueError):
            NRELAggregateBasis(cp, spec)


# --------------------------------------------------------------------------- #
# 4. UtilityBasis
# --------------------------------------------------------------------------- #


class TestUtilityBasis:
    @staticmethod
    def _profiles(rng):
        return {role: rng.random((365, 24)) + 1.0 for role in Role}

    def test_column_order_insertion_independent(self):
        rng = np.random.default_rng(11)
        com, ind, res = rng.random((365, 24)), rng.random((365, 24)), rng.random((365, 24))
        # deliberately scrambled insertion order: R, I, C
        ub = UtilityBasis(
            {Role.RESIDENTIAL: res, Role.INDUSTRIAL: ind, Role.COMMERCIAL: com}
        )
        assert ub.roles == (Role.COMMERCIAL, Role.INDUSTRIAL, Role.RESIDENTIAL)

        day = 200
        base = ub.day_basis(day, day_type=3)
        assert base.shape == (24, 4)
        np.testing.assert_allclose(base[:, 1], _dn(com[day - 1, :]))
        np.testing.assert_allclose(base[:, 2], _dn(ind[day - 1, :]))
        np.testing.assert_allclose(base[:, 3], _dn(res[day - 1, :]))

    def test_day_indexing_one_based(self):
        rng = np.random.default_rng(12)
        profiles = self._profiles(rng)
        ub = UtilityBasis(profiles)
        # day=1 -> row 0; day=365 -> row 364
        np.testing.assert_allclose(
            ub.day_basis(1, 1)[:, 1], _dn(profiles[Role.COMMERCIAL][0, :])
        )
        np.testing.assert_allclose(
            ub.day_basis(365, 1)[:, 3], _dn(profiles[Role.RESIDENTIAL][364, :])
        )

    def test_bad_profile_shape_rejected(self):
        with pytest.raises(ValueError):
            UtilityBasis({Role.COMMERCIAL: np.zeros((24, 365))})  # transposed


# --------------------------------------------------------------------------- #
# 5. clustering
# --------------------------------------------------------------------------- #


class TestClustering:
    def test_correlation_matrix_properties(self):
        rng = np.random.default_rng(13)
        cp = rng.random((8760, 17))
        cp[:, 5] = cp[:, 3]  # duplicate building -> perfect per-day correlation
        cp[:, 2] = 4.2       # constant building -> zero rows via the norm guard

        r = building_correlation_matrix(cp)
        assert r.shape == (16, 16)
        np.testing.assert_allclose(r, r.T)  # symmetric
        # diagonal = sum of 365 per-day unit self-correlations
        for i in (0, 3, 15):
            assert abs(r[i, i] - 365.0) < 1e-9
        # identical buildings correlate at the maximum
        assert abs(r[3, 5] - 365.0) < 1e-9
        # constant building contributes zeros (MATLAB would produce NaN)
        assert r[2, 2] == 0.0
        assert not np.isnan(r).any()

    def test_correlation_matrix_shape_check(self):
        with pytest.raises(ValueError):
            building_correlation_matrix(np.zeros((8760, 16)))

    def test_propose_clusters_labels(self):
        rng = np.random.default_rng(14)
        a = rng.random((16, 16))
        corr = (a + a.T) / 2.0  # symmetric, like a real correlation matrix

        labels = propose_clusters(corr)
        assert labels.shape == (16,)
        assert np.issubdtype(labels.dtype, np.integer)
        assert labels.min() >= 1 and labels.max() <= 9
        # distinct random rows -> distinct merge heights -> exactly 9 clusters
        assert len(np.unique(labels)) == 9

    def test_propose_clusters_duplicate_rows_cluster_together(self):
        rng = np.random.default_rng(15)
        m = rng.random((16, 16))
        m[7, :] = m[2, :]  # exact duplicate rows -> distance 0 -> same cluster
        labels = propose_clusters(m)
        assert labels[2] == labels[7]

    def test_propose_clusters_n_clusters(self):
        rng = np.random.default_rng(16)
        labels = propose_clusters(rng.random((16, 16)), n_clusters=4)
        assert labels.min() >= 1 and labels.max() <= 4


# --------------------------------------------------------------------------- #
# 6. day_basis contract, all three sources
# --------------------------------------------------------------------------- #


def _all_sources():
    rng = np.random.default_rng(17)
    nyseg = NYSEGBasis(rng.random((24, 36, 9)) + 0.5)
    nrel = NRELAggregateBasis(rng.random((8760, 17)) + 0.5, _nrel_spec())
    utility = UtilityBasis({role: rng.random((365, 24)) + 0.5 for role in Role})
    return [("nyseg", nyseg), ("nrel", nrel), ("utility", utility)]


@pytest.mark.parametrize(
    "name,source", _all_sources(), ids=[n for n, _ in _all_sources()]
)
@pytest.mark.parametrize("day,day_type", [(1, 1), (100, 17), (365, 36)])
def test_day_basis_contract(name, source, day, day_type):
    base = source.day_basis(day, day_type)
    assert base.shape == (24, 1 + len(source.roles))
    np.testing.assert_array_equal(base[:, 0], np.ones(24))  # trend column
    for j in range(1, base.shape[1]):
        assert abs(base[:, j].mean()) < 1e-9   # demeaned
        assert abs(np.linalg.norm(base[:, j]) - 1.0) < 1e-9  # unit norm


@pytest.mark.parametrize(
    "name,source", _all_sources(), ids=[n for n, _ in _all_sources()]
)
@pytest.mark.parametrize("day", [0, 366, -3])
def test_day_out_of_range(name, source, day):
    with pytest.raises(ValueError):
        source.day_basis(day, day_type=1)
