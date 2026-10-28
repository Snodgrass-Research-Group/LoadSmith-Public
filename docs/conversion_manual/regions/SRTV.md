# SRTV — Region Extraction (VALIDATED 2026-07-10)

> **Reference provenance (empirical):** `P_Load_SRTV.csv` is a ÷CIR,
> no-loadscaling output at **scale 1.0** (repo script or the algorithmically
> identical KCL-KVL function variant — their only differences are the
> function wrapper, `ispc` path handling, and commented-out csvwrite).
> LoadSmith production mode matches at median rel. diff **AL 6.3e-06 /
> KY 6.0e-06 / TN 6.0e-06 @ scale 1.0; MS 7.6e-06 @ 0.999975** (= MS's
> raw-CIR row sum; the other three sum to 1.0). Whitelists: KY hours 1587 &
> 7298 and TN hour 699 (1-based) are NaN in the reference (unrepaired .mat
> inputs; ours are interpolated at migration), and the three containing days
> (KY days 67 & 305, TN day 30) are **zero-alpha passthrough** days — MATLAB
> `lsqnonneg` returns x=0 when the target contains NaN, so those reference
> days are Σ(raw shares) × raw state load. Locked in by
> tests/test_wave4_south.py.

Canonical script: `SRTV/MakeLoadProfiles_SRTV.m` (657 lines). Config
re-verified line-by-line — zero discrepancies after the AL
dir-order correction below. Archetype: **NREL** — per-day fit against the
same day's slice of full-year NREL aggregates; NYSEG line commented out;
calendar block present but DEAD.

## States & inputs

| # | State | code (col 5) | var | NREL city folder |
|---|-------|--------------|-----|------------------|
| 1 | Alabama | 1 | AL | Birmingham ⚠ (see quirk) |
| 2 | Kentucky | 2 | KY | Louisville |
| 3 | Mississippi | 3 | MS | Jackson |
| 4 | Tennessee | 4 | TN | Nashville |

Profile loading: `dir(fullfile(folderspec,'*.csv'))` glob, `csvread(ff,1,1)`,
row-sum across columns; file #17 in **enumeration order** ×1000.

## ⚠ The Birmingham `aRefBldg` dir-order quirk (settled empirically)

Birmingham's FullServiceRestaurant CSV is a stray **headerless, dateless**
copy named `aRefBldgFullServiceRestaurant…` (present identically in the repo,
the UW archive, and the KCL-KVL Master Load Data copy). Consequences in the
generating MATLAB run — whose `dir()` enumerated **ASCII/case-sensitively**
(`RefBldg* < USA_* < aRefBldg*`), verified by reference agreement
(6.3e-06 for the ASCII reading vs 2.9e-02 for the case-insensitive one):

1. Script position `p ≤ 15` = canonical building `p+1` (Hospital…Warehouse);
   position 16 = the TMY file (**not** ×1000-scaled — the scaling hit
   position 17 instead); position 17 = the `aRefBldg` restaurant (×1000).
2. `csvread(f,1,1)` on the headerless file drops its **first data hour** and
   its **first data column** (`Electricity:Facility`), and the preallocated
   `zeros(8760,1)` buffer leaves hour 8760 = 0 — a one-hour-shifted,
   magnitude-halved restaurant profile. Migrated faithfully
   (`scripts/migrate_data.py::_parse_nrel_csv` zero-pads; canonical idx 1).
3. AL's **"residential" fit basis (group 10) is therefore the shifted
   restaurant profile, not the TMY weather proxy** used everywhere else.
4. The ×1000 mismatches are numerically irrelevant: both affected profiles
   sit in single-member groups and basis columns are demeaned + normalized
   per day.

`loadsmith/regions/srtv.py` stores the **permuted (canonical-index)**
groups, which land exactly on the author's usual semantic patterns —
strong independent evidence for the ASCII reading:

| Group | AL (permuted = actual) | AL (script literals) | KY | MS | TN |
|---|---|---|---|---|---|
| 1 | [13 14 15]/3 retail | [12 13 14]/3 | [13 14 15]/3 | [12] | [2] |
| 2 | [4 5 12]/3 office | [3 4 11]/3 | [4 5 12]/3 | [4 5 13 14 15]/5 | [7] |
| 3 | [9 11]/2 | [8 10]/2 | [8] | [8] | [8] |
| 4 | [8 10]/2 schools | [7 9]/2 | [10] | [10] | [10] |
| 5 | [3] | [2] | [3] | [1 9 11]/3 | [1 9 11]/3 |
| 6 | [6] | [5] | [6] | [3] | [4 5 12 13 14 15]/6 |
| 7 | [2 7]/2 hospital | [1 6]/2 | [1 9 11]/2 ⚠/2 | [6] | [3] |
| 8 | [16] | [15] | [16] | [16] | [6]/2 ⚠B7 |
| 9 | [17 TMY] | [16] | [2 7] ⚠no divisor | [2 7] ⚠no divisor | [16] |
| 10 | [1 shifted rest.] | [17] | [17] | [17] | [17] |

## Fit

Basis groups `[res com ind]`: AL=[10 5 7], KY=[10 5 9], MS=[10 5 6],
TN=[10 1 7]. Residual policy: **proportional** (CIR-weighted, own CIR —
no B6 analogue, no B3 typos).

## CIR & buses

- CIR: `Atmp(1:6,28:30)` — an SRVC 6-state copy-paste; only rows 1:4 are
  real (migration reads 1:4). Raw row sums: AL/KY/TN = 1.0, MS = 0.999975
  (⇒ MS deviates by that factor vs LoadSmith's Σ=1 renormalization).
- BusDist: col 1 = national bus number, col 5 state code, cols 24:26 shares
  **÷ state CIR** (correct convention, F3 #2). **4,451 buses** (loop bound
  1:4451 matches the row count exactly).
- Data repairs at migration: `Kentucky.mat` hours 1587 & 7298,
  `Tennessee.mat` hour 699 (1-based) NaN → linear interpolation.
- Q computed AND written (`Q_Load_SRTV.csv`), old PF ranges, bug B2;
  smoothing loop 1:4451 no-op (B1). Output `[BusNums | 4451×8760]`, no
  header.

## Porting notes

Stale FL/GA/SC header comment; `LoadDist` dead; clustering results
(T_AL…T_TN) computed but unused. The KCL-KVL `Master Load Data/SRTV/`
function variant is algorithmically identical (diffed; function
wrapper + `ispc` paths + csvwrite commented out), so the reference could
have come from either variant — the ASCII `dir()` enumeration is the
empirical fact; which machine/OS produced it is not established (a
case-insensitive enumeration, e.g. typical Windows/NTFS, would instead
have yielded the canonical order that the reference rules out at 2.9e-02).
