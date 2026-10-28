"""Smoothing placement research — NOT part of the pipeline.

Produces the numbers in docs/conversion_manual/SMOOTHING_PLACEMENT.md.
Run: .venv/Scripts/python scripts/research_smoothing_placement.py
(needs the migrated data/ store; ~2 min; prints per-state metrics).

Quantifies the wave-3 finding (multi-GW midnight kinks in the residential
class under residual-in-residential) and compares smoothing placements:

  post   : current experimental behavior — QP smoothing of the FINAL class
           loads (after residual assignment).
  pre    : QP smoothing of the FIT component only, residual recomputed
           against the smoothed fit and then assigned to residential
           (hourly state totals conserved exactly BY CONSTRUCTION).
  zerosum: QP variant that constrains each side's corrections to sum to
           zero across classes (shuffles load between classes; hourly
           totals unchanged) — solved with SLSQP per boundary; boundaries
           where the constrained problem is infeasible are skipped.
  bounded: post-placement QP with a box |x| <= cap * (local load scale),
           cap swept over {1%, 5%, 20%} — SLSQP.

Research script only: no library code is modified.
"""
from __future__ import annotations

import numpy as np
from scipy.optimize import minimize

from loadsmith.core import LoadSmith
from loadsmith.ingest import ParquetStore
from loadsmith.profile_calendar import day_type_calendar
from loadsmith.smoothing import smooth_class_loads, _qp_matrices, RAMP_OUT, RAMP_IN

REGION = "FRCC"
RES_COL = 2  # class_loads columns are [C, I, R]
CLASSES = ["C", "I", "R"]


def boundary_b(arr: np.ndarray, day: int) -> np.ndarray:
    """The 2k second-difference vector the QP sees at boundary `day` (1..364)."""
    a1 = (day - 1) * 24
    w = arr[a1:a1 + 48]
    b1 = w[24] - 2.0 * w[23] + w[22]
    b2 = w[25] - 2.0 * w[24] + w[23]
    return np.concatenate([b1, b2])


def kink_stats(arr: np.ndarray, tol: float = 1.0) -> dict:
    """Concave-midnight census of an (8760, k) matrix.

    Only counts MATERIAL concavity (second difference < -tol MW) so that
    float dust (~1e-12) left by exact-boundary QP solutions is not counted.
    """
    k = arr.shape[1]
    worst_day = -1
    n_concave = 0
    per_class_neg = np.zeros(k, dtype=int)
    per_class_worst = np.zeros(k)
    all_min = []
    worst = 0.0
    for day in range(1, 365):
        b = boundary_b(arr, day)
        mn = float(b.min())
        all_min.append(mn)
        bmat = b.reshape(2, k)
        if mn < -tol:
            n_concave += 1
            per_class_neg += (bmat < -tol).any(axis=0)
            if mn < worst:
                worst, worst_day = mn, day
        per_class_worst = np.minimum(per_class_worst, bmat.min(axis=0))
    return {
        "n_concave_boundaries(<-1MW)": n_concave,
        "worst_neg_2nd_diff_MW": worst,
        "worst_day": worst_day,
        "per_class_concave_counts": dict(zip(CLASSES[:k], per_class_neg.tolist())),
        "per_class_worst_MW": {c: round(float(v), 1)
                               for c, v in zip(CLASSES[:k], per_class_worst)},
        "median_min_b_MW": float(np.median(all_min)),
    }


def within_day_curvature_scale(arr: np.ndarray) -> float:
    """Median |second difference| away from day boundaries (context scale)."""
    total = arr.sum(axis=1)
    sd = total[2:] - 2 * total[1:-1] + total[:-2]
    hours = np.arange(1, 8759)
    interior = (hours % 24 >= 3) & (hours % 24 <= 20)
    return float(np.median(np.abs(sd[interior])))


def variant_metrics(orig: np.ndarray, sm: np.ndarray, y: np.ndarray) -> dict:
    """Compare a smoothed class-load matrix ``sm`` against the original ``orig``.

    Returns per-class and total energy deltas, the worst hourly deviation from
    the target total ``y``, the largest single correction, and residual-kink
    stats after smoothing — the numbers tabulated in SMOOTHING_PLACEMENT.md.
    """
    d = sm - orig
    tot = sm.sum(axis=1)
    return {
        "class_energy_delta_MWh": {c: float(d[:, i].sum()) for i, c in enumerate(CLASSES)},
        "total_energy_delta_MWh": float(d.sum()),
        "total_energy_rel": float(d.sum() / orig.sum()),
        "max_abs_hourly_total_dev_MW": float(np.abs(tot - y).max()),
        "max_abs_correction_MW": float(np.abs(d).max()),
        "residual_kinks_after": kink_stats(sm),
    }


def smooth_constrained(arr: np.ndarray, mode: str, cap_frac: float | None = None) -> np.ndarray:
    """Sequential boundary sweep like smooth_class_loads, but per-boundary QP
    solved with SLSQP under extra constraints. mode: 'zerosum' | 'bounded'."""
    out = arr.astype(np.float64, copy=True)
    k = out.shape[1]
    H, A = _qp_matrices(k)
    n = 2 * k
    skipped = 0
    for day in range(1, 365):
        b = boundary_b(out, day)
        if np.all(b >= 0.0):
            continue
        a1 = (day - 1) * 24
        cons = [{"type": "ineq", "fun": lambda x, b=b: b - A @ x}]  # A x <= b
        if mode == "zerosum":
            cons.append({"type": "eq", "fun": lambda x: x[:k].sum()})
            cons.append({"type": "eq", "fun": lambda x: x[k:].sum()})
            obj = lambda x: 0.5 * float(x @ x)
            jac = lambda x: x
            bounds = None
        elif mode == "bounded":
            local = float(np.abs(out[a1:a1 + 48].sum(axis=1)).max())
            cap = cap_frac * local
            bounds = [(-cap, cap)] * n
            obj = lambda x: 0.5 * float(x @ H @ x) + 5e-10 * float(x @ x)
            jac = lambda x: H @ x + 1e-9 * x
        else:
            raise ValueError(mode)
        res = minimize(obj, np.zeros(n), jac=jac, bounds=bounds,
                       constraints=cons, method="SLSQP",
                       options={"maxiter": 200, "ftol": 1e-12})
        ok = res.success and np.all(A @ res.x <= b + 1e-6 * max(1.0, np.abs(b).max()))
        if not ok:
            skipped += 1  # constrained problem infeasible -> leave boundary as-is
            continue
        x = res.x
        out[a1 + 19:a1 + 24] += np.outer(RAMP_OUT, x[:k])
        out[a1 + 24:a1 + 29] += np.outer(RAMP_IN, x[k:])
    out_stats = {"skipped_infeasible": skipped}
    return out, out_stats


def main() -> None:
    """Run the smoothing-placement study for one region and print the metrics.

    Fits the region under production policies, applies each candidate smoothing
    variant, and reports :func:`variant_metrics` for each so the placement
    trade-offs can be compared (background for the pending smoothing decision).
    """
    smith = LoadSmith("data")
    cfg = smith.region_config(REGION)
    store = ParquetStore("data")
    day_types = day_type_calendar(cfg.calendar_year)[:365]
    fits = smith._fit_all_states(cfg, store, day_types, None)  # production policies

    for abbrev, fit in fits.items():
        cl = fit.class_loads                      # final classes (resid in R)
        y = cl.sum(axis=1)                        # == state load (residential policy)
        fit_only = cl.copy()
        fit_only[:, RES_COL] -= fit.residuals     # fit component, pre-residual

        print(f"\n================ {REGION}/{abbrev} ================")
        print(f"peak load {y.max():,.0f} MW; within-day curvature scale "
              f"{within_day_curvature_scale(cl):,.1f} MW (median |2nd diff|)")
        print("\n-- kink census, FINAL classes (unsmoothed, what 'qp' sees):")
        print(kink_stats(cl))
        print("-- kink census, FIT component only (pre-residual):")
        print(kink_stats(fit_only))

        # post: current experimental behavior
        post = smooth_class_loads(cl)
        print("\n-- POST (current qp placement):")
        print(variant_metrics(cl, post, y))

        # pre: smooth fit, re-derive residual, assign to residential
        fit_s = smooth_class_loads(fit_only)
        pre = fit_s.copy()
        pre[:, RES_COL] += y - fit_s.sum(axis=1)
        print("\n-- PRE (smooth fit component, residual reassigned):")
        print(variant_metrics(cl, pre, y))

        # zerosum: class-shuffle corrections, totals untouched
        zs, zstats = smooth_constrained(cl, "zerosum")
        print(f"\n-- ZEROSUM (post placement, per-side corrections sum to 0) "
              f"{zstats}:")
        print(variant_metrics(cl, zs, y))

        # bounded: cap sweep
        for cap in (0.01, 0.05, 0.20):
            bd, bstats = smooth_constrained(cl, "bounded", cap_frac=cap)
            print(f"\n-- BOUNDED cap={cap:.0%} of local total {bstats}:")
            print(variant_metrics(cl, bd, y))


if __name__ == "__main__":
    main()
