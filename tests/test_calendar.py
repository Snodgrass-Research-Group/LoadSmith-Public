"""Calendar tests — the F4 contract.

Key test: day_type_calendar(2015) equals the MATLAB DayProfileMatch
EXCEPT day 305 (Nov 1 2015, a Sunday MATLAB typed as weekday — hand-coding
miss documented in algorithms/02_calendar.md).

Also covered: the 8 observed-holiday day numbers for 2015, structural
month/weekday consistency across several years, holiday-observation edge
cases (Saturday Jan 1 drop, Sat/Sun shifts for Jul 4 and Christmas), and
leap-year handling (366 entries, Feb 29 gets a February type).
"""

import datetime as dt

import numpy as np
import pytest

from loadsmith.profile_calendar import (
    day_type_calendar,
    matlab_2015_day_profile_match,
    us_holidays,
)

EXPECTED_2015_HOLIDAYS = [1, 19, 145, 184, 250, 330, 331, 359]


# --- F4 contract -------------------------------------------------------------


def test_f4_matches_matlab_2015_except_day_305():
    """Generalized calendar == MATLAB DayProfileMatch except Nov 1 2015."""
    py = day_type_calendar(2015)
    ml = matlab_2015_day_profile_match()
    assert py.shape == (365,)
    assert ml.shape == (365,)

    diff = np.flatnonzero(py != ml)
    assert diff.tolist() == [304], (
        f"expected the single known difference at day 305, got days "
        f"{(diff + 1).tolist()}"
    )
    # Day 305 = Nov 1 2015, a real Sunday: the MATLAB Sunday series anchored
    # at mm+8 skipped it (weekday type 31); the generalized version must type
    # it as November's Sunday (33).
    assert dt.date(2015, 11, 1).weekday() == 6  # sanity: it really is a Sunday
    assert ml[304] == 31
    assert py[304] == 33


def test_matlab_fixture_holiday_days_are_sunday_typed():
    """The reconstruction applies the inlined overrides to the right days."""
    ml = matlab_2015_day_profile_match()
    expected_types = {1: 3, 19: 3, 145: 15, 184: 21, 250: 27, 330: 33, 331: 33, 359: 36}
    for day, t in expected_types.items():
        assert ml[day - 1] == t


# --- holiday rules -----------------------------------------------------------


def test_us_holidays_2015():
    assert us_holidays(2015) == EXPECTED_2015_HOLIDAYS


@pytest.mark.parametrize(
    ("year", "day", "date", "reason"),
    [
        (2020, 185, dt.date(2020, 7, 3), "Jul 4 2020 was a Saturday -> observed Jul 3"),
        (2021, 358, dt.date(2021, 12, 24), "Dec 25 2021 was a Saturday -> observed Dec 24"),
        (2016, 361, dt.date(2016, 12, 26), "Dec 25 2016 was a Sunday -> observed Dec 26"),
        (2023, 2, dt.date(2023, 1, 2), "Jan 1 2023 was a Sunday -> observed Jan 2"),
    ],
)
def test_observed_holiday_shifts(year, day, date, reason):
    assert date.timetuple().tm_yday == day  # sanity on the expected day number
    assert day in us_holidays(year), reason


def test_saturday_new_year_is_dropped():
    """Jan 1 2022 (Saturday) observes Dec 31 2021 — not representable, dropped."""
    assert dt.date(2022, 1, 1).weekday() == 5  # sanity: it really is a Saturday
    hol = us_holidays(2022)
    assert len(hol) == 7
    assert 1 not in hol


def test_holidays_never_land_on_weekend_after_observation():
    """Post-shift holidays are always Mon-Fri, so Saturday typing is never
    disturbed: holidays only map days TO a Sunday type, never away from a
    real Saturday."""
    for year in (2015, 2016, 2020, 2021, 2022, 2023):
        jan1 = dt.date(year, 1, 1)
        for doy in us_holidays(year):
            d = jan1 + dt.timedelta(days=doy - 1)
            assert d.weekday() < 5, f"{d} ({year} day {doy}) falls on a weekend"


# --- structural properties ----------------------------------------------------


@pytest.mark.parametrize("year", [2015, 2016, 2020, 2023])
def test_structural_properties(year):
    """Every day carries its month's triple; weekend/holiday typing is exact."""
    types = day_type_calendar(year)
    jan1 = dt.date(year, 1, 1)
    n_days = (dt.date(year, 12, 31) - jan1).days + 1
    assert types.shape == (n_days,)

    holidays = set(us_holidays(year))
    for i in range(n_days):
        d = jan1 + dt.timedelta(days=i)
        base = 3 * (d.month - 1) + 1
        t = int(types[i])
        # month consistency: type belongs to the day's own month triple
        assert t in (base, base + 1, base + 2)
        if (i + 1) in holidays:
            # holidays get the month's Sunday type (observed dates are all
            # Mon-Fri, so this never collides with a real Saturday)
            assert t == base + 2
            assert t % 3 == 0
        elif d.weekday() == 5:  # real Saturday, never holiday-overridden
            assert t == base + 1
            assert t % 3 == 2
        elif d.weekday() == 6:  # real Sunday
            assert t == base + 2
            assert t % 3 == 0
        else:  # plain weekday
            assert t == base
            assert t % 3 == 1


# --- leap years ---------------------------------------------------------------


def test_leap_year_2016():
    types = day_type_calendar(2016)
    assert len(types) == 366
    feb29 = dt.date(2016, 2, 29).timetuple().tm_yday  # day 60
    t = int(types[feb29 - 1])
    assert t in (4, 5, 6)  # a February type
    assert t == 4  # Feb 29 2016 was a Monday -> February weekday type


def test_common_year_length():
    assert len(day_type_calendar(2015)) == 365
    assert len(day_type_calendar(2023)) == 365
