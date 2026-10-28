# Notice: class-shape mix-up in the published RFCW load profiles (bug B13)

*Prepared 2026-07-10 for forwarding to users of the legacy synthetic RFCW
time-series loads (`P_Load_RFCW.csv` / `Q_Load_RFCW.csv`). Contact:
Jonathan Snodgrass (Jonathan.Snodgrass@tamu.edu).*

## Summary

The published RFCW (Indiana / Michigan / Ohio, 7,217 buses) hourly load
profiles assign the **commercial** daily load shape to each bus's
**residential** load share, while the industrial and residential shapes are
blended and split across the commercial + industrial shares. Bus-level
*totals* are only mildly affected, but any analysis that depends on **which
daily shape a bus follows** — e.g. buses with high residential share
exhibiting an evening peak — is working with mislabeled shape assignments.

## Technical cause

`MakeLoadProfiles_RFCW.m` builds its fitting basis from Ohio Power Company
class profiles in the column order **[commercial, industrial, residential]**,
but reuses split formulas written for a basis whose *first* profile column is
residential (`Res_top = Base(:,2)*alpha(2)`; `CI_top = Base(:,3:4)*alpha(3:4)`).
The result, embodied in the published outputs:

- the **commercial** OPC shape (plus the fit residual) is distributed by the
  buses' **residential** shares;
- the **industrial + residential** OPC shapes form the pool that is split
  C:I and distributed by the commercial and industrial shares.

This was confirmed empirically during the Python conversion (2026-07-10): a
rebuild that deliberately reproduces the swapped roles matches the published
CSV at median relative difference ~6×10⁻⁶ (IN) / 8×10⁻⁶ (MI) / 5.5×10⁻⁵ (OH)
(after the file's global scaling factor of 0.8218, a system-peak-pinning
step), while the correctly-mapped rebuild diverges from it by ~3×10⁻²
(median) — i.e. bus-level hourly values differ by a few percent typically,
with larger deviations at hours where the class shapes disagree most.

## Who is affected

- **Affected:** studies using RFCW bus-level *hourly shapes* by customer
  class — demand response, load composition, coincidence/diversity analysis,
  time-of-peak per bus, class-sensitive dynamic load modeling.
- **Largely unaffected:** studies using system- or state-level totals
  (the state hourly totals are preserved up to the published file's global
  0.8218 peak-scaling factor and the fitting residual policy), and power-flow
  snapshots at hours where class shapes are similar.

## Corrected data

The Python reimplementation (LoadSmith) maps the class shapes by name — the
evident intent — and its RFCW outputs are available in two variants
(energy-exact, and peak-pinned like the published file) under
`RFCW/LoadSmith_outputs/` in the UW-Madison Synthetic Load share. The swapped
behavior is retained only as a validation mode
(`tests/test_wave4_utility.py`) to prove provenance against the legacy file.

Full documentation: `docs/conversion_manual/regions/RFCW.md` and bug **B13**
in `docs/conversion_manual/MATLAB_BUGS.md` (repo
`EPIGRIDS-Time-Series-Load-Code`).
