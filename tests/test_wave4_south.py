"""Regression — SRVC + SRTV + SRMV vs their UW reference CSVs.

SRVC verdict (established 2026-07-10, FRCC methodology):
the reference is the REPO SCRIPT's own output — ÷CIR distribution, no
loadscaling, B6 present, unrepaired NorthCarolina.mat, raw (un-normalized)
CIR rows:

* DC / MY / VG: median ≈ 6e-06 @ scale 1.0 (their raw CIR rows sum to 1.0).
* DL @ 0.999639, NC @ 0.999378 — each scale IS the state's raw-CIR row sum
  (LoadSmith renormalizes CIR to Σ=1, the MATLAB didn't).
* WV: matches (5.5e-06) only with bug B6 reproduced (MY_CIR(3) in the
  residential trend term); the FIXED production output deviates ~14% median.
* NC: reference hour 17 (1-based) is NaN on every NC bus, and reference
  day 1 is the ZERO-ALPHA passthrough (MATLAB lsqnonneg returns x=0 when
  the target has a NaN) = Σ(raw shares) × raw NC load — reproduced at
  median 6.6e-06.

SRTV verdict (same day): ÷CIR, no loadscaling, scale 1.0 (repo script or
the algorithmically identical KCL-KVL function variant):

* AL 6.3e-06 / KY 6.0e-06 / TN 6.0e-06 @ scale 1.0; MS 7.6e-06 @ 0.999975
  (= MS's raw-CIR row sum; AL/KY/TN rows sum to 1.0).
* AL matches ONLY with the Birmingham ASCII dir-order permutation now in
  loadsmith/regions/srtv.py (the stray headerless 'aRefBldg…' restaurant
  sorted LAST, took the x1000 slot, and is AL's actual res-basis; the
  canonical reading deviates 2.9e-02 — guarded below).
* KY hours 1587 & 7298, TN hour 699 (1-based) are NaN in the reference and
  their DAYS (67, 305, 30) are lsqnonneg zero-alpha passthroughs.

SRMV verdict (same day): ÷CIR, no loadscaling, scale 1.0, RAW workbook CIR:

* AR 7.5e-06 / MO 6.0e-06 @ scale 1.0 (raw CIR rows sum to 1.0).
* LO (Louisiana): raw CIR row sums to 0.902455, so the MATLAB fit leaked
  ~9.75% of trend+residual energy. Production (renormalized, conserving)
  runs ~10.8% above the reference BY DESIGN; rebuilding the class loads
  with the raw CIR reproduces the reference at 6.1e-06.

Thresholds = measured medians × ~3 headroom. Skips cleanly without the
parquet store or the external UW reference CSVs.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

DATA_DIR = Path(__file__).resolve().parents[1] / "data"

pytestmark = pytest.mark.skipif(
    not (DATA_DIR / "srvc" / "bus_table.parquet").exists(),
    reason="parquet store not built — run scripts/migrate_data.py first",
)

SRVC_CODES = {"DL": 1, "DC": 2, "MY": 3, "NC": 4, "VG": 5, "WV": 6}


@pytest.fixture(scope="module")
def srvc_reference():
    from loadsmith.validation import Validator

    v = Validator()
    path = v.find_reference("SRVC", "P")
    if path is None:
        pytest.skip("SRVC P reference CSV not found (external UW folder)")
    bus, vals = v.load_reference(path)
    return bus, vals


@pytest.fixture(scope="module")
def srvc_production(srvc_reference):
    """Production run joined to the reference's bus order."""
    from loadsmith import LoadSmith
    from loadsmith.ingest import ParquetStore

    ref_bus, _ = srvc_reference
    res = LoadSmith(store=DATA_DIR).run("SRVC", formats=())
    assert res.validation_report["ok"]
    order = {int(b): i for i, b in enumerate(res.national_bus_numbers)}
    ri = np.array([order[int(b)] for b in ref_bus])   # KeyError = join failure
    codes = ParquetStore(DATA_DIR).bus_table("SRVC")["state_code"].to_numpy()[ri]
    return res.p_load[ri], codes


def _median_rel(mine, theirs, scale=1.0):
    rel = np.abs(mine * scale - theirs) / np.maximum(np.abs(theirs), 1e-6)
    return float(np.median(rel))


def test_srvc_reference_agreement_clean_states(srvc_reference, srvc_production):
    """DC/MY/VG at scale 1.0; DL/NC at their raw-CIR-sum scales."""
    from loadsmith.ingest import ParquetStore

    _, ref = srvc_reference
    mine, codes = srvc_production
    cir = ParquetStore(DATA_DIR).cir_fractions("SRVC").set_index("state")

    for abbrev in ("DC", "MY", "VG"):
        m = codes == SRVC_CODES[abbrev]
        assert _median_rel(mine[m], ref[m]) < 2e-5, abbrev
        # raw CIR rows for these states sum to 1.0 -> no scale ambiguity
        assert abs(cir.loc[abbrev].sum() - 1.0) < 1e-6, abbrev

    # DL: deviation is exactly the raw-CIR-sum renormalization
    m = codes == SRVC_CODES["DL"]
    scale = float(cir.loc["DL"].sum())            # 0.999639
    assert 0.9990 < scale < 0.9999
    assert _median_rel(mine[m], ref[m], scale) < 6e-5
    assert _median_rel(mine[m], ref[m]) < 1.5e-3  # even unscaled: tiny

    # NC: same, on finite columns (hour 17 is NaN in the reference)
    m = codes == SRVC_CODES["NC"]
    fin = np.setdiff1d(np.arange(8760), [16])
    scale = float(cir.loc["NC"].sum())            # 0.999378
    assert 0.9990 < scale < 0.9999
    assert _median_rel(mine[m][:, fin], ref[m][:, fin], scale) < 1.5e-4


def test_srvc_nc_nan_and_day1_zero_alpha(srvc_reference, srvc_production):
    """The NC whitelist: hour 17 NaN; ref day 1 = Sigma(raw shares) x raw load
    because MATLAB lsqnonneg returned x=0 on the NaN-poisoned day."""
    from loadsmith.ingest import ParquetStore

    ref_bus, ref = srvc_reference
    _, codes = srvc_production
    store = ParquetStore(DATA_DIR)

    nc = codes == SRVC_CODES["NC"]
    assert np.isnan(ref[nc][:, 16]).all()                  # hour 17, 1-based
    fin = np.setdiff1d(np.arange(8760), [16])
    assert np.isfinite(ref[nc][:, fin]).all()
    for abbrev in ("DL", "DC", "MY", "VG", "WV"):
        assert np.isfinite(ref[codes == SRVC_CODES[abbrev]]).all(), abbrev

    bus = store.bus_table("SRVC")
    m = (bus["state_code"] == SRVC_CODES["NC"]).to_numpy()
    cir = store.cir_fractions("SRVC").set_index("state").loc["NC"].to_numpy()
    w_raw = bus.loc[m, ["share_c", "share_i", "share_r"]].to_numpy() @ cir
    nat = bus.loc[m, "national_bus_num"].to_numpy()
    order = {int(b): i for i, b in enumerate(nat)}
    sel = np.array([order[int(b)] for b in ref_bus[nc]])
    pred = np.outer(w_raw[sel], store.state_load("SRVC", "NC")[:24])

    day1 = ref[nc][:, :24]
    fmask = np.isfinite(day1)
    rel = np.abs(pred[fmask] - day1[fmask]) / np.maximum(np.abs(day1[fmask]), 1e-6)
    assert np.median(rel) < 5e-5
    assert rel.max() < 5e-4


@pytest.fixture(scope="module")
def srvc_wv_rows(srvc_reference):
    """Reference rows + our WV fit ingredients, shared by both WV tests."""
    from loadsmith.basis import NRELAggregateBasis
    from loadsmith.fitting import fit_state
    from loadsmith.ingest import ParquetStore
    from loadsmith.profile_calendar import day_type_calendar
    from loadsmith.regions import REGISTRY

    ref_bus, ref = srvc_reference
    store = ParquetStore(DATA_DIR)
    bus = store.bus_table("SRVC")
    m = (bus["state_code"] == SRVC_CODES["WV"]).to_numpy()
    nat = bus.loc[m, "national_bus_num"].to_numpy()
    order = {int(b): i for i, b in enumerate(nat)}
    sel = [(order[int(b)], j) for j, b in enumerate(ref_bus) if int(b) in order]
    mi = np.array([s[0] for s in sel])
    rj = np.array([s[1] for s in sel])
    assert len(mi) == m.sum()                     # full WV join coverage

    wv_cfg = next(s for s in REGISTRY["SRVC"].states if s.abbrev == "WV")
    cir = store.cir_fractions("SRVC").set_index("state")
    basis = NRELAggregateBasis(
        store.nrel_profiles("SRVC", wv_cfg.nrel.city_folder), wv_cfg.nrel)
    fit = fit_state(store.state_load("SRVC", "WV"), basis,
                    day_type_calendar(2015)[:365], tuple(cir.loc["WV"]),
                    residual="proportional")
    shares = bus.loc[m, ["share_c", "share_i", "share_r"]].to_numpy()
    return ref[rj], mi, fit, shares, cir


def test_srvc_wv_b6_reproduction_matches(srvc_wv_rows):
    """With MY's CIR(3) fed to the WV residential trend term (bug B6), the
    reference is reproduced at solver precision."""
    from loadsmith.distribution import distribute

    ref_wv, mi, fit, shares, cir = srvc_wv_rows
    trend_hourly = np.repeat(fit.alphas[:, 0], 24)        # basis col 0 = ones
    cl = fit.class_loads.copy()
    cl[:, 2] += trend_hourly * (cir.loc["MY"].iloc[2] - cir.loc["WV"].iloc[2])
    p_bug = distribute(cl, shares)[mi]
    assert _median_rel(p_bug, ref_wv) < 2e-5


def test_srvc_wv_fixed_deviates(srvc_production, srvc_reference):
    """Guard the B6 verdict: the FIXED WV output must deviate substantially
    (if this fails, the reference was regenerated with B6 fixed — update
    the whitelist and the doc)."""
    _, ref = srvc_reference
    mine, codes = srvc_production
    m = codes == SRVC_CODES["WV"]
    assert _median_rel(mine[m], ref[m]) > 5e-2


def test_srvc_structural():
    from loadsmith import LoadSmith
    from loadsmith.ingest import ParquetStore

    res = LoadSmith(store=DATA_DIR).run("SRVC", formats=())
    assert res.validation_report["ok"]
    assert res.p_load.shape == (6340, 8760)
    assert res.national_bus_numbers.min() == 14061
    assert res.national_bus_numbers.max() == 20400
    store = ParquetStore(DATA_DIR)
    total = sum(store.state_load("SRVC", s).sum()
                for s in ("DL", "DC", "MY", "NC", "VG", "WV"))
    np.testing.assert_allclose(res.p_load.sum(), total, rtol=1e-9)


# --------------------------------------------------------------------------- #
# SRTV
# --------------------------------------------------------------------------- #

SRTV_CODES = {"AL": 1, "KY": 2, "MS": 3, "TN": 4}
# 0-based columns that are NaN in the reference (unrepaired .mat inputs)
SRTV_NAN_COLS = {"KY": (1586, 7297), "TN": (698,)}
# 0-based day indices whose reference values are lsqnonneg zero-alpha
# passthroughs (x=0 on a NaN-poisoned target)
SRTV_ZERO_ALPHA_DAYS = {"KY": (66, 304), "TN": (29,)}


def _day_cols(days):
    out = []
    for d in days:
        out.extend(range(d * 24, d * 24 + 24))
    return out


@pytest.fixture(scope="module")
def srtv_reference():
    from loadsmith.validation import Validator

    v = Validator()
    path = v.find_reference("SRTV", "P")
    if path is None:
        pytest.skip("SRTV P reference CSV not found (external UW folder)")
    return v.load_reference(path)


@pytest.fixture(scope="module")
def srtv_production(srtv_reference):
    from loadsmith import LoadSmith
    from loadsmith.ingest import ParquetStore

    ref_bus, _ = srtv_reference
    res = LoadSmith(store=DATA_DIR).run("SRTV", formats=())
    assert res.validation_report["ok"]
    order = {int(b): i for i, b in enumerate(res.national_bus_numbers)}
    ri = np.array([order[int(b)] for b in ref_bus])   # KeyError = join failure
    codes = ParquetStore(DATA_DIR).bus_table("SRTV")["state_code"].to_numpy()[ri]
    return res.p_load[ri], codes


def test_srtv_reference_agreement(srtv_reference, srtv_production):
    """All four states in FULL production mode (the AL dir-order permutation
    is the production config) at their raw-CIR-sum scales."""
    from loadsmith.ingest import ParquetStore

    _, ref = srtv_reference
    mine, codes = srtv_production
    cir = ParquetStore(DATA_DIR).cir_fractions("SRTV").set_index("state")

    for abbrev, code in SRTV_CODES.items():
        m = codes == code
        drop = list(SRTV_NAN_COLS.get(abbrev, ()))
        drop += _day_cols(SRTV_ZERO_ALPHA_DAYS.get(abbrev, ()))
        fin = np.setdiff1d(np.arange(8760), drop)
        scale = float(cir.loc[abbrev].sum())          # 1.0 except MS 0.999975
        assert 0.9999 < scale < 1.0 + 1e-6, abbrev
        rel = (np.abs(mine[m][:, fin] * scale - ref[m][:, fin])
               / np.maximum(np.abs(ref[m][:, fin]), 1e-6))
        assert np.median(rel) < 2e-5, f"{abbrev}: {np.median(rel):.3e}"
        assert (rel <= 1e-2).mean() > 0.999, abbrev


def test_srtv_al_canonical_reading_deviates(srtv_reference, srtv_production):
    """Guard the Birmingham dir-order verdict: fitting AL with the CANONICAL
    (case-insensitive) group reading must deviate badly. If this fails, the
    reference was regenerated with a case-insensitive enumeration — flip
    the AL groups in loadsmith/regions/srtv.py back and update SRTV.md."""
    from loadsmith.basis import NRELAggregateBasis
    from loadsmith.config import NRELBasisSpec
    from loadsmith.distribution import distribute
    from loadsmith.fitting import fit_state
    from loadsmith.ingest import ParquetStore
    from loadsmith.profile_calendar import day_type_calendar

    ref_bus, ref = srtv_reference
    _, codes = srtv_production
    store = ParquetStore(DATA_DIR)

    canonical = NRELBasisSpec(          # the script literals read canonically
        city_folder="NREL_Profiles/Birmingham",
        groups={
            1: ((12, 13, 14), 3), 2: ((3, 4, 11), 3), 3: ((8, 10), 2),
            4: ((7, 9), 2), 5: ((2,), 1), 6: ((5,), 1), 7: ((1, 6), 2),
            8: ((15,), 1), 9: ((16,), 1), 10: ((17,), 1),
        },
        fit_groups=(10, 5, 7),
    )
    cir = store.cir_fractions("SRTV").set_index("state")
    fit = fit_state(
        store.state_load("SRTV", "AL"),
        NRELAggregateBasis(
            store.nrel_profiles("SRTV", "NREL_Profiles/Birmingham"), canonical),
        day_type_calendar(2015)[:365], tuple(cir.loc["AL"]),
        residual="proportional")

    bus = store.bus_table("SRTV")
    m = (bus["state_code"] == SRTV_CODES["AL"]).to_numpy()
    p = distribute(fit.class_loads,
                   bus.loc[m, ["share_c", "share_i", "share_r"]].to_numpy())
    nat = bus.loc[m, "national_bus_num"].to_numpy()
    order = {int(b): i for i, b in enumerate(nat)}
    al_ref = codes == SRTV_CODES["AL"]
    sel = np.array([order[int(b)] for b in ref_bus[al_ref]])
    rel = np.abs(p[sel] - ref[al_ref]) / np.maximum(np.abs(ref[al_ref]), 1e-6)
    assert np.median(rel) > 1e-2, (
        "canonical AL reading now MATCHES the reference — dir-order verdict "
        "inverted; see test docstring")


def test_srtv_nan_whitelist_and_zero_alpha_days(srtv_reference, srtv_production):
    """NaN columns exactly as inventoried; the containing days reproduce the
    Sigma(raw shares) x raw-load passthrough."""
    from loadsmith.ingest import ParquetStore

    ref_bus, ref = srtv_reference
    _, codes = srtv_production
    store = ParquetStore(DATA_DIR)
    cir = store.cir_fractions("SRTV").set_index("state")
    bus = store.bus_table("SRTV")

    for abbrev, code in SRTV_CODES.items():
        m = codes == code
        nan_cols = np.where(~np.isfinite(ref[m]).all(axis=0))[0]
        assert tuple(nan_cols) == SRTV_NAN_COLS.get(abbrev, ()), abbrev

    for abbrev in ("KY", "TN"):
        code = SRTV_CODES[abbrev]
        m = codes == code
        mb = (bus["state_code"] == code).to_numpy()
        w_raw = (bus.loc[mb, ["share_c", "share_i", "share_r"]].to_numpy()
                 @ cir.loc[abbrev].to_numpy())
        nat = bus.loc[mb, "national_bus_num"].to_numpy()
        order = {int(b): i for i, b in enumerate(nat)}
        sel = np.array([order[int(b)] for b in ref_bus[m]])
        load = store.state_load("SRTV", abbrev)
        for d in SRTV_ZERO_ALPHA_DAYS[abbrev]:
            cols = np.arange(d * 24, d * 24 + 24)
            pred = np.outer(w_raw[sel], load[cols])
            day = ref[m][:, cols]
            fmask = np.isfinite(day)
            rel = (np.abs(pred[fmask] - day[fmask])
                   / np.maximum(np.abs(day[fmask]), 1e-6))
            assert np.median(rel) < 5e-5, (abbrev, d, float(np.median(rel)))


def test_srtv_structural():
    from loadsmith import LoadSmith

    res = LoadSmith(store=DATA_DIR).run("SRTV", formats=())
    assert res.validation_report["ok"]
    assert res.p_load.shape == (4451, 8760)


# --------------------------------------------------------------------------- #
# SRMV
# --------------------------------------------------------------------------- #

SRMV_CODES = {"AR": 1, "LO": 2, "MO": 3}


@pytest.fixture(scope="module")
def srmv_reference():
    from loadsmith.validation import Validator

    v = Validator()
    path = v.find_reference("SRMV", "P")
    if path is None:
        pytest.skip("SRMV P reference CSV not found (external UW folder)")
    return v.load_reference(path)


@pytest.fixture(scope="module")
def srmv_production(srmv_reference):
    from loadsmith import LoadSmith
    from loadsmith.ingest import ParquetStore

    ref_bus, _ = srmv_reference
    res = LoadSmith(store=DATA_DIR).run("SRMV", formats=())
    assert res.validation_report["ok"]
    assert res.p_load.shape == (3123, 8760)      # F1: SRMV half resolved
    order = {int(b): i for i, b in enumerate(res.national_bus_numbers)}
    ri = np.array([order[int(b)] for b in ref_bus])   # KeyError = join failure
    codes = ParquetStore(DATA_DIR).bus_table("SRMV")["state_code"].to_numpy()[ri]
    return res.p_load[ri], codes


def test_srmv_reference_agreement_ar_mo(srmv_reference, srmv_production):
    _, ref = srmv_reference
    mine, codes = srmv_production
    assert np.isfinite(ref).all()                # no NaN whitelists in SRMV
    for abbrev in ("AR", "MO"):
        m = codes == SRMV_CODES[abbrev]
        assert _median_rel(mine[m], ref[m]) < 2e-5, abbrev


def test_srmv_lo_raw_cir_reproduction(srmv_reference, srmv_production):
    """LO matches only when the raw workbook CIR (sum 0.902455) is fed
    through the MATLAB class-load formula; production (energy-conserving)
    runs ~10.8% above the reference by design."""
    from loadsmith.basis import NRELAggregateBasis
    from loadsmith.distribution import distribute
    from loadsmith.fitting import fit_state
    from loadsmith.ingest import ParquetStore
    from loadsmith.profile_calendar import day_type_calendar
    from loadsmith.regions import REGISTRY

    ref_bus, ref = srmv_reference
    mine, codes = srmv_production
    store = ParquetStore(DATA_DIR)

    m = codes == SRMV_CODES["LO"]
    # guard: the production deviation IS the documented ~10.8% energy gap
    assert 1.08 < mine[m].sum() / ref[m].sum() < 1.14
    assert _median_rel(mine[m], ref[m]) > 5e-2

    lo_cfg = next(s for s in REGISTRY["SRMV"].states if s.abbrev == "LO")
    raw = store.cir_fractions("SRMV").set_index("state").loc["LO"].to_numpy()
    sigma = raw.sum()
    assert 0.902 < sigma < 0.903                 # the workbook anomaly itself
    fit = fit_state(
        store.state_load("SRMV", "LO"),
        NRELAggregateBasis(
            store.nrel_profiles("SRMV", lo_cfg.nrel.city_folder), lo_cfg.nrel),
        day_type_calendar(2015)[:365], tuple(raw), residual="proportional")
    trend = np.repeat(fit.alphas[:, 0], 24)
    ml_cl = (fit.class_loads
             - (1.0 - sigma) * np.outer(trend + fit.residuals, raw / sigma))

    bus = store.bus_table("SRMV")
    mb = (bus["state_code"] == SRMV_CODES["LO"]).to_numpy()
    p_lo = distribute(
        ml_cl, bus.loc[mb, ["share_c", "share_i", "share_r"]].to_numpy())
    nat = bus.loc[mb, "national_bus_num"].to_numpy()
    order = {int(b): i for i, b in enumerate(nat)}
    sel = np.array([order[int(b)] for b in ref_bus[m]])
    assert _median_rel(p_lo[sel], ref[m]) < 2e-5
