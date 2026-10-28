# AZNM — Region Extraction (VALIDATED 2026-07-10)

> **Reference provenance (empirical):** `P_Load_AZNM.csv` is a ÷CIR,
> no-loadscaling output at **scale 1.0** — but its **column-1 bus numbers
> are an OLDER numbering revision**: 3,948 of 4,536 differ from the current
> `AZNM bus data.xlsx` col 1 / national map (one 143-bus block sits at
> 63344–63486 in the reference vs 61820–61962 today; the set matches
> neither the Steve workbook's *Final* nor *Initial* column). The physical
> rows ARE the same buses in the same order — joined **BY ROW ORDER**,
> LoadSmith production matches **AZ 7.6e-06 / CO 6.1e-06 / NM 7.1e-06 /
> UT 7.5e-06 @ scale 1.0** and **NV 2.6e-05 @ 0.999729** (= NV's raw-CIR
> row sum; the other four sum to 1.0). No NaN whitelists. ⚠ Downstream:
> never join the archived AZNM reference to current models by bus number.
> Locked in by tests/test_wave4_west1.py. Config re-verified line-by-line —
> zero discrepancies; no SPP-style cross-state bugs.

Canonical script: `AZNM/MakeLoadProfiles_AZNM.m` (752 lines). Archetype:
**NREL** — per-day fit against the same day's slice of full-year NREL
aggregates; NYSEG line commented out; calendar block present but DEAD.

## States & inputs

| # | State | code (col 5) | var | NREL city folder |
|---|-------|--------------|-----|------------------|
| 1 | Arizona | 1 | AZ | Phoenix |
| 2 | Colorado | 2 | CO | Boulder |
| 3 | Nevada | 3 | NV | Las_Vegas |
| 4 | New Mexico | 4 | NM | Albuquerque |
| 5 | Utah | 5 | UT | Salt_Lake_City ⚠ (Boulder 5B building CSVs + SLC TMY) |

All five folders hold the standard 16 `RefBldg*` exports + TMY — **no
Birmingham-style stray files** (checked explicitly because AZ's group
literals are identical to SRTV/AL's, which there were an artifact of the
`aRefBldg` dir-order shift; here they are canonical — most likely the
author copy-pasted the AL grouping into AZ).

## Frozen aggregate groups (building indices, /n = divisor)

| Group | AZ | CO | NV | NM | UT |
|---|---|---|---|---|---|
| 1 | [12 13 14]/3 | [13 14 15]/3 | [12] | [2] | [2] |
| 2 | [3 4 11]/3 | [4 5 12]/3 | [4 5 13 14 15]/5 | [7] | [7] |
| 3 | [8 10]/2 | [8] | [8] | [8] | [8] |
| 4 | [7 9]/2 | [10] | [10] | [10] | [10] |
| 5 | [2] | [3] | [1 9 11]/3 | [1 9 11]/3 | [1 9 11]/3 |
| 6 | [5] | [6] | [3] | [4 5 12 13 14 15]/6 | [4 5 12 13 14 15]/6 |
| 7 | [1 6]/2 | [1 9 11]/2 ⚠/2 | [6] | [3] | [3] |
| 8 | [15] | [16] | [16] | [6]/2 ⚠B7 | [6]/2 ⚠B7 |
| 9 | [16] | [2 7] ⚠no div | [2 7] ⚠no div | [16] | [16] |
| 10 | [17] | [17] | [17] | [17] | [17] |

NM and UT share identical groupings ("%Do Tennessee Fit" header over the
NM block is stale copy-paste, B11).

## Fit

Basis groups `[res com ind]`: AZ=[10 2 5], CO=[10 4 9], NV=[10 3 9],
NM=[10 1 4], UT=[10 1 4]. Residual: **proportional**, own CIR, no B3
typos, no B6 analogue, no SPP-style stale-variable bugs.

## CIR & buses

- CIR: `Atmp(1:6,28:30)` — 6-row read over 5 states; row 6 is all-NaN
  padding (migration reads rows 1:5). Raw row sums 1.0 except
  **NV = 0.999729** (⇒ NV's scale vs the reference).
- BusDist: col 1 = national bus number **(current revision 61820–66498;
  the reference's differs — see banner)**, col 5 state code, cols 24:26
  shares ÷ state CIR (correct convention, F3 #2). **4,536 buses.**
- No .mat NaN repairs (cross-checks byte-equal vs the .xls).
- Q computed AND written, old PF ranges, bug B2; smoothing loop 1:4536
  no-op (B1). Output `[BusNums | 4536×8760]`, no header.

## Porting notes

Stale headers (B11); `LoadDist` dead; clustering unused. The bus-number
revision means the **row-order join is the validation contract** for this
region only (every other region so far joins by national bus number).
