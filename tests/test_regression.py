"""Regression vs MATLAB reference outputs + end-to-end pipeline tests.

Reference provenance (established empirically 2026-07-09): the
2024 P_Load_FRCC.csv was produced by the KCL-KVL *function* variant of
MakeLoadProfiles_FRCC, i.e.:

* NYSEG-basis per-class fits with the FL residual DROPPED (bug B3 typo —
  confirmed: FL='residential' pushes median rel. diff from 5.6e-4 to 4.7e-2),
  GA/SC residuals included;
* the ÷CIR ("renormalized", B12-fixed) bus distribution;
* a single global "loadscaling" factor ≈ 0.8814 (peak pinned to the bus
  table's col-16 total — not yet migrated, so tests FIT the scale rather
  than compute it; see HOOKS.md H5);
* no smoothing (B1), no Q, national bus numbers in column 1.

Agreement achieved with per-state fitted scaling: GA median 2.2e-05,
SC 6.7e-06, FL 5.6e-04 (FL uses slightly different raw data in the KCL-KVL
copy — different Florida.xls). The assertions below lock those levels in
with ~3x headroom.

Skips cleanly when the parquet store or the external reference CSV is absent.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

DATA_DIR = Path(__file__).resolve().parents[1] / "data"

pytestmark = pytest.mark.skipif(
    not (DATA_DIR / "frcc" / "bus_table.parquet").exists(),
    reason="parquet store not built — run scripts/migrate_data.py first",
)


@pytest.fixture(scope="module")
def frcc_reference():
    from loadsmith.validation import Validator

    v = Validator()
    path = v.find_reference("FRCC", "P")
    if path is None:
        pytest.skip("FRCC P reference CSV not found (external UW folder)")
    bus, vals = v.load_reference(path)
    return bus, vals


@pytest.fixture(scope="module")
def frcc_matlab_faithful():
    """Rebuild the reference generator's math: FL residual dropped (B3),
    GA/SC residential, renormalized (÷CIR-equivalent) shares, no smoothing."""
    from loadsmith.basis import NYSEGBasis
    from loadsmith.distribution import distribute
    from loadsmith.fitting import fit_state
    from loadsmith.ingest import ParquetStore
    from loadsmith.profile_calendar import day_type_calendar

    store = ParquetStore(DATA_DIR)
    cal = day_type_calendar(2015)[:365]
    basis = NYSEGBasis(store.nyseg_profiles())
    cir = store.cir_fractions("FRCC").set_index("state")
    bus = store.bus_table("FRCC")
    state_codes = bus["state_code"].to_numpy()
    policies = {"FL": "drop", "GA": "residential", "SC": "residential"}
    codes = {"FL": 1, "GA": 2, "SC": 3}

    p = np.zeros((len(bus), 8760))
    for abbrev, code in codes.items():
        fit = fit_state(
            store.state_load("FRCC", abbrev), basis, cal,
            tuple(cir.loc[abbrev]), residual=policies[abbrev])
        mask = state_codes == code
        shares = bus.loc[mask, ["share_c", "share_i", "share_r"]].to_numpy()
        p[mask] = distribute(fit.class_loads, shares)
    return bus["national_bus_num"].to_numpy(), state_codes, codes, p


def test_frcc_reference_agreement(frcc_reference, frcc_matlab_faithful):
    """Per-state, after fitting the reference's global loadscaling factor,
    LoadSmith reproduces the 2024 reference at solver precision (GA/SC) /
    input-data precision (FL)."""
    ref_bus, ref = frcc_reference
    nat, state_codes, codes, mine = frcc_matlab_faithful

    order = {int(b): i for i, b in enumerate(nat)}
    ri = np.array([order[int(b)] for b in ref_bus])
    mine = mine[ri]
    ref_codes = state_codes[ri]

    # thresholds: measured median x ~3 headroom
    limits = {"FL": 2e-3, "GA": 1e-4, "SC": 5e-5}
    scales = {}
    for abbrev, code in codes.items():
        m = ref_codes == code
        scale = ref[m].sum() / mine[m].sum()
        scales[abbrev] = scale
        rel = np.abs(mine[m] * scale - ref[m]) / np.maximum(np.abs(ref[m]), 1e-6)
        assert np.median(rel) < limits[abbrev], (
            f"{abbrev}: median rel diff {np.median(rel):.3e} > {limits[abbrev]}")
        assert (rel <= 1e-2).mean() > 0.99, (
            f"{abbrev}: only {(rel <= 1e-2).mean():.2%} of points within 1%")

    # the loadscaling factor is a single global constant (~0.8814): the three
    # per-state fitted scales must agree within ~0.5% (FL differs slightly
    # because the reference run used a different Florida.xls revision).
    vals = np.array(list(scales.values()))
    assert vals.min() > 0.85 and vals.max() < 0.92, scales
    assert (vals.max() - vals.min()) / vals.mean() < 0.006, scales


def test_frcc_wrong_fl_policy_degrades(frcc_reference):
    """Guard the B3 verdict: including the FL residual must WORSEN agreement
    dramatically (if this fails, the reference was regenerated with fixed
    MATLAB and the faithful-mode policies need updating)."""
    from loadsmith.basis import NYSEGBasis
    from loadsmith.distribution import distribute
    from loadsmith.fitting import fit_state
    from loadsmith.ingest import ParquetStore
    from loadsmith.profile_calendar import day_type_calendar

    ref_bus, ref = frcc_reference
    store = ParquetStore(DATA_DIR)
    bus = store.bus_table("FRCC")
    mask_fl = bus["state_code"].to_numpy() == 1
    fit = fit_state(
        store.state_load("FRCC", "FL"),
        NYSEGBasis(store.nyseg_profiles()),
        day_type_calendar(2015)[:365],
        tuple(store.cir_fractions("FRCC").set_index("state").loc["FL"]),
        residual="residential")
    p_fl = distribute(
        fit.class_loads,
        bus.loc[mask_fl, ["share_c", "share_i", "share_r"]].to_numpy())

    nat = bus["national_bus_num"].to_numpy()
    order = {int(b): i for i, b in enumerate(nat)}
    fl_rows_mine = {int(b): i for i, b in enumerate(nat[mask_fl])}
    sel = [(fl_rows_mine[int(b)], j) for j, b in enumerate(ref_bus)
           if int(b) in fl_rows_mine]
    mi = np.array([s[0] for s in sel]); rj = np.array([s[1] for s in sel])
    mine, theirs = p_fl[mi], ref[rj]
    scale = theirs.sum() / mine.sum()
    rel = np.abs(mine * scale - theirs) / np.maximum(np.abs(theirs), 1e-6)
    assert np.median(rel) > 1e-2, (
        "FL with residual INCLUDED now matches the reference — it was "
        "regenerated with the B3 typo fixed; update the faithful policies")


def test_end_to_end_run_structural():
    """Production-mode FRCC run passes every structural invariant."""
    from loadsmith import LoadSmith

    res = LoadSmith(store=DATA_DIR).run("FRCC", formats=())
    rep = res.validation_report
    failed = {k: v for k, v in rep["checks"].items() if v["ok"] is False}
    assert rep["ok"], f"structural failures: {failed}"
    assert res.p_load.shape == (7224, 8760)
    assert res.national_bus_numbers.min() == 28026
    assert res.national_bus_numbers.max() == 35249
    # energy conservation in production mode (renormalized, residential)
    store_total = sum(
        __import__("loadsmith.ingest", fromlist=["ParquetStore"])
        .ParquetStore(DATA_DIR).state_load("FRCC", s).sum()
        for s in ("FL", "GA", "SC"))
    np.testing.assert_allclose(res.p_load.sum(), store_total, rtol=1e-9)


def test_peak_scaling_kclkvl():
    """D16/H5: 'kclkvl' pins the coincident system peak to the sum of the
    per-state peak loads (bus col 16) with ONE global factor on P and Q."""
    from loadsmith import LoadSmith

    smith = LoadSmith(store=DATA_DIR)
    plain = smith.run("FRCC", formats=(), peak_scaling="none", validate=False)
    scaled = smith.run("FRCC", formats=(), peak_scaling="kclkvl")

    target = scaled.metadata["peak_target_mw"]
    assert target == 78763.0  # FL+GA+SC state peaks from the bus table
    np.testing.assert_allclose(scaled.p_load.sum(axis=0).max(), target, rtol=1e-12)

    factor = scaled.metadata["peak_scale_factor"]
    assert 0.85 < factor < 0.92
    np.testing.assert_allclose(scaled.p_load, plain.p_load * factor, rtol=1e-12)
    np.testing.assert_allclose(scaled.q_load, plain.q_load * factor, rtol=1e-12)
    assert scaled.validation_report["ok"]
    assert plain.metadata["peak_scale_factor"] == 1.0


def test_settings_file_drives_run(tmp_path):
    """A loadsmith.toml [regions.FRCC] override reaches the pipeline."""
    from loadsmith import LoadSmith

    f = tmp_path / "loadsmith.toml"
    f.write_text(
        '[run]\npeak_scaling = "none"\nvalidate = false\n\n'
        '[regions.FRCC]\npeak_scaling = "kclkvl"\n',
        encoding="utf-8",
    )
    res = LoadSmith(store=DATA_DIR, settings=f).run("FRCC", formats=())
    assert res.metadata["peak_scaling"] == "kclkvl"
    assert res.metadata["peak_scale_factor"] != 1.0


def test_run_result_in_memory_contracts():
    """RunResult accessors (D14): frames and KCL-KVL-shaped matrices."""
    from loadsmith import LoadSmith

    res = LoadSmith(store=DATA_DIR).run("FRCC", formats=(), validate=False)
    pm, qm = res.as_matrices()
    assert pm.shape == (7224, 8761) and qm.shape == (7224, 8761)
    np.testing.assert_array_equal(pm[:, 0], res.national_bus_numbers)
    df = res.p_frame()
    assert list(df.columns[:2]) == ["bus Num", "h0001"]
    assert df.shape == (7224, 8761)
    # reproducibility: same seed -> identical Q
    res2 = LoadSmith(store=DATA_DIR).run("FRCC", formats=(), validate=False)
    np.testing.assert_array_equal(res.q_load, res2.q_load)
