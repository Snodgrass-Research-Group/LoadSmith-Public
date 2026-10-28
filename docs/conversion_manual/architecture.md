# LoadSmith Architecture

## 1. Class decomposition — how many classes, and why

The 13 MATLAB mains are ~90% the same algorithm with different constants.
The design therefore is: **one orchestrator + seven stage modules + 13
declarative region configs**. Configuration over subclassing; polymorphism
only where behavior genuinely branches (the basis source).

```
loadsmith/
  core.py              class LoadSmith          — orchestrator; run(region), run_all()
  config.py            RegionConfig, StateConfig, enums, policies (frozen dataclasses)
  regions/             one config module per region (frcc.py, miso.py, …)
                       regions/__init__.py = REGISTRY dict
  ingest.py            class ParquetStore       — runtime reader of data/ store
  profile_calendar.py  day_type_calendar(year)  — pure functions
  basis.py             BasisSource protocol; NYSEGBasis, NRELAggregateBasis, UtilityBasis
  clustering.py        optional analysis tool (hierarchy clustering of building profiles)
  fitting.py           fit_state(...) -> FitResult   — NNLS decomposition + C/I/R split
  smoothing.py         smooth_class_loads(...)   — day-boundary QP (active-set solver)
  distribution.py      distribute(...), reactive_power(...)  — bus P/Q
  outputs.py           class OutputWriter        — CSV + parquet + metadata (H1 hook)
  validation.py        class Validator           — invariants + reference regression
  plotting.py          optional matplotlib diagnostics (C1)
  cli.py               python -m loadsmith …
scripts/
  migrate_data.py      one-time raw → parquet migration (the only Excel/mat parser)
```

Why not one class with many methods: stages have different lifecycles
(migration runs once; calendar/fit/smoothing are pure functions; the
orchestrator has run state). Why not per-region subclasses: only the basis
source is behavioral; everything else is constants — subclasses would bury
data in code, which is exactly what made the MATLAB unmaintainable.

`LoadSmith` (core.py) is intentionally thin:

```python
smith = LoadSmith(store="data/", seed=20260708)
result = smith.run("FRCC", smoothing="qp", residual="residential")
smith.run_all(parallel=True)      # 13 regions via ProcessPoolExecutor
```

Region-level parallelism only (13 independent embarrassingly-parallel runs);
inside a region the heavy math is already BLAS matmuls. Numpy vectorization
first, processes second, nothing exotic (evergreen rule).

## 2. Conversion order — bottom-up, and why

**Decision: bottom-up ("outside-in"): leaf utilities first, orchestrator
last; FRCC as the pilot region end-to-end before the other 12.**

Rationale against top-down: the mains are 90% duplicated inline code — they
have no meaning until the shared stages exist, and each stage is
independently unit-testable against small MATLAB-derived fixtures (an NNLS
fit for one day, one calendar year, one QP window). Testing a converted
"main" first would require all helpers as stubs anyway.

The one top-down artifact built first was the **shells** — the orchestrator
skeleton and stage signatures — so every stage was written against frozen
interfaces (HOOKS.md §2).

## 3. Dependency choices (evergreen audit)

| Package | Why | Risk |
|---------|-----|------|
| numpy >= 2.0 | arrays everywhere | none |
| scipy >= 1.12 | `optimize.nnls`, `io.loadmat` (migration), `cluster.hierarchy` (analysis) | none |
| pandas >= 2.2 | tables, CSV/parquet I/O | none |
| pyarrow | parquet engine | none (pandas' blessed engine) |
| matplotlib (optional extra) | diagnostics | none |
| openpyxl, xlrd (migration-only deps) | .xlsx/.xls parsing, used once | xlrd is frozen-maintenance but .xls is a frozen format; risk accepted because it's quarantined to `scripts/migrate_data.py` |

Rejected: cvxpy/qpsolvers (QP is 6-var, hand-rolled active-set instead),
`holidays` pkg (8 stable rules hand-coded), numba (compile-chain churn),
joblib (stdlib `concurrent.futures` suffices).

## 4. Performance notes

Per region: 365 NNLS solves (ms), ≤ 3×364 tiny QPs (ms), one (n_bus×3)@(3×8760)
matmul (~0.2 s), CSV write of ~7000×8761 floats (the actual bottleneck,
~seconds; parquet is 10×+ faster). Whole 13-region run: well under a minute
of compute + CSV I/O; `run_all(parallel=True)` makes it I/O-bound. No further
optimization warranted — simplicity wins (user priority: speed *balanced
against* simplicity and evergreen-ness).
