# LoadSmith

Synthesizes hourly (8760-h) bus-level **real and reactive load profiles**
(P/Q) for [EPIGRIDS](https://github.com/WISPO-POP/SyntheticElectricNetworkModels)
synthetic grid models, covering 13 regions of the continental US (72,066 load
buses).

LoadSmith is a Python port of the EPIGRIDS time-series load code, MATLAB
originally written by Bernie Lesieutre and his research group at the
University of Wisconsin–Madison. Everything LoadSmith needs at runtime — the
migrated data — is included here.

- **All 13 regions validated** against the published reference outputs, with
  reference provenance settled per region —
  [docs/conversion_manual/VALIDATION_MATRIX.md](docs/conversion_manual/VALIDATION_MATRIX.md).
- **19 MATLAB bugs** found and fixed, with faithful-comparison switches where
  the references embody them —
  [docs/conversion_manual/MATLAB_BUGS.md](docs/conversion_manual/MATLAB_BUGS.md).
- Design notes and algorithm specs:
  [docs/conversion_manual/README.md](docs/conversion_manual/README.md).

## Install

Python >= 3.12.

```
pip install -e .            # runtime
pip install -e .[dev]       # + pytest, ruff (to run the test suite)
pip install -e .[plot]      # + matplotlib (diagnostics)
pip install -e .[migrate]   # + openpyxl, xlrd (only to re-run the data migration)
```

The runtime package never parses Excel or `.mat`; the `[migrate]` extra is only
needed to regenerate `data/` from raw sources (decision D8).

## Usage

```
loadsmith run FRCC                                  # write P/Q per loadsmith.toml
loadsmith run FRCC --formats none --peak-scaling kclkvl
loadsmith run --all                                 # every region, sequentially
```

Run switches (`formats`, `smoothing`, `residual`, `shares`, `peak_scaling`,
`seed`, …) live in [loadsmith.toml](loadsmith.toml); precedence is
`run()` kwarg > `[regions.<NAME>]` > `[run]` > built-in defaults. Every run also
returns an in-memory `RunResult` (numpy P/Q arrays + bus numbers) for direct
hand-off to downstream Python tools:

```python
from loadsmith import LoadSmith

result = LoadSmith().run("FRCC", formats=())   # in-memory only
P, Q = result.as_matrices()                    # national bus number in column 0
```

## Repository layout

```
loadsmith/    Python package (7-stage pipeline + per-region configs)
scripts/      one-time raw-data -> parquet migration + research scripts
data/         migrated parquet store — all the runtime reads
tests/        pytest suite (incl. per-region reference regressions)
validation/   optional in-repo overrides for reference excerpts
docs/         design notes (algorithms, per-region notes, bug register)
```

The pipeline (see
[docs/conversion_manual/algorithms/00_pipeline_overview.md](docs/conversion_manual/algorithms/00_pipeline_overview.md)):

```
ingest -> calendar -> basis -> daily NNLS fit -> smoothing ->
bus distribution (+ reactive power) -> outputs -> validation
```

## Data

`data/` holds the migrated parquet store and is the **only** data LoadSmith
reads at runtime, so the package runs out of the box. Every parquet file
records its source file (from its archive folder on), SHA-256, and migration
date. The data are licensed under CC BY 4.0 (see [LICENSE-DATA](LICENSE-DATA));
the original sources keep their own terms.

| Files | Contents | Original source |
|---|---|---|
| `<region>/bus_table.parquet`, `<region>/cir_fractions.parquet` | Load buses, national bus numbers, census-tract-derived commercial/industrial/residential shares | EPIGRIDS bus data (UW–Madison) |
| `<region>/state_loads.parquet` | Hourly state loads | EPIGRIDS MATLAB archive (UW–Madison) |
| `<region>/nrel_profiles.parquet` | Hourly building load profiles by city | DOE commercial reference building simulations (NREL) |
| `caiso/`, `nwpp/`, `rfcw/` `utility_profiles.parquet` | Utility class load profiles | Published utility load-profile data (PG&E rate-schedule profiles; Ohio Power Company class profiles) |
| `shared/nyseg_profiles.parquet` | Representative-day class load profiles | NYSEG 2016 load profiles |
| `shared/national_bus_map.parquet` | Regional → national bus numbers | EPIGRIDS national bus numbering |

Regenerating `data/` and the reference-CSV regressions need large files that
are not in this repository (the raw MATLAB inputs, reference P/Q CSVs and the
national bus-number workbook). Point `LOADSMITH_UW_LOAD_DIR` at the folder
holding them (default: `UW-Madison Synthetic Load/` next to this clone); see
[loadsmith/locations.py](loadsmith/locations.py).

## Testing

```
pytest
```

176 tests run on a fresh clone; 31 more (per-region regressions against the
reference outputs, and one that reads a raw archived `.mat`) skip unless the
external reference files are present.

## Running

Run every command from the repository root (see Known issues).

| Command | What it does |
|---------|--------------|
| `loadsmith run <REGION> [options]` | One region. `<REGION>` is one of AZNM, CAISO, FRCC, MISO, NEISO, NWPP, NYISO, RFCE, RFCW, SPP, SRMV, SRTV, SRVC (case-insensitive). |
| `loadsmith migrate [--region <REGION>] [--data-dir data]` | Rebuilds the parquet store from the raw inputs. Without `--region` it rebuilds `data/shared/` and every region that has a file in [scripts/migration_specs/](scripts/migration_specs/). Needs the `[migrate]` extra and `LOADSMITH_UW_LOAD_DIR`. |
| `python scripts/research_smoothing_placement.py` | Research study on FRCC that prints the smoothing-placement metrics behind [SMOOTHING_PLACEMENT.md](docs/conversion_manual/SMOOTHING_PLACEMENT.md). Not part of the pipeline. |

Options for `loadsmith run`: `--settings FILE` reads another settings file
instead of `./loadsmith.toml`; each of the others overrides the value from the
settings file: `--formats csv,parquet|csv|parquet|none`,
`--smoothing none|qp`, `--shares renormalized|raw`,
`--peak-scaling none|kclkvl`, `--residual residential|proportional|drop`,
`--seed N`, `--no-header`, `--no-validate`. The command prints one status line
per region (bus count, peak-scale factor, files written) and exits with code 1
if any region fails structural validation.

The `core.py` module docstring gives the MATLAB-comparison settings for FRCC.
From the command line:

```
loadsmith run FRCC --smoothing none --residual drop --shares raw --peak-scaling none --no-header
```

From Python, `LoadSmith().run_all()` runs every region in parallel worker
processes and writes CSV and parquet by default.

## Inputs and outputs

Inputs (read at runtime):

- `data/<region>/`: `bus_table`, `cir_fractions` and `state_loads` parquet
  files, plus `nrel_profiles` and/or `utility_profiles` for the regions whose
  fit basis uses them. The national bus numbers come from `bus_table`.
- `data/shared/nyseg_profiles.parquet`, for the regions that use the NYSEG
  basis. (`data/shared/national_bus_map.parquet` is used by the migration and
  the tests, not by `loadsmith run`.)
- `loadsmith.toml` in the current folder (optional; built-in defaults apply
  when it is missing).

Outputs (when `formats` is not empty), in `outputs/<REGION>/` (the
`output_dir` setting):

- `P_Load_<REGION>.csv`, `Q_Load_<REGION>.csv`: one row per load bus. Column
  `bus Num` is the national bus number, then `h0001` to `h8760` (P in MW, Q in
  Mvar). The header row is omitted with `csv_header = false` or `--no-header`.
- `P_Load_<REGION>.parquet`, `Q_Load_<REGION>.parquet`: the same columns plus
  `regional_bus_num`.
- `run_metadata.json`: seed, switches, peak-scale factor, package version,
  file names and write time.

With `formats = []` or `--formats none`, nothing is written to disk and the
results stay in the returned `RunResult`.

## Known issues

- Paths resolve against the current folder, not the repository. `loadsmith.toml`
  is looked up in the current folder, `store = "data"` and
  `output_dir = "outputs"` are relative, and `loadsmith migrate` imports
  `scripts/migrate_data.py` by adding the relative folder `scripts` to
  `sys.path`. Run from another folder, `loadsmith run` cannot find `data/` and
  `loadsmith migrate` fails to import.
- With the default settings, runs write large CSV and parquet files into
  `outputs/` inside the repository (git-ignored; about 1 GB for an SRVC-size
  CSV). Set `output_dir` in `loadsmith.toml` to move them.
- `loadsmith/plotting.py` is a shell: both functions raise
  `NotImplementedError`. The `[plot]` extra installs matplotlib, but no plots
  are produced.

## License

* Code: MIT — see [LICENSE](LICENSE).
* Data in `data/`: CC BY 4.0 — see [LICENSE-DATA](LICENSE-DATA).

Copyright (c) 2026 Jonathan M. Snodgrass for the Python port. The algorithms
come from the MATLAB code by Bernie Lesieutre's research group at UW–Madison;
please credit both (see [CITATION.cff](CITATION.cff)).

## Acknowledgment

The MATLAB code that LoadSmith ports to Python was developed with support from
the Advanced Research Projects Agency-Energy (ARPA-E), U.S. Department of
Energy, under Award Number DE-AR0000717 (EPIGRIDS, GRID DATA program).

**Disclaimer.** This software was prepared as an account of work sponsored by
an agency of the United States Government. Neither the United States
Government nor any agency thereof, nor any of their employees, makes any
warranty, express or implied, or assumes any legal liability or responsibility
for the accuracy, completeness, or usefulness of any information, apparatus,
product, or process disclosed, or represents that its use would not infringe
privately owned rights. Reference herein to any specific commercial product,
process, or service by trade name, trademark, manufacturer, or otherwise does
not necessarily constitute or imply its endorsement, recommendation, or
favoring by the United States Government or any agency thereof. The views and
opinions of authors expressed herein do not necessarily state or reflect those
of the United States Government or any agency thereof.

## Related repositories

- [WISPO-POP/SyntheticElectricNetworkModels](https://github.com/WISPO-POP/SyntheticElectricNetworkModels):
  the published EPIGRIDS synthetic network models these load profiles feed;
  LoadSmith's national bus numbers match them.
- [GridCrucible](https://github.com/Snodgrass-Research-Group/GridCrucible-Public):
  the KCL-KVL synthetic-grid generator; LoadSmith supersedes its port of the
  MATLAB load-profile builder (`MakeLoadProfiles_<Region>.m`), though
  GridCrucible does not import `loadsmith` yet.
- [GridWeld](https://github.com/Snodgrass-Research-Group/GridWeld-Public): its
  default CAISO load apportionment was built from LoadSmith's CAISO bus table.
- [GridForge](https://github.com/Snodgrass-Research-Group/GridForge-Public) and
  [GridTemper](https://github.com/Snodgrass-Research-Group/GridTemper-Public):
  the rest of the synthetic-grid family.
