# Stage 1 — Ingestion & One-Time Migration (`ingest.py`, `scripts/migrate_data.py`)

## What MATLAB does

- `xls2rawMat_<REGION>.m`: `xlsread` each state's hourly-load workbook (rows =
  days? columns = hours — verify per file), `reshape(X.', 1, [])` row-major
  flatten to 1×8760, save as `<State>.mat` with the state name as variable.
- Main scripts then `load <State>` and transpose to a column.
- Bus tables: `xlsread('<REGION> bus data.xlsx', 1)` → numeric matrix
  (`xlsread` silently drops leading text rows/columns — column indices in the
  scripts refer to the NUMERIC sub-matrix, not the spreadsheet letters!
  Verify each region's column mapping against the actual sheet at migration).
- NYSEG basis: `NYSEGloadprofiles2016.mat` → `profiles_aggregate` (24×36×9).
  Static input, no producer (see HOOKS H2/H4 and DEPENDENCY_TREE).
- NREL building profiles: per-city folders of 17 CSVs, read either explicitly
  (FRCC) or via `dir(fullfile(folderspec,'*.csv'))` glob loops (NREL-basis
  regions) with `csvread(ff, 1, 1)` (skip 1 header row, 1 index column), each
  file row-summed across columns to a single 8760 series; **file #17 (the TMY
  weather file) scaled ×1000**.
  ⚠ The glob order is OS/dirent order in MATLAB; Python must use **sorted
  filenames** and verify the 17-file census per folder (assert count == 17,
  identify the TMY file by name pattern `USA_*_TMY2*.csv`, not by position).
- Utility profiles: CAISO `a1-2000.csv`/`a10-2000.csv`/`e1-2000.csv`
  (`csvread(f,1)`, 365×≥24, day-rows × hour-cols); RFCW OPC/CSP workbooks
  sliced `(3:367, 5:28)` → 365×24.

## Python design (decision D8)

One-time `scripts/migrate_data.py` builds the parquet store described in
HOOKS.md §3; `loadsmith/ingest.py` reads ONLY the store at runtime.

Migration responsibilities (per region):
1. Parse raw sources: `.xls` via pandas+xlrd, `.xlsx` via pandas+openpyxl,
   `.mat` via `scipy.io.loadmat`, `.csv` via pandas. Prefer raw files; use
   `.mat` where no raw source exists (NYSEG, MISO RawStateLoadProfiles).
2. Cross-check every state series: length 8760, no NaNs, positive, and
   `.mat`-derived == raw-xls-derived where both exist (catches parse errors).
3. Bus table: store bus_number, state_code, raw share columns AND
   renormalized shares (each state's class column rescaled to sum to 1.0) —
   resolves flag F3 deterministically; record which convention the raw file
   used in `migration_report.json`.
4. Record row counts vs. the MATLAB hard-coded bus counts (F1, F2, B5).
5. Stamp parquet metadata: source path, SHA-256, migration date.

Runtime `ingest.py` returns plain numpy/pandas objects per the HOOKS.md
contracts. No Excel/`.mat` parsing at runtime — keeps runtime deps to
numpy/scipy/pandas/pyarrow only.
