"""Settings-file tests (loadsmith.toml / loadsmith/settings.py, decision D16).

Covers: built-in defaults with no file, TOML parsing, [regions.<NAME>]
overrides, precedence (run() kwarg > region override > [run]), validation
of unknown keys and invalid values, and the shipped repo loadsmith.toml.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from loadsmith.settings import DEFAULT_SETTINGS_FILE, Settings, load_settings

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_defaults_without_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # no loadsmith.toml here
    s = load_settings()
    assert s == Settings()
    assert s.peak_scaling == "none"
    assert s.smoothing == "none"
    assert s.formats == ("csv", "parquet")


def test_explicit_missing_path_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_settings(tmp_path / "nope.toml")


def test_load_file_and_region_override(tmp_path):
    f = tmp_path / "loadsmith.toml"
    f.write_text(
        '[run]\n'
        'formats = ["parquet"]\n'
        'peak_scaling = "kclkvl"\n'
        'seed = 42\n'
        '\n'
        '[regions.frcc]\n'          # case-insensitive region key
        'peak_scaling = "none"\n'
        'smoothing = "qp"\n',
        encoding="utf-8",
    )
    s = load_settings(f)
    assert s.formats == ("parquet",)
    assert s.peak_scaling == "kclkvl"
    assert s.seed == 42
    # region override wins over [run]
    frcc = s.for_region("FRCC")
    assert frcc.peak_scaling == "none"
    assert frcc.smoothing == "qp"
    assert frcc.seed == 42            # inherited
    # other regions untouched
    assert s.for_region("MISO").peak_scaling == "kclkvl"


@pytest.mark.parametrize(
    "body, message",
    [
        ('[run]\npeak_scaling = "always"\n', "peak_scaling"),
        ('[run]\nsmoothing = "cubic"\n', "smoothing"),
        ('[run]\nformats = ["csv", "hdf5"]\n', "formats"),
        ('[run]\ntypo_key = 1\n', "unknown"),
        ('[regions.FRCC]\nnot_a_switch = true\n', "unknown"),
    ],
)
def test_invalid_settings_raise(tmp_path, body, message):
    f = tmp_path / "loadsmith.toml"
    f.write_text(body, encoding="utf-8")
    with pytest.raises(ValueError, match=message):
        s = load_settings(f)
        s.for_region("FRCC")  # region-override validation happens here


def test_shipped_repo_settings_file_is_valid():
    """The committed loadsmith.toml must always parse and use defaults we
    document: production = energy-conserving, no smoothing."""
    s = load_settings(REPO_ROOT / DEFAULT_SETTINGS_FILE)
    assert s.peak_scaling in ("none", "kclkvl")   # user-flippable switch
    assert s.smoothing == "none"
    assert s.shares == "renormalized"
    assert s.validate is True


def test_loadsmith_uses_settings_object():
    """LoadSmith resolves store/seed and run switches from a Settings object."""
    from loadsmith import LoadSmith

    s = Settings(seed=7, store="data", output_dir="outputs",
                 formats=(), validate=False)
    smith = LoadSmith(settings=s)
    assert smith.seed == 7
    assert smith.settings.formats == ()
