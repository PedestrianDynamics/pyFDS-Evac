"""The simulation time step ``simulationParams.dt`` (#922).

``dt`` is JuPedSim's step in seconds. The trajectory is written every
``OUTPUT_INTERVAL_S``, so its frame rate does not depend on ``dt``.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

DEFAULT_DT_S = 0.01
"""JuPedSim's own default step, used when a scenario sets no ``dt``."""

OUTPUT_INTERVAL_S = 0.1
"""Interval between written trajectory frames."""

_KEY = "simulationParams.dt"
_DIVISOR_TOL = 1e-9


def dt_from_params(sim_params: Mapping[str, Any]) -> float:
    """The step of a scenario: ``dt`` as a finite, positive number of seconds.

    A missing key gives ``DEFAULT_DT_S``. JuPedSim accepts 0, negative and
    NaN steps; with 0 or less the run would never reach its end time.
    """
    value = sim_params.get("dt", DEFAULT_DT_S)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{_KEY}={value!r} is not a number of seconds")
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{_KEY}={value!r} must be finite and greater than 0")
    return float(value)


def check_output_divisor(dt: float) -> None:
    """Raise unless ``OUTPUT_INTERVAL_S`` is a whole number of steps of *dt*."""
    steps = OUTPUT_INTERVAL_S / dt
    if abs(steps - round(steps)) > _DIVISOR_TOL:
        raise ValueError(
            f"{_KEY}={dt!r} does not divide the {OUTPUT_INTERVAL_S:g} s "
            "trajectory interval; use for example 0.1, 0.05, 0.025, 0.02, "
            "0.0125, 0.01 or 0.005"
        )


def checked_dt(sim_params: Mapping[str, Any]) -> float:
    """``dt_from_params`` that also requires the divisor rule (config rules)."""
    dt = dt_from_params(sim_params)
    check_output_divisor(dt)
    return dt


def output_stride(dt: float) -> int:
    """Steps between written trajectory frames (at least 1)."""
    return max(1, round(OUTPUT_INTERVAL_S / dt))


def large_step_warning(model_type: str, dt: float) -> str | None:
    """The warning for a force-based model above the default step, or None."""
    if model_type not in ("SocialForceModel", "GeneralizedCentrifugalForceModel"):
        return None
    if dt <= DEFAULT_DT_S:
        return None
    return (
        f"{model_type}: {_KEY}={dt:g} s is above {DEFAULT_DT_S:g} s; "
        "force-based models are untested at this step and may be unstable."
    )
