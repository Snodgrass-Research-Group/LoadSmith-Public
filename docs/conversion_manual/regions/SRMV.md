# SRMV — Region Extraction (VALIDATED 2026-07-10)

> **Reference provenance (empirical):** `P_Load_SRMV.csv` is a ÷CIR,
> no-loadscaling output at **scale 1.0** with the **raw workbook CIR**
> (Louisiana's 'Total % C/I/R' row sums to **0.902455**). LoadSmith
> production mode matches **AR 7.5e-06 / MO 6.0e-06 @ scale 1.0** (their
> raw CIR rows sum to 1.0). **LO matches (6.1e-06) only with the raw CIR
> reproduced** — i.e. class loads rebuilt as
> `cl_k − (1−Σ)·renorm_k·(Trend + resid)` with Σ = 0.902455 — because the
> MATLAB fit leaks ~9.75% of LA's trend+residual energy (a B12-style
> deficit in the FIT stage). Production LoadSmith renormalizes CIR to Σ=1
> (energy-conserving), so **LO buses run ~10.8% above the reference by
> design**. No NaN repairs, no whitelists. Locked in by
> tests/test_wave4_south.py. Config re-verified line-by-line against the
> MATLAB source — zero discrepancies.

Canonical script: `SRMV/MakeLoadProfiles_SRMV.m` (511 lines). Archetype:
**NREL** — per-day fit against the same day's slice of full-year NREL
aggregates; NYSEG line commented out; calendar block present but DEAD.

## States & inputs

| # | State | code (col 5) | var | NREL city folder |
|---|-------|--------------|-----|------------------|
| 1 | Arkansas | 1 | AR | Little_Rock |
| 2 | Louisiana | 2 | **LO** (not LA) | New_Orleans |
| 3 | Missouri | 3 | MO | Kansas_City |

Profile loading: standard glob + `csvread(ff,1,1)` row-sum; file #17
(TMY, `USA_*` sorts last among the standard names) ×1000. All three city
folders hold the standard 16 `RefBldg*` exports + TMY — no Birmingham-style
stray files (SRTV.md).

## Frozen aggregate groups (building indices, /n = mean divisor)

| Group | AR | LO | MO |
|---|---|---|---|
| 1 | [8] | [8] | [13 14 15]/3 |
| 2 | [10] | [10] | [4 5 12]/3 |
| 3 | [13 14 15]/3 | [4 5 13 14 15]/5 | [8] |
| 4 | [4 5 12]/3 | [12] | [10] |
| 5 | [1 9 11]/3 | [1 9 11]/3 | [1 11]/2 ⚠ omits 9 |
| 6 | [3] | [3] | [3] |
| 7 | [6] | [6] | [6] |
| 8 | [16] | [2 7]/2 | [16] |
| 9 | [2 7]/2 | [16] | [2 7] ⚠ no divisor |
| 10 | [17] | [17] | [17] |

Cosmetic: the MO block initializes a stray `profiles_aggregate_ =
zeros(...)` (missing suffix); MATLAB auto-grows the real
`profiles_aggregate_MO` — not ported.

## Fit

Basis groups `[res com ind]`: AR=[10 1 6], LO=[10 6 8], MO=[10 6 9].
Residual policy: **proportional** (CIR-weighted, own CIR — no B6 analogue,
no B3 typos).

## ⚠ The Louisiana CIR anomaly

`Atmp(1:6,28:30)` (SRVC copy-paste; only rows 1:3 real) yields raw CIR
rows: AR = 1.000000, **LO = 0.902455**, MO = 1.000000. The MATLAB uses LA's
row verbatim in `Trend*CIR(k)` and `CIR(k)*resid`, delivering only 90.25%
of those terms (the com/ind/res "top" shapes are unscaled); the ÷CIR
distribution then cancels bus-share normalization but NOT this fit-stage
leak. LoadSmith renormalizes CIR inside `fit_state` (Σ=1) → exact state
energy conservation → LO ~10.8% above the reference. The compatibility
reconstruction used by the tests:
`ml_k = cl_k − (1−Σ)·renorm_k·(trend_hourly + residuals)`.

## CIR & buses

- BusDist: col 1 = national bus number (range 47011–50133), col 5 state
  code, cols 24:26 shares ÷ state CIR (correct convention, F3 #2).
  **3,123 buses** — loop bound 1:3123 == actual row count, so **F1 is
  RESOLVED for the SRMV half**: the bound is correct here, not a copy-paste
  artifact (see SPP.md for the other half).
- No .mat NaN repairs (AR/LO/MO clean).
- Q computed AND written (`Q_Load_SRMV.csv`), old PF ranges, bug B2;
  smoothing loop 1:3123 no-op (B1). Output `[BusNums | 3123×8760]`,
  no header.

## Porting notes

Stale FL/GA/SC header comment; `LoadDist` dead; clustering results
computed but unused (analysis tool only, D7).
