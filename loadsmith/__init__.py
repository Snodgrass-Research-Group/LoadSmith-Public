"""LoadSmith — hourly bus-level load-profile synthesis for EPIGRIDS grids.

Python port of the UW-Madison MATLAB time-series load code (13 NERC-ish
regions). Named for the GridForge / GridCrucible family.

Pipeline (see docs/conversion_manual/algorithms/00_pipeline_overview.md):
    ingest -> calendar -> basis -> daily NNLS fit -> smoothing ->
    bus distribution (+ reactive power) -> outputs -> validation

Typical use::

    from loadsmith import LoadSmith
    smith = LoadSmith(store="data/")
    result = smith.run("FRCC")

Status: all 13 regions implemented and validated
(docs/conversion_manual/VALIDATION_MATRIX.md).
"""

from loadsmith.core import LoadSmith

__version__ = "0.1.0"
__all__ = ["LoadSmith", "__version__"]
