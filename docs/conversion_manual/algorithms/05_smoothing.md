# Stage 5 — Day-Boundary Smoothing (`smoothing.py`)

## What `smoothprofile.m` was designed to do

The daily fits are independent, so consecutive days can join with a jump at
midnight. For an (N×3) hours-by-class matrix, for each consecutive day pair
(48-h window), add a quadratic correction that pivots at hour 20 of day 1 and
hour 5 of day 2:

```
z[h20..h24, c] = X[c]   * [0,1,4,9,16]/16     (c = 1..3, end of day 1)
z[h25..h29, c] = X[c+3] * [16,9,4,1,0]/16     (start of day 2)
```

The 6-vector X solves the QP:

```
min  ½ Xᵀ H X          H = blkdiag(ones(3,3), ones(3,3))
                        (⇒ objective = ½[(X1+X2+X3)² + (X4+X5+X6)²]
                         = minimize the squared net change in TOTAL load
                         on each side of midnight)
s.t. A X ≤ b            A = (2 − 9/16)·I₆ with A[i, i+3] = A[i+3, i] = −1
                        b = [d²₁(c); d²₂(c)]  the two centered second-
                        difference estimates around midnight per class:
                        d²₁ = p[25] − 2p[24] + p[23]
                        d²₂ = p[26] − 2p[25] + p[24]
```

i.e. the correction must make the load curve convex (2nd derivative ≥ 0)
across midnight while changing total energy as little as possible. Windows
are processed sequentially (day pair 1-2, then 2-3 using already-corrected
values, …), so the operation is order-dependent — replicate the sequential
sweep.

If b ≥ 0 already (curve already convex at that boundary), X = 0 is optimal —
most boundaries need no correction.

## Critical MATLAB finding (bug B1)

Every script calls `smoothprofile(P_load(i,:))` with a 1×8760 **row** vector;
the guard `if size(pin,1) < 48` then returns the input unchanged. **Smoothing
never actually ran** — all MATLAB reference outputs are unsmoothed.

## Python design (decisions C2, C3)

- Apply smoothing to the state-level (8760×3) `ClassLoads` BEFORE bus
  distribution (the function's evident design intent — it expects exactly 3
  channels). Since every bus profile is a nonnegative combination of the 3
  class profiles, convexity at midnight is inherited by all bus profiles.
  This is also ~2,500× cheaper than per-bus smoothing (3 vs 7,000 channels).
- `smoothing="none"` (config) skips the stage → matches MATLAB outputs for
  regression validation. Default TBD after comparing smoothed vs reference.
- Solver: purpose-written dense active-set QP for this 6-var/6-constraint
  structure in pure numpy (no new dependency; scipy-only fallback via
  `scipy.optimize.minimize(method='SLSQP')` for cross-checking in tests).
  Fast path: if `b >= 0`, return X = 0 immediately.
- Unit tests: (a) X=0 when convex; (b) constraint satisfaction and objective
  optimality vs SLSQP on random negative-b cases; (c) idempotence-ish sweep
  behavior on a synthetic year; (d) energy-change minimality.
