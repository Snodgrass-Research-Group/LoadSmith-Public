"""Region config registry — one module per region (decision C5).

The registry AUTO-DISCOVERS configs: every module in this package that
exports a :class:`~loadsmith.config.RegionConfig` instance is registered
under its ``name``. Adding a region = adding one file (e.g. ``srtv.py``
with ``SRTV = RegionConfig(...)``) — no edits here, so regions
stay independent.

Configs are frozen constants extracted verbatim from the canonical MATLAB
scripts (provenance in each module and docs/conversion_manual/regions/).
Validation status: docs/conversion_manual/VALIDATION_MATRIX.md.
"""

from __future__ import annotations

import importlib
import pkgutil

from loadsmith.config import RegionConfig

REGISTRY: dict[str, RegionConfig] = {}

for _mod_info in pkgutil.iter_modules(__path__):
    _mod = importlib.import_module(f"{__name__}.{_mod_info.name}")
    for _val in vars(_mod).values():
        if isinstance(_val, RegionConfig):
            if _val.name in REGISTRY:
                raise ImportError(
                    f"duplicate RegionConfig for {_val.name!r} "
                    f"(module {_mod_info.name})")
            REGISTRY[_val.name] = _val

del _mod_info, _mod, _val  # noqa: F821 — keep the namespace clean
