# Stage 6 — Bus Distribution & Reactive Power (`distribution.py`)

## Real power (decision D1: per-class everywhere)

For each state s with bus set B_s, class loads `L_c(t)` (stage 4/5 output),
and per-bus class shares `w[b, c]`:

```
P[b, t] = Σ_c  w[b, c] · L_c(t)          b ∈ B_s,  c ∈ {C, I, R}
```

`w` comes from the bus table (cols 24:26; CAISO 26:28), **renormalized at
ingestion so Σ_{b∈B_s} w[b,c] = 1 per class** (decision C4). This resolves
the two MATLAB conventions (flag F3):
- FRCC/CAISO/MISO_NEW: `P = BusDist[:,24] · L_C' + …` (raw shares)
- SRVC/RFCW: `P = (BusDist[:,24]/CIR_C) · L_C' + …` (shares ÷ state fraction)

With renormalized shares, state energy is conserved exactly:
`Σ_b P[b,t] = Σ_c L_c(t) = state_load(t)` (validation invariant).

Never implemented: the superseded total-broadcast form (`BusDist[:,24..26] ×
state_total`, the "all buses scale identically" defect — boxnotes, B9).

## Reactive power (decision D3 — NEW ranges, replaces MATLAB's)

Per-bus, per-class power factors drawn once per run from a seeded
`numpy.random.default_rng(seed)`:

| Class | MATLAB range | **LoadSmith range (D3)** |
|-------|--------------|--------------------------|
| Commercial | 0.95–0.98 | **0.98–0.99** |
| Industrial | 0.98–1.00 | **0.99–1.00** |
| Residential | 0.90–0.95 | **0.95–0.98** |

```
qf[b, c] = sqrt(1 − pf[b,c]²) / pf[b,c]          # fixes bug B2 (÷pfC typo)
Q[b, t]  = Σ_c  qf[b, c] · w[b, c] · L_c(t)
```

Q is always computed and written (user: "We definitely want Q_Load").
Draw order is fixed (regions alphabetical, states in config order, classes
C→I→R) so results are reproducible for a given seed. Seed lives in config
(default: 20260708) and is recorded in output metadata.

## MATLAB deviations fixed here

- B2: qfI/qfR divided by pfC — fixed (formula above).
- B9: NYISO used state total for all classes — per-class now.
- B8: MISO output lacked bus numbers — always included now.
- Dead in-loop fixed-pf `*_react` arrays (0.95/0.98/0.90) — not ported.

## Performance note

P and Q are rank-3 outer products: `P = W @ L.T` with W (n_bus×3),
L (8760×3) — one BLAS matmul per state (~7,000 × 8,760 doubles ≈ 490 MB
float64 per region). Compute per state, write incrementally; float32 option
if memory matters. No multiprocessing needed for this stage; the matmul is
the fast part. Region-level parallelism (13 independent regions) happens in
`core.py` via `concurrent.futures` when running `run_all()`.
