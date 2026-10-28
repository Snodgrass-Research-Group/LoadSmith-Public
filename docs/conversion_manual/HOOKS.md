# Hooks — Pending Inputs & Cross-Stage Contracts

Two kinds of "hooks" live here: (1) **pending inputs** we are waiting on from
the user (all resolved), and (2) **data contracts** between LoadSmith
pipeline stages that code touching adjacent stages must respect.

## 1. Pending inputs from the user

| ID | What | Status | Where it plugs in |
|----|------|--------|-------------------|
| H1 | **National bus number mapping.** RESOLVED: `"Entire US Load Data from Steve, Modified.xlsx"` (in the UW-Madison Synthetic Load folder), sheet *Entire US Load Data from Steve* — 75,432 buses; col A **Final National Bus Num** (⚠ use Final, not col B Initial — they differ), col C Regional Bus Num, col D bus type Gen/Load, col F state, col G region, col H region num. Verified: the published WISPO-POP Florida model uses buses 27810+ = FRCC's national block (regional 1..7440 → national 27810..35249). The existing reference P/Q CSVs already carry national numbers in col 1. Migrated to `data/shared/national_bus_map.parquet`; outputs put the national number in column 1 (D13). | ✅ resolved 2026-07-09 | `scripts/migrate_data.py`, `ingest.ParquetStore.national_bus_map()`, `outputs.py`, `core.RunResult`. |
| H2 | **KCL-KVL Compliant Grid Generator.** RESOLVED: lives at `loadsmith.locations.kclkvl_dir()` (external repo, READ-ONLY per D12). Consumption contract learned from `CreateLoadScenarios.m`/`CreateSNet.m`: they call `MakeLoadProfiles_<REGION>(LoadPath)` as a **function returning [P_Load, Q_Load]** matrices, then strip column 1 if `mode(diff(col1)) == 1` (bus numbers), zero-pad gen buses, and align by intersecting bus numbers with their BusInputData. National numbers stay strippable (consecutive-ish) → compatible. A future Python port should consume `RunResult.as_matrices()` directly. | ✅ resolved 2026-07-09 | `locations.py`; `core.RunResult.as_matrices()`. |
| H3 | **Reference outputs.** RESOLVED: full P/Q reference CSVs for all 13 regions live in the external UW-Madison Synthetic Load folder (`locations.reference_dir(region)`), NOT in the repo (0.3–0.5 GB each). Repo folder `validation/reference_outputs/` remains as an optional override for committed excerpts. Quirks: FRCC P (2024) has a header row; CAISO has two P variants (2019/2021); NYISO folder contains a stray bus-column-less MISO CSV; Q is compared statistically only (unseeded MATLAB rand). | ✅ resolved 2026-07-09 | `validation.Validator.find_reference()`; `tests/test_regression.py`. |
| H4 | **RawStateLoadProfiles.mat provenance** (MISO). No producer script exists; if the user has the original IL/IA/MN/WI hourly xls sources, migration can start from raw. Otherwise migration reads the .mat (fine). | optional | `loadsmith/ingest.py` MISO loader. |
| H5 | **loadscaling in production outputs?** RESOLVED (user, 2026-07-09): support BOTH as a switch. `peak_scaling = "kclkvl"` (peak pinned to the col-16 state-peak sum, as in the published reference) or `"none"` (exact state-energy conservation), configured in **`loadsmith.toml`** (decision D16). Col 16 ('State Peak Load', one value per state) is migrated as bus_table.state_peak_mw; FRCC target = 78,763 MW, production factor 0.886683 (peak pinned exactly). | ✅ resolved 2026-07-09 | `loadsmith.toml`, `settings.py`, `core.run(peak_scaling=…)`, bus_table.state_peak_mw. |

External locations (env-var overridable; defaults in `loadsmith/locations.py`):

| Env var | Default | Contents |
|---------|---------|----------|
| `LOADSMITH_UW_LOAD_DIR` | `UW-Madison Synthetic Load/` next to the clone | region folders w/ reference P/Q CSVs + raw inputs; the Steve mapping xlsx; `Mapped Buses - WECC Load Data` + `Mapping Buses - EI Load Data` (per-case load-bus mapping CSVs for the joined EI/WECC models — not needed by LoadSmith core) |
| `LOADSMITH_KCLKVL_DIR` | `Synthetic-Grid-Generator/KCL-KVL Compliant Grid Generator/` next to the clone | downstream consumer (READ-ONLY) |

## 2. Inter-stage data contracts (the "pipeline bus")

All arrays are numpy float64; hours are 0-indexed h = 0..8759 (MATLAB's 1..8760
maps to h+1). All stages exchange data via these shapes:

```
StateLoad        : (8760,)            state hourly demand [MW]
DayTypeCalendar  : (365,) int         day -> NYSEG profile index 1..36 (nyseg archetype)
BasisMatrix      : per day: (24, 1+k) col 0 = ones (trend), cols 1..k demeaned
                                       & L2-normalized basis shapes
ClassLoads       : (8760, 3)          state load split [C, I, R] [MW]
                                       INVARIANT: sum over classes ≈ StateLoad
                                       (exact when residual policy != "drop")
BusShares        : (n_bus, 3)         per-bus share of each state class total
                                       INVARIANT: sums to 1.0 over each state's
                                       buses, per class (renormalized, C4/F3)
PowerFactors     : (n_bus, 3)         seeded-RNG uniform draws in D3 ranges
P_bus            : (n_bus, 8760)      = BusShares[:,c] outer ClassLoads[:,c] summed over c
Q_bus            : (n_bus, 8760)      = sum_c (sqrt(1-pf²)/pf)[:,c] * P_bus_class_c
RunResult        : always returned in memory (D14): national+regional bus
                                       numbers, P, Q, metadata; .p_frame()/
                                       .q_frame() DataFrames; .as_matrices()
                                       = KCL-KVL-shaped [busnum | 8760 cols]
OutputTable      : national_bus_number (col 1, D13) + 8760 hourly cols,
                                       written only for requested formats
                                       (csv, parquet, or none)
```

Stage owners (module -> produces):
- `ingest.py`        -> StateLoad, BusShares, CIR fractions, basis raw data (from parquet store)
- `profile_calendar.py` -> DayTypeCalendar
- `basis.py`         -> BasisMatrix per day (archetype-dependent)
- `fitting.py`       -> ClassLoads (consumes StateLoad + BasisMatrix + CIR)
- `smoothing.py`     -> ClassLoads (smoothed in place, optional; C2)
- `distribution.py`  -> P_bus, Q_bus
- `outputs.py`       -> OutputTable -> CSV + parquet
- `validation.py`    -> checks every INVARIANT above + reference comparison

## 3. Parquet store schema (produced by one-time migration, D8)

```
data/
  shared/
    nyseg_profiles.parquet      # long: (hour 1-24, day_type 1-36, class 1-9) -> value
    national_bus_map.parquet    # region, regional_bus_num, national_bus_num,
                                #   bus_type (Gen/Load), state, region_num (H1)
  <region>/                     # lowercase region code, e.g. data/frcc/
    state_loads.parquet         # columns: state, hour (1-8760), load_mw
    bus_table.parquet           # bus_number (= national numbering: the bus
                                #   xlsx's col 1 IS 'Final National Bus Num'
                                #   — discovered at migration, so MATLAB
                                #   BusNums were national all along),
                                #   national_bus_num (cross-verified vs the
                                #   shared map), regional_bus_num (col 2),
                                #   state_code (col 5), share_c/i/r
                                #   (renormalized to sum to 1.0 per state-class)
                                #   + raw_share_* originals (which sum to the
                                #   CIR fraction — convention #2, F3/B12)
    cir_fractions.parquet       # state, frac_c, frac_i, frac_r
    nrel_profiles.parquet       # (nrel archetype) state, city, building_idx 1-17, hour, value
    utility_profiles.parquet    # (CAISO/RFCW) source (a1/a10/e1/opc_com/...), day, hour, value
    migration_report.json       # row counts, checksums, F1-F3 verification results
```

Migration provenance rule: every parquet file's metadata records the source
file path (from its archive folder on, e.g.
`EPIGRIDS-Time-Series-Load-Code/SRTV/SRTV bus data.xlsx`), its SHA-256, and
the migration date.

## 4. Validation leads (recorded 2026-07-09)

- The KCL-KVL `Master Load Data/<REGION>/` folders contain **function-ized**
  `MakeLoadProfiles_<R>.m` variants (called as functions returning
  [P_Load, Q_Load]) that differ from this repo's scripts. The 2024
  `P_Load_FRCC.csv` reference is finite where the repo's raw `Florida.xls`
  has an empty cell (hour 1707), so the reference was likely produced by the
  KCL-KVL variant with repaired data. Before tolerance-tuning, diff the
  function variant against the repo script (especially whether it fixes the
  B12 energy deficit) — read-only access, never modify (D12).
- Data repairs applied at migration (recorded in migration_report.json):
  Florida hour 1707 NaN → linear interpolation (14455.5); NorthCarolina
  hour 17 NaN → 12922.49.
- SRVC "DC" city folder uses the Sterling/Washington-Dulles (VA) TMY file.
