"""Regression — NWPP + RFCE vs their UW reference CSVs.

NWPP verdict (2026-07-10): ÷CIR, no loadscaling, scale 1.0
(the KCL-KVL function variant is identical — neither has loadscaling):

* ID 6.0e-06 / MT 5.9e-06 / OR 6.2e-06 / WA 6.1e-06 @ scale 1.0 in full
  production (the e1 day-shift quirk is migrated faithfully).
* WY: reference carries the ID_Res_top bug (Idaho's stale day-365
  residential component tiled into every WY day) — faithful 6.0e-06 vs
  production 4.9e-02.
* Reference bus numbers are an OLDER revision (2,845/2,977 differ) —
  row-order join, as with AZNM.
* KNOWN EXCEPTION: production trips q_envelope by ~0.73 MVAr (slack 0.5)
  because WY's residential class goes negative on 138 hours under the
  'residential' residual policy; the structural test below pins exactly this.

RFCE verdict (same day): the reference is the KCL-KVL FUNCTION variant
(like FRCC): ÷CIR × global loadscaling 0.865687 (peak pinned to 48,489 MW
on the BUGGED matrix), raw CIR (NJ sums to 0.999964), and the PN
NJ_CIR(1) bug (NJ's commercial fraction in PN's commercial trend term):

* faithful reconstruction × the computed loadscaling: NJ 7.7e-06 /
  PN 6.5e-06 @ scale 1.0. Production NJ = constant 0.865656 away;
  production PN deviates ~10% median (bug fixed).
* peak_scaling="kclkvl" on the FIXED matrix gives 0.965592, NOT the
  reference's 0.865687 — the reference factor requires the bug.
* NJ hours 1587 & 7298 (1-based) NaN in the reference; days 67 & 305 were
  fit by an NNLS that DROPPED the NaN hour (23-hour fit, reproduced at
  8.6e-06) — a THIRD NaN signature, unlike the zero-alpha passthrough in
  the SRVC/SRTV references (different solver environment for the KCL-KVL
  variant). Bus-number join clean.

Thresholds = measured medians × ~3 headroom. Skips cleanly without the
parquet store or the external UW reference CSVs.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

DATA_DIR = Path(__file__).resolve().parents[1] / "data"

pytestmark = pytest.mark.skipif(
    not (DATA_DIR / "nwpp" / "bus_table.parquet").exists(),
    reason="parquet store not built — run scripts/migrate_data.py first",
)

NWPP_CODES = {"ID": 1, "MT": 2, "OR": 3, "WA": 4, "WY": 5}


def _median_rel(mine, theirs, scale=1.0):
    rel = np.abs(mine * scale - theirs) / np.maximum(np.abs(theirs), 1e-6)
    return float(np.median(rel))


@pytest.fixture(scope="module")
def nwpp_reference():
    from loadsmith.validation import Validator

    v = Validator()
    path = v.find_reference("NWPP", "P")
    if path is None:
        pytest.skip("NWPP P reference CSV not found (external UW folder)")
    return v.load_reference(path)


@pytest.fixture(scope="module")
def nwpp_production():
    from loadsmith import LoadSmith

    return LoadSmith(store=DATA_DIR).run("NWPP", formats=())


def test_nwpp_reference_bus_numbering_is_older_revision(nwpp_reference):
    """Row-order join contract (cf. AZNM): the reference's bus numbers are
    an older revision. If this fails, switch NWPP to the bus-number join."""
    from loadsmith.ingest import ParquetStore

    ref_bus, _ = nwpp_reference
    ours = ParquetStore(DATA_DIR).bus_table("NWPP")["national_bus_num"].to_numpy()
    assert len(ref_bus) == len(ours)
    assert (ref_bus.astype(int) != ours.astype(int)).sum() > 2000
    assert np.all(np.diff(ref_bus.astype(int)) > 0)
    assert np.all(np.diff(ours.astype(int)) > 0)


def test_nwpp_reference_agreement_row_order(nwpp_reference, nwpp_production):
    """ID/MT/OR/WA in full production mode at scale 1.0 (row-order join).
    OR/WA passing at 6e-06 also locks in the e1 day-shift migration."""
    from loadsmith.ingest import ParquetStore

    _, ref = nwpp_reference
    res = nwpp_production
    assert res.p_load.shape == (2977, 8760)
    assert np.isfinite(ref).all()
    codes = ParquetStore(DATA_DIR).bus_table("NWPP")["state_code"].to_numpy()
    for abbrev in ("ID", "MT", "OR", "WA"):
        m = codes == NWPP_CODES[abbrev]
        assert _median_rel(res.p_load[m], ref[m]) < 2e-5, abbrev


def test_nwpp_wy_faithful_id_res_top(nwpp_reference, nwpp_production):
    """The reference's WY residential class contains Idaho's stale day-365
    Res_top (line 405); production (fixed) must deviate."""
    from loadsmith.basis import NRELAggregateBasis
    from loadsmith.distribution import distribute
    from loadsmith.fitting import fit_state
    from loadsmith.ingest import ParquetStore
    from loadsmith.profile_calendar import day_type_calendar
    from loadsmith.regions import REGISTRY

    _, ref = nwpp_reference
    res = nwpp_production
    store = ParquetStore(DATA_DIR)
    bus = store.bus_table("NWPP")
    codes = bus["state_code"].to_numpy()
    cir = store.cir_fractions("NWPP").set_index("state")
    cal = day_type_calendar(2015)[:365]
    cfg = REGISTRY["NWPP"]

    m = codes == NWPP_CODES["WY"]
    assert _median_rel(res.p_load[m], ref[m]) > 1e-2   # guard: bug in ref

    id_cfg = next(s for s in cfg.states if s.abbrev == "ID")
    wy_cfg = next(s for s in cfg.states if s.abbrev == "WY")
    basis_id = NRELAggregateBasis(
        store.nrel_profiles("NWPP", id_cfg.nrel.city_folder), id_cfg.nrel)
    fit_id = fit_state(store.state_load("NWPP", "ID"), basis_id, cal,
                       tuple(cir.loc["ID"]), residual="residential")
    id_res_365 = basis_id.day_basis(365, 0)[:, 1] * fit_id.alphas[364, 1]

    basis_wy = NRELAggregateBasis(
        store.nrel_profiles("NWPP", wy_cfg.nrel.city_folder), wy_cfg.nrel)
    fit_wy = fit_state(store.state_load("NWPP", "WY"), basis_wy, cal,
                       tuple(cir.loc["WY"]), residual="residential")
    wy_res_top = np.empty(8760)
    for day in range(1, 366):
        B = basis_wy.day_basis(day, 0)
        wy_res_top[(day - 1) * 24: day * 24] = B[:, 1] * fit_wy.alphas[day - 1, 1]

    cl = fit_wy.class_loads.copy()
    cl[:, 2] += np.tile(id_res_365, 365) - wy_res_top
    p = distribute(cl, bus.loc[m, ["share_c", "share_i", "share_r"]].to_numpy())
    assert _median_rel(p, ref[m]) < 2e-5


def test_nwpp_structural_known_q_envelope_exception(nwpp_production):
    """Every structural check passes EXCEPT (at most) q_envelope, which the
    WY negative-residential hours push ~0.73 MVAr past the 0.5 slack —
    known + flagged to the validation.py owner. If q_envelope starts
    passing (slack adjusted) this test still passes; if anything ELSE
    fails, that's a real regression."""
    rep = nwpp_production.validation_report
    failed = {k for k, v in rep["checks"].items() if v.get("ok") is False}
    assert failed <= {"q_envelope"}, failed
    if "q_envelope" in failed:
        assert rep["checks"]["q_envelope"]["max_excess_mvar"] < 1.5


# --------------------------------------------------------------------------- #
# RFCE
# --------------------------------------------------------------------------- #

RFCE_CODES = {"NJ": 1, "PN": 2}
RFCE_PEAK_TARGET = 48489.0
NJ_NAN_COLS = (1586, 7297)                 # 0-based
NJ_NAN_FIT_DAYS = (66, 304)                # 0-based days with 23-hour fits


@pytest.fixture(scope="module")
def rfce_reference():
    from loadsmith.validation import Validator

    v = Validator()
    path = v.find_reference("RFCE", "P")
    if path is None:
        pytest.skip("RFCE P reference CSV not found (external UW folder)")
    return v.load_reference(path)


@pytest.fixture(scope="module")
def rfce_faithful():
    """MATLAB-faithful matrix: NJ raw CIR + PN NJ_CIR(1) bug, then the
    KCL-KVL loadscaling computed exactly as the function variant does."""
    from loadsmith.basis import NRELAggregateBasis
    from loadsmith.distribution import distribute
    from loadsmith.fitting import fit_state
    from loadsmith.ingest import ParquetStore
    from loadsmith.profile_calendar import day_type_calendar
    from loadsmith.regions import REGISTRY

    store = ParquetStore(DATA_DIR)
    bus = store.bus_table("RFCE")
    cir = store.cir_fractions("RFCE").set_index("state")
    cal = day_type_calendar(2015)[:365]
    nj_raw = cir.loc["NJ"].to_numpy()
    pn_raw = cir.loc["PN"].to_numpy()

    cls = {}
    for st in REGISTRY["RFCE"].states:
        basis = NRELAggregateBasis(
            store.nrel_profiles("RFCE", st.nrel.city_folder), st.nrel)
        fit = fit_state(store.state_load("RFCE", st.abbrev), basis, cal,
                        tuple(cir.loc[st.abbrev]), residual="proportional")
        trend = np.repeat(fit.alphas[:, 0], 24)
        if st.abbrev == "NJ":
            sigma = nj_raw.sum()             # 0.999964: undo renormalization
            cls["NJ"] = (fit.class_loads
                         - (1.0 - sigma)
                         * np.outer(trend + fit.residuals, nj_raw / sigma))
        else:
            cl = fit.class_loads.copy()
            cl[:, 0] += trend * (nj_raw[0] - pn_raw[0])   # the NJ_CIR(1) bug
            cls["PN"] = cl

    p = np.zeros((len(bus), 8760))
    codes = bus["state_code"].to_numpy()
    for ab, c in RFCE_CODES.items():
        m = codes == c
        p[m] = distribute(cls[ab],
                          bus.loc[m, ["share_c", "share_i", "share_r"]].to_numpy())
    loadscale = RFCE_PEAK_TARGET / p.sum(axis=0).max()
    return p, loadscale, codes, bus


def test_rfce_faithful_matches_with_loadscaling(rfce_reference, rfce_faithful):
    ref_bus, ref = rfce_reference
    p, loadscale, codes, bus = rfce_faithful
    assert 0.86 < loadscale < 0.87            # the reference lineage factor

    order = {int(b): i for i, b in enumerate(bus["national_bus_num"].to_numpy())}
    ri = np.array([order[int(b)] for b in ref_bus])   # bus-number join CLEAN
    mine = p[ri] * loadscale
    rcodes = codes[ri]

    drop = list(NJ_NAN_COLS)
    for d in NJ_NAN_FIT_DAYS:
        drop.extend(range(d * 24, d * 24 + 24))
    fin_nj = np.setdiff1d(np.arange(8760), drop)
    for abbrev, code in RFCE_CODES.items():
        m = rcodes == code
        fin = fin_nj if abbrev == "NJ" else np.arange(8760)
        assert _median_rel(mine[m][:, fin], ref[m][:, fin]) < 2e-5, abbrev


def test_rfce_production_relationships(rfce_reference):
    """Production (fixed): NJ = one constant away from the reference;
    PN deviates; kclkvl factor on the FIXED matrix is 0.9656 (not 0.8657)."""
    from loadsmith import LoadSmith
    from loadsmith.ingest import ParquetStore

    ref_bus, ref = rfce_reference
    res = LoadSmith(store=DATA_DIR).run("RFCE", formats=())
    assert res.validation_report["ok"]
    assert res.p_load.shape == (5218, 8760)

    store = ParquetStore(DATA_DIR)
    codes = store.bus_table("RFCE")["state_code"].to_numpy()
    order = {int(b): i for i, b in enumerate(res.national_bus_numbers)}
    ri = np.array([order[int(b)] for b in ref_bus])
    mine, rcodes = res.p_load[ri], codes[ri]

    fin = np.setdiff1d(np.arange(8760), NJ_NAN_COLS)
    m = rcodes == RFCE_CODES["NJ"]
    scale = ref[m][:, fin].sum() / mine[m][:, fin].sum()
    assert 0.86 < scale < 0.87                # loadscaling x NJ CIR sum
    assert _median_rel(mine[m][:, fin], ref[m][:, fin], scale) < 5e-4

    m = rcodes == RFCE_CODES["PN"]
    scale = ref[m].sum() / mine[m].sum()
    assert _median_rel(mine[m], ref[m], scale) > 5e-2   # bug fixed -> deviates

    scaled = LoadSmith(store=DATA_DIR).run(
        "RFCE", formats=(), peak_scaling="kclkvl", validate=False)
    assert scaled.metadata["peak_target_mw"] == RFCE_PEAK_TARGET
    assert 0.96 < scaled.metadata["peak_scale_factor"] < 0.97


def test_rfce_nj_nan_days_are_23_hour_fits(rfce_reference, rfce_faithful):
    """NJ NaN columns exactly as inventoried; the two containing days were
    fit by an NNLS that DROPPED the NaN hour (23-hour fit) — NOT the
    zero-alpha passthrough seen in the SRVC/SRTV references. If this fails
    with a zero-alpha-like signature, the reference was regenerated with a
    stock-MATLAB lsqnonneg; update the whitelist story in RFCE.md."""
    import scipy.io as sio
    from scipy.optimize import nnls

    from loadsmith.basis import NRELAggregateBasis
    from loadsmith.ingest import ParquetStore
    from loadsmith.profile_calendar import day_type_calendar
    from loadsmith.regions import REGISTRY

    ref_bus, ref = rfce_reference
    _, loadscale, codes, bus = rfce_faithful
    store = ParquetStore(DATA_DIR)

    order = {int(b): i for i, b in enumerate(bus["national_bus_num"].to_numpy())}
    ri = np.array([order[int(b)] for b in ref_bus])
    rcodes = codes[ri]
    nj = rcodes == RFCE_CODES["NJ"]
    nan_cols = np.where(~np.isfinite(ref[nj]).all(axis=0))[0]
    assert tuple(nan_cols) == NJ_NAN_COLS
    assert np.isfinite(ref[rcodes == RFCE_CODES["PN"]]).all()

    nj_raw = store.cir_fractions("RFCE").set_index("state").loc["NJ"].to_numpy()
    nj_cfg = next(s for s in REGISTRY["RFCE"].states if s.abbrev == "NJ")
    basis = NRELAggregateBasis(
        store.nrel_profiles("RFCE", nj_cfg.nrel.city_folder), nj_cfg.nrel)
    # Raw (unrepaired) NJ series from the archived MATLAB input. This file lives
    # in the read-only RFCE/ archive, not the parquet store, so it is absent in a
    # code-only checkout — skip cleanly rather than fail (module docstring).
    nj_mat = Path(__file__).resolve().parents[1] / "RFCE" / "NewJersey.mat"
    if not nj_mat.exists():
        pytest.skip(f"raw MATLAB archive not present ({nj_mat.name})")
    raw = np.asarray(sio.loadmat(str(nj_mat))["NJ"]).ravel()  # unrepaired

    mb = (bus["state_code"] == RFCE_CODES["NJ"]).to_numpy()
    shares = bus.loc[mb, ["share_c", "share_i", "share_r"]].to_numpy()
    nat = bus.loc[mb, "national_bus_num"].to_numpy()
    o = {int(b): i for i, b in enumerate(nat)}
    sel = np.array([o[int(b)] for b in ref_bus[nj]])
    c, i_, r = nj_raw

    for d0 in NJ_NAN_FIT_DAYS:
        B = basis.day_basis(d0 + 1, 0)
        y = raw[d0 * 24:(d0 + 1) * 24]
        fin = np.isfinite(y)
        assert fin.sum() == 23
        alpha, _ = nnls(B[fin], y[fin])          # the NaN-hour-dropped fit
        trend = B[:, 0] * alpha[0]
        res_top = B[:, 1] * alpha[1]
        ci_top = B[:, 2:4] @ alpha[2:4]
        resid = y - B @ alpha
        cl = np.stack([
            trend * c + ci_top * c / (c + i_) + resid * c,
            trend * i_ + ci_top * i_ / (c + i_) + resid * i_,
            trend * r + res_top + resid * r,
        ], axis=1)
        pred = (shares @ cl.T) * loadscale
        day = ref[nj][:, d0 * 24:(d0 + 1) * 24]
        fmask = np.isfinite(day)
        rel = (np.abs(pred[sel][fmask] - day[fmask])
               / np.maximum(np.abs(day[fmask]), 1e-6))
        assert np.median(rel) < 5e-5, (d0, float(np.median(rel)))
