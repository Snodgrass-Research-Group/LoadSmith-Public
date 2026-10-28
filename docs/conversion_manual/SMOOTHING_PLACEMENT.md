# Smoothing placement research — options for the smoothing decision

*2026-07-10. Investigates where day-boundary smoothing belongs before `smoothing="qp"` can graduate
from experimental. **No defaults were changed** — production remains
`smoothing="none"`. Reproduce with `scripts/research_smoothing_placement.py`
(research-only, not part of the pipeline).*

## 1. The problem, quantified (FRCC, the validated pilot)

The per-day NNLS fits are independent, so the fitted class profiles jump at
midnight; the fit residual (assigned to the residential class under the
production policy) absorbs the opposite jump. Census of **material concave
midnights** (centered second difference < −1 MW across the boundary, the
quantity the QP constrains), unsmoothed production class loads:

| State | peak MW | within-day curvature scale¹ | concave boundaries (of 364) | worst per class C / I / R (MW) |
|---|---|---|---|---|
| FL | 48,218 | 531 | 331 | −4,554 / −788 / **−19,562** |
| GA | 35,381 | 259 | 340 | −2,526 / −1,679 / **−23,118** |
| SC | 16,943 | 162 | 321 | −902 / −1,092 / −1,677 |

¹ median |second difference| away from boundaries — the "normal" curvature.

Two facts frame everything below. (a) Concavity at midnight is **near
universal** (~90% of boundaries), not an occasional artifact; the multi-GW
cases are the tail, and they sit **in the residential class**, 40–90× the
normal curvature scale. (b) The fit component *alone* is far better behaved
(worst R-column kink −5.6 GW FL / −2.0 GW GA): the residual contributes the
bulk of the pathological kinks.

**The conservation identity is the crux**: Σ_classes = state load, hour by
hour. The classes' second differences must sum to the (small, real) curvature
of the state load, so a large negative curvature in one class can only be
(i) paid for by changing the total — distortion — or (ii) moved to another
class, never removed, unless the fit itself changes.

## 2. Variants measured

All variants keep the existing QP machinery (quadratic ramp corrections over
the 5 hours on each side of midnight; sequential sweep). Metrics on FRCC:

| Variant | worst remaining kink (FL/GA/SC, MW) | max hourly total deviation (MW) | annual energy error (rel) |
|---|---|---|---|
| **none** (production default) | −19,562 / −23,118 / −1,677 | 0 | 0 |
| **post** — current `"qp"`: smooth final classes | 0 / 0 / 0 | **17,977 / 19,529 / 2,529** | **−1.3e-3 / −5.9e-4 / −1.1e-4** |
| **pre** — smooth FIT component, then re-derive the residual against the smoothed fit and assign to residential | −20,060 / −22,434 / −2,039 (all in R; **C and I fully convex**) | ~1e-12 (exact) | ~1e-17 (exact) |
| **zero-sum** — post placement, per-side corrections constrained to sum to 0 across classes | ≈ unchanged (infeasible at 61–75% of boundaries) | exact | exact |
| **bounded** — post placement, box \|x\| ≤ 5% of local total (skip if infeasible) | −19,562 / −23,118 / −1,677 (the big ones are exactly the infeasible ones) | 234 / 80 / 57 | ≤ 3e-6 |

Reading of each row:

- **post (current experimental)** is the only variant that fully convexifies —
  and it is disqualified by the cost: corrections up to ~18–20 GW at single
  hours (37–55% of state peak) and up to 0.13% annual energy loss. This
  confirms the wave-3 verdict with hard numbers; `"qp"` must not become the
  default in its current placement.
- **pre** conserves hourly state totals **exactly by construction** (the
  residual is recomputed against the smoothed fit, so the sum telescopes back
  to the state load) and cleanly convexifies the C and I classes. But the
  reassigned residual re-imports the kink into the residential class — the
  worst midnights are unchanged or marginally worse (FL −19.6 → −20.1 GW).
  Class annual energies shift ≤ ~0.015% (an honest reallocation; the split
  is a modeling estimate). Cheap to implement: `FitResult` already carries
  `residuals`, so this is ~6 lines in `core.run`.
- **zero-sum** (move curvature between classes instead of creating/destroying
  load) is a dead end: within the ±5-hour ramp correction space the shuffle
  is infeasible at most boundaries — the headroom simply isn't there.
- **bounded** fixes the many small kinks and leaves precisely the
  pathological ones (they are infeasible under any sane cap) — backwards
  relative to the motivation, since the multi-GW corners are what a
  downstream dynamics user would object to.

## 3. Options for the user decision (D-item candidate)

- **Option 0 — keep `smoothing="none"` as the production default
  (recommended).** Every published MATLAB output is unsmoothed (B1), all 13
  reference validations were run unsmoothed, and every measured alternative
  either distorts totals (post) or does not remove the artifact that matters
  (pre/bounded/zero-sum). The kinks are a property of the *fitting
  algorithm* (independent day fits + residual policy), faithfully
  reproduced.
- **Option 1 — re-home `"qp"` to the pre-residual placement** (keep it
  experimental/off by default). Strictly dominates the current placement:
  exact conservation, C/I convex, same code path. Worth doing if `"qp"` is
  to be kept at all; it makes the switch *safe* but only partially
  effective (residential keeps the tail kinks).
- **Option 2 — fix the cause: continuity-regularized fitting.** Add a
  day-to-day coupling to the NNLS stage (penalize ‖α_d − α_{d−1}‖, or
  constrain fit continuity at midnight), so the fit — and therefore the
  residual — stops jumping. This is the only route that can actually remove
  the residential kinks while conserving totals. It is an algorithm change:
  ClassLoads move everywhere (not just 10 hours per boundary), reference
  regressions would need a switch, and the fit-quality/validation trade-off
  needs its own study. Do not start without a user decision.

## 4. Provenance

Method and numbers: `scripts/research_smoothing_placement.py` on the
migrated FRCC store (production fit policies, `residual="residential"` for
all three states). Context: bug B1 (MATLAB smoothing never ran), decision C2
(smoothing operates on state class profiles), `core.run` docstring.
