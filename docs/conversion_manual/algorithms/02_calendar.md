# Stage 2 — Day-Type Calendar (`profile_calendar.py`)

## What MATLAB does

Every main script hand-codes a 365-element `DayProfileMatch` vector mapping
each day-of-year to one of **36 day-types**: for month m (1..12), the types are
`3(m-1)+1` = weekday, `+2` = Saturday, `+3` = Sunday. Construction pattern:

```matlab
DayProfileMatch(mm+1:mm+nn) = 3(m-1)+1;      % default all days to weekday
DayProfileMatch(mm+SAT:7:mm+nn) = 3(m-1)+2;  % Saturdays, hand-picked offset
DayProfileMatch(mm+SUN:7:mm+nn) = 3(m-1)+3;  % Sundays, hand-picked offset
DayProfileMatch(<holiday>) = 3(m-1)+3;       % holidays forced to Sunday type
```

The hand-picked offsets correspond to the **2015 calendar** (verified: Jan 3 =
first Saturday; Feb 7, Apr 4 Saturdays; MLK = day 19, Memorial = 145, Labor =
250, Thanksgiving = 330–331, Christmas = 359). The `Holidays` vector
`[1 19 145 184 250 330 331 359]` is *defined but never read* — the overrides
are inlined per month. Identical (byte-for-byte) in all NYSEG/hybrid scripts.

Holidays treated as Sundays: New Year's Day, MLK Day, Memorial Day, July 4
(observed Jul 3 in 2015), Labor Day, Thanksgiving + day after, Christmas.

**Dead code warning:** the NREL-basis scripts (AZNM NWPP SPP SRMV SRTV SRVC
RFCE) also contain this block and compute `profile = DayProfileMatch(day)`,
but never use it — their basis is the same-day slice of full-year profiles.

## Python design (decision D10)

```python
def day_type_calendar(year: int) -> np.ndarray  # shape (365,) or (366,), int 1..36
```

- Use `datetime.date` weekday logic — no hand-coded offsets.
- US holidays computed internally (fixed rules: New Year, MLK 3rd-Mon-Jan,
  Memorial last-Mon-May, Independence Day *observed*, Labor 1st-Mon-Sep,
  Thanksgiving 4th-Thu-Nov **plus the following Friday**, Christmas). No
  external `holidays` package (evergreen rule) — these 8 rules are stable law.
- Holidays map to that month's Sunday type.
- Leap years: MATLAB uses a fixed 365-day year. For `year % 4 == 0`, LoadSmith
  processes 8784 h with Feb 29 mapped like Feb 28 (documented choice), or the
  input is truncated to 8760 — decide when a leap-year dataset first appears.

## Required unit test (flag F4)

`day_type_calendar(2015)` must equal the MATLAB vector exactly. Reconstruct
the MATLAB vector in the test from the per-month offsets table:

| Month | types | SAT offset | SUN offset | holiday days → Sunday |
|-------|-------|-----------|-----------|----------------------|
| Jan | 1/2/3 | 3 | 4 | 1, 19 |
| Feb | 4/5/6 | mm+7 | mm+1 | — |
| Mar | 7/8/9 | mm+7 | mm+1 | — |
| Apr | 10/11/12 | mm+4 | mm+5 | — |
| May | 13/14/15 | mm+2 | mm+3 | 145 |
| Jun | 16/17/18 | mm+6 | mm+7 | — |
| Jul | 19/20/21 | mm+4 | mm+5 | 184 |
| Aug | 22/23/24 | mm+1 | mm+2 | — |
| Sep | 25/26/27 | mm+5 | mm+6 | 250 |
| Oct | 28/29/30 | mm+3 | mm+4 | — |
| Nov | 31/32/33 | mm+7 | mm+8 | 330, 331 |
| Dec | 34/35/36 | mm+5 | mm+6 | 359 |

(`mm` = cumulative days before the month; offsets are `mm+o : 7 : mm+ndays`.)
Note Nov's Sunday anchor is `mm+8` (Nov 1 2015 was a Sunday; `mm+1` would also
have worked — the +8 skips it, but `:7:` still covers Nov 8,15,22,29; Nov 1
itself stays **weekday-typed** in MATLAB. Reproduce this faithfully: the
generalized generator will type Nov 1 2015 as Sunday, which is CORRECT but
differs from MATLAB. Test must assert this known single-day difference —
see MATLAB_BUGS.md F4.)
