# NEISO — Region Extraction (VALIDATED 2026-07-10)

Canonical script: `NEISO/MakeLoadProfiles_NEISO_NEW.m` (511 lines).
Archetype: **NYSEG** (profiles_aggregate slices 2/3/5, 2015 day-type
calendar) — pure per-class script, no NREL sections.

> **Reference verdict (empirical):** `P_Load_NEISO.csv` in the UW folder is
> NOT the old total-broadcast output (rank-1 residual ≈ 0.15 rules it out —
> the "P_Load_NEISO IS BAD DO NOT USE" boxnote refers to a still older
> file). It matches LoadSmith **production mode (renormalized ÷CIR, no
> loadscaling) at scale 1.0000, median rel. diff ≈ 7e-06** for all six
> states. Locked in by tests/test_wave4_nyseg.py.

## States & inputs

| # (col 5) | State | .mat var | CIR row (cols 28:30) |
|---|-------|----------|----------------------|
| 1 | Connecticut | CT | 1 |
| 2 | Maine | ME | 2 |
| 3 | Massachusetts (file: Massachussetts.mat, sic) | MA | 3 |
| 4 | NewHampshire | NH | 4 |
| 5 | RhodeIsland | RI | 5 |
| 6 | Vermont | VT | 6 |

Bus table: `NEISO bus data.xlsx` — col 1 national bus number, col 2
regional, col 5 state code, cols 24:26 raw shares (sum to CIR fraction —
F3 convention #2), col 16 state peak. **3,370 buses** (national 132–3501).

## Fit & distribution

- Standard NYSEG basis/split. **No B3 typo**: all six states add the daily
  residual to the residential class correctly (`residual="residential"` is
  both production and MATLAB-faithful).
- MATLAB distribution used raw shares (B12 deficit); Q entirely commented
  out; `csvwrite('P_Load_NEISO.csv')` had **no bus-number column** (B8-style
  — B8 is not MISO-only). LoadSmith: renormalized shares, Q per D3,
  national bus numbers always written.

## Validation stats (2026-07-10)

Reference has no bus column → row-order alignment (bus-table order).
Per state, fitted scale = 1.0000: median rel diff CT 7.6e-06, ME 7.0e-06,
MA 6.9e-06, NH 6.6e-06, RI 7.7e-06, VT 7.5e-06.
