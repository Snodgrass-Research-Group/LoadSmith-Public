"""Output-writer tests.

Covers: (1) csv+parquet roundtrip with intact values/bus numbers and the
parquet regional_bus_num column; (2) csv_header=False (MATLAB csvwrite
compatibility); (3) formats=() writes nothing; (4) parquet-only runs;
(5) run_metadata.json contents; (6) to_output_frame layout/dtypes;
plus writer argument validation.
"""

import json
from datetime import datetime

import numpy as np
import pandas as pd
import pytest

import loadsmith
from loadsmith.outputs import HOURS_PER_YEAR, OutputWriter, to_output_frame

N_BUS = 5


@pytest.fixture()
def sample():
    rng = np.random.default_rng(42)
    national = np.arange(27810, 27810 + N_BUS)      # FRCC national block
    regional = np.arange(1, N_BUS + 1)
    p = rng.uniform(0.0, 250.0, size=(N_BUS, HOURS_PER_YEAR))
    q = rng.uniform(0.0, 80.0, size=(N_BUS, HOURS_PER_YEAR))
    meta = {"seed": 20260708, "smoothing": "qp", "residual": "residential"}
    return national, regional, p, q, meta


# ---------------------------------------------------------------------------
# 1. Roundtrip: csv + parquet
# ---------------------------------------------------------------------------


def test_roundtrip_csv_and_parquet(tmp_path, sample):
    national, regional, p, q, meta = sample
    writer = OutputWriter(tmp_path, formats=("csv", "parquet"))
    written = writer.write_region("FRCC", national, regional, p, q, meta)

    assert set(written) == {"p_csv", "q_csv", "p_parquet", "q_parquet",
                            "metadata"}
    region_dir = tmp_path / "FRCC"
    assert written["p_csv"] == region_dir / "P_Load_FRCC.csv"
    assert written["q_parquet"] == region_dir / "Q_Load_FRCC.parquet"
    for path in written.values():
        assert path.is_file()

    # CSV roundtrip (text roundtrip => allclose at float-repr precision).
    p_csv = pd.read_csv(written["p_csv"])
    assert p_csv.shape == (N_BUS, HOURS_PER_YEAR + 1)
    assert p_csv.columns[0] == "bus Num"
    assert p_csv.columns[1] == "h0001"
    assert p_csv.columns[-1] == "h8760"
    np.testing.assert_array_equal(p_csv["bus Num"].to_numpy(), national)
    np.testing.assert_allclose(p_csv.iloc[:, 1:].to_numpy(), p, rtol=1e-12)

    q_csv = pd.read_csv(written["q_csv"])
    np.testing.assert_array_equal(q_csv["bus Num"].to_numpy(), national)
    np.testing.assert_allclose(q_csv.iloc[:, 1:].to_numpy(), q, rtol=1e-12)

    # Parquet roundtrip is exact and carries regional_bus_num (column 2).
    p_pq = pd.read_parquet(written["p_parquet"])
    assert list(p_pq.columns[:3]) == ["bus Num", "regional_bus_num", "h0001"]
    np.testing.assert_array_equal(p_pq["bus Num"].to_numpy(), national)
    np.testing.assert_array_equal(
        p_pq["regional_bus_num"].to_numpy(), regional)
    np.testing.assert_array_equal(p_pq.iloc[:, 2:].to_numpy(), p)

    q_pq = pd.read_parquet(written["q_parquet"])
    np.testing.assert_array_equal(
        q_pq["regional_bus_num"].to_numpy(), regional)
    np.testing.assert_array_equal(q_pq.iloc[:, 2:].to_numpy(), q)


# ---------------------------------------------------------------------------
# 2. csv_header=False (MATLAB csvwrite compatibility)
# ---------------------------------------------------------------------------


def test_csv_no_header_matches_csvwrite(tmp_path, sample):
    national, regional, p, q, meta = sample
    writer = OutputWriter(tmp_path, formats=("csv",), csv_header=False)
    written = writer.write_region("FRCC", national, regional, p, q, meta)

    lines = written["p_csv"].read_text().splitlines()
    assert len(lines) == N_BUS                       # no header row
    assert lines[0].startswith(f"{national[0]},")    # bus number first column

    frame = pd.read_csv(written["p_csv"], header=None)
    assert frame.shape == (N_BUS, HOURS_PER_YEAR + 1)
    np.testing.assert_array_equal(frame.iloc[:, 0].to_numpy(), national)
    np.testing.assert_allclose(frame.iloc[:, 1:].to_numpy(), p, rtol=1e-12)


# ---------------------------------------------------------------------------
# 3. formats=() -> write nothing at all
# ---------------------------------------------------------------------------


def test_no_formats_writes_nothing(tmp_path, sample):
    national, regional, p, q, meta = sample
    out_dir = tmp_path / "outputs"
    writer = OutputWriter(out_dir, formats=())
    result = writer.write_region("FRCC", national, regional, p, q, meta)
    assert result == {}
    assert not out_dir.exists()          # no directory, no metadata file
    assert list(tmp_path.iterdir()) == []


# ---------------------------------------------------------------------------
# 4. Single-format runs
# ---------------------------------------------------------------------------


def test_parquet_only_writes_no_csv(tmp_path, sample):
    national, regional, p, q, meta = sample
    writer = OutputWriter(tmp_path, formats=("parquet",))
    written = writer.write_region("FRCC", national, regional, p, q, meta)
    assert set(written) == {"p_parquet", "q_parquet", "metadata"}
    region_dir = tmp_path / "FRCC"
    assert (region_dir / "P_Load_FRCC.parquet").is_file()
    assert (region_dir / "Q_Load_FRCC.parquet").is_file()
    assert list(region_dir.glob("*.csv")) == []


def test_csv_only_writes_no_parquet(tmp_path, sample):
    national, regional, p, q, meta = sample
    writer = OutputWriter(tmp_path, formats=("csv",))
    written = writer.write_region("FRCC", national, regional, p, q, meta)
    assert set(written) == {"p_csv", "q_csv", "metadata"}
    assert list((tmp_path / "FRCC").glob("*.parquet")) == []


# ---------------------------------------------------------------------------
# 5. run_metadata.json
# ---------------------------------------------------------------------------


def test_metadata_json_contents(tmp_path, sample):
    national, regional, p, q, meta = sample
    writer = OutputWriter(tmp_path, formats=("csv", "parquet"))
    written = writer.write_region("FRCC", national, regional, p, q, meta)

    meta_path = written["metadata"]
    assert meta_path == tmp_path / "FRCC" / "run_metadata.json"
    data = json.loads(meta_path.read_text(encoding="utf-8"))

    for key, value in meta.items():      # caller's dict passed through
        assert data[key] == value
    assert data["loadsmith_version"] == loadsmith.__version__
    datetime.fromisoformat(data["written_at"])   # ISO-parseable timestamp
    assert data["written_files"] == {
        "p_csv": "P_Load_FRCC.csv",
        "q_csv": "Q_Load_FRCC.csv",
        "p_parquet": "P_Load_FRCC.parquet",
        "q_parquet": "Q_Load_FRCC.parquet",
    }
    assert meta == {"seed": 20260708, "smoothing": "qp",
                    "residual": "residential"}   # input dict not mutated


# ---------------------------------------------------------------------------
# 6. to_output_frame layout
# ---------------------------------------------------------------------------


def test_to_output_frame_layout():
    n = 4
    national = np.array([10, 20, 30, 40])
    vals = np.arange(n * HOURS_PER_YEAR, dtype=np.float64).reshape(
        n, HOURS_PER_YEAR)
    frame = to_output_frame(national, vals)

    assert frame.shape == (n, HOURS_PER_YEAR + 1)
    expected_cols = ["bus Num"] + [f"h{h:04d}"
                                   for h in range(1, HOURS_PER_YEAR + 1)]
    assert list(frame.columns) == expected_cols
    assert frame["bus Num"].dtype == np.int64
    assert (frame.dtypes.iloc[1:] == np.float64).all()
    np.testing.assert_array_equal(frame["bus Num"].to_numpy(), national)
    np.testing.assert_array_equal(frame.iloc[:, 1:].to_numpy(), vals)


def test_to_output_frame_validation():
    vals = np.zeros((3, 10))
    with pytest.raises(ValueError):
        to_output_frame(np.array([1, 2]), vals)          # length mismatch
    with pytest.raises(ValueError):
        to_output_frame(np.array([1.5, 2.5, 3.5]), vals)  # non-integer buses
    with pytest.raises(ValueError):
        to_output_frame(np.array([[1, 2, 3]]), vals)     # not 1-D
    with pytest.raises(ValueError):
        to_output_frame(np.array([1, 2, 3]), vals.ravel())  # values not 2-D


# ---------------------------------------------------------------------------
# Writer argument validation
# ---------------------------------------------------------------------------


def test_writer_rejects_unknown_format(tmp_path):
    with pytest.raises(ValueError):
        OutputWriter(tmp_path, formats=("csv", "xml"))


def test_write_region_validation(tmp_path, sample):
    national, regional, p, q, meta = sample
    writer = OutputWriter(tmp_path, formats=("csv",))
    with pytest.raises(ValueError):
        writer.write_region("", national, regional, p, q, meta)
    with pytest.raises(ValueError):
        writer.write_region("   ", national, regional, p, q, meta)
    with pytest.raises(ValueError):
        writer.write_region("FRCC", national[:-1], regional, p, q, meta)
    with pytest.raises(ValueError):
        writer.write_region("FRCC", national, regional[:-1], p, q, meta)
    with pytest.raises(ValueError):
        writer.write_region("FRCC", national, regional,
                            p[:, :100], q[:, :100], meta)   # not 8760 hours
    with pytest.raises(ValueError):
        writer.write_region("FRCC", national, regional, p, q[:-1], meta)
    assert list(tmp_path.iterdir()) == []   # nothing written on failure
