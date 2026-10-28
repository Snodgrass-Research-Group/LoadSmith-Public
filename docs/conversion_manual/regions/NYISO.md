# NYISO — Region Extraction

Canonical script: `NYISO/MakeLoadProfiles_NYISO.m` (180 lines). Fully
analyzed from the MATLAB source. Archetype: **NYSEG**, single state (NY).
No `_NEW` variant exists → decision D1 backport applies.

## Inputs

- `NewYork.mat` → `NY` (from `xls2rawMat_NYISO.m` ← NewYork.xls).
- `NYSEGloadprofiles2016.mat` → `profiles_aggregate`.
- `NYISO bus data.xlsx`: CIR row 1, **cols 27:29**; BusDist col 5 (NY=1),
  shares cols 24:26, LoadDist col 15 rows 1:4880. 4,880 buses.

## Fit

Standard NYSEG basis/split; residual → residential. Dead in-loop fixed-pf
`NY_react` block (not ported).

## Distribution & output — ⚠ bug B9

```
P_load(NY_list,:) = BusDist(:,24)*NY_load_total' + BusDist(:,25)*NY_load_total'
                  + BusDist(:,26)*NY_load_total'    % TOTAL for all 3 columns
```
Same for Q. This is exactly the "all buses scale identically" defect the
_NEW variants fixed elsewhere. **LoadSmith implements per-class (D1); the
old `P_Load_NYISO.csv`/`Q_Load_NYISO.csv` references will NOT match** —
validate structurally or against a corrected MATLAB run.

Q_load: computed AND written (only NYSEG-family script that writes Q);
random PFs with bug B2; superseded by D3 ranges.
