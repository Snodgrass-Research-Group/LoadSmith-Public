"""Validate the migrated parquet store through the runtime ParquetStore.

These tests exercise ONLY the store built by ``scripts/migrate_data.py``
(shared inputs + every region) — never the raw Excel/.mat files. They
skip cleanly on machines where the one-time migration has not been run.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from loadsmith.ingest import ParquetStore

DATA_DIR = Path(__file__).resolve().parents[1] / "data"

if not (DATA_DIR / "shared" / "nyseg_profiles.parquet").exists():
    pytest.skip(
        "parquet store not built — run scripts/migrate_data.py first",
        allow_module_level=True,
    )

REGION_STATES = {
    "FRCC": ["FL", "GA", "SC"],
    "MISO": ["IL", "IA", "MN", "WI"],
    "SRVC": ["DL", "DC", "MY", "NC", "VG", "WV"],
}
NREL_CITIES = {
    "FRCC": ["Miami_Intl_AP", "Atlanta_AP", "Charleston"],
    "SRVC": ["Wilmington", "DC", "Baltimore", "Charlotte", "Richmond", "Charleston"],
}
EXPECTED_BUS_COUNTS = {"FRCC": 7224, "MISO": 6671, "SRVC": 6340}

REGION_STATE_PARAMS = [
    (region, state) for region, states in REGION_STATES.items() for state in states
]
REGION_CITY_PARAMS = [
    (region, city) for region, cities in NREL_CITIES.items() for city in cities
]


@pytest.fixture(scope="module")
def store() -> ParquetStore:
    return ParquetStore(DATA_DIR)


# ---- shared ---------------------------------------------------------------- #


def test_nyseg_shape_and_finite(store):
    arr = store.nyseg_profiles()
    assert arr.shape == (24, 36, 9)
    assert np.isfinite(arr).all()


def test_national_bus_map_regions(store):
    df = store.national_bus_map()
    expected = {"AZNM", "CAISO", "FRCC", "MISO", "NEISO", "NWPP", "NYISO",
                "RFCE", "RFCW", "SPP", "SRMV", "SRTV", "SRVC"}
    assert expected <= set(df["region"].unique())
    frcc = store.national_bus_map("FRCC")
    assert len(frcc) == 7440
    assert frcc["national_bus_num"].min() == 27810
    assert frcc["national_bus_num"].max() == 35249


# ---- state loads ------------------------------------------------------------ #


@pytest.mark.parametrize(("region", "state"), REGION_STATE_PARAMS)
def test_state_load_finite_positive(store, region, state):
    series = store.state_load(region, state)
    assert series.shape == (8760,)
    assert np.isfinite(series).all()
    assert (series > 0).all()


# ---- bus tables --------------------------------------------------------------- #


@pytest.mark.parametrize("region", sorted(REGION_STATES))
def test_bus_table_row_count(store, region):
    assert len(store.bus_table(region)) == EXPECTED_BUS_COUNTS[region]


@pytest.mark.parametrize("region", sorted(REGION_STATES))
def test_bus_shares_renormalized(store, region):
    """Each state's renormalized class column sums to exactly 1.0 (C4/F3)."""
    df = store.bus_table(region)
    sums = df.groupby("state_code")[["share_c", "share_i", "share_r"]].sum()
    assert len(sums) == len(REGION_STATES[region])
    assert np.allclose(sums.to_numpy(), 1.0, atol=1e-9)


@pytest.mark.parametrize("region", sorted(REGION_STATES))
def test_every_bus_has_unique_national_number(store, region):
    df = store.bus_table(region)
    assert df["national_bus_num"].notna().all()
    assert df["national_bus_num"].is_unique
    # bus xlsx col 1 IS the national number (verified layout finding)
    assert (df["national_bus_num"] == df["bus_number"]).all()


def test_frcc_national_numbers_in_block(store):
    df = store.bus_table("FRCC")
    assert df["national_bus_num"].between(27810, 35249).all()


# ---- CIR fractions ----------------------------------------------------------- #


@pytest.mark.parametrize("region", sorted(REGION_STATES))
def test_cir_rows_sum_to_one(store, region):
    df = store.cir_fractions(region)
    assert list(df["state"]) == REGION_STATES[region]
    fracs = df[["frac_c", "frac_i", "frac_r"]].to_numpy(float)
    assert (fracs >= 0).all()
    assert np.allclose(fracs.sum(axis=1), 1.0, atol=0.02)


# ---- NREL profiles ------------------------------------------------------------- #


@pytest.mark.parametrize(("region", "city"), REGION_CITY_PARAMS)
def test_nrel_profile_shapes(store, region, city):
    arr = store.nrel_profiles(region, city)
    assert arr.shape == (8760, 17)
    assert np.isfinite(arr).all()
    assert (arr >= 0).all()


@pytest.mark.parametrize(("region", "city"), REGION_CITY_PARAMS)
def test_nrel_tmy_column_x1000_scaled(store, region, city):
    """Raw TMY weather series are O(1)-O(10) kWh; after the x1000 scaling the
    stored column 17 must be orders of magnitude above that."""
    arr = store.nrel_profiles(region, city)
    tmy_mean = arr[:, 16].mean()
    assert 100.0 < tmy_mean < 1e8


def test_nrel_city_folder_prefix_accepted(store):
    """Config uses 'NREL_Profiles/<city>' — both forms must resolve."""
    a = store.nrel_profiles("FRCC", "NREL_Profiles/Miami_Intl_AP")
    b = store.nrel_profiles("FRCC", "Miami_Intl_AP")
    assert np.array_equal(a, b)


# ---- utility profiles ----------------------------------------------------------- #


def test_utility_profiles(store):
    """Regions without migrated utility data raise cleanly; NWPP (mixed
    archetype) carries PG&E a1/a10/e1 profiles, each (365, 24)."""
    if not (DATA_DIR / "nwpp" / "utility_profiles.parquet").exists():
        pytest.skip("NWPP utility profiles not migrated yet")
    arr = store.utility_profiles("NWPP", "a1")
    assert arr.shape == (365, 24)
    assert np.isfinite(arr).all() and float(arr.max()) > 0
    with pytest.raises((FileNotFoundError, KeyError)):
        store.utility_profiles("NEISO", "a1")   # NYSEG region: no utility data
