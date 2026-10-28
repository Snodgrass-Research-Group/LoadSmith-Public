# 13-Region Validation Matrix

*2026-07-11. One consolidated page: what was
validated, against which reference, and how well it agreed. Per-region
detail: `docs/conversion_manual/regions/<REGION>.md`. Register references
(B*/F*): [MATLAB_BUGS.md](MATLAB_BUGS.md). Structural columns are FRESH
in-memory runs on the final code (production settings: shares=renormalized,
residual per-state default, smoothing=none, peak_scaling=none, seed
20260708); agreement figures are the region validation results, locked in
by the regression tests named in each row.*

**Status: 13/13 regions validated.** Fresh structural pass 13/13 (all
checks green, energy conservation at machine precision — max bus-level
error ≤ 5e-10 MW). Reference provenance settled for all 13 (three
lineages, below).

*Post-matrix update (D18, 2026-07-11): NWPP/WY and FRCC/GA production
residual policy switched to `proportional` (their residential classes went
negative under `residential`; all classes strictly positive after). The
faithful-mode agreement figures below are unaffected (they pass explicit
policies); suite re-validated at 207 passed and FRCC + NWPP production
outputs were redelivered.*

## Reference lineages

1. **Repo script's own ÷CIR output, no loadscaling, scale 1.0** — SRVC,
   SRTV, SRMV, SPP, AZNM, NWPP, NEISO, NYISO, MISO, CAISO (2021 ref).
   Every embodied copy-paste bug is reproduced by a documented
   faithful-mode reconstruction in the region's tests.
2. **KCL-KVL function variant: ÷CIR × global peak-pinning `loadscaling`** —
   FRCC (×0.8814), RFCE (×0.865687), RFCW (×0.8218).
3. **Negative controls** — CAISO 2019 `_NEW` CSV (raw-share B12 output,
   scale 0.3669 = Σ CIR²); NEISO boxnote-flagged file (not the reference).

## The matrix

| Region | Buses | National bus range | Structural (fresh) | Bus energy cons. (max err MW) | Reference & provenance verdict | Agreement (median rel. diff, per state) | Legacy bugs embodied in ref | Join | Tests |
|---|---|---|---|---|---|---|---|---|---|
| FRCC | 7,224 | 28,026–35,249 | ✅ | 2.8e-10 | P_Load_FRCC.csv 2024 = KCL-KVL fn variant, ÷CIR × loadscaling ≈0.8814 (FL-drop policy set) | GA 2.2e-05 / SC 6.7e-06 / FL 5.6e-04 (FL delta = different Florida.xls revision in KCL-KVL copy) | B3 (FL residual dropped), loadscaling (H5) | bus number | test_regression.py |
| NEISO | 3,370 | 132–3,501 | ✅ | 2.7e-11 | regenerated ÷CIR per-class output @ scale 1.0 (NOT the boxnote-flagged file) | 7e-06 × 6 states | none | bus number | test_wave4_nyseg.py |
| NYISO | 4,880 | 3,630–8,509 | ✅ | 1.6e-10 | regenerated ÷CIR per-class @ 0.9988 (B9 rank-1 signature ABSENT) | 1.25e-04 | none (B9 fixed before ref was made) | bus number | test_wave4_nyseg.py |
| MISO | 6,671 | 40,172–46,842 | ✅ | 1.2e-10 | ÷CIR per-class @ ~1.0 (not the raw B12 output) | IL/WI 7e-06, IA/MN 3e-05 | B8 (no bus column in ref CSV) | bus number (ref has none — positional per B8 handling) | test_wave4_nyseg.py |
| RFCW | 7,217 | 20,593–27,809 | ✅ | 1.4e-10 | KCL-KVL fn variant: mismapped class roles × loadscaling 0.8218 | IN 6e-06 / MI 8e-06 / OH 5.5e-05 (swapped-role faithful mode) | **B13** (com shape on res shares — see [RFCW_B13_notice.md](RFCW_B13_notice.md)), loadscaling | bus number | test_wave4_utility.py |
| CAISO | 8,034 | 66,869–74,902 | ✅ | 4.7e-10 | 2021 ref @ scale 1.0 authoritative; 2019 `_NEW` = B12 raw-share negative control (0.3669) | 6.9e-04 (2021 ref) | none in 2021 ref; B12 in 2019 ref | bus number | test_wave4_utility.py |
| SRVC | 6,340 | 14,061–20,400 | ✅ | 9.5e-11 | repo script ÷CIR, no loadscaling, raw CIR | DC/MY/VG 6e-06; WV 5.5e-06 (B6 reproduced); DL/NC @ raw-CIR sums 0.999639/0.999378 | **B6** (WV uses MD's CIR), zero-alpha NaN day (NC day 1) | bus number | test_wave4_south.py |
| SRTV | 4,451 | 35,424–39,874 | ✅ | 8.7e-11 | repo script ÷CIR @ 1.0 | AL 6.3e-06 (B14 shifted basis) / KY, TN 6.0e-06 / MS 7.6e-06 @ 0.999975 | **B14** (shifted headerless Birmingham restaurant as AL res-basis), zero-alpha NaN days | bus number | test_wave4_south.py |
| SRMV | 3,123 | 47,011–50,133 | ✅ | 6.2e-11 | repo script ÷CIR @ 1.0, RAW CIR | AR 7.5e-06 / MO 6.0e-06 / LA 6.1e-06 (raw-CIR reconstruction) | LA raw CIR sums to 0.902455 → ref leaks ~9.75% of LA trend+resid energy (B12/F3 family); production is energy-exact (+10.8% vs ref, by design) | bus number | test_wave4_south.py |
| SPP | 8,025 | 50,550–58,574 | ✅ | 4.0e-10 | repo script ÷CIR @ 1.0 | NB/SD/TX 7e-06; ND 6.6e-06 / OK 5.8e-06 / KS 6.6e-06 (faithful reconstructions; production diverges ND 8.8e-03, OK p99 2.5e-02, KS 2.2e-01 by design) | **B15** (ND fit on OK aggregates), **B16** (OK stale ND_CI_top), **B17** (KS ×1.127 energy leak) | bus number | test_wave4_west1.py |
| AZNM | 4,536 | 61,820–66,498 | ✅ | 5.1e-11 | repo script ÷CIR @ 1.0 | AZ/CO/NM/UT 7e-06; NV 2.6e-05 @ 0.999729 | none cross-state; ⚠ ref bus numbers are an OLDER revision (3,948/4,536 differ) | **ROW ORDER** — never join archived AZNM CSV by bus number | test_wave4_west1.py |
| NWPP | 2,977 | 58,605–61,779 | ✅ | 5.3e-11 | repo script ÷CIR @ 1.0 (MIXED archetype: ID/MT/WY NREL; OR/WA PG&E a1/a10/e1 incl. faithful e1 day-shift) | ID/MT/OR/WA 6e-06; WY 6.0e-06 (faithful; production 4.9e-02 by design) | **B18** (WY tiled from ID's stale day-365 Res_top); ⚠ older bus numbering (2,845/2,977 differ) | **ROW ORDER** | test_wave4_west2.py |
| RFCE | 5,218 | 8,663–13,880 | ✅ | 1.3e-10 | KCL-KVL fn variant: ÷CIR × loadscaling 0.865687 (peak 48,489 MW pinned on the bugged matrix), raw CIR | NJ 7.7e-06 / PN 6.5e-06 (faithful) | **B19** (PN trend uses NJ's CIR), loadscaling; NJ NaN days = 23-hour NaN-dropped fits (third NaN signature) | bus number | test_wave4_west2.py |

Totals: **72,066 load buses**; national numbering spans 13 disjoint
regional blocks consistent with the Steve-workbook Final National Bus Num
(H1/D13) — except the two ⚠ row-order regions, whose *archived references*
(not LoadSmith outputs) carry an older numbering revision.

## Reading the agreement column

- Medians at ~6–8e-06 are solver/CSV-precision level: the rebuild is exact
  up to lsqnonneg tolerance and 6-digit csvwrite rounding.
- Larger production-vs-reference deviations (SPP ND/OK/KS, NWPP WY, SRMV
  LA, RFCW all, FRCC FL) are **deliberate**: production fixes the
  registered bug; the faithful-mode reconstruction named in the row is
  what matches the reference, proving provenance. Each is pinned with
  headroom in the listed test file.
- Q references are compared statistically only (MATLAB `rand` was
  unseeded) — per-bus Q/P inside the legacy PF envelope; see H3.
- Isolated single-day deviations near data holes follow one of three NaN
  signatures (zero-alpha passthrough, repaired-hole interpolation,
  23-hour NaN-dropped fit) — all documented per region and whitelisted.

## Energy conservation statement (production mode)

With `shares="renormalized"` + energy-conserving residual policies +
`peak_scaling="none"`, every state's hourly class sum equals the raw state
load and every state's bus sum reproduces it to ≤ 5e-10 MW (fresh runs,
this page). MISO IA+MN conserve as a combine-group total (per-member split
is fixed-scale by design, B5/D1 notes). With `peak_scaling="kclkvl"` one
documented global factor per region scales P and Q (D16); conservation
then holds against the scaled totals (validated in the same fresh runs for
the delivered outputs).
