# Stage 4 — Daily NNLS Fit & C/I/R Split (`fitting.py`)

## What MATLAB does (per state, per day d = 1..365)

```
y      = state_load[24 hours of day d]          # MW
Base   = stage-3 basis (24 × 4): [ones | res_shape | ci_shape1 | ci_shape2]
alpha  = lsqnonneg(Base, y)                      # non-negative LS, alpha >= 0
fit    = Base @ alpha
Trend  = Base[:,0] * alpha[0]                    # flat base-load component
Res    = Base[:,res_col] * alpha[res_col]        # residential shape component
CI     = Base[:,ci_cols] @ alpha[ci_cols]        # com/ind shape component
resid  = y - fit
```

Split into classes using state CIR fractions `(C, I, R)`, sum = 1:

```
load_C = Trend*C + CI * C/(C+I)
load_I = Trend*I + CI * I/(C+I)
load_R = Trend*R + Res + resid          # residual entirely to residential
```

Rationale: the flat trend is class-agnostic → split by CIR shares; the
commercial/industrial shape energy is split C:I; the residential shape and
the unexplained residual go to residential (residential drives most daily
variation). With residual included, `load_C+load_I+load_R == y` exactly —
**energy conservation** (validation invariant).

## Region deviations (all captured in config, see regions/)

- **FRCC (B3)**: `; +` typo drops the residual → classes don't sum to the
  state load. Fixed by default; `residual="drop"` reproduces MATLAB.
- **FRCC AE variant** (comparison-only): residual split by CIR across all
  three classes (`residual="proportional"`).
- **MISO IA+MN**: IA and MN are fit as one combined series
  (`IAMN = IA + MN`, CIR = load-weighted average of the two states'
  CIR), then de-combined per class:
  `scale_c = IA_CIR[c]*IA_total / (IA_CIR[c]*IA_total + MN_CIR[c]*MN_total)`,
  `IA_load[:,c] = IAMN_load[:,c]*scale_c`, `MN = IAMN - IA`.
- **SRVC (B6)**: WV trend term mistakenly uses Maryland's R fraction — fixed.
- **SRVC residual**: split by raw CIR across all three classes (proportional
  policy) rather than all-to-residential — honor per-region config default.

## Python design

```python
@dataclass
class FitResult:
    class_loads: np.ndarray   # (8760, 3) [C, I, R] MW
    alphas:      np.ndarray   # (365, 4)  fitted coefficients
    residuals:   np.ndarray   # (8760,)   y - fit, for error diagnostics

def fit_state(load, basis_source, calendar, cir,
              residual: Literal["residential","proportional","drop"] = ...,
              ) -> FitResult
```

- `scipy.optimize.nnls` (active-set Lawson–Hanson) replaces `lsqnonneg` —
  same algorithm; agreement to ~1e-12 on well-conditioned 24×4 systems.
- 365 independent 24×4 NNLS solves ≈ milliseconds; the day loop is a plain
  Python loop (no need to parallelize this stage).
- Diagnostics: per-day relative error `resid/y` (the MATLAB error histograms)
  exposed via `FitResult` for the optional plotting helpers (C1).
