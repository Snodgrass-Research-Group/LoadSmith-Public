# NWPP — Region Extraction (VALIDATED 2026-07-10)

> **Reference provenance (empirical):** `P_Load_NWPP.csv` is a ÷CIR,
> no-loadscaling output at **scale 1.0** (repo script or the identical
> KCL-KVL function variant — no loadscaling step in either). LoadSmith
> production matches **ID 6.0e-06 / MT 5.9e-06 / OR 6.2e-06 / WA 6.1e-06
> @ scale 1.0** (all raw CIR rows sum to 1.0; the e1 day-shift quirk is
> migrated faithfully — OR/WA match at solver precision). **WY matches
> (6.0e-06) only with the `ID_Res_top` bug reproduced** (Idaho's stale
> day-365 residential component tiled into every WY day); the FIXED
> production output deviates 4.9e-02 median on WY buses by design.
> ⚠ Like AZNM, the reference's **bus numbers are an older revision**
> (2,845/2,977 differ; a 198-bus block relocated) — **joined BY ROW
> ORDER**. ⚠ Production trips the `q_envelope` structural check by
> 0.73 MVAr (slack 0.5): WY's residential class goes negative on 138
> hours (min −302 MW) under the `residential` residual policy, so those
> buses' Q/P mix exits the PF band — known and documented. Locked in by tests/test_wave4_west2.py.

Canonical script: `NWPP/MakeLoadProfiles_NWPP.m` (524 lines). Config
re-verified line-by-line — zero discrepancies. **MIXED archetype** (unique
among the 13): NREL for ID/MT/WY, PG&E utility profiles for OR/WA.

## States & inputs

| # | State | code (col 5) | var | Basis |
|---|-------|--------------|-----|-------|
| 1 | Idaho | 1 | ID | NREL Boise (⚠ BOULDER CO buildings + Boise TMY) |
| 2 | Montana | 2 | MT | NREL Billings (⚠ HELENA MT buildings + Billings TMY) |
| 3 | Oregon | 3 | OR | PG&E 2000: a1 (com), a10 (ind), e1 (res) |
| 4 | Washington | 4 | WA | PG&E 2000: same |
| 5 | Wyoming | 5 | WY | NREL Cheyenne (⚠ HELENA MT buildings + Cheyenne TMY) |

## OR/WA utility basis (PG&E year-2000 class profiles)

- `com = csvread('a1-2000.csv',1); ind = csvread('a10-2000.csv',1);
  res = csvread('e1-2000.csv',1);` — per-day basis
  `[ones | com(day,:)' | ind(day,:)' | res(day,:)']`, demeaned+normalized,
  indexed by CALENDAR day (no day-type calendar).
- ⚠ **a1/a10 have a header row; e1-2000.csv does NOT** — so `csvread(f,1)`
  drops e1's first DATA day: the residential basis is **day-shifted by
  one** (2000 was also a leap year starting Saturday vs 2015 Thursday —
  day-of-week misalignment is inherent to the whole scheme). Migrated
  faithfully into `utility_profiles.parquet`; validated at 6e-06.

## The WY `ID_Res_top` bug (line 405; fixed in production)

`WY_load(:,3) = WY_Trend*WY_CIR(3) + ID_Res_top + WY_resid;` —
`ID_Res_top` is **Idaho's day-365** residential component (ID's loop
finished earlier), a constant 24-h vector tiled into every WY day.
`WY_Res_top` is computed on line 398 and never used. Same stale-variable
family as SPP bug #2. Faithful reconstruction:
`cl[:,2] += tile(ID_res_365) − WY_Res_top_hourly`.

## Residual policy

**`residential`** for all five states (`XX_resid` added whole to class 3 —
NOT the CIR-proportional split of the southern regions). Consequence: WY's
residential class goes negative on 138 hours (min −302 MW; poor fit hours
— Cheyenne basis uses Helena buildings). MATLAB had the same character
(unchecked). This is what trips the `q_envelope` structural check.

## Frozen aggregate groups (ID and MT share one table)

| Group | ID / MT | WY |
|---|---|---|
| 1 | [8] | [11] |
| 2 | [10] | [13 14 15]/3 |
| 3 | [13 14 15]/3 | [1 9]/2 |
| 4 | [1 9 11]/3 | [3] |
| 5 | [3] | [6] |
| 6 | [6] | [4 5 12]/3 |
| 7 | [4 5 12]/3 | [8 10]/2 |
| 8 | [2 7]/2 | [2 7]/2 |
| 9 | [16] | [16] |
| 10 | [17] | [17] |

Fit groups `[res com ind]`: ID=[10 2 5], MT=[10 2 5], WY=[10 4 6].

## CIR & buses

- CIR: `Atmp(1:6,28:30)`, rows 1:5 real (row 6 NaN pad). All raw sums 1.0.
- BusDist: col 1 = national bus number (current revision; **the reference's
  differ** — row-order join, cf. AZNM), col 5 state code, cols 24:26 ÷ CIR.
  **2,977 buses** (= smoothing bound 1:2977; the commented-out LoadDist
  still says 1:4451 — an SRTV copy-paste, dead).
- No .mat NaN repairs. Q computed AND written, old PF ranges, B2.
  Output `[BusNums | 2977×8760]`, no header.

## Porting notes

The KCL-KVL `Master Load Data/NWPP/` copy is the same code as a function
(csvwrite commented out) — **no loadscaling**, unlike FRCC/RFCW. Stale
headers; clustering unused.
