# Pipeline Overview — What Every Region Does

Every canonical MATLAB main script implements the same 7-stage pipeline; the
archetypes differ only in **where the class-shaped basis profiles come from**
(stage 3). LoadSmith implements each stage once, parameterized by region config.

```
 (1) INGEST        state hourly load (8760h), bus table, CIR fractions,
      │            basis source data              [ingest.py + data/ store]
      ▼
 (2) CALENDAR      map each of 365 days → day-type (weekday/Sat/Sun × month,
      │            holidays→Sunday). Only consumed by NYSEG-basis regions.
      ▼                                           [profile_calendar.py]
 (3) BASIS         per day, a 24×(1+k) matrix: ones-column (trend) + k
      │            demeaned, L2-normalized class shapes. Sources:
      │              nyseg   : NYSEG profiles_aggregate slices [2,3,5],
      │                        day-type selected      (MISO NYISO NEISO FRCC)
      │              nrel    : frozen aggregate groups of 17 NREL building
      │                        profiles, same-day slice (AZNM NWPP SPP SRMV
      │                                                  SRTV SRVC RFCE)
      │              utility : PG&E rate schedules (CAISO), Ohio Power Co.
      │                        365×24 class profiles (RFCW)
      ▼                                           [basis.py]
 (4) DAILY FIT     per day: alpha = NNLS(Base, state_day_load); split into
      │            C/I/R via state CIR fractions; residual → residential.
      ▼                                           [fitting.py]
 (5) SMOOTHING     day-boundary QP on the 8760×3 class matrix (optional;
      │            was a silent no-op in MATLAB — bug B1)
      ▼                                           [smoothing.py]
 (6) DISTRIBUTION  P_bus = Σ_c bus_share[:,c] ⊗ class_load[:,c];
      │            seeded per-bus power factors → Q_bus  (D1, D3)
      ▼                                           [distribution.py]
 (7) OUTPUT        bus# [+ national bus# (H1)] + 8760 hourly cols
                   → CSV + parquet; validation invariants
                                                  [outputs.py, validation.py]
```

## Stage docs

| Doc | Stage | Replaces |
|-----|-------|----------|
| [01_ingestion_migration.md](01_ingestion_migration.md) | 1 | `xls2rawMat_*.m`, all raw reads |
| [02_calendar.md](02_calendar.md) | 2 | inline `DayProfileMatch` blocks |
| [03_basis_construction.md](03_basis_construction.md) | 3 | inline profile loading/aggregation + `clusterdata` sections |
| [04_daily_fit.md](04_daily_fit.md) | 4 | inline `lsqnonneg` + class split |
| [05_smoothing.md](05_smoothing.md) | 5 | `smoothprofile.m` |
| [06_distribution_reactive.md](06_distribution_reactive.md) | 6 | inline bus distribution + power factors |
| [07_outputs_validation.md](07_outputs_validation.md) | 7 | inline `csvwrite` (+ new validation) |

Region-specific parameters and quirks: `../regions/<REGION>.md`.
