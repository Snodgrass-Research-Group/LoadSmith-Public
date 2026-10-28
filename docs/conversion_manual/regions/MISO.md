# MISO — Region Extraction

Canonical script: `MISO/MakeLoadProfiles_MISO_NEW.m` (496 lines). Fully
analyzed from the MATLAB source. Archetype: **NYSEG** (the reference
implementation of it). ⚠ A byte-identical stray copy lives at
`NYISO/MakeLoadProfiles_MISO_NEW.m` (orphan).

## Inputs

- `RawStateLoadProfiles.mat` → IL, IA, MN, WI (8760 each). **No producer
  script exists** (only region without xls2rawMat; hook H4). Folder has
  `WI_Hourly_Load.xls`, `new_load.xlsx` as possible raw sources.
- `NYSEGloadprofiles2016.mat` → `profiles_aggregate` (24×36×9).
- `MISO bus data.xlsx`: CIR rows 1:4 = IL/IA/MN/WI, cols 28:30; BusDist
  col 5 = state code (IL=1, IA=2, MN=3, WI=4), shares cols 24:26 (raw
  convention), LoadDist col 4 (dead).

## Fit

Standard NYSEG basis/split (03/04 docs). **Unique quirk — combined IA+MN
fit:** `IAMN = IA + MN`; `IAMN_CIR` = load-weighted average of IA and MN CIR
rows; fit once; de-combine per class c:
`scale_c = IA_CIR[c]·ΣIA / (IA_CIR[c]·ΣIA + MN_CIR[c]·ΣMN)`;
`IA_load[:,c] = IAMN_load[:,c]·scale_c`; `MN_load = IAMN_load − IA_load`.
Residual → residential (standard).

## Distribution & output

- Per-class, raw shares — **which sum to the CIR fraction, not 1.0**
  (migration 2026-07-09: F3 convention #2 after all → MISO_NEW under-delivers
  energy, bug B12; LoadSmith uses renormalized shares). Bus count: exactly
  **6,671** (B5 resolved); bus xlsx col 1 = national bus numbers, col 2 =
  regional (gen+load numbering; 297 gen buses, loads start at regional 298).
- **B8: no `BusNums` variable — `P_Load_MISO.csv` has NO bus-number column**
  (7,000-ish rows × 8760, alignment implied by xlsx row order). LoadSmith
  always writes bus numbers; note this when comparing against the reference
  CSV (offset columns).
- Q commented out. Boxnote says old P load "INCORRECT" (fixed by _NEW).
