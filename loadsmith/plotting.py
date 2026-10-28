"""Optional matplotlib diagnostics (decision C1) — import-guarded.

Replaces the useful subset of the MATLAB figures: fit-error histogram,
C/I/R class profiles, actual-vs-fitted overlays. Off by default; only
imported when a plot is requested, so matplotlib stays an optional extra.

Implementation status: SHELL (nice-to-have).
"""

from __future__ import annotations

import numpy as np


def plot_fit_error_histogram(residuals: np.ndarray, load: np.ndarray, title: str = ""):
    """MATLAB figure(6): histogram of (actual - fitted)/actual."""
    raise NotImplementedError("plotting is not implemented")


def plot_class_profiles(class_loads: np.ndarray, title: str = "", hours: slice | None = None):
    """MATLAB figure(11): C/I/R hourly profiles."""
    raise NotImplementedError("plotting is not implemented")
