# CAISO — Region Extraction (VALIDATED 2026-07-10)

> **Converted.** F2 resolved: the tracts workbook is exactly 8,034 buses;
> its layout is the national-map column order (regional bus = col 3, State
> Peak Load = col 18, peak target 47,257 MW) — spec overrides handle it.
> **Reference verdicts:** `P_Load_CAISO.csv` (2021) is authoritative —
> matches production mode at scale 1.0000, median 6.9e-04.
> `P_Load_CAISO_NEW.csv` (2019) is the legacy raw-share output (fitted
> scale 0.3669 = Σ CIR² — the B12 deficit signature); kept as a negative
> control in tests/test_wave4_utility.py.

Canonical script: `CAISO/MakeLoadProfiles_CAISO_NEW.m` (207 lines). Fully
analyzed from the MATLAB source. Archetype: **utility** — PG&E rate-schedule
daily profiles are the fit basis. Simplest region: one state, no clustering.

## Inputs

- `California.mat` → `CA` (8760).
- Basis CSVs (`csvread(f, 1)`, 365×24 day-by-hour):
  - `a1-2000.csv` — PG&E rate A-1, small commercial → basis col 2
  - `a10-2000.csv` — PG&E rate A-10, medium/industrial → basis col 3
  - `e1-2000.csv` — PG&E rate E-1, residential → **basis col 4**
- `SEC_com/ind/res.csv` (Southern California Edison, 365×24 via
  `csvread(f,1,2,[1,2,365,25])`) — **commented out**, keep as alternate basis
  in config (disabled).
- `NYSEGloadprofiles2016.mat` loaded but **unused** (dead pedigree code).
- Bus table: `California bus tracts with load apportionemnts.xlsx` (sic).

## Fit

Basis `[ones | com(day,:) | ind(day,:) | res(day,:)]`; residential = col 4
(role mapping differs from NYSEG archetype — config maps by name).
Residual → residential (standard). Calendar computed but only relevant to
the dead NYSEG basis line.

- CIR: **hard-coded** `CA_CIR = [0.455 0.197 0.348]` (comment: EIA data).
- Distribution: per-class, raw shares, **cols 26:28**; state-code **col 6**
  (CA=1); `LoadDist` uses col 17 (dead). Bus count: smoothing loop `1:8034`
  is a magic number — **verify against xlsx rows (flag F2)**.
- Q: commented out (and its commented code references cols 24:26 —
  inconsistent with P's 26:28; use 26:28 when implementing D3 Q).
- Output: `P_Load_CAISO.csv` (bus# prepended).
