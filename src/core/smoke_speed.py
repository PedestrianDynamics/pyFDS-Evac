from __future__ import annotations

from dataclasses import dataclass

import numpy as np

try:
    import fdsvismap as fv
except ModuleNotFoundError:
    fv = None


@dataclass
class SmokeSpeedConfig:
    """Configuration for the extinction-based smoke-speed model.

    The default coefficients follow the linear extinction correlation used by
    FDS+Evac / Lund-style smoke-speed reduction:

        speed_factor(K) = 1 + beta * K / alpha

    where:
    - K is the local extinction coefficient in 1/m
    - alpha = 0.706
    - beta = -0.057

    The resulting factor is clamped to [min_speed_factor, 1.0].
    """

    fds_dir: str
    update_interval_s: float = 1.0
    slice_height_m: float = 2.0
    alpha: float = 0.706
    beta: float = -0.057
    min_speed_factor: float = 0.2


class ExtinctionField:
    """Sample local smoke extinction K [1/m] from FDS slices via fdsvismap.

    This class intentionally treats extinction coefficient as the primary
    normative quantity for smoke-speed modelling. Derived visibility can still
    be computed elsewhere, but speed reduction is based directly on K.
    """

    def __init__(self, vis_map):
        self._vis = vis_map

    @classmethod
    def from_fds(
        cls,
        fds_dir: str,
        *,
        slice_height_m: float = 2.0,
    ) -> "ExtinctionField":
        if fv is None:
            raise ModuleNotFoundError(
                "fdsvismap is required to load extinction fields from FDS data."
            )
        vis = fv.VisMap(quantity="SOOT EXTINCTION COEFFICIENT")
        vis.read_fds_data(str(fds_dir), fds_slc_height=slice_height_m)
        return cls(vis)

    def sample_extinction(self, time_s: float, x: float, y: float) -> float:
        """Return the nearest-grid extinction coefficient K [1/m]."""
        extco_array = self._vis._get_extco_array_at_time(time_s)
        x_id = np.abs(self._vis.all_x_coords - x).argmin()
        y_id = np.abs(self._vis.all_y_coords - y).argmin()
        return float(extco_array[x_id, y_id])


class ConstantExtinctionField:
    """Return a constant extinction coefficient everywhere.

    This is primarily useful for deterministic verification cases such as
    ISO 20414 Table 21, where the corridor is assigned a uniform extinction
    coefficient before the evacuation run starts.
    """

    def __init__(self, extinction_per_m: float):
        self.extinction_per_m = float(extinction_per_m)

    def sample_extinction(self, time_s: float, x: float, y: float) -> float:
        del time_s, x, y
        return self.extinction_per_m


def speed_factor_from_extinction(
    extinction_per_m: float,
    *,
    alpha: float = 0.706,
    beta: float = -0.057,
    min_speed_factor: float = 0.2,
) -> float:
    """Convert extinction coefficient K [1/m] to a normalized speed factor.

    Reference model:
    - FDS+Evac applies the Frantzich/Nilsson data with a fractional speed
      reduction and variable minimum speed.
    - Ronchi et al. (2013) describe this as interpretation A3 and show that
      model results remain comparable when the same dataset and interpretation
      are used consistently across tools.
    - The implementation here follows the linear FDS+Evac/Lund relation:
      v(K) = v0 * (1 + beta * K / alpha)

    Notes:
    - This function returns the multiplicative factor v(K) / v0.
    - beta < 0 means speed decreases as extinction increases.
    - We clamp to a minimum speed factor instead of zero. That preserves the
      FDS+Evac-style fractional interpretation with a variable minimum speed:
      the minimum absolute speed is still proportional to the individual's
      clear-air speed.
    """

    if not np.isfinite(extinction_per_m):
        extinction_per_m = 0.0
    extinction_per_m = max(0.0, float(extinction_per_m))
    factor = 1.0 + (beta * extinction_per_m) / alpha
    return float(np.clip(factor, min_speed_factor, 1.0))


class SmokeSpeedModel:
    """Couple a sampled extinction field with the configured speed law.

    The field can come from `fdsvismap` for real FDS output or from a constant
    field for deterministic verification tests.
    """

    def __init__(self, field: ExtinctionField, config: SmokeSpeedConfig):
        self.field = field
        self.config = config

    def sample(self, time_s: float, x: float, y: float) -> tuple[float, float]:
        """Return `(extinction_K, speed_factor)` at the requested position/time."""
        extinction = self.field.sample_extinction(time_s, x, y)
        return extinction, speed_factor_from_extinction(
            extinction,
            alpha=self.config.alpha,
            beta=self.config.beta,
            min_speed_factor=self.config.min_speed_factor,
        )

    def speed_factor(self, time_s: float, x: float, y: float) -> float:
        """Return only the speed factor at the requested position/time."""
        _, factor = self.sample(time_s, x, y)
        return factor
