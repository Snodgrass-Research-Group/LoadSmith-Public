# SRVC — Region Extraction (VALIDATED 2026-07-10)

> **Reference provenance (empirical):** `P_Load_SRVC.csv` was made by the
> **repo script itself** (÷CIR distribution, **no** loadscaling, scale 1.0)
> with the **B6 bug present** and the **unrepaired** `NorthCarolina.mat`.
> LoadSmith production mode matches at median rel. diff **DC 6.8e-06 /
> MY 5.8e-06 / VG 5.7e-06 @ scale 1.0**; **DL 1.8e-05 @ 0.999639** and
> **NC 4.6e-05 @ 0.999378** — those two scales are exactly each state's
> raw-CIR row sum (LoadSmith renormalizes CIR to Σ=1; the other four states'
> raw rows sum to 1.0). **WV matches (5.5e-06) only with B6 reproduced**
> (MY's CIR(3) in the residential trend term); the B6-FIXED production
> output deviates 14% median on WV buses — intentional. NC whitelist:
> reference hour 17 is NaN (all NC buses), and reference **day 1 is the
> zero-alpha passthrough** — MATLAB `lsqnonneg` returns x=0 when the target
> contains NaN (NaN comparisons are false), so ref day 1 = Σ(raw shares)
> × raw NC load, reproduced at median 6.6e-06. Locked in by
> tests/test_wave4_south.py. Config re-verified line-by-line against the
> MATLAB source (fit groups, frozen groups incl. B7, CIR 1:6/28:30,
> proportional residuals, ÷CIR, 6,340 buses) — zero discrepancies; the
> line-311 comment "profiles 4 and 6 for VA" is wrong (code uses [10 2 6]).

Canonical script: `SRVC/MakeLoadProfiles_SRVC.m` (933 lines). Fully analyzed
from the MATLAB source. Archetype: **NREL** — per-day fit against the same
day's slice of full-year NREL aggregates; NYSEG load line commented out;
calendar block present but DEAD.

## States & inputs

| # | State | code (col 5) | var | NREL city folder |
|---|-------|--------------|-----|------------------|
| 1 | Delaware | 1 | DL | Wilmington |
| 2 | District of Columbia | 2 | DC | DC |
| 3 | Maryland | 3 | MY | Baltimore |
| 4 | North Carolina | 4 | NC | Charlotte |
| 5 | Virginia | 5 | VG | Richmond |
| 6 | West Virginia | 6 | WV | Charleston |

Profile loading: `dir(fullfile(folderspec,'*.csv'))` glob (17 files expected),
`csvread(ff,1,1)`, row-sum across columns; file #17 (TMY) ×1000. ⚠ folderspec
paths are absolute macOS paths — migration must use repo-relative paths and
**sorted** filenames with the TMY identified by name.

## Frozen aggregate groups (building indices, /n = mean divisor)

| Group | DE | DC | MD | VA | NC | WV |
|---|---|---|---|---|---|---|
| 1 | [11] | [2] | [8] | [2] | [12] | [12] |
| 2 | [1 9]/2 | [7] | [10] | [7] | [4 5 13 14 15]/5 | [4 5]/2 |
| 3 | [13 14 15]/3 | [13 14 15]/3 | [13 14 15]/3 | [12] | [8] | [13 14 15]/3 |
| 4 | [4 5 12]/3 | [4 5 12]/3 | [4 5 12]/3 | [4 5 13 14 15]/5 | [10] | [1 9 11]/3 |
| 5 | [8 10]/2 | [1 9 11]/3 | [1 9 11]/3 | [1 9 11]/3 | [1 9 11]/3 | [3] |
| 6 | [3] | [8 10]/2 | [3] | [8 10]/2 | [3] | [6] |
| 7 | [6] | [3] | [6] | [3] | [6] | [8 10]/2 |
| 8 | [2 7]/2 | [6] | [2 7]/2 | [6] | [16] | [2 7]/2 |
| 9 | [16]/2 ⚠B7 | [16] | [16] | [16]/2 ⚠B7 | [2 7]/2 | [16] |
| 10 | [17] | [17] | [17] | [17] | [17] | [17] |

## Fit

Basis groups `[res com ind]`: DE=[10 5 6], DC=[10 6 7], MD=[10 2 6],
NC=[10 4 6], VA=[10 2 6], WV=[10 2 5].
Residual policy: **proportional** (CIR-weighted across all 3 classes).
⚠ B6: WV residential trend term uses `MY_CIR(3)` — fix, note in validation.

## CIR & buses

- CIR: xlsx sheet 1, rows 1:6 (DL,DC,MY,NC,VG,WV), **cols 28:30**.
- BusDist: **col 1 = national bus number** (col 2 = regional; 180 gen buses,
  loads start regional 181 — migration 2026-07-09), col 5 state code,
  cols 24:26 shares **divided by state CIR** in distribution (F3 convention
  #2 — confirmed: raw columns sum to the CIR fraction, so SRVC's ÷CIR was
  CORRECT energy-wise, unlike FRCC/CAISO/MISO — see B12). 6,340 buses.
- Data notes from migration: .mat variable names DL/DC/MY/NC/VG/WV;
  `NorthCarolina.mat` hour 17 NaN interpolated (12922.49); the "DC" city
  folder's TMY file is Sterling/Washington-Dulles (VA).
- Q_load computed AND written (`Q_Load_SRVC.csv`), random PFs, bug B2.
- Both P and Q pass through the no-op smoothing loop (B1).

## Porting notes

Active plots in the MATLAB (six figure blocks) — replicate only behind C1
plot flags. Stale FL/GA/SC header. `LoadDist` dead. Clustering results
(T_DE…T_WV) computed but unused → analysis tool only.
