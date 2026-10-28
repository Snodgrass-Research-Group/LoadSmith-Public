# FRCC — Region Extraction (PILOT — VALIDATED 2026-07-09)

> **Reference provenance (empirical):** the 2024 `P_Load_FRCC.csv` was made
> by the KCL-KVL **function** variant (`Master Load Data/FRCC/`): ÷CIR
> distribution (B12 fixed) × global `loadscaling` ≈ 0.8814 (peak pinned to
> bus col-16 total, hook H5) with the FL residual dropped (B3 — FL only).
> LoadSmith renormalized mode matches at median rel. diff GA 2.2e-05,
> SC 6.7e-06, FL 5.6e-04 (KCL-KVL copy uses a different Florida.xls
> revision). Locked in by tests/test_regression.py.

Canonical script: `FRCC/MakeLoadProfiles_FRCC_NEW.m` (966 lines). Fully read.
Archetype: **hybrid** — NYSEG fit drives the output; a parallel
NREL fit exists for comparison only (B4).

## States & inputs

| State | code (BusDist col 5) | load .mat | raw xls | NREL city folder |
|-------|---------------------|-----------|---------|------------------|
| FL | 1 | Florida.mat (`FL`, 1×8760) | Florida.xls | Miami_Intl_AP |
| GA | 2 | Georgia.mat (`GA`) | GA_Hourly_Load.xls | Atlanta_AP |
| SC | 3 | SouthCarolina.mat (`SC`) | SC_Houly_Load.xls (sic) | Charleston |

⚠ The Charleston folder's 16 building CSVs are **Atlanta files** (names end
`..._3A_USA_GA_ATLANTA.csv`); only the TMY2 weather file is Charleston
(`USA_SC_Charleston.722080_TMY2.csv`). SC building shapes = Atlanta's.

## Output-driving fit (NYSEG)

- Basis: `[ones | profiles_aggregate(:, daytype, 2) | (:,:,3) | (:,:,5)]`,
  cols 2–4 demeaned+normalized. Calendar: standard 2015 mapping (02_calendar.md).
- Class split: standard (04_daily_fit.md) with **B3**: `; +` typo drops the
  residual from the residential class → classes sum ≠ state load. MATLAB-
  faithful mode: `residual="drop"`.
- CIR fractions: `FRCC bus data.xlsx` sheet 1, numeric rows 1:3, **cols 27:29**
  (FL/GA/SC × C/I/R). (Other regions use 28:30 — per-region config.)

## Comparison-only NREL fit (do not port to production path)

17 profiles per city (explicit csvread, no glob), TMY ×1000; clusterdata(R,9)
per city (results unused); frozen aggregate groups (1-based building indices,
`/n` = divide by n):

| Group | FL (Miami) | GA (Atlanta) | SC (Charleston) |
|---|---|---|---|
| 1 | [5] | [12] | [8] |
| 2 | [4 10 13 14 15]/5 | [4 5 13 14 15]/5 | [10] |
| 3 | [8] | [8] | [12] |
| 4 | [12] | [10] | [4 5 12 14 15]/5 ⚠ |
| 5 | [1 9 11]/3 | [1 9 11]/3 | [1 9]/2 |
| 6 | [16] | [3] | [3] |
| 7 | [2 7]/2 | [6] | [6] |
| 8 | [6] | [16] | [16] |
| 9 | [3]/2 ⚠ | [2 7]/2 | [2 7]/2 |
| 10 | [17] | [17] | [17] |

⚠ FL#9 divides a singleton by 2 (like SRVC B7 — harmless after normalization).
⚠ SC#4 contains **12** where GA has 13 — likely typo (12 already = SC#3);
inert in practice (groups feed a comparison fit), but keep verbatim in the
frozen config with a comment.
NREL fit basis groups: `[10 2 7]` (res, com-mix, hospital) for all 3 states.

## Bus distribution

- `BusDist = xlsread('FRCC bus data.xlsx',1)`; **col 1 = 'Final National Bus
  Num'** (the MATLAB BusNums were national all along — migration finding
  2026-07-09), col 2 = regional bus number (gen+load numbering: 216 gen
  buses, loads start at regional 217 → national 28026, matching the 2024
  reference CSV); col 5 = state code; col 15 = bus total load (dead
  `LoadDist` only); **cols 24:26 = C/I/R bus shares** — raw columns sum per
  state to the CIR fraction (F3 convention #2 ⇒ MATLAB FRCC_NEW
  under-delivers energy, bug B12; LoadSmith renormalizes); 7,224 buses.
- Data repair at migration: `Florida.xls` hour 1707 (day 72, hour 3) is an
  empty cell (NaN in Florida.mat too) — linearly interpolated (14455.5).
- P: per-class outer products (raw shares × NYSEG-fit class loads).
- Power factors: randomized (superseded by D3); **Q commented out**; qf bug B2.
- Output: `P_Load_FRCC.csv` = [BusNums | 7224×8760], no header.

## Building-type index legend (1-based, all NREL folders)

1 FullServiceRestaurant, 2 Hospital, 3 LargeHotel, 4 LargeOffice,
5 MediumOffice, 6 MidriseApartment, 7 OutPatient, 8 PrimarySchool,
9 QuickServiceRestaurant, 10 SecondarySchool, 11 SmallHotel, 12 SmallOffice,
13 Stand-aloneRetail, 14 StripMall, 15 SuperMarket, 16 Warehouse,
17 TMY2 weather series (×1000).
