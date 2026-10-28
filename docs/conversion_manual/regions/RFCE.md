# RFCE — Region Extraction (VALIDATED 2026-07-10)

> **Reference provenance (empirical):** `P_Load_RFCE.csv` was made by the
> **KCL-KVL function variant** (like FRCC, unlike every other Machine-B
> region): ÷CIR distribution × global **loadscaling 0.865687** (peak
> pinned to 48,489 MW = Σ unique col-16 state peaks, computed on the
> BUGGED matrix), **raw workbook CIR** (NJ row sums to 0.999964), and the
> **PN `NJ_CIR(1)` bug** (New Jersey's commercial fraction 0.5158 in
> Pennsylvania's commercial trend term instead of PN's 0.3022). The
> faithful reconstruction × 0.865687 matches at **NJ 7.7e-06 / PN
> 6.5e-06 @ scale 1.0**. Production (bugs fixed, `peak_scaling="none"`):
> NJ is a pure constant 0.865656 away (= loadscaling × NJ CIR-sum);
> PN deviates ~10% median by design. ⚠ `peak_scaling="kclkvl"` pins the
> same 48,489 MW on the FIXED matrix ⇒ factor **0.965592 ≠ 0.865687** —
> the reference factor exists only together with the PN bug. Whitelist:
> NJ hours 1587 & 7298 (1-based) NaN in the reference (unrepaired
> NewJersey.mat; interpolated at migration) — and days 67 & 305 were fit
> by an NNLS that **DROPPED the NaN hour** (23-hour fit, reproduced at
> 8.6e-06), a **third NaN signature** distinct from the zero-alpha
> passthrough in the SRVC/SRTV references (stock MATLAB `lsqnonneg`
> returns x=0 on a NaN target; the KCL-KVL variant's environment
> evidently row-dropped instead — e.g. Octave or a patched solver).
> Bus-number join clean (5,218/5,218 — no AZNM-style numbering drift).
> Locked in by tests/test_wave4_west2.py.

Canonical algorithm: `RFCE/MakeLoadProfiles_RFCE.m` (407-line repo script;
the KCL-KVL `Master Load Data/RFCE/` copy is the SAME algorithm wrapped as
a function + `ispc` paths + the loadscaling step + csvwrite commented —
an earlier config note calling them "byte-identical" was wrong, since fixed). Archetype: **NREL**, proportional residual (SRVC-style).

## States & inputs

| # | State | code (col 5) | var | NREL city folder |
|---|-------|--------------|-----|------------------|
| 1 | New Jersey | 1 | NJ | Newark ⚠ (BALTIMORE MD buildings + Newark TMY) |
| 2 | Pennsylvania | 2 | PN | Philadelphia ⚠ (BALTIMORE MD buildings + Philadelphia TMY) |

The glob loop reads exactly these two folders (the "which two
cities" question). Newark also contains a stray `test.m` (orphan, D6 list).

## Frozen aggregate groups

| Group | NJ | PN |
|---|---|---|
| 1 | [8] | [8] |
| 2 | [10] | [10] |
| 3 | [13 14 15]/3 | [13 14 15]/3 |
| 4 | [4 5 12]/3 | [4 5 12]/3 |
| 5 | [1 9 11]/3 | [1 9 11]/3 |
| 6 | [3] | [3] |
| 7 | [6] | [6] |
| 8 | [2 7]/2 | [2 7] ⚠ no divisor |
| 9 | [16] | [16] |
| 10 | [17] | [17] |

## Fit

Basis groups `[res com ind]`: NJ=[10 2 6], PN=[10 2 6]. Residual:
**proportional** (`+ XX_resid*XX_CIR(k)` on every class). The PN
residential line's `+ +` is a harmless unary plus, NOT the FRCC B3 typo.

## The PN `NJ_CIR(1)` bug (line 322; fixed in production)

`PN_load(:,1) = PN_Trend*NJ_CIR(1) + …` — NJ's commercial fraction
(0.5158) in PN's commercial trend term instead of PN's own (0.3022):
+21% of PN's trend energy lands in the commercial class. Same family as
B6 (SRVC/WV). Faithful: `cl_PN[:,0] += trend·(NJ_raw_c − PN_raw_c)`.
Consequence chain: the bugged matrix has a higher system peak, so the
KCL-KVL loadscaling denominator is larger ⇒ 0.865687; with the bug fixed
the same peak-pinning yields 0.965592.

## CIR & buses

- CIR: `Atmp(1:2,28:30)`. Raw sums: NJ 0.999964, PN 1.0.
- BusDist: col 1 = national bus number (8663–13880; matches the reference
  — bus-number join), col 5 state code, cols 24:26 shares ÷ state CIR.
  **5,218 buses** (= smoothing bound 1:5218).
- Data repairs: `NewJersey.mat` hours 1587 & 7298 (1-based) NaN → linear
  interpolation (same hour positions as SRTV/Kentucky — likely a shared
  corrupted source template). Pennsylvania clean.
- Q computed AND written (B2 bug); ×loadscaling in the KCL-KVL variant.
  Repo script csvwrites `[BusNums | 5218×8760]`, no header.

## Porting notes

Dead day-type calendar (`profile` unused); stale "FL, GA, SC" header
(B11); active `histogram` figures (relative fit error, NJ/PN) — C1
optional plots only. `RFCE/NREL_Profiles/Newark/test.m` is an orphan
(already on the D6 deletion list).
