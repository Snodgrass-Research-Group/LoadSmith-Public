# Reference Outputs (hook H3 — RESOLVED 2026-07-09)

The full MATLAB reference files (~0.5 GB each) live OUTSIDE the repo in the
**UW-Madison Synthetic Load** folder:

```
UW-Madison Synthetic Load/<REGION>/P_Load_<REGION>.csv (+ Q)
```

By default that folder is looked for next to this clone.

Override the location with the `LOADSMITH_UW_LOAD_DIR` environment variable
(see `loadsmith/locations.py`). The Validator and `tests/test_regression.py`
read them in place.

**This folder** is an optional repo-local override checked FIRST — use it
for small committed excerpts (e.g. a 50-bus slice for CI) with the same
filenames. Regions without any reference are skipped by tests.

Reference-file facts (surveyed 2026-07-09):
- Column 1 = **national** bus numbers (Final National Bus Num, per
  "Entire US Load Data from Steve, Modified.xlsx").
- FRCC P has a `bus Num` header row; most files have none (loader sniffs).
- CAISO has two P variants (2019 `_NEW`, 2021 plain) — which is authoritative
  is an open question tracked in docs/conversion_manual/regions/CAISO.md.
- `NYISO/P_Load_MISO_NEW.csv` is a stray MISO file with no bus column — ignore.
- Q files: compare statistically only (MATLAB power factors were unseeded).
