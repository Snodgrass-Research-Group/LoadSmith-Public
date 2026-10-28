"""LoadSmith orchestrator — runs the 7-stage pipeline for one or all regions.

This is deliberately the THINNEST module: all algorithms live in the stage
modules (docs/conversion_manual/architecture.md §1); this file only wires
them per the data contracts in HOOKS.md §2.

Results are ALWAYS returned in memory as a :class:`RunResult` (decision D14);
file output is optional (``formats``). Downstream Python (e.g. a future port
of the KCL-KVL grid generator's CreateLoadScenarios) should consume RunResult
directly instead of re-parsing CSVs.

Run switches resolve from ``loadsmith.toml`` (see loadsmith/settings.py);
every ``run()`` keyword overrides its settings-file value.

MATLAB-comparison mode (validation against the legacy reference CSVs)::

    smith.run("FRCC", smoothing="none", residual="drop", shares="raw",
              peak_scaling="none", write_csv_header=False)

``shares="raw"`` reproduces legacy bug B12 (raw xlsx share columns sum to
the CIR fraction, so bus loads under-deliver state energy); the production
default ``"renormalized"`` conserves energy exactly. The published 2024
reference outputs correspond to ``shares="renormalized"`` +
``peak_scaling="kclkvl"`` (with the FL residual dropped — B3).

Implemented (with settings and peak scaling).
"""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import numpy as np
import pandas as pd

from loadsmith.basis import BasisSource, NRELAggregateBasis, NYSEGBasis, UtilityBasis
from loadsmith.config import (
    DEFAULT_SEED,
    BasisKind,
    RegionConfig,
    ResidualPolicy,
    SmoothingPolicy,
    StateConfig,
)
from loadsmith.distribution import distribute, draw_power_factors, reactive_power
from loadsmith.fitting import FitResult, fit_combined_states, fit_state
from loadsmith.ingest import ParquetStore
from loadsmith.outputs import OutputFormat, OutputWriter
from loadsmith.profile_calendar import day_type_calendar
from loadsmith.smoothing import smooth_class_loads

SharesMode = Literal["renormalized", "raw"]

_SHARE_COLS: dict[SharesMode, list[str]] = {
    "renormalized": ["share_c", "share_i", "share_r"],
    "raw": ["raw_share_c", "raw_share_i", "raw_share_r"],
}


@dataclass
class RunResult:
    """One region's synthesized loads, held in memory (decision D14).

    Bus order is identical across all arrays (row i = same bus everywhere)
    and matches the region's bus-table order. ``p_load``/``q_load`` are dense
    float64 numpy arrays — the cheapest way to hand ~500 MB of hourly data to
    another Python stage without copies; use :meth:`p_frame`/:meth:`q_frame`
    only where a labeled pandas DataFrame is genuinely needed.
    """

    region: str
    national_bus_numbers: np.ndarray   # (n_bus,) int — output column 1 (D13)
    regional_bus_numbers: np.ndarray   # (n_bus,) int — region-local numbers
    p_load: np.ndarray                 # (n_bus, 8760) float64 MW
    q_load: np.ndarray                 # (n_bus, 8760) float64 Mvar
    metadata: dict = field(default_factory=dict)
    written_files: dict[str, Path] = field(default_factory=dict)  # {} if formats=()
    validation_report: dict = field(default_factory=dict)

    def p_frame(self) -> pd.DataFrame:
        """P as a DataFrame: 'bus Num' + h0001..h8760 (reference CSV layout)."""
        from loadsmith.outputs import to_output_frame

        return to_output_frame(self.national_bus_numbers, self.p_load)

    def q_frame(self) -> pd.DataFrame:
        """Q as a DataFrame, same layout as :meth:`p_frame`."""
        from loadsmith.outputs import to_output_frame

        return to_output_frame(self.national_bus_numbers, self.q_load)

    def as_matrices(self) -> tuple[np.ndarray, np.ndarray]:
        """(P, Q) with the national bus number prepended as column 0 —
        the exact matrix shape the KCL-KVL MATLAB consumer expects from
        MakeLoadProfiles_<REGION> (it strips column 1 itself)."""
        bus = self.national_bus_numbers.astype(np.float64)[:, None]
        return np.hstack([bus, self.p_load]), np.hstack([bus, self.q_load])


class LoadSmith:
    """Synthesize hourly bus-level P/Q load profiles for EPIGRIDS regions.

    Parameters
    ----------
    store:
        Path to the parquet data store produced by ``scripts/migrate_data.py``
        (schema: HOOKS.md §3). LoadSmith never parses Excel/.mat at runtime.
    output_dir:
        Where ``outputs/<REGION>/`` result folders are written (when file
        formats are requested).
    seed:
        RNG seed for per-bus power factors (D3). Fixed default so runs are
        reproducible; recorded in run metadata.
    """

    def __init__(
        self,
        store: str | Path | None = None,
        output_dir: str | Path | None = None,
        seed: int | None = None,
        settings: "Settings | str | Path | None" = None,
    ) -> None:
        from loadsmith.settings import Settings, load_settings

        if isinstance(settings, Settings):
            self.settings = settings
        else:
            self.settings = load_settings(settings)  # None -> loadsmith.toml or defaults
        self.store_path = Path(store if store is not None else self.settings.store)
        self.output_dir = Path(
            output_dir if output_dir is not None else self.settings.output_dir)
        self.seed = seed if seed is not None else self.settings.seed

    # ------------------------------------------------------------------ #

    def run(
        self,
        region: str,
        *,
        formats: Collection[OutputFormat] | None = None,
        smoothing: SmoothingPolicy | None = None,
        residual: ResidualPolicy | None = None,
        shares: SharesMode | None = None,
        peak_scaling: Literal["none", "kclkvl"] | None = None,
        write_csv_header: bool | None = None,
        validate: bool | None = None,
    ) -> RunResult:
        """Run the full pipeline for one region (e.g. ``"FRCC"``).

        Every ``None`` keyword resolves from the settings file
        (``loadsmith.toml`` -> ``[regions.<NAME>]`` -> ``[run]`` -> built-in
        defaults; see loadsmith/settings.py). ``formats=()`` skips ALL file
        output — the RunResult carries the arrays for direct in-memory
        hand-off (D14). See the module docstring for MATLAB-comparison mode.

        ``smoothing`` defaults to ``"none"`` (matching every MATLAB output
        ever produced — the legacy smoothing loop was a no-op, bug B1).
        ``"qp"`` is EXPERIMENTAL: on real class loads the daily-independent
        fits put multi-GW kinks at some midnights (the residual lands in the
        residential class), and enforcing convexity there requires
        correspondingly large corrections that distort total energy (wave-3
        finding, 2026-07-09; quantified on FRCC 2026-07-10 — corrections up
        to ~20 GW/hour, 0.13% annual energy loss). Placement research and
        the option space for the pending user decision:
        docs/conversion_manual/SMOOTHING_PLACEMENT.md.

        ``peak_scaling`` (decision D16, hook H5): ``"none"`` conserves the
        fitted state energies exactly; ``"kclkvl"`` rescales P and Q by one
        global factor so the region's coincident system peak equals the sum
        of the bus table's per-state peak loads (col 16) — the KCL-KVL
        `loadscaling` step present in the published 2024 reference outputs.
        """
        cfg = self.region_config(region)
        region = cfg.name
        s = self.settings.for_region(region)
        formats = tuple(s.formats) if formats is None else tuple(formats)
        smoothing = smoothing if smoothing is not None else s.smoothing
        shares = shares if shares is not None else s.shares
        peak_scaling = peak_scaling if peak_scaling is not None else s.peak_scaling
        write_csv_header = (write_csv_header if write_csv_header is not None
                            else s.csv_header)
        validate = validate if validate is not None else s.validate
        if residual is None and s.residual:
            residual = s.residual  # type: ignore[assignment]
        if shares not in _SHARE_COLS:
            raise ValueError(f"shares must be 'renormalized' or 'raw', got {shares!r}")
        if peak_scaling not in ("none", "kclkvl"):
            raise ValueError(
                f"peak_scaling must be 'none' or 'kclkvl', got {peak_scaling!r}")
        store = ParquetStore(self.store_path)

        # Stage 2 — calendar (fixed 365-day year; 8760-h data throughout).
        day_types = day_type_calendar(cfg.calendar_year)[:365]

        # Stages 1+3+4+5 — per-state class loads.
        fits = self._fit_all_states(cfg, store, day_types, residual)
        if smoothing == "qp":
            for abbrev, fit in fits.items():
                fit.class_loads = smooth_class_loads(fit.class_loads)
        elif smoothing != "none":
            raise ValueError(f"smoothing must be 'qp' or 'none', got {smoothing!r}")

        # Stage 6 — bus distribution + reactive power.
        bus = store.bus_table(region)
        n_bus = len(bus)
        state_codes = bus["state_code"].to_numpy()
        share_matrix = bus[_SHARE_COLS[shares]].to_numpy(dtype=np.float64)
        pf = draw_power_factors(n_bus, self.seed, region)

        p_load = np.zeros((n_bus, 8760))
        q_load = np.zeros((n_bus, 8760))
        for state in cfg.states:
            mask = state_codes == state.bus_state_code
            if not mask.any():
                raise ValueError(
                    f"{region}: no buses with state code {state.bus_state_code} "
                    f"({state.abbrev})")
            cl = fits[state.abbrev].class_loads
            p_load[mask] = distribute(cl, share_matrix[mask])
            q_load[mask] = reactive_power(cl, share_matrix[mask], pf[mask])

        # Optional KCL-KVL loadscaling (D16/H5): pin the coincident system
        # peak to the sum of the per-state peak loads (bus table col 16).
        # MATLAB: loadscaling = sum(unique(BusDist(:,16))) / max(sum(P_load));
        # we sum per-state firsts (identical unless two states' peaks tie).
        peak_scale = 1.0
        peak_target_mw = float(
            bus.groupby("state_code")["state_peak_mw"].first().sum())
        if peak_scaling == "kclkvl":
            system_peak = float(p_load.sum(axis=0).max())
            peak_scale = peak_target_mw / system_peak
            p_load *= peak_scale
            q_load *= peak_scale

        from loadsmith import __version__  # lazy: avoids the package-init cycle

        metadata = {
            "region": region,
            "loadsmith_version": __version__,
            "seed": self.seed,
            "smoothing": smoothing,
            "residual_override": residual,
            "shares": shares,
            "peak_scaling": peak_scaling,
            "peak_scale_factor": peak_scale,
            "peak_target_mw": peak_target_mw,
            "calendar_year": cfg.calendar_year,
            "matlab_source": cfg.matlab_source,
            "store": str(self.store_path),
        }

        # Stage 7 — outputs (optional) + validation.
        written: dict[str, Path] = {}
        if formats:
            writer = OutputWriter(
                self.output_dir, formats=formats, csv_header=write_csv_header)
            written = writer.write_region(
                region,
                bus["national_bus_num"].to_numpy(),
                bus["regional_bus_num"].to_numpy(),
                p_load, q_load, metadata)

        result = RunResult(
            region=region,
            national_bus_numbers=bus["national_bus_num"].to_numpy(),
            regional_bus_numbers=bus["regional_bus_num"].to_numpy(),
            p_load=p_load,
            q_load=q_load,
            metadata=metadata,
            written_files=written,
        )
        if validate:
            from loadsmith.validation import Validator

            result.validation_report = Validator().structural(
                region=region,
                state_loads={s.abbrev: store.state_load(region, s.abbrev)
                             for s in cfg.states},
                fits=fits,
                result=result,
                bus_state_codes=state_codes,
                config=cfg,
                smoothing=smoothing,
                shares=shares,
                residual_override=residual,
            )
        return result

    def run_all(
        self,
        *,
        parallel: bool = True,
        formats: Collection[OutputFormat] = ("csv", "parquet"),
        **kwargs,
    ) -> dict[str, RunResult]:
        """Run every registered region.

        Note: with ``parallel=True`` and ``formats=()`` the arrays are pickled
        back from worker processes (~1 GB total) — prefer per-region ``run()``
        calls or file formats for whole-fleet runs.
        """
        from loadsmith.regions import REGISTRY

        names = sorted(REGISTRY)
        if parallel and len(names) > 1:
            from concurrent.futures import ProcessPoolExecutor

            with ProcessPoolExecutor() as pool:
                futures = {
                    name: pool.submit(_run_region_worker,
                                      self.store_path, self.output_dir,
                                      self.seed, name, tuple(formats), kwargs)
                    for name in names
                }
                return {name: f.result() for name, f in futures.items()}
        return {name: self.run(name, formats=formats, **kwargs) for name in names}

    # ------------------------------------------------------------------ #

    def _fit_all_states(
        self,
        cfg: RegionConfig,
        store: ParquetStore,
        day_types: np.ndarray,
        residual: ResidualPolicy | None,
    ) -> dict[str, FitResult]:
        """Stage-4 fits for every state, honoring MISO-style combine groups."""
        cir_df = store.cir_fractions(cfg.name)
        cir_map = {
            row["state"]: (row["frac_c"], row["frac_i"], row["frac_r"])
            for _, row in cir_df.iterrows()
        }
        for s in cfg.states:
            if s.abbrev not in cir_map and not cfg.cir_hardcoded:
                raise KeyError(f"{cfg.name}: no CIR fractions for {s.abbrev}")
        if cfg.cir_hardcoded:  # CAISO
            cir_map.update(cfg.cir_hardcoded)

        # NYSEG basis is region-wide; NREL/utility bases are per state.
        nyseg_cache: NYSEGBasis | None = None

        def basis_for(state: StateConfig) -> BasisSource:
            nonlocal nyseg_cache
            if state.basis is BasisKind.NYSEG:
                if nyseg_cache is None:
                    nyseg_cache = NYSEGBasis(store.nyseg_profiles())
                return nyseg_cache
            if state.basis is BasisKind.NREL:
                assert state.nrel is not None, f"{state.abbrev}: missing NREL spec"
                profiles = store.nrel_profiles(cfg.name, state.nrel.city_folder)
                return NRELAggregateBasis(profiles, state.nrel)
            assert state.utility is not None, f"{state.abbrev}: missing utility spec"
            return UtilityBasis({
                role: store.utility_profiles(cfg.name, key)
                for role, key in state.utility.sources.items()
            })

        fits: dict[str, FitResult] = {}
        singles = [s for s in cfg.states if s.combine_group is None]
        groups: dict[str, list[StateConfig]] = {}
        for s in cfg.states:
            if s.combine_group is not None:
                groups.setdefault(s.combine_group, []).append(s)

        for state in singles:
            fits[state.abbrev] = fit_state(
                store.state_load(cfg.name, state.abbrev),
                basis_for(state),
                day_types,
                cir_map[state.abbrev],
                residual=residual or state.residual,
            )
        for name, members in groups.items():
            if len(members) != 2:
                raise ValueError(
                    f"{cfg.name}: combine group {name!r} must have exactly 2 "
                    f"states, got {[m.abbrev for m in members]}")
            a, b = members
            combined = fit_combined_states(
                {m.abbrev: store.state_load(cfg.name, m.abbrev) for m in members},
                {m.abbrev: cir_map[m.abbrev] for m in members},
                basis_for(a),   # combine groups share one basis (MISO: NYSEG)
                day_types,
                residual=residual or a.residual,
            )
            fits.update(combined)
        return fits

    @staticmethod
    def region_config(region: str) -> RegionConfig:
        """Look up a region's config from the registry (loadsmith.regions)."""
        from loadsmith.regions import REGISTRY

        try:
            return REGISTRY[region.upper()]
        except KeyError:
            known = ", ".join(sorted(REGISTRY))
            raise KeyError(f"unknown region {region!r}; known: {known}") from None


def _run_region_worker(store, output_dir, seed, name, formats, kwargs):
    """Module-level worker so ProcessPoolExecutor can pickle it (Windows spawn)."""
    return LoadSmith(store, output_dir, seed).run(name, formats=formats, **kwargs)
