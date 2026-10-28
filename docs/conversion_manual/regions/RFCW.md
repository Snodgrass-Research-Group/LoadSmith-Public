# RFCW — Region Extraction (VALIDATED 2026-07-10)

> **Converted.** 7,217 buses confirmed; peak target 70,558 MW; OPC profiles
> migrated as opc_com/opc_ind/opc_res (365x24, xls slice 3:367/5:28); CSP
> files not migrated (comparison-only, B10). **Reference verdict — the
> semantics warning below is now PROVEN (bug B13):** `P_Load_RFCW.csv`
> matches the MATLAB-mismapped role order (commercial shape in the
> residential slot) x a global loadscaling 0.8218 at median 6e-06 (IN) /
> 8e-06 (MI) / 5.5e-05 (OH); the by-name (intent) mapping diverges ~3e-02.
> LoadSmith production uses by-name (the fix); the faithful swap lives in
> tests/test_wave4_utility.py. ⚠ User note: legacy RFCW bus loads mix the
> class shapes (residential-share buses got the commercial daily shape).

Canonical script: `RFCW/MakeLoadProfiles_RFCW.m` (443 lines). Fully analyzed
from the MATLAB source. Archetype: **hybrid/utility** — IN, MI, and the exported
OH fit all use Ohio Power Company (OPC) 365×24 class profiles; a NYSEG OH fit
and a Columbus Southern (CSP) OH fit are computed for comparison only.

## States & inputs

| # | State | code (col 5) | var | fit basis |
|---|-------|--------------|-----|-----------|
| 1 | Indiana | 1 | IN | OPC com/ind/res |
| 2 | Michigan | 2 | MI | OPC com/ind/res |
| 3 | Ohio | 3 | OH | OPC (exported); NYSEG + CSP comparison-only |

Utility profiles (sliced `(3:367, 5:28)` → 365 days × 24 h):
- `res_OPC` ← OhioPowerCompanyClassLoadProfiles2016YTD_2-23-2017.xls sheet 1
- `com_OPC` ← OPC_com.xlsx; `ind_OPC` ← OPC_ind.xlsx
- `res_CS` ← ColumbusSouthernPower...2016YTD.xls; `com_CS` ← CSP_com.xlsx;
  `ind_CS` ← **CSP_com.xlsx again (bug B10; CSP_ind.xlsx exists unused)**

`Michigan_load/` subfolder is NOT referenced (dead data). Calendar block:
standard 2015 mapping; used only by the comparison NYSEG OH fit (OPC bases
are indexed by calendar `day` directly).

## Fit

Basis: `[ones | com_OPC(day,:)' | ind_OPC(day,:)' | res_OPC(day,:)']` —
**note column roles: 2=com, 3=ind, 4=res**, though the variable names say
`Res_top` for col 2 and `CI_top` for cols 3:4 (copy-paste misnomers; the
CIR split treats col-2 energy as the "residential-shape" slot — see below).

⚠ **Semantics warning:** RFCW reuses the standard split formulas
(`Res_top = Base(:,2)*alpha(2)`, `CI_top = Base(:,3:4)*alpha(3:4)`) on a
basis ordered com/ind/res. Effectively: the *commercial* OPC shape lands in
the residential slot and ind+res shapes are split C:I. This is either a real
bug or deliberate reuse; the exported numbers reflect it. **Porting policy:**
map roles by NAME (com→CI slot, res→RES slot) — i.e., fix the evident intent;
keep a `rfcw_matlab_column_order=True` compatibility switch for validation.
Flag to user during FRCW validation. Residual → residential (standard).

- CIR: `RFCW bus data.xlsx` sheet 1, rows 1:3 (IN/MI/OH), **cols 28:30**.
- Distribution: per-class, shares **cols 24:26 ÷ state CIR** (F3 convention
  #2). 7,217 buses hard-coded (verify row count at migration).
- Q_load: computed AND written; random PFs; bug B2.
- Outputs: `P_Load_RFCW.csv`, `Q_Load_RFCW.csv` (bus# prepended).

## Porting notes

Dead: `LoadDist`, in-loop fixed-pf react arrays, NYSEG `OH_load`, CSP
`OH_load_CS` (plots only). 2016YTD data with 2015 calendar — verify the state
hourly series' actual year at migration (F4).
