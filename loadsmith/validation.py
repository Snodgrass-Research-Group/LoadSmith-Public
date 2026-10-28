"""Stage 7b — validation: structural invariants + MATLAB reference regression.

Structural (always available, no reference data needed): energy conservation
(bus sums == class sums == state load, when the run's policies conserve
energy), non-negativity, Q/P envelope, shapes/uniqueness, midnight convexity
when smoothing ran.

Regression (hook H3): reference P/Q CSVs live in the EXTERNAL UW-Madison
Synthetic Load folder (locations.reference_dir(region)); the in-repo
validation/reference_outputs/<REGION>/ folder is checked FIRST as an
override for small committed excerpts. Reference quirks (surveyed
2026-07-09): column 1 is the NATIONAL bus number everywhere; the 2024 FRCC
P file has a "bus Num" header row, most others have none (the loader
sniffs); NYISO/P_Load_MISO_NEW.csv is a stray MISO file with no bus column
(ignored); Q is compared statistically only (MATLAB rand was unseeded).

Spec: docs/conversion_manual/algorithms/07_outputs_validation.md.
Implemented.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

from loadsmith import locations
from loadsmith.config import PF_RANGES, RegionConfig, Role

if TYPE_CHECKING:  # imported lazily at runtime to avoid a core<->validation cycle
    from loadsmith.core import RunResult
    from loadsmith.fitting import FitResult

# Largest possible qf given the D3 ranges: the residential floor pf = 0.95.
_QF_MAX = float(np.sqrt(1.0 - 0.95**2) / 0.95)  # ~0.3287


class Validator:
    """Stage-7b checks: structural invariants and reference-CSV regression.

    :meth:`structural` needs no external data and is what ``run(validate=True)``
    calls. Reference regression reads P/Q CSVs from ``reference_dir`` (default:
    the external UW-Madison folder via :mod:`loadsmith.locations`), preferring
    an in-repo excerpt under ``repo_override_dir`` when one is present.
    """

    def __init__(
        self,
        reference_dir: str | Path | None = None,   # default: external UW folder
        repo_override_dir: str | Path = "validation/reference_outputs",
    ) -> None:
        self._reference_root = Path(reference_dir) if reference_dir else None
        self.repo_override_dir = Path(repo_override_dir)

    # ------------------------------------------------------------------ #
    # Structural invariants
    # ------------------------------------------------------------------ #

    def structural(
        self,
        region: str,
        state_loads: dict[str, np.ndarray],
        fits: dict[str, FitResult],
        result: RunResult,
        bus_state_codes: np.ndarray,
        config: RegionConfig,
        *,
        smoothing: str,
        shares: str,
        residual_override: str | None,
    ) -> dict:
        """Run all invariant checks; return a JSON-serializable report dict.

        Every check records pass/fail + the measured number; ``ok`` is the
        conjunction of all applicable checks. Checks that don't apply to the
        run's policies (e.g. energy conservation under ``shares="raw"`` or
        ``residual="drop"``) are reported as skipped with the reason.
        """
        checks: dict[str, dict] = {}

        def add(name: str, ok: bool | None, detail: dict) -> None:
            checks[name] = {"ok": ok, **detail}

        p, q = result.p_load, result.q_load
        n_bus = p.shape[0]

        add("shapes", p.shape == (n_bus, 8760) and q.shape == (n_bus, 8760)
            and result.national_bus_numbers.shape == (n_bus,),
            {"n_bus": n_bus})
        add("finite", bool(np.isfinite(p).all() and np.isfinite(q).all()), {})
        # Small negatives are MATLAB-faithful: basis columns are DEMEANED, so
        # class loads (hence bus loads) can dip slightly below zero in hours
        # where a shape term outweighs the trend (FRCC production run:
        # min -0.56 MW vs 396 MW peak bus load). Only flag LARGE negatives:
        # beyond 1% of the peak bus load something is genuinely wrong.
        neg_floor = -1e-2 * float(np.abs(p).max())
        add("p_no_large_negatives", bool(p.min() >= neg_floor),
            {"min_mw": float(p.min()), "floor_mw": neg_floor})
        add("q_no_large_negatives", bool(q.min() >= _QF_MAX * neg_floor),
            {"min_mvar": float(q.min())})
        add("bus_numbers_unique",
            len(np.unique(result.national_bus_numbers)) == n_bus, {})

        # Q/P envelope in magnitude: per-class qf is bounded by the
        # residential-floor qf, so |Q| <= QF_MAX * |P| wherever the class
        # contributions don't cancel. Near P ~ 0 (one class negative, another
        # positive) the ratio is unbounded while the MAGNITUDES stay tiny, so
        # allow a small absolute slack instead of a pure ratio. Slack sized
        # by the worst cancellation observed across the 13 validated regions:
        # NWPP/WY's residential class is negative on 138 h (large negative
        # residuals under the "residential" policy, small class), max excess
        # 0.727 Mvar — 1.0 covers it with margin while real
        # per-class qf violations still trip it (they scale with bus MW).
        excess = np.abs(q) - _QF_MAX * np.abs(p)
        add("q_envelope", bool(excess.max() <= 1.0),
            {"max_excess_mvar": float(excess.max()), "qf_max": _QF_MAX,
             "abs_slack_mvar": 1.0})

        # Per-state energy conservation. Applies only when the residual
        # policy conserves energy AND smoothing didn't modify the class
        # loads (the QP intentionally changes totals at corrected midnights).
        conserving_fit = all(
            (residual_override or s.residual) in ("residential", "proportional")
            for s in config.states) and smoothing == "none"
        skip_reason = ("residual policy drops energy"
                       if smoothing == "none" else
                       "smoothing='qp' modifies totals at corrected midnights")
        for state in config.states:
            abbrev = state.abbrev
            load = state_loads[abbrev]
            cl = fits[abbrev].class_loads
            class_sum_err = float(np.abs(cl.sum(axis=1) - load).max())
            if state.combine_group is not None:
                # Combine groups (MISO IA+MN): fit_combined_states de-combines
                # the class columns with FIXED per-class scales, so a member
                # state's hourly class sum differs from its raw load BY DESIGN
                # (MATLAB identical). Only the group total is conserved —
                # checked below as class_conservation_group_<name>.
                add(f"class_conservation_{abbrev}", None,
                    {"max_abs_err_mw": class_sum_err,
                     "skipped": f"combine_group {state.combine_group!r} "
                                "conserves only the group total"})
            else:
                add(f"class_conservation_{abbrev}",
                    (class_sum_err < 1e-6) if conserving_fit else None,
                    {"max_abs_err_mw": class_sum_err,
                     **({} if conserving_fit else {"skipped": skip_reason})})

            mask = bus_state_codes == state.bus_state_code
            bus_sum = p[mask].sum(axis=0)
            # With peak_scaling="kclkvl" every bus load carries one global
            # factor (metadata peak_scale_factor); conservation then holds
            # against the SCALED class totals.
            scale = float(result.metadata.get("peak_scale_factor", 1.0))
            if shares == "renormalized":
                bus_err = float(np.abs(bus_sum - scale * cl.sum(axis=1)).max())
                add(f"bus_conservation_{abbrev}", bus_err < 1e-6 * max(1.0, scale),
                    {"max_abs_err_mw": bus_err, "n_buses": int(mask.sum()),
                     "peak_scale_factor": scale})
            else:
                ratio = float(bus_sum.sum() / (scale * cl.sum()))
                add(f"bus_conservation_{abbrev}", None,
                    {"skipped": "shares='raw' reproduces legacy B12 deficit",
                     "delivered_fraction": ratio, "n_buses": int(mask.sum())})

        # Combine-group totals: sum of member class loads must reproduce the
        # sum of member state loads (the invariant the combined fit DOES
        # guarantee; per-member checks are skipped above).
        combine_groups: dict[str, list] = {}
        for state in config.states:
            if state.combine_group is not None:
                combine_groups.setdefault(state.combine_group, []).append(state)
        for gname, members in combine_groups.items():
            g_load = sum(state_loads[m.abbrev] for m in members)
            g_cl = sum(fits[m.abbrev].class_loads for m in members)
            g_err = float(np.abs(g_cl.sum(axis=1) - g_load).max())
            add(f"class_conservation_group_{gname}",
                (g_err < 1e-6) if conserving_fit else None,
                {"members": [m.abbrev for m in members],
                 "max_abs_err_mw": g_err,
                 **({} if conserving_fit else {"skipped": skip_reason})})

        # Midnight convexity of the (smoothed) class profiles.
        if smoothing == "qp":
            worst = np.inf
            for fit in fits.values():
                cl = fit.class_loads
                for d in range(1, 365):
                    h = 24 * d
                    b1 = cl[h] - 2 * cl[h - 1] + cl[h - 2]
                    b2 = cl[h + 1] - 2 * cl[h] + cl[h - 1]
                    worst = min(worst, float(b1.min()), float(b2.min()))
            add("midnight_convexity", worst >= -1e-6, {"worst_second_diff": worst})
        else:
            add("midnight_convexity", None, {"skipped": "smoothing='none'"})

        applicable = [c["ok"] for c in checks.values() if c["ok"] is not None]
        return {"region": region, "ok": bool(all(applicable)), "checks": checks}

    # ------------------------------------------------------------------ #
    # Reference regression
    # ------------------------------------------------------------------ #

    def find_reference(self, region: str, kind: str = "P") -> Path | None:
        """Locate the reference CSV: repo override first, then the external
        UW folder; None if neither exists (tests skip the region)."""
        name = f"{kind}_Load_{region}.csv"
        override = self.repo_override_dir / region / name
        if override.exists():
            return override
        root = self._reference_root or locations.reference_dir()
        external = root / region / name
        return external if external.exists() else None

    @staticmethod
    def load_reference(path: Path) -> tuple[np.ndarray, np.ndarray]:
        """Read a reference CSV -> (bus_numbers (n,), values (n, 8760)).

        Sniffs an optional header line (the 2024 FRCC P file starts with
        'bus Num'); requires a bus-number first column (files without one,
        like the stray MISO copy, are not loadable here).
        """
        from pyarrow import csv as pacsv

        with open(path, "rb") as f:
            first = f.readline().decode("ascii", "replace")
        has_header = not first.split(",", 1)[0].strip().replace(".", "").isdigit()
        table = pacsv.read_csv(
            path,
            read_options=pacsv.ReadOptions(autogenerate_column_names=not has_header),
        )
        arr = np.column_stack([c.to_numpy() for c in table.columns]).astype(np.float64)
        bus = arr[:, 0]
        if not np.allclose(bus, np.round(bus)):
            raise ValueError(f"{path}: first column is not integer bus numbers")
        if arr.shape[1] != 8761:
            raise ValueError(f"{path}: expected 8761 columns, got {arr.shape[1]}")
        return bus.astype(np.int64), arr[:, 1:]

    def against_reference(
        self,
        region: str,
        p_load: np.ndarray,
        national_bus_numbers: np.ndarray,
        *,
        kind: str = "P",
    ) -> dict:
        """Tolerance comparison vs the reference CSV, joined on national bus
        number (never row order). Returns a stats report; raises FileNotFoundError
        if no reference exists (tests convert that to a skip)."""
        path = self.find_reference(region, kind)
        if path is None:
            raise FileNotFoundError(f"no {kind} reference for {region}")
        ref_bus, ref_vals = self.load_reference(path)

        ours = {int(b): i for i, b in enumerate(national_bus_numbers)}
        common = [(ours[int(b)], j) for j, b in enumerate(ref_bus) if int(b) in ours]
        if not common:
            raise ValueError(f"{region}: no common bus numbers with {path.name}")
        oi = np.array([c[0] for c in common])
        rj = np.array([c[1] for c in common])
        mine = p_load[oi]
        theirs = ref_vals[rj]

        diff = mine - theirs
        denom = np.maximum(np.abs(theirs), 1e-6)
        rel = np.abs(diff) / denom
        return {
            "region": region,
            "kind": kind,
            "reference": str(path),
            "n_reference_buses": int(len(ref_bus)),
            "n_matched_buses": int(len(common)),
            "energy_ratio_ours_over_ref": float(mine.sum() / theirs.sum()),
            "rel_diff": {
                "median": float(np.median(rel)),
                "p95": float(np.percentile(rel, 95)),
                "p99": float(np.percentile(rel, 99)),
                "max": float(rel.max()),
                "frac_within_1e-6": float((rel <= 1e-6).mean()),
                "frac_within_1e-3": float((rel <= 1e-3).mean()),
                "frac_within_1e-2": float((rel <= 1e-2).mean()),
            },
        }
