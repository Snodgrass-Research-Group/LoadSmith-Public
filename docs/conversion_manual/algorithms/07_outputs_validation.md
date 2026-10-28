# Stage 7 — Outputs & Validation (`outputs.py`, `validation.py`)

## Outputs (decision D4)

Per region, matching MATLAB layout plus modern extras:

Formats are selectable per run (D14): any subset of {csv, parquet} — or NONE,
with results consumed in memory via `RunResult` (numpy arrays; `.p_frame()` /
`.q_frame()` DataFrames on demand; `.as_matrices()` = the [busnum | 8760 cols]
shape the KCL-KVL consumer expects).

```
outputs/<REGION>/P_Load_<REGION>.csv    national_bus_number, h0001..h8760 (D13)
outputs/<REGION>/Q_Load_<REGION>.csv    same layout
outputs/<REGION>/P_Load_<REGION>.parquet  (+ Q)  wide + regional_bus_num column
outputs/<REGION>/run_metadata.json      seed, config hash, package version,
                                        smoothing/residual policies, timestamps
```

- MATLAB `csvwrite` produced NO header row; the CSV writer has
  `header=False` mode for byte-compatibility. The KCL-KVL consumer strips
  the bus-number column itself (`mode(diff(col1))==1` test) and tolerates
  either form.
- **national_bus_number** (H1 RESOLVED): the *Final National Bus Num* from
  the Steve workbook via `data/shared/national_bus_map.parquet`, joined on
  (region, regional bus number, bus_type='Load'). This is the numbering of
  the published WISPO-POP models and of the existing reference CSVs
  (MISO: B8 — the bus column is synthesized since MATLAB omitted it).

## Validation (`validation.py`, decision D5)

### Structural invariants (always run, no reference data needed)

| Check | Definition |
|-------|------------|
| energy conservation | `Σ_bus P[b,t] == state_load(t)` per state, all t (tol 1e-6 rel) — requires residual policy != "drop" |
| class conservation | `Σ_c ClassLoads[t,c] == state_load(t)` (same caveat) |
| non-negativity | `P >= 0` everywhere (NNLS + nonneg shares guarantee it; assert anyway) |
| share sanity | renormalized shares sum to 1 per state-class; raw-vs-renormalized convention logged (F3) |
| Q sanity | `0 <= Q[b,t] <= P[b,t] * max_qf` with max_qf from the residential PF floor (0.95 → qf ≈ 0.3287) |
| shape | (n_bus, 8760), bus numbers unique, no NaN/inf |
| smoothness (if smoothing on) | second difference across each midnight >= -tol for all class profiles |

### Regression vs MATLAB reference (H3 RESOLVED — external UW folder)

References for all 13 regions: `locations.reference_dir(region)/P_Load_<R>.csv`
(+ Q), with `validation/reference_outputs/<REGION>/` as an in-repo override
for committed excerpts. Column 1 is already the NATIONAL bus number — join
on it, never on row order. Comparison mode configures LoadSmith for
MATLAB-faithfulness:
`smoothing="none"`, `residual` per region's MATLAB behavior (e.g. FRCC
"drop"), old PF ranges + B2 bug reproduction is NOT provided — Q comparisons
are structural only (Q depends on MATLAB `rand` without a recorded seed, so
exact Q regression is impossible; compare P exactly, Q statistically:
per-bus Q/P ratio within the old pf-range envelope).

Expected P agreement: `rtol <= 1e-6` for regions without fixed bugs in the
P path; documented per-region deltas where bugs were fixed (B3 FRCC residual,
B6 SRVC WV, B9 NYISO backport → NYISO P will NOT match its old reference; it
should instead be validated structurally + against a fresh MATLAB run of a
corrected script if the user wants).

### Report

`validation.py` emits `outputs/<REGION>/validation_report.json` + a console
summary table. Tests in `tests/test_regression.py` skip regions lacking
reference data.
