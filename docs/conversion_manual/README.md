# LoadSmith design notes

Reference notes from the port of the EPIGRIDS time-series load MATLAB code
(13 regions, 47 `.m` files, ~12.5k lines) to the `loadsmith` package.

**What the code does:** synthesizes hourly (8760-h) real and reactive bus-level
load profiles for synthetic grid models. Per region, state hourly loads are
decomposed day by day into commercial, industrial and residential classes by
non-negative least squares against class-shaped basis profiles, then
distributed to buses using census-tract-derived shares, with randomized bus
power factors giving Q. Outputs feed the EPIGRIDS synthetic network models
(https://github.com/WISPO-POP/SyntheticElectricNetworkModels).

| Document | Contents |
|---|---|
| [architecture.md](architecture.md) | Class design, conversion order, dependency choices |
| [algorithms/](algorithms/) | Reverse-engineered algorithm specs per pipeline stage |
| [regions/](regions/) | Per-region configuration and quirks (all 13 regions) |
| [MATLAB_BUGS.md](MATLAB_BUGS.md) | Bug register B1–B19 and verification flags F1–F4 |
| [VALIDATION_MATRIX.md](VALIDATION_MATRIX.md) | The 13-region validation close-out: bus counts, reference lineages, agreement statistics |
| [HOOKS.md](HOOKS.md) | Inputs from the original authors (H1–H5, all resolved), inter-stage data contracts, parquet schemas |
| [DEPENDENCY_TREE.md](DEPENDENCY_TREE.md) / [dependency_tree.yaml](dependency_tree.yaml) | MATLAB file map |
| [SMOOTHING_PLACEMENT.md](SMOOTHING_PLACEMENT.md) | Where day-boundary smoothing belongs |
| [RFCW_B13_notice.md](RFCW_B13_notice.md) | Notice for users of the legacy RFCW profiles |

Labels such as D8 or C2 in the code and notes refer to design decisions made
during the port; B and F labels are entries in [MATLAB_BUGS.md](MATLAB_BUGS.md).

Ground rules the port followed:

- Python ≥ 3.12 with long-lived dependencies only: numpy, scipy, pandas,
  pyarrow (matplotlib optional; openpyxl/xlrd only in the one-time migration).
- Algorithm for algorithm: intent was reverse-engineered and written as
  idiomatic Python, not transliterated. Known MATLAB bugs are fixed by
  default, with compatibility switches where validation against the MATLAB
  outputs needs them.
