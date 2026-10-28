# SPP — Region Extraction (VALIDATED 2026-07-10)

> **Reference provenance (empirical):** `P_Load_SPP.csv` is a ÷CIR,
> no-loadscaling output at **scale 1.0** carrying **all three SPP
> copy-paste bugs** (below). LoadSmith production mode (bugs fixed) matches
> **NB 6.7e-06 / SD 6.5e-06 / TX 7.0e-06 @ scale 1.0**; the bugged states
> match only via faithful reconstructions: **ND 6.6e-06** (fit on OK-city
> aggregates), **OK 5.8e-06** (stale `ND_CI_top` in the industrial class),
> **KS 6.6e-06** (share col 24 reused for the industrial term — the
> reference over-delivers KS energy ×1.127 = CIR_C/CIR_I leak; production
> conserves). Production deviations on the bugged states: KS 2.2e-01 /
> ND 8.8e-03 / OK 1.4e-05 median (OK's tail p99 2.5e-02). No NaN
> whitelists. Locked in by tests/test_wave4_west1.py. Config re-verified
> line-by-line — zero discrepancies. All raw CIR rows sum to 1.0
> (TX 1.000003).

Canonical script: `SPP/MakeLoadProfiles_SPP.m` (897 lines). Archetype:
**NREL** — per-day fit against the same day's slice of full-year NREL
aggregates; NYSEG line commented out; calendar block present but DEAD.

## States & inputs

| # | State | code (col 5) | var | NREL city folder (building donors) |
|---|-------|--------------|-----|-------------------------------------|
| 1 | Kansas | 1 | KS | Wichita (Baltimore 4A) |
| 2 | Nebraska | 2 | NB | Omaha (Chicago-O'Hare 5A) |
| 3 | North Dakota | 3 | ND | Fargo (Duluth 7A) — **fit unused, see bug #1** |
| 4 | Oklahoma | 4 | OK | Oklahoma_City (Atlanta 3A) |
| 5 | South Dakota | 5 | SD | Sioux_Falls (Minneapolis 6A) |
| 6 | Texas (SPP share) | 6 | TX | Houston |

All six folders hold the standard 16 `RefBldg*` exports + TMY (no
Birmingham-style strays). `'ERCOT Backcasted Load Profiles 2016.xls'` is
**DEAD**: the canonical script never reads it and `xls2rawMat_SPP.m` builds
`Texas.mat` from `TX_Hourly_Load.xls` (migration cross-check: byte-equal).

## The three SPP copy-paste bugs (all in the 2018 reference; all FIXED in production)

1. **ND fit uses OK's aggregates** (line 629): `Base = [ones
   profiles_aggregate_OK(...,[10 5 6])]` — Fargo's aggregates are computed
   but never fit. The comment "use profiles 5 and 6 … in North Dakota"
   shows the intent; production uses Fargo `[10 5 6]`
   (`ND_MATLAB_FAITHFUL_NREL` in regions/spp.py is the validation spec).
2. **OK industrial reuses the stale `ND_CI_top`** (line 683): ND's loop
   finished first, so `ND_CI_top` holds ND's **day-365** 24-h com/ind
   component, tiled into every OK day's industrial class (`(ND_CI_top) *
   OK_CIR(2)/sum(OK_CIR(1:2))`). The commercial/residential classes are
   correct — hence production's tiny median but fat tail vs the reference.
3. **KS distribution reuses share col 24** (line 794): `(BusDist(KS_list,
   24)/KS_CIR(2)) * KS_load(:,2)'` — the industrial term uses the
   COMMERCIAL share column (col 25 never read for KS P). Reference
   delivers CIR_C/CIR_I ≈ 1.127× the fitted KS energy and distributes
   industrial load by commercial shares.

Faithful reconstructions (tests): ND → refit on OK aggregates; OK →
`cl[:,1] += (tile(ND_CI_top_365) − OK_CI_top_hourly) · CIR_I/(CIR_C+CIR_I)`;
KS → `P = renorm_c·(KS_C + KS_I·CIR_C/CIR_I) + renorm_r·KS_R`.

## Frozen aggregate groups (building indices, /n = divisor)

| Group | KS | NB | ND | OK | SD | TX |
|---|---|---|---|---|---|---|
| 1 | [2] | [11] | [11] | [13 14 15]/3 | [4 5 12]/3 | [8] |
| 2 | [7] | [1 9]/2 | [13 14 15]/3 | [4 5 12]/3 | [13 14 15]/3 | [10] |
| 3 | [8] | [13 14 15]/3 | [4 5 12]/3 | [8] | [11] | [12] |
| 4 | [10]/3 ⚠ | [4 5 12]/3 | [1 9]/2 | [10] | [1 9]/2 | [4 5 13 14 15]/5 |
| 5 | [1 9 11]/3 | [8 10]/2 | [8 10]/2 | [1 9 11]/3 | [8 10]/2 | [1 9 11]/2 ⚠ |
| 6 | [4 5 12 13 14 15]/6 | [3] | [3] | [3] | [3] | [3] |
| 7 | [3] | [6] | [6] | [6] | [6] | [6] |
| 8 | [6] | [2 7]/2 | [2 7]/2 | [16] | [2 7] ⚠no div | [2 7] ⚠no div |
| 9 | [16]/2 ⚠ | [16] | [16] | [2 7] ⚠no div | [16] | [16] |
| 10 | [17] | [17] | [17] | [17] | [17] | [17] |

## Fit

Basis groups `[res com ind]`: KS=[10 1 7], NB=[10 5 6], ND=[10 5 6] (on OK
aggregates in the reference; Fargo in production), OK=[10 6 9], SD=[10 1 6],
TX=[10 6 8]. Residual: **proportional**, own CIR, no B3 typos, no B6
analogue.

## CIR & buses

- CIR: `Atmp(1:6,28:30)`, rows 1:6 = KS/NB/ND/OK/SD/TX. Raw row sums all
  1.0 (TX 1.000003 — sub-tolerance).
- BusDist: col 1 = national bus number (50550–58574), col 5 state code,
  cols 24:26 shares ÷ state CIR (except the KS bug above). **8,025 buses.**
- **F1 fully RESOLVED**: SPP's `1:3123` smoothing/LoadDist bound IS an
  SRMV copy-paste (SRMV really has 3,123 rows; SPP has 8,025) — moot at
  runtime because `smoothprofile` is a no-op (B1) and `LoadDist` is dead.
- No .mat NaN repairs (migration cross-checks byte-equal vs the .xls).
- Q computed AND written, old PF ranges, bug B2. Output
  `[BusNums | 8025×8760]`, no header.

## Porting notes

`These profiles seem OK.boxnote` sits in the raw folder (2019-era review
note). Stale header comments; `LoadDist` dead; clustering unused. Bugs
1–3 above are candidates for MATLAB_BUGS.md register numbers B15–B17
(B14 = the SRTV aRefBldg quirk); they were registered there.
