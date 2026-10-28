"""Regression — SPP + AZNM vs their UW reference CSVs.

SPP verdict (2026-07-10): ÷CIR, no loadscaling, scale 1.0,
carrying all three SPP copy-paste bugs (regions/SPP.md):

* NB 6.7e-06 / SD 6.5e-06 / TX 7.0e-06 @ scale 1.0 in production.
* ND: reference fit on OK-CITY aggregates (faithful 6.6e-06 vs production
  8.8e-03) — bug #1.
* OK: reference industrial class tiles ND's stale day-365 CI_top (faithful
  5.8e-06; production median 1.4e-05 but p99 2.5e-02) — bug #2.
* KS: reference distribution reuses share col 24 for the industrial term
  (faithful 6.6e-06 vs production 2.2e-01; reference over-delivers KS
  energy x CIR_C/CIR_I ~= 1.127) — bug #3.
* F1 fully resolved: SPP bus table = 8,025 rows; the 1:3123 bound was an
  SRMV copy-paste (moot via B1). No NaN whitelists.

AZNM verdict (same day): ÷CIR, no loadscaling, scale 1.0 — but the
reference's column-1 bus numbers are an OLDER numbering revision (3,948 of
4,536 differ; matches neither the current xlsx nor the Steve workbook's
Initial column), so AZNM joins BY ROW ORDER (the physical rows are the
same buses, proven by the agreement itself):

* AZ 7.6e-06 / CO 6.1e-06 / NM 7.1e-06 / UT 7.5e-06 @ scale 1.0;
  NV 2.6e-05 @ 0.999729 (= NV's raw-CIR row sum). No NaN whitelists.

Thresholds = measured medians × ~3 headroom. Skips cleanly without the
parquet store or the external UW reference CSVs.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

DATA_DIR = Path(__file__).resolve().parents[1] / "data"

pytestmark = pytest.mark.skipif(
    not (DATA_DIR / "spp" / "bus_table.parquet").exists(),
    reason="parquet store not built — run scripts/migrate_data.py first",
)

SPP_CODES = {"KS": 1, "NB": 2, "ND": 3, "OK": 4, "SD": 5, "TX": 6}


def _median_rel(mine, theirs, scale=1.0):
    rel = np.abs(mine * scale - theirs) / np.maximum(np.abs(theirs), 1e-6)
    return float(np.median(rel))


@pytest.fixture(scope="module")
def spp_reference():
    from loadsmith.validation import Validator

    v = Validator()
    path = v.find_reference("SPP", "P")
    if path is None:
        pytest.skip("SPP P reference CSV not found (external UW folder)")
    return v.load_reference(path)


@pytest.fixture(scope="module")
def spp_production(spp_reference):
    from loadsmith import LoadSmith
    from loadsmith.ingest import ParquetStore

    ref_bus, _ = spp_reference
    res = LoadSmith(store=DATA_DIR).run("SPP", formats=())
    assert res.validation_report["ok"]
    assert res.p_load.shape == (8025, 8760)      # F1: SPP half resolved
    order = {int(b): i for i, b in enumerate(res.national_bus_numbers)}
    ri = np.array([order[int(b)] for b in ref_bus])   # KeyError = join failure
    codes = ParquetStore(DATA_DIR).bus_table("SPP")["state_code"].to_numpy()[ri]
    return res.p_load[ri], codes


@pytest.fixture(scope="module")
def spp_state_helpers(spp_reference):
    """Shared join/fit machinery for the faithful-bug reconstructions."""
    from loadsmith.ingest import ParquetStore

    ref_bus, _ = spp_reference
    store = ParquetStore(DATA_DIR)
    bus = store.bus_table("SPP")
    cir = store.cir_fractions("SPP").set_index("state")

    def rows(code, codes):
        mb = (bus["state_code"] == code).to_numpy()
        shares = bus.loc[mb, ["share_c", "share_i", "share_r"]].to_numpy()
        nat = bus.loc[mb, "national_bus_num"].to_numpy()
        order = {int(b): i for i, b in enumerate(nat)}
        mref = codes == code
        sel = np.array([order[int(b)] for b in ref_bus[mref]])
        return shares, sel, mref

    return store, cir, rows


def test_spp_reference_agreement_clean_states(spp_reference, spp_production):
    _, ref = spp_reference
    mine, codes = spp_production
    assert np.isfinite(ref).all()                # no NaN whitelists in SPP
    for abbrev in ("NB", "SD", "TX"):
        m = codes == SPP_CODES[abbrev]
        assert _median_rel(mine[m], ref[m]) < 2e-5, abbrev


def test_spp_nd_faithful_ok_aggregates(spp_reference, spp_production,
                                       spp_state_helpers):
    """Bug #1: the reference's ND fit sliced profiles_aggregate_OK."""
    from loadsmith.basis import NRELAggregateBasis
    from loadsmith.distribution import distribute
    from loadsmith.fitting import fit_state
    from loadsmith.profile_calendar import day_type_calendar
    from loadsmith.regions.spp import ND_MATLAB_FAITHFUL_NREL

    _, ref = spp_reference
    mine, codes = spp_production
    store, cir, rows = spp_state_helpers

    m = codes == SPP_CODES["ND"]
    assert _median_rel(mine[m], ref[m]) > 2e-3   # production deviates (guard)

    basis = NRELAggregateBasis(
        store.nrel_profiles("SPP", "NREL_Profiles/Oklahoma_City"),
        ND_MATLAB_FAITHFUL_NREL)
    fit = fit_state(store.state_load("SPP", "ND"), basis,
                    day_type_calendar(2015)[:365], tuple(cir.loc["ND"]),
                    residual="proportional")
    shares, sel, mref = rows(SPP_CODES["ND"], codes)
    p = distribute(fit.class_loads, shares)
    assert _median_rel(p[sel], ref[mref]) < 2e-5


def test_spp_ok_faithful_stale_nd_ci_top(spp_reference, spp_production,
                                         spp_state_helpers):
    """Bug #2: the reference's OK industrial class tiles ND's day-365
    com/ind component into all 365 days."""
    from loadsmith.basis import NRELAggregateBasis
    from loadsmith.distribution import distribute
    from loadsmith.fitting import fit_state
    from loadsmith.profile_calendar import day_type_calendar
    from loadsmith.regions.spp import NREL, ND_MATLAB_FAITHFUL_NREL

    _, ref = spp_reference
    mine, codes = spp_production
    store, cir, rows = spp_state_helpers
    cal = day_type_calendar(2015)[:365]
    ok_profiles = store.nrel_profiles("SPP", "NREL_Profiles/Oklahoma_City")

    # the stale vector comes from the ND-FAITHFUL fit (it ran on OK's basis)
    basis_nd = NRELAggregateBasis(ok_profiles, ND_MATLAB_FAITHFUL_NREL)
    fit_nd = fit_state(store.state_load("SPP", "ND"), basis_nd, cal,
                       tuple(cir.loc["ND"]), residual="proportional")
    nd_ci_365 = basis_nd.day_basis(365, 0)[:, 2:4] @ fit_nd.alphas[364, 2:4]

    basis_ok = NRELAggregateBasis(ok_profiles, NREL["OK"])
    fit_ok = fit_state(store.state_load("SPP", "OK"), basis_ok, cal,
                       tuple(cir.loc["OK"]), residual="proportional")
    ok_ci_top = np.empty(8760)
    for day in range(1, 366):
        B = basis_ok.day_basis(day, 0)
        ok_ci_top[(day - 1) * 24: day * 24] = B[:, 2:4] @ fit_ok.alphas[day - 1, 2:4]

    ok_cir = cir.loc["OK"].to_numpy()
    cl = fit_ok.class_loads.copy()
    cl[:, 1] += ((np.tile(nd_ci_365, 365) - ok_ci_top)
                 * ok_cir[1] / (ok_cir[0] + ok_cir[1]))
    shares, sel, mref = rows(SPP_CODES["OK"], codes)
    p = distribute(cl, shares)
    assert _median_rel(p[sel], ref[mref]) < 2e-5
    # guard: production's tail deviates even though its median is small
    rel_prod = (np.abs(mine[mref] - ref[mref])
                / np.maximum(np.abs(ref[mref]), 1e-6))
    assert np.percentile(rel_prod, 99) > 5e-3


def test_spp_ks_faithful_share_col24_reuse(spp_reference, spp_production,
                                           spp_state_helpers):
    """Bug #3: the reference's KS distribution uses the commercial share
    column for the industrial term (col 25 never read)."""
    from loadsmith.basis import NRELAggregateBasis
    from loadsmith.fitting import fit_state
    from loadsmith.profile_calendar import day_type_calendar
    from loadsmith.regions.spp import NREL

    _, ref = spp_reference
    mine, codes = spp_production
    store, cir, rows = spp_state_helpers

    m = codes == SPP_CODES["KS"]
    assert _median_rel(mine[m], ref[m]) > 5e-2   # production deviates (guard)
    # the reference over-delivers KS energy (the CIR_C/CIR_I leak, ~1.127)
    ks_cir = cir.loc["KS"].to_numpy()
    energy_ratio = ref[m].sum() / mine[m].sum()
    assert 1.05 < energy_ratio < 1.25, energy_ratio

    basis = NRELAggregateBasis(
        store.nrel_profiles("SPP", "NREL_Profiles/Wichita"), NREL["KS"])
    fit = fit_state(store.state_load("SPP", "KS"), basis,
                    day_type_calendar(2015)[:365], tuple(ks_cir),
                    residual="proportional")
    shares, sel, mref = rows(SPP_CODES["KS"], codes)
    cl = fit.class_loads
    p = (np.outer(shares[:, 0], cl[:, 0] + cl[:, 1] * ks_cir[0] / ks_cir[1])
         + np.outer(shares[:, 2], cl[:, 2]))
    assert _median_rel(p[sel], ref[mref]) < 2e-5


# --------------------------------------------------------------------------- #
# AZNM
# --------------------------------------------------------------------------- #

AZNM_CODES = {"AZ": 1, "CO": 2, "NV": 3, "NM": 4, "UT": 5}


@pytest.fixture(scope="module")
def aznm_reference():
    from loadsmith.validation import Validator

    v = Validator()
    path = v.find_reference("AZNM", "P")
    if path is None:
        pytest.skip("AZNM P reference CSV not found (external UW folder)")
    return v.load_reference(path)


def test_aznm_reference_is_an_older_bus_numbering(aznm_reference):
    """Guard the row-order join contract: the reference's bus numbers are a
    DIFFERENT (older) revision than the current bus table. If this fails,
    the reference was regenerated with current numbers — switch AZNM to the
    standard bus-number join and update AZNM.md."""
    from loadsmith.ingest import ParquetStore

    ref_bus, _ = aznm_reference
    ours = ParquetStore(DATA_DIR).bus_table("AZNM")["national_bus_num"].to_numpy()
    assert len(ref_bus) == len(ours)
    # same cardinality, same row order semantics, materially different sets
    assert (ref_bus.astype(int) != ours.astype(int)).sum() > 3000
    # both monotone -> row order is well-defined on both sides
    assert np.all(np.diff(ref_bus.astype(int)) > 0)
    assert np.all(np.diff(ours.astype(int)) > 0)


def test_aznm_reference_agreement_row_order(aznm_reference):
    """All five states in production mode, joined BY ROW ORDER; NV at its
    raw-CIR-sum scale 0.999729."""
    from loadsmith import LoadSmith
    from loadsmith.ingest import ParquetStore

    _, ref = aznm_reference
    assert np.isfinite(ref).all()               # no NaN whitelists in AZNM
    store = ParquetStore(DATA_DIR)
    res = LoadSmith(store=DATA_DIR).run("AZNM", formats=())
    assert res.validation_report["ok"]
    assert res.p_load.shape == (4536, 8760)

    codes = store.bus_table("AZNM")["state_code"].to_numpy()
    cir = store.cir_fractions("AZNM").set_index("state")
    for abbrev, code in AZNM_CODES.items():
        m = codes == code
        scale = float(cir.loc[abbrev].sum())    # 1.0 except NV 0.999729
        assert 0.9995 < scale < 1.0 + 1e-6, abbrev
        assert _median_rel(res.p_load[m], ref[m], scale) < 8e-5, abbrev
        rel = (np.abs(res.p_load[m] * scale - ref[m])
               / np.maximum(np.abs(ref[m]), 1e-6))
        assert (rel <= 1e-2).mean() > 0.999, abbrev
