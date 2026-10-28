# MATLAB Function/Data Tree — Human-Readable

> Machine-parseable version: [dependency_tree.yaml](dependency_tree.yaml)
> Bug IDs (B*) and flags (F*): [MATLAB_BUGS.md](MATLAB_BUGS.md)
> Generated 2026-07-08. 47 `.m` files, ~12,500 lines, 13 region folders.
> Statuses refreshed 2026-07-11 — all 13 regions validated;
> per-region verdicts live in [regions/](regions/).

## The call structure is shallow

The MATLAB code has almost no function-call depth: each region has one main
*script* (not a function) that calls exactly **one** user-defined function
(`smoothprofile`, 13 identical copies) plus three toolbox functions
(`clusterdata`, `lsqnonneg`, `quadprog` — the last only inside
`smoothprofile`). The real "tree" is therefore a **data-flow** tree: which
files feed which scripts. All complexity lives inline in the main scripts.

## FRCC — the pilot region (most complicated folder, 2,371 lines)

```
MakeLoadProfiles_FRCC_NEW.m                        [ACTIVE — canonical main]
│
├─ CALLS
│   ├─ smoothprofile.m ── quadprog (Optim toolbox)  [B1: no-op as called]
│   ├─ clusterdata (Stats toolbox)  x3 (Miami/Atlanta/Charleston correlation)
│   └─ lsqnonneg            x6 (NYSEG fit + NREL fit, x3 states)
│
├─ READS
│   ├─ Florida.mat / Georgia.mat / SouthCarolina.mat   <── xls2rawMat_FRCC.m
│   │                                                       ├─ Florida.xls
│   │                                                       ├─ GA_Hourly_Load.xls
│   │                                                       └─ SC_Houly_Load.xls
│   ├─ NYSEGloadprofiles2016.mat (profiles_aggregate, 24x36x9)  [static: no
│   │        in-repo producer; algorithmic ancestor = MISO/loadprofiles2010.m]
│   ├─ NREL_Profiles/Miami_Intl_AP/*.csv     (16 building types + TMY2)
│   ├─ NREL_Profiles/Atlanta_AP/*.csv        (16 + TMY2)
│   ├─ NREL_Profiles/Charleston/*.csv        (16 + TMY2; files are Atlanta
│   │                                         copies renamed — see regions/FRCC.md)
│   └─ FRCC bus data.xlsx   (CIR rows 1:3 cols 27:29; BusDist: col1 bus#,
│                            col5 state code FL=1/GA=2/SC=3, cols 24:26 C/I/R
│                            bus shares; 7224 buses)
│
└─ WRITES
    └─ P_Load_FRCC.csv  (7224 x 8761: bus# + 8760 hourly MW)   [Q commented out]

MakeLoadProfiles_FRCC.m        [SUPERSEDED: broadcasts state total to buses]
NREL_cluster.m                 [ORPHAN: exploratory clustering; loads missing
                                GA_load.mat; saves nothing]
smoothprofile.m                [ACTIVE (shared): convert once]
xls2rawMat_FRCC.m              [ACTIVE (ingestion): folded into migration]
```

## All 13 regions at a glance

| Region | Canonical main | Lines | Archetype | States | Buses | Q written? | Extra quirks |
|--------|----------------|------:|-----------|--------|------:|-----------|--------------|
| FRCC  | MakeLoadProfiles_FRCC_NEW.m | 966 | hybrid (NYSEG output + NREL comparison) | FL GA SC | 7,224 | no (commented) | B3 residual no-op; pilot region |
| SRVC  | MakeLoadProfiles_SRVC.m | 933 | NREL | DE DC MD NC VA WV | 6,340 | yes | B6 WV uses MD CIR; ÷CIR distribution (F3) |
| SPP   | MakeLoadProfiles_SPP.m | 897 | NREL | KS NE ND OK SD TX | 8,025 | yes | ERCOT xls DEAD; 1:3123 bound = SRMV copy-paste (F1); bugs B15–B17 |
| AZNM  | MakeLoadProfiles_AZNM.m | 752 | NREL | AZ CO NM NV UT | 4,536 | yes | reference bus numbers = older revision → row-order join (regions/AZNM.md) |
| SRTV  | MakeLoadProfiles_SRTV.m | 657 | NREL | AL KY MS TN | 4,451 | yes | Birmingham aRefBldg dir-order quirk (B14) — AL groups permuted |
| NWPP  | MakeLoadProfiles_NWPP.m | 524 | **mixed** (ID/MT/WY NREL; OR/WA PG&E a1/a10/e1) | ID MT OR WA WY | 2,977 | yes | e1 headerless → day-shifted res basis; WY ID_Res_top stale-var bug |
| SRMV  | MakeLoadProfiles_SRMV.m | 511 | NREL | AR LA MO | 3,123 | yes | F1 resolved: 3,123 is real here (SPP's bound was the copy-paste); LA raw CIR sums to 0.9025 |
| NEISO | MakeLoadProfiles_NEISO_NEW.m | 511 | NYSEG | CT ME MA NH RI VT | 3,370 | no (commented) | |
| MISO  | MakeLoadProfiles_MISO_NEW.m | 496 | NYSEG | IL IA MN WI | 6,671 | no (commented) | IA+MN combined fit; B8 no bus# column; B5 resolved (6,671 rows) |
| RFCW  | MakeLoadProfiles_RFCW.m | 443 | hybrid (OPC utility profiles) | IN MI OH | 7,217 | yes | 2016 OPC/CSP data; ÷CIR distribution; B13 role mismap |
| RFCE  | MakeLoadProfiles_RFCE.m | 407 | NREL | NJ PA | 5,218 | yes | PN commercial trend uses NJ_CIR(1); KCL-KVL variant adds loadscaling 0.8657 |
| CAISO | MakeLoadProfiles_CAISO_NEW.m | 207 | utility (PG&E a1/a10/e1) | CA | 8,034 | no (commented) | CIR hard-coded [0.455 0.197 0.348]; cols 26:28; state col 6 |
| NYISO | MakeLoadProfiles_NYISO.m | 180 | NYSEG | NY | 4,880 | yes | B9 total-based distribution (needs backport) |

**Archetype key**
- **NYSEG**: per-day NNLS fit against 3 of the 36 NYSEG representative
  day-type profiles (slices [2, 3, 5] of `profiles_aggregate`), selected via
  the 2015 `DayProfileMatch` calendar.
- **NREL**: per-day NNLS fit against that same day's 24-h slice of frozen
  aggregate NREL building profiles (10 groups per state-city). Calendar code
  present but **dead** in these scripts.
- **utility/hybrid**: region-specific class profiles (PG&E rate schedules for
  CAISO, Ohio Power Co. for RFCW) used as the fit basis.

## Orphans (do not convert; delete after validation — user decision D6)

| File | Why orphaned |
|------|--------------|
| `<region>/MakeLoadProfiles_<R>.m` originals where a `_NEW` exists (FRCC, MISO, NEISO, CAISO) | superseded by _NEW (canonical per D1) |
| `NYISO/MakeLoadProfiles_MISO_NEW.m` | stray byte-identical copy of MISO's file |
| `MISO/loadprofiles2010.m` | 2010 New England prototype; computes but never saves the profiles_aggregate recipe; its LoadProfiles.mat output feeds nothing |
| `MISO/MakeLoadProfiles_react.m` | Q prototype; logic already folded into MISO main; outputs don't exist on disk |
| `FRCC/NREL_cluster.m` | exploratory clustering; needs missing GA_load.mat; saves nothing |
| `CAISO/enrel_profiles_CAISO.m` | 27-line throwaway plot |
| `RFCE/NREL_Profiles/Newark/test.m` | 9-line scratch snippet |
| `CAISO/MakeLoadProfiles_CAISO.m~`, `NEISO/MakeLoadProfiles_NEISO.m~` | editor backup files |
| 12 of 13 `smoothprofile.m` copies | identical duplicates (converted once) |

## Static inputs with no in-repo producer

| File | Contents | Consumed by |
|------|----------|-------------|
| `NYSEGloadprofiles2016.mat` | `profiles_aggregate` 24x36x9 (hour x day-type x class) | FRCC, MISO, NYISO, NEISO, RFCW (CAISO loads but ignores) |
| `MISO/RawStateLoadProfiles.mat` | IL, IA, MN, WI hourly vectors | MISO (no xls2rawMat_MISO exists) |
| `<REGION> bus data.xlsx` | bus table: bus#, state code (col 5; col 6 CAISO), per-bus C/I/R shares (cols 24:26; 26:28 CAISO), state CIR fractions (cols 27:29 / 28:30 by region) | all mains |
