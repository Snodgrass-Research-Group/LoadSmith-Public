"""Regression — NEISO, NYISO, MISO vs their UW reference CSVs.

Verdicts established 2026-07-10, mirroring the FRCC methodology:
ALL THREE references are regenerated ÷CIR per-class outputs that match
LoadSmith production mode (shares=renormalized, smoothing=none,
peak_scaling=none) at scale ≈ 1.0 — none carries the legacy defects:

* MISO  (no bus column, row-order aligned): IL/WI median ≈ 7e-06 @ scale
  1.0000; IA/MN ≈ 3e-05 @ 0.99967 (combined-fit pair).
* NEISO (no bus column): all six states median ≈ 7e-06 @ 1.0000 — NOT the
  old total-broadcast file (rank-1 residual ≈ 0.15).
* NYISO (bus column present): median 1.25e-04 @ 0.9988 — the B9 rank-1
  signature is ABSENT (residual ≈ 0.13), i.e. the reference generator had
  the per-class fix.

Thresholds below = measured medians x ~3 headroom. Skips cleanly without
the parquet store or the external UW reference CSVs.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

DATA_DIR = Path(__file__).resolve().parents[1] / "data"

pytestmark = pytest.mark.skipif(
    not (DATA_DIR / "miso" / "bus_table.parquet").exists()
    or not (DATA_DIR / "neiso" / "bus_table.parquet").exists()
    or not (DATA_DIR / "nyiso" / "bus_table.parquet").exists(),
    reason="parquet store not built — run scripts/migrate_data.py first",
)


def _load_headerless_ref(region: str):
    """Reference CSV WITHOUT a bus-number column (MISO/NEISO, bug B8)."""
    from pyarrow import csv as pacsv

    from loadsmith import locations

    path = locations.uw_load_dir() / region / f"P_Load_{region}.csv"
    if not path.exists():
        pytest.skip(f"{region} reference CSV not found (external UW folder)")
    table = pacsv.read_csv(
        path, read_options=pacsv.ReadOptions(autogenerate_column_names=True))
    vals = np.column_stack([c.to_numpy() for c in table.columns]).astype(np.float64)
    assert vals.shape[1] == 8760, f"expected 8760 cols, got {vals.shape[1]}"
    return vals


def _production_run(region: str):
    from loadsmith import LoadSmith

    return LoadSmith(store=DATA_DIR).run(
        region, formats=(), smoothing="none", shares="renormalized",
        peak_scaling="none", validate=True)


def _per_state_stats(mine, theirs, state_mask):
    scale = theirs[state_mask].sum() / mine[state_mask].sum()
    rel = (np.abs(mine[state_mask] * scale - theirs[state_mask])
           / np.maximum(np.abs(theirs[state_mask]), 1e-6))
    return scale, float(np.median(rel))


def _rank1_residual(block: np.ndarray) -> float:
    """~0 iff every row is proportional to one series (the B9 signature)."""
    tot = block.sum(axis=0)
    w = block @ tot / (tot @ tot)
    return float(np.abs(block - np.outer(w, tot)).max() / block.max())


@pytest.mark.parametrize(
    ("region", "codes", "median_limits"),
    [
        ("MISO", {"IL": 1, "IA": 2, "MN": 3, "WI": 4},
         {"IL": 5e-5, "IA": 1e-4, "MN": 1e-4, "WI": 5e-5}),
        ("NEISO", {"CT": 1, "ME": 2, "MA": 3, "NH": 4, "RI": 5, "VT": 6},
         dict.fromkeys(("CT", "ME", "MA", "NH", "RI", "VT"), 5e-5)),
    ],
)
def test_headerless_reference_agreement(region, codes, median_limits):
    from loadsmith.ingest import ParquetStore

    ref = _load_headerless_ref(region)
    res = _production_run(region)
    assert res.validation_report["ok"]
    assert ref.shape[0] == res.p_load.shape[0]

    state_codes = ParquetStore(DATA_DIR).bus_table(region)["state_code"].to_numpy()
    for abbrev, code in codes.items():
        scale, median = _per_state_stats(res.p_load, ref, state_codes == code)
        assert 0.999 < scale < 1.001, f"{region} {abbrev}: scale {scale}"
        assert median < median_limits[abbrev], (
            f"{region} {abbrev}: median {median:.3e} > {median_limits[abbrev]}")


def test_neiso_reference_is_not_total_broadcast():
    """Guard the provenance verdict: a rank-1 (total-broadcast, B9-style)
    reference would make the agreement test above vacuous."""
    from loadsmith.ingest import ParquetStore

    ref = _load_headerless_ref("NEISO")
    state_codes = ParquetStore(DATA_DIR).bus_table("NEISO")["state_code"].to_numpy()
    assert _rank1_residual(ref[state_codes == 1]) > 0.02  # CT block


def test_nyiso_reference_agreement():
    from loadsmith.validation import Validator

    v = Validator()
    path = v.find_reference("NYISO", "P")
    if path is None:
        pytest.skip("NYISO reference CSV not found (external UW folder)")
    ref_bus, ref = v.load_reference(path)

    res = _production_run("NYISO")
    assert res.validation_report["ok"]
    order = {int(b): i for i, b in enumerate(res.national_bus_numbers)}
    ri = np.array([order[int(b)] for b in ref_bus])
    mine = res.p_load[ri]

    # The old B9 defect (every row proportional to the state total) is
    # ABSENT from the reference — it was regenerated per-class.
    assert _rank1_residual(ref) > 0.02

    scale = ref.sum() / mine.sum()
    rel = np.abs(mine * scale - ref) / np.maximum(np.abs(ref), 1e-6)
    assert 0.99 < scale < 1.01
    assert np.median(rel) < 5e-4, f"median {np.median(rel):.3e}"
    assert (rel <= 1e-2).mean() > 0.98
