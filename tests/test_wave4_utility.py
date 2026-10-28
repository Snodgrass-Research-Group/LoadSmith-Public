"""Regression — CAISO and RFCW (utility archetype) vs UW references.

Verdicts established 2026-07-10:

* CAISO — TWO reference P variants:
  - P_Load_CAISO.csv (2021) = AUTHORITATIVE: matches production mode
    (renormalized ÷CIR, no loadscaling) at scale 1.0000, median 6.9e-04.
  - P_Load_CAISO_NEW.csv (2019) = the legacy raw-share output: its fitted
    scale 0.3669 equals Σ CIR_c² for CA (0.455² + 0.197² + 0.348²) — the
    B12 energy-deficit signature; per-bus shapes do NOT match any global
    rescale (median 5.5e-02). Kept as a negative control.
* RFCW — the reference embodies the MATLAB column mismap (B13: the
  commercial OPC shape sits in the residential slot, ind+res form the C/I
  pool) times a global loadscaling 0.8218: swapped-role rebuild matches at
  median 6e-06 (IN) / 8e-06 (MI) / 5.5e-05 (OH); the by-name (intent)
  variant diverges (~3e-02). Production stays by-name; MATLAB-faithful
  comparisons must swap roles as below.

Thresholds = measured medians x ~3 headroom. Skips cleanly without the
parquet store or the external UW reference CSVs.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

DATA_DIR = Path(__file__).resolve().parents[1] / "data"

pytestmark = pytest.mark.skipif(
    not (DATA_DIR / "caiso" / "bus_table.parquet").exists()
    or not (DATA_DIR / "rfcw" / "bus_table.parquet").exists(),
    reason="parquet store not built — run scripts/migrate_data.py "
           "--region CAISO / RFCW first",
)


def _reference(region: str, fname: str):
    from loadsmith import locations
    from loadsmith.validation import Validator

    path = locations.uw_load_dir() / region / fname
    if not path.exists():
        pytest.skip(f"{fname} not found (external UW folder)")
    return Validator.load_reference(path)


def _joined(res, ref_bus, ref_vals):
    order = {int(b): i for i, b in enumerate(res.national_bus_numbers)}
    ri = np.array([order[int(b)] for b in ref_bus if int(b) in order])
    rj = np.array([j for j, b in enumerate(ref_bus) if int(b) in order])
    return res.p_load[ri], ref_vals[rj], ri


def _stats(mine, theirs):
    scale = theirs.sum() / mine.sum()
    rel = np.abs(mine * scale - theirs) / np.maximum(np.abs(theirs), 1e-6)
    return scale, float(np.median(rel))


def test_caiso_authoritative_reference():
    from loadsmith import LoadSmith

    res = LoadSmith(store=DATA_DIR).run("CAISO", formats=())
    assert res.validation_report["ok"]
    assert res.p_load.shape == (8034, 8760)   # F2: exact bus count

    ref_bus, ref = _reference("CAISO", "P_Load_CAISO.csv")
    mine, theirs, _ = _joined(res, ref_bus, ref)
    assert len(mine) == 8034
    scale, median = _stats(mine, theirs)
    assert 0.999 < scale < 1.001
    assert median < 2e-3, f"median {median:.3e}"


def test_caiso_2019_variant_is_the_b12_raw_share_output():
    """Negative control: the _NEW file's energy equals Σ CIR² of the state
    total (raw-share deficit) and its shapes don't match production."""
    from loadsmith import LoadSmith

    res = LoadSmith(store=DATA_DIR).run("CAISO", formats=(), validate=False)
    ref_bus, ref = _reference("CAISO", "P_Load_CAISO_NEW.csv")
    mine, theirs, _ = _joined(res, ref_bus, ref)
    scale, median = _stats(mine, theirs)
    cir = (0.455, 0.197, 0.348)
    assert abs(scale - sum(f * f for f in cir)) < 0.005, scale
    assert median > 1e-2   # not a global-rescale match


def _rfcw_manual(role_map):
    from loadsmith.basis import UtilityBasis
    from loadsmith.distribution import distribute
    from loadsmith.fitting import fit_state
    from loadsmith.ingest import ParquetStore
    from loadsmith.profile_calendar import day_type_calendar

    store = ParquetStore(DATA_DIR)
    bus = store.bus_table("RFCW")
    sc = bus["state_code"].to_numpy()
    cal = day_type_calendar(2015)[:365]
    cir = store.cir_fractions("RFCW").set_index("state")
    profiles = {k: store.utility_profiles("RFCW", k)
                for k in ("opc_com", "opc_ind", "opc_res")}
    basis = UtilityBasis({r: profiles[k] for r, k in role_map.items()})
    p = np.zeros((len(bus), 8760))
    for abbrev, code in {"IN": 1, "MI": 2, "OH": 3}.items():
        fit = fit_state(store.state_load("RFCW", abbrev), basis, cal,
                        tuple(cir.loc[abbrev]), residual="residential")
        mask = sc == code
        p[mask] = distribute(
            fit.class_loads,
            bus.loc[mask, ["share_c", "share_i", "share_r"]].to_numpy())
    return bus["national_bus_num"].to_numpy(), sc, p


def test_rfcw_reference_matches_matlab_mismapped_roles():
    """B13: the reference was produced with the commercial shape in the
    residential slot (RFCW.md semantics warning, now proven) x a global
    loadscaling ≈ 0.8218."""
    from loadsmith.config import Role

    nat, sc, p = _rfcw_manual({Role.COMMERCIAL: "opc_ind",
                               Role.INDUSTRIAL: "opc_res",
                               Role.RESIDENTIAL: "opc_com"})
    ref_bus, ref = _reference("RFCW", "P_Load_RFCW.csv")
    order = {int(b): i for i, b in enumerate(nat)}
    ri = np.array([order[int(b)] for b in ref_bus])
    mine, theirs, codes = p[ri], ref, sc[ri]

    limits = {1: 5e-5, 2: 5e-5, 3: 2e-4}   # IN, MI, OH (measured x3)
    scales = []
    for code, limit in limits.items():
        m = codes == code
        scale, median = _stats(mine[m], theirs[m])
        scales.append(scale)
        assert median < limit, f"state {code}: median {median:.3e}"
    # one GLOBAL loadscaling factor (KCL-KVL lineage), ~0.8218
    assert max(scales) - min(scales) < 0.002
    assert 0.80 < scales[0] < 0.85


def test_rfcw_production_by_name_differs_from_legacy():
    """Production maps roles by name (the fix). If this ever MATCHES the
    reference, the reference was regenerated with corrected MATLAB and the
    faithful mode must be retired."""
    from loadsmith import LoadSmith

    res = LoadSmith(store=DATA_DIR).run("RFCW", formats=())
    assert res.validation_report["ok"]
    ref_bus, ref = _reference("RFCW", "P_Load_RFCW.csv")
    mine, theirs, _ = _joined(res, ref_bus, ref)
    _, median = _stats(mine, theirs)
    assert median > 1e-2, "reference now matches by-name roles — re-verdict!"


def test_rfcw_kclkvl_peak_scaling_uses_migrated_target():
    from loadsmith import LoadSmith

    res = LoadSmith(store=DATA_DIR).run("RFCW", formats=(),
                                        peak_scaling="kclkvl", validate=False)
    assert res.metadata["peak_target_mw"] == 70558.0
    np.testing.assert_allclose(res.p_load.sum(axis=0).max(), 70558.0, rtol=1e-12)
