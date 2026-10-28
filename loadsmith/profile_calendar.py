"""Stage 2 — day-type calendar (replaces the hand-coded DayProfileMatch).

Maps each day of a year to one of 36 day-types: for month m (1..12),
``3*(m-1)+1`` = weekday, ``+2`` = Saturday, ``+3`` = Sunday-or-holiday.
Only NYSEG-basis regions consume this (the NREL scripts carried the same
block as dead code). Spec: docs/conversion_manual/algorithms/02_calendar.md.

The MATLAB hand-coding corresponds to calendar year 2015 and misses exactly
one day (Nov 1 2015, a Sunday typed as weekday) — the required unit test
(flag F4) asserts equality with the MATLAB vector EXCEPT that known day.

US holidays treated as Sundays (stable statutory rules, hand-coded per the
evergreen policy — no `holidays` package): New Year's Day, MLK Day
(3rd Mon Jan), Memorial Day (last Mon May), Independence Day (observed),
Labor Day (1st Mon Sep), Thanksgiving + following Friday, Christmas Day.

Observation-shift note: after federal observation shifting (Saturday -> the
preceding Friday, Sunday -> the following Monday) no holiday in the list ever
lands on a Saturday or Sunday, and none crosses a month boundary — except a
Saturday Jan 1, whose observed date (Dec 31 of the *prior* year) is not
representable in this year's calendar and is therefore dropped (the MATLAB
code, being 2015-only, never modeled that case; likewise a Dec 31 observing
the *next* year's New Year is not included).

Implementation status: IMPLEMENTED.
"""

from __future__ import annotations

import datetime as dt

import numpy as np

WEEKDAY, SATURDAY, SUNDAY = 0, 1, 2  # offsets within a month's day-type triple

# --- MATLAB 2015 fixture data (from the offset table in 02_calendar.md) ----

_MATLAB_2015_MONTH_LENGTHS = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)

# Per-month (SAT, SUN) series start offsets, 1-based within the month.
# MATLAB writes DayProfileMatch(mm+o : 7 : mm+ndays) with mm = cumulative
# days before the month. Note November's Sunday anchor is 8, not 1: the
# hand-coding skips Nov 1 2015 (a Sunday), leaving it weekday-typed — the
# single known error the F4 test pins down.
_MATLAB_2015_OFFSETS = (
    (3, 4),  # Jan
    (7, 1),  # Feb
    (7, 1),  # Mar
    (4, 5),  # Apr
    (2, 3),  # May
    (6, 7),  # Jun
    (4, 5),  # Jul
    (1, 2),  # Aug
    (5, 6),  # Sep
    (3, 4),  # Oct
    (7, 8),  # Nov
    (5, 6),  # Dec
)

# The hand-inlined per-month holiday overrides (identical to the `Holidays`
# vector MATLAB defines but never reads).
_MATLAB_2015_HOLIDAY_DAYS = (1, 19, 145, 184, 250, 330, 331, 359)


# --- date-rule helpers ------------------------------------------------------


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> dt.date:
    """Date of the ``n``-th (1-based) ``weekday`` (Mon=0..Sun=6) in a month."""
    first = dt.date(year, month, 1)
    offset = (weekday - first.weekday()) % 7
    return first + dt.timedelta(days=offset + 7 * (n - 1))


def _last_weekday(year: int, month: int, weekday: int) -> dt.date:
    """Date of the last ``weekday`` (Mon=0..Sun=6) in a month."""
    if month == 12:
        last = dt.date(year, 12, 31)
    else:
        last = dt.date(year, month + 1, 1) - dt.timedelta(days=1)
    return last - dt.timedelta(days=(last.weekday() - weekday) % 7)


def _observed(d: dt.date) -> dt.date:
    """Federal observation shift: Saturday -> Friday before, Sunday -> Monday after."""
    if d.weekday() == 5:  # Saturday
        return d - dt.timedelta(days=1)
    if d.weekday() == 6:  # Sunday
        return d + dt.timedelta(days=1)
    return d


def _day_of_year(d: dt.date) -> int:
    """1-based ordinal day of ``d`` within its own year."""
    return (d - dt.date(d.year, 1, 1)).days + 1


# --- public API -------------------------------------------------------------


def day_type_calendar(year: int) -> np.ndarray:
    """Return int array of day-types (1..36), one entry per day of ``year``.

    Length is 365 for common years, 366 for leap years (Feb 29 typed like the
    surrounding February days, by its real weekday). MATLAB used a fixed
    365-day year; regions with leap-year data decide truncation at ingestion.

    Each day gets its month's triple ``3*(m-1)+1`` (weekday), ``+2``
    (Saturday) or ``+3`` (Sunday) from its real :class:`datetime.date`
    weekday; the observed holidays from :func:`us_holidays` are then forced
    to their month's Sunday type.
    """
    jan1 = dt.date(year, 1, 1)
    n_days = (dt.date(year, 12, 31) - jan1).days + 1  # 365 or 366
    types = np.empty(n_days, dtype=np.int64)
    for i in range(n_days):
        d = jan1 + dt.timedelta(days=i)
        base = 3 * (d.month - 1) + 1
        if d.weekday() == 5:  # Saturday
            types[i] = base + SATURDAY
        elif d.weekday() == 6:  # Sunday
            types[i] = base + SUNDAY
        else:
            types[i] = base + WEEKDAY
    for doy in us_holidays(year):
        month = (jan1 + dt.timedelta(days=doy - 1)).month
        types[doy - 1] = 3 * (month - 1) + 1 + SUNDAY
    return types


def us_holidays(year: int) -> list[int]:
    """Day-of-year numbers (1-based) of the 8 holidays, observed dates.

    Rules (hand-coded per the evergreen policy — stable statutory law):

    * New Year's Day — Jan 1, observed. A Sunday Jan 1 is observed Monday
      Jan 2; a Saturday Jan 1 would be observed Friday Dec 31 of the *prior*
      year, which this year's calendar cannot represent, so the entry is
      dropped (the list then has 7 entries, e.g. 2022).
    * MLK Day — 3rd Monday of January.
    * Memorial Day — last Monday of May.
    * Independence Day — Jul 4, observed (Sat -> Jul 3, Sun -> Jul 5).
    * Labor Day — 1st Monday of September.
    * Thanksgiving — 4th Thursday of November, AND the following Friday.
    * Christmas Day — Dec 25, observed (Sat -> Dec 24, Sun -> Dec 26).

    After observation shifting no returned holiday falls on a Saturday or
    Sunday, and none crosses a month boundary. Result is sorted ascending.
    """
    dates: list[dt.date] = []
    new_year = _observed(dt.date(year, 1, 1))
    if new_year.year == year:  # Saturday Jan 1 observes in the prior year — drop
        dates.append(new_year)
    dates.append(_nth_weekday(year, 1, 0, 3))  # MLK: 3rd Monday of January
    dates.append(_last_weekday(year, 5, 0))  # Memorial: last Monday of May
    dates.append(_observed(dt.date(year, 7, 4)))  # Independence Day, observed
    dates.append(_nth_weekday(year, 9, 0, 1))  # Labor: 1st Monday of September
    thanksgiving = _nth_weekday(year, 11, 3, 4)  # 4th Thursday of November
    dates.append(thanksgiving)
    dates.append(thanksgiving + dt.timedelta(days=1))  # the following Friday
    dates.append(_observed(dt.date(year, 12, 25)))  # Christmas, observed
    return sorted(_day_of_year(d) for d in dates)


def matlab_2015_day_profile_match() -> np.ndarray:
    """The verbatim MATLAB DayProfileMatch vector (test fixture for F4).

    Reconstructed from the per-month offset table in algorithms/02_calendar.md
    rather than stored as 365 literals, so the reconstruction itself is
    reviewable: each month defaults to its weekday type, the Saturday/Sunday
    series start at the hand-picked 1-based offsets and step by 7 up to the
    month's end, then the eight inlined holiday days are forced to their
    month's Sunday type.
    """
    out = np.empty(365, dtype=np.int64)
    mm = 0  # cumulative days before the current month
    for m0, (nn, (sat, sun)) in enumerate(
        zip(_MATLAB_2015_MONTH_LENGTHS, _MATLAB_2015_OFFSETS)
    ):
        base = 3 * m0 + 1
        out[mm : mm + nn] = base  # default: weekday
        out[mm + sat - 1 : mm + nn : 7] = base + 1  # Saturdays
        out[mm + sun - 1 : mm + nn : 7] = base + 2  # Sundays
        mm += nn
    month_ends = np.cumsum(_MATLAB_2015_MONTH_LENGTHS)
    for day in _MATLAB_2015_HOLIDAY_DAYS:
        m0 = int(np.searchsorted(month_ends, day))  # 0-based month of `day`
        out[day - 1] = 3 * m0 + 3  # forced to the month's Sunday type
    return out
